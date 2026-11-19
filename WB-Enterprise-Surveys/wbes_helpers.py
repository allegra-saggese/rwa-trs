"""
wbes_helpers.py -- World Bank Enterprise Survey settings for the shared cleaning helpers (helpers/survey_cleaning.py).

Everything every survey pipeline shares (paths, logging, Stata I/O, name and label hygiene, NameTable,
Checks) lives in that file. What is specific to the World Bank Enterprise Survey is set here, and this file re-exports
both, so the steps import from it as before.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[0] / "helpers"))
sys.path.insert(0, str(HERE.parents[0]))
import paths as P  # noqa: E402
import survey_cleaning as _shared  # noqa: E402

DATASET = "WB-Enterprise-Surveys"
ACRONYMS = ["isic", "isco", "nisr", "vup", "tpr", "paye", "rra", "rdb", "rca", "psf", "rgb", "rssb", "ngo", "vat", "tin", "gdp", "hiv", "aids", "eicv", "lfs",
            "cfsva", "ahs", "sas", "phc", "gps", "psu", "ppp", "usd", "rwf", "wfp", "fao", "ilo", "ict", "tvet", "sme", "ebm", "nid", "sacco", "bnr", "mfi",
            "vsla", "fcs", "cari", "rcsi", "hdds", "wdds", "muac", "iycf", "bmi", "ddi", "eicv1", "eicv2", "eicv3", "eicv4", "eicv5", "eicv7", "pca", "rdhs", "dhs"]

_shared.configure(dataset=DATASET, here=HERE, acronyms=ACRONYMS, data_root=P.DATA, run_env="WBES_RUN_ID")
from survey_cleaning import *  # noqa: E402,F401,F403

DATASET_TAG = "wbes"
WAVE_YEAR = lambda w: int(str(w)[:4])
TRANSLATE_EXTRA = {}
KEY_EXTRA = {"idstd": ("establishment_id", "World Bank standard firm identifier, unique across countries and rounds"),
             "id": ("country_firm_id", "Firm identifier of the round as issued by the survey firm"),
             "panelid": ("panel_id", "Firm identifier shared across rounds by the World Bank panel"),
             "panel": ("panel_rounds", "Rounds in which the firm was interviewed"),
             "strata": ("stratum", "Sampling stratum: industry by size by region"),
             "stratificationregioncode": ("stratum_region", "Stratification region code"),
             "wstrict": ("weight", "Sampling weight under strict eligibility (the World Bank's default)"),
             "wmedian": ("weight_median", "Sampling weight under the median eligibility assumption"),
             "wweak": ("weight_weak", "Sampling weight under the weak eligibility assumption"),
             "a1": ("country_code", "Country code (33 = Rwanda)"),
             "a2": ("sampling_region", "Sampling region"), "a3": ("locality_size", "Size of the locality"),
             "a3a": ("region", "Region of the establishment"),
             "a4a": ("sector_sampling", "Industry sampling sector"), "a4b": ("sector_screener", "Industry screener sector"),
             "a6a": ("size_sampling", "Sampling size class"), "a6b": ("size_screener", "Screener size class"),
             "a7": ("multi_establishment", "The establishment is part of a multi-establishment firm")}
