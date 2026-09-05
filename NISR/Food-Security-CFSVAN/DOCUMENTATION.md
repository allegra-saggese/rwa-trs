# CFSVA — what the documentation says and how it was applied

All 32 files in `z_Documentation/` were extracted to text and the English ones read (2026-09-04):
the detailed-methodology annexes 2012, 2015, 2018, 2024; the definitions-and-computation documents
2012, 2015, 2018; the household questionnaires 2006, 2009, 2012, 2015, 2018, 2021, 2024; the woman /
child questionnaires 2009, 2012, 2015 (2018 and 2021 combined with the household form); the
community / village questionnaires 2012, 2015, 2018, 2021; the 2012 regression and WRSI notes; the
2018 assistance-type grouping. Kinyarwanda forms are listed at the end as **unread**. The 2012
`references.xls` and `cfsvans-2012-data-tables.xls` are bibliography and result tables.

## 1. Facts by document

### Detailed methodology 2012, 2015, 2018, 2024 (English annexes)
- Joint NISR / MINAGRI / WFP surveys (WFP analysis; NISR statistically responsible). **Two-stage
  cluster design representative at district level**, urban and rural, Kigali included: stage 1
  villages selected PPS within each of the 30 districts — **25 per district in 2012 and 2015, 30 in
  2018, 900 EAs (30 per district) in 2024** (2024 frame = 2022-census EAs from the 2020 mapping,
  24,339 EAs); stage 2 **10 households per village** by systematic sampling from the village list, with
  3 reserve households. Sample: 7,500 households (2012: **7,498 interviewed**; 2015: 7,500), 9,000
  (2018, 2024). Eligibility: living in the village at the time of the interview.
- Instruments: village key-informant questionnaire (2012: 748 interviews; 2015 and 2018: 749; 2024:
  900); household questionnaire (demographics, housing, assets and credit, agriculture, livelihoods,
  expenditure, food consumption and sources, shocks, coping, assistance); **woman and child
  questionnaire for women 15–49 and children under 5** (anthropometry for children 6–59 months and
  women 15–49; IYCF for children 6–23/24 months). 2012 measured 7,418 women and 4,651 children;
  2015 interviewed 6,768 women, measured 6,708 women and 3,810 children (248 flagged records removed).
- Data collection: PDAs (2012), ODK tablets (2015+); 2015 mid-April–end May (lean season before
  season-B harvest); 2018 end-February–mid-March (season-A post-harvest); 2024 26 April–2 June.
- **Weights**: design weight = inverse of (P(village) × P(household | village)), adjusted for the
  expected vs actual number of households in the village; normalised weights (design weight ÷
  (population households ÷ sample households)) used for non-complex analyses; 2024 additionally adjusts
  for non-interviews and replacements. Z-scores (WHZ, HAZ, WAZ) with ENA on 2006 WHO standards,
  WHO flags removed.

### Definitions and computation of main indicators (2012, 2015, 2018)
- Household = persons living together at least 6 months sharing at least one daily meal (NISR
  definition); head as designated. **CARI** food-security index from the food consumption score
  (FCS: 7-day food-group frequencies × weights, thresholds 21/35 or 28/42), food expenditure share
  (< 50 / 50–65 / 65–75 / > 75%) and livelihood coping strategies (stress / crisis / emergency);
  reduced coping strategies index (rCSI weights); HDDS and WDDS food groups; anthropometric indices
  (stunting, wasting, underweight, BMI); IYCF; livelihood groups; vulnerability; livelihood zones;
  wealth index (PCA on assets). 2012 adds MINAGRI land-suitability classes and the asset ownership
  by wealth quintile used for the index.

### Household questionnaires
- 2006 and 2009 (English, paper): identification (province, district, sector, cellule, enumeration
  zone, household number; 2009 also village), consent, sections on demographics (head's sex, age,
  literacy, education, marital status, spouses; member roster), housing, assets, agriculture,
  livelihoods, expenditure, food consumption (7-day recall), coping, shocks, assistance; nutrition
  module for women and children. Households skipped when refused / empty / nobody over 15 at home.
- 2012 and 2015 (English): sections 1 demographics, 2 housing and facilities, 3 livelihoods, 4
  household and productive assets, 5 agricultural production, 6 migration and remittances (12
  months), 7 credit (12 months), 8 expenditures (30 days; 2015 adds non-cash modalities), 9 food
  sources and consumption (7 days; staple source over 12 months), 10 coping strategies (7 days), 11
  shocks and food security, 12 external assistance / programme participation.
- 2018, 2021, 2024 (ODK print-outs, English): sections S0 identification … S4 agriculture (animal
  health services 12 months), S6 credit (12 months), S7 expenditure (30 days by food group, then
  non-food), food consumption, coping, shocks, assistance; 2018 and 2021 embed the mother-and-child
  nutrition module (MCHN) in the household form; 2024 uses one household form with the nutrition
  questions and separate anthropometry.
- Woman / child (2009, 2012, 2015): one module per woman 15–49 (age, literacy, education, pregnancy,
  health, hygiene, food consumption) and per child under 5 (breastfeeding, health, supplements,
  IYCF 6–24 months, measurements).
- Community / village (2012, 2015, 2018, 2021): group of key informants (village leaders, local
  government, teachers, health workers, farmers); number of households, rural / urban type,
  infrastructure, markets, crop calendar, shocks, assistance.

## 2. What was applied (2026-09-04)

| Fact | Change in the pipeline |
|---|---|
| Documented sample sizes: households 7,498 (2012), 7,500 (2015), 9,000 (2018, 2024); villages 748 (2012), 749 (2018); women 6,768 (2015) | `03_checks.py` §C: 2012, 2015, 2021, 2024 households, 2015 women and 2012 villages vs the documentation. **The shipped 2018 household file has 9,709 rows and the 2018 village file 987 rows against 9,000 / 749 documented; both are reported as informational rows and recorded in `DECISIONS.md` (NISR's file, not a pipeline artefact — the 2018 household ids are unique).** |
| Units and universes (women 15–49, children 6–59 months, key-informant groups per village) | codebook headers state the universe per pooled file. |
| Weights: design weight adjusted for village size, normalised versions; 2009 undocumented | unchanged (`wt` as shipped; 2009 unweighted, flagged). |
| District-level representativeness (25/30 villages × 10 households per district) | recorded; the coverage checks (29 / 27 / 30 districts) stay. |

## 3. Not read (Kinyarwanda only)
`2015/CFSVA_2015_enumerator_manual_kiny.pdf` (the English enumerator manual `..._eng.pdf` was skimmed:
field procedures, no variable definitions beyond the questionnaire), `2018/CFSVA_2018_hh_mchn_kin.pdf`,
`2018/CFSVA_2018_village_kin.pdf`, `2021/CFSVA_2021_hh_kin.pdf`, `2021/CFSVA_2021_village_kinyarwanda.pdf`.
`2012/CFSVA_2012_csafile.csaplan` is an SPSS complex-samples plan (strata = district, cluster = village).
