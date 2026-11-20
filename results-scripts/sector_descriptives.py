"""Descriptive figures, maps and summary tables on the sector panel. Run micro-analysis/sector_panel.py first.

Run every section in order:   python results-scripts/sector_descriptives.py
Run some sections:            python results-scripts/sector_descriptives.py --only <name> [<name> ...]
List the sections:            python results-scripts/sector_descriptives.py --list

Sections, in run order:
  figures                (was 05_figures.py) Descriptive figures on the repo treatment groups. Writes to output/figures and output/maps (names in helpers/common.py FIGURE_NAMES).
  tables                 (was 06_tables.py) Summary-stat tables T1-T7 on the repo treatment groups. Writes to output/tables/summary_statistics (names in helpers/common.py TABLE_NAMES).
  tourism_definitions    (was 08_tourism_definitions.py) Tourism employment under three definitions.
  map_change             (was 13_map_change.py) Side-by-side maps: change 2012-2022 (Census) in the share of each sector's workers
  map_accommodation      (was 14_map_ec_accommodation.py) Sector-level map of accommodation (ISIC 55) vs food & beverage service (ISIC 56) from the
  musanze_cells          (was 15_musanze_cells.py) Two-cell illustration for the toy model.
  map_admin_levels       (was 20_map_admin_levels.py) Reference map of Rwanda's administrative levels: 30 districts, 416 sectors, 2,148 cells, with national parks
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
from common import *  # noqa: F401,F403  paths, ISIC groups, figure/table names, LaTeX tables (helpers/common.py)


def section_figures():
    """Descriptive figures on the repo treatment groups. Writes to output/figures and output/maps (names in helpers/common.py FIGURE_NAMES).
