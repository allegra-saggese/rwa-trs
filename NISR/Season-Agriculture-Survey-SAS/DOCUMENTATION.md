# Seasonal Agricultural Survey (SAS) — what the documentation says and how it was applied

All 33 files in `z_Documentation/` were extracted to text (2026-09-04); the English ones were read:
the 2013 questionnaires (screening season C, season A/B phase I and II, season C), the 2016 segment
screening (Kinyarwanda, header only), the 2017–2018 plot and screening questionnaires (docx), and the
2019–2025 plot and screening questionnaires (pdf). Kinyarwanda ones are listed at the end as **unread**.
No sampling or weighting report is held for the SAS; design facts come from the questionnaires and,
for 2017, from the AHS 2017 report (see `../Agriculture-Survey-AHS/DOCUMENTATION.md`).

## 1. Facts by document

### 2013 — National Agricultural Survey 2012/13 (English): screening (season C), season A/B phase I and phase II, season C
- Area-frame design: province, district, **stratum, segment, tract letter/number**, site id; the
  screening lists every tract in the segment with operator name/address, sampled plot number, land use
  (agricultural / fallow / pasture / non-agricultural with sub-type), crop, proportion code (10
  classes), season-C flags. **Phase I (planting)** per plot: plot size m², crop (own 34-code list: 1
  maize … 32 coffee, 33 pyrethrum, 34 other; 98 fallow, 99 uncultivated), crop density (11 classes),
  sowing start date code, traditional / improved seeds, expected production and harvest date.
  **Phase II (harvest)** per plot: harvest measurement, with operator type (simple farmer /
  cooperative-institution / **big farmer**). Operator characteristics (sex, age, education, resident,
  respondent relationship, activity crop/livestock, cooperative membership).
- Units are tract × plot × crop within segment; big farmers are a separate list frame.

### 2014–2016 — farm questionnaire and screening (segments, big farmers) — Kinyarwanda
- Only the structure is readable: farm questionnaire (parts 0, 2a, 2b fertiliser / pesticide, 4, 6a,
  7 — the part numbers of the shipped files), segment screening, big-farmer screening. The 2016
  segment screening header (SAS 2015/2016, season A) confirms the segment/stratum identification.

### 2017–2018 — plot questionnaire for segment (docx, English) and screening
- Identification: province, district, **stratum, segment**, plot number, plot area m², operator
  address; **part II crop planted, seeds used and production** (cropping system pure / mixed, number
  of main crops, crop name from the **101–520 code list** (101 maize … 369 tea, 511–520 fodder crops),
  crop area m², trees for plantations, seed type / quantity / cost / source, sowing date and expected
  harvest period codes by season, quantity harvested / remaining / total kg, production status codes,
  use of production: processed, sold (market type, price), consumed, wages, rent, gifts, exchange,
  seeds, fodder, stored (storage type), damaged, other); **part III inputs** (organic; inorganic type,
  unit, quantity, price, source, main crop; pesticides); **part IV practices** (erosion control,
  fences, irrigation, soil preparation); **part V land status and tenure**. Proportion / density codes
  in 10 classes; season A = September–February, season B = March–August (six-month tree windows).
- Screening: segment, stratum, grids sampled; plots by grid point; land use; crops and proportions.

### 2019–2025 — plot questionnaire (English) and small/large-scale screening
- Same parts II–V; from 2019 **farmer type: 1 small-scale (area frame), 2 large-scale farmer (LSF,
  list frame)** on every plot record; sowing-date and harvest-period codes by season A / B / C;
  production status (drought, heavy rain, …, 19 codes); market type 7 codes; storage 5 codes; 2019
  inorganic fertiliser types (NPK 17-17-17 … KCL), pesticides (Dithane … Beam).
- Screening 2022–2025: **strata 10 agricultural land on hillside, 20 marshland, 30 rangeland, 40
  mixed, 90 LSF**; segment or LSF id; farmer category (individual LSF, cooperative / company LSF,
  small farmer); number of grids sampled; per plot: grid points falling in the plot, plot size m²,
  operator address, land use **96 agricultural, 97 pasture, 98 fallow, 99 non-agricultural**,
  non-agricultural type, anti-erosion activities, agroforestry trees, fruit trees, land consolidation
  site, cropping system, number of main crops (≤ 5, ≥ 10% proportion), crop proportion and density
  codes (1 = 10–20% … 9 = 91–100%, 10 = above 100%), banana types, planted / to be harvested this
  season, expected harvest period.

## 2. What was applied (2026-09-04)

| Fact | Change in the pipeline |
|---|---|
| Unit is plot × crop within segment (area frame) or within large-scale farm (list frame); 2013 additionally tract; strata codes 10/20/30/40/90 | codebook headers state the universe per pooled file; the `stratum` value labels in the data match the screening questionnaire (10 hillside, 20 marshland, 30 rangeland, 40 mixed, 90 LSF; 0 = LSF in early files). |
| Crop code lists: own 1–34 list in 2013 (and 2014), 101–520 list from 2017; land-use codes 96–99 on the same variable in screening files | already handled (`crop` keeps the native list per wave with labels; screening land-use codes 97–99 labelled). |
| Seasons: A Sep–Feb, B Mar–Aug, C marshland dry season; date codes differ by season and year | recorded here; `season` is carried as shipped. |
| Weights: plot weights only in screening files (2017–2019) / in the production files (2020+); no weighting document | unchanged (`wt`, `wt_source`); no external total to check against. |

## 3. Not read (Kinyarwanda only)
`2014/*` (farm questionnaire, screening big farmers, screening segments), `2015/*` (same three),
`2016/SAS_2016_questionnaire_farm_kin.pdf`, `2016/SAS_2016_questionnaire_screening_big_farmer_kiny.pdf`;
`2016/SAS_2016_questionnaire_screening_segment.pdf` is also Kinyarwanda (header used only).
