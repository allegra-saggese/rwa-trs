# Census park regressions: status and plan

Last updated 2026-11-22. Code: `micro-analysis/census_park_regressions.py` (sections `outcomes`, `gap`, `person`, `migration`, `eicv_check`; flag `--drop-ring`) and `micro-analysis/tourism_jobs_lasso.py`. Tables go to Dropbox `output/tables/regressions/`.

## Common design

- **Data:** Rwanda Population and Housing Census microdata, 2002, 2012 and 2022. Persons are linked to their sector (umurenge). Kigali City (districts 11, 12, 13) is dropped, including everyone living there.
- **Sample:** 381 sectors outside Kigali, 62 of them park-adjacent. Park-adjacent is the `border` column in `data/harmonized/model_sector_cross.csv`, meaning the sector touches a national park boundary. 20 of the 62 touch Gishwati (17) or Mukura (3).
- **Ring:** 82 sectors that touch a park-adjacent sector but do not border a park themselves. `--drop-ring` removes them, leaving 62 park-adjacent sectors against 237 interior ones (299 in total).
- **Outcomes:** workers per 100 adults aged 16+, built in `data/harmonized/census_sector_work_per_adult.csv`.
  - Non-farm: any industry except agriculture, forestry and fishing.
  - Services: the service sections only.
  - Tourism: accommodation and food (ISIC section I) plus arts and recreation (section R). In 2002, ISIC Rev. 3 divisions 55 and 92.
  - Dividing by adults rather than by workers neutralises the change in the definition of work in 2022.
- **Inference:** standard errors are clustered by district (27 clusters). The p-values come from a wild cluster restricted bootstrap with Webb weights and B = 9,999 draws (`helpers/regression.py::fe_ols`).
- **Framing:** descriptive. The programme started in 2005, but 2002 is not treated as a pre-period and there is no shock. Each coefficient is the change, by wave, in the gap between park-adjacent and interior sectors.

## Regressions run

### Regression 1: sector-level gap

y_st = a_s + g_t + b_2012 Park_s 1[t=2012] + b_2022 Park_s 1[t=2022] + e_st

- Unit: sector x wave (381 x 3).
- Fixed effects: sector and wave only. No controls.
- Additional outcome: log adults.

**Interpretation.** b_t is the change from 2002 to t in (park-adjacent mean - interior mean), in workers per 100 adults. A negative value means park-adjacent sectors fell further behind interior sectors, or closed less of the gap, after 2002.

This is relative composition: the share of adults doing each kind of work. It does not net out population growth or migration. The log-adults outcome measures relative population growth.

| Outcome (per 100 adults) | 2012 | 2022 |
|---|---|---|
| Non-farm | -0.39 [p 0.57] | -1.32 [p 0.06] |
| Services | -0.39 [0.54] | -0.72 [0.17] |
| Tourism | -0.05 [0.39] | -0.10 [0.02] |
| Log adults | +0.06 [0.12] | +0.04 [0.51] |

For scale, national rates per 100 adults in 2022 were 20.7 non-farm, 14.6 services and 0.70 tourism.

**Without the ring** (299 sectors), 2022 coefficients:

| Outcome | 2022 |
|---|---|
| Non-farm | -1.39 [p 0.11] |
| Services | -0.67 [0.27] |
| Tourism | -0.10 [0.03] |

Log adults: +0.07 in 2012 and +0.06 in 2022. The results are unchanged without the ring, so spillover onto neighbouring sectors is not driving the comparison.

**Reading:** park-adjacent sectors lost ground on non-farm work, and on tourism work in particular, by 2022. Their population did not grow measurably slower.

### Census measure checked against the household survey

The non-farm share in the Census was compared with the same measure in the Integrated Household Living Conditions Survey (EICV) at the district level, pairing each Census wave with the nearest survey round: Census 2002 with round 2, 2012 with round 4, and 2022 with round 7. Output: `census_eicv_nonfarm_check.csv`.

- Levels correlate at 0.82-0.87 across districts.
- The Census measures about half the level the survey does, likely because the Census records only the main job.
- Changes over time correlate only at 0.35-0.46.

So the Census ranks places well, but wave-to-wave changes are noisy. This is a reason not to over-read small changes in b_t.

### Regression 2: person-level composition

y_ist = a_s + g_t + sum_t b_t Park_s 1[t] + X_ist' theta_t + e_ist

