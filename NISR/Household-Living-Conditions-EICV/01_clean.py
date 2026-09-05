"""
01_clean.py -- EICV: 1_Raw/<wave>/*  ->  2_Intermediate/EICV_<wave>_{person,household,<module>}_clean.dta

For each wave (EICV1, EICV2, EICV3, EICV4_CS/VUP, EICV5_CS/VUP, EICV7_CS/VUP, EICV3_4_Panel):
  1. build the household key table from the wave's household base module
     (prov dist urban cluster wt wt_hh on the NISR current codes);
  2. clean EVERY module file: lower-case names, normalise the household/person ids to
     hhid/pid, attach the key block, classify the module as person-level ((hhid,pid) unique),
     household-level (hhid unique) or other, write it;
  3. assemble the wave's PERSON file (roster base + every person-level module, 1:1) and
     HOUSEHOLD file (household base + every household-level module + poverty file, 1:1,
     plus hhsize and the head's sex/age from the roster).
See DECISIONS.md for every choice.
"""
import re, sys
import numpy as np, pandas as pd
from eicv_helpers import (paths, get_logger, Checks, read_any, write_dta, lower_names, destring, downcast,
                          save_json, LOGS)

log = get_logger("01_clean")
P = paths()

# ------------------------------------------------------------------ wave configuration
# raw: folder under 1_Raw; base_hh: household base module stem(s); base_p: roster module stem;
# geo: raw name -> key name for the household key table; wt: household weight variable;
# extra: (source wave folder, file stem) of files NISR shipped in another wave's folder.
WAVES = {
    "EICV1":     dict(year=2001, sample="CS",  raw="EICV1/EICV1_data_spss", prefixes=["EICV1_"],
                      base_hh=["s6_housing", "s0_id", "eicv1_remap_weights"], base_p="s1_demographics",
                      geo={"id1_n": "prov", "id2_n": "dist", "milieu": "urban", "zdkey": "cluster"}, wt="pond",
                      rel="s1q2", sex="s1q1", age="s1q3a",
                      extra=[("EICV2", "EICV2_eicv1_econbase"), ("EICV2", "EICV2_eicv1_jobstatus_subsistence1")]),
    "EICV2":     dict(year=2006, sample="CS",  raw="EICV2", prefixes=["EICV2_eng_", "EICV2_"],
                      base_hh=["s0_id", "s5_housing", "b_filters"], base_p="s1_demo",
                      geo={"id1_n": "prov", "id2_n": "dist", "id0": "urban", "clust": "cluster"}, wt="hh_wt",
                      rel="s1q2", sex="s1q1", age="s1q3a", skip=["EICV2_eicv1_econbase", "EICV2_eicv1_jobstatus_subsistence1"]),
    "EICV3":     dict(year=2011, sample="CS",  raw="EICV3", prefixes=["EICV3_"],
                      base_hh=["s05abcd_housing"], base_p="s01_hhmembers_s02_education_s03_health_s04_migration",
                      geo={"province": "prov", "district": "dist", "urb2002": "urban", "cluster": "cluster"}, wt="hh_wt",
                      rel="s1q2", sex="s1q1", age="s1q3y", extra=[("EICV4_CS", "EICV4_CS_eicv3_povertyfile_jan2014")]),
    "EICV3_4_Panel": dict(year=2014, sample="PANEL", raw="EICV3_4_Panel", prefixes=["EICV3_4_Panel_"], base_hh=[], base_p=None,
                      geo={"province": "prov", "district": "dist", "clust": "cluster"}, wt="weight", rel=None, sex=None, age=None),
    "EICV4_CS":  dict(year=2014, sample="CS",  raw="EICV4_CS", prefixes=["EICV4_CS_cs_", "EICV4_CS_"],
                      base_hh=["s0_s5_household", "eicv4_poverty_file"], base_p="s1_s2_s3_s4_s6a_s6e_s6f_person",
                      geo={"province": "prov", "district": "dist", "ur2_2012": "urban", "clust": "cluster"}, wt="weight",
                      rel="s1q2", sex="s1q1", age="s1q3y", skip=["EICV4_CS_eicv3_povertyfile_jan2014"]),
    "EICV4_VUP": dict(year=2014, sample="VUP", raw="EICV4_VUP", prefixes=["EICV4_VUP_vup_", "EICV4_VUP_"],
                      base_hh=["s0_s5_household_dta"], base_p="s1_s2_s3_s4_s6a_s6e_s6f_person",
                      geo={"province": "prov", "district": "dist", "ur2_2012": "urban", "clust": "cluster"}, wt="weight",
                      rel="s1q2", sex="s1q1", age="s1q3y"),
    "EICV5_CS":  dict(year=2017, sample="CS",  raw="EICV5_CS", prefixes=["EICV5_CS_cs_", "EICV5_CS_"],
                      base_hh=["s0_s5_household", "eicv5_poverty_file"], base_p="s1_s2_s3_s4_s6a_s6e_person",
                      geo={"province": "prov", "district": "dist", "ur": "urban", "clust": "cluster"}, wt="weight",
                      rel="s1q2", sex="s1q1", age="s1q3y"),
    "EICV5_VUP": dict(year=2017, sample="VUP", raw="EICV5_VUP", prefixes=["EICV5_VUP_vup_", "EICV5_VUP_"],
                      base_hh=["s0_s5_household"], base_p="s1_s2_s3_s4_s6a_s6e_person",
                      geo={"province": "prov", "district": "dist", "ur": "urban", "clust": "cluster"}, wt="weight",
                      rel="s1q2", sex="s1q1", age="s1q3y",
                      # the EICV5 VUP files carry the EICV4 panel household id as `hhid` (not unique: split
                      # households) and the EICV5 id as `key_17`/`pid_17`; the EICV5 ids are the keys here.
                      idmap={"hhid": "hhid_eicv4", "pid": "pid_eicv4", "key_17": "hhid", "pid_17": "pid"}),
    "EICV7_CS":  dict(year=2024, sample="CS",  raw="EICV7_CS", prefixes=["EICV7_CS_cs_", "EICV7_CS_"],
                      base_hh=["s01_s5_s7_household", "eicv7_poverty_file"], base_p="s0_s1_s2_s3_s4_s6a_s6b_s6c_person",
                      geo={"province": "prov", "district": "dist", "ur": "urban", "clust": "cluster"}, wt="weight",
                      rel="s1q2", sex="s1q1", age="s1q3y"),
    "EICV7_VUP": dict(year=2024, sample="VUP", raw="EICV7_VUP", prefixes=["EICV7_VUP_vup_", "EICV7_VUP_"],
                      base_hh=["s01_s5_s7_household"], base_p="s0_s1_s2_s3_s4_s6a_s6b_s6c_person",
                      geo={"province": "prov", "district": "dist", "ur": "urban", "clust": "cluster"}, wt="weight",
                      rel="s1q2", sex="s1q1", age="s1q3y"),
}
WANT = sys.argv[1:] or list(WAVES)
KEY_ORDER = ["survey", "year", "wave", "sample", "prov", "dist", "urban", "cluster", "hhid", "pid", "sex", "age", "wt", "wt_hh"]
KEY_LABELS = {"survey": "Source survey", "year": "Survey year (mid-fieldwork)", "wave": "Wave / round id", "sample": "CS = national cross-section, VUP = VUP booster, PANEL = EICV3-4 panel link",
              "prov": "Province (1-5, NISR codes)", "dist": "District (11-57, NISR current codes)", "urban": "Area of residence (1 urban, 2 rural)",
              "cluster": "Sampling cluster / enumeration area (as shipped)", "hhid": "Household id (unique within wave)",
              "pid": "Person number within the household", "sex": "Sex (1 male, 2 female)", "age": "Age in years",
              "wt": "Household weight carried by every row (sums to persons in person files, to households in household files)",
              "wt_hh": "Household weight (same value as wt; sums to the number of households)", "pid_nisr": "NISR person id as shipped (EICV3 PID = hhid*100 + person)",
              "hhid_eicv4": "EICV4 panel household id carried in the EICV5 VUP files (not unique: split households)", "pid_eicv4": "EICV4 panel person id carried in the EICV5 VUP files"}
