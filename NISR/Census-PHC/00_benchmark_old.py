"""
00_benchmark_old.py -- Census: record check statistics from the OLD Stata-built outputs
(3 Jul 2026) before they are overwritten by the Python pipeline. Runs once (idempotent).
"""
import json, sys
from census_helpers import paths, read_dta, read_meta, LOGS

OUT = LOGS / "benchmark_old_stata.json"
if OUT.exists():
    print(f"benchmark already recorded at {OUT}; not recomputing"); sys.exit(0)
P = paths()

def stats(path):
    m = read_meta(path)
    cols = [c for c in ["year", "wt", "wt_hh", "sex", "age", "prov", "dist", "sector", "urban", "hhid"] if c in m.column_names]
    df, _, _ = read_dta(path, usecols=cols)
    out = {"file": path.name, "n_rows": int(m.number_rows), "n_vars": len(m.column_names), "by_year": {}}
    for y, g in df.groupby("year"):
        r = {"n": int(len(g)), "sum_wt": float(g["wt"].sum()), "miss_wt": int(g["wt"].isna().sum())}
        if "wt_hh" in g: r["sum_wt_hh"] = float(g["wt_hh"].sum())
        for k in ("prov", "dist", "sector"):
            if k in g: r[f"n_{k}"] = int(g[k].nunique())
        if "sex" in g: r["sex_counts"] = {str(int(k)): int(v) for k, v in g["sex"].value_counts().items()}
        if "age" in g: r["age_min"], r["age_max"] = float(g["age"].min()), float(g["age"].max())
        if "hhid" in g: r["n_hh"] = int(g["hhid"].nunique())
        out["by_year"][str(int(y))] = r
    return out

res = {"source": "old Stata outputs built 3 Jul 2026 (clean.do/merge.do, archived in _archive/code-NISR-stata-2026-09-04)", "files": []}
for name in ["2_Intermediate/Census_2012_clean.dta", "2_Intermediate/Census_2022_clean.dta", "3_Final/Census_panel_2012_2022.dta"]:
    p = P["root"] / name
    if p.exists(): res["files"].append(stats(p)); print("done", p.name)
LOGS.mkdir(exist_ok=True); OUT.write_text(json.dumps(res, indent=1)); print("wrote", OUT)
