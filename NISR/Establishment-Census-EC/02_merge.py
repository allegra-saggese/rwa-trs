"""
02_merge.py -- EC: 2_Intermediate/EC_<year>_establishment_clean.dta -> 3_Final/EC_pooled_establishment.dta
                    + per-year household files                 -> 3_Final/EC_pooled_household.dta

Alignment rule: years are grouped into "versions" of a variable when (a) their variable labels
describe the same question (token Jaccard >= SIM_THRESHOLD to the group's first label) AND
(b) their value labels are compatible -- no code whose text means something else (normalised
text equal, both missing-like, one contained in the other, or difflib ratio >= VL_THRESHOLD),
and an unlabelled year's values stay inside the labelled years' code range. The largest group
keeps the variable's name; the others become <name>_v2, _v3 ... in order of first appearance.
FORCE_ALIGN lists variables whose rewording the data owner judged to be the same question;
FORCE_SPLIT lists closed groups of years that must stay apart. Value labels are unioned within
a version (only compatible rewordings remain; the latest year's text wins and the variants are
recorded). Codes observed in the data but absent from a year's own value labels are reported
as "stale labels". Everything is written to logs/merge_alignment.json for the codebook.
Rule (b), FORCE_ALIGN and FORCE_SPLIT follow the EC audit of 2026-09-05.
"""
import difflib, json, re
from collections import Counter, defaultdict
import numpy as np, pandas as pd
from ec_helpers import (paths, get_logger, Checks, read_dta, write_dta, downcast, to_plain_float,
                         resolve_object_columns, label_similarity, save_json, LOGS)

log = get_logger("02_merge")
P = paths(); ck = Checks(log)
YEARS = [2011, 2014, 2017, 2020, 2023]
KEYS = ["survey", "year", "wave", "prov", "dist", "sector", "urban", "estid", "wt"]
SIM_THRESHOLD = 0.25      # variable-label similarity (token Jaccard) for two years to be the same question
VL_THRESHOLD = 0.6        # value-label text similarity (difflib ratio) for the same code to mean the same thing
# Same question, reworded: the 2023 questionnaire relabels the industry section and the worker counts (verified same codes /
# same concepts -- EC audit 2026-09-05); start_y: 2020 and 2023 share the same bins (2023 adds two), 2017 is split below.
FORCE_ALIGN = {"q6_1", "male_worker", "female_worker", "total_workers", "rwandan_workers", "foregner_workers", "foreign_male", "foreign_female",
               "rwandan_male", "rwandan_female"}
# Same name, different coding or universe (EC audit 2026-09-05), closed groups:
FORCE_SPLIT = {"start_y": [2017, 2023],    # 18 three-year bins in 2017; 7 bins in 2020 (7 = not stated); 9 in 2023 (7 = 2021-2023): three codings
               "q20": [2023], "q21": [2023],   # turnover / capital brackets recut in 2023 (7 brackets; code 5 = 50-400 million, not > 50 million)
               "q9": [2023],                 # owner nationality: 2023 codes 4-7 = Europe / America / Asia / Oceania (2017-20: 4 = other foreign, 5-8 joint)
               "owner_age": [2023]}          # 2017-20: derived, broadly populated; 2023 = the conditional Q14 item (owner not the manager), 4,849 rows

# ---------------------------------------------------------------- load per-year files
data, labels, vlabs = {}, {}, {}
for y in YEARS:
    df, vl, vv = read_dta(P["inter"] / f"EC_{y}_establishment_clean.dta")
    data[y], labels[y], vlabs[y] = df, vl, vv
    log.info("loaded %s: %s rows x %s vars", y, f"{len(df):,}", df.shape[1])

# ---------------------------------------------------------------- alignment decisions
SENTINELS = {98, 99, 998, 999, 9998, 9999}       # NISR's don't-know / missing codes: never evidence of a coding change
MISSING_LIKE = {"not stated", "missing", "dont know", "dk", "unknown", "not known", "non determine", "nd", "ns", "not applicable", "na"}
_SYN = {"others": "other", "yego": "yes", "oya": "no", "specify": "", "please": "", "specified": ""}
def _norm(s):
    toks = [_SYN.get(w, w) for w in re.sub(r"[^a-z0-9]+", " ", str(s).lower()).split()]
    return " ".join(w for w in toks if w)
def _same(x, y):
    """same category? normalised texts equal, both missing-like, one's tokens contained in the other's
    ('Other' ~ 'Other (specify)', 'Cement' ~ 'Cement/pavement'), or close spelling (difflib ratio >= VL_THRESHOLD)"""
    a, b = _norm(x), _norm(y)
    if a == b or (a in MISSING_LIKE and b in MISSING_LIKE): return True
    ta, tb = set(a.split()), set(b.split())
    if ta and tb and (ta <= tb or tb <= ta): return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= VL_THRESHOLD
