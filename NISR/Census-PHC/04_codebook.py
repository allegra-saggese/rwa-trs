"""
04_codebook.py -- Census: generate CODEBOOK_Census.xlsx, the dataset's only codebook, in the Dropbox dataset folder next to README.txt.

For every variable in each 3_Final file: label, storage type, value labels (first few),
non-missing count per year, the raw source variable per year (key block), and the
alignment decision + label variants recorded by 02_merge.py.
"""
import json, re, time
import numpy as np, pandas as pd
from census_helpers import paths, get_logger, read_dta, read_meta, LOGS, HERE, DATASET

TAG = "Census"
log = get_logger("04_codebook")
P = paths()
align = json.load(open(LOGS / "merge_alignment.json"))
metas = {y: json.load(open(LOGS / f"clean_{y}_meta.json")) for y in (2002, 2012, 2022)}
srcs = {y: m["source"] for y, m in metas.items()}
orig = metas[2002].get("var_labels_original", {})
univ = {y: m.get("universe", {}) for y, m in metas.items()}

def chunked_counts(path, key, chunk=250_000):
    """non-missing counts per column by `key` (wave/year), reading the file in row chunks so
    multi-GB pooled files never sit in memory whole; returns (counts DataFrame, ordered key values, n rows)."""
    m = read_meta(path); counts, order = None, []
    for off in range(0, m.number_rows, chunk):
        part, _, _ = read_dta(path, row_offset=off, row_limit=chunk)
        if key not in part.columns: part[key] = "all"
        c = part.groupby(key, sort=False).count(); c[key] = part.groupby(key, sort=False).size()   # the key itself: group size
        counts = c if counts is None else counts.add(c, fill_value=0)
        order += [k for k in part[key].unique().tolist() if k not in order]
    return counts.reindex(order).fillna(0).astype(int), order, int(m.number_rows)


FILE_UNIVERSE = {"Census_pooled_person.dta": "persons in private households (NISR public-use samples; weights sum to the private-household population); who was asked each item is in the universe column",
                 "Census_pooled_household.dta": "private households (NISR public-use samples)"}

def sheet_name(fname, used):
    """Excel sheet name for a file: the stem without the <TAG>_pooled_ prefix, <= 31 chars, unique."""
    s = fname[:-4] if fname.endswith(".dta") else fname
    for pre in (f"{TAG}_pooled_", f"{TAG}_"):
        if s.startswith(pre): s = s[len(pre):]; break
    s = re.sub(r"[\[\]:*?/\\]", "_", s)[:31] or "sheet"
    base, i = s, 2
    while s in used: s = f"{base[:28]}_{i}"; i += 1
    used.add(s); return s


def write_workbook(path, notes, books):
    """One workbook per dataset (its only codebook, next to README.txt on Dropbox): README (notes), files
    (overview), ONE SHEET PER FINAL DATASET (variable table), modules (every appended module file of
    2_Intermediate/appended/ stacked in one sheet, file in the first column), value_labels (every code of
    every labelled variable, all files) and checks (the latest logs/checks_report.txt)."""
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter
    used = {"README", "files", "modules", "value_labels", "checks"}
    finals = [(cb, m) for cb, m, _ in books if m["folder"] == "3_Final"]
    mods = [(cb, m) for cb, m, _ in books if m["folder"] != "3_Final"]
    names = {m["file"]: sheet_name(m["file"], used) for _, m in finals}
    names.update({m["file"]: "modules" for _, m in mods})
    files = pd.DataFrame([dict(m, sheet=names[m["file"]]) for _, m, _ in books])
    vls = pd.DataFrame([r for _, _, v in books for r in v], columns=["file", "variable", "code", "label"])
    report = LOGS / "checks_report.txt"
    checks = pd.DataFrame({"checks_report": report.read_text().splitlines() if report.exists() else ["(no logs/checks_report.txt yet: run 03_checks.py)"]})
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        pd.DataFrame({"README": notes}).to_excel(xw, sheet_name="README", index=False)
        files.to_excel(xw, sheet_name="files", index=False)
        for cb, m in finals: cb.to_excel(xw, sheet_name=names[m["file"]], index=False)
        if mods:
            stack = pd.concat([cb.assign(file=m["file"]) for cb, m in mods], ignore_index=True, sort=False)
            lead = [c for c in ("file", "variable", "label", "type", "value_labels", "n_value_labels", "universe") if c in stack.columns]
            ncols = sorted(c for c in stack.columns if c.startswith("n_") and c not in lead)
            stack = stack[lead + ncols + [c for c in stack.columns if c not in lead + ncols]]
            stack.to_excel(xw, sheet_name="modules", index=False)
        vls.to_excel(xw, sheet_name="value_labels", index=False)
        checks.to_excel(xw, sheet_name="checks", index=False)
        for ws in xw.book.worksheets:
            ws.freeze_panes = "A2"
            for cell in ws[1]: cell.font = Font(bold=True)
            for j, col in enumerate(ws.iter_cols(min_row=1, max_row=min(ws.max_row, 300)), start=1):
                w = max((len(str(c.value)) for c in col if c.value is not None), default=8)
                ws.column_dimensions[get_column_letter(j)].width = min(max(10, w + 2), 80)
    log.info("wrote %s (%d final-dataset sheets, %d module files in one sheet, %d value-label rows)", path, len(finals), len(mods), len(vls))

