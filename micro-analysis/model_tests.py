"""
model_tests.py -- reduced-form tests of the predictions of the two-sector model of park tourism.

The model says that a rise in tourism demand at a park pulls labour and land out of farming near the park, raises
population and services employment there, and raises land values near the park relative to the interior. Every test
here asks whether that pattern is in the data. All are correlations, not causal estimates.

Distance is measured as in census_park_regressions.py (sections `catchments` and `distance`): each sector is assigned
to the park nearest its centroid (its catchment); distance is from the centroid to that park's boundary; bands are 5 km
wide up to 30 km, with 30 km and over as the omitted band. Standard errors are clustered by district, with wild cluster
restricted bootstrap p-values (helpers/regression.py::fe_ols), unless stated.

Sections (python micro-analysis/model_tests.py --list)
  trend        Are services jobs rising?
                 census   workers per 100 adults by Census wave (381 sectors outside Kigali City), all sectors and by
                          distance band to the nearest park
                 lfs      share_dt = a_d + k (t - 2017) + e_dt, Labour Force Survey 2017-2025, district x year; shares of
                          workers in services, in tourism industries and in agriculture (percentage points)
  gradient     Did the distance gradient change? Three Census waves stacked, 286 sectors (Gishwati-Mukura catchment
               dropped, as in the main distance tables):
                 Y_st = a_{p(s),t} + sum_p f_p(km_s) + sum_{t > 2002} sum_p f_pt(km_s) 1[t]
                        + b_t ln area_s + c_t ln adults_st + e_st
               f = slope per km (linear) or 5 km band dummies. The wave interactions are the change in the gradient since
               2002. The model predicts services rising and farm work falling near the park over time: a more negative
               services slope and a more positive farm slope.
  land         The same design for land use (cropland and built-up share of usable land, 2000, 2010, 2020; base 2000).
  dose         Is the gradient steeper where there are more tourists? Slope per km for each park and wave (separate
               cross-sections, all 381 sectors, four catchments from 2015) against log visits to that park. A figure and
               the points behind it; with 9 to 10 points this is descriptive only.
  land_values  Are land values higher near parks? 2021 reference land prices for 14,823 villages (Official Gazette),
               built for the village grants project:
                 ln price_v = a_p(v) + sum_p sum_b d_pb 1[km_v in band b] + X_v g + e_v
               (1) catchment effects and log area; (2) adds geography; (3) adds district effects; (4) as (2), rural
               villages only.
  gravity      How fast does migration fall with distance? Census flows between districts (previous residence), 2012 and
               2022, Poisson with origin and destination effects:
                 movers_od = exp(a_o + b_d - k dist_od)
               k is the product of the location elasticity and the distance cost in the model.

Outputs
  output/tables/regressions/model_tests_<section>.csv
  output/figures/model_tests/*.pdf (and .png)
  docs/model_tests_tables.tex (AER layout; compile with pdflatex)

The village land price file lives in the Dropbox folder of the village grants project. It is found as the sibling
folder "Rwanda - VVP" of the project root, or through the environment variable RWA_VVP_ROOT.

Usage
    python micro-analysis/model_tests.py
    python micro-analysis/model_tests.py --only gradient dose
"""
import argparse
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "helpers"))
sys.path.insert(0, str(ROOT / "micro-analysis"))
import paths as P  # noqa: E402
from regression import fe_ols  # noqa: E402
import census_park_regressions as C  # noqa: E402  (catchments, distance panel, AER table helpers)

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

BANDS = C.DIST_BANDS
GM = C.GM
WAVES = C.WAVES
KIGALI = C.KIGALI
PARKS3 = ["akagera", "nyungwe", "volcanoes"]
LABEL = {"akagera": "Akagera", "nyungwe": "Nyungwe", "volcanoes": "Volcanoes", "gishwati_mukura": "Gishwati-Mukura"}
FIG_DIR = P.FIGS / "model_tests"
STAR_NOTE = C.STAR_NOTE
SE_NOTE = ("Standard errors clustered by district in parentheses; stars follow wild cluster restricted bootstrap "
           "p-values (Webb weights, 9,999 draws): " + STAR_NOTE + ".")
TABLES = []                                  # LaTeX tables, in order


def log(msg):
    print(msg, flush=True)


def vvp_root() -> Path:
    r = os.environ.get("RWA_VVP_ROOT")
    return Path(r) if r else P.DROPBOX.parent / "Rwanda - VVP"


def save(rows, name):
    out = P.TABLES_REG / f"model_tests_{name}.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    log(f"-> {out}")
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- AER layout: figures and tables
def aer_style():
    plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman", "Times", "DejaVu Serif"], "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False, "axes.linewidth": 0.6, "axes.grid": False,
                         "xtick.direction": "out", "ytick.direction": "out", "xtick.major.width": 0.6, "ytick.major.width": 0.6,
                         "legend.frameon": False, "legend.fontsize": 9, "lines.linewidth": 1.2, "savefig.bbox": "tight",
                         "mathtext.fontset": "stix"})