Group colours: treated tiers in reds (repo PARK #c1121f), control navy (repo NONPARK #1b4965), urban greys.
Land colours from rwa-trs/helpers/viz_style.py LANDCOVER."""
    import numpy as np, pandas as pd, geopandas as gpd, matplotlib.pyplot as plt
    from matplotlib.colors import TwoSlopeNorm
    from matplotlib.patches import Patch

    GROUPS = ["Gates", "Gates+", "Bordering", "Control", "Towns", "Kigali"]
    GC = {"Gates": "#6a040f", "Gates+": "#c1121f", "Bordering": "#f4978e", "Control": "#1b4965", "Towns": "#8d8d8d", "Kigali": "#c9c9c9"}
    LC = {"crop": ("Cropland", "#e9c46a"), "built": ("Built-up", "#8b5fbf"), "tree": ("Tree cover", "#2a9d8f"), "other": ("Short veg. / bare", "#cbd5c0")}
    JC = {"AG": ("Agriculture", "#e9c46a"), "IND": ("Industry", "#8d99ae"), "S_loc": ("Local services", "#a8dadc"),
          "S_bus": ("Business svc (J,K,M)", "#1b4965"), "S_tour": ("Tourism svc (I,R)", "#c1121f")}
    d = pd.read_csv(OUT_D / "sector_panel_desc.csv")
    cb = pd.read_csv(OUT_D / "sector_cropland_builtup_glclu.csv")
    tg = pd.read_csv(OUT_D / "treatment_groups.csv")
    GEO = DATA / "geo-data"
    sec = gpd.read_file(GEO / "protected-areas" / "sectors_park_exposure_geodatarw.gpkg")[["sector_id", "geometry"]]
    sec["sid"] = sec.sector_id.astype(int); sec = sec.merge(tg[["sid", "group", "treated_any"]], on="sid").to_crs(32736)
    sec["geometry"] = sec.geometry.simplify(120)            # 120 m tolerance: invisible at figure scale, 20x faster
    pk = gpd.read_file(GEO / "protected-areas" / "rwanda_protected_areas_geodata_rw.gpkg")
    pk = pk[pk.designate.astype(str).str.contains("National Park", case=False, na=False)].to_crs(32736)
    pk["geometry"] = pk.geometry.simplify(120)
    lakes = gpd.read_file(GEO / "water" / "rwanda_lakes_osm.geojson").to_crs(32736); lakes["geometry"] = lakes.geometry.simplify(120)
    dist = gpd.read_file(GEO / "admin-boundaries" / "geodatarw_district_boundary.gpkg").to_crs(32736); dist["geometry"] = dist.geometry.simplify(120)
    xmin, ymin, xmax, ymax = sec.total_bounds
    treated = sec[sec.treated_any == 1].dissolve()

    def basemap(ax):
        lakes.plot(ax=ax, color="#cfe3f0", lw=0, zorder=0)
        pk.plot(ax=ax, facecolor="#dfe9df", edgecolor="#2E6B3E", lw=0.5, hatch="////", zorder=3)
        dist.boundary.plot(ax=ax, color="#7a7a7a", lw=0.25, zorder=4)
        treated.boundary.plot(ax=ax, color="black", lw=0.7, zorder=5)
        ax.set_xlim(xmin, xmax); ax.set_ylim(ymin, ymax); ax.set_axis_off()

    def cbar(fig, ax, cmap, norm, label, fmt="{:.0%}"):
        sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm); cb_ = fig.colorbar(sm, ax=ax, fraction=0.04, pad=0.01, shrink=0.8)
        cb_.ax.tick_params(labelsize=6.5); cb_.set_label(label, fontsize=7)
        cb_.ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: fmt.format(x)))

    def map_grid(rows, years, fname, title, change_from=None, change_to=None, yearcol="wave"):
        """rows: list of (var, label, cmap, vmax_q). Last column = change between change_from and change_to (diverging)."""
        ncol = len(years) + 1
        fig, axes = plt.subplots(len(rows), ncol, figsize=(2.55 * ncol, 2.6 * len(rows)), squeeze=False)
        for r, (var, lab, cmap, q, src) in enumerate(rows):
            df = src
            vmax = df[var].quantile(q); norm = plt.Normalize(0, vmax)
            for c, y in enumerate(years):
                s = df[df[yearcol] == y].set_index("sid")[var]
                g = sec.merge(s.rename("v"), left_on="sid", right_index=True, how="left")
                g.plot(ax=axes[r, c], column="v", cmap=cmap, norm=norm, lw=0.05, edgecolor="white", zorder=1, missing_kwds=dict(color="#eeeeee"))
                basemap(axes[r, c]); axes[r, c].set_title(f"{lab}, {y}", fontsize=8, loc="left")
            cbar(fig, axes[r, len(years) - 1], cmap, norm, lab)
            a = df[df[yearcol] == change_from].set_index("sid")[var]; b = df[df[yearcol] == change_to].set_index("sid")[var]
            ch = (b - a); m = np.nanquantile(np.abs(ch), 0.97); nrm = TwoSlopeNorm(0, -m, m)
            g = sec.merge(ch.rename("v"), left_on="sid", right_index=True, how="left")
            g.plot(ax=axes[r, -1], column="v", cmap="RdBu_r" if var not in ("sh_ag", "crop_sh", "tree_sh", "lam") else "BrBG", norm=nrm, lw=0.05, edgecolor="white", zorder=1)
            basemap(axes[r, -1]); axes[r, -1].set_title(f"Change {change_from}-{str(change_to)[2:]} (pp)", fontsize=8, loc="left")
            cbar(fig, axes[r, -1], "RdBu_r" if var not in ("sh_ag", "crop_sh", "tree_sh", "lam") else "BrBG", nrm, "pp", fmt="{:+.0%}")
        handles = [Patch(facecolor="white", edgecolor="black", label="Treated sectors (44): bordering or near a gate"),
                   Patch(facecolor="#dfe9df", edgecolor="#2E6B3E", hatch="////", label="National park")]
        fig.legend(handles=handles, loc="lower left", ncol=2, fontsize=7.5, frameon=False, bbox_to_anchor=(0.01, -0.01))
        fig.suptitle(title, x=0.01, ha="left", fontsize=10); fig.tight_layout(rect=(0, 0.03, 1, 1))
        fig.savefig(OUT_F / fname, bbox_inches="tight"); plt.close(fig)

    # ---- F1 jobs maps ----
    import os
    SKIP = os.environ.get("SKIP_MAPS") == "1"
    if not SKIP: map_grid([("sh_ag", "Agriculture share", "YlOrBr", 0.99, d), ("sh_tour", "Tourism svc share", "Reds", 0.97, d),
              ("sh_svc", "Services excl. G,O share", "Blues", 0.97, d)], [2002, 2012, 2022], "fig01_map_jobs_levels.png",
             "Employment shares by sector, Census, workers 20-64 (2022 agriculture reconstructed)", 2012, 2022)
    # ---- F2 land maps ----
    cbl = cb.copy()
    if not SKIP: map_grid([("crop_sh", "Cropland share", "YlOrBr", 0.99, cbl), ("built_sh", "Built-up share", "Purples", 0.97, cbl),
              ("tree_sh", "Tree-cover share", "Greens", 0.99, cbl)], [2000, 2005, 2010, 2015, 2020], "fig02_map_land_glclu.png",
             "Land use outside parks, share of usable land, GLCLU v2 (30 m)", 2000, 2020, yearcol="year")

    # ---- F3 stacked jobs by group x wave ----
    def stacked(ax, frame, cats, colors, xlabels, totals=None, gap_every=None):
        x = np.arange(len(frame)); bottom = np.zeros(len(frame))
        for c in cats:
            ax.bar(x, frame[c].values, bottom=bottom, color=colors[c], width=0.82, edgecolor="white", lw=0.6, label=c)
            for i, (v, b) in enumerate(zip(frame[c].values, bottom)):
                if v >= 0.06: ax.text(x[i], b + v / 2, f"{v:.0%}", ha="center", va="center", fontsize=6, color="#222")
            bottom += frame[c].values
        ax.set_xticks(x); ax.set_xticklabels(xlabels, fontsize=6.5); ax.set_ylim(0, 1.06); ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
        ax.grid(axis="x", visible=False)
        if totals is not None:
            for i, t in enumerate(totals): ax.text(x[i], 1.01, t, ha="center", va="bottom", fontsize=5.5, color="#444")

    cats = list(JC)
    gw = d.groupby(["group", "wave"])[cats + ["workers"]].sum()
    gw = gw.reindex(pd.MultiIndex.from_product([GROUPS, [2002, 2012, 2022]]))
    sh = gw[cats].div(gw[cats].sum(1), axis=0)
    fig, ax = plt.subplots(figsize=(11, 4.2))
    # insert spacing between groups
    pos, labs, rows = [], [], []
    for i, g in enumerate(GROUPS):
        for j, w in enumerate([2002, 2012, 2022]): rows.append((g, w)); labs.append(f"{str(w)[2:]}")
    fr = sh.loc[rows]
    xs = np.array([i * 3.6 + j for i in range(len(GROUPS)) for j in range(3)], float)
    bottom = np.zeros(len(fr))
    for c in cats:
        ax.bar(xs, fr[c].values, bottom=bottom, color=JC[c][1], width=0.86, edgecolor="white", lw=0.6, label=JC[c][0])
        for i, (v, b) in enumerate(zip(fr[c].values, bottom)):
            if v >= 0.05: ax.text(xs[i], b + v / 2, f"{v:.0%}", ha="center", va="center", fontsize=6, color="white" if c in ("S_bus", "S_tour") else "#222")
        bottom += fr[c].values
    tot = gw.loc[rows, "workers"].values
    for xx, t in zip(xs, tot): ax.text(xx, 1.01, f"{t/1e3:,.0f}k", ha="center", va="bottom", fontsize=5.5, color="#444")
    ax.set_xticks(xs); ax.set_xticklabels(["2002", "2012", "2022"] * len(GROUPS), fontsize=6.5)
    for i, g in enumerate(GROUPS):
        n = tg.group.eq(g).sum(); ax.text(i * 3.6 + 1, -0.13, f"{g} ({n})", ha="center", fontsize=8, transform=ax.get_xaxis_transform(), color=GC[g] if g != "Kigali" else "#777", weight="bold")
    ax.set_ylim(0, 1.07); ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}")); ax.grid(axis="x", visible=False)
    ax.legend(ncol=5, fontsize=7.5, frameon=False, loc="upper center", bbox_to_anchor=(0.5, 1.13))
    ax.set_title("Employment composition by treatment group and Census wave (number above bar = workers 20-64)", loc="left", fontsize=9, pad=24)
    fig.tight_layout(); fig.savefig(OUT_F / "fig03_stacked_jobs_groups.png", bbox_inches="tight"); plt.close(fig)

    # ---- F3b per park ----
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.6), sharey=True)
    for ax, p in zip(axes, ["Volcanoes", "Nyungwe", "Akagera"]):
        sub = d[(d.park == p) & d.group.isin(["Gates", "Gates+", "Bordering", "Control"])]
        gg = ["Gates", "Gates+", "Bordering", "Control"]
        t = sub.groupby(["group", "wave"])[cats + ["workers"]].sum().reindex(pd.MultiIndex.from_product([gg, [2002, 2012, 2022]])).dropna()
        s = t[cats].div(t[cats].sum(1), axis=0)
        xs = np.array([gg.index(g) * 3.6 + [2002, 2012, 2022].index(w) for g, w in s.index], float)
        b = np.zeros(len(s))
        for c in cats:
            ax.bar(xs, s[c].values, bottom=b, color=JC[c][1], width=0.86, edgecolor="white", lw=0.5, label=JC[c][0]); b += s[c].values
        for xx, (g, w), v in zip(xs, s.index, s["AG"].values): ax.text(xx, v / 2, f"{v:.0%}", ha="center", va="center", fontsize=5.5, rotation=90)
        ax.set_xticks(xs); ax.set_xticklabels([str(w)[2:] for _, w in s.index], fontsize=6.5); ax.set_xlim(-0.7, 3 * 3.6 + 2.7)
        for g in gg:
            if g in s.index.get_level_values(0):
                n = tg[(tg.park == p) & (tg.group == g)].shape[0]
                ax.text(gg.index(g) * 3.6 + 1, -0.11, f"{g} ({n})", ha="center", fontsize=7, transform=ax.get_xaxis_transform(), color=GC[g], weight="bold")
        ax.set_title(f"{p} side", loc="left", fontsize=9); ax.grid(axis="x", visible=False)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    h, l_ = axes[0].get_legend_handles_labels()
    fig.legend(h, l_, ncol=5, fontsize=7.5, frameon=False, loc="upper center", bbox_to_anchor=(0.5, 0.97))
    fig.suptitle("Employment composition by park side, Census waves (label in bar = agriculture share; control = control sectors whose nearest park is that park)", x=0.01, ha="left", fontsize=9, y=1.02)
    fig.subplots_adjust(left=0.05, right=0.99, top=0.86, bottom=0.14, wspace=0.06); fig.savefig(OUT_F / "fig04_stacked_jobs_by_park.png", bbox_inches="tight"); plt.close(fig)

    # ---- F5 stacked land by group x 5 years ----
    years = [2000, 2005, 2010, 2015, 2020]
    lg = cb.groupby(["group", "year"])[["crop", "built", "tree", "other"]].sum()
    ls = lg.div(lg.sum(1), axis=0).reindex(pd.MultiIndex.from_product([GROUPS, years]))
    fig, ax = plt.subplots(figsize=(12, 4.2))
    xs = np.array([i * 6 + j for i in range(len(GROUPS)) for j in range(5)], float); b = np.zeros(len(ls))
    for c in LC:
        ax.bar(xs, ls[c].values, bottom=b, color=LC[c][1], width=0.86, edgecolor="white", lw=0.5, label=LC[c][0])
        for i, (v, bb) in enumerate(zip(ls[c].values, b)):
            if v >= 0.07: ax.text(xs[i], bb + v / 2, f"{v:.0%}", ha="center", va="center", fontsize=5.5, color="#222")
        b += ls[c].values
    ax.set_xticks(xs); ax.set_xticklabels([str(y)[2:] for y in years] * len(GROUPS), fontsize=6.5)
    for i, g in enumerate(GROUPS): ax.text(i * 6 + 2, -0.13, f"{g} ({tg.group.eq(g).sum()})", ha="center", fontsize=8, transform=ax.get_xaxis_transform(), color=GC[g] if g != "Kigali" else "#777", weight="bold")
    ax.set_ylim(0, 1.02); ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}")); ax.grid(axis="x", visible=False)
    ax.legend(ncol=4, fontsize=7.5, frameon=False, loc="upper center", bbox_to_anchor=(0.5, 1.12))
    ax.set_title("Land use outside parks by treatment group, GLCLU 2000-2020 (share of usable land)", loc="left", fontsize=9, pad=22)
    fig.tight_layout(); fig.savefig(OUT_F / "fig05_stacked_land_groups.png", bbox_inches="tight"); plt.close(fig)

    # ---- F6 sector-level cropland vs built-up, treated sectors, 2000 vs 2020 ----
    tr = cb[cb.treated_any == 1].copy()
    order = (tr[tr.year == 2020].assign(gk=lambda x: x.group.map({"Gates": 0, "Gates+": 1, "Bordering": 2}))
             .sort_values(["park", "gk", "crop_sh"], ascending=[True, True, False]))
    fig, axes = plt.subplots(1, 3, figsize=(11, 9.5), sharey=True, gridspec_kw=dict(width_ratios=[1, 1, 0.55]))
    ylab = [f"{r.sector} ({r.district})" for r in order.itertuples()]
    yy = np.arange(len(order))[::-1]
    for ax, yr in zip(axes[:2], [2000, 2020]):
        s = tr[tr.year == yr].set_index("sid").loc[order.sid]
        left = np.zeros(len(s))
        for c in LC:
            ax.barh(yy, s[f"{c}_sh"].values, left=left, color=LC[c][1], height=0.82, edgecolor="white", lw=0.4, label=LC[c][0]); left += s[f"{c}_sh"].values
        ax.set_xlim(0, 1); ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}")); ax.set_title(f"{yr}", loc="left", fontsize=9); ax.grid(axis="y", visible=False)
    axes[0].set_yticks(yy); axes[0].set_yticklabels(ylab, fontsize=6)
    for t, g in zip(axes[0].get_yticklabels(), order.group): t.set_color(GC[g])
    e0 = tr[tr.year == 2000].set_index("sid").loc[order.sid].ell; e1 = tr[tr.year == 2020].set_index("sid").loc[order.sid].ell
    axes[2].hlines(yy, e1.values, e0.values, color="#999", lw=1); axes[2].scatter(e0.values, yy, s=10, color="#bbb", label="2000", zorder=3)
    axes[2].scatter(e1.values, yy, s=12, color="#8b5fbf", label="2020", zorder=4); axes[2].set_xlim(0, 1)
    axes[2].set_title("ell = crop/(crop+built)", loc="left", fontsize=8.5); axes[2].legend(fontsize=7, frameon=False, loc="lower left")
    # park separators
    for p in ["Akagera", "Nyungwe"]:
        idx = np.where(order.park.values == p)[0]
        if len(idx): 
            for ax in axes: ax.axhline(yy[idx[-1]] - 0.5, color="#333", lw=0.6)
    for p in ["Akagera", "Nyungwe", "Volcanoes"]:
        idx = np.where(order.park.values == p)[0]
        axes[1].text(1.01, yy[idx].mean(), p, rotation=270, va="center", fontsize=8, transform=axes[1].get_yaxis_transform())
    axes[0].legend(ncol=4, fontsize=7, frameon=False, loc="upper left", bbox_to_anchor=(0, 1.04))
    fig.suptitle("Land use in each treated sector, share of usable land outside parks (GLCLU). Label colour: Gates / Gates+ / Bordering", x=0.01, ha="left", fontsize=9, y=1.0)
    fig.tight_layout(); fig.savefig(OUT_F / "fig06_sector_land_treated.png", bbox_inches="tight"); plt.close(fig)

    # all 416 sectors: crop vs built share, 2020, sorted within group
    fig, axes = plt.subplots(1, 4, figsize=(12, 3.2), sharey=True, gridspec_kw=dict(width_ratios=[44, 328, 9, 35]))
    for ax, (lab, m) in zip(axes, [("Treated (44)", cb.treated_any == 1), ("Control (328)", cb.control == 1), ("Towns\n(9)", cb.group == "Towns"), ("Kigali (35)", cb.group == "Kigali")]):
        s = cb[m & (cb.year == 2020)].sort_values("crop_sh", ascending=False)
        x = np.arange(len(s)); b = np.zeros(len(s))
        for c in LC: ax.bar(x, s[f"{c}_sh"].values, bottom=b, color=LC[c][1], width=1.0, lw=0); b += s[f"{c}_sh"].values
        ax.set_xticks([]); ax.set_title(lab, fontsize=8.5, loc="left"); ax.set_ylim(0, 1); ax.set_xlim(-0.5, len(s) - 0.5); ax.grid(False)
    axes[0].yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    fig.legend([Patch(color=LC[c][1]) for c in LC], [LC[c][0] for c in LC], ncol=4, fontsize=7.5, frameon=False, loc="upper right", bbox_to_anchor=(0.99, 1.0))
    fig.suptitle("Every sector's land use in 2020 (GLCLU), sorted by cropland share within group; one bar per sector", x=0.01, ha="left", fontsize=9, y=1.0)
    fig.subplots_adjust(left=0.05, right=0.99, top=0.82, bottom=0.04, wspace=0.03); fig.savefig(OUT_F / "fig07_sector_land_all_2020.png", bbox_inches="tight"); plt.close(fig)

    # ---- F8 transitions ----
    T = pd.read_csv(OUT_D / "glclu_transitions_2000_2020.csv")
    T["agg_"] = T.group.map({"Gates": "Treated", "Gates+": "Treated", "Bordering": "Treated", "Control": "Control", "Towns": "Urban", "Kigali": "Urban"})
    cl = ["crop", "built", "tree", "other"]
    fig, axes = plt.subplots(1, 3, figsize=(10.5, 3.4))
    for ax, a in zip(axes, ["Treated", "Control", "Urban"]):
        M = T[(T["agg_"] == a) & T["from"].isin(cl) & T.to.isin(cl)].pivot_table(index="from", columns="to", values="ha", aggfunc="sum").loc[cl, cl]
        R = M.div(M.sum(1), axis=0)
        ax.imshow(R.values, cmap="Greys", vmin=0, vmax=1)
        for i in range(4):
            for j in range(4): ax.text(j, i, f"{R.values[i, j]:.0%}\n{M.values[i, j]/1e3:,.1f}k ha", ha="center", va="center", fontsize=6, color="white" if R.values[i, j] > 0.55 else "#222")
        ax.set_xticks(range(4)); ax.set_xticklabels([LC[c][0] for c in cl], fontsize=6.5, rotation=20); ax.set_yticks(range(4)); ax.set_yticklabels([LC[c][0] for c in cl], fontsize=6.5)
        ax.set_xlabel("2020", fontsize=7); ax.set_ylabel("2000", fontsize=7); ax.set_title(a, loc="left", fontsize=9); ax.grid(False)
    fig.suptitle("Where 2000 land went by 2020: row shares and hectares, outside parks (GLCLU; built-up loss is not mapped)", x=0.01, ha="left", fontsize=9)
    fig.tight_layout(); fig.savefig(OUT_F / "fig08_land_transitions.png", bbox_inches="tight"); plt.close(fig)

    # ---- F9 nightlights by park x group, with visitors ----
    nl = pd.read_csv(OUT_D / "sector_ntl.csv").merge(tg[["sid", "group", "park"]], on="sid")
    vis = pd.read_csv(P.tourism("park_visitors_by_park.csv")).set_index("year")
    fig, axes = plt.subplots(2, 3, figsize=(11, 5.2), sharex=True, gridspec_kw=dict(height_ratios=[2.2, 1]))
    for k, p in enumerate(["Volcanoes", "Nyungwe", "Akagera"]):
        ax = axes[0, k]
        for g in ["Gates", "Gates+", "Bordering", "Control"]:
            s = nl[(nl.park == p) & (nl.group == g) & nl.year.between(2000, 2025)].groupby("year").ntl_chen_asinh.mean()
            if len(s): ax.plot(s.index, s.values, color=GC[g], lw=1.8 if g != "Control" else 1.4, ls="-" if g != "Control" else "--", label=f"{g} ({tg[(tg.park==p)&(tg.group==g)].shape[0]})")
        ax.set_title(f"{p} side: night lights", loc="left", fontsize=9); ax.legend(fontsize=6.5, frameon=False)
        if k == 0: ax.set_ylabel("mean asinh(sum), Chen VIIRS-like", fontsize=7)
        v = vis[p.lower()].dropna(); axes[1, k].bar(v.index, v.values / 1e3, color="#888", width=0.8)
        axes[1, k].set_title("Park visitors (000s)", loc="left", fontsize=8); axes[1, k].axvline(2017, color="#c1121f", lw=0.8, ls=":")
        axes[1, k].set_xlim(1999.5, 2025.5)
    fig.tight_layout(); fig.savefig(OUT_F / "fig09_ntl_by_park.png", bbox_inches="tight"); plt.close(fig)

    # ---- F10 district small multiples: EICV 2001/06/14 + LFS 2017-25 ----
    import os
    cross = pd.read_csv(ANA / "model_sector_cross.csv")[["sid", "district_id", "district"]]
    tgx = tg.merge(cross[["sid", "district_id"]], on="sid")
    park_d = set(tgx[tgx.treated_any == 1].district_id)
    dname = cross.groupby("district_id").district.first()
    lfs = pd.read_csv(P.HARM_LABOUR / "lfs_district_isic.csv"); lfs["sec"] = lfs.isic.astype(int).map(SEC)
    lfs["w_ag"] = lfs.workers * (lfs.sec == "A"); lfs["w_tour"] = lfs.workers * lfs.sec.isin(["I", "R"])
    lfs_sh = lfs.groupby(["dist", "year"])[["workers", "w_ag", "w_tour"]].sum()
    lfs_sh = pd.DataFrame({"ag": lfs_sh.w_ag / lfs_sh.workers, "tour": lfs_sh.w_tour / lfs_sh.workers}).reset_index()
    e = pd.read_parquet(P.HARM_EXTRACTS / "eicv_sub.parquet")
    e = e[(e.eicv_employed == 1) & (e.eicv_age_years >= 16) & e.eicv_year.isin([2001, 2006, 2014])]
    e["isic"] = e.eicv_industry_isic.fillna(e.eicv_industry_isic_approx)
    e["w_ag"] = e.eicv_weight * (e.isic == 1); e["w_tour"] = e.eicv_weight * e.isic.isin([9, 18])
    e_sh = e.groupby(["eicv_district", "eicv_year"])[["eicv_weight", "w_ag", "w_tour"]].sum()
    e_sh = pd.DataFrame({"ag": e_sh.w_ag / e_sh.eicv_weight, "tour": e_sh.w_tour / e_sh.eicv_weight}).reset_index()
    e_sh.columns = ["dist", "year", "ag", "tour"]
    pd.concat([e_sh.assign(src="EICV"), lfs_sh.assign(src="LFS")]).to_csv(OUT_T / "district_shares_eicv_lfs.csv", index=False)
    dorder = sorted(dname.index, key=lambda i: (i not in park_d, i // 10 == 1, dname[i]))
    for var, lab, fn in [("ag", "Agriculture share of employed", "fig10_district_facets_agriculture.png"), ("tour", "Tourism services (I,R) share of employed", "fig11_district_facets_tourism.png")]:
        fig, axes = plt.subplots(5, 6, figsize=(12, 9), sharex=True, sharey=True)
        for ax, di in zip(axes.flat, dorder):
            a = e_sh[e_sh.dist == di]; b = lfs_sh[lfs_sh.dist == di]
            col = "#c1121f" if di in park_d else "#1b4965"
            ax.plot(a.year, a[var], marker="o", ms=3, color=col, lw=1, ls=":"); ax.plot(b.year, b[var], marker="o", ms=2.5, color=col, lw=1.5)
            ax.axvline(2016, color="#bbb", lw=0.6); ax.axvspan(2019.6, 2021.4, color="#f0f0f0", zorder=0)
            ax.set_title(dname[di] + (" *" if di in park_d else ""), fontsize=7.5, loc="left", color=col)
            ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}")); ax.tick_params(labelsize=6)
        fig.suptitle(f"{lab} by district: EICV 2001/06/14 (dotted, usual activity, 16+) and LFS 2017-25 (solid, ILO). Red * = district with a treated sector; grey = COVID",
                     x=0.01, ha="left", fontsize=9)
        fig.tight_layout(); fig.savefig(OUT_F / fn, bbox_inches="tight"); plt.close(fig)

    # ---- F12 violins ----
    d["agg_"] = np.select([d.treated_any == 1, d.control == 1], ["Treated (44)", "Control (328)"], "Urban (44)")
    AG_ = ["Treated (44)", "Control (328)", "Urban (44)"]; AC = {"Treated (44)": "#c1121f", "Control (328)": "#1b4965", "Urban (44)": "#9e9e9e"}
    vars_ = [("lam", "lambda: ag share of (ag + services excl. G,O)"), ("ell", "ell: crop / (crop + built), GLCLU"), ("sh_tour", "Tourism svc share of workers"),
             ("crop_sh", "Cropland share of usable land"), ("built_sh", "Built-up share of usable land"), ("ntl_chen_asinh", "Night lights, asinh(sum)")]
    fig, axes = plt.subplots(2, 3, figsize=(12, 6.4))
    for ax, (v, lab) in zip(axes.flat, vars_):
        for j, w in enumerate([2002, 2012, 2022]):
            for k, a in enumerate(AG_):
                vals = d[(d.wave == w) & (d["agg_"] == a)][v].dropna().values
                pos = j * 4 + k
                if len(vals) > 2:
                    vp = ax.violinplot(vals, [pos], widths=0.9, showmedians=True, showextrema=False)
                    for b in vp["bodies"]: b.set_facecolor(AC[a]); b.set_alpha(0.55); b.set_edgecolor(AC[a])
                    vp["cmedians"].set_color("#111")
                gts = d[(d.wave == w) & (d.group == "Gates")][v].values
                if a.startswith("Treated"): ax.scatter(np.full(len(gts), pos), gts, marker="*", s=28, color="#6a040f", zorder=5)
        ax.set_xticks([1, 5, 9]); ax.set_xticklabels(["2002 / 2000", "2012 / 2010", "2022 / 2020"] if v in ("ell", "crop_sh", "built_sh") else ["2002", "2012", "2022"], fontsize=7)
        ax.set_title(lab, loc="left", fontsize=8.5); ax.grid(axis="x", visible=False)
        if v == "sh_tour": ax.set_ylim(0, d.sh_tour.quantile(0.995))
    axes[0, 0].legend([Patch(color=AC[a], alpha=.6) for a in AG_] + [plt.Line2D([], [], marker="*", ls="", color="#6a040f")], AG_ + ["Gate sectors (4)"], fontsize=7, frameon=False, loc="lower left")
    fig.suptitle("Distribution across sectors by group and Census wave (land and lights matched to nearest year)", x=0.01, ha="left", fontsize=9.5)
    fig.tight_layout(); fig.savefig(OUT_F / "fig12_violins.png", bbox_inches="tight"); plt.close(fig)
    print("figures done")


def section_tables():
    """Summary-stat tables T1-T7 on the repo treatment groups. Writes to output/tables/summary_statistics (names in helpers/common.py TABLE_NAMES).
Treated = bordering Volcanoes/Nyungwe/Akagera or near a pre-2005 gate (44); Control = 328; Urban = Kigali (35) + 2002 towns (9)."""
    import os, numpy as np, pandas as pd, statsmodels.formula.api as smf

    d = pd.read_csv(OUT_D / "sector_panel_desc.csv")
    cb = pd.read_csv(OUT_D / "sector_cropland_builtup_glclu.csv")
    tg = pd.read_csv(OUT_D / "treatment_groups.csv")
    cross = pd.read_csv(ANA / "model_sector_cross.csv")[["sid", "district_id"]]
    tg = tg.merge(cross, on="sid")
    d["sample"] = np.select([d.treated_any == 1, d.control == 1], ["Treated", "Control"], "Urban")
    d["near_gate"] = d.group.isin(["Gates", "Gates+"]).astype(int)

    def tex(df, name, cap, fmt="{:,.3f}", idx=True):
        df.to_csv(OUT_T / f"{name}.csv", index=idx)
        s = df.to_latex(float_format=lambda x: fmt.format(x), na_rep="--", caption=cap, label=f"tab:{name}", position="htbp", index=idx, escape=True)
        (OUT_T / f"{name}.tex").write_text(s)

    # ---------- T1 national employment ----------
    j = pd.read_csv(OUT_D / "sector_jobs_panel.csv")
    n = j.groupby("wave")[["AG", "IND", "S_tour", "S_bus", "S_loc", "S_broad", "workers"]].sum()
    lab = {"AG": "Agriculture", "IND": "Industry (B-F)", "S_tour": "Tourism services (I, R)", "S_bus": "Business services (J, K, M)",
           "S_loc": "Local services (G, H, L, N-Q, S-U)", "S_broad": "Services excl. trade and govt (memo)", "workers": "Total"}
    t1 = pd.DataFrame(index=[lab[c] for c in n.columns])
    for w in [2002, 2012, 2022]:
        t1[f"{w} (000s)"] = (n.loc[w] / 1e3).values
    for w in [2002, 2012, 2022]:
        t1[f"{w} share"] = (n.loc[w] / n.loc[w, "workers"]).values
    t1["growth p.a. 02-12"] = ((n.loc[2012] / n.loc[2002]) ** 0.1 - 1).values
    t1["growth p.a. 12-22"] = ((n.loc[2022] / n.loc[2012]) ** 0.1 - 1).values
    tex(t1, "T1_national_employment", "Workers aged 20--64 by sector, Census 2002/2012/2022 (10\\% public-use samples, weighted). 2022 agriculture is the reconstructed own-use-inclusive count (recorded: 1.69M).")

    # ---------- T2 model objects by group x wave ----------
    V = [("workers", "Workers (H)"), ("density", "Workers per km2 usable land"), ("lam", "lambda: ag / (ag + svc excl. G,O)"),
         ("sh_ag", "Agriculture share of workers"), ("sh_tour", "Tourism svc share"), ("sh_svc", "Svc excl. G,O share"),
         ("crop_sh", "Cropland share of usable land"), ("built_sh", "Built-up share"), ("tree_sh", "Tree-cover share"),
         ("ell", "ell: crop / (crop + built)"), ("k_a", "k_a: crop ha per farm worker"), ("k_s", "k_s: built ha per svc worker"),
         ("c", "c = k_a / k_s"), ("eps_model", "eps_L implied (1-ell)/(1-lambda)"), ("inmig_share", "In-migrant share"),
         ("ntl_chen_asinh", "Night lights asinh(sum)")]
    rows = []
    for gname, m in [("Treated (44)", d["sample"] == "Treated"), ("  of which near gate (12)", d.near_gate == 1), ("Control (328)", d["sample"] == "Control"), ("Urban (44)", d["sample"] == "Urban")]:
        for v, vl in V:
            r = {"Variable": vl, "Group": gname}
            for w in [2002, 2012, 2022]:
                x = d[m & (d.wave == w)][v].replace([np.inf, -np.inf], np.nan).dropna()
                r.update({f"{w} mean": x.mean(), f"{w} sd": x.std(), f"{w} p10": x.quantile(.1), f"{w} p50": x.median(), f"{w} p90": x.quantile(.9)})
            rows.append(r)
    t2 = pd.DataFrame(rows).set_index(["Variable", "Group"]).sort_index(level=0, sort_remaining=False)
    t2 = t2.loc[[vl for _, vl in V]]
    t2.to_csv(OUT_T / "T2_model_objects_full.csv")
    t2s = t2[[c for c in t2.columns if c.endswith(("mean", "sd", "p50"))]]
    tex(t2s, "T2_model_objects", "Model objects by group and Census wave: mean, SD and median across sectors (p10/p90 in the CSV). Land is GLCLU 2000/2010/2020 matched to the 2002/2012/2022 waves; in-migrant share is missing in 2002.")

    # ---------- T3 balance: three treatment definitions vs control ----------
    w = d.pivot_table(index="sid", columns="wave", values=["lam", "sh_tour", "sh_svc", "log_workers", "crop_sh", "built_sh", "tree_sh", "ell", "ntl_chen_asinh", "density"])
    B = pd.DataFrame(index=w.index)
    for v in ["lam", "sh_tour", "sh_svc", "log_workers", "crop_sh", "built_sh", "tree_sh", "ell", "ntl_chen_asinh", "density"]:
        B[f"{v} 2002"] = w[v][2002]; B[f"d {v} 02-12"] = w[v][2012] - w[v][2002]; B[f"d {v} 12-22"] = w[v][2022] - w[v][2012]
    B = B.join(tg.set_index("sid")[["gates", "near_gates", "border", "treated_any", "control", "district_id"]])
    defs = [("Bordering or near gate (44)", B.treated_any == 1), ("Near a gate (12)", B.near_gates == 1), ("Gate sectors (4)", B.gates == 1)]
    rows = []
    for col in [c for c in B.columns if c.endswith(("2002", "02-12", "12-22")) and not c.startswith("d ") or c.startswith("d ")]:
        r = {"Variable": col, "Control mean": B.loc[B.control == 1, col].mean()}
        for dn, m in defs:
            s = B[(m) | (B.control == 1)].copy(); s["T"] = m[s.index].astype(int); s = s.dropna(subset=[col])
            f = smf.ols(f"Q('{col}') ~ T", s).fit(cov_type="cluster", cov_kwds={"groups": s.district_id})
            r[f"{dn}: mean"] = s.loc[s["T"] == 1, col].mean(); r[f"{dn}: diff"] = f.params["T"]; r[f"{dn}: se"] = f.bse["T"]
        rows.append(r)
    t3 = pd.DataFrame(rows).set_index("Variable")
    order = [f"{v} 2002" for v in ["lam", "sh_tour", "sh_svc", "log_workers", "density", "crop_sh", "built_sh", "tree_sh", "ell", "ntl_chen_asinh"]] + \
            [f"d {v} {p}" for p in ["02-12", "12-22"] for v in ["lam", "sh_tour", "sh_svc", "log_workers", "density", "crop_sh", "built_sh", "tree_sh", "ell", "ntl_chen_asinh"]]
    t3 = t3.loc[order]
    tex(t3, "T3_balance_treated_control", "Treated vs control (328 sectors, Kigali and the four 2002 towns excluded), three treatment definitions as in map3. Diff = OLS on a treatment dummy, SE clustered by district. With 4 gate sectors in 3 districts the gate-sector SEs are not reliable. Land and lights use 2000/2010/2020 for the 2002/2012/2022 columns.")

    # ---------- T4 per park ----------
    pk_rows = []
    for p in ["Volcanoes", "Nyungwe", "Akagera"]:
        for gname, m in [("Near gate (Gates + Gates+)", d.near_gate == 1), ("Bordering only", d.group == "Bordering"), ("Control, same park side", d.control == 1)]:
            s = d[(d.park == p) & m]
            if not len(s): continue
            r = {"Park": p, "Group": gname, "Sectors": s.sid.nunique()}
            for wv in [2002, 2012, 2022]:
                x = s[s.wave == wv]; A = x[["AG", "S_tour", "S_broad", "workers", "crop", "built", "tree", "other"]].sum()
                r[f"Workers {wv} (000s)"] = A.workers / 1e3; r[f"lambda {wv}"] = A.AG / (A.AG + A.S_broad); r[f"Tourism sh {wv}"] = A.S_tour / A.workers
                u = A[["crop", "built", "tree", "other"]].sum(); r[f"Crop sh {wv-2}"] = A.crop / u; r[f"Built sh {wv-2}"] = A.built / u; r[f"Tree sh {wv-2}"] = A.tree / u
            pk_rows.append(r)
    t4 = pd.DataFrame(pk_rows).set_index(["Park", "Group"])
    tex(t4[[c for c in t4.columns if c.startswith(("Sectors", "Workers", "lambda", "Tourism"))]], "T4a_parks_jobs", "Jobs by park side and group, aggregated within group (Census).")
    tex(t4[[c for c in t4.columns if c.startswith(("Crop", "Built", "Tree"))]], "T4b_parks_land", "Land use by park side and group, share of usable land outside parks, aggregated within group (GLCLU).")
    vis = pd.read_csv(P.tourism("park_visitors_by_park.csv")).set_index("year")
    t4c = pd.DataFrame({p.capitalize(): [vis.loc[2005, p], vis.loc[2012, p], vis.loc[2019, p], vis.loc[2020, p], vis.loc[2023, p]] for p in ["volcanoes", "nyungwe", "akagera"]},
                       index=["2005", "2012", "2019", "2020", "2023"]).T
    t4c["growth 2005-19 p.a."] = (t4c["2019"] / t4c["2005"]) ** (1 / 14) - 1
    tex(t4c, "T4c_park_visitors", "Park visitors (RDB annual reports).", "{:,.3f}")

    # ---------- T5 transitions ----------
    T = pd.read_csv(OUT_D / "glclu_transitions_2000_2020.csv")
    T["agg_"] = T.group.map({"Gates": "Treated", "Gates+": "Treated", "Bordering": "Treated", "Control": "Control", "Towns": "Urban", "Kigali": "Urban"})
    cl = ["crop", "built", "tree", "other"]; out = []
    for a in ["Treated", "Control", "Urban"]:
        M = T[(T.agg_ == a) & T["from"].isin(cl) & T.to.isin(cl)].pivot_table(index="from", columns="to", values="ha", aggfunc="sum").loc[cl, cl]
        R = M.div(M.sum(1), axis=0)
        for f_ in cl:
            out.append({"Group": a, "2000 class": f_, "2000 ha (000s)": M.loc[f_].sum() / 1e3, **{f"to {t} (row share)": R.loc[f_, t] for t in cl}})
        # source of new cropland
        newcrop = M.loc[["built", "tree", "other"], "crop"]; out.append({"Group": a, "2000 class": "memo: sources of 2020 cropland not cropland in 2000",
                  **{f"to {t} (row share)": (newcrop.get(t, np.nan) / newcrop.sum()) if t != "crop" else np.nan for t in cl}, "2000 ha (000s)": newcrop.sum() / 1e3})
    t5 = pd.DataFrame(out).set_index(["Group", "2000 class"])
    tex(t5, "T5_land_transitions", "GLCLU land transitions 2000 to 2020, outside parks. Rows: 2000 class; columns: share of that land in each 2020 class. Built-up loss is not mapped in GLCLU v2.")

    # ---------- T6 output panel ----------
    park_d = set(tg[tg.treated_any == 1].district_id); kig = {11, 12, 13}
    dg = lambda di: "Kigali" if di in kig else ("Park districts" if di in park_d else "Other districts")
    ag = pd.read_csv(OUT_D / "district_ag_output.csv"); ag["dg"] = ag.district_id.map(dg)
    a6 = ag.groupby(["dg", "year"])[["v", "ha"]].sum(min_count=1); a6 = pd.DataFrame({"Crop value (bn RWF, fixed prices)": a6.v / 1e9, "Value per ha (000 RWF)": a6.v / a6.ha / 1e3}).unstack(0)
    ec = pd.read_csv(OUT_D / "district_ec_output.csv"); ec["dg"] = ec.district_id.map(dg); ec = ec[ec.year > 2011]
    e6 = ec.groupby(["year", "dg", "grp"])[["turnover", "emp_rep", "emp"]].sum()
    e6 = pd.DataFrame({"Turnover per reporting worker (m 2014 RWF)": e6.turnover / e6.emp_rep / 1e6, "Workers (000s)": e6.emp / 1e3}).unstack("grp")
    nl = pd.read_csv(OUT_D / "sector_ntl.csv").merge(d[["sid", "sample"]].drop_duplicates(), on="sid")
    n6 = nl[nl.year.isin([2000, 2005, 2010, 2015, 2020, 2025])].groupby(["year", "sample"])[["ntl_chen_asinh", "ntl_li_asinh"]].mean().unstack("sample")
    tex(a6, "T6a_output_agriculture", "SAS crop output by district group. Park districts = districts containing a treated sector (13). 2021 and 2024 have no area variable.", "{:,.1f}")
    tex(e6, "T6b_output_services", "Establishment Census by district group and ISIC group. Turnover is bracketed (midpoints; >50M RWF top-coded at 100M), CPI-deflated.", "{:,.2f}")
    tex(n6, "T6c_output_nightlights", "Mean night lights per sector, asinh(sum), Chen (VIIRS-like) and Li (DMSP-like) harmonised products.", "{:,.2f}")

    # ---------- T7 earnings ----------
    l = pd.read_parquet(P.HARM_EXTRACTS / "lfs_sub.parquet")
    l = l[(l.lfs_employment_status == 1) & l.lfs_monthly_cash_income.gt(0) & l.lfs_age.between(16, 64)]
    l["sec"] = l.lfs_industry_isic.map(lambda x: SEC.get(int(x)) if pd.notna(x) and int(x) in SEC else None)
    l["grp"] = l.sec.map(GROUP); l = l.dropna(subset=["grp"])
    cpi = pd.read_csv(P.tourism("world_bank_wdi.csv")).query("country=='RWA' and indicator_code=='FP.CPI.TOTL'").set_index("year").value
    l["real"] = l.lfs_monthly_cash_income / l.lfs_year.map(lambda y: cpi.get(min(y, cpi.dropna().index.max())) / cpi[2014])
    l["dg"] = l.lfs_district.map(dg)
    l["period"] = pd.cut(l.lfs_year, [2016, 2019, 2021, 2025], labels=["2017-19", "2020-21", "2022-25"])
    def wq(x, w, q):
        o = np.argsort(x.values); cx = np.cumsum(w.values[o]); return x.values[o][np.searchsorted(cx, q * cx[-1])]
    rows = []
    for (p, g_, s), x in l.groupby(["period", "dg", "grp"], observed=True):
        rows.append({"Period": p, "District group": g_, "Sector": s, "N": len(x), "Median (000 2014 RWF/month)": wq(x.real, x.lfs_weight, .5) / 1e3,
                     "Mean": np.average(x.real, weights=x.lfs_weight) / 1e3})
    t7 = pd.DataFrame(rows)
    piv = t7.pivot_table(index=["Period", "District group"], columns="Sector", values="Median (000 2014 RWF/month)")
    piv["Tourism / Agriculture"] = piv.S_tour / piv.AG; piv["Local svc / Agriculture"] = piv.S_loc / piv.AG
    t7.to_csv(OUT_T / "T7_earnings_long.csv", index=False)
    tex(piv, "T7_earnings_ratios", "Median real monthly cash earnings of employees aged 16--64 (000 2014 RWF, LFS, weighted) by sector and district group, with ratios to agriculture. Employees only: own-account farmers have no wage, so these are wages of hired workers.", "{:,.2f}")

    pd.set_option("display.width", 220, "display.max_columns", 30)
    for nme, t in [("T1", t1), ("T3", t3), ("T4a", t4.iloc[:, :10]), ("T5", t5), ("T7", piv)]:
        print("=====", nme); print(t.round(3).to_string())


def section_tourism_definitions():
    """Tourism employment under three definitions.
 Narrow (Census panel)      : ISIC sections I + R
 Section-broad (Census)     : I + H + R   (transport kept whole; freight is small in Rwanda)
 TSA-broad (divisions)      : 49, 50, 51 (transport), 55, 56 (accommodation, food), 79 (travel agencies, tour operators),
                              90-93 (culture, recreation) -- the UN tourism-characteristic industries at 2-digit
A) 2012 Census, 4-digit ISIC4: how much of TSA-broad employment the section definitions capture, by group.
B) LFS 2017-2025, 2-digit, district x year: TSA-broad share of employed (16+), by district group."""
    import os, numpy as np, pandas as pd, matplotlib.pyplot as plt

    TSA = [49, 50, 51, 55, 56, 79, 90, 91, 92, 93]
    tg = pd.read_csv(OUT_D / "treatment_groups.csv")
    grp = tg.set_index("sid").group.map(lambda g: "Treated: near gate" if g in ("Gates", "Gates+") else ("Treated: bordering only" if g == "Bordering" else ("Urban" if g in ("Kigali", "Towns") else "Control")))
    cc = tg.set_index("sid").control_clean

    # ---- A) Census 2012 4-digit ----
    c = pd.read_parquet(P.HARM_EXTRACTS / "census_sub.parquet", columns=["census_year", "census_sector", "census_age", "census_weight", "census_industry_isic4_2012"])
    c = c[(c.census_year == 2012) & c.census_age.between(20, 64) & c.census_industry_isic4_2012.between(100, 9900)].copy()
    c["div"] = (c.census_industry_isic4_2012 // 100).astype(int)
    c["grp"] = c.census_sector.map(grp)
    def agg(x):
        w = x.census_weight; tot = w.sum()
        tsa = w[x["div"].isin(TSA)].sum(); ir = w[x["div"].isin([55, 56, 90, 91, 92, 93])].sum(); ihr = w[x["div"].between(49, 53) | x["div"].isin([55, 56, 90, 91, 92, 93])].sum()
        return pd.Series({"Workers (000s)": tot / 1e3, "TSA-broad share": tsa / tot, "I+R share": ir / tot, "I+H+R share": ihr / tot,
                          "I+R / TSA-broad": ir / tsa, "I+H+R / TSA-broad": ihr / tsa,
                          "of TSA: accommodation (55)": w[x["div"] == 55].sum() / tsa, "of TSA: food & beverage (56)": w[x["div"] == 56].sum() / tsa,
                          "of TSA: transport (49-51)": w[x["div"].between(49, 51)].sum() / tsa, "of TSA: tour operators (79)": w[x["div"] == 79].sum() / tsa,
                          "of TSA: culture & recreation (90-93)": w[x["div"].between(90, 93)].sum() / tsa})
    A = pd.concat([c.groupby("grp").apply(agg, include_groups=False), agg(c).to_frame("National").T])
    A = A.loc[["Treated: near gate", "Treated: bordering only", "Control", "Urban", "National"]]
    A.to_csv(OUT_T / "T9a_tourism_definitions_census2012.csv")
    (OUT_T / "T9a_tourism_definitions_census2012.tex").write_text(A.T.to_latex(float_format=lambda v: f"{v:,.3f}", caption="Tourism employment under three definitions, Census 2012 (4-digit ISIC Rev.4), workers 20--64. TSA-broad = divisions 49--51, 55, 56, 79, 90--93.", label="tab:T9a", position="htbp"))

    # ---- B) LFS 2-digit district panel ----
    l = pd.read_parquet(P.HARM_EXTRACTS / "lfs_isic.parquet")
    l = l[l.lfs_isic_section_main_job.notna() & (l.lfs_age >= 16)].copy()
    l["div"] = l.lfs_isic_2digit_main_2017_2018.fillna(l.lfs_isic_main_job_2020).fillna(l.lfs_isic_two_digit_main_job)
    l["div"] = l["div"].fillna(l.lfs_isic_main_job_2019_2021 // 100)
    print("2-digit coverage by year:", l.groupby("lfs_year")["div"].apply(lambda s: s.notna().mean()).round(3).to_dict())
    cross = pd.read_csv(ANA / "model_sector_cross.csv")[["sid", "district_id"]]
    park_d = set(tg.merge(cross, on="sid").query("treated_any == 1").district_id)
    l["dg"] = l.lfs_district.map(lambda di: "Kigali" if di in (11, 12, 13) else ("Park districts" if di in park_d else "Other districts"))
    l["w"] = l.lfs_weight
    for k, codes in {"tsa": TSA, "ir": [55, 56, 90, 91, 92, 93], "ihr": [49, 50, 51, 52, 53, 55, 56, 90, 91, 92, 93]}.items():
        l[k] = l["div"].isin(codes) * l.w
    dp = l.groupby(["lfs_district", "lfs_year"])[["w", "tsa", "ir", "ihr"]].sum()
    dp = dp[["tsa", "ir", "ihr"]].div(dp.w, axis=0).rename(columns=lambda x: f"sh_{x}").reset_index()
    dp.to_csv(OUT_D / "district_tourism_lfs.csv", index=False)
    gp = l.groupby(["dg", "lfs_year"])[["w", "tsa", "ir", "ihr", ]].sum()
    B = pd.DataFrame({"TSA-broad": gp.tsa / gp.w, "I+R": gp.ir / gp.w, "I+H+R": gp.ihr / gp.w}).unstack(0)
    nat = l.groupby("lfs_year")[["w", "tsa", "ir"]].sum(); B[("TSA-broad", "National")] = nat.tsa / nat.w; B[("TSA-broad", "National (000s)")] = nat.tsa / 1e3
    B = B.sort_index(axis=1)
    B.to_csv(OUT_T / "T9b_tourism_lfs_district_groups.csv")
    (OUT_T / "T9b_tourism_lfs_district_groups.tex").write_text(B.to_latex(float_format=lambda v: f"{v:,.3f}", caption="Tourism share of employed (16+), LFS, by district group. Park districts contain a treated sector.", label="tab:T9b", position="htbp"))

    fig, ax = plt.subplots(1, 2, figsize=(9, 3.2))
    for i, g in enumerate(["Park districts", "Other districts", "Kigali"]):
        ax[0].plot(B.index, B[("TSA-broad", g)], marker="o", ms=3, color=["#c1121f", "#1b4965", "#9e9e9e"][i], label=g)
        ax[1].plot(B.index, B[("I+R", g)], marker="o", ms=3, color=["#c1121f", "#1b4965", "#9e9e9e"][i], label=g)
    for a, t in zip(ax, ["TSA-broad (49-51, 55, 56, 79, 90-93)", "Narrow (I + R)"]):
        a.axvspan(2019.6, 2021.4, color="#eee", zorder=0); a.set_title(t + ", share of employed", loc="left", fontsize=8.5)
        a.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    ax[0].legend(fontsize=7, frameon=False); fig.tight_layout(); fig.savefig(OUT_F / "fig13_tourism_definitions_lfs.png"); plt.close(fig)
    pd.set_option("display.width", 220); print(A.round(3).T.to_string()); print(B.round(3).to_string())


def section_map_change():
    """Side-by-side maps: change 2012-2022 (Census) in the share of each sector's workers
