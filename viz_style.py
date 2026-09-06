"""
viz_style.py — shared plotting conventions for the project.

Imported by summary.py and maps.py so every figure uses the same palette,
fonts and axis rules. Keeping this in one place is what stops the figure set
from drifting into eight different colour schemes.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import matplotlib as mpl
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import FuncFormatter

ROOT = Path(__file__).resolve().parent
GEO = Path(
    "/Users/allegrasaggese/Library/CloudStorage/Dropbox/Rwanda - TRS/data/geo-data"
)
NISR = Path(
    "/Users/allegrasaggese/Library/CloudStorage/Dropbox/Rwanda - TRS/"
    "data/Publicly-Available-NISR"
)
FIGS = ROOT / "output" / "figures"
MAPS = ROOT / "output" / "maps"

# Treated / control, used for the same meaning in every figure.
PARK, NONPARK = "#c1121f", "#1b4965"

# Land-cover classes keep one colour throughout, matching Dynamic World's own
# palette conventions so maps and stacked bars agree.
LANDCOVER = {
    "dw_trees": ("trees", "#2a9d8f"),
    "dw_crops": ("cropland", "#e9c46a"),
    "dw_shrub_and_scrub": ("shrub & scrub", "#a3b18a"),
    "dw_grass": ("grass", "#cbd5c0"),
    "dw_built": ("built-up", "#8b5fbf"),
    "dw_water": ("water", "#457b9d"),
    "dw_bare": ("bare", "#d4a373"),
    "dw_flooded_vegetation": ("flooded vegetation", "#6a994e"),
    "dw_snow_and_ice": ("snow & ice", "0.9"),
}

ISIC = {
    1: "Agriculture, forestry & fishing", 2: "Mining & quarrying", 3: "Manufacturing",
    4: "Electricity & gas", 5: "Water & waste", 6: "Construction",
    7: "Wholesale & retail trade", 8: "Transport & storage",
    9: "Accommodation & food service", 10: "Information & communication",
    11: "Finance & insurance", 12: "Real estate", 13: "Professional & technical",
    14: "Administrative & support", 15: "Public administration", 16: "Education",
    17: "Human health & social work", 18: "Arts, entertainment & recreation",
    19: "Other service activities", 20: "Households as employers",
    21: "Extraterritorial", 99: "Not stated",
}
TOURISM_ISIC = [9, 18]        # accommodation & food; arts, entertainment & recreation

# Years are integers. Matplotlib will happily render 2016.5 on a date axis
# otherwise, which looks like an error in a paper.
YEAR_FMT = FuncFormatter(lambda v, _p: f"{int(v)}")

RC = {
    "figure.dpi": 150, "savefig.dpi": 300, "savefig.bbox": "tight",
    "font.family": "serif", "font.size": 9, "axes.titlesize": 10,
    "axes.labelsize": 9, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.alpha": 0.25, "grid.linewidth": 0.5,
    "legend.frameon": False,
}


def apply_style() -> None:
    mpl.rcParams.update(RC)


def year_axis(ax) -> None:
    """Force integer year ticks. Call on any axis with years on it."""
    ax.xaxis.set_major_formatter(YEAR_FMT)


def save(fig, name: str, kind: str = "figure") -> Path:
    d = FIGS if kind == "figure" else MAPS
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{name}.png"
    fig.savefig(p)
    plt.close(fig)
    print(f"  -> {p.relative_to(ROOT)}", flush=True)
    return p


# --------------------------------------------------------------------------
# Shared loaders. Every id is cast on read: GeoPackage round-trips integer ids
# as text, which silently breaks merges against the CSVs.
# --------------------------------------------------------------------------

def sectors() -> gpd.GeoDataFrame:
    g = gpd.read_file(GEO / "protected-areas/sectors_park_exposure_geodatarw.gpkg")
    g["sector_id"] = g.sector_id.astype("int64")
    return g.to_crs(32735)


def cells() -> gpd.GeoDataFrame:
    g = gpd.read_file(GEO / "protected-areas/cells_park_exposure_geodatarw.gpkg")
    g["cell_id"] = g.cell_id.astype("int64")
    return g.to_crs(32735)


def districts() -> gpd.GeoDataFrame:
    g = gpd.read_file(GEO / "admin-boundaries/geodatarw_district_boundary.gpkg")
    g["dist"] = pd.to_numeric(g.code_dist, errors="coerce").astype("Int64")
    return g.to_crs(32735)


def parks() -> gpd.GeoDataFrame:
    """The five national parks, dissolved. geodata.rw is the authoritative source."""
    pa = gpd.read_file(GEO / "protected-areas/rwanda_protected_areas_geodata_rw.gpkg")
    keep = ["Nyungwe National Park", "Akagera National Park",
            "Volcanoes National Park", "Gishwati", "Mukura"]
    return pa[pa.areaname.isin(keep)].dissolve(by="areaname").reset_index().to_crs(32735)


def csv(rel: str, id_col: str | None = None) -> pd.DataFrame:
    d = pd.read_csv(GEO / rel)
    if id_col and id_col in d.columns:
        d[id_col] = d[id_col].astype("int64")
    return d


def frame_map(ax, title: str, park_layer=None) -> None:
    """Standard map furniture: park outlines, no axes, equal aspect."""
    if park_layer is not None:
        park_layer.boundary.plot(ax=ax, color=NONPARK, linewidth=1.0)
    ax.set_title(title)
    ax.set_axis_off()
    ax.set_aspect("equal")