def savefig(fig, name):
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    for ext in ("pdf", "png"):
        fig.savefig(FIG_DIR / f"{name}.{ext}", dpi=300)
    plt.close(fig)
    log(f"-> {FIG_DIR / (name + '.pdf')}")


def cell(coef, se, p, d=3):
    if coef is None or pd.isna(coef):
        return "", ""
    st = C.tex_star(p) if p is not None and pd.notna(p) else ""
    return (f"{C.tex_fmt(coef, d)}$^{{{st}}}$" if st else C.tex_fmt(coef, d)), f"({C.tex_fmt(se, d)})"


def two_rows(label, cells):
    return [f"{label} & " + " & ".join(c[0] for c in cells) + r" \\", " & " + " & ".join(c[1] for c in cells) + r" \\"]


def add_table(caption, label, ncols, header, lines, foot, notes):
    TABLES.append(C._tex_wrap(caption, label, ncols, header, lines, foot, notes))
    TABLES.append(r"\clearpage")


def numbers(n):
    return " & " + " & ".join(f"({i + 1})" for i in range(n)) + r" \\"


# ---------------------------------------------------------------- 1. trend
def section_trend():
    rows = []
    # Census: workers per 100 adults by wave, all sectors outside Kigali and by distance band to the nearest park
    d = C.distance_panel()
    t = pd.read_csv(C.PANEL)[["sid", "wave", "tourism"]]
    d = d.merge(t, on=["sid", "wave"], validate="1:1")
    d["band"] = pd.cut(d.km, [-1, 5, 15, 30, 1e6], labels=["0-5 km", "5-15 km", "15-30 km", "30 km and over"])
    groups = [("All sectors outside Kigali City", d)] + [(str(b), d[d.band == b]) for b in d.band.cat.categories]
    for g, x in groups:
        for w in WAVES:
            s = x[x.wave == w]
            for y, lab in [("services", "Services"), ("tourism", "Tourism"), ("nonfarm", "Non-farm"), ("farm", "Farm")]:
                rows.append({"part": "census", "group": g, "year": w, "outcome": lab, "value": 100 * s[y].sum() / s.adults.sum(),
                             "sectors": s.sid.nunique()})
    # Labour Force Survey: district shares and a linear trend
    l = pd.read_csv(P.HARM_LABOUR / "lfs_district_isic.csv")
    l = l[l.isic != 99]
    tot = l.groupby(["year", "dist"]).workers.sum().rename("tot")
    sh = pd.DataFrame({"services": l[l.isic.between(7, 21)].groupby(["year", "dist"]).workers.sum(),
                       "tourism": l[l.isic.isin([9, 18])].groupby(["year", "dist"]).workers.sum(),
                       "agriculture": l[l.isic == 1].groupby(["year", "dist"]).workers.sum()}).join(tot, how="right").fillna(0)
    for c in ("services", "tourism", "agriculture"):
        sh[c] = 100 * sh[c] / sh.tot
    sh = sh.reset_index()
    sh["trend"] = sh.year - 2017
    nat = l.groupby("year").apply(lambda x: pd.Series({
        "services": 100 * x[x.isic.between(7, 21)].workers.sum() / x.workers.sum(),
        "tourism": 100 * x[x.isic.isin([9, 18])].workers.sum() / x.workers.sum(),
        "agriculture": 100 * x[x.isic == 1].workers.sum() / x.workers.sum()}), include_groups=False)
    for y in nat.columns:
        for yr, v in nat[y].items():
            rows.append({"part": "lfs_national", "group": "All districts", "year": yr, "outcome": y.capitalize(), "value": v})
    for sample, x in [("All districts", sh), ("Outside Kigali City", sh[~sh.dist.isin(KIGALI)])]:
        for y in ("services", "tourism", "agriculture"):
            est, n, g = fe_ols(x, y, ["trend"], ["dist"], "dist")
            e = est.loc["trend"]
            rows.append({"part": "lfs_trend", "group": sample, "outcome": y.capitalize(), "coef": e.coef, "se": e.se, "p_wcb": e.p_wcb,
                         "mean_2017": x[x.year == 2017][y].mean(), "obs": n, "clusters": g})
            log(f"[trend] LFS {sample} | {y}: {e.coef:+.3f} pp per year [{e.p_wcb:.3f}]")
    r = save(rows, "trend")

    # table
    tr = r[r.part == "lfs_trend"]
    cols = [(s, y) for s in ("All districts", "Outside Kigali City") for y in ("Services", "Tourism", "Agriculture")]
    pick = lambda s, y: tr[(tr.group == s) & (tr.outcome == y)].iloc[0]
    cells = [cell(pick(s, y).coef, pick(s, y).se, pick(s, y).p_wcb) for s, y in cols]
    header = [r" & \multicolumn{3}{c}{All districts} & \multicolumn{3}{c}{Outside Kigali City} \\", r"\cmidrule(lr){2-4}\cmidrule(lr){5-7}",
              " & " + " & ".join(y for _, y in cols) + r" \\", numbers(6)]
    lines = two_rows("Year (trend)", cells)
    foot = ["Mean in 2017 & " + " & ".join(C.tex_fmt(pick(s, y).mean_2017, 1) for s, y in cols) + r" \\",
            "District FE & " + " & ".join("Yes" for _ in cols) + r" \\",
            "Districts & " + " & ".join(str(int(pick(s, y).clusters)) for s, y in cols) + r" \\",
            "Observations & " + " & ".join(f"{int(pick(s, y).obs):,}" for s, y in cols) + r" \\"]
    add_table("Trends in the Sector of Work, 2017--2025", "tab:mt_trend", 6, header, lines, foot,
              "OLS on district-by-year shares from the Labour Force Survey, 2017--2025. Outcome: the share of workers with a stated "
              "industry whose main job is in services (ISIC sections G--U), in tourism industries (accommodation and food; arts and "
              "recreation) or in agriculture, in percentage points. The coefficient is the change per year. 2020 and 2021 are the "
              "COVID-19 years. " + SE_NOTE)

    # figure: Census workers per 100 adults by wave and distance band; LFS national shares
    aer_style()
    fig, ax = plt.subplots(1, 3, figsize=(10.5, 3.4))
    fig.subplots_adjust(wspace=0.28)
    cs = r[r.part == "census"]
    marks = ["o", "s", "^", "D"]
    for (y, a) in zip(("Services", "Farm"), ax[:2]):
        for k, b in enumerate(d.band.cat.categories):
            x = cs[(cs.group == str(b)) & (cs.outcome == y)]
            a.plot(x.year, x.value, marker=marks[k], ms=4, color=str(0.15 + 0.2 * k), label=str(b))
        a.set_xticks(list(WAVES)); a.set_title(f"{y} workers per 100 adults\n(Census)", fontsize=10); a.set_xlabel("Census wave")
    ax[0].legend(title="Distance to nearest park", title_fontsize=9)
    ln = r[r.part == "lfs_national"]
    for k, y in enumerate(("Services", "Agriculture", "Tourism")):
        x = ln[ln.outcome == y]
        ax[2].plot(x.year, x.value, marker=marks[k], ms=4, color=str(0.1 + 0.3 * k), label=y)
    ax[2].set_title("Share of workers, %\n(Labour Force Survey)", fontsize=10); ax[2].set_xlabel("Year"); ax[2].legend()
    savefig(fig, "trend_services_jobs")