def codebook(fname, unit):
    df, vl, vv = read_dta(P["final"] / fname, row_limit=1)          # one row: columns and dtypes only
    m = read_meta(P["final"] / fname)
    types = m.readstat_variable_types
    nn, years, nrows = chunked_counts(P["final"] / fname, "year")
    rows = []
    for c in df.columns:
        base = c.rsplit("_v", 1)[0] if ("_v" in c and c.rsplit("_v", 1)[-1].isdigit()) else c
        d = align["decisions"].get(base) or {}
        vers = d.get("versions") or {}
        ys_here = vers.get(c, [])
        labs = {y: l for y, l in (d.get("labels_by_year") or {}).items() if int(y) in ys_here}
        variants = "; ".join(f"{y}: {l[:60]}" for y, l in labs.items() if l and l != d.get("reference_label")) if len(set(labs.values())) > 1 else ""
        other_versions = ", ".join(f"{n} ({ys[0]}–{ys[-1]})" for n, ys in vers.items() if n != c) if len(vers) > 1 else ""
        src = "; ".join(f"{y}: {s.get(c, s.get(base))}" for y, s in srcs.items() if (c in s or base in s) and (not ys_here or int(y) in ys_here))
        if c in orig and orig[c] and orig[c] != (vl.get(c) or ""): src = (src + "; " if src else "") + f"2002 original label (FR): {orig[c][:60]}"
        vlab = vv.get(c, {})
        vtxt = ", ".join(f"{k}={v}" for k, v in list(vlab.items())[:6]) + (" …" if len(vlab) > 6 else "")
        conf = align["value_label_conflicts"].get(c)
        yrs = ys_here if ys_here else list(univ)              # versioned columns: only the years of this version, under the base name
        uni = {y: univ[y][base] for y in yrs if y in univ and base in univ[y]}
        utxt = ("; ".join(f"{y}: {t}" for y, t in uni.items()) if len(set(uni.values())) > 1 else next(iter(uni.values()), "")) if uni else ""
        rows.append({"variable": c, "label": vl.get(c) or "", "type": types.get(c, str(df[c].dtype)),
                     "value_labels": vtxt, "n_value_labels": len(vlab), "universe": utxt,
                     **{f"n_{y}": int(nn.loc[y, c]) if c in nn.columns else 0 for y in years},
                     "source_by_year": src, "version_years": ",".join(map(str, ys_here)) if len(vers) > 1 else "",
                     "other_versions": other_versions,
                     "label_variants": variants, "value_label_conflicts": json.dumps(conf) if conf else ""})
    vl_rows = [{"file": fname, "variable": c, "code": k, "label": v} for c in df.columns for k, v in vv.get(c, {}).items()]
    return pd.DataFrame(rows), {"file": fname, "folder": "3_Final", "unit": unit, "rows": nrows, "variables": df.shape[1],
                                "years": ", ".join(map(str, years)), "universe": FILE_UNIVERSE.get(fname, "")}, vl_rows

NOTES = [f"Census codebook -- generated by rwa-trs/NISR/{DATASET}/04_codebook.py on {time.strftime('%Y-%m-%d %H:%M')} from 3_Final/ (and 2_Intermediate/appended/). Do not hand-edit: re-run python master.py 04.",
         "Sheets: files = one row per final/appended file (folder, unit, rows, variables, years, universe, sheet); one sheet per FINAL dataset = one row per variable (label, storage type, first value labels, number of value labels, universe, non-missing count per year, source variable per year, versions, label variants, value-label text conflicts); modules = the same table for every appended module file of 2_Intermediate/appended/, stacked, file in the first column; value_labels = every code of every labelled variable (all files); checks = the latest verification report (logs/checks_report.txt).",
         'Key block (identical names in every NISR dataset): survey year wave prov dist sector urban cluster hhid pid sex age wt wt_hh.',
         f"Alignment rule: years are grouped into versions of a variable by label similarity (token Jaccard >= {align['threshold']}); the largest group keeps the name, the others are <name>_v2, _v3 ...; forced alignments: {', '.join(sorted(align.get('force_align', []))) or 'none'}; forced splits: {', '.join(f'{k} ({v})' for k, v in (align.get('force_split') or {}).items()) or 'none'}.",
         "Value labels are the union over years within a version; where the same code had different text the most recent year's text is kept and the conflict listed.",
         "universe = who was asked, from the questionnaires; per variable and year in the universe column of each sheet; out-of-universe rows carry NISR's not-applicable code or are missing.",
         f"Processing notes (what z_Documentation says and how it was applied; every decision and why) are kept in the project memory file NISR-{DATASET}.md (Green Jobs - TRS folder), not in git or Dropbox."]
