# Purpose: Service sector, labor market and conservation
## The unit of analysis is the **sector** (416) and, where the outcome supports it,
the **cell** (2,148). Both are joined to Census microdata through the national
administrative code scheme.

## Repository layout

Folders are organised by **task**, not by pipeline stage.

| Folder | Holds |
|---|---|
| `info-scripts/` | Anything that reads variable names, metadata or dataset structure |
| `data-build-scripts/` | Acquiring and assembling data — spatial layers, remote sensing, survey extracts, and the two analysis panels |
| `summary-stat-scripts/` | Preliminary descriptive analysis: figures, maps, tables |
| `spatial-analysis-scripts/` | Spatial estimation on the sector and cell panels — **currently empty**, reserved |
| `output/` | The STEG results scripts and `STEG-Results.tex` (see "STEG results scripts" below). Not the same as the Dropbox `output/` folder, which holds rendered files |
| `district-level-analysis/` | District-year models, where the survey microdata lives |
| `interim-processing/` | Everything this repo produces on the way to an analysis file |
| `NISR/` | One cleaning pipeline per NISR survey (see below) |
| `WB-Enterprise-Surveys/` | World Bank Enterprise Survey pipeline, same shape as the NISR ones |
| `Nighttime-Lights/` | Annual nighttime lights, 2000 onwards, same shape as the NISR ones |
| `docs/` | Internal documentation — provenance, decisions, audits |
| `archive/` | Frozen copies of previous runs. Gitignored, never read by any script |

### Two rules that govern where data comes from and goes

**1. Always read `4_Harmonized/`, and never write to it.** Every NISR survey
folder on Dropbox ends in a harmonised file — `H_EC_establishment.dta`,
`H_LFS_person.dta`, and so on. That is the dataset of record. It is the cleaned
output the pipelines finish on, and it carries the cross-survey comparable
variables (`lfs_industry_isic`, `lfs_employed`, `*_key`) that the earlier stages
lack. Never read `1_Raw/`, `2_Intermediate/` or `3_Final/` for analysis.

Those files belong to the `NISR/` pipelines. **Nothing outside `NISR/` may
modify them, and nothing may write anywhere inside the NISR holdings** — a
derived table sitting next to `H_LFS_person.dta` would be read as source data by
the next person to look. Analysis reads harmonised data and writes derived
tables to `geo-data/`. `extract_labour()` enforces this and raises rather than
writing into the holdings.

`5_Analysis/` stays empty for now.

**2. Anything we generate on the way is interim.** Intermediate and processed
files this repo builds go to `interim-processing/{raw,processed}/`, which is
gitignored. Nothing intermediate is written next to the scripts.

**Dropbox `output/` folder**: Rendered figures, maps and tables
```
~/Library/CloudStorage/Dropbox/Rwanda - TRS/output/{figures,maps,tables}
```

Every path comes from **`paths.py`** at the repo root — one module, imported by
every script:

```python
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import paths as P          # P.GEO, P.NISR, P.FIGS, P.PROC, P.POP_RASTER ...
```

It follows the convention the NISR pipelines already use: `RWA_ROOT` overrides
everything, otherwise the login user picks a root from `ROOTS`. Add yourself
there and the code runs unchanged on another Mac. `P.check_writable()` is the
guard that refuses writes into the NISR holdings.

## Scripts

| Script | Does | Writes to |
|---|---|---|
| `data-build-scripts/extract.py` | Acquires, cleans and merges every source, including the labour extracts | `interim-processing/processed/`, `geo-data/labour/` |
| `data-build-scripts/gee_extract.py` | Earth Engine layers: TMF, Dynamic World, RADD | `geo-data/` |
| `data-build-scripts/fetch_geodata_rw.py` | Rwanda national geoportal layers (ArcGIS FeatureServers) | `geo-data/` |
| `info-scripts/inventory.py` | Indexes every file and variable across the holdings | `docs/` |
| `info-scripts/variables.py` | EICV7 codebook by workstream, with a verifier | `docs/` |
| **`summary-stat-scripts/prelim_public_figures.py`** | **Every preliminary descriptive figure and map** | Dropbox `output/` |
| `summary-stat-scripts/summary.py` | Rainfall and WDI tables and figures | Dropbox `output/` |
| `summary-stat-scripts/maps.py` | Rainfall and reference choropleths | Dropbox `output/maps/` |
| `data-build-scripts/build_panels.py` | **The two analysis panels**, with the denominator rules applied | `geo-data/forest/` |
| `district-level-analysis/district_models.py` | District-year models, cluster-robust + wild bootstrap | Dropbox `output/tables/` |
| `summary-stat-scripts/viz_style.py` | Shared palette, paths and loaders for the figure scripts | — |

