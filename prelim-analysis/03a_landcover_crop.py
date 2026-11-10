"""Crop downloaded GLAD GLCLU v2 (2000/2005/2010/2015/2020, 30 m) and ESA WorldCover 2021 v200 (10 m) tiles to Rwanda.
Sources (downloaded via browser, Nov 2026):
  https://storage.googleapis.com/earthenginepartners-hansen/GLCLU2000-2020/v2/{year}/{00N_020E,00N_030E}.tif
  https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_{S03E027,S03E030}_Map.tif
Files are identified by byte size (GLCLU) or bounds (WorldCover) because the browser left most under temp names."""
import os, glob, rasterio
from rasterio.merge import merge
from _common import DATA
DL = os.path.expanduser("~/mnt/Downloads")
OUT = DATA / "geo-data" / "land-cover" / "rasters"
BBOX = (28.80, -2.90, 30.95, -1.00)
SIZES = {500947581: ("2005", "00N_020E"), 428679603: ("2005", "00N_030E"), 471057334: ("2015", "00N_020E"),
         422975701: ("2015", "00N_030E"), 502672521: ("2000", "00N_020E"), 428918654: ("2000", "00N_030E"), 493795316: ("2010", "00N_020E"),
         425733990: ("2010", "00N_030E"), 458235005: ("2020", "00N_020E"), 416094531: ("2020", "00N_030E")}
files = [f for f in glob.glob(DL + "/.Q6L2SF6YDW*") + glob.glob(DL + "/GLCLU*") + glob.glob(DL + "/ESA_WorldCover*")]
glclu, wc = {}, {}
for f in files:
    sz = os.path.getsize(f)
    if sz in SIZES and not f.endswith(".crdownload"): glclu.setdefault(SIZES[sz], f)
    else:
        try:
            with rasterio.open(f) as r:
                if abs(r.res[0] - 1 / 12000) < 1e-9: wc.setdefault(round(r.bounds.left), f)
        except Exception: pass
print("GLCLU found:", sorted(glclu)); print("WorldCover found:", sorted(wc))
def write(srcs, out):
    ds = [rasterio.open(s) for s in srcs]
    arr, tr = merge(ds, bounds=BBOX)
    prof = ds[0].profile | dict(driver="GTiff", height=arr.shape[1], width=arr.shape[2], transform=tr, compress="deflate",
                               tiled=True, blockxsize=512, blockysize=512, count=1, BIGTIFF="IF_SAFER")
    with rasterio.open(out, "w", **prof) as o: o.write(arr)
    print(out.name, arr.shape, round(os.path.getsize(out) / 1e6, 1), "MB")
for y in ["2000", "2005", "2010", "2015", "2020"]:
    if (OUT / f"glclu_v2_{y}_rwanda.tif").exists() and os.environ.get("REDO") != "1": continue
    write([glclu[(y, "00N_020E")], glclu[(y, "00N_030E")]], OUT / f"glclu_v2_{y}_rwanda.tif")
if not (OUT / "worldcover_2021_v200_rwanda.tif").exists(): write([wc[27], wc[30]], OUT / "worldcover_2021_v200_rwanda.tif")
