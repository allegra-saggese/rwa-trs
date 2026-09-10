"""
bar_chart_education.py -- descriptive difference-in-differences on education, census 2002/2012/2022.

    python bar_chart_education.py

    Analysis/census_sector_education_panel.csv   sector x wave, every indicator plus the 2002 controls
    output/figures/bar_chart_education.pdf       three outcomes and the index, two treatments

Built to mirror bar_chart_housing.py: same geography, same control pool, same bootstrap, so the two
figures can sit side by side. What differs is the unit and the age window.

Outcomes (Matteo, 2026-09-08), all measured over ADULTS AGED 20 AND OVER:

  primary    completed six years or more, the end of Rwandan primary
  years      total years of schooling
  literacy   can read and write in at least one language

Why 20 and over rather than 15. Fifteen-year-olds are still in school, so their attainment is not yet
final, and the bias is not random across sectors: a sector keeping more of its children in school
looks WORSE on years completed. Twenty is late enough that primary and lower secondary are settled
and early enough to keep the cohorts schooled after 2005 in the sample.

Total years is not what the census records. Every wave stores a LEVEL and a CLASS WITHIN THAT LEVEL,
so a 2002 code of 16 is primary class 6, six years, not sixteen. Years are rebuilt as the level's
base (0 primary, 6 post-primary and secondary, 12 university) plus the class within it, and anyone
who never attended is a zero rather than a missing. That reconstruction reproduces NISR's published
mean of about 5 years for adults 25 and over in 2022.

The index is the mean of the three standardised outcomes, NOT the housing construction of averaging
the raw shares first: two of these are shares and one is a count of years, so they cannot be averaged
before they are put on a common scale.
"""
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyreadstat

import bar_chart_housing as B

DB, NISR, ANALYSIS, FIG = B.DB, B.NISR, B.ANALYSIS, B.FIG
RNG, BOOT = np.random.default_rng(20260908), 2000
AGE_MIN = 20
OUTCOMES = ["primary", "years", "literacy"]
NICE = {"primary": "Completed primary", "years": "Years of schooling",
        "literacy": "Literate", "index": "Education index"}
UNIT = {"primary": "pp", "years": "years", "literacy": "pp", "index": "SD"}
# extra 2002 sector controls the housing set does not carry, offered to the lasso
EDU_CONTROLS = ["edu02_years", "edu02_primary", "edu02_literacy", "edu02_secondary",
                "edu02_attend617"]
OWN_BASE = {"years": "edu02_years", "primary": "edu02_primary", "literacy": "edu02_literacy"}


