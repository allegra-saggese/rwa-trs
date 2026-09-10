"""
cohort_education.py -- the cohort exposure design for education, main and PDS lasso.

    python cohort_education.py [build|run|all]

    Analysis/census_sector_cohort_panel.csv    sector x birth cohort x wave x sex
    Analysis/reg_education_cohort.csv          every coefficient
    output/figures/coefplot_education_cohort.pdf
    output/figures/event_study_education_cohort.pdf

WHY THIS AND NOT THE ANCOVA. coefplot_education.py compares sector LEVELS conditional on the 2002
level, and on these outcomes that design fails its own placebo: adults who finished school before
2000 show the same negative gap as those schooled after 2005 (-0.26, p=.031), and nothing done at the
parks in 2005 can reach them. What it measures is the standing difference between park-adjacent
sectors and the rest, which is real and is not an effect.

Schooling is a stock laid down at a fixed age, so a programme starting in 2005 can only reach people
still of school age then. That gives a control group inside the treated sectors: their own older
cohorts. The design is Duflo's (2001) INPRES construction -- place intensity interacted with cohort
exposure, with place fixed effects.

    Y(s,c,t) = a_s + d_c + w_t + b treated(s) x exposure(c) + e

exposure(c) is the share of ages 6-17 falling in 2005 or later: zero for cohorts born by 1987, one
from 1999 -- the cohort that enters P1 in 2005 -- and a linear ramp between. Errors clustered at
sector. The event studies drop that ramp entirely and give every cohort its own coefficient, since a
half-exposed cohort almost certainly does not collect half the effect: a programme reaching a child
at six is not the same as one reaching them at seventeen, when the schooling decisions are already
made.

WHAT IS A CONTROL HERE. The sector fixed effect absorbs every variable measured once in 2002 --
all 53 project controls and the education baselines with them. They cannot enter in levels; they are
already gone. A baseline characteristic can only enter INTERACTED WITH EXPOSURE, which lets it carry
its own cohort gradient, and that is the right object anyway: it asks whether places with a given
2002 characteristic were on a different trajectory regardless of the parks.

    main      treated x exposure, sector FE, cohort FE, wave FE, and district x cohort FE.
              The district x cohort effects are not a robustness check but part of the specification:
              without them regional cohort trends masquerade as the effect, and adding them moved the
              wide group's pre-trend from p=.065 to p=.580.
    lasso     every candidate is an interaction with exposure -- 58 baseline characteristics, their
              squares and their pairwise products, 1,769 terms. The one that matters most is
              edu02_years x exposure: it lets sectors that started further behind converge at their
              own rate, which is the mechanical-catch-up story written as a control.

Estimated separately by sex. Cells are not used: treatment is constant within a sector, so cell and
sector fixed effects give numerically identical estimates.
"""
import sys
import textwrap

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyreadstat
import statsmodels.formula.api as smf
from scipy import stats

import bar_chart_education as E
import bar_chart_housing as B
import build_controls as CTL
import coefplot_housing_lasso as L

FIG, ANALYSIS, NISR = B.FIG, B.ANALYSIS, B.NISR
T0 = 2005
PANEL = ANALYSIS / "census_sector_cohort_panel.csv"
# age window each outcome is measured over, and the youngest birth cohort it can reach in 2022
AGE_RANGE = {"primary": (15, 120), "years": (22, 120), "literacy": (15, 120)}
COHORT_HI = {"primary": 2007, "literacy": 2007, "years": 2000}
AGE_MIN = {k: v[0] for k, v in AGE_RANGE.items()}
NICE = {"primary": "Completed primary", "years": "Years of schooling", "literacy": "Literate"}

# Which censuses each outcome may use (Matteo, 2026-09-08). 2002 is worth having because it observes
# the pre-2005 cohorts a decade earlier and so sharpens the placebo, which is the weakest part of the
# design. It is admissible only where the instrument is the same in all three waves: completed
# primary and years of schooling are both rebuilt from the level and the class within it, and that
# reconstruction reproduces NISR's published mean for 2022. Literacy is NOT -- 2002 asks one
# read/write question with a "can read only" middle category that the later waves do not have -- so
# 2002's codes 1 and 2 are read together as literate (Matteo, 2026-09-08), which lines the middle
# category up with the later waves' "named at least one language" and lets literacy use 2002 too.
WAVES_FOR = {o: [2002, 2012, 2022] for o in ("primary", "years", "literacy")}
BASE_CTRL = {}

