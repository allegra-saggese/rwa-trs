"""
02_merge.py -- CFSVA: 2_Intermediate/CFSVA_<wave>_*_clean.dta -> 3_Final/

  CFSVA_pooled_person.dta / CFSVA_pooled_household.dta          national cross-sections (CFSVA1,2,3,4_CS,5_CS,7_CS)
  CFSVA_pooled_person_vup.dta / CFSVA_pooled_household_vup.dta  VUP booster samples (CFSVA4/5/7_VUP)
  CFSVA_pooled_<module>.dta                                    modules with the same content in >= 2 waves (MODULE_MAP)
  CFSVA3_4_panel_link.dta, CFSVA5_vup_panel_link.dta            NISR's household/person linking files, keys harmonised

Alignment rule as in every NISR dataset: waves are grouped into versions of a variable by
label similarity (token Jaccard >= 0.25); the largest group keeps the name, others become
<name>_v2, _v3 ...; FORCE_ALIGN lists rewordings judged to be the same question.
"""
import json
from collections import Counter
import numpy as np, pandas as pd
from cfsva_helpers import (paths, get_logger, Checks, read_dta, write_dta, downcast, to_plain_float,
                          resolve_object_columns, label_similarity, save_json, LOGS)

log = get_logger("02_merge"); P = paths(); ck = Checks(log)
CS = ["2006", "2009", "2012", "2015", "2018", "2021", "2024"]
VUP = []
KEYS = ["survey", "year", "wave", "unit", "prov", "dist", "sector", "urban", "cluster", "hhid", "wt"]
STR_KEYS = ("survey", "wave", "unit", "cluster", "hhid", "key", "parent_key", "chn_key", "woman_key", "child_key")
SIM_THRESHOLD = 0.25
FORCE_ALIGN = set()
FORCE_SPLIT = {}
KEEP_DOUBLE = ("wt", "final_popweight", "final_norm_weight", "weight", "hhweight", "normalized_weight", "finalweight")

MODULE_MAP = {}
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
        for w in waves:
            if "wt" in data[w].columns: ck(abs(out.loc[out.wave == w, "wt"].sum() - data[w]["wt"].sum()) < 1e-6, f"{out_name}: {w} sum wt preserved")
    write_dta(out, P["final"] / out_name, var_labels, value_labels, label, log)
    return {"rows": len(out), "vars": list(out.columns), "unit": unit, "waves": waves, "decisions": decisions,
            "value_label_conflicts": {k: {c: sorted(s) for c, s in d.items()} for k, d in vl_conflicts.items()}}

summary = {"threshold": SIM_THRESHOLD, "force_align": sorted(FORCE_ALIGN), "files": {}}
inter = P["inter"]
for unit in ("household", "woman", "child", "village"):
    files = {w: inter / f"CFSVA_{w}_{unit}_clean.dta" for w in CS if (inter / f"CFSVA_{w}_{unit}_clean.dta").exists()}
    if not files: continue
    name = f"CFSVA_pooled_{unit}.dta"
    log.info("---------------- %s (%s)", name, list(files))
    summary["files"][name] = pool(files, name, f"CFSVA pooled {unit} file (NISR/WFP, 2006-2024)", unit)

# ---- modules with the same content in >= 2 waves
by_module = {}
for w, mp in MODULE_MAP.items():
    for stem, canon in mp.items():
        f = inter / f"CFSVA_{w}_{stem}_clean.dta"
        if f.exists(): by_module.setdefault(canon, {})[w] = f
for canon, files in sorted(by_module.items()):
    if len(files) < 2: continue
    name = f"CFSVA_pooled_{canon}.dta"
    log.info("---------------- %s (%s)", name, list(files))
    summary["files"][name] = pool(files, name, f"CFSVA pooled module '{canon}' (one row per {canon} record; see codebook)", canon)
summary["module_map"] = MODULE_MAP

save_json(summary, LOGS / "merge_alignment.json")
ck.done(); log.info("02_merge done")
