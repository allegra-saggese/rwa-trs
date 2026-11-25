"""
sector_question_plots.py -- descriptive and regression-based figures for the question-based sector analysis (AER style, one figure per file).

Files go to output/figures/sector-questions/. Sample: the 381 sectors outside Kigali City unless a figure says otherwise.
Park-adjacent = the sector borders a national park (62); ring = touches a park-adjacent sector without bordering a park (82);
interior = the other 237. Services share = services / (farm + non-farm) workers, % (Census, industry of main work).

Descriptive (no regression)
  geo_{elev,rain,kigali,area}_services_2022   services share against a geographic control, park-adjacent vs other sectors, with a linear fit per group.
  binscatter_gate_services_{raw,adjusted}     2022; mean in 5-km bins of distance to the nearest gate, 95% intervals. Adjusted: residual of
                                              ln(services workers) on ln(adults), the geography controls and nearest-park dummies.
  trend_{services,nonfarm}                    geometric mean workers per 100 adults, park-adjacent vs other, at each Census wave (linear axis).
  land_means_{built,crop}                     mean built-up / cropland share, park-adjacent vs other, 2000-2020 (raw %, two lines).
  growth_{services,nonfarm}, levels_{...}     ln workers 2022 against 2002 (levels) and the change against the 2002 level (growth), by group.
  map_{groups,services_2022,built_change}     sector maps. balance_X: park minus interior gap in each geography control, in SD.
  visits_by_park, district_rent_by_exposure   RDB visits by park; district rent per hectare by EICV round.
Regression-based, shown in real units (read census_park_questions.csv; one cross-section regression per wave, no base year)
  trend_{services,nonfarm}_adjusted   predicted workers per sector, park-adjacent vs comparable interior sector, after geography (same scale as trend_*).
  land_{built,crop}_adjusted          predicted land share (%), park-adjacent vs comparable interior sector, after geography (same scale as land_means_*).

Usage: python results-scripts/sector_question_plots.py [--tex]    (--tex also writes docs/sector_question_figures.tex)
"""
import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "helpers"))
sys.path.insert(0, str(ROOT / "micro-analysis"))
sys.path.insert(0, str(ROOT / "results-scripts"))
import paths as P  # noqa: E402
import sector_gate_plots as S  # noqa: E402  (style, load, hav)
import census_park_regressions as C  # noqa: E402
import census_park_questions as Q  # noqa: E402
import park_land_regressions as L  # noqa: E402

OUT = P.FIGS / "sector-questions"
DARK, MID, LIGHT = S.DARK, S.MID, S.LIGHT
CAPTIONS = {}
RES = P.TABLES_REG / "census_park_questions.csv"


def save(fig, name, caption):
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / f"{name}.pdf", bbox_inches="tight")
    plt.close(fig)
    CAPTIONS[name] = caption


# ---------------------------------------------------------------------------- data
def build():
    d = S.load()                                              # sector x wave: shares, km_gate, gate, border, density
    x = Q.controls()                                          # z-scored X, nearest_park
    c = pd.read_csv(C.SECTORS)[["sid", "dist_kigali_km"]]
    raw = pd.read_csv(P.GEO / "raster/sector_terrain.csv")[["sid", "elev_mean"]].merge(
        pd.read_csv(P.GEO / "raster/sector_rainfall.csv")[["sid", "rain_mean"]], on="sid")
    ring = C.ring_sectors()
    d = d.merge(pd.read_csv(C.PANEL)[["sid", "wave", "adults"]], on=["sid", "wave"], validate="1:1")
    d = d.merge(x[["sid", "nearest_park"]], on="sid").merge(raw, on="sid").merge(c, on="sid")
    d["group"] = np.where(d.border == 1, "park", np.where(d.sid.isin(ring), "ring", "interior"))
    return d, x, ring


def fit_line(ax, xv, yv, color, ls):
    b = np.polyfit(xv, yv, 1)
    g = np.linspace(xv.min(), xv.max(), 50)
    ax.plot(g, np.polyval(b, g), color=color, linestyle=ls, linewidth=1.2)


