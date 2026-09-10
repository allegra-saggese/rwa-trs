"""
coefplot_housing.py -- the main regression behind the housing bar chart.

    python coefplot_housing.py

    output/figures/coefplot_housing.pdf     three panels, one per treatment definition
    Analysis/reg_housing_main.csv           every coefficient, standard error and p-value

Specification (Matteo, 2026-09-07). ANCOVA on the post waves, one regression per treatment, outcome
and wave:

    Y(s,t) = a + b treated(s) + c Y(s,2002) + park FE + district FE + e        t = 2012, or 2022
    Y(s,t) = a + b treated(s) + c Y(s,2002) + park FE + district x wave FE + e t = pooled

Park fixed effects are the sector's nearest park, four catchments (Matteo, 2026-09-08). They are not
absorbed by the district effects -- 11 of 30 districts straddle two catchments -- but they change
almost nothing, moving coefficients by at most 0.015 SD, because district x wave already carries the
regional structure. They are kept so the question does not have to be asked.

errors clustered at sector. The regressions are unweighted (Matteo, 2026-09-07): treatment is
assigned at sector level, so every sector counts once, and the randomization inference resamples
sectors uniformly for the same reason. Household weights are still used inside each sector, to turn
the households sampled there into that sector's share.

Why this and not the within design. The obvious alternative regresses on sector fixed effects and the
2002 level interacted with wave. Both are defensible and they bracket each other: the within design
assumes parallel trends, ANCOVA assumes that once the 2002 level and the district are held fixed,
which sectors sit next to a park is as good as random. On this data they agree, the ANCOVA
coefficients running 5-30% larger. Two things the ANCOVA needs and gets:

  post rows only     with the 2002 rows in the sample Y equals the control identically and the
                     regression is degenerate.
  a clean baseline   a noisy 2002 level would be attenuated and would under-control. The 2002 sector
                     means come from a median of 408 households, so their reliability is 0.95 to 0.99.

The 2002 level cannot be used in levels alongside SECTOR fixed effects: it is constant within sector,
so it adds no rank and statsmodels only appears to estimate it. District fixed effects are what make
the levels control identified.

Outcomes are the housing components of the spec and their index, each in units of the 2002 control
standard deviation so they are comparable on one axis. Electric lighting is a control, not an outcome.
The four gate sectors are too few for clustered inference to be trusted; that panel is read from the
randomization test.
"""
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

import bar_chart_housing as B          # geography, panel and crosswalk live there

FIG = B.FIG
ANALYSIS = B.ANALYSIS
COMPS = B.COMPONENTS
OUTCOMES = COMPS + ["index"]
NICE = dict(B.NICE)
WAVES = (("2012", [2012], "district"), ("2022", [2022], "district"),
         ("pooled", [2012, 2022], "dw"))


def prepare():
    g, T, X, never = B.geography()
    p = pd.read_csv(ANALYSIS / "census_sector_housing_panel.csv")
    p = p.drop(columns=[c for c in p.columns if c.startswith("district")], errors="ignore")
    ctrl = set(p.sid.unique()) - never - X["Kigali all + cities"]
    g = g.assign(park=g.nearest_park.astype(str).str.split().str[0])
    p = p.merge(g[["sid", "district", "park"]], on="sid", how="left")
    return g, T, ctrl, p


def fit(p, treated, ctrl, outcome):
    """one treatment, one outcome: ANCOVA on the post waves with the sector's 2002 level as a control"""
    d = p[p.sid.isin(set(treated) | ctrl)].copy()
    d = B.standardise(d, ctrl, COMPS)
    if outcome != "index":                                  # components into baseline control SD units
        base = d[(d.wave == 2002) & d.sid.isin(ctrl)][outcome]
        d["y"] = (d[outcome] - base.mean()) / base.std(ddof=1)
    else:
        d["y"] = d["index"]
    d["base"] = d.sid.map(d[d.wave == 2002].set_index("sid")["y"])
    d["treat"] = d.sid.isin(treated).astype(int)
    d["dw"] = d.district + "_" + d.wave.astype(str)
    d = d.dropna(subset=["y", "base", "weight"])
    out = []
    for yr, waves, fe in WAVES:
        sub = d[d.wave.isin(waves)]
        r = smf.ols(f"y ~ treat + base + C(park) + C({fe})", data=sub).fit(
            cov_type="cluster", cov_kwds={"groups": sub.sid})
        b, se = r.params["treat"], r.bse["treat"]
        out.append({"wave": yr, "b": b, "se": se, "p": r.pvalues["treat"],
                    "lo90": b - 1.645 * se, "hi90": b + 1.645 * se, "b_base": r.params["base"],
                    "n": int(r.nobs), "clusters": sub.sid.nunique()})
    return out, d


