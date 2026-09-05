# Agricultural Household Survey (AHS) — decisions log

## 2026-09-04 — first pipeline (nothing existed before)

**Waves.** 2017 (16 section files, `idquest` household id, segment sample), 2020 (15 numbered
section files, `HHUID`), 2024 (14 files, `hhid`/`pid` on the EICV7 id scheme — the 2024 AHS is
a 3,724-household follow-up sample; its section 3–4 file is seasonal, one row per plot × crop
× season). Geography is district everywhere (codes 11–57 as shipped); 2017 carries the
segment id, 2024 the cluster.

**Units.** Person file = roster (`s1…`) plus every person-level module; household file =
section 0 plus every household-level module, `hhsize` and the head's sex/age
(relationship code 1: `s1q3` 2017, `s1q4` 2020, `s1q2` 2024). Module classification and
1:1 joins follow the EICV rule (unique keys decide; identical duplicate columns dropped).
2017's section 0 lists 289 duplicate `idquest` rows (dwellings re-listed); the first row is
kept and the count logged.

**Weights.** Household weight carried by every row: `weight` (segment weight) in 2017;
in 2020 section 0 ships no weight, so it is taken from section 1 (constant within
household); 2024 `weight` is the "final season A weight".

**Pooled modules.** All three waves are mapped to canonical modules (milk, eggs, honey, land,
inputs, fruits, extension, credits, livestock, animal inputs, tools …). The 2020 section files are
numbered without titles; their content was mapped from the 2020 questionnaire (section II = land
tenure / crops & inputs / fruits, III = extension and programmes, IV = savings-credits, V–VI =
livestock numbers and stock change, VII = milk / eggs / honey, VIII = animal health, IX = animal
input expenditures). Modules that exist in one wave only stay per-wave in `2_Intermediate/`.

**Layout (2026-09-04, Matteo).** `3_Final/` holds only the appended unit-level datasets; every
module-level file — per wave at the top of `2_Intermediate/`, appended across waves in
`2_Intermediate/appended/` — lives in Intermediate. For AHS: `3_Final/` = person + household; the 13 appended modules are in `2_Intermediate/appended/`.

## 2026-09-04 — documentation pass (see DOCUMENTATION.md)

The 2017 report and the 2024 DDI describe two different frames: 2017 lists every household in 1,560
SAS/village segments and interviews the 16,057 with any member in crop or livestock production;
2024 takes all EICV7 households flagged agricultural in a 600-EA sub-sample of the EICV7 sample
(weights inherit the EICV7 weights). 2020 is documented only as "inverse probability of selection".
The waves are therefore pooled as independent cross-sections with their own weights, as already
implemented; the published 2017 household count is now a check, and the age bases of the roster
items (economic activity above 10 in 2017; savings/credit 16+ in 2020) are stated in the codebook.