# ---------------------------------------------------------------- 2-3. change in the gradient
def change_terms(d, parks, design, periods, col="wave"):
    """Base terms (all periods) and their interactions with each later period."""
    base = [f"km_{p}" for p in parks] if design == "linear" else [f"b{lo}_{hi}_{p}" for p in parks for lo, hi in BANDS]
    base = [t for t in base if d[t].abs().sum() > 0]
    inter = []
    for w in periods[1:]:
        for t in base:
            d[f"{t}_x{w}"] = d[t] * (d[col] == w)
            inter.append(f"{t}_x{w}")
    return base, inter


def run_change(d, y, label, design, parks, periods, controls, section, rows, col="wave"):
    d = d.copy()
    base, inter = change_terms(d, parks, design, periods, col)
    ctrl = []
    for c in controls:
        ctrl.append(c)
        for w in periods[1:]:
            d[f"{c}_x{w}"] = d[c] * (d[col] == w)
            ctrl.append(f"{c}_x{w}")
    d["cat_period"] = d.cat.astype(str) + "_" + d[col].astype(str)
    est, n, g = fe_ols(d, y, base + inter + ctrl, ["cat_period"], "district_id", test=base + inter)
    for t in base + inter:
        e = est.loc[t]
        stem, per = (t.rsplit("_x", 1) + [None])[:2] if "_x" in t else (t, None)
        park = next(p for p in parks if stem.endswith(p))
        band = "per km" if stem.startswith("km_") else stem[1:].rsplit("_" + park, 1)[0].replace("_", "-")
        rows.append({"section": section, "design": design, "outcome": y, "label": label, "park": park, "term": band,
                     "period": periods[0] if per is None else int(per), "kind": "level in base period" if per is None else "change since base",
                     "coef": e.coef, "se": e.se, "p_wcb": e.p_wcb, "n_sectors_cell": int((d[stem] != 0).groupby(d.sid).any().sum()),
                     "obs": n, "sectors": d.sid.nunique(), "clusters": g})
    last = periods[-1]
    msg = ", ".join(f"{p} {est.loc[f'km_{p}_x{last}', 'coef']:+.4f} [{est.loc[f'km_{p}_x{last}', 'p_wcb']:.3f}]" for p in parks) if design == "linear" else ""
    log(f"[{section}] {design} | {label}: change {periods[0]}-{last} {msg}")


GRAD_OUT = [("ln_services", "Services workers"), ("ln_farm_sub", "Farm workers incl. subsistence"), ("ln_farm", "Farm workers (market farming in 2022)")]


