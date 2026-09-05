"""
02_merge.py -- EICV: 2_Intermediate/EICV_<wave>_*_clean.dta -> 3_Final/ and 2_Intermediate/appended/

  3_Final/EICV_pooled_person.dta, EICV_pooled_household.dta   the appended unit datasets (national rounds EICV1,2,3,4_CS,5_CS,7_CS)
  2_Intermediate/appended/
    EICV_pooled_person_vup.dta, EICV_pooled_household_vup.dta VUP booster samples (EICV4/5/7_VUP), appended
    EICV_pooled_<module>.dta                                  modules with the same content in >= 2 waves (MODULE_MAP), appended
    EICV3_4_panel_link.dta, EICV5_vup_panel_link.dta          NISR's household/person linking files, keys harmonised
  Rule (Matteo, 2026-09-04): 3_Final holds only the appended unit-level datasets (<= 5 files);
  every module-level file, per wave or appended, lives in 2_Intermediate.

Alignment rule as in every NISR dataset: waves are grouped into versions of a variable by
label similarity (token Jaccard >= 0.25); the largest group keeps the name, others become
<name>_v2, _v3 ...; FORCE_ALIGN lists rewordings judged to be the same question.
"""
import json
from collections import Counter
import numpy as np, pandas as pd
from eicv_helpers import (paths, get_logger, Checks, read_dta, write_dta, downcast, to_plain_float,
                          resolve_object_columns, label_similarity, save_json, LOGS)

log = get_logger("02_merge"); P = paths(); ck = Checks(log)
CS = ["EICV1", "EICV2", "EICV3", "EICV4_CS", "EICV5_CS", "EICV7_CS"]
VUP = ["EICV4_VUP", "EICV5_VUP", "EICV7_VUP"]
KEYS = ["survey", "year", "wave", "sample", "prov", "dist", "urban", "cluster", "hhid", "pid", "sex", "age", "wt", "wt_hh"]
STR_KEYS = ("survey", "wave", "sample", "cluster")
SIM_THRESHOLD = 0.25
FORCE_ALIGN = set()
FORCE_SPLIT = {}
KEEP_DOUBLE = ("wt", "wt_hh", "hhid", "pid_nisr", "pop_wt", "hh_wt", "pond", "weight")

# Canonical module names for files whose content repeats across waves (same questionnaire block).
MODULE_MAP = {
    "EICV1": {"s10_enter_1": "enterprise", "s11_tran_in": "transfers_in", "s11_tran_out": "transfers_out", "s12_credit": "credits",
              "s12_durables": "durables", "s12_saving": "savings", "s8_livestock": "livestock", "s8_livestock_products": "livestock_products",
              "s8_livestock_expense": "livestock_expenditure", "s8_farm_plot_details": "parcels", "s8_farm_expense": "agri_expenditure",
              "s8_farm_assets": "equipment", "s8_farm_processing": "agri_processing", "s9_expen_food": "food"},
    "EICV2": {"s6d_employ_roster": "jobs", "s7_enterprise": "enterprise", "s8a1_livestock": "livestock", "s8a2_livestock_products": "livestock_products",
              "s8a3_livestock_expenditure": "livestock_expenditure", "s8b_ag_assets": "equipment", "s8c_ag_plots": "parcels",
              "s8d_ag_production1": "crop_large", "s8e_ag_production2": "crop_small", "s8g_ag_expense": "agri_expenditure", "s8h_ag_process": "agri_processing",
              "s9a1_nfood_annual": "expenditure_annual", "s9a2_nfood_month": "expenditure_monthly", "s9a3_nfood_freq": "expenditure_frequent",
              "s9b_food": "food", "s9d_ex_owncons": "own_consumption", "s10a_transfer_out": "transfers_out", "s10b_transfer_in": "transfers_in",
              "s10c_misc": "other_income", "s11a_credit": "credits", "s11b_durables": "durables", "s11c_savings": "savings", "s5e_services": "services"},
    "EICV3": {"s05e_services": "services", "s06cdef_jobs": "jobs", "s07_enterprise": "enterprise", "s08a1_livestock": "livestock",
              "s08a3_livestock": "livestock_products", "s08a4_livestock": "livestock_expenditure", "s08b2_equipment": "equipment", "s08c_parcels": "parcels",
              "s08d_croplarge": "crop_large", "s08e_cropsmall": "crop_small", "s08f_otheragric": "agri_other", "s08g_inputs": "agri_expenditure",
              "s08h_processing": "agri_processing", "s09a1_consnonfood": "expenditure_annual", "s09a2_consnonfood": "expenditure_monthly",
              "s09a3_consnonfood": "expenditure_frequent", "s09b_consfood": "food", "s09c_consownfood": "own_consumption", "s10a_transfersout": "transfers_out",
              "s10b_transfersin": "transfers_in", "s10c_otherinc": "other_income", "s10e_otherexp": "other_expenditure", "s11a2_credit": "credits",
              "s11b_durables": "durables", "s11c_savings": "savings"},
}
for w, pre in (("EICV4_CS", ""), ("EICV4_VUP", ""), ("EICV5_CS", ""), ("EICV5_VUP", "")):
    MODULE_MAP[w] = {"s5e_access_to_services": "services", "s5f_access_to_services": "services",
                     "s6b_employement_6c_salaried_s6d_business": "jobs", "s7a1_livestock": "livestock", "s7a3_livestock": "livestock_products",
                     "s7a4_livestock": "livestock_expenditure", "s7b2_land_agriculture": "land", "s7c_parcels": "parcels", "s7d_large_crop": "crop_large",
                     "s7e_small_crop": "crop_small", "s7f_income_agriculture": "agri_income", "s7g_expenditure_agriculture": "agri_expenditure",
                     "s7h_transformation_agriculture": "agri_processing", "s8a1_expenditure": "expenditure_annual", "s8a2_expenditure": "expenditure_monthly",
                     "s8a3_expenditure": "expenditure_frequent", "s8b_expenditure": "food", "s8c_farming": "own_consumption", "s9a_transfers_out": "transfers_out",
                     "s9b_transfers_in": "transfers_in", "s9d_other_income": "other_income", "s9e_other_expenditure": "other_expenditure",
                     "s10a2_credits": "credits", "s10a2_listing_of_credits": "credits", "s10b_goods": "durables", "s10b2_durable_household_goods": "durables",
                     "s10c_savings": "savings", "s10c1_savings": "savings", "s10c2_tontine": "tontine"}
