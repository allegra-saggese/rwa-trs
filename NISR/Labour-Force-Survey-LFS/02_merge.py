"""
02_merge.py -- LFS: 2_Intermediate/LFS_<year>_person_clean.dta -> 3_Final/LFS_pooled_person.dta
                    + per-year household files                 -> 3_Final/LFS_pooled_household.dta

Alignment rule: years are grouped into "versions" of a variable when (a) their variable labels
describe the same question (token Jaccard >= SIM_THRESHOLD to the group's first label) AND
(b) their value labels are compatible -- no code whose text means something else (difflib
ratio < VL_THRESHOLD after normalisation), and an unlabelled year's values stay inside the
labelled years' code range. The largest group keeps the variable's name; the others become
<name>_v2, _v3 ... in order of first appearance. FORCE_ALIGN lists variables whose rewording
the data owner judged to be the same question; FORCE_SPLIT lists closed groups of years that
must stay apart (same name, different question or coding). Value labels are unioned within a
version (only compatible rewordings remain; the latest year's text wins and the variants are
recorded). Codes observed in the data but absent from a year's own value labels are reported
as "stale labels". Everything is written to logs/merge_alignment.json for the codebook.
Rule (b) and FORCE_SPLIT groups were added after the LFS audit of 2026-09-05.
"""
import difflib, json, re
from collections import Counter, defaultdict
import numpy as np, pandas as pd
from lfs_helpers import (paths, get_logger, Checks, read_dta, write_dta, downcast, to_plain_float,
                         resolve_object_columns, label_similarity, save_json, LOGS)

log = get_logger("02_merge")
P = paths(); ck = Checks(log)
YEARS = list(range(2017, 2026))
KEYS = ["survey", "year", "wave", "round", "quarter", "interview", "prov", "dist", "urban",
        "cluster", "psu", "hhid", "pid", "sex", "age", "wt", "wt_round"]
SIM_THRESHOLD = 0.25      # variable-label similarity (token Jaccard) for two years to be the same question
VL_THRESHOLD = 0.6        # value-label text similarity (difflib ratio) for the same code to mean the same thing
# Same question, reworded (checked against the questionnaires and value labels; see NISR-Labour-Force-Survey-LFS.md (decisions log)):
FORCE_ALIGN = {"b01", "d03a", "d06", "lu2", "psu_no", "status1"}   # status1: same codes, label states the year-specific age base.
#   d23 removed 2026-09-05 (LFS audit): 2025 recodes 7/8/11 and adds 12/13 -> the value-label rule splits it.
# Same name, different question or coding: each entry lists closed groups (a year, or a list of years pooled together)
# that must not join the other years. Verified against the questionnaires and the data (LFS audit 2026-09-05):
FORCE_SPLIT = {
    "a02": [[2024, 2025]],        # relationship to head recoded to 14 codes from 2024 (the 2024 file's stale labels are corrected in 01_clean)
    "d24": [[2024, 2025]],        # total experience: duration bands 1-6 in 2017, number of years 0-75 in 2024-2025 (2019-2023 ship it as d24a)
    "a14b": [2024],               # district of birth: the 2024 file mixes district codes (11-57) and sector codes (1101-5714)
    "d03b1": [2020],              # ISIC of the main job: 4-digit classes in 2019/2021, 2-digit divisions in the reduced 2020 file
    "h02": [[2021, 2022, 2023]],  # 2021-2023 = hours per week in the last 7 days (median 12, max 61); other years = days per week (<= 7)
    "h03": [[2021, 2022, 2023]],  # 2021-2023 = usual hours per week (median 18); other years = hours per day
    "subhrs": [[2022, 2023]],     # NISR's h02*h03: product of two weekly-hours measures in 2022-2023 (median 216); hours per week from 2024
}

# ---------------------------------------------------------------- load per-year files
data, labels, vlabs = {}, {}, {}
for y in YEARS:
    df, vl, vv = read_dta(P["inter"] / f"LFS_{y}_person_clean.dta")
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
    """same category? normalised texts equal, both missing-like, one's tokens contained in the other's ('Other' ~ 'Other (specify)',
    '16-30' ~ 'Youth (16-30 yrs)', 'Cement' ~ 'Cement/pavement'), or close spelling (difflib ratio >= VL_THRESHOLD)"""
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
person = resolve_object_columns(person, log, keep_str=("survey", "wave", "round", "cluster"))
person = person[KEYS + [c for c in person.columns if c not in KEYS]]
person = downcast(person, keep_double=("wt", "wt_round", "hhid", "hhid_nisr", "pid_nisr", "pkey"))
vl_text_conflicts = {k: {c: sorted(s) for c, s in d.items()} for k, d in vl_text_conflicts.items()}
log.info("pooled person file: %s rows x %s vars; %d variables with >1 version; %d value-label text conflicts",
         f"{len(person):,}", person.shape[1], sum(len(d["versions"]) > 1 for d in decisions.values()), len(vl_text_conflicts))
