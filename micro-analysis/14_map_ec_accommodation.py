"""Sector-level map of accommodation (ISIC 55) vs food & beverage service (ISIC 56) from the
Establishment Census 2011, the only EC round with 4-digit ISIC at sector level (2014 has
1-digit sections only, a weighted sample; 2017-2023 identify districts only).
Universe: operating establishments (status 1 or 2). Workers: ec_total_workers_2011,
missing codes (>= 99,998) dropped."""
import numpy as np, pandas as pd, geopandas as gpd, matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
from matplotlib.patches import Patch
from _common import *

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
