"""Population density by sector, Census 2002, 2012, 2022.
Population = weighted count of all persons in the Census 10% sample (census_weight), by sector.
Density = persons per km2 of usable land outside national parks and water (GLCLU, as in the panel)."""
import numpy as np, pandas as pd, geopandas as gpd, matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm
from matplotlib.patches import Patch
from _common import *

C = DATA / "Publicly-Available-NISR/Census-PHC/2_Intermediate"
pop = {}
for y in (2002, 2012, 2022):
    c = pd.read_stata(C / f"Census_{y}_person_clean.dta", columns=["census_sector", "census_weight"], convert_categoricals=False)
    pop[y] = c.groupby("census_sector").census_weight.sum()
pop = pd.DataFrame(pop); pop.index = pop.index.astype(int)
print("national totals:", pop.sum().round(-3).to_dict())
usable = pd.read_csv(OUT_D / "sector_cropland_builtup_glclu.csv").query("year == 2020").set_index("sid").usable / 100  # km2
dens = pop.div(usable, axis=0)
dens.to_csv(OUT_D / "sector_pop_density.csv")
print(dens.describe().round(0))

GEO = DATA / "geo-data"
sec = gpd.read_file(GEO / "protected-areas" / "sectors_park_exposure_geodatarw.gpkg")[["sector_id", "geometry"]].to_crs(32736)
sec["sid"] = sec.sector_id.astype(int); sec["geometry"] = sec.geometry.simplify(120)
sec = sec.merge(dens, left_on="sid", right_index=True, how="left")
sec["chg"] = 100 * (sec[2022] / sec[2002] - 1)
pk = gpd.read_file(GEO / "protected-areas" / "rwanda_protected_areas_geodata_rw.gpkg")
pk = pk[pk.designate.astype(str).str.contains("National Park", case=False, na=False)].to_crs(32736)
lakes = gpd.read_file(GEO / "water" / "rwanda_lakes_osm.geojson").to_crs(32736)
dist = gpd.read_file(GEO / "admin-boundaries" / "geodatarw_district_boundary.gpkg").to_crs(32736)
xmin, ymin, xmax, ymax = sec.total_bounds

def base(ax):
    lakes.plot(ax=ax, color="#cfe3f0", lw=0, zorder=0)
    pk.plot(ax=ax, facecolor="#dfe9df", edgecolor="#2E6B3E", lw=0.5, hatch="////", zorder=3)
    dist.boundary.plot(ax=ax, color="#7a7a7a", lw=0.25, zorder=4)
    ax.set_xlim(xmin, xmax); ax.set_ylim(ymin, ymax); ax.set_axis_off()

fig = plt.figure(figsize=(15, 4.2))
W = 0.205
axes = [fig.add_axes([0.005 + k * W, 0.08, W, 0.84]) for k in range(3)] + [fig.add_axes([0.70, 0.08, W, 0.84])]
def binbar(cax, cmap, bounds, labels, title):
    n = len(bounds) - 1
    cb = fig.colorbar(plt.cm.ScalarMappable(cmap=cmap, norm=BoundaryNorm(range(n + 1), n)), cax=cax, ticks=[k + 0.5 for k in range(n)])
    cb.ax.set_yticklabels(labels, fontsize=7); cb.ax.tick_params(length=0); cb.set_label(title, fontsize=8)
B = [0, 250, 400, 600, 1000, 2500, 1e9]; cm1 = plt.get_cmap("YlOrRd", len(B) - 1); nrm = BoundaryNorm(B, cm1.N)
for ax, y in zip(axes[:3], (2002, 2012, 2022)):
    sec.plot(ax=ax, column=y, cmap=cm1, norm=nrm, lw=0.05, edgecolor="white", zorder=1)
    base(ax); ax.set_title(f"{y}: {pop[y].sum()/1e6:.1f}m people", fontsize=9, loc="left")
binbar(fig.add_axes([0.625, 0.18, 0.008, 0.64]), cm1, B, ["<250", "250-400", "400-600", "600-1,000", "1,000-2,500", ">2,500"],
       "persons per km$^2$ of usable land")
B2 = [-1e9, 0, 25, 50, 100, 200, 1e9]; cm2 = plt.get_cmap("PuRd", len(B2) - 1); n2 = BoundaryNorm(B2, cm2.N)
sec.plot(ax=axes[3], column="chg", cmap=cm2, norm=n2, lw=0.05, edgecolor="white", zorder=1)
base(axes[3]); axes[3].set_title("Change in density, 2002-2022", fontsize=9, loc="left")
binbar(fig.add_axes([0.915, 0.18, 0.008, 0.64]), cm2, B2, ["<0%", "0-25%", "25-50%", "50-100%", "100-200%", ">200%"], "% change")
fig.legend(handles=[Patch(facecolor="#dfe9df", edgecolor="#2E6B3E", hatch="////", label="National park")],
           loc="lower left", fontsize=8, frameon=False, bbox_to_anchor=(0.01, -0.04))
fig.text(0.93, -0.02, "Census 2002, 2012, 2022, all persons (weighted 10% sample). Usable land excludes parks and water (GLCLU).",
         ha="right", fontsize=7, color="0.35")
fig.savefig(OUT_F / "fig17_map_pop_density.png", dpi=250, bbox_inches="tight")
fig.savefig(OUT_F / "fig17_map_pop_density.pdf", bbox_inches="tight")
