"""
01_clean.py -- SAS: 1_Raw/<year>/**/*.dta -> 2_Intermediate/SAS_<year>_<season>_<module>_clean.dta

Every shipped file is cleaned on its own: lower-case names, key block attached where the
file allows (survey year season wave farm_type prov dist stratum segment holder plot crop wt),
destring, downcast, write. Small tabulation files (yield tables, province area summaries,
weight tables) are written too but flagged `level = table`. The per-year key map below
records which native variable feeds each key; nothing else is recoded. See NISR-Season-Agriculture-Survey-SAS.md (decisions log).
"""
import re, sys
import numpy as np, pandas as pd
from sas_helpers import (paths, get_logger, Checks, read_any, write_dta, lower_names, destring, downcast, save_json, LOGS)

log = get_logger("01_clean"); P = paths()
YEARS = sys.argv[1:] or [str(y) for y in range(2013, 2026)]
KEY_ORDER = ["survey", "year", "season", "wave", "farm_type", "prov", "dist", "stratum", "segment", "holder", "plot", "crop", "wt"]
KEY_LABELS = {"survey": "Source survey", "year": "Agricultural year of the season (as in the NISR release)", "season": "Season (A, B, C)",
              "wave": "Wave id: <year>_<season>", "farm_type": "1 small-scale farmer (area frame), 2 large-scale farmer (list frame)",
              "prov": "Province (1-5, NISR codes)", "dist": "District (11-57, NISR codes)", "stratum": "Sampling stratum (as shipped)",
              "segment": "Segment id (area frame) or LSF id (list frame), as shipped", "holder": "Holder / questionnaire id (as shipped)",
              "plot": "Plot number within segment/holder", "crop": "Crop code (native list of the wave -- the lists differ before / from 2020; see crop_name, crop_list)",
              "wt": "Weight (plot weight where shipped, else segment/stratum weight; missing where none is shipped)"}
PROV_LABELS = {1: "City of Kigali", 2: "Southern Province", 3: "Western Province", 4: "Northern Province", 5: "Eastern Province"}
DIST_LABELS = {11: "Nyarugenge", 12: "Gasabo", 13: "Kicukiro", 21: "Nyanza", 22: "Gisagara", 23: "Nyaruguru", 24: "Huye", 25: "Nyamagabe", 26: "Ruhango",
               27: "Muhanga", 28: "Kamonyi", 31: "Karongi", 32: "Rutsiro", 33: "Rubavu", 34: "Nyabihu", 35: "Ngororero", 36: "Rusizi", 37: "Nyamasheke",
               41: "Rulindo", 42: "Gakenke", 43: "Musanze", 44: "Burera", 45: "Gicumbi", 51: "Rwamagana", 52: "Nyagatare", 53: "Gatsibo", 54: "Kayonza",
               55: "Kirehe", 56: "Ngoma", 57: "Bugesera"}

# native variable -> key, tried in order; the first one present in a file wins
KEYMAP = {
    "prov": ["s1q1", "id1", "province"], "dist": ["s1q2", "district"], "stratum": ["s1q3", "strate", "id3", "stratum"],
    "segment": ["segment_id", "s1q0", "lsf_id", "s1q4", "id4"], "holder": ["idquest", "tractid", "s1q6", "lsf_id"],
    "plot": ["s2q1", "b1", "plot_no", "plot_number", "s2q2_plot"], "crop": ["s2q6", "s2q4", "s2q11", "s3q1", "c03a", "crop_code", "crop_codg", "c03c"],
    "wt": ["plot_weight", "finalplot_weight", "weight_plot", "wh_plot", "coef", "weight", "wt"],
}
CROP_LIST = {"2013": "2013 list (1 Maize ...)", "2014": "2014 list (1 maize ...)", "2015": "2014 list", "2016": "2014 list"}

def season_of(path, year):
    s = str(path).lower()
    for tag, val in (("season_a", "A"), ("season_b", "B"), ("season_c", "C"), ("seasona", "A"), ("seasonb", "B"), ("seasonc", "C"),
                     ("season a", "A"), ("season b", "B"), ("season c", "C"), ("_a_", "A"), ("_b_", "B"), ("_c_", "C")):
        if tag in s: return val
    m = re.search(r"_([abc])(?:_|\.dta)", path.name.lower())
    return m.group(1).upper() if m else "?"

def module_name(path, year, season):
    n = path.stem.lower()
    n = re.sub(rf"^sas_{year}_", "", n); n = re.sub(r"^raw_", "", n)
    n = re.sub(r"^(season_?[abc]_?|[abc]_)", "", n); n = re.sub(rf"{year}", "", n)
    n = re.sub(r"_{2,}", "_", n).strip("_")
    return n or path.stem.lower()

