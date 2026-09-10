"""
housing_inference.py -- the housing result under inference that takes the geography seriously.

    python housing_inference.py

    Analysis/reg_housing_inference.csv    every treatment, outcome and wave, under five p-values

Clustering at sector is not enough, and in the single-wave regressions it is nothing at all: there
is one row per sector, so a sector cluster is a cluster of one and the estimator collapses to
heteroskedasticity-robust. Meanwhile treatment is organised around three or four parks, so
neighbouring treated sectors share whatever the park does to them and the number of independent
units is nearer the number of parks than the 416 sectors. Four alternatives are therefore reported:

  conley50, conley100   Conley spatial HAC, uniform kernel, 50 km and 100 km cutoffs on sector
                        centroids. Lets nearby sectors' errors correlate regardless of district.
  wild_district         wild cluster bootstrap, Rademacher weights, imposing the null, resampled at
                        DISTRICT level. Few clusters, which is the point: 30 districts is closer to
                        the real number of independent shocks than 416 sectors.
  ri_block              randomization inference that respects contiguity. The earlier version
                        reassigned scattered individual sectors, which no real park would ever do;
                        this grows a connected blob of the same size from a random seed, so the
                        placebo treatments look like the actual one.

Multiplicity. Correction is OFF for now (MHT = False): premature while the outcome set and the
specification are still in motion. The Romano-Wolf stepdown of List, Shaikh and Xu (2019) and a Holm
column are implemented below and come back by flipping that flag. The primary outcome is still fixed
in advance -- the housing INDEX at the POOLED wave, one test per treatment -- because designating it
costs nothing and is what any correction would later be applied to.
"""
import sys
import warnings
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.stats import norm as N

import bar_chart_housing as B
import build_controls as CTL
import coefplot_housing_lasso as L

warnings.filterwarnings("ignore")
REPS_WILD, REPS_RI = 999, 2000
SEED = 20260908
PRIMARY = ("index", "pooled")
# Multiple-hypothesis correction is written and tested but switched off (Matteo, 2026-09-08): it is
# premature while the outcome set and the specification are still moving. Set MHT = True to bring
# back the Romano-Wolf stepdown and the Holm column; nothing else needs changing.
MHT = False


# ------------------------------------------------------------------ geography for the inference
def centroids_and_adjacency():
    g = gpd.read_file(B.GEO / "protected-areas/sectors_park_exposure_wdpa.gpkg")
    g["sid"] = g.sector_id.astype(int)
    g = g.sort_values("sid").reset_index(drop=True)
    m = g.to_crs(32736)
    xy = np.column_stack([m.geometry.centroid.x.values, m.geometry.centroid.y.values]) / 1000
    nb = {int(s): set() for s in g.sid}
    sindex = m.sindex
    for i, geom in enumerate(m.geometry):
        for j in sindex.query(geom, predicate="touches"):
            if i != j:
                nb[int(g.sid[i])].add(int(g.sid[j]))
    return dict(zip(g.sid.astype(int), xy)), nb


def conley(y, X, resid, xy, cutoff_km):
    """spatial HAC over sector centroids, Bartlett kernel out to cutoff_km.

    Bartlett rather than uniform: a uniform kernel does not guarantee a positive semi-definite
    variance matrix and it produced negative variances here, which is where the missing standard
    errors came from. The triangular weight declines to zero at the cutoff and is always PSD."""
    n, k = X.shape
    XtX_inv = np.linalg.pinv(X.T @ X)
    d = np.sqrt(((xy[:, None, :] - xy[None, :, :]) ** 2).sum(-1))
    W = np.maximum(0.0, 1.0 - d / cutoff_km)
    u = X * resid[:, None]
    meat = u.T @ W @ u
    V = XtX_inv @ meat @ XtX_inv
    return np.sqrt(np.diag(V) * n / max(n - k, 1))


