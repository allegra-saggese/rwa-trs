# EICV — what the documentation says and how it was applied

All 188 files in `z_Documentation/` were extracted to text (2026-09-04). The English ones were read;
the EICV1 and EICV2 questionnaires are in **French** (despite the `_english` file names) and were read
as well because they are the only source for those rounds; Kinyarwanda manuals are listed at the end as
**unread**. Facts that matter for processing are recorded per document, then what was changed in the
pipeline (also logged in `DECISIONS.md`).

## 1. Facts by document

### Household membership (all rounds — EICV1/2 roster pages, EICV3 `Section 01.pdf`, EICV4/5/7 section 1)
- A household = persons who usually live and take their meals together and recognise the authority of
  the head. Persons absent **6 months or less** in the last 12 months are members; if absent more than
  6 months only the head, children under 6 months, persons who did not join another household, new
  spouses and persons who recently joined intending to stay are members. Roster order: head, spouse(s)
  with their children, other relatives, non-relatives, absent members. From EICV4 the roster also
  records (S1Q14) whether the person is a household member; visitors are listed but skip all later
  sections. EICV4–7 ask nationality, birthplace (district/country), 12-month absences with reason,
  and parents' survival.
- Relationship codes change: EICV1 8 codes (head, spouse, son/daughter, grandchild, father/mother,
  other relative, domestic staff and related persons, boarders/others); EICV2 9 codes (adds fostered
  child, brother/sister, other relative, non-relative); EICV3–5 12 codes (adds step/adopted child,
  parent-in-law, sibling-in-law, waged domestic worker); EICV7 14 codes (adds nephew/niece, no
  relationship, unknown). Marital status: EICV1/2 6 codes (monogamous, polygamous, living together,
  divorced/separated, single, widowed; EICV1 data distinguish head/non-head married); EICV3 7 codes
  (divorced and separated split); EICV4/5 8 codes (monogamous with / without legal certificate);
  EICV7 7 codes. Marital status is asked from age 12.

### EICV1 (2000/01) — `EICV1/EICV1_questionnaire_english.pdf` (French, 13 sections + community)
- Universes: education section 2 **members 7+** (school-career parts B/C for under-40s, literacy 5+);
  health all; **economic activity section 4: members 7+**, reference period the **last 12 months**
  (part A filter and list of jobs, B main occupation, C secondary occupation, D job search 12 months,
  E activities and job search in the last 7 days, hours); migration section 5 **15+**; housing 6;
  agriculture 8 (livestock, land, parcels, crops, harvest/sales/consumption/stocks by visit dates);
  expenditure 9; enterprises 10; transfers 11; credit/durables/savings 12. Value labels in the NISR
  SPSS files are already English.
- Sample (Megill 2004, table 6): 570 cellule-segments, **6,450 households** allocated in 13 strata
  (Kigali-ville 720, other urban 450, rural 480 per old province); 6,420 interviewed. Weights `POND`
  (equal to NISR's `eicv1_remap_weights`, which also maps each household to the current district).

### EICV2 (2005/06) — questionnaire (French), Megill sampling report, Muñoz mission report, weighting workbook, data-processing report, poverty methodology note, economic-activity files note, social-sector data guide
- Universes: education section 2 **members 6+**; health 3 all; migration 4 **15+**; housing 5 (5E
  services); **economic activity section 6: members 6+**, last 12 months (6A filter, 6B unemployment
  and job search, 6C household chores, 6D list of all jobs with months worked and hours in the last 7
  days and **status: agricultural wage, non-agricultural wage, agricultural independent, non-agricultural
  independent, unpaid**, 6E wage employment, 6F unpaid); enterprises 7; agriculture 8; expenditure 9
  (annual, monthly, frequent non-food; food; own consumption); transfers/other 10; credit/durables/
  savings 11; a community questionnaire in rural areas.
- Design (Megill; Muñoz): stratified two-stage sample, PSU = 2002-census enumeration area (ZD, 7,727
  in the frame, ~227 households each), PPS within 13 explicit strata (Kigali-ville, other urban, rural
  part of each of 11 old provinces) with implicit stratification by a well-being indicator in Kigali
  and a semi-rural sub-stratum in urban areas; **9 households per urban ZD, 12 per rural ZD** after a
  listing; 6,900 households; 10 data-collection cycles over the year; weight = inverse selection
  probability (three stages when segmented), approximately self-weighting within stratum
  (`EICV2_ponderation.xls` lists every sampled ZD with stratum, cycle, frame counts and selection).
- Data processing: CSPro, full double entry, DHS-style system; "recodes and comparability" section.
- Economic-activity files note: **EICV1 and EICV2 are not directly comparable** (EICV1 main +
  secondary job; EICV2 all jobs); NISR's `Jobs database` syntax derives main usual job (most months in
  the year) and main current job (most hours in the last 7 days), `Curr_Active`, and the Rwandan ISIC
  grouping (11–93 → 11 short groups). The two EICV1-derived files shipped in the EICV2 folder
  (`eicv1_econbase`, `eicv1_jobstatus_subsistence1`) come from this work.