meta_all = {}
for y in YEARS:
    log.info("================ %s ================", y)
    files = sorted((P["raw"] / y).rglob("*.dta")); ck = Checks(log); mods = {}
    for f in files:
        season = season_of(f, y); name = module_name(f, y, season)
        df, vl, vv = read_any(f); df, vl, vv = lower_names(df, vl, vv, log); srcmap = {}
        farm = 2 if re.search(r"(^|_)(lsf|big|large|big_farmer)(_|$)", f.stem.lower()) else (1 if re.search(r"(^|_)(ssf|small)(_|$)", f.stem.lower()) else np.nan)
        # the plot number is identified by its LABEL: screening files list sampled grid points in
        # s2q1 and the plot number in s2q2, production files the plot number in s2q1
        pcol = next((c for c in df.columns if re.search(r"plot[\s_]*(number|no\b)", str(vl.get(c, "")), re.I) and "grid" not in str(vl.get(c, "")).lower()), None)
        if pcol and "plot" not in df.columns:
            df = df.rename(columns={pcol: "plot"}); vl["plot"] = vl.pop(pcol, ""); vv["plot"] = vv.pop(pcol, {}) if pcol in vv else {}; srcmap["plot"] = pcol + " (by label)"
        for key, cands in KEYMAP.items():
            present = [c for c in cands if c in df.columns]
            if key == "crop":      # SAS audit 2026-09-05: from 2020 s2q6 is the perennial plant count and s2q4 the crop code; in the
                                   # screening files the crop name is s2q11 (2019) / s3q1 (2020+). The crop key is the candidate that
                                   # carries the wave's crop dictionary (>= 20 value labels); only files without any labelled candidate fall back to the list order.
                present = [c for c in present if len(vv.get(c, {})) >= 20] or present
            for c in present:
                if key not in df.columns:
                    df = df.rename(columns={c: key}); vl[key] = vl.pop(c, ""); vv[key] = vv.pop(c, {}) if c in vv else vv.get(key, {}); srcmap[key] = c; break
        if "crop" in df.columns and len(vv.get("crop", {})) >= 20:       # the wave's own crop text, so that codes stay interpretable after pooling (lists differ before / from 2020)
            lab = {float(k): str(v) for k, v in vv["crop"].items() if str(k).replace(".", "", 1).lstrip("-").isdigit()}
            df["crop_name"] = pd.to_numeric(df["crop"], errors="coerce").astype(float).map(lab)
            vl["crop_name"] = "Crop name (text of the wave's own crop list for crop)"; srcmap["crop_name"] = f"value labels of {srcmap.get('crop', 'crop')}"
        if "dist" in df.columns:
            x = pd.to_numeric(df["dist"], errors="coerce"); df["dist"] = np.where(x >= 100, (x // 100) * 10 + x % 100, x)
            if not set(pd.Series(df["dist"]).dropna().unique()) <= set(DIST_LABELS):      # 2013 ID2A is a within-province sequence, not a code
                df = df.rename(columns={"dist": "dist_seq"}); vl["dist_seq"] = vl.pop("dist", "") + " (within-province sequence, not an NISR code)"; srcmap["dist_seq"] = srcmap.pop("dist")
        if "dist" in df.columns:                                  # province from the district code (11-57 -> 1-5) where the file ships none or leaves gaps (2021 C: all 3,416 rows)
            pv = pd.to_numeric(df["dist"], errors="coerce") // 10
            if "prov" not in df.columns: df["prov"] = pv; srcmap["prov"] = "dist // 10 (province from the district code)"
            else:
                cur = pd.to_numeric(df["prov"], errors="coerce"); gap = cur.isna() & pv.notna()
                if gap.any(): df["prov"] = cur.where(~gap, pv); srcmap["prov"] = f"{srcmap.get('prov', 'prov')}; {int(gap.sum())} missing values derived from dist // 10"
        if "farm_type" not in df.columns:
            if "s1q7" in df.columns: df["farm_type"] = pd.to_numeric(df["s1q7"], errors="coerce").map({1: 1, 2: 1, 3: 2, 4: 2}); srcmap["farm_type"] = "s1q7 (1,2 -> SSF; 3,4 -> LSF)"
            elif "s2q3_1" in df.columns: df["farm_type"] = pd.to_numeric(df["s2q3_1"], errors="coerce"); srcmap["farm_type"] = "s2q3_1"
            else: df["farm_type"] = farm; srcmap["farm_type"] = "file name (ssf/lsf)" if not np.isnan(farm) else "not identifiable"
        df["survey"] = "SAS"; df["year"] = np.int16(int(y)); df["season"] = season; df["wave"] = f"{y}_{season}"
        level = "table" if len(df) < 200 and not any(k in df.columns for k in ("holder", "segment", "plot")) else "records"
        for c, t in KEY_LABELS.items():
            if c in df.columns: vl[c] = t
        vv["prov"] = PROV_LABELS
        if "dist" in df.columns: vv["dist"] = DIST_LABELS
        df = destring(df, log, skip=("survey", "season", "wave", "crop_name"))
        df = downcast(df, keep_double=("wt", "holder", "segment"))
        df = df[[c for c in KEY_ORDER if c in df.columns] + [c for c in df.columns if c not in KEY_ORDER]]
        if "wt" in df.columns: ck((df["wt"].dropna() > 0).all(), f"{y}/{season}/{name}: weights > 0", hard=False)
        if "prov" in df.columns: ck(set(pd.to_numeric(df["prov"], errors="coerce").dropna().unique()) <= set(PROV_LABELS), f"{y}/{season}/{name}: province codes 1-5", hard=False)
        out = f"SAS_{y}_{season}_{name}_clean.dta"
        write_dta(df, P["inter"] / out, vl, vv, f"SAS {y} season {season} module {name} ({level})", log)
        mods[f"{season}/{name}"] = {"file": f.name, "rows": len(df), "vars": df.shape[1], "level": level, "keys_present": [k for k in KEY_ORDER if k in df.columns],
                                   "source": srcmap, "var_labels": vl, "value_labels": {k: v for k, v in vv.items() if k in df.columns}, "out": out}
    ck.done(); meta_all[y] = mods; save_json(mods, LOGS / f"clean_{y}_meta.json")
    log.info("%s: %d files cleaned", y, len(mods))
log.info("01_clean done for %s", YEARS)
