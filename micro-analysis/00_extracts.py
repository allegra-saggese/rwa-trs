"""Column subsets of the cleaned survey files, saved once so the analysis scripts open them quickly.

Reads Matteo's cleaned NISR files in Dropbox (nothing about the cleaning changes) and writes one
parquet file per subset to data/harmonized/extracts/. Every row is kept; the analysis scripts apply
their own age, year and industry filters.

    python micro-analysis/00_extracts.py            # build any subset that is missing
    REDO=1 python micro-analysis/00_extracts.py     # rebuild all of them
"""
import os
import sys
from pathlib import Path

import pyreadstat

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import paths as P  # noqa: E402

N = P.NISR
SUBSETS = {
    # name: (source file, columns)
    "census_sub": (N / "Census-PHC/4_Harmonized/H_Census_person.dta",
                   ["census_year", "census_sector", "census_age", "census_weight", "census_urban",
                    "census_industry_isic", "census_industry_isic4_2012"]),
    "lfs_sub": (N / "Labour-Force-Survey-LFS/4_Harmonized/H_LFS_person.dta",
                ["lfs_year", "lfs_district", "lfs_age", "lfs_weight", "lfs_employment_status", "lfs_industry_isic",
                 "lfs_monthly_cash_income"]),
    "lfs_demo": (N / "Labour-Force-Survey-LFS/4_Harmonized/H_LFS_person.dta",
                 ["lfs_sex", "lfs_education_level_highest"]),
    "lfs_isic": (N / "Labour-Force-Survey-LFS/4_Harmonized/H_LFS_person.dta",
                 ["lfs_year", "lfs_district", "lfs_age", "lfs_weight", "lfs_isic_section_main_job",
                  "lfs_isic_2digit_main_2017_2018", "lfs_isic_main_job_2019_2021", "lfs_isic_main_job_2020",
                  "lfs_isic_two_digit_main_job"]),
    "eicv_sub": (N / "Household-Living-Conditions-EICV/4_Harmonized/H_EICV_person.dta",
                 ["eicv_year", "eicv_district", "eicv_age", "eicv_weight", "eicv_employed", "eicv_industry_isic",
                  "eicv_industry_isic_approx"]),
    "eicv_parcels": (N / "Household-Living-Conditions-EICV/2_Intermediate/appended/EICV_pooled_parcels.dta",
                     ["eicv_year", "eicv_district", "eicv_weight", "eicv_household_weight", "eicv_area_hectares_2001",
                      "eicv_surface_area", "eicv_surface_area_2006_2011", "eicv_cost_include_renting_2001",
                      "eicv_cost_rental_2006", "eicv_cost_renting_2011", "eicv_cost_renting_months_2014",
                      "eicv_cost_renting_2017"]),
    "ahs_land": (N / "Agriculture-Survey-AHS/2_Intermediate/appended/AHS_pooled_land.dta",
                 ["ahs_year", "ahs_district", "ahs_weight", "ahs_household_weight", "ahs_area_sqm_2024",
                  "ahs_pay_cash_renting_plot_2024"]),
    "sas_sub": (N / "Season-Agriculture-Survey-SAS/4_Harmonized/H_SAS_plotcrop.dta",
                ["sas_year", "sas_district", "sas_weight", "sas_crop_name", "sas_crop_area_ha", "sas_harvested_area_ha",
                 "sas_production_kg", "sas_selling_price_2018_2022", "sas_selling_price_2023_2025"]),
    "ec_sub": (N / "Establishment-Census-EC/4_Harmonized/H_EC_establishment.dta",
               ["ec_year", "ec_district", "ec_isic_section_comparable_2011", "ec_main_activity_section",
                "ec_total_workers", "ec_total_workers_2011", "ec_total_workers_2014", "ec_annual_turnover_2014",
                "ec_annual_turnover_2017_2020", "ec_annual_total_turnover_2023"]),
}

# The scripts read EICV age as eicv_age_years. The column of that name in the cleaned file is filled for 2001
# only; eicv_age (the cross-survey age in the key block) covers every round, and is what the scripts need.
RENAME = {"eicv_sub": {"eicv_age": "eicv_age_years"}}


def main():
    P.HARM_EXTRACTS.mkdir(parents=True, exist_ok=True)
    redo = os.environ.get("REDO") == "1"
    for name, (src, cols) in SUBSETS.items():
        out = P.HARM_EXTRACTS / f"{name}.parquet"
        if out.exists() and not redo:
            continue
        # apply_value_formats=False keeps codes, not labels; the scripts work with codes.
        df, _ = pyreadstat.read_dta(str(src), usecols=cols)
        df = df[cols].rename(columns=RENAME.get(name, {}))
        df.to_parquet(out, index=False)
        print(f"{name:13s} {len(df):>9,} rows x {len(cols):>2} columns  <- {src.relative_to(P.DATA)}")

    # Census population and urban share by sector and wave (all ages, Census weights; census_urban 1 = urban).
    import pandas as pd
    P.HARM_PRELIM.mkdir(parents=True, exist_ok=True)
    c = pd.read_parquet(P.HARM_EXTRACTS / "census_sub.parquet",
                        columns=["census_year", "census_sector", "census_weight", "census_urban"])
    c["w_urban"] = c.census_weight * (c.census_urban == 1)
    g = c.groupby(["census_sector", "census_year"])[["census_weight", "w_urban"]].sum()
    g.index.names = ["sid", "wave"]
    g.census_weight.rename("pop_total").reset_index().to_csv(P.HARM_PRELIM / "sector_pop_total.csv", index=False)
    (g.w_urban / g.census_weight).rename("urban_sh").reset_index().to_csv(P.HARM_PRELIM / "sector_urban_share.csv", index=False)
    print("sector_pop_total.csv, sector_urban_share.csv ->", P.HARM_PRELIM)


if __name__ == "__main__":
    main()
