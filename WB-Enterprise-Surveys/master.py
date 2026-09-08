"""
master.py -- WBES: run the whole pipeline top to bottom.

    python master.py            # all steps
    python master.py 01 02      # selected steps

Steps: 01 clean (one file per round) -> 02 merge (the pooled establishment file) -> 03 checks -> 04 codebook.
    python master.py names      # rebuild variable_names.csv from the last run's logs (00_names.py); review, commit, rerun
All steps of one run log to the same logs/run_<timestamp>.log. Stops at the first failure.
Set WBES_DB_ROOT to override the Dropbox data root (otherwise resolved from the login user).
"""
import os, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
STEPS = {"01": "01_clean.py", "02": "02_merge.py", "03": "03_checks.py", "04": "04_codebook.py", "names": "00_names.py"}
want = sys.argv[1:] or [s for s in STEPS if s != "names"]
os.environ.setdefault("WBES_RUN_ID", time.strftime("%Y%m%d-%H%M%S"))
t0 = time.time()
for s in want:
    print(f"\n{'=' * 78}\n>>> {STEPS[s]}\n{'=' * 78}", flush=True)
    r = subprocess.run([sys.executable, str(HERE / STEPS[s])], cwd=str(HERE))
    if r.returncode:
        sys.exit(f"{STEPS[s]} failed (rc={r.returncode}) after {time.time() - t0:.0f}s -- see logs/run_{os.environ['WBES_RUN_ID']}.log")
print(f"\nWBES pipeline complete in {time.time() - t0:.0f}s; log: logs/run_{os.environ['WBES_RUN_ID']}.log")
