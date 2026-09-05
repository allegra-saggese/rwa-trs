"""
02_merge.py -- EICV: 2_Intermediate/EICV_<wave>_*_clean.dta -> 3_Final/ and 2_Intermediate/appended/

  3_Final/EICV_pooled_person.dta, EICV_pooled_household.dta   the appended unit datasets (national rounds EICV1,2,3,4_CS,5_CS,7_CS)
  2_Intermediate/appended/
    EICV_pooled_person_vup.dta, EICV_pooled_household_vup.dta VUP booster samples (EICV4/5/7_VUP), appended
    EICV_pooled_<module>.dta                                  modules with the same content in >= 2 waves (MODULE_MAP), appended
    EICV3_4_panel_link.dta, EICV5_vup_panel_link.dta          NISR's household/person linking files, keys harmonised
  Rule (Matteo, 2026-09-04): 3_Final holds only the appended unit-level datasets (<= 5 files);
  every module-level file, per wave or appended, lives in 2_Intermediate.

Alignment rule: waves are grouped into versions of a variable when (a) their variable labels
describe the same question (token Jaccard >= SIM_THRESHOLD; 0.5 for EICV because item numbers
move between rounds and many same-named items are different questions with a shared word --
EICV audit 2026-09-05) AND (b) their value labels are compatible (no code whose text means
something else; an unlabelled wave's values inside the labelled range). The largest group keeps
the name, others become <name>_v2 ...; FORCE_ALIGN lists rewordings judged to be the same
question (skips test (a) only; value labels verified compatible when the list was written);
FORCE_SPLIT lists closed groups of waves that must stay apart. Reasons for every split and the
"stale labels" (codes observed outside a wave's own value labels) go to merge_alignment.json.
"""
import difflib, json, re
from collections import Counter
import numpy as np, pandas as pd
from eicv_helpers import (paths, get_logger, Checks, read_dta, write_dta, downcast, to_plain_float,
                          resolve_object_columns, label_similarity, save_json, LOGS)

log = get_logger("02_merge"); P = paths(); ck = Checks(log)
CS = ["EICV1", "EICV2", "EICV3", "EICV4_CS", "EICV5_CS", "EICV7_CS"]
VUP = ["EICV4_VUP", "EICV5_VUP", "EICV7_VUP"]
KEYS = ["survey", "year", "wave", "sample", "prov", "dist", "urban", "cluster", "stratum", "hhid", "pid", "sex", "age", "wt", "wt_hh"]
STR_KEYS = ("survey", "wave", "sample", "cluster")
SIM_THRESHOLD = 0.5       # variable-label similarity (token Jaccard); 0.5 for EICV (see the docstring)
VL_THRESHOLD = 0.6        # value-label text similarity (difflib ratio) for the same code to mean the same thing
# Rewordings of the same question across rounds (read from the labels; value labels verified compatible in every
# wave pair when the list was written, 2026-09-05). The rule still splits them if their value labels ever conflict.
FORCE_ALIGN = {'s5aq4', 's4aq14', 's6bq1', 's3q1', 's8bq15', 's11aq1', 's8bq13', 's5bq8', 's5cq5', 's8bq3', 's6aq1', 's3aq19', 'ur', 's7a2q5', 's2cq13', 's3aq22', 's8bq7', 's5cq22', 's7a2q9', 's8bq2', 's8bq5', 's2q1'}
# same name, different question, but labels too alike for the threshold (found while harmonising, 2026-09-05):
# s6aq6 EICV3 'VUP works programme' vs EICV5 'worked in a non-farm business'; s6aq8 EICV5 'months occupied' vs
# EICV4 'main reason for not working'; s4bq4 EICV4 'can write' vs EICV5/7 'able to read'.
FORCE_SPLIT = {   # closed groups of waves (a wave, or a list of waves pooled together) that must not join the others
    "s6aq6": ["EICV3"], "s6aq8": [["EICV5_CS", "EICV5_VUP"]], "s4bq4": [["EICV4_CS", "EICV4_VUP"]],                 # found while harmonising
    # EICV audit 2026-09-05 -- same name, different question (variable labels verified per wave):
    "s1q13": [["EICV7_CS", "EICV7_VUP"]],          # father alive (EICV3/4) vs mother alive (EICV7); EICV5 = disability (own version)
    "s1q14": [["EICV5_CS", "EICV5_VUP"], ["EICV7_CS", "EICV7_VUP"]],   # mother alive (EICV3/4) vs father alive (EICV5) vs household membership (EICV7)
    "s3q7": [["EICV7_CS", "EICV7_VUP"]], "s3q8": [["EICV7_CS", "EICV7_VUP"]], "s3q9": [["EICV7_CS", "EICV7_VUP"]],   # disability items shift by one in EICV7
    "s4aq7": ["EICV1"], "s4aq8": [["EICV7_CS", "EICV7_VUP"]],                                                      # other work (EICV1) / school type vs highest level (EICV7)
    "s2cq6": ["EICV3"], "s3aq12": ["EICV1"], "s2bq7": ["EICV1"], "s3bq8": ["EICV2"],                                  # literacy course vs months of training; cost vs reason; primary completed vs type; prenatal vs vaccination
    "s3cq5a": ["EICV1"], "s3cq5c": ["EICV1"], "s3cq5d": ["EICV1"],                                                  # vaccine items shift between EICV1 and EICV2
    "s5cq7": [["EICV7_CS", "EICV7_VUP"]], "s7a2q2": [["EICV7_CS", "EICV7_VUP"]], "s5aq1": ["EICV2"], "s5bq10": ["EICV2"], "s5aq3": [["EICV7_CS", "EICV7_VUP"]],
    "s5cq9a": ["EICV5_CS"], "s8bq10": ["EICV1"], "s6bq4": ["EICV2"],
    "s10aq7": [["EICV7_CS", "EICV7_VUP"]],         # loan amount vs main purpose of loan (credits module)
    "s7dq6": [["EICV5_CS", "EICV5_VUP"]],          # kg sold vs average price per kg (crop_large module)
    "s7bq15": ["EICV3"],                            # amount borrowed vs main source of credit (enterprise module)
    "sol_jan": [["EICV7_CS", "EICV7_VUP"]],        # consumption aggregate in January-2024 prices (EICV3/5: January-2014 prices)
    "pov": ["EICV2"], "ae": [["EICV7_CS", "EICV7_VUP"]],   # poverty incidence (EICV1) vs poverty line (EICV2); adult equivalents (EICV5 label) vs hhsize A/E (EICV7)
}
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

