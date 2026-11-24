"""
census_park_status.py -- park-adjacent vs interior sectors by employment status of main work, Census 2002, 2012, 2022.

Same design as census_park_regressions.py (section gap), with employment status in place of industry:

    y_st = a_s + g_t + b_2012 Park_s 1[t = 2012] + b_2022 Park_s 1[t = 2022] + e_st

  y     workers per 100 adults, by status of main work: wage employee, self-employed, family worker, other; and all
        workers per 100 adults. Data: data/harmonized/district/sector-labour-status.csv (columns per_adult_wage,
        per_adult_self, per_adult_family, per_adult_other, workers / adults), times 100.
  Park  1 if the sector borders a national park: model_sector_cross.csv, column border (62 sectors outside Kigali).
        The file's own `adjacent` flag marks only 51 sectors (it misses 9 Gishwati, 1 Nyungwe and 1 Akagera sector) and is not used.
  FE    sector and wave. Standard errors clustered by district, wild cluster restricted bootstrap p-values (fe_ols).

Two caveats. (1) The panel's adult count is 92-94% of the Census work panel's (different age cutoff or universe; not
documented in the file), so rates here are not comparable in level with census_sector_work_per_adult.csv; each rate uses
its own numerator and denominator. (2) In 2022 farming counts as work only if mainly for the market, so self-employed and
family work (mostly farming) and all workers fall in every sector; wave fixed effects absorb a common fall, not one that
differs by sector.

Usage
    python micro-analysis/census_park_status.py
    python micro-analysis/census_park_status.py --drop-ring     # drop the 82 sectors touching a park-adjacent sector
Output: output/tables/regressions/census_park_status[_no_ring].csv
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "helpers"))
sys.path.insert(0, str(ROOT / "micro-analysis"))
import paths as P  # noqa: E402
from regression import fe_ols  # noqa: E402
import census_park_regressions as C  # noqa: E402  (ring_sectors, KIGALI)

STATUS = P.HARMONIZED / "district" / "sector-labour-status.csv"
OUTCOMES = [("wage100", "Wage employees"), ("self100", "Self-employed"), ("family100", "Family workers"),
            ("other100", "Other status"), ("workers100", "All workers")]


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--drop-ring", action="store_true")
    args = a.parse_args(argv)
    suffix = "_no_ring" if args.drop_ring else ""

    s = pd.read_csv(STATUS).rename(columns={"sector_id": "sid", "year": "wave"})
    s["wage100"], s["self100"] = 100 * s.per_adult_wage, 100 * s.per_adult_self
    s["family100"], s["other100"] = 100 * s.per_adult_family, 100 * s.per_adult_other
    s["workers100"] = 100 * s.workers / s.adults
    x = pd.read_csv(C.SECTORS)[["sid", "district_id", "border"]]
    d = s.drop(columns=["district_id"]).merge(x, on="sid", how="inner", validate="m:1")
    d = d[~d.district_id.isin(C.KIGALI)].copy()
    if args.drop_ring:
        d = d[~d.sid.isin(C.ring_sectors())].copy()
    for t in (2012, 2022):
        d[f"park_x_{t}"] = d.border * (d.wave == t)
    terms = ["park_x_2012", "park_x_2022"]
    print(f"[status] {d.sid.nunique()} sectors, {int(d.drop_duplicates('sid').border.sum())} park-adjacent", flush=True)

    rows = []
    for y, label in OUTCOMES:
        est, n, G = fe_ols(d, y, terms, ["sid", "wave"], "district_id", test=terms)
        m = {t: d[(d.wave == t)].groupby("border")[y].mean() for t in (2002, 2012, 2022)}
        for t in (2012, 2022):
            e = est.loc[f"park_x_{t}"]
            rows.append({"outcome": y, "label": label, "wave": t, "coef": e.coef, "se": e.se, "p_wcb": e.p_wcb,
                         "mean_park_2002": m[2002][1], "mean_interior_2002": m[2002][0],
                         "mean_park_wave": m[t][1], "mean_interior_wave": m[t][0], "obs": n, "clusters": G})
        print(f"[status]   {label}: 2012 {est.loc['park_x_2012','coef']:+.2f} [{est.loc['park_x_2012','p_wcb']:.3f}], "
              f"2022 {est.loc['park_x_2022','coef']:+.2f} [{est.loc['park_x_2022','p_wcb']:.3f}]", flush=True)
    P.TABLES_REG.mkdir(parents=True, exist_ok=True)
    out = P.TABLES_REG / f"census_park_status{suffix}.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"[status] -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
