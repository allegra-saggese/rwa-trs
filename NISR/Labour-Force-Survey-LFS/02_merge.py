"""
02_merge.py -- LFS: 2_Intermediate/LFS_<year>_person_clean.dta -> 3_Final/LFS_pooled_person.dta
                    + per-year household files                 -> 3_Final/LFS_pooled_household.dta

Alignment rule (applied identically in every NISR dataset): years are grouped into
"versions" of a variable by label similarity (token Jaccard >= 0.25 to the group's first
label). The largest group keeps the variable's name; the others become <name>_v2, _v3 ...
in order of first appearance. FORCE_ALIGN lists variables whose rewording the data owner
judged to be the same question. Value labels are unioned within a version; conflicts
recorded. Everything is written to logs/merge_alignment.json for the codebook.
"""
import json
from collections import Counter, defaultdict
import numpy as np, pandas as pd
from lfs_helpers import (paths, get_logger, Checks, read_dta, write_dta, downcast, to_plain_float,
                         resolve_object_columns, label_similarity, save_json, LOGS)

log = get_logger("02_merge")
P = paths(); ck = Checks(log)
YEARS = list(range(2017, 2026))
KEYS = ["survey", "year", "wave", "round", "quarter", "interview", "prov", "dist", "urban",
        "cluster", "psu", "hhid", "pid", "sex", "age", "wt", "wt_round"]
SIM_THRESHOLD = 0.25
# Same question, reworded (checked against the questionnaires and value labels; see DECISIONS.md):
FORCE_ALIGN = {"b01", "d03a", "d06", "d23", "lu2", "psu_no", "status1"}   # status1: same codes, label now states the year-specific age base
# Force a separate version for given years even if labels look alike (none needed so far):
FORCE_SPLIT = {}   # e.g. {"d05": [2025]}

# ---------------------------------------------------------------- load per-year files
data, labels, vlabs = {}, {}, {}
for y in YEARS:
    df, vl, vv = read_dta(P["inter"] / f"LFS_{y}_person_clean.dta")
    data[y], labels[y], vlabs[y] = df, vl, vv
    log.info("loaded %s: %s rows x %s vars", y, f"{len(df):,}", df.shape[1])

# ---------------------------------------------------------------- alignment decisions
def version_groups(v, yrs, labs):
    """Greedy grouping of years by label similarity; returns list of year-lists, largest first."""
    if v in KEYS or v in FORCE_ALIGN or len(yrs) == 1: return [list(yrs)]
    groups = []            # [(representative_label, [years])]
    for y in yrs:
        if v in FORCE_SPLIT and y in FORCE_SPLIT[v]:
            groups.append((labs[y], [y])); continue
        for rep, ys in groups:
            if not labs[y] or not rep or label_similarity(labs[y], rep) >= SIM_THRESHOLD:   # no label = no evidence of a change
                ys.append(y); break
        else:
            groups.append((labs[y], [y]))
    groups.sort(key=lambda g: (-len(g[1]), -max(g[1])))     # biggest group keeps the base name
    return [ys for _, ys in groups]

allvars = sorted({c for df in data.values() for c in df.columns})
decisions, label_variants, vl_conflicts, colname = {}, {}, {}, {}   # colname[(v, y)] -> column in pool
for v in allvars:
    yrs = [y for y in YEARS if v in data[y].columns]
    labs = {y: (labels[y].get(v) or "").strip() for y in yrs}
    groups = version_groups(v, yrs, labs)
    versions = {}
    for i, ys in enumerate(groups):
        name = v if i == 0 else f"{v}_v{i + 1}"
        versions[name] = ys
        for y in ys: colname[(v, y)] = name
    decisions[v] = {"years": yrs, "versions": versions, "labels_by_year": labs,
                    "reference_label": labs[groups[0][-1]]}
    if len(set(l for l in labs.values() if l)) > 1: label_variants[v] = labs
    if len(groups) > 1: log.info("VERSIONS %s: %s", v, {n: ys for n, ys in versions.items()})

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
                    vl_conflicts.setdefault(c, {}).setdefault(str(code), set()).update([merged[code], txt])
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
vl_conflicts = {k: {c: sorted(s) for c, s in d.items()} for k, d in vl_conflicts.items()}
log.info("pooled person file: %s rows x %s vars; %d variables with >1 version; %d value-label text conflicts",
         f"{len(person):,}", person.shape[1], sum(len(d["versions"]) > 1 for d in decisions.values()), len(vl_conflicts))
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
           "value_label_conflicts": vl_conflicts,
           "person": {"rows": len(person), "vars": list(person.columns)},
           "household": {"rows": len(household), "vars": list(household.columns)}},
          LOGS / "merge_alignment.json")
ck.done(); log.info("02_merge done")
