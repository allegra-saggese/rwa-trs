"""
01_download.py -- fetch each global annual composite, cut Rwanda out of it, throw the global file away.

    python 01_download.py [li|chen] [--force]

    geo-data/nightlights/ntl_<product>_<year>_rwanda.tif   the cut-outs, kept
    1_Raw/source_manifest.csv                              url, size and sha256 of every source file

The global rasters are 33 MB (Li) to 10 GB uncompressed (Chen) per year and nothing downstream needs
anything outside Rwanda, so they are deleted as soon as the window is written. 1_Raw therefore holds
the manifest rather than the files: every source is reproducible from the url and checksum in it.

A year already cut is skipped, so an interrupted run resumes where it stopped.
"""

import sys
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.windows import from_bounds

import ntl_helpers as H

FIGSHARE = "https://api.figshare.com/v2/articles/{}/files?page_size=200"
DATAVERSE = "https://dataverse.harvard.edu/api/datasets/:persistentId/?persistentId={}"
DV_FILE = "https://dataverse.harvard.edu/api/access/datafile/{}"


def li_sources():
    """{year: (url, filename)} -- calibrated DMSP through 2013, VIIRS converted to DN from 2014"""
    files = H.get_json(FIGSHARE.format(H.PRODUCTS["li"]["figshare_article"]))
    out = {}
    for f in files:
        n = f["name"]
        if not n.endswith(".tif"):
            continue
        year = int("".join(c for c in n if c.isdigit())[:4])
        branch = "calDMSP" if "calDMSP" in n else "simVIIRS"
        if year not in H.YEARS:
            continue
        # 2013 ships on both branches; the series takes the DMSP one, which is the calibrated original
        if year in out and branch == "simVIIRS":
            continue
        out[year] = (f"https://ndownloader.figshare.com/files/{f['id']}", n, f.get("size"))
    return out


def chen_sources():
    """{year: (url, filename)} -- version 2 only, the version 1 files stop in 2020"""
    ds = H.get_json(DATAVERSE.format(H.PRODUCTS["chen"]["dataverse_doi"]))
    out = {}
    for f in ds["data"]["latestVersion"]["files"]:
        d = f["dataFile"]
        n = d["filename"]
        if "Version2" not in n or not n.endswith(".zip"):
            continue
        year = int(n[:4])
        if year in H.YEARS:
            out[year] = (DV_FILE.format(d["id"]), n, d.get("filesize"))
    return out


def cut(src_tif, dst):
    """write the Rwanda window, keeping the source's dtype, transform and crs"""
    with rasterio.open(src_tif) as s:
        w = from_bounds(*H.BBOX, s.transform).round_offsets().round_lengths()
        a = s.read(1, window=w)
        prof = s.profile | {"height": a.shape[0], "width": a.shape[1],
                            "transform": s.window_transform(w), "compress": "deflate"}
        for k in ("tiled", "blockxsize", "blockysize", "interleave"):
            prof.pop(k, None)                       # the windows are small; a stripped layout is fine
        dst.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(dst, "w", **prof) as o:
            o.write(a, 1)
    return a


def run(product, force=False):
    src = li_sources() if product == "li" else chen_sources()
    rows = []
    for year in sorted(src):
        url, name, size = src[year]
        out = H.clip_path(product, year)
        if out.exists() and not force:
            print(f"  {product} {year}  already cut")
            rows.append({"product": product, "year": year, "source_file": name, "url": url,
                         "source_bytes": size, "sha256": "", "note": "skipped, clip present"})
            continue
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            blob = H.download(url, tmp / name)
            digest = H.sha256(blob)
            if name.endswith(".zip"):
                with zipfile.ZipFile(blob) as z:
                    tif = [i for i in z.namelist() if i.lower().endswith((".tif", ".tiff"))][0]
                    z.extract(tif, tmp)
                    blob.unlink()                      # the zip is not needed once the tif is out
                    a = cut(tmp / tif, out)
            else:
                a = cut(blob, out)
        print(f"  {product} {year}  {a.shape[1]}x{a.shape[0]} px, max {float(a.max()):.4g} -> {out.name}")
        rows.append({"product": product, "year": year, "source_file": name, "url": url,
                     "source_bytes": size, "sha256": digest, "note": ""})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    force = "--force" in sys.argv
    products = args or list(H.PRODUCTS)
    H.RAW.mkdir(parents=True, exist_ok=True)
    man = H.RAW / "source_manifest.csv"
    old = pd.read_csv(man) if man.exists() else pd.DataFrame()
    new = pd.concat([run(p, force) for p in products], ignore_index=True)
    if len(old):
        old = old[~old.set_index(["product", "year"]).index.isin(
            new.set_index(["product", "year"]).index)]
    pd.concat([old, new], ignore_index=True).sort_values(["product", "year"]).to_csv(man, index=False)
    print("\nmanifest ->", man)
