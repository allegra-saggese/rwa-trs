"""
01_harmonize.py -- NISR/Harmonize: harmonised copies of every final and appended file of the seven datasets.

For EVERY file in <dataset>/3_Final/ and <dataset>/2_Intermediate/appended/:
  * identical key-block labels (survey year wave prov dist sector urban hhid pid sex age wt wt_hh) and
    identical province / district / sector / urban / sex value labels;
  * h_hhkey / h_pkey: string keys unique across datasets and waves (survey_wave[_interview]_hhid[_pid]);
  * nothing dropped, no rows lost, native variables untouched (renamed/labelled in place only).
For the PERSON files of the household surveys (LFS, Census, EICV incl. VUP, AHS) the common concepts are
added as new h_* variables next to the native ones (never overwriting them):
  h_sex h_marital h_relation h_attend h_educ h_literacy h_lfstatus h_employed h_lfs_def h_empstat
  h_isic1 h_isic1_approx h_isco1 h_isco1_approx
For HOUSEHOLD files: h_head_sex h_head_age (+ h_head_marital h_head_educ h_head_literacy for CFSVA, whose
household file carries the head's characteristics directly); CFSVA woman file: h_educ h_literacy.
Every code mapping is written to harmonization_map.csv (dataset, waves, file, h_variable, source, rule,
level, quality, note). Scope and code lists: the project notes NISR-Harmonize.md (Green Jobs - TRS folder).
"""
import csv, os, shutil, sys, time
import numpy as np, pandas as pd
from harmonize_helpers import (DATASETS, ds_paths, out_dir, alignment, decisions_for, col_for, get_logger, Checks,
                               read_dta, read_dta_typed, read_meta, write_dta, downcast_new, save_json, recode, flat, rule_text, LOGS, db_root)

log = get_logger("01_harmonize"); P_OUT = out_dir(); ck = Checks(log)
ONLY = sys.argv[1:]                                    # optional: dataset tags to (re)build, e.g. LFS Census
MIN_FREE_GB = 12.0                                     # never fill the disk: skip a file if less would remain (the Mac needs room for Dropbox and swap)
STAMP = time.strftime("%Y-%m-%d")

# ------------------------------------------------------------------ common labels
KEY_LABELS = {
    "survey": "Source dataset (LFS, Census, EICV, EC, AHS, SAS, CFSVA)", "year": "Reference year of the wave",
    "wave": "Wave / round id within the dataset (string)", "sample": "Sample (CS national, VUP booster, PANEL)",
    "round": "Data-collection round (LFS)", "quarter": "Quarter of the round (1 Feb, 2 May, 3 Aug, 4 Nov)",
    "interview": "Interview number of the household within the year (LFS)",
    "prov": "Province, NISR code 1-5", "dist": "District, NISR code 11-57 (prov*10 + sequence)",
    "sector": "Sector, NISR code 1101-5715 (dist*100 + sequence)", "urban": "Area of residence: 1 urban, 2 rural",
    "cluster": "Sampling cluster id (string, dataset-specific)", "hhid": "Household id as built by the dataset pipeline (unique within wave [+ interview])",
    "pid": "Person number within the household", "sex": "Sex: 1 male, 2 female", "age": "Age in completed years",
    "wt": "Weight that sums to the population of the file's unit (person / household / establishment / plot)",
    "wt_hh": "Household weight (same value on every member)", "estid": "Establishment id (EC)",
    "h_hhkey": "Harmonised household key: survey_wave[_interview]_hhid (string, unique across datasets)",
    "h_pkey": "Harmonised person key: h_hhkey_pid (string)",
}
geo = pd.read_csv(db_root() / "geodata-nisr" / "Village_Boundary_2022_924768113126413998.csv")
SECT = geo.drop_duplicates("Sector ID")[["Province ID", "Province", "District ID", "District", "Sector ID", "Sector"]]
PROV_L = {int(k): s for k, s in SECT.drop_duplicates("Province ID")[["Province ID", "Province"]].values}
DIST_L = {int(k): s for k, s in SECT.drop_duplicates("District ID")[["District ID", "District"]].values}
SECT_L = {int(k): s for k, s in SECT[["Sector ID", "Sector"]].values}
KEY_VALUES = {"prov": PROV_L, "dist": DIST_L, "sector": SECT_L, "urban": {1: "Urban", 2: "Rural"}, "sex": {1: "Male", 2: "Female"}}

H_LABELS = {
    "h_sex": "Sex (harmonised): 1 male, 2 female", "h_marital": "Marital status (harmonised, 4 groups)",
    "h_relation": "Relationship to household head (harmonised, 5 groups)", "h_attend": "Ever attended school (harmonised)",
    "h_educ": "Highest level of education attended (harmonised, 4 levels)", "h_literacy": "Can read and write (harmonised)",
    "h_lfstatus": "Labour-force status (harmonised codes; definition in h_lfs_def)", "h_employed": "Employed (harmonised; definition in h_lfs_def)",
    "h_lfs_def": "Definition and age base behind h_lfstatus / h_employed", "h_empstat": "Status in employment, main job (harmonised, 5 groups)",
    "h_isic1": "Industry of main job, ISIC Rev.4 section (harmonised 1-21)", "h_isic1_approx": "h_isic1 from an older/national classification (approximate)",
    "h_isco1": "Occupation of main job, ISCO-08 major group (harmonised 0-9)", "h_isco1_approx": "h_isco1 from an older/national classification (approximate)",
    "h_head_sex": "Sex of household head (harmonised)", "h_head_age": "Age of household head (harmonised)",
    "h_head_marital": "Marital status of household head (harmonised, 4 groups)", "h_head_educ": "Education of household head (harmonised, 4 levels)",
    "h_head_literacy": "Household head can read and write (harmonised)",
}
ISIC = {1: "A Agriculture, forestry and fishing", 2: "B Mining and quarrying", 3: "C Manufacturing", 4: "D Electricity, gas, steam and air conditioning",
        5: "E Water supply, sewerage, waste management", 6: "F Construction", 7: "G Wholesale and retail trade, repair of vehicles",
        8: "H Transportation and storage", 9: "I Accommodation and food service", 10: "J Information and communication",
        11: "K Financial and insurance activities", 12: "L Real estate", 13: "M Professional, scientific and technical", 14: "N Administrative and support services",
        15: "O Public administration and defence", 16: "P Education", 17: "Q Human health and social work", 18: "R Arts, entertainment and recreation",
        19: "S Other service activities", 20: "T Households as employers", 21: "U Extraterritorial organisations"}
ISCO = {0: "Armed forces occupations", 1: "Managers", 2: "Professionals", 3: "Technicians and associate professionals", 4: "Clerical support workers",
        5: "Service and sales workers", 6: "Skilled agricultural, forestry and fishery workers", 7: "Craft and related trades workers",
        8: "Plant and machine operators and assemblers", 9: "Elementary occupations"}
