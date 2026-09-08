"""
build_panels.py — the two analysis panels, from source layers.

    sector_year_panel.csv    416 sectors x 19 years (2006-2024)
    cell_master.csv          2,148 cells, cross-section

These are the files every regression and every figure runs on. They previously
existed only as saved output — no script built them, so nobody could check how
`hazard_pct` was constructed or rebuild them after a data refresh. This is that
step, written down.

Usage
-----
    python data-build-scripts/build_panels.py --all
    python data-build-scripts/build_panels.py --only sector_year
    python data-build-scripts/build_panels.py --checks       # validate, build nothing

Denominator rules are applied HERE, once, and travel with the data as columns.
Do not re-derive them downstream:

    hazard_pct        loss in year t / forest standing at the start of t
    hazard_usable     False where that denominator is < MIN_FOREST_HA
    loss_rate         cumulative loss / tree cover in 2000
    loss_rate_usable  False where 2000 cover is < MIN_FOREST_HA
    loss_per_km2      loss / land area — no forest denominator, never degenerate

See docs/cleaning_decisions.md, "Hansen loss: which denominator", for why each
guard exists and which measure to use for what.
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import paths as P

import numpy as np
import pandas as pd

# A forest denominator smaller than this is not a denominator. 162 sector-years
# hold under 1 ha and one holds 1.4e-16 ha — floating-point residue of zero —
# which returns a hazard of 1.9e17 and swamps any mean taken over the column.
MIN_FOREST_HA = 10.0

FIRST_YEAR, LAST_YEAR = 2006, 2024      # boundaries are stable from the 2006 reform


def _log(msg: str) -> None:
    print(f"[panels] {msg}", flush=True)


def _csv(rel: str, id_col: str | None = None) -> pd.DataFrame:
    d = pd.read_csv(P.GEO / rel)
    if id_col and id_col in d.columns:
        d[id_col] = d[id_col].astype("int64")
    return d


def _dkey(s) -> str:
    """Canonical district key: lowercase, accents and punctuation stripped.

    The only safe join between the CHIRPS panel and the NISR tables, which use
    incompatible numeric district ids.
    """
    if pd.isna(s):
        return ""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _loss_long(wide: pd.DataFrame, id_col: str) -> pd.DataFrame:
    """Hansen loss_YYYY_ha columns -> long (id, year, loss_ha)."""
    cols = [c for c in wide.columns if c.startswith("loss_") and c.endswith("_ha")
            and c[5:9].isdigit()]
    long = wide.melt(id_vars=[id_col], value_vars=cols,
                     var_name="v", value_name="loss_ha")
    long["year"] = long.v.str[5:9].astype(int)
    return long.drop(columns="v").sort_values([id_col, "year"])


# ==========================================================================
# SECTOR x YEAR
# ==========================================================================

def build_sector_year() -> pd.DataFrame:
    """416 sectors x 19 years, with the forest, land-cover and rainfall series.

    `forest_start_ha` is a depleting stock: tree cover in 2000 less cumulative
    loss before year t, floored at zero. That is the denominator a discrete-time
    hazard wants, and it is why the guard below is needed — 12 sectors exhaust
    their 2000 stock entirely while Hansen keeps recording loss on post-2000
    plantations.
    """
    _log("sector-year panel")
    han = _csv("forest/hansen_sdpt_by_sector.csv", "sector_id")
    ex = _csv("protected-areas/sectors_park_exposure_geodatarw.csv", "sector_id")

    long = _loss_long(han, "sector_id")
    long = long[long.year.between(FIRST_YEAR, LAST_YEAR)].copy()

    tc = han.set_index("sector_id").treecover2000_ha
    long["cum_prior"] = (long.groupby("sector_id").loss_ha.cumsum() - long.loss_ha)
    long["forest_start_ha"] = (long.sector_id.map(tc) - long.cum_prior).clip(lower=0)

    # The guard. Both columns travel with the data so no downstream script has
    # to remember to apply it.
    ok = long.forest_start_ha >= MIN_FOREST_HA
    long["hazard_pct"] = np.where(
        ok, 100 * long.loss_ha / long.forest_start_ha.where(ok), np.nan)
    long["hazard_usable"] = ok
    long = long.drop(columns="cum_prior")

    # Dynamic World: stocks and year-on-year change.
    #
    # The dw_* columns are ALREADY shares of sector area - carried through as
    # they are, not re-normalised. They sum to ~0.9998 rather than exactly 1
    # because some pixels are unclassified, and dividing that shortfall away
    # would inflate every class by ~0.12% and quietly assert full coverage the
    # product does not have.
    dw = _csv("land-cover/dw_by_sector.csv", "sector_id")
    dw = dw[["sector_id", "year", "dw_trees", "dw_crops"]].sort_values(["sector_id", "year"])
    dw["tree_chg"] = dw.groupby("sector_id").dw_trees.diff()
    dw["crop_chg"] = dw.groupby("sector_id").dw_crops.diff()

    # TMF: forest = undisturbed + degraded. Regrowth is reported separately
    # because it is a different process, not a smaller loss.
    tmf = _csv("forest/tmf_by_sector.csv", "sector_id")
    tmf["tmf_forest"] = tmf.tmf_undisturbed_forest_ha + tmf.tmf_degraded_forest_ha
    tmf = tmf[["sector_id", "year", "tmf_forest", "tmf_regrowth_ha"]].sort_values(
        ["sector_id", "year"])
    tmf["tmf_net_chg"] = tmf.groupby("sector_id").tmf_forest.diff()

    # Rainfall is district-level (CHIRPS zonal means), so it repeats across the
    # sectors of a district. Flagged here so nobody reads it as sector variation.
    #
    # JOIN ON NAME, NOT ID. rainfall_annual.csv carries extract.py's own
    # district_id (1-30, assigned after sorting GADM by province then district);
    # the exposure tables carry NISR codes (11-57). The two ranges OVERLAP at
    # 11, 12, 13, 21..., so joining on district_id does not fail - it silently
    # matches the wrong districts for a third of the panel.
    rain = pd.read_csv(P.PROC / "rainfall_annual.csv")[
        ["district", "year", "rain_mm", "rain_z"]]
    rain["dkey"] = rain.district.map(_dkey)
    rain = rain.drop(columns="district")

    geo = ex[["sector_id", "district_id", "district", "border", "dist_to_park_km"]].copy()
    geo["dkey"] = geo.district.map(_dkey)
    p = (long.merge(geo, on="sector_id", how="left")
              .merge(dw, on=["sector_id", "year"], how="left")
              .merge(tmf, on=["sector_id", "year"], how="left")
              .merge(rain, on=["dkey", "year"], how="left")
              .drop(columns="dkey"))

    cols = ["sector_id", "year", "loss_ha", "forest_start_ha", "hazard_pct",
            "hazard_usable", "dw_crops", "dw_trees", "crop_chg", "tree_chg",
            "tmf_forest", "tmf_net_chg", "tmf_regrowth_ha", "district",
            "district_id", "border", "dist_to_park_km", "rain_mm", "rain_z"]
    return p[cols].sort_values(["sector_id", "year"]).reset_index(drop=True)


# ==========================================================================
# CELL CROSS-SECTION
# ==========================================================================

def _cells_gdf():
    import geopandas as gpd
    g = gpd.read_file(P.GEO / "protected-areas/cells_park_exposure_geodatarw.gpkg")
    g["cell_id"] = g.cell_id.astype("int64")
    return g.to_crs(32735)


def _buildings_by_cell(cells) -> pd.DataFrame:
    """Google Open Buildings, joined to cells by centroid.

    A point-in-polygon join drops footprints whose centroid falls outside every
    cell polygon, so cell totals sit ~1% under the sector totals computed on
    sector polygons. That is expected, not a merge failure.
    """
    import geopandas as gpd
    _log("  buildings: spatial join (543 MB, slow)")
    b = gpd.read_parquet(P.GEO / "buildings/gob_rwanda_buildings.parquet",
                         columns=["geometry", "area_in_meters"])
    b = b.to_crs(32735)
    b["geometry"] = b.geometry.centroid
    j = gpd.sjoin(b, cells[["cell_id", "geometry"]], how="inner", predicate="within")
    return (j.groupby("cell_id")
             .agg(n_buildings=("area_in_meters", "size"),
                  building_area_m2=("area_in_meters", "sum"),
                  mean_building_m2=("area_in_meters", "mean"))
             .reset_index())


def _grid_by_cell(cells) -> pd.DataFrame:
    """gridfinder medium-voltage lines, clipped to each cell, length in km."""
    import geopandas as gpd
    _log("  gridfinder: overlay")
    g = gpd.read_file(P.GEO / "electricity/gridfinder_rwanda.gpkg").to_crs(32735)
    j = gpd.overlay(gpd.GeoDataFrame(geometry=g.geometry, crs=g.crs),
                    cells[["cell_id", "geometry"]], how="intersection",
                    keep_geom_type=False)
    j["grid_km"] = j.geometry.length / 1000
    return j.groupby("cell_id").grid_km.sum().reset_index()


def _sdpt_by_cell(cells) -> pd.DataFrame:
    """WRI planted trees, area intersecting each cell, in hectares."""
    import geopandas as gpd
    _log("  SDPT: overlay (284 MB, slow)")
    s = gpd.read_file(P.GEO / "planted-trees/sdpt_rwanda.gpkg").to_crs(32735)
    j = gpd.overlay(gpd.GeoDataFrame(geometry=s.geometry, crs=s.crs),
                    cells[["cell_id", "geometry"]], how="intersection",
                    keep_geom_type=False)
    j["sdpt_area_ha"] = j.geometry.area / 10_000
    return j.groupby("cell_id").sdpt_area_ha.sum().reset_index()


def _pop_by_cell(cells) -> pd.DataFrame:
    """1 km gridded population, summed over each cell.

    Two traps in this raster, both of which silently return garbage rather than
    failing. It is NOT in EPSG:4326 - it ships in a projected ITRF_2005
    transverse Mercator - so the cells are reprojected onto whatever CRS the
    file declares rather than to a guess. And its nodata is int32 minimum
    (-2147483648), so passing any other nodata value makes every cell sum to
    that number; the value is read from the file instead of being asserted.

    all_touched is FALSE here, unlike the rest of the zonal work. Population is
    a count, and all_touched assigns a 1 km pixel to every cell it overlaps, so
    with ~12 km2 cells it counts the same people several times: the national
    total came to 28.5M against Rwanda's ~13.2M. Centroid assignment gives each
    pixel to exactly one cell and conserves the total. The cost is that a few
    cells smaller than a pixel capture nothing and read zero.
    """
    import rasterio
    from rasterstats import zonal_stats
    _log("  population: zonal sum")
    with rasterio.open(P.POP_RASTER) as src:
        crs, nodata = src.crs, src.nodata
    c = cells.to_crs(crs)
    st = zonal_stats(c.geometry, str(P.POP_RASTER), stats=["sum"],
                     all_touched=False, nodata=nodata)
    return pd.DataFrame({"cell_id": c.cell_id.values,
                         "pop_total": [(s or {}).get("sum") or 0 for s in st]})


def build_cell_master(fast: bool = False) -> pd.DataFrame:
    """2,148 cells: park exposure, forest, and the infrastructure covariates.

    The cell is the finest geography on which the forest measures and the park
    boundaries are both defined, so it is the sharpest cross-section the public
    data supports.
    """
    _log("cell master")
    ex = _csv("protected-areas/cells_park_exposure_geodatarw.csv", "cell_id")
    han = _csv("forest/hansen_by_cell.csv", "cell_id")

    base = ex.merge(
        han[["cell_id", "treecover2000_ha", "loss_total_ha"]], on="cell_id", how="left")

    if fast:
        _log("  --fast: reusing infrastructure columns from the previous build")
        prev = _csv("forest/cell_master.csv", "cell_id")
        keep = ["cell_id", "n_buildings", "building_area_m2", "mean_building_m2",
                "grid_km", "sdpt_area_ha", "pop_total"]
        infra = prev[[c for c in keep if c in prev.columns]]
    else:
        cells = _cells_gdf()
        infra = (_buildings_by_cell(cells)
                 .merge(_grid_by_cell(cells), on="cell_id", how="outer")
                 .merge(_sdpt_by_cell(cells), on="cell_id", how="outer")
                 .merge(_pop_by_cell(cells), on="cell_id", how="outer"))

    d = base.merge(infra, on="cell_id", how="left")
    for c in ("n_buildings", "building_area_m2", "grid_km", "sdpt_area_ha", "pop_total"):
        if c in d.columns:
            d[c] = d[c].fillna(0)

    km2 = d.unit_km2.replace(0, np.nan)
    d["bld_density"] = d.n_buildings / km2
    d["pop_density"] = d.pop_total / km2
    d["grid_km_per_km2"] = d.grid_km / km2
    # ha of planted trees over ha of land. The previous hand-built
    # cell_master.csv had this wrong by ~300x - values ran to 32,308 for a
    # quantity that cannot exceed 1 - so do not compare against that file.
    d["planted_share"] = d.sdpt_area_ha / (km2 * 100)

    # Same denominator discipline as the sector panel. 81 cells exceed 100%
    # because Hansen records loss on plantations established after 2000; they
    # sit mostly far from parks, so an unguarded mean reverses the gradient.
    ok = d.treecover2000_ha >= MIN_FOREST_HA
    d["loss_rate"] = np.where(ok, 100 * d.loss_total_ha / d.treecover2000_ha.where(ok),
                              np.nan)
    d["loss_rate_usable"] = ok
    d["loss_per_km2"] = d.loss_total_ha / km2
    return d.sort_values("cell_id").reset_index(drop=True)


# ==========================================================================
# CHECKS
# ==========================================================================

def checks() -> int:
    """Validate both panels. Mirrors the 03_checks.py step in the NISR pipelines."""
    fails = []

    def chk(name: str, ok: bool, detail: str = "") -> None:
        print(f"  {'ok  ' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
        if not ok:
            fails.append(name)

    print("[checks] sector_year_panel")
    s = _csv("forest/sector_year_panel.csv", "sector_id")
    chk("416 sectors", s.sector_id.nunique() == 416, f"got {s.sector_id.nunique()}")
    chk("years 2006-2024", (s.year.min(), s.year.max()) == (FIRST_YEAR, LAST_YEAR),
        f"got {s.year.min()}-{s.year.max()}")
    chk("no duplicate sector-year", not s.duplicated(["sector_id", "year"]).any())
    chk("hazard finite where usable",
        np.isfinite(s.loc[s.hazard_usable, "hazard_pct"]).all())
    chk("hazard null where not usable", s.loc[~s.hazard_usable, "hazard_pct"].isna().all())
    chk("forest_start never negative", (s.forest_start_ha >= 0).all())
    chk("border flag present", s.border.notna().all())
    chk("rainfall joined", s.rain_mm.notna().mean() > 0.95,
        f"{100 * s.rain_mm.notna().mean():.1f}% non-null")

    print("[checks] cell_master")
    c = _csv("forest/cell_master.csv", "cell_id")
    chk("2,148 cells", len(c) == 2148, f"got {len(c)}")
    chk("no duplicate cell_id", not c.cell_id.duplicated().any())
    chk("cells nest in 416 sectors", c.sector_id.nunique() == 416,
        f"got {c.sector_id.nunique()}")
    chk("loss_rate null where not usable", c.loc[~c.loss_rate_usable, "loss_rate"].isna().all())
    chk("loss_per_km2 always defined", c.loss_per_km2.notna().all())
    chk("planted_share in [0, 1]", c.planted_share.between(0, 1).all(),
        f"max {c.planted_share.max():.3f}")

    print(f"[checks] {'all passed' if not fails else str(len(fails)) + ' FAILED'}")
    return 1 if fails else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--all", action="store_true")
    p.add_argument("--only", nargs="+", choices=["sector_year", "cell_master"])
    p.add_argument("--checks", action="store_true", help="validate existing panels only")
    p.add_argument("--fast", action="store_true",
                   help="cell_master: reuse infrastructure columns instead of "
                        "re-running the spatial joins (minutes -> seconds)")
    a = p.parse_args(argv)

    if a.checks:
        return checks()
    todo = ["sector_year", "cell_master"] if a.all else (a.only or [])
    if not todo:
        p.print_help()
        return 1

    out = P.GEO / "forest"
    P.check_writable(out)
    out.mkdir(parents=True, exist_ok=True)

    if "sector_year" in todo:
        d = build_sector_year()
        d.to_csv(out / "sector_year_panel.csv", index=False)
        _log(f"  -> sector_year_panel.csv ({len(d):,} rows, "
             f"{d.sector_id.nunique()} sectors)")
    if "cell_master" in todo:
        d = build_cell_master(fast=a.fast)
        d.to_csv(out / "cell_master.csv", index=False)
        _log(f"  -> cell_master.csv ({len(d):,} cells)")

    _log("done")
    return checks()


if __name__ == "__main__":
    sys.exit(main())