# ---------------------------------------------------------------------------- descriptive
def geo_scatter(d, col, xlabel, name, log=False):
    w = d[d.wave == 2022]
    fig, ax = plt.subplots(figsize=(5.2, 4.0))
    i, p = w[w.border == 0], w[w.border == 1]
    f = (lambda v: np.log(v)) if log else (lambda v: v)
    ax.scatter(i[col], i.services_sh, s=11, color=LIGHT, edgecolor=MID, linewidth=0.3, label=f"Other sectors ({len(i)})")
    ax.scatter(p[col], p.services_sh, s=26, marker="^", facecolor="none", edgecolor=DARK, linewidth=0.8,
               label=f"Park-adjacent sectors ({len(p)})")
    ex = (lambda v: np.exp(v)) if log else (lambda v: v)
    for g, ls, colr in ((i, "--", MID), (p, "-", DARK)):
        b = np.polyfit(f(g[col]), g.services_sh, 1)
        gx = np.linspace(f(g[col]).min(), f(g[col]).max(), 50)
        ax.plot(ex(gx), np.polyval(b, gx), color=colr, linestyle=ls, linewidth=1.2)
    if log:
        ax.set_xscale("log")
    ax.set_xlabel(xlabel); ax.set_ylabel("Workers in services (%), 2022")
    ax.legend(frameon=False, loc="best")
    save(fig, name, f"Services share of workers against {xlabel[0].lower() + xlabel[1:] if not xlabel.startswith('Kigali') and not xlabel.startswith('Distance') else xlabel.lower().replace('kigali', 'Kigali')}, 2022. Lines: linear fit within each group.")


def binscatter(d, x):
    w = d[d.wave == 2022].copy()
    edges = np.arange(0, 100, 5)
    w["bin"] = pd.cut(w.km_gate, edges, right=False)
    # raw
    def draw(y, ylabel, name, cap):
        g = w.groupby("bin", observed=True)[y].agg(["mean", "std", "count"])
        mid = np.array([b.left + 2.5 for b in g.index])
        ci = 1.96 * g["std"] / np.sqrt(g["count"])
        fig, ax = plt.subplots(figsize=(5.4, 3.6))
        ax.errorbar(mid, g["mean"], yerr=ci, fmt="o", color=DARK, ecolor=MID, elinewidth=0.8, capsize=2, markersize=4)
        ax.set_xlabel("Distance from sector centroid to nearest park gate, km (5-km bins)"); ax.set_ylabel(ylabel)
        save(fig, name, cap)
    draw("services_sh", "Workers in services (%), 2022", "binscatter_gate_services_raw",
         "Mean services share in 5-km bins of distance to the nearest gate, 2022, 95% intervals. No controls.")
    q = Q.census(x, set(), False)
    q = q[q.wave == 2022].copy()
    q["ln_services"] = np.log(q.services)
    Xm = pd.concat([q[["log_adults"] + Q.XVARS], pd.get_dummies(q.nearest_park, drop_first=True, dtype=float)], axis=1)
    Xm = np.column_stack([np.ones(len(q)), Xm.values.astype(float)])
    b = np.linalg.lstsq(Xm, q.ln_services.values, rcond=None)[0]
    q["resid"] = q.ln_services.values - Xm @ b
    w = w.merge(q[["sid", "resid"]], on="sid")
    draw("resid", "ln services workers, residual", "binscatter_gate_services_adjusted",
         "Residual of ln(services workers), 2022, on ln(adults), X and nearest-park dummies; mean in 5-km bins of distance to the nearest gate, 95% intervals.")


def boundaries():
    import geopandas as gpd
    g = gpd.read_file(C.SECTOR_BOUNDARIES)
    g["sid"] = g.sector_id.astype(int)
    g = g[["sid", "geometry"]].dissolve("sid").reset_index().to_crs(32736)
    parks = gpd.read_file(P.GEO / "protected-areas/rwanda_protected_areas_geodata_rw.gpkg")
    parks = parks[parks["type"].isin(["National Park", "Volcanoes National Park"])].to_crs(32736)
    return g, parks


