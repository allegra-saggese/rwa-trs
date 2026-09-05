# Data requirements: proposal vs. holdings

Reconciles three lists: the **proposal data table** (Fossi & Saggese, 4 Sep 2026),
the **spatial stack** specified separately, and what is **actually on disk**.

Last updated: 2026-09-04

---

## Status summary

| | In proposal table | Have | Gap |
|---|---|---|---|
| Panel A — economic | 6 datasets | 3 | **3** |
| Panel B — conservation | 5 datasets | 0 | **5** |
| Spatial stack (separate list) | 6 layers | 3 | 3 |
| Required by design, listed nowhere | — | — | **2** |

---

## Panel A — economic measures

| Dataset | Proposal frequency | Status |
|---|---|---|
| **RDB project data** | annual, 2005– | **MISSING — the treatment variable** |
| Population and Housing Census (PHC) | 2002, 2012, 2022 | HAVE, all three |
| EICV | 7 waves | HAVE 5 (EICV1,2,3,4,5,7) — **EICV6 (2020/21) missing** |
| Labour Force Survey | annual 2017–2025 | HAVE, all nine years |
| **Establishment Census (EC)** | 2011, 2014, 2017, 2020, 2023 | **MISSING** — folder created at `Establishment-Census-EC/` |
| **Integrated Business Enterprise Survey (IBES)** | annual 2014–2024 | **MISSING** — no folder yet |

**RDB project data is the binding gap.** TRS project location, category, amount,
approval/disbursement/completion dates, park visitor numbers and park revenue by
source are the treatment in equations (1) and (3). Nothing public substitutes.
The proposal's own note anticipates this: an RDB letter of approval, then
district governments who hold the implementation records.

**EICV6** is listed as a wave in the proposal but is absent from the NISR public
catalogue (see `Publicly-Available-NISR/EICV/README.txt`). The proposal already
flags it covered ~40% of the planned sample with limited variables due to COVID.

---

## Panel B — conservation and environmental measures

**None of these are held. All five are missing.**

| Dataset | Resolution / frequency | Route |
|---|---|---|
| JRC Tropical Moist Forest (TMF) | 30 m, annual 1990–2025 | Google Earth Engine, or JRC direct download |
| RADD deforestation alerts | 10 m, weekly since Jan 2019 | GEE, or GFW data-api (**needs free API key**) |
| Dynamic World | 10 m, ≥weekly, June 2015– | GEE only (near-real-time collection) |
| Hansen Global Forest Change | 30 m, annual 2000–2025 | GEE, or direct tile download from the Hansen/UMD server |
| Animal censuses | park-level, irregular | RDB / park authorities — not public |

**Practical route: Google Earth Engine.** Four of the five are GEE collections;
pulling them any other way means downloading global tiles and clipping. A GEE
account (free for research) plus the Python `earthengine-api` would let all four
be reduced to sector-level zonal statistics server-side, which is far cheaper
than local rasters. This is a dependency the project does not yet have.

The proposal's own footnotes already note two limits worth carrying forward:
TMF's primary humid tropical forest mask **covers Volcanoes and Nyungwe but not
Gishwati-Mukura**, and Dynamic World is used for cropland and settlement
encroachment *outside* the park boundary.

---

## Spatial stack (specified separately, not in the proposal table)

| Layer | Status |
|---|---|
| NISR admin boundaries, 2022 census | HAVE — 14,823 villages, nested IDs, in `geodata-nisr` |
| WDPA / Protected Planet | HAVE — 7 Rwandan protected areas, Sep 2026 release |
| GRID3 settlement extents | HAVE — v3.0 (2024), 25,122 settlements |
| Google Open Buildings | HAVE — 5,815,098 buildings, aggregated to 416 sectors |
| gridfinder | HAVE — 2,671 km of grid, per-sector length |
| **RCMRD / SERVIR land cover** | **BLOCKED — `geoportal.rcmrd.org` is down** |
| **WRI SDPT v2.1** | **BLOCKED — needs a free GFW API key** |
| NISR 13-class land cover (SAS frame) | to request from NISR/MINAGRI |