H_VALUES = {
    "h_sex": {1: "Male", 2: "Female"},
    "h_marital": {1: "Never married", 2: "Married or in union (monogamous, polygamous, cohabiting)", 3: "Divorced or separated", 4: "Widowed"},
    "h_relation": {1: "Head", 2: "Spouse", 3: "Child (own, step, adopted, foster)", 4: "Other relative", 5: "Non-relative (incl. domestic worker, unknown)"},
    "h_attend": {0: "Never attended school", 1: "Attended or attending"},
    "h_educ": {0: "None or pre-primary", 1: "Primary", 2: "Secondary (post-primary, vocational, lower or upper secondary)", 3: "Tertiary"},
    "h_literacy": {0: "Cannot read and write", 1: "Can read and write"},
    "h_lfstatus": {1: "Employed", 2: "Unemployed", 3: "Outside the labour force"}, "h_employed": {0: "Not employed", 1: "Employed"},
    "h_lfs_def": {1: "LFS: NISR status1, ILO 7-day; ages 16+ in 2017-2019, 14+ from 2020",
                  2: "Census 2002: activity situation over 15/07-15/08/2002; ages 6+",
                  3: "Census 2012: NISR rp2024, 7-day, relaxed unemployment (availability only); ages 5+",
                  4: "EICV1/EICV2: NISR econstatus, usual activity over 12 months; ages 7+ / 6+",
                  5: "EICV3/EICV5: any work in the last 12 months incl. own farm (no unemployment category in EICV3); ages 6+",
                  6: "EICV4: NISR lfs6, current status; ages 6+",
                  7: "EICV7 / AHS 2024: any work in the last 7 days incl. own farm, or temporarily absent; no unemployment category; ages 6+",
                  8: "AHS 2017/2020: main economic activity of members above 10"},
    "h_empstat": {1: "Employee (incl. paid apprentice / intern)", 2: "Employer", 3: "Own-account worker / self-employed", 4: "Contributing family worker",
                  5: "Other (cooperative member, unpaid apprentice, other)"},
    "h_isic1": ISIC, "h_isco1": ISCO,
    "h_isic1_approx": {0: "Native ISIC Rev.4 1-digit", 1: "Approximate crosswalk (ISIC Rev.3 divisions or the EICV1/2 national groups)"},
    "h_isco1_approx": {0: "Native ISCO-08 1-digit", 1: "Approximate crosswalk (ISCO-88 major groups or the EICV1/2 national groups)"},
}
for k in ("h_head_sex", "h_head_marital", "h_head_educ", "h_head_literacy"): H_VALUES[k] = H_VALUES[k.replace("h_head_", "h_")]

# ------------------------------------------------------------------ the map (written to harmonization_map.csv)
MAP = []
H = pd.DataFrame()
def note_map(dataset, waves, fname, hvar, source, rule, level, quality, note=""):
    MAP.append({"dataset": dataset, "waves": ",".join(map(str, waves)) if not isinstance(waves, str) else waves, "file": fname,
                "h_variable": hvar, "source_variables": source, "rule": rule, "level": level, "quality": quality, "note": note})

LEVEL_ALL = "all household surveys (LFS, Census, EICV, AHS) + CFSVA head/woman"
LEVEL_LAB = "employment group: LFS, Census, EICV (+ AHS where asked)"
LEVEL_EDU = "education group: Census, EICV, LFS (+ AHS, CFSVA head/woman)"

def apply_recode(df, m, src_col, hvar, spec, dataset, wave, fname, level, quality, note=""):
    global H
    """Apply {target: [sources]} on rows `m` from column src_col into hvar; record the rule."""
    if src_col is None or src_col not in df.columns:
        note_map(dataset, [wave], fname, hvar, "(not available)", "", level, "missing", note or "no source item in this wave"); return
    H.loc[m, hvar] = recode(df.loc[m, src_col], flat(spec)).values
    note_map(dataset, [wave], fname, hvar, src_col, rule_text(spec), level, quality, note)

# ------------------------------------------------------------------ crosswalks for older classifications
# ISIC Rev.3 division -> ISIC Rev.4 section (1-21); used for the 2002 census (p24, 3-digit Rev.3 groups)
ISIC3_DIV_TO_SEC = {**{d: 1 for d in (1, 2, 5)}, **{d: 2 for d in range(10, 15)}, **{d: 3 for d in range(15, 38)}, 40: 4, 41: 5, 45: 6,
                    50: 7, 51: 7, 52: 7, 55: 9, 60: 8, 61: 8, 62: 8, 63: 8, 64: 10, 65: 11, 66: 11, 67: 11, 70: 12, 71: 14, 72: 10, 73: 13, 74: 13,
                    75: 15, 80: 16, 85: 17, 90: 5, 91: 19, 92: 18, 93: 19, 95: 20, 99: 21}
# EICV1/EICV2 national industry groups (NISR 'ISICGroup', 2-digit) -> ISIC Rev.4 section
EICV12_GRP_TO_SEC = {**{g: 1 for g in (11, 12, 13, 14)}, 21: 2, 22: 2, **{g: 3 for g in range(31, 39)}, 41: 4, 51: 6, 52: 6, 53: 6,
                     61: 7, 62: 7, 63: 7, 64: 9, 65: 7, 71: 8, 72: 8, 73: 10, 81: 11, 82: 11, 83: 12, 84: 13, 91: 15, 92: 18, 93: 20}
# EICV1/EICV2 'Occupation - Grouped' -> ISCO-08 major group (approximate)
EICV12_OCC_TO_ISCO = {1: 2, 2: 1, 3: 4, 4: 5, 5: 5, 6: 6, 7: 7, 8: 8, 9: 9}

# plain numpy booleans (missing -> False): nullable-boolean NA would count as True in .all() and as False in .where()
def yes(s): return pd.to_numeric(s, errors="coerce").astype("float64") == 1
def no(s): return pd.to_numeric(s, errors="coerce").astype("float64") == 2

