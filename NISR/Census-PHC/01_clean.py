"""
01_clean.py -- Census: 1_Raw/<year>/Census_<year>.(sav|dta) -> 2_Intermediate/Census_<year>_person_clean.dta

Per census: lower-case names, build the harmonised key block (survey year wave prov dist
sector urban cluster hhid pid sex age wt wt_hh), attach NISR's current province / district /
sector names as value labels, keep every other variable under its own name (2002: English
variable labels from the questionnaire, French originals recorded), destring, downcast,
back-check, write. Unit = person (public-use 10% household samples; see DECISIONS.md).
"""
import difflib, sys
import numpy as np, pandas as pd
from census_helpers import (paths, db_root, get_logger, Checks, read_any, write_dta, lower_names,
                            destring, downcast, save_json, LOGS)

log = get_logger("01_clean")
P = paths()
YEARS = [int(a) for a in sys.argv[1:]] or [2002, 2012, 2022]
PUBLISHED_POP = {2002: 8_128_553, 2012: 10_515_973, 2022: 13_246_394}   # NISR published census totals

KEY_ORDER = ["survey", "year", "wave", "prov", "dist", "sector", "urban", "cluster", "hhid", "pid", "sex", "age", "wt", "wt_hh"]
KEY_LABELS = {
    "survey": "Source survey", "year": "Census year", "wave": "Wave (census year)",
    "prov": "Province (1-5, NISR codes)", "dist": "District (11-57, NISR codes)",
    "sector": "Sector (1101-5715, NISR codes; names attached)", "urban": "Area of residence (1 urban, 2 rural)",
    "cluster": "Sampling cluster proxy (year_sector)", "hhid": "Household id (unique within year)",
    "pid": "Person number within the household", "sex": "Sex (1 male, 2 female)", "age": "Age in years",
    "wt": "Person weight (sums to the census population)", "wt_hh": "Household weight (2022 as shipped; 2002/2012 = person weight of the household sample)",
    "pid_nisr": "NISR person number as shipped", "collective": "1 = row belongs to a collective/institutional household (2002 only)",
    "sector_code_file": "Sector code as shipped in the 2002 file (before the name-based correction, see DECISIONS)",
}
URBAN_LABELS = {1: "Urban", 2: "Rural"}

