# Census (RPHC) — what the documentation says and how it was applied

Every document in `z_Documentation/` was extracted to text and the English ones read in full
(2026-09-04). This file records, per document, the facts that matter for processing and what
was changed in the pipeline because of them (the code changes are also logged in
`DECISIONS.md`). Documents in Kinyarwanda are listed at the end as **unread**.

## 1. Facts by document

### 2002 — `Census_2002_questionnaire_household.pdf` (English, 8 pp.)
- Census night 15–16 August 2002; reference period for economic activity **15 July – 15 August 2002**
  (one month, not seven days as in 2012/2022).
- Identification: province (2 digits), district/town, sector, cell, enumeration area; area of residence
  1 urban / 2 rural; type of household 100 = ordinary.
- Roster order: head, unmarried children whose mothers are not resident, first wife and her children,
  further wives, married children with spouses, unrelated children, other relatives, non-relatives,
  absent residents, then visitors. Residence status P03: 1 present resident, 2 absent resident,
  3 visitor, 4 collective household. Visitors skip everything after P06.
- Universes: P07–P13 (nationality, birthplace, duration, previous residence, languages, religion,
  handicap) residents; P14 cause of handicap if P13 ≠ 1; **P15 survival of parents: aged 25 or less**;
  P16–P20 (school attendance, highest class, specialisation, diploma, literacy) **aged 6+**;
  P21–P25 (activity situation, occupation, status, branch, institutional sector) **aged 6+**,
  P22–P25 only for the economically active (P21 = 1 employed or 2 temporarily unemployed);
  P26 marital status **residents 12+**; P27–P30 fertility **women 12+**; H01–H16 housing (ordinary
  households); deaths in the last 12 months D0–D4.
- Code lists (used for the English value labels now attached — see §2): relationship P02 (9 codes),
  languages P11 (bit-coded: Kinyarwanda 1, French 2, Swahili 4, English 8, other 16, 0 mute), religion
  P12, handicap P13 (1 none … 8 other), cause P14, survival P15 (both / mother / father / none / don't
  know), school attendance P16, level P17 (PR0-8 primary, PP1-3 post-primary, FP/FT/EG 1-7 secondary
  professional / technical / general, SU1-9 higher), diploma P19 (none, EMA, A3/D4/D5, A2/D6/D7, A1,
  A0, >A0), literacy P20, activity P21 (employed, temporarily unemployed, first job seeker, unpaid
  homekeeper, pupil/student, retired, rentier, jobless), status P23 (self-employed, employer,
  regularly paid, temporarily paid, apprentice, unpaid family worker, other), institutional sector P25
  (public, parastatal, NGO, cooperative, other private), marital P26 (never married, cohabitation,
  monogamous, polygamous man, 1st/2nd/3rd+ wife, divorced/separated, widowed), housing H01–H16.
- Occupation (P22) and branch (P24) were written in words and coded afterwards: the public file carries
  3-digit ISCO-88 and ISIC Rev.3 codes with **French** labels; no English list is in the documentation.

### 2002 — `Census_2002_questionnaire_institutional.pdf` (English)
- Collective households (police, homes for the elderly, military camps, religious communities, street
  children, schools, prisons, reception centres, hotels, centres for the disabled, hospitals,
  orphanages, refugee camps, youth centres = codes 201–214) are enumerated on a separate short form.
  The public 2002 file contains 16,717 such rows (flag `collective`), with no household id and no H-block.

### 2012 — `Census_2012_questionnaire_household.pdf` (English, 16 pp.)
- Census night 15–16 August 2012; economic-activity reference period **8–14 August 2012** (7 days);
  fertility reference 15/08/2011–15/08/2012.
