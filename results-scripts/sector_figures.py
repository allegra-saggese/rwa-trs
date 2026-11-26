"""
sector_figures.py -- every figure on the 381 sectors outside Kigali City, one script, one folder (output/figures/sector/, AER style,
one figure per file) and one document (docs/sector_figures.pdf, written with --tex).

Sections (python results-scripts/sector_figures.py [--only gate questions descriptive] [--tex])
  gate         ranked_{farm,services}_{dot,bar}_{2002,2012,2022}  sectors ordered by distance to the nearest park gate; four classes (gate-touching,
                                               other park-adjacent, ring, interior) with class-mean lines
               scatter_land_density_{2002,2012,2022}  land area against population density
  questions    figures that go with the regressions of micro-analysis/census_park_regressions.py (they read its CSV):
               geo_*, binscatter_gate_services_*, map_*, growth_*, levels_*, trend_*, trend_*_adjusted, land_means_*, land_*_adjusted,
               balance_X, visits_by_park, district_rent_by_exposure
  descriptive  histograms, scatters and group plots for park-adjacent / ring / interior sectors: hist_*, scatter_*, services_breakdown_*,
               occupation_mix_*, land_*_by_category, land_transitions_2000_2020, ec_*, osm_accommodation_by_park, visits_vs_services_by_park,
               district_status_*, district_ag_*, district_rent_exposure_*
Run micro-analysis/census_park_regressions.py first (the questions section reads census_park_questions.csv) and
data-build/sector_work_type.py (the descriptive section reads sector_work_type.csv).

Descriptive section: three categories of sector throughout (counts in every legend):
  Park-adjacent   the sector borders a national park or touches a park gate (64 sectors; 62 border a park, 2 more touch a gate)
  Ring            touches a park-adjacent sector, does not border a park or touch a gate (80)
  Interior        every other sector (237)
Variables (Census sector x wave unless stated)
  Services share        services / (farm + non-farm) workers, %, recorded workers (census_sector_work_per_adult.csv)
  Agriculture share     agriculture, forestry and fishing workers aged 20-64 per 100 adults aged 20-64, including estimated
                        subsistence farmers in 2022 (census_sector_jobs_panel.csv, n_AG_pt; the 2022 Census records farming as work
                        only if mainly for the market, so the point estimate adds farm-household adults with no recorded industry,
                        less a false-positive rate measured in 2012: micro-analysis/census/build_jobs_panel.py)
  Subsistence share     (n_AG_pt - n_AG) / adults 20-64, % : the 2022 add-back only (zero by construction in 2002, 2012, when
                        subsistence farming is recorded inside agriculture)
  Non-farm share        100 - farm share of recorded workers
  Service-and-sales occupation share   ISCO major group 5 among adults 16+ with a stated occupation (data-build/sector_work_type.py)
  Household size        mean persons per household (household-weighted), same script
  Schooling             mean years of schooling, secondary completion (census_sector_education_panel.csv)
  Housing quality       mean of four household shares: improved floor, improved water, private toilet, brick wall
                        (census_sector_housing_panel.csv)
  In-migration share    share of residents whose previous residence was another district or abroad (2012, 2022; model_sector_panel.csv)
  Urban share           share of the sector's population in urban areas (sector_urban_share.csv)
  Density               residents per km2 of sector area (log scale)
  Other                 distances to park, gate, road and Kigali; elevation, slope, rainfall; GLAD land cover; Hansen tree cover and
                        loss; Establishment Census 2011 accommodation and food; OSM accommodation; RDB visits; district labour
                        status, agricultural output and land rent (see each caption).


Output: output/figures/sector/*.pdf; docs/sector_figures.tex (--tex), compiled to docs/sector_figures.pdf.
"""

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import FixedLocator, NullFormatter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "helpers"))
sys.path.insert(0, str(ROOT / "micro-analysis"))
import paths as P  # noqa: E402
import census_park_regressions as C  # noqa: E402  (regression data and helpers: controls, land_panel, exposure_sectors, ring_sectors, hav, TG)

OUT = P.FIGS / "sector"
H, A, GEO = P.HARMONIZED, P.HARM_PANELS, P.GEO
KIGALI, WAVES = C.KIGALI, C.WAVES
RES = P.TABLES_REG / "census_park_questions.csv"
CAP = {}

DARK, LIGHT, MID = "#111111", "#C8C8C8", "#6E6E6E"
plt.rcParams.update({"font.family": "sans-serif", "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"], "font.size": 10,
                     "axes.labelsize": 10, "xtick.labelsize": 9, "ytick.labelsize": 9, "legend.fontsize": 9, "pdf.fonttype": 42,
                     "axes.spines.top": False, "axes.spines.right": False, "axes.linewidth": 0.8})
CATS = [("park", "Park-adjacent"), ("ring", "Ring"), ("interior", "Interior")]
STY = {"park": dict(marker="^", s=26, fc="none", ec=DARK, ls="-", lc=DARK),
       "ring": dict(marker="s", s=14, fc="#8F8F8F", ec="#8F8F8F", ls="-.", lc="#4F4F4F"),
       "interior": dict(marker="o", s=11, fc="none", ec=MID, ls=":", lc=MID)}



def _log(msg):
    print(f"[sector-figures] {msg}", flush=True)


def save(fig, name, caption):
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / f"{name}.pdf", bbox_inches="tight")                        # vector master (AER production)
    fig.savefig(OUT / f"{name}.jpg", bbox_inches="tight", dpi=300, pil_kwargs={"quality": 95})  # raster copy for LaTeX/slides
    plt.close(fig)
    CAP[name] = caption



# ============================================================ gate: ranked plots and land-density scatters

def gate_load() -> pd.DataFrame:
    c = pd.read_csv(P.HARMONIZED / "model_sector_cross.csv")[["sid", "district_id", "sector", "lon", "lat", "unit_km2", "border"]]
    c = c[~c.district_id.isin(KIGALI)].copy()
    D = np.column_stack([C.hav(c.lon, c.lat, *xy) for xy in C.TG.GATE_XY.values()])
    c["km_gate"] = D.min(axis=1)
    g = pd.read_csv(P.HARM_PANELS / "treatment_groups.csv")[["sid", "group"]]
    c = c.merge(g, on="sid", how="left")
    c["gate"] = c.group.isin(["Gates", "Gates+"]).astype(int)
    ring = C.ring_sectors()                                    # touch a park-adjacent sector, do not border a park
    c["zone"] = np.where(c.border == 1, "park", np.where(c.sid.isin(ring), "ring", "interior"))
    w = pd.read_csv(P.HARMONIZED / "census_sector_work_per_adult.csv")[["sid", "wave", "nonfarm", "services", "farm"]]
    pop = pd.read_csv(P.HARM_PANELS / "sector_pop_total.csv")
    d = c.merge(w, on="sid").merge(pop, on=["sid", "wave"])
    workers = d.farm + d.nonfarm
    d["farm_sh"], d["services_sh"] = 100 * d.farm / workers, 100 * d.services / workers
    d["density"] = d.pop_total / d.unit_km2
    assert d.sid.nunique() == 381 and d.gate.groupby(d.wave).sum().eq(12).all()
    return d