# --- 2002: English variable labels transcribed from the census questionnaire (z_Documentation/2002).
#     Originals (French) are kept in logs/clean_2002_meta.json under var_labels_original.
EN2002 = {
    "province_code": "Province code", "novprov": "Province name", "district_code": "District code (3-digit, as shipped)",
    "novdistr": "District name", "sector_code": "Sector code (5-digit, as shipped)", "novsect": "Sector name",
    "g06_milieu": "Area of residence", "hhid": "Household id", "p00": "Serial number in household roster",
    "p02": "Relationship to household head", "p03": "Residence status (present/absent resident, visitor, collective)",
    "p04": "Sex", "p05x": "Day of birth", "p05a": "Month of birth", "p05b": "Year of birth", "p06": "Age at last birthday",
    "agcm": "Age (NISR derived copy)", "p061": "Age (NISR derived copy 1)", "p062": "Age (NISR derived copy 2)",
    "p063": "Age (NISR derived copy 3)", "p0631": "Age (NISR derived copy 3b)", "age_5": "Age (NISR derived copy, 5)",
    "gpe_age": "Age (NISR derived copy, groups)", "age1_1": "Age (NISR derived copy 1-1)", "a46": "Age (NISR derived copy A46)",
    "age26": "Age (NISR derived copy 26)", "age18": "Age (NISR derived copy 18)", "age19": "Age (NISR derived copy 19)",
    "p07": "Nationality", "p08": "Place of birth (district or country)", "p09": "Duration of residence in this locality (years; 99 since birth)",
    "p10": "Place of previous residence (district or country)", "p11": "Languages spoken", "p12": "Religious affiliation",
    "p13": "Type of major handicap", "personnes_handic": "Persons with a handicap (NISR grouped)", "p14": "Cause of handicap",
    "p15": "Survival of parents", "p16": "School attendance (ever attended)", "fr_quentation": "School attendance (NISR grouped)",
    "p17": "Highest class successfully completed", "p171": "Educational level attained (NISR grouped)",
    "p18": "Area of specialisation (secondary/higher)", "p19": "Highest certificate or diploma obtained", "p20": "Literacy",
    "p21": "Economic activity situation (15/07-15/08/2002)", "p211": "Activity status (NISR grouped)",
    "p22": "Main occupation (type of work done)", "emploi_exerc": "Occupation (NISR grouped)",
    "p23": "Status in employment", "p24": "Branch of economic activity", "p241": "Branch of economic activity (NISR grouped)",
    "p25": "Institutional sector of employment (public/parastatal/NGO/cooperative/other private)",
    "p26": "Marital status", "etat_matri": "Marital status (NISR grouped)",
    "p27a": "Live births ever, boys", "p27b": "Live births ever, girls", "p28a": "Children surviving, boys", "p28b": "Children surviving, girls",
    "p29a": "Births in the last 12 months, boys", "p29b": "Births in the last 12 months, girls",
    "p30a": "Of births in the last 12 months, surviving boys", "p30b": "Of births in the last 12 months, surviving girls",
    "grpage5": "Five-year age group (NISR derived)", "agebetween5_17": "Flag: age 5-17 (NISR derived)", "agegrp_nisr": "Age group (NISR derived, 0-5; shipped as 'Age')",
    "p02_hh": "Flag: household head (P02 = 1)", "h100": "Household type (100 = ordinary household)", "h200": "Collective household type (codes 201-214; not filled)",
    "h101": "Questionnaire serial number in household", "h102": "Number of questionnaires filled in household",
    "h110": "Recap: male residents present", "h111": "Recap: male residents absent", "h112": "Recap: male residents total",
    "h113": "Recap: male residents aged 17+", "h114": "Recap: male visitors", "h115": "Recap: female residents present",
    "h116": "Recap: female residents absent", "h117": "Recap: female residents total", "h118": "Recap: female residents aged 17+",
    "h119": "Recap: female visitors", "h120": "Recap: residents present, total", "h121": "Recap: residents absent, total",
    "h122": "Recap: residents, total", "h123": "Recap: residents aged 17+, total", "h124": "Recap: visitors, total",
    "h01": "Type of housing", "h02": "Type of building", "h03": "Roof material", "h04": "Outer wall material", "h05": "Floor material",
    "h06": "Number of living rooms", "h07": "Main source of water supply", "h08": "Main source of lighting", "h09": "Main cooking energy",
    "h10": "Main toilet facility", "h11": "Main mode of household waste disposal", "h12": "Occupancy status of the dwelling",
    "h13": "Radio / television ownership", "h14": "Fixed-line / cell phone", "h15": "Computer / internet connection",
    "h16a": "Number of vehicles", "h16b": "Number of motorcycles", "h16c": "Number of bicycles", "h17": "Total persons counted in the household",
    "h18": "(empty in the public file)", "h19a": "Any death of a resident member in the last 12 months", "h19b": "Number of deaths in the last 12 months",
    "probability": "Inclusion (selection) probability", "weight": "Final sampling weight", "p00_nu": "NISR artefact: count of P00 in household",
    "p00_mean": "NISR artefact: mean of P00 in household",
}

# --- NISR current administrative names (geodata-nisr village file) -> value labels for prov/dist/sector
geo = db_root() / "geodata-nisr" / "Village_Boundary_2022_924768113126413998.csv"
v = pd.read_csv(geo)
SECTORS = v.drop_duplicates("Sector ID")[["Province ID", "Province", "District ID", "District", "Sector ID", "Sector"]].sort_values("Sector ID")
PROV_LABELS = {int(k): s for k, s in SECTORS.drop_duplicates("Province ID")[["Province ID", "Province"]].values}
DIST_LABELS = {int(k): s for k, s in SECTORS.drop_duplicates("District ID")[["District ID", "District"]].values}
SECT_LABELS = {int(k): s for k, s in SECTORS[["Sector ID", "Sector"]].values}
assert len(SECT_LABELS) == 416 and len(DIST_LABELS) == 30 and len(PROV_LABELS) == 5