def wild_cluster_p(y, X, groups, j, rng, reps=REPS_WILD):
    """wild bootstrap-t at the group level, imposing the null on the coefficient of interest"""
    keep = [c for c in range(X.shape[1]) if c != j]
    b_full = np.linalg.lstsq(X, y, rcond=None)[0]
    t_obs = b_full[j] / max(_robust_se(y, X, groups)[j], 1e-12)
    Xr = X[:, keep]
    br = np.linalg.lstsq(Xr, y, rcond=None)[0]
    e0 = y - Xr @ br                                   # residuals under the null
    fit0 = Xr @ br
    gs = pd.factorize(groups)[0]
    G = gs.max() + 1
    t_star = np.empty(reps)
    for r in range(reps):
        w = rng.choice([-1.0, 1.0], size=G)[gs]        # Rademacher, constant within a cluster
        ys = fit0 + e0 * w
        bs = np.linalg.lstsq(X, ys, rcond=None)[0]
        t_star[r] = bs[j] / max(_robust_se(ys, X, groups)[j], 1e-12)
    return float((np.abs(t_star) >= abs(t_obs)).mean())


def _robust_se(y, X, groups):
    n, k = X.shape
    b = np.linalg.lstsq(X, y, rcond=None)[0]
    e = y - X @ b
    XtX_inv = np.linalg.pinv(X.T @ X)
    meat = np.zeros((k, k))
    for _, idx in pd.Series(range(n)).groupby(pd.factorize(groups)[0]):
        i = idx.values
        s = X[i].T @ e[i]
        meat += np.outer(s, s)
    V = XtX_inv @ meat @ XtX_inv
    return np.sqrt(np.maximum(np.diag(V), 0))


def components(treated, nb):
    """the treated set broken into its connected pieces, which is what actually got assigned"""
    s, seen, out = set(treated), set(), []
    for x in s:
        if x in seen:
            continue
        stack, c = [x], set()
        while stack:
            v = stack.pop()
            if v in c:
                continue
            c.add(v); seen.add(v)
            stack += [w for w in nb.get(v, ()) if w in s and w not in c]
        out.append(c)
    return sorted(out, key=len, reverse=True)


def grow(nb, pool, k, rng, taken):
    """one connected blob of k sectors, avoiding anything already used in this draw"""
    avail = set(pool) - taken
    for _ in range(80):
        if not avail:
            break
        seed = int(rng.choice(sorted(avail)))
        blob, frontier = {seed}, set(nb.get(seed, ())) & avail
        while len(blob) < k and frontier:
            nxt = int(rng.choice(sorted(frontier)))
            blob.add(nxt)
            frontier |= (set(nb.get(nxt, ())) & avail) - blob
            frontier.discard(nxt)
        if len(blob) == k:
            return blob
    return set(rng.choice(sorted(avail or pool), size=min(k, len(avail or pool)), replace=False))


def block_draw(nb, pool, sizes, rng):
    """a placebo with the SAME shape as the real treatment: same number of connected pieces, same
    sizes. Drawing one blob of 42 when the treatment is three blobs of 23, 11 and 8 is the wrong
    null, and so is drawing one blob of 4 when the four gate sectors are four isolated singletons
    sitting on three different parks."""
    taken, out = set(), set()
    for k in sizes:
        b = grow(nb, pool, k, rng, taken)
        taken |= b
        out |= b
    return out


def ri_block_p(d, treated, waves, fe, chosen, nb, rng, reps=REPS_RI):
    s = d[d.wave.isin(waves)].reset_index(drop=True)
    blocks = [pd.get_dummies(s[fe]).values.astype(float), s.base.values[:, None]]
    if chosen is not None and chosen.shape[1]:
        blocks.append(chosen)
    M = np.column_stack(blocks)
    U, sv, _ = np.linalg.svd(M, full_matrices=False)
    U = U[:, sv > sv.max() * 1e-10]
    proj = lambda v: v - U @ (U.T @ v)
    ys = proj(s.y.values)
    sids = s.sid.values
    pool = sorted(set(sids))
    k = len(set(treated) & set(pool))

    def beta(t):
        a = proj(np.isin(sids, list(t)).astype(float))[:, None]
        return float(np.linalg.lstsq(a, ys, rcond=None)[0][0])

    obs = beta(treated)
    null = np.array([beta(block_draw(nb, pool, k, rng)) for _ in range(reps)])
    return obs, max(float((np.abs(null) >= abs(obs)).mean()), 1 / reps)


