"""
01_clean.py -- AHS: 1_Raw/<year>/*  ->  2_Intermediate/AHS_<year>_{person,household,<module>}_clean.dta

For each wave (2017, 2020, 2024):
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
from ahs_helpers import (paths, get_logger, Checks, read_any, write_dta, lower_names, destring, downcast,
                          save_json, LOGS)

log = get_logger("01_clean")
P = paths()

# ------------------------------------------------------------------ wave configuration
# raw: folder under 1_Raw; base_hh: household base module stem(s); base_p: roster module stem;
# geo: raw name -> key name for the household key table; wt: household weight variable;
# extra: (source wave folder, file stem) of files NISR shipped in another wave's folder.
WAVES = {
    "2017": dict(year=2017, sample="CS", raw="2017", prefixes=["AHS_2017_"], base_hh=["s0_general_information"],
                 base_p="s1_household_members_characteristics", hhid_var="idquest", pid_var="s1q1",
                 geo={"s0q1": "prov", "s0q2": "dist", "segment_id": "cluster"}, wt="weight", rel="s1q3", sex="s1q4", age="s1q5"),
    "2020": dict(year=2020, sample="CS", raw="2020", prefixes=["AHS_2020_"], base_hh=["section_0", "section_1_wt"],
                 base_p="section_1", hhid_var="hhuid", pid_var="s1q2",
                 geo={"s0q1": "prov", "s0q2": "dist"}, wt="weight", rel="s1q4", sex="s1q5", age="s1q6",
                 # section_0 ships no weight; the household weight is taken from section_1 (constant within household)
                 wt_from="section_1"),
    "2024": dict(year=2024, sample="CS", raw="2024", prefixes=["AHS_2024_"], base_hh=["section0", "section8_sustainable_agriculture"],
                 base_p="section1_household_members_characteristics", hhid_var="hhid", pid_var="pid",
                 geo={"province": "prov", "district": "dist", "clust": "cluster"}, wt="weight", rel="s1q2", sex="s1q1", age="s1q3y"),
}
WANT = sys.argv[1:] or list(WAVES)
KEY_ORDER = ["survey", "year", "wave", "sample", "prov", "dist", "urban", "cluster", "hhid", "pid", "sex", "age", "wt", "wt_hh"]
KEY_LABELS = {"survey": "Source survey", "year": "Survey year", "wave": "Wave (survey year)", "sample": "CS = national sample of agricultural households",
              "prov": "Province (1-5, NISR codes)", "dist": "District (11-57, NISR current codes)", "urban": "Area of residence (1 urban, 2 rural)",
              "cluster": "Sampling segment / cluster (as shipped)", "hhid": "Household id (unique within wave)",
              "pid": "Person number within the household", "sex": "Sex (1 male, 2 female)", "age": "Age in years",
              "wt": "Household weight carried by every row (sums to persons in person files, to households in household files)",
              "wt_hh": "Household weight (same value as wt; sums to the number of households)", "pid_nisr": "NISR person id as shipped"}
PROV_LABELS = {1: "City of Kigali", 2: "Southern Province", 3: "Western Province", 4: "Northern Province", 5: "Eastern Province"}
DIST_LABELS = {11: "Nyarugenge", 12: "Gasabo", 13: "Kicukiro", 21: "Nyanza", 22: "Gisagara", 23: "Nyaruguru", 24: "Huye", 25: "Nyamagabe", 26: "Ruhango",
               27: "Muhanga", 28: "Kamonyi", 31: "Karongi", 32: "Rutsiro", 33: "Rubavu", 34: "Nyabihu", 35: "Ngororero", 36: "Rusizi", 37: "Nyamasheke",
               41: "Rulindo", 42: "Gakenke", 43: "Musanze", 44: "Burera", 45: "Gicumbi", 51: "Rwamagana", 52: "Nyagatare", 53: "Gatsibo", 54: "Kayonza",
               55: "Kirehe", 56: "Ngoma", 57: "Bugesera"}
URBAN_LABELS = {1: "Urban", 2: "Rural"}
HH_ID_NAMES = ("hhid",)
PID_NAMES = ("pid",)

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
    for src, dst in ((W.get("hhid_var"), "hhid"), (W.get("pid_var"), "pid")):
        if src and src in df.columns and dst not in df.columns and src != dst:
            df = df.rename(columns={src: dst}); vl[dst] = vl.pop(src, ""); vv.pop(src, None); srcmap.setdefault(dst, src)
    for c in HH_ID_NAMES:
        if c in df.columns and "hhid" not in df.columns and c != "hhid":
            df = df.rename(columns={c: "hhid"}); vl["hhid"] = vl.pop(c, ""); srcmap.setdefault("hhid", c)
    for c in PID_NAMES:
        if c in df.columns and "pid" not in df.columns and c != "pid":
            df = df.rename(columns={c: "pid"}); vl["pid"] = vl.pop(c, ""); srcmap.setdefault("pid", c)
    if "hhid" in df.columns: df["hhid"] = pd.to_numeric(df["hhid"], errors="coerce").astype("Int64")
    if "pid" in df.columns:
        p = pd.to_numeric(df["pid"], errors="coerce")
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
    df["survey"] = "AHS"; df["year"] = np.int16(W["year"]); df["wave"] = wave; df["sample"] = W["sample"]
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

    if W.get("wt_from") and W["wt_from"] in modules:
        src = modules[W["wt_from"]]
        cols = ["hhid"] + [c for c in ("wt", "prov", "dist", "cluster") if c in src.columns and c not in modules[W["base_hh"][0]].columns]
        modules[W["wt_from"] + "_wt"] = src[cols].drop_duplicates("hhid").reset_index(drop=True)
        labels[W["wt_from"] + "_wt"] = {c: labels[W["wt_from"]].get(c, "") for c in cols}; vlabels[W["wt_from"] + "_wt"] = {}
        srcmaps[W["wt_from"] + "_wt"] = {"wt": f"module {W['wt_from']} (household weight, constant within household)"}
        log.info("household weight taken from module %s (%d households)", W["wt_from"], len(modules[W["wt_from"] + "_wt"]))

    # ---------------- household key table
    hh_base = None
    for stem in W["base_hh"]:
        m = modules.get(stem)
        if m is None: continue
        if not m["hhid"].is_unique:      # 2017 s0 lists dwellings with no household / repeated households: keep the first row per hhid
            ndup = int(m.duplicated("hhid").sum()); m = m.drop_duplicates("hhid", keep="first")
            ck(False, f"{wave}: household base {stem} had {ndup} duplicate hhid rows; first row kept", hard=False)
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
        if name.endswith("_wt"): level[name] = "household"; continue
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
        meta_modules[name] = {"level": lvl, "rows": len(df), "vars": df.shape[1], "hh_match_rate": None if np.isnan(rate) else round(float(rate), 4)}
        write_dta(df, P["inter"] / f"AHS_{wave}_{name}_clean.dta", vl, vv, f"AHS {wave} module {name} ({lvl}-level)", log)
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
        write_dta(person, P["inter"] / f"AHS_{wave}_person_clean.dta", pvl, pvv, f"AHS {wave} person file (roster + person-level modules)", log)
        meta["person"] = {"n": len(person), "vars": list(person.columns), "var_labels": pvl, "value_labels": {k: v for k, v in pvv.items() if k in person.columns}, "source": psrc}
    else:
        person = None

    # ---------------- HOUSEHOLD file
    if hh_base is not None:
        hh = hh_base[hh_base["hhid"].notna()].copy()
        if person is not None:      # listing rows for dwellings without an interviewed household are not households
            n0 = len(hh); hh = hh[hh["hhid"].isin(person["hhid"])]
            if len(hh) < n0: ck(False, f"{wave}: {n0 - len(hh)} household-base rows without any roster member dropped (dwellings listed but not interviewed)", hard=False)
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
        write_dta(hh, P["inter"] / f"AHS_{wave}_household_clean.dta", hvl, hvv, f"AHS {wave} household file (household base + household-level modules)", log)
        meta["household"] = {"n": len(hh), "vars": list(hh.columns), "var_labels": hvl, "value_labels": {k: v for k, v in hvv.items() if k in hh.columns}, "source": hsrc}
    ck.done()
    save_json(meta, LOGS / f"clean_{wave}_meta.json")
log.info("01_clean done for %s", WANT)
