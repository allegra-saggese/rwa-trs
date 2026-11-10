"""Hansen GFC tree-cover loss by sector and year, outside parks, from the Rwanda crops in geo-data/forest.
Tree cover = canopy >= 30% in 2000 (Hansen convention). Loss year 1-24 = 2001-2024. Pixel area by latitude.
Writes Analysis/prelim/sector_hansen_annual.csv (sector x year: loss_ha, treecover2000_ha) and
sector_forest_census.csv: for each Census wave, mean annual loss over the years AFTER it, as % of 2000 tree cover:
  2002 -> 2003-2005, 2012 -> 2013-2015, 2022 -> 2023-2024 (only two years exist after 2022)."""
import numpy as np, pandas as pd, geopandas as gpd, rasterio
from rasterio.features import rasterize
from _common import DATA, OUT_D
F = DATA / "geo-data" / "forest"
sec = gpd.read_file(DATA / "geo-data/protected-areas/sectors_park_exposure_geodatarw.gpkg")[["sector_id", "geometry"]]; sec["sector_id"] = sec.sector_id.astype(int)
pa = gpd.read_file(DATA / "geo-data/protected-areas/rwanda_protected_areas_geodata_rw.gpkg")
park = pa[pa["type"].isin(["National Park", "Volcanoes National Park", "Forest Reserve"])].union_all()
with rasterio.open(F / "hansen_rwanda_lossyear.tif") as r1, rasterio.open(F / "hansen_rwanda_treecover2000.tif") as r2:
    ly = r1.read(1); tc = r2.read(1); tr = r1.transform; shp = ly.shape
sid = rasterize(zip(sec.geometry, sec.sector_id), out_shape=shp, transform=tr, fill=0, dtype="int32")
pk = rasterize([(park, 1)], out_shape=shp, transform=tr, fill=0, dtype="uint8")
lat = tr.f + tr.e * (np.arange(shp[0]) + 0.5)
ha = np.broadcast_to((((abs(tr.a) * 111320 * np.cos(np.radians(lat))) * (abs(tr.e) * 110574)) / 1e4)[:, None], shp)
m = (sid > 0) & (pk == 0) & (tc >= 30) & (tc <= 100)
NS = sid.max() + 1
tc_ha = np.bincount(sid[m], weights=ha[m], minlength=NS)
rows = []
for y in range(1, 25):
    mm = m & (ly == y); loss = np.bincount(sid[mm], weights=ha[mm], minlength=NS)
    rows += [dict(sid=s, year=2000 + y, loss_ha=loss[s], treecover2000_ha=tc_ha[s]) for s in sec.sector_id]
A = pd.DataFrame(rows); A.to_csv(OUT_D / "sector_hansen_annual.csv", index=False)
W = {2002: [2003, 2004, 2005], 2012: [2013, 2014, 2015], 2022: [2023, 2024]}
C = pd.concat([A[A.year.isin(ys)].groupby("sid").agg(loss_ha=("loss_ha", "mean"), tc=("treecover2000_ha", "first")).assign(wave=w) for w, ys in W.items()]).reset_index()
C["loss_rate"] = 100 * C.loss_ha / C.tc.where(C.tc >= 10)          # % of 2000 cover per year; sectors with >= 10 ha cover
C["asinh_loss"] = np.arcsinh(C.loss_ha)
C.to_csv(OUT_D / "sector_forest_census.csv", index=False)
print("national tree cover 2000 outside parks (000 ha):", round(tc_ha.sum() / 1e3, 1))
print(A.groupby("year").loss_ha.sum().round(0).to_dict())
print(C.groupby("wave")[["loss_rate", "loss_ha"]].describe().round(2).T)
