"""
05_codebook.py -- the Excel codebook and the README block for the Dropbox folder.

    python 05_codebook.py

    CODEBOOK_Nightlights.xlsx   data/harmonized/nightlights/: one sheet per final file, plus Sources and Coverage
    README.txt                  data/Nighttime-Lights/: describes the folder for someone who
                                opens it without this repository in front of them
"""
import numpy as np
import pandas as pd

import ntl_helpers as H

README = """NIGHTTIME LIGHTS -- Rwanda, 1992-2025
========================================================================

This folder holds the satellite images: the files as downloaded (source/) and the same images
clipped to Rwanda (clipped-rwanda/). Everything averaged to sectors or cells is in
data/harmonized/nightlights/.

THE SIX PRODUCTS
  product        what it is                                         years      units
  dmsp           NOAA/EOG DMSP-OLS annual composites, version 4,     1992-2013  digital number 0-63
                 one per satellite (F10, F12, F14, F15, F16, F18)
  dmsp_m         DMSP-OLS monthly composites                         1992-2014  digital number 0-63
  viirs          EOG VIIRS annual composites, VNL version 2.1        2012-2025  radiance nW/cm2/sr
  viirs_m        EOG VIIRS monthly cloud-free composites, version 1  2012-2025  radiance nW/cm2/sr
  li             Li, Zhou, Zhao and Zhao (2020), DMSP and VIIRS       1992-2024  digital number 0-63
                 spliced into one DMSP-scale series
  chen           Chen, Yu, Yang and others (2021), version 2,        2000-2025  radiance nW/cm2/sr
                 a VIIRS-scale series extended back in time

  Layers within a product:
    avgvis / avg   average brightness over cloud-free nights
    cfcvg          number of cloud-free nights observed (quality weight, not brightness)
    stable         DMSP stable lights: fires and other ephemeral lights removed
    intercal       DMSP stable lights intercalibrated across satellites
    med            VIIRS median brightness
    lit            VIIRS lit mask (1 = pixel lit)

  li and chen are built by different methods on different scales; where they disagree that is
  information, not error. Never average them.

FOLDERS
  source/                       files as downloaded
    dmsp_v4/                    DMSP annual, global .tif.gz, one folder per satellite-year
    dmsp_monthly/               DMSP monthly, one folder per satellite (1.4 GB)
    viirs_annual/               VIIRS annual, already clipped to Rwanda by EOG (.RWA.tif)
    viirs_monthly/              VIIRS monthly, original world tiles (.tgz), one folder per year (1.1 GB)
    source_manifest.csv         li and chen: product, year, file name, URL, size, sha256
    source_manifest_dmsp.csv    DMSP annual: the same fields
  clipped-rwanda/               every product clipped to Rwanda, one GeoTIFF per product, layer and
                                period: ntl_<product>_<layer>_<year or yyyymm>_rwanda.tif (1,362 files)
  z_Documentation/sources.txt   citation, DOI and licence of each product (all CC BY 4.0)

  li and chen are kept only as Rwanda clips: their global files are 33 MB to 10 GB per year. The
  manifest is the download log that lets them be fetched again and checked byte for byte (sha256).
  DMSP monthly, VIIRS annual and VIIRS monthly have no manifest.

  dmsp_v4/ and viirs_annual/ are online-only in Dropbox: they show 0 bytes until opened.

WHAT IS BUILT FROM THESE (in data/harmonized/nightlights/)
  Nightlights_pooled_sector / _cell     annual, one row per sector-year (416 x 34) or cell-year,
                                        all annual products side by side, .dta and .csv
  Nightlights_monthly_sector / _cell    monthly DMSP and VIIRS
  sector-cell-long/                     one long file per product and unit, before merging
  CODEBOOK_Nightlights.xlsx             every variable, its label and its range
  Built by rwa-trs/Nighttime-Lights.

HOW THE NUMBERS ARE MADE
Each raster pixel is split into 4 x 4 sub-pixels that inherit its value; each sub-pixel is
assigned to whichever sector or cell contains it; the statistics are taken over those. This
matters for cells, the smallest of which are under a square kilometre and would otherwise
contain no pixel centre at all. Areas are computed per raster row, since a degree of longitude
shortens with latitude.

  mean        area-weighted average brightness
  sum         area-weighted total, in whole-pixel equivalents, the usual "sum of lights"
  max         the brightest single pixel
  lit_share   share of the unit's area above the noise floor (0 for the 0-63 products, 0.5 nW for radiance)

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

Both are checked in the pipeline's logs/checks_report.txt, section B.

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
    out = H.FINAL / "CODEBOOK_Nightlights.xlsx"   # data/harmonized/nightlights/
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
