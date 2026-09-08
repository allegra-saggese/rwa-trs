"""
extract.py — acquire, clean, and merge all Rwanda project data.

Runs the full data build: downloads open sources, loads any survey microdata
placed in data/raw/, cleans each to a tidy frame, and merges to analysis files
in data/processed/.

Usage
-----
    python extract.py --all
    python extract.py --sources boundaries chirps
    python extract.py --sources chirps --start 2010 --end 2020

Outputs (data/processed/)
-------------------------
    districts.gpkg          30 districts, harmonised names + district_id
    rainfall_monthly.csv    district x month CHIRPS totals, 1981-present
    rainfall_annual.csv     district x year totals, anomalies, SPI-style z-scores
    wdi.csv                 national indicators from the World Bank API
    dhs_*.csv               DHS recode files, if present in data/raw/

Notes
-----
Downloads are cached in data/raw/ and skipped if already present; re-running is
cheap. Delete a cached file to force a refresh.
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
from pathlib import Path

import numpy as np
import pandas as pd
import requests

# --------------------------------------------------------------------------
# Paths and constants
# --------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"

# Survey microdata is read from the Dropbox holdings, not the repo.
NISR_ROOT = Path(
    "/Users/allegrasaggese/Library/CloudStorage/Dropbox/Rwanda - TRS/"
    "data/Publicly-Available-NISR"
)

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
    zpath = RAW / "gadm41_RWA_2.json.zip"
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
            gz = RAW / "chirps" / f"chirps-v2.0.{year}.{month:02d}.tif.gz"
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

    src = Path("/Users/allegrasaggese/Library/CloudStorage/Dropbox/"
               "Rwanda - TRS/data/DHS")
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

    src = Path("/Users/allegrasaggese/Library/CloudStorage/Dropbox/"
               "Rwanda - TRS/data/DHS")
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


# EICV7 (2023-24) ships 21 files, all sharing the same identifier block:
# hhid, clust, province, district, strata_id, weight. Numbering follows the
# official variable dictionary (EICV7_2023-24_variable_dictionary.csv).
EICV7_FILES = {
    "F1": "poverty",          # analysis-ready welfare aggregates
    "F2": "person",           # demographics, education, labour (S0-S4, S6)
    "F3": "household",        # dwelling, water, energy, assets (S1, S5, S7)
    "F4": "services",         # access to services
    "F5": "exp_annual",       # non-food, 12-month recall
    "F6": "exp_monthly",      # non-food, 4-week recall
    "F7": "exp_weekly",       # non-food + own production, 7-day recall
    "F8": "food",             # food expenditure/consumption
    "F9": "food_away",        # food away from home (person-level)
    "F10": "transfers_out",
    "F11": "transfers_in",
    "F12": "other_expenditure",
    "F13": "vup_direct_support",
    "F14": "vup_classic_public_work",
    "F15": "vup_expanded_public_work",
    "F16": "vup_nsds",
    "F17": "vup_financial_services",
    "F18": "other_income",
    "F19": "credits",
    "F20": "durables",
    "F21": "savings",
}

# Two weights, and they are not interchangeable.
#   weight  - household weight. Use for household-level statistics
#             (share of households in poverty, mean household size).
#   pop_wt  - population weight. Use for person-level statistics
#             (poverty headcount among individuals, employment rates).
# Only F1 and F3 carry pop_wt; person-level work on F2 must bring it across
# from F1 on hhid.
EICV7_HH_WEIGHT = "weight"
EICV7_POP_WEIGHT = "pop_wt"


def _eicv7_unit(path: Path) -> str | None:
    """Map an EICV7 filename to a short unit name via its F-number prefix."""
    stem = path.stem.upper()
    for fnum, unit in sorted(EICV7_FILES.items(), key=lambda kv: -len(kv[0])):
        # Match 'F1 CS_...', 'F1_CS_...', 'F1CS...' but not F10 when asked for F1.
        if stem.startswith(fnum) and (len(stem) == len(fnum) or not stem[len(fnum)].isdigit()):
            return unit
    return None


def extract_eicv() -> dict[str, pd.DataFrame]:
    """Load EICV files from the Dropbox EICV folder.

    The folder holds three different kinds of file and they need different
    handling:

      Raw/<round>/     original NISR distribution, still zipped. EICV7's sections
                       use the F-number scheme (F1..F21) that EICV7_FILES maps.
      Cleaned/         one harmonised person-level file per round, built by the
                       project's own Stata pipeline (EICV3_clean.dta etc).
      Merged Panel/    the pooled cross-section and the EICV3-4 panel.

    An earlier version applied the F-number matcher to everything and rejected
    every cleaned file, because those names carry no F-number. Files are now
    routed by which subfolder they sit in.
    """
    import pyreadstat

    src = NISR_ROOT / "Household-Living-Conditions-EICV"
    if not src.exists():
        _log(f"eicv: {src} not found - skipping")
        return {}

    files = sorted(p for p in src.glob("**/*")
                   if p.suffix.upper() in {".DTA", ".SAV"})
    if not files:
        _log("eicv: no .dta/.sav found (Raw/ rounds are still zipped) - skipping")
        return {}

    _log(f"eicv: {len(files)} file(s)")
    districts = load_districts()
    key_to_id = dict(zip(districts["district_key"], districts["district_id"]))

    out: dict[str, pd.DataFrame] = {}
    for fp in files:
        parts = {x.lower() for x in fp.relative_to(src).parts}
        if "cleaned" in parts:
            kind, unit = "cleaned", fp.stem.replace("_clean", "").lower()
        elif "merged panel" in parts:
            kind, unit = "merged", fp.stem.lower()
        else:
            unit = _eicv7_unit(fp)
            if unit is None:
                _log(f"  ? {fp.name}: raw file with no recognised F-number, skipping")
                continue
            kind = "raw"

        df = None
        reader = pyreadstat.read_dta if fp.suffix.upper() == ".DTA" else pyreadstat.read_sav
        for enc in (None, "latin1", "cp1252"):
            try:
                kw = {"apply_value_formats": True}
                if enc:
                    kw["encoding"] = enc
                df, _ = reader(fp, **kw)
                break
            except Exception as exc:  # noqa: BLE001
                last = exc
        if df is None:
            _log(f"  ! {fp.name}: {str(last)[:70]}")
            continue

        dcol = next((c for c in df.columns if str(c).strip().lower() == "district"), None)
        if dcol:
            df["district_key"] = df[dcol].map(normalise_name)
            df["district_id"] = df["district_key"].map(key_to_id)
            n = df["district_id"].notna().sum()
            geo = f"{n:,}/{len(df):,} geocoded"
        else:
            geo = "no district column"

        df["source_file"] = fp.name
        out[f"{kind}_{unit}"] = df
        dest = PROC / f"eicv_{kind}_{normalise_name(unit)[:50]}.csv"
        df.to_csv(dest, index=False)
        _log(f"  [{kind:7s}] {fp.name[:38]:40s} {len(df):>8,} rows  {geo}")

    return out


def build_eicv7_district_welfare(poverty: pd.DataFrame) -> pd.DataFrame:
    """Collapse the EICV7 poverty file to district-level welfare indicators.

    Weighting follows the distinction above: poverty rates are population-
    weighted (a headcount is a statement about people), while mean household
    consumption is household-weighted. Getting this backwards shifts poverty
    rates by several points, since poor households are larger.
    """
    if "district_id" not in poverty.columns:
        _log("  ! poverty file has no district_id; skipping district welfare")
        return pd.DataFrame()

    df = poverty.copy()
    hw = df[EICV7_HH_WEIGHT] if EICV7_HH_WEIGHT in df else pd.Series(1.0, index=df.index)
    pw = df[EICV7_POP_WEIGHT] if EICV7_POP_WEIGHT in df else hw

    def wmean(values: pd.Series, weights: pd.Series) -> float:
        m = values.notna() & weights.notna()
        return np.average(values[m], weights=weights[m]) if m.any() else np.nan

    rows = []
    for did, g in df.groupby("district_id"):
        gw, gp = hw.loc[g.index], pw.loc[g.index]
        rec = {"district_id": int(did), "n_households": len(g)}
        # Poverty status is coded as a label; treat the poor category as 1.
        for src_col, name in [("pov_jan", "poverty_rate"), ("epov_jan", "extreme_poverty_rate")]:
            if src_col in g:
                v = g[src_col]
                ind = (v.astype(str).str.strip().str.lower().str.startswith("poor").astype(float)
                       if v.dtype == object else v.astype(float))
                rec[name] = wmean(ind, gp)
        if "cons1ae" in g:
            rec["cons_pae_mean"] = wmean(g["cons1ae"], gw)
        if "sol_jan" in g:
            rec["cons_pae_jan2024"] = wmean(g["sol_jan"], gw)
        if "ae" in g:
            rec["hh_size_ae_mean"] = wmean(g["ae"], gw)
        if "member" in g:
            rec["hh_size_mean"] = wmean(g["member"], gw)
        rows.append(rec)

    out = pd.DataFrame(rows).sort_values("district_id").reset_index(drop=True)
    out["survey"] = "EICV7"
    out["survey_year"] = 2024  # EICV7 covers 2023-24; January 2024 price base
    out.to_csv(PROC / "eicv7_district_welfare.csv", index=False)
    _log(f"  -> eicv7_district_welfare.csv ({len(out)} districts)")
    return out


# --------------------------------------------------------------------------
# Other NISR surveys: REC, Establishment Survey, AHS
# --------------------------------------------------------------------------

# All four are account-gated NISR products with no public download endpoint, so
# each is read from a subdirectory of data/raw/. No variable dictionary is held
# in this repo for any of them, so files are loaded faithfully and left
# un-harmonised - the same policy applied to EICV before its dictionary arrived.
SURVEYS = {
    "rec": {
        "dir": "Establishment-Census-EC",
        "title": "Rwanda Establishment Census",
        "unit": "establishment",
        "source": "microdata.statistics.gov.rw",
        "note": "Firm-level census: employment, sector (ISIC), location, ownership.",
    },
    "est": {
        "dir": "Establishment-Census-EC",
        "title": "Establishment Survey",
        "unit": "establishment",
        "source": "microdata.statistics.gov.rw",
        "note": "Sample survey of establishments; overlaps REC but is run more often.",
    },
    "ahs": {
        "dir": "Agriculture-Survey-AHS",
        "title": "Agriculture Household Survey",
        "unit": "household / parcel / plot",
        "source": "microdata.statistics.gov.rw",
        "note": ("Carries the crop area, yield and agricultural income content "
                 "that EICV7 dropped. Often distributed alongside the Seasonal "
                 "Agriculture Survey (SAS); season files may need stacking."),
    },
    "sas": {
        "dir": "Season-Agriculture-Survey-SAS",
        "title": "Seasonal Agriculture Survey",
        "unit": "segment x plot x season",
        "source": "microdata.statistics.gov.rw",
        "note": ("Area-frame survey: the unit is a PLOT within a sampled segment, "
                 "not a household. Files split by Season A/B/C and by part. "
                 "Held: 2019, 2020."),
    },
    "lfs": {
        "dir": "Labour-Force-Survey-LFS",
        "title": "Labour Force Survey",
        "unit": "person",
        "source": "microdata.statistics.gov.rw",
        "note": ("Quarterly since 2016/17. The consistent labour series over "
                 "time - unlike the EICV employment module, which broke at "
                 "EICV7 (main-job-only capture, and the shift to the "
                 "international definition excluding own-use subsistence "
                 "agriculture). Files arrive one per quarter/round and are "
                 "loaded separately; see the stacking caveat below before "
                 "pooling them."),
    },
}


def extract_survey(key: str) -> dict[str, pd.DataFrame]:
    """Load any NISR survey registered in SURVEYS from data/raw/<dir>/.

    Generic on purpose: without a variable dictionary there is nothing reliable
    to key file identification on, so every readable file is loaded under its
    own stem. District names are normalised and joined to `district_id` whenever
    a district column is present, which is the one harmonisation that can be
    done safely sight-unseen.
    """
    import pyreadstat

    spec = SURVEYS[key]
    # Survey microdata lives outside the repo: it is licensed to the researcher
    # and far too large to sit in a git tree. NISR_ROOT is the Dropbox holdings;
    # data/raw/ is still used for open sources the pipeline downloads itself.
    base = NISR_ROOT if (NISR_ROOT / spec["dir"]).exists() else RAW
    src = base / spec["dir"]
    exts = {".DTA", ".SAV", ".CSV", ".XLSX"}
    files = sorted([p for p in src.glob("**/*") if p.suffix.upper() in exts]) if src.exists() else []

    if not files:
        _log(f"{key}: no files in data/raw/{spec['dir']}/ - skipping "
             f"({spec['title']}; request at {spec['source']})")
        return {}

    _log(f"{key}: {len(files)} file(s) - {spec['title']}")

    districts = load_districts()
    key_to_id = dict(zip(districts["district_key"], districts["district_id"]))

    out: dict[str, pd.DataFrame] = {}
    for fp in files:
        suffix = fp.suffix.upper()
        df = None
        if suffix in (".DTA", ".SAV"):
            reader = pyreadstat.read_dta if suffix == ".DTA" else pyreadstat.read_sav
            # NISR files mix encodings; try utf-8 first so clean files are not mangled.
            for enc in (None, "latin1", "cp1252"):
                try:
                    kw = {"apply_value_formats": True}
                    if enc:
                        kw["encoding"] = enc
                    df, _ = reader(fp, **kw)
                    break
                except Exception as exc:  # noqa: BLE001
                    last = exc
            if df is None:
                _log(f"  ! {fp.name}: {last}")
                continue
        else:
            try:
                df = (pd.read_csv(fp, low_memory=False) if suffix == ".CSV"
                      else pd.read_excel(fp))
            except Exception as exc:  # noqa: BLE001
                _log(f"  ! {fp.name}: {exc}")
                continue

        # Join geography where a district column exists under any common spelling.
        dcol = next((c for c in df.columns if str(c).strip().lower() == "district"), None)
        if dcol:
            df["district_key"] = df[dcol].map(normalise_name)
            df["district_id"] = df["district_key"].map(key_to_id)
            unmatched = df["district_id"].isna().sum()
            if unmatched:
                bad = sorted(df.loc[df["district_id"].isna(), dcol].dropna().astype(str).unique())[:5]
                _log(f"  ! {fp.name}: {unmatched:,} row(s) with unmatched district {bad}")
        else:
            _log(f"  . {fp.name}: no district column found; not geocoded")

        df["source_file"] = fp.name
        out[fp.stem] = df
        dest = PROC / f"{key}_{normalise_name(fp.stem)[:60]}.csv"
        df.to_csv(dest, index=False)
        _log(f"  {fp.name}: {len(df):,} rows x {df.shape[1]} cols -> {dest.name}")

    return out


# Establishment Census geography, by round. The detail DEGRADES over time:
# 2011 reaches village, 2014 reaches sector, and 2017 onward stop at district.
# Only 2011 and 2014 can therefore support sector-level work. `q1_5_1` in the
# later rounds is "Village type" (an urban/rural classification), NOT a village
# identifier - it must not be mistaken for one.
# NOTE on 2011: its ID2/ID3 are sequential WITHIN the parent unit (8 and 21
# distinct values), not the national codes, so they cannot be joined on their own
# and are left unmapped pending a concordance. 2014's ID3 IS the national sector
# code (416 distinct, 1101-5715) and matches the Census and village files exactly.
EC_GEOGRAPHY = {
    "EC_2011": {"province": "ID1", "district": "ID2", "sector": "ID3",
                "cell": "ID4", "village": "ID5"},
    "EC_2014": {"province": "ID1", "district": "ID2", "sector": "ID3"},
    "EC_2017": {"province": "q1_1", "district": "q1_2"},
    "EC_2020": {"province": "q1_1", "district": "q1_2"},
    "EC_2023": {"province": "q1_1", "district": "q1_2"},
}


def extract_rec():
    """Rwanda Establishment Census.

    Geography is renamed to the common names in EC_GEOGRAPHY so the rounds can
    be stacked, and the finest level available in each round is recorded in a
    `geo_level` column - district-level rounds must not be silently pooled with
    sector-level ones.
    """
    out = extract_survey("rec")
    if not out:
        return out

    districts = load_districts()
    key_to_id = dict(zip(districts["district_key"], districts["district_id"]))

    for stem, df in out.items():
        cols = next((v for k, v in EC_GEOGRAPHY.items() if k.lower() in stem.lower()), None)
        if cols is None:
            _log(f"  ? {stem}: no geography mapping recorded; left as-is")
            continue
        for name, src in cols.items():
            if src in df.columns:
                df[f"geo_{name}"] = df[src]
        df["geo_level"] = max(cols, key=lambda k: ["province","district","sector","cell","village"].index(k))

        if "geo_district" in df.columns:
            df["district_key"] = df["geo_district"].map(normalise_name)
            df["district_id"] = df["district_key"].map(key_to_id)
            n = df["district_id"].notna().sum()
            _log(f"  {stem}: geo to {df['geo_level'].iloc[0]}, "
                 f"{n:,}/{len(df):,} rows matched to a district")
        df.to_csv(PROC / f"rec_{normalise_name(stem)[:60]}.csv", index=False)
    return out


def extract_est():
    """Establishment Survey."""
    return extract_survey("est")


def extract_ahs():
    """Agriculture Household Survey."""
    return extract_survey("ahs")


def extract_lfs():
    """Labour Force Survey.

    Files are loaded one per quarter and NOT stacked. Pooling LFS rounds
    requires care that cannot be taken sight-unseen: sampling weights are
    round-specific and must not be summed across quarters, and question wording
    and derived-variable definitions have changed over the series. Stack
    deliberately, in analysis code, once the files are in hand.
    """
    return extract_survey("lfs")


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
# Labour extracts: pooled NISR microdata -> the tables the figures read
#
# These files used to be cut by hand in throwaway sessions, so the ISIC recode,
# the weighting and the park-exposure flag existed only as their output and
# went stale whenever the NISR/ pipelines were re-run. Everything below is that
# step, written down.
# --------------------------------------------------------------------------

GEO = Path(
    "/Users/allegrasaggese/Library/CloudStorage/Dropbox/Rwanda - TRS/data/geo-data"
)

EC_FINAL = NISR_ROOT / "Establishment-Census-EC/3_Final/EC_pooled_establishment.dta"
LFS_FINAL = NISR_ROOT / "Labour-Force-Survey-LFS/3_Final/LFS_pooled_person.dta"

# ISIC Rev.4 sections, 1-21. Both surveys code the section as an integer with
# the same numbering in every wave, so no crosswalk is needed - only a coalesce
# across the wave-specific column names.
ISIC_NAMES = {
    1: "Agriculture, forestry & fishing", 2: "Mining & quarrying",
    3: "Manufacturing", 4: "Electricity & gas", 5: "Water & waste",
    6: "Construction", 7: "Wholesale & retail trade", 8: "Transport & storage",
    9: "Accommodation & food service", 10: "Information & communication",
    11: "Finance & insurance", 12: "Real estate",
    13: "Professional & technical", 14: "Administrative & support",
    15: "Public administration", 16: "Education",
    17: "Human health & social work", 18: "Arts, entertainment & recreation",
    19: "Other service activities", 20: "Households as employers",
    21: "Extraterritorial",
}
TOURISM_ISIC = [9, 18]   # accommodation & food; arts, entertainment & recreation


def _park_exposure() -> pd.DataFrame:
    """Sector-level park exposure, collapsed to districts.

    `border_dist` is 1 where a district contains at least one sector that
    touches or lies within 1 km of a national park. It is a coarse flag - the
    treatment is defined at sector level - but the surveys only reach district,
    so it is the finest split the microdata supports.
    """
    ex = pd.read_csv(GEO / "protected-areas/sectors_park_exposure_geodatarw.csv")
    d = (ex.groupby("district_id")
           .agg(border_sectors=("border", "sum"), n_sectors=("border", "size"),
                meandist=("dist_to_park_km", "mean"))
           .reset_index().rename(columns={"district_id": "dist"}))
    d["border_dist"] = (d.border_sectors > 0).astype(int)
    return d


def _coalesce(df: pd.DataFrame, cols: list[str]) -> pd.Series:
    """First non-null across wave-specific columns, in the order given."""
    out = pd.Series(np.nan, index=df.index, dtype="float64")
    for c in cols:
        if c in df.columns:
            out = out.fillna(pd.to_numeric(df[c], errors="coerce"))
    return out


def _shares_wide(long: pd.DataFrame, value: str) -> pd.DataFrame:
    """ISIC x year share table, indexed by the label the figures parse.

    fig_economy_composition recovers the section code with
    `int(str(i).split()[0])`, so the index has to start with the number.
    """
    g = long.groupby(["year", "isic"])[value].sum().reset_index()
    g["pct"] = 100 * g[value] / g.groupby("year")[value].transform("sum")
    w = g.pivot(index="isic", columns="year", values="pct").reindex(range(1, 22))
    w.index = [f" {i}  {ISIC_NAMES[i]}" for i in w.index]
    w.columns = [int(c) for c in w.columns]
    return w


def extract_labour() -> None:
    """Build every labour table the figures read, from the pooled .dta files.

    Reads the *cleaned* output of the NISR/ pipelines (3_Final), never the raw
    survey files, so the ISIC harmonisation and pooling decisions live in one
    place and are not re-implemented here.
    """
    import pyreadstat

    _log("labour: building from pooled NISR microdata")
    out = GEO / "labour"
    out.mkdir(parents=True, exist_ok=True)
    park = _park_exposure()

    # ---- Establishment Census ------------------------------------------
    if not EC_FINAL.exists():
        _log(f"  ! {EC_FINAL.name} missing - run NISR/Establishment-Census-EC/master.py")
    else:
        cols = ["ec_year", "ec_province", "ec_district", "ec_sector", "ec_weight",
                "ec_main_activity_section", "ec_main_activity_section_2011",
                "ec_main_activity_section_2014", "ec_total_workers",
                "ec_total_workers_2011", "ec_total_workers_2014"]
        raw, _m = pyreadstat.read_dta(str(EC_FINAL), usecols=cols,
                                      apply_value_formats=False)
        ec = pd.DataFrame({
            "year": raw.ec_year.astype(int),
            "prov": pd.to_numeric(raw.ec_province, errors="coerce"),
            "dist": pd.to_numeric(raw.ec_district, errors="coerce"),
            "sector": pd.to_numeric(raw.ec_sector, errors="coerce"),
            "isic": _coalesce(raw, ["ec_main_activity_section",
                                    "ec_main_activity_section_2011",
                                    "ec_main_activity_section_2014"]),
            "emp": _coalesce(raw, ["ec_total_workers", "ec_total_workers_2011",
                                   "ec_total_workers_2014"]),
            "wt": pd.to_numeric(raw.ec_weight, errors="coerce").fillna(1.0),
        })
        ec["isic_name"] = ec.isic.map(ISIC_NAMES)
        ec["tourism"] = ec.isic.isin(TOURISM_ISIC).astype(int)
        ec = ec.merge(park[["dist", "border_dist"]], on="dist", how="left")
        ec[["year", "prov", "dist", "sector", "isic", "isic_name", "emp", "wt",
            "border_dist", "tourism"]].to_csv(out / "ec_establishments_long.csv",
                                              index=False)
        _log(f"  -> ec_establishments_long.csv ({len(ec):,} establishments)")

        v = ec.dropna(subset=["isic", "dist"])
        di = (v.groupby(["year", "dist", "isic"]).size().rename("n").reset_index())
        di["share"] = di.n / di.groupby(["year", "dist"])["n"].transform("sum")
        di.to_csv(out / "ec_district_isic.csv", index=False)
        _log(f"  -> ec_district_isic.csv ({len(di):,} rows)")

        _shares_wide(v.assign(one=1), "one").to_csv(out / "ec_isic_shares_wide.csv")
        _log("  -> ec_isic_shares_wide.csv")

    # ---- Labour Force Survey -------------------------------------------
    if not LFS_FINAL.exists():
        _log(f"  ! {LFS_FINAL.name} missing - run NISR/Labour-Force-Survey-LFS/master.py")
        return
    cols = ["lfs_year", "lfs_district", "lfs_weight", "lfs_isic_section_main_job"]
    raw, _m = pyreadstat.read_dta(str(LFS_FINAL), usecols=cols,
                                  apply_value_formats=False)
    lfs = pd.DataFrame({
        "year": raw.lfs_year.astype(int),
        "dist": pd.to_numeric(raw.lfs_district, errors="coerce"),
        "isic": pd.to_numeric(raw.lfs_isic_section_main_job, errors="coerce"),
        "wt": pd.to_numeric(raw.lfs_weight, errors="coerce").fillna(0.0),
    }).dropna(subset=["isic", "dist"])
    # Every LFS figure is weighted: the survey is a sample, unlike the census.
    lfs["workers"] = lfs.wt

    di = (lfs.groupby(["year", "dist", "isic"])["workers"].sum().reset_index())
    di["share"] = 100 * di.workers / di.groupby(["year", "dist"])["workers"].transform("sum")
    di.to_csv(out / "lfs_district_isic.csv", index=False)
    _log(f"  -> lfs_district_isic.csv ({len(di):,} rows)")

    _shares_wide(lfs, "workers").to_csv(out / "lfs_isic_shares_wide.csv")
    _log("  -> lfs_isic_shares_wide.csv")

    t = lfs.merge(park[["dist", "border_dist"]], on="dist", how="left")
    ts = (t.groupby(["year", "border_dist"])
            .apply(lambda g: pd.Series({
                "workers": g.workers.sum(),
                "tour": g.loc[g.isic.isin(TOURISM_ISIC), "workers"].sum()}),
                include_groups=False)
            .reset_index())
    ts["share"] = 100 * ts.tour / ts.workers
    ts.to_csv(out / "lfs_tourism_share.csv", index=False)
    _log("  -> lfs_tourism_share.csv")

    # ---- District worker x forest panel --------------------------------
    wide = (di.pivot_table(index=["year", "dist"], columns="isic", values="share")
              .reindex(columns=range(1, 22)))
    wide.columns = [f"lfs_isic{int(c)}_pct" for c in wide.columns]
    wide = wide.reset_index()

    fo = pd.read_csv(GEO / "forest/pop_vs_forest_by_sector.csv")
    fo = (fo.groupby("district_id")
            .agg(tc2000=("treecover2000_ha", "sum"), loss=("loss_total_ha", "sum"),
                 km2=("unit_km2", "sum"), pop_total=("pop_total", "sum"))
            .reset_index().rename(columns={"district_id": "dist"}))
    fo["loss_rate"] = 100 * fo.loss / fo.tc2000.replace(0, np.nan)
    fo["loss_per_km2"] = fo.loss / fo.km2
    fo["loss_ha"] = fo.loss
    fo["loss_ha_per_km2"] = fo.loss_per_km2

    panel = (wide.merge(fo, on="dist", how="left")
                 .merge(park[["dist", "meandist", "border_sectors", "n_sectors"]],
                        on="dist", how="left"))
    panel.to_csv(out / "district_workers_forest_panel.csv", index=False)
    _log(f"  -> district_workers_forest_panel.csv ({len(panel):,} rows)")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

SOURCES = ["boundaries", "chirps", "wdi", "dhs", "dhs_gps", "eicv",
           "rec", "est", "ahs", "sas", "lfs", "labour"]


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
    RAW.mkdir(parents=True, exist_ok=True)

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
    if "eicv" in todo:
        extract_eicv()
    if "rec" in todo:
        extract_rec()
    if "est" in todo:
        extract_est()
    if "ahs" in todo:
        extract_ahs()
    if "sas" in todo:
        extract_survey("sas")
    if "lfs" in todo:
        extract_lfs()
    if "labour" in todo:
        extract_labour()

    if not args.no_merge:
        merge_district_panel()

    _log("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