for w in ("EICV7_CS", "EICV7_VUP"):
    MODULE_MAP[w] = {"s5f_access_to_services": "services", "s8a1_expenditure": "expenditure_annual", "s8a2_expenditure": "expenditure_monthly",
                     "s8a3_expenditure": "expenditure_frequent", "s8b_food_expenditure_consumption": "food", "s9a_transfers_out": "transfers_out",
                     "s9b_transfers_in": "transfers_in", "s9c_other_expenditure": "other_expenditure", "s9e_other_income": "other_income",
                     "s10a1_a2_credits": "credits", "s10b_durables": "durables", "s10c_savings": "savings"}

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
CS_ORDER = {w: i for i, w in enumerate(CS + VUP)}

APPENDED = P["inter"] / "appended"; APPENDED.mkdir(exist_ok=True)

def pool(files, out_name, label, unit, out_dir=None):
    """files: {wave: path}. Writes the pooled file to out_dir (default 3_Final) and returns its summary."""
    out_dir = out_dir or P["final"]
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
    write_dta(out, out_dir / out_name, var_labels, value_labels, label, log)
    return {"rows": len(out), "vars": list(out.columns), "unit": unit, "waves": waves, "dir": str(out_dir.relative_to(P["root"])), "decisions": decisions,
            "value_label_conflicts": {k: {c: sorted(s) for c, s in d.items()} for k, d in vl_conflicts.items()}}

summary = {"threshold": SIM_THRESHOLD, "force_align": sorted(FORCE_ALIGN), "files": {}}
inter = P["inter"]
for unit in ("person", "household"):
    for tag, waves in (("", CS), ("_vup", VUP)):
        files = {w: inter / f"EICV_{w}_{unit}_clean.dta" for w in waves if (inter / f"EICV_{w}_{unit}_clean.dta").exists()}
        name = f"EICV_pooled_{unit}{tag}.dta"
        log.info("---------------- %s (%s)", name, list(files))
        summary["files"][name] = pool(files, name, f"EICV pooled {unit} file, {'VUP booster samples' if tag else 'national cross-sections'}", unit,
                                      out_dir=APPENDED if tag else None)

# ---- modules with the same content in >= 2 waves
# Item-level consumption and asset modules (food, expenditure_*, own_consumption, durables) pool into
# multi-GB files (the food module alone reaches 10.8m rows x 168 vars = 5.8 GB); they are cleaned per
# wave in 2_Intermediate/ and left out of the pooled set. Add a name to POOL_ITEM_MODULES to pool it.
ITEM_MODULES = {"food", "expenditure_annual", "expenditure_monthly", "expenditure_frequent", "own_consumption", "durables"}
POOL_ITEM_MODULES = set(ITEM_MODULES)      # 2026-09-04: pooled on Matteo's request (disk freed)
by_module = {}
for w, mp in MODULE_MAP.items():
    for stem, canon in mp.items():
        f = inter / f"EICV_{w}_{stem}_clean.dta"
        if f.exists(): by_module.setdefault(canon, {})[w] = f
for canon, files in sorted(by_module.items()):
    if len(files) < 2: continue
    if canon in ITEM_MODULES and canon not in POOL_ITEM_MODULES:
        log.info("---------------- %s: item-level module, not pooled (per-wave files in 2_Intermediate)", canon); continue
    name = f"EICV_pooled_{canon}.dta"
    log.info("---------------- %s (%s)", name, list(files))
    summary["files"][name] = pool(files, name, f"EICV pooled module '{canon}' (one row per {canon} record; see codebook)", canon, out_dir=APPENDED)
summary["module_map"] = MODULE_MAP

# ---- link files
for w, stem, out in (("EICV3_4_Panel", "data_stata", "EICV3_4_panel_link.dta"), ("EICV5_VUP", "panel_for_merge", "EICV5_vup_panel_link.dta")):
    f = inter / f"EICV_{w}_{stem}_clean.dta"
    if f.exists():
        df, vl, vv = read_dta(f); write_dta(df, APPENDED / out, vl, vv, f"NISR linking file {stem} ({w}), keys harmonised", log)
        summary["files"][out] = {"rows": len(df), "vars": list(df.columns), "unit": "link", "waves": [w], "dir": str(APPENDED.relative_to(P["root"]))}
save_json(summary, LOGS / "merge_alignment.json")
ck.done(); log.info("02_merge done")