- Poverty methodology (McKay & Greenwell 2007): consumption aggregate (food purchases, own-produced
  food, non-food, imputed rent, education, routine health, utilities, durables' use value, transfers
  out, wages in kind); outliers > 3.5 sd replaced by regional means; **Laspeyres price index** by
  province and month, basket of the poorest 60% in January 2001 prices (MINAGRI market prices for 26
  food items); adult-equivalent scale; poverty line at January 2001 prices. EICV1 figures in the
  Poverty Update are on the same basis.

### EICV3 (2010/11) — section files `Section 01–11.pdf` (English) and Word sections (Kinyarwanda headers)
- Sections: 1 roster; 2 education **6+**; 3 health / disability (all); 4 migration (moves of 6+ months,
  all); 5 housing; 6 economic activity **6+**, last 12 months (6A filter, 6B, 6C–6F jobs, wage, business,
  unpaid); 7 non-farm enterprises; 8 agriculture; 9 expenditure; 10 transfers and other income/
  expenditure; 11 credit, durables, savings. Codes list `EICV3_CODES_Kiny1.doc` (Kinyarwanda).
- No sampling document is held for EICV3; the poverty file shipped in the EICV4 folder
  (`eicv3_povertyfile_jan2014`) is the January-2014-price re-expression (DECISIONS: 46.0% headcount).

### EICV3–4 panel and EICV4 (2013/14) — English questionnaire (CS = VUP = panel questionnaire), controller/listing/enumerator manuals (Kinyarwanda), panel forms
- Panel: EICV3 households re-visited with the EICV3 person ids copied into section 0/1 (`EICV3 PID`,
  "write 00 if not in EICV3"); tracked movers; new ids allocated sequentially; the linking file is
  `EICV3_4_Panel`. Section 0 records VUP sector and Ubudehe category for every household.
- Universes: 1 roster (all; marital 12+); 2 migration (all); 3 health (all); **4 education: 3+**
  (part B literacy/ICT 10+; class codes 10 = never completed P1); 5 housing; **6 economic activity:
  6+, usual activity over the last 12 months** — 6A filter (any farm/non-farm/paid/unpaid work), 6B
  list of all jobs in the last 12 months (occupation ISCO, industry ISIC, agricultural for sale / for
  family use / non-agricultural, months, main job over 12 months, worked ≥ 1 h in the last 7 days,
  main job in the last 7 days, hours, days), 6C wage jobs (sector: private non-farm / private farm /
  public / cooperative / local NGO / international / VUP private / VUP public / household domestic /
  other), 6D business, 6E underemployment (currently working), 6F unpaid domestic work 6+; 7 agriculture
  (livestock, land, parcels, large and small crops, other income, costs, processing); 8 expenditure
  (annual, monthly, frequent, food, own consumption); 9 transfers out/in, **VUP/Ubudehe/RSSP** schemes,
  income support and other revenues; 10 credit, durables, savings.
- VUP booster (EICV5 VUP report §2): the EICV4 VUP survey sampled 2,460 households from the VUP
  administrative frame (stratified two-stage); not nationally representative.

