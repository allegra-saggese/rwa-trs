"""
district_survey_tables.py -- district-level tables built from the cleaned surveys.

Sections (python micro-analysis/district_survey_tables.py --list):
    labour_tables   LFS and Establishment Census workers and establishments by district and ISIC
                    section, from the 4_Harmonized files -> data/harmonized/labour/
                    (lfs_district_isic, lfs_isic_shares_wide, lfs_tourism_share, ec_district_isic,
                    ec_isic_shares_wide, ec_establishments_long, district_workers_forest_panel)

Formerly the labour part of data-build-scripts/extract.py. Its EICV 7 district welfare function
(never run) is archived in Dropbox _archive/code-eicv7-district-welfare-2026-11-19/. Its other survey extracts
(EICV, Establishment Census and other per-year CSVs) were read by no script and were dropped on
2026-11-19; their last outputs are in Dropbox _archive/district-survey-extracts-2026-11-19/.

Usage
-----
    python micro-analysis/district_survey_tables.py            # every section
    python micro-analysis/district_survey_tables.py --list
    python micro-analysis/district_survey_tables.py --only labour_tables
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import paths as P  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

NISR_ROOT = P.NISR
PROC = P.HARM_DISTRICT


def _log(msg: str) -> None:
    print(f"[extract] {msg}", flush=True)



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

SECTIONS = {"labour_tables": extract_labour}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--only", nargs="+", choices=list(SECTIONS), help="run these sections only")
    p.add_argument("--list", action="store_true", help="list the sections")
    args = p.parse_args(argv)
    if args.list:
        print("\n".join(SECTIONS))
        return 0
    for name in args.only or SECTIONS:
        SECTIONS[name]()
    _log("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
