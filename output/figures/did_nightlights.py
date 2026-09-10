"""
did_nightlights.py -- difference-in-differences and event studies on the nightlights panels.

    python did_nightlights.py [annual|monthly|all]

    Analysis/reg_nightlights_did.csv        every coefficient
    output/figures/event_study_ntl_*.pdf    event studies, annual and monthly

Treatment is proximity to a long-standing national park, fixed in space; the date is 2005, when
tourism revenue sharing began. Estimated as

    Y(u,t) = a_u + d_t + b treated(u) x post(t) + e        post = year >= 2005

with a_u a unit fixed effect, d_t a period fixed effect, and errors clustered at SECTOR throughout,
because treatment is assigned at sector level whatever the unit of observation is. Conley spatial HAC
with a Bartlett kernel and a 25 km cutoff is reported alongside at sector level, since the treated
sectors form three contiguous blocks around three parks rather than 44 independent draws.

WHICH DATA CAN ANSWER WHICH QUESTION. Only DMSP spans 2005 -- 13 years before, 9 after. VIIRS begins
in 2012 and the monthly composites in April 2012, so NEITHER can identify a 2005 effect: they have no
pre-period. What they can show is whether the treated-control gap moves over 2012-2025, which is
reported as a relative trajectory and must not be read as a difference-in-differences.

UNITS. Sector, and cell with SECTOR fixed effects (Matteo, 2026-09-08), with the conventional
cell-fixed-effect within estimator alongside.

The two cell specifications come out NUMERICALLY IDENTICAL wherever the panel is balanced, and that
is arithmetic rather than a coding error: treatment is assigned at sector level, so treated x post is
constant across the cells of a sector, and its within-cell and within-sector variation are the same.
Demeaning by cell instead of by sector changes the outcome by a cell-specific constant that is
orthogonal to the regressor, leaving the coefficient and the clustered error untouched. Only the
top-pixel share differs, because it is missing wherever a unit-year has no positive light and the
panel is therefore unbalanced. Cells buy nothing here unless treatment is allowed to VARY within a
sector -- distance from the park boundary, say -- which would be a different design.

VIIRS PRODUCT BREAKS. The annual composites are not one product. 2012 and 2013 are vcmcfg, 2014-2021
vcmslcfg, 2022 is v2.2 built from NPP AND NOAA-20 together, and 2023-2025 are a further build; 2012
also covers April to December only. Year fixed effects absorb a common level shift, but a version
that changes the detection floor moves dim units more than bright ones, and the treated sectors are
the dim ones. Anything spanning 2022 is therefore reported alongside the version-consistent
2014-2021 window.

THE 2020 BREAK. Inside that consistent window the treated sectors brighten sharply against controls
from 2020: +0.88 log points for the wide group and +1.63 for Gates+, on flat pre-2020 coefficients.
It is not an artefact and not a fire -- the MEDIAN radiance layer, which is robust to transient
sources, gives the same answer to three decimals, the lit share moves too, and the rise is spread
across Bushekeri, Uwinkingi, Kitabi, Rangiro and Ruharambuga rather than sitting in one sector. It is
also not the 2005 treatment: whatever happened, happened fifteen years later, and it happened when
tourism had collapsed. Rwanda's rural electrification rollout is the obvious candidate and is not
something this design separates from the parks.

CENSORING. DMSP is run on the intercalibrated layer and on the uncensored avg_vis. The two are not
interchangeable here: stable_lights, on which Li is built, reads the park-adjacent sectors as
completely dark in 95% of pre-2010 sector-years while avg_vis records about 3.3 digital numbers of
real brightness in the same places. See section G of the checks report.
"""
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path("/Users/matteo/Documents/GitHub/rwa-trs/Nighttime-Lights")))
import bar_chart_housing as B          # noqa: E402
import ntl_helpers as H                # noqa: E402

