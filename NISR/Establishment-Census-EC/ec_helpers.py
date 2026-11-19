"""
ec_helpers.py -- Establishment Census settings for the shared cleaning helpers (helpers/survey_cleaning.py).

Everything every survey pipeline shares (paths, logging, Stata I/O, name and label hygiene, NameTable,
Checks) lives in that file. What is specific to the Establishment Census is set here, and this file re-exports
both, so the steps import from it as before.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "helpers"))
sys.path.insert(0, str(HERE.parents[1]))
import paths as P  # noqa: E402
import survey_cleaning as _shared  # noqa: E402

DATASET = "Establishment-Census-EC"
ACRONYMS = ["isic", "isco", "nisr", "vup", "tpr", "paye", "rra", "rdb", "rca", "psf", "rgb", "rssb", "ngo", "vat", "tin", "gdp", "hiv", "aids", "eicv", "lfs",
            "cfsva", "ahs", "sas", "phc", "gps", "psu", "ppp", "usd", "rwf", "wfp", "fao", "ilo", "ict", "tvet", "sme", "ebm", "nid", "sacco", "bnr", "mfi",
            "vsla", "fcs", "cari", "rcsi", "hdds", "wdds", "muac", "iycf", "bmi", "ddi", "eicv1", "eicv2", "eicv3", "eicv4", "eicv5", "eicv7", "pca", "rdhs", "dhs"]

_shared.configure(dataset=DATASET, here=HERE, acronyms=ACRONYMS)
from survey_cleaning import *  # noqa: E402,F401,F403

DATASET_TAG = "ec"
WAVE_YEAR = lambda w: int(str(w)[:4])
TRANSLATE_EXTRA = {}
KEY_EXTRA = {"key": ("nisr_establishment_key", "NISR establishment key as shipped (2011 and 2014)"),
             "year_nisr": ("nisr_year_variable", "NISR variable named year as shipped, a year-of-start group"),
             "geo_conflict_2011": ("district_name_conflict_2011", "District code disagreed with the district name; the names were used"),
             "prov_derived": ("province_derived", "Province derived from the district code where missing"),
             "cell_seq_2011": ("cell_sequence_2011", "Cell sequence within the sector as shipped"),
             "village_seq_2011": ("village_sequence_2011", "Village sequence within the cell as shipped")}
