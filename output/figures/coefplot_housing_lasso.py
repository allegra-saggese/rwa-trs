"""
coefplot_housing_lasso.py -- the same ANCOVA as coefplot_housing.py, with the control set chosen
by post-double-selection lasso instead of by hand.

    python coefplot_housing_lasso.py

    output/figures/coefplot_housing_lasso.pdf   three panels, one per treatment definition
    Analysis/reg_housing_lasso.csv              coefficients, errors, p-values and what was selected

Method (Belloni, Chernozhukov and Hansen 2014). District fixed effects and the sector's own 2002
level of the outcome are always included and never penalised, so they are partialled out of
everything first. Two lassos then run on the residuals, one of the outcome on the candidate controls
and one of the treatment on the candidate controls, and the union of what they select goes into the
final least squares together with the treatment. Selecting on the outcome alone is not
enough: a control that predicts treatment strongly but the outcome weakly is exactly the one that
biases the estimate, and only the second lasso catches it.

The penalty is the BCH plug-in, lambda = 2 c sigma sqrt(n) Phi^-1(1 - gamma / 2p) with c = 1.1 and
gamma = 0.1 / log(n), sigma iterated from the residuals. It is theory-driven rather than
cross-validated on purpose: cross-validation over-selects and invalidates the inference that follows.

Candidates are the 46 controls in build_controls.py plus their squares and every pairwise product,
1,127 terms in all, against roughly 350 sectors. All of them are measured in 2002 or earlier.

The regressions are unweighted (Matteo, 2026-09-07): treatment is assigned at sector level, so every
sector counts once, and the randomization inference resamples sectors uniformly for the same reason.
Household weights are still used inside each sector, to turn the households sampled there into that
sector's share.

Two limits worth knowing. Selection happens once on the observed assignment and is then held fixed
across the permutations, because re-selecting inside each of 2,000 draws is out of reach. And the
Gates panel has four treated sectors, so its treatment lasso is fitting a nearly degenerate target
across a thousand candidates and can select terms that isolate those four; read that panel as
illustrative, and Bordering and Gates+ as inferential.
"""
import textwrap
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy.stats import norm
from sklearn.linear_model import Lasso

import bar_chart_housing as B
import build_controls as CTL   # not C: patsy's C() lives in this namespace

FIG = B.FIG
ANALYSIS = B.ANALYSIS
COMPS = B.COMPONENTS
OUTCOMES = COMPS + ["index"]
NICE = dict(B.NICE)
WAVES = (("2012", [2012], "district"), ("2022", [2022], "district"),
         ("pooled", [2012, 2022], "dw"))
REPS = 2000
SEED = 20260907


def prepare():
    g, T, X, never = B.geography()
    p = pd.read_csv(ANALYSIS / "census_sector_housing_panel.csv")
    p = p.drop(columns=[c for c in p.columns if c.startswith("district")], errors="ignore")
    ctrl = set(p.sid.unique()) - never - X["Kigali all + cities"]
    z = pd.read_csv(ANALYSIS / "census_sector_controls_2002.csv")
    for c in CTL.CONTROLS:                                   # z-scored: they are only ever controls
        z[c] = (z[c] - z[c].mean()) / z[c].std(ddof=1)
    p = p.merge(g[["sid", "district"]], on="sid", how="left").merge(z, on="sid", how="left")
    return g, T, ctrl, p


def frame(p, treated, ctrl, outcome):
    d = p[p.sid.isin(set(treated) | ctrl)].copy()
    d = B.standardise(d, ctrl, COMPS)
    if outcome != "index":                                 # components into baseline control SD units
        base = d[(d.wave == 2002) & d.sid.isin(ctrl)][outcome]
        d["y"] = (d[outcome] - base.mean()) / base.std(ddof=1)
    else:
        d["y"] = d["index"]
    d["base"] = d.sid.map(d[d.wave == 2002].set_index("sid")["y"])
    d["treat"] = d.sid.isin(treated).astype(int)
    d["dw"] = d.district + "_" + d.wave.astype(str)
    return d.dropna(subset=["y", "base", "weight"] + CTL.CONTROLS)


