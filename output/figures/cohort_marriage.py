"""
cohort_marriage.py -- the cohort exposure design applied to marriage timing.

    python cohort_marriage.py

    Analysis/census_sector_cohort_marriage.csv   sector x birth cohort x wave, women
    output/figures/event_study_marriage_{3,5}yr.pdf

Same machinery as cohort_education.py -- sector, district by cohort and wave fixed effects, the eight
2002 violence variables interacted with cohort, cohorts from 1970, errors clustered at sector -- on
two outcomes:

    married by 18   age at first marriage 18 or under. A COMPLETED-HISTORY variable: it is known for
                    a woman of 45 who married at 17, and a woman who never married is a clean zero.
                    That is what lets it span cohorts the way schooling attainment does.
    age at first    conditional on ever having married, so it is selected: young cohorts contain many
    marriage        women who have not married yet, and those who have married by 20 necessarily
                    married young. The level therefore falls mechanically for the youngest cohorts
                    and must not be read. The treated-minus-control DIFFERENCE is far less affected,
                    since the truncation hits both groups, which is why the event study is readable
                    where the raw means are not.

WOMEN ONLY. For men these questions are asked differently and answered much more noisily.

TWO WAVES, NOT THREE. Age at first marriage does not exist in the 2002 census, so both outcomes run
on 2012 and 2022. That matters for the placebo: adding 2002 is what sharpened the education pre-trend
test from p=.011 to p=.136, so the marriage pre-trends are tested with less power and will clear more
easily. Read a pass here as weaker evidence than a pass there.

Exposure is the SCHOOLING window, ages 6-17, as in cohort_education.py -- zero for cohorts born by
1987, one from 1999. The hypothesised channel is that staying in school delays marriage, so the
schooling window is the right one. The marriage risk window, roughly ages 14-18, would give a much
sharper ramp (unexposed to 1987, full from 1991) and is the natural alternative if the channel is
income rather than schooling.
"""
import numpy as np
import pandas as pd
import pyreadstat

import bar_chart_housing as B
import cohort_education as C

ANALYSIS, FIG, NISR = C.ANALYSIS, C.FIG, B.NISR
PANEL = ANALYSIS / "census_sector_cohort_marriage.csv"
# 18, not 20: "married by 18" is complete by construction the moment a woman turns 18, so nothing is
# truncated by measuring her then. It buys two more birth cohorts, 2003 and 2004, at the youngest and
# most fully exposed end. Age at first marriage is a different matter -- it stays selected on having
# married at all, and the level for these cohorts must not be read.
AGE_MIN = 18
OUTCOMES = ["married18", "age_marriage"]


def build():
    need = ["census_wave", "census_sector", "census_weight", "census_age", "census_sex",
            "census_age_first_marriage_2012", "census_age_first_marriage_2022"]
    d, _ = pyreadstat.read_dta(NISR / "Census-PHC/3_Final/Census_pooled_person.dta",
                               usecols=sorted(set(need)))
    d["wave"] = d.census_wave.astype(str).astype(int)
    d = d[(d.census_sex == 2) & d.wave.isin([2012, 2022]) & (d.census_age >= AGE_MIN)].copy()
    afm = pd.Series(np.nan, index=d.index)
    for y in (2012, 2022):
        v = pd.to_numeric(d[f"census_age_first_marriage_{y}"], errors="coerce")
        m = d.wave == y
        afm[m] = v[m]
    # 999 in 2012 and a blank in 2022 both mean never married; 99 is not stated in either.
    never = afm.isna() | afm.eq(999)
    valid = afm.where((afm >= 8) & (afm <= 60))
    d["age_marriage"] = valid
    d["married18"] = np.where(never, 0.0, np.where(valid.notna(), (valid <= 18).astype(float), np.nan))
    d["cohort"] = (d.wave - d.census_age).astype("Int64")
    d = d[d.cohort.between(C.COHORT_LO, 2004)]
    w = d.census_weight.fillna(1.0)
    frames = []
    for o in OUTCOMES:
        s = d[d[o].notna()]
        ww = w[s.index]
        k = [s.census_sector, s.cohort, s.wave]
        f = ((s[o] * ww).groupby(k).sum() / ww.groupby(k).sum()).rename("value").reset_index()
        f["w"] = ww.groupby(k).sum().values
        f["outcome"] = o
        frames.append(f)
    p = pd.concat(frames, ignore_index=True).rename(columns={"census_sector": "sid"})
    p["exposure"] = C.exposure(p.cohort)
    p.to_csv(PANEL, index=False)
    print(f"panel {p.shape} -> {PANEL.name}")
    print(p.groupby(["outcome", "wave"]).value.mean().round(3).to_string())
    return p


def main():
    p = build()
    g, T, X, never = B.geography()
    g2 = g.assign(park=g.nearest_park.astype(str).str.split().str[0])
    Z, cols = C.controls_frame()
    Z = Z.merge(g2[["sid", "district"]], on="sid", how="left")
    ctrl = set(p.sid.unique()) - never - X["Kigali all + cities"]

    rows = []
    for tn, tset in T.items():
        for o in OUTCOMES:
            s = C.frame(p, o, tset, ctrl, None, Z, cols)
            for spec in ("main", "violence"):
                r = C.estimate(s, cols, Z, spec=spec)
                rows.append(dict(treatment=tn, outcome=o, spec=spec, **r))
                print(f"  {tn:20s} {o:13s} {spec:9s} b={r['b']:+.4f} ({r['se']:.4f}) p={r['p']:.4f}")
    pd.DataFrame(rows).to_csv(ANALYSIS / "reg_marriage_cohort.csv", index=False)

    C.AGE_RANGE = {o: (AGE_MIN, 120) for o in OUTCOMES}
    C.COHORT_HI = {o: 2004 for o in OUTCOMES}
    C.NICE = {"married18": "Married by 18", "age_marriage": "Age at first marriage"}
    print("\nPRE-TREND TESTS")
    evs = []
    for width in (3, 5):
        ev = C.draw_event(p, T, ctrl, Z, cols, FIG / f"event_study_marriage_{width}yr.pdf", width)
        ev["width"] = width
        evs.append(ev)
        print("written:", FIG / f"event_study_marriage_{width}yr.pdf")
    pd.concat(evs, ignore_index=True).to_csv(ANALYSIS / "reg_marriage_event.csv", index=False)


if __name__ == "__main__":
    main()
