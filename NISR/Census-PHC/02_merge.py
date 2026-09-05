"""
02_merge.py -- Census: 2_Intermediate/Census_<year>_person_clean.dta -> 3_Final/Census_pooled_person.dta
                    + per-year household files                 -> 3_Final/Census_pooled_household.dta

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
Rule (b) and FORCE_SPLIT groups follow the LFS / Census audits of 2026-09-05.
"""
import difflib, json, re
from collections import Counter, defaultdict
import numpy as np, pandas as pd
from census_helpers import (paths, get_logger, Checks, read_dta, write_dta, downcast, to_plain_float,
                         resolve_object_columns, label_similarity, save_json, LOGS)

log = get_logger("02_merge")
P = paths(); ck = Checks(log)
YEARS = [2002, 2012, 2022]
KEYS = ["survey", "year", "wave", "prov", "dist", "sector", "urban", "cluster", "hhid", "pid", "sex", "age", "wt", "wt_hh"]
SIM_THRESHOLD = 0.25      # variable-label similarity (token Jaccard) for two years to be the same question
VL_THRESHOLD = 0.6        # value-label text similarity (difflib ratio) for the same code to mean the same thing
# Same question, reworded (checked against the questionnaires and value labels; see NISR-Census-PHC.md (decisions log)):
FORCE_ALIGN = set()
# Same name, different question or coding: closed groups of years (a year, or a list of years pooled together).
# p13 handicap (2002) vs insurance (2012); p22 occupation ISCO-88 (2002) vs activities done (2012); p26 marital status
# (2002) vs status in employment (2012); h08 rooms for sleeping (2012) vs rooms (2022) -- found while harmonising 2026-09-05.
# Census audit 2026-09-05: h01 habitat and h02 dwelling type recoded in 2022 (2022 code 2 = integrated model village,
# 3 = old settlement; h02 3/4 = storey building one / many households, 5-7 new); p19 highest diploma 2002 (1 = none,
# 7 = MA/PhD) vs 2012 (0 = none, 1 = CE/FE, 7 = MA, 8 = PhD). The value-label rule splits them too; listed to be explicit.
FORCE_SPLIT = {"p13": [2002], "p22": [2002], "p26": [2002], "h08": [2012], "h01": [2022], "h02": [2022], "p19": [2002]}

# ---------------------------------------------------------------- load per-year files
data, labels, vlabs = {}, {}, {}
for y in YEARS:
    df, vl, vv = read_dta(P["inter"] / f"Census_{y}_person_clean.dta")
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
    if v in KEYS or v in FORCE_ALIGN or len(yrs) == 1: return [list(yrs)], []
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
            if labs[y] and rep and label_similarity(labs[y], rep) < SIM_THRESHOLD:       # no label = no evidence of a change
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
    stale = {y: sorted(_obs(data[y][v]) - set(vls[y]) - SENTINELS)[:20] for y in yrs if len(set(vls[y]) - SENTINELS) >= 3}   # categorical variables only
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
person = pd.concat(frames, ignore_index=True, sort=False)
person = resolve_object_columns(person, log, keep_str=("survey", "wave", "cluster", "novprov", "novdistr", "novsect"))
person = person[KEYS + [c for c in person.columns if c not in KEYS]]
person = downcast(person, keep_double=("wt", "wt_hh", "hhid", "probability"))
vl_text_conflicts = {k: {c: sorted(s) for c, s in d.items()} for k, d in vl_text_conflicts.items()}
log.info("pooled person file: %s rows x %s vars; %d variables with >1 version; %d value-label text conflicts",
         f"{len(person):,}", person.shape[1], sum(len(d["versions"]) > 1 for d in decisions.values()), len(vl_text_conflicts))
ck(not any(person[c].dtype == object and person[c].dropna().map(lambda x: isinstance(x, (int, float, np.integer, np.floating))).any()
           for c in person.columns), "no numeric column left object-typed after concat")

ck(len(person) == sum(len(d) for d in data.values()), "pooled rows == sum of yearly rows")
for y in YEARS:
    ck(abs(person.loc[person.year == y, "wt"].sum() - data[y]["wt"].sum()) < 1e-6, f"{y}: sum wt preserved in pool")
write_dta(person, P["final"] / "Census_pooled_person.dta", var_labels, value_labels,
          "Rwanda Census 2002/2012/2022 pooled person file (public-use samples, repeated cross-section)", log)