- **Outcome:** 100 x 1[person i works in category k]. Adults aged 16+.
- **Weights:** person weight / sector-wave total, so each sector-wave counts equally. Column (1) then reproduces regression 1 exactly.
- **Controls X, each interacted with wave:**
  - Age bands, with 30-34 omitted.
  - Female.
  - Urban.
  - Household size, with people in collective quarters given size 0 and their own dummy.
  - Education group, with primary omitted.
  - Marital group, with married omitted.
- **Columns:** (1) no controls; (2) controls x wave.

**Interpretation.** b_t in column (2) is the change in the gap among adults with the same observable traits. The fall from column (1) to column (2) is the part of the gap explained by who lives in park-adjacent sectors (age, sex, schooling, urban status) and by how the returns to those traits change across waves.

2022 coefficients, column (1) -> column (2):

| Outcome | No controls | Controls x wave |
|---|---|---|
| Non-farm | -1.32 | -0.65 (p 0.19) |
| Services | -0.72 | -0.16 |
| Tourism | -0.10 | -0.04 |

Composition accounts for half or more of the lag. The rest is not distinguishable from zero.

**Without the ring** (299 sectors), 2022 coefficients:

| Outcome | No controls | Controls x wave |
|---|---|---|
| Non-farm | -1.39 [p 0.11] | -0.76 [0.19] |
| Services | -0.67 [0.27] | -0.15 [0.66] |
| Tourism | -0.103 [0.03] | -0.053 [0.13] |

Same pattern as the main sample.

### Migration regression (run, both samples)

- **Data:** 2012 and 2022 only, because the 2002 previous-residence variable does not match the current boundaries.
- **Term:** Park_s x 1[t=2022], so 2012 is the base wave.
- **Mover:** previous residence in another district or abroad.
  - In 2012, "not stated" (code 999) is not counted as a move.
  - This is a lower bound, because moves within a district are not recorded.
- **Columns:**

  | Column | Level | Controls |
  |---|---|---|
  | (1) | person | none |
  | (2) | person | regression 2 controls x wave |
  | (3) | person | (2) plus mover x wave |
  | (4) | sector | none |
  | (5) | sector | the sector's share of adults who moved in, x wave |

**Interpretation.** If b_2022 shrinks from (2) to (3), or from (4) to (5), part of the 2012-2022 change in the gap comes from who moved in. Migration can itself respond to jobs, so read (3) and (5) as the gap net of who moved in, not as a causal decomposition.

Outputs: `census_park_gap_migration{,_no_ring}.csv/.tex`.

**Results, main sample** (381 sectors; 1,186,909 adults):

| Outcome | (1) person, none | (2) controls | (3) + mover | (4) sector, none | (5) + mover share |
|---|---|---|---|---|---|
| Non-farm | -0.93 [0.06] | -0.82 [0.10] | -0.67 [0.16] | -0.93 [0.06] | -0.34 [0.42] |
| Services | -0.33 [0.33] | -0.19 [0.67] | -0.06 [0.89] | -0.33 [0.33] | +0.16 [0.66] |
| Tourism | -0.046 [0.33] | -0.040 [0.44] | -0.033 [0.52] | -0.046 [0.33] | -0.017 [0.73] |

Column (1) equals regression 1's 2022 coefficient minus its 2012 coefficient (-1.32 - (-0.39) = -0.93).

**Results without the ring** (299 sectors; 916,672 adults; b_2022 is the change in the gap from 2012 to 2022; wild-bootstrap p in brackets):

| Outcome | (1) person, none | (2) controls | (3) + mover | (4) sector, none | (5) + mover share |
|---|---|---|---|---|---|
| Non-farm | -0.97 [0.10] | -0.96 [0.07] | -0.79 [0.11] | -0.97 [0.10] | -0.34 [0.51] |
| Services | -0.30 [0.43] | -0.22 [0.55] | -0.09 [0.82] | -0.30 [0.43] | +0.22 [0.57] |
| Tourism | -0.061 [0.17] | -0.057 [0.25] | -0.049 [0.32] | -0.061 [0.17] | -0.029 [0.52] |