in tourism industries (ISIC I+H+R) and in agriculture, with national parks shaded.
Workers aged 20-64; 2022 agriculture reconstructed (n_AG_pt), as in the panel."""
    import numpy as np, pandas as pd, geopandas as gpd, matplotlib.pyplot as plt
    from matplotlib.colors import TwoSlopeNorm
    from matplotlib.patches import Patch

    GEO = DATA / "geo-data"
    d = pd.read_csv(OUT_D / "sector_panel_desc.csv")
    d["tour"] = 100 * (d.n_I + d.n_H + d.n_R) / d.workers
    d["ag"] = 100 * d.AG / d.workers
    w = d.pivot(index="sid", columns="wave", values=["tour", "ag"])
    ch = pd.DataFrame({"tour": w["tour"][2022] - w["tour"][2012], "ag": w["ag"][2022] - w["ag"][2012]})

    sec = gpd.read_file(GEO / "protected-areas" / "sectors_park_exposure_geodatarw.gpkg")[["sector_id", "geometry"]].to_crs(32736)
    sec["sid"] = sec.sector_id.astype(int); sec["geometry"] = sec.geometry.simplify(120)
    sec = sec.merge(ch, left_on="sid", right_index=True, how="left")
    pk = gpd.read_file(GEO / "protected-areas" / "rwanda_protected_areas_geodata_rw.gpkg")
    pk = pk[pk.designate.astype(str).str.contains("National Park", case=False, na=False)].to_crs(32736)
    lakes = gpd.read_file(GEO / "water" / "rwanda_lakes_osm.geojson").to_crs(32736)
    dist = gpd.read_file(GEO / "admin-boundaries" / "geodatarw_district_boundary.gpkg").to_crs(32736)
    xmin, ymin, xmax, ymax = sec.total_bounds

    fig, axes = plt.subplots(1, 2, figsize=(12, 5.6))
    for ax, (v, ttl, cmap) in zip(axes, [("tour", "Tourism industries (I, H, R)", "RdBu_r"),
                                         ("ag", "Agriculture", "BrBG")]):
        m = np.nanquantile(np.abs(sec[v]), 0.97); nrm = TwoSlopeNorm(0, -m, m)
        lakes.plot(ax=ax, color="#cfe3f0", lw=0, zorder=0)
        sec.plot(ax=ax, column=v, cmap=cmap, norm=nrm, lw=0.05, edgecolor="white", zorder=1,
                 missing_kwds=dict(color="#eeeeee"))
        pk.plot(ax=ax, facecolor="#dfe9df", edgecolor="#2E6B3E", lw=0.6, hatch="////", zorder=3)
        dist.boundary.plot(ax=ax, color="#7a7a7a", lw=0.25, zorder=4)
        ax.set_xlim(xmin, xmax); ax.set_ylim(ymin, ymax); ax.set_axis_off()
        ax.set_title(f"{ttl}: change in share of workers, 2012-2022", fontsize=9, loc="left")
        sm = plt.cm.ScalarMappable(cmap=cmap, norm=nrm)
        c = fig.colorbar(sm, ax=ax, fraction=0.04, pad=0.01, shrink=0.75, extend="both")
        c.set_label("percentage points", fontsize=8); c.ax.tick_params(labelsize=7)
    fig.legend(handles=[Patch(facecolor="#dfe9df", edgecolor="#2E6B3E", hatch="////", label="National park")],
               loc="lower left", fontsize=8, frameon=False, bbox_to_anchor=(0.01, 0.0))
    fig.text(0.99, 0.01, "Census 2012 and 2022, workers aged 20-64; 2022 agriculture reconstructed. "
             "Colour scales capped at the 97th percentile of |change|.", ha="right", fontsize=7, color="0.35")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(OUT_F / "fig14_map_change_tourism_agriculture.png", dpi=250, bbox_inches="tight")
    print(ch.describe().round(2))


def section_map_accommodation():
    """Sector-level map of accommodation (ISIC 55) vs food & beverage service (ISIC 56) from the