def change_tables(r, outcomes, periods, title, label, unit_note, sample_note, d_lin=4, d_band=3):
    """One table for the linear design (all outcomes) and one band table per outcome."""
    last = periods[-1]
    pick = lambda **kw: C.tex_pick(r, **kw)
    lin = r[r.design == "linear"]
    cols = [(y, per) for y, _ in outcomes for per in (periods[0], last)]
    lines = []
    for p in PARKS3:
        cells = []
        for y, per in cols:
            x = lin[(lin.outcome == y) & (lin.park == p) & (lin.period == per) & (lin.kind == ("level in base period" if per == periods[0] else "change since base"))]
            cells.append(cell(x.coef.iloc[0], x.se.iloc[0], x.p_wcb.iloc[0], d_lin) if len(x) else ("", ""))
        lines += two_rows(f"Distance to {LABEL[p]} (km)", cells)
    k = len(outcomes)
    header = [" & " + " & ".join(rf"\multicolumn{{2}}{{c}}{{{lab}}}" for _, lab in outcomes) + r" \\",
              " ".join(rf"\cmidrule(lr){{{2 + 2 * i}-{3 + 2 * i}}}" for i in range(k)),
              " & " + " & ".join(f"{periods[0]} & Change to {last}" for _ in outcomes) + r" \\", numbers(2 * k)]
    any_ = lin.iloc[0]
    foot = [r"Catchment $\times$ period FE & " + " & ".join("Yes" for _ in cols) + r" \\",
            "Sectors & " + " & ".join(f"{int(any_.sectors):,}" for _ in cols) + r" \\",
            "Observations & " + " & ".join(f"{int(any_.obs):,}" for _ in cols) + r" \\"]
    add_table(f"{title}: Linear Distance", f"tab:{label}_linear", 2 * k, header, lines, foot,
              f"OLS, the {len(periods)} periods stacked ({', '.join(str(p) for p in periods)}). For each outcome one regression gives both columns: "
              f"the slope in {periods[0]} and the change in the slope from {periods[0]} to {last} (the interaction of distance with the {last} dummy). "
              + unit_note + " " + sample_note + " Each sector is assigned to the park nearest its centroid; distance is from the centroid to that park's "
              "boundary. Controls and catchment effects are interacted with period. " + SE_NOTE)
    for y, lab in outcomes:
        b = r[(r.design == "bands") & (r.outcome == y)]
        cols = [(periods[0], "level in base period")] + [(per, "change since base") for per in periods[1:]]
        lines = []
        for p in PARKS3:
            lines.append(rf"\multicolumn{{{len(cols) + 1}}}{{l}}{{\textit{{Catchment: {LABEL[p]}}}}} \\")
            for lo, hi in BANDS:
                cells = []
                for per, kind in cols:
                    x = b[(b.park == p) & (b.term == f"{lo}-{hi}") & (b.period == per) & (b.kind == kind)]
                    cells.append(cell(x.coef.iloc[0], x.se.iloc[0], x.p_wcb.iloc[0], d_band) if len(x) else ("", ""))
                lines += two_rows(rf"\quad {lo}--{hi} km", cells)
            lines.append(r"\addlinespace")
        header = [" & " + " & ".join(str(periods[0]) if k == "level in base period" else f"Change to {per}" for per, k in cols) + r" \\", numbers(len(cols))]
        foot = [r"Catchment $\times$ period FE & " + " & ".join("Yes" for _ in cols) + r" \\",
                "Sectors & " + " & ".join(f"{int(b.sectors.iloc[0]):,}" for _ in cols) + r" \\",
                "Observations & " + " & ".join(f"{int(b.obs.iloc[0]):,}" for _ in cols) + r" \\"]
        add_table(f"{title}: {lab}, Distance Bands", f"tab:{label}_bands_{y}", len(cols), header, lines, foot,
                  f"OLS, one regression. Column (1) is the gap in {periods[0]} between sectors in that band and sectors 30 km or more from the same "
                  "park (the omitted band); the other columns are the change in that gap since " + f"{periods[0]}. " + unit_note + " " + sample_note
                  + " Controls and catchment effects are interacted with period. " + SE_NOTE)


