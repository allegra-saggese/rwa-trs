# Harmonize — decisions log

## 2026-09-05 — cross-dataset harmonisation layer (agreed with Matteo on 2026-09-04)

**What it is.** A separate code base (`NISR/Harmonize/`, own helpers, run by `master.py`) that reads
every dataset's `3_Final/` and `2_Intermediate/appended/` files and writes a harmonised **copy** of
each to `Publicly-Available-NISR/Harmonized/` as `H_<dataset>_<unit or module>.dta`. The old
three-file harmonisation of July 2026 stays untouched in `Archive/Harmonized/`. Nothing is
collapsed, aggregated or dropped: every output has exactly the rows and the native columns of
its source (`02_checks.py` §A).

**Stylistic layer (every file).** Identical key-block variable labels; identical province /
district / sector value labels (NISR village file, the project's geographic spine), `urban` and
`sex` labels; `h_hhkey` = `survey_wave[_interview]_hhid` and `h_pkey` = `h_hhkey_pid` as strings
unique across datasets and waves (the LFS household is interviewed up to three times a year, so
the interview index is part of the key).

**Concept layer (person files of LFS, Census, EICV incl. the VUP pool, AHS; household and woman
files of CFSVA; head's sex/age on every household file).** Common names, common codes, kept as
new `h_*` variables next to the native ones (never overwriting). Code lists:
- `h_marital` 1 never married, 2 married or in union (monogamous, polygamous, cohabiting / partner),
  3 divorced or separated, 4 widowed.
- `h_relation` 1 head, 2 spouse, 3 child (own, step, adopted, foster; the census "unrelated child
  brought up in the household" is a child), 4 other relative, 5 non-relative (domestic worker,
  boarder, unknown).
- `h_attend` ever attended school; `h_educ` 0 none / pre-primary, 1 primary, 2 secondary (post-
  primary, vocational, lower and upper secondary), 3 tertiary — four levels because the 2012 census
  and the EICV class codes do not split lower / upper secondary consistently; tertiary is also set
  from the highest diploma where a class code stops at secondary (EICV: bachelor … doctorate).
- `h_literacy` 1 = can read AND write ("read only" = 0; the census 2012/2022 items are the
  languages read and written, 0 = none).
- `h_lfstatus` 1 employed, 2 unemployed, 3 outside the labour force, with **`h_lfs_def`** stating
  the definition and age base behind it (1 LFS ILO 7-day; 2 Census 2002 one-month situation; 3 Census
  2012 NISR relaxed 7-day; 4 EICV1/2 NISR 12-month usual activity; 5 EICV3/5 any work in 12 months
  incl. own farm — no unemployment item in EICV3; 6 EICV4 NISR current status; 7 EICV7/AHS 2024 any
  work in 7 days incl. own farm — no unemployment item; 8 AHS 2017/2020 main activity). `h_employed`
  = `h_lfstatus == 1`. The census 2022 public file has no employment identification block, so its
  status stays missing (only the employed have P46–P49). **These employment measures are not
  comparable across definitions** — that is what `h_lfs_def` is for; the informational table in
  `02_checks.py` §D shows the spread.
- `h_empstat` 1 employee (incl. paid apprentice / intern), 2 employer, 3 own-account / self-employed,
  4 contributing family worker, 5 other (cooperative member, unpaid apprentice, other). EICV3–5 have
  no person-level item (status sits in the jobs module) → missing; EICV2's NISR `workstats` has no
  employer category (approximate); LFS 2025 is NISR's ICSE-93 recode.
- `h_isic1` ISIC Rev.4 section 1–21 (A–U) and `h_isco1` ISCO-08 major group 0–9, exact where NISR
  ships 1-digit Rev.4 / ISCO-08 (LFS, census 2012 `rp27`/`rp25`, 2022 `p47a`/`p48a`, EICV4 `isic`/
  `isco`, EICV7 `s6bq4`/`s6bq3`); **approximate** (flagged in `h_isic1_approx` / `h_isco1_approx`)
  where the native code is an older or national list: census 2002 ISIC Rev.3 3-digit groups → division
  → Rev.4 section (`ISIC3_DIV_TO_SEC`), ISCO-88 3-digit → major group; EICV1/2 NISR industry groups
  11–93 → section (`EICV12_GRP_TO_SEC`, hotels & restaurants (64) → I, government/admin/social
  services (91) → O), NISR occupation groups → ISCO major (`EICV12_OCC_TO_ISCO`).
- CFSVA: the household file carries the head's characteristics, so `h_head_sex/age/marital/educ/
  literacy` are built there; the woman file gets `h_educ` / `h_literacy`; 2009 has no head block
  (missing).

**Harmonisation level per variable** is recorded in `harmonization_map.csv` (`level` column):
"all household surveys" for sex, marital, relationship, head sex/age; "education group" (Census,
EICV, LFS, + AHS, CFSVA) for attend / educ / literacy; "employment group" (LFS, Census, EICV, + AHS)
for status, employed, empstat, ISIC, ISCO. Establishment (EC), plot × crop (SAS) and every module
file receive the stylistic layer only, as agreed.

**Version rule respected.** The pooled files keep same-named-but-different questions apart as
`<name>_v2` …; the harmoniser looks the right column up per wave in each dataset's
`logs/merge_alignment.json` (`col_for`), so e.g. the census marital status is `p29_v2` in 2012 and
`p06` in 2022, the LFS 2025 status in employment is `d05_v2`.

**Two verification routes.** `02_checks.py` recomputes the labour-force status, marital status and
the head count independently from the native items and compares them with `h_*` (LFS status1,
census rp2024 / p21 / p29 / p06, EICV lfs6 / econstatus), asserts no row or native column is lost
and that household keys are unique.

**Disk.** The copies double the footprint of the pipeline outputs (~20 GB, the EICV item modules
alone ~8 GB). `01_harmonize.py` checks the free space before every write and skips a file (logged,
listed in the summary and the codebook) if less than `MIN_FREE_GB` would remain; rerun
`python 01_harmonize.py <dataset>` once space is freed.

**Disk incident, 2026-09-05 01:40.** The first full run wrote all 77 copies (≈ 20 GB) and left the
Mac with 4 GB free; the six largest EICV item-module copies (`H_EICV_food`, `_own_consumption`,
`_expenditure_annual/monthly/frequent`, `_durables`, 11.4 GB) were deleted again and are marked
"skipped" in `logs/harmonize_summary.json`, the codebook and `Harmonized/README.txt`.
`MIN_FREE_GB` is now 12. To rebuild them: free space (or make `2_Intermediate/` online-only in
Dropbox) and run `python 01_harmonize.py EICV`.
