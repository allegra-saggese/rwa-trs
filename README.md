# rwa-trs

spatial and micro analysis of rwa census data

---

## Scripts

Three task-based scripts. Run in order on a fresh clone.

| Script | Does | Writes to |
|---|---|---|
| `extract.py` | Downloads open data, loads survey microdata from `data/raw/`, cleans and merges everything | `data/processed/` |
| `summary.py` | Descriptive tables, figures, graphs | `output/tables/`, `output/figures/` |
| `maps.py` | Choropleths and other spatial output | `output/maps/` |

`variables.py` is not a pipeline stage — it is the EICV7 codebook, mapping
analysis names to variable codes by workstream (labour, livelihood,
conservation). All 107 codes verify against the shipped dictionary:

```bash
python variables.py --check           # verify every code exists
python variables.py --list labour     # print one workstream
python variables.py --export          # regenerate docs/variable_lists.md
```

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Quickstart

```bash
python extract.py --all          # first run downloads ~4 GB of CHIRPS, ~25 min
python summary.py --all
python maps.py --all
```

Downloads are cached in `data/raw/` and skipped on re-run. To test on a short
window instead:

```bash
python extract.py --sources boundaries wdi chirps --start 2015 --end 2020
```

## Data sources

| Source | Access | Coverage | Status |
|---|---|---|---|
| GADM 4.1 admin-2 | open, auto-downloaded | 30 districts, 5 provinces | working |
| CHIRPS v2.0 monthly | open, auto-downloaded | 1981–present, 0.05° | working, built 2000–2024 |
| World Bank WDI | open API, auto-downloaded | national, 1960–present | working |
| EICV7 (2023-24) | **NISR account required** | 21 files, household + person | loader written, awaiting files |
| DHS recodes + GPS | **account required** | 2000, 2005, 2010, 2014-15, 2019-20 | loader written, awaiting files |
| Rwanda Establishment Census (`rec`) | **NISR account required** | establishment level | generic loader, awaiting files + dictionary |
| Establishment Survey (`est`) | **NISR account required** | establishment level | generic loader, awaiting files + dictionary |
| Agriculture Household Survey (`ahs`) | **NISR account required** | household / parcel | generic loader, awaiting files + dictionary |
| Labour Force Survey (`lfs`) | **NISR account required** | quarterly, 2016/17– | generic loader, awaiting files + dictionary |

Both survey loaders skip with an explanatory message when files are absent, so
the rest of the pipeline runs without them.

### Adding EICV7

Request at [microdata.statistics.gov.rw](https://microdata.statistics.gov.rw),
put the files in `data/raw/eicv/`, then:

```bash
python extract.py --sources eicv
```

Files are identified by their `F`-number prefix (`F1 CS_EICV7_poverty_file.dta`
→ `poverty`), per `EICV7_2023-24_variable_dictionary.csv` in the repo root. All
21 files are recognised. District names are normalised and joined to
`district_id`, so survey data lines up with the climate panel with no manual
crosswalk.

`F1` (poverty) additionally collapses to `eicv7_district_welfare.csv` —
population-weighted poverty and extreme-poverty rates, household-weighted mean
consumption per adult equivalent — which merges into `district_panel.csv`.

### Adding REC, Establishment Survey, AHS, LFS

Put files in `data/raw/rec/`, `data/raw/est/`, `data/raw/ahs/`, `data/raw/lfs/`
respectively, then:

```bash
python extract.py --sources rec est ahs lfs
```

Reads `.dta`, `.sav`, `.csv` and `.xlsx`. No variable dictionary is held for
these, so files load under their own stem with value labels applied and a
`district_id` join where a district column exists — nothing else is assumed.
Verified variable lists follow once the dictionaries arrive.

LFS quarters are **not** stacked automatically: weights are round-specific and
definitions have shifted over the series. Stack deliberately in analysis code.

### Adding DHS

Register at [dhsprogram.com](https://dhsprogram.com), put the recode `.DTA`
files and GPS shapefile in `data/raw/dhs/`, then:

```bash
python extract.py --sources dhs dhs_gps
```

## Current outputs

`district_panel.csv` — 750 district-years (30 districts × 2000–2024): rainfall
totals, within-district anomalies and percentiles, a drought indicator, area,
province, and national WDI controls.

5 figures, 5 maps, 3 tables in `output/`.

## Documentation

- [`docs/data_provenance.md`](docs/data_provenance.md) — where each file came from, when, licensing
- [`docs/cleaning_decisions.md`](docs/cleaning_decisions.md) — every judgment call, with reasoning
- [`docs/variable_lists.md`](docs/variable_lists.md) — EICV7 variables by workstream (generated)
- [`docs/eicv_rounds.md`](docs/eicv_rounds.md) — round structure and what pools across waves

**Read the second one before designing a specification.** It documents a real
constraint: rainfall shocks in Rwanda are ~79% absorbed by year fixed effects
(mean pairwise correlation of district anomalies is 0.79), which limits what a
district × year design can identify.

## Useful invocations

```bash
python maps.py --list-vars                        # what can be mapped
python maps.py --var rain_z --year 2018           # map any panel column
python summary.py --all --format pdf              # vector output for LaTeX
python extract.py --sources chirps --start 1981   # full CHIRPS record
```
