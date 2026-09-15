"""
steg_ntl_gates.py -- nighttime lights within 10 km of the park gates, for the STEG appendix.

    python steg_ntl_gates.py
    output/figures/steg_ntl_gates.pdf

The land within 10 km of the park gates, with the parks themselves taken out (park land is dark by
construction) and anything outside Rwanda taken out, so the area is a circle conditional on not being
in the park. All four gates pooled into one area: Kinigi (Volcanoes), Gisakura and Kitabi (Nyungwe),
the South Gate (Akagera). Gishwati-Mukura has no gate in the data. Coordinates: bar_chart_housing.GATE_XY.

City sectors are removed from every area: the whole City of Kigali (list 2a) and the nine sectors of the
four largest towns of 2002 (list 3), as settled in TRS-Border-Sectors.md ("Kigali all + cities" in
bar_chart_housing.geography). This takes Musanze town out of the Volcanoes area, where it sat within
10 km of Kinigi and gave about half the light.

Comparison: the rest of Rwanda outside the parks, the city sectors and the gate area.

Annual VIIRS VNL v2 composites, 2012-2025, background-masked average radiance. The monthly composites were tried first and dropped: in dark areas
they are dominated by background noise and fires (Akagera area 0.02-0.38 nW/cm2/sr monthly against
0.001-0.03 annual), and cloud removes 7-11 months a year in 2021-2025.
    mean radiance over observed pixels (cf_cvg > 0), an area-year seen over less than 90% of its
    pixels dropped; pixels assigned by centre.
    each series indexed to its own 2012 value = 100; the levels are printed alongside.
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

KM, MIN_OBS, BASE = 10.0, 0.90, 2012
GATE = f"Within {KM:.0f} km of the park gates"
REST = "Rest of rural Rwanda"
COL = {GATE: "#2a9d8f", REST: "#8c8c8c"}
RX = re.compile(r"ntl_viirs_avg_(\d{4})_rwanda\.tif$")


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


def masks(zone):
    with rasterio.open(next(p for p in sorted(H.CLIPS.glob("ntl_viirs_avg_*.tif")) if RX.match(p.name))) as r:
        grid = dict(out_shape=r.shape, transform=r.transform)
        crs = r.crs
    to_r = lambda z: gpd.GeoSeries([z], crs=32736).to_crs(crs).iloc[0]
    return {n: rasterize([(to_r(z), 1)], fill=0, **grid).astype(bool) for n, z in zone.items()}, grid


def series(M, grid):
    rows = []
    for p in sorted(H.CLIPS.glob("ntl_viirs_avg_*.tif")):
        m = RX.match(p.name)
        if not m:
            continue
        with rasterio.open(p) as r:
            assert r.shape == grid["out_shape"] and r.transform == grid["transform"], p.name
            y = r.read(1).astype(float)
        with rasterio.open(H.CLIPS / p.name.replace("_avg_", "_cfcvg_")) as r:
            obs = r.read(1) > 0
        for n, mk in M.items():
            share = obs[mk].mean()
            rows.append(dict(year=int(m.group(1)), area=n, obs=share,
                             light=np.nanmean(y[mk & obs]) if share >= MIN_OBS else np.nan))
    return pd.DataFrame(rows)


def main():
    zone = areas()
    M, grid = masks(zone)
    for n, m in M.items():
        print(f"{n:22s} {zone[n].area / 1e6:8,.0f} km2  {m.sum():7,d} pixels")
    d = series(M, grid)
    w = d.pivot(index="year", columns="area", values="light")[list(COL)]
    print("dropped area-years (<90% observed):", w.isna().sum().to_dict())
    idx = w / w.loc[BASE] * 100

    fig, ax = plt.subplots(figsize=(9.5, 4.8))
    for n in COL:
        ax.plot(idx.index, idx[n], "-o", color=COL[n], lw=2, ms=4, label=n)
    ax.axhline(100, color="0.3", lw=.6, ls=":")
    ax.set_ylabel(f"Nighttime lights, {BASE} = 100")
    ax.set_xticks(range(BASE, int(idx.index.max()) + 1, 1))
    ax.set_ylim(bottom=0)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.grid(axis="y", lw=.35, color="#DDD"); ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    ax.legend(loc="upper left", frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(B.FIG / "steg_ntl_gates.pdf", bbox_inches="tight"); plt.close(fig)
    print(f"written {B.FIG / 'steg_ntl_gates.pdf'}")
    print("levels, mean radiance nW/cm2/sr:"); print(w.round(4).to_string())
    print(f"index, {BASE} = 100:"); print(idx.round(0).to_string())


if __name__ == "__main__":
    main()