**None of these appear in the proposal's data table.** They are supporting
layers, not measures the design estimates on. That is defensible, but it should
be a stated choice: if GRID3, Open Buildings or gridfinder are used as controls
or as outcome denominators, they belong in the table; if they are only for
descriptive maps and sample construction, they belong in an appendix.

Two of them substantially overlap Panel B and may be redundant:

- **RCMRD land cover (1990/2000/2010/2015)** vs **Dynamic World (2015–)**. The
  RCMRD series ends where Dynamic World begins. As a *pre-period* land-cover
  baseline RCMRD is complementary; as a current-outcome measure it is superseded.
- **WRI SDPT (planted trees)** vs **TMF forest regrowth**. Both speak to
  plantation vs natural forest. Decide which identifies the outcome and which is
  a robustness layer.

---

## Required by the empirical design, listed in neither

### 1. Park gate locations and gate-level visitor counts

Equation (2) defines tourism exposure as

    Tourism_st = SUM over gates g in park p(s) of  V_gt / (1 + d_sg)

This needs **two things that appear in no data source listed**:

- `d_sg` — distance from each sector to each **gate**. Gate coordinates are not
  in WDPA, not in the NISR boundaries, and not in the proposal's table.
- `V_gt` — visitors entering **through gate g** in year t. The RDB row promises
  "park visitor numbers", which may well be park-level totals only.

**If RDB supplies park-level totals rather than gate-level counts, equation (2)
cannot be estimated as written.** The distance-weighted sum collapses to a single
park total scaled by distance to the park, which is a materially weaker
instrument for local exposure. Worth confirming in the RDB request itself, and
worth deciding on a fallback (nearest-gate distance, or park-boundary distance)
before the data arrives rather than after.

Gate coordinates may be recoverable from OSM (`barrier=gate`, `tourism`
information points near park boundaries) or from RDB directly, but this should be
an explicit ask.

### 2. Park boundaries as an estimation input

`Border_s` in equation (1) requires park polygons. These are held (WDPA) but do
not appear in the proposal's data table. They should — the definition of
`Border_s` is load-bearing (see below).

---

## Verified: `Border_s` definition

The proposal's footnote 3 states 51 sectors across 14 districts, about 1.5
million people. Reproduced exactly against WDPA national-park polygons dissolved
NISR village boundaries and Census 2022 weights:

| Definition | Sectors | Districts |
|---|---|---|
| Overlaps park (>0.1% of sector area) | 45 | 14 |
| Intersects park polygon at all | 48 | 14 |
| **Touches or within 1 km** | **51** | **14** |
| Within 2 km | 58 | 14 |
| Within 5 km | 84 | 14 |

Weighted population under the 1 km rule: **1,549,299** (national 13,245,753
against 13,246,394 published — 0.005% off).

**`Border_s` = touches or within 1 km** is therefore the operative definition.
Recorded because the count moves from 45 to 84 across plausible readings of
"borders a park", and every treated/control split depends on it.

Two dependencies to keep in view:

- **Boundary vintage.** WDPA lists Volcanoes twice: `Volcans` National Park
  (162.7 km², IUCN II) and `Parc national des Volcans` UNESCO-MAB Biosphere
  Reserve (454.5 km²). The national park is used. If TRS eligibility follows the
  buffer zone, the biosphere footprint is the correct treatment boundary and all
  counts change.
- **Gishwati-Mukura entered TRS in 2019** (sharing moved 40/30/30 → 35/25/25/15).
  Sectors bordering it are untreated before 2019, which the event study must
  respect.

---

## Requested but not in the proposal table

**DHS Rwanda** (recodes + GPS shapefile) has been requested from dhsprogram.com.
It does not appear in the proposal's data table. Loaders are written
(`extract.py --sources dhs dhs_gps`) and it will land in `data/DHS/`.

Worth deciding what role it plays: DHS carries health and asset outcomes the
other sources do not, and its **geocoded clusters are the only household-level
GPS in the whole stack** — but cluster coordinates are displaced (2 km urban,
5 km rural, 1% of rural up to 10 km), which is large relative to a 1 km
`Border_s` rule. Sectors are ~64 km² on average; a 5 km displacement can move a
rural cluster across two sector boundaries. **DHS cannot be used to assign
households to border sectors** without accounting for that, though it remains
usable at district level or with buffer-based exposure.
