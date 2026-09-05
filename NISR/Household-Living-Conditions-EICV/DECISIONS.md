# EICV — decisions log

Running record of every crucial step and why. Cross-dataset conventions live in
`NISR/README.md`; this file records how they were applied to the Integrated Household
Living Conditions Survey (EICV) and every EICV-specific call.

## 2026-09-04 — rebuild in Python, all rounds, all modules

**Waves processed.** EICV1 (2000/01), EICV2 (2005/06), EICV3 (2010/11), EICV4 (2013/14),
EICV5 (2016/17), EICV7 (2023/24), each of EICV4/5/7 in its cross-section (CS) and VUP booster
sample, plus the EICV3–4 panel linking file. `year` is the mid-fieldwork year (2001, 2006,
2011, 2014, 2017, 2024). The archived Stata pipeline processed only EICV3–7 and only the
person module; here every module file of every wave is cleaned.

**Old rounds are in.** EICV1 and EICV2 predate the 2006 territorial reform, but NISR
already mapped both to the current districts: EICV2 carries `ID1_N`/`ID2_N` (new province
and district) next to the old prefecture (`ID2`), and EICV1 ships `eicv1_remap_weights.sav`
with every household's new province, district, EA key and weight (identical to the
original `POND`). So the key block uses current districts in all waves; the old geography
(`prefect`, `id2`, `strate`, `id1`) is carried under its own name. No boundary crosswalk was
needed. NISR's EICV2 folder also holds two EICV1-derived files (`eicv1_econbase`,
`eicv1_jobstatus_subsistence1`) and the EICV4 folder holds the EICV3 poverty file
(`eicv3_povertyfile_jan2014`); each is processed as a module of the wave it describes.

**District codes** come in three schemes (101… in EICV1/2, the string `'0101'` in EICV3,
11–57 in EICV4+); all are mapped to NISR's 11–57 scheme (`prov*10 + sequence`) and asserted
to be exactly the 30 current districts.

**Weights.** EICV weights are household weights carried by every person row: summed over
persons they give the population (EICV3: 10.76m, EICV4: 11.43m, EICV5: 11.89m, EICV7: 13.55m),
summed over households the number of households (EICV4: 2.49m). `wt` is that weight in
both the person and the household file; `wt_hh` is the same number. NISR's `pop_wt`
(household weight × household size, for household-level estimates of persons) is carried
where shipped. The EICV1 remap weight equals the original `POND` exactly.

**Units and module handling — one mechanical rule.** Every module file is classified from
its keys: household-level if `hhid` is unique, person-level if `(hhid, pid)` is unique,
otherwise "multi" (plots, crops, livestock, expenditure items, jobs, credits …); community
questionnaires (EICV1 `comm_sect*`) have no household key and are "other". The wave's
PERSON file is the roster module left-joined 1:1 with every person-level module; the
HOUSEHOLD file is the household base module(s) left-joined 1:1 with every household-level
module and the poverty file, plus `hhsize` (roster count) and the head's sex and age
(relationship code 1). Names that collide on a join are dropped when the module's copy is
identical to the base (NISR repeats geography and weights in every file) and kept with a
`_<module>` suffix when they differ. Every module is also written on its own to
`2_Intermediate/` with the key block attached, so nothing is lost.

**Person ids.** `hhid` = NISR's `KEY` (EICV1/2) or `hhid`; `pid` = `ID`/`pid`/`idind` (EICV1),
`PID` (EICV2), `PID % 100` in EICV3 (where `PID = hhid*100 + person`, kept as `pid_nisr`),
`pid` in EICV4+.

**Urban/rural.** EICV4 ships two definitions — `ur2012` (4 categories) and `ur2_2012`
(2 categories); the key block uses the 2-category one, both are carried.

**Pooled files.** National cross-sections (EICV1,2,3,4_CS,5_CS,7_CS) and VUP boosters
(EICV4/5/7_VUP) are pooled separately, for both person and household units, because the
VUP samples are drawn from programme beneficiary lists and are not nationally
representative. Modules with the same questionnaire block in two or more waves are pooled
under a canonical name (`MODULE_MAP` in `02_merge.py`: jobs, enterprise, livestock, parcels,
crop_large/small, expenditure_*, food, transfers_in/out, credits, durables, savings, …);
modules without a counterpart stay per-wave. **Item-level consumption and asset modules** (food,
expenditure_annual/monthly/frequent, own_consumption, durables) are pooled as well since the disk was freed (the food module alone is 10.8m rows × 168 columns,
5.8 GB; `POOL_ITEM_MODULES` in `02_merge.py` can switch any of them off again). NISR's linking files (EICV3–4 panel,
EICV5 VUP panel) are written to `3_Final/` with harmonised keys.

**Labour is not harmonised** (as in the archived pipeline): activity, industry and
occupation items differ across rounds and only get ISIC/ISCO coding late; they are carried
wave by wave and the version rule keeps different questions apart.

**Poverty check.** The pooled household file reproduces NISR's published headcounts from NISR's own
flags weighted by `pop_wt`: EICV4 39.1, EICV5 38.2, EICV7 27.4 (revised basis). For EICV3 the shipped
file is the January-2014-price re-expression made for the EICV3–EICV4 comparison and gives 46.0, the
figure of the EICV4 trend report, not the 44.9 of the original 2010/11 basis.

**Layout (2026-09-04, Matteo).** `3_Final/` holds only the appended unit-level datasets; every
module-level file — per wave at the top of `2_Intermediate/`, appended across waves in
`2_Intermediate/appended/` — lives in Intermediate. For EICV that means `3_Final/` = `EICV_pooled_person` + `EICV_pooled_household` (the six national rounds); the VUP pools, the 27 appended modules and the two panel link files are in `2_Intermediate/appended/`.

## 2026-09-04 — documentation pass (see DOCUMENTATION.md)

**Universes recorded by questionnaire section and round.** The section that carries a concept moves
across rounds (employment is section 4 in EICV1, 6 afterwards; migration 5/4/2; education 2/2/2/4)
and its age base moves too (economic activity 7+ in EICV1, 6+ from EICV2; education 7+/6+/3+;
literacy 5+/6+/10+). `SECTION_UNIVERSE` in `01_clean.py` maps each round's section numbers to the
universe text and the codebook shows it per variable and per appended module.

**EICV7 employment is not comparable with EICV1–5 without care.** EICV1–5 record all jobs over the
last 12 months (usual activity) plus a 7-day filter; EICV7 records the main job over the last 7 days
only. The round-specific variables are kept apart by the version rule, as before; the harmonisation
step must treat "employed" in EICV7 as a current-status (7-day) measure.

**Sample-size checks from the documentation** added to `03_checks.py` §C: EICV1 6,450 households
allocated (6,420 interviewed, within 1%), EICV2 6,900, EICV4 14,419, EICV5 14,580, EICV7 15,054
households and 62,110 persons.

**Labels.** NISR's EICV1/EICV2 SPSS files already carry English value labels, so nothing had to be
translated for the pre-2006 rounds (the questionnaires themselves are French).

## 2026-09-05 — three forced splits found while harmonising

Section 6A/4B item numbers move between rounds and the label rule merged three pairs of different
questions: `s6aq6` (EICV3 participation in VUP works / EICV5 worked in a non-farm business),
`s6aq8` (EICV4 main reason for not working / EICV5 months occupied), `s4bq4` (EICV4 can write /
EICV5–7 able to read). Listed in `FORCE_SPLIT` and the pooled files rebuilt; the harmonisation step
follows the version columns through `logs/merge_alignment.json`.
