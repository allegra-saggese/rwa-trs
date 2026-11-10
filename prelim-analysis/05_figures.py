"""Descriptive figures on the repo treatment groups. Writes to output/figures and output/maps (names in _common.FIGURE_NAMES).
Group colours: treated tiers in reds (repo PARK #c1121f), control navy (repo NONPARK #1b4965), urban greys.
Land colours from rwa-trs/summary-stat-scripts/viz_style.py LANDCOVER."""
import numpy as np, pandas as pd, geopandas as gpd, matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm
from matplotlib.patches import Patch
from _common import *

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
vis = pd.read_csv(DATA / "Tourism Data" / "park_visitors_by_park.csv").set_index("year")
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
lfs = pd.read_csv(DATA / "geo-data" / "labour" / "lfs_district_isic.csv"); lfs["sec"] = lfs.isic.astype(int).map(SEC)
lfs["w_ag"] = lfs.workers * (lfs.sec == "A"); lfs["w_tour"] = lfs.workers * lfs.sec.isin(["I", "R"])
lfs_sh = lfs.groupby(["dist", "year"])[["workers", "w_ag", "w_tour"]].sum()
lfs_sh = pd.DataFrame({"ag": lfs_sh.w_ag / lfs_sh.workers, "tour": lfs_sh.w_tour / lfs_sh.workers}).reset_index()
e = pd.read_parquet(os.path.expanduser("~/eicv_sub.parquet"))
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