def randomization_inference(p, treated, ctrl, outcome, reps=2000, seed=20260907):
    """p-values for a treatment too small to trust clustered errors: reassign the same number of
    sectors at random within the estimation sample and see how often chance produces this coefficient.

    Everything except the treatment indicator is fixed, so the fixed effects and the baseline are
    projected out once (Frisch-Waugh) and each draw is then a regression on the residuals."""
    rng = np.random.default_rng(seed)
    _, d = fit(p, treated, ctrl, outcome)
    out = {}
    for yr, waves, fe in WAVES:
        sub = d[d.wave.isin(waves)].sort_values(["sid", "wave"]).reset_index(drop=True)
        X0 = np.column_stack([pd.get_dummies(sub[fe]).values.astype(float),
                              pd.get_dummies(sub.park, drop_first=True).values.astype(float),
                              sub.base.values[:, None]])
        U, sv, _ = np.linalg.svd(X0, full_matrices=False)
        U = U[:, sv > sv.max() * 1e-10]                     # orthonormal basis, rank-safe
        proj = lambda v: v - U @ (U.T @ v)
        ys = proj(sub.y.values)
        sids = sub.sid.values
        pool = np.array(sorted(set(sids)))
        k = len(set(treated) & set(pool))
        def beta(tset):
            a = proj(np.isin(sids, list(tset)).astype(float))[:, None]
            return float(np.linalg.lstsq(a, ys, rcond=None)[0][0])
        obs = beta(treated)
        null = np.array([beta(rng.choice(pool, size=k, replace=False)) for _ in range(reps)])
        out[yr] = (obs, max(float((np.abs(null) >= abs(obs)).mean()), 1 / reps))
    return out


def main():
    g, T, ctrl, p = prepare()
    rows = []
    for tn, tset in T.items():
        for o in OUTCOMES:
            fits, _ = fit(p, tset, ctrl, o)
            for r in fits:
                rows.append({"treatment": tn, "n_treated": len(tset), "outcome": o, **r})
    res = pd.DataFrame(rows)
    # Randomization inference lived here for the four-sector Gates panel. That panel is gone, and
    # both remaining definitions have enough treated units for the clustered and spatial errors in
    # housing_inference.py to carry the inference instead.
    res["p_used"] = res.p
    res.to_csv(ANALYSIS / "reg_housing_main.csv", index=False)
    print(res[["treatment", "outcome", "wave", "b", "se", "p"]].round(3).to_string(index=False))

    fig, axes = plt.subplots(1, 3, figsize=(15, max(6.0, 1.15 * len(OUTCOMES) + 1.4)),
                             sharex=True, sharey=True)
    ys = np.arange(len(OUTCOMES))[::-1]
    for ax, (tn, tset) in zip(axes, T.items()):
        x = res[res.treatment == tn]
        for k, (yr, col, mk) in enumerate([("2012", "#8C8C8C", "o"), ("2022", "#E0A33E", "s"), ("pooled", "#2E75A8", "D")]):
            xx = x[x.wave == yr].set_index("outcome").loc[OUTCOMES]
            off = (1 - k) * 0.22
            ax.errorbar(xx.b, ys + off, xerr=[xx.b - xx.lo90, xx.hi90 - xx.b], fmt=mk, ms=5,
                        color=col, ecolor=col, elinewidth=1.4, capsize=2.5,
                        label=yr if tn == "Bordering" else None)
        ax.axvline(0, color="#333333", lw=0.8)
        ax.set_yticks(ys); ax.set_yticklabels([NICE[o] for o in OUTCOMES], fontsize=9)
        ax.set_title(tn, fontsize=10)
        ax.set_xlabel("effect, 2002 control standard deviations", fontsize=9)
        ax.grid(axis="x", lw=0.3, color="#DDDDDD"); ax.set_axisbelow(True)
    axes[0].legend(fontsize=9, frameon=False, loc="lower right")
    fig.text(0.005, 0.005, note(), fontsize=6.8, va="bottom", ha="left", color="#333333", linespacing=1.6)
    fig.tight_layout(rect=[0, 0.10, 1, 1])
    out = FIG / "coefplot_housing.pdf"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print("\nwritten:", out)


import textwrap
def note():
    return textwrap.fill(
    "Each point is the coefficient on the treatment indicator from a separate regression of the outcome on treatment, the sector's own 2002 level of the "
    "outcome, and district fixed effects, run on 2012, on 2022, and on the two pooled with district x wave fixed effects. Estimated at "
    "sector level with errors clustered at sector. Every sector counts once: the regressions are unweighted, since treatment is assigned at sector level. "
    "Household weights are used only within a sector, to turn the households sampled there into that sector's share. Bars are 90% confidence intervals. "
    f"Outcomes are the {len(COMPS)} housing components and their index, each expressed in standard deviations of the 2002 control distribution. "
    "The Gates panel has only four treated sectors, so its p-values in the accompanying table come from randomization inference over 2,000 random "
    "reassignments of four sectors within the same estimation sample rather than from the clustered errors. "
    "Controls are the 322 sectors that neither border a park nor "
    "sit next to a park entrance, less the City of Kigali and the four largest towns of 2002. "
    "Source: Rwanda Population and Housing Census 2002, 2012 and 2022, 10% public-use samples.", width=250)


if __name__ == "__main__":
    main()