# Cohorts before 1970 are dropped (Matteo, 2026-09-08). They were schooled under a different system,
# they are small -- 43,000 people for 1955 against 274,000 for 2007 -- and sixty years of mortality
# plus the genocide have selected them heavily. Born 1970 was 24 in 1994, so every cohort kept from
# 1970 to about 1975 finished school BEFORE the genocide, which makes them a clean control rather
# than merely a better-measured one.
COHORT_LO = 1970

# The 1994 genocide and the 1997-99 northwest insurgency are cohort-BY-PLACE shocks, which is exactly
# the dimension the treatment lives in: sector fixed effects absorb their level, cohort fixed effects
# their national average, and neither touches the interaction. That matters here because the
# insurgency fell hardest on Ruhengeri and Gisenyi -- where Volcanoes National Park is -- while the
# cohorts born 1985-1992 were in school, immediately around our reference.
#
# These eight 2002 sector variables are carried individually rather than as an index (Matteo,
# 2026-09-08), so each is free to have its own cohort profile. District x cohort effects already
# absorb violence that varies between districts; what these add is the within-district variation.
VIOLENCE = ["orphan_double", "orphan_any", "war_disab", "widowed", "sex_ratio", "child_head",
            "prev_abroad", "foreign_born"]
BINS = [(1950, 1969, "<=1969"), (1970, 1975, "1970-75"), (1976, 1981, "1976-81"),
        (1982, 1987, "1982-87*"), (1988, 1992, "1988-92"), (1993, 1998, "1993-98"),
        (1999, 2003, "1999-2003"), (2004, 2007, "2004-07")]
REF, PRE = "1982-87*", ["<=1969", "1970-75", "1976-81"]


ENTRY_AGE = 6            # Rwandan P1 entry (Matteo, 2026-09-08): the 1999 cohort starts in 2005
YEARS_OF_SCHOOL = 12     # P1 to S6, ages 6 to 17
LAST_UNEXPOSED = T0 - ENTRY_AGE - YEARS_OF_SCHOOL      # 1987: left school the year before 2005
FIRST_FULL = T0 - ENTRY_AGE                            # 1999: starts P1 in 2005


def exposure(cohort):
    """share of ages 6-17 falling in 2005 or later.

    A cohort born in year c sits in school over calendar years c+6 to c+17, so the number of those
    years from 2005 is c - 1987. Zero for cohorts born by 1987, who had left school before revenue
    sharing began; one from 1999, the cohort that starts P1 in 2005."""
    return np.clip(np.asarray(cohort, float) - LAST_UNEXPOSED, 0, YEARS_OF_SCHOOL) / YEARS_OF_SCHOOL


