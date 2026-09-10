"""
coefplot_education_lasso.py -- the education ANCOVA with the control set chosen by PDS lasso.

    python coefplot_education_lasso.py

    output/figures/coefplot_education_lasso.pdf   two panels, one per treatment definition
    Analysis/reg_education_lasso.csv              coefficients, p-values and what was selected

Post-double selection exactly as in coefplot_housing_lasso.py -- park and district fixed effects and
the sector's own 2002 level are always in and never penalised, two cluster-robust rigorous lassos run
on the residuals, one on the outcome and one on the treatment, and the union enters the final least
squares. The penalty is the BCH plug-in with cluster-robust loadings.

What differs is the candidate pool. The housing set of 53 baseline controls carries demographics,
resettlement, language, religion, 2002 housing, terrain, access and rainfall, but nothing about the
sector's schooling in 2002 beyond the outcome's own level. Five education baselines are added here
(Matteo, 2026-09-08), because the concern these regressions have to answer is precisely that
park-adjacent sectors started from a different educational position:

    edu02_years        mean years of schooling, adults 20+
    edu02_primary      share who completed primary
    edu02_literacy     share literate
    edu02_secondary    share who reached secondary or above
    edu02_attend617    share of children 6-17 who had ever attended school

The outcome's OWN 2002 level is dropped from the candidates for that outcome, since it is already in
the regression unpenalised as the ANCOVA baseline. With 57 levels the pool is 57 levels, 57 squares
and 1,596 pairwise products, 1,710 terms against roughly 350 sectors.

A warning about what this can and cannot do. Richer baseline controls narrow the gap between treated
and control sectors at the STARTING LINE. They cannot establish that the two groups were on the same
TRAJECTORY, because every one of these variables is measured once, in 2002. The cohort exposure design
is what tests trajectories; this is what tests levels.
"""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

import bar_chart_education as E
import bar_chart_housing as B
import build_controls as CTL
import coefplot_education as EM
import coefplot_housing_lasso as L

FIG, ANALYSIS = B.FIG, B.ANALYSIS
OUTCOMES = EM.OUTCOMES
WAVES = EM.WAVES


def control_list(outcome):
    """the housing 53 plus the education baselines, less this outcome's own baseline"""
    extra = [c for c in E.EDU_CONTROLS if c != E.OWN_BASE.get(outcome)]
    return list(CTL.CONTROLS) + extra


def candidates(s, controls):
    A = s[controls].values.astype(float)
    cols, names = [A, A ** 2], list(controls) + [f"{c}^2" for c in controls]
    for i in range(len(controls)):
        for j in range(i + 1, len(controls)):
            cols.append((A[:, i] * A[:, j])[:, None])
            names.append(f"{controls[i]}x{controls[j]}")
    X = np.column_stack(cols)
    keep = X.std(axis=0, ddof=1) > 1e-8
    X, names = X[:, keep], [n for n, k in zip(names, keep) if k]
    return (X - X.mean(axis=0)) / X.std(axis=0, ddof=1), names


def select_and_fit(d, waves, fe, controls):
    s = d[d.wave.isin(waves)].reset_index(drop=True)
    F = np.column_stack([pd.get_dummies(s[fe]).values.astype(float),
                         pd.get_dummies(s.park, drop_first=True).values.astype(float),
                         s.base.values])
    X, names = candidates(s, controls)
    Xr = L.residualise(X, F)
    Xr = Xr / np.maximum(Xr.std(axis=0, ddof=1), 1e-12)
    yr = L.residualise(s.y.values[:, None], F)[:, 0]
    dr = L.residualise(s.treat.values.astype(float)[:, None], F)[:, 0]
    cl = s.sid.values
    union = sorted(set(L.rlasso(Xr, yr, cl)) | set(L.rlasso(Xr, dr, cl)))
    sub = s.copy()
    for k, i in enumerate(union):
        sub[f"z{k}"] = X[:, i]
    f = f"y ~ treat + base + C(park) + C({fe})" + "".join(f" + z{k}" for k in range(len(union)))
    r = smf.ols(f, data=sub).fit(cov_type="cluster", cov_kwds={"groups": sub.sid})
    b, se = r.params["treat"], r.bse["treat"]
    return {"b": b, "se": se, "p": r.pvalues["treat"], "lo90": b - 1.645 * se,
            "hi90": b + 1.645 * se, "n": int(r.nobs), "clusters": sub.sid.nunique(),
            "k_selected": len(union), "n_candidates": len(names),
            "selected": "; ".join(names[i] for i in union)}


def prepare():
    g, T, X, never = B.geography()
    p = pd.read_csv(ANALYSIS / "census_sector_education_panel.csv")
    ctrl = set(p.sid.unique()) - never - X["Kigali all + cities"]
    z = pd.read_csv(ANALYSIS / "census_sector_controls_2002.csv")
    for c in CTL.CONTROLS:
        z[c] = (z[c] - z[c].mean()) / z[c].std(ddof=1)
    g = g.assign(park=g.nearest_park.astype(str).str.split().str[0])
    p = p.merge(g[["sid", "district", "park"]], on="sid", how="left").merge(z, on="sid", how="left")
    for c in E.EDU_CONTROLS:                                  # z-scored like the rest
        p[c] = (p[c] - p[c].mean()) / p[c].std(ddof=1)
    return g, T, ctrl, p


def main():
    g, T, ctrl, p = prepare()
    rows = []
    for tn, tset in T.items():
        for o in OUTCOMES:
            controls = control_list(o)
            d = EM.frame(p, tset, ctrl, o).dropna(subset=controls)
            for yr, waves, fe in WAVES:
                r = select_and_fit(d, waves, fe, controls)
                rows.append({"treatment": tn, "n_treated": len(tset), "outcome": o, "wave": yr, **r})
                print(f"  {tn:20s} {o:9s} {yr:6s} b={r['b']:+.3f} p={r['p']:.3f} "
                      f"k={r['k_selected']:2d}/{r['n_candidates']}")
    res = pd.DataFrame(rows)
    res.to_csv(ANALYSIS / "reg_education_lasso.csv", index=False)
    EM.draw(res, T, FIG / "coefplot_education_lasso.pdf",
            "Education: ANCOVA with controls chosen by cluster-robust post-double-selection lasso",
            EM.note("Controls beyond those are chosen by post-double-selection lasso from 1,710 candidate "
                    "terms: 57 sector characteristics measured in 2002, their squares and every pairwise "
                    "product, among them five baseline education measures. "))
    print("\nwritten:", FIG / "coefplot_education_lasso.pdf")


if __name__ == "__main__":
    main()
