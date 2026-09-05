"""
02_merge.py -- SAS: 2_Intermediate/SAS_<year>_<season>_*_clean.dta -> 3_Final/

  SAS_pooled_plotcrop.dta        one row per plot x crop x season x year, 2017-2025 (the post-redesign
                                 crop-production module: small- and large-scale farmers), with a
                                 harmonised core (area in ha, production in kg, weight) mapped
                                 explicitly per year in CORE below, plus every native variable
                                 (version rule) -- 2017/2018 plot weights come from the screening file
  SAS_pooled_plotcrop_2013_2014.dta  crop-area records of the pre-redesign waves that carry a crop
                                 code and an area (2013 area files, 2014 screening); native crop lists
  SAS_pooled_<module>.dta        other modules with the same content in >= 2 waves (2019+ design)
See DECISIONS.md.
"""
import json, re
import numpy as np, pandas as pd
from sas_helpers import (paths, get_logger, Checks, read_dta, write_dta, downcast, to_plain_float, resolve_object_columns,
                         label_similarity, save_json, LOGS)

log = get_logger("02_merge"); P = paths(); ck = Checks(log)
KEYS = ["survey", "year", "season", "wave", "farm_type", "prov", "dist", "stratum", "segment", "holder", "plot", "crop", "wt"]
CORE_KEYS = KEYS + ["plot_area_ha", "crop_area_ha", "harvested_area_ha", "production_kg", "yield_kg_ha", "wt_source"]
STR_KEYS = ("survey", "season", "wave", "wt_source")
SIM_THRESHOLD = 0.25; FORCE_ALIGN = set(); FORCE_SPLIT = {}
KEEP_DOUBLE = ("wt", "holder", "segment", "plot_area_ha", "crop_area_ha", "harvested_area_ha", "production_kg", "yield_kg_ha")

# ---- explicit per-year mapping of the core quantities in the crop-production module.
#      (native variable, unit): m2 -> divided by 10,000; ha as is; production in kg as shipped.
CORE = {
    "2017": dict(module="ssf_crop_production|lsf_crop_production", plot_area=("s2q2", "m2"), crop_area=("s2q7", "m2"), harvested=None, production=("s2q22", "kg"), yield_=None),
    "2018": dict(module="ssf_crop_production|lsf_crop_production", plot_area=("s2q2", "m2"), crop_area=("s2q7", "m2"), harvested=("harvested_area", "m2"), production=("s2q21", "kg"), yield_=None),
    "2019": dict(module="crop_production", plot_area=("s2q2", "m2"), crop_area=("s2q7", "ha"), harvested=("harvested_area", "ha"), production=("s2q21", "kg"), yield_=None),
    "2020": dict(module="crop_production", plot_area=("s2q2", "m2"), crop_area=("crop_area", "ha"), harvested=None, production=("s2q21", "kg"), yield_=None),
    "2021": dict(module="crop_production", plot_area=("s2q2", "m2"), crop_area=("crop_area", "ha"), harvested=None, production=("s2q21", "kg"), yield_=None),
    "2022": dict(module="crop_production", plot_area=("s2q2", "m2"), crop_area=None, harvested=("harv_area", "ha"), production=("s2q21", "kg"), yield_=("yield", "kg/ha")),
    "2023": dict(module="crop_production", plot_area=("s2q2", "m2"), crop_area=None, harvested=("harv_area", "ha"), production=("s2q21", "kg"), yield_=("yield", "kg/ha")),
    "2024": dict(module="production", plot_area=("s2q2", "m2"), crop_area=None, harvested=None, production=("s2q21", "kg"), yield_=None),
    "2025": dict(module="production", plot_area=("plot_area_ha", "ha"), crop_area=("crop_area_ha", "ha"), harvested=("harvested_crop_area_ha", "ha"), production=("s2q21", "kg"), yield_=("yield", "kg/ha")),
}
SCREENING_WT = {"2017": ("screening", "wh_plot"), "2018": ("screening", "wh_plot"), "2019": ("screening", "wt")}   # plot weight lives in the screening file
# other 2019+ modules that repeat across waves
MODULES = {"fertilizers_pesticides": r"partiii_fertilizers_pesticides", "agricultural_practice": r"partiv_agricultural_practice",
           "land_tenure": r"partv_land_tenure", "screening_crops": r"screening_crops|^screening$", "screening_agroforestry": r"screening_agroforestry",
           "screening_antierosion": r"screening_antierosion_land_consolidation"}

inter = P["inter"]
def files_for(year, pattern):
    return sorted(f for f in inter.glob(f"SAS_{year}_*_clean.dta") if re.search(rf"^SAS_{year}_[ABC]_({pattern})_clean\.dta$", f.name))