- L-block: province, district, sector, cell, village, EA, area of residence (urban 1 / rural 2 on the
  form; the public file's L07 has four codes: urban, rural, peri-urban, semi-urban), building and
  household number, type of household (100 private).
- Universes (all after the roster): P07–P10 usual residents; P11 religion, P12 disability (up to six
  type/cause pairs), P13 insurance all; **P14 parental survivorship: residents under 18**; P15 birth
  registration all; **P16 literacy (sum of language codes) and P17–P19 education: residents aged 3+**;
  **P20–P28 economic activity: residents aged 5+** — P20 worked ≥1 hour in the last 7 days; if not,
  P21 reason (home worker, never worked, ever worked, on leave, retired, old age, student, other),
  P22 activities done (farming, production, services, house worker …), P23 available, P24 seeking
  (no / first job / new job); P25 occupation (ISCO-08 4-digit), P26 status in employment (employee,
  employer, self-employed, contributing family worker, producers' cooperative member, other), P27
  branch (ISIC Rev.4 4-digit), P28 institutional sector (public, private, non-profit, household) for
  those currently working or who ever worked; **P29 marital status: residents 12+** (never married,
  married, separated, widowed, divorced); P30 number of spouses (men), P31 rank as spouse (women),
  P32 age at first marriage (ever married); **P33–P36 fertility: resident women 12+**.
- H-block H01–H35 (habitat, building, tenure, materials, rooms, water, toilet, energy, stove, waste,
  sewage, assets H17–H25, internet H26–H27, livestock H28–H34, land H35); deaths M1.

### 2012 — `Census_2012_rhpc_coding_manual_20120410.pdf` (English, 40 pp.)
- Manual coding after collection: L01–L05 geographic codes from the annex; P07/P09 place of birth and
  previous residence coded as 3-digit district codes **011–057 (province × 10 + rank)** or 3xx
  country codes; P08 nationality codes (100 Rwanda, 1xx/3xx countries); P25 ISCO-08 4-digit, P27
  ISIC Rev.4 4-digit; institutional households L10 codes 201–215.
- The same district numbering (prov×10 + rank = 11…57) is the one used for the key-block `dist`.

### 2012 — `Census_2012_rhpc_edit_specs_20120405.pdf` (English, 7 pp.)
- NISR's edit and imputation rules: age imputed from date of birth when missing/inconsistent; head must
  be ≥ 12, children ≥ 12/15 years younger than the head, parents ≥ 12/15 years older; P10 duration
  forced to 999 when previous residence = birthplace; P18b years-completed capped by level (preschool 3,
  primary 6, post-primary 3, secondary 7, university 7); P19 diploma checked against level + years and
  otherwise **hot-deck imputed on (age, sex, area)**; P21–P24 blanked when P20 = 1; P21 = 4 (retired)
  under 65 and P21 = 6 (student) over 30 recoded to 7; P25/P27 invalid codes set to **9999**; fertility
  counts (P33–P36) made consistent and hot-decked. The public file carries **no imputation flags**.
- Consequence: 9/99/999/9999 are NISR's "missing" and "not applicable" codes and are kept as such
  (labelled in the value labels; never recoded to Stata missing).

### 2012 — `Census_2012_description_of_the_public_use_sample_10_data_file.pdf` (English, 2 pp.)
- 10% equal-probability sample of **private households**; only resident members (institutional
  population excluded); one case per household, one record per member; H-variables repeated on every
  member; household analysis = select P02 = 1.
- Three added variables: 5-year age group, ISCO 1-digit (rp25), ISIC section (rp27); P25 and P27 are
  4-digit codes without labels (refer to ISCO-08 / ISIC Rev.4).
- Self-weighting sample; weights needed only for totals; **analysis valid down to district level**.
- Sample: 1,038,369 persons (498,302 M / 540,067 F); 242,461 households (Kigali 28,665, South 60,364,
  West 54,345, North 39,165, East 59,922) — all used as checks in `03_checks.py` §C.

### 2012 — `Census_2012_data_quality_assessment.pdf` (English)
- Post-enumeration survey in 120 EAs: net coverage > 99%; gross under-coverage ≈ 1.5%, over-coverage
  ≈ 0.6%. Final resident population 10,515,973 (5,064,868 M / 5,451,105 F); de jure basis (present +
  absent residents); EA = village of 150–200 housing units.

### 2012 — thematic reports (English): labour force, education, population size, others
- Labour force report §2.4.4: population in **private households 10,378,021**, institutional 137,952;
  working age **16+** (national definition); "relaxed" unemployment (did not work, available, seeking
  not required) because the seeking reference period was only 7 days. NISR's recode **RP2024** is this
  activity status (verified: 1 = P20 = 1 or P21 = 3 on leave; 2/3 = did not work and available (P23 = 1)
  never/ever worked; 4 home worker; 5 retired/old; 6 student; 9 = unlabelled residual). The census
  cannot measure hours, income or informality.
- Population size report: urban share **16.5%** in 2012 (16.9% in 2002, 5.5% in 1991, 4.6% in 1978);
  NISR's 2-way recode **RL07** puts semi-urban with urban and peri-urban with rural (verified in the
  data; 16.2% in the sample vs 13.9% for L07 = 1 alone).
- Education report: literacy is reported for 15+; school ages 3–6 pre-primary, 7–12 primary, 13–18
  secondary; level of education tabulated for residents 3+.
- Glossary (labour report Annex C): residents = lived or intend to live > 6 months in the place;
  absent residents away ≤ 6 months; de jure = present + absent residents; private household = persons
  sharing at least one daily meal; institutional households include the homeless.

### 2022 — `Census_2022_questionnaire_household.pdf` (English, 10 pp.)
- Census night 15–16 August 2022; CAPI; ML-block adds foot-print number, GPS, household type
  (private / institutional), consent and non-interview reason.
- P02 relationship expanded to 14 codes (adds adoptive child, in-laws, house help, unknown); P06 marital
  status **12+** (married officially / not officially / polygamous union / divorced / separated /
  never married / widowed); P07a usual resident vs visitor, P07b slept in household (PR/AR);
  P08a–c spouses / rank / age at first marriage (12+, in union); P09–P12 birthplace, duration,
  previous residence, nationality (residents; 888 = never moved); P13 religion (11 codes); P14
  insurance; **P15–P22 disability: residents 5+**, Washington-Group scale (0 none, 1 some, 2 a lot,
  3 cannot) with aids questions, plus short stature and albinism; **P23 parents: under 18**; P24 birth
  registration; **P25–P28 identity documents: 18+ and unregistered under-18s**; P29–P31 education
  (all residents; levels ECD, nursery, primary, Ingoboka/vocational, lower secondary, upper secondary,
  tertiary; certificates 16 codes incl. TVET I–V); **P32–P36 literacy, adult literacy, internet, mobile:
  10+**; **P37–P45 employment identification: 16+** (worked ≥1 h in the last 7 days, absence, reason
  incl. COVID-19 codes, own-consumption farming, job search 4 weeks, availability); **P46–P49 job
  characteristics** (institutional sector 9 codes incl. VUP, ISIC, ISCO, status in employment 7 codes
  incl. paid apprentice and cooperative member); **P50–P51 fertility: women 10+**.
- H-block H01–H27 (habitat, building, tenure, own dwelling elsewhere, materials, rooms, sleeping rooms,
  water for general use and for drinking, toilet, grid connection, lighting, cooking main/secondary,
  stove, waste, sewage, 16 assets, livestock by type/number/district, crops, vegetables, tea/coffee trees).

### 2022 — `Census_2022_statement_of_the_public_use_sample_of_the_1.pdf` (English, 2 pp.)
- 10% equal-probability sample of private households, residents only; two weights **HH_weight** and
  **Pop_weight**; **analysis valid down to sector level**; 1,313,015 persons (631,543 M / 681,472 F)
  weighting to 13,245,753; 331,606 households weighting to 3,309,692; province tables (used in
  `03_checks.py` §C).
- Verified in the data: the public 2022 file **does not carry P37–P45** (the employment identification
  block) nor the 4-digit P47/P48 codes; only P46, P47A (ISIC section), P48A (ISCO major group) and P49
  for the 359,336 employed residents. Employment status (employed / unemployed / inactive) cannot be
  rebuilt for 2022 from the public sample; only "has a job" (P46–P49 non-missing) is observable.

### 2022 — `Census_2022_listing_form_english_version.pdf`, `Census_2022_questionnaire_institutional.pdf`
- Listing form (buildings, households, footprints) and the institutional form; neither affects the
  public private-household sample.

### 2012 — operational documents (English): supervisors' manual, data-entry manual, call-back/revisit
form, PES forms/manuals, atlas, brochure, campaign material, provisional results, publication tables
- Field organisation, data entry (CSPro), PES matching rules, maps and communication material. No
  variable definitions beyond those above. PES report = same content as the data-quality assessment.

## 2. What was applied (2026-09-04)

| Fact | Change in the pipeline |
|---|---|
| 2002 value labels are French; questionnaire gives the English wording | `01_clean.py` `EN2002_VALUES`: English value labels for the key block and concept variables (relationship, residence, religion, disability, parents, school attendance, diploma, literacy, activity, status, institutional sector, marital status, fertility counts, housing block, collective-household types); languages P11 decoded token by token; recurring phrases (non déterminé, aucun, autre …) translated everywhere. French originals kept in `logs/clean_2002_meta.json` → `value_labels_original`. Left French: P08/P10 (pre-2006 district names), P18 (field of study), P22 (ISCO-88), P24/P241 (ISIC Rev.3). |
| 2012 urban share published 16.5%; NISR's 2-way recode RL07 | key-block `urban` for 2012 = `rl07` (was L07 = 1 only); `l07` still carried. Check added: rl07 = 1 ⇔ l07 ∈ {urban, semi-urban}. |
| 2012 recodes RP142 RP12 RP08 RP2024 RP2124 RL07 RP04Y shipped with their name as label | descriptive labels (`RP2012_LABELS`), unlabelled code 9 of RP2024 labelled "not classified". |
| 2012 P25 is ISCO-08 4-digit without labels; NISR's 2012 coding list is in `z_Documentation/2012` | ISCO-08 unit-group titles attached as value labels to `p25` (418 codes in the data); P27 relabelled as ISIC Rev.4 class code (no English ISIC list in the census documentation; sections in `rp27`). |
| Universes differ by year (education 6+/3+/all; activity 6+/5+/16+; marital 12+; fertility women 12+/12+/10+; parents ≤25/<18/<18; literacy 6+/3+/10+) | `UNIVERSE` table per year in `01_clean.py`, written to the meta files and shown as a `universe` column / note in `CODEBOOK.md` and `codebook_*.csv`. |
| Population in private households 2012 = 10,378,021; urban shares 16.9 / 16.5 / 27.9% | `03_checks.py` §C: weighted 2012 population vs 10,378,021 (±0.5%); weighted urban share per year vs the published share (±3% relative). |
| 2022 public file lacks P37–P45 | recorded here and in `DECISIONS.md`; no employment-status variable is derived for 2022. |
| NISR sentinels 9/99/999/9999 = missing / not applicable | unchanged policy: kept and labelled, never set to system missing. |

## 3. Not read (Kinyarwanda only)
`2012/Census_2012_003_enumerators_manual_kiny.pdf`, `004_supervisors_manual_kiny.pdf`,
`006_sector_controllers_manual_kiny.pdf`, `007_zone_supervisors_manual_kiny.pdf`,
`008_district_coordinators_manual_kiny.pdf`, `009_province_coordinators_manual_kiny.pdf`,
`Census_2012_isic_kiny.pdf` (ISIC Rev.4 in Kinyarwanda), `Census_2012_questionnaire_hh_kiny_20120221.pdf`,
`Census_2012_questionnaire_institution_kiny_20120314.pdf`, the Kinyarwanda PES forms and manual,
and `2022/Census_2022_1_phc2022_instruction_manual.pdf` (118 pp., Kinyarwanda despite the English
title; its education table — years per level: primary 0–8, lower/upper secondary 0–4, TVET 0–6,
tertiary 0–15 — was the only part used).