def build():
    need = ["census_wave", "census_sector", "census_weight", "census_age", "census_sex",
            "census_ever_attended_school_2002", "census_highest_class_2002", "census_literacy_2002",
            "census_school_attendance_2012", "census_education_level_2012",
            "census_years_completed_2012", "census_languages_literate_2012",
            "census_school_attendance_2022", "census_education_level_2022",
            "census_years_completed_2022", "census_literacy_languages_2022"]
    d, _ = pyreadstat.read_dta(NISR / "Census-PHC/3_Final/Census_pooled_person.dta",
                               usecols=sorted(set(need)))
    d["wave"] = d.census_wave.astype(str).astype(int)
    yr, lit, _sec, _att = E._person_outcomes(d)
    d["years"], d["literacy"] = yr, lit
    d["primary"] = (yr >= 6).astype(float).where(yr.notna())
    # CURRENT attendance, not ever attended. 2002 cannot separate the two, but the cohort design
    # uses only 2012 and 2022, which both code "is currently attending" as its own category. This is
    # the one schooling outcome that reaches the cohorts born after 2007: a child born in 2016 is six
    # in the 2022 census, old enough to be in school and far too young for completed attainment.
    att = pd.Series(np.nan, index=d.index)
    v = pd.to_numeric(d["census_school_attendance_2012"], errors="coerce"); m = d.wave == 2012
    att[m] = v[m].eq(3).astype(float); att[m & v.isin([9, 99])] = np.nan
    v = pd.to_numeric(d["census_school_attendance_2022"], errors="coerce"); m = d.wave == 2022
    att[m] = v[m].eq(2).astype(float); att[m & v.eq(99)] = np.nan
    d["attending"] = att
    d["cohort"] = (d.wave - d.census_age).astype("Int64")
    d = d[d.cohort.between(COHORT_LO, 2016)]
    w = d.census_weight.fillna(1.0)
    frames = []
    for o, (amin, amax) in AGE_RANGE.items():
        s = d[(d.census_age >= amin) & (d.census_age <= amax) & d[o].notna()
              & (d.cohort <= COHORT_HI[o]) & d.wave.isin(WAVES_FOR[o])]
        ww = w[s.index]
        k = [s.census_sector, s.cohort, s.wave, s.census_sex]
        f = ((s[o] * ww).groupby(k).sum() / ww.groupby(k).sum()).rename("value").reset_index()
        f["w"] = ww.groupby(k).sum().values
        f["outcome"] = o
        frames.append(f)
    p = pd.concat(frames, ignore_index=True).rename(
        columns={"census_sector": "sid", "wave": "wave", "census_sex": "sex"})
    p["exposure"] = exposure(p.cohort)
    ANALYSIS.mkdir(parents=True, exist_ok=True)
    p.to_csv(PANEL, index=False)
    print(f"panel {p.shape} -> {PANEL.name}")
    print(p.groupby(["outcome", "wave"]).value.mean().round(4).to_string())
    return p


# ------------------------------------------------------------------ estimation machinery
def absorb(M, keys, wv, maxit=300, tol=1e-11):
    """weighted alternating projections: absorbs several high-dimensional fixed effects at once"""
    M = M.copy()
    pre = []
    for k in keys:
        c_, u_ = pd.factorize(k)
        pre.append((c_, len(u_), np.bincount(c_, weights=wv, minlength=len(u_))))
    for _ in range(maxit):
        chg = 0.0
        for c_, n, wsum in pre:
            num = np.zeros((n, M.shape[1]))
            np.add.at(num, c_, M * wv[:, None])
            dd = (num / np.maximum(wsum, 1e-12)[:, None])[c_]
            chg = max(chg, float(np.abs(dd).max()))
            M -= dd
        if chg < tol:
            break
    return M


def wls_cluster(yv, Xm, wv, cl):
    XtX = Xm.T @ (Xm * wv[:, None])
    b = np.linalg.solve(XtX, Xm.T @ (yv * wv))
    e = yv - Xm @ b
    inv = np.linalg.inv(XtX)
    G = pd.factorize(cl)[0]
    ng = G.max() + 1
    S = np.zeros((ng, Xm.shape[1]))
    np.add.at(S, G, Xm * (wv * e)[:, None])
    V = inv @ (S.T @ S) @ inv * (ng / (ng - 1.0))
    return b, V, ng


def controls_frame():
    z = pd.read_csv(ANALYSIS / "census_sector_controls_2002.csv")
    e = pd.read_csv(ANALYSIS / "census_sector_education_panel.csv")
    e = e[e.wave == 2002][["sid"] + E.EDU_CONTROLS]
    z = z.merge(e, on="sid", how="left")
    cols = list(dict.fromkeys(list(CTL.CONTROLS) + E.EDU_CONTROLS + VIOLENCE))
    for c in cols:
        z[c] = (z[c] - z[c].mean()) / z[c].std(ddof=1)
    return z[["sid"] + cols].dropna(), cols


