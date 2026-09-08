"""
02_merge.py -- WBES: 2_Intermediate/WBES_<wave>_establishment_clean.dta -> 3_Final/WBES_pooled_establishment.dta

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
One row per establishment-round: 2006, 2011, 2019 and 2023 stacked (1,171 firm-rounds). The World Bank
already stacks 2006-2019 in its panel file with the same questionnaire codes, so the rule mostly has to
decide whether a 2023 item (the redesigned BEE questionnaire) is the same question as its 2019 namesake.
Names: the per-year files are read back under the native names (variable_names.csv inverted) and the rule
works on the native labels and value labels saved by 01_clean in logs/clean_<wave>_meta.json; the pooled file
is written under the clean names and labels of variable_names.csv (scope pooled:WBES_pooled_establishment.dta).
"""
import difflib, json, re
from collections import Counter, defaultdict
import numpy as np, pandas as pd
from wbes_helpers import (paths, get_logger, Checks, read_dta, write_dta, downcast, to_plain_float,
                          resolve_object_columns, label_similarity, save_json, LOGS, HERE, NameTable, DATASET_TAG)

log = get_logger("02_merge")
P = paths(); ck = Checks(log)
NAMES = NameTable(HERE / "variable_names.csv", DATASET_TAG); POOLED = "pooled:WBES_pooled_establishment.dta"
YEARS = ["2006", "2011", "2019", "2023"]           # rounds; the column is `wave` (string), `year` is its integer
KEYS = ["survey", "year", "wave", "idstd", "id", "panelid", "panel", "a2", "a3a", "a3", "a4a", "a4b",
        "a6a", "a6b", "strata", "stratificationregioncode", "wstrict", "wmedian", "wweak"]
SIM_THRESHOLD = 0.25      # variable-label similarity (token Jaccard) for two years to be the same question
VL_THRESHOLD = 0.6        # value-label text similarity (difflib ratio) for the same code to mean the same thing
# Same question, reworded across rounds (fill in as the questionnaires are read; nothing forced yet):
FORCE_ALIGN: set[str] = set()
# Same name, different question or coding: closed groups of rounds that must not join the others.
FORCE_SPLIT: dict[str, list] = {}

# ---------------------------------------------------------------- load per-year files
def _code(k):
    """value-label code as saved in the meta file (json string) -> the number pyreadstat returns for a .dta"""
    try: f = float(k)
    except (TypeError, ValueError): return k
    return int(f) if f.is_integer() else f
data, labels, vlabs = {}, {}, {}
for y in YEARS:
    df, vl, vv = read_dta(P["inter"] / f"WBES_{y}_establishment_clean.dta")
    meta = json.load(open(LOGS / f"clean_{y}_meta.json"))
    inv = {c: n for n, c in (meta.get("clean_names") or {}).items()}        # exactly the names 01_clean wrote; falls back to the table
    df = df.rename(columns=inv) if inv else NAMES.invert(df, vl, vv, f"wave:{y}")[0]   # native names; native labels and value labels from the meta file
    vl = {c: meta["var_labels"].get(c, "") for c in df.columns}
    vv = {c: {_code(k): t for k, t in d.items()} for c, d in meta["value_labels"].items() if c in df.columns}
    data[y], labels[y], vlabs[y] = df, vl, vv
    log.info("loaded %s: %s rows x %s vars", y, f"{len(df):,}", df.shape[1])

# ---------------------------------------------------------------- alignment decisions
SENTINELS = {98, 99, 998, 999, 9998, 9999}       # the shipped don't-know / missing codes: never evidence of a coding change
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
    groups.sort(key=lambda g: (-len(g[1]), -max(int(y) for y in g[1])))     # biggest group keeps the base name; ties to the later round
    return [ys for _, ys in groups], (reasons if len(groups) > 1 else [])

allvars = sorted({c for df in data.values() for c in df.columns})
taken = set(allvars)         # 2023 ships names that already end in a version suffix (a4b_v4, d1a2_v4): never reuse one
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
        name = v
        if i:
            k = i + 1
            while f"{v}_v{k}" in taken: k += 1
            name = f"{v}_v{k}"; taken.add(name)
        versions[name] = ys
        for y in ys: colname[(v, y)] = name
    decisions[v] = {"years": yrs, "versions": versions, "labels_by_wave": labs,
                    "reference_label": labs[groups[0][-1]], "split_reasons": reasons}
    if len(set(l for l in labs.values() if l)) > 1: label_variants[v] = labs
    if len(groups) > 1: log.info("VERSIONS %s: %s | %s", v, {n: ys for n, ys in versions.items()}, " / ".join(reasons[:2]))