def candidates(s):
    """the 46 levels, their squares and every pairwise product, standardised"""
    A = s[CTL.CONTROLS].values.astype(float)
    cols, names = [A, A ** 2], list(CTL.CONTROLS) + [f"{c}^2" for c in CTL.CONTROLS]
    for i in range(len(CTL.CONTROLS)):
        for j in range(i + 1, len(CTL.CONTROLS)):
            cols.append((A[:, i] * A[:, j])[:, None])
            names.append(f"{CTL.CONTROLS[i]}x{CTL.CONTROLS[j]}")
    X = np.column_stack(cols)
    keep = X.std(axis=0, ddof=1) > 1e-8
    X, names = X[:, keep], [n for n, k in zip(names, keep) if k]
    return (X - X.mean(axis=0)) / X.std(axis=0, ddof=1), names


def rlasso(X, y, n_iter=15):
    """rigorous lasso with the plug-in penalty; returns the indices it keeps"""
    n, p = X.shape
    lam = 2 * 1.1 * np.sqrt(n) * norm.ppf(1 - (0.1 / np.log(max(n, 3))) / (2 * p))
    sig, sel = y.std(ddof=1), np.array([], dtype=int)
    for _ in range(n_iter):
        m = Lasso(alpha=lam * sig / (2 * n), fit_intercept=False, max_iter=20000, tol=1e-6).fit(X, y)
        new = np.flatnonzero(np.abs(m.coef_) > 1e-10)
        if len(new) > n // 3:                              # runaway guard: keep the sparser set
            break
        r = y - X @ m.coef_
        sig_new = np.sqrt((r ** 2).sum() / max(n - len(new), 1))
        if np.array_equal(new, sel) and abs(sig_new - sig) < 1e-8:
            sel = new
            break
        sel, sig = new, sig_new
    return sel


def residualise(M, F):
    Q, _ = np.linalg.qr(F)
    return M - Q @ (Q.T @ M)


def select_and_fit(d, waves, fe):
    """post-double selection, then least squares with the union"""
    s = d[d.wave.isin(waves)].reset_index(drop=True)
    F = np.column_stack([pd.get_dummies(s[fe]).values.astype(float), s.base.values])
    X, names = candidates(s)
    Xr = residualise(X, F)
    Xr = Xr / np.maximum(Xr.std(axis=0, ddof=1), 1e-12)     # unit sd, so the penalty is on scale
    yr = residualise(s.y.values[:, None], F)[:, 0]
    dr = residualise(s.treat.values.astype(float)[:, None], F)[:, 0]
    union = sorted(set(rlasso(Xr, yr)) | set(rlasso(Xr, dr)))
    picked = [names[i] for i in union]
    sub = s.copy()
    for k, i in enumerate(union):
        sub[f"z{k}"] = X[:, i]
    f = f"y ~ treat + base + C({fe})" + "".join(f" + z{k}" for k in range(len(union)))
    r = smf.ols(f, data=sub).fit(cov_type="cluster", cov_kwds={"groups": sub.sid})
    b, se = r.params["treat"], r.bse["treat"]
    return ({"b": b, "se": se, "p": r.pvalues["treat"], "lo90": b - 1.645 * se, "hi90": b + 1.645 * se,
             "n": int(r.nobs), "clusters": sub.sid.nunique(), "k_selected": len(picked),
             "n_candidates": len(names), "selected": "; ".join(picked)},
            s, X[:, union] if union else np.empty((len(s), 0)))


def randomization_p(s, treated, fe, chosen):
    """reassign the same number of sectors at random and see how often chance does this well"""
    rng = np.random.default_rng(SEED)
    blocks = [pd.get_dummies(s[fe]).values.astype(float), s.base.values[:, None]]
    if chosen.shape[1]:
        blocks.append(chosen)
    M = np.column_stack(blocks)
    U, sv, _ = np.linalg.svd(M, full_matrices=False)
    U = U[:, sv > sv.max() * 1e-10]                        # orthonormal basis, rank-safe
    proj = lambda v: v - U @ (U.T @ v)
    ys = proj(s.y.values)
    sids = s.sid.values
    pool = np.array(sorted(set(sids)))
    k = len(set(treated) & set(pool))

    def beta(t):
        a = proj(np.isin(sids, list(t)).astype(float))[:, None]
        return float(np.linalg.lstsq(a, ys, rcond=None)[0][0])

    obs = beta(treated)
    null = np.array([beta(rng.choice(pool, size=k, replace=False)) for _ in range(REPS)])
    return max(float((np.abs(null) >= abs(obs)).mean()), 1 / REPS)