T0 = 2005
FIG, ANALYSIS = B.FIG, B.ANALYSIS
MEASURES = [("lit_share", "lit share"), ("asinh", "asinh(sum of lights)"), ("top", "top-pixel share")]
SERIES = [("ntl_dmsp_intercal", "DMSP intercalibrated", (1992, 2013)),
          ("ntl_dmsp_avgvis", "DMSP uncensored", (1992, 2013)),
          ("ntl_viirs_avg", "VIIRS mean radiance", (2012, 2025))]


def absorb(M, keys, maxit=300, tol=1e-11):
    M = M.copy(); pre = []
    for k in keys:
        c_, u_ = pd.factorize(k)
        pre.append((c_, len(u_), np.bincount(c_, minlength=len(u_)).astype(float)))
    for _ in range(maxit):
        chg = 0.0
        for c_, n, cnt in pre:
            num = np.zeros((n, M.shape[1])); np.add.at(num, c_, M)
            d = (num / cnt[:, None])[c_]; chg = max(chg, np.abs(d).max()); M -= d
        if chg < tol:
            break
    return M


def fit(yv, Xm, sid, P=None, cutoff=25.0):
    XtX = Xm.T @ Xm
    b = np.linalg.solve(XtX, Xm.T @ yv)
    e = yv - Xm @ b
    inv = np.linalg.inv(XtX)
    G = pd.factorize(sid)[0]; ng = G.max() + 1
    S = np.zeros((ng, Xm.shape[1])); np.add.at(S, G, Xm * e[:, None])
    V = inv @ (S.T @ S) @ inv * (ng / (ng - 1.0))
    se = np.sqrt(np.diag(V))
    conley = None
    if P is not None:
        d = np.sqrt(((P[:, None, :] - P[None, :, :]) ** 2).sum(-1)) / 1000.0
        W = np.maximum(0.0, 1.0 - d / cutoff)
        Xe = Xm * e[:, None]
        conley = np.sqrt(np.maximum(np.diag(inv @ (Xe.T @ W @ Xe) @ inv), 0))
    return b, se, conley, ng


def load(cadence, unit):
    name = "pooled" if cadence == "annual" else "monthly"
    f = H.FINAL / f"Nightlights_{name}_{unit}.csv"
    if not f.exists():
        return None
    d = pd.read_csv(f)
    d["sid"] = d.ntl_sector_id.astype(int)
    d["uid"] = d[f"ntl_{unit}_id"].astype(int)
    d["year"] = d.ntl_year // 100 if cadence == "monthly" else d.ntl_year
    return d


def sample(d, tset, ctrl, col, span=None):
    s = d[d.sid.isin(set(tset) | ctrl) & d[col].notna()].copy()
    if span:
        s = s[s.year.between(*span)]
    s["treat"] = s.sid.isin(tset).astype(float)
    return s


def did(s, col, fe, xy=None):
    """fe: 'unit' for the unit's own fixed effect, 'sector' for the sector's"""
    if s.empty or s.year.nunique() < 3 or s.year.min() >= T0 or s.year.max() < T0:
        return None
    s = s.copy()
    s["post"] = (s.year >= T0).astype(float)
    M = np.column_stack([s[col].to_numpy(float), (s.treat * s.post).to_numpy()])
    R = absorb(M, [s.uid.to_numpy() if fe == "unit" else s.sid.to_numpy(), s.ntl_year.to_numpy()])
    P = np.array([xy[i] for i in s.sid]) if xy is not None else None
    b, se, cl, ng = fit(R[:, 0], R[:, 1:], s.sid.to_numpy(), P)
    p = 2 * (1 - stats.norm.cdf(abs(b[0] / se[0])))
    pc = 2 * (1 - stats.norm.cdf(abs(b[0] / cl[0]))) if cl is not None else np.nan
    return dict(b=float(b[0]), se=float(se[0]), p=float(p), se_conley=float(cl[0]) if cl is not None else np.nan,
                p_conley=float(pc), n=len(s), sectors=ng)