def gate_ranked(d, wave, col, ylabel, kind):
    """Sectors ordered by distance to the nearest gate. Four classes: sectors touching a gate (black), other park-adjacent
    sectors, ring sectors (touch a park-adjacent sector, do not border a park), and the remaining interior sectors."""
    x = d[d.wave == wave].sort_values("km_gate").reset_index(drop=True)
    n, pos = len(x), np.arange(len(x))
    fig, ax = plt.subplots(figsize=(6.5, 3.6))
    gate = x.gate.values == 1
    cls = [("interior", ~gate & (x.zone.values == "interior"), "Interior sectors"),
           ("ring", ~gate & (x.zone.values == "ring"), "Ring sectors"),
           ("park", ~gate & (x.zone.values == "park"), "Other park-adjacent sectors")]
    sty = {"interior": dict(bar="#D9D9D9", marker="o", s=9, fc="none", ec=MID, mk=None),
           "ring": dict(bar="#8F8F8F", marker="s", s=14, fc="#8F8F8F", ec="#8F8F8F", mk=None),
           "park": dict(bar="#4A4A4A", marker="^", s=24, fc="none", ec=DARK, mk=None)}
    ls = {"interior": ":", "ring": "-.", "park": "--", "gate": "-"}
    lc = {"interior": MID, "ring": "#4F4F4F", "park": DARK, "gate": DARK}

    def mean_line(key, m):
        mu = x[col][m].mean()
        ax.axhline(mu, color=lc[key], linestyle=ls[key], linewidth=1.1, zorder=4,
                   path_effects=[pe.Stroke(linewidth=1.9, foreground="white", alpha=0.7), pe.Normal()])
        return mu

    for key, m, name in cls:
        st = sty[key]
        mu = x[col][m].mean()
        lab = f"{name} ({int(m.sum())}), mean {mu:.0f}%"
        if kind == "bar":
            ax.bar(pos[m], x[col][m], width=1.0, color=st["bar"], linewidth=0, label=lab)
        else:
            ax.scatter(pos[m], x[col][m], s=st["s"], marker=st["marker"], facecolor=st["fc"], edgecolor=st["ec"], linewidth=0.7, label=lab)
        mean_line(key, m)
    mu = x[col][gate].mean()
    lab = f"Sectors touching a park gate ({int(gate.sum())}), mean {mu:.0f}%"
    if kind == "bar":
        ax.bar(pos[gate], x[col][gate], width=1.0, color=DARK, linewidth=0, label=lab)
    else:
        ax.scatter(pos[gate], x[col][gate], s=34, marker="D", color=DARK, linewidth=0, label=lab, zorder=3)
    mean_line("gate", gate)
    ticks = [0, n // 5, 2 * n // 5, 3 * n // 5, 4 * n // 5, n - 1]
    ax.set_xticks(ticks)
    ax.set_xticklabels([f"{x.km_gate[i]:.0f}" for i in ticks])
    ax.set_xlim(-1, n)
    ax.set_xlabel(f"Distance to nearest park gate, km (sectors ranked from nearest to farthest, n = {n})")
    ax.set_ylabel(ylabel)
    ax.set_ylim(0, 100 if kind == "bar" or col == "farm_sh" else None)
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=2, fontsize=8)
    return fig


def gate_scatter(d, wave):
    x = d[d.wave == wave]
    fig, ax = plt.subplots(figsize=(5.2, 4.2))
    o = x[(x.gate == 0) & (x.border == 0)]; b = x[(x.gate == 0) & (x.border == 1)]; g = x[x.gate == 1]
    ax.scatter(o.unit_km2, o.density, s=11, color=LIGHT, edgecolor=MID, linewidth=0.3, label=f"Other sectors ({len(o)})")
    ax.scatter(b.unit_km2, b.density, s=26, marker="^", facecolor="none", edgecolor=DARK, linewidth=0.8, label=f"Other park-adjacent sectors ({len(b)})")
    ax.scatter(g.unit_km2, g.density, s=40, marker="D", color=DARK, linewidth=0, label=f"Sectors touching a park gate ({len(g)})", zorder=3)
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlabel("Land area of the sector (km$^2$, log scale)")
    ax.set_ylabel("Population density (residents per km$^2$, log scale)")
    ax.legend(frameon=False, loc="best")
    return fig




NOTE_GATE = ("One point (bar) per sector for the 381 sectors outside Kigali City, ordered from nearest to farthest from a park gate. Distance is the great-circle distance in "
             "kilometres from the sector centroid to the nearest of four park entrances in use in 2005 (Kinigi, Gisakura, Kitabi, Akagera South Gate); Gishwati-Mukura has no gate. "
             "Black diamonds (bars) are the 12 sectors that contain a gate or sit next to one (10 border a park, 2 are ring sectors); the other 52 park-adjacent sectors are dark open "
             "triangles (dark grey bars); the other 80 ring sectors, which touch a park-adjacent sector without bordering a park, are grey squares (mid-grey bars); the remaining 237 "
             "interior sectors are open circles (light bars). Horizontal lines mark the simple mean of the share within each class (values in the legend): gate-touching solid, "
             "other park-adjacent dashed, ring dash-dotted, interior dotted.")


def section_gate():
    d = gate_load()
    for w in WAVES:
        for col, lab, nm, title, what in (
                ("farm_sh", "Workers in agriculture, forestry and fishing (%)", "farm", "Share of Workers in Agriculture",
                 "Share of workers in agriculture, forestry and fishing, out of workers with a stated industry."),
                ("services_sh", "Workers in services (%)", "services", "Share of Workers in Services",
                 "Share of workers in services (ISIC Rev. 4 sections G-U; Rev. 3 divisions 50-99 in 2002), out of workers with a stated industry.")):
            for kind in ("dot", "bar"):
                extra = " In 2022 farming counts as work only if mainly for the market, so the 2022 farm share is not comparable with earlier waves." if (nm == "farm" and w == 2022) else ""
                save(gate_ranked(d, w, col, lab, kind), f"ranked_{nm}_{kind}_{w}",
                     f"{title} by Distance to the Nearest Park Gate, {w} ({'Dots' if kind == 'dot' else 'Bars'}). {NOTE_GATE} {what} Source: Population and Housing Census {w}.{extra}")
        save(gate_scatter(d, w), f"scatter_land_density_{w}",
             f"Sector Land Area and Population Density, {w}. One point per sector, 381 sectors outside Kigali City, Census {w}. Land area is the sector's area; population density is residents per "
             "square kilometre; both axes are on a log scale. Filled diamonds are the 12 sectors that contain a park gate or sit next to one, open triangles the other 52 sectors that border a park.")
    _log(f"gate: ranked plots and land-density scatters -> {OUT}")



# ============================================================ questions: figures for the regressions