def conv(s, unit):
    x = pd.to_numeric(s, errors="coerce")
    return x / 10_000 if unit == "m2" else x

def version_pool(frames, labels, vlabs, out_name, label, unit):
    """generic pooling with the version rule (as in every NISR dataset); frames keyed by wave."""
    waves = list(frames); allvars = sorted({c for df in frames.values() for c in df.columns})
    decisions, colname, var_labels, value_labels, conflicts = {}, {}, {}, {}, {}
    order = {w: i for i, w in enumerate(waves)}
    for v in allvars:
        ws = [w for w in waves if v in frames[w].columns]; labs = {w: (labels[w].get(v) or "").strip() for w in ws}
        groups = []
        if v in CORE_KEYS or v in FORCE_ALIGN or len(ws) == 1: groups = [list(ws)]
        else:
            for w in ws:
                for rep, g in groups:
                    if not labs[w] or not rep or label_similarity(labs[w], rep) >= SIM_THRESHOLD: g.append(w); break
                else: groups.append((labs[w], [w]))
            groups.sort(key=lambda g: (-len(g[1]), -max(order[x] for x in g[1]))); groups = [g for _, g in groups]
        versions = {}
        for i, g in enumerate(groups):
            name = v if i == 0 else f"{v[:28]}_v{i + 1}"; versions[name] = g
            for w in g: colname[(v, w)] = name
        decisions[v] = {"waves": ws, "versions": versions, "labels_by_wave": labs, "reference_label": labs[groups[0][-1]]}
    out = []
    for w in waves:
        df = frames[w].copy(); ren = {v: colname[(v, w)] for v in df.columns if colname[(v, w)] != v}; df = df.rename(columns=ren)
        for c in df.columns:
            v = next((k for k, n in ren.items() if n == c), c); var_labels[c] = labels[w].get(v) or var_labels.get(c) or ""
            if v in vlabs[w]:
                merged = value_labels.get(c, {})
                for code, txt in vlabs[w][v].items():
                    if code in merged and str(merged[code]).strip().lower() != str(txt).strip().lower(): conflicts.setdefault(c, {}).setdefault(str(code), set()).update([merged[code], txt])
                    merged[code] = txt
                value_labels[c] = merged
        out.append(to_plain_float(df))
    pooled = pd.concat(out, ignore_index=True, sort=False)
    pooled = resolve_object_columns(pooled, log, keep_str=STR_KEYS)
    keys = [k for k in CORE_KEYS if k in pooled.columns]; pooled = pooled[keys + [c for c in pooled.columns if c not in keys]]
    pooled = downcast(pooled, keep_double=KEEP_DOUBLE)
    ck(len(pooled) == sum(len(d) for d in frames.values()), f"{out_name}: pooled rows == sum of wave rows")
    write_dta(pooled, P["final"] / out_name, var_labels, value_labels, label, log)
    return {"rows": len(pooled), "vars": list(pooled.columns), "unit": unit, "waves": waves, "decisions": decisions,
            "value_label_conflicts": {k: {c: sorted(s) for c, s in d.items()} for k, d in conflicts.items()}}

summary = {"threshold": SIM_THRESHOLD, "force_align": [], "files": {}, "core_map": {y: {k: v for k, v in d.items()} for y, d in CORE.items()}}
KEYLAB = {"plot_area_ha": "Plot area (ha) -- CORE map, see codebook", "crop_area_ha": "Crop area on the plot (ha) -- CORE map",
          "harvested_area_ha": "Harvested crop area (ha) -- CORE map", "production_kg": "Total quantity harvested (kg) -- CORE map",
          "yield_kg_ha": "Yield (kg/ha) as shipped by NISR -- CORE map", "wt_source": "Where the plot weight came from (own file / screening file / none)"}