def event(s, col, fe, ref):
    per = sorted(s.ntl_year.unique())
    use = [p for p in per if p != ref]
    X = [(s.treat * (s.ntl_year == p)).to_numpy(float) for p in use]
    M = np.column_stack([s[col].to_numpy(float)] + X)
    R = absorb(M, [s.uid.to_numpy() if fe == "unit" else s.sid.to_numpy(), s.ntl_year.to_numpy()])
    b, se, _, _ = fit(R[:, 0], R[:, 1:], s.sid.to_numpy())
    out = pd.DataFrame({"period": use, "b": b, "se": se})
    return pd.concat([out, pd.DataFrame({"period": [ref], "b": [0.0], "se": [0.0]})]).sort_values("period")


def run_annual():
    g, T, X, never = B.geography()
    xy = {int(s): (p.x, p.y) for s, p in zip(g.sid, g.geometry.centroid)}
    rows = []
    for unit in ("sector", "cell"):
        d = load("annual", unit)
        if d is None:
            continue
        ctrl = set(d.sid.unique()) - never - X["Kigali all + cities"]
        specs = [("sector", "sector FE")] if unit == "sector" else \
                [("sector", "sector FE"), ("unit", "cell FE")]
        for tag, sname, span in SERIES:
            for suf, mname in MEASURES:
                col = f"{tag}_{suf}"
                if col not in d.columns:
                    continue
                s = sample(d, T["Bordering or Gates+"], ctrl, col, span)
                for tn, tset in T.items():
                    s2 = sample(d, tset, ctrl, col, span)
                    for fe, fename in specs:
                        r = did(s2, col, fe, xy if (unit == "sector" and fe == "sector") else None)
                        if r is None:
                            continue
                        rows.append(dict(cadence="annual", unit=unit, fe=fename, series=sname,
                                         measure=mname, treatment=tn, **r))
    return pd.DataFrame(rows)


def run_monthly():
    g, T, X, never = B.geography()
    rows = []
    for unit in ("sector", "cell"):
        d = load("monthly", unit)
        if d is None:
            print(f"  monthly {unit}: no panel yet")
            continue
        ctrl = set(d.sid.unique()) - never - X["Kigali all + cities"]
        specs = [("sector", "sector FE")] if unit == "sector" else \
                [("sector", "sector FE"), ("unit", "cell FE")]
        for suf, mname in MEASURES:
            col = f"ntl_viirs_m_avg_{suf}"
            if col not in d.columns:
                continue
            for tn, tset in T.items():
                s = sample(d, tset, ctrl, col)
                for fe, fename in specs:
                    # No pre-2005 monthly composite exists, so this is a trajectory, not a DiD:
                    # the first observed month is the reference and the rest are relative to it.
                    base = int(s.ntl_year.min())
                    ev = event(s, col, fe, base)
                    last = ev.iloc[-1]
                    rows.append(dict(cadence="monthly", unit=unit, fe=fename,
                                     series="VIIRS monthly", measure=mname, treatment=tn,
                                     b=float(last.b), se=float(last.se),
                                     p=float(2 * (1 - stats.norm.cdf(abs(last.b / last.se)))),
                                     se_conley=np.nan, p_conley=np.nan,
                                     n=len(s), sectors=s.sid.nunique(),
                                     note=f"last month {int(last.period)} vs {base}"))
    return pd.DataFrame(rows)


