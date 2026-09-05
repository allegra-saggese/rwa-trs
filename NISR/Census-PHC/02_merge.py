"""
02_merge.py -- Census: 2_Intermediate/Census_<year>_person_clean.dta -> 3_Final/Census_pooled_person.dta
                    + per-year household files                 -> 3_Final/Census_pooled_household.dta

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
from census_helpers import (paths, get_logger, Checks, read_dta, write_dta, downcast, to_plain_float,
                         resolve_object_columns, label_similarity, save_json, LOGS)

log = get_logger("02_merge")
P = paths(); ck = Checks(log)
YEARS = [2002, 2012, 2022]
KEYS = ["survey", "year", "wave", "prov", "dist", "sector", "urban", "cluster", "hhid", "pid", "sex", "age", "wt", "wt_hh"]
SIM_THRESHOLD = 0.25
# Same question, reworded (checked against the questionnaires and value labels; see DECISIONS.md):
FORCE_ALIGN = set()      # filled after reading the first VERSIONS log; see DECISIONS.md
# Force a separate version for given years even if labels look alike:
# same name, different question, but labels too alike for the 0.25 threshold (found while harmonising, 2026-09-05):
# p13 handicap (2002) vs insurance (2012); p22 occupation ISCO-88 (2002) vs activities done (2012);
# p26 marital status (2002) vs status in employment (2012); h08 rooms for sleeping (2012) vs rooms (2022).
FORCE_SPLIT = {"p13": [2002], "p22": [2002], "p26": [2002], "h08": [2012]}

# ---------------------------------------------------------------- load per-year files
data, labels, vlabs = {}, {}, {}
for y in YEARS:
    df, vl, vv = read_dta(P["inter"] / f"Census_{y}_person_clean.dta")
    data[y], labels[y], vlabs[y] = df, vl, vv
    log.info("loaded %s: %s rows x %s vars", y, f"{len(df):,}", df.shape[1])

# ---------------------------------------------------------------- alignment decisions
def version_groups(v, yrs, labs):
    """Greedy grouping of years by label similarity; returns list of year-lists, largest first."""
    if v in KEYS or v in FORCE_ALIGN or len(yrs) == 1: return [list(yrs)]
    groups = []            # [(representative_label, [years])]
    for y in yrs:
        if v in FORCE_SPLIT and y in FORCE_SPLIT[v]:
            groups.append(("__forced__", [y])); continue   # closed group: nothing else may join it
        for rep, ys in groups:
            if rep != "__forced__" and (not labs[y] or not rep or label_similarity(labs[y], rep) >= SIM_THRESHOLD):   # no label = no evidence of a change
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
person = resolve_object_columns(person, log, keep_str=("survey", "wave", "cluster", "novprov", "novdistr", "novsect"))
person = person[KEYS + [c for c in person.columns if c not in KEYS]]
person = downcast(person, keep_double=("wt", "wt_hh", "hhid", "probability"))
vl_conflicts = {k: {c: sorted(s) for c, s in d.items()} for k, d in vl_conflicts.items()}
log.info("pooled person file: %s rows x %s vars; %d variables with >1 version; %d value-label text conflicts",
         f"{len(person):,}", person.shape[1], sum(len(d["versions"]) > 1 for d in decisions.values()), len(vl_conflicts))
ck(not any(person[c].dtype == object and person[c].dropna().map(lambda x: isinstance(x, (int, float, np.integer, np.floating))).any()
           for c in person.columns), "no numeric column left object-typed after concat")

ck(len(person) == sum(len(d) for d in data.values()), "pooled rows == sum of yearly rows")
for y in YEARS:
    ck(abs(person.loc[person.year == y, "wt"].sum() - data[y]["wt"].sum()) < 1e-6, f"{y}: sum wt preserved in pool")
write_dta(person, P["final"] / "Census_pooled_person.dta", var_labels, value_labels,
          "Rwanda Census 2002/2012/2022 pooled person file (public-use samples, repeated cross-section)", log)

# ---------------------------------------------------------------- household files
# Household-level = every variable constant within (year, hhid), plus hhsize (roster count)
# and the head's sex/age; wt = household weight. 2002 collective households are excluded.
hh_frames, hh_vl, hh_vv = [], {}, {}
for y in YEARS:
    df = data[y]; vl, vv = labels[y], vlabs[y]
    d = df[df["collective"] == 0] if "collective" in df.columns else df
    log.info("%s: %s of %s rows in ordinary households", y, f"{len(d):,}", f"{len(df):,}")
    g = d.groupby("hhid", sort=False)
    const = [c for c in d.columns if c not in ("pid", "pid_nisr", "sex", "age", "wt") and (g[c].nunique(dropna=False) <= 1).all()]
    hh = g[const].first().reset_index(drop=True)
    hh["hhsize"] = g.size().values
    head = d[d["p02"] == 1].groupby("hhid", sort=False)[["sex", "age"]].first()
    hh = hh.merge(head.rename(columns={"sex": "head_sex", "age": "head_age"}), left_on="hhid", right_index=True, how="left")
    hh["wt"] = hh["wt_hh"]
    hh = hh.rename(columns={v: colname[(v, y)] for v in hh.columns if (v, y) in colname and colname[(v, y)] != v})
    hh_frames.append(to_plain_float(hh))
    for c in hh.columns: hh_vl[c] = var_labels.get(c) or vl.get(c) or hh_vl.get(c) or ""
    for c in const:
        n = colname.get((c, y), c)
        if c in vv: hh_vv[n] = {**hh_vv.get(n, {}), **vv[c]}
    ck(not hh.duplicated(["hhid"]).any(), f"{y}: household rows unique")
    ck(hh["head_sex"].notna().all(), f"{y}: every household has a head")
    log.info("%s: %s households, %d household-level variables carried", y, f"{len(hh):,}", len(const))
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
    write_dta(household[household.year == y], P["inter"] / f"Census_{y}_household_clean.dta", hh_vl, hh_vv,
              f"Rwanda Census {y} household file (cleaned)", log)

save_json({"threshold": SIM_THRESHOLD, "force_align": sorted(FORCE_ALIGN), "force_split": FORCE_SPLIT, "decisions": decisions, "label_variants": label_variants,
           "value_label_conflicts": vl_conflicts,
           "person": {"rows": len(person), "vars": list(person.columns)},
           "household": {"rows": len(household), "vars": list(household.columns)}},
          LOGS / "merge_alignment.json")
ck.done(); log.info("02_merge done")
