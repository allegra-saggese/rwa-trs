"""
02_merge.py -- SAS: 2_Intermediate/SAS_<year>_<season>_*_clean.dta -> 3_Final/

  SAS_pooled_plotcrop.dta        one row per crop-production record (plot x crop x season x year),
                                 2017-2025 (the post-redesign crop-production module: small- and
                                 large-scale farmers), with a harmonised core (area in ha, production
                                 in kg, weight) mapped explicitly per year AND season in CORE /
                                 CORE_SEASON below, plus every native variable (version rule) --
                                 2017/2018 plot weights come from the screening file. The crop code is
                                 the wave's own list (crop_list, crop_name): two lists, 2017-2019 and 2020+.
                                 The official CULTIVATED-AREA universe is the screening crop record, not
                                 this file: see 2_Intermediate/appended/SAS_pooled_screening_crops.dta.
  SAS_pooled_plotcrop_2013_2016.dta  plot x crop records of the pre-redesign waves (screening / area /
                                 sowing-production / plot-roster files, record_type + source_module tag
                                 the shipped record); native crop lists; keys are NOT unique across record types
  2_Intermediate/appended/SAS_pooled_<module>*.dta   every module-level append (2013-16, 2017-18, 2019+)
  Rule: 3_Final holds only the appended unit-level datasets; module-level files live in 2_Intermediate.
  Version rule (as in every NISR dataset): a same-named variable is one column across waves only when its
  variable labels are similar (token Jaccard >= SIM_THRESHOLD) AND its value labels are compatible
  (no code whose text means something else; an unlabelled wave's values inside the labelled range);
  otherwise <name>_v2 ...; FORCE_SPLIT closes groups by year.
See NISR-Season-Agriculture-Survey-SAS.md (decisions log).
"""
import difflib, json, re
import numpy as np, pandas as pd
from sas_helpers import (paths, get_logger, Checks, read_dta, write_dta, downcast, to_plain_float, resolve_object_columns,
                         label_similarity, save_json, LOGS)

log = get_logger("02_merge"); P = paths(); ck = Checks(log)
KEYS = ["survey", "year", "season", "wave", "farm_type", "prov", "dist", "stratum", "segment", "holder", "plot", "crop", "wt"]
CORE_KEYS = KEYS + ["plot_area_ha", "crop_area_ha", "harvested_area_ha", "production_kg", "yield_kg_ha", "wt_source"]
STR_KEYS = ("survey", "season", "wave", "wt_source")
SIM_THRESHOLD = 0.25; VL_THRESHOLD = 0.6; FORCE_ALIGN = set()
# FORCE_SPLIT: closed groups of YEARS (a wave belongs to a group when its year is listed) -- same name, different
# question, not caught by the labels (SAS audit 2026-09-05, verified on the raw labels):
#   s3q2   2019 organic-fertiliser quantity (kg) vs 2020+ number of sources (both unlabelled quantities)
#   s2q17  2017 quantity purchased vs 2018-2019 seed source vs 2020+ quantity purchased and sown
#   s4q14a 2018 C ssf: stage codes 14 / 15 are combined stages ("Ploughing and soil levelling") instead of "Threshing and other" (the
#          cleaned file carries no label set for this wave because the shipped labels are not writable, so the rule cannot see it)
FORCE_SPLIT = {"s3q2": [["2019"]], "s2q17": [["2017"], ["2018", "2019"]], "s4q14a": [["2018_C_ssf"]]}
KEEP_DOUBLE = ("wt", "holder", "segment", "plot_area_ha", "crop_area_ha", "harvested_area_ha", "production_kg", "yield_kg_ha")
STR_KEYS = STR_KEYS + ("crop_name", "crop_list", "record_type", "source_module")

SENTINELS = {98, 99, 998, 999, 9998, 9999}       # NISR's don't-know / missing codes: never evidence of a coding change
MISSING_LIKE = {"not stated", "missing", "dont know", "dk", "unknown", "not known", "non determine", "nd", "ns", "not applicable", "na"}
_SYN = {"others": "other", "yego": "yes", "oya": "no", "specify": "", "please": "", "specified": ""}
def _norm(s):
    toks = [_SYN.get(w, w) for w in re.sub(r"[^a-z0-9]+", " ", str(s).lower()).split()]
    return " ".join(w for w in toks if w)
