"""
district_models.py — district-year regressions with cluster-robust inference.

The household and firm side of this project cannot go below district: the LFS,
EICV and AHS are anonymised to district, and only the Census reaches sector. So
the labour panel is 30 districts x 9 years = 270 observations, and everything
here is built around that being a SMALL panel.

    python district-level-analysis/district_models.py --all
    python district-level-analysis/district_models.py --only tourism_forest
    python district-level-analysis/district_models.py --list

Inference
---------
Default is cluster-robust by district (CR1), which is the right cluster level:
treatment (park exposure) varies across districts, and the errors of a district
are serially correlated across years.

WITH 30 CLUSTERS, THE ASYMPTOTICS DO NOT HOLD. Cameron, Gelbach & Miller (2008)
put the rule of thumb at ~50 clusters; 30 over-rejects, sometimes badly. Every
model therefore reports, side by side:

    cluster    CR1 cluster-robust, t(G-1) critical values
    wild       wild cluster bootstrap-t, Rademacher weights, null imposed

The wild bootstrap is the one to quote. Where the two disagree the bootstrap
p-value is the honest one, and a coefficient that is significant on CR1 alone
should be reported as suggestive, not as a finding.

Nothing here is causal. These are conditional correlations on 270 observations
with no design; they are for memos and for deciding what is worth pursuing.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import paths as P

import numpy as np
import pandas as pd

RNG = np.random.default_rng(20260907)
B_BOOT = 1999          # bootstrap replications; odd, so percentiles are exact ranks
MIN_CLUSTERS = 50      # below this, lean on the bootstrap rather than CR1

# Set by --no-bootstrap. Module-level so the model functions, which take no
# arguments, do not each need the flag threaded through them.
BOOTSTRAP = True


def _log(m: str) -> None:
    print(f"[models] {m}", flush=True)


# --------------------------------------------------------------------------
# Estimation
# --------------------------------------------------------------------------

def ols(y: np.ndarray, X: np.ndarray):
    """Plain OLS by least squares. Returns (beta, residuals, XtX_inv)."""
    xtx_inv = np.linalg.pinv(X.T @ X)
    beta = xtx_inv @ X.T @ y
    return beta, y - X @ beta, xtx_inv


def cluster_vcov(X: np.ndarray, resid: np.ndarray, groups: np.ndarray,
                 xtx_inv: np.ndarray) -> np.ndarray:
    """CR1 cluster-robust covariance (Liang-Zeger with the Stata finite-sample
    correction). Meat is summed over clusters, so within-cluster serial
    correlation of any form is allowed."""
    n, k = X.shape
    uniq = np.unique(groups)
    g = len(uniq)
    meat = np.zeros((k, k))
    for cl in uniq:
        m = groups == cl
        s = X[m].T @ resid[m]
        meat += np.outer(s, s)
    c = (g / (g - 1)) * ((n - 1) / (n - k))
    return c * (xtx_inv @ meat @ xtx_inv)


def wild_cluster_bootstrap(y, X, groups, j: int, b_reps: int = B_BOOT) -> float:
    """Wild cluster bootstrap-t p-value for H0: beta[j] == 0.

    The null is imposed — the restricted model is re-estimated without column
    j and residuals are drawn from it — which is what makes the procedure work
    with few clusters. Rademacher weights are applied at the CLUSTER level, one
    draw per district, not per observation.
    """
    n, k = X.shape
    beta, resid, xtx_inv = ols(y, X)
    se = np.sqrt(np.diag(cluster_vcov(X, resid, groups, xtx_inv)))
    t_obs = beta[j] / se[j]

    keep = [c for c in range(k) if c != j]
    Xr = X[:, keep]
    beta_r, resid_r, _ = ols(y, Xr)
    y_hat_r = Xr @ beta_r

    uniq = np.unique(groups)
    idx = {cl: (groups == cl) for cl in uniq}

    count = 0
    for _ in range(b_reps):
        w = RNG.choice([-1.0, 1.0], size=len(uniq))
        e = np.empty(n)
        for wi, cl in zip(w, uniq):
            e[idx[cl]] = resid_r[idx[cl]] * wi
        y_b = y_hat_r + e
        b_b, r_b, xi_b = ols(y_b, X)
        se_b = np.sqrt(np.diag(cluster_vcov(X, r_b, groups, xi_b)))
        if abs(b_b[j] / se_b[j]) >= abs(t_obs):
            count += 1
    return (count + 1) / (b_reps + 1)


def fit(df: pd.DataFrame, y: str, xs: list[str], cluster: str = "dist",
        fe: list[str] | None = None, bootstrap: bool | None = None) -> pd.DataFrame:
    """OLS with optional fixed effects, CR1 SEs and a wild bootstrap p-value."""
    bootstrap = BOOTSTRAP if bootstrap is None else bootstrap
    # Deduplicate: the cluster variable is often also a fixed effect (district
    # FE clustered by district). Selecting it twice makes df[cluster] return a
    # DataFrame rather than a Series, and the cluster loop then indexes the
    # wrong axis.
    need = list(dict.fromkeys([y] + xs + [cluster] + (fe or [])))
    d = df[need].dropna()
    if d.empty:
        raise ValueError(f"no rows left after dropna for {y}")

    parts = [np.ones((len(d), 1)), d[xs].to_numpy(float)]
    names = ["const"] + list(xs)
    for f in fe or []:
        dummies = pd.get_dummies(d[f].astype("category"), prefix=f, drop_first=True)
        parts.append(dummies.to_numpy(float))
        names += list(dummies.columns)

    X = np.hstack(parts)
    yv = d[y].to_numpy(float)
    groups = d[cluster].to_numpy()

    # A regressor with no variation left after the fixed effects returns a
    # near-zero SE and a t of 1e12. Say so instead of reporting it.
    for i, nm in enumerate(names):
        if nm == "const" or nm not in xs:
            continue
        resid_x = X[:, i] - X[:, [c for c in range(X.shape[1]) if c != i]] @ ols(
            X[:, i], X[:, [c for c in range(X.shape[1]) if c != i]])[0]
        if np.std(resid_x) < 1e-10 * max(np.std(X[:, i]), 1e-12):
            raise ValueError(
                f"{nm!r} has no variation left after the fixed effects "
                f"({','.join(fe or [])}) - the model is not identified")

    beta, resid, xtx_inv = ols(yv, X)
    v = cluster_vcov(X, resid, groups, xtx_inv)
    se = np.sqrt(np.diag(v))
    g = len(np.unique(groups))

    from scipy import stats
    t = beta / se
    p_cl = 2 * (1 - stats.t.cdf(np.abs(t), df=g - 1))     # t(G-1), not normal

    rows = []
    for i, nm in enumerate(names):
        if nm.startswith(tuple(f + "_" for f in (fe or []))):
            continue                                      # don't print every FE
        p_wild = (wild_cluster_bootstrap(yv, X, groups, i)
                  if bootstrap and nm != "const" else np.nan)
        rows.append(dict(term=nm, coef=beta[i], se_cluster=se[i], t=t[i],
                         p_cluster=p_cl[i], p_wild=p_wild))
    out = pd.DataFrame(rows)
    out.attrs.update(n=len(d), clusters=g, y=y,
                     fe=",".join(fe or []) or "none")
    return out


def report(res: pd.DataFrame, title: str) -> None:
    a = res.attrs
    print(f"\n  {title}")
    print(f"    y = {a['y']}   n = {a['n']}   clusters = {a['clusters']}   FE: {a['fe']}")
    if a["clusters"] < MIN_CLUSTERS:
        print(f"    ! {a['clusters']} clusters is below the ~{MIN_CLUSTERS} rule of "
              "thumb: quote p_wild, treat p_cluster as anti-conservative")
    print(res.to_string(index=False, float_format=lambda v: f"{v:9.4f}"))


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------

def load() -> pd.DataFrame:
    """District-year labour panel joined to YEAR-VARYING forest outcomes.

    The forest columns already in district_workers_forest_panel.csv are
    cross-sectional totals — one value per district, repeated across years — so
    any specification with district fixed effects has zero within variation in
    the outcome and returns degenerate standard errors. The year-varying series
    is built here by aggregating the sector-year panel up to district-year.
    """
    d = pd.read_csv(P.GEO / "labour/district_workers_forest_panel.csv")

    s = pd.read_csv(P.GEO / "forest/sector_year_panel.csv")
    fy = (s.groupby(["district_id", "year"])
            .agg(loss_ha_yr=("loss_ha", "sum"),
                 forest_start_yr=("forest_start_ha", "sum"),
                 rain_mm=("rain_mm", "first"), rain_z=("rain_z", "first"))
            .reset_index().rename(columns={"district_id": "dist"}))
    # Land area is fixed, so per-km2 stays comparable across districts while
    # varying over time through the numerator only.
    area = d.groupby("dist").km2.first()
    fy["loss_per_km2_yr"] = fy.loss_ha_yr / fy.dist.map(area)
    fy["hazard_yr"] = np.where(fy.forest_start_yr >= 10,
                               100 * fy.loss_ha_yr / fy.forest_start_yr, np.nan)

    d = d.merge(fy, on=["dist", "year"], how="left")
    d["parkiness"] = d.border_sectors / d.n_sectors
    d["any_park"] = (d.border_sectors > 0).astype(int)
    d["log_pop"] = np.log(d.pop_total.replace(0, np.nan))
    d["tourism_pct"] = d.lfs_isic9_pct                     # accommodation & food
    return d


# --------------------------------------------------------------------------
# Models
# --------------------------------------------------------------------------

def m_tourism_park():
    """Is tourism employment higher in park-bordering districts?

    Descriptive: park exposure is fixed within district, so a district FE would
    absorb it entirely. Year FE only, and the coefficient is a cross-sectional
    contrast — it carries every other way park districts differ.
    """
    d = load()
    return fit(d, "tourism_pct", ["parkiness", "log_pop"], fe=["year"]), \
        "Tourism employment on park exposure"


def m_agriculture_park():
    """The same contrast for agricultural employment, which runs the other way."""
    d = load()
    return fit(d, "lfs_isic1_pct", ["parkiness", "log_pop"], fe=["year"]), \
        "Agricultural employment on park exposure"


def m_tourism_forest():
    """Does forest loss track tourism employment across districts?

    loss_per_km2 is the outcome, not loss_rate: it needs no forest denominator
    and so cannot be driven by the plantation artefact that makes the rate
    measure non-monotone in park distance.
    """
    d = load()
    return fit(d, "loss_per_km2_yr", ["tourism_pct", "lfs_isic1_pct", "log_pop"],
               fe=["year"]), \
        "Forest loss per km2 on employment composition"


def m_within_district():
    """Within-district: does a district's own change in tourism track its loss?

    District FE absorb every fixed difference between places, so this is
    identified off within-district movement over 2017-2025 only. With 30
    districts and 9 years this is a demanding specification and is expected to
    be underpowered — it is here to show what the data cannot support, not to
    be believed if it comes out significant.
    """
    d = load()
    return fit(d, "loss_per_km2_yr", ["tourism_pct"],
               fe=["year", "dist"]), \
        "Forest loss on tourism, district and year FE"


MODELS = {
    "tourism_park": m_tourism_park,
    "agriculture_park": m_agriculture_park,
    "tourism_forest": m_tourism_forest,
    "within_district": m_within_district,
}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--all", action="store_true")
    p.add_argument("--only", nargs="+", choices=list(MODELS))
    p.add_argument("--list", action="store_true")
    p.add_argument("--no-bootstrap", action="store_true",
                   help="skip the wild bootstrap (fast, but CR1 alone over-rejects)")
    a = p.parse_args(argv)

    if a.list:
        for k, f in MODELS.items():
            print(f"  {k:18} {(f.__doc__ or '').strip().splitlines()[0]}")
        return 0
    global BOOTSTRAP
    BOOTSTRAP = not a.no_bootstrap

    todo = list(MODELS) if a.all else (a.only or [])
    if not todo:
        p.print_help()
        return 1

    P.TABLES.mkdir(parents=True, exist_ok=True)
    for k in todo:
        _log(k)
        res, title = MODELS[k]()
        report(res, title)
        res.to_csv(P.TABLES / f"model_{k}.csv", index=False)
        print(f"    -> output/tables/model_{k}.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