log.info("%d variables with codes observed outside their own value labels (stale labels; listed in merge_alignment.json): %s", len(stale_labels), sorted(stale_labels)[:30])

# ---------------------------------------------------------------- apply the decisions, pool the rounds
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
        d = decisions.get(c.rsplit("_v", 1)[0])
        if not d or c not in d["versions"]: continue          # a shipped name that merely looks like a version
        ys = d["versions"][c]
        var_labels[c] = f"[{ys[0]}-{ys[-1]} version] " + var_labels[c][:60]

def drop_exact_duplicates(df, name, log):
    """Matteo's rule (2026-09-05): a saved dataset holds no duplicated rows (Stata `duplicates drop`, all variables).
    Returns the frame without exact duplicates and the dropped rows per wave (+ their weight)."""
    dup = df.duplicated(keep="first")
    if not dup.any(): return df, {}, {}
    key = "wave" if "wave" in df.columns else "year"
    rows = {str(k): int(v) for k, v in df.loc[dup, key].value_counts().items()}
    wts = {str(k): float(v) for k, v in df.loc[dup].groupby(key)["wstrict"].sum().items()} if "wstrict" in df.columns else {}
    log.info("  %s: %d exact duplicate rows dropped (duplicates drop, all variables): %s", name, int(dup.sum()), rows)
    return df.loc[~dup].reset_index(drop=True), rows, wts
est = pd.concat(frames, ignore_index=True, sort=False)
est = resolve_object_columns(est, log, keep_str=("survey", "wave", "panel"))
est = est[[c for c in KEYS if c in est.columns] + [c for c in est.columns if c not in KEYS]]   # a key a round never asked is simply absent
est = downcast(est, keep_double=("idstd", "id", "panelid", "wstrict", "wmedian", "wweak"))
vl_text_conflicts = {k: {c: sorted(s) for c, s in d.items()} for k, d in vl_text_conflicts.items()}
log.info("pooled establishment file: %s rows x %s vars; %d variables with >1 version; %d value-label text conflicts",
         f"{len(est):,}", est.shape[1], sum(len(d["versions"]) > 1 for d in decisions.values()), len(vl_text_conflicts))
ck(not any(est[c].dtype == object and est[c].dropna().map(lambda x: isinstance(x, (int, float, np.integer, np.floating))).any()
           for c in est.columns), "no numeric column left object-typed after concat")

ck(len(est) == sum(len(d) for d in data.values()), "pooled rows == sum of yearly rows")
for y in YEARS:
    ck(abs(est.loc[est.wave == y, "wstrict"].sum() - data[y]["wstrict"].sum()) < 1e-6, f"{y}: the strict weight total is preserved in the pool")
est, DUP_ROWS, DUP_WT = drop_exact_duplicates(est, "WBES_pooled_establishment.dta", log)
out, vl_out, vv_out, CLEAN = NAMES.apply(est, var_labels, value_labels, POOLED, log)      # clean names, labels and value labels
write_dta(out, P["final"] / "WBES_pooled_establishment.dta", vl_out, vv_out,
          "World Bank Enterprise Surveys Rwanda 2006-2023 pooled establishment file", log)

save_json({"threshold": SIM_THRESHOLD, "force_align": sorted(FORCE_ALIGN), "force_split": FORCE_SPLIT, "decisions": decisions, "label_variants": label_variants,
           "value_label_conflicts": vl_text_conflicts, "stale_labels": stale_labels, "vl_threshold": VL_THRESHOLD,
           "establishment": {"rows": len(est), "vars": list(est.columns), "clean_vars": list(out.columns)}, "clean_names": CLEAN, "duplicates_dropped": {"WBES_pooled_establishment.dta": DUP_ROWS}, "wt_dropped": {"WBES_pooled_establishment.dta": DUP_WT}},
          LOGS / "merge_alignment.json")
ck.done(); log.info("02_merge done")
