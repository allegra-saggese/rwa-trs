# rwa-trs

Tourism, jobs and conservation in the communities bordering Rwanda's national
parks. Estimates the effect of park-based tourism and of the Tourism Revenue
Sharing (TRS) programme on local economies, and asks whether tourism-led
development raises or relieves pressure on the forest.

The unit of analysis is the **sector** (416) and, where the outcome supports it,
the **cell** (2,148). Both are joined to Census microdata through the national
administrative code scheme.

## Scripts

| Script | Does | Writes to |
|---|---|---|
| `extract.py` | Acquires, cleans and merges every source | `data/processed/` |
| `gee_extract.py` | Earth Engine layers: TMF, Dynamic World, RADD | `data/processed/` |
| `fetch_geodata_rw.py` | Rwanda national geoportal layers (ArcGIS FeatureServers) | `geo-data/` |
| `inventory.py` | Indexes every file and variable across the holdings | `docs/`, `data/processed/` |
| `summary.py` | Rainfall and WDI tables and figures | `output/tables`, `output/figures` |
| `maps.py` | Rainfall and reference choropleths | `output/maps/` |
| **`prelim_public_figures.py`** | **Every preliminary descriptive figure and map** | `output/figures/`, `output/maps/` |
| `viz_style.py` | Shared palette, fonts and loaders for the figure scripts | — |
| `variables.py` | EICV7 codebook by workstream, with a verifier | — |

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python extract.py --all && python summary.py --all && python maps.py --all
python prelim_public_figures.py --all
```

## Where the graphics come from

**`prelim_public_figures.py` generates every preliminary figure and map** — 17
outputs, all from **public data only**: NISR public-use microdata, Dynamic World,
Hansen GFC, JRC TMF, RADD, WRI SDPT, CHIRPS, WDPA and geodata.rw, GRID3, Google
Open Buildings, gridfinder, OpenStreetMap. Nothing here uses restricted RDB
programme data, and nothing here is a causal estimate — these are descriptives
for memos and grant applications.

```bash
python prelim_public_figures.py --all                    # rebuild everything
python prelim_public_figures.py --list                   # what exists, by group
python prelim_public_figures.py --group forest labour
python prelim_public_figures.py --only distance_decay
```

| Group | Outputs |
|---|---|
| `forest` | hazard_vs_tmf, distance_decay, firewood_trend, firewood_vs_grid |
| `landcover` | transition_matrices_yoy, transition_flows, transition_flows_district, landuse_stacked_district, dw_all_classes |
| `labour` | tourism_employment, economy_composition, district_trajectories, agriculture_workers_forest |
| `infrastructure` | infrastructure_vs_forest |
| `spatial` | correlation_heatmap, lisa_clusters |
| `cell` | cell_quadrants |

`output/` is gitignored: the images are reproducible from the script, so the repo
holds the code rather than the PNGs. Regenerate with `--all` after any data
change. `viz_style.py` fixes the shared conventions — park-bordering red
`#c1121f`, other navy `#1b4965`, one colour per land-cover class, and integer
year axes — so the whole set reads as one system rather than 17 separate charts.

Inputs come from the Dropbox `geo-data/` and `Publicly-Available-NISR/` folders;
those paths are set in `viz_style.py` (`GEO`, `NISR`).

## NISR microdata pipelines (`NISR/`)

The survey microdata (LFS, Census, EICV, Establishment Census, AHS, SAS, CFSVA) are
cleaned and pooled by independent Python pipelines in `NISR/` (read `NISR/README.txt`
first for survey data): one folder per survey, `python master.py` runs it top to bottom,
outputs go to the Dropbox data folder (`2_Intermediate/`, `3_Final/`). Each dataset's
codebook is the Excel workbook `CODEBOOK_<survey>.xlsx` next to that folder's `README.txt`
on Dropbox; the repository holds code and run logs only, and the processing notes (what the
NISR documentation says, every decision and why) are kept with the project memory outside
git. An eighth folder, `NISR/Harmonize/`, writes harmonised copies of every final and
appended file (common keys, labels and `h_*` concept variables) to
`Publicly-Available-NISR/Harmonized/`. The `extract.py` survey loaders predate these pipelines.

## The three measurement problems this project has to solve

