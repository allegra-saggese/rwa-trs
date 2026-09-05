# NISR microdata pipelines

One folder per NISR dataset, named exactly as the data folder on Dropbox
(`Rwanda - TRS/data/Publicly-Available-NISR/<dataset>/`). Each folder is an independent,
replicable code base: nothing is imported across folders, and `python master.py` runs the
whole pipeline top to bottom. Data never enter git; the code reads and writes the Dropbox
folder, whose root is resolved from the login user (or `NISR_DB_ROOT`).

| Folder | Survey | Final files (one row per …) |
|---|---|---|
| `Labour-Force-Survey-LFS/` | Labour Force Survey 2017–2025 | person-interview; household-interview |
| `Census-PHC/` | Population and Housing Census 2002, 2012, 2022 (10% public samples) | person; private household |
| `Household-Living-Conditions-EICV/` | EICV1–EICV7 (+ VUP boosters, EICV3–4 and EICV5-VUP panel links) | person; household (national and VUP pools); pooled modules (jobs, enterprise, livestock, parcels, crops, transfers, credits, …); link files |
| `Establishment-Census-EC/` | Establishment Census 2011–2023 | establishment |
| `Agriculture-Survey-AHS/` | Agricultural Household Survey 2017, 2020, 2024 | person; household; pooled modules (milk, honey, land, extension, tools, livestock, credits) |
| `Season-Agriculture-Survey-SAS/` | Seasonal Agriculture Survey 2013–2025 | plot × crop × season (2017–2025 core map; 2013–2014 crop-area records); pooled 2019+ modules |
| `Food-Security-CFSVAN/` | CFSVA 2006–2024 (NISR/WFP) | household; woman; child; village |

All seven were built and verified on 2026-09-04 (see each folder's `logs/checks_report.md`).
`3_Final/` holds one appended-across-waves file per unit of observation and per module; nothing
is merged across units or aggregated — household summaries are a `groupby` on the module files,
whose rows all carry the key block. The EICV item-level consumption modules are large (the food
module is 10.8m rows, 5.8 GB); `POOL_ITEM_MODULES` in its `02_merge.py` can switch them off.
Total footprint of `2_Intermediate/` + `3_Final/` across the seven datasets is roughly 30 GB.

## Layout of every dataset folder

```
master.py           runs 00 -> 04; one log per run in logs/; stops at the first failure
<ds>_helpers.py     dataset-local helpers (paths, logging, Stata I/O, name/label hygiene)
00_benchmark_old.py records check statistics of any pre-existing outputs before overwriting (idempotent)
01_clean.py         1_Raw -> 2_Intermediate : one cleaned file per wave and unit
02_merge.py         2_Intermediate -> 3_Final : one pooled file per unit of observation
03_checks.py        independent verification -> logs/checks_report.md
04_codebook.py      CODEBOOK.md + codebook_<unit>.csv generated from 3_Final
DECISIONS.md        every crucial step and decision, and why (hand-written, chronological)
CODEBOOK.md         generated; do not hand-edit
logs/               run logs, per-wave metadata, alignment decisions, check reports (committed)
```

## Conventions (identical in every dataset)

**Units.** One pooled file per unit of observation, named `<SURVEY>_pooled_<unit>.dta`;
per-wave files `<SURVEY>_<wave>_<unit>_clean.dta`. Household surveys produce `person` and
`household` (CFSVA also `child`, `village`); the Establishment Census `establishment`; the
SAS `plotcrop` (plot × crop × season × year). No cross-survey harmonisation: each survey is
harmonised within itself only.

**Key block** — the same names and codes everywhere:

| variable | meaning |
|---|---|
| `survey` | source survey (string) |
| `year` | survey year (int) |
| `wave` | wave label as a string (e.g. `2017`, `EICV4_CS`, `2015_A`) |
| `round` / `quarter` / `interview` | sub-annual round where the survey has one |
| `prov` | province, NISR code 1–5 |
| `dist` | district, NISR code 11–57 |
| `sector` | sector, NISR code 1101–5715 — only where the file carries it |
| `urban` | 1 urban, 2 rural |
| `cluster` | sampling cluster id (string, `<year>_<psu>`) |
| `hhid`, `pid` | household id (unique within wave [+ round]); person number within household (EC: `estid`; SAS: `segment holder plot crop`) |
| `sex`, `age` | person files only: 1 male / 2 female; age in years — plain renames, native codes |
| `wt` | the weight that sums to the population of the unit (person weight in person files, household weight in household files) |

**Everything else is carried, never dropped,** under its lower-cased original name. A
same-named variable is one column across waves when its labels describe the same question.
Waves are grouped into *versions* by label similarity (token Jaccard ≥ 0.25 to the group's
first label); the largest group keeps the name, the others become `<name>_v2`, `_v3` … in
order of first appearance. A short `FORCE_ALIGN` list in each `02_merge.py` records the
rewordings the data owner judged to be the same question. Every decision and every label
variant is listed in the codebook. Value labels are the union within a version; where the
same code carries different text the most recent wave's text is kept and the conflict listed.

**Types and units.** Lower-case names, Stata-legal (≤32 chars). Numeric-looking strings
are destringed. Storage types are the smallest exact ones (byte/int/long/float/double);
weights and ids stay double. Area in hectares, production in kilograms, money in nominal RWF
with the year attached, age in years. Dates as Stata dates. Nothing is imputed or recoded
beyond the key block.

**Verification.** Every step logs PASS/FAIL checks; a failure stops the run. Crucial
numbers are computed two independent ways and compared: Python vs a Stata recomputation
on the written files, new outputs vs the archived Stata pipeline's outputs (where those
existed), weighted totals vs figures published in NISR reports.

## Running

```bash
cd NISR/Labour-Force-Survey-LFS && python master.py        # everything
python master.py 01 02                                      # selected steps
python 01_clean.py 2019                                     # one wave (for debugging)
```

Requirements: Python ≥ 3.10, pandas ≥ 2.0, numpy, pyreadstat (reading). Stata is optional
(section B of the checks is skipped without it).
