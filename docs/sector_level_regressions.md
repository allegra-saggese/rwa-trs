# Sector-level regressions run: specification, outcomes, controls

Last updated 2026-11-24. Results: Dropbox `output/tables/regressions/`.

## Common to every regression below

- **Park** = 1 if the sector borders a national park (`border` in `model_sector_cross.csv`): 62 of the 381 sectors outside Kigali City (Nyarugenge, Gasabo, Kicukiro dropped).
- **No ring** = the same regression dropping the 82 sectors that touch a park-adjacent sector without bordering a park (299 sectors left, 62 park-adjacent).
- **Estimation:** OLS on sector panels, unweighted (each sector-wave counts once), unless stated. Absorbed fixed effects as listed.
- **Standard errors:** clustered by district (27 clusters). p-values are wild cluster restricted bootstrap (Webb weights, 9,999 draws) unless stated.
- **No sector-level covariates are used anywhere.** Time-invariant sector characteristics are absorbed by the sector fixed effects; time-varying ones (population, urban share) are themselves outcomes of the programme, so they would be bad controls. The only control used is log adults, where stated.
- **Census waves:** 2002, 2012, 2022; base wave 2002. "Adults" = residents aged 16+ (Census-weighted) except in R5 and R7 (see there).
- **Worker definitions (industry of main work):** non-farm = every industry except agriculture, forestry and fishing; services = ISIC Rev. 4 sections G-U (Rev. 3 divisions 50-99 in 2002); tourism = accommodation and food plus arts, entertainment and recreation (Rev. 3 divisions 55, 92 in 2002); farm = agriculture, forestry and fishing. In 2022 farming counts as work only if mainly for the market, so farm (and anything that includes it) falls mechanically in 2022.

## Census sector-by-wave regressions

| # | Regression | Sample (N obs) | Outcome(s) | Terms | Controls and fixed effects |
|---|---|---|---|---|---|
| R1 | Gap in rates. y_st = a_s + g_t + b_2012 Park 1[2012] + b_2022 Park 1[2022] + e | 381 sectors x 3 waves (1,143); no ring 299 (897) | Workers per 100 adults: non-farm, services, tourism. Also log adults (as an outcome) | Park x 2012, Park x 2022 | None. Sector FE, wave FE |
| R2 | Migration, sector columns (cols 4-5 of the migration table) | 2012 and 2022 only (762); no ring 598 | Workers per 100 adults: non-farm, services, tourism | Park x 2022 (2012 is the base) | Col 4: none. Col 5: sector's in-mover share (% of adults whose previous residence was another district or abroad) x 2022. Sector FE, wave FE |
| R3 | Worker counts, controlling for population. y_st = a_s + g_t + sum_t b_t Park 1[t] + lam ln(adults_st) + e; spec 2 adds d_t Park (Share - 0.29) 1[t] | 1,143 (897 no ring); farm 2002-2012 only: 762 (598); farm all three waves: 1,143 | Number of workers (Census-weighted): non-farm, services, tourism, farm | Park x 2012, Park x 2022; spec 2 adds Park share x wave (park area / sector area, centred at its mean 0.29 among park-adjacent sectors) | ln(adults) with a free coefficient. Sector FE, wave FE |
| R4 | Within-wave level gap. y_st = g_t + sum_t b_t Park 1[t] + lam ln(adults_st) + e | 1,143 (897 no ring) | Number of workers: non-farm, services, tourism, farm | Park x each of 2002, 2012, 2022 (a level difference in that wave, not a change since 2002) | ln(adults). Spec A: wave FE only (no sector FE). Spec B: wave FE and district FE |
| R5 | Gap in rates by employment status (script `census_park_status.py`) | 1,143 (897 no ring) | Workers per 100 adults by status of main work: wage employee, self-employed, family worker, other; and all workers. Uses the `sector-labour-status.csv` panel, whose adult count is 92-94% of the Census work panel's (age cutoff undocumented) | Park x 2012, Park x 2022 | None. Sector FE, wave FE |
| R6 | Logs, industry (script `census_park_logs.py`). ln(y_st) = a_s + g_t + b_t Park 1[t] + lam ln(adults_st) + e | 1,143 (897 no ring); tourism drops sectors with no tourism workers in any wave | ln(number of workers): non-farm, services, farm (OLS, bootstrap p). Tourism: number of workers, Poisson regression with log link (cluster-robust normal p, not bootstrapped) | Park x 2012, Park x 2022 | ln(adults) free coefficient. Sector FE, wave FE |
| R7 | Logs, status | 1,143 (897 no ring); "other" 1,137 (894) | ln(number of workers) for wage and self-employed (OLS); number of workers for family and other (Poisson; other drops 2 sectors with zeros) | Park x 2012, Park x 2022 | ln(adults of the status panel) free coefficient. Sector FE, wave FE |

## Sector-by-year land and exposure regressions (script `park_land_regressions.py`)