# ---------------------------------------------------------------------------- data
def q_build():
    d = gate_load()                                              # sector x wave: shares, km_gate, gate, border, density
    x = C.controls()                                          # z-scored X, nearest_park
    c = pd.read_csv(C.SECTORS)[["sid", "dist_kigali_km"]]
    raw = pd.read_csv(P.GEO / "raster/sector_terrain.csv")[["sid", "elev_mean"]].merge(
        pd.read_csv(P.GEO / "raster/sector_rainfall.csv")[["sid", "rain_mean"]], on="sid")
    ring = C.ring_sectors()
    d = d.merge(pd.read_csv(C.PANEL)[["sid", "wave", "adults"]], on=["sid", "wave"], validate="1:1")
    d = d.merge(x[["sid", "nearest_park"]], on="sid").merge(raw, on="sid").merge(c, on="sid")
    d["group"] = np.where(d.border == 1, "park", np.where(d.sid.isin(ring), "ring", "interior"))
    return d, x, ring


def q_fit_line(ax, xv, yv, color, ls):
    b = np.polyfit(xv, yv, 1)
    g = np.linspace(xv.min(), xv.max(), 50)
    ax.plot(g, np.polyval(b, g), color=color, linestyle=ls, linewidth=1.2)


# ---------------------------------------------------------------------------- descriptive
def q_geo_scatter(d, col, xlabel, name, log=False):
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


def q_binscatter(d, x):
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
    q = C.question_panel(x)
    q = q[q.wave == 2022].copy()
    q["ln_services"] = np.log(q.services)
    Xm = pd.concat([q[["log_adults"] + C.XVARS], pd.get_dummies(q.nearest_park, drop_first=True, dtype=float)], axis=1)
    Xm = np.column_stack([np.ones(len(q)), Xm.values.astype(float)])
    b = np.linalg.lstsq(Xm, q.ln_services.values, rcond=None)[0]
    q["resid"] = q.ln_services.values - Xm @ b
    w = w.merge(q[["sid", "resid"]], on="sid")
    draw("resid", "ln services workers, residual", "binscatter_gate_services_adjusted",
         "Residual of ln(services workers), 2022, on ln(adults), X and nearest-park dummies; mean in 5-km bins of distance to the nearest gate, 95% intervals.")


def q_boundaries():
    import geopandas as gpd
    g = gpd.read_file(C.SECTOR_BOUNDARIES)
    g["sid"] = g.sector_id.astype(int)
    g = g[["sid", "geometry"]].dissolve("sid").reset_index().to_crs(32736)
    parks = gpd.read_file(P.GEO / "protected-areas/rwanda_protected_areas_geodata_rw.gpkg")
    parks = parks[parks["type"].isin(["National Park", "Volcanoes National Park"])].to_crs(32736)
    return g, parks


def q_draw_map(g, parks, col, name, cap, labels=None, colors=None):
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


def q_maps(d, ring):
    g, parks = q_boundaries()
    w = d[d.wave == 2022][["sid", "group", "services_sh"]]
    g = g.merge(w, on="sid", how="left")
    q_draw_map(g, parks, "group", "map_groups",
             "Park-adjacent (62), ring (82) and interior (237) sectors. Black lines: park boundaries (geodata.rw). Kigali City not in the sample.",
             labels={"park": "Park-adjacent", "ring": "Ring (touches a park-adjacent sector)", "interior": "Interior"},
             colors={"park": "#111111", "ring": "#8C8C8C", "interior": "#E4E4E4"})
    ramp = ["#E4E4E4", "#BDBDBD", "#9A9A9A", "#666666", "#222222"]
    for col, name, cap, lab in (("services_sh", "map_services_2022", "Services share of workers, 2022, in quintiles of the 381 sectors.", "services"),
                                ("built_change", "map_built_change", "Change in built-up share of usable land, 2000-2020 (percentage points, GLAD), in quintiles.", "built")):
        if col == "built_change":
            lp = C.land_panel()
            a = lp[lp.year == 2020].set_index("sid").built_pp - lp[lp.year == 2000].set_index("sid").built_pp
            g = g.merge(a.rename("built_change"), left_on="sid", right_index=True, how="left")
        q = pd.qcut(g[col], 5, labels=False, duplicates="drop")
        edges = g.groupby(q)[col].agg(["min", "max"])
        g[col + "_q"] = q
        q_draw_map(g, parks, col + "_q", name, cap,
                 labels={k: f"{r['min']:.1f} to {r['max']:.1f}" for k, r in edges.iterrows()},
                 colors={k: ramp[int(k)] for k in edges.index})


def q_growth(d):
    w = d.pivot(index="sid", columns="wave", values=["services", "nonfarm"])
    grp = d.drop_duplicates("sid").set_index("sid").group
    for y, lab in (("services", "services"), ("nonfarm", "non-farm")):
        a, b = np.log(w[(y, 2002)]), np.log(w[(y, 2022)])
        z = pd.DataFrame({"x": a, "y": b - a, "p": grp == "park"})
        fig, ax = plt.subplots(figsize=(5.2, 4.0))
        ax.scatter(z[~z.p].x, z[~z.p].y, s=11, color=LIGHT, edgecolor=MID, linewidth=0.3, label=f"Other sectors ({int((~z.p).sum())})")
        ax.scatter(z[z.p].x, z[z.p].y, s=26, marker="^", facecolor="none", edgecolor=DARK, linewidth=0.8, label=f"Park-adjacent sectors ({int(z.p.sum())})")
        q_fit_line(ax, z[~z.p].x, z[~z.p].y, MID, "--"); q_fit_line(ax, z[z.p].x, z[z.p].y, DARK, "-")
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
        q_fit_line(ax, z[~z.p].x, z[~z.p].y22, MID, "--"); q_fit_line(ax, z[z.p].x, z[z.p].y22, DARK, "-")
        ax.set_xlabel(f"ln {lab} workers, 2002"); ax.set_ylabel(f"ln {lab} workers, 2022")
        ax.legend(frameon=False, loc="upper left", fontsize=8)
        save(fig, f"levels_{y}", f"ln {lab} workers in 2022 against 2002, one point per sector. Dotted: 45 degree line. Solid and dashed: linear fit for park-adjacent and other sectors; a vertical gap between them is differential growth at a given 2002 level.")


# ---------------------------------------------------------------------------- regression-based
def q_load_res():
    return pd.read_csv(RES)


def q_trends(d):
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


def q_land_means(lp):
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


def q_adjusted_counts(r, d, lims):
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


def q_adjusted_land(r, lp, lims):
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