def sector_by_name_2002(df, log, ck):
    """Assign the current NISR sector code to each 2002 sector by NAME within district (the
    shipped codes are permuted in Musanze 4301-4304 and spelt with R/L variants elsewhere)."""
    tab = df[["sector_code_file", "novsect", "dist"]].drop_duplicates("sector_code_file")
    mapping, changed = {}, []
    for d, grp in tab.groupby("dist"):
        cand = SECTORS[SECTORS["District ID"] == d]
        names = {s.strip().upper(): int(k) for k, s in cand[["Sector ID", "Sector"]].values}
        left = dict(names)
        pend = []
        for code, nm in grp[["sector_code_file", "novsect"]].values:
            key = str(nm).strip().upper()
            if key in left: mapping[code] = left.pop(key)
            else: pend.append((code, key))
        for code, key in pend:   # spelling variants: closest remaining name in the same district
            m = difflib.get_close_matches(key, list(left), n=1, cutoff=0.6)
            if not m: raise ValueError(f"2002 sector {key} ({code}) in district {d} has no match among {list(left)}")
            mapping[code] = left.pop(m[0]); log.info("2002 sector name %-14s matched to %-14s (%s)", key, m[0], mapping[code])
    out = df["sector_code_file"].map(mapping)
    shipped = (df["sector_code_file"] // 10000) * 1000 + ((df["sector_code_file"] % 10000) // 100) * 100 + df["sector_code_file"] % 100
    for code, new in mapping.items():
        old = int((code // 10000) * 1000 + ((code % 10000) // 100) * 100 + code % 100)
        if old != new: changed.append((int(code), old, new, SECT_LABELS[new]))
    log.info("2002 sectors whose code changed after name matching: %s", changed)
    ck(len(set(mapping.values())) == 416, "2002: 416 distinct sectors after name matching")
    ck((out // 100 == df["dist"]).all(), "2002: corrected sector code nests in district")
    return out, shipped

def ren(df, vl, vv, src, dst, srcmap):
    if src in df.columns and dst not in df.columns:
        df.rename(columns={src: dst}, inplace=True)
        if src in vl: vl[dst] = vl.pop(src)
        if src in vv: vv[dst] = vv.pop(src)
        srcmap[dst] = src; return True
    return False

for y in YEARS:
    log.info("---------------- %s ----------------", y)
    raw = P["raw"] / str(y) / (f"Census_{y}.sav" if y == 2002 else f"Census_{y}.dta")
    df, vl, vv = read_any(raw)
    n_raw = len(df); log.info("read %s: %s rows x %s vars", raw.name, f"{n_raw:,}", df.shape[1])
    df, vl, vv = lower_names(df, vl, vv, log)
    srcmap, ck = {}, Checks(log)
    df["survey"] = "Census"; df["year"] = np.int16(y); df["wave"] = str(y)
    vl_original = None

    if y == 2002:
        df = df.rename(columns={"age": "agegrp_nisr"}); vl["agegrp_nisr"] = vl.pop("age", ""); vv.pop("age", None)   # free the name for P06
        vl_original = dict(vl)
        for c, t in EN2002.items():
            if c in df.columns: vl[c] = t
        missing = [c for c in df.columns if c not in EN2002 and c not in ("survey", "year", "wave")]
        ck(not missing, f"2002: every variable has an English label ({missing})", hard=False)
        ren(df, vl, vv, "province_code", "prov", srcmap)
        df["dist"] = (df["district_code"] // 100) * 10 + df["district_code"] % 100; srcmap["dist"] = "district_code (3-digit prov*100+seq -> prov*10+seq)"
        df = df.rename(columns={"sector_code": "sector_code_file"}); vl["sector_code_file"] = KEY_LABELS["sector_code_file"]
        df["sector"], _ = sector_by_name_2002(df, log, ck); srcmap["sector"] = "novsect matched by name to NISR current sector codes (sector_code_file kept)"
        ren(df, vl, vv, "g06_milieu", "urban", srcmap)
        df["pid_nisr"] = df["p00"]; df = df.drop(columns=["p00"])
        df["pid"] = df.groupby("hhid").cumcount() + 1; srcmap["pid"] = "row order within household (P00 is not unique within households; kept as pid_nisr)"
        ren(df, vl, vv, "p04", "sex", srcmap); ren(df, vl, vv, "p06", "age", srcmap)
        ren(df, vl, vv, "weight", "wt", srcmap); df["wt_hh"] = df["wt"]; srcmap["wt_hh"] = "= wt (10% household sample, self-weighting)"
        df["collective"] = (df["h100"].isna()).astype("int8"); srcmap["collective"] = "h100 missing (P03 = 4 'ménage collectif')"
        vv["sex"] = {1: "Male", 2: "Female"}
    elif y == 2012:
        ren(df, vl, vv, "l01", "prov", srcmap); ren(df, vl, vv, "dui", "dist", srcmap); ren(df, vl, vv, "sui", "sector", srcmap)
        # l07 has 4 categories (urban 13.9%, rural 75.3%, peri-urban 8.5%, semi-urban 2.3%, weighted);
        # key-block urban = 1 for 'urban' only, 2 otherwise; l07 is carried untouched.
        df["urban"] = np.where(df["l07"] == 1, 1, np.where(df["l07"].isna(), np.nan, 2)); srcmap["urban"] = "l07 == 1 -> 1, l07 in {2,3,4} -> 2 (l07 kept)"
        ren(df, vl, vv, "p01", "pid", srcmap); ren(df, vl, vv, "p03", "sex", srcmap); ren(df, vl, vv, "p05", "age", srcmap)
        ren(df, vl, vv, "sampleweight_final_", "wt", srcmap); df["wt_hh"] = df["wt"]; srcmap["wt_hh"] = "= wt (10% household sample, self-weighting)"
    else:
        ren(df, vl, vv, "ml01", "prov", srcmap); ren(df, vl, vv, "ml02", "dist", srcmap); ren(df, vl, vv, "ml03", "sector", srcmap)
        ren(df, vl, vv, "ml07", "urban", srcmap)
        ren(df, vl, vv, "p01", "pid", srcmap); ren(df, vl, vv, "p03", "sex", srcmap); ren(df, vl, vv, "p04", "age", srcmap)
        ren(df, vl, vv, "pop_weight", "wt", srcmap); ren(df, vl, vv, "hh_weight", "wt_hh", srcmap)
    df["cluster"] = df["year"].astype(str) + "_" + df["sector"].astype("Int64").astype(str)
    df["hhid"] = df["hhid"].astype("Int64")            # nullable: 2002 collective-household rows carry no hhid
    log.info("rows without a household id: %s", f"{int(df['hhid'].isna().sum()):,}")
    vv["prov"], vv["dist"], vv["sector"], vv["urban"] = PROV_LABELS, DIST_LABELS, SECT_LABELS, URBAN_LABELS
    for c, t in KEY_LABELS.items():
        if c in df.columns: vl[c] = t

    df = destring(df, log, skip=("survey", "wave", "cluster", "novprov", "novdistr", "novsect"))
    df = downcast(df, keep_double=("wt", "wt_hh", "hhid", "probability"))
    df = df[KEY_ORDER + [c for c in df.columns if c not in KEY_ORDER]]

    # ---- back-checks
    ck(len(df) == n_raw, f"row count unchanged ({n_raw:,})")
    ck(df["wt"].notna().all() and (df["wt"] > 0).all(), "wt present and > 0 on every row")
    ck(df["prov"].nunique() == 5 and df["dist"].nunique() == 30 and df["sector"].nunique() == 416, "5 provinces / 30 districts / 416 sectors")
    ck(set(df["sector"].unique()) == set(SECT_LABELS), "sector codes == NISR current 416-sector list")
    ck((df["sector"] // 100 == df["dist"]).all() and (df["dist"] // 10 == df["prov"]).all(), "sector nests in district nests in province")
    ck(set(df["sex"].dropna().unique()) <= {1, 2}, "sex in {1,2}")
    ck(df["age"].between(0, 130).all(), f"age in [0,130] (max {df['age'].max()})")
    ordinary = df if "collective" not in df.columns else df[df["collective"] == 0]
    heads = ordinary.groupby("hhid")["p02"].apply(lambda s: int((s == 1).sum()))
    ck(heads.eq(1).all(), f"exactly one head per (ordinary) household: {heads.eq(1).mean():.4%} of {len(heads):,}")
    ck(not df[df["hhid"].notna()].duplicated(["hhid", "pid"]).any(), "(hhid, pid) unique")
    ck((df.groupby("hhid")["wt_hh"].nunique() <= 1).all(), "wt_hh constant within household")
    ck((df.groupby("hhid")[["prov", "dist", "sector"]].nunique() <= 1).all().all(), "prov/dist/sector constant within household")
    n_urb = int((df.groupby("hhid")["urban"].nunique(dropna=False) > 1).sum())
    ck(n_urb == 0, f"urban constant within household ({n_urb} households differ; NISR data as shipped, head's value used in the household file)", hard=False)
    if "collective" in df.columns:
        ck(bool(((df["collective"] == 1) == (df["p03"] == 4)).mean() > 0.99), f"collective flag agrees with P03 == 4 ({((df['collective'] == 1) == (df['p03'] == 4)).mean():.4%})", hard=False)
    tot = df["wt"].sum(); pub = PUBLISHED_POP[y]
    ck(abs(tot / pub - 1) < 0.02, f"weighted population {tot:,.0f} within 2% of published {pub:,} ({tot / pub - 1:+.2%})")
    if "hhsize" in df.columns:
        ck((df.groupby("hhid").size() == df.groupby("hhid")["hhsize"].first()).all(), "shipped hhsize == roster count")
    log.info("households: %s | urban share (weighted): %.3f", f"{df['hhid'].nunique():,}", (df["wt"] * (df["urban"] == 1)).sum() / tot)
    ck.done()

    out = P["inter"] / f"Census_{y}_person_clean.dta"
    write_dta(df, out, vl, vv, f"Rwanda Census {y} person file (public-use sample, cleaned)", log)
    meta = {"n": len(df), "vars": list(df.columns), "var_labels": vl, "value_labels": {k: v for k, v in vv.items() if k in df.columns},
            "source": srcmap, "dtypes": {c: str(df[c].dtype) for c in df.columns}}
    if vl_original: meta["var_labels_original"] = vl_original
    save_json(meta, LOGS / f"clean_{y}_meta.json")
log.info("01_clean done for %s", YEARS)
