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
from _common import DATA, OUT_F

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
