"""
00_names.py -- LFS: build variable_names.csv (native name -> clean name and label, per file) from the last run's logs.

Rules (Matteo, 2026-09-06): every variable name is lowercase English words joined by underscores with the dataset prefix,
at most 32 characters, full words unless the name does not fit; every label is a plain English sentence of at most 80
characters starting with the dataset tag; nothing in French or Kinyarwanda. Names are generated from the labels by the
engine in <ds>_helpers.py, reviewed here (collisions get distinguishing words, then the item number, then the native
code) and written to variable_names.csv, which 01_clean / 02_merge apply and 03_checks / 04_codebook / Harmonize read.
Pooled columns are named first (one name per version, with the years in the name when a variable has several versions);
the per-wave files take the pooled name of their version so that a variable keeps one name from cleaning to harmonisation.
Run after a build whose logs carry the native labels; the table is committed next to the code.
"""
import json, re, sys
from lfs_helpers import (paths, get_logger, LOGS, HERE, DATASET_TAG, NameTable, KEY_STEMS, KEY_EXTRA, WAVE_YEAR, TRANSLATE_EXTRA,
                       clean_label, assign_names, label_with_tag, version_suffix, versioned, cut, make_slug, _words)

log = get_logger("00_names"); P = paths(); TAG = DATASET_TAG; TAGU = TAG.upper()
align = json.load(open(LOGS / "merge_alignment.json"))
metas = {f.stem[6:-5]: json.load(open(f)) for f in sorted(LOGS.glob("clean_*_meta.json"))}
table = NameTable(HERE / "variable_names.csv", TAG); table.rows = []; table.by_scope = {}
stems = {**KEY_STEMS, **KEY_EXTRA}
# hand overrides: native name -> (clean stem, label text), from variable_name_overrides.csv next to the code (reviewed items)
OVERRIDES = {}
_ov = HERE / "variable_name_overrides.csv"
if _ov.exists():
    import csv
    with open(_ov, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("native"): OVERRIDES[r["native"].strip()] = (r["clean_stem"].strip(), r["clean_label"].strip())

def native_labels(meta_entry):
    return meta_entry.get("native_labels") or meta_entry.get("var_labels") or {}

def _years_text(ws):
    ys = sorted({int(WAVE_YEAR(w)) for w in ws}); return f"{ys[0]}" if ys[0] == ys[-1] else f"{ys[0]}-{ys[-1]}"

def _suffix(ws, multi, all_waves):
    """the years suffix a pooled column carries: always for a versioned variable, never otherwise"""
    return version_suffix(ws, WAVE_YEAR) if multi else ""

def resolve(names, items, all_waves):
    """make names unique inside one file: duplicates get the distinguishing words of their labels (years kept), then the
    item number of the native code, then the native code"""
    groups = {}
    for i, n in enumerate(names): groups.setdefault(n, []).append(i)
    out = list(names)
    for n, idx in groups.items():
        if len(idx) == 1: continue
        labels = [items[i][2] for i in idx]; common = set.intersection(*[set(_words(l)) for l in labels])
        for i in idx:
            col, base, lab, ws, multi, text, fixed = items[i]; suf = _suffix(ws, multi, all_waves)
            if fixed: continue                                                              # a key or reviewed stem keeps its name
            ws_ = [w for w in _words(lab) if w not in common][:3]; head = [w for w in _words(lab) if w in common][:2]
            cand = (make_slug(" ".join(head + ws_), TAG, col, 32 - len(suf)) + suf) if ws_ else n
            if cand == n and not multi and set(map(str, ws)) != set(map(str, all_waves)): cand = versioned(n, version_suffix(ws, WAVE_YEAR))
            m = re.search(r"(\d+[a-z]?)$", str(col).replace("_v", "v"))
            if cand == n and m: cand = cut(n, 32 - len(m.group(1)) - 1) + "_" + m.group(1)
            out[i] = cand
        seen = set(out[j] for j in range(len(out)) if j not in idx)
        for i in idx:
            if out[i] in seen:
                suf = "_" + re.sub(r"[^a-z0-9]+", "", str(items[i][0]).lower())[:10]; out[i] = cut(out[i], 32 - len(suf)) + suf
            seen.add(out[i])
    return out

def name_pooled(fname, decisions, wave_labels):
    """one clean name per pooled column from ITS OWN label (a version is a different question or coding); keys and
    overridden items get fixed stems; several versions -> the years of the version in name and label; a column that
    does not cover every wave says its years in the label; collisions resolved by resolve()"""
    items = []
    for base, d in decisions.items():
        multi = len(d["versions"]) > 1
        for col, ws in d["versions"].items():
            lb = d.get("labels_by_wave") or d.get("labels_by_year") or {}
            lab = lb.get(str(ws[-1]), lb.get(ws[-1])) or d.get("reference_label") or ""
            if col in OVERRIDES: text = OVERRIDES[col][1]; stem = OVERRIDES[col][0]
            elif col in stems: text = stems[col][1]; stem = stems[col][0]
            else: text = clean_label(lab, TAG, TRANSLATE_EXTRA); stem = None
            text = re.sub(r"^(19|20)\d\d(\s*-\s*(19|20)\d\d)?[:,]?\s+", "", text)      # the years come from the waves covered
            items.append((col, base, lab, ws, multi, text, stem))
    all_waves = sorted({w for _, _, _, ws, _, _, _ in items for w in ws}, key=str)
    names = []
    for col, base, lab, ws, multi, text, stem in items:
        suf = _suffix(ws, multi, all_waves)
        if stem:
            n = f"{TAG}_{stem}"
            if len(n) > 32: log.warning("override stem too long, cut: %s", n); n = cut(n, 32)
            if suf and not re.search(r"_(19|20)\d\d(_(19|20)\d\d)?$", n): n = versioned(n, suf)          # unless the stem carries its years
        else: n = make_slug(text, TAG, col, 32 - len(suf)) + suf
        names.append(n)
    names = resolve(names, [(col, base, lab, ws, multi, text, bool(stem)) for col, base, lab, ws, multi, text, stem in items], all_waves)
    for (col, base, lab, ws, multi, text, stem), n in zip(items, names):
        years = _years_text(ws) if (multi or set(map(str, ws)) != set(map(str, all_waves))) else None
        table.rows.append({"scope": f"pooled:{fname}", "wave": ",".join(map(str, ws)), "native": col, "clean_name": n,
                           "clean_label": label_with_tag(TAGU, text, years), "native_label": lab})
        if not table.rows[-1]["clean_label"].endswith(text.strip()[-12:]): log.warning("label cut to 80 characters: %s -> %s", col, table.rows[-1]["clean_label"])
    return {col: (base, ws) for col, base, lab, ws, multi, text, stem in items}

def name_wave(scope, wave, vars_, labels, pooled_map):
    """per-wave file: pooled columns take their version's clean name; the rest are named from their own labels"""
    pooled_names = {}
    for col, (base, ws) in pooled_map.items():
        if str(wave) in {str(w) for w in ws}: pooled_names[base] = col
    taken, rows, todo = set(), [], []
    for v in vars_:
        if v in pooled_names:
            r = table.by_scope_pooled[pooled_names[v]]; rows.append({"scope": scope, "wave": wave, "native": v, "clean_name": r["clean_name"], "clean_label": r["clean_label"], "native_label": labels.get(v, "")}); taken.add(r["clean_name"])
        else: todo.append(v)
    if todo:
        gen = assign_names(TAG, [(v, clean_label(labels.get(v, "") or v, TAG, TRANSLATE_EXTRA)) for v in todo])
        for v, n in zip(todo, gen):
            if v in OVERRIDES: n = f"{TAG}_{OVERRIDES[v][0]}"; lab = label_with_tag(TAGU, OVERRIDES[v][1])
            elif v in stems: n = f"{TAG}_{stems[v][0]}"; lab = label_with_tag(TAGU, stems[v][1])
            else: lab = label_with_tag(TAGU, clean_label(labels.get(v, "") or v, TAG, TRANSLATE_EXTRA))
            k = 2
            while n in taken: n = cut(n, 30) + f"_{k}"; k += 1
            taken.add(n); rows.append({"scope": scope, "wave": wave, "native": v, "clean_name": n, "clean_label": lab, "native_label": labels.get(v, "")})
    table.rows += rows

# ---------------------------------------------------------------- LFS: pooled person (versions), pooled household (subset + hhsize/head_*), per-year person files
pooled_map = name_pooled("LFS_pooled_person.dta", align["decisions"], None)
table.by_scope_pooled = {r["native"]: r for r in table.rows}
hh_scope = "pooled:LFS_pooled_household.dta"
for v in align["household"]["vars"]:                     # household-level columns keep the person file's clean names
    if v in table.by_scope_pooled:
        r = table.by_scope_pooled[v]; table.rows.append({**r, "scope": hh_scope})
    elif v in stems:
        table.rows.append({"scope": hh_scope, "wave": "", "native": v, "clean_name": f"{TAG}_{stems[v][0]}", "clean_label": label_with_tag(TAGU, stems[v][1]), "native_label": ""})
    else: log.warning("household column %r has no pooled name; engine name used", v); table.rows.append({"scope": hh_scope, "wave": "", "native": v, "clean_name": make_slug(v, TAG, v), "clean_label": label_with_tag(TAGU, clean_label(v, TAG)), "native_label": ""})
for y, m in metas.items():
    name_wave(f"wave:{y}", y, m["vars"], native_labels(m), pooled_map)

table.save()
n_scopes = len({r["scope"] for r in table.rows})
log.info("variable_names.csv written: %d names in %d files (pooled + per-wave)", len(table.rows), n_scopes)
# review helpers: longest names, abbreviated names, names carrying a native code
import collections
ab = [r for r in table.rows if r["scope"].startswith("pooled") and re.search(r"_(hh|agri|expend|prod|qty|num|estab|employ|educ|info|org|govt|comm|activ|consum|transp|recvd|mo|quest|pop|avg|pct|second|prim|intl|environ|devt|coop|insur|relation|charact|veg|fert|pest|irrig|lvstk|equip|maint|regist|resp|ref|prev|biz|svc|wkrs|wkr|emps|emp)(_|$)", r["clean_name"])]
log.info("pooled names that needed an abbreviation to fit 32 characters: %d", len(ab))
code = [r for r in table.rows if r["scope"].startswith("pooled") and re.search(r"_[a-z]{1,3}\d+[a-z0-9]*$", r["clean_name"]) and not re.search(r"_(19|20)\d\d$", r["clean_name"])]
log.info("pooled names that carry the native code to stay unique: %d (e.g. %s)", len(code), [r["clean_name"] for r in code[:8]])
