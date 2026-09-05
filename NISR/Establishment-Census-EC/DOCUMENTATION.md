# Establishment Census (EC) — what the documentation says and how it was applied

All 28 files in `z_Documentation/` were extracted to text and the English ones read (2026-09-04):
the five questionnaires (2011, 2014, 2017, 2020, 2023), the 2014 project document, the ISIC Rev.4
list, and the listing / progress-report / contract forms. Kinyarwanda instruction manuals and
questionnaires are listed at the end as **unread**.

## 1. Facts by document

### Scope and unit (2014 project document; all questionnaires)
- Complete count of **every operating establishment with a fixed location and a specific economic
  activity**, country-wide; every three years; enumeration by village with a serial number within the
  village. Objectives: characteristics and geographic distribution, economic activity (ISIC), employment
  by sex / nationality / contract, a business register for economic surveys. The 2011 census "enumerated
  127,662 establishments" (= rows of the 2011 file; 123,526 of them operating).
- The unit of the questionnaire is the establishment (a head office reports only persons working at
  the head office; branches are separate units, with the head office's activity and total branches /
  workers asked from 2014).
- Working status: 1 working, 2 closed temporarily, 3 closed permanently (interview ends). 2020 and
  2023 add the cause of temporary / permanent closure (COVID-19, closed by authorities, bankruptcy,
  liquidation, seasonal, …). Working place: within / outside market place; 2014+ industrial zone; 2020+
  ICPC-Udukiriro.

### 2011 questionnaire (English, 4 pp.) — items S-…
- Location L1–L8 (province … village, serial number, name, phone); manager sex; working place and
  status; **sector** (household, private, public, mixed, cooperative, private education, private
  health, local non-profit, international organisation); nationality of owners (10 codes); year of
  start; major activity → **ISIC Rev.4 4-digit code** (labels shipped in the data); legal status (sole
  proprietorship, limited by shares / guarantee / both, unlimited, other); owner = manager, sex of
  owner; registration with 8 institutions (social security, RRA, RDB, district, sector, RCA, PSF,
  other); taxes paid (VAT, TPR, income tax); regular accounts; capital employed (RWF); **workers by
  education (none / primary / secondary / university) × nationality × permanent/temporary × sex**.

### 2014 questionnaire (English, 3+ pp.) — items Q1–Q27
- Adds: abbreviation, e-mail; manager age band (14–35 / 36+); secondary economic activity (ISIC);
  **institutional sector** (private, mixed, public, household, NGO Rwanda / international) with
  categories of private (cooperative, company, association) and mixed (commercial / non-commercial);
  nationality of owners 15 codes; separation of establishment and household management; owner
  age; establishment type (head office, single unit, branch, sub-branch) with branches and workers in
  all branches; **workers by sex × nationality** and **by length of contract / payment status** (unpaid:
  working owners, apprentices; paid: < 1 month, 1–6 months, > 6 months, open contract) × sex;
  turnover and capital brackets (private / mixed), income and contribution brackets (public / NGO /
  household); registration and taxes. The public 2014 file is a **weighted sample** (DECISIONS).

### 2017, 2020, 2023 questionnaires (English) — one layout, items q1–q27
- 2017: manager age in years, ISIC major activity, legal status, owner = manager / sex / age,
  regular accounts and **books kept** (ledgers, journals, balance sheet, income statement, invoices),
  head office block, workers by contract / payment status × sex (unpaid: working owners, unpaid
  family workers, industrial attachment, apprentices; paid: open contract-permanent, fixed > 6 months,
  1–6 months, < 1 month, professional internship), workers by sex × nationality, turnover / capital,
  **foreign transactions in goods and services**, taxes (8 types), **TIN number**.
- 2020: adds causes of closure (COVID-19 first), ICPC-Udukiriro working place, institutional sector
  7 codes (private, cooperative, public, mixed/PPP, NGO Rwanda / international) with profit / non-profit
  for mixed, nationality 8 codes, head-office ISIC of the entire enterprise.
- 2023: adds **establishment category** (schools, health facilities, faith-based, hotel/restaurant,
  banks/SACCO, public administration, other commercial, other non-commercial), website, manager and
  owner **education level** and date of birth, number of cooperative members by sex, nationality 11
  codes, statistical law 45/2013.

### `2011/EC_2011_isic4_codes.pdf` (Kinyarwanda / English, 42 pp.)
- ISIC Rev.4 sections, divisions, groups and classes with English titles (the class titles are the
  ones NISR attached as value labels to the 2011 4-digit code). From 2014 the public files carry only
  the 1-digit section (`isic1q6b`, `q6_1`), not the 4-digit code.

### Operational documents (English): listing forms 2011/2014/2017, progress-report forms, 2014 contracts, activities plan
- Listing by village (structure, establishment, name, activity); daily / weekly / district / zone /
  provincial progress reports; no variable definitions.

## 2. What was applied (2026-09-04)

| Fact | Change in the pipeline |
|---|---|
| 2011 census enumerated 127,662 establishments (project document) | `03_checks.py` §C: 2011 file rows vs 127,662. |
| Universe = operating establishments with a fixed location; closed-permanently units end the interview but are in the 2011 file | codebook header states the universe and that `s04` / `q3_1` working status must be used to select operating units (2011 report figure 123,526 = working). |
| 4-digit ISIC only in 2011; 1-digit sections from 2014; questionnaire content changes listed above | recorded here; the version rule already keeps the 2011/2014 items apart from the 2017+ series. |

## 3. Not read (Kinyarwanda only)
`2011/EC_2011_instruction_manual_kinyarwanda.pdf`, `2014/EC_2014_instruction_manual_kinyarwanda.pdf`,
and the Kinyarwanda questionnaires of 2011, 2014, 2017, 2020, 2023 (identical in structure to the
English ones).
