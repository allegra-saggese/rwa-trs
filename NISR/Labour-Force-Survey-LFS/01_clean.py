"""
01_clean.py -- LFS: 1_Raw/<year>/LFS_<year>.dta  ->  2_Intermediate/LFS_<year>_person_clean.dta

Per year: lower-case names, build the harmonised key block (survey year wave round
quarter interview prov dist urban cluster psu hhid pid wt wt_round), keep every other
variable under its own name, destring numeric-looking strings, downcast, back-check,
write. Unit = person-interview (see NISR-Labour-Force-Survey-LFS.md (decisions log)).
"""
import json, sys
import numpy as np, pandas as pd
from lfs_helpers import (paths, get_logger, Checks, read_dta, write_dta, lower_names,
                         destring, downcast, save_json, LOGS)

log = get_logger("01_clean")
P = paths()
YEARS = [int(a) for a in sys.argv[1:]] or list(range(2017, 2026))

# NISR round numbering as labelled inside the 2020 file (0 = AUG16 ... 12 = NOV20); the
# 2021 file uses its own (2 = FEB17 ... 17 = NOV21). Rounds are carried as strings.
ROUNDS_2020 = {0: "AUG16", 1: "FEB17", 2: "AUG17", 3: "FEB18", 4: "AUG18", 5: "FEB19", 6: "MAY19",
               7: "AUG19", 8: "NOV19", 9: "FEB20", 10: "MAY20", 11: "AUG20", 12: "NOV20"}
ROUNDS_2021 = {2: "FEB17", 3: "AUG17", 4: "FEB18", 5: "AUG18", 6: "FEB19", 7: "MAY19", 8: "AUG19",
               9: "NOV19", 10: "FEB20", 11: "MAY20", 12: "AUG20", 13: "NOV20", 14: "FEB21",
               15: "MAY21", 16: "AUG21", 17: "NOV21"}
MONTH_Q = {"FEB": 1, "MAY": 2, "AUG": 3, "NOV": 4}

KEY_LABELS = {
    "survey": "Source survey", "year": "Survey year", "wave": "Wave (survey year)",
    "round": "Data-collection round as labelled by NISR (FEB17 ... NOV21); empty in 2022-2025 (not shipped)",
    "quarter": "Quarter (1 Feb, 2 May, 3 Aug, 4 Nov): from the round to 2021, from the file's block structure in 2023-2025; missing in 2022",
    "interview": "Interview number of the household within the year (1, 2): rank of the quarter where known; order of appearance in the file in 2022",
    "prov": "Province (1-5, NISR codes)", "dist": "District (11-57, NISR codes)",
    "urban": "Area of residence (1 urban, 2 rural)", "cluster": "Sampling cluster id (year_psu)",
    "psu": "Primary sampling unit number (NISR PSU_NO; anonymised)",
    "hhid": "Household id = PSU*100 + household number (unique with year + interview)",
    "pid": "Person number within the household (2025: row order within the household-interview; no person id shipped)", "sex": "Sex (1 male, 2 female)", "age": "Age in years",
    "wt": "Annual person weight (sums to population)",
    "wt_round": "Round weight (where released)", "hhid_nisr": "NISR household id as shipped (HHID)",
    "pid_nisr": "NISR person id as shipped (pid / pkey)",
}
KEY_ORDER = ["survey", "year", "wave", "round", "quarter", "interview", "prov", "dist", "urban",
             "cluster", "psu", "hhid", "pid", "sex", "age", "wt", "wt_round"]
PROV_LABELS = {1: "City of Kigali", 2: "Southern Province", 3: "Western Province", 4: "Northern Province", 5: "Eastern Province"}
URBAN_LABELS = {1: "Urban", 2: "Rural"}

