"""
steg_ntl_gates.py -- share of land lit within 5 km of the park gates, for the STEG appendix.

    python steg_ntl_gates.py
    output/figures/steg_ntl_gates.pdf

The land within 5 km of the park gates, with the parks themselves taken out (park land is dark by
construction) and anything outside Rwanda taken out, so the area is a circle conditional on not being
in the park. All four gates pooled into one area: Kinigi (Volcanoes), Gisakura and Kitabi (Nyungwe),
the South Gate (Akagera). Gishwati-Mukura has no gate in the data. Coordinates: bar_chart_housing.GATE_XY.

City sectors are removed from every area: the whole City of Kigali (list 2a) and the nine sectors of
Muhanga, Huye, Musanze and Rubavu (list 3), as settled in TRS-Border-Sectors.md ("Kigali all + cities" in
bar_chart_housing.geography). This takes Musanze town out of the gate area around Kinigi.

Comparison: the rest of Rwanda outside the parks, the city sectors and the gate area.

MEASURE. Share of the area's observed pixels inside the VIIRS VNL v2 annual lit mask, 2012-2025, in
percent; pixels with no cloud-free night that year (cf_cvg = 0) are missing rather than dark, and an
area-year seen over less than 90% of its pixels is dropped. Pixels are assigned by centre.

Chosen by Matteo, 2026-09-14, from eight versions: share of land lit and median radiance, 5 and 10 km,
annual and 3-month bins. Before that, mean radiance indexed to 2012 = 100 was tried and dropped: the dark
areas start near zero, so the index turns noise into ten-fold growth, and the monthly composites, which
are not background-masked, are dominated by noise and fires in dark areas and do not reproduce the
annual gap.
"""
import sys, re
from pathlib import Path
import numpy as np, pandas as pd, geopandas as gpd, rasterio, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
from rasterio.features import rasterize
from shapely.geometry import Point
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Nighttime-Lights"))
import ntl_helpers as H
import bar_chart_housing as B

KM, MIN_OBS = 5.0, 0.90
GATE = f"Within {KM:.0f} km of the park gates"
REST = "Rest of rural Rwanda"
COL = {GATE: "#2a9d8f", REST: "#8c8c8c"}
RX = re.compile(r"ntl_viirs_lit_(\d{4})_rwanda\.tif$")


def areas():
    """the gate area and the comparison area, in UTM 36S, parks and city sectors removed from both"""
    g, _, X, _ = B.geography()
    pk = gpd.read_file(B.GEO / "protected-areas/rwanda_protected_areas_geodata_rw.gpkg")
    pk = pk[pk.designate.astype(str).str.contains("National Park", case=False, na=False)].to_crs(32736)
    park = pk[pk.geometry.area > 1e5].union_all()
    cities = g[g.sid.isin(X["Kigali all + cities"])].union_all()
    land = g.union_all().difference(park).difference(cities)
    pts = gpd.GeoSeries([Point(*B.GATE_XY[s]) for s in B.GATES], crs=4326).to_crs(32736)
    near = pts.buffer(KM * 1000).union_all().intersection(land)
    return {GATE: near, REST: land.difference(near)}


def lit_files():
    return [(int(m.group(1)), p) for p in sorted(H.CLIPS.glob("ntl_viirs_lit_*.tif")) if (m := RX.match(p.name))]


def masks(zone):
    with rasterio.open(lit_files()[0][1]) as r:
        grid = dict(out_shape=r.shape, transform=r.transform)
        crs = r.crs
    to_r = lambda z: gpd.GeoSeries([z], crs=32736).to_crs(crs).iloc[0]
    return {n: rasterize([(to_r(z), 1)], fill=0, **grid).astype(bool) for n, z in zone.items()}, grid


def series(M, grid):
    rows = []
    for year, p in lit_files():
        with rasterio.open(p) as r:
            assert r.shape == grid["out_shape"] and r.transform == grid["transform"], p.name
            lit = r.read(1) > 0
        with rasterio.open(H.CLIPS / p.name.replace("_lit_", "_cfcvg_")) as r:
            obs = r.read(1) > 0
        for n, mk in M.items():
            share = obs[mk].mean()
            rows.append(dict(year=year, area=n, obs=share,
                             lit_pct=lit[mk & obs].mean() * 100 if share >= MIN_OBS else np.nan))
    return pd.DataFrame(rows)


def main():
    zone = areas()
    M, grid = masks(zone)
    for n, m in M.items():
        print(f"{n:32s} {zone[n].area / 1e6:8,.0f} km2  {m.sum():7,d} pixels")
    d = series(M, grid)
    w = d.pivot(index="year", columns="area", values="lit_pct")[list(COL)]
    print("dropped area-years (<90% observed):", w.isna().sum().to_dict())

    fig, ax = plt.subplots(figsize=(9.5, 4.8))
    for n in COL:
        ax.plot(w.index, w[n], "-o", color=COL[n], lw=2, ms=4, label=n)
    ax.set_ylabel("Share of land lit, %")
    ax.set_xticks(range(int(w.index.min()), int(w.index.max()) + 1))
    ax.set_ylim(0, w.max().max() * 1.15)
    ax.grid(axis="y", lw=.35, color="#DDD"); ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    ax.legend(loc="upper left", frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(B.FIG / "steg_ntl_gates.pdf", bbox_inches="tight"); plt.close(fig)
    print(f"written {B.FIG / 'steg_ntl_gates.pdf'}")
    print("share of land lit, %:"); print(w.round(1).to_string())


if __name__ == "__main__":
    main()