Everything in the data build exists to address one of these. They are not
side-quests; each one determines whether a headline result survives.

### 1. Where are the households?

Public microdata is anonymised to coarse geography, and it differs by source:

| Source | Finest named geography |
|---|---|
| **Census (PHC)** | **sector — 416, named and coded** |
| Establishment Census 2011 / 2014 | village / **sector** |
| LFS, EICV, AHS | district only (30) |
| DHS | GPS, but displaced 2–10 km |

The Census sector code (1101–5715) matches the NISR village boundary file
**416 of 416**, which is what makes sector-level analysis possible at all. EICV
and LFS clusters are more numerous than districts but carry no place name, so
they support clustered standard errors and nothing spatial.

**Consequence:** the household-side econometrics is district-level and
non-spatial; the spatial work runs on the Census and on the environmental
layers.

### 2. What counts as treated?

`Border_s` — a sector touching or within 1 km of a national park — is
load-bearing, and the count moves with the boundary source:

| Boundary source | Border sectors | Population |
|---|---|---|
| WDPA | 51 | 1,549,299 |
| geodata.rw (authoritative, in use) | 62 | 1,925,052 |
| Population within 2 km (1 km grid) | — | **490,308** |

The third row is the point. Sectors average 64 km², so most people in a
"treated" sector live far from the boundary. The gridded population raster gives
a continuous exposure measure that does not inherit sector shape.

Boundaries are stable from the **2006 administrative reform** onward. All time
series are therefore clipped to 2006+; full-length versions are kept as
`*_full.csv`.

### 3. Is forest loss deforestation, or is it harvest?

Rwandan forest loss runs 1,200–2,100 ha/yr through 2012 and 5,500–9,100 ha/yr
from 2013. That step change is not obviously a change in deforestation
pressure — planted area correlates 0.154 with 2006–2012 loss but **0.565** with
2013–2024 loss. Rwanda planted heavily in the 1980s–90s and those stands came
due.

Separating the two requires the planted-tree layer alongside the loss layer.
Without it, a forest result is partly an estimate of eucalyptus rotation.

## Data

Full detail in [`docs/data_catalogue.md`](docs/data_catalogue.md); the paper
table is [`output/tables/data_table.tex`](output/tables/data_table.tex).

**Economic** — Census (2002/2012/2022), EICV (6 waves), LFS (2017–2025),
Establishment Census (5 rounds), AHS (2017/2020/2024), SAS (2019/2020), IBES
(provincial aggregates). Awaited: **RDB TRS project data**, the treatment
itself, and DHS GPS.

**Conservation** — Hansen forest loss (sector and cell), JRC TMF (forest
quality: undisturbed / degraded / regrowth), Dynamic World (9 land-cover
classes), RADD alerts, WRI SDPT planted trees, CHIRPS rainfall. Missing: RCMRD
land cover (portal down), animal censuses.

**Infrastructure and geography** — Google Open Buildings (5.8M footprints),
GRID3 settlements, gridfinder electricity, NISR administrative boundaries
(province → village), geodata.rw protected areas, 1 km gridded population.

Survey microdata is licensed to the researcher and lives outside this repo. The
paths are set in `extract.py:NISR_ROOT` and `inventory.py:DEFAULT_ROOT`.

## Documentation

| File | Contents |
|---|---|
| [`docs/data_catalogue.md`](docs/data_catalogue.md) | Every dataset: contents, path, years, source |
| [`docs/data_requirements.md`](docs/data_requirements.md) | Proposal table vs holdings, and the gaps |
| [`docs/geodata_audit.md`](docs/geodata_audit.md) | Spatial layers held and still needed |
| [`docs/cleaning_decisions.md`](docs/cleaning_decisions.md) | Every judgment call, dated, with reasoning |
| [`docs/eicv_rounds.md`](docs/eicv_rounds.md) | Round structure and what pools across waves |
| [`docs/variable_lists.md`](docs/variable_lists.md) | EICV7 variables by workstream (generated) |
| [`docs/data_inventory.md`](docs/data_inventory.md) | File-level index (generated) |

**Read `cleaning_decisions.md` before specifying anything.** It records the
constraints that shape what can be identified — including that rainfall shocks
are ~79% absorbed by year fixed effects.