def candidates(s, Z, cols, pairwise=True):
    """every candidate is a 2002 characteristic INTERACTED WITH EXPOSURE.

    Uninteracted, all of them are constant within sector and the sector fixed effect has already
    removed them; the interaction is what lets a baseline characteristic carry its own cohort
    gradient. float32 keeps the 1,769-column matrix inside memory."""
    A = s[cols].to_numpy(np.float32)
    x = s.exposure.to_numpy(np.float32)[:, None]
    blocks, names = [A * x, (A ** 2) * x], [f"{c}:exp" for c in cols] + [f"{c}^2:exp" for c in cols]
    if pairwise:
        for i in range(len(cols)):
            blocks.append(A[:, i:i + 1] * A[:, i + 1:] * x)
            names += [f"{cols[i]}x{c}:exp" for c in cols[i + 1:]]
    X = np.concatenate(blocks, axis=1)
    keep = X.std(axis=0, ddof=1) > 1e-6
    X, names = X[:, keep], [n for n, k in zip(names, keep) if k]
    return (X - X.mean(axis=0)) / X.std(axis=0, ddof=1), names


def frame(p, outcome, tset, ctrl, sex, Z, cols):
    s = p[(p.outcome == outcome) & p.sid.isin(set(tset) | ctrl)]
    if sex is not None:
        s = s[s.sex == sex]
    s = s.merge(Z, on="sid", how="inner").reset_index(drop=True)
    s["treat"] = s.sid.isin(tset).astype(float)
    s["dc"] = s.district.astype(str) + "_" + s.cohort.astype(str) if "district" in s else ""
    bc = BASE_CTRL.get(outcome)
    s["basex"] = (s[bc] * s.exposure) if bc and bc in s.columns else 0.0
    s["_has_basex"] = 1.0 if bc and bc in s.columns else 0.0
    return s


def violence_terms(s, bins=None):
    """the eight 2002 violence variables, interacted so they survive the sector fixed effect.

    With cohort bins they get an unrestricted cohort profile; without, a single exposure gradient."""
    V = s[VIOLENCE].to_numpy(float)
    if bins is None:
        return V * s.exposure.to_numpy(float)[:, None]
    lab = {c: l for a, b_, l in bins for c in range(a, b_ + 1)}
    b = s.cohort.map(lab)
    out = []
    for l in sorted(set(b.dropna()))[1:]:                 # first bin is the omitted reference
        out.append(V * (b == l).to_numpy(float)[:, None])
    return np.concatenate(out, axis=1) if out else np.zeros((len(s), 0))


def estimate(s, cols, Z, spec="main", district_cohort=True, lasso=False):
    """returns coefficient on treated x exposure, its clustered error and p"""
    wv = s.w.to_numpy(float)
    key2 = s.dc.to_numpy() if district_cohort else s.cohort.to_numpy()
    keys = [s.sid.to_numpy(), key2, s.wave.to_numpy()]
    tx = (s.treat * s.exposure).to_numpy(float)
    picked = []
    if lasso:
        X, names = candidates(s, Z, cols)
        R = absorb(np.column_stack([s.value.to_numpy(float), tx, X.astype(float)]), keys, wv)
        yr, dr, Xr = R[:, 0], R[:, 1], R[:, 2:]
        Xr = Xr / np.maximum(Xr.std(axis=0, ddof=1), 1e-12)
        union = sorted(set(L.rlasso(Xr, yr, s.sid.values)) | set(L.rlasso(Xr, dr, s.sid.values)))
        picked = [names[i] for i in union]
        Xm = np.column_stack([dr] + [Xr[:, i] for i in union]) if union else dr[:, None]
        b, V, ng = wls_cluster(yr, Xm, wv, s.sid.to_numpy())
    else:
        cols_ = [s.value.to_numpy(float), tx]
        if spec in ("violence_trend",):
            # treated-specific LINEAR cohort trend: the effect is then identified off the deviation
            # from a trend fitted across cohorts, not off the level difference. A weaker identifying
            # assumption, stated in the specification rather than hidden by it.
            cols_.append((s.treat * (s.cohort - LAST_UNEXPOSED)).to_numpy(float))
        extra = violence_terms(s) if spec in ("violence", "violence_trend") else np.zeros((len(s), 0))
        M = np.column_stack(cols_ + ([extra] if extra.shape[1] else []))
        R = absorb(M, keys, wv)
        b, V, ng = wls_cluster(R[:, 0], R[:, 1:], wv, s.sid.to_numpy())
    se = float(np.sqrt(V[0, 0]))
    return dict(b=float(b[0]), se=se, p=2 * (1 - stats.norm.cdf(abs(b[0] / se))),
                n=len(s), sectors=ng, k_selected=len(picked), selected="; ".join(picked[:12]))


