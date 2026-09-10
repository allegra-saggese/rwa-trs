"""JRC forest-loss DiD coefficient plot, excluding Akagera.

The unit is a fixed 1-km grid cell observed annually from 1995 through
2025. Treatment covers each national park and its 10-km buffer. Volcanoes
and Nyungwe turn on in 2005; Gishwati--Mukura turns on in 2015. Akagera
and its 10-km buffer are omitted from the estimation sample in every year.

The script writes a transparent regression-results CSV alongside the
coefficient plot. JRC's official Tropical Moist Forest DeforestationYear
layer is read from the Source Cooperative COG mirror.
"""

from __future__ import annotations

import argparse
import sys
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
from scipy import stats


REPO = Path("/Users/matteo/Documents/GitHub/rwa-trs")
FIGURE_CODE = REPO / "output/figures"
if str(FIGURE_CODE) not in sys.path:
    sys.path.insert(0, str(FIGURE_CODE))

import bar_chart_housing as B


DB = Path("/Users/matteo/Library/CloudStorage/Dropbox/1-Ongoing Projects/Rwanda - TRS")
PARK_FILE = DB / "data/geo-data/protected-areas/rwanda_protected_areas_geodata_rw.gpkg"
JRC_COGS = (
    "https://data.source.coop/epoch/jrc-tmf/v1_2025/N0_E20/DeforestationYear.tif",
    "https://data.source.coop/epoch/jrc-tmf/v1_2025/N0_E30/DeforestationYear.tif",
)
YEARS = np.arange(1995, 2026)
BUFFER_METERS = 10_000
BLOCK_METERS = 20_000
CI_Z = 1.645


def make_grid():
    """Construct the fixed Rwanda grid and masks used by the analysis."""
    sectors, _, exclusions, _ = B.geography()
    sectors = sectors.to_crs(32736)
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
        [(country, 1)], out_shape=shape, transform=transform,
        fill=0, all_touched=False, dtype="uint8"
    ).astype(bool)

    city_sids = exclusions["Kigali all + cities"]
    city_geom = sectors.loc[sectors.sid.isin(city_sids), "geometry"].union_all()
    city_mask = rasterize(
        [(city_geom, 1)], out_shape=shape, transform=transform,
        fill=0, all_touched=False, dtype="uint8"
    ).astype(bool)

    parks = gpd.read_file(PARK_FILE)
    parks = parks[
        parks.designate.astype(str).str.contains("National Park", case=False, na=False)
    ].to_crs(32736)

    def park_geometry(pattern):
        subset = parks[
            parks.areaname.astype(str).str.contains(pattern, case=False, na=False)
        ]
        if subset.empty:
            raise ValueError(f"No national-park polygon matches {pattern!r}")
        return subset.geometry.union_all()

    park_geometries = {
        "Volcanoes": park_geometry("Volcanoes"),
        "Nyungwe": park_geometry("Nyungwe"),
        "Gishwati-Mukura": park_geometry("Gishwati|Mukura"),
        "Akagera": park_geometry("Akagera"),
    }
    zones = {
        name: rasterize(
            [(geom.buffer(BUFFER_METERS), 1)], out_shape=shape,
            transform=transform, fill=0, all_touched=False, dtype="uint8"
        ).astype(bool)
        for name, geom in park_geometries.items()
    }

    sample_mask = country_mask & ~city_mask & ~zones["Akagera"]
    rows, cols = np.where(sample_mask)
    x = minx + (cols + 0.5) * 1000
    y = maxy - (rows + 0.5) * 1000
    zone_vectors = {name: mask[rows, cols] for name, mask in zones.items()}
    return transform, shape, rows, cols, x, y, zone_vectors, int(country_mask.sum()), int(city_mask.sum())


