"""
district_sources.py -- the district-level sources that do not come from a survey, and the district panel.

Downloads (cached) and cleans:
    boundaries   GADM district boundaries                 -> districts.gpkg
    chirps       CHIRPS monthly rainfall by district      -> rainfall_monthly.csv, rainfall_annual.csv
    wdi          World Bank national indicators           -> wdi.csv
    dhs          DHS recode files (data/DHS/)             -> dhs_*.csv
    dhs_gps      DHS cluster locations                    -> dhs_clusters.gpkg
then merges rainfall, WDI and the EICV 7 district welfare table into district_panel.csv
(district x year). All outputs go to data/harmonized/district/ (paths.HARM_DISTRICT).
Downloads are cached with their source: GADM in data/geo-data/admin-boundaries/, CHIRPS in
data/geo-data/climate/chirps/. Delete a cached file to force a refresh.

The merge also picks up eicv7_district_welfare.csv if it exists. Nothing builds that file at present
(see build_eicv7_district_welfare in micro-analysis/district_survey_tables.py), so the panel has no
EICV columns.

Usage
-----
    python data-build/district_sources.py --all
    python data-build/district_sources.py --sources boundaries chirps
    python data-build/district_sources.py --sources chirps --start 2010 --end 2020

Formerly the non-survey half of data-build-scripts/extract.py.
"""
from __future__ import annotations

import argparse
import gzip
import io
import re
import shutil
import sys
import unicodedata
import warnings
import zipfile
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import paths as P

import numpy as np
import pandas as pd
import requests

# --------------------------------------------------------------------------
# Paths and constants
# --------------------------------------------------------------------------

REPO = P.REPO
ROOT = P.REPO          # back-compat for older references

# Everything this script writes is manipulated data: data/harmonized/district/.
PROC = P.HARM_DISTRICT
DROPBOX = P.DROPBOX

# Survey microdata is read from the Dropbox holdings, never written to.
NISR_ROOT = P.NISR

GADM_URL = "https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_RWA_2.json.zip"

# CHIRPS v2.0, Africa monthly window. ~4 MB per month gzipped; the Africa subset
# is used rather than the global product purely to keep the download tractable.
CHIRPS_URL = (
    "https://data.chc.ucsb.edu/products/CHIRPS-2.0/africa_monthly/tifs/"
    "chirps-v2.0.{year}.{month:02d}.tif.gz"
)
CHIRPS_NODATA = -9999.0
CHIRPS_START = 1981  # first full year of the CHIRPS record

# World Bank indicators. Extend freely — the loader is generic.
WDI_INDICATORS = {
    "NY.GDP.PCAP.KD": "gdp_pc_const2015usd",
    "SP.RUR.TOTL.ZS": "rural_pop_share",
    "SL.AGR.EMPL.ZS": "employment_agriculture_share",
    "AG.LND.AGRI.ZS": "agricultural_land_share",
    "SP.POP.TOTL": "population",
    "SI.POV.DDAY": "poverty_headcount_215",
}

# Province names as GADM ships them (Kinyarwanda, and unspaced) mapped to the
# conventional English forms used in NISR publications.
PROVINCE_LABELS = {
    "amajyaruguru": "North",
    "amajyepfo": "South",
    "iburasirazuba": "East",
    "iburengerazuba": "West",
    "umujyiwakigali": "Kigali City",
}


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _log(msg: str) -> None:
    print(f"[extract] {msg}", flush=True)


def normalise_name(s: str) -> str:
    """Canonical key for joining place names across sources.

    Survey files, GADM, and NISR tables disagree on accents, case, spacing, and
    hyphens for the same district. Lowercase, strip accents, and drop every
    non-alphanumeric character so 'Nyabihu', 'NYABIHU' and 'Nyabihu ' all match.
    """
    if pd.isna(s):
        return ""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    # NISR value labels often carry the numeric code as a prefix ("11 -Nyarugenge",
    # "1-Kigali", "21- Nyanza"). Strip a leading code so the name matches GADM.
    s = re.sub(r"^\s*\d+\s*[-–—.]?\s*", "", s)
    return re.sub(r"[^a-z0-9]", "", s.lower())