def section_gradient():
    d = C.distance_panel()
    m = d[d.park != GM].copy()
    rows = []
    for design in ("linear", "bands"):
        for y, lab in GRAD_OUT:
            run_change(m, y, lab, design, PARKS3, list(WAVES), ["log_area", "log_adults"], "gradient", rows)
    r = save(rows, "gradient")
    change_tables(r, GRAD_OUT[:2], list(WAVES), "Change in the Distance Gradient of Work", "mt_gradient",
                  "Outcomes are in logs, so a coefficient is a log-point difference; controls are log area and log adults aged 16 and over. "
                  "Farm workers include the estimated subsistence farmers of 2022, when the Census counts farming as work only if it is mainly for the market.",
                  "Sample: the 286 sectors outside Kigali City whose nearest park is Akagera, Nyungwe or Volcanoes.")
    # figure: band coefficients by wave, services, from the per-wave regressions already in census_park_distance.csv
    f = P.TABLES_REG / "census_park_distance.csv"
    if f.exists():
        e = pd.read_csv(f)
        e = e[(e["set"] == "no_gm") & (e.design == "bands") & (e.outcome == "ln_services") & e["sample"].isin(["2002", "2012", "2022"]) & e.park.isin(PARKS3)]
        aer_style()
        fig, ax = plt.subplots(1, 3, figsize=(10.5, 3.1), sharey=True)
        mids = {f"{lo}-{hi}": (lo + hi) / 2 for lo, hi in BANDS}
        for a, p in zip(ax, PARKS3):
            for k, w in enumerate(("2002", "2012", "2022")):
                x = e[(e.park == p) & (e["sample"] == w)].copy()
                x["mid"] = x.term.map(mids)
                x = x.sort_values("mid")
                a.errorbar(x.mid + (k - 1) * 0.6, x.coef, yerr=1.96 * x.se, marker=["o", "s", "^"][k], ms=4, lw=0.8, capsize=2,
                           color=str(0.1 + 0.3 * k), label=w)
            a.axhline(0, color="0.5", lw=0.5); a.set_title(LABEL[p], fontsize=10); a.set_xlabel("Distance to the park (km)")
        ax[0].set_ylabel("Log services workers,\nrelative to 30 km and over"); ax[0].legend(title="Census wave", title_fontsize=9)
        savefig(fig, "gradient_services_by_wave")


LAND_OUT = [("crop_pp", "Cropland share"), ("built_pp", "Built-up share")]
LAND_YEARS = [2000, 2010, 2020]


def land_panel():
    c = pd.read_csv(C.CATCHMENT)[["sid", "district_id", "park", "km_park", "park_pre", "km_park_pre"]]
    l = pd.read_csv(C.LAND_PATH)[["sid", "year", "crop_sh", "built_sh"]]
    d = l[l.year.isin(LAND_YEARS)].merge(c, on="sid", validate="m:1")
    d["crop_pp"], d["built_pp"] = 100 * d.crop_sh, 100 * d.built_sh
    pre = d.year < 2015
    d["cat"] = np.where(pre, d.park_pre, d.park)
    d["km"] = np.where(pre, d.km_park_pre, d.km_park)
    a = pd.read_csv(C.SECTORS)[["sid", "unit_km2"]]
    d = d.merge(a, on="sid", validate="m:1")
    d["log_area"] = np.log(d.unit_km2)
    for p in sorted(d.cat.unique()):
        cp = (d.cat == p).astype(int)
        d[f"km_{p}"] = cp * d.km
        for lo, hi in BANDS:
            d[f"b{lo}_{hi}_{p}"] = cp * ((d.km >= lo) & (d.km < hi)).astype(int)
    return d


def section_land():
    d = land_panel()
    m = d[d.park != GM].copy()
    rows = []
    for design in ("linear", "bands"):
        for y, lab in LAND_OUT:
            run_change(m, y, lab, design, PARKS3, LAND_YEARS, ["log_area"], "land", rows, col="year")
    r = save(rows, "land")
    change_tables(r, LAND_OUT, LAND_YEARS, "Change in the Distance Gradient of Land Use", "mt_land",
                  "Outcomes are the cropland and built-up shares of the sector's usable (non-park) land, in percentage points (GLAD land cover); the control is log area.",
                  "Sample: the 286 sectors outside Kigali City whose nearest park is Akagera, Nyungwe or Volcanoes.", d_lin=3, d_band=2)


# ---------------------------------------------------------------- 4. dose
VISIT_WINDOWS = {2002: (2005, 2005), 2012: (2008, 2012), 2022: (2015, 2019)}


