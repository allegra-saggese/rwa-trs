# LFS — decisions log

Running record of every crucial step and why. Newest at the bottom. Cross-dataset
conventions live in `NISR/README.md`; this file records how they were applied to the
Labour Force Survey and every LFS-specific call.

## 2026-09-04 — rebuild in Python

**Why rebuild.** The Stata pipeline (archived at `Rwanda - TRS/_archive/code-NISR-stata-2026-09-04/`)
was repointed to the new folder scheme on 4 Sep but never re-run; its outputs date from
3 Jul 2026. Project decision: one language (Python) for every NISR dataset. Before
overwriting, the old outputs' check statistics were recorded once in
`logs/benchmark_old_stata.json` (`00_benchmark_old.py`, idempotent) so the rewrite can be
compared against them.

**Raw files.** One `.dta` per year, 2017–2025, `1_Raw/<year>/LFS_<year>.dta`. No zips. The
2019 and 2023 files carry latin1 (not UTF-8) labels; every reader falls back to latin1.

**Unit of observation in the raw files = person-interview.** The LFS is a rotating panel
within a year: 2017–18 have two rounds (February, August), 2019+ four quarters, and a
household is interviewed in more than one round. NISR's annual weight (`weight2`,
`weight` in 2019) already divides the round weight by the number of rounds, so summing
it over all rows reproduces the annual population. The person file therefore keeps one
row per person-interview, and the household file one row per household-interview.
Collapsing to person-year would require a cross-round person link that the public file
does not reliably provide.

**Round / quarter identification, by year (verified from the data):**
- 2017–2018: `phase` (1 = February, 2 = August).
- 2019: no round variable, but `pkey` = PSU(3–4) + household(2) + person(2) + round(2);
  the round digits take values 5–8 = FEB19/MAY19/AUG19/NOV19 under the numbering NISR
  labels in the 2020 file (0 = AUG16 … 12 = NOV20). Decoded into psu / hhid / pid / round.
- 2020: `LFS_round` 9–12 = FEB20…NOV20. `pid` is entirely missing in rounds 10 and 12 —
  a household key cannot be built for those two quarters.
- 2021: `LFS_round` 14–17 = FEB21…NOV21 (the 2021 file uses a different numbering: 2 = FEB17).
- 2022–2025: **no round variable at all.** 2023–2025 files are stored in four contiguous
  blocks (PSU_NO restarts three times) that correspond to the quarters; 2022 is sorted by
  PSU with the two interviews of a household adjacent. See the (HHID, weight2) test below.
Rounds are mapped to a common `round` string (e.g. "FEB20") and `quarter` (1–4;
February = 1, May = 2, August = 3, November = 4; for 2017–18 February = 1, August = 3).

**Household key.** Built as `hhid` = PSU × 100 + household number: 2017–18 from `pid` // 100,
2019 from `pkey`, 2021–2025 from NISR's own `HHID` (verified equal to PSU_NO*100+QH_NO
in every year), 2020 from `pid` where present. Exactly one head (`A02 == 1`) per
household-interview wherever the key is complete — used as the acceptance test.

**Harmonised key block** (identical names across every NISR dataset): `survey year wave
round quarter interview prov dist urban cluster hhid pid sex age wt` plus LFS-specific
`wt_round`, `psu`. `sex` and `age` are plain renames of A01/A04 (native codes; 1 male,
2 female; age in years) — the two demographics every NISR file carries.
`wt` = annual weight (person-expansion; sums to the population). `cluster` = year_psu.
`sector` is not in the LFS public file (district is the lowest geography) and is left absent
rather than filled with missings.

**All other variables are carried under their own (lower-cased) names.** Same name across
years = same column when the variable labels describe the same question. Years are grouped
into versions by label similarity (token Jaccard ≥ 0.25 to the group's first label); the
largest group keeps the name, the others become `<name>_v2`, `_v3` …. Every decision and
label variant is written to `CODEBOOK.md`. Value labels are the union within a version; where
the same code carries different text the most recent year's text is kept and the variants
recorded.

*Overrides after reading the split list (2026-09-04).* Forced to one column because the
2021/2025 questionnaires only reworded the question and the codes are compatible: `b01`
(currently studying), `d03a` (workplace has a name), `d06` (written/oral contract), `d23`
(type of workplace; 2025 adds two categories), `lu2` (label spelling), `psu_no` (label
only). Left as separate versions because the question or the coding really changed: `a15`
(2021/2025 ask "lived outside this district" — the opposite polarity of "always lived
here"), `d05` (2025 recodes status in employment to ICSE-93, 5 codes vs 7), `d18a` (2025
reuses the name for "how did you obtain your job"), `b15` (2025 reuses the name for
"time to first job"), `c21a`–`c21l` (job-search-method items change meaning across
2017/19, 2018/21 and 2024).

**Person-key duplicates.** NISR's own files contain a handful of rows with the same
person number inside one household-interview (2 in 2020, 1 in 2022). They are kept as
shipped; the uniqueness check is reported, not enforced.

**2020 household file** covers rounds 9 and 11 only (person/household ids were not
released for rounds 10 and 12), i.e. 37,319 of 70,172 person rows.

**Storage-type lesson.** `pd.concat` of yearly frames turns nullable-integer columns into
object dtype whenever a column is absent in some years; the writer then stores them as
strings. All frames are cast to float64 before concatenation and downcast afterwards, and
the writer refuses to stringify a numeric object column.

**Storage.** pandas `to_stata` (Stata 118 format) so small storage types survive; every
integer-valued variable is downcast (byte/int/long, or float if it has missings);
weights and ids stay double. pyreadstat only reads.