ck(not any(person[c].dtype == object and person[c].dropna().map(lambda x: isinstance(x, (int, float, np.integer, np.floating))).any()
           for c in person.columns), "no numeric column left object-typed after concat")

ck(len(person) == sum(len(d) for d in data.values()), "pooled rows == sum of yearly rows")
for y in YEARS:
    ck(abs(person.loc[person.year == y, "wt"].sum() - data[y]["wt"].sum()) < 1e-6, f"{y}: sum wt preserved in pool")
write_dta(person, P["final"] / "LFS_pooled_person.dta", var_labels, value_labels,
          "Rwanda LFS 2017-2025 pooled person-interview file (repeated cross-section)", log)

# ---------------------------------------------------------------- household files
# Household-level = every variable constant within (year, hhid, interview) in that year,
# plus hhsize (roster count) and the head's sex/age. Rows without a household key are dropped
# (2020 rounds 10 and 12), and that loss is logged.
hh_frames, hh_vl, hh_vv = [], {}, {}
for y in YEARS:
    df = data[y]; vl, vv = labels[y], vlabs[y]
    keep = df["hhid"].notna()
    log.info("%s: %s of %s rows have a household key", y, f"{keep.sum():,}", f"{len(df):,}")
    d = df[keep]
    g = d.groupby(["hhid", "interview"], sort=False)
    const = [c for c in d.columns if c not in ("pid", "pid_nisr", "sex", "age") and (g[c].nunique(dropna=False) <= 1).all()]
    hh = g[const].first().reset_index(drop=True)
    hh["hhsize"] = g.size().values
    head = d[d["a02"] == 1].groupby(["hhid", "interview"], sort=False)[["sex", "age"]].first()
    hh = hh.merge(head.rename(columns={"sex": "head_sex", "age": "head_age"}), left_on=["hhid", "interview"], right_index=True, how="left")
    hh = hh.rename(columns={v: colname[(v, y)] for v in hh.columns if (v, y) in colname and colname[(v, y)] != v})
    hh_frames.append(to_plain_float(hh))
    for c in hh.columns: hh_vl[c] = var_labels.get(c) or vl.get(c) or hh_vl.get(c) or ""
    for c in const:
        n = colname.get((c, y), c)
        if c in vv: hh_vv[n] = {**hh_vv.get(n, {}), **vv[c]}
    ck(not hh.duplicated(["hhid", "interview"]).any(), f"{y}: household-interview rows unique")
    log.info("%s: %s household-interviews, %d household-level variables carried", y, f"{len(hh):,}", len(const))
household = pd.concat(hh_frames, ignore_index=True, sort=False)
household = resolve_object_columns(household, log, keep_str=("survey", "wave", "round", "cluster"))
hkeys = [k for k in KEYS if k in household.columns]
household = household[hkeys + [c for c in household.columns if c not in hkeys]]
hh_vl.update({"hhsize": "Household size (persons listed in this interview)",
              "head_sex": "Sex of household head (sex of a02==1)", "head_age": "Age of household head (age of a02==1)"})
hh_vv["head_sex"] = value_labels.get("sex", {})
household = downcast(household, keep_double=("wt", "wt_round", "hhid", "hhid_nisr"))
write_dta(household, P["final"] / "LFS_pooled_household.dta", hh_vl, hh_vv,
          "Rwanda LFS 2017-2025 pooled household-interview file", log)
for y in YEARS:
    write_dta(household[household.year == y], P["inter"] / f"LFS_{y}_household_clean.dta", hh_vl, hh_vv,
              f"Rwanda LFS {y} household-interview file (cleaned)", log)

save_json({"threshold": SIM_THRESHOLD, "force_align": sorted(FORCE_ALIGN), "force_split": FORCE_SPLIT, "decisions": decisions, "label_variants": label_variants,
           "value_label_conflicts": vl_text_conflicts, "stale_labels": stale_labels, "vl_threshold": VL_THRESHOLD,
           "person": {"rows": len(person), "vars": list(person.columns)},
           "household": {"rows": len(household), "vars": list(household.columns)}},
          LOGS / "merge_alignment.json")
ck.done(); log.info("02_merge done")
