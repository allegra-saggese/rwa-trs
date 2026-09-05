"""
02_merge.py -- CFSVA: 2_Intermediate/CFSVA_<wave>_*_clean.dta -> 3_Final/

  CFSVA_pooled_person.dta / CFSVA_pooled_household.dta          national cross-sections (CFSVA1,2,3,4_CS,5_CS,7_CS)
  CFSVA_pooled_person_vup.dta / CFSVA_pooled_household_vup.dta  VUP booster samples (CFSVA4/5/7_VUP)
  CFSVA_pooled_<module>.dta                                    modules with the same content in >= 2 waves (MODULE_MAP)
  CFSVA3_4_panel_link.dta, CFSVA5_vup_panel_link.dta            NISR's household/person linking files, keys harmonised

Alignment rule as in every NISR dataset: a same-named variable is ONE column across waves only
when (a) its variable labels are similar (token Jaccard >= SIM_THRESHOLD) AND (b) its value labels
are compatible (no code whose text means something else; an unlabelled wave's values inside the
labelled range); otherwise <name>_v2, _v3 ... FORCE_ALIGN skips only the label test; FORCE_SPLIT
closes groups. CFSVA audit 2026-09-05: the old label-only rule (0.25) pooled 2006 food quantities
with 2012 crop indicators (rice, beans, maize, cassava), child name with caregiver (s14_02) and
recoded categorical items (seed / fertiliser sources AS5_03 ..., loan refusal s6_03_2, shocks
as10_05, food sources s8_04 ...).
"""
import difflib, json, re
from collections import Counter
import numpy as np, pandas as pd
from cfsva_helpers import (paths, get_logger, Checks, read_dta, write_dta, downcast, to_plain_float,
                          resolve_object_columns, label_similarity, save_json, LOGS)

log = get_logger("02_merge"); P = paths(); ck = Checks(log)
CS = ["2006", "2009", "2012", "2015", "2018", "2021", "2024"]
VUP = []
KEYS = ["survey", "year", "wave", "unit", "prov", "dist", "sector", "urban", "cluster", "hhid", "wt"]
STR_KEYS = ("survey", "wave", "unit", "cluster", "hhid", "key", "parent_key", "chn_key", "woman_key", "child_key")
SIM_THRESHOLD = 0.5; VL_THRESHOLD = 0.6
FORCE_ALIGN = set()
FORCE_SPLIT = {}
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
def vl_conflicts_of(a, b):
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
        c = vl_conflicts_of(a, b)
        if c: return f"{y} vs {z}: value labels differ -- " + "; ".join(f"{k:g}: {p!r} vs {q!r}" for k, (p, q) in sorted(c.items())[:3])
    elif a or b:
        lab, u = (a, z) if a else (b, y)
        codes = [c for c in lab if c not in SENTINELS]
        r = rng.get(u)
        if len(codes) >= 2 and r and r[1] > max(codes):
            return f"{y} vs {z}: {u} is unlabelled and its values reach {r[1]:g}, beyond the labelled codes ({min(codes):g}-{max(codes):g})"
    return None
KEEP_DOUBLE = ("wt", "final_popweight", "final_norm_weight", "weight", "hhweight", "normalized_weight", "finalweight")

MODULE_MAP = {}
# ------------------------------------------------------------------ generic pooling
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

def pool(files, out_name, label, unit):
    """files: {wave: path}. Returns (frame, decisions) and writes the pooled file."""
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
        vls = {w: _numlab(vlabs[w].get(v)) for w in ws}; rng = {w: _range(data[w][v]) for w in ws}
        groups, reasons = version_groups(v, ws, labs, vls, rng); versions = {}
        stale = {w: sorted(_obs(data[w][v]) - set(vls[w]) - SENTINELS)[:20] for w in ws if len(set(vls[w]) - SENTINELS) >= 3}
        stale = {w: s for w, s in stale.items() if s}
        if stale: stale_labels[v] = stale
        for i, g in enumerate(groups):
            name = v if i == 0 else f"{v[:28]}_v{i + 1}"; versions[name] = g
            for w in g: colname[(v, w)] = name
        decisions[v] = {"waves": ws, "versions": versions, "labels_by_wave": labs, "reference_label": labs[groups[0][-1]], "split_reasons": reasons}
        if len(groups) > 1: log.info("  VERSIONS %s: %s | %s", v, {k: len(g) for k, g in versions.items()}, " / ".join(reasons[:2]))
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
        for w in waves:
            if "wt" in data[w].columns: ck(abs(out.loc[out.wave == w, "wt"].sum() - data[w]["wt"].sum()) < 1e-6, f"{out_name}: {w} sum wt preserved")
    write_dta(out, P["final"] / out_name, var_labels, value_labels, label, log)
    return {"rows": len(out), "vars": list(out.columns), "unit": unit, "waves": waves, "decisions": decisions,
            "value_label_conflicts": {k: {c: sorted(s) for c, s in d.items()} for k, d in vl_conflicts.items()}, "stale_labels": stale_labels}

summary = {"threshold": SIM_THRESHOLD, "vl_threshold": VL_THRESHOLD, "force_align": sorted(FORCE_ALIGN), "force_split": FORCE_SPLIT, "files": {}}
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