def q_balance(x):
    names = {"log_area": "Log area", "log_dist_road": "Log distance to road", "log_dist_kigali": "Log distance to Kigali",
             "elev_mean": "Elevation", "slope_mean": "Slope", "rain_mean": "Rainfall"}
    T, Z = x[x.border == 1], x[x.border == 0]
    diff = [(T[v].mean() - Z[v].mean()) / x[v].std() for v in C.XVARS]
    fig, ax = plt.subplots(figsize=(5.0, 3.2))
    pos = np.arange(len(C.XVARS))
    ax.scatter(diff, pos, s=36, color=DARK)
    ax.axvline(0, color=MID, linewidth=0.7)
    ax.set_yticks(pos); ax.set_yticklabels([names[v] for v in C.XVARS]); ax.invert_yaxis()
    ax.set_xlabel("Park-adjacent minus interior mean, in standard deviations")
    save(fig, "balance_X", "Difference in the geographic controls between the 62 park-adjacent and 319 interior sectors, in standard deviations of each variable over the 381 sectors. "
         "Elevation and rainfall differ by more than one standard deviation.")


# ---------------------------------------------------------------------------- time and district
def q_visits():
    v = pd.read_excel(P.HARMONIZED / "rwanda-parks-tourism-rdb.xlsx", sheet_name="visits_by_park")
    v = v[pd.to_numeric(v.year, errors="coerce").notna()].copy(); v["year"] = v.year.astype(int)
    fig, ax = plt.subplots(figsize=(5.4, 3.6))
    for col, ls, mk in (("Volcanoes", "-", "o"), ("Akagera", "--", "s"), ("Nyungwe", ":", "^")):
        ax.plot(v.year, v[col] / 1e3, linestyle=ls, color=DARK, marker=mk, markersize=3.5, linewidth=1.0, label=col)
    ax.set_xticks(range(2005, 2024, 3)); ax.set_xlabel("Year"); ax.set_ylabel("Visits (thousands)")
    ax.legend(frameon=False, loc="best")
    save(fig, "visits_by_park", "Annual visits to the three tourist parks, Rwanda Development Board.")


def q_district_rent():
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




def section_questions():
    d, x, ring = q_build()
    r = q_load_res()
    q_geo_scatter(d, "elev_mean", "Mean elevation of the sector (m)", "geo_elev_services_2022")
    q_geo_scatter(d, "rain_mean", "Mean annual rainfall (mm)", "geo_rain_services_2022")
    q_geo_scatter(d, "dist_kigali_km", "Distance to Kigali (km)", "geo_kigali_services_2022")
    q_geo_scatter(d, "unit_km2", "Land area of the sector (km$^2$, log scale)", "geo_area_services_2022", log=True)
    q_binscatter(d, x)
    q_maps(d, ring)
    q_growth(d)
    lims = q_trends(d)
    q_adjusted_counts(r, d, lims)
    lp = C.land_panel()
    llims = q_land_means(lp)
    q_adjusted_land(r, lp, llims)
    q_balance(x)
    q_visits()
    q_district_rent()



# ============================================================ descriptive: three categories of sector

# ---------------------------------------------------------------------------- data
def d_build() -> pd.DataFrame:
    d = gate_load()
    d["cat"] = np.where((d.border == 1) | (d.gate == 1), "park", np.where(d.zone == "ring", "ring", "interior"))
    d["urban"] = 100 * d.merge(pd.read_csv(A / "sector_urban_share.csv"), on=["sid", "wave"], how="left").urban_sh.values
    e = pd.read_csv(H / "census_sector_education_panel.csv")[["sid", "wave", "years", "secondary", "literacy"]]
    h = pd.read_csv(H / "census_sector_housing_panel.csv")[["sid", "wave", "improved_floor", "improved_water", "private_toilet", "wall_brick"]]
    h["housing"] = 100 * h[["improved_floor", "improved_water", "private_toilet", "wall_brick"]].mean(axis=1)
    m = pd.read_csv(H / "model_sector_panel.csv")[["sid", "wave", "inmig_share"]]
    j = pd.read_csv(H / "census_sector_jobs_panel.csv", usecols=["sid", "wave", "adults", "n_AG", "n_AG_pt"]).rename(columns={"adults": "adults2064"})
    w = pd.read_csv(A / "sector_work_type.csv")
    lj = pd.read_csv(A / "sector_land_jobs_panel.csv", usecols=["sid", "wave"] + [f"n_{c}" for c in "GHIJKLMNOPQRSTU"])
    for t in (e, h, m, j, w, lj):
        d = d.merge(t, on=["sid", "wave"], how="left", validate="1:1")
    d["ag"] = 100 * d.n_AG_pt / d.adults2064
    d["subsistence"] = np.where(d.wave == 2022, 100 * (d.n_AG_pt - d.n_AG) / d.adults2064, 0.0)
    d["nonfarm_sh"] = 100 - d.farm_sh
    d["inmig"] = 100 * d.inmig_share
    d["occ_service"] = 100 * d.occ_service_sales / d.occ_total
    x = pd.read_csv(C.SECTORS)[["sid", "dist_to_park_km", "nearest_park", "dist_kigali_km", "osm_accom"]]
    geo = (pd.read_csv(GEO / "raster/sector_terrain.csv")[["sid", "elev_mean", "slope_mean"]]
           .merge(pd.read_csv(GEO / "raster/sector_rainfall.csv")[["sid", "rain_mean"]], on="sid")
           .merge(pd.read_csv(GEO / "roads/sector_distances.csv")[["sid", "log_dist_road"]], on="sid"))
    geo["dist_road_km"] = np.exp(geo.log_dist_road)
    d = d.merge(x, on="sid", validate="m:1").merge(geo.drop(columns="log_dist_road"), on="sid", validate="m:1")
    return d


def d_counts(d):
    s = d.drop_duplicates("sid").cat.value_counts()
    return {k: int(s.get(k, 0)) for k, _ in CATS}


# ---------------------------------------------------------------------------- generic plots
def d_scatter(d, x, y, xl, yl, name, cap, wave=2022, xlog=False, fit=True, ylog=False):
    w = d[d.wave == wave].dropna(subset=[x, y]) if wave else d.drop_duplicates("sid").dropna(subset=[x, y])
    fig, ax = plt.subplots(figsize=(5.4, 4.1))
    for k, lab in CATS[::-1]:
        z = w[w.cat == k]
        st = STY[k]
        ax.scatter(z[x], z[y], s=st["s"], marker=st["marker"], facecolor=st["fc"], edgecolor=st["ec"], linewidth=0.7, label=f"{lab} ({len(z)})", zorder=3 if k == "park" else 2)
    xv = np.log(w[x]) if xlog else w[x]
    yv = np.log(w[y]) if ylog else w[y]
    r = np.corrcoef(xv, yv)[0, 1]
    if fit:
        b = np.polyfit(xv, yv, 1)
        g = np.linspace(xv.min(), xv.max(), 50)
        ax.plot(np.exp(g) if xlog else g, np.exp(np.polyval(b, g)) if ylog else np.polyval(b, g), color="black", linewidth=0.9, linestyle="--", label="Linear fit, all sectors", zorder=4)
    if xlog:
        ax.set_xscale("log")
    if ylog:
        ax.set_yscale("log")
    ax.set_xlabel(xl); ax.set_ylabel(yl)
    ax.text(0.98, 0.03, f"correlation {r:.2f}, n = {len(w)}", transform=ax.transAxes, ha="right", va="bottom", fontsize=8)
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=2, fontsize=8)
    save(fig, name, cap + (f" Census {wave}." if wave else "") + " Markers: park-adjacent (open triangles), ring (grey squares), interior (open circles); dashed line is a linear fit over all sectors.")


