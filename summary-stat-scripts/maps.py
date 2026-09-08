"""
maps.py — spatial visualisation for the Rwanda project.

Reads from data/processed/ and writes to output/maps/. Built around one
reusable `choropleth()` so every map in the paper shares projection,
classification, and legend conventions.

Usage
-----
    python maps.py --all
    python maps.py --only rainfall_mean drought_rate
    python maps.py --only rainfall_facets --format pdf
    python maps.py --list-vars                 # what can be mapped

Projection
----------
Everything is drawn in UTM 35S (EPSG:32735), not lon/lat. Plotting geographic
degrees stretches Rwanda horizontally by ~cos(2 deg S) and, more importantly,
makes any area or distance read off the map wrong. GADM ships EPSG:4326, so
each map reprojects on the way in.
"""

from __future__ import annotations

import argparse
import sys
import textwrap
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import paths as P

import matplotlib as mpl
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO = P.REPO
PROC = P.PROC
DROPBOX = P.DROPBOX
OUT = P.OUT
MAPS = P.MAPS

# Rwanda falls in UTM zone 35S. Metres, so scale bars and areas are honest.
CRS_PROJ = 32735
CRS_GEO = 4326

mpl.rcParams.update({
    "figure.dpi": 150,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "font.family": "serif",
    "font.size": 9,
    "axes.titlesize": 10,
})

FMT = "png"


def _log(msg: str) -> None:
    print(f"[maps] {msg}", flush=True)


def save_map(fig, name: str) -> None:
    MAPS.mkdir(parents=True, exist_ok=True)
    path = MAPS / f"{name}.{FMT}"
    fig.savefig(path)
    plt.close(fig)
    _log(f"  -> maps/{path.name}")


# --------------------------------------------------------------------------
# Data access
# --------------------------------------------------------------------------

def load_districts():
    """District polygons, reprojected to UTM 35S."""
    import geopandas as gpd

    fp = PROC / "districts.gpkg"
    if not fp.exists():
        raise FileNotFoundError(
            "interim-processing/processed/districts.gpkg missing - run: "
            "python data-build-scripts/extract.py --sources boundaries")
    return gpd.read_file(fp, layer="districts").to_crs(CRS_PROJ)


def load_panel() -> pd.DataFrame | None:
    fp = PROC / "district_panel.csv"
    if not fp.exists():
        _log("  ! district_panel.csv missing - run extract.py first")
        return None
    return pd.read_csv(fp)


def district_values(var: str, year: int | None = None, agg: str = "mean"):
    """Attach one district-level number to the polygons, ready to map.

    `year` selects a single year; otherwise values are aggregated over the whole
    panel with `agg`. Returns a GeoDataFrame with a `value` column.
    """
    gdf = load_districts()
    panel = load_panel()
    if panel is None:
        return None
    if var not in panel.columns:
        _log(f"  ! '{var}' not in panel; try --list-vars")
        return None

    if year is not None:
        sub = panel[panel["year"] == year]
        if sub.empty:
            _log(f"  ! no rows for year {year}")
            return None
        vals = sub.set_index("district_id")[var]
    else:
        vals = panel.groupby("district_id")[var].agg(agg)

    gdf["value"] = gdf["district_id"].map(vals)
    return gdf


# --------------------------------------------------------------------------
# Core map primitive
# --------------------------------------------------------------------------