def _same(x, y):
    """same category? normalised texts equal, both missing-like, one's tokens contained in the other's, or close spelling"""
    a, b = _norm(x), _norm(y)
    if a == b or (a in MISSING_LIKE and b in MISSING_LIKE): return True
    ta, tb = set(a.split()), set(b.split())
    if ta and tb and (ta <= tb or tb <= ta): return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= VL_THRESHOLD
def vl_conflicts(a, b):
    return {c: (a[c], b[c]) for c in set(a) & set(b) if c not in SENTINELS and not _same(a[c], b[c])}
def _numlab(d):
    return {float(k): str(v) for k, v in (d or {}).items() if str(k).replace(".", "", 1).lstrip("-").isdigit()}
def _range(s):
    s = pd.to_numeric(s, errors="coerce") if s.dtype == object else s
    if not pd.api.types.is_numeric_dtype(s): return None
    s = s[s.notna() & ~s.isin(SENTINELS)]
    return (float(s.min()), float(s.max())) if len(s) else None
def _obs(s):
    s = pd.to_numeric(s, errors="coerce") if s.dtype == object else s
    return set(s.dropna().unique().tolist()) if pd.api.types.is_numeric_dtype(s) else set()
def incompatible(y, z, vls, rng):
    a, b = vls.get(y) or {}, vls.get(z) or {}
    if a and b:
        c = vl_conflicts(a, b)
        if c: return f"{y} vs {z}: value labels differ -- " + "; ".join(f"{k:g}: {p!r} vs {q!r}" for k, (p, q) in sorted(c.items())[:3])
    elif a or b:
        lab, u = (a, z) if a else (b, y)
        codes = [c for c in lab if c not in SENTINELS]
        r = rng.get(u)
        if len(codes) >= 2 and r and r[1] > max(codes):
            return f"{y} vs {z}: {u} is unlabelled and its values reach {r[1]:g}, beyond the labelled codes ({min(codes):g}-{max(codes):g})"
    return None
