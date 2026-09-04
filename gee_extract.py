"""
gee_extract.py — pull TMF and Dynamic World to sector level via Google Earth Engine.

Neither layer has a working bulk download: the JRC TMF tile endpoint returns HTTP
500, and Dynamic World is a near-real-time global collection with no download at
all. Both live on Earth Engine, which also computes the zonal statistics
server-side — so this uploads 416 sector polygons and gets back a table, with no
rasters crossing the network.

Setup (once)
------------
    pip install earthengine-api
    earthengine authenticate            # opens a browser
    # register a Cloud project at code.earthengine.google.com (noncommercial)

Usage
-----
    python gee_extract.py --project YOUR_GEE_PROJECT --datasets tmf dw
    python gee_extract.py --project YOUR_GEE_PROJECT --datasets tmf --years 1990 2024

Outputs (data/processed/)
-------------------------
    tmf_by_sector.csv   sector x year x TMF annual-change class, area in ha
    dw_by_sector.csv    sector x year, mean fraction of each Dynamic World class
    radd_by_sector.csv  sector x year, hectares of confirmed RADD alerts

Both key on `sector_id`, so they join to the Census microdata and to the
existing park-exposure and Hansen tables.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
PROC = ROOT / "data" / "processed"

SECTORS_GPKG = Path(
    "/Users/allegrasaggese/Library/CloudStorage/Dropbox/Rwanda - TRS/"
    "data/geo-data/protected-areas/sectors_park_exposure_wdpa.gpkg"
)

# JRC Tropical Moist Forest, annual change collection.
TMF_ANNUAL = "projects/JRC/TMF/v1_2023/AnnualChanges"
# Class codes in the AnnualChange product. Verified against the Rwanda totals:
# class 6 dominates (~2.0M ha of Rwanda's 2.63M), which is "other land cover"
# (mostly agriculture) - not water, as an earlier version of this mapping had it.
TMF_CLASSES = {
    1: "undisturbed_forest",
    2: "degraded_forest",
    3: "deforested",
    4: "regrowth",
    5: "water",              # permanent or seasonal
    6: "other_land_cover",
}

# RADD deforestation alerts. The collection mixes alert images with forest-mask
# baselines, so it must be filtered on `layer` or a mosaic fails on mismatched
# bands. Alert: 2 = unconfirmed, 3 = confirmed. Date: YYDOY (19008 = 2019 day 8).
RADD = "projects/radar-wur/raddalert/v1"

DW = "GOOGLE/DYNAMICWORLD/V1"
DW_BANDS = ["water", "trees", "grass", "flooded_vegetation", "crops",
            "shrub_and_scrub", "built", "bare", "snow_and_ice"]

# Native resolutions. TMF is 30 m; Dynamic World is 10 m but is reduced at 30 m
# here so the two share a grid and the export stays within EE's limits.
SCALE_M = 30


def _log(msg: str) -> None:
    print(f"[gee] {msg}", flush=True)


def init(project: str):
    import ee
    try:
        ee.Initialize(project=project)
    except Exception:
        _log("not authenticated - run: earthengine authenticate")
        raise
    _log(f"Earth Engine initialised on project {project!r}")
    return ee


def sectors_to_ee(ee):
    """Upload the 416 sector polygons as an in-memory FeatureCollection.

    Sent inline rather than as an EE asset: 416 polygons is small enough, and it
    avoids an asset-upload step that would need separate permissions.
    """
    import geopandas as gpd

    if not SECTORS_GPKG.exists():
        raise FileNotFoundError(f"sector file not found: {SECTORS_GPKG}")

    g = gpd.read_file(SECTORS_GPKG).to_crs(4326)
    # Simplify slightly: sector borders are far finer than a 30 m grid needs,
    # and the raw geometry makes the request payload large.
    g["geometry"] = g.geometry.simplify(0.0005)

    feats = []
    for r in g.itertuples():
        feats.append(ee.Feature(
            ee.Geometry(r.geometry.__geo_interface__),
            {"sector_id": int(r.sector_id), "sector": str(r.sector),
             "district": str(r.district)},
        ))
    _log(f"{len(feats)} sector polygons prepared")
    return ee.FeatureCollection(feats)


def fetch_tmf(ee, sectors, years: range) -> pd.DataFrame:
    """Area (ha) of each TMF annual-change class, per sector per year."""
    _log(f"TMF annual change, {years.start}-{years.stop - 1}")
    coll = ee.ImageCollection(TMF_ANNUAL)

    rows = []
    for yr in years:
        band = f"Dec{yr}"
        try:
            img = coll.mosaic().select(band)
        except Exception as exc:  # noqa: BLE001
            _log(f"  ! {yr}: {exc}")
            continue

        # Pixel area in hectares, grouped by class code.
        area = ee.Image.pixelArea().divide(1e4).addBands(img)
        stats = area.reduceRegions(
            collection=sectors,
            reducer=ee.Reducer.sum().group(groupField=1, groupName="class"),
            scale=SCALE_M,
        )
        try:
            got = stats.getInfo()
        except Exception as exc:  # noqa: BLE001
            _log(f"  ! {yr} reduce failed: {str(exc)[:90]}")
            continue

        for f in got["features"]:
            p = f["properties"]
            rec = {"sector_id": p["sector_id"], "sector": p["sector"],
                   "district": p["district"], "year": yr}
            for grp in p.get("groups", []):
                name = TMF_CLASSES.get(int(grp["class"]), f"class_{grp['class']}")
                rec[f"tmf_{name}_ha"] = grp["sum"]
            rows.append(rec)
        _log(f"  {yr} done")
        time.sleep(0.3)   # be polite to the EE quota

    return pd.DataFrame(rows).fillna(0)


def _dw_reduce(ee, img, subset, tile_scale):
    """One reduceRegions call. Separated so it can be retried with new settings."""
    return img.reduceRegions(collection=subset, reducer=ee.Reducer.mean(),
                             scale=SCALE_M, tileScale=tile_scale).getInfo()


def fetch_dw(ee, sectors, years: range) -> pd.DataFrame:
    """Mean per-class probability from Dynamic World, per sector per year.

    Dynamic World gives per-pixel class probabilities, so the annual mean of each
    band is the expected fraction of the sector in that class. Cloudy scenes are
    already excluded by the collection's own masking.

    Memory handling: a year of Dynamic World over all 416 sectors exceeds Earth
    Engine's per-request memory. Two escalating fallbacks are used - a larger
    `tileScale` (which splits the computation into more, smaller tiles), then
    chunking the sectors. Escalating only on failure keeps the common case fast.
    """
    _log(f"Dynamic World, {years.start}-{years.stop - 1}")
    n = sectors.size().getInfo()
    rows = []

    for yr in years:
        if yr < 2015:
            continue   # collection starts June 2015
        img = (ee.ImageCollection(DW).filterDate(f"{yr}-01-01", f"{yr}-12-31")
               .select(DW_BANDS).mean())

        feats, ok = [], False
        for tile_scale in (4, 16):
            try:
                feats = _dw_reduce(ee, img, sectors, tile_scale)["features"]
                ok = True
                break
            except Exception as exc:  # noqa: BLE001
                if "memory" not in str(exc).lower():
                    _log(f"  ! {yr}: {str(exc)[:80]}")
                    break

        if not ok:
            # Last resort: reduce the sectors in chunks so each request is small.
            feats, failed = [], 0
            lst = sectors.toList(n)
            CHUNK = 40
            for start in range(0, n, CHUNK):
                sub = ee.FeatureCollection(lst.slice(start, min(start + CHUNK, n)))
                try:
                    feats += _dw_reduce(ee, img, sub, 16)["features"]
                except Exception:  # noqa: BLE001
                    failed += 1
                time.sleep(0.2)
            if failed:
                _log(f"    {yr}: {failed} chunk(s) failed")
            ok = bool(feats)

        if not ok:
            _log(f"  ! {yr}: no data"); continue

        for f in feats:
            pr = f["properties"]
            rec = {"sector_id": pr["sector_id"], "sector": pr["sector"],
                   "district": pr["district"], "year": yr}
            for b in DW_BANDS:
                rec[f"dw_{b}"] = pr.get(b)
            rows.append(rec)
        _log(f"  {yr} done ({len(feats)} sectors)")
        time.sleep(0.3)

    return pd.DataFrame(rows)


def fetch_radd(ee, sectors, years: range) -> pd.DataFrame:
    """Confirmed RADD deforestation alerts per sector per year.

    Only confirmed alerts (Alert == 3) are counted; unconfirmed ones are
    provisional and are revised in later releases. Alert area is reported in
    hectares from pixel area rather than a pixel count, so the 10 m grid is
    handled correctly away from the equator.
    """
    _log(f"RADD alerts, {years.start}-{years.stop - 1}")
    al = (ee.ImageCollection(RADD)
          .filter(ee.Filter.eq("geography", "africa"))
          .filter(ee.Filter.eq("layer", "alerts")))
    img = al.mosaic()
    alert, date = img.select("Alert"), img.select("Date")

    rows = []
    for yr in years:
        if yr < 2019:
            continue   # RADD starts January 2019
        # YYDOY -> year: 19008 is 2019 day 8, so the year is Date // 1000 + 2000.
        yr_band = date.divide(1000).floor().add(2000)
        mask = alert.eq(3).And(yr_band.eq(yr))
        area = ee.Image.pixelArea().divide(1e4).updateMask(mask)

        feats, ok = [], False
        for tile_scale in (4, 16):
            try:
                feats = area.reduceRegions(collection=sectors,
                                           reducer=ee.Reducer.sum(),
                                           scale=SCALE_M,
                                           tileScale=tile_scale).getInfo()["features"]
                ok = True
                break
            except Exception as exc:  # noqa: BLE001
                if "memory" not in str(exc).lower():
                    _log(f"  ! {yr}: {str(exc)[:80]}")
                    break
        if not ok:
            _log(f"  ! {yr}: skipped"); continue

        for f in feats:
            pr = f["properties"]
            rows.append({"sector_id": pr["sector_id"], "sector": pr["sector"],
                         "district": pr["district"], "year": yr,
                         "radd_alert_ha": pr.get("sum", 0) or 0})
        _log(f"  {yr} done ({len(feats)} sectors)")
        time.sleep(0.3)

    return pd.DataFrame(rows)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--project", required=True, help="your GEE Cloud project id")
    p.add_argument("--datasets", nargs="+", default=["tmf", "dw", "radd"],
                   choices=["tmf", "dw", "radd"])
    p.add_argument("--years", nargs=2, type=int, default=[1990, 2024],
                   metavar=("START", "END"))
    args = p.parse_args(argv)

    ee = init(args.project)
    sectors = sectors_to_ee(ee)
    years = range(args.years[0], args.years[1] + 1)
    PROC.mkdir(parents=True, exist_ok=True)

    if "tmf" in args.datasets:
        d = fetch_tmf(ee, sectors, years)
        if not d.empty:
            d.to_csv(PROC / "tmf_by_sector.csv", index=False)
            _log(f"-> tmf_by_sector.csv ({len(d):,} sector-years)")

    if "dw" in args.datasets:
        d = fetch_dw(ee, sectors, years)
        if not d.empty:
            d.to_csv(PROC / "dw_by_sector.csv", index=False)
            _log(f"-> dw_by_sector.csv ({len(d):,} sector-years)")

    if "radd" in args.datasets:
        d = fetch_radd(ee, sectors, years)
        if not d.empty:
            d.to_csv(PROC / "radd_by_sector.csv", index=False)
            _log(f"-> radd_by_sector.csv ({len(d):,} sector-years)")

    _log("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
