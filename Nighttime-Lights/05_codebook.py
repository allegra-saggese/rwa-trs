"""
05_codebook.py -- the Excel codebook and the README block for the Dropbox folder.

    python 05_codebook.py

    CODEBOOK_Nightlights.xlsx   one sheet per final file, plus Sources and Coverage
    README.txt                  written next to it, describing the folder for someone who
                                opens it without this repository in front of them
"""
import numpy as np
import pandas as pd

import ntl_helpers as H

README = """NIGHTTIME LIGHTS -- Rwanda, 2000 onwards
{rule}

WHAT THIS IS
Annual nighttime light brightness for every Rwandan sector (416) and cell (2,148), from two
independent global products, both harmonised across the 2012 change of satellite sensor.

  li     Li, Zhou, Zhao and Zhao (2020), extended to 2024. Digital numbers on the DMSP scale,
         0 to 63, originally 30 arc-second (about 0.9 km over Rwanda). Calibrated DMSP through
         2013, VIIRS converted to DMSP-like numbers from 2014.
  chen   Chen, Yu, Yang and others (2021), version 2, 1992 to 2025. Radiance in nW/cm2/sr,
         originally 15 arc-second (about 0.5 km). VIIRS-like throughout, extended backwards.

Both are carried and neither is preferred. They are built by different methods on different
scales, so where they disagree that disagreement is information, not error. Never average them.

FILES
  3_Final/Nightlights_pooled_sector.dta   {sector_rows} rows, one per sector-year
  3_Final/Nightlights_pooled_cell.dta     {cell_rows} rows, one per cell-year
  (.csv copies sit beside both)
  2_Intermediate/                         one long file per product and unit, before merging
  1_Raw/source_manifest.csv               url, byte size and sha256 of every source file
  CODEBOOK_Nightlights.xlsx               every variable, its label and its range
  z_Documentation/                        the two source papers' citations and licences

The Rwanda cut-outs of the rasters live in geo-data/nightlights/, one GeoTIFF per product-year,
alongside the other gridded layers. The global originals run from 33 MB to 10 GB per year and
are not kept: they are reproducible from the manifest, and nothing here needs a pixel outside
the country.

WHAT IS NOT HERE
The raw composites these products are built from, DMSP-OLS v4 and VIIRS VNL v2 from NOAA/EOG,
now sit behind an account login at eogdata.mines.edu. They can be added to 1_Raw by anyone with
an account; the pipeline does not fetch them.

Monthly VIIRS is not here either. Only annual composites were built.

HOW THE NUMBERS ARE MADE
Each raster pixel is split into 4 x 4 sub-pixels that inherit its value; each sub-pixel is
assigned to whichever sector or cell contains it; the statistics are taken over those. This
matters for cells, the smallest of which are under a square kilometre and would otherwise
contain no pixel centre at all. Areas are computed per raster row, since a degree of longitude
shortens with latitude.

  mean        area-weighted average brightness
  sum         area-weighted total, in whole-pixel equivalents, the usual "sum of lights"
  max         the brightest single pixel
  lit_share   share of the unit's area above the noise floor (0 for Li, 0.5 nW for Chen)

MERGING
Merge on the codes. ntl_sector_id is the NISR sector code, the same one the census and the
geo-data layers use, so the sector file joins onto them directly, and ntl_cell_id nests inside
it.

Never merge on a name alone. Sector names are not unique: 379 distinct names cover 416 sectors,
and there are four sectors called Remera, plus three each of Karama, Kageyo, Murambi, Muganza
and Ngoma. Cell names are worse, 1,467 names for 2,148 cells. A join on name alone silently
multiplies rows.

Names are unique once the district is added. If you must join on text, the keys are

  sector level   district + sector
  cell level     district + sector + cell

Both are checked in logs/checks_report.txt, section B.

{stamp}
"""


def sheet(df, labels=None):
    rows = []
    for c in df.columns:
        s = df[c]
        num = pd.api.types.is_numeric_dtype(s)
        rows.append({
            "variable": c,
            "label": (labels or {}).get(c, ""),
            "type": "numeric" if num else "text",
            "non_missing": int(s.notna().sum()),
            "unique": int(s.nunique()),
            "min": float(s.min()) if num else "",
            "mean": round(float(s.mean()), 4) if num else "",
            "max": float(s.max()) if num else "",
        })
    return pd.DataFrame(rows)


def main():
    out = H.NTL / "CODEBOOK_Nightlights.xlsx"
    counts = {}
    with pd.ExcelWriter(out, engine="openpyxl") as xl:
        for cadence, stem in (("annual", "pooled"), ("monthly", "monthly")):
            for unit in H.UNITS:
                f = H.FINAL / f"Nightlights_{stem}_{unit}.dta"
                if not f.exists():
                    continue
                df = pd.read_stata(f)
                labels = pd.read_stata(f, iterator=True).variable_labels()
                name = f"{unit}_variables" if cadence == "annual" else f"{unit}_monthly"
                sheet(df, labels).to_excel(xl, sheet_name=name, index=False)
                counts[unit if cadence == "annual" else f"{unit}_monthly"] = len(df)

        src = pd.DataFrame([{
            "product": k, "kind": v["kind"], "cadence": v["cadence"], "label": v["short"],
            "layers": ", ".join(sorted(v["layers"])), "units": v["unit"], "doi": v["doi"],
            "lit_floor": H.FLOORS.get(k, ""), "citation": v["citation"],
        } for k, v in H.PRODUCTS.items()])
        src.to_excel(xl, sheet_name="Sources", index=False)

        pd.DataFrame([{"statistic": k, "short_label": H.STATS[k], "definition": v}
                      for k, v in H.STATS_LONG.items()]
                     + [{"statistic": k, "short_label": H.DERIVED[k], "definition": v}
                        for k, v in H.DERIVED_LONG.items()] + [
            {"statistic": "zonal method", "short_label": f"{H.SUPERSAMPLE}x{H.SUPERSAMPLE} supersampling",
             "definition": ("Each raster pixel is split into sub-pixels that inherit its value and are "
                            "assigned to whichever unit contains them. A pixel-centre rule would leave "
                            "the smallest cells, under a square kilometre, with no data at all.")},
            {"statistic": "areas", "short_label": "per raster row",
             "definition": ("A degree of longitude shortens with latitude, so sub-pixel area is "
                            "computed row by row. The boundary layers cover land only, about 24,350 "
                            "km2; Rwanda's headline 26,338 km2 includes its share of the lakes.")},
        ]).to_excel(xl, sheet_name="Definitions", index=False)

        man = H.RAW / "source_manifest.csv"
        if man.exists():
            pd.read_csv(man).to_excel(xl, sheet_name="Coverage", index=False)
    print("codebook ->", out)

    doc = H.DOCS / "sources.txt"
    doc.write_text("\n\n".join(
        f"{k}\n{'-' * len(k)}\n{v['citation']}\nDOI: {v['doi']}\nUnits: {v['unit']}\n"
        f"Licence: CC BY 4.0" for k, v in H.PRODUCTS.items()) + "\n")
    print("citations ->", doc)

    txt = README.format(rule="=" * 72, sector_rows=f"{counts.get('sector', 0):,}",
                        cell_rows=f"{counts.get('cell', 0):,}",
                        stamp=f"Built by rwa-trs/Nighttime-Lights, {pd.Timestamp.today():%Y-%m-%d}.")
    (H.NTL / "README.txt").write_text(txt)
    print("readme ->", H.NTL / "README.txt")


if __name__ == "__main__":
    main()
