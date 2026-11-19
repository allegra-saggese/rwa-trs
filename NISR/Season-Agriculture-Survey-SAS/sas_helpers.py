"""
sas_helpers.py -- Seasonal Agriculture Survey settings for the shared cleaning helpers (helpers/survey_cleaning.py).

Everything every survey pipeline shares (paths, logging, Stata I/O, name and label hygiene, NameTable,
Checks) lives in that file. What is specific to the Seasonal Agriculture Survey is set here, and this file re-exports
both, so the steps import from it as before.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "helpers"))
sys.path.insert(0, str(HERE.parents[1]))
import paths as P  # noqa: E402
import survey_cleaning as _shared  # noqa: E402

DATASET = "Season-Agriculture-Survey-SAS"
ACRONYMS = ["isic", "isco", "nisr", "vup", "tpr", "paye", "rra", "rdb", "rca", "psf", "rgb", "rssb", "ngo", "vat", "tin", "gdp", "hiv", "aids", "eicv", "lfs",
            "cfsva", "ahs", "sas", "phc", "gps", "psu", "ppp", "usd", "rwf", "wfp", "fao", "ilo", "ict", "tvet", "sme", "ebm", "nid", "sacco", "bnr", "mfi",
            "vsla", "fcs", "cari", "rcsi", "hdds", "wdds", "muac", "iycf", "bmi", "ddi", "eicv1", "eicv2", "eicv3", "eicv4", "eicv5", "eicv7", "pca", "rdhs", "dhs"]

_shared.configure(dataset=DATASET, here=HERE, acronyms=ACRONYMS)
from survey_cleaning import *  # noqa: E402,F401,F403

DATASET_TAG = "sas"
WAVE_YEAR = lambda w: int(str(w)[:4])
TRANSLATE_EXTRA = {}
KEY_EXTRA = {"dist_seq": ("district_sequence", "District as a within-province sequence, not an NISR code"),
             "plot_area_ha": ("plot_area_ha", "Plot area in hectares"), "crop_area_ha": ("crop_area_ha", "Crop area in hectares"),
             "harvested_area_ha": ("harvested_area_ha", "Harvested area in hectares"), "production_kg": ("production_kg", "Production in kilograms"),
             "yield_kg_ha": ("yield_kg_ha", "Yield in kilograms per hectare"), "wh_plot": ("plot_weight_shipped", "Plot weight as shipped"), "wh_sgt": ("segment_weight_shipped", "Segment weight as shipped"),
             "crop_area": ("crop_area_shipped", "Crop area as shipped"), "harvested_area": ("harvested_area_shipped", "Harvested area as shipped")}
