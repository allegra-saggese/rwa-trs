"""Figures and maps for the STEG grant appendix, all from public data.

Run every section in order:   python results-scripts/STEG_figures_script.py
Run some sections:            python results-scripts/STEG_figures_script.py --only <name> [<name> ...]
List the sections:            python results-scripts/STEG_figures_script.py --list

Each section runs one module of results-scripts/STEG/, exactly as `python <module>.py` would.
The nightlights-near-gates figure of the same appendix is in Nighttime-Lights/analysis/steg_ntl_gates.py.
Outputs go to Dropbox output/figures/ and output/maps/.

Sections, in run order:
  services_establishments_map   results-scripts/STEG/steg_ec_maps.py               services establishments per 1,000 residents by sector, 2014
  census_change_maps            results-scripts/STEG/steg_census_change_maps.py    agriculture and services shares, change 2002-2022
  employment_series             results-scripts/STEG/steg_employment_series.py     structural transformation and tourism jobs, 2001-2025
  forest_cover_series           results-scripts/STEG/steg_forest_jrc.py            tropical moist forest in and outside parks, 1995-2024 (reads JRC rasters online)
  crop_productivity_map         results-scripts/STEG/steg_sas_productivity_map.py  crop output per hectare by district, 2025
  tourism_series                results-scripts/STEG/steg_tourism_series.py        visitors and tourism revenue, RDB
"""
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent / "STEG"
sys.path.insert(0, str(HERE))

SECTIONS = {
    "services_establishments_map": "steg_ec_maps",
    "census_change_maps": "steg_census_change_maps",
    "employment_series": "steg_employment_series",
    "forest_cover_series": "steg_forest_jrc",
    "crop_productivity_map": "steg_sas_productivity_map",
    "tourism_series": "steg_tourism_series",
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
