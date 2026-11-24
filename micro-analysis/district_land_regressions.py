"""
district_land_regressions.py -- land rents and land values in districts exposed to park tourism.

Unit: district x EICV round, 27 districts outside Kigali City. Data: data/harmonized/district/district-land-prices.csv
(EICV parcel reports aggregated to the district: mean of log rent or value per hectare, in 2014 RWF; the AHS 2024 rent
round is a different survey and is left out). Exposure E_d = share of the district's 2002 population living in
park-adjacent sectors (district-park-exposure-border.csv, from the 62-sector border flag); E_pd is the same share for
sectors whose nearest park is p (Volcanoes, Akagera, Nyungwe, Gishwati-Mukura). Fixed at 2002 so exposure does not respond
to later population moves. District and round fixed effects; standard errors clustered by district, wild cluster
restricted bootstrap p-values (helpers/regression.py::fe_ols).

Sections (python micro-analysis/district_land_regressions.py --list)
  rent_rounds    y_dt = a_d + g_t + sum_{t > 2001} b_t E_d 1[t],   log rent per ha, rounds 2001, 2006, 2011, 2014, 2017.
  first_last     y_dt = a_d + g_t + b E_d 1[2017],                 log rent (2001, 2017) and log value (2001, 2017).
  by_park        y_dt = a_d + g_t + sum_p b_p E_pd 1[2017],        same outcomes; one coefficient per park.
Only 14 districts have any exposure (Nyungwe 5, Volcanoes 4, Akagera 3, Gishwati-Mukura 4; Rubavu and Nyabihu border two
parks), so per-park coefficients rest on 3-5 treated districts. Descriptive; not causal.

Output: output/tables/regressions/district_land_values.csv
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

PRICES = P.HARM_DISTRICT / "district-land-prices.csv"
EXPOSURE = P.HARM_DISTRICT / "district-park-exposure-border.csv"
PARKS = ["volcanoes", "akagera", "nyungwe", "gishwati_mukura"]
ROWS = []


def panel(measure: str, rounds) -> pd.DataFrame:
    p = pd.read_csv(PRICES, usecols=["district_id", "source", "round", "measure", "n_parcels", "mean_ln_per_ha"])
    p = p[(p.source == "EICV") & (p.measure == measure) & p["round"].isin(rounds)]
    e = pd.read_csv(EXPOSURE).set_index("district_id")
    p = p.assign(E=p.district_id.map(e.adj_share_pop_2002))
    for k in PARKS:
        p[f"E_{k}"] = p.district_id.map(e[f"pop_share_{k}_2002"])
    return p


def run(d, y, terms, section, spec, label):
    est, n, G = fe_ols(d, y, terms, ["district_id", "round"], "district_id", test=terms)
    for t in terms:
        e = est.loc[t]
        ROWS.append({"section": section, "spec": spec, "outcome": label, "term": t, "coef": e.coef, "se": e.se,
                     "p_wcb": e.p_wcb, "obs": n, "districts": d.district_id.nunique(), "clusters": G,
                     "min_parcels": int(d.n_parcels.min())})
    print(f"[district-land]   {spec}, {label}: " + ", ".join(
        f"{t} {est.loc[t, 'coef']:+.3f} [{est.loc[t, 'p_wcb']:.3f}]" for t in terms), flush=True)


def section_rent_rounds():
    d = panel("rent", (2001, 2006, 2011, 2014, 2017))
    ts = [r for r in (2006, 2011, 2014, 2017)]
    for r in ts:
        d[f"E_x_{r}"] = d.E * (d["round"] == r)
    print(f"[district-land] rent_rounds: {d.district_id.nunique()} districts, {len(d)} district-rounds, min parcels {d.n_parcels.min()}")
    run(d, "mean_ln_per_ha", [f"E_x_{r}" for r in ts], "rent_rounds", "EICV 2001-2017", "Log rent per ha")


def section_first_last():
    for measure, label in (("rent", "Log rent per ha"), ("value", "Log value per ha")):
        d = panel(measure, (2001, 2017))
        d["E_x_2017"] = d.E * (d["round"] == 2017)
        print(f"[district-land] first_last {measure}: {d.district_id.nunique()} districts, {len(d)} district-rounds")
        run(d, "mean_ln_per_ha", ["E_x_2017"], "first_last", "2001 vs 2017", label)


def section_by_park():
    for measure, label in (("rent", "Log rent per ha"), ("value", "Log value per ha")):
        d = panel(measure, (2001, 2017))
        for k in PARKS:
            d[f"E_{k}_x_2017"] = d[f"E_{k}"] * (d["round"] == 2017)
        run(d, "mean_ln_per_ha", [f"E_{k}_x_2017" for k in PARKS], "by_park", "2001 vs 2017, one term per park", label)


SECTIONS = {"rent_rounds": section_rent_rounds, "first_last": section_first_last, "by_park": section_by_park}


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
    out = P.TABLES_REG / "district_land_values.csv"
    pd.DataFrame(ROWS).to_csv(out, index=False)
    print(f"[district-land] -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
