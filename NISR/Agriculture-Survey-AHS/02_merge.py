"""
02_merge.py -- AHS: 2_Intermediate/AHS_<wave>_*_clean.dta -> 3_Final/

  AHS_pooled_person.dta / AHS_pooled_household.dta          national cross-sections (AHS1,2,3,4_CS,5_CS,7_CS)
  AHS_pooled_person_vup.dta / AHS_pooled_household_vup.dta  VUP booster samples (AHS4/5/7_VUP)
  AHS_pooled_<module>.dta                                    modules with the same content in >= 2 waves (MODULE_MAP)
  AHS3_4_panel_link.dta, AHS5_vup_panel_link.dta            NISR's household/person linking files, keys harmonised

Alignment rule as in every NISR dataset: waves are grouped into versions of a variable by
label similarity (token Jaccard >= 0.25); the largest group keeps the name, others become
<name>_v2, _v3 ...; FORCE_ALIGN lists rewordings judged to be the same question.
"""
import json
from collections import Counter
import numpy as np, pandas as pd
from ahs_helpers import (paths, get_logger, Checks, read_dta, write_dta, downcast, to_plain_float,
                          resolve_object_columns, label_similarity, save_json, LOGS)

log = get_logger("02_merge"); P = paths(); ck = Checks(log)
CS = ["2017", "2020", "2024"]
VUP = []
KEYS = ["survey", "year", "wave", "sample", "prov", "dist", "urban", "cluster", "hhid", "pid", "sex", "age", "wt", "wt_hh"]
STR_KEYS = ("survey", "wave", "sample", "cluster")
SIM_THRESHOLD = 0.25
FORCE_ALIGN = set()
FORCE_SPLIT = {}
KEEP_DOUBLE = ("wt", "wt_hh", "hhid", "pid_nisr", "pop_wt", "hh_wt", "pond", "weight")

# Canonical module names for files whose content repeats across waves (same questionnaire block).
# The 2020 sections are numbered without titles in the shipped files and are mapped only where the
# variable labels make the content unambiguous; unmapped modules stay per-wave in 2_Intermediate.
MODULE_MAP = {
    "2017": {"s10_1_cattle_milk_production": "milk", "s10_2_cattle_milk_production_use": "milk_use", "s10_3_honey_production": "honey",
             "s11_animal_inputs_and_services": "animal_inputs", "s2_land_tenure_and_crops_planted": "land", "s3_extension_services_and_agricultural_programmes": "extension",
             "s4_funding_during_2016": "credits", "s5_agricultural_inputs": "inputs", "s6_agricultural_practices": "practices",
             "s7_1_agricultural_small_tools": "tools", "s7_2_agricultural_durable_tools": "tools_durable", "s8_a_production_use_storage_and_expenses": "production",
             "s8_b_production_use_storage_and_expenses": "production_b", "s9_number_of_animals": "livestock"},
    # 2020 sections mapped from the questionnaire (z_Documentation/2020): II land tenure / crops & inputs /
    # fruits, III extension, IV savings-credits, V livestock numbers, VI stock change, VII milk / eggs / honey,
    # VIII animal health, IX animal input expenditures
    "2020": {"section_2_1": "land", "section_2_2": "inputs", "section_2_3": "fruits", "section_3_1": "extension", "section_3_2": "programmes",
             "section_4": "credits", "section_5": "livestock", "section_6": "livestock_change", "section_7_1": "milk", "section_7_2": "eggs",
             "section_7_3": "honey", "section_8": "animal_health", "section_9": "animal_inputs"},
    "2024": {"section11_1_cattle_milk_production_and_use": "milk", "section11_2_egg_production": "eggs", "section11_3_honey_production": "honey",
             "section2_land_tenure": "land", "section6_extension_services_and_agricultural_programmes": "extension", "credits": "credits", "saving": "savings",
             "section7_agricultural_tools": "tools", "section9_10_12_livestock_and_animal_inputs_expenditures": "livestock", "section5_fruits_production": "fruits",
             "section3_4_crop_grown_seeds_and_production_agricultural_inputs_and_practices": "plotcrop"},
}
# ------------------------------------------------------------------ generic pooling
def version_groups(v, waves, labs):
    if v in KEYS or v in FORCE_ALIGN or len(waves) == 1: return [list(waves)]
    groups = []
    for w in waves:
        if v in FORCE_SPLIT and w in FORCE_SPLIT[v]: groups.append((labs[w], [w])); continue
        for rep, ws in groups:
            if not labs[w] or not rep or label_similarity(labs[w], rep) >= SIM_THRESHOLD: ws.append(w); break
        else: groups.append((labs[w], [w]))
    groups.sort(key=lambda g: (-len(g[1]), -max(CS_ORDER.get(x, 0) for x in g[1])))
    return [ws for _, ws in groups]