def main():
    g, T, ctrl, p = prepare()
    rows = []
    for tn, tset in T.items():
        for o in OUTCOMES:
            d = frame(p, tset, ctrl, o)
            for yr, waves, fe in WAVES:
                r, s, chosen = select_and_fit(d, waves, fe)
                r["p_ri"] = randomization_p(s, tset, fe, chosen) if tn == "Gates" else np.nan
                rows.append({"treatment": tn, "n_treated": len(tset), "outcome": o, "wave": yr, **r})
    res = pd.DataFrame(rows)
    res["p_used"] = np.where(res.treatment == "Gates", res.p_ri, res.p)
    res.to_csv(ANALYSIS / "reg_housing_lasso.csv", index=False)
    print(res[["treatment", "outcome", "wave", "b", "se", "p", "p_ri", "k_selected"]]
          .round(3).to_string(index=False))

    fig, axes = plt.subplots(1, 3, figsize=(15, max(6.0, 1.15 * len(OUTCOMES) + 1.4)),
                             sharex=True, sharey=True)
    ys = np.arange(len(OUTCOMES))[::-1]
    for ax, (tn, tset) in zip(axes, T.items()):
        x = res[res.treatment == tn]
        for k, (yr, col, mk) in enumerate([("2012", "#8C8C8C", "o"), ("2022", "#E0A33E", "s"),
                                           ("pooled", "#2E75A8", "D")]):
            xx = x[x.wave == yr].set_index("outcome").loc[OUTCOMES]
            off = (1 - k) * 0.22
            ax.errorbar(xx.b, ys + off, xerr=[xx.b - xx.lo90, xx.hi90 - xx.b], fmt=mk, ms=5,
                        color=col, ecolor=col, elinewidth=1.4, capsize=2.5,
                        label=yr if tn == "Bordering" else None)
        ax.axvline(0, color="#333333", lw=0.8)
        ax.set_yticks(ys)
        ax.set_yticklabels([NICE[o] for o in OUTCOMES], fontsize=9)
        ax.set_title(tn, fontsize=10)
        ax.set_xlabel("effect, 2002 control standard deviations", fontsize=9)
        ax.grid(axis="x", lw=0.3, color="#DDDDDD")
        ax.set_axisbelow(True)
    axes[0].legend(fontsize=9, frameon=False, loc="lower right")
    fig.text(0.005, 0.005, note(), fontsize=6.8, va="bottom", ha="left", color="#333333",
             linespacing=1.6)
    fig.tight_layout(rect=[0, 0.10, 1, 1])
    out = FIG / "coefplot_housing_lasso.pdf"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print("\nwritten:", out)


def note():
    blocks = "; ".join(f"{n} ({len(c)})" for n, c in CTL.BLOCKS.items())
    return textwrap.fill(
        "Each point is the coefficient on the treatment indicator from a separate regression of the outcome on treatment, the sector's own 2002 level of "
        "the outcome, district fixed effects, and a set of controls chosen by post-double-selection lasso, run on 2012, on 2022, and on the two pooled with "
        f"district x wave fixed effects. The algorithm is offered {len(CTL.CONTROLS)} candidate controls across {len(CTL.BLOCKS)} categories -- {blocks} -- "
        "together with their squares and every pairwise product, 1,127 terms in all; the fixed effects and the 2002 level are never penalised and always "
        "kept. Every candidate is measured in the 2002 census or earlier. Estimated at sector level with errors clustered at sector. Every sector counts once: "
        "the regressions are unweighted, since treatment is assigned at sector level; household weights are used only within a sector, to turn the "
        "households sampled there into that sector's share. Bars are 90% confidence intervals. Outcomes are the five housing components and their index, each expressed in standard "
        "deviations of the 2002 control distribution. The Gates panel has four treated sectors, so its p-values in the accompanying table come from "
        "randomization inference over 2,000 random reassignments of four sectors rather than from the clustered errors. Controls are the 322 sectors that "
        "neither border a park nor sit next to a park entrance, less the City of Kigali and the four largest towns of 2002. "
        "Source: Rwanda Population and Housing Census 2002, 2012 and 2022, 10% public-use samples.", width=250)


if __name__ == "__main__":
    main()