# ---------------------------------------------------------------- plot x crop, 2017-2025
frames, labels, vlabs = {}, {}, {}
for y, m in CORE.items():
    for f in files_for(y, m["module"]):
        df, vl, vv = read_dta(f); season = df["season"].iloc[0]; wave = f"{y}_{season}" + ("_lsf" if "lsf_" in f.name else ("_ssf" if "ssf_" in f.name else ""))
        for key, spec in (("plot_area_ha", m["plot_area"]), ("crop_area_ha", m["crop_area"]), ("harvested_area_ha", m["harvested"]), ("production_kg", m["production"]), ("yield_kg_ha", m["yield_"])):
            if spec and spec[0] in df.columns: df[key] = conv(df[spec[0]], spec[1]); vl[key] = KEYLAB[key] + f" [from {spec[0]}, {spec[1]}]"
            else: df[key] = np.nan; vl[key] = KEYLAB[key] + " [not shipped this year]"
        # plot weight
        if "wt" in df.columns and df["wt"].notna().any(): df["wt_source"] = "own file"
        else:
            src = None
            if y in SCREENING_WT:
                scr = files_for(y, SCREENING_WT[y][0].replace("screening", r"ssf_screening|lsf_screening|screening"))
                scr = [s for s in scr if s.name.split("_")[2] == season and (("lsf" in s.name) == ("lsf" in f.name))]
                if scr:
                    sd, svl, _ = read_dta(scr[0])
                    wcol = next((c for c in ("wt", "wh_plot") if c in sd.columns), None)
                    # the screening lists grid points AND plots: take the column whose label says "plot number"
                    pcol = next((c for c in sd.columns if re.search(r"plot[\s_]*(number|no\b)", str(svl.get(c, "")), re.I) and "grid" not in str(svl.get(c, "")).lower()), None)
                    log.info("  %s: screening plot column = %s (%s)", wave, pcol, svl.get(pcol, ""))
                    if wcol and pcol and "segment" in sd.columns and "segment" in df.columns and "plot" in df.columns:
                        w = sd[["segment", pcol, wcol]].dropna().drop_duplicates(["segment", pcol]).rename(columns={pcol: "plot", wcol: "wt"})
                        df = df.drop(columns=[c for c in ("wt",) if c in df.columns]).merge(w, on=["segment", "plot"], how="left")
                        src = f"screening file {scr[0].name} on (segment, plot): {df['wt'].notna().mean():.1%} matched"
                        if df["wt"].isna().any() and "wh_sgt" in sd.columns:
                            sw = sd[["segment", "wh_sgt"]].dropna().drop_duplicates("segment")
                            df = df.merge(sw, on="segment", how="left"); df["wt"] = df["wt"].fillna(df["wh_sgt"]); df = df.drop(columns=["wh_sgt"])
                            src += f"; segment weight used for the rest ({df['wt'].notna().mean():.1%} weighted)"
            if "wt" not in df.columns: df["wt"] = np.nan
            df["wt_source"] = src or "none shipped"
            log.info("  %s: weight -> %s", wave, df["wt_source"].iloc[0])
        vl["wt_source"] = KEYLAB["wt_source"]
        frames[wave], labels[wave], vlabs[wave] = df, vl, vv
        log.info("  loaded %-14s %-55s %8s rows", wave, f.name, f"{len(df):,}")
summary["files"]["SAS_pooled_plotcrop.dta"] = version_pool(frames, labels, vlabs, "SAS_pooled_plotcrop.dta", "SAS 2017-2025 pooled plot x crop x season records (crop-production module)", "plotcrop")
pc = summary["files"]["SAS_pooled_plotcrop.dta"]

# ---------------------------------------------------------------- crop-area records 2013-2014
frames, labels, vlabs = {}, {}, {}
for f in sorted(inter.glob("SAS_2013_*_area_*_clean.dta")) + sorted(inter.glob("SAS_2014_*_farmq_screening_clean.dta")):
    df, vl, vv = read_dta(f)
    if "crop" not in df.columns or not any(c in df.columns for c in ("area_ha", "ha")): continue
    if len(df) < 500: continue                                   # province summaries
    df["crop_area_ha"] = pd.to_numeric(df["area_ha"] if "area_ha" in df.columns else df["ha"], errors="coerce"); vl["crop_area_ha"] = KEYLAB["crop_area_ha"] + " [from area_ha / ha]"
    frames[f.name] = df; labels[f.name] = vl; vlabs[f.name] = vv
if frames:
    summary["files"]["SAS_pooled_plotcrop_2013_2014.dta"] = version_pool(frames, labels, vlabs, "SAS_pooled_plotcrop_2013_2014.dta", "SAS 2013-2014 crop-area records (pre-redesign design; native crop lists)", "plotcrop_area")

# ---------------------------------------------------------------- other 2019+ modules
for canon, pat in MODULES.items():
    frames, labels, vlabs = {}, {}, {}
    for y in ("2019", "2020", "2021", "2022", "2023", "2024", "2025"):
        for f in files_for(y, pat):
            df, vl, vv = read_dta(f); wave = f"{y}_{df['season'].iloc[0]}"; frames[wave], labels[wave], vlabs[wave] = df, vl, vv
    if len({w[:4] for w in frames}) >= 2:
        summary["files"][f"SAS_pooled_{canon}.dta"] = version_pool(frames, labels, vlabs, f"SAS_pooled_{canon}.dta", f"SAS 2019-2025 pooled module '{canon}'", canon)
save_json(summary, LOGS / "merge_alignment.json"); ck.done(); log.info("02_merge done")