Establishment Census 2011, the only EC round with 4-digit ISIC at sector level (2014 has
1-digit sections only, a weighted sample; 2017-2023 identify districts only).
Universe: operating establishments (status 1 or 2). Workers: ec_total_workers_2011,
missing codes (>= 99,998) dropped."""
    import numpy as np, pandas as pd, geopandas as gpd, matplotlib.pyplot as plt
    from matplotlib.colors import LogNorm
    from matplotlib.patches import Patch

    GEO = DATA / "geo-data"
    d = pd.read_stata(DATA / "Publicly-Available-NISR/Establishment-Census-EC/2_Intermediate/EC_2011_establishment_clean.dta",
                      convert_categoricals=False)
    d = d[d.ec_working_status_2011.isin([1, 2])].copy()
    d["isic2"] = d.ec_main_activity_isic_2011.astype(str).str[:2]
    d["wk"] = d.ec_total_workers_2011.where(d.ec_total_workers_2011 < 99998)
    g = (d[d.isic2.isin(["55", "56"])].groupby(["ec_sector", "isic2"])
           .agg(n=("wk", "size"), wk=("wk", "sum")).unstack("isic2").fillna(0))
    g.columns = [f"{a}_{b}" for a, b in g.columns]
    g.index = g.index.astype(int)
    g.to_csv(OUT_D / "sector_ec2011_accommodation_food.csv")
    print(g.sum().round(0)); print("sectors with any ISIC 55:", (g.n_55 > 0).sum())
    print("missing worker codes in 55/56:", d[d.isic2.isin(["55","56"])].wk.isna().sum())

    sec = gpd.read_file(GEO / "protected-areas" / "sectors_park_exposure_geodatarw.gpkg")[["sector_id", "geometry"]].to_crs(32736)
    sec["sid"] = sec.sector_id.astype(int); sec["geometry"] = sec.geometry.simplify(120)
    sec = sec.merge(g, left_on="sid", right_index=True, how="left").fillna({c: 0 for c in g.columns})
    print("unmatched EC sectors:", sorted(set(g.index) - set(sec.sid)))
    pk = gpd.read_file(GEO / "protected-areas" / "rwanda_protected_areas_geodata_rw.gpkg")
    pk = pk[pk.designate.astype(str).str.contains("National Park", case=False, na=False)].to_crs(32736)
    lakes = gpd.read_file(GEO / "water" / "rwanda_lakes_osm.geojson").to_crs(32736)
    dist = gpd.read_file(GEO / "admin-boundaries" / "geodatarw_district_boundary.gpkg").to_crs(32736)
    xmin, ymin, xmax, ymax = sec.total_bounds

    fig, axes = plt.subplots(1, 2, figsize=(12, 5.6))
    for ax, (v, ttl, cmap) in zip(axes, [("wk_55", "Accommodation (ISIC 55)", "RdPu"),
                                         ("wk_56", "Food & beverage service (ISIC 56)", "Oranges")]):
        tot = int(sec[v].sum()); nz = sec[sec[v] > 0]
        nrm = LogNorm(1, nz[v].max())
        lakes.plot(ax=ax, color="#cfe3f0", lw=0, zorder=0)
        sec[sec[v] == 0].plot(ax=ax, color="#f2f2f2", lw=0.05, edgecolor="white", zorder=1)
        nz.plot(ax=ax, column=v, cmap=cmap, norm=nrm, lw=0.05, edgecolor="white", zorder=1)
        pk.plot(ax=ax, facecolor="#dfe9df", edgecolor="#2E6B3E", lw=0.6, hatch="////", zorder=3)
        dist.boundary.plot(ax=ax, color="#7a7a7a", lw=0.25, zorder=4)
        ax.set_xlim(xmin, xmax); ax.set_ylim(ymin, ymax); ax.set_axis_off()
        ax.set_title(f"{ttl}: workers by sector, 2011\n{tot:,} workers in {len(nz)} sectors", fontsize=9, loc="left")
        c = fig.colorbar(plt.cm.ScalarMappable(cmap=cmap, norm=nrm), ax=ax, fraction=0.04, pad=0.01, shrink=0.75)
        c.set_label("workers (log scale)", fontsize=8); c.ax.tick_params(labelsize=7)
    fig.legend(handles=[Patch(facecolor="#dfe9df", edgecolor="#2E6B3E", hatch="////", label="National park"),
                        Patch(facecolor="#f2f2f2", edgecolor="0.7", label="No establishments")],
               loc="lower left", ncol=2, fontsize=8, frameon=False, bbox_to_anchor=(0.01, 0.0))
    fig.text(0.99, 0.01, "Establishment Census 2011, operating establishments. ISIC 55: hotels, lodges, camping, other accommodation. "
             "ISIC 56: restaurants, bars, catering.", ha="right", fontsize=7, color="0.35")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(OUT_F / "fig15_map_ec2011_accommodation.png", dpi=250, bbox_inches="tight")


def section_musanze_cells():
    """Two-cell illustration for the toy model.