### EICV5 (2016/17) — English questionnaire, enumerator and listing manuals (Kinyarwanda), VUP thematic report (English)
- Same structure as EICV4 (sections 0.3–0.5 add panel identification, listing of panel villages);
  disability items asked from age 5; economic activity 6+, 12-month usual activity; section 9 splits
  VUP into parts C1–C5.
- VUP report: **EICV4 14,419 and EICV5 14,580 cross-section households**; VUP panel of **1,642
  households** that were VUP beneficiaries in 2014 (2,460 sampled in 2014; attrition 175; 324 split
  households); CAPI for the first time; quintiles from consumption per adult equivalent; VUP
  components: direct support, public works, financial services.

### EICV7 (2023/24) — English questionnaire, DDI variable documentation (English), instruction manual (Kinyarwanda)
- Design (DDI): 12 months Oct-2023–Oct-2024 in **9 cycles of 3 sub-cycles**; master sample from the
  2022 census; **30 district strata**, PPS EAs (72 per Kigali district, 54 elsewhere; 1,674 EAs),
  urban/rural allocation proportional to households, listing, **9 households per EA** with 3
  replacements; **15,054 of 15,066 households interviewed (> 99%)**; weights = inverse selection
  probabilities, **no non-response adjustment** (all non-interviews replaced); 62,110 persons.
- Questionnaire changes (DDI + questionnaire): employment now **main job only, reference period the
  last 7 days** (6A filter: own farm, products for sale/family use, paid work, business, unpaid help,
  temporary absence with reason incl. leave codes; 6B hours usual/actual, occupation ISCO, industry
  ISIC, institutional sector 9 codes incl. VUP and cooperative, night work, status in employment 8
  codes incl. paid/unpaid apprentice, contract type, last pay and period); **6C domestic work 5–17**;
  agriculture shortened; consumption recorded by source (purchase / own production / gift) with
  meals outside the home; in-kind transfers moved to section 8, only cash transfers in section 9;
  durables list revised; health disability 5+; education 3+ with literacy/ICT 10+; housing adds shocks
  and access/satisfaction with services. Data files: 21 files incl. the poverty file (15,054 rows).

## 2. What was applied (2026-09-04)

| Fact | Change in the pipeline |
|---|---|
| Section universes differ by round (economic activity 7+/6+, education 7+/6+/3+, literacy 5+/6+/10+, migration 15+/all, disability 5+ from EICV5, domestic work 6+ → 5–17) and the employment reference period changes in EICV7 (12 months → 7 days, main job only) | `SECTION_UNIVERSE` in `01_clean.py` (per round, by questionnaire section) → written per variable into the person/household meta and per module stem into the module meta → `universe` column / note in `CODEBOOK.md` and `codebook_*.csv` (versioned columns show the universe of their own waves). |
| Documented sample sizes: EICV1 6,450 allocated, EICV2 6,900, EICV4 14,419, EICV5 14,580, EICV7 15,054 households / 62,110 persons | `03_checks.py` §C: household counts per wave vs the documentation (EICV1 within 1% for non-response), EICV7 person rows vs the DDI. |
| EICV1/EICV2 value labels: NISR's SPSS files already carry English labels | no translation needed (verified: roster, education, employment, housing labels are English in EICV1–3). |
| EICV1 vs EICV2 economic activity not directly comparable; EICV7 7-day reference | recorded here and in `DECISIONS.md`; labour variables stay round-specific (no cross-round labour harmonisation inside EICV, as before). |
| Household-membership rule identical across rounds (6-month rule) | no change; the person files keep every roster row incl. non-members flagged by NISR (S1Q14 in EICV4+). |

## 3. Not read (Kinyarwanda only)
`EICV3/EICV3_CODES_Kiny1.doc`, the `IGIKA … _Title.doc` files, `EICV3_4_Panel/*` and `EICV4_*/*`
controller / enumerator / listing manuals and Kinyarwanda questionnaires (parts A and B), `EICV5_*/*`
enumerator instruction and listing manuals, `EICV7_CS/EICV7_CS_instruction_manual.pdf`. The EICV2
CSPro data-entry application files (`EICV2_data_entry_apps/`) are binary dictionaries and were not
used.