def version_groups(v, waves, labs, vls, rng, order):
    """Greedy grouping of waves: a wave joins the first group whose variable label is similar (skipped for FORCE_ALIGN)
    AND whose value labels are compatible with every member; FORCE_SPLIT groups (by year) are closed. Returns (groups, reasons)."""
    if v in CORE_KEYS or len(waves) == 1: return [list(waves)], []
    forced = {}
    for i, g in enumerate(FORCE_SPLIT.get(v, [])):
        for w in waves:
            if w[:4] in g or w in g: forced[w] = i          # entries are years or full wave ids
    groups, reasons = [], []
    for w in waves:
        if w in forced:
            key = ("__forced__", forced[w])
            for rep, ws in groups:
                if rep == key: ws.append(w); break
            else: groups.append((key, [w])); reasons.append(f"{w}: FORCE_SPLIT")
            continue
        for rep, ws in groups:
            if isinstance(rep, tuple): continue
            if v not in FORCE_ALIGN and labs[w] and rep and label_similarity(labs[w], rep) < SIM_THRESHOLD:
                reasons.append(f"{w} vs {ws[0]}: variable label differs ({labs[w][:40]!r} vs {rep[:40]!r})"); continue
            why = next((x for z in ws for x in [incompatible(w, z, vls, rng)] if x), None)
            if why: reasons.append(why); continue
            ws.append(w); break
        else: groups.append((labs[w], [w]))
    groups.sort(key=lambda g: (-len(g[1]), -max(order[x] for x in g[1])))
    return [ws for _, ws in groups], (reasons if len(groups) > 1 else [])

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
# season-specific exceptions to the annual map (SAS audit 2026-09-05; verified on the raw labels and distributions):
CORE_SEASON = {
    ("2019", "B"): dict(plot_area=("s2q2", "ha")),                              # label "2.2 Plot size (ha)", median 0.126 (A is m2, median 1,252)
    ("2019", "C"): dict(plot_area=("s2q2", "ha"), crop_area=("s2q7", "pct")),   # "2.2 Plot area in ha"; s2q7 = plot area x crop share in % = 100 x harvested_area
    ("2021", "A"): dict(crop_area=None), ("2021", "B"): dict(crop_area=None),    # the shipped crop_area equals the plot area on every row: not a crop area
    ("2022", "C"): dict(harvested=("harvested_area", "ha")), ("2023", "C"): dict(harvested=("harvested_area", "ha")),   # season C names the field harvested_area (A/B: harv_area)
}
CROP_LIST = lambda y: "2013 list" if y == "2013" else "2014 list" if y in ("2014", "2015", "2016") else "2017-2019 list" if y in ("2017", "2018", "2019") else "2020+ list"
SCREENING_WT = {"2017": ("screening", "wh_plot"), "2018": ("screening", "wh_plot"), "2019": ("screening", "wt")}   # plot weight lives in the screening file
# other 2019+ modules that repeat across waves
MODULES = {  # canonical name: file-stem pattern (2019-2023 partiii_/partiv_ names, 2024-2025 short names, 2019 and 2024-2025 one screening file), (years)
    "fertilizers_pesticides": (r"partiii_fertilizers_pesticides|fertilizer_pesticide[abc]", range(2019, 2026)), "agricultural_practice": (r"partiv_agricultural_practice|agricultural_practice", range(2019, 2026)),
    "land_tenure": (r"partv_land_tenure", range(2019, 2026)), "screening_crops": (r"screening_crops|screening", range(2019, 2026)),
    "screening_agroforestry": (r"screening_agroforestry", range(2019, 2026)), "screening_antierosion": (r"screening_antierosion_land_consolidation", range(2019, 2026)),
    "fertilizers_2017_2018": (r"(ssf|lsf)_fertilizers", range(2017, 2019)), "pesticides_2017_2018": (r"(ssf|lsf)_pesticides", range(2017, 2019)),
    "antierosion_2017_2018": (r"(ssf|lsf)_antierosion", range(2017, 2019)), "irrigation_land_tenure_2017_2018": (r"(ssf|lsf)_irrigation_soil_preparation_and_land_tenure", range(2017, 2019)),
    "screening_2017_2018": (r"(ssf|lsf)_screening", range(2017, 2019)),
}
# 2013-2016 plot x crop records appended into one file with the record type and source module tagged (SAS audit: every
# shipped file that carries a crop record at plot level -- screening, crop-area, sowing / production / harvest and plot-roster files)
PLOTCROP_EARLY = {  # record_type: file-stem patterns
    "screening": [r"farmq_screening$", r"(ssf|lsf)_screening(_season_b|_segment)?$", r"screening_c$", r"screeningc$", r"screening_[abc]_final(_big)?$"],
    "crop area": [r"area_[abc]$", r"^area$", r"lsf_area$", r"area_province_crop_c$", r"pure_mixed_crop_land$", r"pure_and_mixed_c$"],
    "sowing / production / harvest": [r"date_sowing_production_harvest", r"sowing_production_harvest(_c)?$"],
    "plot roster": [r"big_farmer_[abc]$", r"farmq_part1$", r"part_i_farm(_big)?$", r"plot_ident_lsf$", r"phase_2_part_1$"],
}
EARLY_AREA = ("area_crop", "ha_d", "area_ha", "ha", "area", "crop_area_ha")   # crop-area field per shipped file, first present (labels: crop area / developed area / area by crop in ha)
def early_type(stem):
    return next((rt for rt, pats in PLOTCROP_EARLY.items() if any(re.search(p, stem) for p in pats)), None)
def modkey(f):
    """(year, 'S/stem') of a cleaned file -> the entry of logs/clean_<year>_meta.json (codebook lineage)."""
    m = re.match(r"^SAS_(\d{4})_([ABC?])_(.*)_clean\.dta$", f.name); return (m.group(1), f"{m.group(2)}/{m.group(3)}")

inter = P["inter"]
def files_for(year, pattern):
    return sorted(f for f in inter.glob(f"SAS_{year}_*_clean.dta") if re.search(rf"^SAS_{year}_[ABC]_({pattern})_clean\.dta$", f.name))