def vl_conflicts(a, b):
    """codes labelled in both years whose texts do not describe the same category: {code: (text_a, text_b)}"""
    return {c: (a[c], b[c]) for c in set(a) & set(b) if c not in SENTINELS and not _same(a[c], b[c])}
def _range(s):
    s = pd.to_numeric(s, errors="coerce") if s.dtype == object else s
    if not pd.api.types.is_numeric_dtype(s): return None
    s = s[s.notna() & ~s.isin(SENTINELS)]
    return (float(s.min()), float(s.max())) if len(s) else None
def _obs(s):
    s = pd.to_numeric(s, errors="coerce") if s.dtype == object else s
    return set(s.dropna().unique().tolist()) if pd.api.types.is_numeric_dtype(s) else set()
def incompatible(y, z, vls, rng):
    """reason why year y cannot share a column with year z, or None"""
    a, b = vls.get(y) or {}, vls.get(z) or {}
    if a and b:
        c = vl_conflicts(a, b)
        if c: return f"{y} vs {z}: value labels differ -- " + "; ".join(f"{k}: {p!r} vs {q!r}" for k, (p, q) in sorted(c.items())[:3])
    elif a or b:                                  # one side labelled: the other side's values must not exceed the labelled (non-sentinel) codes
        lab, u = (a, z) if a else (b, y)
        codes = [c for c in lab if c not in SENTINELS]
        r = rng.get(u)
        if len(codes) >= 2 and r and r[1] > max(codes):
            return f"{y} vs {z}: {u} is unlabelled and its values reach {r[1]:g}, beyond the labelled codes ({min(codes):g}-{max(codes):g})"
    return None

def version_groups(v, yrs, labs, vls, rng):
    """Greedy grouping of years: a year joins the first group whose variable label is similar AND whose value
    labels are compatible with every member; FORCE_SPLIT groups are closed. Returns (year-lists largest first, reasons)."""
    if v in KEYS or len(yrs) == 1: return [list(yrs)], []
    forced = {}
    for i, g in enumerate(FORCE_SPLIT.get(v, [])):
        for y in ([g] if not isinstance(g, list) else g): forced[y] = i
    groups, reasons = [], []
    for y in yrs:
        if y in forced:
            key = ("__forced__", forced[y])
            for rep, ys in groups:
                if rep == key: ys.append(y); break
            else: groups.append((key, [y])); reasons.append(f"{y}: FORCE_SPLIT")
            continue
        for rep, ys in groups:
            if isinstance(rep, tuple): continue                                         # closed group
            if v not in FORCE_ALIGN and labs[y] and rep and label_similarity(labs[y], rep) < SIM_THRESHOLD:       # FORCE_ALIGN skips this test only; no label = no evidence of a change
                reasons.append(f"{y} vs {ys[0]}: variable label differs ({labs[y][:40]!r} vs {rep[:40]!r})"); continue
            why = next((w for z in ys for w in [incompatible(y, z, vls, rng)] if w), None)
            if why: reasons.append(why); continue
            ys.append(y); break
        else:
            groups.append((labs[y], [y]))
    groups.sort(key=lambda g: (-len(g[1]), -max(g[1])))     # biggest group keeps the base name
    return [ys for _, ys in groups], (reasons if len(groups) > 1 else [])

allvars = sorted({c for df in data.values() for c in df.columns})
decisions, label_variants, vl_text_conflicts, colname, stale_labels = {}, {}, {}, {}, {}   # colname[(v, y)] -> column in pool
for v in allvars:
    yrs = [y for y in YEARS if v in data[y].columns]
    labs = {y: (labels[y].get(v) or "").strip() for y in yrs}
    vls = {y: (vlabs[y].get(v) or {}) for y in yrs}
    rng = {y: _range(data[y][v]) for y in yrs}
    groups, reasons = version_groups(v, yrs, labs, vls, rng)
    stale = {y: sorted(_obs(data[y][v]) - set(vls[y]) - SENTINELS)[:20] for y in yrs if len(set(vls[y]) - SENTINELS) >= 3}
    stale = {y: s for y, s in stale.items() if s}
    if stale: stale_labels[v] = stale
    versions = {}
    for i, ys in enumerate(groups):
        name = v if i == 0 else f"{v}_v{i + 1}"
        versions[name] = ys
        for y in ys: colname[(v, y)] = name
    decisions[v] = {"years": yrs, "versions": versions, "labels_by_year": labs,
                    "reference_label": labs[groups[0][-1]], "split_reasons": reasons}
    if len(set(l for l in labs.values() if l)) > 1: label_variants[v] = labs
    if len(groups) > 1: log.info("VERSIONS %s: %s | %s", v, {n: ys for n, ys in versions.items()}, " / ".join(reasons[:2]))