# ---------------------------------------------------------------- household files
# Household-level = the key block (geography and weights taken from the HEAD, p02 == 1: NISR ships a few
# households whose members disagree, e.g. 89 on urban in 2002 -- counted and logged), every H-block / household
# variable constant within (year, hhid) that is not a person-block item (p##, rp##) and not entirely missing in the
# wave, plus hhsize (roster count) and the head's sex/age; wt = household weight. 2002 collective households are
# excluded. (Census audit 2026-09-05: the previous rule dropped 2002 urban because of the 89 households.)
HEAD_FIELDS = ["prov", "dist", "sector", "urban", "cluster", "wt_hh"]
PERSON_BLOCK = re.compile(r"^r?p\d")
hh_frames, hh_vl, hh_vv, hh_inconsistent = [], {}, {}, {}
for y in YEARS:
    df = data[y]; vl, vv = labels[y], vlabs[y]
    d = df[df["collective"] == 0] if "collective" in df.columns else df
    log.info("%s: %s of %s rows in ordinary households", y, f"{len(d):,}", f"{len(df):,}")
    g = d.groupby("hhid", sort=False)
    nun = g.nunique(dropna=False)
    const = [c for c in d.columns if c != "hhid" and c not in ("pid", "pid_nisr", "sex", "age", "wt") and c not in HEAD_FIELDS
             and not PERSON_BLOCK.match(c) and (nun[c] <= 1).all() and d[c].notna().any()]
    hh = g[const].first().reset_index()
    hh["hhsize"] = g.size().values
    head = d[d["p02"] == 1].drop_duplicates("hhid").set_index("hhid")[[c for c in HEAD_FIELDS if c in d.columns] + ["sex", "age"]]
    hh = hh.merge(head.rename(columns={"sex": "head_sex", "age": "head_age"}), left_on="hhid", right_index=True, how="left")
    hh_inconsistent[y] = {c: int((nun[c] > 1).sum()) for c in HEAD_FIELDS if c in nun.columns and (nun[c] > 1).any()}
    if hh_inconsistent[y]: log.warning("%s: households whose members disagree on a key field (head's value used): %s", y, hh_inconsistent[y])
    hh["wt"] = hh["wt_hh"]
    hh = hh.rename(columns={v: colname[(v, y)] for v in hh.columns if (v, y) in colname and colname[(v, y)] != v})
    hh_frames.append(to_plain_float(hh))
    for c in hh.columns: hh_vl[c] = var_labels.get(c) or vl.get(c) or hh_vl.get(c) or ""
    for c in const:
        n = colname.get((c, y), c)
        if c in vv: hh_vv[n] = {**hh_vv.get(n, {}), **vv[c]}
    ck(not hh.duplicated(["hhid"]).any(), f"{y}: household rows unique")
    ck(hh["head_sex"].notna().all(), f"{y}: every household has a head")
    ck(hh["urban"].notna().all() and hh["dist"].notna().all(), f"{y}: geography from the head is complete on every household")
    log.info("%s: %s households, %d household-level variables carried (person-block and all-missing columns excluded)", y, f"{len(hh):,}", len(const))
household = pd.concat(hh_frames, ignore_index=True, sort=False)
household = resolve_object_columns(household, log, keep_str=("survey", "wave", "cluster", "novprov", "novdistr", "novsect"))
hkeys = [k for k in KEYS if k in household.columns]
household = household[hkeys + [c for c in household.columns if c not in hkeys]]
hh_vl.update({"hhsize": "Household size (persons in the public-use roster)", "wt": "Household weight (sums to the number of households)",
              "head_sex": "Sex of household head (sex of p02==1)", "head_age": "Age of household head (age of p02==1)"})
hh_vv["head_sex"] = value_labels.get("sex", {})
household = downcast(household, keep_double=("wt", "wt_hh", "hhid", "probability"))
write_dta(household, P["final"] / "Census_pooled_household.dta", hh_vl, hh_vv,
          "Rwanda Census 2002/2012/2022 pooled household file (public-use samples)", log)
for y in YEARS:
    hy = household[household.year == y]
    hy = hy[[c for c in hy.columns if c in hkeys or hy[c].notna().any()]]        # per-wave file: only the columns the wave carries
    write_dta(hy, P["inter"] / f"Census_{y}_household_clean.dta", hh_vl, hh_vv, f"Rwanda Census {y} household file (cleaned)", log)

save_json({"threshold": SIM_THRESHOLD, "force_align": sorted(FORCE_ALIGN), "force_split": FORCE_SPLIT, "decisions": decisions, "label_variants": label_variants,
           "value_label_conflicts": vl_text_conflicts, "stale_labels": stale_labels, "vl_threshold": VL_THRESHOLD,
           "person": {"rows": len(person), "vars": list(person.columns)},
           "household": {"rows": len(household), "vars": list(household.columns), "head_fields": HEAD_FIELDS,
                         "inconsistent_households": hh_inconsistent}},
          LOGS / "merge_alignment.json")
ck.done(); log.info("02_merge done")