# --- Value-label corrections from the questionnaires (NISR metadata errors found by the LFS audit of
#     2026-09-05 and verified against z_Documentation; see the notes file). Year None = every year in
#     which the variable carries value labels. Applied before writing and logged.
VALUE_LABEL_FIXES = {
    ("a02", 2024): {1: "Household Head", 2: "Spouse (Wife/Husband)", 3: "Child (Son/daughter)", 4: "Adopted/Foster/step child",
                    5: "Parent(Father/Mother)", 6: "Parent-in-law", 7: "Brother or Sister-In law", 8: "Brother or Sister",
                    9: "Grandchild", 10: "Son/Daughter-in-law", 11: "Other relative", 12: "Domestic worker",
                    13: "Non-relative", 14: "Unknown relationship", 98: "Don't Know", 99: "Missing"},
    #   2024 questionnaire A02 = the 14-code list above; the 2024 file shipped the pre-2024 11-code labels although its
    #   data follow the new list (codes 12-14 present; code 9 = grandchild has the pre-2024 code-5 frequencies).
    ("phase", None): {1: "February round", 2: "August round"},   # 2017/2018 files label 1/2 as February_<year>/August_<year>; the year is in `year`, the round in `round`
    ("d03a", 2019): {1: "Name of workplace"},   # 2019 file: "Valid name"; same category as every other year (the workplace has a name)
    ("b09", None): {2: "1-3 months"},          # questionnaires 2018, 2021, 2025: "1-3 months"; the files say "1- 2 months"
    ("d13", None): {5: "One year"},            # questionnaires 2017-2023: D13 code 5 = one year (files 2017/2022/2023: "Other(specify)")
    ("d16", None): {5: "Year"},                # questionnaires 2017-2023: D16 code 5 = year (files 2017/2022/2023: "Other(specify)")
    ("i03", None): {3: "Pit latrine without constructed floor slab", 4: "Pit latrine covered by concrete floor slab"},
    #   full texts as in the 2021 file; the other years' files truncate them ("... without constructed" / "floor slab")
}
DROP_VALUE_LABELS = {("d24", 2024)}   # 2024 questionnaire D24 = total number of years (0-70 in the data); the file kept the 2017 duration-band labels
VAR_LABEL_FIXES = {("d24", 2024): "Total work experience in years (2024 questionnaire D24; 2017 = duration bands, 2019-2023 = d24a)",
                   ("d24", 2025): "Total work experience in years (2025 questionnaire D24; 2017 = duration bands, 2019-2023 = d24a)",
                   ("a14b", 2024): "District of birth -- 2024 file mixes district codes (11-57) and sector codes (1101-5714; district = code // 100)",
                   ("d03b1", 2020): "ISIC code of the main job -- 2-digit divisions in the reduced 2020 file (4-digit classes in 2019, 2021)",
                   ("subhrs", 2022): "NISR subsistence hours = h02 x h03; in 2022-2023 both inputs are weekly hours, so this is NOT hours per week",
                   ("subhrs", 2023): "NISR subsistence hours = h02 x h03; in 2022-2023 both inputs are weekly hours, so this is NOT hours per week"}

# --- Universe (who was asked) per variable, from the questionnaires 2017-2025 (z_Documentation; see
#     NISR-Labour-Force-Survey-LFS.md (documentation notes)). Section universes did not change across years: A05 12+, A06-A11 5+, A25-A27
#     children 5-13, sections B-H 14+, section I and H05-H11 household level. NISR's derived labour-force
#     status (status1) is defined on 16+ in the 2017-2019 files and on 14+ from 2020 (verified in the data).
#     Patterns are regexes on the lower-cased variable name; first match wins.
UNIVERSE_LFS = [
    (r"^a05$", "household members aged 12+"), (r"^a(0[6-9]|1[01])a?$", "household members aged 5+ (disability, Washington Group)"),
    (r"^a2[5-9]", "children aged 5-13 (activities of children; not in the 2024-2025 questionnaires)"),
    (r"^a(1[2-9]|2[0-4])", "all household members (migration, absence)"),
    (r"^b\d", "household members aged 14+ (education)"), (r"^c\d", "household members aged 14+ (labour force identification)"),
    (r"^d\d|^ds\d", "employed members aged 14+ (main job)"), (r"^e\d", "employed members aged 14+ with a secondary job"),
    (r"^f\d", "members aged 14+ not in employment (past employment, income source)"),
    (r"^g\d", "household members aged 14+ (own-use production; domestic workers excluded from 2024)"),
    (r"^h0[1-4]$", "household members aged 14+ (subsistence foodstuff production)"), (r"^h(0[5-9]|1\d)$", "household level (family farm)"),
    (r"^i\d", "household level (housing and assets)"),
    (r"^(wap16|employed16|ur1|lfpr|youth|young|neet|yur1|age3_16_30)", "population aged 16+ (NISR indicator base)"),
    (r"^(tru|trur|plf|sub|luu|luur|lu[234]|discourage|willing|is|ie|iev2|ud|sm|main_sect|prod_unit|usualhrs|acthrs|usual_h|act_hrs|combhrs|subhrs|hr_own|timegood|timeservice)$",
     "labour-force population on the status1 universe (16+ in 2017-2019 files, 14+ from 2020)"),
    (r"^(cash|intcash|hr_cash|hr_cshmain)$", "employees (main job earnings)"),
    (r"^(isco|isic|indd0|inde0)", "employed (occupation / industry codes)"), (r"^(attained|indb|tvt|tvet)", "household members aged 14+ (education recodes)"),
]
def universe_for(y, cols):
    import re
    out = {}
    for c in cols:
        if c == "status1": out[c] = f"population aged {16 if y <= 2019 else 14}+ (NISR derived; see DECISIONS)"; continue
        for pat, txt in UNIVERSE_LFS:
            if re.match(pat, c): out[c] = txt; break
    return out