log.info("%d variables with codes observed outside their own value labels (stale labels; listed in merge_alignment.json): %s", len(stale_labels), sorted(stale_labels)[:30])

# ---------------------------------------------------------------- apply, pool persons
frames, var_labels, value_labels = [], {}, {}
for y in YEARS:
    df, vl, vv = data[y].copy(), labels[y], vlabs[y]
    ren = {v: colname[(v, y)] for v in df.columns if colname[(v, y)] != v}
    df = df.rename(columns=ren)
    for c in df.columns:
        v = next((k for k, n in ren.items() if n == c), c)
        var_labels[c] = vl.get(v) or var_labels.get(c) or ""            # most recent year's label wins
        if v in vv:
            merged = value_labels.get(c, {})
            for code, txt in vv[v].items():
                if code in merged and str(merged[code]).strip().lower() != str(txt).strip().lower():
                    vl_text_conflicts.setdefault(c, {}).setdefault(str(code), set()).update([merged[code], txt])
                merged[code] = txt                                        # most recent year's text wins
            value_labels[c] = merged
    frames.append(to_plain_float(df))
for c in list(var_labels):
    if "_v" in c and c.rsplit("_v", 1)[-1].isdigit():
        base = c.rsplit("_v", 1)[0]; ys = decisions[base]["versions"][c]
        var_labels[c] = f"[{ys[0]}-{ys[-1]} version] " + var_labels[c][:60]

def drop_exact_duplicates(df, name, log):
    """Matteo's rule (2026-09-05): a saved dataset holds no duplicated rows (Stata `duplicates drop`, all variables).
    Returns the frame without exact duplicates and the dropped rows per wave (+ their weight)."""
    dup = df.duplicated(keep="first")
    if not dup.any(): return df, {}, {}
    key = "wave" if "wave" in df.columns else "year"
    rows = {str(k): int(v) for k, v in df.loc[dup, key].value_counts().items()}
    wts = {str(k): float(v) for k, v in df.loc[dup].groupby(key)["wt"].sum().items()} if "wt" in df.columns else {}
    log.info("  %s: %d exact duplicate rows dropped (duplicates drop, all variables): %s", name, int(dup.sum()), rows)
    return df.loc[~dup].reset_index(drop=True), rows, wts
person = pd.concat(frames, ignore_index=True, sort=False)
person = resolve_object_columns(person, log, keep_str=("survey", "wave", "s001", "s002", "s003", "q22_other"))
person = person[KEYS + [c for c in person.columns if c not in KEYS]]
person = downcast(person, keep_double=("wt", "estid", "key"))
vl_text_conflicts = {k: {c: sorted(s) for c, s in d.items()} for k, d in vl_text_conflicts.items()}
log.info("pooled person file: %s rows x %s vars; %d variables with >1 version; %d value-label text conflicts",
         f"{len(person):,}", person.shape[1], sum(len(d["versions"]) > 1 for d in decisions.values()), len(vl_text_conflicts))
ck(not any(person[c].dtype == object and person[c].dropna().map(lambda x: isinstance(x, (int, float, np.integer, np.floating))).any()
           for c in person.columns), "no numeric column left object-typed after concat")

ck(len(person) == sum(len(d) for d in data.values()), "pooled rows == sum of yearly rows")
for y in YEARS:
    ck(abs(person.loc[person.year == y, "wt"].sum() - data[y]["wt"].sum()) < 1e-6, f"{y}: sum wt preserved in pool")
person, DUP_ROWS, DUP_WT = drop_exact_duplicates(person, "EC_pooled_establishment.dta", log)
write_dta(person, P["final"] / "EC_pooled_establishment.dta", var_labels, value_labels,
          "Rwanda Establishment Census 2011-2023 pooled establishment file", log)

save_json({"threshold": SIM_THRESHOLD, "force_align": sorted(FORCE_ALIGN), "force_split": FORCE_SPLIT, "decisions": decisions, "label_variants": label_variants,
           "value_label_conflicts": vl_text_conflicts, "stale_labels": stale_labels, "vl_threshold": VL_THRESHOLD,
           "establishment": {"rows": len(person), "vars": list(person.columns)}, "duplicates_dropped": {"EC_pooled_establishment.dta": DUP_ROWS}, "wt_dropped": {"EC_pooled_establishment.dta": DUP_WT}},
          LOGS / "merge_alignment.json")
ck.done(); log.info("02_merge done")
