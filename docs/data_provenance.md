# Data provenance

Internal record. Where every file came from, when, and under what terms.
Not for external distribution.

Last updated: 2026-09-03

---

## GADM 4.1 — administrative boundaries

- **URL**: `https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_RWA_2.json.zip`
- **Retrieved**: 2026-09-03
- **Level**: admin-2 (district). 30 districts nested in 5 provinces.
- **CRS as delivered**: EPSG:4326
- **Licence**: free for academic use; redistribution restricted. Not committed to
  the repo — `extract.py` re-downloads.
- **Vintage**: reflects the post-2006 administrative structure. See
  `cleaning_decisions.md` on the 2006 reorganisation.

Province names ship in Kinyarwanda and without spaces (`UmujyiwaKigali`). Mapped
to English NISR conventions in `extract.py:PROVINCE_LABELS`.

## CHIRPS v2.0 — precipitation

- **URL**: `https://data.chc.ucsb.edu/products/CHIRPS-2.0/africa_monthly/tifs/`
- **Retrieved**: 2026-09-03 (2000–2024 currently built; record starts 1981)
- **Resolution**: 0.05° (~5.5 km at the equator)
- **Units**: mm/month
- **Nodata**: -9999
- **Producer**: Climate Hazards Center, UC Santa Barbara
- **Citation**: Funk et al. (2015), *Scientific Data* 2:150066
- **Licence**: public domain

The Africa window is used rather than the global product purely for download
size (~4 MB vs ~"whole planet" per month). Identical values over Rwanda.

## World Bank WDI

- **URL**: `https://api.worldbank.org/v2/country/RWA/indicator/{code}`
- **Retrieved**: 2026-09-03
- **Indicators**: see `extract.py:WDI_INDICATORS`
- **Licence**: CC BY 4.0
- **Note**: national aggregates only. Constant within a year by construction, so
  usable as controls but never as identifying variation in a district panel.

## DHS — Demographic and Health Surveys

- **Status**: NOT YET OBTAINED. Loader written, awaiting files.
- **Access**: registration + project request at dhsprogram.com
- **Rwanda rounds**: 2000, 2005, 2010, 2014-15, 2019-20
- **Licence**: licensed to the named researcher. **Redistribution prohibited** —
  `data/raw/` is gitignored for this reason.
- **Expected location**: `data/raw/dhs/`
- **Files needed**: recode `.DTA` files (HR/PR/IR/MR/KR/BR) and the GPS shapefile.

## EICV7 — Integrated Household Living Conditions Survey, 2023-24

- **Status**: variable dictionary obtained 2026-09-03; data files NOT YET OBTAINED.
- **Access**: request at microdata.statistics.gov.rw
- **Producer**: National Institute of Statistics of Rwanda
- **Licence**: NISR terms; redistribution prohibited. `data/raw/` is gitignored.
- **Expected location**: `data/raw/eicv/`
- **Dictionary**: `EICV7_2023-24_variable_dictionary.csv` (repo root), 751
  variable definitions across 21 files. This *is* committed — it is metadata,
  not respondent data.

### Structure

21 files, all sharing an identical identifier block: `hhid`, `clust`,
`province`, `district`, `strata_id`, `weight`. Because the block is identical,
files are identified by their `F`-number prefix rather than by column sniffing;
the mapping is `extract.py:EICV7_FILES`.

Core files:

| File | Unit | Contents |
|---|---|---|
| F1 | household | Analysis-ready welfare: `cons1ae`, `sol_jan`, `pov_jan`, `epov_jan`, `quintile`, poverty lines |
| F2 | person | Demographics, education (S4), labour (S6): ISCO occupation, ISIC industry, hours, earnings, contract type |
| F3 | household | Dwelling, water, energy, sanitation, internet (S5) |
| F5–F9 | household | Expenditure modules by recall period; F9 is person-level |
| F13–F17 | household | VUP social protection programmes |

### Price base

Welfare aggregates are in **January 2024 prices** (`sol_jan`, `Poverty_line`,
`Extreme_line`). Any comparison with an earlier EICV wave requires deflating to
a common base; the wave-specific price bases are not interchangeable.

### Earlier waves

EICV1–6 are not yet obtained. Variable names and definitions change
substantially across waves, so cross-wave harmonisation is deferred until those
files are in hand rather than guessed at. The current loader targets EICV7 only.

## Other NISR surveys — REC, Establishment Survey, AHS, LFS

- **Status**: NOT OBTAINED, no variable dictionary held. Generic loaders written.
- **Access**: microdata.statistics.gov.rw (account + data request)
- **Licence**: NISR terms; redistribution prohibited.
- **Expected locations**: `data/raw/rec/`, `data/raw/est/`, `data/raw/ahs/`,
  `data/raw/lfs/`
- **Loader**: `extract.py:extract_survey()`, registry in `extract.py:SURVEYS`

| Key | Survey | Unit | Why it is in scope |
|---|---|---|---|
| `rec` | Rwanda Establishment Census | establishment | Firm-level employment, ISIC sector, location, ownership — the firm side of the tourism-jobs thread |
| `est` | Establishment Survey | establishment | Sample survey overlapping REC, run more often |
| `ahs` | Agriculture Household Survey | household / parcel | Carries the crop area, yield and agricultural income content EICV7 dropped |
| `lfs` | Labour Force Survey | person | Quarterly since 2016/17; the consistent labour series over time |

Because no dictionary is held for any of these, the loader reads every file it
finds under its own stem, applies value labels where the format supports them,
and performs the one harmonisation that is safe sight-unseen: normalising a
`district` column and joining `district_id`. Nothing else is assumed.

**Verified variable lists cannot be produced for these until the dictionaries
arrive.** The EICV7 lists in `variable_lists.md` are checkable precisely because
`EICV7_2023-24_variable_dictionary.csv` is in the repo; asserting codes for REC,
AHS, EST or LFS without the equivalent would be guesswork that fails silently.

### LFS stacking caveat

LFS files arrive one per quarter and are deliberately **not** stacked by the
loader. Sampling weights are round-specific and must not be summed across
quarters, and question wording and derived-variable definitions have changed
over the series. Stack deliberately in analysis code once the files are in hand.

### REC and AHS wave coverage

Wave years for REC, the Establishment Survey and AHS are **not recorded here**
because they have not been verified against the NISR catalogue. Fill this in
from the catalogue when the data request is placed, rather than relying on
recollection.

## Terminology

"Census" is used interchangeably with "survey" in this project's description.
The data in scope is EICV7 — the household survey above. RPHC (the actual
Population and Housing Census) is **not** part of this project.
