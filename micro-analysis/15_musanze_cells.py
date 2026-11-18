"""Two-cell illustration for the toy model.
Usage: python 15_musanze_cells.py [GATE_SID INT_SID TAG]. Default Kinigi (4307) / Musanze (4310).
Gate cell (n=1) touches a national park; interior cell (n=2) touches the gate cell but no park.
Cropland: GLCLU v2 2020, share of usable land outside parks (Kinigi's polygon includes ~32 km2 of park). Employment shares: Census 2022, workers 20-64,
agriculture (2022 reconstructed) and services excluding G and O (lambda denominator).
Wage: LFS 2022, Musanze district (one value for both cells), employees 16-64, weighted mean
monthly cash earnings in nominal RWF; services = sections H-U excluding O."""
import os, numpy as np, pandas as pd, geopandas as gpd, matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
from shapely.geometry import Point
from _common import *

import sys
GEO = DATA / "geo-data"
GATE, INT, TAG = (int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]) if len(sys.argv) > 3 else (4307, 4310, "musanze")
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
l = pd.read_parquet(os.path.expanduser("~/lfs_sub.parquet"))
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
