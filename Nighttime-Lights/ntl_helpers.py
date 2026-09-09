"""
ntl_helpers.py -- paths, product definitions and shared helpers for the nightlights pipeline.

The dataset is built raw first (Matteo, 2026-09-08). The sensor composites are the backbone; the two
published harmonised products ride alongside as a bridge across the 2012 sensor break and as a check
on each other. That ordering matters, because the harmonised products are derived FROM the raw, so
they cannot verify it -- the informative comparison runs the other way, and each product's modelled
half can be tested against the raw it was imitating.

BACKBONE -- what the sensors actually recorded

  dmsp    DMSP-OLS version 4 annual composites, 1992-2013, 30 arc-second, digital numbers 0-63.
          Downloaded by hand from EOG, whose programmatic route is now behind a paid subscription.
          Four layers, and the distinction between the first two is the point:
            stable     cleaned; dim and ephemeral light is set to zero by design
            intercal   the same, made comparable across satellites and years (Elvidge). Raw DN are
                       NOT year-comparable without this: use it for anything spanning years.
            avgvis     the composite WITHOUT that censoring
            cfcvg      cloud-free nights behind each pixel-year
          Twelve years have two satellites flying. Both are kept, and a preferred series picks the
          one with more cloud-free coverage that year.

  viirs   VIIRS VNL version 2 annual composites, 2012 onwards, 15 arc-second, radiance.
            avg / med  mean and median radiance, background-masked. The median is robust to fires
                       and one-off flares, which matters next to parks with agricultural burning.
            cfcvg      cloud-free nights
            lit        the lit mask

  viirs_m VIIRS monthly, 2012 onwards, tile 00N060E. Same layers. This is what makes an event study
          possible; the annual composites cannot see a border closing in March.

BRIDGE -- one continuous series, at the cost of a model in the middle

  li      Li et al. (2020), extended to 2024. DMSP-scale DN. Real calibrated DMSP through 2013, then
          VIIRS converted to look like DMSP. Everything from 2014 is model output.
  chen    Chen et al. (2021) version 2, to 2025. VIIRS-like radiance. Real VIIRS from 2012, then
          DMSP back-converted. Everything before 2012 is model output.

Never average across products: they are on different scales and two of the four halves are models.
"""
import hashlib
import json
import re
import urllib.request
from pathlib import Path

DB = Path("/Users/matteo/Library/CloudStorage/Dropbox/1-Ongoing Projects/Rwanda - TRS")
DATA = DB / "data"
NTL = DATA / "Nighttime-Lights"
RAW, INTERMEDIATE, FINAL = NTL / "1_Raw", NTL / "2_Intermediate", NTL / "3_Final"
DOCS = NTL / "z_Documentation"
GEO = DATA / "geo-data"
CLIPS = GEO / "nightlights"
LOGS = Path(__file__).resolve().parent / "logs"

SECTORS = GEO / "protected-areas/sectors_park_exposure_wdpa.gpkg"
CELLS = GEO / "protected-areas/cells_park_exposure_geodatarw.gpkg"
UNITS = {"sector": (SECTORS, "sector_id"), "cell": (CELLS, "cell_id")}

YEARS = range(1992, 2027)
BBOX = (28.80, -2.90, 30.95, -1.00)               # Rwanda with a margin
SUPERSAMPLE = 4                                   # sub-pixels per pixel side, for area weighting

# What counts as lit. DMSP digital numbers are integers, so anything above zero is a detection.
# VIIRS radiance has a noise floor: below it a dark rural scene is indistinguishable from background.
FLOORS = {"dmsp": 0.0, "viirs": 0.5, "viirs_m": 0.5, "li": 0.0, "chen": 0.5}

PRODUCTS = {
    "dmsp": {
        "kind": "raw", "cadence": "annual", "unit": "digital number, 0-63",
        "short": "DMSP raw DN", "layers": {"stable", "intercal", "avgvis", "cfcvg"},
        "citation": ("Elvidge, C. et al. DMSP-OLS Nighttime Lights Time Series version 4. "
                     "Earth Observation Group, Payne Institute, Colorado School of Mines."),
        "doi": "https://eogdata.mines.edu/products/dmsp/",
    },
    "viirs": {
        "kind": "raw", "cadence": "annual", "unit": "nW/cm2/sr",
        "short": "VIIRS raw radiance", "layers": {"avg", "med", "cfcvg", "lit"},
        "citation": ("Elvidge, C., Zhizhin, M., Ghosh, T., Hsu, F.-C., Taneja, J. (2021). Annual "
                     "time series of global VIIRS nighttime lights. Remote Sensing 13(5):922."),
        "doi": "https://eogdata.mines.edu/products/vnl/",
    },
    "viirs_m": {
        "kind": "raw", "cadence": "monthly", "unit": "nW/cm2/sr",
        "short": "VIIRS monthly radiance", "layers": {"avg", "cfcvg"},
        "citation": "Earth Observation Group, VIIRS monthly cloud-free composites version 1.",
        "doi": "https://eogdata.mines.edu/products/vnl/",
    },
    "li": {
        "kind": "bridge", "cadence": "annual", "unit": "digital number, 0-63",
        "short": "Li harmonised DN", "layers": {"main"},
        "citation": ("Li, X., Zhou, Y., Zhao, M. and Zhao, X. (2020). A harmonized global nighttime "
                     "light dataset 1992-2018. Scientific Data 7:168."),
        "doi": "10.6084/m9.figshare.9828827",
    },
    "chen": {
        "kind": "bridge", "cadence": "annual", "unit": "nW/cm2/sr",
        "short": "Chen VIIRS-like radiance", "layers": {"main"},
        "citation": ("Chen, Z., Yu, B., Yang, C. et al. (2021). An extended time series (2000-2018) "
                     "of global NPP-VIIRS-like nighttime light data. ESSD 13:889. Version 2."),
        "doi": "10.7910/DVN/YGIVCD",
    },
}

