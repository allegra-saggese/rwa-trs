# prelim-analysis/

Preliminary descriptives and regressions for the 2x2 model (November 2026). Run the scripts in numeric order.

- Inputs: harmonised NISR files and geo-data in the Dropbox `data/` folder (paths from the repo-root `paths.py`).
- Derived sector panels: `data/Publicly-Available-NISR/Analysis/prelim/`.
- Rendered output: the Dropbox `output/` folder: `figures/`, `maps/`, `tables/summary_statistics/`,
  `tables/regressions/` (journal-style tables in `tables/regressions/journal_format/`), `writeup/`.
- Scripts refer to outputs by short ids (`fig03_...`, `T10_B_jobs`, `tab3_B_jobs`). `_common.py` maps each id to its
  descriptive file name and folder (`FIGURE_NAMES`, `TABLE_NAMES`, `JOURNAL_NAMES`). Add an entry there for any new output.
- Treatment groups come from `output/maps/maps-treat-sectors.py::classify()` in this repo.

| Script | Builds |
|---|---|
| `00_treatment_groups.py` | `treatment_groups.csv` (sector -> group, flags, nearest park) |
| `01_jobs.py` | Census 2002/12/22 sector jobs by ISIC group (workers 20-64) |
| `02_output.py` | SAS crop output (district), EC turnover (district) |
| `03a/03b_landcover_*.py` | GLCLU v2 2000/05/10/15/20 + WorldCover 2021 cropped to Rwanda; sector land use (ha); 2000->2020 transitions by group |
| `04_build_panel.py` | `sector_panel_desc.csv` (sector x wave) and `sector_cropland_builtup_glclu.csv` (sector x year: crop/built/tree/other ha and shares, ell) |
| `05_figures.py` | `figures/fig01`-`fig12` |
| `06_tables.py` | `tables/T1`-`T7` (.tex + .csv) |
| `07_land_regressions.py` | T8: four land-use regressions on services share + ln total pop (sector FE, district x wave FE, park-border x wave); ell on lambda |
| `08_tourism_definitions.py` | T9a (Census 2012 4-digit: I+R vs I+H+R vs TSA-broad), T9b + fig13 (LFS 2-digit district panel) |
| `09_section_b.py` | Section B: T10 jobs/pop, T11 land/lights, T12 robustness, T13 by park, T14 within-district wage gaps |
| `07b_land_timing_fe.py` | Table-1 fixed-effect variants (land measured after the Census) |
| `10_paper_tables.py` | Journal-style LaTeX tables -> `tables/paper/regression_tables.pdf` |
| `11a_forest_outcomes.py` | Hansen tree-cover loss by sector-year outside parks (2001-2024) |
| `11b_ghsl_built.py` | GHSL R2023A built-up surface 2000-2020 (total; NRES checked and not usable for Rwanda) |
| `11c_land_rent.py` | District rent per ha from EICV parcels (2001-2017) and AHS 2024 |
| `11d_new_outcome_regressions.py` | Tables 11-13: forest, GHSL built-up, land rent |
| `_reg.py` | FE OLS (FWL), district-clustered SE, wild cluster restricted bootstrap (Rademacher, 9,999) |

Figures: 01 jobs maps (levels + change), 02 land maps 2000-2020, 03 stacked jobs by group, 04 stacked jobs by park, 05 stacked land by group,
06 land in each treated sector 2000 vs 2020 + ell, 07 every sector's land 2020, 08 land transitions, 09 night lights by park + visitors,
10/11 district facets (EICV + LFS), 12 violins.
Tables: T1 national employment; T2 model objects by group x wave (mean/sd/p50; p10/p90 in T2_model_objects_full.csv); T3 treated vs control

## Write-up
`writeup/template.tex` holds the text, with `%%TABLE:name%%` markers. `12_writeup.py` fills the markers and writes `output/writeup/prelim_results_writeup.tex`; compile with pdflatex twice.
