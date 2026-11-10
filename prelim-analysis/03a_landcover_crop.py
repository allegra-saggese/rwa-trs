"""Crop GLAD GLCLU v2 (2000/2005/2010/2015/2020, 30 m) and ESA WorldCover 2021 v200 (10 m) tiles to Rwanda.

Raw tiles live in data/geo-data/land-cover/raw-tiles/ under the names below; the Rwanda crops go to
data/geo-data/land-cover/rasters/. A crop that already exists is skipped (REDO=1 rebuilds it), so the raw
tiles are only needed to rebuild a crop. A missing tile stops the script with the file name and URL to fetch.
Sources:
  GLCLU:      https://storage.googleapis.com/earthenginepartners-hansen/GLCLU2000-2020/v2/{year}/{tile}.tif
  WorldCover: https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_{tile}_Map.tif"""
import os, rasterio
from rasterio.merge import merge
from _common import DATA
RAW = DATA / "geo-data" / "land-cover" / "raw-tiles"
OUT = DATA / "geo-data" / "land-cover" / "rasters"
BBOX = (28.80, -2.90, 30.95, -1.00)
GLCLU_URL = "https://storage.googleapis.com/earthenginepartners-hansen/GLCLU2000-2020/v2/{y}/{t}.tif"
WC_URL = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_{t}_Map.tif"
REDO = os.environ.get("REDO") == "1"


def tiles(names_urls):
    missing = [(n, u) for n, u in names_urls if not (RAW / n).exists()]
    if missing:
        raise SystemExit("Missing raw tiles in " + str(RAW) + ":\n" + "\n".join(f"  {n}  <-  {u}" for n, u in missing))
    return [RAW / n for n, _ in names_urls]


def write(srcs, out):
    ds = [rasterio.open(s) for s in srcs]
    arr, tr = merge(ds, bounds=BBOX)
    prof = ds[0].profile | dict(driver="GTiff", height=arr.shape[1], width=arr.shape[2], transform=tr, compress="deflate",
                               tiled=True, blockxsize=512, blockysize=512, count=1, BIGTIFF="IF_SAFER")
    with rasterio.open(out, "w", **prof) as o: o.write(arr)
    print(out.name, arr.shape, round(os.path.getsize(out) / 1e6, 1), "MB")
for y in ["2000", "2005", "2010", "2015", "2020"]:
    out = OUT / f"glclu_v2_{y}_rwanda.tif"
    if out.exists() and not REDO: continue
    write(tiles([(f"glclu_v2_{y}_tile_{t}.tif", GLCLU_URL.format(y=y, t=t)) for t in ["00N_020E", "00N_030E"]]), out)
out = OUT / "worldcover_2021_v200_rwanda.tif"
if not out.exists() or REDO:
    write(tiles([(f"worldcover_2021_v200_tile_{t}.tif", WC_URL.format(t=t)) for t in ["S03E027", "S03E030"]]), out)
