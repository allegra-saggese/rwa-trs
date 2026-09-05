"""
01_clean.py -- CFSVA: 1_Raw/<year>/** -> 2_Intermediate/CFSVA_<year>_<unit>_clean.dta

Units per wave: household, woman (15-49), child (under 5 / 6-59 months), village/community
(where shipped). Every file is cleaned with the key block (survey year wave prov dist sector
urban cluster hhid wt) attached where the file allows; women/child files carry the household
id where the file links to it. See NISR-Food-Security-CFSVAN.md (decisions log) for the per-wave id, geography and weight sources.
"""
import re, sys
import numpy as np, pandas as pd
from cfsva_helpers import (paths, get_logger, Checks, read_any, write_dta, lower_names, destring, downcast, save_json, LOGS)

log = get_logger("01_clean"); P = paths()
WANT = sys.argv[1:] or ["2006", "2009", "2012", "2015", "2018", "2021", "2024"]
KEY_ORDER = ["survey", "year", "wave", "unit", "prov", "dist", "sector", "urban", "cluster", "hhid", "wt"]
KEY_LABELS = {"survey": "Source survey", "year": "Survey year", "wave": "Wave (survey year)", "unit": "Unit of the file (household, woman, child, village)",
              "prov": "Province (1-5, NISR codes)", "dist": "District (11-57, NISR codes)", "sector": "Sector (1101-5715, NISR codes; where shipped)",
              "urban": "Area of residence (1 urban, 2 rural; where shipped)", "cluster": "Village / cluster id (as shipped)",
              "hhid": "Household id (unique within wave; composite string in 2009)", "wt": "Household weight as shipped (see DECISIONS: normalised in 2006/2012, none in 2009)"}
PROV_LABELS = {1: "City of Kigali", 2: "Southern Province", 3: "Western Province", 4: "Northern Province", 5: "Eastern Province"}
DIST_LABELS = {11: "Nyarugenge", 12: "Gasabo", 13: "Kicukiro", 21: "Nyanza", 22: "Gisagara", 23: "Nyaruguru", 24: "Huye", 25: "Nyamagabe", 26: "Ruhango",
               27: "Muhanga", 28: "Kamonyi", 31: "Karongi", 32: "Rutsiro", 33: "Rubavu", 34: "Nyabihu", 35: "Ngororero", 36: "Rusizi", 37: "Nyamasheke",
               41: "Rulindo", 42: "Gakenke", 43: "Musanze", 44: "Burera", 45: "Gicumbi", 51: "Rwamagana", 52: "Nyagatare", 53: "Gatsibo", 54: "Kayonza",
               55: "Kirehe", 56: "Ngoma", 57: "Bugesera"}
DIST_BY_NAME = {v.upper(): k for k, v in DIST_LABELS.items()}
URBAN_LABELS = {1: "Urban", 2: "Rural"}