def section_dose():
    d = C.distance_panel()
    v = pd.read_csv(P.tourism("park_visitors_by_park.csv")).set_index("year")
    rows = []
    for y, lab in GRAD_OUT[:2]:
        for w in WAVES:
            x = d[d.wave == w]
            parks = sorted(x.cat.unique())
            terms = [f"km_{p}" for p in parks]
            est, n, g = fe_ols(x, y, terms + ["log_area", "log_adults"], ["cat"], "district_id", test=terms)
            for p in parks:
                lo, hi = VISIT_WINDOWS[w]
                vis = v.loc[lo:hi, p].mean() if p in v.columns else np.nan
                rows.append({"outcome": y, "label": lab, "park": p, "wave": w, "slope_per_km": est.loc[f"km_{p}", "coef"],
                             "se": est.loc[f"km_{p}", "se"], "p_wcb": est.loc[f"km_{p}", "p_wcb"], "visits_per_year": vis,
                             "visit_years": f"{lo}-{hi}", "sectors": int((x.cat == p).sum())})
    r = pd.DataFrame(rows)
    fits = []
    for y, lab in GRAD_OUT[:2]:
        x = r[(r.outcome == y) & r.visits_per_year.notna()]
        X = sm.add_constant(np.log(x.visits_per_year.values))
        f = sm.OLS(x.slope_per_km.values, X).fit()
        fits.append({"outcome": y, "label": lab, "park": "fit", "wave": np.nan, "slope_per_km": f.params[1], "se": f.bse[1], "p_wcb": np.nan,
                     "visits_per_year": np.nan, "visit_years": "slope of the gradient on log visits", "sectors": len(x)})
        log(f"[dose] {lab}: gradient on log visits {f.params[1]:+.5f} (se {f.bse[1]:.5f}), {len(x)} park-waves, R2 {f.rsquared:.2f}")
    r = save(pd.concat([r, pd.DataFrame(fits)], ignore_index=True).to_dict("records"), "dose")

    aer_style()
    fig, ax = plt.subplots(1, 2, figsize=(9.4, 3.6))
    fig.subplots_adjust(wspace=0.25)
    mk = {"akagera": "o", "nyungwe": "s", "volcanoes": "^"}
    off = {"akagera": (6, 5), "nyungwe": (6, -11), "volcanoes": (-24, 6)}
    for a, (y, lab) in zip(ax, GRAD_OUT[:2]):
        x = r[(r.outcome == y) & r.visits_per_year.notna() & (r.park != "fit")]
        for p in PARKS3:
            z = x[x.park == p].sort_values("wave")
            a.errorbar(z.visits_per_year / 1000, 100 * z.slope_per_km, yerr=196 * z.se, marker=mk[p], ms=5, lw=0.8, capsize=2,
                       color="0.2", ls="none", label=LABEL[p])
            for _, q in z.iterrows():
                a.annotate(str(int(q.wave)), (q.visits_per_year / 1000, 100 * q.slope_per_km), textcoords="offset points", xytext=off[p], fontsize=8)
        g = r[(r.outcome == y) & (r.park == GM)]
        if len(g):
            a.axhline(100 * g.slope_per_km.iloc[0], color="0.5", lw=0.8, ls="--")
            a.annotate("Gishwati-Mukura, 2022", (0.02, 100 * g.slope_per_km.iloc[0]), xycoords=("axes fraction", "data"),
                       ha="left", va="bottom", fontsize=8, color="0.35")
        a.axhline(0, color="0.5", lw=0.5); a.set_xscale("log")
        a.set_xlabel("Visits to the park per year (thousands, log scale)"); a.set_title(lab, fontsize=10)
    ax[0].set_ylabel("Change in workers per km\nfrom the park (%)"); ax[1].legend(loc="lower left")
    savefig(fig, "dose_gradient_vs_visits")

    cols = [(y, w) for y, _ in GRAD_OUT[:2] for w in WAVES]
    lines = []
    for p in PARKS3 + [GM]:
        cells = []
        for y, w in cols:
            x = r[(r.outcome == y) & (r.park == p) & (r.wave == w)]
            cells.append(cell(x.slope_per_km.iloc[0], x.se.iloc[0], x.p_wcb.iloc[0], 4) if len(x) else ("", ""))
        lines += two_rows(f"Distance to {LABEL[p].replace('-', '--')} (km)", cells)
    vis = r[(r.outcome == GRAD_OUT[0][0]) & (r.park != "fit")]
    lines.append(r"\addlinespace")
    lines.append(rf"\multicolumn{{{len(cols) + 1}}}{{l}}{{\textit{{Visits per year (thousands)}}}} \\")
    for p in PARKS3:
        vals = [vis[(vis.park == p) & (vis.wave == w)].visits_per_year.iloc[0] / 1000 for w in WAVES]
        lines.append(rf"\quad {LABEL[p]} & " + " & ".join(C.tex_fmt(x, 1) for x in vals) + " & " + " & ".join("" for _ in WAVES) + r" \\")
    header = [" & " + " & ".join(rf"\multicolumn{{3}}{{c}}{{{lab}}}" for _, lab in GRAD_OUT[:2]) + r" \\", r"\cmidrule(lr){2-4}\cmidrule(lr){5-7}",
              " & " + " & ".join(str(w) for _, w in cols) + r" \\", numbers(len(cols))]
    foot = ["Catchment FE & " + " & ".join("Yes" for _ in cols) + r" \\", "Sectors & " + " & ".join("381" for _ in cols) + r" \\"]
    add_table("Distance Gradient by Park and Census Wave, and Visits to Each Park", "tab:mt_dose", len(cols), header, lines, foot,
              "OLS, one cross-section per column, 381 sectors outside Kigali City. Outcome in logs; a coefficient is the log-point change in "
              "workers per extra km from the park, within the park's catchment, controlling for log area and log adults. Gishwati--Mukura "
              "became a national park in 2015, so it has a catchment only in 2022. Visits are annual averages over 2005 (the first year "
              "recorded) for the 2002 wave, 2008--2012 for 2012 and 2015--2019 for 2022. " + SE_NOTE)


# ---------------------------------------------------------------- 5. land values
VILLAGE_FILE = "data/Spatial/intermediate/land_prices/Rwanda_Villages_Covariates.csv"
VPARK = {"Akagera": "akagera", "Gishwati-Mukura": "gishwati_mukura", "Nyungwe": "nyungwe", "Volcans": "volcanoes"}
VGEO = ["log_dist_kigali", "log_dist_city", "log_dist_road", "elev", "slope", "rain"]