def _person_outcomes(d):
    """years of schooling, completed primary and literacy, on the pooled person file"""
    y = d.census_wave.astype(str).astype(int)
    num = lambda c: pd.to_numeric(d[c], errors="coerce")
    NA = lambda s, b: s.where(~s.isin(b))
    yr = pd.Series(np.nan, index=d.index)

    code = NA(num("census_highest_class_2002"), [99])          # tens digit level, units class
    m = y == 2002
    never = num("census_ever_attended_school_2002").eq(2)
    yr[m] = ((code // 10).map({1: 0, 2: 6, 3: 6, 4: 12}) + code % 10)[m]
    yr[m & never] = 0.0
    yr[m & num("census_ever_attended_school_2002").eq(9)] = np.nan

    lv = NA(num("census_education_level_2012"), [9]); cl = NA(num("census_years_completed_2012"), [9, 99])
    m = y == 2012
    yr[m] = (lv.map({0: 0, 1: 0, 2: 6, 3: 6, 4: 12}) + cl.fillna(0))[m]
    yr[m & lv.eq(99)] = 0.0

    lv2 = num("census_education_level_2022"); cl2 = num("census_years_completed_2022")
    m = y == 2022
    t = lv2.map({1: 0, 2: 0, 3: 0, 4: 6, 5: 6, 6: 9, 7: 12}) + np.where(lv2.isin([1, 2]), 0, cl2.fillna(0))
    yr[m] = pd.Series(t, index=d.index)[m].fillna(0.0)

    lit = pd.Series(np.nan, index=d.index)
    # 2002 P21 "Does ... know how to read and write?" offers a middle option, "can read only", that
    # the later waves do not: 2012 P16 asks whether the person can "read and write WITH
    # UNDERSTANDING" in named languages, with no partial answer. Counting 1 and 2 together
    # (Matteo, 2026-09-08) puts anyone with some literacy on the literate side, matching the later
    # waves' "named at least one language". The two instruments still differ -- 2012's "with
    # understanding" is the stricter bar -- so the residual bias is of unknown sign, not zero.
    v = num("census_literacy_2002"); m = y == 2002       # 1 read and write, 2 read only, 3 neither
    lit[m] = v[m].isin([1, 2]).astype(float); lit[m & ~v.isin([1, 2, 3])] = np.nan
    v = NA(num("census_languages_literate_2012"), [99, 999]); m = y == 2012
    lit[m] = (v > 0).astype(float)[m]; lit[m & v.isna()] = np.nan
    v = num("census_literacy_languages_2022"); m = y == 2022
    lit[m] = (v > 0).astype(float)[m]; lit[m & v.isna()] = np.nan

    sec = pd.Series(np.nan, index=d.index)                              # reached secondary or above
    lv02 = (NA(num("census_highest_class_2002"), [99]) // 10); m = y == 2002
    sec[m] = lv02.isin([3, 4]).astype(float)[m]; sec[m & never] = 0.0
    lv12 = NA(num("census_education_level_2012"), [9]); m = y == 2012
    sec[m] = lv12.isin([3, 4]).astype(float)[m]; sec[m & lv12.eq(99)] = 0.0
    m = y == 2022
    sec[m] = lv2.isin([5, 6, 7]).astype(float)[m]; sec[m & lv2.isna()] = 0.0

    att = pd.Series(np.nan, index=d.index)                              # ever attended, ages 6-17
    v = num("census_ever_attended_school_2002"); m = y == 2002
    att[m] = v[m].isin([1]).astype(float); att[m & v.eq(9)] = np.nan
    v = num("census_school_attendance_2012"); m = y == 2012
    att[m] = v[m].isin([2, 3]).astype(float); att[m & v.isin([9, 99])] = np.nan
    v = num("census_school_attendance_2022"); m = y == 2022
    att[m] = v[m].isin([1, 2]).astype(float); att[m & v.eq(99)] = np.nan
    return yr, lit, sec, att


def panel():
    """person file -> sector x wave means, adults 20+, plus the 2002 education controls"""
    need = ["census_wave", "census_sector", "census_weight", "census_age",
            "census_ever_attended_school_2002", "census_highest_class_2002", "census_literacy_2002",
            "census_school_attendance_2012", "census_education_level_2012",
            "census_years_completed_2012", "census_languages_literate_2012",
            "census_school_attendance_2022", "census_education_level_2022",
            "census_years_completed_2022", "census_literacy_languages_2022"]
    d, _ = pyreadstat.read_dta(NISR / "Census-PHC/3_Final/Census_pooled_person.dta",
                               usecols=sorted(set(need)))
    d["wave"] = d.census_wave.astype(str).astype(int)
    yr, lit, sec, att = _person_outcomes(d)
    d["years"], d["literacy"], d["secondary"] = yr, lit, sec
    d["primary"] = (yr >= 6).astype(float).where(yr.notna())
    d["attend617"] = att.where(d.census_age.between(6, 17))
    w = d.census_weight.fillna(1.0)
    adult = d.census_age >= AGE_MIN
    rows = []
    for (sid, wv), g in d.groupby(["census_sector", "wave"]):
        r = {"sid": int(sid), "wave": int(wv), "persons": int(adult[g.index].sum()),
             "weight": float(w[g.index][adult[g.index]].sum())}
        for c in OUTCOMES + ["secondary"]:
            v, ww = g[c][adult[g.index]], w[g.index][adult[g.index]]
            ok = v.notna()
            r[c] = float((v[ok] * ww[ok]).sum() / ww[ok].sum()) if ok.any() else np.nan
        v, ww = g["attend617"], w[g.index]                       # children, not adults
        ok = v.notna()
        r["attend617"] = float((v[ok] * ww[ok]).sum() / ww[ok].sum()) if ok.any() else np.nan
        rows.append(r)
    p = pd.DataFrame(rows)
    b = p[p.wave == 2002].set_index("sid")
    for src, dst in [("years", "edu02_years"), ("primary", "edu02_primary"),
                     ("literacy", "edu02_literacy"), ("secondary", "edu02_secondary"),
                     ("attend617", "edu02_attend617")]:
        p[dst] = p.sid.map(b[src])
    return p


def standardise(p, control_sids):
    """each outcome in 2002 control standard deviations; the index is their mean"""
    z = []
    for o in OUTCOMES:
        base = p[(p.wave == 2002) & p.sid.isin(control_sids)][o]
        p[o + "_z"] = (p[o] - base.mean()) / base.std(ddof=1)
        z.append(p[o + "_z"])
        p[o + "_disp"] = p[o] * (1.0 if o == "years" else 100.0)   # years stay years, shares to points
    p["index"] = pd.concat(z, axis=1).mean(axis=1)
    return p


def draw(p, T, X, never, path):
    ctrl = set(p.sid.unique()) - never - X["Kigali all + cities"]
    ps = standardise(p.copy(), ctrl)
    outs = OUTCOMES + ["index"]
    fig, axes = plt.subplots(len(T), len(outs), figsize=(3.6 * len(outs), 6.6), sharey="col")
    for i, (tn, tset) in enumerate(T.items()):
        for j, o in enumerate(outs):
            ax = axes[i, j]
            col = "index" if o == "index" else o + "_disp"
            R = [B.boot(a, b) for a, b in zip(B.changes(ps, tset, col), B.changes(ps, ctrl, col))]
            xs = np.array([0, 1, 2])
            for k, (lab, cc, key) in enumerate([("Treated", "#E0A33E", "T"), ("Control", "#8C8C8C", "C")]):
                r = [x[key] for x in R]
                ax.bar(xs + (k - 0.5) * 0.36, [v[0] for v in r], 0.34, color=cc,
                       yerr=[[v[0] - v[1] for v in r], [v[2] - v[0] for v in r]], capsize=2,
                       label=lab if (i == 0 and j == 0) else None,
                       error_kw=dict(lw=0.7, ecolor="#333333"))
            for xx, r in zip(xs, R):
                ax.annotate(f"{r['D'][0]:+.2f}", (xx, 0.012), xycoords=ax.get_xaxis_transform(),
                            ha="center", va="bottom", fontsize=6.8, color="#555555")
            ax.set_xticks(xs); ax.set_xticklabels(["2012", "2022", "pooled"], fontsize=7)
            ax.axhline(0, color="#555555", lw=0.6); ax.tick_params(labelsize=7)
            if i == 0: ax.set_title(f"{NICE[o]}  ({UNIT[o]})", fontsize=9)
            if j == 0: ax.set_ylabel(f"{tn} ({len(tset)})\nchange since 2002", fontsize=8)
    for j in range(len(outs)):
        lo_, hi_ = axes[0, j].get_ylim()
        axes[0, j].set_ylim(min(lo_, 0) - 0.22 * (hi_ - lo_), hi_)
    fig.legend(loc="upper right", fontsize=9, frameon=False, ncol=2, bbox_to_anchor=(0.99, 0.985))
    fig.suptitle("Education: adults aged 20 and over, control excludes Kigali and the four largest towns of 2002",
                 fontsize=13, fontweight="bold", x=0.008, ha="left", y=0.995)
    fig.text(0.008, 0.012, note(), fontsize=6.6, va="bottom", ha="left", color="#333333",
             linespacing=1.6)
    fig.tight_layout(rect=[0, 0.10, 1, 0.965])
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


import textwrap
def note():
    return textwrap.fill(
    "Bars show the change since 2002 for the treated sectors and for the control sectors, at 2012, at 2022, and the two pooled, with 90% bootstrap intervals over "
    "sectors. The number under each pair is the difference in differences. Outcomes are measured over adults aged 20 and over, as weighted means within each sector "
    "and then unweighted across sectors, since treatment is assigned at sector level. Completed primary and literacy are in percentage points, years of schooling in "
    "years, and the index is the mean of the three standardised in 2002 control standard deviations. Total years of schooling is rebuilt from the level and the class "
    "within it, which is how all three censuses record education; anyone who never attended counts as zero. Controls are the 328 sectors that neither border a "
    "long-standing national park nor sit within 5 km of a park entrance, less the City of Kigali and the four largest towns of 2002. "
    "Source: Rwanda Population and Housing Census 2002, 2012 and 2022, 10% public-use samples.", width=210)


def main():
    g, T, X, never = B.geography()
    p = panel()
    ANALYSIS.mkdir(parents=True, exist_ok=True)
    out = ANALYSIS / "census_sector_education_panel.csv"
    p.to_csv(out, index=False)
    print(f"panel: {p.shape} -> {out}")
    print(p.groupby("wave")[OUTCOMES + ["secondary", "attend617"]].mean().round(4).to_string())
    FIG.mkdir(parents=True, exist_ok=True)
    draw(p, T, X, never, FIG / "bar_chart_education.pdf")
    print("written:", FIG / "bar_chart_education.pdf")


if __name__ == "__main__":
    main()