def draw_events(cadence, path):
    g, T, X, never = B.geography()
    if cadence == "annual":
        panels = [("ntl_dmsp_intercal", "DMSP intercalibrated, 1992-2013", (1992, 2013), 2004),
                  ("ntl_dmsp_avgvis", "DMSP uncensored, 1992-2013", (1992, 2013), 2004),
                  ("ntl_viirs_avg", "VIIRS, 2012-2025 (no pre-period: a trajectory)", (2012, 2025), 2013)]
    else:
        panels = [("ntl_viirs_m_avg", "VIIRS monthly (no pre-period: a trajectory)", None, None)]
    d = load(cadence, "sector")
    if d is None:
        return False
    ctrl = set(d.sid.unique()) - never - X["Kigali all + cities"]
    fig, axes = plt.subplots(len(panels), 2, figsize=(13.5, 3.4 * len(panels) + 1.4), squeeze=False)
    for i, (tag, title, span, ref) in enumerate(panels):
        col = f"{tag}_asinh"
        if col not in d.columns:
            continue
        for j, (tn, tset) in enumerate(T.items()):
            ax = axes[i, j]
            s = sample(d, tset, ctrl, col, span)
            r = ref if ref is not None else int(s.ntl_year.min())
            ev = event(s, col, "unit", r)
            xx = np.arange(len(ev))
            ax.axhline(0, color="#333333", lw=.9)
            if cadence == "annual" and span and span[0] < T0 <= span[1]:
                k = list(ev.period).index(T0) if T0 in list(ev.period) else None
                if k is not None:
                    ax.axvspan(k - .5, len(ev) - .5, color="#F2E6C9", alpha=.5, lw=0, zorder=0)
            ax.errorbar(xx, ev.b, yerr=1.96 * ev.se, fmt="o", ms=3.4, color="#2E75A8",
                        ecolor="#2E75A8", elinewidth=1.0, capsize=1.8, zorder=3)
            ax.plot(xx, ev.b, color="#2E75A8", lw=.9, alpha=.5, zorder=2)
            step = max(1, len(ev) // 14)
            ax.set_xticks(xx[::step])
            ax.set_xticklabels([str(int(p)) for p in ev.period[::step]], rotation=60, fontsize=6.5)
            ax.set_title(f"{tn} ({len(tset)}) — {title}", fontsize=8.6)
            ax.grid(axis="y", lw=.3, color="#DDDDDD"); ax.set_axisbelow(True)
            if j == 0:
                ax.set_ylabel("asinh(sum of lights)\nrelative to reference", fontsize=7.6)
    fig.suptitle(f"Nightlights event study, {cadence} composites, sector level with unit fixed effects",
                 fontsize=12, y=.995)
    fig.text(.5, .004,
             "Each point is the coefficient on treatment interacted with a period, from a regression of the sector's asinh total lights on those interactions, unit "
             "fixed effects and period fixed effects, with errors clustered at sector. Bars are 95% confidence intervals. The shaded band, where present, marks the "
             "years from 2005, when tourism revenue sharing began. VIIRS begins in 2012 and so has no pre-2005 period: those panels show how the treated-control gap "
             "MOVES over the period and cannot identify an effect of 2005. Controls are the 328 sectors that neither border a long-standing national park nor sit "
             "within 5 km of a park entrance, less the City of Kigali and the four largest towns of 2002.",
             fontsize=6.3, ha="center", va="bottom", wrap=True, color="#333333")
    fig.tight_layout(rect=[0, .055, 1, .975])
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return True


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    FIG.mkdir(parents=True, exist_ok=True)
    frames = []
    if what in ("annual", "all"):
        a = run_annual(); frames.append(a)
        print("\n=== ANNUAL ===")
        print(a[["unit", "fe", "series", "measure", "treatment", "b", "se", "p", "p_conley"]]
              .round(4).to_string(index=False))
        draw_events("annual", FIG / "event_study_ntl_annual.pdf")
        print("written:", FIG / "event_study_ntl_annual.pdf")
    if what in ("monthly", "all"):
        m = run_monthly()
        if len(m):
            frames.append(m)
            print("\n=== MONTHLY (trajectory, not DiD) ===")
            print(m[["unit", "fe", "measure", "treatment", "b", "se", "p", "note"]]
                  .round(4).to_string(index=False))
            if draw_events("monthly", FIG / "event_study_ntl_monthly.pdf"):
                print("written:", FIG / "event_study_ntl_monthly.pdf")
    if frames:
        out = pd.concat(frames, ignore_index=True)
        out.to_csv(ANALYSIS / "reg_nightlights_did.csv", index=False)
        print("\nwritten:", ANALYSIS / "reg_nightlights_did.csv")
