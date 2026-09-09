"""
02_zonal.py -- area-weighted statistics for every sector and every cell, one row per unit-period.

    python 02_zonal.py [dmsp|viirs|viirs_m|li|chen]

    2_Intermediate/ntl_<product>_<unit>_long.csv

The step is driven by what is on disk: H.clips() lists every Rwanda cut-out with its product, layer,
satellite and period, and each one gets the same four statistics. Nothing here knows the product
list in advance, so adding a layer to 01b_clip_raw.py is enough to bring it into the panel.

Rows are long in the layer and the satellite, because the raw products are not one series each:
DMSP has four layers and two satellites flying in twelve of its years, VIIRS has four layers, and
the harmonised products have one apiece. 03_merge.py does the reshaping and the satellite averaging.

Not every statistic means something for every layer. mean is the only one to read on cf_cvg, which
counts cloud-free nights rather than measuring light, and on the VIIRS lit mask mean IS the lit
share. They are all computed anyway: they cost one pass, and the merge step picks.

Why area-weighted and not "pixels whose centre falls inside". Cells average 12 km2 but the smallest
are well under 1 km2, and a DMSP pixel is 0.85 km2, so a centre-in-polygon rule would hand some
cells no pixels at all and would misattribute the edges of the rest. Instead each pixel is split
into SUPERSAMPLE^2 sub-pixels that inherit its value, the sub-pixels are assigned to whichever unit
contains them, and the statistics are taken over those. At 4x4 the worst-case edge error is an
eighth of a pixel, and every unit gets a value.

Areas are computed per raster row, since a degree of longitude shortens with latitude. Over Rwanda
that correction is tiny, but it costs nothing and makes the km2 columns honest.
"""
import sys

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from affine import Affine
from rasterio.features import rasterize

import ntl_helpers as H

R_EARTH_LAT_KM = 110.574        # km per degree of latitude
R_EARTH_LON_KM = 111.320        # km per degree of longitude at the equator

_GRIDS = {}                     # (unit, raster grid) -> labels, sub-pixel areas


def geometry(unit):
    path, idcol = H.UNITS[unit]
    g = gpd.read_file(path)
    g = g.rename(columns={idcol: "unit_id"})
    g["unit_id"] = g.unit_id.astype(int)
    return g.sort_values("unit_id").reset_index(drop=True)


def subpixel_grid(src, g, unit):
    """labels and per-sub-pixel area at SUPERSAMPLE times the raster's resolution.

    Cached on the raster geometry, not on the file: DMSP and Li share a 30 arc-second grid and VIIRS
    and Chen a 15 arc-second one, so four rasterisations serve all 207 clips."""
    key = (unit, src.width, src.height, tuple(np.round(src.transform[:6], 10)))
    if key in _GRIDS:
        return _GRIDS[key]
    s = H.SUPERSAMPLE
    fine = src.transform * Affine.scale(1 / s, 1 / s)
    shape = (src.height * s, src.width * s)
    lab = rasterize(((geom, i + 1) for i, geom in enumerate(g.to_crs(src.crs).geometry)),
                    out_shape=shape, transform=fine, fill=0, dtype="int32")
    rows = np.arange(shape[0])
    lat = fine.f + fine.e * (rows + 0.5)                       # centre latitude of each fine row
    dy = abs(fine.e) * R_EARTH_LAT_KM
    dx = abs(fine.a) * R_EARTH_LON_KM * np.cos(np.radians(lat))
    area = np.repeat((dx * dy)[:, None], shape[1], axis=1).astype("float64")
    _GRIDS[key] = (lab, area)
    return lab, area


