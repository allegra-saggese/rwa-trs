"""
paths.py -- every folder the code reads or writes, defined once.

Every script in this repo imports this module. No other file names a Dropbox path.

How the Dropbox project folder ("Rwanda - TRS") is found, in order:
  1. the RWA_ROOT environment variable, if set (use this on any new machine);
  2. otherwise the login user's entry in ROOTS below.

Scripts in a subfolder reach this module with:
    import sys; from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # [2] from NISR/<survey>/
    import paths as P
"""

from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent

ROOTS = {
    "matteo": "/Users/matteo/Library/CloudStorage/Dropbox/1-Ongoing Projects/Rwanda - TRS",
    "allegrasaggese": "/Users/allegrasaggese/Library/CloudStorage/Dropbox/Rwanda - TRS",
}


def db_root() -> Path:
    """The 'Rwanda - TRS' Dropbox folder on this machine."""
    r = os.environ.get("RWA_ROOT")
    if not r:
        u = getpass.getuser()
        if u not in ROOTS:
            sys.exit(f"Unknown user {u!r}: set RWA_ROOT to the 'Rwanda - TRS' Dropbox folder, "
                     f"or add yourself to ROOTS in {Path(__file__).name}")
        r = ROOTS[u]
    p = Path(r)
    if not p.is_dir():
        sys.exit(f"Project root not found: {p}")
    return p


DROPBOX = db_root()

# ---- source data (read) -----------------------------------------------------
DATA = DROPBOX / "data"
NISR = DATA / "Publicly-Available-NISR"            # one folder per survey
WBES = DATA / "WB-Enterprise-Surveys"
GEO = DATA / "geo-data"                            # parks, roads, land cover, forest, climate ...
POP_RASTER = NISR / "geodata-nisr" / "PopulationDensity01.tif"

# Nighttime lights: the images, as downloaded and clipped to Rwanda.
NIGHTLIGHTS = DATA / "Nighttime-Lights"
NTL_SOURCE = NIGHTLIGHTS / "source"                # as downloaded, plus the two download manifests
NTL_CLIPS = NIGHTLIGHTS / "clipped-rwanda"         # one GeoTIFF per product, layer and period
NTL_DOCS = NIGHTLIGHTS / "z_Documentation"

# National tourism series (assembled 2026-09-14), each kept with its source. Look up by file name.
_TOURISM_DIRS = {
    "world_bank_wdi.csv": DATA / "WB-Tourism-data",
    "rdb_tourism_revenue_usd_million.csv": DATA / "RDB",
    "rdb_visitor_arrivals.csv": DATA / "RDB",
    "park_revenue_usd_million.csv": NISR / "Travel-Expenditure-Survey-TES",
    "park_visitors_by_park.csv": NISR / "Travel-Expenditure-Survey-TES",
    "park_visitors_by_nationality.csv": NISR / "Travel-Expenditure-Survey-TES",
    "arrivals_by_purpose_nisr.csv": NISR / "Travel-Expenditure-Survey-TES",
}


def tourism(name: str) -> Path:
    """Path of one of the national tourism series (see _TOURISM_DIRS)."""
    return _TOURISM_DIRS[name] / name

# ---- manipulated data (written) ---------------------------------------------
# Anything collapsed to sectors / cells / districts, merged across sources, or built for an analysis.
HARMONIZED = DATA / "harmonized"
HARM_PRELIM = HARMONIZED / "prelim"                # micro-analysis descriptive panels
HARM_EXTRACTS = HARMONIZED / "extracts"            # column subsets of the cleaned survey files (micro-analysis)
HARM_LABOUR = HARMONIZED / "labour"                # LFS and Establishment Census industry tables
HARM_NTL = HARMONIZED / "nightlights"              # nightlight sector and cell panels + codebook
HARM_NTL_LONG = HARM_NTL / "sector-cell-long"      # one long file per product and unit
HARM_DISTRICT = HARMONIZED / "district"            # district panel, rainfall, WDI, DHS extracts (data-build/)

# ---- results (written) ------------------------------------------------------
ANALYSIS = DROPBOX / "analysis" / "nisr-public-data-analysis"   # regression results (reg_*.csv)
OUT = DROPBOX / "output"
FIGS = OUT / "figures"
MAPS = OUT / "maps"
TABLES = OUT / "tables"
TABLES_SUM = TABLES / "summary_statistics"       # descriptive tables
TABLES_REG = TABLES / "regressions"              # regression tables
LATEX = OUT / "latex"                              # write-ups: .tex sources and compiled .pdf
VARLISTS = OUT / "variable-lists"                  # generated variable inventories

# Download caches of data-build/district_sources.py (source data, so kept with their source).
GADM_CACHE = GEO / "admin-boundaries"              # gadm41_RWA_2.json.zip
CHIRPS_CACHE = GEO / "climate" / "chirps"          # monthly CHIRPS rasters, downloaded on first run


def check_writable(target: Path) -> None:
    """Refuse to write inside the NISR holdings.

    Only the NISR/ pipelines write there. A derived table written next to a survey file would be
    read as source data by the next person, so derived tables go to HARMONIZED instead.
    """
    if target == NISR or NISR in target.parents:
        raise RuntimeError(f"refusing to write inside the NISR holdings ({target}); "
                           "derived tables belong in data/harmonized/")
