# LFS — what the documentation says and how it was applied

Every document in `z_Documentation/` was extracted to text and the English ones read (2026-09-04):
the questionnaires 2017 (xls), 2018–2020 (pdf), 2021–2023 (xls), 2024–2025 (pdf), the 2021 methodology
annex and the 2022 variable list. This file records the facts that matter for processing and what was
changed because of them (code changes are also logged in `DECISIONS.md`). Kinyarwanda documents are
listed at the end as **unread**.

## 1. Facts by document

### `2021/LFS_2021_methodology.pdf` — Annex B "Survey methodology and data quality" (English, 18 pp.)
- **Design.** Two-stage stratified sample: PSU = enumeration area of the 2012 census (14,784 EAs in the
  frame), drawn PPS within district after sorting by urban/rural (implicit stratification); 16 households
  per EA by systematic sampling from a fresh listing (all if ≤ 16); all members of sampled households.
  District allocation by the square-root rule; 288 EAs per round.
- **Scope.** Persons in private households; institutional population, seasonal dwellings and workers
  living on work sites excluded. Household = persons living together making common provision for food.
- **Programme.** Pilot Feb-2016; first round Aug-2016; bi-annual (February, August) until Aug-2018;
  quarterly since 2019 (February, May, August, November — chosen for the agricultural seasons) with
  ≈ 4,608–4,668 households per quarter in three rotation groups; rotation 1-1-1 (a household is
  interviewed three times, once every two quarters). Sample size derived for unemployment/WAP = 2.4%
  (2012 census), deff 3, margin ±0.3% → ≈ 18,700 households a year.
- **Weights.** Design weight = 1/(P(EA) × 16/N′ₖ); non-response adjustment by EA response rate; quarterly
  weight = old bi-annual weight × ¾ × 144/146 × ⅓; then **calibration (Deville–Särndal) to population
  projections for four groups: males/females under 16 and 16+ in private households**; *all individuals
  in a household receive the household's weight*. The annual weight (`weight2`) is the calibrated
  quarter weight divided by the number of quarters, so summing it over all interviews of the year gives
  the annual average population.
- **Questionnaire.** 149 questions, 9 sections: A roster (+ activities of children 5–13), B education,
  C identification of employed / time-related underemployed / unemployed / potential labour force,
  D main job, E secondary job, F past employment, G own-use production, H subsistence foodstuff
  production, I housing and assets. Children under 14 get a minimum of questions; sections B–H are
  for persons **14 and above**; reference period = last 7 days (4 weeks for job search, last month for
  subsistence agriculture). Derived variables defined by NISR's Stata syntax: STATUS1 (employed /
  unemployed / outside labour force), TRU, PLF, discouraged, willing, subsistence foodstuff producer
  (sub), informal/formal sector and employment (IS/FS, IE/FE), cash income of employees, NEET 16–24
  and 16–30, migrant, disability.
- **Field.** CAPI; on-screen coding of education (ISCED), occupation (ISCO-08) and industry (ISIC
  Rev.4) with Kinyarwanda dictionaries; listing at the same time as interviewing; large EAs segmented.

### `2022/LFS_2022_variables.xlsx` (English, 240 variables)
- Full variable list of the 2022 release with untruncated labels: PSU_NO "Primary Sampling Unit-quarterly",
  HHID "Household identification", pid, province, Code_UR, code_dis, LFS_year, weight2 "Annual_weight",
  A01–A24 roster/migration, B01–B19 education (B18/B19 social media and internet use), C01–C26 (C21_A–L
  job-search methods), D03A–D27 main job, E11–E13 secondary job, F01–F05 past employment, G01–G07 (+ G01A–
  G07A yes/no) own-use production, H00–H10 subsistence agriculture, I01–I07Q housing and assets, and the
  derived block: status1 "Labour force status with 16+", wap16, employed16, UR1, LFPR, sub, TRU, PLF,
  youth 16–24, young 16–30, LUU/LUUR, disable, discourage, willing, migrant, neetyouth/neetyoung, youngs,
  main_sect, indb1 years of schooling, attained, cash, intcash, age5/age10/age3, usualhrs, timegood/
  timeservice, hhsize, usual_h, act_hrs, acthrs, YA, hr_own, combhrs, subhrs, hr_cshmain, hr_cash, TVT2/
  TVET3/TVT, agdis, Prod_unit, SM search methods, UD unemployment duration, IEV2 formal/informal
  employment, head, dG01–dG07, LU2–LU4, TRUR, indb05 field of education, isco2digit, isic2digitdigit,
  indd01 ISCO major group, indd03 / inde02 ISIC section (main / secondary job), age3_16_30, YUR1.

