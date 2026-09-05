# Seasonal Agriculture Survey (SAS) — decisions log

## 2026-09-04 — first pipeline (nothing existed before)

**Three designs in thirteen waves.** 2013 (topic files per season, `IDQUEST`/tract keys,
own crop list, weights `Coef`); 2014–2016 (farm questionnaire "parts" per season, `idquest`
/`tractid`, stratum weights, own crop list, no district in most files); 2017–2018 (per
season × small-scale/large-scale: screening, crop production, fertilizers, pesticides,
irrigation/tenure, anti-erosion; plot weights only in the screening file); 2019–2025 (per
season: crop production, part III fertilizers/pesticides, part IV practices, part V tenure
/ screening files; plot weights in the files from 2020). Crop codes are one list from 2017
(101 Maize, 102 Paddy rice, …); 2013 and 2014 use their own lists.

**Every file is cleaned on its own** (`2_Intermediate/SAS_<year>_<season>_<module>_clean.dta`)
with the key block attached wherever the file allows: `survey year season wave farm_type
prov dist stratum segment holder plot crop wt`. The native variable behind each key is
recorded per file in `logs/clean_<year>_meta.json`. 2013's `ID2A` is a within-province
sequence, not a district code, and is kept as `dist_seq`. Small tabulation files shipped
inside the microdata packages (yield tables, province area summaries, weight tables) are
written with `level = table` and never pooled.

**Pooled plot × crop file, 2017–2025.** One row per plot × crop × season × year from the
crop-production module (small- and large-scale farmers). The core quantities are mapped
explicitly per year in `CORE` (`02_merge.py`): plot area (m² → ha where shipped in m²),
crop area (2017–2021, 2025), harvested area (2018–2019, 2022–2023, 2025), production
(kg, `s2q22` in 2017, `s2q21` after), NISR's yield where shipped (2022–2025). Question
numbers shift between years (e.g. `s2q21` is "remaining quantity" in 2017 and "total
harvest" from 2018), which is exactly why the map is explicit and why the version rule keeps
same-named, different-question variables apart. **Weights**: 2017–2019 production files ship
none; the plot weight is merged from the same season's screening file on (segment, plot),
falling back to the segment weight, and `wt_source` records what happened per row.

**2013–2016 plot × crop records** are appended into `SAS_pooled_plotcrop_2013_2016` with
`source_module` tagging the record type (crop-area files, sowing/planting files, big-farmer area
files, screening files) and the waves' own crop lists; crop area is filled where the record type
carries one (2013 area files, 2014 screening), missing otherwise (2015–2016 ship no plot-level crop
area). Other 2013–2016 modules with the same file name in two or more years are appended as
`SAS_pooled_<module>_2013_2016`; the 2017–2018 modules (fertilizers, pesticides, anti-erosion,
irrigation/tenure, screening) as `SAS_pooled_<module>_2017_2018`.

**Layout (2026-09-04, Matteo).** `3_Final/` holds only the appended unit-level datasets; every
module-level file — per wave at the top of `2_Intermediate/`, appended across waves in
`2_Intermediate/appended/` — lives in Intermediate. For SAS: `3_Final/` = `SAS_pooled_plotcrop` (2017–2025) + `SAS_pooled_plotcrop_2013_2016`; every appended module (2013–16, 2017–18, 2019+) is in `2_Intermediate/appended/`.

## 2026-09-04 — documentation pass (see DOCUMENTATION.md)

The questionnaires confirm the three designs already implemented (2013 tract/plot phases, 2014–16
farm-questionnaire parts, 2017+ plot questionnaire with small/large-scale farmer type from 2019)
and the code lists (own 34-crop list in 2013/14, the 101–520 list from 2017, land-use 96–99 and
strata 10/20/30/40/90 in the screening files). No sampling or weighting report is held, so the plot
weights stay as shipped and no published total is checked. The codebook headers now state the
universe of each pooled file.
