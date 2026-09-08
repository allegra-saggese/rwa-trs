# Cleaning decisions

Internal record of every judgment call, with reasoning. Each entry is dated so
the log survives coauthor turnover.

---

## 2026-09-03 — District identifiers

**Decision.** Built `district_id` as a 1–30 integer assigned after sorting by
(province, district), rather than adopting GADM's `GID_2`.

**Why.** GID codes are not stable across GADM releases; a version bump would
silently repoint every merge. `district_id` is reproducible from names alone.
`gid_2` is retained as a column for traceability.

## 2026-09-03 — Place-name join keys

**Decision.** All place-name joins go through `normalise_name()`: lowercase,
strip accents, drop every non-alphanumeric character.

**Why.** GADM, NISR tables, and survey files disagree on case, accents, spacing,
and hyphens for the same district. Matching raw strings produces silent
unmatched rows that surface as unexplained missingness much later.

## 2026-09-03 — Projection

**Decision.** All spatial operations and all maps use EPSG:32735 (UTM 35S).
GADM's EPSG:4326 is reprojected on the way in.

**Why.** Areas and distances computed in degrees are wrong, and a map drawn in
lon/lat stretches Rwanda horizontally. Any buffer measured in km — notably the
DHS displacement buffers — requires a metric CRS to be meaningful.

## 2026-09-03 — Zonal statistics use `all_touched=True`

**Decision.** District rainfall is the mean of every CHIRPS pixel *touching* the
polygon, not only those whose centroid falls inside it.

**Why.** CHIRPS is ~5.5 km while the smallest districts are urban Kigali cells.
Kicukiro captures only 14 pixels even with `all_touched=True`; with centroid-only
matching some districts would draw on a handful of pixels or none.

**Consequence.** Adjacent districts share border pixels, so district rainfall
series are smoothed toward one another. This *inflates* the apparent spatial
correlation of shocks and should be acknowledged wherever cross-district
variation is the identifying variation. A robustness check using centroid-only
matching is worth running before anything goes in a paper.

## 2026-09-03 — Incomplete years dropped from annual aggregates

**Decision.** `build_rainfall_annual()` keeps only district-years with all 12
months present.

**Why.** CHIRPS publishes with a lag. A partially published current year would
otherwise sum to a low total and be recorded as a severe drought.

## 2026-09-03 — Anomalies benchmarked within district

**Decision.** `rain_z` and `rain_pctile` are computed against each district's own
long-run distribution, not against a national distribution.

**Why.** The west–east rainfall gradient is very steep (period means run ~967 mm
in Nyagatare to ~1414 mm in Nyabihu). A national benchmark would classify the
dry east as permanently drought-stricken and the wet west as never in drought,
which measures geography rather than shocks.

**Caveat.** With 25 years the district-level SD is estimated on 25 observations.
Usable, but the full 1981–present record is preferable for a final version.

## 2026-09-03 — Drought threshold set at z < −1

**Decision.** `drought = 1` when the annual total is more than one district-level
SD below the district mean.

**Why.** Conventional and simple. It is *arbitrary*: nothing in the data selects
−1 over −1.5 or the 10th percentile. Treat any result that depends on it as
requiring a threshold-robustness table. `rain_pctile` is carried alongside so
alternative cutoffs need no re-extraction.

## 2026-09-03 — DHS sampling weights

**Decision.** `weight = v005 / 1e6` (or `hv005 / 1e6` for household-level files).

**Why.** DHS stores weights as integers scaled by one million. Using them
unscaled leaves every weighted statistic off by that factor. Different recode
files use different weight variables, so the mapping is explicit in
`extract.py:DHS_WEIGHT_COLS`.

## 2026-09-03 — DHS clusters at (0, 0) dropped

**Decision.** Clusters with coordinates exactly (0, 0) are removed.