def draw_map(g, parks, col, name, cap, labels=None, colors=None):
    fig, ax = plt.subplots(figsize=(5.6, 5.0))
    g[~g.sid.isin(g.dropna(subset=[col]).sid)].plot(ax=ax, color="white", edgecolor=MID, linewidth=0.3)
    h = []
    for k, colr in colors.items():
        s = g[g[col] == k]
        s.plot(ax=ax, color=colr, edgecolor="white", linewidth=0.15)
        h.append(plt.Rectangle((0, 0), 1, 1, color=colr, label=labels[k]))
    parks.boundary.plot(ax=ax, color="black", linewidth=0.7)
    h.append(plt.Rectangle((0, 0), 1, 1, facecolor="white", edgecolor=MID, label="Kigali City (excluded)"))
    ax.legend(handles=h, frameon=False, loc="upper center", bbox_to_anchor=(0.5, 0.02), ncol=2, fontsize=8)
    ax.set_axis_off()
    save(fig, name, cap)


def maps(d, ring):
    g, parks = boundaries()
    w = d[d.wave == 2022][["sid", "group", "services_sh"]]
    g = g.merge(w, on="sid", how="left")
    draw_map(g, parks, "group", "map_groups",
             "Park-adjacent (62), ring (82) and interior (237) sectors. Black lines: park boundaries (geodata.rw). Kigali City not in the sample.",
             labels={"park": "Park-adjacent", "ring": "Ring (touches a park-adjacent sector)", "interior": "Interior"},
             colors={"park": "#111111", "ring": "#8C8C8C", "interior": "#E4E4E4"})
    ramp = ["#E4E4E4", "#BDBDBD", "#9A9A9A", "#666666", "#222222"]
    for col, name, cap, lab in (("services_sh", "map_services_2022", "Services share of workers, 2022, in quintiles of the 381 sectors.", "services"),
                                ("built_change", "map_built_change", "Change in built-up share of usable land, 2000-2020 (percentage points, GLAD), in quintiles.", "built")):
        if col == "built_change":
            lp = L.land_panel()
            a = lp[lp.year == 2020].set_index("sid").built_pp - lp[lp.year == 2000].set_index("sid").built_pp
            g = g.merge(a.rename("built_change"), left_on="sid", right_index=True, how="left")
        q = pd.qcut(g[col], 5, labels=False, duplicates="drop")
        edges = g.groupby(q)[col].agg(["min", "max"])
        g[col + "_q"] = q
        draw_map(g, parks, col + "_q", name, cap,
                 labels={k: f"{r['min']:.1f} to {r['max']:.1f}" for k, r in edges.iterrows()},
                 colors={k: ramp[int(k)] for k in edges.index})


