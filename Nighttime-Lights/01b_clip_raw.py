"""
01b_clip_raw.py -- cut Rwanda out of the raw sensor composites sitting in 1_Raw.

    python 01b_clip_raw.py [dmsp|viirs]

    geo-data/nightlights/ntl_dmsp_<layer>_<sat>_<year>_rwanda.tif
    geo-data/nightlights/ntl_viirs_<layer>_<year>_rwanda.tif

Unlike 01_download.py, which fetches the published harmonised products, this step works on files
already on disk: the DMSP-OLS v4 and VIIRS VNL v2 composites downloaded by hand from EOG, whose
programmatic route is now behind a paid subscription. The global originals stay in 1_Raw; only the
Rwanda windows are written, because a global DMSP cf_cvg year is 300 MB and the window is 60 KB.

Why the raw layers are worth carrying, when two harmonised products already cover the same years:

  stable_lights   the cleaned DMSP product. Dim and ephemeral light is set to zero by design. This
                  is what Li's harmonisation is built on, so it is what our current panel inherits.
  avg_vis         the same composite WITHOUT that censoring. If a sector reads zero in stable_lights
                  but is non-zero here, the harmonised series has been discarding real signal --
                  which matters, because the park-adjacent sectors read exactly zero before 2010.
  cf_cvg          how many cloud-free nights went into each pixel-year. Rwanda is cloudy and
                  mountainous and cloud cover tracks altitude, so this is the difference between a
                  well-measured sector-year and a barely-measured one. Neither Li nor Chen ships it.

A year already cut is skipped, so the step is cheap to re-run.
"""
import gzip
import re
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path

import rasterio
from rasterio.windows import from_bounds

import ntl_helpers as H

RAW_SETS = {
    "dmsp": {
        "dir": "dmsp_v4",
        # Order does not matter, layer_of() takes the LONGEST match: without the intercal entry
        # every "...intercal.stable_lights.avg_vis..." file matched "stable_lights.avg_vis", was
        # labelled stable, and was then skipped because the plain stable file had already written
        # that target. The intercalibrated layer is the one that is comparable across years.
        "layers": {"intercal.stable_lights.avg_vis": "intercal",
                   "stable_lights.avg_vis": "stable", "avg_vis": "avgvis", "cf_cvg": "cfcvg"},
    },
    "viirs": {
        "dir": "viirs_annual",
        "layers": {"average_masked": "avg", "median_masked": "med",
                   "cf_cvg": "cfcvg", "lit_mask": "lit"},
    },
    # The monthly composites arrive as .tgz tarballs of one tile, not gzipped single rasters, and
    # each holds two layers: the radiance and the cloud-free coverage count.
    # EOG splits the monthly composites into six tiles. Rwanda sits at 28.8-31.0E, 1-3S, which is
    # tile 00N060W (60W-60E, 0-75S). 00N060E covers 60E-180E -- Asia and Australia -- and holds no
    # Rwandan territory at all; clipping it fails with a zero-width window. The glob is pinned to the
    # right tile so a stray download of another one is skipped rather than silently mis-clipped.
    "viirs_m": {
        "dir": "viirs_monthly", "archive": "tgz", "tile": "00N060W",
        "layers": {"avg_rade9h": "avg", "cf_cvg": "cfcvg"},
    },
}


def layer_of(name, layers):
    """longest match wins: stable_lights.avg_vis must not be read as avg_vis"""
    hits = [(k, v) for k, v in layers.items() if f".{k}." in name]
    return max(hits, key=lambda kv: len(kv[0]))[1] if hits else None


def target(product, short, stem, path):
    if product == "dmsp":
        sat, year = path.parent.name.split("_")           # F15_2000
        return H.CLIPS / f"ntl_dmsp_{short}_{sat}_{year}_rwanda.tif"
    if product == "viirs_m":
        ym = re.search(r"_(\d{6})\d{2}-", stem).group(1)  # SVDNB_npp_20140801-20140831_...
        return H.CLIPS / f"ntl_viirs_m_{short}_{ym}_rwanda.tif"
    return H.CLIPS / f"ntl_viirs_{short}_{path.parent.name}_rwanda.tif"