def romano_wolf(fam, sids, rng, reps=2000):
    """Romano-Wolf stepdown as implemented for economics by List, Shaikh and Xu (2019).

    Holm is the wrong tool for this family. It is valid under any dependence, which is exactly why
    it is wasteful when the dependence is strong and known: our six outcomes are five housing
    components plus an index that is their average, so the test statistics move together almost
    mechanically. Holm charges the full Bonferroni price for the smallest p as if they were
    unrelated.

    The bootstrap instead reproduces that dependence. One draw of Rademacher weights, applied at
    sector level, is used for EVERY outcome in the same replication, so the joint distribution of
    the six statistics is resampled rather than assumed. The stepdown then compares the largest
    observed statistic to the bootstrap distribution of the maximum, removes it, and repeats on
    what is left. Family-wise error is controlled, and with correlated outcomes the adjusted
    p-values are far smaller than Holm's.

    fam: list of (name, y, X, j) -- one entry per outcome, sharing the same sectors."""
    names = [f[0] for f in fam]
    m = len(fam)
    gidx = pd.factorize(sids)[0]
    G = gidx.max() + 1
    pre, t_obs = [], np.empty(m)
    for i, (_, y, X, j) in enumerate(fam):
        XtX_inv = np.linalg.pinv(X.T @ X)
        P = XtX_inv @ X.T
        keep = [c for c in range(X.shape[1]) if c != j]
        Xr = X[:, keep]
        br = np.linalg.lstsq(Xr, y, rcond=None)[0]
        e0, fit0 = y - Xr @ br, Xr @ br              # residuals with the treatment set to zero
        b = P @ y
        t_obs[i] = abs(b[j] / max(_se_from(X, XtX_inv, y - X @ b, gidx, G)[j], 1e-12))
        pre.append((X, XtX_inv, P, j, fit0, e0))
    tmax = np.empty((reps, m))
    for r in range(reps):
        w = rng.choice([-1.0, 1.0], size=G)[gidx]    # ONE draw, shared across all outcomes
        for i, (X, XtX_inv, P, j, fit0, e0) in enumerate(pre):
            ys = fit0 + e0 * w
            b = P @ ys
            se = _se_from(X, XtX_inv, ys - X @ b, gidx, G)[j]
            tmax[r, i] = abs(b[j] / max(se, 1e-12))
    order = np.argsort(-t_obs)                        # largest statistic first
    adj = np.empty(m)
    run = 0.0
    for step, i in enumerate(order):
        rest = order[step:]
        pv = float((tmax[:, rest].max(axis=1) >= t_obs[i]).mean())
        run = max(run, pv)                            # monotone, as the procedure requires
        adj[i] = min(run, 1.0)
    return dict(zip(names, adj))


def _se_from(X, XtX_inv, e, gidx, G):
    """cluster-robust standard errors, vectorised.

    This sits inside the Romano-Wolf bootstrap and is called a few hundred thousand times, so the
    cluster sums are accumulated with one scatter-add rather than a groupby. When every cluster
    holds a single row -- which is the case in the single-wave regressions -- the scatter is the
    identity and the meat matrix is just U'U."""
    u = X * e[:, None]
    if G == len(u):
        meat = u.T @ u
    else:
        S = np.zeros((G, X.shape[1]))
        np.add.at(S, gidx, u)
        meat = S.T @ S
    V = XtX_inv @ meat @ XtX_inv
    return np.sqrt(np.maximum(np.diag(V), 0))


def holm(pvals):
    p = np.asarray(pvals, float)
    order = np.argsort(p)
    m = len(p)
    adj = np.empty(m)
    run = 0.0
    for rank, i in enumerate(order):
        run = max(run, (m - rank) * p[i])
        adj[i] = min(run, 1.0)
    return adj


# ------------------------------------------------------------------ the run
def design(d, waves, fe, chosen=None):
    """outcome, design matrix with fixed effects and the 2002 level, and the treatment column index"""
    s = d[d.wave.isin(waves)].reset_index(drop=True)
    fe_d = pd.get_dummies(s[fe], drop_first=True).values.astype(float)
    pk = pd.get_dummies(s.park, drop_first=True).values.astype(float)
    cols = [np.ones((len(s), 1)), s.treat.values[:, None], s.base.values[:, None], fe_d, pk]
    if chosen is not None and chosen.shape[1]:
        cols.append(chosen)
    return s, np.column_stack(cols), s.y.values, 1