def growth(d):
    w = d.pivot(index="sid", columns="wave", values=["services", "nonfarm"])
    grp = d.drop_duplicates("sid").set_index("sid").group
    for y, lab in (("services", "services"), ("nonfarm", "non-farm")):
        a, b = np.log(w[(y, 2002)]), np.log(w[(y, 2022)])
        z = pd.DataFrame({"x": a, "y": b - a, "p": grp == "park"})
        fig, ax = plt.subplots(figsize=(5.2, 4.0))
        ax.scatter(z[~z.p].x, z[~z.p].y, s=11, color=LIGHT, edgecolor=MID, linewidth=0.3, label=f"Other sectors ({int((~z.p).sum())})")
        ax.scatter(z[z.p].x, z[z.p].y, s=26, marker="^", facecolor="none", edgecolor=DARK, linewidth=0.8, label=f"Park-adjacent sectors ({int(z.p.sum())})")
        fit_line(ax, z[~z.p].x, z[~z.p].y, MID, "--"); fit_line(ax, z[z.p].x, z[z.p].y, DARK, "-")
        ax.set_xlabel(f"ln {lab} workers, 2002"); ax.set_ylabel(f"Change in ln {lab} workers, 2002 to 2022")
        ax.legend(frameon=False, loc="best")
        save(fig, f"growth_{y}", f"Growth in {lab} workers 2002-2022 against the 2002 level. Lines: linear fit within each group. The negative slope is regression to the mean (sectors that start high grow less in proportion, partly because the 2002 level is measured with noise), not a decline; see the levels plot.")
        # levels against levels: slope near 1 = persistence; a group's vertical gap from the other = differential growth
        fig, ax = plt.subplots(figsize=(5.2, 4.0))
        z["y22"] = z.x + z.y
        ax.scatter(z[~z.p].x, z[~z.p].y22, s=11, color=LIGHT, edgecolor=MID, linewidth=0.3, label=f"Other sectors ({int((~z.p).sum())})")
        ax.scatter(z[z.p].x, z[z.p].y22, s=26, marker="^", facecolor="none", edgecolor=DARK, linewidth=0.8, label=f"Park-adjacent sectors ({int(z.p.sum())})")
        lo, hi = z.x.min(), z.x.max()
        ax.plot([lo, hi], [lo, hi], color=MID, linewidth=0.7, linestyle=":", label="45 degree line (no change)")
        fit_line(ax, z[~z.p].x, z[~z.p].y22, MID, "--"); fit_line(ax, z[z.p].x, z[z.p].y22, DARK, "-")
        ax.set_xlabel(f"ln {lab} workers, 2002"); ax.set_ylabel(f"ln {lab} workers, 2022")
        ax.legend(frameon=False, loc="upper left", fontsize=8)
        save(fig, f"levels_{y}", f"ln {lab} workers in 2022 against 2002, one point per sector. Dotted: 45 degree line. Solid and dashed: linear fit for park-adjacent and other sectors; a vertical gap between them is differential growth at a given 2002 level.")


# ---------------------------------------------------------------------------- regression-based
def load_res():
    return pd.read_csv(RES)


def trends(d):
    """Geometric mean number of workers per 100 adults by group at each Census wave: no controls, no base year, linear axis.
    Returns y-limits by outcome so the adjusted figure can use the same scale."""
    lims = {}
    g = d.copy()
    g["grp"] = np.where(g.border == 1, "park", "other")
    for y, lab in (("services", "services"), ("nonfarm", "non-farm")):
        g["rate"] = 100 * g[y] / g.adults
        fig, ax = plt.subplots(figsize=(5.2, 3.8))
        hi = 0
        for grp, ls, colr, name in (("park", "-", DARK, "Park-adjacent sectors (solid line, 62)"), ("other", "--", MID, "Interior and ring sectors (dashed line, 319)")):
            z = g[g.grp == grp].assign(ly=lambda v: np.log(v.rate)).groupby("wave").ly.agg(["mean", "std", "count"])
            se = z["std"] / np.sqrt(z["count"])
            ax.errorbar(z.index, np.exp(z["mean"]), yerr=[np.exp(z["mean"]) - np.exp(z["mean"] - 1.96 * se), np.exp(z["mean"] + 1.96 * se) - np.exp(z["mean"])],
                        fmt="o", linestyle=ls, color=colr, markersize=5, linewidth=1.3, capsize=2, elinewidth=0.7, label=name)
            hi = max(hi, float((np.exp(z["mean"] + 1.96 * se)).max()))
        lims[y] = (0, hi * 1.08)
        ax.set_ylim(*lims[y])
        ax.set_xticks(C.WAVES); ax.set_xlabel("Census year")
        ax.set_ylabel(f"{lab.capitalize()} workers per 100 adults (geometric mean)")
        ax.legend(frameon=False, loc="upper left", fontsize=8, handlelength=3.5)
        save(fig, f"trend_{y}", f"Geometric mean (exponential of the mean of ln) of {lab} workers per 100 residents aged 16 and over, by Census wave, 381 sectors outside Kigali City. No controls. Bars: 95% intervals (unclustered).")
    return lims