def conv(s, unit):
    x = pd.to_numeric(s, errors="coerce")
    return x / 10_000 if unit == "m2" else x / 100 if unit == "pct" else x

APPENDED = P["inter"] / "appended"; APPENDED.mkdir(exist_ok=True)
def labels_of(vl, c): return (vl.get(c) or "").strip()[:40]

def version_pool(frames, labels, vlabs, out_name, label, unit, out_dir=None, sources=None, crop_native=False):
    """generic pooling with the version rule (as in every NISR dataset); frames keyed by wave.
    Writes to out_dir (default 3_Final; modules go to 2_Intermediate/appended). sources: {wave: (year, 'S/stem')}
    for the codebook lineage; crop_native: the crop code keeps NO pooled value labels (lists differ by wave: crop_list, crop_name)."""
    out_dir = out_dir or P["final"]
    waves = list(frames); allvars = sorted({c for df in frames.values() for c in df.columns})
    decisions, colname, var_labels, value_labels, conflicts, stale_labels = {}, {}, {}, {}, {}, {}
    order = {w: i for i, w in enumerate(waves)}
    for v in allvars:
        ws = [w for w in waves if v in frames[w].columns]; labs = {w: (labels[w].get(v) or "").strip() for w in ws}
        vls = {w: _numlab(vlabs[w].get(v)) for w in ws}; rng = {w: _range(frames[w][v]) for w in ws}
        groups, reasons = version_groups(v, ws, labs, vls, rng, order)
        stale = {w: sorted(_obs(frames[w][v]) - set(vls[w]) - SENTINELS)[:20] for w in ws if len(set(vls[w]) - SENTINELS) >= 3}
        stale = {w: s for w, s in stale.items() if s}
        if stale: stale_labels[v] = stale
        versions = {}
        for i, g in enumerate(groups):
            name = v if i == 0 else f"{v[:28]}_v{i + 1}"; versions[name] = g
            for w in g: colname[(v, w)] = name
        decisions[v] = {"waves": ws, "versions": versions, "labels_by_wave": labs, "reference_label": labs[groups[0][-1]], "split_reasons": reasons}
        if len(groups) > 1: log.info("  VERSIONS %s: %s | %s", v, {k: len(g) for k, g in versions.items()}, " / ".join(reasons[:2]))
    if stale_labels: log.info("  %d variables with codes observed outside their own value labels (stale labels)", len(stale_labels))
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
    if crop_native and "crop" in value_labels:
        value_labels.pop("crop"); var_labels["crop"] = "Crop code -- the wave's OWN list (crop_list; text in crop_name): codes are comparable only within a list, so no pooled value labels"
    if "stratum" in value_labels and len({json.dumps(_numlab(vlabs[w].get("stratum")), sort_keys=True) for w in waves if "stratum" in vlabs[w]}) > 1:
        value_labels.pop("stratum"); var_labels["stratum"] = "Sampling stratum as shipped -- codes and meanings are wave-specific (2017-2019: 10 hillside / 20 marshland / 30 rangeland / 40 household-village / 50 LSF; 2020+: 40 mixed, 50 site): labels in the per-wave cleaned files"
    pooled = pd.concat(out, ignore_index=True, sort=False)
    pooled = resolve_object_columns(pooled, log, keep_str=STR_KEYS)
    keys = [k for k in CORE_KEYS if k in pooled.columns]; pooled = pooled[keys + [c for c in pooled.columns if c not in keys]]
    pooled = downcast(pooled, keep_double=KEEP_DOUBLE)
    ck(len(pooled) == sum(len(d) for d in frames.values()), f"{out_name}: pooled rows == sum of wave rows")
    write_dta(pooled, out_dir / out_name, var_labels, value_labels, label, log)
    return {"rows": len(pooled), "vars": list(pooled.columns), "unit": unit, "waves": waves, "dir": str(out_dir.relative_to(P["root"])), "decisions": decisions,
            "value_label_conflicts": {k: {c: sorted(s) for c, s in d.items()} for k, d in conflicts.items()}, "stale_labels": stale_labels,
            "wave_modules": {w: list(s) for w, s in (sources or {}).items()}}