# ------------------------------------------------------------------ concept functions per dataset (person files)
def concepts_lfs(df, dec, fname):
    global H
    ds = "LFS"; waves = sorted(df["wave"].unique())
    for w in waves:
        m = df["wave"] == w; y = int(w)
        a02 = col_for(dec, "a02", w, df.columns); a05 = col_for(dec, "a05", w, df.columns); b02a = col_for(dec, "b02a", w, df.columns)
        b06 = col_for(dec, "b06", w, df.columns); st = col_for(dec, "status1", w, df.columns); d05 = col_for(dec, "d05", w, df.columns)
        i03 = col_for(dec, "indd03", w, df.columns); i01 = col_for(dec, "indd01", w, df.columns)
        if y >= 2024: rel = {1: [1], 2: [2], 3: [3, 4], 4: list(range(5, 12)), 5: [12, 13, 14]}   # 14-code list from 2024 (a02_v2; the 2024 file's data already follow it -- LFS audit 2026-09-05)
        else: rel = {1: [1], 2: [2], 3: [3, 4], 4: [5, 6, 7, 8, 9], 5: [10, 11]}
        apply_recode(df, m, a02, "h_relation", rel, ds, w, fname, LEVEL_ALL, "exact", "98/99 don't know/missing -> missing")
        apply_recode(df, m, a05, "h_marital", {1: [6], 2: [1, 2, 3], 3: [4, 5], 4: [7]}, ds, w, fname, LEVEL_ALL, "exact", "asked of members 12+")
        apply_recode(df, m, b02a, "h_educ", {0: [1, 2], 1: [3], 2: [4, 5], 3: [6]}, ds, w, fname, LEVEL_EDU, "exact", "asked of members 14+; level attended/attending")
        if b02a: H.loc[m, "h_attend"] = pd.to_numeric(df.loc[m, b02a], errors="coerce").astype("float64").map(lambda v: 0 if v == 1 else (1 if v in (2, 3, 4, 5, 6) else np.nan)).values
        note_map(ds, [w], fname, "h_attend", b02a or "(none)", "b02a=1 (none)->0; 2-6->1", LEVEL_EDU, "exact" if b02a else "missing", "14+")
        apply_recode(df, m, b06, "h_literacy", {1: [1], 0: [2]}, ds, w, fname, LEVEL_EDU, "exact", "14+; B06 not asked from 2024" if y >= 2024 else "asked of members 14+")
        apply_recode(df, m, st, "h_lfstatus", {1: [1], 2: [2], 3: [3]}, ds, w, fname, LEVEL_LAB, "exact", "NISR status1; ages 16+ (2017-19) / 14+ (2020+)")
        H.loc[m & H["h_lfstatus"].notna(), "h_lfs_def"] = 1
        if y >= 2025: apply_recode(df, m, d05, "h_empstat", {1: [1], 2: [3], 3: [4], 4: [6], 5: [5]}, ds, w, fname, LEVEL_LAB, "exact", "2025 ICSE-93 recode d05_v2")
        else: apply_recode(df, m, d05, "h_empstat", {1: [1, 2], 2: [3], 3: [4], 4: [6], 5: [5, 7]}, ds, w, fname, LEVEL_LAB, "exact")
        apply_recode(df, m, i03, "h_isic1", {k: [k] for k in range(1, 22)}, ds, w, fname, LEVEL_LAB, "exact", "NISR indd03 (ISIC Rev.4 section, main job)")
        apply_recode(df, m, i01, "h_isco1", {k: [k] for k in range(1, 10)}, ds, w, fname, LEVEL_LAB, "exact", "NISR indd01 (ISCO-08 major group, main job)")
        H.loc[m & H["h_isic1"].notna(), "h_isic1_approx"] = 0; H.loc[m & H["h_isco1"].notna(), "h_isco1_approx"] = 0