def version_groups(v, waves, labs, vls, rng):
    """Greedy grouping of waves: a wave joins the first group whose variable label is similar (skipped for FORCE_ALIGN)
    AND whose value labels are compatible with every member; FORCE_SPLIT groups are closed. Returns (groups, reasons)."""
    if v in KEYS or len(waves) == 1: return [list(waves)], []
    forced = {}
    for i, g in enumerate(FORCE_SPLIT.get(v, [])):
        for w in ([g] if not isinstance(g, list) else g): forced[w] = i
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
    groups.sort(key=lambda g: (-len(g[1]), -max(CS_ORDER.get(x, 0) for x in g[1])))
    return [ws for _, ws in groups], (reasons if len(groups) > 1 else [])
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
    decisions, colname, vl_conflicts, var_labels, value_labels, stale_labels = {}, {}, {}, {}, {}, {}
    for v in allvars:
        ws = [w for w in waves if v in data[w].columns]
        labs = {w: (labels[w].get(v) or "").strip() for w in ws}
        vls = {w: (vlabs[w].get(v) or {}) for w in ws}
        rng = {w: _range(data[w][v]) for w in ws}
        groups, reasons = version_groups(v, ws, labs, vls, rng); versions = {}
        stale = {w: sorted(_obs(data[w][v]) - set(vls[w]) - SENTINELS)[:20] for w in ws if len(set(vls[w]) - SENTINELS) >= 3}
        stale = {w: s for w, s in stale.items() if s}
        if stale: stale_labels[v] = stale
        for i, g in enumerate(groups):
            name = v if i == 0 else f"{v[:28]}_v{i + 1}"; versions[name] = g
            for w in g: colname[(v, w)] = name
        decisions[v] = {"waves": ws, "versions": versions, "labels_by_wave": labs, "reference_label": labs[groups[0][-1]], "split_reasons": reasons}
        if len(groups) > 1: log.info("  VERSIONS %s: %s | %s", v, versions, " / ".join(reasons[:2]))
    if stale_labels: log.info("  %d variables with codes observed outside their own value labels (stale labels)", len(stale_labels))
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
            "stems": {w: [f.name.replace(f"EICV_{w}_", "").replace("_clean.dta", "")] for w, f in files.items()},
            "value_label_conflicts": {k: {c: sorted(s) for c, s in d.items()} for k, d in vl_conflicts.items()}, "stale_labels": stale_labels}

summary = {"threshold": SIM_THRESHOLD, "vl_threshold": VL_THRESHOLD, "force_align": sorted(FORCE_ALIGN), "force_split": FORCE_SPLIT, "files": {}}
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
    summary["files"][name] = pool(files, name, f"EICV pooled module '{canon}' (one row per record; CS and VUP samples appended -- filter on sample)", canon, out_dir=APPENDED)
summary["module_map"] = MODULE_MAP

# ---- link files
for w, stem, out in (("EICV3_4_Panel", "data_stata", "EICV3_4_panel_link.dta"), ("EICV5_VUP", "panel_for_merge", "EICV5_vup_panel_link.dta")):
    f = inter / f"EICV_{w}_{stem}_clean.dta"
    if f.exists():
        df, vl, vv = read_dta(f); write_dta(df, APPENDED / out, vl, vv, f"NISR linking file {stem} ({w}), keys harmonised", log)
        summary["files"][out] = {"rows": len(df), "vars": list(df.columns), "unit": "link", "waves": [w], "dir": str(APPENDED.relative_to(P["root"]))}
save_json(summary, LOGS / "merge_alignment.json")
ck.done(); log.info("02_merge done")
