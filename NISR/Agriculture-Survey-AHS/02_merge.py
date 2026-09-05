"""
02_merge.py -- AHS: 2_Intermediate/AHS_<wave>_*_clean.dta -> 3_Final/ (person, household) and 2_Intermediate/appended/ (modules)

  3_Final/AHS_pooled_person.dta, AHS_pooled_household.dta   the three independent waves 2017, 2020, 2024 appended
  2_Intermediate/appended/AHS_pooled_<module>.dta            modules with the same content in >= 2 waves (MODULE_MAP);
                                                             rows outside the household sample carry sample = LSF

Alignment rule: waves are grouped into versions of a variable when (a) their variable labels
describe the same question (token Jaccard >= SIM_THRESHOLD) AND (b) their value labels are
compatible (no code whose text means something else; an unlabelled wave's values inside the
labelled range); the largest group keeps the name, others become <name>_v2 ...; FORCE_ALIGN
skips test (a); FORCE_SPLIT lists closed groups of waves that must stay apart. The AHS
questionnaires renumber items between waves, so many same-named items are different questions
(AHS audit 2026-09-05): the confirmed ones are FORCE_SPLIT below, the rest are caught by (b).
"""
import difflib, json, re
from collections import Counter
import numpy as np, pandas as pd
from ahs_helpers import (paths, get_logger, Checks, read_dta, write_dta, downcast, to_plain_float,
                          resolve_object_columns, label_similarity, save_json, LOGS)

log = get_logger("02_merge"); P = paths(); ck = Checks(log)
CS = ["2017", "2020", "2024"]
VUP = []
KEYS = ["survey", "year", "wave", "sample", "prov", "dist", "urban", "cluster", "hhid", "pid", "sex", "age", "wt", "wt_hh"]
STR_KEYS = ("survey", "wave", "sample", "cluster")
SIM_THRESHOLD = 0.5       # variable-label similarity (token Jaccard); 0.5 for AHS (items renumbered between waves; see the docstring)
VL_THRESHOLD = 0.6        # value-label text similarity (difflib ratio) for the same code to mean the same thing
FORCE_ALIGN = set()
# Same name, different question or coding (variable labels verified per wave, AHS audit 2026-09-05); closed groups:
FORCE_SPLIT = {"s1q2": ["2017"],                       # 2017 member NAME (text) vs 2024 relationship code
               "s1q7": ["2020"], "s1q8": ["2020"],      # 2017 education 4 codes vs 2020 7 codes; 2017 activity (cropping/non-farm) vs 2020 labour status
               "s0q9": ["2020"], "s0q12": ["2020"],     # respondent is head (2017) vs head's marital status (2020); relationship (2017) vs respondent is head (2020)
               "s0q13": ["2024"], "s0q15": ["2020", "2024"],   # activity (2017) vs relationship (2024); coop type (2017) / relationship (2020) / activity (2024)
               "s0q7": ["2020"], "s0q11": ["2020"],     # head's name (2017) vs household number (2020); non-head contact (2017) vs head's contact (2020)
               "s2q1": ["2020"], "s2q2": ["2020", "2024"], "s2q3": ["2020"],   # land items shift between 2017 and 2020; 2024 s2q2 = always lived in district
               "s7q2": ["2024"]}                        # tool owned (2017) vs purchased and used this season (2024)
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
CS_ORDER = {w: i for i, w in enumerate(CS)}

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
            "value_label_conflicts": {k: {c: sorted(s) for c, s in d.items()} for k, d in vl_conflicts.items()}, "stale_labels": stale_labels}

summary = {"threshold": SIM_THRESHOLD, "vl_threshold": VL_THRESHOLD, "force_align": sorted(FORCE_ALIGN), "force_split": FORCE_SPLIT, "files": {}}
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
    summary["files"][name] = pool(files, name, f"AHS pooled module '{canon}' (one row per record; sampled households plus large-scale-farmer supplement rows, sample = LSF -- filter on sample)", canon, out_dir=APPENDED)
summary["module_map"] = MODULE_MAP

save_json(summary, LOGS / "merge_alignment.json")
ck.done(); log.info("02_merge done")