def concepts_census(df, dec, fname):
    global H
    ds = "Census"
    for w in sorted(df["wave"].unique()):
        m = df["wave"] == w; y = int(w); C = lambda b: col_for(dec, b, w, df.columns)
        if y == 2002:
            apply_recode(df, m, C("p02"), "h_relation", {1: [1], 2: [2], 3: [3, 4], 4: [5, 6, 7, 8], 5: [9]}, ds, w, fname, LEVEL_ALL, "exact", "code 4 = unrelated child brought up in the household -> child")
            apply_recode(df, m, C("p26"), "h_marital", {1: [1], 2: [2, 3, 4, 5, 6, 7], 3: [8], 4: [9]}, ds, w, fname, LEVEL_ALL, "exact", "residents 12+")
            p16, p17 = C("p16"), C("p17")
            apply_recode(df, m, p16, "h_attend", {1: [1], 0: [2]}, ds, w, fname, LEVEL_EDU, "exact", "ages 6+")
            if p17:
                v = pd.to_numeric(df.loc[m, p17], errors="coerce").astype("float64")
                e = pd.Series(np.nan, index=v.index); e[(v >= 10) & (v <= 19)] = 1; e[(v >= 20) & (v <= 59)] = 2; e[(v >= 60) & (v <= 69)] = 3
                if p16: e[no(df.loc[m, p16])] = 0
                H.loc[m, "h_educ"] = e.values
            note_map(ds, [w], fname, "h_educ", f"{p17} (class code) + {p16}", "10-19 primary->1; 21-23 post-primary, 31-57 secondary (FP/FT/EG)->2; 61-69 university->3; never attended->0", LEVEL_EDU, "exact", "ages 6+; highest class successfully completed")
            apply_recode(df, m, C("p20"), "h_literacy", {1: [1], 0: [2, 3]}, ds, w, fname, LEVEL_EDU, "exact", "ages 6+; 'read only' -> 0")
            apply_recode(df, m, C("p21"), "h_lfstatus", {1: [1], 2: [2, 3], 3: [4, 5, 6, 7, 8]}, ds, w, fname, LEVEL_LAB, "exact", "one-month reference period; ages 6+")
            H.loc[m & H["h_lfstatus"].notna(), "h_lfs_def"] = 2
            apply_recode(df, m, C("p23"), "h_empstat", {1: [3, 4, 5], 2: [2], 3: [1], 4: [6], 5: [7]}, ds, w, fname, LEVEL_LAB, "exact", "economically active 6+")
            p24 = C("p24")
            if p24:
                v = pd.to_numeric(df.loc[m, p24], errors="coerce").astype("float64"); div = (v // 10).where(v < 999)
                H.loc[m, "h_isic1"] = div.map(ISIC3_DIV_TO_SEC).values; H.loc[m & H["h_isic1"].notna(), "h_isic1_approx"] = 1
            note_map(ds, [w], fname, "h_isic1", p24 or "(none)", "ISIC Rev.3 3-digit group -> division (code//10) -> Rev.4 section crosswalk (ISIC3_DIV_TO_SEC)", LEVEL_LAB, "approximate", "999 = not stated -> missing")
            p22 = C("p22")
            if p22:
                v = pd.to_numeric(df.loc[m, p22], errors="coerce").astype("float64"); mg = (v // 100).where((v >= 111) & (v < 999)); mg = mg.where(v != 101, 0)
                H.loc[m, "h_isco1"] = mg.where(mg.between(0, 9)).values; H.loc[m & H["h_isco1"].notna(), "h_isco1_approx"] = 1
            note_map(ds, [w], fname, "h_isco1", p22 or "(none)", "ISCO-88 3-digit -> major group (code//100); 101 armed forces -> 0", LEVEL_LAB, "approximate", "999 = not stated -> missing")
        elif y == 2012:
            apply_recode(df, m, C("p02"), "h_relation", {1: [1], 2: [2], 3: [3, 4], 4: [5, 6, 7, 8], 5: [9]}, ds, w, fname, LEVEL_ALL, "exact", "code 4 = unrelated child -> child")
            apply_recode(df, m, C("p29"), "h_marital", {1: [1], 2: [2], 3: [3, 5], 4: [4]}, ds, w, fname, LEVEL_ALL, "exact", "residents 12+; 9/99 -> missing")
            p17, p18a = C("p17"), C("p18a")
            apply_recode(df, m, p17, "h_attend", {0: [1], 1: [2, 3]}, ds, w, fname, LEVEL_EDU, "exact", "residents 3+")
            apply_recode(df, m, p18a, "h_educ", {0: [0], 1: [1], 2: [2, 3], 3: [4]}, ds, w, fname, LEVEL_EDU, "exact", "residents 3+ who attended; never attended -> 0 below")
            if p17: H.loc[m & (pd.to_numeric(df[p17], errors="coerce").astype("float64") == 1), "h_educ"] = 0
            p16 = C("p16")
            if p16:
                v = pd.to_numeric(df.loc[m, p16], errors="coerce").astype("float64"); H.loc[m, "h_literacy"] = v.map(lambda x: 0 if x == 0 else (1 if 1 <= x <= 15 else np.nan)).values
            note_map(ds, [w], fname, "h_literacy", p16 or "(none)", "P16 sum of languages read and written: 0->0, 1-15->1; 99/999 -> missing", LEVEL_EDU, "exact", "residents 3+")
            apply_recode(df, m, C("rp2024"), "h_lfstatus", {1: [1], 2: [2, 3], 3: [4, 5, 6, 7, 9]}, ds, w, fname, LEVEL_LAB, "exact", "NISR rp2024; code 9 (not classified) -> outside the labour force")
            H.loc[m & H["h_lfstatus"].notna(), "h_lfs_def"] = 3
            apply_recode(df, m, C("p26"), "h_empstat", {1: [1], 2: [2], 3: [3], 4: [4], 5: [5, 6]}, ds, w, fname, LEVEL_LAB, "exact", "9/99 -> missing")
            apply_recode(df, m, C("rp27"), "h_isic1", {k: [k] for k in range(1, 22)}, ds, w, fname, LEVEL_LAB, "exact", "NISR rp27 sections; 22/23 -> missing")
            apply_recode(df, m, C("rp25"), "h_isco1", {k: [k] for k in range(1, 10)}, ds, w, fname, LEVEL_LAB, "exact", "NISR rp25; 11/12 -> missing")
            H.loc[m & H["h_isic1"].notna(), "h_isic1_approx"] = 0; H.loc[m & H["h_isco1"].notna(), "h_isco1_approx"] = 0
        else:  # 2022
            apply_recode(df, m, C("p02"), "h_relation", {1: [1], 2: [2], 3: [3, 4], 4: list(range(5, 12)), 5: [12, 13, 14]}, ds, w, fname, LEVEL_ALL, "exact")
            apply_recode(df, m, C("p06"), "h_marital", {1: [6], 2: [1, 2, 3], 3: [4, 5], 4: [7]}, ds, w, fname, LEVEL_ALL, "exact", "residents 12+")
            p29, p30a = C("p29"), C("p30a")
            apply_recode(df, m, p29, "h_attend", {1: [1, 2], 0: [3]}, ds, w, fname, LEVEL_EDU, "exact", "all residents; 99 -> missing")
            apply_recode(df, m, p30a, "h_educ", {0: [1, 2], 1: [3], 2: [4, 5, 6], 3: [7]}, ds, w, fname, LEVEL_EDU, "exact", "never attended -> 0 below")
            if p29: H.loc[m & (pd.to_numeric(df[p29], errors="coerce").astype("float64") == 3), "h_educ"] = 0
            p32 = C("p32")
            if p32:
                v = pd.to_numeric(df.loc[m, p32], errors="coerce").astype("float64"); H.loc[m, "h_literacy"] = v.map(lambda x: 0 if x == 0 else (1 if 1 <= x <= 31 else np.nan)).values
            note_map(ds, [w], fname, "h_literacy", p32 or "(none)", "P32 languages read and written with understanding: 0->0, 1-31->1", LEVEL_EDU, "exact", "residents 10+")
            note_map(ds, [w], fname, "h_lfstatus", "(not available)", "", LEVEL_LAB, "missing", "P37-P45 (employment identification) are not in the public 2022 file; only characteristics of the employed (P46-P49)")
            apply_recode(df, m, C("p49"), "h_empstat", {1: [1, 2], 2: [3], 3: [4], 4: [6], 5: [5, 7]}, ds, w, fname, LEVEL_LAB, "exact", "employed residents 16+")
            apply_recode(df, m, C("p47a"), "h_isic1", {k: [k] for k in range(1, 22)}, ds, w, fname, LEVEL_LAB, "exact", "P47A ISIC section")
            apply_recode(df, m, C("p48a"), "h_isco1", {k: [k] for k in range(1, 10)}, ds, w, fname, LEVEL_LAB, "exact", "P48A ISCO major group; 99 -> missing")
            H.loc[m & H["h_isic1"].notna(), "h_isic1_approx"] = 0; H.loc[m & H["h_isco1"].notna(), "h_isco1_approx"] = 0

def concepts_eicv(df, dec, fname):
    global H
    ds = "EICV"
    for w in sorted(df["wave"].unique()):
        m = df["wave"] == w; base = w.split("_")[0]; C = lambda b: col_for(dec, b, w, df.columns)
        s1q2, s1q4 = C("s1q2"), C("s1q4")
        rel = {"EICV1": {1: [1], 2: [2], 3: [3], 4: [4, 5, 6], 5: [7, 8]}, "EICV2": {1: [1], 2: [2], 3: [3, 4], 4: [5, 6, 7, 8], 5: [9]},
               "EICV3": {1: [1], 2: [2], 3: [3, 4], 4: [5, 6, 7, 8, 9, 10], 5: [11, 12]}, "EICV7": {1: [1], 2: [2], 3: [3, 4], 4: list(range(5, 12)), 5: [12, 13, 14]}}
        rel["EICV4"] = rel["EICV5"] = rel["EICV3"]
        apply_recode(df, m, s1q2, "h_relation", rel[base], ds, w, fname, LEVEL_ALL, "exact", "EICV1 code 7 'domestic and related persons' -> non-relative" if base == "EICV1" else "")
        mar = {"EICV1": {1: [5], 2: [1, 2, 8, 9], 3: [3, 4], 4: [6]}, "EICV2": {1: [5], 2: [1, 2, 3, 7], 3: [4], 4: [6]}, "EICV3": {1: [6], 2: [1, 2, 3], 3: [4, 5], 4: [7]},
               "EICV4": {1: [7], 2: [1, 2, 3, 4], 3: [5, 6], 4: [8]}, "EICV7": {1: [6], 2: [1, 2, 3], 3: [4, 5], 4: [7]}}
        mar["EICV5"] = mar["EICV4"]
        apply_recode(df, m, s1q4, "h_marital", mar[base], ds, w, fname, LEVEL_ALL, "exact", "asked of members 12+")
        # education: ever attended + class code (+ diploma override for tertiary)
        att = {"EICV1": "s2aq2", "EICV2": "s2aq2", "EICV3": "s2aq2", "EICV4": "s4aq1", "EICV5": "s4aq1", "EICV7": "s4aq1"}[base]
        cls = {"EICV1": "s2aq3", "EICV2": "s2aq3", "EICV3": "s2cq3", "EICV4": "s4aq2", "EICV5": "s4aq2", "EICV7": "s4aq2"}[base]
        dip = {"EICV1": "s2aq4", "EICV2": "s2bq23", "EICV3": "s2cq4", "EICV4": "s4aq3", "EICV5": "s4aq3", "EICV7": "s4aq3"}[base]
        a, c, d = C(att), C(cls), C(dip)
        apply_recode(df, m, a, "h_attend", {1: [1], 0: [2]}, ds, w, fname, LEVEL_EDU, "exact", "ages 7+ (EICV1), 6+ (EICV2/3), 3+ (EICV4+)")
        e = pd.Series(np.nan, index=df.index[m])
        if c:
            v = pd.to_numeric(df.loc[m, c], errors="coerce").astype("float64")
            if base == "EICV7": e[v.isin([1, 2])] = 0; e[v == 3] = 1; e[v.isin([4, 5, 6])] = 2; e[v == 7] = 3
            else: e[v == 1] = 0; e[(v >= 10) & (v <= 19)] = 1; e[(v >= 20) & (v <= 39)] = 2; e[v >= 40] = 3
        if d:
            dv = pd.to_numeric(df.loc[m, d], errors="coerce").astype("float64")
            tert = dv.between(6, 10) if base != "EICV7" else dv.between(11, 15)
            if base == "EICV1": tert = dv.between(6, 10)
            e[tert] = 3
        if a: e[no(df.loc[m, a])] = 0
        H.loc[m, "h_educ"] = e.values
        rule = ("s4aq2 1,2->0; 3->1; 4,5,6->2; 7->3; diploma 11-15->3" if base == "EICV7" else
                f"{cls} class code: 1 pre-primary->0; 10-19 primary->1; 20-39 post-primary/vocational/secondary->2; 40+ university->3; diploma {dip} 6-10 (bachelor..doctorate)->3")
        note_map(ds, [w], fname, "h_educ", f"{c} + {d} + {a}", rule + "; never attended->0", LEVEL_EDU, "exact", "")
        rd, wr = {"EICV1": ("s2cq1", "s2cq3"), "EICV2": ("s2cq1", "s2cq3"), "EICV3": ("s2dq1", "s2dq3"), "EICV4": ("s4bq3", "s4bq4"),
                  "EICV5": ("s4bq4", "s4bq5"), "EICV7": ("s4bq4", "s4bq6")}[base]
        r, wv = C(rd), C(wr)
        if r and wv:
            lit = pd.Series(np.nan, index=df.index[m]); lit[yes(df.loc[m, r]) & yes(df.loc[m, wv])] = 1; lit[no(df.loc[m, r]) | no(df.loc[m, wv])] = 0
            H.loc[m, "h_literacy"] = lit.values
        note_map(ds, [w], fname, "h_literacy", f"{r} & {wv}", "read=1 & write=1 -> 1; either =2 -> 0", LEVEL_EDU, "exact" if (r and wv) else "missing", "literacy 5+/6+/10+ by round")
        # labour-force status
        if base in ("EICV1", "EICV2"):
            ec = C("econstatus")
            apply_recode(df, m, ec, "h_lfstatus", {1: [1], 2: [2], 3: [3, 5]}, ds, w, fname, LEVEL_LAB, "exact", "NISR econstatus (12-month usual activity); code 4 'under 7' -> missing")
            if ec: H.loc[m & H["h_lfstatus"].notna(), "h_lfs_def"] = 4
        elif base == "EICV4":
            lf = C("lfs6")
            apply_recode(df, m, lf, "h_lfstatus", {1: [1], 2: [2], 3: [3]}, ds, w, fname, LEVEL_LAB, "exact", "NISR lfs6 (current status, 6+)")
            if lf: H.loc[m & H["h_lfstatus"].notna(), "h_lfs_def"] = 6
        else:
            work = {"EICV3": ["s6aq2", "s6aq3", "s6aq4", "s6aq5", "s6aq6"], "EICV5": ["s6aq2", "s6aq3", "s6aq4", "s6aq5", "s6aq6"],
                    "EICV7": ["s6aq2", "s6aq4", "s6aq5", "s6aq6", "s6aq7", "s6aq8", "s6aq9"]}[base]
            cols = [C(x) for x in work if C(x)]
            reason = C({"EICV3": "s6aq7", "EICV5": "s6aq9", "EICV7": "s6aq10"}[base])
            if cols:
                anyw = pd.concat([yes(df.loc[m, x]) for x in cols], axis=1).any(axis=1)
                allno = pd.concat([no(df.loc[m, x]) for x in cols], axis=1).all(axis=1)
                st = pd.Series(np.nan, index=df.index[m]); st[anyw] = 1
                if base == "EICV5" and reason:
                    rv = pd.to_numeric(df.loc[m, reason], errors="coerce").astype("float64"); st[~anyw & (rv == 1)] = 2; st[~anyw & rv.between(2, 7)] = 3
                else:
                    st[~anyw & allno] = 3
                H.loc[m, "h_lfstatus"] = st.values; H.loc[m & H["h_lfstatus"].notna(), "h_lfs_def"] = 5 if base != "EICV7" else 7
            note_map(ds, [w], fname, "h_lfstatus", " | ".join(cols) + (f" | {reason}" if reason else ""),
                     "any work item = yes -> 1 (employed); " + ("EICV5: reason s6aq9 = 1 unemployed/seeking -> 2, 2-7 -> 3" if base == "EICV5" else "all work items = no -> 3 (no unemployment item)"),
                     LEVEL_LAB, "approximate", "12-month reference (EICV3/5) / 7-day reference (EICV7)")
        # status in employment
        if base == "EICV1": apply_recode(df, m, C("s4bq14"), "h_empstat", {1: [1], 2: [2], 3: [3], 4: [4], 5: [5]}, ds, w, fname, LEVEL_LAB, "exact", "main job work status; 6 no work / 7 not known -> missing")
        elif base == "EICV2": apply_recode(df, m, C("workstats"), "h_empstat", {1: [1, 4], 3: [2, 5], 4: [3, 6]}, ds, w, fname, LEVEL_LAB, "approximate", "NISR usual work status (wage / independent / unpaid, farm and non-farm); no employer category")
        elif base == "EICV7": apply_recode(df, m, C("s6bq7"), "h_empstat", {1: [1, 2], 2: [3], 3: [4], 4: [6], 5: [5, 7, 8]}, ds, w, fname, LEVEL_LAB, "exact", "main job, last 7 days")
        else: note_map(ds, [w], fname, "h_empstat", "(not available at person level)", "", LEVEL_LAB, "missing", "status is recorded per job in the jobs module (EICV3-5), not on the person record")
        # industry / occupation
        if base in ("EICV1", "EICV2"):
            g = C("mainisic") if base == "EICV1" else C("isicgroup"); o = C("occupation")
            if g:
                v = pd.to_numeric(df.loc[m, g], errors="coerce").astype("float64"); H.loc[m, "h_isic1"] = v.map(EICV12_GRP_TO_SEC).values; H.loc[m & H["h_isic1"].notna(), "h_isic1_approx"] = 1
            note_map(ds, [w], fname, "h_isic1", g or "(none)", "NISR national industry group (11-93) -> ISIC Rev.4 section (EICV12_GRP_TO_SEC)", LEVEL_LAB, "approximate", "main job")
            if o:
                v = pd.to_numeric(df.loc[m, o], errors="coerce").astype("float64"); H.loc[m, "h_isco1"] = v.map(EICV12_OCC_TO_ISCO).values; H.loc[m & H["h_isco1"].notna(), "h_isco1_approx"] = 1
            note_map(ds, [w], fname, "h_isco1", o or "(none)", "NISR 'Occupation - Grouped' (1-9) -> ISCO-08 major group (EICV12_OCC_TO_ISCO); 100/999 -> missing", LEVEL_LAB, "approximate", "main job")
        elif base == "EICV4":
            apply_recode(df, m, C("isic"), "h_isic1", {k: [k] for k in range(1, 22)}, ds, w, fname, LEVEL_LAB, "exact", "NISR 'Current main economic activity' (ISIC section)")
            apply_recode(df, m, C("isco"), "h_isco1", {k: [k] for k in range(1, 10)}, ds, w, fname, LEVEL_LAB, "exact", "NISR 'Current main occupation'; 99 -> missing")
            H.loc[m & H["h_isic1"].notna(), "h_isic1_approx"] = 0; H.loc[m & H["h_isco1"].notna(), "h_isco1_approx"] = 0
        elif base == "EICV7":
            apply_recode(df, m, C("s6bq4"), "h_isic1", {k: [k] for k in range(1, 22)}, ds, w, fname, LEVEL_LAB, "exact", "ISIC level 1, main job")
            apply_recode(df, m, C("s6bq3"), "h_isco1", {k: [k] for k in range(1, 10)}, ds, w, fname, LEVEL_LAB, "exact", "ISCO level 1, main job")
            H.loc[m & H["h_isic1"].notna(), "h_isic1_approx"] = 0; H.loc[m & H["h_isco1"].notna(), "h_isco1_approx"] = 0
        else:
            note_map(ds, [w], fname, "h_isic1", "(not available at person level)", "", LEVEL_LAB, "missing", "codes are in the jobs module (EICV3/5)")
            note_map(ds, [w], fname, "h_isco1", "(not available at person level)", "", LEVEL_LAB, "missing", "codes are in the jobs module (EICV3/5)")

def concepts_ahs(df, dec, fname):
    global H
    ds = "AHS"
    for w in sorted(df["wave"].unique()):
        m = df["wave"] == w; y = int(w); C = lambda b: col_for(dec, b, w, df.columns)
        if y == 2017:
            apply_recode(df, m, C("s1q3"), "h_relation", {1: [1], 2: [2], 3: [3], 4: [4, 5], 5: [6, 7]}, ds, w, fname, LEVEL_ALL, "exact", "7-code list")
            note_map(ds, [w], fname, "h_marital", "(not available)", "", LEVEL_ALL, "missing", "not asked in the 2017 roster")
            e = C("s1q7"); apply_recode(df, m, e, "h_educ", {0: [4], 1: [1], 2: [2], 3: [3]}, ds, w, fname, LEVEL_EDU, "exact", "members above 10")
            if e: H.loc[m, "h_attend"] = pd.to_numeric(df.loc[m, e], errors="coerce").astype("float64").map(lambda v: 0 if v == 4 else (1 if v in (1, 2, 3) else np.nan)).values
            note_map(ds, [w], fname, "h_attend", e or "(none)", "s1q7 4 (no education)->0; 1-3->1", LEVEL_EDU, "exact" if e else "missing", "members above 10")
            a = C("s1q8"); apply_recode(df, m, a, "h_lfstatus", {1: [1, 2, 3, 5, 6], 3: [4]}, ds, w, fname, LEVEL_LAB, "approximate", "main economic activity (cropping / non-farm / livestock / both = employed, none = outside); no unemployment item")
            if a: H.loc[m & H["h_lfstatus"].notna(), "h_lfs_def"] = 8
        elif y == 2020:
            apply_recode(df, m, C("s1q4"), "h_relation", {1: [1], 2: [2], 3: [3, 4], 4: [5, 6, 7, 8, 9, 10, 12], 5: [11, 13]}, ds, w, fname, LEVEL_ALL, "exact")
            note_map(ds, [w], fname, "h_marital", "(head only: s0q9 in the household file)", "", LEVEL_ALL, "missing", "")
            e = C("s1q7"); apply_recode(df, m, e, "h_educ", {0: [8], 1: [1, 2], 2: [3, 4, 5], 3: [6, 7]}, ds, w, fname, LEVEL_EDU, "exact", "9 don't know -> missing")
            if e: H.loc[m, "h_attend"] = pd.to_numeric(df.loc[m, e], errors="coerce").astype("float64").map(lambda v: 0 if v == 8 else (1 if 1 <= v <= 7 else np.nan)).values
            note_map(ds, [w], fname, "h_attend", e or "(none)", "s1q7 8 (not schooled)->0; 1-7->1", LEVEL_EDU, "exact" if e else "missing", "")
            a = C("s1q8"); apply_recode(df, m, a, "h_lfstatus", {1: list(range(1, 10)), 3: [10, 11, 12]}, ds, w, fname, LEVEL_LAB, "approximate", "main economic activity; 13 other -> missing; no unemployment item")
            if a: H.loc[m & H["h_lfstatus"].notna(), "h_lfs_def"] = 8
            apply_recode(df, m, a, "h_empstat", {3: [1, 5, 6, 7], 1: [2, 4, 8, 9], 4: [3]}, ds, w, fname, LEVEL_LAB, "approximate", "from the main-activity list: self-employed/sale -> own-account; paid labour/salaried -> employee; contributing in household agriculture -> family worker")
        else:  # 2024, EICV7 questionnaire
            apply_recode(df, m, C("s1q2"), "h_relation", {1: [1], 2: [2], 3: [3, 4], 4: list(range(5, 12)), 5: [12, 13, 14]}, ds, w, fname, LEVEL_ALL, "exact")
            apply_recode(df, m, C("s1q4"), "h_marital", {1: [6], 2: [1, 2, 3], 3: [4, 5], 4: [7]}, ds, w, fname, LEVEL_ALL, "exact", "12+")
            a, c, d = C("s4aq1"), C("s4aq2"), C("s4aq3")
            apply_recode(df, m, a, "h_attend", {1: [1], 0: [2]}, ds, w, fname, LEVEL_EDU, "exact")
            e = pd.Series(np.nan, index=df.index[m])
            if c:
                v = pd.to_numeric(df.loc[m, c], errors="coerce").astype("float64"); e[v.isin([1, 2])] = 0; e[v == 3] = 1; e[v.isin([4, 5, 6])] = 2; e[v == 7] = 3
            if d: e[pd.to_numeric(df.loc[m, d], errors="coerce").astype("float64").between(11, 15)] = 3
            if a: e[no(df.loc[m, a])] = 0
            H.loc[m, "h_educ"] = e.values
            note_map(ds, [w], fname, "h_educ", f"{c} + {d} + {a}", "s4aq2 1,2->0; 3->1; 4,5,6->2; 7->3; diploma 11-15->3; never attended->0", LEVEL_EDU, "exact", "")
            r, wv = C("s4bq4"), C("s4bq6")
            if r and wv:
                lit = pd.Series(np.nan, index=df.index[m]); lit[yes(df.loc[m, r]) & yes(df.loc[m, wv])] = 1; lit[no(df.loc[m, r]) | no(df.loc[m, wv])] = 0
                H.loc[m, "h_literacy"] = lit.values
            note_map(ds, [w], fname, "h_literacy", f"{r} & {wv}", "read=1 & write=1 -> 1; either =2 -> 0", LEVEL_EDU, "exact" if (r and wv) else "missing", "")
            cols = [C(x) for x in ("s6aq2", "s6aq4", "s6aq5", "s6aq6", "s6aq7", "s6aq8", "s6aq9") if C(x)]
            if cols:
                anyw = pd.concat([yes(df.loc[m, x]) for x in cols], axis=1).any(axis=1); allno = pd.concat([no(df.loc[m, x]) for x in cols], axis=1).all(axis=1)
                st = pd.Series(np.nan, index=df.index[m]); st[anyw] = 1; st[~anyw & allno] = 3
                H.loc[m, "h_lfstatus"] = st.values; H.loc[m & H["h_lfstatus"].notna(), "h_lfs_def"] = 7
            note_map(ds, [w], fname, "h_lfstatus", " | ".join(cols), "any work item = yes -> 1; all = no -> 3 (no unemployment item)", LEVEL_LAB, "approximate", "7-day reference, 6+")
            apply_recode(df, m, C("s6bq7"), "h_empstat", {1: [1, 2], 2: [3], 3: [4], 4: [6], 5: [5, 7, 8]}, ds, w, fname, LEVEL_LAB, "exact", "main job")
            note_map(ds, [w], fname, "h_isco1", "(s6bq3a is a text description)", "", LEVEL_LAB, "missing", "no coded ISCO/ISIC in the AHS 2024 person file")

def head_concepts_cfsva(df, dec, fname):
    global H
    ds = "CFSVA"
    for w in sorted(df["wave"].unique()):
        m = df["wave"] == w; C = lambda b: col_for(dec, b, w, df.columns)
        sex, age, lit, edu, mar = {"2006": ("s12", "s13", "s14", "s15", "s16a"), "2012": ("q102", "q103", "q104", "q105", "q107"),
                                   "2015": ("s1_01_3", "s1_01_4", "s1_01_7", "s1_01_8", "s1_01_10")}.get(w if w in ("2006", "2012") else "2015", (None,) * 5)
        if w == "2009": sex = age = lit = edu = mar = None
        s, a = C(sex) if sex else None, C(age) if age else None
        if s: H.loc[m, "h_head_sex"] = recode(df.loc[m, s], {1: 1, 2: 2}).values
        if a: H.loc[m, "h_head_age"] = pd.to_numeric(df.loc[m, a], errors="coerce").astype("float64").where(lambda x: x.between(10, 120)).values
        note_map(ds, [w], fname, "h_head_sex", s or "(none)", "1->1; 2->2 (0 missing)", LEVEL_ALL, "exact" if s else "missing", "2009 household file carries no head block")
        note_map(ds, [w], fname, "h_head_age", a or "(none)", "years as shipped (10-120 kept)", LEVEL_ALL, "exact" if a else "missing", "")
        if w == "2006":
            apply_recode(df, m, C(lit), "h_head_literacy", {1: [1], 0: [0]}, ds, w, fname, LEVEL_EDU, "exact", "9 -> missing")
            apply_recode(df, m, C(edu), "h_head_educ", {0: [1], 1: [2, 3], 2: [4, 5, 6, 7], 3: [8, 9]}, ds, w, fname, LEVEL_EDU, "exact", "0 ND / 10 other -> missing")
            apply_recode(df, m, C(mar), "h_head_marital", {1: [6], 2: [1, 2], 3: [3, 4], 4: [5]}, ds, w, fname, LEVEL_ALL, "exact", "0 -> missing")
        elif w == "2012":
            apply_recode(df, m, C(lit), "h_head_literacy", {1: [1], 0: [0, 2]}, ds, w, fname, LEVEL_EDU, "exact", "'read only' -> 0")
            apply_recode(df, m, C(edu), "h_head_educ", {0: [1], 1: [2, 3], 2: [4, 5, 6], 3: [7]}, ds, w, fname, LEVEL_EDU, "exact")
            apply_recode(df, m, C(mar), "h_head_marital", {1: [5], 2: [1, 2], 3: [3], 4: [4]}, ds, w, fname, LEVEL_ALL, "exact")
        elif w in ("2015", "2018", "2021", "2024"):
            apply_recode(df, m, C(lit), "h_head_literacy", {1: [1], 0: [0, 2]}, ds, w, fname, LEVEL_EDU, "exact", "'read only' -> 0")
            apply_recode(df, m, C(edu), "h_head_educ", {0: [1], 1: [2, 3], 2: [4, 5, 6], 3: [7, 8]}, ds, w, fname, LEVEL_EDU, "exact", "88 don't know -> missing")
            apply_recode(df, m, C(mar), "h_head_marital", {1: [6], 2: [1, 2], 3: [3, 4], 4: [5]}, ds, w, fname, LEVEL_ALL, "exact")

def woman_concepts_cfsva(df, dec, fname):
    global H
    ds = "CFSVA"
    for w in sorted(df["wave"].unique()):
        m = df["wave"] == w; C = lambda b: col_for(dec, b, w, df.columns)
        lit, edu = {"2006": ("s124a", "s125aa"), "2012": ("q102_03", "q102_04"), "2015": ("s13_02_3", "s13_02_4"), "2024": ("s12_01_4", "s12_01_5")}.get(w, (None, None))
        if w == "2006":
            apply_recode(df, m, C(lit), "h_literacy", {1: [1], 0: [0]}, ds, w, fname, LEVEL_EDU, "exact", "9 -> missing")
            apply_recode(df, m, C(edu), "h_educ", {0: [1], 1: [2], 2: [3, 4, 5, 6], 3: [7, 8]}, ds, w, fname, LEVEL_EDU, "exact", "9 -> missing")
        elif w == "2012":
            apply_recode(df, m, C(lit), "h_literacy", {1: [3], 0: [0, 1, 2]}, ds, w, fname, LEVEL_EDU, "exact", "read only / write only -> 0")
            apply_recode(df, m, C(edu), "h_educ", {0: [1], 1: [2, 3], 2: [4, 5, 6], 3: [7]}, ds, w, fname, LEVEL_EDU, "exact")
        elif w in ("2015", "2024"):
            apply_recode(df, m, C(lit), "h_literacy", {1: [1], 0: [0, 2]}, ds, w, fname, LEVEL_EDU, "exact", "'read only' -> 0")
            apply_recode(df, m, C(edu), "h_educ", {0: [1], 1: [2, 3], 2: [4, 5, 6], 3: [7, 8]}, ds, w, fname, LEVEL_EDU, "exact")
        else:
            note_map(ds, [w], fname, "h_educ", "(not available)", "", LEVEL_EDU, "missing", "2009 woman file: no education item identified")
            note_map(ds, [w], fname, "h_literacy", "(not available)", "", LEVEL_EDU, "missing", "")

CONCEPTS = {("LFS", "person"): concepts_lfs, ("Census", "person"): concepts_census, ("EICV", "person"): concepts_eicv,
            ("AHS", "person"): concepts_ahs, ("CFSVA", "household"): head_concepts_cfsva, ("CFSVA", "woman"): woman_concepts_cfsva}
PERSON_H = ["h_sex", "h_marital", "h_relation", "h_attend", "h_educ", "h_literacy", "h_lfstatus", "h_employed", "h_lfs_def", "h_empstat",
            "h_isic1", "h_isic1_approx", "h_isco1", "h_isco1_approx"]

# ------------------------------------------------------------------ the generic pass
def out_name(tag, fname):
    stem = fname[:-4]
    for pre in (f"{tag}_pooled_", f"{tag}_"):
        if stem.startswith(pre): stem = stem[len(pre):]; break
    return f"H_{tag}_{stem}.dta"

def unit_of(tag, fname, align):
    if "files" in align and fname in align["files"]: return align["files"][fname].get("unit", "")
    return "person" if "person" in fname else "household" if "household" in fname else "establishment" if tag == "EC" else ""

summary = {"stamp": STAMP, "files": {}}
if ONLY and (LOGS / "harmonize_summary.json").exists():       # partial run: keep what was built for the other datasets
    import json
    prev = json.load(open(LOGS / "harmonize_summary.json"))
    summary["files"] = {k: v for k, v in prev.get("files", {}).items() if v.get("dataset") not in ONLY and not any(k.startswith(f"H_{t}_") for t in ONLY)}
    if (P_OUT / "harmonization_map.csv").exists():
        MAP.extend(r for r in csv.DictReader(open(P_OUT / "harmonization_map.csv")) if r["dataset"] not in ONLY)
for tag in DATASETS:
    if ONLY and tag not in ONLY: continue
    P = ds_paths(tag); align = alignment(tag)
    files = [(P["final"], f) for f in sorted(P["final"].glob("*.dta"))] + ([(P["appended"], f) for f in sorted(P["appended"].glob("*.dta"))] if P["appended"].exists() else [])
    for folder, f in files:
        fname = f.name; unit = unit_of(tag, fname, align); out = P_OUT / out_name(tag, fname)
        free_gb = shutil.disk_usage(P_OUT).free / 1e9; size_gb = os.path.getsize(f) / 1e9
        if free_gb - size_gb * 1.3 < MIN_FREE_GB:
            log.warning("SKIPPED %s: %.1f GB file, only %.1f GB free (MIN_FREE_GB=%s) -- rerun when space is available", fname, size_gb, free_gb, MIN_FREE_GB)
            summary["files"][out.name] = {"source": str(f.relative_to(db_root())), "skipped": "disk space"}; continue
        log.info("---------------- %s / %s (%s, %.2f GB) -> %s", tag, fname, unit or "module", size_gb, out.name)
        df, vl, vv = read_dta_typed(f, log); n_in = len(df)
        # 1. common key labels and value labels; sex/age plain copies where present
        for c, t in KEY_LABELS.items():
            if c in df.columns: vl[c] = t
        for c, d in KEY_VALUES.items():
            if c in df.columns and pd.api.types.is_numeric_dtype(df[c]): vv[c] = d
        # 2. cross-dataset keys
        def id_text(col):   # numeric ids without a trailing ".0"; string ids (CFSVA 2009 composite keys) as they are
            s_ = df[col]
            if pd.api.types.is_numeric_dtype(s_): return s_.astype("float64").round().astype("Int64").astype(str)
            return s_.astype(object).where(s_.notna(), "").astype(str).str.strip()
        if "hhid" in df.columns:
            hh_ok = df["hhid"].notna() & (df["hhid"].astype(str).str.strip() != "")
            key = df["survey"].astype(str) + "_" + df["wave"].astype(str) + ("_" + id_text("interview") if "interview" in df.columns else "") + "_" + id_text("hhid")
            key = key.where(hh_ok, ""); df["h_hhkey"] = key
            if "pid" in df.columns:
                p_ok = df["pid"].notna() & (df["pid"].astype(str).str.strip() != "")
                df["h_pkey"] = (key + "_" + id_text("pid")).where(p_ok & (key != ""), "")
        # 3. concepts
        fn = CONCEPTS.get((tag, unit)) or (CONCEPTS.get((tag, "person")) if (tag == "EICV" and fname == "EICV_pooled_person_vup.dta") else None)
        H = pd.DataFrame(index=df.index)             # the h_* columns are built apart from the wide native frame (memory), joined once at the end
        if fn:
            dec = decisions_for(tag, fname, align)
            if unit == "person" or fname == "EICV_pooled_person_vup.dta":
                for h in PERSON_H: H[h] = np.nan
                if "sex" in df.columns: H["h_sex"] = recode(df["sex"], {1: 1, 2: 2}).values
                note_map(tag, sorted(df["wave"].unique()), fname, "h_sex", "sex", "1->1; 2->2", LEVEL_ALL, "exact", "")
                fn(df, dec, fname)
                H["h_employed"] = H["h_lfstatus"].map({1: 1, 2: 0, 3: 0})
                for h in PERSON_H: vl[h] = H_LABELS[h]; vv[h] = H_VALUES.get(h, {})
                H = downcast_new(H, PERSON_H)
                for h in ("h_marital", "h_relation", "h_educ", "h_literacy", "h_lfstatus", "h_empstat", "h_isic1", "h_isco1"):
                    log.info("   %-11s non-missing by wave: %s", h, H.groupby(df["wave"])[h].apply(lambda s: int(s.notna().sum())).to_dict())
            elif unit == "household":
                for h in ("h_head_sex", "h_head_age", "h_head_marital", "h_head_educ", "h_head_literacy"): H[h] = np.nan
                fn(df, dec, fname)
                for h in ("h_head_sex", "h_head_age", "h_head_marital", "h_head_educ", "h_head_literacy"): vl[h] = H_LABELS[h]; vv[h] = H_VALUES.get(h, {})
                H = downcast_new(H, ["h_head_sex", "h_head_age", "h_head_marital", "h_head_educ", "h_head_literacy"])
            elif unit == "woman":
                for h in ("h_educ", "h_literacy"): H[h] = np.nan
                fn(df, dec, fname)
                for h in ("h_educ", "h_literacy"): vl[h] = H_LABELS[h]; vv[h] = H_VALUES[h]
                H = downcast_new(H, ["h_educ", "h_literacy"])
        elif unit == "household" and "head_sex" in df.columns:
            H["h_head_sex"] = recode(df["head_sex"], {1: 1, 2: 2}); H["h_head_age"] = pd.to_numeric(df["head_age"], errors="coerce").astype("float64") if "head_age" in df.columns else np.nan
            vl["h_head_sex"], vl["h_head_age"] = H_LABELS["h_head_sex"], H_LABELS["h_head_age"]; vv["h_head_sex"] = H_VALUES["h_head_sex"]
            H = downcast_new(H, ["h_head_sex", "h_head_age"])
            note_map(tag, sorted(df["wave"].unique()), fname, "h_head_sex", "head_sex", "1->1; 2->2", LEVEL_ALL, "exact", "head = relationship code 1 in the roster")
            note_map(tag, sorted(df["wave"].unique()), fname, "h_head_age", "head_age", "as shipped", LEVEL_ALL, "exact", "")
        if len(H.columns): df = pd.concat([df, H], axis=1)
        del H
        ck(len(df) == n_in, f"{out.name}: row count unchanged ({n_in:,})")
        write_dta(df, out, vl, vv, f"H {STAMP}: {tag} {fname[:-4]} harmonised copy (keys, labels, h_* concepts)", log)
        summary["files"][out.name] = {"source": str(f.relative_to(db_root())), "dataset": tag, "unit": unit or "module", "rows": n_in, "vars": int(df.shape[1]),
                                      "h_vars": [c for c in df.columns if c.startswith("h_")], "waves": sorted(map(str, df["wave"].unique())) if "wave" in df.columns else []}
        del df
ck.done()
with open(P_OUT / "harmonization_map.csv", "w", newline="") as fh:
    wr = csv.DictWriter(fh, fieldnames=["dataset", "waves", "file", "h_variable", "source_variables", "rule", "level", "quality", "note"]); wr.writeheader(); wr.writerows(MAP)
save_json(summary, LOGS / "harmonize_summary.json")
log.info("01_harmonize done: %d files, %d map rows", len(summary["files"]), len(MAP))