def event(s, district_cohort=True):
    s = s.copy()
    s["bin"] = s.cohort.map(lambda v: next((l for a, b_, l in BINS if a <= v <= b_), None))
    s = s[s.bin.notna()]
    use = [l for _, _, l in BINS if l != REF and (s.bin == l).any()]
    X = [(s.treat * (s.bin == l)).to_numpy(float) for l in use]
    wv = s.w.to_numpy(float)
    key2 = s.dc.to_numpy() if district_cohort else s.cohort.to_numpy()
    R = absorb(np.column_stack([s.value.to_numpy(float)] + X),
               [s.sid.to_numpy(), key2, s.wave.to_numpy()], wv)
    b, V, _ = wls_cluster(R[:, 0], R[:, 1:], wv, s.sid.to_numpy())
    b, V = b[:len(use)], V[:len(use), :len(use)]
    ev = pd.DataFrame({"bin": use, "b": b, "se": np.sqrt(np.diag(V))})
    ev = pd.concat([ev, pd.DataFrame({"bin": [REF], "b": [0.0], "se": [0.0]})])
    order = [l for _, _, l in BINS]
    ev["k"] = ev.bin.map(order.index)
    ev = ev.sort_values("k")
    idx = [i for i, l in enumerate(use) if l in PRE]
    if idx:
        Rm = np.zeros((len(idx), len(b)))
        for r_, i in enumerate(idx):
            Rm[r_, i] = 1
        Rb = Rm @ b
        W = float(Rb @ np.linalg.solve(Rm @ V @ Rm.T, Rb))
        pw = 1 - stats.chi2.cdf(W, len(idx))
    else:
        W, pw = np.nan, np.nan
    return ev, W, pw


def note():
    return textwrap.fill(
    "Each point is the coefficient on treatment interacted with cohort exposure -- the share of ages 7 to 18 falling in 2005 or later, zero for cohorts born by 1986 "
    "and one from 1998 -- from a regression of the sector-cohort mean outcome on that interaction, sector fixed effects, district by birth-cohort fixed effects and a "
    "census-wave indicator, weighted by cohort size with errors clustered at sector. Bars are 90% confidence intervals. The coefficient is the effect on a cohort "
    "schooled entirely after 2005. Sector fixed effects absorb every characteristic measured once in 2002, so the lasso panel selects from 1,769 candidate terms that "
    "are all INTERACTIONS WITH EXPOSURE: 58 baseline characteristics, their squares and their pairwise products, each allowed its own cohort gradient. Adults aged 15 "
    "and over for completed primary and literacy, 22 and over for years of schooling, in the 2012 and 2022 censuses. Controls are the 328 sectors that neither border "
    "a long-standing national park nor sit within 5 km of a park entrance, less the City of Kigali and the four largest towns of 2002. "
    "Source: Rwanda Population and Housing Census 2002, 2012 and 2022, 10% public-use samples.", width=250)


def draw_coef(res, T, path):
    outs = list(AGE_MIN)
    fig, axes = plt.subplots(1, len(T), figsize=(11, 4.6), sharex=True, sharey=True)
    ys = np.arange(len(outs))[::-1]
    for ax, (tn, tset) in zip(np.atleast_1d(axes), T.items()):
        x = res[res.treatment == tn]
        for k, (sp, col, mk) in enumerate([("main", "#2E75A8", "o"), ("lasso", "#E0A33E", "D")]):
            xx = x[(x.spec == sp) & (x.sex == "all")].set_index("outcome").reindex(outs)
            ax.errorbar(xx.b, ys + (0.5 - k) * 0.22, xerr=1.645 * xx.se, fmt=mk, ms=5.5,
                        color=col, ecolor=col, elinewidth=1.4, capsize=2.5,
                        label={"main": "main", "lasso": "PDS lasso"}[sp] if tn == list(T)[0] else None)
        ax.axvline(0, color="#333333", lw=.8)
        ax.set_yticks(ys); ax.set_yticklabels([NICE[o] for o in outs], fontsize=9)
        ax.set_title(f"{tn} ({len(tset)} treated)", fontsize=10)
        ax.set_xlabel("effect of full exposure", fontsize=9)
        ax.grid(axis="x", lw=.3, color="#DDDDDD"); ax.set_axisbelow(True)
    np.atleast_1d(axes)[0].legend(fontsize=9, frameon=False, loc="lower right")
    fig.suptitle("Education, cohort exposure design: sector, district by cohort and wave fixed effects",
                 fontsize=12, x=.008, ha="left", y=.995)
    fig.text(.005, .005, note(), fontsize=6.6, va="bottom", ha="left", color="#333333", linespacing=1.6)
    fig.tight_layout(rect=[0, .17, 1, .96])
    fig.savefig(path, bbox_inches="tight"); plt.close(fig)


