# Data catalogue

Every dataset in `output/tables/data_table.tex`: what it contains, where it
lives, how many years, and where it came from. Verified against disk on
2026-09-04 — row counts and year ranges are read from the files, not recalled.

**Dropbox root** (`$DB` below):
`~/Library/CloudStorage/Dropbox/Rwanda - TRS/data/`

**Repo root** (`$R`): `~/Documents/GitHub/rwa-trs/`

Legend: ✅ held · ⏳ requested/in progress · ❌ not obtainable yet

---

## Panel A — Economic measures

### RDB project data ❌
- **Location** `$DB/RDB/` — README only, no data
- **Coverage** annual 2005 onwards (target)
- **Source** Rwanda Development Board, via letter of approval then district governments
- **Contents** TRS projects: location, category, amount, approval/disbursement/completion dates; park visitor numbers **by gate**; park revenue by source
- **Note** This is the treatment variable. No public substitute. Gate-level visitor counts are required for the tourism-exposure measure; park totals alone would not identify it.

### Population and Housing Census (PHC) ✅
- **Location** `$DB/Publicly-Available-NISR/Census-PHC/`
  - `Raw/2002/Census_2002.sav` — 814,432 rows × 112 vars
  - `Raw/2012/Census_2012.dta` — 1,038,369 × 115
  - `Raw/2022/Census_2022.dta` — 1,313,015 × 250
  - `2_Intermediate/Census_<year>_person_clean.dta` and `Census_<year>_household_clean.dta` for 2002, 2012, 2022 (Python pipeline `rwa-trs/NISR/Census-PHC/`, 2026-09-04)
  - `3_Final/Census_pooled_person.dta` — 3,165,816 × ~700 (2002 + 2012 + 2022) · `3_Final/Census_pooled_household.dta` — one row per private household
- **Coverage** 3 waves: 2002, 2012, 2022
- **Source** NISR, microdata.statistics.gov.rw
- **Contents** Activity status; occupation, industry, employment status, public/private sector; migration (place of birth, previous residence, duration); education; housing and assets; sector population
- **Why it matters** The only source geocoded below district: `sector`, 416 named codes matching the NISR village file exactly (416/416). 2002 is kept raw only — pre-2006 boundaries, French labels, excluded by project decision.
- **Weights** `wt` (person, sums to 13,245,753 against 13,246,394 published) and `wt_hh`. The microdata is a ~10% sample; unweighted counts are not population.

### EICV ✅ (6 of 7 waves)
- **Location** `$DB/Publicly-Available-NISR/Household-Living-Conditions-EICV/`
  - `1_Raw/EICV1..EICV7_VUP/` — original NISR data files (zips extracted; questionnaires in `z_Documentation/`)
  - `2_Intermediate/EICV_<wave>_person_clean.dta`, `EICV_<wave>_household_clean.dta` and one file per module for EICV1, EICV2, EICV3, EICV4_CS/VUP, EICV5_CS/VUP, EICV7_CS/VUP
  - `3_Final/EICV_pooled_person.dta` (EICV1–7 national cross-sections, 327,841 rows), `EICV_pooled_household.dta`, the `_vup` counterparts for the VUP boosters, pooled modules (`EICV_pooled_<module>.dta`) and the linking files `EICV3_4_panel_link.dta` / `EICV5_vup_panel_link.dta` — Python pipeline `rwa-trs/NISR/Household-Living-Conditions-EICV/` (2026-09-04); every module of every wave is in `2_Intermediate/`
- **Coverage** 2000, 2005, 2011, 2013/14, 2016/17, 2023/24. **EICV6 (2020/21) missing** — not in the NISR public catalogue; covered ~40% of planned sample due to COVID
- **Source** NISR, microdata.statistics.gov.rw (login + data request; the public study page carries documentation only)
- **Contents** Consumption aggregate, poverty status, inequality; employment status, hours, own-farm work, nonfarm wage and business activity, ISCO occupation, ISIC industry, status in employment, contract type, main-job earnings; education, health, housing
- **Comparability** EICV4↔EICV5 pool cleanly. EICV3→EICV4 and EICV5→EICV7 are methodological breaks. EICV7 poverty is on a revised basis and a January 2024 price base — NISR explicitly cautions against comparing it to earlier rounds. See `eicv_rounds.md`.