PROV_LABELS = {1: "City of Kigali", 2: "Southern Province", 3: "Western Province", 4: "Northern Province", 5: "Eastern Province"}
DIST_LABELS = {11: "Nyarugenge", 12: "Gasabo", 13: "Kicukiro", 21: "Nyanza", 22: "Gisagara", 23: "Nyaruguru", 24: "Huye", 25: "Nyamagabe", 26: "Ruhango",
               27: "Muhanga", 28: "Kamonyi", 31: "Karongi", 32: "Rutsiro", 33: "Rubavu", 34: "Nyabihu", 35: "Ngororero", 36: "Rusizi", 37: "Nyamasheke",
               41: "Rulindo", 42: "Gakenke", 43: "Musanze", 44: "Burera", 45: "Gicumbi", 51: "Rwamagana", 52: "Nyagatare", 53: "Gatsibo", 54: "Kayonza",
               55: "Kirehe", 56: "Ngoma", 57: "Bugesera"}
URBAN_LABELS = {1: "Urban", 2: "Rural"}
HH_ID_NAMES = ("hhid", "key")
PID_NAMES = ("pid", "id", "idind")

# ------------------------------------------------------------------ universes (who was asked), by wave and section
# From the questionnaires in z_Documentation (EICV1/EICV2 French, EICV3 Kinyarwanda section headers + English
# pdf sections, EICV4/5/7 English) — see DOCUMENTATION.md. Keyed by questionnaire section number; applied to
# variables named s<section><part>q<n> and to module stems s<section>..., so the codebook can show the universe.
SECTION_UNIVERSE = {
    "EICV1": {1: "all household members (roster; marital status 12+)", 2: "members aged 7+ (general education; school career parts for under-40s; literacy 5+)",
              3: "all household members (health)", 4: "members aged 7+ (economic activity over the last 12 months; main + secondary job)",
              5: "members aged 15+ (migration)", 6: "household (housing)", 7: "household (identification of respondents for part B)",
              8: "household / farm (agriculture, livestock)", 9: "household (expenditure and own consumption)", 10: "household (non-farm enterprises)",
              11: "household (transfers)", 12: "household (credit, durables, savings)"},
    "EICV2": {1: "all household members (roster; marital status 12+)", 2: "members aged 6+ (education, literacy)", 3: "all household members (health)",
              4: "members aged 15+ (migration)", 5: "household (housing, services)", 6: "members aged 6+ (economic activity over the last 12 months; 6D-6F employed only)",
              7: "household (non-farm enterprises)", 8: "household / farm (agriculture, livestock)", 9: "household (expenditure and own consumption)",
              10: "household (transfers, other income)", 11: "household (credit, durables, savings)"},
    "EICV3": {1: "all household members (roster)", 2: "members aged 6+ (education)", 3: "all household members (health, disability)",
              4: "all household members (migration of 6+ months)", 5: "household (housing, services)", 6: "members aged 6+ (economic activity over the last 12 months; 6C-6F employed only)",
              7: "household (non-farm enterprises)", 8: "household / farm (agriculture, livestock)", 9: "household (expenditure and own consumption)",
              10: "household (transfers, other income)", 11: "household (credit, durables, savings)"},
    "EICV4": {1: "all household members (roster; marital status 12+)", 2: "all household members (migration)", 3: "all household members (health)",
              4: "members aged 3+ (education; literacy and ICT part B 10+)", 5: "household (housing, services)",
              6: "members aged 6+ (usual activity over the last 12 months; 6B-6E employed; 6F domestic work 6+)", 7: "household / farm (agriculture, livestock)",
              8: "household (expenditure and own consumption)", 9: "household (transfers, VUP, other income)", 10: "household (credit, durables, savings)"},
    "EICV7": {0: "household (identification, food habits)", 1: "all household members (roster; marital status 12+)", 2: "all household members (migration)",
              3: "all household members (health; disability items 5+)", 4: "members aged 3+ (education; literacy and ICT part B 10+)",
              5: "household (housing, shocks, services)", 6: "members aged 6+ (economic activity over the LAST 7 DAYS, main job only; 6C domestic work 5-17)",
              7: "household / farm (agriculture, livestock)", 8: "household (consumption by source)", 9: "household (cash transfers, VUP, other income)",
              10: "household (credit, durables, savings)"},
}
SECTION_UNIVERSE["EICV5"] = dict(SECTION_UNIVERSE["EICV4"]); SECTION_UNIVERSE["EICV5"][3] = "all household members (health; disability items 5+)"
def _base_wave(wave): return wave.split("_")[0] if wave != "EICV3_4_Panel" else "EICV3"
def universe_for(wave, names):
    """{name: universe text} for variable names (s<sec><part>q...) or module stems (s<sec>...)."""
    import re
    table = SECTION_UNIVERSE.get(_base_wave(wave), {}); out = {}
    for n in names:
        m = re.match(r"^s0?(\d{1,2})(?:[a-z]|q|_|$)", n)
        if m and int(m.group(1)) in table: out[n] = table[int(m.group(1))]
    return out