def note_event(width=3):
    grid = "single birth year" if width == 1 else "three-year birth cohort group"
    return textwrap.fill(
    f"Each point is the coefficient on treatment interacted with a {grid}, from a regression of the sector-cohort mean outcome on those "
    "interactions, sector fixed effects, district by birth-cohort fixed effects and a census-wave indicator, weighted by cohort size with errors clustered at sector. "
    "Bars are 95% confidence intervals. The reference is the last cohort group entirely finished with school by 2005 -- born 1987, who entered P1 at six and left S6 "
    "in 2004 -- and the bin "
    "grid is built outward from it so no bin straddles the start of exposure. Shading covers every cohort still of school age in 2005 or later, from those born in 1988, partially exposed, to those born from "
    "1999, the cohort entering P1 in 2005. Cohorts to the LEFT of the reference had left school by 2005 and cannot have been affected: the reported test is "
    "the joint hypothesis that every one of them is zero, and it is the placebo the design exists to provide. No lasso controls are used. "
    "Adults aged 15 and over for completed primary and literacy, 22 and over for years of schooling, in the 2012 and 2022 censuses. Controls are the 328 sectors that "
    "neither border a long-standing national park nor sit within 5 km of a park entrance, less the City of Kigali and the four largest towns of 2002. "
    "Source: Rwanda Population and Housing Census 2002, 2012 and 2022, 10% public-use samples.", width=250)


def draw_event(p, T, ctrl, Z, cols, path):
    outs = list(AGE_MIN)
    fig, axes = plt.subplots(len(outs), len(T), figsize=(13, 3.1 * len(outs) + 1), squeeze=False)
    for i, o in enumerate(outs):
        for j, (tn, tset) in enumerate(T.items()):
            ax = axes[i, j]
            s = frame(p, o, tset, ctrl, None, Z, cols)
            ev, W, pw = event(s)
            xx = np.arange(len(ev))
            kref = list(ev.bin).index(REF)
            ax.axvspan(kref + .5, len(ev) - .5, color="#F2E6C9", alpha=.5, lw=0, zorder=0)
            ax.axhline(0, color="#333333", lw=.9)
            ax.errorbar(xx, ev.b, yerr=1.96 * ev.se, fmt="o", ms=4, color="#2E75A8",
                        ecolor="#2E75A8", elinewidth=1.1, capsize=2, zorder=3)
            ax.plot(xx, ev.b, color="#2E75A8", lw=.9, alpha=.5, zorder=2)
            ax.set_xticks(xx); ax.set_xticklabels(ev.bin, rotation=55, fontsize=6.5)
            ax.set_title(f"{NICE[o]} — {tn} ({len(tset)})", fontsize=9)
            ax.grid(axis="y", lw=.3, color="#DDDDDD"); ax.set_axisbelow(True)
            ax.text(.02, .95, f"pre-trend $\\chi^2$ p = {pw:.3f}", transform=ax.transAxes,
                    fontsize=7.6, va="top",
                    bbox=dict(fc="white", ec="#CCCCCC", lw=.6, pad=3, alpha=1.0), zorder=6)
            if j == 0:
                ax.set_ylabel("relative to 1980-86 cohort", fontsize=7.6)
    fig.suptitle("Education by birth cohort: cohorts left of the shaded band finished school before 2005",
                 fontsize=12, y=.997)
    fig.text(.5, .004, note_event(), fontsize=6.2, ha="center", va="bottom", wrap=True, color="#333333")
    fig.tight_layout(rect=[0, .055, 1, .975])
    fig.savefig(path, bbox_inches="tight"); plt.close(fig)