| # | Regression | Sample (N obs) | Outcome(s) | Terms | Controls and fixed effects |
|---|---|---|---|---|---|
| R8 | Land use. y_st = a_s + g_t + sum_{t>2000} b_t Park 1[t] + e | 381 sectors x years 2000, 2010, 2020 (1,143). The five-year version adds 2005 and 2015 | Cropland share and built-up share of the sector's usable (non-park) land, in percentage points (GLAD land cover); ln(1 + built-up hectares) (GHSL) | Park x 2010, Park x 2020 (2000 base) | None. Sector FE, year FE |
| R9 | Tourism exposure, land panel. (A) y = a_s + g_t + beta E_s T_t; (B) y = a_s + g_t + sum_{t>2005} b_t E_s 1[t] | 361 sectors (Gishwati-Mukura dropped) x 2005, 2010, 2015, 2020 (1,444) | Same three land outcomes as R8 | E_s x T_t (A); E_s x year, 2005 base (B). E_s = the nearest park's share of three-park visits in 2005-2019 (Volcanoes 0.40, Akagera 0.46, Nyungwe 0.14), 0 for interior sectors; T_t = national park visits in 100,000s (0.24, 0.45, 0.73, 0.36) | None. Sector FE, year FE |
| R10 | Tourism exposure, Census waves. y = a_s + g_t + sum_t b_t E_s 1[t] | 361 sectors x 3 waves (1,083) | Workers per 100 adults: non-farm, services, tourism | E_s x 2012, E_s x 2022 | None. Sector FE, wave FE |
| R11 | Gishwati-Mukura opening, land panel (park created 2015). (A) y = a_s + g_t + b GM 1[t>2015]; (B) GM x year, 2010 base | 339 sectors (319 interior + 20 bordering Gishwati or Mukura) x 2000, 2005, 2010, 2015, 2020 (1,695) | Same three land outcomes as R8 | GM x post (post = 2020 only) (A); GM x each year except 2010 (B) | None. Sector FE, year FE |
| R12 | Gishwati-Mukura opening, Census | 339 sectors x 3 waves (1,017) | Workers per 100 adults: non-farm, services, tourism | GM x 2022 (2002 and 2012 are before the opening) | None. Sector FE, wave FE |

## Question-based regressions with geographic controls (script `census_park_questions.py`)

**Design:** the Census waves are repeated cross-sections, so each regression is a separate OLS for one wave. No sector fixed effects, no base year, no change-from-baseline terms, no reweighting. The core is log-log: ln(workers) on ln(adults). Output: `census_park_questions[_no_ring].csv` (every row carries its controls and fixed effects); tables in `docs/sector_question_tables.pdf`, figures in `docs/sector_question_figures.pdf`.

Controls X (z-scored over the 381 sectors): log area; log distance to trunk/primary road; log distance to Kigali; mean elevation; mean slope; mean rainfall (CHIRPS 1981-2002). Building footprints and grid length are not used (recent snapshots, partly outcomes). Every regression has column (1) without X and column (2) with X. Clustering by district (27); p-values are wild cluster bootstrap for OLS, cluster-robust normal for Poisson.

| # | Question and regression (one per wave) | Sample | Outcomes | Terms | Controls and fixed effects |
|---|---|---|---|---|---|
| Q1 | Labour mix of park-adjacent vs interior sectors. ln(workers_s) = a_district + b Park + lam ln(adults) [+ X g] | 381 sectors (299 no ring), per wave 2002, 2012, 2022 | ln workers: non-farm, services, farm (OLS); tourism workers (Poisson) | Park | (1) ln(adults); (2) ln(adults), X. District FE |
| Q2 | Distance to the nearest of four park gates. ln(workers_s) = a_nearest park + sum_k d_k 1[bin k] + lam ln(adults) + X g [+ b Park] | as Q1 | as Q1 | Bins of centroid-to-gate distance: under 10 km (17 sectors), 10-20 (43), 20-40 (125); 40 km+ omitted (196). (2) adds Park | ln(adults), X in both. Nearest-park FE (5) |
| Q3 | Exposure to park tourism. ln(workers_s) = a_district + b E_s + lam ln(adults) [+ X g] | 361 sectors (279 no ring), Gishwati-Mukura dropped, per wave | as Q1 | E_s = nearest park's share of three-park visits 2005-2019 (Volcanoes .40, Akagera .46, Nyungwe .14), 0 for other sectors | (1) ln(adults); (2) ln(adults), X. District FE |
| Q4 | Land use. y_s = a_district + b Park [+ X g] | 381 sectors (299 no ring), per land-cover year 2000, 2010, 2020 | Cropland share and built-up share of usable land (pp, GLAD); ln(1 + built-up ha) (GHSL) | Park | (1) none; (2) X. District FE |

**Retired:** the sector-FE change-from-baseline designs (R1-R7, R10, R12 above, and an earlier version of Q2/Q4 with Park x wave and a 2002/2000 base) are no longer used. R8, R9 and R11 (land panels) are likewise superseded by Q4 for descriptive purposes. The balancing-weights version was dropped with them.

**Main results (full sample, 2022, % difference in workers, park-adjacent vs interior, same district):** without geography, services -17%, non-farm -13%, tourism -32%, farm +29% (bootstrap p 0.003-0.027); with geography, all within +-10% and p > 0.5. Q2 shows no gradient in gate distance. Q3 exposure shows the same pattern as Q1. Q4: the built-up gap is negative without X and positive with X, but p > 0.15 in every year, and it is already present in 2000, so it is not a gain.

## Not sector-level but run on the same sectors

- **Person-level composition** (`census_park_regressions.py`, section person): 1,574,787 adults. Outcome = 100 if the adult's main work is in the group, else 0 (non-farm, services, tourism). Terms Park x 2012, Park x 2022. Sector FE, wave FE; each sector-wave weighted equally. Spec 2 controls (each x wave): age band (30-34 omitted), female, urban, household size (people in collective quarters set to 0 with their own dummy), education group (primary omitted), marital group (married omitted).
- **Migration, person columns** (cols 1-3): 1,186,909 adults, 2012 and 2022. Same person controls; col 3 adds a mover indicator x 2022.
- **Tourism-jobs lasso** (`tourism_jobs_lasso.py`): not re-run in this work.

## Not run

No-ring versions of R8-R12 and of the person-level lasso.
