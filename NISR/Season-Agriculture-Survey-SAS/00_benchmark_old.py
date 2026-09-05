"""00_benchmark_old.py -- SAS: no processed outputs existed before 2026-09-04; records raw file counts per wave. Idempotent."""
import json, sys
from sas_helpers import paths, read_meta, LOGS
OUT = LOGS / "benchmark_old_stata.json"
if OUT.exists(): print(f"benchmark already recorded at {OUT}"); sys.exit(0)
P = paths(); res = {"source": "no prior outputs; raw NISR files as shipped", "files": []}
for f in sorted(P["raw"].rglob("*.dta")):
    m = read_meta(f); res["files"].append({"file": str(f.relative_to(P["raw"])), "n_rows": int(m.number_rows), "n_vars": len(m.column_names)})
LOGS.mkdir(exist_ok=True); OUT.write_text(json.dumps(res, indent=1)); print("wrote", OUT, len(res["files"]), "files")
