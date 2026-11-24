"""
district_ag_labour_regressions.py -- farm output, crop mix and employment status in districts exposed to park tourism.

Unit: district x year (or round); the 27 districts outside Kigali City. Exposure E_d = share of the district's
population living in park-adjacent sectors (district-park-exposure-border.csv; 62-sector border flag); E_pd is the same
share for sectors whose nearest park is p (Volcanoes, Akagera, Nyungwe, Gishwati-Mukura). Standard errors clustered by
district, wild cluster restricted bootstrap p-values (helpers/regression.py::fe_ols). Province = first digit of the
district code. Descriptive; with 14 exposed districts (3-5 per park) the per-park terms are leads, not estimates.

Sections (python micro-analysis/district_ag_labour_regressions.py --list)
  ag      district-ag-productivity.csv, 2019-2025 (agricultural survey output, 189 district-years; output per worker
          needs ag_workers, missing in 2019, 162). Outcomes: log crop value per ha and log output per worker (2019
          RWF-deflated, `_dprice`), and the area shares in bananas, export crops, horticulture and staples (pp).
            cross   y_dt = g_t + h_province + b E_d             (exposure measured in 2022; no pre-period, so a level
                                                                 difference, not a change)
            park    y_dt = g_t + h_province + sum_p b_p E_pd
            trend   y_dt = a_d + g_t + b E_d (t - 2019)         (differential trend; 2020 is the COVID year)
  crop    district-household-crop-value.csv, EICV 2011, 2014, 2017 (district x round). Outcomes: mean log crop value per
          ha and value shares of bananas, export crops, horticulture and staples (pp). Exposure measured in 2002.
            rounds  y_dt = a_d + g_t + sum_{t > 2011} b_t E_d 1[t]
            park    y_dt = a_d + g_t + sum_p b_p E_pd 1[2017]     (2011 and 2017 only)
  labour  district-labour-status.csv, labour force survey 2017-2025 (243 district-years). Outcomes: wage employees,
          self-employed, family workers and subsistence workers per 100 adults. Same three specifications as ag
          (exposure measured in 2022, trend base 2017). Subsistence is missing for 27 district-years.

Output: output/tables/regressions/district_ag_labour.csv
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "helpers"))
import paths as P  # noqa: E402
from regression import fe_ols  # noqa: E402

D = P.HARM_DISTRICT
EXPOSURE = D / "district-park-exposure-border.csv"
PARKS = ["volcanoes", "akagera", "nyungwe", "gishwati_mukura"]
ROWS = []


def exposure(d: pd.DataFrame, wave: int) -> pd.DataFrame:
    e = pd.read_csv(EXPOSURE).set_index("district_id")
    d = d.copy()
    d["E"] = d.district_id.map(e[f"adj_share_pop_{wave}"])
    for k in PARKS:
        d[f"E_{k}"] = d.district_id.map(e[f"pop_share_{k}_{wave}"])
    d["province"] = d.district_id // 10
    return d


def run(d, outcomes, terms, fes, section, spec):
    for y, label in outcomes:
        est, n, G = fe_ols(d, y, terms, fes, "district_id", test=terms)
        for t in terms:
            e = est.loc[t]
            ROWS.append({"section": section, "spec": spec, "outcome": y, "label": label, "term": t, "coef": e.coef,
                         "se": e.se, "p_wcb": e.p_wcb, "obs": n, "districts": d.dropna(subset=[y]).district_id.nunique(), "clusters": G})
        print(f"[district-al]   {section}/{spec}, {label}: " + ", ".join(
            f"{t} {est.loc[t, 'coef']:+.2f} [{est.loc[t, 'p_wcb']:.3f}]" for t in terms), flush=True)


def survey_sections(d, outcomes, section, base_year):
    """cross, park and trend specifications for a district-year panel measured after the programme began."""
    d = exposure(d, 2022)
    d["E_x_trend"] = d.E * (d.year - base_year)
    run(d, outcomes, ["E"], ["year", "province"], section, "cross")
    run(d, outcomes, [f"E_{k}" for k in PARKS], ["year", "province"], section, "park")
    run(d, outcomes, ["E_x_trend"], ["district_id", "year"], section, "trend")


def section_ag():
    a = pd.read_csv(D / "district-ag-productivity.csv")
    for k in ("bananas", "export", "horticulture", "staples"):
        a[f"area_{k}_pp"] = 100 * a[f"share_area_{k}"]
    outs = [("ln_value_per_ha_dprice", "Log crop value per ha"), ("ln_output_per_worker_dprice", "Log output per worker"),
            ("area_bananas_pp", "Banana area share (pp)"), ("area_export_pp", "Export-crop area share (pp)"),
            ("area_horticulture_pp", "Horticulture area share (pp)"), ("area_staples_pp", "Staples area share (pp)")]
    survey_sections(a, outs, "ag", 2019)


def section_crop():
    h = pd.read_csv(D / "district-household-crop-value.csv").rename(columns={"round": "year"})
    for k in ("bananas", "export", "horticulture", "staples"):
        h[f"value_{k}_pp"] = 100 * h[f"share_value_{k}"]
    outs = [("mean_ln_value_per_ha", "Log crop value per ha"), ("value_bananas_pp", "Banana value share (pp)"),
            ("value_export_pp", "Export-crop value share (pp)"), ("value_horticulture_pp", "Horticulture value share (pp)"),
            ("value_staples_pp", "Staples value share (pp)")]
    h = exposure(h, 2002)
    for r in (2014, 2017):
        h[f"E_x_{r}"] = h.E * (h.year == r)
    run(h, outs, ["E_x_2014", "E_x_2017"], ["district_id", "year"], "crop", "rounds")
    h = h[h.year.isin((2011, 2017))].copy()
    for k in PARKS:
        h[f"E_{k}_x_2017"] = h[f"E_{k}"] * (h.year == 2017)
    run(h, outs, [f"E_{k}_x_2017" for k in PARKS], ["district_id", "year"], "crop", "park")


def section_labour():
    l = pd.read_csv(D / "district-labour-status.csv")
    outs = []
    for k, lab in (("wage", "Wage employees"), ("self", "Self-employed"), ("family", "Family workers"), ("subsistence", "Subsistence workers")):
        l[f"{k}100"] = 100 * l[f"per_adult_{k}"]
        outs.append((f"{k}100", lab))
    survey_sections(l, outs, "labour", 2017)


SECTIONS = {"ag": section_ag, "crop": section_crop, "labour": section_labour}


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--only", nargs="+", choices=list(SECTIONS))
    a.add_argument("--list", action="store_true")
    args = a.parse_args(argv)
    if args.list:
        print("\n".join(SECTIONS)); return 0
    for k in args.only or SECTIONS:
        SECTIONS[k]()
    P.TABLES_REG.mkdir(parents=True, exist_ok=True)
    out = P.TABLES_REG / "district_ag_labour.csv"
    pd.DataFrame(ROWS).to_csv(out, index=False)
    print(f"[district-al] -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
