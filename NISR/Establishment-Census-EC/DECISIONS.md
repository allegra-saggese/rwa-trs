# Establishment Census (EC) — decisions log

## 2026-09-04 — first pipeline (nothing existed before)

**Raw files.** One file per census: 2011, 2014, 2017 (SPSS), 2020, 2023 (Stata). 2011 and 2014
questionnaires differ from the 2017+ series; 2017/2020/2023 share one questionnaire (q1_…q25).

**Unit = establishment.** Key block `survey year wave prov dist sector urban estid wt`. No id
is shipped in 2017–2023, so `estid = year*1e6 + row number`; 2011/2014 keep NISR's `key`.

**Geography.** 2014 ships the full 416-sector code (`ID3`, verified equal to NISR's current
list). 2011 ships only within-parent sequence numbers (`ID1…ID5`) plus names: the district
comes from NISR's own `Districts_names` (101… → 11…) and the sector from the sector NAME
matched within that district (closest spelling for variants; 4 names in 621 rows — Karago,
Busasamana, Mudende, Gatagara — sit in a district where no such sector exists and are left
missing). 2017–2023 carry district only. `urban` is recoded from `U_R` in 2011/2014 (NISR
coded 1 = rural, 2 = urban there) to the key-block 1 urban / 2 rural; `q1_5_1` already uses
1 urban / 2 rural.

**Weights.** Full enumerations (`wt = 1`) except 2014, whose public file is a sample with
`SampleWeight_Final_`; its weighted total reproduces the published 154,236 exactly.

**Checks against the reports** (`zz_Reports/`): 2011 operating establishments 123,526
(`S04 == 1`), 2014 weighted 154,236, 2017 190,288, 2020 232,283. No 2023 report is held.

**Everything else is carried** under its own name with the version rule; 2011/2014 items
(S…/Q…) and 2017+ items (q…) are different questionnaires and pool only where names match.

## 2026-09-04 — documentation pass (see DOCUMENTATION.md)

The English questionnaires confirm the coding used in the pipeline and add one published figure:
the 2014 project document states that the 2011 census enumerated 127,662 establishments, which is
exactly the 2011 file (`03_checks.py` §C). The universe (operating establishments with a fixed
location; permanently closed units are recorded in 2011 but end the interview) and the questionnaire
changes by round (institutional sector recoded in 2014 and 2020, contract categories 2014 vs 2017+,
4-digit ISIC only in 2011) are documented; no data change was needed.
