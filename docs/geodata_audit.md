# Geospatial audit

State of every spatial layer, and what is still missing. Verified against disk
2026-09-04. `$DB` = `~/Library/CloudStorage/Dropbox/Rwanda - TRS/data/`

---

## Administrative boundaries — now complete except district

`$DB/Publicly-Available-NISR/geodata-nisr/`

| Layer | Features | Format | Status |
|---|---|---|---|
| Sector_Boundary_2022 | **416** | GeoJSON, 20 MB | ✅ authoritative |
| Cell_Boundary_2022 | **2,148** | GeoJSON, 45 MB | ✅ authoritative |
| Village_Boundary_2022 | **14,823** | GeoJSON 116 MB + shapefile zip + CSV | ✅ authoritative |
| Cell_Office | points | shapefile zip | ✅ |
| **District_Boundary** | **0** | GeoJSON, 98 bytes | ❌ **failed download** |

All carry the nested code scheme (`province_id`, `district_id`, `sector_id`,
`cell_id`) in EPSG:4326.

**Two housekeeping issues found and fixed:**
- `Sector_Boundary ... (1).geojson` was an exact md5 duplicate — removed.
- `District_Boundary` downloaded as an **empty FeatureCollection**
  (`"features":[]`, 98 bytes). Renamed to `.bad`. **Re-download needed.**

**Worth doing now that sector boundaries are authoritative:** the 416 sector
polygons used throughout `geo-data/` are currently *dissolved from villages*.
They should be swapped for the native sector file and the park-exposure
measures recomputed. Dissolving 14,823 village polygons introduces sliver
artifacts at shared borders that the native file will not have.

---

## Protected areas — three sources, now including the authoritative one

`$DB/geo-data/protected-areas/`

| Source | Features | Notes |
|---|---|---|
| **geodata.rw** (new) | **219** | Government of Rwanda ArcGIS FeatureServer. **Authoritative** |
| WDPA Sep 2026 | 7 | International standard, IUCN categories |
| OSM | 5 | Contributor-maintained; kept only for comparison |

### The geodata.rw layer changes things

It carries a **`status`** field that neither WDPA nor OSM has:
`Core`, `Buffer`, `Extension`, `Recaptured`, `Boundary cut`, `Reclassified`.

Area by park and status (km²):

| Park | Core | Buffer | Extension | Recaptured | Boundary cut | Total |
|---|---|---|---|---|---|---|
| Nyungwe | — | — | — | 1096.3 | — | **1100.7** |
| Akagera | — | — | — | — | 1082.8 | **1082.8** |
| Volcanoes | — | — | — | — | 165.0 | **165.0** |
| Gishwati | 14.4 | 2.6 | 1.4 | 222.8 | — | **241.1** |
| Mukura | 19.9 | 7.0 | — | 9.4 | — | **36.3** |

Also present and absent from WDPA's national-park set: **Nyabarongo (282.3
km²)**, **Akanyaru (130.8)**, **Rugezi (58.3)** — wetland protected areas.

**This resolves the open buffer-zone question.** The project has been carrying a
decision about whether `Border_s` should follow the national park (162.7 km² in
WDPA) or the UNESCO biosphere reserve (454.5 km²). The official Rwandan data
answers it directly with an explicit core/buffer zonation — for Gishwati-Mukura
at least. Volcanoes and Akagera appear only as `Boundary cut`, so the buffer
question for VNP specifically may still need RDB.

**Gishwati is 241 km² here vs 32 km² in WDPA** — a 7.5× difference, because WDPA
carries only the gazetted core while geodata.rw includes 223 km² of
"Recaptured" land. Which is correct depends on what TRS eligibility follows.

**Action:** rebuild `sectors_park_exposure` on geodata.rw rather than WDPA, and
re-verify the 51 border sectors. The count will move.

---

## Environmental / land layers

`$DB/geo-data/`

| Layer | Form | Extent |
|---|---|---|
| Hansen loss + tree cover | 2 GeoTIFFs, 30 m | 8152×7172 px, Rwanda-clipped |
| TMF | sector table | 34 yrs × 416 sectors |
| Dynamic World | sector table | 10 yrs × 416 sectors |
| RADD | sector table | 7 yrs × 416 sectors |
| SDPT planted trees | 103,138 polygons + sector table | 2008 imagery |
| CHIRPS | in repo | district-level only |

**Gap: RCMRD land cover** — portal still down. Would give 1990/2000/2010/2015
and complete the 1990–2025 land-use series.

**Gap: CHIRPS is district, not sector.** Every other environmental layer is at
416 sectors; rainfall is at 30 districts. Re-extractable from the cached rasters.

---

## Infrastructure

| Layer | Form | Note |
|---|---|---|
| Google Open Buildings | 5,813,271 polygons (parquet) | sector-stamped |
| GRID3 settlements | 25,122 polygons (zip) | v3.0, 2024 |
| gridfinder | 711 lines + global targets raster | 2,671 km in Rwanda |
| OSM tourism POIs | 888 points | 469 accommodation |

**Gap: OSM roads.** Not yet pulled. Needed for travel time and market access.

**Gap: park gates.** Equation (2) needs distance from each sector to each gate.
You said roads plus OSM would get there — that still has to be built, and gates
may be tagged inconsistently (`barrier=gate`, `tourism=information`, or absent).

---

## What is still needed, in priority order

1. **District boundaries** — re-download; current file is empty
2. **Park gate locations** — required by the tourism exposure measure; no source
   holds them yet. Try OSM, then RDB
3. **RDB TRS project data** — the treatment. Not obtainable publicly
4. **OSM road network** — market access, and the route to gates
5. **RCMRD land cover** — blocked on their server
6. **DHS GPS (`RWGE##FL`)** — the covariate files held are not coordinates
7. **Animal censuses** — RDB / park authorities

## Rebuilds worth doing with what just arrived

- Swap dissolved-from-village sectors for the **native 416-sector file**
- Rebuild park exposure on **geodata.rw** instead of WDPA, and re-verify the 51
  border sectors against the proposal's footnote
- Decide **core vs buffer vs recaptured** for `Border_s` now that the official
  zonation is available