def d_hist(d, col, xl, name, cap, wave=2022, bins=22, rng=None):
    w = d[d.wave == wave] if wave else d.drop_duplicates("sid")
    w = w.dropna(subset=[col])
    lo, hi = (w[col].min(), w[col].max()) if rng is None else rng
    edges = np.linspace(lo, hi, bins + 1)
    fig, ax = plt.subplots(figsize=(5.4, 3.8))
    for k, lab in CATS:
        z = w[w.cat == k][col].clip(lo, hi)
        n, _ = np.histogram(z, bins=edges)
        ax.stairs(100 * n / len(z), edges, color=STY[k]["lc"], linestyle=STY[k]["ls"], linewidth=1.5, label=f"{lab} ({len(z)}), mean {z.mean():.1f}")
    ax.set_xlabel(xl); ax.set_ylabel("Share of sectors in the category in each bin (%)")
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=1, fontsize=8, handlelength=3.5)
    save(fig, name, cap + (f" Census {wave}." if wave else "") + " Each line is the distribution of one category of sector, as a percentage of the sectors in that category, so categories of different size are comparable. Line styles: park-adjacent solid, ring dash-dotted, interior dotted.")


def d_group_lines(d, col, yl, name, cap, waves=None):
    fig, ax = plt.subplots(figsize=(5.3, 3.8))
    xs = waves or sorted(d.wave.unique())
    for k, lab in CATS:
        z = d[(d.cat == k) & d.wave.isin(xs)].groupby("wave")[col].agg(["mean", "std", "count"])
        ax.errorbar(z.index, z["mean"], yerr=1.96 * z["std"] / np.sqrt(z["count"]), fmt="o", linestyle=STY[k]["ls"], color=STY[k]["lc"], markersize=5,
                    linewidth=1.4, capsize=2, elinewidth=0.7, label=f"{lab} ({int(z['count'].iloc[0])})")
    ax.set_xticks(xs); ax.set_xticklabels([str(int(t)) for t in xs]); ax.set_xlabel("Year"); ax.set_ylabel(yl)
    ax.legend(frameon=False, loc="best", fontsize=8, handlelength=3.5)
    save(fig, name, cap + " Mean over sectors in each category; bars are 95% intervals (unclustered). Line styles: park-adjacent solid, ring dash-dotted, interior dotted.")


def d_stacked(parts, labels, xl, name, cap, shades):
    """parts: DataFrame rows = categories, columns = components (percent summing to 100)."""
    fig, ax = plt.subplots(figsize=(5.6, 4.0))
    bottom = np.zeros(len(parts))
    for c, lab, sh in zip(parts.columns, labels, shades):
        ax.bar(range(len(parts)), parts[c], bottom=bottom, color=sh, edgecolor="white", linewidth=0.6, label=lab, width=0.62)
        bottom += parts[c].values
    ax.set_xticks(range(len(parts))); ax.set_xticklabels(parts.index)
    ax.set_ylabel(xl); ax.set_ylim(0, 100)
    ax.legend(frameon=False, loc="upper left", bbox_to_anchor=(1.0, 1.0), fontsize=8)
    save(fig, name, cap)


# ---------------------------------------------------------------------------- figures
def d_distributions(d):
    for t in (2002, 2012, 2022):
        d_hist(d, "services_sh", "Workers in services (% of recorded workers)", f"hist_services_share_{t}", "Distribution of the services share of workers across sectors.", wave=t, rng=(0, 60))
        d_hist(d, "ag", "Agriculture workers per 100 adults aged 20-64 (including estimated subsistence in 2022)", f"hist_agriculture_share_{t}", "Distribution of the agriculture share of adults across sectors.", wave=t, rng=(0, 100))
    for t in (2012, 2022):
        d_hist(d, "occ_service", "Service and sales occupations (% of workers with a stated occupation)", f"hist_occ_service_sales_{t}", "Distribution of the service-and-sales occupation share (ISCO major group 5).", wave=t, rng=(0, 30))
    for t in (2002, 2022):
        d_hist(d, "years", "Mean years of schooling", f"hist_schooling_years_{t}", "Distribution of mean years of schooling.", wave=t)
    d_hist(d, "housing", "Housing quality index (0-100)", "hist_housing_2022", "Distribution of the housing-quality index (mean of the household shares with an improved floor, improved water, a private toilet and brick walls).", wave=2022)
    d_hist(d, "hh_size", "Mean household size (persons)", "hist_household_size_2022", "Distribution of mean household size.", wave=2022)
    for col, xl, nm in (("elev_mean", "Mean elevation (m)", "elevation"), ("slope_mean", "Mean slope (degrees)", "slope"), ("rain_mean", "Mean annual rainfall (mm)", "rainfall"),
                        ("dist_road_km", "Distance to nearest trunk or primary road (km)", "dist_road"), ("dist_kigali_km", "Distance to Kigali (km)", "dist_kigali"),
                        ("km_gate", "Distance to nearest park gate (km)", "dist_gate")):
        d_hist(d, col, xl, f"hist_geo_{nm}", "Geography of the three categories of sector (the controls used in the regressions).", wave=None)


def d_services_breakdown(d):
    groups = [("Trade (G)", ["n_G"]), ("Transport (H)", ["n_H"]), ("Accommodation and food (I)", ["n_I"]), ("Information, finance, real estate, professional (J-N)", [f"n_{c}" for c in "JKLMN"]),
              ("Public administration, education, health (O-Q)", ["n_O", "n_P", "n_Q"]), ("Arts and other personal services (R-U)", [f"n_{c}" for c in "RSTU"])]
    shades = ["#111111", "#4A4A4A", "#7A7A7A", "#A5A5A5", "#CFCFCF", "#EDEDED"]
    for t in (2002, 2012, 2022):
        w = d[d.wave == t]
        tot = w.groupby("cat")[[c for _, cs in groups for c in cs]].sum()
        parts = pd.DataFrame({lab: tot[cs].sum(axis=1) for lab, cs in groups})
        parts = 100 * parts.div(parts.sum(axis=1), axis=0)
        parts.index = [f"{dict(CATS)[k]}\n({d_counts(d)[k]})" for k in parts.index]
        parts = parts.loc[[f"{dict(CATS)[k]}\n({d_counts(d)[k]})" for k, _ in CATS]]
        d_stacked(parts, [g[0] for g in groups], "% of services workers", f"services_breakdown_{t}",
                f"Composition of services employment (ISIC Rev. 4 sections G-U; 2002 mapped from Rev. 3) by category of sector, Census {t}: counts summed over the sectors in each category.", shades)


