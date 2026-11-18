"""Side-by-side maps: change 2012-2022 (Census) in the share of each sector's workers
in tourism industries (ISIC I+H+R) and in agriculture, with national parks shaded.
Workers aged 20-64; 2022 agriculture reconstructed (n_AG_pt), as in the panel."""
import numpy as np, pandas as pd, geopandas as gpd, matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm
from matplotlib.patches import Patch
from _common import *

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