# ---------------------------------------------------------------- event study, configurable bins
def make_bins(width, lo=COHORT_LO, hi=2007):
    """bins built OUTWARD from LAST_UNEXPOSED so the reference ends exactly on it.

    1987 is the last cohort with exposure zero: entering P1 at six, they finished S6 in 2004.
    Aligning the grid on it keeps the reference clean and stops a bin straddling the ramp's start."""
    out = []
    a = LAST_UNEXPOSED + 1 - width
    while a >= lo:
        out.append((a, a + width - 1)); a -= width
    out = out[::-1]
    a = LAST_UNEXPOSED + 1
    while a <= hi:
        out.append((a, min(a + width - 1, hi))); a += width
    return [(x, y, (str(x) if width == 1 else f"{x}-{str(y)[2:]}")) for x, y in out]


def event_bins(s, bins, ref_lab, district_cohort=True, violence=True):
    lab = {}
    for a, b_, l in bins:
        for c in range(a, b_ + 1):
            lab[c] = l
    s = s.assign(bin=s.cohort.map(lab))
    s = s[s.bin.notna()]
    use = [l for _, _, l in bins if l != ref_lab and (s.bin == l).any()]
    X = [(s.treat * (s.bin == l)).to_numpy(float) for l in use]
    if violence:
        vt = violence_terms(s, bins)
        if vt.shape[1]:
            X += [vt[:, j] for j in range(vt.shape[1])]
    wv = s.w.to_numpy(float)
    key2 = s.dc.to_numpy() if district_cohort else s.cohort.to_numpy()
    R = absorb(np.column_stack([s.value.to_numpy(float)] + X),
               [s.sid.to_numpy(), key2, s.wave.to_numpy()], wv)
    b, V, _ = wls_cluster(R[:, 0], R[:, 1:], wv, s.sid.to_numpy())
    b, V = b[:len(use)], V[:len(use), :len(use)]
    ev = pd.DataFrame({"bin": use, "b": b, "se": np.sqrt(np.diag(V))})
    ev = pd.concat([ev, pd.DataFrame({"bin": [ref_lab], "b": [0.0], "se": [0.0]})])
    order = [l for _, _, l in bins]
    ev["k"] = ev.bin.map(order.index); ev = ev.sort_values("k").reset_index(drop=True)
    end = {l: y for _, y, l in bins}
    pre = [i for i, l in enumerate(use) if end[l] <= LAST_UNEXPOSED]
    if pre:
        Rm = np.zeros((len(pre), len(b)))
        for r_, i in enumerate(pre):
            Rm[r_, i] = 1
        Rb = Rm @ b
        W = float(Rb @ np.linalg.solve(Rm @ V @ Rm.T, Rb))
        pw = 1 - stats.chi2.cdf(W, len(pre))
    else:
        W, pw = np.nan, np.nan
    return ev, W, len(pre), pw


