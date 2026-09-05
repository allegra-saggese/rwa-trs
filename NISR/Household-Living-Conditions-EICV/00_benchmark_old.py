"""
00_benchmark_old.py -- EICV: record check statistics from the OLD Stata-built outputs
(3 Jul 2026) before they are overwritten by the Python pipeline. Runs once (idempotent).
"""
import json, sys
from eicv_helpers import paths, read_dta, read_meta, LOGS

OUT = LOGS / "benchmark_old_stata.json"
if OUT.exists():
    print(f"benchmark already recorded at {OUT}; not recomputing"); sys.exit(0)
P = paths()

def stats(path):
    m = read_meta(path)
    cols = [c for c in ["year", "round", "wt", "sex", "age", "prov", "district", "hhid"] if c in m.column_names]
    df, _, _ = read_dta(path, usecols=cols)
    out = {"file": path.name, "n_rows": int(m.number_rows), "n_vars": len(m.column_names), "by_round": {}}
    key = "round" if "round" in df else ("year" if "year" in df else None)
    groups = df.groupby(key) if key else [("all", df)]
    for k, g in groups:
        r = {"n": int(len(g))}
        if "wt" in g: r["sum_wt"] = float(g["wt"].sum()); r["miss_wt"] = int(g["wt"].isna().sum())
        if "sex" in g: r["sex_counts"] = {str(v): int(c) for v, c in g["sex"].value_counts().items()}
        if "hhid" in g: r["n_hh"] = int(g["hhid"].nunique())
        if "district" in g: r["n_district"] = int(g["district"].nunique())
        out["by_round"][str(k)] = r
    return out

res = {"source": "old Stata outputs built 3 Jul 2026 (clean.do/merge.do, archived in _archive/code-NISR-stata-2026-09-04)", "files": []}
for name in ["2_Intermediate/EICV3_clean.dta", "2_Intermediate/EICV4_CS_clean.dta", "2_Intermediate/EICV4_VUP_clean.dta",
             "2_Intermediate/EICV5_CS_clean.dta", "2_Intermediate/EICV5_VUP_clean.dta", "2_Intermediate/EICV7_CS_clean.dta",
             "2_Intermediate/EICV7_VUP_clean.dta", "3_Final/EICV_pooled_crosssection.dta", "3_Final/EICV3_4_panel.dta"]:
    p = P["root"] / name
    if p.exists(): res["files"].append(stats(p)); print("done", p.name)
LOGS.mkdir(exist_ok=True); OUT.write_text(json.dumps(res, indent=1)); print("wrote", OUT)
