"""Census analysis: sector panels from the 2002, 2012 and 2022 censuses, the housing, education and
jobs regressions, and the cohort-exposure designs for education and marriage.

Run every section in order:   python micro-analysis/census.py
Run some sections:            python micro-analysis/census.py --only <name> [<name> ...]
List the sections:            python micro-analysis/census.py --list

Each section runs one module of micro-analysis/census/, exactly as `python <module>.py` would. The
modules import one another (bar_chart_housing holds the geography and panel functions the others use),
so they stay separate files; this runner is the single entry point and fixes the order.

Sections, in run order:
  controls               census/build_controls.py         2002 sector controls the lasso chooses from
  housing                census/bar_chart_housing.py      housing panel + descriptive bar chart
  education              census/bar_chart_education.py    education panel + descriptive bar chart
  jobs_panel             census/build_jobs_panel.py       workers by broad sector, sector x wave
  housing_regressions    census/coefplot_housing.py       housing ANCOVA
  housing_lasso          census/coefplot_housing_lasso.py housing ANCOVA, PDS-lasso controls
  housing_inference      census/housing_inference.py      housing result under spatial inference
  education_regressions  census/coefplot_education.py     education ANCOVA
  education_lasso        census/coefplot_education_lasso.py education ANCOVA, PDS-lasso controls
  jobs_regressions       census/coefplot_jobs.py          three-sector employment
  cohort_education       census/cohort_education.py       cohort exposure design, education
  cohort_marriage        census/cohort_marriage.py        cohort exposure design, marriage timing

Writes panels to data/harmonized/ (census_sector_*.csv), regression results to analysis/, figures to
output/figures/. Inputs: the Census pooled files and data/geo-data/.
"""
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent / "census"
sys.path.insert(0, str(HERE))

SECTIONS = {
    "controls": "build_controls",
    "housing": "bar_chart_housing",
    "education": "bar_chart_education",
    "jobs_panel": "build_jobs_panel",
    "housing_regressions": "coefplot_housing",
    "housing_lasso": "coefplot_housing_lasso",
    "housing_inference": "housing_inference",
    "education_regressions": "coefplot_education",
    "education_lasso": "coefplot_education_lasso",
    "jobs_regressions": "coefplot_jobs",
    "cohort_education": "cohort_education",
    "cohort_marriage": "cohort_marriage",
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
