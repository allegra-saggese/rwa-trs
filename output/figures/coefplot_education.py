"""
coefplot_education.py -- the ANCOVA behind the education bar chart.

    python coefplot_education.py

    output/figures/coefplot_education.pdf   two panels, one per treatment definition
    Analysis/reg_education_main.csv         every coefficient, standard error and p-value

Same specification as coefplot_housing.py, on the education outcomes of bar_chart_education.py:

    Y(s,t) = a + b treated(s) + c Y(s,2002) + park FE + district FE + e        t = 2012, or 2022
    Y(s,t) = a + b treated(s) + c Y(s,2002) + park FE + district x wave FE + e t = pooled

Estimated at sector level, unweighted, errors clustered at sector, outcomes in 2002 control standard
deviations. Post waves only: with the 2002 rows in the sample Y equals the control identically.

Read this next to the cohort exposure design rather than instead of it. This regression compares
sector LEVELS and conditions on the 2002 level; it cannot tell a treatment effect from a sector that
was already on a different trajectory, and on these outcomes that distinction turns out to matter --
adults schooled entirely before 2005 show the same gap as those schooled after. What the ANCOVA
measures here is the standing difference between park-adjacent sectors and the rest.
"""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

import bar_chart_education as E
import bar_chart_housing as B

FIG, ANALYSIS = B.FIG, B.ANALYSIS
OUTCOMES = E.OUTCOMES + ["index"]
WAVES = (("2012", [2012], "district"), ("2022", [2022], "district"),
         ("pooled", [2012, 2022], "dw"))


def prepare():
    g, T, X, never = B.geography()
    p = pd.read_csv(ANALYSIS / "census_sector_education_panel.csv")
    ctrl = set(p.sid.unique()) - never - X["Kigali all + cities"]
    g = g.assign(park=g.nearest_park.astype(str).str.split().str[0])
    p = p.merge(g[["sid", "district", "park"]], on="sid", how="left")
    return g, T, ctrl, p


def frame(p, treated, ctrl, outcome):
    d = p[p.sid.isin(set(treated) | ctrl)].copy()
    d = E.standardise(d, ctrl)
    d["y"] = d["index"] if outcome == "index" else d[outcome + "_z"]
    d["base"] = d.sid.map(d[d.wave == 2002].set_index("sid")["y"])
    d["treat"] = d.sid.isin(treated).astype(int)
    d["dw"] = d.district + "_" + d.wave.astype(str)
    return d.dropna(subset=["y", "base", "weight"])


def fit(p, treated, ctrl, outcome):
    d = frame(p, treated, ctrl, outcome)
    out = []
    for yr, waves, fe in WAVES:
        sub = d[d.wave.isin(waves)]
        r = smf.ols(f"y ~ treat + base + C(park) + C({fe})", data=sub).fit(
            cov_type="cluster", cov_kwds={"groups": sub.sid})
        b, se = r.params["treat"], r.bse["treat"]
        out.append({"wave": yr, "b": b, "se": se, "p": r.pvalues["treat"],
                    "lo90": b - 1.645 * se, "hi90": b + 1.645 * se,
                    "n": int(r.nobs), "clusters": sub.sid.nunique()})
    return out


def draw(res, T, path, title, sub):
    fig, axes = plt.subplots(1, len(T), figsize=(11, 5.2), sharex=True, sharey=True)
    ys = np.arange(len(OUTCOMES))[::-1]
    for ax, (tn, tset) in zip(np.atleast_1d(axes), T.items()):
        x = res[res.treatment == tn]
        for k, (yr, col, mk) in enumerate([("2012", "#8C8C8C", "o"), ("2022", "#E0A33E", "s"),
                                           ("pooled", "#2E75A8", "D")]):
            xx = x[x.wave == yr].set_index("outcome").loc[OUTCOMES]
            ax.errorbar(xx.b, ys + (1 - k) * 0.22, xerr=[xx.b - xx.lo90, xx.hi90 - xx.b], fmt=mk,
                        ms=5, color=col, ecolor=col, elinewidth=1.4, capsize=2.5,
                        label=yr if tn == list(T)[0] else None)
        ax.axvline(0, color="#333333", lw=0.8)
        ax.set_yticks(ys); ax.set_yticklabels([E.NICE[o] for o in OUTCOMES], fontsize=9)
        ax.set_title(f"{tn} ({len(tset)} treated)", fontsize=10)
        ax.set_xlabel("effect, 2002 control standard deviations", fontsize=9)
        ax.grid(axis="x", lw=0.3, color="#DDDDDD"); ax.set_axisbelow(True)
    np.atleast_1d(axes)[0].legend(fontsize=9, frameon=False, loc="lower right")
    fig.suptitle(title, fontsize=12, x=0.008, ha="left", y=0.995)
    fig.text(0.005, 0.005, sub, fontsize=6.8, va="bottom", ha="left", color="#333333",
             linespacing=1.6)
    fig.tight_layout(rect=[0, 0.14, 1, 0.96])
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


import textwrap
def note(extra=""):
    return textwrap.fill(
    "Each point is the coefficient on the treatment indicator from a separate regression of the outcome on treatment, the sector's own 2002 level of that outcome, "
    "park fixed effects and district fixed effects, run on 2012, on 2022, and on the two pooled with district by wave fixed effects. " + extra +
    "Estimated at sector level over adults aged 20 and over, unweighted, with errors clustered at sector; household weights are used only within a sector. Bars are "
    "90% confidence intervals. Outcomes are in standard deviations of the 2002 control distribution and the index is their mean. Controls are the 328 sectors that "
    "neither border a long-standing national park nor sit within 5 km of a park entrance, less the City of Kigali and the four largest towns of 2002. "
    "Source: Rwanda Population and Housing Census 2002, 2012 and 2022, 10% public-use samples.", width=235)


def main():
    g, T, ctrl, p = prepare()
    rows = [{"treatment": tn, "n_treated": len(ts), "outcome": o, **r}
            for tn, ts in T.items() for o in OUTCOMES for r in fit(p, ts, ctrl, o)]
    res = pd.DataFrame(rows)
    res.to_csv(ANALYSIS / "reg_education_main.csv", index=False)
    print(res[["treatment", "outcome", "wave", "b", "se", "p"]].round(3).to_string(index=False))
    draw(res, T, FIG / "coefplot_education.pdf",
         "Education: ANCOVA on the 2002 level, park and district fixed effects", note())
    print("\nwritten:", FIG / "coefplot_education.pdf")


if __name__ == "__main__":
    main()