books = [codebook("Census_pooled_person.dta", "person"), codebook("Census_pooled_household.dta", "household")]
write_workbook(P["root"] / f"CODEBOOK_{TAG}.xlsx", NOTES, books)

# ---------------------------------------------------------------- README.txt on Dropbox
# The dataset folder's README.txt keeps its hand-written sections; the block between the two
# marker lines below is regenerated from 3_Final/ and 2_Intermediate/ on every run, and the
# pre-pipeline sentences that are now stale are replaced by a pointer to the git folder.
def update_readme():
    import re, time
    from pathlib import Path
    readme = P["root"] / "README.txt"
    if not readme.exists(): log.warning("no README.txt in %s; skipped", P["root"]); return
    start, end = "=== PROCESSED OUTPUTS (generated by 04_codebook.py; do not edit inside) ===", "=== END PROCESSED OUTPUTS ==="
    finals = sorted(P["final"].glob("*.dta")); inters = sorted(P["inter"].glob("*.dta"))
    lines = [start, f"Pipeline: rwa-trs/NISR/{DATASET}/  (python master.py)   last run: {time.strftime('%Y-%m-%d %H:%M')}",
             f"Codebook: CODEBOOK_{TAG}.xlsx in this folder (sheets: README, files, one per final dataset, modules, value_labels, checks).",
             f"Code and run logs: git repository rwa-trs/NISR/{DATASET}/. Processing notes (what z_Documentation says and how it was applied; every decision and why): project memory file NISR-{DATASET}.md (Green Jobs - TRS folder, outside git and Dropbox).", "",
             f"3_Final/  ({len(finals)} files)"]
    for f in finals:
        try:
            m = read_meta(f); lines.append(f"  {f.name:55s} {m.number_rows:>10,} rows x {len(m.column_names):>4} vars   {m.file_label or ''}")
        except Exception as e: lines.append(f"  {f.name:55s} (unreadable: {e})")
    app = sorted((P["inter"] / "appended").glob("*.dta")) if (P["inter"] / "appended").exists() else []
    lines += ["", f"2_Intermediate/  ({len(inters)} files: one cleaned file per wave and unit/module; see CODEBOOK_{TAG}.xlsx)"]
    if app:
        lines.append(f"2_Intermediate/appended/  ({len(app)} module-level files appended across waves)")
        for f in app:
            try: m = read_meta(f); lines.append(f"  {f.name:55s} {m.number_rows:>10,} rows x {len(m.column_names):>4} vars")
            except Exception as e: lines.append(f"  {f.name:55s} (unreadable: {e})")
    lines.append(end)
    txt = readme.read_text(encoding="utf-8", errors="replace")
    for stale in ["2_Intermediate/ and 3_Final/ are empty: no clean.do / merge.do written for\nthis survey yet. The Census, EICV and LFS folders have working examples.",
                  "2_Intermediate/  0 files (not built yet)", "3_Final/         0 files (not built yet)"]:
        txt = txt.replace(stale, "Processed by the Python pipeline in rwa-trs/NISR/ (see the PROCESSED OUTPUTS block).")
    txt = re.sub(r"Code lives in code/Publicly Available Data - NISR/ and was repointed to these\npaths on the same date \(previous paths under \"Rwanda - Tourism, Green Jobs/\nData/Public\" were already stale\).",
                 "Code now lives in the git repository rwa-trs/NISR/<dataset>/ (Python); the Stata\ndo-files are archived in Rwanda - TRS/_archive/code-NISR-stata-2026-09-04/.", txt)
    new_block = "\n".join(lines)
    if start in txt and end in txt:
        txt = txt[:txt.index(start)] + new_block + txt[txt.index(end) + len(end):]
    else:
        head_end = txt.find("\n\n") + 2 if "\n\n" in txt[:600] else 0
        txt = txt[:head_end] + new_block + "\n\n" + txt[head_end:]
    readme.write_text(txt, encoding="utf-8"); log.info("README.txt updated (%s)", readme)

update_readme()
