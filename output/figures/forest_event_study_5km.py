"""Annual forest-loss event study around Rwanda's national parks.

Run with:

    python3 output/figures/forest_event_study_5km.py

The analysis uses a fixed 1-km grid and the common 2001-2024 period for
Hansen Global Forest Change and JRC Tropical Moist Forest. It estimates
year-specific differences relative to 2004 for three 5-km treatment
definitions. Gishwati-Mukura and the city-sector exclusion sample are
removed. Overlap weights balance the predetermined covariates separately
for every product and comparison without repeatedly using a small number
of matched controls.
"""

from __future__ import annotations

import math
import os
import textwrap
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from affine import Affine
from rasterio.features import rasterize
from rasterio.merge import merge
from rasterio.warp import Resampling, reproject, transform_bounds
from shapely import distance as shapely_distance
from shapely import points as shapely_points


REPO = Path("/Users/matteo/Documents/GitHub/rwa-trs")
DB = Path("/Users/matteo/Library/CloudStorage/Dropbox/1-Ongoing Projects/Rwanda - TRS")
GEO = DB / "data/geo-data"
FIGURE = DB / "output/figures/event_study_forest_5km.pdf"
RESULTS = DB / "output/tables/event_study_forest_5km.csv"
DIAGNOSTICS = DB / "output/tables/event_study_forest_5km_diagnostics.csv"

SECTORS = GEO / "protected-areas/sectors_park_exposure_wdpa.gpkg"
PARKS = GEO / "protected-areas/rwanda_protected_areas_geodata_rw.gpkg"
HANSEN_TC = GEO / "forest/hansen_rwanda_treecover2000.tif"
HANSEN_LOSS = GEO / "forest/hansen_rwanda_lossyear.tif"
DEM = GEO / "raster/rwanda_dem_z11_3857.tif"
ROADS = GEO / "roads/osm_trunk_primary.gpkg"
POPULATION = (
    DB / "data/Publicly-Available-NISR/geodata-nisr/PopulationDensity01.tif"
)
CLIMATE = {
    variable: GEO / f"climate/rwanda_{variable}_1995_2025.nc"
    for variable in ("ppt", "tmax", "tmin", "pdsi")
}
JRC = {
    "def20": "https://data.source.coop/epoch/jrc-tmf/v1_2025/N0_E20/DeforestationYear.tif",
    "def30": "https://data.source.coop/epoch/jrc-tmf/v1_2025/N0_E30/DeforestationYear.tif",
    "stock20": "https://data.source.coop/epoch/jrc-tmf/v1_2025/N0_E20/AnnualChange_2004.tif",
    "stock30": "https://data.source.coop/epoch/jrc-tmf/v1_2025/N0_E30/AnnualChange_2004.tif",
}

YEARS = np.arange(2001, 2025)
BASE_YEAR = 2004
PARK_NAMES = ("Volcanoes", "Nyungwe", "Gishwati-Mukura", "Akagera")
ACTIVE_PARKS = ("Volcanoes", "Nyungwe", "Akagera")
COMPARISONS = (
    "Park vs all non-park",
    "Park + 5 km vs beyond 5 km",
    "0-5 km ring vs beyond 5 km",
    "Gates+ sectors vs beyond 5 km",
    "Revenue sharing only vs beyond 5 km",
)
# The last two split the revenue-sharing zone by whether the sector also holds a park entrance, so
# that tourism can be separated from the transfer. Gates+ is the 12 entrance sectors; "revenue
# sharing only" is the other 32 of the 44 bordering sectors. Both are compared with the same far
# cells as the geographic panels, less the sectors bordering Gishwati-Mukura, which entered the
# revenue-sharing zone in 2015-16 and would otherwise be treated units sitting in the control group.
CITY_SECTORS = [2708, 2712, 2409, 2414, 4308, 4302, 3304, 3311, 3312]
BASELINE_MIN_HA = 10
BLOCK_METERS = 20_000
CI_Z = 1.645