### Labour Force Survey (LFS) ✅
- **Location** `$DB/Publicly-Available-NISR/Labour-Force-Survey-LFS/`
  - `Raw/2017..2025/LFS_<year>.dta` + questionnaires
  - `2_Intermediate/LFS_<year>_person_clean.dta` and `LFS_<year>_household_clean.dta` (Python pipeline `rwa-trs/NISR/Labour-Force-Survey-LFS/`, 2026-09-04)
  - `3_Final/LFS_pooled_person.dta` — 724,015 × 441 (person-interviews) · `3_Final/LFS_pooled_household.dta` — 166,772 household-interviews
- **Coverage** annual, 2017–2025 (9 years, all present)
- **Source** NISR, microdata.statistics.gov.rw
- **Contents** Activity status; ISCO occupation and ISIC industry; formal/informal employment, contract type; time-related underemployment; entrepreneurship
- **Note** The more consistent labour series over time than the EICV employment module. Finest geography is **district**; `psu` (1,242) is anonymised. LFS 2020 is a reduced file (55 vars) and 2019 has no urban variable.

### Establishment Census (EC) ✅ (all 5 rounds)
- **Location** `$DB/Publicly-Available-NISR/Establishment-Census-EC/1_Raw/<year>/` (cleaned + pooled by `rwa-trs/NISR/Establishment-Census-EC/`: `3_Final/EC_pooled_establishment.dta`)
  - `EC_2011.sav` 127,662 establishments · `EC_2014.sav` 77,151 · `EC_2017.sav` 190,288 · `EC_2020.dta` 232,283 · `EC_2023.dta` 269,326
- **Geographic depth degrades by round** 2011 → village · 2014 → **sector** (national code, matches Census 416/416) · 2017/2020/2023 → district only. `q1_5_1` in later rounds is *village type*, not a village id. EC 2011's ID2/ID3 are province-relative, not national codes, and are unmapped
- **Coverage** 5 rounds: 2011, 2014, 2017, 2020, 2023
- **Source** NISR catalog ids **62** (2011), **67** (2014), **87** (2017), **94** (2020), **112** (2023). Login required; public study pages carry questionnaires and reports only
- **Contents** All economic activities by size, formal/informal status; location; ISIC; employment; year of establishment
- **Why it matters** Full count with establishment location — the operative firm-side source, since IBES cannot support sub-provincial work

### IBES ✅ (aggregates only)
- **Location** `$DB/Publicly-Available-NISR/Business-Survey-IBES/`
  - `IBES2024_Main_Report_English.pdf` (3.9 MB)
  - `IBES2024_Tables_and_Figures.xlsx` (517 KB, 5 sheets)
- **Coverage** 2024 report; series runs 2014–2024 (2019 and 2021 combined)
- **Source** statistics.gov.rw publication page — **not** in the microdata catalogue
- **Contents** Firm employment by sex; income, expenditure, assets, equity, liabilities, access to finance; ownership residency; legal form; ISIC section
- **Hard limit** The only geographic breakdown in the published tables is the **five provinces**. No district, no sector. Cannot support a sector-level design; use as national/provincial context only.

### Agriculture Household Survey (AHS) ✅ (3 waves)
- **Location** `$DB/Publicly-Available-NISR/Agriculture-Survey-AHS/1_Raw/<year>/` — 2017, 2020, 2024 section files (pooled by `rwa-trs/NISR/Agriculture-Survey-AHS/`: `3_Final/AHS_pooled_person.dta`, `AHS_pooled_household.dta`, pooled modules)
  - Section 1 household members 16,292 × 142 · Section 2 land tenure 23,266 × 20 · Sections 3–4 crops/inputs 32,616 × 331 · Section 5 fruits 9,193 · Section 6 extension 9,286 · Section 7 tools 9,981 · Section 8 sustainable ag 3,724 · Sections 9–12 livestock 9,947 · milk 12,209 · eggs 19,077 · honey 9,387 · credits 5,224 · savings 10,342 · Section 0 roster 3,724