def run_tarballs(product, spec):
    """monthly tiles: each .tgz holds one raster per layer, so the members are the unit of work"""
    src_dir = H.RAW / spec["dir"]
    files = sorted(src_dir.rglob(f"*{spec['tile']}*.tgz"))
    other = len(list(src_dir.rglob("*.tgz"))) - len(files)
    print(f"  {product}: {len(files)} tarballs for tile {spec['tile']} in {src_dir.name}"
          + (f"  ({other} of other tiles ignored)" if other else ""))
    done = skipped = 0
    failed = []
    for f in files:
        try:
            # streamed in ONE pass: the tarball is a gzip stream, so getmembers() followed by
            # extract() per member decompresses it twice over.
            with tarfile.open(f, "r|gz") as tf:
                for m in tf:
                    if not m.name.endswith(".tif"):
                        continue
                    short = layer_of(m.name, spec["layers"])
                    if short is None:
                        continue
                    out = target(product, short, m.name, f)
                    if out.exists():
                        skipped += 1
                        continue
                    with tempfile.TemporaryDirectory() as tmp:
                        fh = tf.extractfile(m)
                        plain = Path(tmp) / Path(m.name).name
                        with open(plain, "wb") as w:
                            shutil.copyfileobj(fh, w, 1 << 22)
                        a = cut(plain, out)
                    print(f"    {out.name}  {a.shape[1]}x{a.shape[0]} px, max {float(a.max()):.4g}")
                    done += 1
        except Exception as e:
            print(f"    SKIPPED {f.name}: {e}")
            failed.append(f.name)
    print(f"  {product}: {done} cut, {skipped} already present, {len(failed)} failed")


def cut(src_path, dst):
    """src_path may be a plain .tif or a /vsigzip/ handle onto the .tif.gz"""
    with rasterio.open(src_path) as s:
        w = from_bounds(*H.BBOX, s.transform).round_offsets().round_lengths()
        a = s.read(1, window=w)
        prof = s.profile | {"height": a.shape[0], "width": a.shape[1],
                            "transform": s.window_transform(w), "compress": "deflate"}
        for k in ("tiled", "blockxsize", "blockysize", "interleave"):
            prof.pop(k, None)
        dst.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(dst, "w", **prof) as o:
            o.write(a, 1)
    return a


def run(product):
    spec = RAW_SETS[product]
    if spec.get("archive") == "tgz":
        return run_tarballs(product, spec)
    src_dir = H.RAW / spec["dir"]
    if not src_dir.exists():
        print(f"  {product}: nothing in {src_dir}")
        return
    files = sorted(src_dir.rglob("*.tif.gz"))
    print(f"  {product}: {len(files)} archives in {src_dir.name}")
    done = skipped = 0
    failed = []
    for f in files:
        short = layer_of(f.name, spec["layers"])
        if short is None:
            continue                                       # a layer we do not carry
        out = target(product, short, f.name, f)
        if out.exists():
            skipped += 1
            continue
        try:
            # GDAL reads the gzip stream in place. The alternative -- unpack, then window -- writes
            # a 12 GB global float raster to disk for every VIIRS year to keep a 456x516 window, and
            # a short write leaves a truncated TIFF that fails to open. Streaming takes ~15 s a file.
            a = cut(f"/vsigzip/{f}", out)
        except Exception as e:
            print(f"    vsigzip failed on {f.name} ({e.__class__.__name__}), unpacking instead")
            out.unlink(missing_ok=True)
            try:
                with tempfile.TemporaryDirectory() as tmp:
                    plain = Path(tmp) / f.name[:-3]
                    with gzip.open(f, "rb") as gz, open(plain, "wb") as fh:
                        shutil.copyfileobj(gz, fh, 1 << 22)
                    a = cut(plain, out)
            except Exception as e2:                        # one unreadable archive must not stop the run
                print(f"    SKIPPED {f.name}: {e2}")
                out.unlink(missing_ok=True)
                failed.append(f.name)
                continue
        print(f"    {out.name}  {a.shape[1]}x{a.shape[0]} px, max {float(a.max()):.4g}")
        done += 1
    print(f"  {product}: {done} cut, {skipped} already present, {len(failed)} failed")
    for n in failed:
        print(f"    failed: {n}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    for p in (args or list(RAW_SETS)):
        run(p)