summary = {"threshold": SIM_THRESHOLD, "vl_threshold": VL_THRESHOLD, "force_align": [], "force_split": FORCE_SPLIT, "files": {},
           "core_map": {y: {k: v for k, v in d.items()} for y, d in CORE.items()}, "core_map_season": {f"{y}_{s}": d for (y, s), d in CORE_SEASON.items()}}
KEYLAB = {"plot_area_ha": "Plot area (ha) -- CORE map, see codebook", "crop_area_ha": "Crop area on the plot (ha) -- CORE map",
          "harvested_area_ha": "Harvested crop area (ha) -- CORE map", "production_kg": "Total quantity harvested (kg) -- CORE map",
          "yield_kg_ha": "Yield (kg/ha) as shipped by NISR -- CORE map", "wt_source": "Where the plot weight came from (own file / screening file / none)"}

# ---------------------------------------------------------------- plot x crop, 2017-2025
frames, labels, vlabs, sources = {}, {}, {}, {}
for y, m0 in CORE.items():
    for f in files_for(y, m0["module"]):
        df, vl, vv = read_dta(f); season = df["season"].iloc[0]; wave = f"{y}_{season}" + ("_lsf" if "lsf_" in f.name else ("_ssf" if "ssf_" in f.name else ""))
        m = dict(m0, **CORE_SEASON.get((y, season), {})); sources[wave] = modkey(f)
        for key, spec in (("plot_area_ha", m["plot_area"]), ("crop_area_ha", m["crop_area"]), ("harvested_area_ha", m["harvested"]), ("production_kg", m["production"]), ("yield_kg_ha", m["yield_"])):
            if spec and spec[0] in df.columns: df[key] = conv(df[spec[0]], spec[1]); vl[key] = KEYLAB[key] + f" [from {spec[0]}, {spec[1]}]"
            else: df[key] = np.nan; vl[key] = KEYLAB[key] + (" [not shipped this year / season]" if spec is None or y not in ("2021",) else " [not shipped this year]")
        if m["crop_area"] is None and m0["crop_area"] is not None: vl["crop_area_ha"] = KEYLAB["crop_area_ha"] + " [the shipped crop_area equals the plot area in this season: not used]"
        df["crop_list"] = CROP_LIST(y); vl["crop_list"] = "Crop code list generation of crop (2017-2019 vs 2020+; within 2020+ a few codes moved: fruits 414-418 in 2020 B/C, 140/206 from 2022 -- use crop_name for the text)"
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
summary["files"]["SAS_pooled_plotcrop.dta"] = version_pool(frames, labels, vlabs, "SAS_pooled_plotcrop.dta", "SAS 2017-2025 pooled crop-production records (plot x crop x season; crop = wave's own list, see crop_list / crop_name)", "plotcrop", sources=sources, crop_native=True)
pc = summary["files"]["SAS_pooled_plotcrop.dta"]

# ---------------------------------------------------------------- plot x crop records 2013-2016
# The pre-redesign waves ship plot x crop records in several shapes (crop-area files, planting /
# sowing files, holder-level big-farmer area files, screening files). They are appended into one
# file with `source_module` saying which record type each row is; crop lists are the waves' own.
frames, labels, vlabs, sources = {}, {}, {}, {}
for y in ("2013", "2014", "2015", "2016"):
    for f in sorted(inter.glob(f"SAS_{y}_*_clean.dta")):
        stem = re.sub(rf"^SAS_{y}_[ABC?]_(.*)_clean\.dta$", r"\1", f.name); rtype = early_type(stem)
        if rtype is None: continue
        df, vl, vv = read_dta(f)
        if "crop" not in df.columns or len(df) < 200: continue                 # tabulations / files without a crop record
        df["source_module"] = stem; vl["source_module"] = "Shipped file this row comes from (stem)"
        df["record_type"] = rtype; vl["record_type"] = "Record type of the shipped file: screening / crop area / sowing-production-harvest / plot roster (keys are unique only within a record type, if at all)"
        area = next((c for c in EARLY_AREA if c in df.columns and pd.to_numeric(df[c], errors="coerce").notna().any()), None)
        df["crop_area_ha"] = pd.to_numeric(df[area], errors="coerce") if area else np.nan
        vl["crop_area_ha"] = KEYLAB["crop_area_ha"] + (f" [from {area}: {labels_of(vl, area)}]" if area else " [not in this record type]")
        df["crop_list"] = CROP_LIST(y); vl["crop_list"] = "Crop code list generation of crop (codes comparable only within a list; use crop_name for the text)"
        w = f"{y}_{df['season'].iloc[0]}_{stem}"; frames[w], labels[w], vlabs[w] = df, vl, vv; sources[w] = modkey(f)
