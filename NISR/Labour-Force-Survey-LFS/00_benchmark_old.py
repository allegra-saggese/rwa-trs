"""
00_benchmark_old.py -- LFS: record check statistics from the OLD Stata-built outputs
(3 Jul 2026) before they are overwritten by the Python pipeline.

Runs once. If logs/benchmark_old_stata.json already exists it does nothing, so the
benchmark can never be recomputed from the new outputs by mistake.
"""
import json, os, sys, getpass
from pathlib import Path
import pandas as pd, pyreadstat

HERE = Path(__file__).resolve().parent
OUT = HERE / "logs" / "benchmark_old_stata.json"
ROOTS = {
    "matteo": "/Users/matteo/Library/CloudStorage/Dropbox/1-Ongoing Projects/Rwanda - TRS/data/Publicly-Available-NISR",
    "allegrasaggese": "/Users/allegrasaggese/Library/CloudStorage/Dropbox/Rwanda - TRS/data/Publicly-Available-NISR",
}
DB = Path(os.environ.get("NISR_DB_ROOT") or ROOTS[getpass.getuser()]) / "Labour-Force-Survey-LFS"

def read_dta_any(path, **kw):
    """pyreadstat with a latin1 fallback: several NISR files carry non-UTF-8 labels."""
    try:
        return pyreadstat.read_dta(str(path), **kw)
    except UnicodeDecodeError:
        return pyreadstat.read_dta(str(path), encoding="latin1", **kw)

def stats(path, cols):
    _, m = read_dta_any(path, metadataonly=True)
    df, _ = read_dta_any(path, usecols=[c for c in cols if c in m.column_names])
    out = {"file": path.name, "n_rows": int(m.number_rows), "n_vars": len(m.column_names),
           "file_date": m.file_label if hasattr(m, "file_label") else None}
    by = "year" if "year" in df else None
    def agg(g):
        r = {"n": int(len(g))}
        if "wt_annual" in g: r["sum_wt_annual"] = float(g["wt_annual"].sum()); r["miss_wt_annual"] = int(g["wt_annual"].isna().sum())
        if "wt_round" in g: r["sum_wt_round"] = float(g["wt_round"].sum())
        if "wap16" in g and "wt_annual" in g: r["wpop_wap16"] = float((g["wap16"] * g["wt_annual"]).sum())
        if "dist" in g: r["n_dist"] = int(g["dist"].nunique())
        if "A01" in g: r["A01_counts"] = {str(k): int(v) for k, v in g["A01"].value_counts(dropna=False).items()}
        if "A04" in g: r["age_min"] = float(g["A04"].min()); r["age_max"] = float(g["A04"].max())
        return r
    if by: out["by_year"] = {str(int(y)): agg(g) for y, g in df.groupby(by)}
    else: out["all"] = agg(df)
    return out

if OUT.exists():
    print(f"benchmark already recorded at {OUT}; not recomputing"); sys.exit(0)
cols = ["year", "wt_annual", "wt_round", "wap16", "dist", "A01", "A04"]
res = {"source": "old Stata outputs built 3 Jul 2026 (clean.do/merge.do, archived in _archive/code-NISR-stata-2026-09-04)", "files": []}
for y in range(2017, 2026):
    p = DB / "2_Intermediate" / f"LFS_{y}_clean.dta"
    if p.exists(): res["files"].append(stats(p, cols)); print("done", p.name)
p = DB / "3_Final" / "LFS_panel_2017_2025.dta"
if p.exists(): res["files"].append(stats(p, cols)); print("done", p.name)
OUT.parent.mkdir(exist_ok=True)
OUT.write_text(json.dumps(res, indent=1))
print("wrote", OUT)