def main():
    rng = np.random.default_rng(SEED)
    xy_map, nb = centroids_and_adjacency()
    g, T, ctrl, p = L.prepare()
    blobs = {}                                            # placebo blobs, reused across outcomes
    rows = []
    fams = {}                                             # (treatment, wave, spec) -> outcome designs
    for tn, tset in T.items():
        for o in L.OUTCOMES:
            d = L.frame(p, tset, ctrl, o)
            for yr, waves, fe in L.WAVES:
                sub = d[d.wave.isin(waves)]
                for spec in ("main", "lasso"):
                    chosen = None
                    if spec == "lasso":
                        _, s_l, chosen = L.select_and_fit(d, waves, fe)
                    s, X, y, j = design(d, waves, fe, chosen)
                    b = np.linalg.lstsq(X, y, rcond=None)[0]
                    resid = y - X @ b
                    se_cl = _robust_se(y, X, s.sid.values)[j]
                    r = {"treatment": tn, "outcome": o, "wave": yr, "spec": spec,
                         "b": b[j], "se_cluster": se_cl, "n": len(s),
                         "k_selected": 0 if chosen is None else chosen.shape[1]}
                    r["p_cluster"] = 2 * (1 - N.cdf(abs(b[j] / max(se_cl, 1e-12))))
                    xy = np.array([xy_map[int(v)] for v in s.sid.values])
                    for cut in (25, 50, 100):             # Conley is cheap: every outcome gets it
                        se = conley(y, X, resid, xy, cut)[j]
                        r[f"se_conley{cut}"] = se
                        r[f"p_conley{cut}"] = 2 * (1 - N.cdf(abs(b[j] / max(se, 1e-12))))
                    if o == "index":                      # the slow battery only for the primary
                        r["p_wild_district"] = wild_cluster_p(y, X, s.district.values, j, rng)
                        key = (tn, yr)
                        if key not in blobs:
                            pool = sorted(set(s.sid.values))
                            sizes = [len(c) for c in components(set(tset) & set(pool), nb)]
                            blobs[key] = [block_draw(nb, pool, sizes, rng) for _ in range(1000)]
                        _, r["p_ri_block"] = _ri_with(blobs[key], d, tset, waves, fe, chosen)
                    fams.setdefault((tn, yr, spec), []).append((o, y, X, j, s.sid.values))
                    rows.append(r)
                    print(f"  {tn:10s} {o:15s} {yr:7s} {spec:6s} b={b[j]:+.3f}")
    res = pd.DataFrame(rows)
    # Multiplicity within each treatment, wave and specification, over the family of six outcomes.
    # Romano-Wolf is the reported correction; Holm is kept alongside to show what assuming arbitrary
    # dependence costs when the outcomes are in fact strongly dependent.
    if MHT:
        print("\nRomano-Wolf stepdown, 2,000 bootstrap draws per family")
        for (tn, yr, spec), grp in res.groupby(["treatment", "wave", "spec"]):
            res.loc[grp.index, "p_holm"] = holm(grp.p_cluster.values)
            fam = fams.get((tn, yr, spec), [])
            if fam:
                rw = romano_wolf([(o, y, X, j) for o, y, X, j, _ in fam], fam[0][4],
                                 np.random.default_rng(SEED))
                res.loc[grp.index, "p_rw"] = grp.outcome.map(rw).values
            print(f"  {tn:10s} {yr:7s} {spec:6s} done")
    res.to_csv(CTL.ANALYSIS / "reg_housing_inference.csv", index=False)
    print("\n->", CTL.ANALYSIS / "reg_housing_inference.csv")
    return res


def _ri_with(blobs, d, treated, waves, fe, chosen):
    s = d[d.wave.isin(waves)].reset_index(drop=True)
    cols = [pd.get_dummies(s[fe]).values.astype(float),
            pd.get_dummies(s.park, drop_first=True).values.astype(float), s.base.values[:, None]]
    if chosen is not None and chosen.shape[1]:
        cols.append(chosen)
    M = np.column_stack(cols)
    U, sv, _ = np.linalg.svd(M, full_matrices=False)
    U = U[:, sv > sv.max() * 1e-10]
    proj = lambda v: v - U @ (U.T @ v)
    ys = proj(s.y.values)
    sids = s.sid.values

    def beta(t):
        a = proj(np.isin(sids, list(t)).astype(float))[:, None]
        return float(np.linalg.lstsq(a, ys, rcond=None)[0][0])

    obs = beta(treated)
    null = np.array([beta(bl) for bl in blobs])
    return obs, max(float((np.abs(null) >= abs(obs)).mean()), 1 / len(blobs))


if __name__ == "__main__":
    main()