def one_raster(clip, g, unit, floor):
    """the four statistics for one clip, one row per unit"""
    k = len(g)
    with rasterio.open(clip["path"]) as src:
        a = src.read(1).astype("float64")
        if src.nodata is not None:
            a = np.where(a == src.nodata, 0.0, a)
        lab, area = subpixel_grid(src, g, unit)
        s = H.SUPERSAMPLE
        v = np.repeat(np.repeat(a, s, axis=0), s, axis=1)
        rr, cc = np.divmod(np.arange(lab.size), lab.shape[1])
        pid = (rr // s) * src.width + (cc // s)              # which whole pixel each sub-pixel is in
    flat, vf, af = lab.ravel(), v.ravel(), area.ravel()
    keep = flat > 0
    flat, vf, af, pidf = flat[keep], vf[keep], af[keep], pid[keep]
    n = np.bincount(flat, minlength=k + 1)[1:]
    km2 = np.bincount(flat, weights=af, minlength=k + 1)[1:]
    wsum = np.bincount(flat, weights=vf * af, minlength=k + 1)[1:]
    lit = np.bincount(flat, weights=(vf > floor) * af, minlength=k + 1)[1:]
    mx = np.full(k + 1, -np.inf)
    np.maximum.at(mx, flat, vf)
    # Share of the unit's light in its brightest WHOLE pixel. Each sub-pixel is tagged with the
    # parent pixel it came from, the area-weighted contributions are summed within (unit, pixel),
    # and the largest is taken. max/sum would do instead only if every unit held at least one whole
    # pixel: a unit covering a sixteenth of one pixel has sum = value/16 and max = value, giving 16.
    # Computed on NON-NEGATIVE contributions only. VIIRS mean and median radiance are background
    # subtracted and go negative over dark ground, so the plain total can be near zero or below it
    # and the ratio then explodes -- cells reached 4.09 before this. Numerator and denominator are
    # both sums of non-negative terms and the numerator is one of the denominator's groups, so the
    # share is bounded by one by construction.
    vpos = np.maximum(vf, 0.0)
    wpos = np.bincount(flat, weights=vpos * af, minlength=k + 1)[1:]
    top = pd.DataFrame({"u": flat, "p": pidf, "va": vpos * af}).groupby(["u", "p"], sort=False).va.sum()
    top = top.groupby(level=0).max().reindex(np.arange(1, k + 1)).to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.where(km2 > 0, wsum / km2, np.nan)
        lit_share = np.where(km2 > 0, lit / km2, np.nan)
    px_km2 = af.sum() / len(af) * H.SUPERSAMPLE ** 2            # area of one whole pixel here
    return pd.DataFrame({
        "unit_id": g.unit_id.values, "layer": clip["layer"], "sat": clip["sat"],
        "period": clip["period"], "mean": mean, "sum": wsum / px_km2,
        "max": np.where(np.isfinite(mx[1:]), mx[1:], np.nan), "lit_share": lit_share,
        "top": np.where(wpos > 0, np.minimum(top / np.where(wpos > 0, wpos, 1), 1.0), np.nan),
        "area_km2": km2, "n_subpixels": n})


def stats(product, unit):
    cl = [c for c in H.clips() if c["product"] == product]
    if not cl:
        return None
    g = geometry(unit)
    floor = H.FLOORS[product]
    rows = []
    for c in sorted(cl, key=lambda d: (d["period"], d["layer"], d["sat"])):
        r = one_raster(c, g, unit, floor)
        rows.append(r)
        tag = f"{c['layer']}{'/' + c['sat'] if c['sat'] else ''}"
        print(f"  {product:7s} {unit:6s} {c['period']} {tag:14s} "
              f"mean {np.nanmean(r['mean']):.4g}  max {np.nanmax(r['max']):.4g}")
    out = pd.concat(rows, ignore_index=True)
    keep_cols = [c for c in ("sector", "cell", "district", "province",
                             "sector_id", "district_id", "province_id") if c in g.columns]
    return out.merge(g[["unit_id"] + keep_cols], on="unit_id", how="left")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    H.INTERMEDIATE.mkdir(parents=True, exist_ok=True)
    for product in (args or list(H.PRODUCTS)):
        for unit in H.UNITS:
            df = stats(product, unit)
            if df is None:
                print(f"{product}: no clips on disk, skipped\n")
                break
            out = H.INTERMEDIATE / f"ntl_{product}_{unit}_long.csv"
            df.to_csv(out, index=False)
            print(f"{product} {unit}: {df.shape} -> {out.name}\n")