def load_jrc(transform, shape, rows, cols):
    """Aggregate annual JRC deforestation to hectares in each 1-km cell."""
    minx = transform.c
    maxy = transform.f
    maxx = minx + shape[1] * transform.a
    miny = maxy + shape[0] * transform.e
    bounds_wgs84 = transform_bounds(
        "EPSG:32736", "EPSG:4326", minx, miny, maxx, maxy, densify_pts=21
    )

    sources = [rasterio.open(url) for url in JRC_COGS]
    try:
        source, source_transform = merge(
            sources, bounds=bounds_wgs84, nodata=0, dtype="uint16"
        )
        source = source[0]
        source_crs = sources[0].crs
    finally:
        for dataset in sources:
            dataset.close()

    observed = np.unique(source)
    year_codes = YEARS if 1995 in observed else YEARS - 1989
    outcome = np.empty((len(rows), len(YEARS)), dtype=np.float32)
    for j, code in enumerate(year_codes):
        destination = np.zeros(shape, dtype=np.float32)
        reproject(
            source=(source == code).astype(np.float32),
            destination=destination,
            src_transform=source_transform,
            src_crs=source_crs,
            dst_transform=transform,
            dst_crs="EPSG:32736",
            src_nodata=None,
            dst_nodata=0,
            resampling=Resampling.average,
        )
        # A 1-km cell contains 100 hectares, so forest-loss share x 100 is hectares.
        outcome[:, j] = destination[rows, cols] * 100
    return outcome


def within(array):
    """Remove grid-cell and year means from a balanced panel."""
    return (
        array
        - array.mean(axis=1, keepdims=True)
        - array.mean(axis=0, keepdims=True)
        + array.mean()
    )


def fit_twfe(outcome, treatments, block_ids):
    """Fit TWFE and return 20-km spatial-block clustered inference."""
    y = within(outcome)
    x_arrays = [within(treatment.astype(float)) for treatment in treatments]
    x = np.column_stack([array.ravel() for array in x_arrays])
    y_vector = y.ravel()
    xtx_inv = np.linalg.inv(x.T @ x)
    beta = xtx_inv @ (x.T @ y_vector)
    residual = (y_vector - x @ beta).reshape(outcome.shape)

    # Sum the score over years within cells, then over cells within fixed 20-km blocks.
    score_by_cell = np.column_stack(
        [(x_arrays[k] * residual).sum(axis=1) for k in range(len(x_arrays))]
    )
    _, inverse = np.unique(block_ids, return_inverse=True)
    score_by_block = np.zeros((inverse.max() + 1, len(x_arrays)))
    np.add.at(score_by_block, inverse, score_by_cell)
    meat = score_by_block.T @ score_by_block
    groups = score_by_block.shape[0]
    covariance = xtx_inv @ meat @ xtx_inv * groups / (groups - 1)
    se = np.sqrt(np.diag(covariance))
    p = 2 * stats.t.sf(np.abs(beta / se), df=groups - 1)
    return beta, se, p, groups


def estimate(outcome, years, x_coord, y_coord, zones):
    post_2005 = years >= 2005
    post_2015 = years >= 2015
    treatment = {
        "Volcanoes": zones["Volcanoes"][:, None] & post_2005[None, :],
        "Nyungwe": zones["Nyungwe"][:, None] & post_2005[None, :],
        "Gishwati-Mukura": zones["Gishwati-Mukura"][:, None] & post_2015[None, :],
    }
    pooled = treatment["Volcanoes"] | treatment["Nyungwe"] | treatment["Gishwati-Mukura"]
    block_x = np.floor((x_coord - x_coord.min()) / BLOCK_METERS).astype(int)
    block_y = np.floor((y_coord - y_coord.min()) / BLOCK_METERS).astype(int)
    block_ids = block_y * (block_x.max() + 1) + block_x

    pooled_beta, pooled_se, pooled_p, groups = fit_twfe(outcome, [pooled], block_ids)
    names = ["Volcanoes", "Nyungwe", "Gishwati-Mukura"]
    park_beta, park_se, park_p, park_groups = fit_twfe(
        outcome, [treatment[name] for name in names], block_ids
    )
    assert groups == park_groups

    rows = [{
        "estimate": "Pooled forest parks",
        "coefficient": pooled_beta[0],
        "standard_error": pooled_se[0],
        "p_value": pooled_p[0],
        "cells": outcome.shape[0],
        "years": outcome.shape[1],
        "spatial_blocks": groups,
    }]
    rows.extend({
        "estimate": name,
        "coefficient": beta,
        "standard_error": se,
        "p_value": p_value,
        "cells": outcome.shape[0],
        "years": outcome.shape[1],
        "spatial_blocks": groups,
    } for name, beta, se, p_value in zip(names, park_beta, park_se, park_p))
    results = pd.DataFrame(rows)
    results["lo90"] = results.coefficient - CI_Z * results.standard_error
    results["hi90"] = results.coefficient + CI_Z * results.standard_error
    return results