def module_name(stem, prefixes):
    for p in prefixes:
        if stem.startswith(p): stem = stem[len(p):]; break
    stem = re.sub(r"_dta$", "", stem)
    return stem.lower()

def to_dist(s):
    """NISR district codes to the 11-57 scheme: 101 -> 11 (prov*100+seq), '0101' -> 11, 11 -> 11."""
    x = pd.to_numeric(s, errors="coerce")
    return np.where(x >= 100, (x // 100) * 10 + x % 100, x)

def normalise_keys(df, vl, vv, W, srcmap):
    """hhid / pid from the wave's id names; geography/weight natives renamed to key names."""
    for c in HH_ID_NAMES:
        if c in df.columns and "hhid" not in df.columns and c != "hhid":
            df = df.rename(columns={c: "hhid"}); vl["hhid"] = vl.pop(c, ""); srcmap.setdefault("hhid", c)
    for c in PID_NAMES:
        if c in df.columns and "pid" not in df.columns and c != "pid":
            df = df.rename(columns={c: "pid"}); vl["pid"] = vl.pop(c, ""); srcmap.setdefault("pid", c)
    if "hhid" in df.columns: df["hhid"] = pd.to_numeric(df["hhid"], errors="coerce").astype("Int64")
    if "pid" in df.columns:
        p = pd.to_numeric(df["pid"], errors="coerce")
        if W["raw"] == "EICV3" and p.max() > 1000:         # EICV3 PID = hhid*100 + person
            df["pid_nisr"] = p.astype("Int64"); p = p % 100; srcmap.setdefault("pid", "PID % 100 (PID = hhid*100 + person)")
        df["pid"] = p.astype("Int64")
    for raw, key in W["geo"].items():
        if raw in df.columns and key not in df.columns:
            df = df.rename(columns={raw: key}); vl[key] = vl.pop(raw, ""); vv.pop(raw, None); srcmap.setdefault(key, raw)
    if W["wt"] in df.columns and "wt" not in df.columns:
        df = df.rename(columns={W["wt"]: "wt"}); vl["wt"] = vl.pop(W["wt"], ""); srcmap.setdefault("wt", W["wt"])
    if "dist" in df.columns: df["dist"] = to_dist(df["dist"])
    if "cluster" in df.columns: df["cluster"] = df["cluster"].astype(object).where(df["cluster"].notna(), "").astype(str).str.replace(r"\.0$", "", regex=True)
    return df, vl, vv

def stamp(df, W, wave):
    df["survey"] = "EICV"; df["year"] = np.int16(W["year"]); df["wave"] = wave; df["sample"] = W["sample"]
    return df

def join_1to1(base, other, on, tag, log):
    """left-join `other` onto `base` on `on`; colliding non-key names get _<tag>."""
    other = other.drop(columns=[c for c in ("_merge",) if c in other.columns])   # NISR poverty files ship a Stata _merge artefact
    base = base.drop(columns=[c for c in ("_merge",) if c in base.columns])
    ren = {c: f"{c}_{tag}"[:32] for c in other.columns if c not in on and c in base.columns}
    other = other.rename(columns=ren)
    out = base.merge(other, on=on, how="left", indicator=True)
    rate = (out["_merge"] == "both").mean()
    # a colliding column that merely repeats the base (same values wherever both are non-missing)
    # is a redundant copy and is dropped; a copy that differs is kept with the _<tag> suffix.
    dropped = []
    for c, n in list(ren.items()):
        a, b = out[c], out[n]
        both = a.notna() & b.notna()
        same = (a[both].astype(str) == b[both].astype(str)).all() if both.any() else True
        if same: out = out.drop(columns=[n]); dropped.append(c); del ren[c]
    log.info("   joined %-45s %6.2f%% of base rows matched, %d columns added%s%s", tag, 100 * rate, len(other.columns) - len(on) - len(dropped),
             f", identical copies dropped: {dropped[:8]}" if dropped else "", f", differing copies kept as _{tag}: {list(ren)[:6]}" if ren else "")
    return out.drop(columns="_merge"), ren

for wave in WANT:
    W = WAVES[wave]
    log.info("================ %s ================", wave)
    ck = Checks(log)
    rawdir = P["raw"] / W["raw"]
    files = sorted([f for f in rawdir.iterdir() if f.suffix.lower() in (".dta", ".sav")])
    files = [f for f in files if f.stem not in W.get("skip", [])]
    for src_wave, stem in W.get("extra", []):
        cand = [f for f in (P["raw"] / src_wave).iterdir() if f.stem == stem]
        files += cand
    modules, labels, vlabels, srcmaps, level = {}, {}, {}, {}, {}
    for f in files:
        name = module_name(f.stem, W["prefixes"] + [f"{src}_" for src, _ in W.get("extra", [])])
        df, vl, vv = read_any(f)
        df, vl, vv = lower_names(df, vl, vv, log)
        srcmap = {}
        if W.get("idmap"):
            m = {k: v for k, v in W["idmap"].items() if k in df.columns}
            df = df.rename(columns=m); vl.update({v: vl.pop(k, "") for k, v in m.items()}); srcmap.update({v: k for k, v in m.items()})
        df, vl, vv = normalise_keys(df, vl, vv, W, srcmap)
        modules[name], labels[name], vlabels[name], srcmaps[name] = df, vl, vv, srcmap
        log.info("read %-50s -> %-45s %8s rows x %4d vars", f.name, name, f"{len(df):,}", df.shape[1])

    # ---------------- household key table
    hh_base = None
    for stem in W["base_hh"]:
        m = modules.get(stem)
        if m is None: continue
        hh_base = m if hh_base is None else join_1to1(hh_base, m, ["hhid"], stem, log)[0]
    keycols = [c for c in ["prov", "dist", "urban", "cluster", "wt"] if hh_base is not None and c in hh_base.columns]
    keys = hh_base[["hhid"] + keycols].drop_duplicates("hhid") if hh_base is not None else None
    if keys is not None:
        ck(keys["hhid"].is_unique, f"{wave}: hhid unique in household base ({len(keys):,} households)")
        for c in keycols: ck(keys[c].notna().all(), f"{wave}: {c} complete in household key table")
        if "prov" in keycols: ck(set(keys["prov"].unique()) <= set(PROV_LABELS), f"{wave}: province codes 1-5")
        if "dist" in keycols: ck(set(keys["dist"].unique()) == set(DIST_LABELS), f"{wave}: 30 districts on the 11-57 scheme")
        if "wt" in keycols: ck((keys["wt"] > 0).all(), f"{wave}: household weight > 0")

    # ---------------- attach keys to every module, classify, write
    meta_modules = {}
    for name, df in modules.items():
        vl, vv, srcmap = labels[name], vlabels[name], srcmaps[name]
        if keys is not None and "hhid" in df.columns:
            need = [c for c in keycols if c not in df.columns]
            if need:
                df = df.merge(keys[["hhid"] + need], on="hhid", how="left")
                for c in need: srcmap[c] = f"household key table ({W['base_hh']})"
            rate = df["hhid"].isin(keys["hhid"]).mean()
        else:
            rate = np.nan
        if "hhid" not in df.columns or (not np.isnan(rate) and rate < 0.5):
            lvl = "other"      # community questionnaires etc.: no household key
        elif df["hhid"].is_unique: lvl = "household"
        elif "pid" in df.columns and df["pid"].notna().all() and not df.duplicated(["hhid", "pid"]).any(): lvl = "person"
        else: lvl = "multi"    # several rows per household or person (plots, items, jobs, ...)
        level[name] = lvl
        df = stamp(df, W, wave)
        if "wt" in df.columns: df["wt_hh"] = df["wt"]
        vv.update({"prov": PROV_LABELS, "dist": DIST_LABELS, "urban": URBAN_LABELS})
        for c, t in KEY_LABELS.items():
            if c in df.columns: vl[c] = t
        df = destring(df, log, skip=("survey", "wave", "sample", "cluster"))
        df = downcast(df, keep_double=("wt", "wt_hh", "hhid", "pid_nisr", "pop_wt", "hh_wt", "pond", "weight"))
        df = df[[c for c in KEY_ORDER if c in df.columns] + [c for c in df.columns if c not in KEY_ORDER]]
        modules[name] = df
        meta_modules[name] = {"level": lvl, "rows": len(df), "vars": df.shape[1], "hh_match_rate": None if np.isnan(rate) else round(float(rate), 4),
                              "universe": universe_for(wave, [name]).get(name, "")}
        write_dta(df, P["inter"] / f"EICV_{wave}_{name}_clean.dta", vl, vv, f"EICV {wave} module {name} ({lvl}-level)", log)
    log.info("module levels: %s", {k: v["level"] for k, v in meta_modules.items()})

    # ---------------- PERSON file
    meta = {"wave": wave, "year": W["year"], "sample": W["sample"], "modules": meta_modules}
    if W["base_p"] and W["base_p"] in modules:
        person = modules[W["base_p"]].copy(); pvl, pvv = dict(labels[W["base_p"]]), dict(vlabels[W["base_p"]])
        psrc = dict(srcmaps[W["base_p"]]); psrc.update({"base module": W["base_p"]})
        for name, df in modules.items():
            if name == W["base_p"] or level[name] != "person": continue
            other = df.drop(columns=[c for c in KEY_ORDER + ["wt_hh", "pid_nisr"] if c in df.columns and c not in ("hhid", "pid")])
            person, ren = join_1to1(person, other, ["hhid", "pid"], name, log)
            for c in other.columns:
                n = ren.get(c, c)
                if c not in ("hhid", "pid"):
                    pvl[n] = labels[name].get(c, ""); psrc[n] = f"module {name}"
                    if c in vlabels[name]: pvv[n] = vlabels[name][c]
        for raw, key in (("sex", W["sex"]), ("age", W["age"])):
            if key and key in person.columns:
                person = person.rename(columns={key: raw}); pvl[raw] = KEY_LABELS[raw]; pvv[raw] = pvv.pop(key, {}); psrc[raw] = key
        person = person[[c for c in KEY_ORDER if c in person.columns] + [c for c in person.columns if c not in KEY_ORDER]]
        ck(not person.duplicated(["hhid", "pid"]).any(), f"{wave}: (hhid, pid) unique in the person file")
        ck(person["wt"].notna().all() and (person["wt"] > 0).all(), f"{wave}: wt present and > 0 on every person row")
        if "sex" in person: ck(set(person["sex"].dropna().unique()) <= {1, 2}, f"{wave}: sex in {{1,2}}")
        log.info("%s person file: %s rows x %s vars; weighted persons = %s", wave, f"{len(person):,}", person.shape[1], f"{person['wt'].sum():,.0f}")
        person = downcast(person, keep_double=("wt", "wt_hh", "hhid", "pid_nisr", "pop_wt", "hh_wt", "pond", "weight"))
        write_dta(person, P["inter"] / f"EICV_{wave}_person_clean.dta", pvl, pvv, f"EICV {wave} person file (roster + person-level modules)", log)
        meta["person"] = {"n": len(person), "vars": list(person.columns), "var_labels": pvl, "value_labels": {k: v for k, v in pvv.items() if k in person.columns}, "source": psrc,
                          "universe": universe_for(wave, person.columns)}
    else:
        person = None

    # ---------------- HOUSEHOLD file
    if hh_base is not None:
        hh = hh_base.copy()
        hvl = {}; hvv = {}; hsrc = {"base modules": ", ".join(W["base_hh"])}
        for stem in W["base_hh"]:
            if stem in labels:
                hvl.update(labels[stem]); hvv.update(vlabels[stem])
                for c in modules[stem].columns: hsrc.setdefault(c, f"module {stem}")
        for name, df in modules.items():
            if name in W["base_hh"] or level[name] != "household": continue
            other = df.drop(columns=[c for c in KEY_ORDER + ["wt_hh", "pid_nisr"] if c in df.columns and c != "hhid"])
            hh, ren = join_1to1(hh, other, ["hhid"], name, log)
            for c in other.columns:
                n = ren.get(c, c)
                if c != "hhid":
                    hvl[n] = labels[name].get(c, ""); hsrc[n] = f"module {name}"
                    if c in vlabels[name]: hvv[n] = vlabels[name][c]
        if person is not None:
            g = person.groupby("hhid", sort=False)
            agg = pd.DataFrame({"hhsize": g.size()})
            if W["rel"] and W["rel"] in person.columns:
                head = person[person[W["rel"]] == 1].groupby("hhid", sort=False)[[c for c in ("sex", "age") if c in person.columns]].first()
                agg = agg.join(head.rename(columns={"sex": "head_sex", "age": "head_age"}))
                nh = person[person[W["rel"]] == 1].groupby("hhid").size().reindex(agg.index).fillna(0)
                ck(nh.eq(1).mean() > 0.99, f"{wave}: one head ({W['rel']} == 1) per household: {nh.eq(1).mean():.4%}", hard=False)
            hh = hh.merge(agg, left_on="hhid", right_index=True, how="left")
            hvl.update({"hhsize": "Household size (persons in the roster)", "head_sex": f"Sex of household head ({W['rel']} == 1)", "head_age": f"Age of household head ({W['rel']} == 1)"})
            hvv["head_sex"] = pvv.get("sex", {})
        hh = stamp(hh, W, wave); hh["wt_hh"] = hh["wt"]
        hvv.update({"prov": PROV_LABELS, "dist": DIST_LABELS, "urban": URBAN_LABELS})
        for c, t in KEY_LABELS.items():
            if c in hh.columns: hvl[c] = t
        hh = hh[[c for c in KEY_ORDER if c in hh.columns] + [c for c in hh.columns if c not in KEY_ORDER]]
        ck(hh["hhid"].is_unique, f"{wave}: hhid unique in the household file ({len(hh):,} households)")
        if person is not None: ck(hh["hhsize"].sum() == len(person), f"{wave}: sum of hhsize == person rows")
        log.info("%s household file: %s rows x %s vars; weighted households = %s", wave, f"{len(hh):,}", hh.shape[1], f"{hh['wt'].sum():,.0f}")
        hh = downcast(hh, keep_double=("wt", "wt_hh", "hhid", "pop_wt", "hh_wt", "pond", "weight"))
        write_dta(hh, P["inter"] / f"EICV_{wave}_household_clean.dta", hvl, hvv, f"EICV {wave} household file (household base + household-level modules)", log)
        meta["household"] = {"n": len(hh), "vars": list(hh.columns), "var_labels": hvl, "value_labels": {k: v for k, v in hvv.items() if k in hh.columns}, "source": hsrc,
                             "universe": universe_for(wave, hh.columns)}
    ck.done()
    save_json(meta, LOGS / f"clean_{wave}_meta.json")
log.info("01_clean done for %s", WANT)
