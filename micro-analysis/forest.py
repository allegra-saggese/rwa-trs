"""Forest-loss analysis around the national parks.

Run every section in order:   python micro-analysis/forest.py
Run some sections:            python micro-analysis/forest.py --only <name> [<name> ...]
List the sections:            python micro-analysis/forest.py --list

Each section runs one module of micro-analysis/forest/, exactly as `python <module>.py` would.
Sector-year Hansen tree-cover loss outside parks is built in micro-analysis/sector_panel.py (section
forest_outcomes). Results go to output/tables/regressions/ and analysis/; figures to output/figures/.

Sections, in run order:
  event_study_5km   micro-analysis/forest/forest_event_study_5km.py  annual forest-loss event study, 1-km grid, 5-km matched sample (reads JRC rasters online)
  coefplot_5km      micro-analysis/forest/coefplot_forest_5km.py     coefficient plot of the 5-km matched DiD (estimates typed into the script)
  jrc_did           micro-analysis/forest/coefplot_jrc_forest.py     JRC forest-loss DiD by park, excluding Akagera (reads JRC rasters online)
"""
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent / "forest"
sys.path.insert(0, str(HERE))

SECTIONS = {
    "event_study_5km": "forest_event_study_5km",
    "coefplot_5km": "coefplot_forest_5km",
    "jrc_did": "coefplot_jrc_forest",
}


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", nargs="+", choices=list(SECTIONS), help="run only these sections, in run order")
    ap.add_argument("--list", action="store_true", help="list the sections and exit")
    a = ap.parse_args(argv)
    if a.list:
        print("\n".join(SECTIONS)); return
    for name, module in SECTIONS.items():
        if a.only and name not in a.only:
            continue
        print(f"\n==== {name}  ({module}.py)", flush=True)
        path = HERE / f"{module}.py"
        saved = sys.argv[:]
        sys.argv = [str(path)]          # modules that read arguments see none, as when run on their own
        try:
            runpy.run_path(str(path), run_name="__main__")
        finally:
            sys.argv = saved


if __name__ == "__main__":
    main()