def choropleth(gdf, column="value", *, title="", legend_label="", cmap="YlGnBu",
               scheme=None, k=5, ax=None, labels=False, vcenter=None,
               vmin=None, vmax=None, missing_label="no data"):
    """Draw one district choropleth with the project's shared conventions.

    Parameters that matter for interpretation:

    scheme      classification for the colour bins. None gives a continuous
                colour ramp. 'quantiles' equalises the count per bin (good for
                skewed variables); 'natural_breaks' (Jenks) minimises within-bin
                variance and is usually the honest default for a spatial
                variable with real clusters; 'equal_interval' is easiest to read
                but hides clustering.
    vcenter     anchors a diverging colormap at a meaningful midpoint, normally
                0 for anomalies. Without it, matplotlib centres on the data
                range and a colour ramp that reads as 'wet vs dry' silently
                shifts its neutral point between maps.
    """
    own_fig = ax is None
    if own_fig:
        fig, ax = plt.subplots(figsize=(6.2, 5.6))
    else:
        fig = ax.figure

    norm = None
    if vcenter is not None and scheme is None:
        lim = float(np.nanmax(np.abs(gdf[column] - vcenter)))
        norm = mpl.colors.TwoSlopeNorm(vmin=vcenter - lim, vcenter=vcenter,
                                       vmax=vcenter + lim)

    plot_kw = dict(column=column, cmap=cmap, ax=ax,
                   edgecolor="white", linewidth=0.5,
                   missing_kwds=dict(color="0.9", edgecolor="white",
                                     hatch="///", label=missing_label))
    if scheme:
        # Placed outside the axes: Rwanda's outline fills nearly its whole
        # bounding box, so any in-axes corner overlaps a district.
        plot_kw.update(scheme=scheme, k=k,
                       legend=True,
                       legend_kwds=dict(loc="center left",
                                        bbox_to_anchor=(1.01, 0.5), fontsize=7,
                                        title=legend_label, title_fontsize=7.5,
                                        frameon=False))
    else:
        plot_kw.update(legend=True, norm=norm,
                       legend_kwds=dict(label=legend_label, shrink=0.6,
                                        fraction=0.04, pad=0.02))
        if norm is None:
            plot_kw.update(vmin=vmin, vmax=vmax)

    gdf.plot(**plot_kw)

    # Province outlines on top, so the administrative structure stays readable
    # even where adjacent districts take near-identical colours.
    gdf.dissolve(by="province").boundary.plot(ax=ax, color="0.25", linewidth=0.9)

    if labels:
        for r in gdf.itertuples():
            c = r.geometry.representative_point()  # guaranteed inside the polygon
            ax.annotate(r.district, (c.x, c.y), ha="center", va="center",
                        fontsize=5.5, color="0.15",
                        path_effects=[pe.withStroke(
                            linewidth=1.6, foreground="white")])

    ax.set_title(title, fontsize=10)
    ax.set_axis_off()
    ax.set_aspect("equal")
    _add_scalebar(ax, gdf)
    return fig, ax


def _add_scalebar(ax, gdf, length_km: int = 25) -> None:
    """Simple metric scale bar. Valid because the CRS is in metres."""
    xmin, ymin, xmax, ymax = gdf.total_bounds
    # Top-left: the northwest corner of the bounding box is the one area the
    # country outline does not reach.
    x0 = xmin + 0.02 * (xmax - xmin)
    y0 = ymax - 0.04 * (ymax - ymin)
    ax.plot([x0, x0 + length_km * 1000], [y0, y0], color="0.15", lw=2,
            solid_capstyle="butt")
    ax.text(x0 + length_km * 500, y0 + 0.015 * (ymax - ymin), f"{length_km} km",
            ha="center", fontsize=6.5, color="0.15")


# --------------------------------------------------------------------------
# Maps
# --------------------------------------------------------------------------

def map_districts_reference() -> None:
    """Labelled reference map — provinces coloured, districts named."""
    gdf = load_districts()
    colors = {"Kigali City": "#1b4965", "North": "#5fa8d3", "South": "#c98b3a",
              "East": "#8b5a3c", "West": "#4a7c59"}

    fig, ax = plt.subplots(figsize=(6.8, 6.0))
    for prov, g in gdf.groupby("province"):
        g.plot(ax=ax, color=colors.get(prov, "0.6"), edgecolor="white",
               linewidth=0.6, alpha=0.85, label=prov)

    gdf.dissolve(by="province").boundary.plot(ax=ax, color="0.2", linewidth=1.0)

    for r in gdf.itertuples():
        c = r.geometry.representative_point()
        ax.annotate(r.district, (c.x, c.y), ha="center", va="center",
                    fontsize=6, color="0.1",
                    path_effects=[pe.withStroke(
                        linewidth=1.8, foreground="white")])

    ax.legend(fontsize=7.5, loc="center left", bbox_to_anchor=(1.01, 0.5),
              frameon=False, title="Province", title_fontsize=8)
    ax.set_title("Rwanda: 30 districts, 5 provinces (GADM 4.1)")
    ax.set_axis_off()
    ax.set_aspect("equal")
    _add_scalebar(ax, gdf)
    save_map(fig, "districts_reference")