Run everything from the repo venv so the spatial stack resolves:

```bash
python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
```

```bash
python data-build-scripts/extract.py --all
python summary-stat-scripts/prelim_public_figures.py --check
python summary-stat-scripts/prelim_public_figures.py --all
python summary-stat-scripts/summary.py --all
python summary-stat-scripts/maps.py --all
```

## Where the graphics come from

Every figure and map in the Dropbox `output/` folder is generated by a script in
this repo. Nothing is produced by hand or in a scratch session — if an image
exists, the command that rebuilds it is listed below.

**`prelim_public_figures.py` generates 32 of them.** All from **public data
only**: NISR public-use microdata, Dynamic World, Hansen GFC, JRC TMF, RADD, WRI
SDPT, CHIRPS, WDPA and geodata.rw, GRID3, Google Open Buildings, gridfinder,
OpenStreetMap. Nothing uses restricted RDB programme data, and nothing here is a
causal estimate — these are descriptives for memos and grant applications.

```bash
cd summary-stat-scripts
python prelim_public_figures.py --check                  # verify the script itself
python prelim_public_figures.py --all                    # rebuild all 32
python prelim_public_figures.py --list                   # what exists, by group
python prelim_public_figures.py --group forest labour
python prelim_public_figures.py --only distance_decay
```

Run `--check` before `--all`. It parses the file and fails on duplicate function
definitions, registry keys pointing at functions that do not exist, figure
functions nobody registered, and missing input folders. It exists because an
edit once duplicated a block and left two definitions of the same function:
Python keeps the last one, so the corrected version was shadowed by the stale
one and the rebuilt figure came out identical to the old one, with no error.

| Group | Outputs |
|---|---|
| `forest` | hazard_vs_tmf, distance_decay, firewood_trend, firewood_vs_grid, hansen_tmf_divergence, sdpt_confound, tmf_forest_quality, radd_annual, pop_vs_forest_loss |
| `landcover` | transition_matrices_yoy, transition_flows, transition_flows_district, landuse_stacked_district, dw_all_classes, dw_biennial, dw_landuse_change, landcover_change_district |
| `labour` | tourism_employment, economy_composition, district_trajectories, agriculture_workers_forest, accommodation_district, establishments_six_sectors, workers_six_sectors, isic_composition_full, isic_trends_full |
| `infrastructure` | infrastructure_vs_forest |
| `spatial` | correlation_heatmap, lisa_clusters |
| `cell` | cell_quadrants, cell_deforestation_park |
| `panel` | sector_panel_overview |

**The rainfall and country-context set lives in `summary.py` and `maps.py`** — 13
further outputs, built on the CHIRPS district panel and WDI rather than the
sector/cell spatial stack:

```bash
python summary.py --all    # rainfall_climatology, rainfall_gradient, rainfall_timeseries,
                           # drought_frequency, wdi_context + district_summary,
                           # balance_by_province, wdi_trends tables
python maps.py --all       # districts_reference, rainfall_mean, rainfall_variability,
                           # drought_rate, rainfall_facets
```

`maps.py --all` also builds `dhs_clusters`, which skips with a message until the
DHS GPS shapefile is in `interim-processing/raw/dhs/`.


## Labor extracts

`extract.py --sources labour` builds every labour table the figures read,
straight from `4_Harmonized/`:

```bash
python data-build-scripts/extract.py --sources labour --no-merge
```

| File | Rows |
|---|---|
| `ec_establishments_long.csv` | 896,710 establishments |
| `ec_district_isic.csv` | 2,611 |
| `lfs_district_isic.csv` | 4,492 |
| `ec_isic_shares_wide.csv`, `lfs_isic_shares_wide.csv` | 21 sections x years |
| `lfs_tourism_share.csv` | year x park-exposure |
| `district_workers_forest_panel.csv` | 270 |