def download(url: str, dest: Path, timeout: int = 300) -> Path | None:
    """Download to `dest` unless cached. Returns None on failure (never raises)."""
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with requests.get(url, stream=True, timeout=timeout) as r:
            r.raise_for_status()
            tmp = dest.with_suffix(dest.suffix + ".part")
            with open(tmp, "wb") as fh:
                shutil.copyfileobj(r.raw, fh)
            tmp.rename(dest)
        return dest
    except Exception as exc:  # noqa: BLE001 - one bad month must not kill the run
        _log(f"  ! failed {url.rsplit('/', 1)[-1]}: {exc}")
        return None


# --------------------------------------------------------------------------
# Boundaries
# --------------------------------------------------------------------------

def extract_boundaries() -> "gpd.GeoDataFrame":  # noqa: F821
    """Rwanda admin-2 (district) boundaries from GADM 4.1.

    Produces the spatial spine every other source joins onto: 30 districts with
    a stable `district_id`, a normalised join key, and English province labels.
    """
    import geopandas as gpd

    _log("boundaries: GADM 4.1 admin-2")
    zpath = P.GADM_CACHE / "gadm41_RWA_2.json.zip"
    if download(GADM_URL, zpath) is None:
        raise RuntimeError("could not download GADM boundaries")

    g = gpd.read_file(f"zip://{zpath}")

    g = g.rename(columns={"NAME_1": "province_raw", "NAME_2": "district", "GID_2": "gid_2"})
    g["district_key"] = g["district"].map(normalise_name)
    g["province"] = g["province_raw"].map(normalise_name).map(PROVINCE_LABELS)

    if g["province"].isna().any():
        missing = g.loc[g["province"].isna(), "province_raw"].unique().tolist()
        warnings.warn(f"unmapped province labels: {missing}", stacklevel=2)

    # Stable, sorted integer id. Deliberately not GADM's GID, which can change
    # between GADM releases; district_id is reproducible from names alone.
    g = g.sort_values(["province", "district"]).reset_index(drop=True)
    g["district_id"] = np.arange(1, len(g) + 1)

    # Equal-area CRS for any area/distance work. Rwanda sits in UTM 35S.
    g["area_km2"] = g.to_crs(32735).geometry.area / 1e6

    keep = ["district_id", "district", "district_key", "province", "gid_2", "area_km2", "geometry"]
    g = g[keep]

    PROC.mkdir(parents=True, exist_ok=True)
    g.to_file(PROC / "districts.gpkg", layer="districts", driver="GPKG")
    _log(f"  -> districts.gpkg ({len(g)} districts, {g['province'].nunique()} provinces)")
    return g


def load_districts() -> "gpd.GeoDataFrame":  # noqa: F821
    """Read cached districts, building them if this is a first run."""
    import geopandas as gpd

    fp = PROC / "districts.gpkg"
    if not fp.exists():
        return extract_boundaries()
    return gpd.read_file(fp, layer="districts")


# --------------------------------------------------------------------------
# CHIRPS rainfall
# --------------------------------------------------------------------------

def extract_chirps(start: int = 1981, end: int | None = None) -> pd.DataFrame:
    """District-month rainfall totals from CHIRPS v2.0.

    For each month the raster is downloaded (cached), then averaged over each
    district polygon. `all_touched=True` is used because CHIRPS is 0.05 deg
    (~5.5 km) while the smallest Rwandan districts are urban Kigali cells that
    would otherwise capture very few pixel centroids.
    """
    from rasterstats import zonal_stats

    end = end or pd.Timestamp.today().year
    districts = load_districts()
    _log(f"chirps: {start}-{end} ({(end - start + 1) * 12} months, cached after first run)")

    rows = []
    for year in range(start, end + 1):
        for month in range(1, 13):
            gz = P.CHIRPS_CACHE / f"chirps-v2.0.{year}.{month:02d}.tif.gz"
            tif = gz.with_suffix("")  # strip .gz

            if not tif.exists():
                if download(CHIRPS_URL.format(year=year, month=month), gz) is None:
                    continue  # month not yet published, or transient failure
                try:
                    with gzip.open(gz, "rb") as fin, open(tif, "wb") as fout:
                        shutil.copyfileobj(fin, fout)
                except Exception as exc:  # noqa: BLE001
                    _log(f"  ! bad archive {gz.name}: {exc}")
                    gz.unlink(missing_ok=True)
                    continue

            stats = zonal_stats(
                districts, str(tif),
                stats=["mean", "count"], nodata=CHIRPS_NODATA, all_touched=True,
            )
            for d, s in zip(districts.itertuples(), stats):
                rows.append({
                    "district_id": d.district_id,
                    "district": d.district,
                    "year": year,
                    "month": month,
                    "rain_mm": s["mean"],
                    "n_pixels": s["count"],
                })
        _log(f"  {year} done")

    monthly = pd.DataFrame(rows)
    if monthly.empty:
        raise RuntimeError("no CHIRPS months retrieved")

    monthly["date"] = pd.to_datetime(dict(year=monthly.year, month=monthly.month, day=1))
    monthly = monthly.sort_values(["district_id", "date"]).reset_index(drop=True)
    monthly.to_csv(PROC / "rainfall_monthly.csv", index=False)
    _log(f"  -> rainfall_monthly.csv ({len(monthly):,} district-months)")

    annual = build_rainfall_annual(monthly)
    annual.to_csv(PROC / "rainfall_annual.csv", index=False)
    _log(f"  -> rainfall_annual.csv ({len(annual):,} district-years)")
    return monthly


