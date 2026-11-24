"""
district_ag_regressions.py -- does farming intensify in districts with more park-adjacent population?

Unit: district (27 outside Kigali City). Exposure E_d = share of the district's 2012 population living in park-adjacent
sectors (district-park-exposure.csv, adj_share_pop_2012), entered per 0.10. District and period fixed effects; district-level
standard errors with wild cluster restricted bootstrap p-values (each district is a cluster, so 27 clusters).

  eicv   y_dr = a_d + g_r + sum_{r > 2011} b_r E_d 1[r] + e_dr, EICV rounds 2011, 2014, 2017 (81 obs).
         y = mean log crop value per hectare, 2014 RWF (district-household-crop-value.csv, mean_ln_value_per_ha).
  sas    y_dt = a_d + g_t + sum_{t > 2019} b_t E_d 1[t] + e_dt, SAS 2019-2025 (189 obs).
         y = log value per hectare at constant prices (district-ag-productivity.csv, ln_value_per_ha_dprice);
             log farm output per worker = log(value at constant prices / farm workers). Farm workers come from the Census
             (sector panel farm count summed to districts, linearly interpolated between 2012 and 2022), not the SAS;
             log cropped area (area_ha).
EICV (household crop value) and SAS (district crop value) are different sources, so the two sets are not stacked.

Output: output/tables/regressions/district_ag_intensification.csv

Usage: python micro-analysis/district_ag_regressions.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "helpers"))
import paths as P  # noqa: E402
from regression import fe_ols  # noqa: E402

D = P.HARM_DISTRICT
CENSUS_PANEL = P.HARMONIZED / "census_sector_work_per_adult.csv"
SECTORS = P.HARMONIZED / "model_sector_cross.csv"


def exposure() -> pd.DataFrame:
    e = pd.read_csv(D / "district-park-exposure.csv")[["district_id", "adj_share_pop_2012"]]
    e["exposure"] = e.adj_share_pop_2012 / 0.10
    return e[["district_id", "exposure"]]


def census_farm_workers() -> pd.DataFrame:
    """District farm workers, Census 2012 and 2022, linearly interpolated to each year."""
    c = pd.read_csv(CENSUS_PANEL).merge(pd.read_csv(SECTORS)[["sid", "district_id"]], on="sid")
    f = c[c.wave.isin([2012, 2022])].groupby(["district_id", "wave"]).farm.sum().unstack()
    rows = [{"district_id": d, "year": y, "farm_workers": r[2012] + (r[2022] - r[2012]) * (y - 2012) / 10}
            for d, r in f.iterrows() for y in range(2019, 2026)]
    return pd.DataFrame(rows)


def run(d, outcomes, terms, spec, period, rows):
    for y, label in outcomes:
        est, n, G = fe_ols(d, y, terms, ["district_id", period], "district_id", test=terms)
        for t in terms:
            e = est.loc[t]
            rows.append({"spec": spec, "outcome": y, "label": label, "term": t, "coef": e.coef, "se": e.se,
                         "p_wcb": e.p_wcb, "obs": n, "districts": G})
        print(f"[ag] {spec}, {label}: " + ", ".join(f"{t} {est.loc[t, 'coef']:+.3f} [{est.loc[t, 'p_wcb']:.3f}]" for t in terms))


def main() -> int:
    e, rows = exposure(), []
    h = pd.read_csv(D / "district-household-crop-value.csv").merge(e, on="district_id")
    h["period"] = h["round"]
    terms = []
    for r in (2014, 2017):
        h[f"E_x_{r}"] = h.exposure * (h.period == r); terms.append(f"E_x_{r}")
    run(h, [("mean_ln_value_per_ha", "Log crop value per ha (EICV)")], terms, "eicv 2011-2017, 2011 base", "period", rows)

    s = pd.read_csv(D / "district-ag-productivity.csv").merge(e, on="district_id").merge(census_farm_workers(), on=["district_id", "year"])
    s["ln_output_per_worker_census"] = np.log(s.value_dprice_rwf / s.farm_workers)
    s["ln_area"] = np.log(s.area_ha)
    s["period"] = s.year
    terms = []
    for t in range(2020, 2026):
        s[f"E_x_{t}"] = s.exposure * (s.period == t); terms.append(f"E_x_{t}")
    run(s, [("ln_value_per_ha_dprice", "Log value per ha (SAS)"), ("ln_output_per_worker_census", "Log output per farm worker (Census workers)"),
            ("ln_area", "Log cropped area (SAS)")], terms, "sas 2019-2025, 2019 base", "period", rows)
    P.TABLES_REG.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(P.TABLES_REG / "district_ag_intensification.csv", index=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
