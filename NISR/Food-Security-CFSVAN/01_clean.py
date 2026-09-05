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
              "hhid": "Household id (unique within wave; composite string in 2009; absent on the 2015 woman / child files, which carry nutrition-form ids only)",
              "wt": "Household weight as shipped (normalised in 2006, population expansion 2012, household expansion 2015-2024, none in 2009)"}
CLUSTER_LABEL = {"2006": "Village / cluster id (zid, as shipped)", "2009": "Enumeration zone: province-district-zone composite (ID1-ID2-ID6; ID6 alone repeats across districts); 449 zones of 12 households (one of 24)",
                 "2012": "Village id (vill_id, as shipped; 750 villages of 10 households)", "2015": "Village, RECONSTRUCTED: households sharing the same embedded village-questionnaire answers (v_* and road_distance; 750 groups of 10 households = 25 villages x 30 districts); not an NISR identifier",
                 "2018": "No village / PSU identifier in the public household file", "2021": "No village / PSU identifier in the public household file", "2024": "No village / PSU identifier in the public household file"}
STATA_RESERVED = {"class", "in", "if", "int", "long", "byte", "double", "float", "str", "using", "with", "_all", "_n", "_b", "_cons", "_pi", "_rc", "_skip", "strl"}
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
    "2009": dict(files={"Data/CFSVA_2009_all_section_without_tables.sav": "household", "Data/CFSVA_2009_section_12_female_15_49.sav": "woman",         # cluster: composite id1-id2-id6 built below (audit: id6 alone repeats across districts)
                        "Data/CFSVA_2009_section_13_enfants.sav": "child", "Data/CFSVA_2009_pam_community.sav": "village",
                        "Data/CFSVA_2009_s10b.sav": "other", "Data/CFSVA_2009_s1_13_question.sav": "other", "Data/CFSVA_2009_s1_15_question.sav": "other",
                        "Data/CFSVA_2009_s1_21question.sav": "other", "Data/CFSVA_2009_s3_17_question.sav": "other", "Data/CFSVA_2009_s4.sav": "other",
                        "Data/CFSVA_2009_s7.sav": "other", "Data/CFSVA_2009_s8.sav": "other", "Data/CFSVA_2009_s8_823_32question.sav": "other", "Data/CFSVA_2009_s9_question.sav": "other"},
                 hhid=("id1", "id2", "id4", "id5", "id6", "id7"), prov="id1", dist_name="s00e", sector=None, cluster=None, wt=None, urban=None),
    "2012": dict(files={"CFSVA_2012_household.sav": "household", "CFSVA_2012_mother.sav": "woman", "CFSVA_2012_children.sav": "child",
                        "CFSVA_2012_children_mothers_household.sav": "child_mother_household", "CFSVA_2012_community.sav": "village"},
                 hhid="hh_id", prov="p_code", dist="d_code", sector="s_code", cluster="vill_id", wt="final_popweight", urban="urban_new"),   # urban_new = NISR's 2-category field; the native urban is 1 urban / 2 rural / 3 semi-urban (kept as urban_nisr)
    "2015": dict(files={"CFSVA_2015_master_db.sav": "household", "CFSVA_2015_mother_db.sav": "woman", "CFSVA_2015_child_db.sav": "child"},
                 hhid="key", prov="s0_c_prov", dist="s0_d_dist", sector="s0_e_sect", cluster=None, wt="weight", urban="urban"),             # household cluster reconstructed below; woman / child carry nutrition-form ids, not the household key
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
        for c in [c for c in df.columns if c in STATA_RESERVED]:                       # Stata reserved words cannot be variable names: rename explicitly (lineage kept)
            df = df.rename(columns={c: c + "_"}); vl[c + "_"] = vl.pop(c, ""); vv[c + "_"] = vv.pop(c, {}) if c in vv else {}; srcmap[c + "_"] = f"{c} (Stata reserved word)"
        if y == "2012" and "urban" in df.columns:                                       # native 3-category area (1 urban, 2 rural, 3 semi-urban) kept under its own name
            df = df.rename(columns={"urban": "urban_nisr"}); vl["urban_nisr"] = "Area of residence as shipped (1 urban, 2 rural, 3 semi-urban; NISR's 2-category urban_new is the key urban)"; vv["urban_nisr"] = vv.pop("urban", {}); srcmap["urban_nisr"] = "urban"
        if "v_code" in df.columns and len(vv.get("v_code", {})) > 5000:                # 2012: 14,837 village names exceed a Stata label set -> text companion
            lab = {float(k): str(v) for k, v in vv["v_code"].items() if str(k).replace(".", "", 1).isdigit()}
            df["v_name"] = pd.to_numeric(df["v_code"], errors="coerce").astype(float).map(lab); vl["v_name"] = "Village name (text of the v_code value labels, too many to be written as a Stata label set)"; srcmap["v_name"] = "value labels of v_code"
        # ---- household id
        hid = W["hhid"]
        if y == "2015" and unit in ("woman", "child"):                                  # audit: KEY / PARENT_KEY are nutrition-form record ids, not the household key (0 overlap with the household KEY)
            hid = None
            for c, txt in (("key", "Woman nutrition-form record id (KEY) -- NOT the household id; the 2015 woman / child files do not link to households"),
                           ("parent_key", "Parent nutrition-form id (PARENT_KEY) -- NOT the household id"), ("mhn_key", "Mother's record id (= the woman file's KEY; links most child rows to their mother)"),
                           ("chn_key", "Child nutrition-form record id")):
                if c in df.columns: vl[c] = txt
        if isinstance(hid, tuple):
            if all(c in df.columns for c in hid):
                df["hhid"] = df[list(hid)].astype("Int64").astype(str).agg("-".join, axis=1); srcmap["hhid"] = "composite " + "-".join(hid)
        elif hid in df.columns:
            df = df.rename(columns={hid: "hhid"}); vl["hhid"] = vl.pop(hid, ""); srcmap["hhid"] = hid
        elif y == "2012" and unit in ("woman", "child", "child_mother_household") and "hh_id" in df.columns:
            df = df.rename(columns={"hh_id": "hhid"}); srcmap["hhid"] = "hh_id"
        if "hhid" in df.columns and df["hhid"].dtype != object: df["hhid"] = pd.to_numeric(df["hhid"], errors="coerce")
        if y == "2009" and all(c in df.columns for c in ("id1", "id2", "id6")):        # enumeration zone is unique only within province x district (built before id1 becomes prov)
            df["cluster"] = df[["id1", "id2", "id6"]].astype("Int64").astype(str).agg("-".join, axis=1); srcmap["cluster"] = "composite id1-id2-id6 (province-district-zone; id6 alone repeats across districts)"
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
            u = pd.to_numeric(df["urban"], errors="coerce"); df["urban"] = u
            ck(set(u.dropna().unique()) <= {1, 2}, f"{y} {unit}: urban coded 1 / 2 only ({u.notna().mean():.1%} non-missing)")
        if "cluster" in df.columns: df["cluster"] = df["cluster"].astype(object).where(df["cluster"].notna(), "").astype(str).str.replace(r"\.0$", "", regex=True)
        if y == "2015" and unit == "household":                                         # PSU reconstructed from the village-questionnaire answers embedded in the household file
            sig = [c for c in df.columns if c.startswith("v_")] + [c for c in ("road_distance",) if c in df.columns]
            grp = df.groupby(sig, dropna=False, sort=False).ngroup(); sizes = grp.value_counts()
            ck(len(sizes) == 750 and (sizes == 10).all(), f"2015: embedded village signature forms 750 groups of 10 households ({len(sizes)} groups, sizes {sorted(sizes.unique())})")
            df["cluster"] = "v" + (grp + 1).astype(str).str.zfill(3); srcmap["cluster"] = f"RECONSTRUCTED: households sharing the same {len(sig)} embedded village-questionnaire fields (v_*, road_distance)"
            village = df.groupby("cluster", sort=True).agg(**{c: (c, "first") for c in ["prov", "dist"] + sig}, n_households=("hhid", "size")).reset_index()
            for c in sig: ck(df.groupby("cluster")[c].nunique(dropna=False).le(1).all(), f"2015: {c} constant within the reconstructed village", hard=False)
            village_meta = (village, {c: vl.get(c, "") for c in village.columns} | {"cluster": CLUSTER_LABEL["2015"], "n_households": "Households in the group (10 by design)", "prov": KEY_LABELS["prov"], "dist": KEY_LABELS["dist"]}, {c: vv[c] for c in sig if c in vv})
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
        if "cluster" in df.columns: vl["cluster"] = CLUSTER_LABEL.get(y, KEY_LABELS["cluster"]) if unit == "household" or y in ("2006", "2009", "2012") else vl.get("cluster") or KEY_LABELS["cluster"]
        df = destring(df, log, skip=("survey", "wave", "unit", "cluster", "hhid", "key", "parent_key", "chn_key", "woman_key", "child_key", "mhn_key", "v_name"))
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
        meta["files"][tag] = {"file": rel, "rows": len(df), "vars": list(df.columns), "var_labels": vl, "value_labels": {k: v for k, v in vv.items() if k in df.columns}, "source": srcmap, "out": out, "unit": unit,
                              "hhid_nonmissing": int(df["hhid"].notna().sum()) if "hhid" in df.columns else 0, "cluster_nonmissing": int((df["cluster"] != "").sum()) if "cluster" in df.columns else 0}
        if y == "2015" and unit == "household":                                         # the reconstructed 2015 village file (one row per group of 10 households)
            vdf, vvl, vvv = village_meta; vdf["survey"] = "CFSVA"; vdf["year"] = np.int16(2015); vdf["wave"] = "2015"; vdf["unit"] = "village"
            vvl.update({c: t for c, t in KEY_LABELS.items() if c in vdf.columns and c != "cluster"}); vvv.update({"prov": PROV_LABELS, "dist": DIST_LABELS})
            vdf = vdf[[c for c in KEY_ORDER if c in vdf.columns] + [c for c in vdf.columns if c not in KEY_ORDER]]
            write_dta(vdf, P["inter"] / "CFSVA_2015_village_clean.dta", vvl, vvv, "CFSVA 2015 village file (RECONSTRUCTED from the village answers embedded in the household file)", log)
            meta["files"]["village"] = {"file": rel + " (embedded village fields, collapsed)", "rows": len(vdf), "vars": list(vdf.columns), "var_labels": vvl, "value_labels": {k: v for k, v in vvv.items() if k in vdf.columns},
                                        "source": {"cluster": srcmap["cluster"], **{c: f"{c} (first value within the group; constant by construction)" for c in vdf.columns if c.startswith("v_") or c == "road_distance"}}, "out": "CFSVA_2015_village_clean.dta", "unit": "village",
                                        "hhid_nonmissing": 0, "cluster_nonmissing": len(vdf)}
    ck.done(); save_json(meta, LOGS / f"clean_{y}_meta.json")
log.info("01_clean done for %s", WANT)
