"""
steg_forest_jrc.py -- tropical moist forest remaining in and outside national parks, 1995-2024, for the STEG appendix.

    python steg_forest_jrc.py
    output/figures/steg_forest_jrc.pdf

MEASURE (Matteo, 2026-09-15). JRC Tropical Moist Forest, version 2025, read as cloud-optimised GeoTIFFs from
the Source Cooperative mirror (the same source as coefplot_jrc_forest.py and forest_event_study_5km.py; only
Rwanda's window is fetched). Forest is the 1995 annual-change map's undisturbed and degraded classes (1, 2).
Each year's value is the area of that 1995 forest not yet recorded as deforested (DeforestationYear after
1995 and up to the year), as a share of 1995, so 1995 = 100. Parks are the current national-park polygons of
the Government of Rwanda protected-areas layer; outside parks is the rest of Rwanda's 2022 sector boundaries.
Pixel areas are computed per row, since a degree of longitude shortens with latitude.

WHAT WAS TRIED. Hansen Global Forest Change cannot start before 2000 (its baseline is tree cover in 2000).
A parks + 5 km buffer comparison was dropped. Regrowth is left out twice: regrowing forest (class 4) is not
in the 1995 base, and 1995 forest that grows back after being cleared is not added back. Tested on a base
that included class 4, netting regrowth in gave 94.9 against 92.6 inside parks and 27.0 against 18.8 outside
in 2024, with the two lines within two points of each other until 2015.

CAVEAT. JRC maps natural moist forest. Outside the parks it records fragmented and largely degraded forest
(41% degraded in 2000, against 9% inside parks), and after 2015 new forest appears there that the 1995
cohort, by construction, does not count.
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd, geopandas as gpd, rasterio, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
from rasterio.features import rasterize
from rasterio.merge import merge
from shapely.validation import make_valid
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import paths as P
import steg_ec_maps as M

JRC = "https://data.source.coop/epoch/jrc-tmf/v1_2025/{tile}/{layer}.tif"
TILES = ("N0_E20", "N0_E30")           # Rwanda straddles 30E
BASE, END = 1995, 2024
FOREST = [1, 2]                        # undisturbed, degraded
LINES = {"park": ("National parks", "#2E6B3E"), "outside": ("Outside national parks", "#8c8c8c")}


def jrc(layer, bounds):
    srcs = [rasterio.open(JRC.format(tile=t, layer=layer)) for t in TILES]
    arr, transform = merge(srcs, bounds=bounds)
    crs = srcs[0].crs
    for x in srcs:
        x.close()
    return arr[0], transform, crs


def main():
    s = gpd.read_file(M.SECTORS)
    s["geometry"] = s.geometry.apply(make_valid)
    land = s.to_crs(M.CRS).union_all()
    pk = gpd.read_file(M.PARKS)
    pk = pk[pk.designate.astype(str).str.contains("National Park", case=False, na=False)].to_crs(M.CRS)
    park = pk.union_all().intersection(land)
    areas = {"park": park, "outside": land.difference(park)}
    bounds = tuple(gpd.GeoSeries([land], crs=M.CRS).to_crs(4326).total_bounds)

    ac, tr, crs = jrc(f"AnnualChange_{BASE}", bounds)
    dy, tr2, _ = jrc("DeforestationYear", bounds)
    assert tr2 == tr and dy.shape == ac.shape
    to = lambda g: gpd.GeoSeries([g], crs=M.CRS).to_crs(crs).iloc[0]
    lat = tr.f + (np.arange(ac.shape[0]) + .5) * tr.e
    row_ha = abs(tr.a) * 111320 * np.cos(np.radians(lat)) * abs(tr.e) * 110574 / 1e4
    ha = lambda m: float(m.sum(axis=1) @ row_ha)
    forest = np.isin(ac, FOREST)

    out = {}
    for k, g in areas.items():
        mk = rasterize([(to(g), 1)], out_shape=ac.shape, transform=tr, fill=0, dtype="uint8").astype(bool) & forest
        base = ha(mk)
        out[k] = pd.Series({y: ha(mk & ~((dy > BASE) & (dy <= y))) / base * 100 for y in range(BASE, END + 1)})
        print(f"{k}: forest {BASE} {base:,.0f} ha | index " +
              ", ".join(f"{y} {out[k][y]:.1f}" for y in (2000, 2005, 2010, 2015, 2020, END)))

    fig, ax = plt.subplots(figsize=(9.5, 4.8))
    for k, (lab, col) in LINES.items():
        ax.plot(out[k].index, out[k].values, "-o", color=col, lw=2, ms=3.5, label=lab)
    ax.set_ylabel(f"Forest remaining, {BASE} = 100")
    ax.set_ylim(0, 105); ax.set_xlim(BASE - .6, END + .6)
    ax.set_xticks(range(BASE, END + 1, 5))
    ax.grid(axis="y", lw=.35, color="#DDD"); ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    ax.legend(loc="lower left", frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(P.FIGS / "steg_forest_jrc.pdf", bbox_inches="tight"); plt.close(fig)
    print(f"written {P.FIGS / 'steg_forest_jrc.pdf'}")


if __name__ == "__main__":
    main()