def build_rainfall_annual(monthly: pd.DataFrame) -> pd.DataFrame:
    """Collapse to district-years and attach anomaly measures.

    Two shock measures are produced, both relative to the district's own long-run
    distribution so that cross-district comparisons are not driven by the very
    steep west-east rainfall gradient:

      rain_z        annual total in district-specific standard deviations
      rain_pctile   empirical percentile of the annual total within the district

    Only years with all 12 months present are kept, so a partially published
    current year is not mistaken for a drought.
    """
    counts = monthly.groupby(["district_id", "year"])["rain_mm"].transform("count")
    complete = monthly[counts == 12]

    annual = (
        complete.groupby(["district_id", "district", "year"], as_index=False)
        .agg(rain_mm=("rain_mm", "sum"), months=("rain_mm", "count"))
    )

    grp = annual.groupby("district_id")["rain_mm"]
    annual["rain_mean"] = grp.transform("mean")
    annual["rain_sd"] = grp.transform("std")
    annual["rain_z"] = (annual["rain_mm"] - annual["rain_mean"]) / annual["rain_sd"]
    annual["rain_pctile"] = grp.rank(pct=True)
    annual["drought"] = (annual["rain_z"] < -1).astype(int)
    return annual


# --------------------------------------------------------------------------
# World Bank WDI
# --------------------------------------------------------------------------

def extract_wdi(indicators: dict[str, str] | None = None) -> pd.DataFrame:
    """National-level indicators from the World Bank API (no key required)."""
    indicators = indicators or WDI_INDICATORS
    _log(f"wdi: {len(indicators)} indicators")

    frames = []
    for code, name in indicators.items():
        url = (f"https://api.worldbank.org/v2/country/RWA/indicator/{code}"
               f"?format=json&per_page=500")
        try:
            payload = requests.get(url, timeout=60).json()
        except Exception as exc:  # noqa: BLE001
            _log(f"  ! {code}: {exc}")
            continue
        if len(payload) < 2 or payload[1] is None:
            _log(f"  ! {code}: no observations returned")
            continue
        frames.append(pd.DataFrame([
            {"year": int(r["date"]), name: r["value"]}
            for r in payload[1] if r["value"] is not None
        ]))

    if not frames:
        raise RuntimeError("no WDI indicators retrieved")

    wdi = frames[0]
    for f in frames[1:]:
        wdi = wdi.merge(f, on="year", how="outer")
    wdi = wdi.sort_values("year").reset_index(drop=True)

    wdi.to_csv(PROC / "wdi.csv", index=False)
    _log(f"  -> wdi.csv ({len(wdi)} years, {wdi.shape[1] - 1} indicators)")
    return wdi


# --------------------------------------------------------------------------
# Survey microdata (DHS / EICV)
# --------------------------------------------------------------------------