if frames:
    summary["files"]["SAS_pooled_plotcrop_2013_2016.dta"] = version_pool(frames, labels, vlabs, "SAS_pooled_plotcrop_2013_2016.dta", "SAS 2013-2016 plot x crop records (pre-redesign; record_type / source_module tag the shipped record; crop = wave's own list)", "plotcrop_early", sources=sources, crop_native=True)
    old_file = P["final"] / "SAS_pooled_plotcrop_2013_2014.dta"
    if old_file.exists(): old_file.unlink(); log.info("removed superseded SAS_pooled_plotcrop_2013_2014.dta")

# ---------------------------------------------------------------- other 2013-2016 modules: same module name in >= 2 wave-seasons
by_name = {}
for y in ("2013", "2014", "2015", "2016"):
    for f in sorted(inter.glob(f"SAS_{y}_*_clean.dta")):
        stem = re.sub(rf"^SAS_{y}_[ABC?]_(.*)_clean\.dta$", r"\1", f.name)
        if early_type(stem) is not None or re.search(r"yield|_province|weight$", stem): continue      # plot x crop record types live in the early file
        by_name.setdefault(stem, []).append(f)
for stem, fs in sorted(by_name.items()):
    if len({f.name.split("_")[1] for f in fs}) < 2: continue        # needs >= 2 years
    frames, labels, vlabs, sources = {}, {}, {}, {}
    for f in fs:
        df, vl, vv = read_dta(f)
        if len(df) < 200: continue
        w = f"{f.name.split('_')[1]}_{df['season'].iloc[0]}"; frames[w], labels[w], vlabs[w] = df, vl, vv; sources[w] = modkey(f)
    if len({w[:4] for w in frames}) >= 2:
        summary["files"][f"SAS_pooled_{stem}_2013_2016.dta"] = version_pool(frames, labels, vlabs, f"SAS_pooled_{stem}_2013_2016.dta", f"SAS 2013-2016 pooled module '{stem}' (pre-redesign design)", stem, out_dir=APPENDED, sources=sources)

# ---------------------------------------------------------------- other 2019+ modules
for canon, (pat, years) in MODULES.items():
    frames, labels, vlabs, sources = {}, {}, {}, {}
    for y in years:
        for f in files_for(str(y), pat):
            df, vl, vv = read_dta(f); wave = f"{y}_{df['season'].iloc[0]}" + ("_lsf" if "lsf_" in f.name else ("_ssf" if "ssf_" in f.name else ""))
            if "crop" in df.columns: df["crop_list"] = CROP_LIST(str(y)); vl["crop_list"] = "Crop code list generation of crop (codes comparable only within a list)"
            frames[wave], labels[wave], vlabs[wave] = df, vl, vv; sources[wave] = modkey(f)
    if len({w[:4] for w in frames}) >= 2:
        ys = sorted({w[:4] for w in frames})
        summary["files"][f"SAS_pooled_{canon}.dta"] = version_pool(frames, labels, vlabs, f"SAS_pooled_{canon}.dta", f"SAS {ys[0]}-{ys[-1]} pooled module '{canon}' ({len(ys)} years; crop = wave's own list)", canon, out_dir=APPENDED, sources=sources, crop_native="crop" in {c for d in frames.values() for c in d.columns})
for f in sorted(APPENDED.glob("*.dta")):                       # appended/ is entirely generated here: drop copies of modules no longer produced
    if f.name not in summary["files"]: f.unlink(); log.info("removed superseded %s", f.name)
save_json(summary, LOGS / "merge_alignment.json"); ck.done(); log.info("02_merge done")