**Why.** That is the DHS missing-location sentinel, not a location in the Gulf of
Guinea. Retaining them puts clusters thousands of km outside Rwanda and silently
corrupts any spatial join.

## 2026-09-03 — DHS displacement carried, not corrected

**Decision.** `displacement_km` is stored per cluster (2 km urban, 5 km rural)
and clusters are joined to districts on the *published* point. No correction is
attempted.

**Why.** DHS displaces coordinates for confidentiality; the true location is not
recoverable. Carrying the radius lets downstream work buffer explicitly or run
sensitivity checks. Joining on the point is the standard convention but is
measured with error, and near district borders clusters can be assigned to the
wrong district. `extract_dhs_gps()` reports how many clusters fall outside all
districts as a diagnostic.

**Open.** For district-level exposure measures, consider averaging the climate
variable over the displacement buffer rather than at the point. Not yet
implemented — pending the actual GPS files.

## 2026-09-03 — EICV7 files identified by F-number, not by columns

**Decision.** `_eicv7_unit()` maps a filename to a unit via its `F`-number
prefix, with an explicit guard so `F1` does not swallow `F10`–`F19` and `F2`
does not swallow `F20`/`F21`.

**Why.** All 21 EICV7 files carry the same identifier block (`hhid`, `clust`,
`province`, `district`, `strata_id`, `weight`), so there is nothing to sniff.
The F-number is the only reliable discriminator. Tested against all 21 official
filenames plus underscore and lowercase variants.

## 2026-09-03 — EICV7 weights: `weight` vs `pop_wt`

**Decision.** Poverty and extreme-poverty rates are computed with `pop_wt`
(population weight). Mean consumption per adult equivalent and mean household
size are computed with `weight` (household weight).

**Why.** A poverty *headcount* is a statement about people, not households.
Poor households are systematically larger, so household-weighting a headcount
understates poverty — typically by several percentage points. Only F1 and F3
carry `pop_wt`; person-level work on F2 has to bring it across from F1 on
`hhid`.

## 2026-09-03 — EICV7 poverty status read as a label

**Decision.** `pov_jan` / `epov_jan` are read with value labels applied, and the
indicator is built by testing whether the label begins with "poor"
(case-insensitive), falling back to the numeric value when the column is not
categorical.

**Why.** `pyreadstat` with `apply_value_formats=True` returns these as strings.
Assuming a 0/1 numeric coding would silently produce all-missing rates.

**Fragile.** This depends on the exact label text NISR ships. **Verify against
the real file** and adjust `build_eicv7_district_welfare()` — the published
national poverty rate is the check to reproduce before trusting district
numbers.

## 2026-09-03 — EICV7 merged into the panel on district only

**Decision.** `eicv7_district_welfare.csv` merges into `district_panel.csv` on
`district_id` alone, with every column prefixed `eicv7_`.

**Why.** EICV7 is one cross-section (2023-24) against a 25-year climate panel.
Merging on district repeats the same 2023-24 value down every year, which is
correct for a time-invariant district characteristic but **is not panel
variation**. The prefix makes that visible at the point of use, so nobody
regresses an annual outcome on it and reads the result as within-district
identification.

## 2026-09-03 — VUP has seven named components but only five files

**Finding.** EICV7 splits VUP into seven components (Direct Support,
Nutrition-Sensitive Direct Support, Classic Public Works, Expanded Public Works,
Asset Transfers, Financial Services, Skills Development), but the public release
carries only **five** S9D files: F13 Direct Support, F14 Classic PW, F15
Expanded PW, F16 NSDS, F17 Financial Services.

**Consequence.** **Asset Transfers and Skills Development have no file.**
Participation in those two components is not observable in the public-use data
beyond the universal `s9d1q1` flag, which does not identify which component.
Any claim about VUP graduation pathways has to say so explicitly rather than
treating five files as full coverage.

## 2026-09-03 — Welfare columns are pre-merged into the VUP files