def section_land_values():
    f = vvp_root() / VILLAGE_FILE
    if not f.exists():
        log(f"[land_values] skipped: {f} not found (set RWA_VVP_ROOT)")
        return
    d = pd.read_csv(f)
    d = d[d.value_rwf_m2 > 0].copy()
    d["district_id"] = d.sector_id // 100
    d = d[~d.district_id.isin(KIGALI)]
    d["ln_price"] = np.log(d.value_rwf_m2)
    d["cat"] = d.nearest_park.map(VPARK)
    d["km"] = d.dist_park_km
    d["log_area"] = np.log(d.area_km2)
    raw = {"log_dist_kigali": np.log(d.dist_kigali_km.clip(lower=0.1)), "log_dist_city": np.log(d.dist_secondary_city_km.clip(lower=0.1)),
           "log_dist_road": np.log(d.dist_road_main_km.clip(lower=0.01)), "elev": d.elev_m, "slope": d.slope_deg, "rain": d.ppt_annual_mm}
    for k, s in raw.items():
        d[k] = (s - s.mean()) / s.std()
    parks = sorted(d.cat.dropna().unique())
    terms = []
    for p in parks:
        for lo, hi in BANDS:
            t = f"b{lo}_{hi}_{p}"
            d[t] = ((d.cat == p) & (d.km >= lo) & (d.km < hi)).astype(int)
            terms.append(t)
    specs = [("(1)", d, ["log_area"], ["cat"], "No", "No", "All"),
             ("(2)", d, ["log_area"] + VGEO, ["cat"], "Yes", "No", "All"),
             ("(3)", d, ["log_area"] + VGEO, ["cat", "district_id"], "Yes", "Yes", "All"),
             ("(4)", d[d.urban == 0], ["log_area"] + VGEO, ["cat"], "Yes", "No", "Rural")]
    rows = []
    for name, x, ctrl, fes, geo, dfe, sample in specs:
        est, n, g = fe_ols(x, "ln_price", terms + ctrl, fes, "district_id", test=terms)
        for t in terms:
            p = next(q for q in parks if t.endswith(q))
            band = t[1:].rsplit("_" + p, 1)[0].replace("_", "-")
            rows.append({"spec": name, "park": p, "term": band, "coef": est.loc[t, "coef"], "se": est.loc[t, "se"], "p_wcb": est.loc[t, "p_wcb"],
                         "pct": 100 * (np.exp(est.loc[t, "coef"]) - 1), "n_villages_cell": int(x[t].sum()), "obs": n, "clusters": g,
                         "geography": geo, "district_fe": dfe, "sample": sample})
        log(f"[land_values] {name}: " + ", ".join(f"{p} 0-5 km {est.loc[f'b0_5_{p}', 'coef']:+.3f} [{est.loc[f'b0_5_{p}', 'p_wcb']:.3f}]" for p in parks))
    r = save(rows, "land_values")

    names = [s[0] for s in specs]
    lines = []
    for p in parks:
        lines.append(rf"\multicolumn{{{len(names) + 1}}}{{l}}{{\textit{{Catchment: {LABEL[p].replace('-', '--')}}}}} \\")
        for lo, hi in BANDS:
            cells = []
            for s in names:
                x = r[(r.spec == s) & (r.park == p) & (r.term == f"{lo}-{hi}")].iloc[0]
                cells.append(cell(x.coef, x.se, x.p_wcb))
            lines += two_rows(rf"\quad {lo}--{hi} km", cells)
        lines.append(r"\addlinespace")
    one = lambda s, c: r[r.spec == s][c].iloc[0]
    foot = ["Catchment FE & " + " & ".join("Yes" for _ in names) + r" \\", "Geographic controls & " + " & ".join(one(s, "geography") for s in names) + r" \\",
            "District FE & " + " & ".join(one(s, "district_fe") for s in names) + r" \\", "Villages & " + " & ".join(one(s, "sample") for s in names) + r" \\",
            "Observations & " + " & ".join(f"{int(one(s, 'obs')):,}" for s in names) + r" \\"]
    add_table("Land Values and Distance to the Park, 2021", "tab:mt_land_values", len(names), [numbers(len(names))], lines, foot,
              "OLS on villages outside Kigali City. Outcome: log reference land price per square metre in 2021 (Official Gazette; an assessed "
              "value, not a transaction price). Each village is assigned to the nearest national park; distance is from the village to that "
              "park's boundary. Each coefficient is the log-point difference between villages in that band and villages 30 km or more from the "
              "same park. All columns control for log village area. Geographic controls: log distance to Kigali, to the nearest secondary city "
              "and to the nearest main road, elevation, slope and annual rainfall (standardised). " + SE_NOTE)

    aer_style()
    fig, ax = plt.subplots(1, len(parks), figsize=(2.7 * len(parks), 3.0), sharey=True)
    mids = {f"{lo}-{hi}": (lo + hi) / 2 for lo, hi in BANDS}
    for a, p in zip(ax, parks):
        for k, s in enumerate(("(1)", "(2)")):
            x = r[(r.spec == s) & (r.park == p)].copy()
            x["mid"] = x.term.map(mids)
            a.errorbar(x.mid + (k - 0.5) * 0.8, x.coef, yerr=1.96 * x.se, marker=["o", "s"][k], ms=4, lw=0.8, capsize=2, color=str(0.1 + 0.4 * k),
                       label=["Catchment effects", "With geographic controls"][k])
        a.axhline(0, color="0.5", lw=0.5); a.set_title(LABEL[p], fontsize=10); a.set_xlabel("Distance to the park (km)")
    ax[0].set_ylabel("Log land price per m$^2$,\nrelative to 30 km and over"); ax[0].legend()
    savefig(fig, "land_values_by_distance")