def land_means(lp):
    lims = {}
    lp = lp[lp.year.isin((2000, 2005, 2010, 2015, 2020))]
    for y, lab, nm in (("built_pp", "Built-up share of usable land (%)", "built"), ("crop_pp", "Cropland share of usable land (%)", "crop")):
        fig, ax = plt.subplots(figsize=(5.2, 3.8))
        for flag, ls, colr, name in ((1, "-", DARK, "Park-adjacent sectors (solid line, 62)"), (0, "--", MID, "Interior and ring sectors (dashed line, 319)")):
            z = lp[lp.border == flag].groupby("year")[y].agg(["mean", "std", "count"])
            ax.errorbar(z.index, z["mean"], yerr=1.96 * z["std"] / np.sqrt(z["count"]), fmt="o", linestyle=ls, color=colr, markersize=5,
                        linewidth=1.3, capsize=2, elinewidth=0.7, label=name)
        ax.set_xticks([2000, 2005, 2010, 2015, 2020]); ax.set_xticklabels(["2000", "2005", "2010", "2015", "2020"]); ax.set_xlabel("Year"); ax.set_ylabel(lab)
        ax.legend(frameon=False, loc="best", fontsize=8, handlelength=3.5)
        lims[y] = ax.get_ylim()
        save(fig, f"land_means_{nm}", f"Mean {lab.lower()} by group, GLAD land cover, 381 sectors outside Kigali City. No controls. Bars: 95% intervals (unclustered).")
    return lims


def adjusted_counts(r, d, lims):
    """Q1 in the same units as trend_*: workers per 100 adults for a park-adjacent sector and an otherwise comparable interior sector.
    The Q1 regression (ln workers on Park, ln adults, geography, district FE) is evaluated at the average ln(workers), average ln(adults),
    average geography and average district: rate = 100 exp(mean ln w + b (p - share of park sectors) - mean ln a)."""
    pbar = d.drop_duplicates("sid").border.mean()
    for y, lab in (("services", "services"), ("nonfarm", "non-farm")):
        fig, ax = plt.subplots(figsize=(5.2, 3.8))
        park, inter, notes = [], [], []
        for t in C.WAVES:
            w = d[d.wave == t]
            m, ma = np.log(w[y]).mean(), np.log(w.adults).mean()
            e = r[(r.question == "Q1") & (r.wave == t) & (r.outcome == y) & (r.spec == "(2) ln adults + X") & (r.term == "border")].iloc[0]
            park.append(100 * np.exp(m + e.coef * (1 - pbar) - ma)); inter.append(100 * np.exp(m - e.coef * pbar - ma))
            notes.append(f"{t}: park-adjacent {100 * (np.exp(e.coef) - 1):+.0f}% (95% CI {100 * (np.exp(e.coef - 1.96 * e.se) - 1):+.0f}% to {100 * (np.exp(e.coef + 1.96 * e.se) - 1):+.0f}%)")
        ax.plot(C.WAVES, park, "o-", color=DARK, linewidth=1.3, markersize=5, label="Park-adjacent sector (solid line)")
        ax.plot(C.WAVES, inter, "o--", color=MID, linewidth=1.3, markersize=5, label="Comparable interior sector (dashed line)")
        ax.set_ylim(*lims[y])
        ax.set_xticks(C.WAVES); ax.set_xlabel("Census year")
        ax.set_ylabel(f"{lab.capitalize()} workers per 100 adults (adjusted)")
        ax.legend(frameon=False, loc="upper left", fontsize=8, handlelength=3.5)
        ax.text(0.98, 0.04, "Difference in number of workers:\n" + "\n".join(notes), transform=ax.transAxes, ha="right", va="bottom", fontsize=7)
        save(fig, f"trend_{y}_adjusted", f"Workers per 100 residents aged 16 and over in a park-adjacent sector and in an otherwise comparable interior sector, by Census wave. From one OLS regression per wave of ln(workers) on a park-adjacent indicator, "
             "ln(adults), district fixed effects, log area, log distance to road and to Kigali, elevation, slope and rainfall; predictions hold population, geography and district at their averages. "
             "The text gives the park-adjacent difference in the number of workers with a 95% interval (district-clustered, 27 clusters). 381 sectors. Same units and vertical scale as the unadjusted figure.")