**Finding.** F13–F17 each already carry `quintile`, `poverty`, `pov_jan` and
`epov_jan`, and `s9d1q1` (VUP beneficiary, any component) appears in all five.

**Consequence.** No F1 merge is needed for those four welfare measures when
working within a VUP component file. Merging F1 anyway risks duplicate-suffixed
columns and, if the merge key is wrong, silently disagreeing values. Merge F1
only for the continuous aggregates (`cons1ae`, `sol_jan`) that the VUP files do
not carry.

## 2026-09-03 — Two duplicate-looking fields in F16 (NSDS)

**Finding.** `s9d4q8` and `s9d4q8a` carry the **same label** ("Amount from NSDS
in first quarter"), and `s9d4q11` is labelled "HH member ID", duplicating `pid`.

**Unresolved.** The dictionary alone cannot say whether `s9d4q8` is a legacy
column, a total, or a true duplicate. **Check against the real file before using
either**; if they disagree, prefer the `s9d4q8a`–`s9d4q8d` quarterly series,
which is internally consistent. Flagged rather than silently picking one.

## 2026-09-03 — Variable codebook kept in `variables.py`

**Decision.** Analysis-name-to-EICV7-code mappings live in `variables.py`,
organised by workstream, with `python variables.py --check` verifying every code
exists in the declared file.

**Why.** Bare codes like `s6bq3` scattered through cleaning code are unreadable
and unauditable, and a typo produces a silently missing column rather than an
error. The check runs against the shipped dictionary, so a mistyped or
hallucinated code fails loudly. All 107 codes currently verify.

**EICV7-specific by design.** Section letters shifted between rounds (s5e→s5f,
s6e/s6f→s6b/s6c), so these mappings must not be reused for earlier waves. See
`eicv_rounds.md`.

---

## 2026-09-07 — Hansen loss: which denominator

**Decision.** Three denominators are carried, and which one is correct depends
on the estimand. None is the default.

| Measure | Definition | Where it lives |
|---|---|---|
| `loss_rate` | 100 x cumulative loss / tree cover in 2000 | `cell_master.csv`, `pop_vs_forest_by_sector.csv` |
| `hazard_pct` | 100 x loss in year t / forest still standing at start of t | `sector_year_panel.csv` |
| `loss_per_km2` | loss (ha) / land area (km2) of the unit | `cell_master.csv` |

Verified against the data: `hazard_pct == 100 * loss_ha / forest_start_ha`, and
`forest_start_ha` is a *depleting* stock — tree cover in 2000 less cumulative
prior loss, floored at zero — not a fixed 2000 denominator.

**Why it matters.** Rwanda plants and harvests timber. Hansen records the
harvest of a post-2000 plantation as loss, but no product adds the planting back
to the denominator. Every denominator breaks somewhere on that fact:

- **Fixed 2000 (`loss_rate`).** Cumulative loss can exceed the year-2000 stock:
  81 of 2,115 cells with tree cover exceed 100%. Those cells sit mostly far
  from parks, so an unguarded mean *reverses the park gradient* — the 40+ km
  band reads 77.9% against 17.1% at 0–2 km, while the medians are 15.8 and 11.7.
- **Depleting stock (`hazard_pct`).** This is the discrete-time hazard a
  duration model wants, but it divides by a quantity heading to zero. 162
  sector-years hold under 1 ha; sector 1303 in 2014 holds 1.4e-16 ha —
  floating-point residue of zero — returning a hazard of 1.9e17. Worse, it is
  silently *lossy*: once the 2000 stock is exhausted the hazard is undefined and
  the loss is dropped. 12 of 416 sectors exhaust, discarding 1,653 ha (1.8% of
  the national 94,126 ha). Sector 1303 records 5.4 ha of loss after its 2.07 ha
  stock is gone.
- **Land area (`loss_per_km2`).** Cannot blow up and cannot drop loss, because
  it has no forest denominator. It is an intensity, not a rate, so it does not
  separate "a place with a lot of forest" from "a place losing forest fast".

**Practical rule adopted.**

1. `loss_per_km2` is the headline descriptive. It needs no guard, and it is the
   only one of the three monotone in park distance (9.67 -> 6.20 -> 2.26 -> 2.57
   ha/km2 across 0–2, 2–10, 10–40, 40+ km).
2. `hazard_pct` is used only for the duration framing, restricted to
   sector-years with >= 10 ha standing. That guard drops 1.9% of recorded loss,
   which must be reported, not silently absorbed.
3. `loss_rate` is not used for cross-sector comparison wherever plantations are
   present. It is fine within the park interiors, where SDPT planted share is
   near zero.

**The confound underneath.** All of this is one fact seen three ways: Hansen and
JRC TMF agree until about 2014 and then diverge sharply, with Hansen cumulating
roughly 85,000 ha against TMF's 33,000 by 2023. TMF treats plantation cycling as
land already deforested; Hansen counts each harvest. `sdpt_confound` and
`hansen_tmf_divergence` in `prelim_public_figures.py` show this directly. Any
result that rests on Hansen loss alone is measuring timber rotation as much as
forest conversion.

## Open questions

### The analysis panels have no builder script

`sector_year_panel.csv` (7,904 rows) and `cell_master.csv` (2,148 rows) are the
two files the descriptive work actually runs on, and **nothing in this repo
builds them.** `grep -rl "sector_year_panel" --include="*.py"` returns only
`prelim_public_figures.py`, which reads them. They were assembled in throwaway
inline sessions, so the joins, the `forest_start_ha` recursion and the >= 2006
clipping exist only as their output.

Consequence: the figures are reproducible, the data they stand on is not. A
reviewer cannot check how `hazard_pct` was constructed, and neither can we —
the definitions in the entry above were recovered by testing identities against
the saved columns, not by reading the code that produced them.

**Not yet built.** This wants an `extract.py` target that goes from the Hansen /
TMF / DW / RADD / SDPT sector tables to both panels, with the denominator rules
above applied once, in one place, rather than re-guarded in every figure.

### The 2006 administrative reorganisation

Rwanda replaced 12 prefectures with 5 provinces and 30 districts in January 2006.
Anything spanning EICV1/EICV2 (2000/01, 2005/06) and later waves needs an
explicit crosswalk. **Not yet built** — deferred until the EICV files are in hand,
because the right mapping depends on which geographic identifiers those files
actually carry. Flagged here so it is not discovered mid-merge.

### Spatial correlation of rainfall shocks limits the district-year design

Measured on the 2000–2024 panel:

| Quantity | Value |
|---|---|
| Mean pairwise correlation of district anomalies | **0.79** |
| Share of `rain_z` variance absorbed by year FE | **0.79** |
| SD of `rain_z`, raw | 0.98 |
| SD of `rain_z` after removing the national year effect | **0.45** |

Rwanda is ~26,000 km². Rainfall shocks are close to national events: 2018 was wet
almost everywhere, 2017 and 2000 dry almost everywhere. Once year fixed effects
are included, roughly a fifth of the anomaly variance survives, and part of that
residual is the border-pixel smoothing noted above.

**Implication for design.** A district × year specification with year FE has
limited power in Rwanda. Options worth weighing before committing:

1. Use **seasonal** rather than annual shocks — the long and short rains diverge
   more across districts than annual totals do.
2. Exploit **elevation-interacted** exposure, where the same national shock has
   different consequences by terrain.
3. Move to a **finer spatial unit** (sector, admin-3) if the outcome data support
   it, so within-year variation is not aggregated away.
4. Treat shocks as national and identify off **cross-sectional differences in
   vulnerability** instead.

This is a property of Rwanda's size and climate, not a defect in the pipeline —
better to confront it now than after the outcome data arrive.