All land in `geo-data/labour/`. The ISIC section is coalesced across the
wave-specific columns (`_2011`, `_2014`, 2017+), which code 1–21 identically, so
no crosswalk is needed. LFS is weighted throughout because it is a sample; the
Establishment Census is a census and is not. `border_dist` marks a district
containing at least one sector that touches or lies within 1 km of a park —
coarser than the sector-level treatment, but the microdata only reaches district.

## The analysis panels

`build_panels.py` builds the two files every figure and model runs on. Before
this existed they were saved output with no generating code, so nobody could
check how `hazard_pct` was constructed or rebuild them after a refresh.

```bash
python data-build-scripts/build_panels.py --all
python data-build-scripts/build_panels.py --checks      # validate, build nothing
python data-build-scripts/build_panels.py --only cell_master --fast
```

| Panel | Shape |
|---|---|
| `sector_year_panel.csv` | 416 sectors x 19 years (2006-2024) = 7,904 rows |
| `cell_master.csv` | 2,148 cells, cross-section |

`--all` runs a 14-point validation afterwards (sector and cell counts, no
duplicate keys, guards consistent, rainfall coverage) in the same spirit as the
`03_checks.py` step in each NISR pipeline. `cell_master` re-runs spatial joins
against the 543 MB buildings parquet and the 284 MB SDPT layer, so it takes a
few minutes; `--fast` reuses the previous infrastructure columns.

**The denominator rules live here, not in the figures.** Each panel carries the
measure and a usability flag together:

| Column | Meaning |
|---|---|
| `hazard_pct` / `hazard_usable` | loss_t / forest standing at start of t; unusable under 10 ha |
| `loss_rate` / `loss_rate_usable` | cumulative loss / cover in 2000; unusable under 10 ha |
| `loss_per_km2` | loss / land area — no forest denominator, never degenerate |

Do not re-derive these downstream. `docs/cleaning_decisions.md` explains which
to use for what.

## District-level models

The labour panel is **30 districts x 9 years**. That is the ceiling: LFS, EICV
and AHS are anonymised to district and only the Census reaches sector.

```bash
python district-level-analysis/district_models.py --all
python district-level-analysis/district_models.py --list
python district-level-analysis/district_models.py --only tourism_forest --no-bootstrap
```

Every model reports two p-values. **Quote `p_wild`.** With 30 clusters the CR1
asymptotics do not hold — Cameron, Gelbach & Miller put the rule of thumb near
50 — so `p_cluster` over-rejects. The gap is not hypothetical: in
`tourism_park`, `log_pop` has p_cluster 0.024 and p_wild 0.095.


## NISR microdata pipelines (`NISR/`)

The survey microdata (LFS, Census, EICV, Establishment Census, AHS, SAS, CFSVA) are
cleaned by independent Python pipelines in `NISR/` (read `NISR/README.txt` first for
survey data):
- one folder per survey; `python master.py` runs it top to bottom, and `NISR/master.py`
  runs all seven surveys and then the harmonisation step.
- outputs go to the Dropbox data folder (`2_Intermediate/`, `3_Final/`, then `4_Harmonized/`).
- codebook: each dataset's codebook is the Excel workbook `CODEBOOK_<survey>.xlsx` next to
  that folder's `README.txt` on Dropbox.
- repo: holds code and run logs only; the processing notes (what the NISR documentation
  says, every decision and why) are kept outside the repository.
- `NISR/Harmonize/` writes the harmonised copy of every final file (common keys, labels and
  `h_*` concept variables) into that dataset's own `4_Harmonized/`. **Those are the files
  analysis reads.** The `extract.py` survey loaders for EICV predate these pipelines and
  still read `1_Raw`; the labour extracts do not.

## STEG results scripts (`output/`)

`output/figures/` holds the scripts behind the STEG results document
(`output/STEG-Results.tex`) and its appendix; `output/maps/maps-treat-sectors.py` draws
the treated-sector maps. They write rendered figures to the Dropbox `output/figures/`
folder. `make_tex_figures.py` regenerates every figure without its embedded caption so
the note sits in the LaTeX instead of the image. Each script's docstring states its
inputs and outputs; the groups are:

| Group | Scripts |
|---|---|
| Census DiD (2002/2012/2022) | `bar_chart_{education,housing}.py`, `coefplot_{education,housing}.py` and `_lasso` variants (PDS-lasso control choice), `housing_inference.py`, `cohort_{education,marriage}.py`, `build_controls.py` (2002 control block), `build_jobs_panel.py`, `coefplot_jobs.py` |
| Forest | `forest_event_study_5km.py`, `coefplot_forest_5km.py`, `coefplot_jrc_forest.py` |
| Nighttime lights | `did_nightlights.py`, `event_ntl_{gates,gates_monthly,groups,monthly_prepost}.py`, `ntl_monthly_groups.py`, `ntl_engine_gates.py` (estimation engine), `ntl_intercal{,_monthly}.py` (DMSP intercalibration) |
| STEG appendix descriptives | `steg_{census_change_maps,ec_maps,employment_series,forest_jrc,ntl_gates,sas_productivity_map,tourism_series}.py` |

These scripts read analysis files (e.g. `Analysis/census_sector_education_panel.csv`)
that live outside the repo, and `STEG-Results.tex` has a hardcoded local graphics path,
so check both before running on another machine.

## Measurement review of data

### Household-level data

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

### Treatment definitions

| Boundary source | Border sectors | Population |
|---|---|---|
| WDPA | 51 | 1,549,299 |
| geodata.rw (authoritative, in use) | 62 | 1,925,052 |
| Population within 2 km (1 km grid) | — | **490,308** |

`Border_s` — a sector touching or within 1 km of a national park — is
load-bearing, and the count moves with the boundary source:

Population-points Sectors average 64 km², so most people in a
"treated" sector live far from the boundary. The gridded population raster gives
a continuous exposure measure that does not inherit sector shape.

Boundaries are stable from the **2006 administrative reform** onward. All time
series are therefore clipped to 2006+; full-length versions are kept as
`*_full.csv`.


## Data sources (review)

Full detail in [`docs/data_catalogue.md`](docs/data_catalogue.md); the paper
table is `output/tables/data_table.tex` on Dropbox.

**Economic** — Census (2002/2012/2022), EICV (6 waves), LFS (2017–2025),
Establishment Census (5 rounds), AHS (2017/2020/2024), SAS (2019/2020), IBES
(provincial aggregates). Awaited: **RDB TRS project data**, the treatment
itself, and DHS GPS.

**Conservation** — Hansen forest loss (sector and cell), JRC TMF (forest
quality: undisturbed / degraded / regrowth), Dynamic World (9 land-cover
classes), RADD alerts, WRI SDPT planted trees, CHIRPS rainfall. 
Missing: RCMRD land cover (portal down at extraction time), animal censuses (disaggregated)

**Infrastructure and geography** — Google Open Buildings (5.8M footprints),
GRID3 settlements, gridfinder electricity, NISR administrative boundaries
(province to village), geodata.rw protected areas, 1 km gridded population.

## Documentation

| File | Contents |
|---|---|
| [`docs/data_catalogue.md`](docs/data_catalogue.md) | Every dataset: contents, path, years, source |
| [`docs/data_requirements.md`](docs/data_requirements.md) | Proposal table vs holdings, and the gaps |
| [`docs/geodata_audit.md`](docs/geodata_audit.md) | Spatial layers held and still needed |
| [`docs/cleaning_decisions.md`](docs/cleaning_decisions.md) | Every judgment call, dated, with reasoning |
| [`docs/data_provenance.md`](docs/data_provenance.md) | Where each file came from, and under what licence |
| [`docs/eicv_rounds.md`](docs/eicv_rounds.md) | Round structure and what pools across waves |
| [`docs/variable_lists.md`](docs/variable_lists.md) | EICV7 variables by workstream (generated) |
| [`docs/data_inventory.md`](docs/data_inventory.md) | File-level index (generated) |

**Read `cleaning_decisions.md` before specifying anything.** 



Two docs are machine-generated and must not be hand-edited:

```bash
python info-scripts/inventory.py            # docs/data_inventory.md
python info-scripts/variables.py --export   # docs/variable_lists.md
```

`data_inventory.md` predates the current layout and should be regenerated or deleted.