def ren(df, vl, vv, src, dst, srcmap):
    """rename src -> dst if present; record the mapping for the codebook."""
    if src in df.columns and dst not in df.columns:
        df.rename(columns={src: dst}, inplace=True)
        if src in vl: vl[dst] = vl.pop(src)
        if src in vv: vv[dst] = vv.pop(src)
        srcmap[dst] = src
        return True
    return False

meta_all = {}
for y in YEARS:
    log.info("---------------- %s ----------------", y)
    raw = P["raw"] / str(y) / f"LFS_{y}.dta"
    df, vl, vv = read_dta(raw)
    n_raw, k_raw = df.shape
    log.info("read %s: %s rows x %s vars", raw.name, f"{n_raw:,}", k_raw)
    df, vl, vv = lower_names(df, vl, vv, log)
    srcmap = {}
    ck = Checks(log)

    # ---- stamp
    df["survey"] = "LFS"; df["year"] = np.int16(y); df["wave"] = str(y)

    # ---- geography  (priority mirrors the old pipeline: code_dis > district; code_ur > ur)
    for s in ("code_dis", "district"):
        if ren(df, vl, vv, s, "dist", srcmap): break
    ren(df, vl, vv, "province", "prov", srcmap)
    for s in ("code_ur", "ur"):
        if ren(df, vl, vv, s, "urban", srcmap): break
    if "prov" not in df.columns:            # 2020: province not shipped; district code = prov*10 + seq
        df["prov"] = (df["dist"] // 10).astype("float64"); srcmap["prov"] = "derived: dist // 10"
        log.info("prov derived from dist // 10 (province not shipped in %s)", y)
    if "urban" not in df.columns:
        df["urban"] = np.nan; srcmap["urban"] = "not shipped"
    vv["prov"] = PROV_LABELS; vv["urban"] = URBAN_LABELS; vv["dist"] = vv.get("dist", {})

    # ---- weights
    if "weight2" in df.columns:
        ren(df, vl, vv, "weight2", "wt", srcmap)
        ren(df, vl, vv, "weight", "wt_round", srcmap)
    else:                                   # 2019: `weight` is the annual weight (label 'anual_weight')
        ren(df, vl, vv, "weight", "wt", srcmap)
    if "wt_round" not in df.columns: df["wt_round"] = np.nan; srcmap.setdefault("wt_round", "not shipped")

    # ---- ids: psu, hhid, pid, round
    if y in (2017, 2018):
        pid_raw = df["pid"].astype("int64")
        df["psu"] = df["psu_no"]; df["hhid"] = pid_raw // 100; df["pid"] = pid_raw % 100
        df["pid_nisr"] = pid_raw; srcmap.update(psu="psu_no", hhid="pid // 100", pid="pid % 100", pid_nisr="pid (NISR person id as shipped)")
        df["round"] = df["phase"].map({1: f"FEB{y % 100}", 2: f"AUG{y % 100}"}); srcmap["round"] = "phase"
    elif y == 2019:
        pk = df["pkey"].astype("int64")
        df["psu"] = pk // 1_000_000; df["hhid"] = pk // 10_000; df["pid"] = (pk // 100) % 100
        df["pid_nisr"] = pk; srcmap.update(psu="pkey // 1e6", hhid="pkey // 1e4", pid="(pkey // 100) % 100", pid_nisr="pkey")
        df["round"] = (pk % 100).map(ROUNDS_2020); srcmap["round"] = "pkey % 100 (2020-file numbering)"
    elif y == 2020:
        pid_raw = pd.to_numeric(df["pid"], errors="coerce")   # string; empty in rounds 10 and 12
        df["psu"] = df["psu_no"]; df["hhid"] = pid_raw // 100; df["pid"] = pid_raw % 100
        df["pid_nisr"] = pid_raw; srcmap.update(psu="psu_no", hhid="pid // 100 (missing in rounds 10, 12)", pid="pid % 100", pid_nisr="pid (NISR; empty in rounds 10, 12)")
        df["round"] = df["lfs_round"].map(ROUNDS_2020); srcmap["round"] = "lfs_round (2020-file numbering)"
    else:
        df["psu"] = df["psu_no"]; df["hhid_nisr"] = df["hhid"].astype("int64"); df["hhid"] = df["hhid_nisr"]
        srcmap.update(psu="psu_no", hhid="HHID (= PSU_NO*100 + QH_NO)", hhid_nisr="HHID")
        ck(bool((df["hhid"] == df["psu_no"] * 100 + df["qh_no"]).all()), "HHID == PSU_NO*100 + QH_NO")
        if "pid" in df.columns:
            df["pid_nisr"] = df["pid"].astype("int64"); df["pid"] = df["pid_nisr"] % 100; srcmap["pid"] = "pid % 100"; srcmap["pid_nisr"] = "pid (NISR person id as shipped)"
        else:                               # 2025 ships no person id: number people by row order within the interview
            df["pid"] = np.nan; srcmap["pid"] = "row order within household-interview (no pid shipped)"
        if y == 2021:
            df["round"] = df["lfs_round"].map(ROUNDS_2021); srcmap["round"] = "lfs_round (2021-file numbering)"
        else:
            df["round"] = ""; srcmap["round"] = "not shipped"
    df["quarter"] = df["round"].str[:3].map(MONTH_Q)
    ren(df, vl, vv, "a01", "sex", srcmap); ren(df, vl, vv, "a04", "age", srcmap)   # core demographics, native codes

    # ---- interview index within the year. 2021+: (hhid, wt) identifies the household-interview
    # (verified: exactly one head per group, and equal to LFS_round in 2021). 2023-2025 files are
    # stored in four quarter blocks (PSU_NO restarts) -> quarter from block position.
    if y >= 2021:
        blk = ((df["psu_no"].diff() < 0).cumsum() + 1).astype("int8")
        if y >= 2023:
            ck(blk.max() == 4, f"file holds 4 quarter blocks (found {blk.max()})")
            df["quarter"] = blk; srcmap["quarter"] = "position block in file (PSU_NO restarts) -- see DECISIONS"
        grp = df.groupby(["hhid", "wt"], sort=False).ngroup()
        first = pd.Series(np.arange(len(df))).groupby(grp).transform("min")
        df["interview"] = pd.DataFrame({"h": df["hhid"].values, "f": first.values}).groupby("h")["f"].rank(method="dense").astype("int8").values
        if y == 2021: ck(bool((df["interview"] == df.groupby("hhid")["quarter"].rank(method="dense")).all()), "interview index == rank of LFS_round within household")
        if df["pid"].isna().all():
            df["pid"] = df.groupby([df["hhid"], df["wt"]]).cumcount() + 1
    else:
        df["interview"] = df.groupby("hhid")["quarter"].rank(method="dense") if y != 2020 else np.nan
        if y == 2020:
            ok = df["hhid"].notna()
            df.loc[ok, "interview"] = df[ok].groupby("hhid")["quarter"].rank(method="dense")
    df["cluster"] = df["year"].astype(str) + "_" + df["psu"].astype("Int64").astype(str)

    # ---- everything else: destring, downcast
    df = destring(df, log, skip=("survey", "wave", "round", "cluster"))
    for c, t in KEY_LABELS.items():
        if c in df.columns: vl[c] = t
    for (v, yy), fix in VALUE_LABEL_FIXES.items():          # questionnaire-verified corrections of NISR's labels (see above)
        if v in df.columns and ((yy is None and v in vv) or yy == y):
            vv[v] = {**vv.get(v, {}), **fix}; log.info("value labels corrected from the questionnaire: %s codes %s", v, sorted(fix))
    for (v, yy) in DROP_VALUE_LABELS:
        if v in df.columns and yy == y and v in vv: del vv[v]; log.info("stale value labels dropped: %s (continuous in %s)", v, y)
    for (v, yy), txt in VAR_LABEL_FIXES.items():
        if v in df.columns and yy == y: vl[v] = txt
    if "status1" in df.columns:   # NISR's own label says 16+ or 14+ inconsistently with the data; state the verified universe
        lo = 16 if y <= 2019 else 14
        miss = int(df.loc[df["age"] >= lo, "status1"].isna().sum())
        ck(df.loc[df["age"] < lo, "status1"].isna().all() and df.loc[df["age"] >= lo, "status1"].notna().mean() > 0.99,
           f"status1 populated on ages {lo}+ and empty below (threshold 99%): {miss:,} rows aged {lo}+ without status1" + (" -- all of MAY20 age 14" if y == 2020 else ""), hard=False)
        vl["status1"] = f"Labour force status (NISR derived; population aged {lo}+: 1 employed, 2 unemployed, 3 outside the labour force)"
    df = downcast(df, keep_double=("wt", "wt_round", "hhid", "hhid_nisr", "pid_nisr", "pkey"))
    df = df[KEY_ORDER + [c for c in df.columns if c not in KEY_ORDER]]

    # ---- back-checks
    ck(len(df) == n_raw, f"row count unchanged ({n_raw:,})")
    ck(df["wt"].notna().all() and (df["wt"] > 0).all(), "wt present and > 0 on every row")
    hk = df["hhid"].notna()   # methodology (LFS 2021 Annex B): the calibrated household weight is assigned to every member
    ck(bool((df[hk].groupby(["hhid", "interview"], dropna=False)["wt"].nunique() <= 1).all()), "wt constant within household-interview (household-level calibrated weight)")
    ck(df["dist"].nunique() == 30, f"30 districts (found {df['dist'].nunique()})")
    ck(df["prov"].nunique() == 5, f"5 provinces (found {df['prov'].nunique()})")
    ck(set(df["sex"].dropna().unique()) <= {1, 2}, "sex (a01) in {1,2}")
    ck(df["age"].between(0, 120).all(), f"age (a04) in [0,120] (min {df['age'].min()}, max {df['age'].max()})")
    hh = df[df["hhid"].notna()]
    heads = hh.groupby(["hhid", "interview"])["a02"].apply(lambda s: int((s == 1).sum()))
    ck(heads.eq(1).mean() > 0.999, f"one head per household-interview (threshold 99.9%; exceptions reported in 03_checks): {heads.eq(1).mean():.4%} of {len(heads):,} (0 heads: {(heads==0).sum()}, 2+: {(heads>1).sum()})")
    ndup = int(hh.duplicated(["hhid", "interview", "pid"]).sum())
    ck(ndup <= 5, f"(hhid, interview, pid) unique up to NISR's own duplicates: {ndup} duplicate rows (kept, see DECISIONS)", hard=False)
    log.info("share of rows with a household key: %.3f", df["hhid"].notna().mean())
    log.info("rounds: %s", df["round"].value_counts(dropna=False).to_dict())
    log.info("weighted total (sum wt) = %s ; wap16-weighted = %s", f"{df['wt'].sum():,.0f}",
             f"{(df['wap16'] * df['wt']).sum():,.0f}" if "wap16" in df else "n/a")
    ck.done()

    out = P["inter"] / f"LFS_{y}_person_clean.dta"
    write_dta(df, out, vl, vv, f"Rwanda LFS {y} person-interview file (cleaned)", log)
    meta_all[y] = {"n": len(df), "vars": list(df.columns), "var_labels": vl,
                   "value_labels": {k: v for k, v in vv.items() if k in df.columns}, "source": srcmap,
                   "dtypes": {c: str(df[c].dtype) for c in df.columns}, "universe": universe_for(y, df.columns)}
    save_json(meta_all[y], LOGS / f"clean_{y}_meta.json")
log.info("01_clean done for %s", YEARS)