def draw_event(p, T, ctrl, Z, cols, path, width=3):  # noqa: C901
    """one figure: three outcomes, both sector definitions overlaid, three-year birth cohorts"""
    outs = list(AGE_RANGE)
    hi = COHORT_HI
    style = [("#E0A33E", "s"), ("#2E75A8", "o")]
    fig, axes = plt.subplots(1, len(outs), figsize=(21.5, 5.4))
    rows = []
    for i, o in enumerate(outs):
        ax = axes[i]
        bins = make_bins(width, COHORT_LO, hi[o])
        ref_lab = [l for a, b_, l in bins if b_ == LAST_UNEXPOSED][0]
        labs, ptxt = None, []
        for j, (tn, tset) in enumerate(T.items()):
            s = frame(p, o, tset, ctrl, None, Z, cols)
            ev, W, k, pw = event_bins(s, bins, ref_lab, violence=True)
            _, _, _, pw0 = event_bins(s, bins, ref_lab, violence=False)
            print(f"    {o:9s} {tn:20s} {width}yr  pre-trend p: "
                  f"no violence controls {pw0:.3f} -> with {pw:.3f}")
            rows += [dict(outcome=o, treatment=tn, bin=r.bin, b=r.b, se=r.se) for _, r in ev.iterrows()]
            labs = list(ev.bin)
            xx = np.arange(len(ev)) + (j - 0.5) * 0.20
            c, mk = style[j]
            ax.errorbar(xx, ev.b, yerr=1.645 * ev.se, fmt=mk, ms=4.2, color=c, ecolor=c,
                        elinewidth=1.0, capsize=1.8, zorder=3 + j,
                        label=f"{tn} ({len(tset)})" if i == 0 else None)
            ax.plot(xx, ev.b, color=c, lw=.9, alpha=.45, zorder=2)
            ptxt.append(f"{tn.split(' or ')[0] if ' or ' in tn else tn}: {pw:.3f}")
        kref = labs.index(ref_lab)
        ax.axvspan(kref + .5, len(labs) - .5, color="#EDE6D6", alpha=.75, lw=0, zorder=0)
        ax.axvline(kref, color="#B0B0B0", lw=.9, ls=":")
        ax.axhline(0, color="#333333", lw=.9)
        ax.set_xticks(np.arange(len(labs)))
        ax.set_xticklabels(labs, rotation=60, fontsize=6.4)
        ax.set_title(NICE[o], fontsize=10.5)
        ax.set_xlabel("birth cohort", fontsize=8.5)
        ax.grid(axis="y", lw=.3, color="#DDDDDD"); ax.set_axisbelow(True)
        ax.text(.015, .975, "pre-trend  " + " | ".join(ptxt), transform=ax.transAxes,
                fontsize=7.0, va="top",
                bbox=dict(fc="white", ec="#CCCCCC", lw=.6, pad=3, alpha=1.0), zorder=6)
        if i == 0:
            ax.set_ylabel(f"effect relative to the {ref_lab} cohort", fontsize=8.5)
    axes[0].legend(fontsize=8.5, frameon=False, loc="upper left", bbox_to_anchor=(0.015, 0.90))
    fig.suptitle("Education by birth cohort: shaded cohorts were of school age after revenue sharing began in 2005",
                 fontsize=12.5, y=.995)
    fig.text(.5, .004, note_event(width), fontsize=6.4, ha="center", va="bottom", wrap=True,
             color="#333333")
    fig.tight_layout(rect=[0, .10, 1, .96])
    fig.savefig(path, bbox_inches="tight"); plt.close(fig)
    return pd.DataFrame(rows)


def main(what="all"):
    if what in ("build", "all") or not PANEL.exists():
        p = build()
    else:
        p = pd.read_csv(PANEL)
    if what == "build":
        return
    g, T, X, never = B.geography()
    g2 = g.assign(park=g.nearest_park.astype(str).str.split().str[0])
    Z, cols = controls_frame()
    Z = Z.merge(g2[["sid", "district"]], on="sid", how="left")
    ctrl = set(p.sid.unique()) - never - X["Kigali all + cities"]

    rows = []
    for tn, tset in T.items():
        for o in AGE_RANGE:
            s = frame(p, o, tset, ctrl, None, Z, cols)
            if s.empty:
                continue
            for spec in ("main", "violence", "violence_trend"):
                r = estimate(s, cols, Z, spec=spec)
                rows.append(dict(treatment=tn, outcome=o, spec=spec, **r))
                print(f"  {tn:20s} {o:9s} {spec:15s} b={r['b']:+.4f} ({r['se']:.4f}) p={r['p']:.4f}")
    res = pd.DataFrame(rows)
    res.to_csv(ANALYSIS / "reg_education_cohort.csv", index=False)

    FIG.mkdir(parents=True, exist_ok=True)
    evs = []
    print("\nPRE-TREND TESTS")
    for width in (1, 2, 3, 4, 5):
        ev = draw_event(p, T, ctrl, Z, cols, FIG / f"event_study_education_{width}yr.pdf", width)
        ev["width"] = width
        evs.append(ev)
        print("written:", FIG / f"event_study_education_{width}yr.pdf")
    pd.concat(evs, ignore_index=True).to_csv(ANALYSIS / "reg_education_event.csv", index=False)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "all")