# ---------------------------------------------------------------- 6. gravity
def section_gravity():
    m = pd.read_csv(P.HARMONIZED / "model_district_migration.csv").dropna(subset=["origin_district"])
    m["origin_district"] = m.origin_district.astype(int)
    s = pd.read_csv(C.SECTORS)[["district_id", "cx_km", "cy_km", "unit_km2"]]
    cen = s.groupby("district_id").apply(lambda x: pd.Series({"x": np.average(x.cx_km, weights=x.unit_km2), "y": np.average(x.cy_km, weights=x.unit_km2)}),
                                         include_groups=False)
    ids = sorted(cen.index)
    rows = []
    for w in sorted(m.wave.unique()):
        g = pd.MultiIndex.from_product([ids, ids], names=["origin_district", "dest_district"]).to_frame(index=False)
        g = g[g.origin_district != g.dest_district]
        g = g.merge(m[m.wave == w], on=["origin_district", "dest_district"], how="left")
        g["movers"] = g.movers.fillna(0)
        g["dist"] = np.hypot(cen.x.reindex(g.origin_district).values - cen.x.reindex(g.dest_district).values,
                             cen.y.reindex(g.origin_district).values - cen.y.reindex(g.dest_district).values)
        g["dist10"], g["ln_dist"] = g.dist / 10, np.log(g.dist)
        D = pd.concat([pd.get_dummies(g.origin_district, prefix="o", drop_first=True, dtype=float),
                       pd.get_dummies(g.dest_district, prefix="d", drop_first=True, dtype=float)], axis=1)
        for x, lab in (("dist10", "Distance (10 km)"), ("ln_dist", "Log distance")):
            X = sm.add_constant(pd.concat([g[[x]], D], axis=1))
            f = sm.GLM(g.movers, X, family=sm.families.Poisson()).fit(cov_type="cluster", cov_kwds={"groups": g.origin_district.values})
            rows.append({"wave": int(w), "term": lab, "coef": f.params[x], "se": f.bse[x], "p": f.pvalues[x], "obs": len(g),
                         "districts": len(ids), "zero_flows": int((g.movers == 0).sum()), "movers": g.movers.sum()})
            log(f"[gravity] {int(w)} | {lab}: {f.params[x]:+.4f} (se {f.bse[x]:.4f})")
    r = save(rows, "gravity")
    waves = sorted(r.wave.unique())
    cols = [(w, t) for w in waves for t in ("Distance (10 km)", "Log distance")]
    pick = lambda w, t: r[(r.wave == w) & (r.term == t)].iloc[0]
    lines = []
    for t in ("Distance (10 km)", "Log distance"):
        cells = [cell(pick(w, tt).coef, pick(w, tt).se, pick(w, tt).p) if tt == t else ("", "") for w, tt in cols]
        lines += two_rows(t, cells)
    header = [" & " + " & ".join(rf"\multicolumn{{2}}{{c}}{{Census {w}}}" for w in waves) + r" \\",
              " ".join(rf"\cmidrule(lr){{{2 + 2 * i}-{3 + 2 * i}}}" for i in range(len(waves))), numbers(len(cols))]
    foot = ["Origin and destination FE & " + " & ".join("Yes" for _ in cols) + r" \\",
            "District pairs & " + " & ".join(f"{int(pick(w, t).obs):,}" for w, t in cols) + r" \\"]
    add_table("Migration Between Districts and Distance", "tab:mt_gravity", len(cols), header, lines, foot,
              "Poisson pseudo-maximum likelihood on flows between districts from the Census question on previous residence; pairs with no "
              "movers are kept as zeros. Distance is between district centroids (area-weighted sector centroids), a straight line. "
              "Standard errors clustered by origin district in parentheses; stars follow cluster-robust p-values: " + STAR_NOTE
              + ". In the model the coefficient on distance is minus the product of the location elasticity and the distance cost.")


SECTIONS = {"trend": section_trend, "gradient": section_gradient, "land": section_land, "dose": section_dose,
            "land_values": section_land_values, "gravity": section_gravity}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--only", nargs="+", choices=list(SECTIONS))
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args(argv)
    if a.list:
        print("\n".join(SECTIONS)); return 0
    for name in (a.only or list(SECTIONS)):
        SECTIONS[name]()
    if TABLES:
        name = "model_tests_tables.tex" if not a.only else "model_tests_tables_" + "_".join(a.only) + ".tex"
        C._tex_doc(TABLES, name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
