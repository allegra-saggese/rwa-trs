"""00_benchmark_old.py -- AHS: no processed outputs existed before 2026-09-04; records raw file row counts. Idempotent."""
import json, sys
from ahs_helpers import paths, read_meta, LOGS
OUT = LOGS / "benchmark_old_stata.json"
if OUT.exists(): print(f"benchmark already recorded at {OUT}"); sys.exit(0)
P = paths(); res = {"source": "no prior outputs; raw NISR files as shipped", "files": []}
for y in ("2017", "2020", "2024"):
    for f in sorted((P["raw"] / y).glob("*.dta")):
        m = read_meta(f); res["files"].append({"file": f.name, "year": int(y), "n_rows": int(m.number_rows), "n_vars": len(m.column_names)})
LOGS.mkdir(exist_ok=True); OUT.write_text(json.dumps(res, indent=1)); print("wrote", OUT)