# Statistics computed for every layer of every product, per unit and period.
STATS = {
    "mean": "area-weighted mean",
    "sum": "area-weighted total, pixel equivalents",
    "max": "brightest pixel",
    "lit_share": "share of area above the noise floor",
    "top": "share of the total contributed by the brightest pixel",
}
STATS_LONG = {
    "mean": "Area-weighted mean over the unit.",
    "sum": ("Area-weighted total in whole-pixel equivalents: the usual sum of lights, independent "
            "of how the unit happens to fall on the raster grid."),
    "max": "Value of the brightest single pixel intersecting the unit.",
    "lit_share": ("Share of the unit's area above the product's noise floor: zero for the digital "
                  "number products, 0.5 nW/cm2/sr for radiance."),
    "top": ("Share of the unit's total light contributed by its single brightest pixel. Computed "
            "from each whole pixel's area-weighted contribution, so it is bounded by one even where "
            "a unit is smaller than a pixel; max divided by the total is NOT bounded there."),
}

# Plain-English name for each layer, for column labels and the codebook.
LAYER_DESC = {
    "stable": "stable lights", "intercal": "intercalibrated", "avgvis": "uncensored",
    "cfcvg": "cloud-free nights", "avg": "mean radiance", "med": "median radiance",
    "lit": "lit mask", "cvg": "coverage", "main": "",
}

# The series the derived measures are built on. cf_cvg and the lit mask are excluded: the first is a
# measurement-quality weight rather than a measure of light, and the second is already a lit share.
HEADLINE = [("dmsp", "intercal"), ("dmsp", "stable"), ("dmsp", "avgvis"),
            ("viirs", "avg"), ("viirs", "med"), ("li", "main"), ("chen", "main")]

# Measures derived in 03_merge.py from the four raw statistics, for each headline series.
DERIVED = {
    "asinh": "inverse hyperbolic sine of the total",
    "pc": "total per 1,000 residents",
    "first": "first year the unit was lit",
}
DERIVED_LONG = {
    "asinh": ("Inverse hyperbolic sine of the area-weighted total. Behaves like a log at bright "
              "values and is defined at zero, which matters where most unit-years are dark."),
    "pc": ("Area-weighted total per 1,000 residents, population interpolated between the 2002, 2012 "
           "and 2022 censuses. Sectors only, and missing before 2002: interpolating a Rwandan "
           "sector's population back through 1994 is not defensible."),
    "first": ("First year in which any of the unit's area was above the noise floor, repeated down "
              "the panel. Missing for a unit never lit in that series."),
}

# Clip filenames. Bridge products carry only a year; raw DMSP also a satellite; monthly a year-month.
CLIP_PATTERNS = [
    (re.compile(r"^ntl_(dmsp)_(\w+?)_(F\d{2})_(\d{4})_rwanda\.tif$"), ("product", "layer", "sat", "period")),
    (re.compile(r"^ntl_(viirs_m)_(\w+?)_(\d{6})_rwanda\.tif$"), ("product", "layer", "period")),
    (re.compile(r"^ntl_(viirs)_(\w+?)_(\d{4})_rwanda\.tif$"), ("product", "layer", "period")),
    (re.compile(r"^ntl_(li|chen)_(\d{4})_rwanda\.tif$"), ("product", "period")),
]


def clips():
    """every Rwanda cut-out on disk, as dicts with product, layer, satellite and period"""
    out = []
    for p in sorted(CLIPS.glob("*.tif")):
        for rx, fields in CLIP_PATTERNS:
            m = rx.match(p.name)
            if not m:
                continue
            d = dict(zip(fields, m.groups()))
            d.setdefault("layer", "main")
            d.setdefault("sat", "")
            d["period"] = int(d["period"])
            d["path"] = p
            out.append(d)
            break
    return out


def sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while (b := f.read(chunk)):
            h.update(b)
    return h.hexdigest()


def get_json(url, timeout=120):
    req = urllib.request.Request(url, headers={"User-Agent": "rwa-trs-research"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def download(url, path, timeout=1800):
    req = urllib.request.Request(url, headers={"User-Agent": "rwa-trs-research"})
    path.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(req, timeout=timeout) as r, open(path, "wb") as f:
        while (b := r.read(1 << 22)):
            f.write(b)
    return path


def log(name, text):
    LOGS.mkdir(parents=True, exist_ok=True)
    (LOGS / name).write_text(text)
    print(f"log -> {LOGS / name}")