def adjusted_land(r, lp, lims):
    """Q4 turned into numbers: predicted land share for a park-adjacent and an otherwise comparable interior sector."""
    pbar = lp.drop_duplicates("sid").border.mean()
    for y, lab, nm in (("built_pp", "Built-up share of usable land (%)", "built"), ("crop_pp", "Cropland share of usable land (%)", "crop")):
        fig, ax = plt.subplots(figsize=(5.2, 3.8))
        yrs = (2000, 2010, 2020)
        park, inter, notes = [], [], []
        for t in yrs:
            m = lp[lp.year == t][y].mean()
            e = r[(r.question == "Q4") & (r.wave == t) & (r.outcome == y) & (r.spec == "(2) X") & (r.term == "border")].iloc[0]
            park.append(m + e.coef * (1 - pbar)); inter.append(m - e.coef * pbar)
            notes.append(f"{t}: park-adjacent {e.coef:+.1f} pp (95% CI {e.coef - 1.96 * e.se:+.1f} to {e.coef + 1.96 * e.se:+.1f})")
        ax.plot(yrs, park, "o-", color=DARK, linewidth=1.3, markersize=5, label="Park-adjacent sector (solid line)")
        ax.plot(yrs, inter, "o--", color=MID, linewidth=1.3, markersize=5, label="Comparable interior sector (dashed line)")
        ax.set_ylim(*lims[y]); ax.set_xticks(yrs); ax.set_xticklabels([str(t) for t in yrs])
        ax.set_xlabel("Year"); ax.set_ylabel(lab + ", adjusted")
        ax.legend(frameon=False, loc="upper left", fontsize=8, handlelength=3.5)
        ax.text(0.98, 0.04, "Difference:\n" + "\n".join(notes), transform=ax.transAxes, ha="right", va="bottom", fontsize=7)
        save(fig, f"land_{nm}_adjusted", f"Predicted {lab.lower()} for a park-adjacent sector and an otherwise comparable interior sector. From one OLS regression per year of the land share on a park-adjacent indicator, "
             "district fixed effects, log area, log distance to road and to Kigali, elevation, slope and rainfall, evaluated at average geography and district. The text gives the difference with a 95% interval "
             "(district-clustered, 27 clusters). 381 sectors. Same vertical scale as the unadjusted figure.")


def balance(x):
    names = {"log_area": "Log area", "log_dist_road": "Log distance to road", "log_dist_kigali": "Log distance to Kigali",
             "elev_mean": "Elevation", "slope_mean": "Slope", "rain_mean": "Rainfall"}
    T, Z = x[x.border == 1], x[x.border == 0]
    diff = [(T[v].mean() - Z[v].mean()) / x[v].std() for v in Q.XVARS]
    fig, ax = plt.subplots(figsize=(5.0, 3.2))
    pos = np.arange(len(Q.XVARS))
    ax.scatter(diff, pos, s=36, color=DARK)
    ax.axvline(0, color=MID, linewidth=0.7)
    ax.set_yticks(pos); ax.set_yticklabels([names[v] for v in Q.XVARS]); ax.invert_yaxis()
    ax.set_xlabel("Park-adjacent minus interior mean, in standard deviations")
    save(fig, "balance_X", "Difference in the geographic controls between the 62 park-adjacent and 319 interior sectors, in standard deviations of each variable over the 381 sectors. "
         "Elevation and rainfall differ by more than one standard deviation.")


# ---------------------------------------------------------------------------- time and district
def visits():
    v = pd.read_excel(P.HARMONIZED / "rwanda-parks-tourism-rdb.xlsx", sheet_name="visits_by_park")
    v = v[pd.to_numeric(v.year, errors="coerce").notna()].copy(); v["year"] = v.year.astype(int)
    fig, ax = plt.subplots(figsize=(5.4, 3.6))
    for col, ls, mk in (("Volcanoes", "-", "o"), ("Akagera", "--", "s"), ("Nyungwe", ":", "^")):
        ax.plot(v.year, v[col] / 1e3, linestyle=ls, color=DARK, marker=mk, markersize=3.5, linewidth=1.0, label=col)
    ax.set_xticks(range(2005, 2024, 3)); ax.set_xlabel("Year"); ax.set_ylabel("Visits (thousands)")
    ax.legend(frameon=False, loc="best")
    save(fig, "visits_by_park", "Annual visits to the three tourist parks, Rwanda Development Board.")