def map_rainfall_mean() -> None:
    """Mean annual rainfall — the core spatial gradient of the project."""
    gdf = district_values("rain_mm", agg="mean")
    if gdf is None:
        return
    fig, _ = choropleth(
        gdf, title="Mean annual rainfall, CHIRPS",
        legend_label="mm/year", cmap="YlGnBu",
        scheme="natural_breaks", k=5, labels=True)
    save_map(fig, "rainfall_mean")


def map_rainfall_variability() -> None:
    """Coefficient of variation — where rainfall is least predictable.

    Distinct from the level: a district can be wet on average and still highly
    variable, which is what matters for agricultural risk.
    """
    panel = load_panel()
    if panel is None:
        return
    cv = (panel.groupby("district_id")["rain_mm"]
          .agg(lambda s: s.std() / s.mean() if s.mean() else np.nan))
    gdf = load_districts()
    gdf["value"] = gdf["district_id"].map(cv)

    fig, _ = choropleth(
        gdf, title="Rainfall variability (CV of annual totals)",
        legend_label="SD / mean", cmap="OrRd",
        scheme="natural_breaks", k=5, labels=True)
    save_map(fig, "rainfall_variability")


def map_drought_rate() -> None:
    """Share of years classified as a dry shock (z < -1)."""
    panel = load_panel()
    if panel is None:
        return
    if panel["year"].nunique() < 5:
        _log("  ! fewer than 5 years; drought rate not meaningful, skipping")
        return

    rate = panel.groupby("district_id")["drought"].mean()
    gdf = load_districts()
    gdf["value"] = gdf["district_id"].map(rate)

    fig, _ = choropleth(
        gdf, title="Share of years with a dry anomaly (z < -1)",
        legend_label="share of years", cmap="YlOrBr",
        scheme="quantiles", k=4, labels=True)
    save_map(fig, "drought_rate")