# DHS recode files are named like RWHR7BFL.DTA: RW + recode + version + FL.
# Only the two-letter recode code matters for identifying the unit of analysis.
DHS_RECODES = {
    "HR": "household",       # household recode      - hv001 cluster, hv005 weight
    "PR": "person",          # household member      - hv001 cluster, hv005 weight
    "IR": "women",           # individual women      - v001 cluster,  v005 weight
    "MR": "men",             # individual men        - mv001 cluster, mv005 weight
    "KR": "children",        # children under 5      - v001 cluster,  v005 weight
    "BR": "births",          # birth history         - v001 cluster,  v005 weight
}

DHS_WEIGHT_COLS = {"household": "hv005", "person": "hv005", "women": "v005",
                   "men": "mv005", "children": "v005", "births": "v005"}
DHS_CLUSTER_COLS = {"household": "hv001", "person": "hv001", "women": "v001",
                    "men": "mv001", "children": "v001", "births": "v001"}


def extract_dhs() -> dict[str, pd.DataFrame]:
    """Load any DHS recode files found in data/raw/dhs/.

    DHS distributes each survey round as several files at different units of
    analysis. This walks whatever is present, applies the correct sampling
    weight (DHS stores weights scaled by 1e6), and writes one tidy CSV per
    recode. Nothing is downloaded: DHS requires a registered account, so files
    must be placed in data/raw/dhs/ by hand.
    """
    import pyreadstat

    src = (P.DROPBOX / "data/DHS")
    files = sorted([p for p in src.glob("**/*") if p.suffix.upper() in {".DTA", ".SAV"}]) if src.exists() else []

    if not files:
        _log("dhs: no files in data/raw/dhs/ - skipping "
             "(register at dhsprogram.com, then drop the .DTA files there)")
        return {}

    _log(f"dhs: {len(files)} file(s)")
    out: dict[str, pd.DataFrame] = {}

    for fp in files:
        code = fp.stem[2:4].upper()
        unit = DHS_RECODES.get(code)
        if unit is None:
            _log(f"  ? {fp.name}: unrecognised recode '{code}', skipping")
            continue

        if fp.suffix.upper() == ".DTA":
            df, meta = pyreadstat.read_dta(fp, apply_value_formats=True)
        else:
            df, meta = pyreadstat.read_sav(fp, apply_value_formats=True)

        # DHS weights are integers scaled by 1e6; divide before any weighted stat.
        wcol = DHS_WEIGHT_COLS.get(unit)
        if wcol and wcol in df.columns:
            df["weight"] = df[wcol] / 1e6
        else:
            _log(f"  ! {fp.name}: expected weight column '{wcol}' absent")

        ccol = DHS_CLUSTER_COLS.get(unit)
        if ccol and ccol in df.columns:
            df["cluster"] = df[ccol]

        # Survey year is not always a column; recover it from the filename when
        # absent so rounds can be pooled.
        if "survey_year" not in df.columns:
            m = re.search(r"(19|20)\d{2}", fp.stem)
            df["survey_year"] = int(m.group()) if m else pd.NA

        df["source_file"] = fp.name
        out[unit] = pd.concat([out[unit], df]) if unit in out else df
        _log(f"  {fp.name}: {unit}, {len(df):,} rows x {df.shape[1]} cols")

    for unit, df in out.items():
        dest = PROC / f"dhs_{unit}.csv"
        df.to_csv(dest, index=False)
        _log(f"  -> {dest.name} ({len(df):,} rows)")
    return out