def d_occupation_mix(d):
    comp = [("skilled_ag", "Skilled agriculture"), ("elementary", "Elementary"), ("craft", "Craft trades"), ("service_sales", "Service and sales"), ("operators", "Machine operators"),
            ("technicians", "Technicians"), ("professionals", "Professionals"), ("clerical", "Clerical"), ("managers", "Managers")]
    shades = ["#EDEDED", "#CFCFCF", "#A5A5A5", "#111111", "#7A7A7A", "#4A4A4A", "#8F8F8F", "#BDBDBD", "#2E2E2E"]
    for t in (2012, 2022):
        w = d[d.wave == t]
        tot = w.groupby("cat")[[f"occ_{c}" for c, _ in comp]].sum()
        parts = 100 * tot.div(tot.sum(axis=1), axis=0)
        parts.columns = [c for c, _ in comp]
        parts = parts.loc[[k for k, _ in CATS]]
        parts.index = [f"{dict(CATS)[k]}\n({d_counts(d)[k]})" for k in parts.index]
        d_stacked(parts, [l for _, l in comp], "% of workers with a stated occupation", f"occupation_mix_{t}",
                f"Occupation (ISCO major group) of workers by category of sector, Census {t}. In 2022 farming counts as work only if mainly for the market, so skilled agriculture is undercounted.", shades)


def d_scatters(d):
    D, AGL = "Population density (residents per km$^2$, log scale)", "Agriculture workers per 100 adults aged 20-64"
    d_scatter(d, "density", "services_sh", D, "Workers in services (% of recorded workers)", "scatter_density_services", "Population density against the services share.", xlog=True)
    d_scatter(d, "density", "ag", D, AGL + " (incl. subsistence)", "scatter_density_agriculture", "Population density against the agriculture share of adults.", xlog=True)
    d_scatter(d, "density", "urban", D, "Urban share of the sector's population (%)", "scatter_density_urban", "Population density against the urban share.", xlog=True)
    d_scatter(d, "density", "subsistence", D, "Estimated subsistence farmers per 100 adults aged 20-64", "scatter_density_subsistence", "Population density against estimated subsistence farming (the 2022 add-back).", xlog=True)
    d_scatter(d, "density", "farm_sh", D, "Farm workers (% of recorded workers)", "scatter_density_farm_recorded", "Population density against the recorded farm share of workers.", xlog=True)
    HH = "Mean household size (persons)"
    d_scatter(d, "hh_size", "subsistence", HH, "Estimated subsistence farmers per 100 adults", "scatter_hhsize_subsistence", "Household size against estimated subsistence farming.")
    d_scatter(d, "hh_size", "ag", HH, AGL + " (incl. subsistence)", "scatter_hhsize_agriculture", "Household size against the agriculture share of adults.")
    d_scatter(d, "hh_size", "services_sh", HH, "Workers in services (% of recorded workers)", "scatter_hhsize_services", "Household size against the services share.")
    d_scatter(d, "years", "nonfarm_sh", "Mean years of schooling", "Non-farm workers (% of recorded workers)", "scatter_schooling_nonfarm", "Schooling against the non-farm share of workers.")
    d_scatter(d, "secondary", "nonfarm_sh", "Share of adults with secondary schooling", "Non-farm workers (% of recorded workers)", "scatter_secondary_nonfarm", "Secondary schooling against the non-farm share of workers.")
    d_scatter(d, "urban", "nonfarm_sh", "Urban share of the sector's population (%)", "Non-farm workers (% of recorded workers)", "scatter_urban_nonfarm", "Urban share against the non-farm share of workers.")
    HQ = "Housing quality index (0-100)"
    d_scatter(d, "housing", "services_sh", HQ, "Workers in services (% of recorded workers)", "scatter_housing_services", "Housing quality index (mean of the household shares with improved floor, improved water, private toilet and brick walls) against the services share.")
    d_scatter(d, "dist_to_park_km", "housing", "Distance from the sector to the nearest park boundary (km)", HQ, "scatter_housing_distance_park", "Housing quality index (mean of the household shares with improved floor, improved water, private toilet and brick walls) against distance to the nearest park.")
    d_scatter(d, "km_gate", "housing", "Distance from sector centroid to the nearest park gate (km)", HQ, "scatter_housing_distance_gate", "Housing quality index (mean of the household shares with improved floor, improved water, private toilet and brick walls) against distance to the nearest park gate.")
    d_scatter(d, "inmig", "services_sh", "In-migrants (% of residents)", "Workers in services (% of recorded workers)", "scatter_migration_services", "In-migration share against the services share.")
    d_scatter(d, "inmig", "ag", "In-migrants (% of residents)", AGL + " (incl. subsistence)", "scatter_migration_agriculture", "In-migration share against the agriculture share of adults.")
    d_scatter(d, "rain_mean", "ag", "Mean annual rainfall (mm)", AGL + " (incl. subsistence)", "scatter_rainfall_agriculture", "Rainfall against the agriculture share of adults.")
    d_scatter(d, "elev_mean", "services_sh", "Mean elevation (m)", "Workers in services (% of recorded workers)", "scatter_elevation_services", "Elevation against the services share.")
    d_scatter(d, "occ_service", "services_sh", "Service and sales occupations (% of workers with a stated occupation)", "Workers in services (% of recorded workers)", "scatter_occupation_vs_industry",
            "Two measures of service work: occupation (ISCO group 5) against industry (ISIC G-U).")