def make_grid():
    """Construct the fixed Rwanda grid, geography, and exclusion masks."""
    sectors = gpd.read_file(SECTORS).to_crs(32736)
    sectors["sid"] = sectors.sector_id.astype(int)
    country = sectors.geometry.union_all()
    minx, miny, maxx, maxy = country.bounds
    minx = np.floor(minx / 1000) * 1000
    miny = np.floor(miny / 1000) * 1000
    maxx = np.ceil(maxx / 1000) * 1000
    maxy = np.ceil(maxy / 1000) * 1000
    width = int((maxx - minx) / 1000)
    height = int((maxy - miny) / 1000)
    transform = Affine(1000, 0, minx, 0, -1000, maxy)
    shape = (height, width)

    country_mask = rasterize(
        [(country, 1)], shape, transform=transform, fill=0,
        all_touched=False, dtype="uint8"
    ).astype(bool)
    kigali = sectors[sectors.province.str.contains("Kigali", na=False)]
    city_ids = set(kigali.sid) | set(CITY_SECTORS)
    city_geometry = sectors.loc[sectors.sid.isin(city_ids), "geometry"].union_all()
    city_mask = rasterize(
        [(city_geometry, 1)], shape, transform=transform, fill=0,
        all_touched=False, dtype="uint8"
    ).astype(bool)
    district = rasterize(
        [(row.geometry, int(row.sid) // 100) for row in sectors.itertuples()],
        shape, transform=transform, fill=0, all_touched=False, dtype="int16"
    )
    sector = rasterize(
        [(row.geometry, int(row.sid)) for row in sectors.itertuples()],
        shape, transform=transform, fill=0, all_touched=False, dtype="int32"
    )

    parks = gpd.read_file(PARKS)
    parks = parks[
        parks.designate.astype(str).str.contains("National Park", case=False, na=False)
    ].to_crs(32736)

    def park_geometry(pattern):
        subset = parks[
            parks.areaname.astype(str).str.contains(pattern, case=False, na=False)
        ]
        if subset.empty:
            raise RuntimeError(f"No national-park polygon matches {pattern!r}")
        return subset.geometry.union_all()

    geometries = {
        "Volcanoes": park_geometry("Volcanoes"),
        "Nyungwe": park_geometry("Nyungwe"),
        "Gishwati-Mukura": park_geometry("Gishwati|Mukura"),
        "Akagera": park_geometry("Akagera"),
    }
    zones = {}
    for label, buffer_meters in (("Park only", 0), ("Park + 5 km", 5_000)):
        zones[label] = {
            name: rasterize(
                [(geometry.buffer(buffer_meters), 1)], shape,
                transform=transform, fill=0, all_touched=False, dtype="uint8"
            ).astype(bool)
            for name, geometry in geometries.items()
        }

    row, column = np.indices(shape)
    x = minx + (column + 0.5) * 1000
    y = maxy - (row + 0.5) * 1000
    valid = country_mask & ~city_mask & (district > 0)
    return {
        "transform": transform,
        "shape": shape,
        "valid": valid,
        "district": district,
        "sector": sector,
        "x": x,
        "y": y,
        "zones": zones,
    }


def reproject_average(path, grid):
    destination = np.full(grid["shape"], np.nan, dtype=np.float32)
    with rasterio.open(path) as source:
        values = source.read(1, masked=True).astype(np.float32).filled(np.nan)
        reproject(
            values,
            destination,
            src_transform=source.transform,
            src_crs=source.crs,
            dst_transform=grid["transform"],
            dst_crs="EPSG:32736",
            src_nodata=np.nan,
            dst_nodata=np.nan,
            resampling=Resampling.average,
        )
    return destination


def static_controls(grid):
    elevation = reproject_average(DEM, grid)
    elevation[(elevation < 500) | (elevation > 5000)] = np.nan
    gradient_y, gradient_x = np.gradient(elevation, 1000, 1000)
    slope = np.degrees(np.arctan(np.sqrt(gradient_x ** 2 + gradient_y ** 2)))
    population = reproject_average(POPULATION, grid)

    roads = gpd.read_file(ROADS).to_crs(32736).geometry.union_all()
    points = shapely_points(grid["x"].ravel(), grid["y"].ravel())
    road_km = np.asarray(shapely_distance(points, roads)).reshape(grid["shape"]) / 1000
    return elevation, slope, population, road_km


def annual_climate(grid):
    source_years = np.arange(1995, 2026)
    output = {}
    for variable, path in CLIMATE.items():
        values = np.empty((*grid["shape"], len(source_years)), dtype=np.float32)
        with rasterio.open(path) as source:
            if source.count != len(source_years) * 12:
                raise ValueError(f"Unexpected number of monthly bands in {path}")
            scale, offset = source.scales[0], source.offsets[0]
            for index in range(len(source_years)):
                bands = list(range(index * 12 + 1, index * 12 + 13))
                raw = source.read(bands, masked=True).astype(np.float32)
                monthly = raw.filled(np.nan) * scale + offset
                annual = (
                    np.nansum(monthly, axis=0)
                    if variable == "ppt"
                    else np.nanmean(monthly, axis=0)
                )
                destination = np.full(grid["shape"], np.nan, dtype=np.float32)
                reproject(
                    annual,
                    destination,
                    src_transform=source.transform,
                    src_crs=source.crs or "EPSG:4326",
                    dst_transform=grid["transform"],
                    dst_crs="EPSG:32736",
                    src_nodata=np.nan,
                    dst_nodata=np.nan,
                    resampling=Resampling.bilinear,
                )
                values[:, :, index] = destination
        output[variable] = values
    output["tmean"] = (output.pop("tmax") + output.pop("tmin")) / 2
    return source_years, output


def load_hansen(grid):
    """Return 2004 forest stock and annual loss in hectares per 1-km cell."""
    with rasterio.open(HANSEN_TC) as tree_source, rasterio.open(HANSEN_LOSS) as loss_source:
        tree_cover = tree_source.read(1)
        loss_year = loss_source.read(1)
        valid = (tree_cover <= 100) & (loss_year != 255)
        baseline_forest = valid & (tree_cover >= 30)
        baseline_share = np.zeros(grid["shape"], dtype=np.float32)
        reproject(
            baseline_forest.astype(np.float32),
            baseline_share,
            src_transform=tree_source.transform,
            src_crs=tree_source.crs,
            dst_transform=grid["transform"],
            dst_crs="EPSG:32736",
            src_nodata=None,
            dst_nodata=0,
            resampling=Resampling.average,
        )
        annual_loss = np.empty((*grid["shape"], len(YEARS)), dtype=np.float32)
        for index, year in enumerate(YEARS):
            annual = baseline_forest & (loss_year == year - 2000)
            destination = np.zeros(grid["shape"], dtype=np.float32)
            reproject(
                annual.astype(np.float32),
                destination,
                src_transform=tree_source.transform,
                src_crs=tree_source.crs,
                dst_transform=grid["transform"],
                dst_crs="EPSG:32736",
                src_nodata=None,
                dst_nodata=0,
                resampling=Resampling.average,
            )
            annual_loss[:, :, index] = destination * 100
    stock_2004 = np.maximum(
        baseline_share * 100 - annual_loss[:, :, YEARS <= 2004].sum(axis=2), 0
    )
    return stock_2004, annual_loss


def read_jrc_crop(urls, grid, dtype):
    transform = grid["transform"]
    maxx = transform.c + grid["shape"][1] * transform.a
    miny = transform.f + grid["shape"][0] * transform.e
    bounds = transform_bounds(
        "EPSG:32736", "EPSG:4326", transform.c, miny, maxx, transform.f,
        densify_pts=21,
    )
    sources = [rasterio.open(url) for url in urls]
    try:
        values, source_transform = merge(sources, bounds=bounds, nodata=0, dtype=dtype)
        source_crs = sources[0].crs
    finally:
        for source in sources:
            source.close()
    return values[0], source_transform, source_crs


def load_jrc(grid):
    """Return 2004 TMF stock and annual deforestation in hectares per cell."""
    deforestation, deforestation_transform, deforestation_crs = read_jrc_crop(
        [JRC["def20"], JRC["def30"]], grid, "uint16"
    )
    observed = np.unique(deforestation)
    year_codes = YEARS if 2001 in observed else YEARS - 1989
    annual_loss = np.empty((*grid["shape"], len(YEARS)), dtype=np.float32)
    for index, code in enumerate(year_codes):
        destination = np.zeros(grid["shape"], dtype=np.float32)
        reproject(
            (deforestation == code).astype(np.float32),
            destination,
            src_transform=deforestation_transform,
            src_crs=deforestation_crs,
            dst_transform=grid["transform"],
            dst_crs="EPSG:32736",
            src_nodata=None,
            dst_nodata=0,
            resampling=Resampling.average,
        )
        annual_loss[:, :, index] = destination * 100

    annual_change, stock_transform, stock_crs = read_jrc_crop(
        [JRC["stock20"], JRC["stock30"]], grid, "uint8"
    )
    # JRC annual-state classes 1, 2, and 4 are undisturbed, degraded, or regrowing TMF.
    forest = np.isin(annual_change, [1, 2, 4])
    stock_share = np.zeros(grid["shape"], dtype=np.float32)
    reproject(
        forest.astype(np.float32),
        stock_share,
        src_transform=stock_transform,
        src_crs=stock_crs,
        dst_transform=grid["transform"],
        dst_crs="EPSG:32736",
        src_nodata=None,
        dst_nodata=0,
        resampling=Resampling.average,
    )
    return stock_share * 100, annual_loss


def fill_panel(values, districts):
    values = values.astype(float, copy=True)
    for year_index in range(values.shape[1]):
        column = values[:, year_index]
        for district in np.unique(districts):
            take = districts == district
            observed = take & np.isfinite(column)
            district_mean = np.nanmean(column[observed]) if observed.any() else np.nan
            column[take & ~np.isfinite(column)] = district_mean
        column[~np.isfinite(column)] = np.nanmean(column)
        values[:, year_index] = column
    return values


def standardize(values):
    values = values.astype(float, copy=True)
    values[~np.isfinite(values)] = np.nanmedian(values)
    standard_deviation = np.std(values)
    if standard_deviation == 0:
        return np.zeros_like(values)
    return (values - np.mean(values)) / standard_deviation


def overlap_weights(features, treated, districts, ridge=1e-6):
    """Estimate logit propensity scores and construct overlap weights."""
    district_values = np.unique(districts)
    district_dummies = np.column_stack([
        (districts == value).astype(float) for value in district_values[1:]
    ])
    design = np.column_stack([np.ones(len(treated)), features, district_dummies])
    outcome = treated.astype(float)
    coefficient = np.zeros(design.shape[1])
    penalty = np.eye(design.shape[1]) * ridge
    penalty[0, 0] = 0

    for _ in range(100):
        linear = np.clip(design @ coefficient, -30, 30)
        probability = 1 / (1 + np.exp(-linear))
        variance = np.maximum(probability * (1 - probability), 1e-8)
        score = design.T @ (outcome - probability) - penalty @ coefficient
        information = (design.T * variance) @ design + penalty
        step = np.linalg.solve(information, score)
        coefficient += step
        if np.max(np.abs(step)) < 1e-9:
            break

    probability = 1 / (1 + np.exp(-np.clip(design @ coefficient, -30, 30)))
    weights = np.where(treated, 1 - probability, probability)
    weights /= weights.mean()
    return weights, probability


def residualize_weighted(values, districts, weights):
    """Remove cell and district-by-year fixed effects under fixed cell weights."""
    result = values - values.mean(axis=1, keepdims=True)
    for district in np.unique(districts):
        take = districts == district
        result[take] -= np.average(result[take], axis=0, weights=weights[take])
    return result


def fit_weighted_panel(outcome, regressors, districts, blocks, weights):
    """Weighted FE regression with 20-km spatial-block clustered inference."""
    y = residualize_weighted(outcome, districts, weights)
    x_arrays = [
        residualize_weighted(regressor.astype(float), districts, weights)
        for regressor in regressors
    ]
    x = np.column_stack([regressor.ravel() for regressor in x_arrays])
    y_vector = y.ravel()
    row_weights = np.repeat(weights, outcome.shape[1])
    inverse = np.linalg.pinv(x.T @ (row_weights[:, None] * x))
    beta = inverse @ (x.T @ (row_weights * y_vector))
    residual = (y_vector - x @ beta).reshape(outcome.shape)

    score_cell = np.column_stack([
        weights * (regressor * residual).sum(axis=1) for regressor in x_arrays
    ])
    unique_blocks, block_index = np.unique(blocks, return_inverse=True)
    score_block = np.zeros((len(unique_blocks), len(regressors)))
    np.add.at(score_block, block_index, score_cell)
    correction = len(unique_blocks) / (len(unique_blocks) - 1)
    covariance = inverse @ (score_block.T @ score_block * correction) @ inverse
    standard_error = np.sqrt(np.maximum(np.diag(covariance), 0))
    p_value = np.array([
        math.erfc(abs(value) / math.sqrt(2))
        for value in beta / standard_error
    ])
    return beta, standard_error, p_value, len(unique_blocks), covariance


def chi_square_three_sf(value):
    """Survival function for chi-square(3), the joint test of three leads."""
    root = math.sqrt(value / 2)
    return math.erfc(root) + 2 * root * math.exp(-(root ** 2)) / math.sqrt(math.pi)


def sector_groups():
    """The 12 entrance sectors, the other 32 bordering sectors, and the 9 Gishwati-Mukura sectors.

    Taken from bar_chart_housing.geography() so the definitions match every other figure in the
    project rather than being re-derived here.
    """
    import bar_chart_housing as housing          # never alias to C: shadows patsy C()
    sectors, treated, _excluded, _never = housing.geography()
    gates_plus = set(treated["Gates+"])
    sharing_only = set(treated["Bordering or Gates+"]) - gates_plus
    parks = gpd.read_file(PARKS)
    parks = parks[
        parks.designate.astype(str).str.contains("National Park", case=False, na=False)
    ].to_crs(32736)
    gishwati = parks[
        parks.areaname.astype(str).str.contains("Gishwati|Mukura", case=False, na=False)
    ].geometry.union_all()
    projected = sectors.to_crs(32736)
    gishwati_sectors = set(projected.sid[projected.geometry.distance(gishwati) == 0])
    return gates_plus, sharing_only, gishwati_sectors


def spatial_blocks(x, y):
    width = int(np.ceil((x.max() - x.min()) / BLOCK_METERS)) + 1
    block_x = np.floor((x - x.min()) / BLOCK_METERS).astype(int)
    block_y = np.floor((y - y.min()) / BLOCK_METERS).astype(int)
    return block_y * width + block_x


def estimate_product(product, stock_grid, loss_grid, grid, climate_years,
                     climate, elevation, slope, population, road_km):
    row, column = np.where(grid["valid"])
    all_outcome = loss_grid[row, column, :].astype(float)
    all_stock = stock_grid[row, column].astype(float)
    all_districts = grid["district"][row, column].astype(int)
    all_sectors = grid["sector"][row, column].astype(int)
    all_x = grid["x"][row, column]
    all_y = grid["y"][row, column]

    climate_index = [int(np.where(climate_years == year)[0][0]) for year in YEARS]
    all_rain = fill_panel(climate["ppt"][row, column, :][:, climate_index], all_districts)
    all_temperature = fill_panel(
        climate["tmean"][row, column, :][:, climate_index], all_districts
    )
    all_pdsi = fill_panel(climate["pdsi"][row, column, :][:, climate_index], all_districts)
    baseline_rain = np.nanmean(climate["ppt"][row, column, :][:, :10], axis=1)

    pre = YEARS < 2005
    centered_pre_year = YEARS[pre] - YEARS[pre].mean()
    pre_mean = all_outcome[:, pre].mean(axis=1)
    pre_slope = (
        all_outcome[:, pre] @ centered_pre_year / np.sum(centered_pre_year ** 2)
    )
    raw_features = [
        all_stock / 100,
        elevation[row, column],
        slope[row, column],
        np.log1p(road_km[row, column]),
        np.log1p(population[row, column]),
        baseline_rain,
        pre_mean,
        pre_slope,
    ]
    all_features = np.column_stack([standardize(value) for value in raw_features])

    park = {
        name: grid["zones"]["Park only"][name][row, column]
        for name in PARK_NAMES
    }
    outer = {
        name: grid["zones"]["Park + 5 km"][name][row, column]
        for name in PARK_NAMES
    }
    active_park = np.logical_or.reduce([park[name] for name in ACTIVE_PARKS])
    any_park = np.logical_or.reduce(list(park.values()))
    active_outer = np.logical_or.reduce([outer[name] for name in ACTIVE_PARKS])
    gishwati_mukura = park["Gishwati-Mukura"]
    ring = active_outer & ~any_park & ~gishwati_mukura
    far = ~active_outer & ~any_park & ~gishwati_mukura
    # The two sector-based panels. Cells are assigned by the sector they fall in, because revenue
    # sharing is allocated to sectors, not to distance bands. Their control group is `far` less the
    # sectors bordering Gishwati-Mukura: that park was gazetted in 2015-16, so those sectors are
    # treated from then on and cannot stay in the comparison group.
    gates_plus, sharing_only, gishwati_sectors = sector_groups()
    in_gates = np.isin(all_sectors, list(gates_plus))
    in_sharing = np.isin(all_sectors, list(sharing_only))
    far_clean = far & ~np.isin(all_sectors, list(gishwati_sectors))
    eligible = np.isfinite(all_stock) & (all_stock >= BASELINE_MIN_HA)
    comparison_zones = {
        "Park vs all non-park": (active_park, ~any_park & ~gishwati_mukura),
        "Park + 5 km vs beyond 5 km": (active_outer & ~gishwati_mukura, far),
        "0-5 km ring vs beyond 5 km": (ring, far),
        "Gates+ sectors vs beyond 5 km": (in_gates & ~any_park, far_clean),
        "Revenue sharing only vs beyond 5 km": (in_sharing & ~any_park, far_clean),
    }

    event_years = YEARS[YEARS != BASE_YEAR]
    results = []
    diagnostics = []

    for comparison in COMPARISONS:
        treated_zone, control_zone = comparison_zones[comparison]
        candidate = eligible & (treated_zone | control_zone)
        candidate_districts = all_districts[candidate]
        candidate_treated = treated_zone[candidate]
        valid_districts = [
            district for district in np.unique(candidate_districts)
            if np.any(candidate_treated[candidate_districts == district])
            and np.any(~candidate_treated[candidate_districts == district])
        ]
        candidate &= np.isin(all_districts, valid_districts)

        outcome = all_outcome[candidate]
        districts = all_districts[candidate]
        treated = treated_zone[candidate]
        features = all_features[candidate]
        rain = all_rain[candidate]
        temperature = all_temperature[candidate]
        pdsi = all_pdsi[candidate]
        weights, propensity = overlap_weights(features, treated, districts)
        blocks = spatial_blocks(all_x[candidate], all_y[candidate])

        event_regressors = [
            treated[:, None] * (YEARS[None, :] == year)
            for year in event_years
        ]
        beta, standard_error, p_value, n_blocks, covariance = fit_weighted_panel(
            outcome,
            event_regressors + [rain, temperature, pdsi],
            districts,
            blocks,
            weights,
        )

        # Pooled post-2005 coefficient, same weights, same controls, same clustering: the event
        # regressors are replaced by a single treated-by-post indicator.
        pooled_beta, pooled_se, pooled_p, _, _ = fit_weighted_panel(
            outcome,
            [treated[:, None] * (YEARS[None, :] >= 2005), rain, temperature, pdsi],
            districts,
            blocks,
            weights,
        )

        lead_indices = np.where(event_years < BASE_YEAR)[0]
        lead_covariance = covariance[np.ix_(lead_indices, lead_indices)]
        lead_wald = (
            beta[lead_indices]
            @ np.linalg.pinv(lead_covariance)
            @ beta[lead_indices]
        )
        pretrend_p = chi_square_three_sf(lead_wald)

        treated_weights = weights[treated]
        control_weights = weights[~treated]
        treated_ess = treated_weights.sum() ** 2 / np.sum(treated_weights ** 2)
        control_ess = control_weights.sum() ** 2 / np.sum(control_weights ** 2)
        weighted_imbalance = np.abs(
            np.average(features[treated], axis=0, weights=treated_weights)
            - np.average(features[~treated], axis=0, weights=control_weights)
        )
        diagnostics.append({
            "product": product,
            "comparison": comparison,
            "treated_cells": int(treated.sum()),
            "control_cells": int((~treated).sum()),
            "treated_effective_n": treated_ess,
            "control_effective_n": control_ess,
            "spatial_blocks": n_blocks,
            "mean_abs_weighted_imbalance": weighted_imbalance.mean(),
            "max_abs_weighted_imbalance": weighted_imbalance.max(),
            "propensity_p01": np.quantile(propensity, 0.01),
            "propensity_p99": np.quantile(propensity, 0.99),
            "pretrend_joint_p": pretrend_p,
            "pooled_post2005": pooled_beta[0],
            "pooled_post2005_se": pooled_se[0],
            "pooled_post2005_p": pooled_p[0],
        })
        for index, year in enumerate(event_years):
            results.append({
                "product": product,
                "comparison": comparison,
                "year": int(year),
                "event_time": int(year - 2005),
                "coefficient": beta[index],
                "standard_error": standard_error[index],
                "p_value": p_value[index],
                "treated_cells": int(treated.sum()),
                "control_cells": int((~treated).sum()),
                "treated_effective_n": treated_ess,
                "control_effective_n": control_ess,
                "spatial_blocks": n_blocks,
            })

    return results, diagnostics


def figure_note():
    return textwrap.fill(
        "Points are year-specific treated-control differences in annual forest loss relative to "
        "2004. The unit is a fixed 1-km cell and the outcome is hectares lost. Regressions cover "
        "2001-2024 and include cell and district-by-year fixed effects plus annual rainfall, "
        "temperature, and PDSI. Overlap weights are estimated separately for each panel from 2004 "
        "forest stock, elevation, slope, distance to primary or trunk roads, 2001 gridded population "
        "density, baseline precipitation, and the 2001-2004 level and trend of forest loss. Bars are "
        "90% confidence intervals using 20-by-20-km spatial-block clustered standard errors. Panels "
        "pool Volcanoes, Nyungwe, and Akagera; Gishwati-Mukura and city sectors are excluded. Each "
        "product uses cells containing at least 10 hectares of its forest measure in 2004. The first "
        "three panels are geographic; the last two split the revenue-sharing zone by whether the "
        "sector also holds a park entrance, so that tourism can be separated from the transfer, and "
        "compare each against the same far cells less the sectors bordering Gishwati-Mukura, which "
        "entered the scheme only in 2015-16. Pre-trend "
        "p-values jointly test the 2001-2003 coefficients. Sources: Hansen Global Forest Change 2024 "
        "v1.12, JRC Tropical Moist Forest 2025, NISR, OpenStreetMap, and TerraClimate.",
        width=225,
    )


def plot_results(results, diagnostics):
    plot_data = results.copy()
    omitted = diagnostics[["product", "comparison"]].copy()
    omitted["year"] = BASE_YEAR
    omitted["coefficient"] = 0.0
    omitted["standard_error"] = 0.0
    plot_data = pd.concat(
        [plot_data, omitted[plot_data.columns.intersection(omitted.columns)]],
        ignore_index=True,
        sort=False,
    )
    plot_data["lo90"] = plot_data.coefficient - CI_Z * plot_data.standard_error
    plot_data["hi90"] = plot_data.coefficient + CI_Z * plot_data.standard_error

    colors = {"Hansen": "#8C8C8C", "JRC": "#2E75A8"}
    fig, axes = plt.subplots(
        2, len(COMPARISONS), figsize=(3.05 * len(COMPARISONS) + 2.0, 8.8),
        sharex=True, sharey="row"
    )
    for row_index, product in enumerate(("Hansen", "JRC")):
        for column_index, comparison in enumerate(COMPARISONS):
            axis = axes[row_index, column_index]
            panel = plot_data[
                (plot_data["product"] == product)
                & (plot_data["comparison"] == comparison)
            ].sort_values("year")
            axis.axvspan(2000.5, 2004.5, color="#F2F2F2", zorder=0)
            axis.axhline(0, color="#333333", linewidth=0.8, zorder=1)
            axis.axvline(2005, color="#777777", linewidth=0.8, linestyle="--", zorder=1)
            axis.plot(
                panel.year,
                panel.coefficient,
                color=colors[product],
                linewidth=1.15,
                zorder=2,
            )
            axis.errorbar(
                panel.year,
                panel.coefficient,
                yerr=CI_Z * panel.standard_error,
                fmt="o",
                markersize=3.2,
                color=colors[product],
                ecolor=colors[product],
                elinewidth=0.9,
                capsize=1.8,
                zorder=3,
            )
            pretrend = diagnostics[
                (diagnostics["product"] == product)
                & (diagnostics["comparison"] == comparison)
            ].iloc[0]
            axis.text(
                0.02,
                0.96,
                f"Pre-trend p = {pretrend.pretrend_joint_p:.3f}",
                transform=axis.transAxes,
                va="top",
                ha="left",
                fontsize=8,
                color="#555555",
            )
            axis.grid(axis="y", color="#DDDDDD", linewidth=0.35)
            axis.set_axisbelow(True)
            axis.spines["top"].set_visible(False)
            axis.spines["right"].set_visible(False)
            axis.set_xticks([2001, 2005, 2010, 2015, 2020, 2024])
            axis.tick_params(labelsize=8.5)
            if row_index == 0:
                axis.set_title(comparison, fontsize=10, pad=9)
            if column_index == 0:
                axis.set_ylabel(
                    f"{product}\nEffect on annual forest loss\n(hectares per 1-km cell)",
                    fontsize=9,
                )
            if row_index == 1:
                axis.set_xlabel("Year", fontsize=9)

    fig.suptitle(
        "Forest loss around national parks: annual event-study estimates",
        fontsize=12,
        y=0.985,
    )
    fig.text(
        0.012,
        0.012,
        figure_note(),
        fontsize=6.55,
        va="bottom",
        ha="left",
        color="#333333",
        linespacing=1.4,
    )
    fig.tight_layout(rect=[0.01, 0.185, 0.995, 0.96], h_pad=1.2, w_pad=1.0)
    FIGURE.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURE, bbox_inches="tight")
    plt.close(fig)


def main():
    os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
    grid = make_grid()
    elevation, slope, population, road_km = static_controls(grid)
    climate_years, climate = annual_climate(grid)

    rows = []
    checks = []
    hansen_stock, hansen_loss = load_hansen(grid)
    product_rows, product_checks = estimate_product(
        "Hansen", hansen_stock, hansen_loss, grid, climate_years, climate,
        elevation, slope, population, road_km,
    )
    rows.extend(product_rows)
    checks.extend(product_checks)

    jrc_stock, jrc_loss = load_jrc(grid)
    product_rows, product_checks = estimate_product(
        "JRC", jrc_stock, jrc_loss, grid, climate_years, climate,
        elevation, slope, population, road_km,
    )
    rows.extend(product_rows)
    checks.extend(product_checks)

    results = pd.DataFrame(rows)
    diagnostics = pd.DataFrame(checks)
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(RESULTS, index=False)
    diagnostics.to_csv(DIAGNOSTICS, index=False)
    plot_results(results, diagnostics)

    print(diagnostics.to_string(index=False, float_format=lambda value: f"{value:.4f}"))
    print(f"Written: {RESULTS}")
    print(f"Written: {DIAGNOSTICS}")
    print(f"Written: {FIGURE}")


if __name__ == "__main__":
    main()