def draw(results, output, zone_counts, country_cells, city_cells):
    labels = results.estimate.tolist()
    y = np.arange(len(labels))[::-1]
    colors = ["#2E75A8", "#8C8C8C", "#8C8C8C", "#8C8C8C"]
    markers = ["D", "o", "o", "o"]

    fig, ax = plt.subplots(figsize=(9.4, 5.8))
    for row_y, (_, row), color, marker in zip(y, results.iterrows(), colors, markers):
        ax.errorbar(
            row.coefficient,
            row_y,
            xerr=[[row.coefficient - row.lo90], [row.hi90 - row.coefficient]],
            fmt=marker,
            ms=7 if marker == "D" else 6,
            color=color,
            ecolor=color,
            elinewidth=1.6,
            capsize=3,
        )
    ax.axvline(0, color="#333333", lw=0.9)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=10)
    ax.set_xlabel("DiD effect on annual deforestation (hectares per 1-km cell)", fontsize=10)
    ax.set_title("JRC deforestation: national parks and 10-km buffers", fontsize=12, pad=10)
    ax.grid(axis="x", lw=0.35, color="#DDDDDD")
    ax.set_axisbelow(True)
    ax.tick_params(axis="x", labelsize=9)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)

    counts = ", ".join(f"{name} {count:,}" for name, count in zone_counts.items())
    note = (
        "Each point is a two-way fixed-effects difference-in-differences coefficient with fixed "
        "1-km-cell and year effects. The pooled specification turns on cells in Volcanoes and "
        "Nyungwe National Parks and their 10-km buffers in 2005, and cells in Gishwati-Mukura "
        "National Park and its 10-km buffer in 2015. Park-specific estimates come from one joint "
        "regression. Akagera and its 10-km buffer are excluded in all years. The comparison group "
        "is all other non-city cells in Rwanda; the city exclusion matches the housing analysis "
        "(the City of Kigali and the four largest cities in 2002). Bars are 90% confidence "
        "intervals with errors clustered by fixed 20-by-20-km spatial block. Positive coefficients "
        "mean more deforestation. Sample: 1995-2025. "
        f"Treatment-zone cells in the estimation sample: {counts}. Rwanda contains {country_cells:,} "
        f"grid cells; {city_cells:,} fall in the excluded city sectors. Source: JRC Tropical "
        "Moist Forest, DeforestationYear, version 1 (2025)."
    )
    fig.text(
        0.02, 0.015, textwrap.fill(note, width=158), fontsize=7.1,
        va="bottom", ha="left", color="#333333", linespacing=1.45
    )
    fig.tight_layout(rect=[0.02, 0.24, 0.99, 0.98])
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, bbox_inches="tight")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--figure",
        type=Path,
        default=DB / "output/figures/coefplot_jrc_forest.pdf",
    )
    parser.add_argument(
        "--results",
        type=Path,
        default=DB / "data/Publicly-Available-NISR/Analysis/reg_jrc_forest_did.csv",
    )
    args = parser.parse_args()

    transform, shape, rows, cols, x, y, zones, country_cells, city_cells = make_grid()
    outcome = load_jrc(transform, shape, rows, cols)
    results = estimate(outcome, YEARS, x, y, zones)
    args.results.parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(args.results, index=False)
    zone_counts = {
        name: int(zones[name].sum())
        for name in ("Volcanoes", "Nyungwe", "Gishwati-Mukura")
    }
    draw(results, args.figure, zone_counts, country_cells, city_cells)
    print(results.to_string(index=False, float_format=lambda value: f"{value:.6f}"))
    print(f"\nWritten: {args.figure}")
    print(f"Written: {args.results}")


if __name__ == "__main__":
    main()