def district_rent():
    e = pd.read_csv(P.HARM_DISTRICT / "district-park-exposure-border.csv")[["district_id", "n_adjacent_sectors"]]
    d = pd.read_csv(P.HARM_DISTRICT / "district-land-prices.csv")
    d = d[(d.measure == "rent") & (d.source == "EICV")][["district_id", "round", "mean_ln_per_ha", "n_parcels"]].merge(
        e, on="district_id")
    d["exposed"] = d.n_adjacent_sectors > 0
    fig, ax = plt.subplots(figsize=(5.4, 3.8))
    for k, g in d.groupby("district_id"):
        ax.plot(g["round"], g.mean_ln_per_ha, color=(DARK if g.exposed.iloc[0] else LIGHT), linewidth=0.5, alpha=0.7)
    for flag, ls, lbl in ((True, "-", "Mean, districts with a park-adjacent sector (thick solid line)"),
                          (False, "--", "Mean, other districts (thick dashed line)")):
        m = d[d.exposed == flag].groupby("round").mean_ln_per_ha.mean()
        ax.plot(m.index, m.values, color=DARK, linestyle=ls, linewidth=2.0, marker="o", markersize=4, label=lbl)
    ax.plot([], [], color=DARK, linewidth=0.5, label="Single district, exposed (thin dark line)")
    ax.plot([], [], color=LIGHT, linewidth=0.8, label="Single district, other (thin light line)")
    rounds = sorted(d["round"].unique()); ax.set_xticks(rounds); ax.set_xticklabels([str(int(r)) for r in rounds])
    ax.set_xlabel("EICV round"); ax.set_ylabel("Median land rent per hectare, ln (2014 RWF)")
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=1, fontsize=8, handlelength=3.5)
    save(fig, "district_rent_by_exposure", "District median rent per hectare by EICV round (mean of district log medians). Dark thin lines: districts with a park-adjacent sector; light: others. Some district-round cells have few parcels (min 19).")


# ---------------------------------------------------------------------------- tex
def write_tex():
    names = sorted(CAPTIONS)
    body = "\n".join(
        f"\\begin{{figure}}[p]\\centering\\includegraphics[width=0.85\\textwidth]{{{OUT / (n + '.pdf')}}}\n"
        f"\\caption{{\\small {CAPTIONS[n].replace('%', '\\%').replace('_', ' ').replace('&', '\\&')}}}\n\\end{{figure}}" for n in names)
    tex = ("\\documentclass[11pt]{article}\n\\usepackage[margin=1in]{geometry}\n\\usepackage{graphicx}\n"
           "\\usepackage[font=small,labelfont=bf]{caption}\n\\begin{document}\n" + body + "\n\\end{document}\n")
    p = ROOT / "docs" / "sector_question_figures.tex"
    p.write_text(tex)
    print(f"[question-plots] -> {p}")


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--tex", action="store_true")
    args = a.parse_args(argv)
    d, x, ring = build()
    geo_scatter(d, "elev_mean", "Mean elevation of the sector (m)", "geo_elev_services_2022")
    geo_scatter(d, "rain_mean", "Mean annual rainfall (mm)", "geo_rain_services_2022")
    geo_scatter(d, "dist_kigali_km", "Distance to Kigali (km)", "geo_kigali_services_2022")
    geo_scatter(d, "unit_km2", "Land area of the sector (km$^2$, log scale)", "geo_area_services_2022", log=True)
    binscatter(d, x)
    maps(d, ring)
    growth(d)
    r = load_res()
    lims = trends(d)
    adjusted_counts(r, d, lims)
    lp = L.land_panel()
    llims = land_means(lp)
    adjusted_land(r, lp, llims)
    balance(x)
    visits()
    district_rent()
    print(f"[question-plots] {len(CAPTIONS)} figures -> {OUT}")
    if args.tex:
        write_tex()
    return 0


if __name__ == "__main__":
    sys.exit(main())
