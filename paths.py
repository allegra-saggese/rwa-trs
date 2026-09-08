"""
paths.py — every filesystem root the analysis scripts use, resolved once.

Follows the convention already established in the NISR pipelines
(`NISR/*/[a-z]*_helpers.py`): the Dropbox project folder sits at a different
path on each collaborator's Mac, so an environment variable overrides
everything and otherwise the login user decides. Same idea here, one level up:
these roots cover the whole project, not one survey.

This module lives at the repo root so every task folder can import it. Scripts
in subfolders reach it with:

    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import paths as P

Set RWA_ROOT to point at the "Rwanda - TRS" Dropbox folder on a machine that is
not listed below, or add yourself to ROOTS.
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
            sys.exit(
                f"Unknown user {u!r}: set RWA_ROOT to the 'Rwanda - TRS' Dropbox "
                f"folder, or add yourself to ROOTS in {Path(__file__).name}"
            )
        r = ROOTS[u]
    p = Path(r)
    if not p.is_dir():
        sys.exit(f"Project root not found: {p}")
    return p


DROPBOX = db_root()

# ---- data the project reads -------------------------------------------------
DATA = DROPBOX / "data"
GEO = DATA / "geo-data"
NISR = DATA / "Publicly-Available-NISR"

# The 1 km population raster ships inside the NISR geoportal download.
POP_RASTER = NISR / "geodata-nisr" / "PopulationDensity01.tif"

# ---- what the project writes ------------------------------------------------
# Rendered output goes to Dropbox so a coauthor who does not run the code
# still sees it. Interim files stay in the repo, gitignored.
OUT = DROPBOX / "output"
FIGS = OUT / "figures"
MAPS = OUT / "maps"
TABLES = OUT / "tables"

INTERIM = REPO / "interim-processing"
RAW = INTERIM / "raw"
PROC = INTERIM / "processed"


def check_writable(target: Path) -> None:
    """Refuse to write inside the NISR holdings.

    4_Harmonized and everything around it belongs to the NISR/ pipelines. A
    derived table landing next to H_LFS_person.dta would be read as source data
    by the next person to look, so this is enforced rather than documented.
    """
    if target == NISR or NISR in target.parents:
        raise RuntimeError(
            f"refusing to write inside the NISR holdings ({target}); "
            "those files are read-only, derived tables belong in geo-data/"
        )
