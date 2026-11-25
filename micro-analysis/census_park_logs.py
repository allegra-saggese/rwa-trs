"""
census_park_logs.py -- the sector-level park-adjacent gap with log outcomes (Census 2002, 2012, 2022).

Same design as census_park_regressions.py (sections gap, status), with the outcome in logs instead of workers per 100 adults:

    ln(y_st) = a_s + g_t + b_2012 Park_s 1[t = 2012] + b_2022 Park_s 1[t = 2022] + lam ln(adults_st) + e_st

  y        number of workers (Census-weighted): non-farm, services, farm (industry of main work); wage employees,
           self-employed, family workers and other status (employment status of main work).
  lam      free coefficient on log adults (the outcome is not forced to be a rate), so b_t is the proportional difference
           in workers between park-adjacent and interior sectors, relative to 2002, at a given population.
  FE       sector and wave. Sample: the 381 sectors outside Kigali; --drop-ring drops the 82 ring sectors.
  OLS      outcomes with no zero counts: wild cluster restricted bootstrap p-values by district (fe_ols), as elsewhere.
  Poisson  outcomes with zero counts (tourism): Poisson regression with sector and wave dummies, a log link, sectors with
           no workers in any wave dropped (their fixed effect is not identified). Coefficients are proportional differences
           (log points); standard errors clustered by district; p-values are cluster-robust normal, not bootstrapped
           (27 clusters, so they are too small by an unknown amount).

Why logs: a rate per 100 adults is dominated by sectors with large baselines; a log difference weights proportional change
and is not driven by a low 2002 base. Farm and "all workers" in 2022 are affected by the 2022 change in what counts as work.

Usage
    python micro-analysis/census_park_logs.py
    python micro-analysis/census_park_logs.py --drop-ring
Output: output/tables/regressions/census_park_logs[_no_ring].csv
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "helpers"))
sys.path.insert(0, str(ROOT / "micro-analysis"))
import paths as P  # noqa: E402
from regression import fe_ols  # noqa: E402
import census_park_regressions as C  # noqa: E402  (PANEL, SECTORS, KIGALI, ring_sectors)

STATUS = P.HARM_DISTRICT / "sector-labour-status.csv"
TERMS = ["park_x_2012", "park_x_2022"]
INDUSTRY = [("nonfarm", "Non-farm workers"), ("services", "Services workers"), ("tourism", "Tourism workers"), ("farm", "Farm workers")]
STAT = [("wage", "Wage employees"), ("self", "Self-employed"), ("family", "Family workers"), ("other", "Other status")]
ROWS = []


def prepare(drop_ring: bool):
    x = pd.read_csv(C.SECTORS)[["sid", "district_id", "border"]]
    ind = pd.read_csv(C.PANEL)[["sid", "wave", "adults", "nonfarm", "services", "tourism", "farm"]]
    st = pd.read_csv(STATUS).rename(columns={"sector_id": "sid", "year": "wave"})
    for k, _ in STAT:
        st[k] = st[f"per_adult_{k}"] * st.adults
    st = st[["sid", "wave", "adults", "wage", "self", "family", "other"]]
    out = []
    for d in (ind, st):
        d = d.merge(x, on="sid", validate="m:1")
        d = d[~d.district_id.isin(C.KIGALI)].copy()
        if drop_ring:
            d = d[~d.sid.isin(C.ring_sectors())].copy()
        d["log_adults"] = np.log(d.adults)
        for t in (2012, 2022):
            d[f"park_x_{t}"] = d.border * (d.wave == t)
        out.append(d)
    return out


def ppml(d, y):
    g = d.groupby("sid")[y].transform("sum") > 0                     # drop sectors with no workers in any wave
    d = d[g].copy()
    X = pd.concat([d[TERMS + ["log_adults"]], pd.get_dummies(d.sid, prefix="s", drop_first=True, dtype=float),
                   pd.get_dummies(d.wave, prefix="w", drop_first=True, dtype=float)], axis=1)
    m = sm.GLM(d[y], sm.add_constant(X), family=sm.families.Poisson()).fit(
        cov_type="cluster", cov_kwds={"groups": pd.factorize(d.district_id)[0]}, maxiter=200)
    r = pd.DataFrame({"coef": m.params, "se": m.bse, "p": m.pvalues}).loc[TERMS + ["log_adults"]]
    return r, int(len(d)), d.sid.nunique(), d.district_id.nunique()


def run(d, y, label, spec):
    if (d[y] > 0).all():
        d = d.assign(ln_y=np.log(d[y]))
        est, n, G = fe_ols(d, "ln_y", TERMS + ["log_adults"], ["sid", "wave"], "district_id", test=TERMS)
        est = est.rename(columns={"p_wcb": "p"})
        kind, ns = "OLS, log workers", d.sid.nunique()
    else:
        est, n, ns, G = ppml(d, y)
        kind = "Poisson, workers"
    for t in (2012, 2022):
        e = est.loc[f"park_x_{t}"]
        ROWS.append({"spec": spec, "outcome": y, "label": label, "estimator": kind, "wave": t, "coef": e.coef, "se": e.se,
                     "p": e.p, "log_adults_coef": est.loc["log_adults", "coef"], "obs": n, "sectors": ns, "clusters": G})
    print(f"[logs]   {spec}, {label} ({kind}): 2012 {est.loc['park_x_2012','coef']:+.3f} [{est.loc['park_x_2012','p']:.3f}], "
          f"2022 {est.loc['park_x_2022','coef']:+.3f} [{est.loc['park_x_2022','p']:.3f}]; ln adults {est.loc['log_adults','coef']:.2f}", flush=True)


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--drop-ring", action="store_true")
    args = a.parse_args(argv)
    ind, st = prepare(args.drop_ring)
    print(f"[logs] {ind.sid.nunique()} sectors ({int(ind.drop_duplicates('sid').border.sum())} park-adjacent)", flush=True)
    for y, lab in INDUSTRY:
        run(ind, y, lab, "industry")
    for y, lab in STAT:
        run(st, y, lab, "status")
    P.TABLES_REG.mkdir(parents=True, exist_ok=True)
    out = P.TABLES_REG / f"census_park_logs{'_no_ring' if args.drop_ring else ''}.csv"
    pd.DataFrame(ROWS).to_csv(out, index=False)
    print(f"[logs] -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
