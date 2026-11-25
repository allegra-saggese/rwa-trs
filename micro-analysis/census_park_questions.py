"""
census_park_questions.py -- sector-level regressions organised by question, with geographic controls (Census 2002, 2012, 2022).

Every regression is printed with its specification, outcomes, controls and fixed effects, and saved with them as columns.

Controls X (six sector characteristics, z-scored over the 381 sectors outside Kigali; none is an outcome of tourism)
    log area (km2)                                   model_sector_cross.csv, unit_km2
    log distance to the nearest trunk/primary road   data/geo-data/roads/sector_distances.csv (OSM snapshot, treated as fixed)
    log distance to Kigali                           same file
    mean elevation (m), mean slope (degrees)         data/geo-data/raster/sector_terrain.csv (DEM)
    mean annual rainfall (mm, CHIRPS 1981-2002)      data/geo-data/raster/sector_rainfall.csv (before the first Census wave)
  Not used: building footprints and grid length (recent snapshots, partly outcomes of tourism and settlement).
  In a panel with sector fixed effects the levels of X are absorbed, so X enters as X x wave (a separate coefficient per
  wave): sectors differing in elevation, rainfall, remoteness or size are allowed to follow different time paths.

Questions
  Q1  Do park-adjacent sectors have a different labour mix, comparing sectors in the same district with the same geography?
      Per wave:  ln(y_s) = a_district + b Park_s + lam ln(adults_s) [+ X_s g] + e_s
      y = non-farm, services, farm workers (OLS on logs, wild cluster bootstrap p); tourism workers (Poisson, normal p).
      Spec A: no X. Spec B: with X.
  Q2  Do they change differently from 2002, comparing like with like?
      ln(y_st) = a_s + g_t + sum_t b_t Park_s 1[t] + lam ln(adults_st) [+ sum_t X_s g_t] + e_st
      Same outcomes in logs, and workers per 100 adults (OLS, no ln adults). Spec A: no X x wave. Spec B: with X x wave.
      Spec C: spec B estimated by weighted least squares, interior sectors reweighted by entropy balancing so that their
      means of X equal the park-adjacent sectors' (park-adjacent weight 1, interior weights sum to the park-adjacent count);
      OLS outcomes only; cluster-robust normal p (no bootstrap).
  Q3  Does distance to a park gate matter, beyond bordering a park?
      Per wave:  ln(y_s) = a_nearest-park + sum_k d_k 1[gate distance bin k] + lam ln(adults_s) + X_s g [+ b Park_s] + e_s
      Bins of distance from the sector centroid to the nearest of four gates: under 10 km, 10-20, 20-40 (40 km+ omitted).
      Spec A: bins. Spec B: bins and the Park dummy. Fixed effects: nearest park (5 values), not district.
  Q4  Does exposure to park tourism change the labour mix?
      y_st = a_s + g_t + sum_t b_t E_s 1[t] + lam ln(adults) (log outcomes only) [+ sum_t X_s g_t] + e_st
      E_s = nearest park's share of three-park visits 2005-2019 (Volcanoes .40, Akagera .46, Nyungwe .14), 0 interior;
      361 sectors (Gishwati-Mukura dropped). Spec A: no X x wave. Spec B: with.
  Q5  Does land use move with the park, with the same geography held fixed?
      y_st = a_s + g_t + sum_t b_t Park_s 1[t] [+ sum_t X_s g_t] + e_st,  t = 2010, 2020 (2000 base)
      y = cropland share, built-up share (pp, GLAD), ln(1 + built-up ha, GHSL). Spec A: no X x year. Spec B: with.

Standard errors are clustered by district (27) throughout. Sample: the 381 sectors outside Kigali (--drop-ring: the 299
that remain without the 82 sectors touching a park-adjacent sector). A sector with no workers in any wave has no identified
sector effect and is dropped from the tourism Poisson regressions. The 2022 farm count is affected by the change in what
counts as work; Q1 and Q3 compare sectors within a wave, Q2 and Q4 difference it out only if it is common to all sectors.

Usage
    python micro-analysis/census_park_questions.py
    python micro-analysis/census_park_questions.py --drop-ring
    python micro-analysis/census_park_questions.py --only Q1 Q3
Output: output/tables/regressions/census_park_questions[_no_ring].csv
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "helpers"))
sys.path.insert(0, str(ROOT / "micro-analysis"))
sys.path.insert(0, str(ROOT / "results-scripts"))
import paths as P  # noqa: E402
from regression import fe_ols  # noqa: E402
import census_park_regressions as C  # noqa: E402  (PANEL, SECTORS, KIGALI, ring_sectors)
import park_land_regressions as L  # noqa: E402  (sectors with exposure E_s, land_panel)
import sector_gate_plots as G  # noqa: E402  (hav, TG.GATE_XY: distance from centroid to the nearest gate)

XVARS = ["log_area", "log_dist_road", "log_dist_kigali", "elev_mean", "slope_mean", "rain_mean"]
X_LABEL = "log area, log distance to road, log distance to Kigali, elevation, slope, rainfall (z-scored)"
INDUSTRY = [("nonfarm", "Non-farm workers"), ("services", "Services workers"), ("tourism", "Tourism workers"), ("farm", "Farm workers")]
RATES = [("nonfarm_per100", "Non-farm per 100 adults"), ("services_per100", "Services per 100 adults"),
         ("tourism_per100", "Tourism per 100 adults")]
LAND = [("crop_pp", "Cropland share (pp)"), ("built_pp", "Built-up share (pp)"), ("log_built", "ln(1 + built-up ha)")]
BINS = [("gate_lt10", 0, 10), ("gate_10_20", 10, 20), ("gate_20_40", 20, 40)]
RHO = 0.3                                    # penalty in the balancing weights (see entropy_weights)
ROWS = []


# ---------------------------------------------------------------------------- data
def controls() -> pd.DataFrame:
    """Sector attributes and z-scored controls for the 381 sectors outside Kigali, plus distance to the nearest gate."""
    c = pd.read_csv(C.SECTORS)[["sid", "district_id", "border", "nearest_park", "unit_km2", "lon", "lat"]]
    c = c[~c.district_id.isin(C.KIGALI)].copy()
    c["log_area"] = np.log(c.unit_km2)
    for f, cols in [("roads/sector_distances.csv", ["log_dist_road", "log_dist_kigali"]),
                    ("raster/sector_terrain.csv", ["elev_mean", "slope_mean"]), ("raster/sector_rainfall.csv", ["rain_mean"])]:
        c = c.merge(pd.read_csv(P.GEO / f)[["sid"] + cols], on="sid", how="left", validate="1:1")
    assert c[XVARS].notna().all().all() and len(c) == 381
    c[XVARS] = (c[XVARS] - c[XVARS].mean()) / c[XVARS].std()
    km = np.column_stack([G.hav(c.lon, c.lat, *xy) for xy in G.TG.GATE_XY.values()]).min(axis=1)
    for name, lo, hi in BINS:
        c[name] = ((km > lo) & (km <= hi)).astype(int) if lo else (km <= hi).astype(int)
    c["km_gate"] = km
    return c.drop(columns=["lon", "lat", "unit_km2"])


def sample(d: pd.DataFrame, drop_ring: bool, ring: set) -> pd.DataFrame:
    return d[~d.sid.isin(ring)].copy() if drop_ring else d


def census(x, ring, drop_ring) -> pd.DataFrame:
    d = pd.read_csv(C.PANEL)[["sid", "wave", "adults", "nonfarm", "services", "tourism", "farm",
                              "nonfarm_per100", "services_per100", "tourism_per100"]]
    d = d.merge(x, on="sid", validate="m:1")
    d["log_adults"] = np.log(d.adults)
    for t in (2012, 2022):
        d[f"park_x_{t}"] = d.border * (d.wave == t)
    return sample(d, drop_ring, ring)


def with_x_by_wave(d: pd.DataFrame, wave_col: str, waves) -> list:
    names = []
    for t in waves:
        for v in XVARS:
            d[f"{v}_x_{t}"] = d[v] * (d[wave_col] == t)
            names.append(f"{v}_x_{t}")
    return names


# ---------------------------------------------------------------------------- estimators
def ols(d, y, xs, fes, test):
    est, n, g = fe_ols(d, y, xs, fes, "district_id", test=test)
    return est.rename(columns={"p_wcb": "p"}), n, d.dropna(subset=[y] + xs).sid.nunique(), g


def poisson(d, y, xs, fes):
    """Poisson, log link; FE as dummies; groups with no positive outcome dropped; cluster-robust (district) normal p."""
    d = d.copy()
    while True:
        keep = np.ones(len(d), bool)
        for f in fes:
            keep &= (d.groupby(f)[y].transform("sum") > 0).values
        if keep.all():
            break
        d = d[keep]
    X = pd.concat([d[xs]] + [pd.get_dummies(d[f], prefix=f, drop_first=True, dtype=float) for f in fes], axis=1)
    m = sm.GLM(d[y], sm.add_constant(X), family=sm.families.Poisson()).fit(
        cov_type="cluster", cov_kwds={"groups": pd.factorize(d.district_id)[0]}, maxiter=200)
    r = pd.DataFrame({"coef": m.params, "se": m.bse, "p": m.pvalues}).loc[xs]
    return r, int(len(d)), d.sid.nunique(), d.district_id.nunique()


def wls(d, y, xs, fes, w):
    X = pd.concat([d[xs]] + [pd.get_dummies(d[f], prefix=f, drop_first=True, dtype=float) for f in fes], axis=1)
    m = sm.WLS(d[y], sm.add_constant(X), weights=d[w]).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(d.district_id)[0]})
    r = pd.DataFrame({"coef": m.params, "se": m.bse, "p": m.pvalues}).loc[xs]
    return r, int(len(d)), d.sid.nunique(), d.district_id.nunique()


def entropy_weights(x: pd.DataFrame, rho: float = RHO):
    """Penalised entropy-balancing weights on interior sectors (dual of Hainmueller 2012 with an L2 penalty rho on the
    multipliers). Exact balance of the six park-adjacent means is infeasible (the best achievable worst gap is 0.22 SD with
    weights concentrated on a handful of sectors), so the penalty trades balance for effective sample size. Park-adjacent
    sectors get weight 1; the interior weights sum to the number of park-adjacent sectors."""
    T = x[x.border == 1]
    Z = x[x.border == 0]
    m = T[XVARS].mean().values
    A = Z[XVARS].values - m
    f = lambda lam: np.log(np.exp(A @ lam).sum()) + rho / 2 * lam @ lam
    g = lambda lam: (np.exp(A @ lam)[:, None] * A).sum(0) / np.exp(A @ lam).sum() + rho * lam
    r = minimize(f, np.zeros(len(XVARS)), jac=g, method="BFGS")
    w = np.exp(A @ r.x)
    w = w / w.sum() * len(T)
    ess = w.sum() ** 2 / (w ** 2).sum()
    gap = np.abs((w[:, None] * Z[XVARS].values).sum(0) / w.sum() - m)
    print(f"[questions]   balancing (penalty {rho}): converged {r.success}; worst mean gap {gap.max():.2f} SD "
          f"(unweighted {np.abs(Z[XVARS].mean().values - m).max():.2f}); interior effective sample {ess:.0f} of {len(Z)}; "
          f"max weight {w.max():.1f}", flush=True)
    out = pd.concat([pd.Series(w, index=Z.sid), pd.Series(1.0, index=T.sid)])
    return out.rename("w_eb")


# ---------------------------------------------------------------------------- recording
def record(q, spec, y, label, est, n, ns, g, focal, kind, ptype, controls_, fe, wave=None, note=""):
    for t in focal:
        e = est.loc[t]
        ROWS.append({"question": q, "spec": spec, "outcome": y, "label": label, "estimator": kind, "p_type": ptype, "term": t,
                     "wave": wave, "coef": e.coef, "se": e.se, "p": e.p, "obs": n, "sectors": ns, "clusters": g,
                     "controls": controls_, "fixed_effects": fe, "note": note})
    print(f"[questions]   {spec} | {label} ({kind}): " + ", ".join(f"{t} {est.loc[t,'coef']:+.3f} [{est.loc[t,'p']:.3f}]" for t in focal), flush=True)


def run_outcome(d, y, label, q, spec, terms, ctrl, fes, controls_, wave=None, ln_adults=True, rate=False, note=""):
    """Counts: OLS on ln(y) (bootstrap p) when y > 0 everywhere, otherwise Poisson. rate=True: OLS on y itself."""
    xs = terms + (["log_adults"] if ln_adults else []) + ctrl
    if rate:
        est, n, ns, g = ols(d, y, xs, fes, terms)
        record(q, spec, y, label, est, n, ns, g, terms, "OLS, rate per 100 adults", "wild cluster bootstrap", controls_, "+".join(fes), wave, note)
    elif (d[y] > 0).all():
        dd = d.assign(ln_y=np.log(d[y]))
        est, n, ns, g = ols(dd, "ln_y", xs, fes, terms)
        record(q, spec, y, label, est, n, ns, g, terms, "OLS, ln workers", "wild cluster bootstrap", controls_, "+".join(fes), wave, note)
    else:
        est, n, ns, g = poisson(d, y, xs, fes)
        record(q, spec, y, label, est, n, ns, g, terms, "Poisson, workers", "cluster-robust normal", controls_, "+".join(fes), wave, note)


# ---------------------------------------------------------------------------- questions
def q1(x, ring, drop_ring):
    print("[questions] Q1 cross-section, park-adjacent vs interior, district FE", flush=True)
    d = census(x, ring, drop_ring)
    for t in C.WAVES:
        w = d[d.wave == t].copy()
        print(f"[questions]  Q1 wave {t}: {w.sid.nunique()} sectors ({int(w.border.sum())} park-adjacent)", flush=True)
        for spec, ctrl in [("A: ln adults", []), ("B: ln adults + X", XVARS)]:
            cs = "ln(adults)" + (f"; {X_LABEL}" if ctrl else "")
            for y, lab in INDUSTRY:
                run_outcome(w, y, lab, "Q1", spec, ["border"], ctrl, ["district_id"], cs, wave=t)


def q2(x, ring, drop_ring):
    print("[questions] Q2 panel, Park x wave, sector FE, with and without X x wave", flush=True)
    d = census(x, ring, drop_ring)
    xw = with_x_by_wave(d, "wave", (2012, 2022))
    terms = ["park_x_2012", "park_x_2022"]
    cs_b = f"ln(adults); {X_LABEL} x wave (2012, 2022)"
    print(f"[questions]  Q2: {d.sid.nunique()} sectors, {int(d.drop_duplicates('sid').border.sum())} park-adjacent", flush=True)
    for spec, ctrl, cs in [("A: ln adults", [], "ln(adults)"), ("B: ln adults + X x wave", xw, cs_b)]:
        for y, lab in INDUSTRY:
            run_outcome(d, y, lab, "Q2", spec, terms, ctrl, ["sid", "wave"], cs)
    for spec, ctrl, cs in [("A rate: none", [], "none"), ("B rate: X x wave", xw, f"{X_LABEL} x wave (2012, 2022)")]:
        for y, lab in RATES:
            run_outcome(d, y, lab, "Q2", spec, terms, ctrl, ["sid", "wave"], cs, ln_adults=False, rate=True)
    # spec C: entropy-balanced WLS, OLS outcomes
    xs_ = x[x.sid.isin(d.sid)]
    w = entropy_weights(xs_)
    dw = d.merge(w, left_on="sid", right_index=True, validate="m:1")
    for y, lab in [("nonfarm", "Non-farm workers"), ("services", "Services workers"), ("farm", "Farm workers")]:
        dd = dw.assign(ln_y=np.log(dw[y]))
        est, n, ns, g = wls(dd, "ln_y", terms + ["log_adults"] + xw, ["sid", "wave"], "w_eb")
        record("Q2", "C: B, entropy-balanced WLS", y, lab, est, n, ns, g, terms, "WLS, ln workers", "cluster-robust normal",
               cs_b + "; interior sectors reweighted to park-adjacent means of X", "sid+wave")
    for y, lab in RATES:
        est, n, ns, g = wls(dw, y, terms + xw, ["sid", "wave"], "w_eb")
        record("Q2", "C rate: balanced WLS", y, lab, est, n, ns, g, terms, "WLS, rate", "cluster-robust normal",
               f"{X_LABEL} x wave; interior reweighted", "sid+wave")


def q3(x, ring, drop_ring):
    print("[questions] Q3 gate-distance bins, cross-section, nearest-park FE", flush=True)
    d = census(x, ring, drop_ring)
    terms = [b[0] for b in BINS]
    for t in C.WAVES:
        w = d[d.wave == t].copy()
        print(f"[questions]  Q3 wave {t}: {w.sid.nunique()} sectors; bin counts " +
              ", ".join(f"{b[0]} {int(w[b[0]].sum())}" for b in BINS), flush=True)
        for spec, tm in [("A: bins", terms), ("B: bins + Park dummy", terms + ["border"])]:
            cs = f"ln(adults); {X_LABEL}"
            for y, lab in INDUSTRY:
                run_outcome(w, y, lab, "Q3", spec, tm, XVARS, ["nearest_park"], cs, wave=t)


def q4(x, ring, drop_ring):
    print("[questions] Q4 visit-share exposure E_s x wave", flush=True)
    s = L.sectors()[["sid", "exposure", "gm"]]
    d = census(x, ring, drop_ring).merge(s, on="sid", validate="m:1")
    d = d[d.gm == 0].copy()
    for t in (2012, 2022):
        d[f"E_x_{t}"] = d.exposure * (d.wave == t)
    xw = with_x_by_wave(d, "wave", (2012, 2022))
    terms = ["E_x_2012", "E_x_2022"]
    print(f"[questions]  Q4: {d.sid.nunique()} sectors (Gishwati-Mukura dropped)", flush=True)
    for spec, ctrl, cs in [("A: ln adults", [], "ln(adults)"), ("B: ln adults + X x wave", xw, f"ln(adults); {X_LABEL} x wave")]:
        for y, lab in INDUSTRY:
            run_outcome(d, y, lab, "Q4", spec, terms, ctrl, ["sid", "wave"], cs)
    for spec, ctrl, cs in [("A rate: none", [], "none"), ("B rate: X x wave", xw, f"{X_LABEL} x wave")]:
        for y, lab in RATES:
            run_outcome(d, y, lab, "Q4", spec, terms, ctrl, ["sid", "wave"], cs, ln_adults=False, rate=True)


def q5(x, ring, drop_ring):
    print("[questions] Q5 land panel, Park x year, with and without X x year", flush=True)
    d = L.land_panel()
    d = d[d.year.isin((2000, 2010, 2020))].drop(columns=["border", "district_id", "nearest_park"]).merge(
        x[["sid", "district_id", "border", "nearest_park"] + XVARS], on="sid", validate="m:1")
    d = sample(d, drop_ring, ring)
    for t in (2010, 2020):
        d[f"park_x_{t}"] = d.border * (d.year == t)
    xy = with_x_by_wave(d, "year", (2010, 2020))
    terms = ["park_x_2010", "park_x_2020"]
    print(f"[questions]  Q5: {d.sid.nunique()} sectors, {int(d.drop_duplicates('sid').border.sum())} park-adjacent", flush=True)
    for spec, ctrl, cs in [("A: none", [], "none"), ("B: X x year", xy, f"{X_LABEL} x year (2010, 2020)")]:
        for y, lab in LAND:
            est, n, ns, g = ols(d, y, terms + ctrl, ["sid", "year"], terms)
            record("Q5", spec, y, lab, est, n, ns, g, terms, "OLS, level", "wild cluster bootstrap", cs, "sid+year")


QUESTIONS = {"Q1": q1, "Q2": q2, "Q3": q3, "Q4": q4, "Q5": q5}


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--drop-ring", action="store_true")
    a.add_argument("--only", nargs="+", choices=list(QUESTIONS))
    args = a.parse_args(argv)
    x = controls()                                   # z-scored over all 381 sectors, also with --drop-ring
    ring = C.ring_sectors() if args.drop_ring else set()
    n = len(x[~x.sid.isin(ring)])
    print(f"[questions] {n} sectors{' (ring dropped)' if args.drop_ring else ''}", flush=True)
    for k in (args.only or list(QUESTIONS)):
        QUESTIONS[k](x, ring, args.drop_ring)
    P.TABLES_REG.mkdir(parents=True, exist_ok=True)
    out = P.TABLES_REG / f"census_park_questions{'_no_ring' if args.drop_ring else ''}.csv"
    pd.DataFrame(ROWS).to_csv(out, index=False)
    print(f"[questions] -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
