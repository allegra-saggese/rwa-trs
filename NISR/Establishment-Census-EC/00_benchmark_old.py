"""
00_benchmark_old.py -- EC: no pre-existing processed outputs existed for the Establishment
Census (2_Intermediate/ and 3_Final/ were empty on 2026-09-04). Records that fact plus the
raw-file row counts so later runs can be compared against the shipped files. Idempotent.
"""
import json, sys
from ec_helpers import paths, read_meta, LOGS
OUT = LOGS / "benchmark_old_stata.json"
if OUT.exists(): print(f"benchmark already recorded at {OUT}"); sys.exit(0)
P = paths(); res = {"source": "no prior outputs; raw NISR files as shipped", "files": []}
for y, fn in [(2011, "EC_2011.sav"), (2014, "EC_2014.sav"), (2017, "EC_2017.sav"), (2020, "EC_2020.dta"), (2023, "EC_2023.dta")]:
    m = read_meta(P["raw"] / str(y) / fn); res["files"].append({"file": fn, "year": y, "n_rows": int(m.number_rows), "n_vars": len(m.column_names)})
LOGS.mkdir(exist_ok=True); OUT.write_text(json.dumps(res, indent=1)); print("wrote", OUT)
