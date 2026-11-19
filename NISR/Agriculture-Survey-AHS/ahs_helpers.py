"""
ahs_helpers.py -- Agriculture Household Survey settings for the shared cleaning helpers (helpers/survey_cleaning.py).

Everything every survey pipeline shares (paths, logging, Stata I/O, name and label hygiene, NameTable,
Checks) lives in that file. What is specific to the Agriculture Household Survey is set here, and this file re-exports
both, so the steps import from it as before.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "helpers"))
sys.path.insert(0, str(HERE.parents[1]))
import paths as P  # noqa: E402
import survey_cleaning as _shared  # noqa: E402

DATASET = "Agriculture-Survey-AHS"
ACRONYMS = ["isic", "isco", "nisr", "vup", "tpr", "paye", "rra", "rdb", "rca", "psf", "rgb", "rssb", "ngo", "vat", "tin", "gdp", "hiv", "aids", "eicv", "lfs",
            "cfsva", "ahs", "sas", "phc", "gps", "psu", "ppp", "usd", "rwf", "wfp", "fao", "ilo", "ict", "tvet", "sme", "ebm", "nid", "sacco", "bnr", "mfi",
            "vsla", "fcs", "cari", "rcsi", "hdds", "wdds", "muac", "iycf", "bmi", "ddi", "eicv1", "eicv2", "eicv3", "eicv4", "eicv5", "eicv7", "pca", "rdhs", "dhs"]

_shared.configure(dataset=DATASET, here=HERE, acronyms=ACRONYMS)
from survey_cleaning import *  # noqa: E402,F401,F403

DATASET_TAG = "ahs"
WAVE_YEAR = lambda w: int(str(w)[:4])
TRANSLATE_EXTRA = {}
KEY_EXTRA = {"sample": ("sample", "Sample: sampled household or LSF large-scale-farmer supplement"), "hhsize_nisr": ("household_size_nisr", "Household size as shipped by NISR"),
             "pop_wt": ("population_weight", "NISR population weight"), "hh_wt": ("household_weight_nisr", "NISR household weight as shipped"),
             "pid_nisr": ("nisr_person_id", "NISR person identifier as shipped"), "hhid_nisr": ("nisr_household_id", "NISR household identifier as shipped")}