def map_rainfall_facets(years: list[int] | None = None) -> None:
    """Small-multiple anomaly maps — one panel per year, shared colour scale.

    The shared, zero-centred scale is the point: panels are only comparable if
    a given colour means the same anomaly in every one of them.
    """
    panel = load_panel()
    if panel is None:
        return

    years = years or sorted(panel["year"].unique())[-9:]
    years = [y for y in years if y in set(panel["year"])]
    if not years:
        return

    gdf = load_districts()
    vals = panel[panel["year"].isin(years)]["rain_z"]
    lim = float(np.nanmax(np.abs(vals))) if vals.notna().any() else 1.0
    norm = mpl.colors.TwoSlopeNorm(vmin=-lim, vcenter=0, vmax=lim)

    ncol = 3
    nrow = int(np.ceil(len(years) / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(3.0 * ncol, 2.9 * nrow), squeeze=False)

    for ax, yr in zip(axes.flat, years):
        g = gdf.copy()
        g["value"] = g["district_id"].map(
            panel[panel["year"] == yr].set_index("district_id")["rain_z"])
        g.plot(column="value", cmap="RdBu", norm=norm, ax=ax,
               edgecolor="white", linewidth=0.3,
               missing_kwds=dict(color="0.9"))
        g.dissolve(by="province").boundary.plot(ax=ax, color="0.3", linewidth=0.5)
        ax.set_title(str(yr), fontsize=9)
        ax.set_axis_off()
        ax.set_aspect("equal")

    for ax in axes.flat[len(years):]:
        ax.axis("off")

    sm = mpl.cm.ScalarMappable(cmap="RdBu", norm=norm)
    cb = fig.colorbar(sm, ax=axes, fraction=0.025, pad=0.02)
    cb.set_label("Rainfall anomaly (SD from district mean)", fontsize=8)
    cb.ax.tick_params(labelsize=7)

    fig.suptitle("Annual rainfall anomalies by district", fontsize=11)
    save_map(fig, "rainfall_facets")


def map_dhs_clusters() -> None:
    """DHS cluster locations over districts, with displacement buffers.

    Each cluster is drawn as its displacement circle rather than a point,
    because the published coordinate is deliberately offset (up to 2 km urban,
    5 km rural). Anything joined at the point alone is measured with error whose
    size this map makes visible.
    """
    import geopandas as gpd

    fp = PROC / "dhs_clusters.gpkg"
    if not fp.exists():
        _log("  ! dhs_clusters.gpkg missing - place DHS GPS shapefile in "
             "interim-processing/raw/dhs/ and run: "
             "python data-build-scripts/extract.py --sources dhs_gps; skipping")
        return

    pts = gpd.read_file(fp, layer="clusters").to_crs(CRS_PROJ)
    gdf = load_districts()

    fig, ax = plt.subplots(figsize=(6.8, 6.0))
    gdf.plot(ax=ax, color="0.94", edgecolor="white", linewidth=0.6)
    gdf.dissolve(by="province").boundary.plot(ax=ax, color="0.3", linewidth=0.9)

    if "displacement_km" in pts.columns:
        buf = pts.copy()
        buf["geometry"] = buf.geometry.buffer(buf["displacement_km"] * 1000)
        buf.plot(ax=ax, color="#1b4965", alpha=0.12, edgecolor="none")

    urban = pts.get("URBAN_RURA", pd.Series(index=pts.index, dtype=object))
    colors = np.where(urban.astype(str).str.upper().str[0] == "U", "#c1121f", "#1b4965")
    ax.scatter(pts.geometry.x, pts.geometry.y, s=5, c=colors, zorder=3, linewidths=0)

    handles = [plt.Line2D([], [], marker="o", ls="", ms=4, color="#c1121f", label="Urban"),
               plt.Line2D([], [], marker="o", ls="", ms=4, color="#1b4965", label="Rural"),
               mpl.patches.Patch(color="#1b4965", alpha=0.12, label="Displacement radius")]
    ax.legend(handles=handles, fontsize=7.5, loc="center left",
              bbox_to_anchor=(1.01, 0.5), frameon=False)

    ax.set_title(f"DHS cluster locations ({len(pts)} clusters)")
    ax.set_axis_off()
    ax.set_aspect("equal")
    _add_scalebar(ax, gdf)
    save_map(fig, "dhs_clusters")


def map_custom(var: str, year: int | None, cmap: str, scheme: str | None) -> None:
    """Map any panel variable — the escape hatch for exploratory work."""
    gdf = district_values(var, year=year)
    if gdf is None:
        return
    yr = f", {year}" if year else " (period mean)"
    fig, _ = choropleth(gdf, title=f"{var.replace('_', ' ')}{yr}",
                        legend_label=var, cmap=cmap,
                        scheme=scheme, k=5, labels=True)
    save_map(fig, f"custom_{var}" + (f"_{year}" if year else ""))


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

OUTPUTS = {
    "districts_reference": map_districts_reference,
    "rainfall_mean": map_rainfall_mean,
    "rainfall_variability": map_rainfall_variability,
    "drought_rate": map_drought_rate,
    "rainfall_facets": map_rainfall_facets,
    "dhs_clusters": map_dhs_clusters,
}


def main(argv=None) -> int:
    global FMT
    p = argparse.ArgumentParser(
        description=textwrap.dedent(__doc__),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--all", action="store_true")
    p.add_argument("--only", nargs="+", choices=list(OUTPUTS))
    p.add_argument("--var", help="map an arbitrary panel column")
    p.add_argument("--year", type=int, help="single year (default: period mean)")
    p.add_argument("--cmap", default="viridis", help="colormap for --var")
    p.add_argument("--scheme", default="natural_breaks",
                   choices=["natural_breaks", "quantiles", "equal_interval", "none"])
    p.add_argument("--format", default="png", choices=["png", "pdf", "svg"])
    p.add_argument("--list-vars", action="store_true", help="show mappable columns")
    args = p.parse_args(argv)

    if args.list_vars:
        panel = load_panel()
        if panel is not None:
            num = panel.select_dtypes("number").columns.difference(["district_id", "year"])
            print("\n".join(sorted(num)))
        return 0

    if not (args.all or args.only or args.var):
        p.print_help()
        return 1

    FMT = args.format

    if args.var:
        map_custom(args.var, args.year, args.cmap,
                   None if args.scheme == "none" else args.scheme)
        return 0

    for name in (list(OUTPUTS) if args.all else args.only):
        _log(name)
        OUTPUTS[name]()

    _log("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
