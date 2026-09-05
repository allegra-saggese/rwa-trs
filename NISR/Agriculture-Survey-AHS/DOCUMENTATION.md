# Agricultural Household Survey (AHS) — what the documentation says and how it was applied

All 8 files in `z_Documentation/` were extracted to text and read (2026-09-04): the AHS 2017 report
(chapter 2 methodology), the questionnaires 2017, 2020 (English) and 2024, the 2020 and 2024 DDI
metadata (xml / pdf). Everything is in English.

## 1. Facts by document

### `2017/AHS_2017_agricultural_household_survey.pdf` — report, chapter 2 (methodology)
- **Open-segment approach** (FAO 1996): the SAS area frame collects plot data in closed segments; the
  AHS lists and interviews all households residing inside the segment to obtain household-based
  socio-economic and livestock data. Target population: all households, including urban ones where
  agriculture matters. **Unit of analysis = agricultural household.**
- Sample: the 960 SAS 2017 segments (PSU selected PPS, one SSU per PSU) in three agricultural strata
  (1.1 intensive agriculture on hillsides, 2.0 marshland, 3.0 rangeland) **plus 600 village segments**
  in stratum 4 (4.1 urban, 4.2 rural settlements) added so that livestock kept in villages is covered:
  **1,560 segments** (table 1 by district). Listing of all households in the segments: 23,419
  households; **16,057 households with at least one member engaged in cropping and/or livestock in
  agricultural year 2016/17** were interviewed (table 2 by district; Kigali 1,520 … East 5,649).
- Definitions: household = persons living in the same dwelling, eating together, acknowledging a head
  (polygamous spouses elsewhere, tenants eating separately, married sons, and unmarried co-residents
  with own means form separate households). "Agricultural household" is defined as a household whose
  largest income source is agriculture, but the **selection criterion at listing was any member in
  crop or livestock production**. Weights = inverse of the overall two-stage selection probability
  (strata 1.1, 2.0, 3.0) and of the village-segment selection (strata 4.1, 4.2). CSPro on tablets;
  the head answered for the household.
- Key published results used elsewhere: 2.1 million agricultural households (80.2% of all
  households), average size 4.5, 9.7 million persons, 27.8% female-headed.

### `2017/AHS_2017_questionnaire.pdf` (English)
- Sections: 0 identification; **I household members** (sex, age, relationship, schooling; for members
  **above 10 years**: highest education, main economic activity — cropping / non-farm / none —, where
  the farm activity is located, time worked on the household farm by month for seasons A and B);
  II land tenure and crops planted per season (A and B 2017); III extension services and programmes;
  IV funding; V inputs per season; VI practices; VII tools; VIII use of production, storage and
  harvest expenses; IX number of animals; X animal products and use; XI animal inputs and services.
  Reference: agricultural year 2016/17 (season A Sep-2016–Feb-2017, season B Mar–Jun 2017).

### `2020/AHS_2020_questionnaire_english.pdf` and `AHS_2020_agriculture_household_survey.xml` (DDI)
- Sections: 0; I members (activities during agricultural year 2019/20); **II land tenure, land use,
  inputs and practices** (one long section, by plot and season); III extension and programmes; **IV
  saving / credit / funding in the last 12 months — asked of members aged 16+**; V livestock numbers
  (by age class of animals); VI livestock stock change in 12 months; VII livestock products (milk,
  eggs, honey); VIII animal health, reproduction and feeding; IX animal input expenditures. The DDI
  states that the weight of a sample household is the inverse of its selection probability and that
  the unit of analysis is the agricultural household (household and individual levels).

### `2024/AHS_2024_questionnaire.pdf`, `ddi-documentation-english-123.pdf`, `AHS_2024_rahs_1.xml`
- Design: **subsample of 600 of the 1,674 EICV7 EAs**, allocated to districts in proportion to the
  number of agricultural households (RPHC-2022), selected PPS on agricultural households within
  district (urban and rural EAs combined); **all EICV7 households identified as agricultural in those
  EAs** were interviewed, so the number per EA varies. Weight = EICV7 household weight × inverse of
  the EA sub-sampling probability. Files: 14 (credits 5,224 rows, saving 10,342, …).
- Questionnaire: 0 identification; I members (roster with the **EICV7 14-code relationship list**);
  II land tenure (plot, area m², land use 95–99, owner/user members, access mode, rent, land title,
  rights); III crops grown, seeds and production (by plot × crop × season, sowing and harvest date
  codes by season); IV inputs and practices; V fruits; VI extension and programmes; VI tools; VIII
  sustainable agriculture; IX livestock numbers (12-month reference from September); X stock change;
  XI livestock products; XII animal input expenditures (last 6 months).

## 2. What was applied (2026-09-04)

| Fact | Change in the pipeline |
|---|---|
| Unit = agricultural household; selection differs (2017: any member in crop/livestock at listing in 1,560 segments; 2024: EICV7 agricultural households in 600 EICV7 EAs; 2020 undocumented beyond "inverse probability") | codebook headers state the universe per file; recorded here and in `DECISIONS.md` — the three waves are not a panel and their frames differ. |
| Age bases: economic-activity items for members above 10 (2017); savings/credit 16+ (2020) | codebook header note for the person and credits modules. |
| 16,057 agricultural households interviewed in 2017 (report table 2) | `03_checks.py` §C: 2017 household rows vs 16,057. |
| Weights: inverse selection probability (2017, 2020); EICV7 weight × sub-sampling (2024) | unchanged (`wt` as shipped; 2020 taken from section 1 as before). |