def d_land_forest(d):
    g = pd.read_csv(A / "sector_landcover_glclu.csv").rename(columns={"sector_id": "sid"})
    for c in ("crop", "built", "tree"):
        g[f"{c}_sh"] = 100 * g[f"{c}_out_ha"] / g[[f"{k}_out_ha" for k in ("crop", "built", "tree", "water", "other")]].sum(axis=1)
    cat = d.drop_duplicates("sid")[["sid", "cat", "density", "unit_km2"]]
    g = g.merge(cat, on="sid", how="inner").rename(columns={"year": "wave"})
    for c, lab, nm in (("crop_sh", "Cropland share of usable land (%)", "cropland"), ("built_sh", "Built-up share of usable land (%)", "builtup"), ("tree_sh", "Tree cover share of usable land (%)", "tree")):
        d_group_lines(g, c, lab, f"land_{nm}_by_category", f"{lab.split(' (')[0]} by category of sector, GLAD land cover 2000-2020 (usable = outside the park).", waves=[2000, 2005, 2010, 2015, 2020])
    ch = g[g.wave == 2020].set_index("sid").built_sh - g[g.wave == 2000].set_index("sid").built_sh
    z = cat.merge(ch.rename("built_change"), left_on="sid", right_index=True).assign(wave=2022)
    d_hist(z, "built_change", "Change in built-up share of usable land, 2000-2020 (percentage points)", "hist_builtup_change", "Distribution of built-up change.", wave=None, rng=(0, 20))
    # agriculture and land cover
    y = d[d.wave == 2022][["sid", "ag", "cat"]].merge(g[g.wave == 2020][["sid", "crop_sh"]], on="sid").assign(wave=2022)
    d_scatter(y.assign(), "crop_sh", "ag", "Cropland share of usable land, 2020 (%)", "Agriculture workers per 100 adults (incl. subsistence)", "scatter_cropland_agriculture", "Cropland share against the agriculture share of adults.")
    hs = pd.read_csv(A / "sector_hansen_annual.csv")
    tc = hs.groupby("sid").agg(tc=("treecover2000_ha", "first"), loss=("loss_ha", lambda v: v[hs.loc[v.index, "year"].between(2001, 2020)].sum())).reset_index()
    tc = tc.merge(d.drop_duplicates("sid")[["sid", "cat", "dist_to_park_km", "unit_km2"]], on="sid").assign(wave=2022)
    tc["loss_pct"] = 100 * tc.loss / tc.tc
    tc["tc_pct"] = 100 * tc.tc / (100 * tc.unit_km2)
    d_scatter(tc[tc.tc >= 50], "dist_to_park_km", "loss_pct", "Distance from the sector to the nearest park boundary (km)", "Tree cover lost 2001-2020 (% of 2000 tree cover)", "scatter_forest_loss_distance_park",
            "Forest loss against distance to the nearest park (Hansen; sectors with at least 50 ha of tree cover in 2000).", wave=None)
    ag22 = d[d.wave == 2022][["sid", "ag"]]
    d_scatter(tc.merge(ag22, on="sid"), "tc_pct", "ag", "Tree cover in 2000 (% of sector area)", "Agriculture workers per 100 adults (incl. subsistence)", "scatter_treecover_agriculture", "Tree cover in 2000 against the agriculture share of adults.", wave=None)
    # transition matrix
    t = pd.read_csv(A / "glclu_transitions_2000_2020.csv")
    m = t.groupby(["from", "to"]).ha.sum().unstack(fill_value=0)
    keep = [c for c in ("crop", "built", "tree", "water") if c in m.index and c in m.columns]
    m = m.loc[keep, keep]
    m = 100 * m.div(m.sum(axis=1), axis=0)
    fig, ax = plt.subplots(figsize=(4.8, 4.0))
    ax.imshow(m.values, cmap="Greys", vmin=0, vmax=100)
    ax.set_xticks(range(len(keep))); ax.set_xticklabels(keep); ax.set_yticks(range(len(keep))); ax.set_yticklabels(keep)
    for i in range(len(keep)):
        for j in range(len(keep)):
            ax.text(j, i, f"{m.values[i, j]:.1f}", ha="center", va="center", color="white" if m.values[i, j] > 55 else "black", fontsize=9)
    ax.set_xlabel("Land cover in 2020"); ax.set_ylabel("Land cover in 2000")
    for s_ in ax.spines.values():
        s_.set_visible(True)
    save(fig, "land_transitions_2000_2020", "Share of 2000 land in each class (rows) that was in each class in 2020 (columns), %, all sectors in treatment_groups.csv (GLAD land cover).")


def d_tourism(d):
    ec = pd.read_csv(A / "sector_ec2011_accommodation_food.csv").rename(columns={"ec_sector": "sid"})
    ec["est"] = ec.n_55.fillna(0) + ec.n_56.fillna(0)
    ec["wk"] = ec.wk_55.fillna(0) + ec.wk_56.fillna(0)
    ec["acc"] = ec.n_55.fillna(0)
    z = d.drop_duplicates("sid")[["sid", "km_gate", "cat"]].merge(ec, on="sid", how="left").fillna({"est": 0, "wk": 0, "acc": 0})
    edges = list(range(0, 100, 10))
    z["bin"] = pd.cut(z.km_gate, edges, right=False)
    for col, yl, nm in (("acc", "Accommodation establishments per sector, 2011", "ec_accommodation_by_gate"), ("est", "Accommodation and food establishments per sector, 2011", "ec_accfood_by_gate"),
                        ("wk", "Workers in accommodation and food per sector, 2011", "ec_workers_by_gate")):
        g = z.groupby("bin", observed=True)[col].agg(["mean", "std", "count"])
        mid = np.array([b.left + 5 for b in g.index])
        fig, ax = plt.subplots(figsize=(5.4, 3.6))
        ax.errorbar(mid, g["mean"], yerr=1.96 * g["std"] / np.sqrt(g["count"]), fmt="o", color=DARK, ecolor=MID, capsize=2, elinewidth=0.8, markersize=5)
        ax.set_xlabel("Distance from sector centroid to nearest park gate, km (10-km bins)"); ax.set_ylabel(yl)
        save(fig, nm, "Mean over sectors in 10-km bins of distance to the nearest gate; bars are 95% intervals (unclustered). Establishment Census 2011 (ISIC 55 accommodation, 56 food and beverage); sectors with none count as zero.")
    # OSM accommodation by park
    o = d.drop_duplicates("sid").assign(park=lambda v: np.where((v.border == 1), v.nearest_park.str.replace(" National Park", ""), "Not park-adjacent"))
    b = o.groupby("park").osm_accom.sum().sort_values(ascending=False)
    fig, ax = plt.subplots(figsize=(5.4, 3.6))
    ax.bar(range(len(b)), b.values, color="#6E6E6E", width=0.6)
    ax.set_xticks(range(len(b))); ax.set_xticklabels(b.index, rotation=0, fontsize=8)
    ax.set_ylabel("OpenStreetMap accommodation points")
    save(fig, "osm_accommodation_by_park", "OpenStreetMap accommodation points located in sectors that border each park, and in all other sectors (OSM tourism extract).")
    # visits vs services share, park level
    v = pd.read_excel(H / "rwanda-parks-tourism-rdb.xlsx", sheet_name="visits_by_park")
    v = v[pd.to_numeric(v.year, errors="coerce") == 2019].iloc[0]
    rows = []
    for park, col in (("Volcanoes National Park", "Volcanoes"), ("Akagera National Park", "Akagera"), ("Nyungwe National Park", "Nyungwe")):
        s_ = d[(d.wave == 2022) & (d.border == 1) & (d.nearest_park == park)]
        rows.append((col, v[col] / 1e3, s_.services_sh.mean(), len(s_)))
    fig, ax = plt.subplots(figsize=(5.0, 3.6))
    for nm_, x_, y_, n_ in rows:
        ax.scatter(x_, y_, s=40, color=DARK)
        ax.annotate(f"{nm_} ({n_} sectors)", (x_, y_), textcoords="offset points", xytext=(6, 4), fontsize=8)
    ax.set_xlabel("Park visits in 2019 (thousands)"); ax.set_ylabel("Mean services share of workers in bordering sectors, 2022 (%)")
    ax.set_xlim(left=0)
    save(fig, "visits_vs_services_by_park", "Visits in 2019 (RDB) against the mean 2022 services share of the sectors that border each of the three tourist parks. Three observations: descriptive only.")


