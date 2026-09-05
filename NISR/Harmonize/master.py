"""master.py -- NISR/Harmonize: run 01 -> 03 top to bottom; stops at the first failure.
usage: python master.py [01|02|03 ...]   (default: all)"""
import os, subprocess, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
steps = {"01": "01_harmonize.py", "02": "02_checks.py", "03": "03_codebook.py"}
want = sys.argv[1:] or list(steps)
os.environ["NISR_RUN_ID"] = os.environ.get("NISR_RUN_ID") or time.strftime("%Y%m%d-%H%M%S")
for k in want:
    print(f"\n{'=' * 78}\n>>> {steps[k]}\n{'=' * 78}", flush=True)
    r = subprocess.run([sys.executable, str(HERE / steps[k])], cwd=str(HERE))
    if r.returncode: sys.exit(f"{steps[k]} failed (rc={r.returncode}); see logs/")
print("\nmaster: all steps done")
