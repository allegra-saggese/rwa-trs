# rwa-trs

Code for the Rwanda Tourism Revenue Sharing (TRS) project. The repository holds code only. All data,
results and figures live in the Dropbox folder `Rwanda - TRS`, and every script reads from and writes to
that folder.

## 1. Set up (once per machine)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Tell the code where the Dropbox folder is. Either set an environment variable:

```bash
export RWA_ROOT="/path/to/Dropbox/Rwanda - TRS"
```

or add your username and path to `ROOTS` in `paths.py`. Every folder the code uses is defined in
`paths.py` and nowhere else.

## 2. Run order

Run from the repository root. Each step only needs re-running when its inputs change.

| Step | Command | Builds |
|---|---|---|
| 1. Clean the surveys | `python NISR/master.py` and `python WB-Enterprise-Surveys/master.py` | cleaned survey files in each survey folder: `2_Intermediate/`, `3_Final/`, `4_Harmonized/` (about 1.5 hours) |
| 2. Build spatial and labour data | `python data-build-scripts/extract.py --all`, then `python data-build-scripts/build_panels.py --all` | `data/geo-data/`, `data/harmonized/labour/` |
| 3. Model panel | `python model/model_inputs.py --only model_panel` | `data/harmonized/model_*.csv` |
| 4. Sector panel | `python micro-analysis/sector_panel.py` | `data/harmonized/extracts/`, `data/harmonized/prelim/` |
| 5. Land moments | `python model/model_inputs.py --only land_moments` | land-moment panels and tables |
| 6. Descriptives | `python results-scripts/sector_descriptives.py` | figures, maps, summary tables |
| 7. Sector regressions | `python micro-analysis/sector_regressions.py` | regression tables |
| 8. Paper tables | `python micro-analysis/paper_tables.py` | journal-format tables and the write-up in `output/latex/` |
| 9. Census analysis | `python micro-analysis/census.py` | census panels, housing / education / jobs / cohort results |
| 10. Forest analysis | `python micro-analysis/forest.py` | forest-loss event study and DiD (reads JRC rasters online) |
| 11. Figures | `python results-scripts/treatment_maps.py`, `python results-scripts/STEG_figures_script.py` | treatment maps, grant-appendix figures |

Each multi-part script runs all its sections in order. `--list` shows the sections, and `--only <name>`
runs one of them.

Other scripts, run as needed:

- `summary-stat-scripts/prelim_public_figures.py --all`
- `summary-stat-scripts/summary.py --all`
- `summary-stat-scripts/maps.py --all`
- `district-level-analysis/district_models.py --all`
- `info-scripts/inventory.py` and `info-scripts/variables.py` (variable lists)
- `data-build-scripts/gee_extract.py` (needs an Earth Engine account)
- `data-build-scripts/fetch_geodata_rw.py` (downloads from the national geoportal)
- `results-scripts/make_tex_figures.py` (figures without captions for `STEG-Results.tex`)

The nightlights pipeline and its analysis (`Nighttime-Lights/`) are kept but not part of the main run.

## 3. Where things go (Dropbox `Rwanda - TRS`)

| Folder | Holds |
|---|---|
| `data/<source>/` | source data, one folder per source; nothing in the analysis writes here |
| `data/harmonized/` | everything built from the sources: panels, survey subsets, labour tables |
| `analysis/nisr-public-data-analysis/` | regression results (`reg_*.csv`) |
| `output/figures/`, `output/maps/`, `output/tables/` | figures, maps, summary and regression tables |
| `output/latex/` | write-ups (`.tex` and compiled `.pdf`) |
| `output/variable-lists/` | generated variable inventories |

Each data folder has its own `README.txt`.

## 4. Repository layout

| Folder | Holds |
|---|---|
| `paths.py` | every Dropbox path |
| `helpers/` | shared code: paths and table helpers, regressions, treatment groups |
| `NISR/`, `WB-Enterprise-Surveys/` | survey cleaning pipelines, one folder per survey |
| `data-build-scripts/` | spatial layers, labour tables, analysis panels |
| `micro-analysis/` | reduced-form analysis: `sector_panel`, `sector_regressions`, `paper_tables`, `census` (with `census/`), `forest` (with `forest/`) |
| `model/` | inputs of the 2x2 model |
| `results-scripts/` | figures and maps only (`STEG/` holds the grant-appendix modules) |
| `summary-stat-scripts/`, `district-level-analysis/`, `info-scripts/` | public-data figures, district models, variable lists |
| `Nighttime-Lights/` | nightlights pipeline and analysis (not part of the main run) |
| `docs/` | cleaning decisions, data provenance, earlier READMEs |

Run logs (`logs/`) and the files each pipeline writes between steps stay on disk and are not committed.