def extract_dhs_gps() -> "gpd.GeoDataFrame | None":  # noqa: F821
    """Load DHS cluster GPS points and join them to districts.

    Two things are handled explicitly:

    1. Clusters at (0, 0) are DHS's missing-location sentinel, not a real place
       in the Gulf of Guinea. They are dropped.
    2. DHS displaces cluster coordinates for confidentiality - up to 2 km urban,
       5 km rural, with 1% of rural clusters moved up to 10 km. The displacement
       radius is carried as a column so downstream spatial joins can buffer by it
       rather than pretending the point is exact.
    """
    import geopandas as gpd

    src = (P.DROPBOX / "data/DHS")
    shp = sorted(src.glob("**/*.shp")) if src.exists() else []
    if not shp:
        _log("dhs gps: no shapefile in data/raw/dhs/ - skipping")
        return None

    pts = gpd.read_file(shp[0])
    _log(f"dhs gps: {shp[0].name} ({len(pts)} clusters)")

    n0 = len(pts)
    pts = pts[~((pts.geometry.x == 0) & (pts.geometry.y == 0))].copy()
    if len(pts) < n0:
        _log(f"  dropped {n0 - len(pts)} cluster(s) with missing (0,0) coordinates")

    urban = pts.get("URBAN_RURA", pd.Series(index=pts.index, dtype=object)).astype(str).str.upper().str[0]
    pts["displacement_km"] = np.where(urban == "U", 2.0, 5.0)

    districts = load_districts().to_crs(pts.crs)
    pts = gpd.sjoin(pts, districts[["district_id", "district", "province", "geometry"]],
                    how="left", predicate="within").drop(columns="index_right")

    unmatched = pts["district_id"].isna().sum()
    if unmatched:
        _log(f"  ! {unmatched} cluster(s) fell outside all districts "
             f"(expected: displacement can push points over a border)")

    pts.to_file(PROC / "dhs_clusters.gpkg", layer="clusters", driver="GPKG")
    _log(f"  -> dhs_clusters.gpkg ({len(pts)} clusters)")
    return pts

# --------------------------------------------------------------------------
# Merge
# --------------------------------------------------------------------------

def merge_district_panel() -> pd.DataFrame:
    """Assemble the district-year analysis panel from whatever has been built.

    Rainfall is the spine (it is the only district-year source available for the
    full period); national WDI series are attached by year, which makes them
    constant within a year by construction - useful as controls, never as
    identifying variation.
    """
    _log("merge: district-year panel")

    fp = PROC / "rainfall_annual.csv"
    if not fp.exists():
        _log("  ! rainfall_annual.csv absent; run with --sources chirps first")
        return pd.DataFrame()

    panel = pd.read_csv(fp)

    districts = load_districts()
    panel = panel.merge(
        pd.DataFrame(districts.drop(columns="geometry"))[
            ["district_id", "province", "area_km2"]],
        on="district_id", how="left",
    )

    wdi_fp = PROC / "wdi.csv"
    if wdi_fp.exists():
        panel = panel.merge(pd.read_csv(wdi_fp), on="year", how="left")

    # EICV welfare is a single cross-section, so it is merged on district only
    # and repeats down the years. Columns are suffixed with the survey to keep
    # that obvious: eicv7_poverty_rate is a 2023-24 value on every row.
    wel_fp = PROC / "eicv7_district_welfare.csv"
    if wel_fp.exists():
        wel = pd.read_csv(wel_fp).drop(columns=["survey", "survey_year"], errors="ignore")
        wel = wel.rename(columns={c: f"eicv7_{c}" for c in wel.columns if c != "district_id"})
        panel = panel.merge(wel, on="district_id", how="left")

    panel = panel.sort_values(["district_id", "year"]).reset_index(drop=True)
    panel.to_csv(PROC / "district_panel.csv", index=False)

    yrs = f"{panel.year.min()}-{panel.year.max()}"
    _log(f"  -> district_panel.csv ({len(panel):,} rows, "
         f"{panel.district_id.nunique()} districts, {yrs})")
    return panel


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

SOURCES = ["boundaries", "chirps", "wdi", "dhs", "dhs_gps"]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sources", nargs="+", choices=SOURCES,
                   help="subset of sources to build")
    p.add_argument("--all", action="store_true", help="build every source, then merge")
    p.add_argument("--start", type=int, default=CHIRPS_START, help="first CHIRPS year")
    p.add_argument("--end", type=int, default=None, help="last CHIRPS year")
    p.add_argument("--no-merge", action="store_true", help="skip the merge step")
    args = p.parse_args(argv)

    if not args.sources and not args.all:
        p.print_help()
        return 1

    todo = SOURCES if args.all else args.sources
    PROC.mkdir(parents=True, exist_ok=True)

    if "boundaries" in todo or "chirps" in todo or "dhs_gps" in todo:
        extract_boundaries()
    if "chirps" in todo:
        extract_chirps(start=args.start, end=args.end)
    if "wdi" in todo:
        extract_wdi()
    if "dhs" in todo:
        extract_dhs()
    if "dhs_gps" in todo:
        extract_dhs_gps()

    if not args.no_merge:
        merge_district_panel()

    _log("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
