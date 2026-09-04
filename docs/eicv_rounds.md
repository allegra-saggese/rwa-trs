# EICV rounds: structure, breaks, and what pools

**Source note.** The round-to-round history below comes from a research brief
supplied by the PI (2026-09-03), not from anything verifiable in the EICV7
dictionary held in this repo. The EICV7 column is confirmed against
`EICV7_2023-24_variable_dictionary.csv`; the earlier rounds are **not verified
here** and should be re-checked against NISR documentation before anything
depends on them in print.

---

## Round structure

| Round | Years | Gap | Sampling frame | Panel / VUP | Mode |
|---|---|---|---|---|---|
| EICV1 | 2000-01 | base | pre-2002 frame | none | paper |
| EICV2 | 2005-06 | 5 yr | 2002 census | none | paper |
| EICV3 | 2010-11 | 5 yr | 2002 census | none | paper |
| EICV4 | 2013-14 | 3 yr | 2012 census | panel from EICV3, VUP sample introduced | paper |
| EICV5 | 2016-17 | 3 yr | 2012 census | panel + VUP panel | paper |
| EICV6 | 2019-20 | 3 yr | 2012 census | conducted; absent from the NISR public catalogue | mixed |
| EICV7 | 2023-24 | 4 yr | 2022 census | VUP sample from the MINALOC list | CAPI tablets |

### Frame breaks matter for spatial linkage

The PSU frame moves 2002 census (through EICV3) → 2012 census (EICV4, EICV5) →
2022 census (EICV7). **Village and EA identifiers do not carry across these
breaks** without a geographic crosswalk. This is the same class of problem as
the 2006 administrative reorganisation already flagged in
`cleaning_decisions.md`, and it compounds with it.

---

## Module changes

**EICV3 → EICV4.** First panel and first VUP beneficiary sample. Module content
otherwise stable. Poverty line rebased — see below.

**EICV4 → EICV5.** Near-identical structure. Both carry the full agriculture
block as separate files (s7a livestock ×4, s7b land, s7c parcels, s7d/s7e crops,
s7f ag income, s7g ag expenditure, s7h transformation) plus s8a1-a3 and s8b
expenditure. Person-file composition shifts: EICV4 is
`s1_s2_s3_s4_s6a_s6e_s6f`, EICV5 is `s1_s2_s3_s4_s6a_s6e`. Access to services is
s5e in both.

**EICV5 → EICV7 — the largest break in the series.**

- **Agriculture gutted.** The separate land, parcels, crop, ag-income,
  ag-expenditure and transformation files are gone. Livestock survives only as a
  short household-file block (`s7aq4*` → `s7a2q7`). For crop area, yield, and
  agricultural income, go to SAS or AHS, not EICV.
- **Employment restructured to main job only.** Secondary and multiple-job
  capture discontinued.
- **Consumption restructured.** Food consumption recorded separately from
  expenditure and split by source (purchase / own production / gift or in-kind).
  Food away from home moved to person level (s8c). Non-food now captures in-kind
  receipts, not only purchases.
- **Transfers relocated.** In-kind transfers moved out of Section 9 into Section
  8 consumption; Section 9 retains cash transfers plus VUP.
- **VUP expanded from three components to seven.**
- **Section letters shifted.** Access to services s5e → s5f. Person employment
  and time-use s6e/s6f → s6b/s6c.

> **Consequence for code.** Variable-name matching across rounds is unreliable.
> Match on **question content**, never on the `sNqM` code. `variables.py` is
> EICV7-specific for exactly this reason.

---

## Measurement breaks that stop things pooling

| Transition | Status | Detail |
|---|---|---|
| EICV3 → EICV4 | **Break** | Poverty line rebased on an updated food basket. Independent researchers could not replicate the official trend from released microdata; the direction of the 2010-11 → 2013-14 change was contested (official: fall; Reyntjens: rise). NISR revised in 2015 and again in 2016. Not cleanly comparable without reconstructing a consistent line and deflator. |
| EICV4 → EICV5 | **Comparable** | Aggregate and line methodology held constant; EICV5 reports present both side by side. Consumption and poverty pool across this pair. |
| EICV5 → EICV7 | **Hard break** | NISR states consumption and poverty methodology was significantly revised, and explicitly cautions against comparing EICV7 poverty to earlier rounds. Combined with the consumption module restructure, and on a new January 2024 price base. |
| Labour, all rounds | **Break at EICV7** | Main-job-only capture, plus the shift toward the international employment definition excluding own-use subsistence agriculture. Employment status and sector are not on the same basis as earlier rounds. **The LFS (2017-) is the more consistent labour instrument over time.** |
| Seasonality | Composition only | Fieldwork moves from 10 cycles over 12 months (EICV4, EICV5) to 9 cycles of 3 sub-cycles (EICV7); completed interviews per cluster drop 12 → 9. Affects the seasonal composition of the consumption sample, not the concept measured. |

---

## Net position

- Treat **EICV4 and EICV5 as a comparable pair** for welfare, labour, and
  agriculture.
- Treat **EICV3→EICV4 and EICV5→EICV7 as methodological breaks** requiring
  harmonisation before pooling.
- Expect EICV7 agriculture and secondary-employment content to be thin. **SAS,
  AHS, and the LFS carry those threads better over time.**

---

## Geographic resolution ceiling

EICV7 public-use files geocode to **province and district only**. `clust` and
`strata_id` are present, but the **EA and village identifiers needed to link
villages to VNP forest cells are not in the public release** — they come through
a data-request agreement with NISR.

**This is the binding constraint on the conservation workstream.** Without
village identifiers, forest-pressure proxies can only be analysed at district
level, which for the districts bordering Volcanoes National Park (Musanze,
Burera, Nyabihu, Rubavu) mixes park-adjacent and distant households in the same
cell. Worth resolving before investing in the cooking-fuel and foraging
measures — the request should go in early, since it gates the design.