- **Coverage** 2017, 2020, 2024 — all three held (`Agriculture-Survey-AHS/AHS-<year>-microdata/`)
- **Not poolable as-is** Identifiers differ per wave: 2017 `idquest` + `s0q1/s0q2`; 2020 `HHUID` + `s0q1/s0q2`; 2024 `hhid`/`clust` + named `province`/`district`. Match on question content, not code
- **Source** NISR
- **Why it matters** Carries the crop area, yield and agricultural-income content EICV7 dropped when its agriculture module was discontinued. Geography: district.

### Seasonal Agriculture Survey (SAS) ✅ (2 waves)
- **Location** `$DB/Publicly-Available-NISR/Season-Agriculture-Survey-SAS/1_Raw/<year>/` — 13 waves 2013–2025 (pooled by `rwa-trs/NISR/Season-Agriculture-Survey-SAS/`: `3_Final/SAS_pooled_plotcrop.dta` 2017–2025 plot × crop × season)
- **Coverage** 2019, 2020. Not held: SAS 2021 (id **102**), SAS 2022 (id **103**)
- **Source** NISR
- **Unit** **PLOT within a sampled SEGMENT — not a household.** `Segment_ID`, `s1q1` province, `s1q2` district, `s1q3` stratum, `s1q4` segment, `s2q1` plot, `s2q2` plot area m². No household id, so it does not join to AHS or EICV at household level
- **Seasons** Files split by Season A (Sep–Feb), B (Mar–Jun), C (marshland). Stack deliberately — weights and definitions differ by season
- **Why it matters** The agricultural area frame RCMRD Scheme II was meant to crosswalk to, and the only source of within-year seasonal variation

### DHS ⏳
- **Location** `$DB/DHS/covariates/RWGC{62,81,8A,91}FL/` — 4 rounds of **Geographic Covariates**
- **Wrong file type held** RWGC = covariates (DHSID, DHSCLUST, pre-computed population/aridity/temperature per cluster; 560 rows × 135 cols). **No latitude or longitude.** The GPS files are **RWGE##FL** — still needed
- **Coverage** 5 rounds: 2000, 2005, 2010, 2014/15, 2019/20
- **Source** dhsprogram.com
- **Files to take** GE (GPS), HR (household), PR (member), IR (women), MR (men). Skip KR/BR unless child health is in scope
- **Critical limit** Cluster coordinates are displaced up to 2 km urban, 5 km rural, 1% of rural up to 10 km. Sectors average 64 km² and `Border_s` is a 1 km rule, so **DHS cannot assign households to border sectors**. Use distance-to-park as a continuous measure, or work at district level.

---

