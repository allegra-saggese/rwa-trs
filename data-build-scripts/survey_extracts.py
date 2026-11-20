"""
survey_extracts.py -- the survey sections of the old data-build-scripts/extract.py, held here until
it is decided where they go (each survey's own folder, or dropped).

    eicv     EICV 7 files from the NISR holdings -> eicv_cleaned_*.csv, eicv_merged_*.csv, and
             eicv7_district_welfare.csv (read by data-build/district_sources.py for the district panel)
    rec      Establishment Census, per year      -> rec_*.csv
    est, ahs, sas, lfs                           -> per-survey CSV extracts
    labour   LFS and Establishment Census industry tables from 4_Harmonized -> data/harmonized/labour/

Everything except labour writes to data/harmonized/district/. Shared helpers (logging, name
matching, district boundaries) come from data-build/district_sources.py.

Usage
-----
    python data-build-scripts/survey_extracts.py --all
    python data-build-scripts/survey_extracts.py --sources labour
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data-build"))
import paths as P  # noqa: E402
from district_sources import _log, normalise_name, load_districts, PROC, DROPBOX, NISR_ROOT  # noqa: E402,F401

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

RAW = NISR_ROOT  # fallback holdings folder of extract_survey (formerly interim-processing/raw)

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
# Labour extracts: pooled NISR microdata -> the tables the figures read
#
# These files used to be cut by hand in throwaway sessions, so the ISIC recode,
# the weighting and the park-exposure flag existed only as their output and
# went stale whenever the NISR/ pipelines were re-run. Everything below is that
# step, written down.
# --------------------------------------------------------------------------

GEO = P.GEO

# 4_Harmonized/ is the dataset of record for every NISR survey: it is the
# cleaned file the pipelines end on, and it adds the cross-survey comparable
# variables (lfs_industry_isic, lfs_employed, *_key) that 3_Final lacks.
# Always read these, never 1_Raw / 2_Intermediate / 3_Final.
EC_HARM = NISR_ROOT / "Establishment-Census-EC/4_Harmonized/H_EC_establishment.dta"
LFS_HARM = NISR_ROOT / "Labour-Force-Survey-LFS/4_Harmonized/H_LFS_person.dta"

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

    Reads 4_Harmonized, the dataset of record, never the raw
    survey files, so the ISIC harmonisation and pooling decisions live in one
    place and are not re-implemented here.
    """
    import pyreadstat

    _log("labour: building from harmonized NISR microdata (4_Harmonized)")
    out = P.HARM_LABOUR

    # The harmonised files are the partner's output and are READ-ONLY here.
    # Nothing this repo runs may write inside the NISR holdings: a derived
    # table that lands next to H_LFS_person.dta would be picked up as source
    # data by the next person to look. Enforced, not just documented.
    if NISR_ROOT in out.parents or out == NISR_ROOT:
        raise RuntimeError(
            f"refusing to write inside the NISR holdings ({out}); "
            "4_Harmonized is read-only and derived tables belong in geo-data/"
        )
    out.mkdir(parents=True, exist_ok=True)
    park = _park_exposure()

    # ---- Establishment Census ------------------------------------------
    if not EC_HARM.exists():
        _log(f"  ! {EC_HARM.name} missing - run NISR/Establishment-Census-EC/master.py then NISR/Harmonize/master.py")
    else:
        cols = ["ec_year", "ec_province", "ec_district", "ec_sector", "ec_weight",
                "ec_main_activity_section", "ec_main_activity_section_2011",
                "ec_main_activity_section_2014", "ec_total_workers",
                "ec_total_workers_2011", "ec_total_workers_2014"]
        raw, _m = pyreadstat.read_dta(str(EC_HARM), usecols=cols,
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
    if not LFS_HARM.exists():
        _log(f"  ! {LFS_HARM.name} missing - run NISR/Labour-Force-Survey-LFS/master.py then NISR/Harmonize/master.py")
        return
    cols = ["lfs_year", "lfs_district", "lfs_weight", "lfs_industry_isic"]
    raw, _m = pyreadstat.read_dta(str(LFS_HARM), usecols=cols,
                                  apply_value_formats=False)
    lfs = pd.DataFrame({
        "year": raw.lfs_year.astype(int),
        "dist": pd.to_numeric(raw.lfs_district, errors="coerce"),
        "isic": pd.to_numeric(raw.lfs_industry_isic, errors="coerce"),
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



SOURCES = ["eicv", "rec", "est", "ahs", "sas", "lfs", "labour"]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sources", nargs="+", choices=SOURCES, help="subset of sources to build")
    p.add_argument("--all", action="store_true", help="build every source")
    args = p.parse_args(argv)
    if not args.sources and not args.all:
        p.print_help()
        return 1
    todo = SOURCES if args.all else args.sources
    PROC.mkdir(parents=True, exist_ok=True)
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
    _log("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