CS_ORDER = {w: i for i, w in enumerate(CS)}

def pool(files, out_name, label, unit):
    """files: {wave: path}. Returns (frame, decisions) and writes the pooled file."""
    data, labels, vlabs = {}, {}, {}
    for w, f in files.items():
        df, vl, vv = read_dta(f); data[w], labels[w], vlabs[w] = df, vl, vv
        log.info("  loaded %-10s %-55s %9s rows x %4d", w, f.name, f"{len(df):,}", df.shape[1])
    waves = list(files)
    allvars = sorted({c for df in data.values() for c in df.columns})
    decisions, colname, vl_conflicts, var_labels, value_labels = {}, {}, {}, {}, {}
    for v in allvars:
        ws = [w for w in waves if v in data[w].columns]
        labs = {w: (labels[w].get(v) or "").strip() for w in ws}
        groups = version_groups(v, ws, labs); versions = {}
        for i, g in enumerate(groups):
            name = v if i == 0 else f"{v[:28]}_v{i + 1}"; versions[name] = g
            for w in g: colname[(v, w)] = name
        decisions[v] = {"waves": ws, "versions": versions, "labels_by_wave": labs, "reference_label": labs[groups[0][-1]]}
        if len(groups) > 1: log.info("  VERSIONS %s: %s", v, versions)
    frames = []
    for w in waves:
        df, vl, vv = data[w].copy(), labels[w], vlabs[w]
        ren = {v: colname[(v, w)] for v in df.columns if colname[(v, w)] != v}
        df = df.rename(columns=ren)
        for c in df.columns:
            v = next((k for k, n in ren.items() if n == c), c)
            var_labels[c] = vl.get(v) or var_labels.get(c) or ""
            if v in vv:
                merged = value_labels.get(c, {})
                for code, txt in vv[v].items():
                    if code in merged and str(merged[code]).strip().lower() != str(txt).strip().lower():
                        vl_conflicts.setdefault(c, {}).setdefault(str(code), set()).update([merged[code], txt])
                    merged[code] = txt
                value_labels[c] = merged
        frames.append(to_plain_float(df))
    for c in list(var_labels):
        if "_v" in c and c.rsplit("_v", 1)[-1].isdigit():
            base = next((b for b, d in decisions.items() if c in d["versions"]), None)
            if base: g = decisions[base]["versions"][c]; var_labels[c] = f"[{g[0]}..{g[-1]} version] " + var_labels[c][:56]
    out = pd.concat(frames, ignore_index=True, sort=False)
    out = resolve_object_columns(out, log, keep_str=STR_KEYS)
    keys = [k for k in KEYS if k in out.columns]
    out = out[keys + [c for c in out.columns if c not in keys]]
    out = downcast(out, keep_double=KEEP_DOUBLE)
    ck(len(out) == sum(len(d) for d in data.values()), f"{out_name}: pooled rows == sum of wave rows")
    if "wt" in out.columns:
        for w in waves: ck(abs(out.loc[out.wave == w, "wt"].sum() - data[w]["wt"].sum()) < 1e-6, f"{out_name}: {w} sum wt preserved")
    write_dta(out, P["final"] / out_name, var_labels, value_labels, label, log)
    return {"rows": len(out), "vars": list(out.columns), "unit": unit, "waves": waves, "decisions": decisions,
            "value_label_conflicts": {k: {c: sorted(s) for c, s in d.items()} for k, d in vl_conflicts.items()}}

summary = {"threshold": SIM_THRESHOLD, "force_align": sorted(FORCE_ALIGN), "files": {}}
inter = P["inter"]
for unit in ("person", "household"):
    for tag, waves in (("", CS),):
        files = {w: inter / f"AHS_{w}_{unit}_clean.dta" for w in waves if (inter / f"AHS_{w}_{unit}_clean.dta").exists()}
        name = f"AHS_pooled_{unit}{tag}.dta"
        log.info("---------------- %s (%s)", name, list(files))
        summary["files"][name] = pool(files, name, f"AHS pooled {unit} file (agricultural households)", unit)

# ---- modules with the same content in >= 2 waves
by_module = {}
for w, mp in MODULE_MAP.items():
    for stem, canon in mp.items():
        f = inter / f"AHS_{w}_{stem}_clean.dta"
        if f.exists(): by_module.setdefault(canon, {})[w] = f
for canon, files in sorted(by_module.items()):
    if len(files) < 2: continue
    name = f"AHS_pooled_{canon}.dta"
    log.info("---------------- %s (%s)", name, list(files))
    summary["files"][name] = pool(files, name, f"AHS pooled module '{canon}' (one row per {canon} record; see codebook)", canon)
summary["module_map"] = MODULE_MAP

save_json(summary, LOGS / "merge_alignment.json")
ck.done(); log.info("02_merge done")