### Questionnaires 2017 (xls), 2018, 2019, 2020 (pdf), 2021, 2023 (xls), 2024, 2025 (pdf) — all English
- **Universes (identical in every year read):** A05 marital status 12+; A06–A11 disability 5+
  (Washington Group short set, 4-point scale); A12–A24 nationality, residence status, birthplace,
  migration and absences: all members; A25–A27 activities of children 5–13 (present 2017–2023, absent in
  2024–2025); **sections B–H: members 14+**; H05–H11 (family farm) and section I: household level.
- **Section C flow.** C01 paid work ≥ 1 hour / C02 business / C03 unpaid help → C04/C05 agriculture and
  product destination (mainly for sale vs family use decides employment for farmers) → C06–C09
  temporary absence (reason, expected duration, income continues) → C10–C18 hours and time-related
  underemployment → C19–C22 job search in the last 4 weeks (C21 methods) → C23–C26 willingness and
  availability. 2024–2025 split C02 into C02 (non-farm business) / C02A (farm business) and add C09A,
  C10A (number of other jobs), C19A (tried to start a business), C20A.
- **Section D.** D01 occupation → ISCO code (D01B2), D03 workplace name and activity → ISIC code (D03B1),
  D04 institutional sector (public, mixed, private, international NGO, local NGO/religious, cooperative,
  household; 2024 adds VUP/community-based jobs), D05 status in employment (employee, paid
  apprentice/intern, employer, own-account, cooperative member, contributing family worker, other);
  **2024 introduces the ICSE-18 block DS07–DS10a** (self-identified status, decision-making in family
  business, paid employees, price setting, dependence on a client, types of pay) and 2025 ships D05
  recoded on 5 codes — kept as `d05_v2` in the pooled file. D06–D10 contract, social security and
  benefits; D12–D17 earnings (amount, period, in-kind, interval); D20–D21A registration and accounts;
  D23 place of work (13 codes in 2024); D23A/B commuting; D24 experience; D25 district of work (2024+).
- **Section B.** B01 currently studying; B02A level (none, pre-primary, primary, lower secondary, upper
  secondary, tertiary) and B02B years; B03 highest certificate and **B06 literacy exist 2017–2023 only**
  (dropped from the 2024 questionnaire, hence `b03`/`b06` empty in 2024–2025); B07–B15 TVET.
- **Section 0 (2024).** Rotation group, group appearance/acceptance counts, consent and non-interview
  reason, interview start/end time, GPS — not released in the public files.

## 2. What was applied (2026-09-04)

| Fact | Change in the pipeline |
|---|---|
| Household-level calibrated weight assigned to every member | hard check in `01_clean.py`: `wt` constant within (hhid, interview) in every year (holds on 100% of rows). |
| Sections B–H asked to 14+, disability 5+, marital 12+, children's activities 5–13 | `UNIVERSE_LFS` in `01_clean.py` → meta files → `universe` column / note in `CODEBOOK.md` and `codebook_*.csv`. |
| NISR's `status1` label says "with 16+" or "with 14+" by year, but the data show it populated for 16+ in 2017–2019 and for 14+ from 2020 | per-year check in `01_clean.py` (status1 populated exactly on the verified age base); label rewritten to state the age base; `status1` added to `FORCE_ALIGN` so the years stay one column. Any 16+ indicator must restrict on `age >= 16` explicitly. |
| B03/B06 dropped in 2024; D05 recoded in 2025; A25–A27 dropped in 2024 | documented (no code change: the version rule already separates `d05_v2`; empty years show as 0 in the codebook). |
| Annual weight = calibrated quarter weight / number of quarters | unchanged (already the basis of `wt`; §C check on the 2024 working-age population). |

## 3. Not read (Kinyarwanda only)
`2017/LFS_2017_interviewer_manual_aug.doc` (Kinyarwanda despite the file name; only its section list
was used), `2019/LFS_2019_interviewer_manual_in_kinya.pdf`, `2020/LFS_2020_interviewer_manual_in_kinya.pdf`
(identical to 2019).
