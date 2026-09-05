# Census (RPHC) — decisions log

Running record of every crucial step and why. Cross-dataset conventions live in
`NISR/README.md`; this file records how they were applied to the Population and Housing
Census public-use samples and every census-specific call.

## 2026-09-04 — rebuild in Python, 2002 brought back in

**Raw files.** `1_Raw/2002/Census_2002.sav` (SPSS, French labels), `1_Raw/2012/Census_2012.dta`,
`1_Raw/2022/Census_2022.dta`. Each is NISR's 10% equal-probability sample of private
households (2012 and 2022 statements in `z_Documentation/`); the 2002 file additionally
carries 16,717 rows of collective/institutional households. The 2012 and 2022 files carry
latin1 labels in places; readers fall back to latin1.

**2002 is processed** (the archived Stata pipeline excluded it as "pre-2006"). Verified from
the data: the public 2002 file is already on the current administrative structure —
5 provinces, 30 districts, 416 sectors, codes nesting exactly (`Sector_Code // 100 ==
District_Code`). It is the only sector-level observation before the 2005 start of TRS and
carries the full labour module (P21–P25, including institutional sector = cooperative).

**2002 sector codes are assigned by name, not by the shipped code.** Comparing the 2002
sector names (`novsect`) with NISR's current village file (`geodata-nisr/`), 399 of 416
match exactly; 13 differ by spelling (R/L variants such as MUSHELI/Musheri) and match to
the only remaining candidate in the same district; and in Musanze the shipped codes
4301–4304 are **permuted** relative to the current scheme (shipped 4301 = Gashaki, current
4301 = Busogo, etc.). The pipeline therefore maps every 2002 sector to the current code by
name within district, logs the four re-coded sectors, and keeps the shipped code as
`sector_code_file`. District and province names agree 100%.

**Province / district / sector value labels** come from the NISR village boundary file
(`Village_Boundary_2022_...csv`, the project's geographic spine) and are attached in every
census year, so `label list` shows names for all 416 sectors. The pipeline asserts that
each year's sector set equals that list.

**Unit of observation = person; second file = household.** The person file keeps every
row of the public samples (2002 collective households flagged `collective = 1`). The
household file has one row per private household with every variable that is constant
within the household (the H-block, geography, weights), `hhsize` (roster count; equal to
NISR's shipped `hhsize` in 2012), and the head's sex and age. Collective households are
excluded from the household file.

**Weights.** `wt` = person weight (`Weight` 2002, `SampleWeight_Final_` 2012, `Pop_weight`
2022); it reproduces the published census totals (8.13m / 10.52m / 13.25m). `wt_hh` =
household weight: `HH_weight` in 2022; in 2002 and 2012 the samples are self-weighting
household samples with no separate household weight, so `wt_hh` = the household's person
weight (constant within household — asserted). The household file's `wt` is `wt_hh`.

**Household and person ids.** `hhid` as shipped (unique within year; nullable in 2002 for
collective rows). `pid` = NISR's person number in 2012/2022 (`P01`/`p01`, unique within
household); in 2002 `P00` is not unique within households (16,769 duplicate pairs), so
`pid` is the row order within the household and `P00` is kept as `pid_nisr`.

**Urban/rural.** 2002 and 2022 ship a 1/2 variable. 2012 ships four categories (weighted:
urban 13.9%, rural 75.3%, peri-urban 8.5%, semi-urban 2.3%); the key-block `urban` is 1
for "urban" only and 2 otherwise, and the native `l07` is carried untouched so any other
grouping can be rebuilt. NISR's published 2022 urban share (27.9%) is reproduced exactly.

**2002 labels.** Variable labels were transcribed into English from the 2002 questionnaire
(`z_Documentation/2002/Census_2002_questionnaire_household.pdf`); the French originals are
kept in `logs/clean_2002_meta.json` (`var_labels_original`) and shown in the codebook.
Value labels stay in French as shipped (they are NISR's codes; nothing is recoded), except
the key block. The household recap block `H110–H124` was decoded from the data (identities
such as `H112 = H110 + H111`, `H122 = H120 + H121`; best match to the roster counts by sex,
residence status and age 17+) and labelled accordingly. `H18` is empty in the public file.
`P061…AGE19` are NISR's duplicated age columns and are labelled as such.

**No sentinel recoding.** The archived pipeline set 9998/9999 ("missing"/"not applicable")
to Stata missing in the harmonised categorical variables. Here every carried variable keeps
its native codes and labels; the codebook lists the value labels so the sentinels are visible.

**Alignment across years.** Names differ by year anyway (2002 `P##`, 2012 `P##`, 2022
`p##`, all lower-cased), and the same name means different questions in different years
(e.g. `p21` = activity status in 2002, "why did not work" in 2012). The version rule
(label similarity) separates them automatically; forced alignments are listed in
`02_merge.py` once the first VERSIONS log has been reviewed.

## 2026-09-04 — documentation pass (see DOCUMENTATION.md)

**2012 `urban` now follows NISR's 2-way recode `rl07`.** The population-size report gives 16.5%
urban in 2012; in the sample L07 = 1 alone gives 13.9% while `rl07` (urban + semi-urban = 1,
rural + peri-urban = 2, verified cell by cell) gives 16.2%. The earlier rule (L07 = 1 only)
understated urbanisation and is replaced; `l07` is still carried, and a hard check asserts the
rl07/L07 correspondence.

**2002 value labels translated to English** for the key block and every concept variable, from
the English questionnaire (code lists match one-for-one). French originals are in
`logs/clean_2002_meta.json` (`value_labels_original`). P08/P10 (140 pre-2006 district names),
P18, P22 (ISCO-88) and P24/P241 (ISIC Rev.3) stay French — no English list exists in the
documentation and they are not concept variables.

**2012 recodes labelled from the data.** Cross-tabulations against the source questions:
`rp2024` 1 ⇔ P20 = 1 or P21 = 3 (on leave, 61,515 rows); 2/3 ⇔ P21 = 1/2 and P23 = 1; 4 ⇔ P21 = 0
home worker; 5 ⇔ P21 = 4/5; 6 ⇔ P21 = 6; the unlabelled code 9 (86,066 rows) collects
P21 = 7 "other" plus home workers and never-worked persons not available for work — labelled
"not classified" rather than guessed. `rp12` = any P12 difficulty; `rp142` = P14b × P14d;
`rl07` as above; `rp04y` = P04Y (identical on every row).

**ISCO-08 titles attached to 2012 `p25`** from NISR's own 2012 coding list; every one of the 418
codes in the data is in the list. No English ISIC Rev.4 list ships with the census documentation,
so `p27` keeps its bare codes (sections are in `rp27`); the Kinyarwanda ISIC list was not used.

**Universe per variable recorded** (`UNIVERSE` in `01_clean.py` → meta → codebook). Age
thresholds differ across censuses (activity 6+/5+/16+, education 6+/3+/all, literacy 6+/3+/10+,
fertility 12+/12+/10+); the harmonisation step must restrict on age explicitly rather than rely on
non-missingness.

**2022 employment identification (P37–P45) is not in the public file.** Only the job
characteristics P46–P49 of employed residents 16+ are released, so no labour-force status is
derived for 2022 (2002 and 2012 carry NISR's own status variables `p211` / `rp2024`).

**New published checks:** 2012 weighted population vs the private-household population
10,378,021 (labour-force report), and the weighted urban share per census vs 16.9 / 16.5 / 27.9%.