### Harmonised NISR layer ✅ (2026-09-05)
- **Location** `$DB/Publicly-Available-NISR/Harmonized/` — `H_<dataset>_<unit or module>.dta`, one harmonised copy of every final and appended file of the seven NISR pipelines (71 written; the six largest EICV item-module copies — food, own consumption, expenditure annual/monthly/frequent, durables — were removed to free the Mac's disk and are listed as skipped until `python NISR/Harmonize/01_harmonize.py EICV` is rerun with space available)
- **Coverage** every wave of LFS 2017–2025, Census 2002/2012/2022, EICV1–EICV7, EC 2011–2023, AHS 2017/2020/2024, SAS 2013–2025, CFSVA 2006–2024
- **Source** built by `$R/NISR/Harmonize/` (`master.py`); map of every code rule in `harmonization_map.csv` and code lists and counts in `CODEBOOK_Harmonized.xlsx`, both in that Dropbox folder (the repo holds code and logs only; reasoning in the project notes kept with the chat memory)
- **Contents** same rows and native variables as the source file, plus identical key-block labels and NISR geography value labels, cross-dataset keys `h_hhkey` / `h_pkey`, and on person / household / woman files the `h_*` concepts: sex, marital status, relationship to head, ever attended, education (4 levels), literacy, labour-force status with its definition code `h_lfs_def`, employed, status in employment, ISIC section, ISCO major group (approximation flags), head's sex and age
- **Note** employment measures carry different definitions and age bases by source (`h_lfs_def` 1–8); do not compare levels across definitions. The census 2022 public file has no labour-force identification block, so its status is missing.

## Panel B — Conservation and environmental measures

### JRC Tropical Moist Forest (TMF) ✅
- **Location** `$DB/geo-data/forest/tmf_by_sector.csv` (1.8 MB) · also `$R/data/processed/`
- **Coverage** **34 years, 1990–2023**, all 416 sectors — 14,144 sector-years, complete
- **Source** Earth Engine `projects/JRC/TMF/v1_2023/AnnualChanges`, 30 m
- **Contents** Area in hectares per sector-year of: undisturbed forest, degraded forest, deforested, regrowth, water, other land cover
- **Coverage caveat** The humid-tropical-forest mask covers ~2.43M of Rwanda's 2.63M ha; it includes Volcanoes and Nyungwe but not Gishwati-Mukura
- **Headline** Undisturbed forest 1990→2023: **−33.4%** in park-bordering sectors, **−95.2%** elsewhere. Sharp discontinuity 1995–2000 (genocide and resettlement).

### RADD deforestation alerts ✅
- **Location** `$DB/geo-data/forest/radd_by_sector.csv`
- **Coverage** **7 years, 2019–2025**, all 416 sectors — 2,912 sector-years
- **Source** Earth Engine `projects/radar-wur/raddalert/v1`, africa/alerts, 10 m
- **Contents** Hectares of **confirmed** alerts (Alert==3) per sector-year. Date is YYDOY encoded
- **Critical caveat** Restricted to the primary humid tropical forest mask, which in Rwanda is almost entirely inside the parks: **340 of 341 ha** of alerts fall in park-bordering sectors. Supplies essentially no non-park variation — not a substitute for Hansen or TMF outside the parks.

### Dynamic World ✅
- **Location** `$DB/geo-data/land-cover/dw_by_sector.csv`
- **Coverage** **10 years, 2015–2024**, all 416 sectors — 4,160 sector-years (collection begins June 2015, so 2015 is partial)
- **Source** Earth Engine `GOOGLE/DYNAMICWORLD/V1`, 10 m, reduced at 30 m
- **Contents** Annual mean per-pixel probability of each of nine classes: water, trees, grass, flooded vegetation, crops, shrub and scrub, built, bare, snow and ice
- **Headline** trees 0.226→0.263 and built 0.139→0.177 (2016→2024), shrub/scrub 0.240→0.185

### RCMRD/SERVIR Rwanda land cover ❌
- **Location** `$DB/geo-data/land-cover/` — empty
- **Coverage** would be 1990, 2000, 2010, 2015
- **Source** RCMRD, for the Government of Rwanda under the WAVES natural-capital-accounting programme, supporting the LULUCF inventory. Landsat supervised classification, maximum likelihood, 30 m
- **Blocked** `geoportal.rcmrd.org` resolves but accepts no connection (http or https). `opendata.rcmrd.org` is up but its ArcGIS Hub catalog API returns 400 and lists nothing Rwandan. Not mirrored on HDX.
- **What it costs** The pre-2015 half of the land-use series. RCMRD ends where Dynamic World begins, so together they would give continuous 1990–2025 coverage; without it that series starts in 2015. TMF partly compensates for forest classes but not for the agricultural/settlement classes that crosswalk to the SAS strata. Take **Scheme II** (disaggregated land cover), not Scheme I (IPCC classes).

### Hansen Global Forest Change ✅
- **Location** `$DB/geo-data/forest/`
  - `hansen_forest_loss_by_sector.csv` — 416 sectors, `treecover2000_ha` + `loss_<year>_ha` for 2001–2024
  - `hansen_sdpt_by_sector.csv` — the same plus SDPT planted area and early/late loss splits
  - `hansen_rwanda_lossyear.tif` (2.6 MB), `hansen_rwanda_treecover2000.tif` (16 MB)
- **Coverage** **24 years, 2001–2024**, all 416 sectors
- **Source** GFC-2024-v1.12, direct tiles `00N_020E` + `00N_030E`, merged and clipped, 30 m
- **Headline** 825,196 ha tree cover in 2000, 101,953 ha lost 2001–2024. Loss runs 1,200–2,100 ha/yr through 2012 then 5,500–9,100 ha/yr from 2013

### WRI SDPT (planted trees) ✅
- **Location** `$DB/geo-data/planted-trees/`
  - `sdpt_rwanda.gpkg` — **103,138 polygons**, 298 MB, full attributes
  - `sdpt_by_sector.csv` — 414 sectors, planted area in hectares
- **Coverage** **Rwanda source imagery 2008** (382/400 sampled polygons), small 2019 oil-palm subset. GFW release v20231128
- **Vintage warning** SDPT is billed as a 2020 product, but the Rwandan layer is a **2008 snapshot** from the Government of Rwanda. `plantedyear` runs from the early 1980s (1982, 1984, 1989, 1991, 1994, 2003). Post-2008 plantations are absent, so this is a **lower bound** on current planted area
- **Source** GFW data-API, keyset-paginated with a geometry filter
- **Contents** simplename, simpletype, sizecategory, ownership, leaftype, woodtype + geometry. 100,317 of the polygons are "Wood fiber or timber"
- **Why it matters** 291,944 ha = **35.4%** of Hansen's 2000 tree cover. Sector planted area correlates **0.154** with 2001–2012 loss but **0.565** with 2013–2024 loss — the post-2013 surge is plantation rotation, not a change in deforestation pressure
- **Version trap** GFW's highest-numbered version, v20239998, contains **only Uruguay**. Use v20231128.

### CHIRPS precipitation ✅
- **Location** `$R/data/processed/rainfall_monthly.csv`, `rainfall_annual.csv`, `district_panel.csv`
- **Coverage** monthly 2000–2024 built (record starts 1981), 30 districts — 9,000 district-months, 750 district-years
- **Source** Climate Hazards Center UCSB, CHIRPS v2.0 Africa monthly, 0.05°
- **Contents** District rainfall totals, within-district z-scores and percentiles, drought indicator
- **Note** Currently district-level, not sector. Design caveat: shocks are ~79% absorbed by year fixed effects (mean pairwise correlation of district anomalies 0.79).

### Animal censuses ❌
- **Location** none
- **Source** RDB / park authorities — not public

---

## Panel C — Infrastructure and settlement

### Google Open Buildings ✅
- **Location** `$DB/geo-data/buildings/`
  - `gob_rwanda_buildings.parquet` — **5,813,271 building polygons**, 570 MB, each stamped with sector_id, district, park exposure
  - `gob_buildings_by_sector.csv` — 416 sectors
- **Coverage** v3, single vintage
- **Source** Google Research, S2 tile `19d` (2.1 GB), filtered to Rwanda
- **Contents** Polygon footprint, area in m², detection confidence, plus-code
- **Note** The sector aggregate counts 5,815,098 (centroid join); the parquet has 5,813,271 (polygon `within` join). The 1,827 difference is buildings straddling sector borders.

### GRID3 settlement extents ✅
- **Location** `$DB/geo-data/settlements/GRID3_RWA_settlement_extents_v3_0.zip` (49 MB) + release notes PDF
- **Coverage** v3.0, 2024 release — **25,122 settlement polygons**
- **Source** GRID3 via HDX, CC BY-SA
- **Contents** building_count, building_area, type, probability, date, source, mgrs_code
- **Note** This is the v3.0 extents product, not the 2018–21 land-use-change layer.

### gridfinder ✅
- **Location** `$DB/geo-data/electricity/`
  - `gridfinder_rwanda.gpkg` — 711 line features, 2,671 km within Rwanda
  - `gridfinder_by_sector.csv` — grid km and km/km² per sector
  - `gridfinder_targets_global.tif` — 28 MB electrification-targets raster
- **Coverage** single vintage (2020)
- **Source** Zenodo record 3628142, CC BY 4.0 (global `grid.gpkg`, clipped)
- **Headline** Park sectors have half the grid density of the rest: 0.08 vs 0.16 km/km²

### OpenStreetMap infrastructure ✅ (partial)
- **Location** `$DB/geo-data/tourism/rwanda_tourism_osm.{gpkg,csv}` — 888 POIs across 143 sectors
- **Coverage** continuously edited; snapshot 2026-09-04
- **Source** Overpass API
- **Contents** hotels, guest houses, lodges, hostels, chalets, camp sites, attractions, museums, viewpoints, information points, restaurants — each joined to its sector with park exposure. 469 are accommodation; 61 within 5 km of a park (VNP 21, Nyungwe 24, Akagera 16)
- **Not yet pulled** road network and park gates

---

## Panel D — Geographic base layers

### NISR administrative boundaries ✅
- **Location** `$DB/Publicly-Available-NISR/geodata-nisr/`
  - `Village_Boundary_2022_4682352090287555743.zip` — 27 MB shapefile
  - `Village_Boundary_2022_924768113126413998.csv` — 14,823 rows
  - `Cell_Office_...zip`
- **Coverage** 2022 census vintage
- **Source** NISR open data
- **Contents** 5 provinces, 30 districts, **416 sectors**, 2,148 cells, **14,823 villages**, with the nested national code scheme (province 1 → district 11 → sector 1101 → cell 110101 → village 11010101)
- **Why it matters** The sector codes match the Census microdata exactly, 416/416. This is what makes sector-level analysis possible, and it also supplies the district-code concordance that `crosswalk.txt` lists as an outstanding NISR ask.

### WDPA / Protected Planet ✅
- **Location** `$DB/geo-data/protected-areas/`
  - `WDPA_WDOECM_Sep2026_Public_RWA_shp.zip` (11 MB) + extracted shapefiles
  - `wdpa_rwanda.gpkg` — 7 polygons
  - `sectors_park_exposure_wdpa.{gpkg,csv}` — 416 sectors with park share, distance, nearest park
  - `border_sectors_51.csv` — the 51 treated sectors
  - `rwanda_protected_areas_osm.{gpkg,geojson}` — OSM alternative, kept for comparison
- **Coverage** September 2026 release
- **Source** protectedplanet.net country download (no token needed)
- **Contents** Akagera 1,023.6 km² · Nyungwe 1,019.4 · Volcans 162.7 · Gishwati-Mukura 32.1 · Rugezi Ramsar 68.8 · plus Nyungwe World Heritage and the Volcans Biosphere Reserve
- **Verified** `Border_s` = touches or within 1 km reproduces the proposal exactly: **51 sectors, 14 districts, 1,549,299 people**
- **Open decision** Volcanoes appears twice — National Park 162.7 km² vs UNESCO-MAB Biosphere Reserve 454.5 km². The national park is used. If TRS eligibility follows the buffer zone, the biosphere footprint is correct and all counts change.

---

## Summary

| Panel | Held | Outstanding |
|---|---|---|
| A. Economic | PHC, EICV, LFS, IBES (aggregates), AHS | RDB, EC (downloading), DHS (granted), EICV6 |
| B. Conservation | TMF, RADD, Dynamic World, Hansen, SDPT, CHIRPS | RCMRD, animal censuses |
| C. Infrastructure | Open Buildings, GRID3, gridfinder, OSM tourism | OSM roads and gates |
| D. Geographic | NISR boundaries, WDPA | — |

**Every derived layer keys on `sector_id`** and joins to the Census microdata, the park-exposure table, and each other.
