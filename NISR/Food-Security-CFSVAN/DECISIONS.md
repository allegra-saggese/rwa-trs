# CFSVA — decisions log

## 2026-09-04 — first pipeline (nothing existed before)

**Waves and units.** 2006, 2009, 2012, 2015, 2018, 2021, 2024 (NISR/WFP). Units per wave:
household; woman 15–49 (2006, 2009, 2012, 2015, 2024); child under 5 / 6–59 months (2006,
2009, 2012, 2015, 2018 child-and-mother, 2021 child-with-mother, 2024); village/community
(2009, 2012, 2018, 2021). 2009 also ships the household questionnaire in section files
(`s10b`, `s3_17`, `s4`, `s7`, `s8`, `s9` …); they are cleaned under their own names. Each unit
is pooled across waves with the version rule; no content is recoded.

**Household ids** as shipped: `hid` (2006), the composite `id1-id2-id4-id5-id6-id7` (2009,
verified unique), `hh_id` (2012), `KEY` (2015), `PARENT_KEY` (2018), `index` (2021),
`___index` (2024). Women/child files link to the household file on that id in 2006, 2009,
2012, 2018, 2021 and 2024 (match rates logged). **2015 women/child files do not link**: their
`PARENT_KEY` uuids come from the nutrition form, not the household form's `KEY`, and no
common household number is shipped; they are pooled as stand-alone units and already carry
the household-level variables NISR attached to them.

**Geography.** Districts come in three schemes — `101…` (2006, 2012, 2015, 2018), a
within-province sequence plus the district *name* (2009: matched by name to the NISR list),
and `11…57` (2021, 2024) — all mapped to the 11–57 scheme. Sectors are shipped in 2006 (5-digit),
2012, 2015 (5-digit) and 2018, converted to the 4-digit NISR code. 2006 covers 29 of the 30
current districts; 2009 excluded the three City of Kigali districts (27 districts). Urban/rural is shipped from 2012 on (2012 codes 1/0 recoded to 1/2).

**Weights.** `wt` is the household weight as shipped: `hhweight` 2006 (normalised, mean 1),
`FINAL_PopWeight` 2012 (population expansion; the normalised `FINAL_norm_weight` is carried),
`weight` 2015, `FinalWeight` 2018/2021/2024 (household expansion; sums ≈ 2.5m, 2.6m, 3.4m
households). **2009 ships no weight**: `wt` is absent and the file is flagged unweighted.

## 2026-09-04 — documentation pass (see DOCUMENTATION.md)

**Sample sizes from the methodology annexes are now checks** (households 2012 7,498, 2015 7,500,
2021 and 2024 9,000; women 2015 6,768; villages 2012 748). **2018 does not match the documentation:**
the shipped household file holds 9,709 households (unique ids) and the village file 987 villages,
against 9,000 households in 30 villages × 30 districts and 749 village interviews stated in the
2018 annex. The files are kept as shipped and the two figures are reported as informational rows in
`logs/checks_report.md`; NISR would have to say whether the extra rows are replacement or
additional households.

**Universes stated in the codebook headers**: households living in the sampled village at interview
time; women 15–49 (one record per woman); children under 5 (anthropometry 6–59 months, IYCF 6–23
months); one key-informant group per village. The design (district strata, PPS villages, 10
households per village, design weights adjusted for village size) is documented and the shipped
weights are used unchanged.
