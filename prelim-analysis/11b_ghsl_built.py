"""GHSL built-up surface (GHS-BUILT-S R2023A, 3 arc-second ~90 m, EPSG:4326), total and non-residential (NRES),
epochs 2000/2005/2010/2015/2020, tiles R10_C21 and R10_C22, downloaded via browser Nov 2026 from
https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/GHS_BUILT_S_GLOBE_R2023A/ . Cell values are m2 of built surface.
Files identified by byte size. Writes the Rwanda crops to geo-data/land-cover/rasters/ and
Analysis/prelim/sector_ghsl_built.csv: sector x year, built_total_ha, built_nres_ha, built_res_ha, outside parks."""
import os, glob, zipfile, io, numpy as np, pandas as pd, geopandas as gpd, rasterio
from rasterio.merge import merge
from rasterio.io import MemoryFile
from rasterio.features import rasterize
from _common import DATA, OUT_D
DL = os.path.expanduser("~/mnt/Downloads"); RAS = DATA / "geo-data" / "land-cover" / "rasters"
SZ = {1499665: ("NRES", 2000, "C21"), 1608426: ("NRES", 2000, "C22"), 1503681: ("NRES", 2005, "C21"), 1621220: ("NRES", 2005, "C22"),
      1507142: ("NRES", 2010, "C21"), 1632033: ("NRES", 2010, "C22"), 1514811: ("NRES", 2015, "C21"), 1652889: ("NRES", 2015, "C22"),
      1518864: ("NRES", 2020, "C21"), 1662719: ("NRES", 2020, "C22"), 9355899: ("TOT", 2000, "C21"), 22336968: ("TOT", 2000, "C22"),
      10217173: ("TOT", 2005, "C21"), 27419403: ("TOT", 2005, "C22"), 10965637: ("TOT", 2010, "C21"), 31911173: ("TOT", 2010, "C22"),
      11860725: ("TOT", 2015, "C21"), 37053299: ("TOT", 2015, "C22"), 12533573: ("TOT", 2020, "C21"), 41038054: ("TOT", 2020, "C22")}
files = {}
for f in glob.glob(DL + "/.Q6L2SF6YDW*") + glob.glob(DL + "/GHS_*.zip"):
    k = SZ.get(os.path.getsize(f))
    if k and zipfile.is_zipfile(f): files.setdefault(k, f)
assert len(files) == 20, sorted(files)
sec = gpd.read_file(DATA / "geo-data/protected-areas/sectors_park_exposure_geodatarw.gpkg")[["sector_id", "geometry"]]; sec["sector_id"] = sec.sector_id.astype(int)
pa = gpd.read_file(DATA / "geo-data/protected-areas/rwanda_protected_areas_geodata_rw.gpkg")
park = pa[pa["type"].isin(["National Park", "Volcanoes National Park", "Forest Reserve"])].union_all()
BBOX = (28.80, -2.90, 30.95, -1.00); rows = []
TMP = os.path.expanduser("~/ghsl_tiles"); os.makedirs(TMP, exist_ok=True)
def open_tif(zf):
    z = zipfile.ZipFile(zf); n = [x for x in z.namelist() if x.endswith(".tif")][0]
    out = os.path.join(TMP, os.path.basename(n))
    if not os.path.exists(out): z.extract(n, TMP); os.replace(os.path.join(TMP, n), out) if n != os.path.basename(n) else None
    return rasterio.open(out), os.path.basename(n)
for kind in ["TOT", "NRES"]:
    for y in [2000, 2005, 2010, 2015, 2020]:
        ds = [open_tif(files[(kind, y, c)]) for c in ["C21", "C22"]]
        assert all(str(y) in n and (("NRES" in n) == (kind == "NRES")) for _, n in ds), [n for _, n in ds]
        arr, tr = merge([d for d, _ in ds], bounds=BBOX); a = arr[0].astype("float64"); nod = ds[0][0].nodata
        if nod is not None: a[a == nod] = 0
        a[a < 0] = 0
        prof = ds[0][0].profile | dict(driver="GTiff", height=a.shape[0], width=a.shape[1], transform=tr, compress="deflate", count=1)
        with rasterio.open(RAS / f"ghsl_built_{kind.lower()}_{y}_rwanda.tif", "w", **prof) as o: o.write(arr)
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
