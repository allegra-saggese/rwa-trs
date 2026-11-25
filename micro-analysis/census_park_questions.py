"""
census_park_questions.py -- sector-level regressions organised by question, estimated one Census wave at a time.

Design. The Census waves are repeated cross-sections, so every regression is a separate OLS for ONE wave (2002, 2012 or 2022;
land cover: 2000, 2010 or 2020). There are no sector fixed effects, no base year and no change-from-baseline terms. The
workhorse is a log-log regression of the number of workers on the number of adults:

    ln(workers_s) = a_district(s) + b Park_s + lam ln(adults_s) [+ X_s g] + e_s

  workers  Census-weighted count of workers by industry of main work: non-farm, services, farm (OLS on logs; wild cluster
           bootstrap p); tourism (Poisson with a log link, because some sectors have none; cluster-robust normal p).
  adults   residents aged 16+ (Census-weighted), with a free coefficient lam (an elasticity; 1 would mean workers scale with population).
  Park_s   1 if the sector borders a national park (62 of 381 sectors outside Kigali City).
  FE       district (27): the comparison is between park-adjacent and interior sectors of the same district. Q2 uses nearest-park FE.
  b        proportional difference in workers between park-adjacent and interior sectors at the same population; 100*(exp(b)-1) = % difference.

Controls X (six sector characteristics, z-scored over the 381 sectors; none is an outcome of tourism)
    log area (km2)                                   model_sector_cross.csv, unit_km2
    log distance to the nearest trunk/primary road   data/geo-data/roads/sector_distances.csv (OSM snapshot)
    log distance to Kigali                           same file
    mean elevation (m), mean slope (degrees)         data/geo-data/raster/sector_terrain.csv (DEM)
    mean annual rainfall (mm, CHIRPS 1981-2002)      data/geo-data/raster/sector_rainfall.csv
  Not used: building footprints and grid length (recent snapshots, partly outcomes of tourism and settlement).
  Every regression has two columns: (1) without X, (2) with X.

Questions
  Q1  Park-adjacent vs interior labour mix, per Census wave. Terms: Park. Outcomes: non-farm, services, tourism, farm workers.
  Q2  Distance to the nearest of four park gates (centroid to gate, km): bins under 10, 10-20, 20-40 (40+ omitted), per wave.
      Same outcomes; nearest-park FE instead of district FE; column (2) adds Park. Controls: ln(adults), X.
  Q3  Exposure to park tourism, per wave. Term: E_s = nearest park's share of three-park visits 2005-2019 (Volcanoes .40,
      Akagera .46, Nyungwe .14), 0 for interior sectors; 361 sectors (Gishwati-Mukura has no visit data). Same outcomes, district FE.
  Q4  Land use, per land-cover year (2000, 2010, 2020). Term: Park. Outcomes: cropland share and built-up share of usable land
      (percentage points, GLAD), ln(1 + built-up hectares, GHSL). Level regressions (no ln adults); district FE.

Standard errors are clustered by district (27). Sample: the 381 sectors outside Kigali City (--drop-ring: the 299 that remain
without the 82 sectors touching a park-adjacent sector). A district or nearest-park group with no workers is dropped from the
tourism Poisson regressions. The 2022 farm count is affected by the change in what counts as work, which is common to all
sectors within a cross-section, so Q1-Q3 compare sectors within a wave.

Usage
    python micro-analysis/census_park_questions.py
    python micro-analysis/census_park_questions.py --drop-ring
    python micro-analysis/census_park_questions.py --only Q1 Q4
Output: output/tables/regressions/census_park_questions[_no_ring].csv
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
sys.path.insert(0, str(ROOT / "results-scripts"))
import paths as P  # noqa: E402
from regression import fe_ols  # noqa: E402
import census_park_regressions as C  # noqa: E402  (PANEL, SECTORS, KIGALI, ring_sectors)
import park_land_regressions as L  # noqa: E402  (sectors with exposure E_s, land_panel)
import sector_gate_plots as G  # noqa: E402  (hav, TG.GATE_XY: distance from centroid to the nearest gate)

XVARS = ["log_area", "log_dist_road", "log_dist_kigali", "elev_mean", "slope_mean", "rain_mean"]
X_LABEL = "log area, log distance to road, log distance to Kigali, elevation, slope, rainfall (z-scored)"
INDUSTRY = [("nonfarm", "Non-farm workers"), ("services", "Services workers"), ("tourism", "Tourism workers"), ("farm", "Farm workers")]
LAND = [("crop_pp", "Cropland share (pp)"), ("built_pp", "Built-up share (pp)"), ("log_built", "ln(1 + built-up ha)")]
BINS = [("gate_lt10", 0, 10), ("gate_10_20", 10, 20), ("gate_20_40", 20, 40)]
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


def census(x, ring, drop_ring) -> pd.DataFrame:
    d = pd.read_csv(C.PANEL)[["sid", "wave", "adults", "nonfarm", "services", "tourism", "farm"]]
    d = d.merge(x, on="sid", validate="m:1")
    d["log_adults"] = np.log(d.adults)
    return d[~d.sid.isin(ring)].copy() if drop_ring else d


# ---------------------------------------------------------------------------- estimators
def ols(d, y, xs, fes, test):
    est, n, g = fe_ols(d, y, xs, fes, "district_id", test=test)
    return est.rename(columns={"p_wcb": "p"}), n, g


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
    return r, int(len(d)), d.district_id.nunique()


def record(q, spec, y, label, est, n, g, focal, kind, ptype, controls_, fe, wave):
    for t in focal:
        e = est.loc[t]
        ROWS.append({"question": q, "spec": spec, "outcome": y, "label": label, "estimator": kind, "p_type": ptype, "term": t,
                     "wave": wave, "coef": e.coef, "se": e.se, "p": e.p, "log_adults_coef": est.loc["log_adults", "coef"] if "log_adults" in est.index else np.nan,
                     "obs": n, "clusters": g, "controls": controls_, "fixed_effects": fe})
    print(f"[questions]   {wave} | {spec} | {label} ({kind}): " + ", ".join(f"{t} {est.loc[t,'coef']:+.3f} [{est.loc[t,'p']:.3f}]" for t in focal), flush=True)


def run_count(d, y, label, q, spec, terms, ctrl, fes, controls_, wave):
    """Count outcome, per wave: OLS on ln(y) (bootstrap p) if y > 0 everywhere, otherwise Poisson."""
    xs = terms + ["log_adults"] + ctrl
    if (d[y] > 0).all():
        est, n, g = ols(d.assign(ln_y=np.log(d[y])), "ln_y", xs, fes, terms)
        record(q, spec, y, label, est, n, g, terms, "OLS on ln(workers)", "wild cluster bootstrap", controls_, "+".join(fes), wave)
    else:
        est, n, g = poisson(d, y, xs, fes)
        record(q, spec, y, label, est, n, g, terms, "Poisson", "cluster-robust normal", controls_, "+".join(fes), wave)


# ---------------------------------------------------------------------------- questions
def q1(x, ring, drop_ring):
    print("[questions] Q1 per wave: ln workers on Park, ln adults, district FE [+ X]", flush=True)
    d = census(x, ring, drop_ring)
    for t in C.WAVES:
        w = d[d.wave == t]
        print(f"[questions]  Q1 {t}: {len(w)} sectors ({int(w.border.sum())} park-adjacent)", flush=True)
        for spec, ctrl in [("(1) ln adults", []), ("(2) ln adults + X", XVARS)]:
            for y, lab in INDUSTRY:
                run_count(w, y, lab, "Q1", spec, ["border"], ctrl, ["district_id"], "ln(adults)" + (f"; {X_LABEL}" if ctrl else ""), t)


def q2(x, ring, drop_ring):
    print("[questions] Q2 per wave: gate-distance bins, nearest-park FE", flush=True)
    d = census(x, ring, drop_ring)
    terms = [b[0] for b in BINS]
    for t in C.WAVES:
        w = d[d.wave == t]
        print(f"[questions]  Q2 {t}: {len(w)} sectors; " + ", ".join(f"{b[0]} {int(w[b[0]].sum())}" for b in BINS), flush=True)
        for spec, tm in [("(1) bins", terms), ("(2) bins + Park", terms + ["border"])]:
            for y, lab in INDUSTRY:
                run_count(w, y, lab, "Q2", spec, tm, XVARS, ["nearest_park"], f"ln(adults); {X_LABEL}", t)


def q3(x, ring, drop_ring):
    print("[questions] Q3 per wave: visit-share exposure E_s, district FE [+ X]", flush=True)
    s = L.sectors()[["sid", "exposure", "gm"]]
    d = census(x, ring, drop_ring).merge(s, on="sid", validate="m:1")
    d = d[d.gm == 0]
    for t in C.WAVES:
        w = d[d.wave == t]
        print(f"[questions]  Q3 {t}: {len(w)} sectors (Gishwati-Mukura dropped)", flush=True)
        for spec, ctrl in [("(1) ln adults", []), ("(2) ln adults + X", XVARS)]:
            for y, lab in INDUSTRY:
                run_count(w, y, lab, "Q3", spec, ["exposure"], ctrl, ["district_id"], "ln(adults)" + (f"; {X_LABEL}" if ctrl else ""), t)


def q4(x, ring, drop_ring):
    print("[questions] Q4 per land-cover year: land outcomes on Park, district FE [+ X]", flush=True)
    d = L.land_panel()
    d = d[d.year.isin((2000, 2010, 2020))].drop(columns=["border", "district_id", "nearest_park"]).merge(
        x[["sid", "district_id", "border", "nearest_park"] + XVARS], on="sid", validate="m:1")
    d = d[~d.sid.isin(ring)] if drop_ring else d
    for t in (2000, 2010, 2020):
        w = d[d.year == t]
        print(f"[questions]  Q4 {t}: {len(w)} sectors ({int(w.border.sum())} park-adjacent)", flush=True)
        for spec, ctrl in [("(1) none", []), ("(2) X", XVARS)]:
            for y, lab in LAND:
                est, n, g = ols(w, y, ["border"] + ctrl, ["district_id"], ["border"])
                record("Q4", spec, y, lab, est, n, g, ["border"], "OLS, level", "wild cluster bootstrap",
                       "none" + "" if not ctrl else X_LABEL, "district_id", t)


QUESTIONS = {"Q1": q1, "Q2": q2, "Q3": q3, "Q4": q4}


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--drop-ring", action="store_true")
    a.add_argument("--only", nargs="+", choices=list(QUESTIONS))
    args = a.parse_args(argv)
    x = controls()                                   # z-scored over all 381 sectors, also with --drop-ring
    ring = C.ring_sectors() if args.drop_ring else set()
    print(f"[questions] {len(x[~x.sid.isin(ring)])} sectors{' (ring dropped)' if args.drop_ring else ''}", flush=True)
    for k in (args.only or list(QUESTIONS)):
        QUESTIONS[k](x, ring, args.drop_ring)
    P.TABLES_REG.mkdir(parents=True, exist_ok=True)
    out = P.TABLES_REG / f"census_park_questions{'_no_ring' if args.drop_ring else ''}.csv"
    pd.DataFrame(ROWS).to_csv(out, index=False)
    print(f"[questions] -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
