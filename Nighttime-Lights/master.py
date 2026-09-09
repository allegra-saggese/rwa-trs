"""
master.py -- run the whole nightlights pipeline.

    python master.py            every step
    python master.py 02 03      only those steps

01_download  global annual composites -> Rwanda cut-outs in geo-data/nightlights/, plus the manifest
02_zonal     cut-outs -> area-weighted statistics per sector and per cell, in 2_Intermediate/
03_merge     -> the two pooled panels in 3_Final/, as .dta and .csv
04_checks    -> logs/checks_report.txt
05_codebook  -> CODEBOOK_Nightlights.xlsx, README.txt and the citations file

Step 01 is the slow one: it downloads roughly 4 GB and expands a 10 GB raster per year for the Chen
product. It skips any year whose cut-out already exists, so it is safe to interrupt and restart.
"""
import runpy
import sys
import time
from pathlib import Path

STEPS = ["01_download", "02_zonal", "03_merge", "04_checks", "05_codebook"]
HERE = Path(__file__).resolve().parent


def main():
    want = [a for a in sys.argv[1:] if not a.startswith("-")]
    steps = [s for s in STEPS if not want or any(s.startswith(w) or w in s for w in want)]
    if not steps:
        raise SystemExit(f"nothing matched; steps are {STEPS}")
    sys.path.insert(0, str(HERE))
    for s in steps:
        print(f"\n{'=' * 80}\n{s}\n{'=' * 80}")
        t0 = time.time()
        sys.argv = [s]
        try:
            runpy.run_path(str(HERE / f"{s}.py"), run_name="__main__")
        except SystemExit as e:
            if e.code:
                raise SystemExit(f"{s} exited with code {e.code}")
        print(f"-- {s} done in {time.time() - t0:.0f}s")
    print("\nall steps complete")


if __name__ == "__main__":
    main()