- Column (1) equals regression 1's 2022 coefficient minus its 2012 coefficient (-1.39 - (-0.42)), as it should.
- **Person-level mover dummy, (2) -> (3):** removes about 17% of the non-farm gap. Movers are more likely to hold non-farm jobs, but individual movers explain little of the gap.
- **Sector mover share, (4) -> (5):** removes about two-thirds of the non-farm gap and all of the services gap.
- The difference between the two is what matters. The mover share picks up the sector-wide correlates of in-migration, not just the jobs held by movers themselves. Sectors that attract migrants are likely those where non-farm demand grew, so the mover share is plausibly an outcome of the same process (a bad control). Read (5) as: the 2012-2022 gap is concentrated in the sector-level variation that goes with in-migration, not as evidence that migration causes the gap.
- Standard errors differ between the person and sector levels for an identical coefficient (non-farm: 0.57 vs 0.80), while the bootstrap p-values agree. This is the degrees-of-freedom convention still to unify.

### Lasso: who holds tourism jobs (run)

- **Method:** L1-penalised logit on Census workers outside Kigali, with cross-validation folds grouped by sector. Then post-lasso weighted linear probability models with CR1 standard errors, and average effects that include the interaction terms.
- **Outcomes:**
  - 2012: tourism, accommodation, food and beverage, arts and recreation.
  - 2022: tourism, accommodation and food, arts and recreation.
- **Models:**
  - Individual: demographics, education, household assets (electricity, phone, vehicle), crops, land ownership, plus demographic interactions.
  - Exposure: adds the park border dummy, park share of the sector, and log population density, all kept unpenalised.
  - Assets are kept as predictors despite the risk of reverse causality, to test the hypothesis that better-off households find service jobs more easily.
- **Fit:** out-of-fold AUC is about 0.77 for tourism and 0.93 for 2012 accommodation.
- **Strongest predictors:**
  - Positive: education, never married, urban, grid electricity, smartphone.
  - Negative: female, farm household.
- **Park exposure:** read the border dummy and park share together. For 2012 accommodation, border is -0.057 (p 0.002) and share is +0.183 (p 0.024), so the net effect is about zero at the median share of 0.30 and positive only in sectors with a large share of park land.
- **Density:** population density matters; restaurants and bars show no park effect.
- **Outputs:** `census_tourism_jobs_lasso_*.csv` and `census_tourism_jobs_lasso_summary.tex`.

## Remaining plan

1. **Regression 5: park share as exposure intensity.** Apply to regressions 1 and 2.

   y_st = a_s + g_t + sum_t [ b_t Park_s + d_t Park_s (Share_s - Share_bar) ] 1[t] + e_st,  Share_bar = 0.29

   - Share_s > 0 only in bordering sectors, so Park_s x Share_s = Share_s. The border interaction is therefore already built in; a separate share term would be the same variable.
   - Centring at the mean share among bordering sectors makes b_t the gap for a park-adjacent sector with a typical share of park land.
   - d_t measures how the gap changes with park share. Report 0.1 d_t, the effect of 10 more percentage points of park land.
   - This lines up with the lasso finding that the border dummy and share have opposite signs.

2. **Regression 3: land use** (to discuss before building).
   - Candidate outcomes, measured on non-park land in each sector:
     - Cropland, built-up and tree-cover shares from the GLAD land-cover maps (2000, 2005, 2010, 2015, 2020).
     - Log built-up area from the Global Human Settlement Layer (GHSL).
     - Annual Hansen forest loss, 2001-2024.
   - Files are in `data/harmonized/analysis-panels/`: `sector_landcover_glclu.csv`, `sector_cropland_builtup_glclu.csv`, `sector_ghsl_built.csv`, `sector_hansen_annual.csv`.
   - Same specification as regression 1, with year fixed effects.
   - To decide:
     - Which outcomes to use.
     - Whether to match the Census waves or use every year.
     - Whether this belongs now, given the census-only scope.

3. **Regression 4: shift-share with tourism demand** (later).
   - Use the Rwanda Development Board (RDB) park permit data, by where the permits are sold.
   - Interact a park's permit sales with its adjacent sectors' exposure, estimated as a regression, not a lasso.
   - Design once the RDB data are in hand.

4. **Open decisions and housekeeping:**
   - Whether the 20 Gishwati and Mukura sectors count as park-adjacent. Gishwati and Mukura have no gorilla tourism, so one option is to run Volcanoes, Nyungwe and Akagera separately.
   - Unify the degrees-of-freedom convention for standard errors between the sector-level and person-level tables.
   - Combined standard error for border + share in the lasso.
   - Coefficient figures in R with ggplot, in AER style, one plot per file.
   - Deferred: full rebuild of the survey pipeline on the Mac; the forest scripts; rerun `public_data_figures.py --all`; Matteo to run `git pull`.