def to_dist(s):
    x = pd.to_numeric(s, errors="coerce"); return np.where(x >= 100, (x // 100) * 10 + x % 100, x)
def to_sector(s):
    x = pd.to_numeric(s, errors="coerce")
    return np.where(x >= 10000, (x // 10000) * 1000 + ((x % 10000) // 100) * 100 + x % 100, x)   # 5-digit p-dd-ss -> 4-digit

# per wave: files -> unit, and the native names of the keys
WAVES = {
    "2006": dict(files={"Data/CFSVA_2006_june_10_section1_11.sav": "household", "Data/CFSVA_2006_june10_section12.sav": "woman", "Data/CFSVA_2006_june10_section13_mg.sav": "child"},
                 hhid="hid", prov="prov06", dist="distr06", sector="sect06", cluster="zid", wt="hhweight", urban=None),
    "2009": dict(files={"Data/CFSVA_2009_all_section_without_tables.sav": "household", "Data/CFSVA_2009_section_12_female_15_49.sav": "woman",
                        "Data/CFSVA_2009_section_13_enfants.sav": "child", "Data/CFSVA_2009_pam_community.sav": "village",
                        "Data/CFSVA_2009_s10b.sav": "other", "Data/CFSVA_2009_s1_13_question.sav": "other", "Data/CFSVA_2009_s1_15_question.sav": "other",
                        "Data/CFSVA_2009_s1_21question.sav": "other", "Data/CFSVA_2009_s3_17_question.sav": "other", "Data/CFSVA_2009_s4.sav": "other",
                        "Data/CFSVA_2009_s7.sav": "other", "Data/CFSVA_2009_s8.sav": "other", "Data/CFSVA_2009_s8_823_32question.sav": "other", "Data/CFSVA_2009_s9_question.sav": "other"},
                 hhid=("id1", "id2", "id4", "id5", "id6", "id7"), prov="id1", dist_name="s00e", sector=None, cluster="id6", wt=None, urban=None),
    "2012": dict(files={"CFSVA_2012_household.sav": "household", "CFSVA_2012_mother.sav": "woman", "CFSVA_2012_children.sav": "child",
                        "CFSVA_2012_children_mothers_household.sav": "child_mother_household", "CFSVA_2012_community.sav": "village"},
                 hhid="hh_id", prov="p_code", dist="d_code", sector="s_code", cluster="vill_id", wt="final_popweight", urban="urban"),
    "2015": dict(files={"CFSVA_2015_master_db.sav": "household", "CFSVA_2015_mother_db.sav": "woman", "CFSVA_2015_child_db.sav": "child"},
                 hhid="key", prov="s0_c_prov", dist="s0_d_dist", sector="s0_e_sect", cluster="s0_g_vill", wt="weight", urban="urban"),
    "2018": dict(files={"CFSVA_2018_db_householdques_201904.dta": "household", "CFSVA_2018_db_childandmother_201904.dta": "child", "CFSVA_2018_db_villageques_201904.dta": "village"},
                 hhid="parent_key", prov="s0_c_prov", dist="s0_d_dist", sector="s0_e_sect", cluster="s0_g_vill", wt="finalweight", urban="urbanrural"),
    "2021": dict(files={"Microdata/CFSVA_2021_hh_master_dataset.dta": "household", "Microdata/CFSVA_2021_cfsvahh2021_under_5_childwithmother.dta": "child", "Microdata/CFSVA_2021_VILLAGE.dta": "village"},
                 hhid="index", prov="s0_c_prov", dist="s0_d_dist", sector=None, cluster=None, wt="finalweight", urban="urbanrural"),
    "2024": dict(files={"Microdata/stata/CFSVA_2024_hh.dta": "household", "Microdata/stata/CFSVA_2024_hh_women_15_49_years.dta": "woman", "Microdata/stata/CFSVA_2024_hh_child_6_59_months.dta": "child"},
                 hhid="___index", prov="s0_c_prov", dist="s0_d_dist", sector=None, cluster=None, wt="finalweight", urban="urbanrural"),
}

for y in WANT:
    W = WAVES[y]; log.info("================ %s ================", y); ck = Checks(log); meta = {"year": y, "files": {}}
    keys_hh = None
    for rel, unit in W["files"].items():
        f = P["raw"] / y / rel
        if not f.exists(): log.warning("missing %s", f); continue
        df, vl, vv = read_any(f); df, vl, vv = lower_names(df, vl, vv, log); srcmap = {}
        # ---- household id
        hid = W["hhid"]
        if isinstance(hid, tuple):
            if all(c in df.columns for c in hid):
                df["hhid"] = df[list(hid)].astype("Int64").astype(str).agg("-".join, axis=1); srcmap["hhid"] = "composite " + "-".join(hid)
        elif hid in df.columns:
            df = df.rename(columns={hid: "hhid"}); vl["hhid"] = vl.pop(hid, ""); srcmap["hhid"] = hid
        elif unit != "village" and y == "2015" and "parent_key" in df.columns:
            df = df.rename(columns={"parent_key": "hhid"}); srcmap["hhid"] = "parent_key (does NOT match the household file's key -- see DECISIONS)"
        elif y == "2012" and unit in ("woman", "child", "child_mother_household") and "hh_id" in df.columns:
            df = df.rename(columns={"hh_id": "hhid"}); srcmap["hhid"] = "hh_id"
        if "hhid" in df.columns and df["hhid"].dtype != object: df["hhid"] = pd.to_numeric(df["hhid"], errors="coerce")
        # ---- geography, weight, urban
        for key, src in (("prov", W.get("prov")), ("dist", W.get("dist")), ("sector", W.get("sector")), ("cluster", W.get("cluster")), ("wt", W.get("wt")), ("urban", W.get("urban"))):
            if src and src in df.columns and key not in df.columns:
                df = df.rename(columns={src: key}); vl[key] = vl.pop(src, ""); vv.pop(src, None); srcmap[key] = src
        if "dist" in df.columns: df["dist"] = to_dist(df["dist"])
        elif W.get("dist_name") and W["dist_name"] in df.columns:
            import difflib
            names = df[W["dist_name"]].astype(str).str.strip().str.upper()
            lookup = {n: DIST_BY_NAME.get(n) or next((DIST_BY_NAME[m] for m in difflib.get_close_matches(n, list(DIST_BY_NAME), n=1, cutoff=0.75)), np.nan) for n in names.unique()}
            fuzzy = {n: v for n, v in lookup.items() if n not in DIST_BY_NAME and not pd.isna(v)}
            if fuzzy: log.info("  %s: district names matched by closest spelling: %s", y, fuzzy)
            df["dist"] = names.map(lookup); srcmap["dist"] = f"{W['dist_name']} (district name; closest spelling for variants such as RURINDO -> Rulindo)"
        if "sector" in df.columns: df["sector"] = to_sector(df["sector"])
        if "urban" in df.columns:
            u = pd.to_numeric(df["urban"], errors="coerce")
            if y == "2012": df["urban"] = np.where(u == 1, 1, np.where(u == 0, 2, np.nan)); srcmap["urban"] = srcmap.get("urban", "urban") + " (1 urban, 0 rural -> 1/2)"
        if "cluster" in df.columns: df["cluster"] = df["cluster"].astype(object).where(df["cluster"].notna(), "").astype(str).str.replace(r"\.0$", "", regex=True)
        # ---- attach household keys to women/child files that lack them
        if unit == "household" and "hhid" in df.columns:
            keys_hh = df[["hhid"] + [c for c in ("prov", "dist", "sector", "urban", "cluster", "wt") if c in df.columns]].drop_duplicates("hhid")
        elif keys_hh is not None and "hhid" in df.columns:
            need = [c for c in keys_hh.columns if c != "hhid" and c not in df.columns]
            if need:
                df = df.merge(keys_hh[["hhid"] + need], on="hhid", how="left"); rate = df["hhid"].isin(keys_hh["hhid"]).mean()
                log.info("  %s %s: %d keys attached from the household file (%.1f%% of rows matched)", y, unit, len(need), 100 * rate)
                ck(rate > 0.95, f"{y} {unit}: rows link to a household in the household file ({rate:.1%})", hard=False)
        df["survey"] = "CFSVA"; df["year"] = np.int16(int(y)); df["wave"] = y; df["unit"] = unit
        vv.update({"prov": PROV_LABELS, "dist": DIST_LABELS, "urban": URBAN_LABELS})
        for c, t in KEY_LABELS.items():
            if c in df.columns: vl[c] = t
        df = destring(df, log, skip=("survey", "wave", "unit", "cluster", "hhid", "key", "parent_key", "chn_key", "woman_key", "child_key"))
        df = downcast(df, keep_double=("wt",))
        df = df[[c for c in KEY_ORDER if c in df.columns] + [c for c in df.columns if c not in KEY_ORDER]]
        if unit == "household":
            ck("hhid" in df.columns and df["hhid"].is_unique, f"{y}: household id unique ({len(df):,} households)")
            if "wt" in df.columns: ck((df["wt"] > 0).all(), f"{y}: household weight > 0")
            else: ck(False, f"{y}: no household weight shipped (wt absent; treat as unweighted)", hard=False)
        if "prov" in df.columns: ck(set(pd.to_numeric(df["prov"], errors="coerce").dropna().unique()) <= set(PROV_LABELS), f"{y} {unit}: province codes 1-5")
        if "dist" in df.columns: ck(set(pd.Series(df["dist"]).dropna().unique()) <= set(DIST_LABELS), f"{y} {unit}: district codes on the 11-57 scheme ({pd.Series(df['dist']).nunique()} districts)")
        tag = unit if unit not in ("other", "child_mother_household") else re.sub(rf"^cfsva_{y}_", "", f.stem.lower())
        out = f"CFSVA_{y}_{tag}_clean.dta"
        write_dta(df, P["inter"] / out, vl, vv, f"CFSVA {y} {unit} file (cleaned)", log)
        meta["files"][tag] = {"file": rel, "rows": len(df), "vars": list(df.columns), "var_labels": vl, "value_labels": {k: v for k, v in vv.items() if k in df.columns}, "source": srcmap, "out": out}
    ck.done(); save_json(meta, LOGS / f"clean_{y}_meta.json")
log.info("01_clean done for %s", WANT)