def d_district(d):
    e = pd.read_csv(P.HARM_DISTRICT / "district-park-exposure-border.csv")[["district_id", "district", "n_adjacent_sectors", "adj_share_pop_2022"]]
    lab = pd.read_csv(P.HARM_DISTRICT / "district-labour-status.csv").drop(columns=[c for c in ("district", "n_adjacent_sectors") if c in ()])
    lab = lab[["district_id", "year", "share_wage", "share_self", "share_family"]].merge(e, on="district_id")
    lab["exposed"] = lab.n_adjacent_sectors > 0
    for col, nm, t in (("share_wage", "wage", "Wage employees"), ("share_self", "self", "Self-employed"), ("share_family", "family", "Contributing family workers")):
        fig, ax = plt.subplots(figsize=(5.3, 3.8))
        for flag, ls, colr, name in ((True, "-", DARK, "Districts with a park-adjacent sector"), (False, "--", MID, "Other districts")):
            z = lab[lab.exposed == flag].groupby("year")[col].agg(["mean", "std", "count"])
            ax.errorbar(z.index, 100 * z["mean"], yerr=100 * 1.96 * z["std"] / np.sqrt(z["count"]), fmt="o", linestyle=ls, color=colr, markersize=5, linewidth=1.4, capsize=2, elinewidth=0.7,
                        label=f"{name} ({int(z['count'].iloc[0])})")
        ax.set_xticks(sorted(lab.year.unique())); ax.set_xlabel("Survey year"); ax.set_ylabel(f"{t} (% of workers)")
        ax.legend(frameon=False, loc="best", fontsize=8, handlelength=3.5)
        save(fig, f"district_status_{nm}", f"{t} as a share of workers, mean over districts (Labour Force Survey district labour-status panel, 2017-2025). Bars: 95% intervals. Solid: 14 districts with a park-adjacent sector; dashed: 13 others.")
    ag = pd.read_csv(P.HARM_DISTRICT / "district-ag-productivity.csv")[["district_id", "year", "value_per_ha_dprice", "output_per_worker_dprice"]].merge(e, on="district_id")
    yr = ag.year.max()
    ag = ag[ag.year == yr]
    for col, yl, nm in (("value_per_ha_dprice", "Agricultural output value per hectare (RWF)", "ag_value_per_ha"), ("output_per_worker_dprice", "Agricultural output value per ag worker (RWF)", "ag_output_per_worker")):
        fig, ax = plt.subplots(figsize=(5.2, 3.8))
        x_, y_ = 100 * ag.adj_share_pop_2022, ag[col]
        ax.scatter(x_[ag.n_adjacent_sectors > 0], y_[ag.n_adjacent_sectors > 0], s=26, marker="^", facecolor="none", edgecolor=DARK, linewidth=0.8, label="Districts with a park-adjacent sector")
        ax.scatter(x_[ag.n_adjacent_sectors == 0], y_[ag.n_adjacent_sectors == 0], s=14, facecolor="none", edgecolor=MID, linewidth=0.7, label="Other districts")
        ax.set_xlabel("Population share living in park-adjacent sectors, 2022 (%)"); ax.set_ylabel(yl + f", {int(yr)}")
        ax.legend(frameon=False, loc="best", fontsize=8)
        save(fig, f"district_{nm}_exposure", f"{yl} in the {int(yr)} survey round against district exposure, one point per district (EICV agricultural module).")
    lp = pd.read_csv(P.HARM_DISTRICT / "district-land-prices.csv")
    lp = lp[(lp.measure == "rent") & (lp.source == "EICV")][["district_id", "round", "median_per_ha_2014rwf", "n_parcels"]].merge(e, on="district_id")
    for rd in (2001, int(lp["round"].max())):
        z = lp[lp["round"] == rd]
        fig, ax = plt.subplots(figsize=(5.2, 3.8))
        ex = z.n_adjacent_sectors > 0
        ax.scatter(100 * z.adj_share_pop_2022[ex], z.median_per_ha_2014rwf[ex], s=26, marker="^", facecolor="none", edgecolor=DARK, linewidth=0.8, label="Districts with a park-adjacent sector")
        ax.scatter(100 * z.adj_share_pop_2022[~ex], z.median_per_ha_2014rwf[~ex], s=14, facecolor="none", edgecolor=MID, linewidth=0.7, label="Other districts")
        ax.set_yscale("log"); ticks = [10000, 20000, 50000, 100000, 200000, 500000, 1000000]
        ax.yaxis.set_major_locator(FixedLocator(ticks)); ax.set_yticklabels([f"{t:,}" for t in ticks]); ax.yaxis.set_minor_formatter(NullFormatter())
        ax.set_xlabel("Population share living in park-adjacent sectors, 2022 (%)"); ax.set_ylabel(f"Median land rent per hectare, {rd} (2014 RWF, log scale)")
        ax.legend(frameon=False, loc="best", fontsize=8)
        save(fig, f"district_rent_exposure_{rd}", f"Median land rent per hectare against district exposure, EICV round {rd}; one point per district. District-round cells have as few as 19 parcels.")




def section_descriptive():
    d = d_build()
    _log(f"descriptive categories: {d_counts(d)}")
    d_distributions(d); d_services_breakdown(d); d_occupation_mix(d); d_scatters(d); d_land_forest(d); d_tourism(d); d_district(d)


def write_tex(only):
    sections = [("gate", "Ranked by distance to a park gate"), ("questions", "Figures for the regressions"), ("descriptive", "Descriptive figures")]
    esc = lambda s: s.replace("%", "\\%").replace("&", "\\&").replace("_", " ").replace("#", "\\#")
    body = []
    for key, title in sections:
        if key in only:
            body.append(f"\\section*{{{title}}}")
            body += [f"\\begin{{figure}}[H]\\centering\\includegraphics[width=0.78\\textwidth]{{{OUT / (n + '.pdf')}}}\n\\caption{{\\small {esc(CAP[n])}}}\n\\end{{figure}}" for n in SECTION_FIGS[key]]
    tex = ("\\documentclass[11pt]{article}\n\\usepackage[margin=1in]{geometry}\n\\usepackage{graphicx,float}\n\\usepackage[font=small,labelfont=bf]{caption}\n\\begin{document}\n"
           + "\n".join(body) + "\n\\end{document}\n")
    p = ROOT / "docs" / "sector_figures.tex"
    p.write_text(tex)
    _log(f"-> {p} (compile with pdflatex)")


SECTION_FIGS = {}
SECTIONS = {"gate": section_gate, "questions": section_questions, "descriptive": section_descriptive}


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--only", nargs="+", choices=list(SECTIONS))
    a.add_argument("--tex", action="store_true", help="write docs/sector_figures.tex")
    args = a.parse_args(argv)
    todo = args.only or list(SECTIONS)
    for k in todo:
        before = set(CAP)
        SECTIONS[k]()
        SECTION_FIGS[k] = sorted(set(CAP) - before)
        _log(f"{k}: {len(SECTION_FIGS[k])} figures -> {OUT}")
    if args.tex:
        write_tex(todo)
    return 0


if __name__ == "__main__":
    sys.exit(main())
