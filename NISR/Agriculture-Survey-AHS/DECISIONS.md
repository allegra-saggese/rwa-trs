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

**Pooled modules.** Only 2017 and 2024 files are mapped to canonical modules (milk, honey,
land, extension, tools, livestock, credits/savings …); the 2020 section files are numbered
without titles and are left per-wave until their content is mapped from the questionnaire.