Other sectors: MUSANZE_CELLS="GATE_SID INT_SID TAG" python results-scripts/sector_descriptives.py --only musanze_cells.
Default Kinigi (4307) / Musanze (4310).
Gate cell (n=1) touches a national park; interior cell (n=2) touches the gate cell but no park.
Cropland: GLCLU v2 2020, share of usable land outside parks (Kinigi's polygon includes ~32 km2 of park). Employment shares: Census 2022, workers 20-64,
agriculture (2022 reconstructed) and services excluding G and O (lambda denominator).
Wage: LFS 2022, Musanze district (one value for both cells), employees 16-64, weighted mean
monthly cash earnings in nominal RWF; services = sections H-U excluding O."""
    import os, numpy as np, pandas as pd, geopandas as gpd, matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D
    from shapely.geometry import Point

    import sys
    GEO = DATA / "geo-data"
    import os
    _c = os.environ.get("MUSANZE_CELLS", "").split()  # e.g. MUSANZE_CELLS="4307 4310 musanze"
    GATE, INT, TAG = (int(_c[0]), int(_c[1]), _c[2]) if len(_c) == 3 else (4307, 4310, "musanze")
    sec = gpd.read_file(GEO / "protected-areas" / "sectors_park_exposure_geodatarw.gpkg")[["sector_id", "geometry"]].to_crs(32736)
    sec["sid"] = sec.sector_id.astype(int)
    core = sec[sec.sid.isin([GATE, INT])]
    mz = sec[sec.geometry.intersects(core.union_all().buffer(3000))].copy()
    tg = pd.read_csv(OUT_D / "treatment_groups.csv").set_index("sid")
    towns = mz[mz.sid.map(tg.group).isin(["Towns", "Kigali"])]
    pk = gpd.read_file(GEO / "protected-areas" / "rwanda_protected_areas_geodata_rw.gpkg").to_crs(32736)
    pk = pk[pk.designate.astype(str).str.contains("National Park", case=False, na=False)]
    dist = gpd.read_file(GEO / "admin-boundaries" / "geodatarw_district_boundary.gpkg").to_crs(32736)

    # stats
    p = pd.read_csv(OUT_D / "sector_panel_desc.csv").query("wave == 2022").set_index("sid")
    cb = pd.read_csv(OUT_D / "sector_cropland_builtup_glclu.csv").query("year == 2020").set_index("sid")
    area_ha = mz.set_index("sid").geometry.area / 1e4
    st = {}
    for s in (GATE, INT):
        st[s] = dict(name=p.sector[s], crop=100 * cb.crop_sh[s], crop_total=100 * cb.crop[s] / area_ha[s], ag=100 * p.sh_ag[s],
                     svc=100 * p.sh_S_broad[s], workers=p.workers[s], area=cb.usable[s] / 100)
    l = pd.read_parquet(P.HARM_EXTRACTS / "lfs_sub.parquet")
    l = l[(l.lfs_employment_status == 1) & l.lfs_monthly_cash_income.gt(0) & l.lfs_age.between(16, 64)
          & l.lfs_industry_isic.notna() & (l.lfs_year == 2022)].copy()
    l["sec"] = l.lfs_industry_isic.astype(int).map(SEC)
    w = {}
    for s_ in (GATE, INT):
        dcode = s_ // 100
        for k, codes in [("ag", ["A"]), ("svc", list("HIJKLMNPQRSTU"))]:
            x = l[l.sec.isin(codes) & (l.lfs_district == dcode)]
            w[(s_, k)] = (np.average(x.lfs_monthly_cash_income, weights=x.lfs_weight), len(x))
    pd.DataFrame(st).T.to_csv(OUT_T / f"{TAG}_two_cells.csv")
    print(pd.DataFrame(st).T.round(1)); print(w)

    # figure
    C1, C2 = "#c1121f", "#1b4965"
    fig = plt.figure(figsize=(7.2, 6.4))
    ax = fig.add_axes([0.0, 0.25, 1.0, 0.72])
    xmin, ymin, xmax, ymax = mz.total_bounds; pad = 1500
    pkc = pk[pk.geometry.intersects(core.union_all().buffer(3000))]
    VLAB = (pkc.union_all().intersection(core.union_all().buffer(6000)).representative_point().coords[0]) if len(pkc) else (xmin, ymax)
    pk.plot(ax=ax, facecolor="#dfe9df", edgecolor="#2E6B3E", lw=0.8, hatch="////", zorder=5)
    mz.plot(ax=ax, facecolor="#eeeeee", edgecolor="white", lw=0.8, zorder=2)
    mz[mz.sid == GATE].plot(ax=ax, facecolor=C1, edgecolor="white", lw=0.8, alpha=0.85, zorder=3)
    mz[mz.sid == INT].plot(ax=ax, facecolor=C2, edgecolor="white", lw=0.8, alpha=0.85, zorder=3)
    if len(towns): towns.dissolve().boundary.plot(ax=ax, color="0.25", lw=0.9, ls="--", zorder=4)
    dist[dist.geometry.intersects(mz.union_all())].boundary.plot(ax=ax, color="0.5", lw=0.4, zorder=1)
    dist.boundary.plot(ax=ax, color="0.2", lw=1.0, zorder=4)
    for s, lab in [(GATE, f"Gate ($n=1$)\n{st[GATE]['name']}"), (INT, f"Interior ($n=2$)\n{st[INT]['name']}")]:
        gg = mz[mz.sid == s].geometry.iloc[0].difference(pk.union_all().buffer(800))
        c = max(getattr(gg, "geoms", [gg]), key=lambda q: q.area).buffer(-600).representative_point()
        ax.annotate(lab, (c.x, c.y), ha="center", va="center", fontsize=7, color="white", fontweight="bold", zorder=7)
    for _, r in mz[~mz.sid.isin([GATE, INT])].iterrows():
        c = r.geometry.representative_point()
        ax.annotate(tg.sector.get(r.sid, ""), (c.x, c.y), ha="center", fontsize=6, color="0.45", zorder=7)
    ax.text(*VLAB, "Volcanoes National Park", fontsize=9, color="#2E6B3E", style="italic", ha="center", zorder=8, bbox=dict(facecolor="white", edgecolor="none", pad=1))
    ax.set_xlim(xmin - pad, xmax + pad); ax.set_ylim(ymin - pad, ymax + pad); ax.set_axis_off()
    ax.legend(handles=[Patch(facecolor="#dfe9df", edgecolor="#2E6B3E", hatch="////", label="National park"),
                       Line2D([], [], color="0.2", lw=1, label="District boundary")]
                      + ([Line2D([], [], color="0.25", ls="--", label="Town sectors")] if len(towns) else []),
              loc="lower right", fontsize=7, frameon=False)
    # inset
    ia = fig.add_axes([0.0, 0.70, 0.22, 0.26])
    dist.plot(ax=ia, facecolor="#f4f4f4", edgecolor="0.6", lw=0.3)
    core.plot(ax=ia, facecolor="0.15", edgecolor="0.15", lw=1.5)
    pk.plot(ax=ia, facecolor="#dfe9df", edgecolor="#2E6B3E", lw=0.3); ia.set_axis_off()
    # table
    g, i = st[GATE], st[INT]
    rows = [("", f"Gate ({g['name']})", f"Interior ({i['name']})"),
            ("Cropland, % of land outside the park (2020)", f"{g['crop']:.0f}%", f"{i['crop']:.0f}%"),
            ("Agriculture, % of workers (2022)", f"{g['ag']:.0f}%", f"{i['ag']:.0f}%"),
            ("Services excl. retail & govt, % of workers (2022)", f"{g['svc']:.0f}%", f"{i['svc']:.0f}%"),
            ("Land outside park (km$^2$) / workers (2022)", f"{g['area']:.0f} / {g['workers']:,.0f}", f"{i['area']:.0f} / {i['workers']:,.0f}")]
    ta = fig.add_axes([0.03, 0.02, 0.94, 0.22]); ta.set_axis_off()
    for r, row in enumerate(rows):
        y = 1 - r * 0.17
        for x, txt, ha in zip([0.0, 0.70, 0.90], row, ["left", "center", "center"]):
            ta.text(x, y, txt, fontsize=8, ha=ha, va="top", fontweight="bold" if r == 0 else "normal",
                    color={1: C1, 2: C2}.get([0.0, 0.70, 0.90].index(x), "black") if r == 0 else "black")
    ta.axhline(0.86, color="0.3", lw=0.6)
    dn = {s_: tg.district[s_] for s_ in (GATE, INT)}
    txt = "; ".join(f"{dn[s_]}: agriculture RWF {w[(s_,'ag')][0]:,.0f}, services RWF {w[(s_,'svc')][0]:,.0f}" for s_ in dict.fromkeys((GATE, INT)) if True)
    if dn[GATE] == dn[INT]: txt = txt.split("; ")[0]
    ta.text(0.0, 0.10, "District average monthly cash earnings, employees, LFS 2022 (district values, not cell values). " + txt + ".",
            fontsize=6.5, va="top", color="0.25", wrap=True)
    fig.savefig(OUT_F / f"fig16_{TAG}_two_cells.pdf", bbox_inches="tight")
    fig.savefig(OUT_F / f"fig16_{TAG}_two_cells.png", dpi=250, bbox_inches="tight")


def section_map_admin_levels():
    """Reference map of Rwanda's administrative levels: 30 districts, 416 sectors, 2,148 cells, with national parks
and lakes, plus a zoom on the Volcanoes National Park area with sector names.
Writes output/maps/admin_levels.{pdf,png}.
Layers: NISR 2022 sectors and cells (geo-data/protected-areas/*_park_exposure_geodatarw.gpkg), geodata.rw districts,
WDPA September 2026 national parks, OpenStreetMap lakes clipped to Rwanda."""
    import warnings
    import geopandas as gpd, matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch, Rectangle
    from shapely.geometry import box

    warnings.filterwarnings("ignore", "Geometry is in a geographic CRS")
    GEO = DATA / "geo-data"
    UTM = 32735                                   # UTM 36S: metres, for the scale bars
    ZOOM = (29.26, -1.73, 29.88, -1.245)          # lon/lat box around Volcanoes NP (Rubavu, Nyabihu, Musanze, Burera)
    PARK_FILL, PARK_EDGE, LAKE, BOX = "#d3e6cc", "#3d7a3d", "#cfe1f2", "#b03a2e"

    sec = gpd.read_file(GEO / "protected-areas/sectors_park_exposure_geodatarw.gpkg").to_crs(UTM)
    cell = gpd.read_file(GEO / "protected-areas/cells_park_exposure_geodatarw.gpkg").to_crs(UTM)
    dist = gpd.read_file(GEO / "admin-boundaries/geodatarw_district_boundary.gpkg").to_crs(UTM)
    wdpa = gpd.read_file(GEO / "protected-areas/wdpa_rwanda.gpkg")
    parks = wdpa[wdpa.DESIG_ENG == "National Park"].to_crs(UTM)
    rwa = sec.union_all()
    lakes = gpd.read_file(GEO / "water/rwanda_lakes_osm.geojson").to_crs(UTM).clip(rwa)
    zb = gpd.GeoSeries.from_xy([ZOOM[0], ZOOM[2]], [ZOOM[1], ZOOM[3]], crs=4326).to_crs(UTM)
    x0, y0, x1, y1 = zb.x[0], zb.y[0], zb.x[1], zb.y[1]
    VIEW = box(x0, y0, x1, y1)


    def layers(ax):
        lakes.plot(ax=ax, color=LAKE, edgecolor="none", zorder=1)
        parks.plot(ax=ax, color=PARK_FILL, edgecolor=PARK_EDGE, linewidth=0.8, zorder=2)
        cell.boundary.plot(ax=ax, color="0.65", linewidth=0.25, zorder=3)
        sec.boundary.plot(ax=ax, color="0.25", linewidth=0.6, zorder=4)
        dist.boundary.plot(ax=ax, color="black", linewidth=1.8, zorder=5)
        ax.set_axis_off(); ax.set_aspect("equal")


    def scalebar(ax, km, xfrac=0.02, yfrac=0.04):
        (a0, a1), (b0, b1) = ax.get_xlim(), ax.get_ylim()
        x, y = a0 + xfrac * (a1 - a0), b0 + yfrac * (b1 - b0)
        ax.plot([x, x + km * 1000], [y, y], color="black", linewidth=3, solid_capstyle="butt", zorder=8)
        ax.text(x + km * 500, y + 0.012 * (b1 - b0), f"{km} km", ha="center", va="bottom", fontsize=8, zorder=8)


    fig, (axL, axR) = plt.subplots(1, 2, figsize=(15, 7.6), gridspec_kw=dict(width_ratios=[1, 1]))

    # Whole country, district names
    layers(axL)
    for _, r in dist.iterrows():
        p = r.geometry.representative_point()
        axL.text(p.x, p.y, r.district, ha="center", va="center", fontsize=6.5, zorder=7,
                 bbox=dict(facecolor="white", edgecolor="none", alpha=0.75, pad=0.6))
    axL.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, edgecolor=BOX, linewidth=1.5, zorder=9))
    axL.set_title("Rwanda: 30 districts, 416 sectors, 2,148 cells", fontsize=11)
    scalebar(axL, 25)

    # Zoom, sector names and district names
    layers(axR)
    axR.set_xlim(x0, x1); axR.set_ylim(y0, y1)
    for _, r in sec.cx[x0:x1, y0:y1].iterrows():
        p = r.geometry.representative_point()
        if x0 < p.x < x1 and y0 < p.y < y1:
            axR.text(p.x, p.y, r.sector, ha="center", va="center", fontsize=6.5, color="0.2", zorder=7)
    for _, r in dist.cx[x0:x1, y0:y1].iterrows():
        part = r.geometry.intersection(VIEW)
        if part.area < 0.3 * r.geometry.area: continue   # name only districts mostly inside the zoom
        p = part.representative_point()
        axR.text(p.x, p.y, r.district.upper(), ha="center", va="center", fontsize=9, fontweight="bold", zorder=7,
                 bbox=dict(facecolor="white", edgecolor="none", alpha=0.75, pad=0.8))
    for s in axR.spines.values():
        s.set_visible(True); s.set_edgecolor(BOX); s.set_linewidth(1.5)
    axR.set_axis_on(); axR.set_xticks([]); axR.set_yticks([])
    axR.set_title("Zoom: Volcanoes National Park area (sector names)", fontsize=11)
    scalebar(axR, 5)

    handles = [Line2D([], [], color="black", linewidth=1.8, label="District (30)"),
               Line2D([], [], color="0.25", linewidth=0.8, label="Sector (416)"),
               Line2D([], [], color="0.65", linewidth=0.5, label="Cell (2,148)"),
               Patch(facecolor=PARK_FILL, edgecolor=PARK_EDGE, label="National park"),
               Patch(facecolor=LAKE, edgecolor="none", label="Lake")]
    fig.legend(handles=handles, loc="lower center", ncol=5, frameon=False, fontsize=9, bbox_to_anchor=(0.5, 0.04))
    fig.text(0.5, 0.005, "Boundaries: NISR 2022 (cells, sectors), geodata.rw (districts); parks: WDPA, September 2026.",
             ha="center", fontsize=7.5, color="0.35")
    fig.subplots_adjust(left=0.01, right=0.99, top=0.95, bottom=0.12, wspace=0.04)
    for ext, dpi in [("pdf", None), ("png", 200)]:
        fig.savefig(OUT_F / f"admin_levels_map.{ext}", dpi=dpi, bbox_inches="tight")
    plt.close(fig)

SECTIONS = {
    "figures": section_figures,
    "tables": section_tables,
    "tourism_definitions": section_tourism_definitions,
    "map_change": section_map_change,
    "map_accommodation": section_map_accommodation,
    "musanze_cells": section_musanze_cells,
    "map_admin_levels": section_map_admin_levels,
}


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", nargs="+", choices=list(SECTIONS), help="run only these sections, in run order")
    ap.add_argument("--list", action="store_true", help="list the sections and exit")
    a = ap.parse_args(argv)
    if a.list:
        print("\n".join(SECTIONS)); return
    for name, fn in SECTIONS.items():
        if a.only and name not in a.only:
            continue
        print(f"\n==== {name}", flush=True)
        fn()


if __name__ == "__main__":
    main()
