"""GHSL built-up surface (GHS-BUILT-S R2023A, 3 arc-second ~90 m, EPSG:4326), total and non-residential (NRES),
epochs 2000/2005/2010/2015/2020, tiles R10_C21 and R10_C22. Cell values are m2 of built surface.

Uses the Rwanda crops in data/geo-data/land-cover/rasters/ (ghsl_built_{tot,nres}_{year}_rwanda.tif) when they exist
(REDO=1 rebuilds them); otherwise builds them from the zipped tiles in data/geo-data/land-cover/raw-tiles/, named
ghsl_built_{tot,nres}_{year}_tile_R10_{C21,C22}.zip. A missing tile stops the script with the file to fetch from
https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/GHS_BUILT_S_GLOBE_R2023A/ (original name in the message).
Writes Analysis/prelim/sector_ghsl_built.csv: sector x year, built_total_ha, built_nres_ha, built_res_ha, outside parks."""
import os, zipfile, tempfile, numpy as np, pandas as pd, geopandas as gpd, rasterio
from rasterio.merge import merge
from rasterio.features import rasterize
from pathlib import Path
from _common import DATA, OUT_D
RAW = DATA / "geo-data" / "land-cover" / "raw-tiles"; RAS = DATA / "geo-data" / "land-cover" / "rasters"
REDO = os.environ.get("REDO") == "1"
SRC = "https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/GHS_BUILT_S_GLOBE_R2023A/"
def orig_name(kind, y, c):
    return f"GHS_BUILT_S{'_NRES' if kind == 'NRES' else ''}_E{y}_GLOBE_R2023A_4326_3ss_V1_0_R10_{c}.zip"
sec = gpd.read_file(DATA / "geo-data/protected-areas/sectors_park_exposure_geodatarw.gpkg")[["sector_id", "geometry"]]; sec["sector_id"] = sec.sector_id.astype(int)
pa = gpd.read_file(DATA / "geo-data/protected-areas/rwanda_protected_areas_geodata_rw.gpkg")
park = pa[pa["type"].isin(["National Park", "Volcanoes National Park", "Forest Reserve"])].union_all()
BBOX = (28.80, -2.90, 30.95, -1.00); rows = []
TMP = Path(tempfile.mkdtemp(prefix="ghsl_tiles_"))
def open_tif(zf):
    z = zipfile.ZipFile(zf); n = [x for x in z.namelist() if x.endswith(".tif")][0]
    return rasterio.open(z.extract(n, TMP)), os.path.basename(n)
def build_crop(kind, y, out):
    zs = [RAW / f"ghsl_built_{kind.lower()}_{y}_tile_R10_{c}.zip" for c in ["C21", "C22"]]
    miss = [(z.name, orig_name(kind, y, c)) for z, c in zip(zs, ["C21", "C22"]) if not z.exists()]
    if miss:
        raise SystemExit(f"Missing raw tiles in {RAW} (source {SRC}):\n" + "\n".join(f"  {n}  <-  {o}" for n, o in miss))
    ds = [open_tif(z) for z in zs]
    assert all(str(y) in n and (("NRES" in n) == (kind == "NRES")) for _, n in ds), [n for _, n in ds]
    arr, tr = merge([d for d, _ in ds], bounds=BBOX); nod = ds[0][0].nodata
    if nod is not None: arr[arr == nod] = 0
    arr[arr < 0] = 0
    prof = ds[0][0].profile | dict(driver="GTiff", height=arr.shape[1], width=arr.shape[2], transform=tr, compress="deflate", count=1)
    with rasterio.open(out, "w", **prof) as o: o.write(arr)
for kind in ["TOT", "NRES"]:
    for y in [2000, 2005, 2010, 2015, 2020]:
        crop = RAS / f"ghsl_built_{kind.lower()}_{y}_rwanda.tif"
        if REDO or not crop.exists(): build_crop(kind, y, crop)
        with rasterio.open(crop) as r: a = r.read(1).astype("float64"); tr = r.transform; nod = r.nodata
        if nod is not None: a[a == nod] = 0
        a[a < 0] = 0
        sid = rasterize(zip(sec.geometry, sec.sector_id), out_shape=a.shape, transform=tr, fill=0, dtype="int32")
        pk = rasterize([(park, 1)], out_shape=a.shape, transform=tr, fill=0, dtype="uint8")
        m = (sid > 0) & (pk == 0)
        s = np.bincount(sid[m], weights=a[m], minlength=sid.max() + 1) / 1e4      # m2 -> ha
        rows += [dict(sid=i, year=y, kind=kind, ha=s[i]) for i in sec.sector_id]
        print(kind, y, "Rwanda total (000 ha):", round(s.sum() / 1e3, 1))
G = pd.DataFrame(rows).pivot_table(index=["sid", "year"], columns="kind", values="ha").reset_index().rename(columns={"TOT": "built_total_ha", "NRES": "built_nres_ha"})
G["built_res_ha"] = G.built_total_ha - G.built_nres_ha
G.to_csv(OUT_D / "sector_ghsl_built.csv", index=False)
print(G.groupby("year")[["built_total_ha", "built_nres_ha", "built_res_ha"]].sum().div(1e3).round(1))
