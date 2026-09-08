"""
master.py -- NISR: the master of masters. Runs the whole public-data pipeline top to bottom.

    python master.py                     # the seven datasets, then the harmonisation step
    python master.py EC LFS              # only those datasets (Harmonize is skipped unless asked for)
    python master.py Harmonize           # only the harmonisation step
    python master.py --from EICV         # from that dataset onwards (the order below)

Each dataset folder has its own master.py (00 benchmark -> 01 clean -> 02 merge -> 03 checks -> 04 codebook);
NISR/Harmonize/master.py then writes the harmonised copies (01), verifies them (02) and rebuilds the
cross-dataset codebook (03). Every step reads the raw files on Dropbox and writes 2_Intermediate, 3_Final and
4_Harmonized there; nothing in 1_Raw is ever touched. The run stops at the first failure and says which step
failed. One NISR_RUN_ID is shared by every step, so a whole run is one timestamp across all the logs/ folders.

The variable names and labels are NOT rebuilt here: `variable_names.csv` is committed next to each dataset's
code and is applied as it stands (rebuild it deliberately with `python master.py names` inside a dataset
folder, review the table, commit it, then rerun the pipeline).
"""
import os, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORDER = ["Establishment-Census-EC", "Labour-Force-Survey-LFS", "Census-PHC", "Household-Living-Conditions-EICV",
         "Agriculture-Survey-AHS", "Season-Agriculture-Survey-SAS", "Food-Security-CFSVAN", "Harmonize"]
ALIAS = {"EC": "Establishment-Census-EC", "LFS": "Labour-Force-Survey-LFS", "Census": "Census-PHC",
         "EICV": "Household-Living-Conditions-EICV", "AHS": "Agriculture-Survey-AHS",
         "SAS": "Season-Agriculture-Survey-SAS", "CFSVA": "Food-Security-CFSVAN", "Harmonize": "Harmonize"}

args = sys.argv[1:]
if args and args[0] == "--from":
    if len(args) < 2: sys.exit("usage: python master.py --from <dataset>")
    start = ALIAS.get(args[1], args[1])
    if start not in ORDER: sys.exit(f"unknown dataset {args[1]!r}; known: {', '.join(ALIAS)}")
    want = ORDER[ORDER.index(start):]
elif args:
    want = []
    for a in args:
        name = ALIAS.get(a, a)
        if name not in ORDER: sys.exit(f"unknown dataset {a!r}; known: {', '.join(ALIAS)}")
        want.append(name)
else:
    want = list(ORDER)

os.environ.setdefault("NISR_RUN_ID", time.strftime("%Y%m%d-%H%M%S"))
print(f"NISR pipeline: {len(want)} step(s) -- {', '.join(want)}\nrun id {os.environ['NISR_RUN_ID']}", flush=True)
t0 = time.time()
done = []
for name in want:
    folder = HERE / name
    if not (folder / "master.py").is_file(): sys.exit(f"{name}: no master.py in {folder}")
    print(f"\n{'#' * 78}\n### {name}\n{'#' * 78}", flush=True)
    t1 = time.time()
    r = subprocess.run([sys.executable, "master.py"], cwd=str(folder))
    if r.returncode:
        print("\n".join(f"  done: {d}" for d in done), flush=True)
        sys.exit(f"{name} failed (rc={r.returncode}) after {time.time() - t0:.0f}s -- see {name}/logs/run_{os.environ['NISR_RUN_ID']}.log")
    done.append(f"{name} ({time.time() - t1:.0f}s)")
print(f"\n{'#' * 78}\nNISR pipeline complete in {time.time() - t0:.0f}s: " + ", ".join(done))
print(f"logs: <dataset>/logs/run_{os.environ['NISR_RUN_ID']}.log")
