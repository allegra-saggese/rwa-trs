"""Sector-level land use (hectares) from GLCLU v2 2000/2010/2020 and WorldCover 2021, total and outside parks.
GLCLU legend: 244 cropland; 250 built-up (any man-made surface in a 30 m pixel, so rural homesteads count);
25-48 and 125-148 tree height 3 to >25 m (terra firma / wetland); 200-211 and 254 water; rest = other
(short vegetation, bare). WorldCover: 10 tree, 20 shrub, 30 grass, 40 cropland, 50 built-up, 60 bare,
80 water, 90 wetland. Pixel area varies with latitude and is computed per row.
Park mask = RDB national parks + Gishwati/Mukura forest reserves (geodata.rw), wetlands excluded."""
import numpy as np, pandas as pd, geopandas as gpd, rasterio
from rasterio.features import rasterize
from rasterio.windows import Window
from _common import DATA, OUT_D
GEO = DATA / "geo-data"; RAS = GEO / "land-cover" / "rasters"
sec = gpd.read_file(GEO / "protected-areas" / "sectors_park_exposure_geodatarw.gpkg")[["sector_id", "geometry"]]
sec["sector_id"] = sec.sector_id.astype(int)
pa = gpd.read_file(GEO / "protected-areas" / "rwanda_protected_areas_geodata_rw.gpkg")
park = pa[pa["type"].isin(["National Park", "Volcanoes National Park", "Forest Reserve"])].union_all()
NS = int(sec.sector_id.max()) + 1

def classes_glclu(a):
    c = np.full(a.shape, 5, np.uint8)            # 5 other
    c[a == 244] = 0                               # crop
    c[a == 250] = 1                               # built
    c[((a >= 25) & (a <= 48)) | ((a >= 125) & (a <= 148))] = 2  # tree
    c[((a >= 200) & (a <= 211)) | (a == 254)] = 3                # water
    c[a == 255] = 4                               # nodata
    return c
def classes_wc(a):
    m = np.full(256, 5, np.uint8); m[40] = 0; m[50] = 1; m[10] = 2; m[80] = 3; m[0] = 4; m[[20, 30]] = 6; m[90] = 7
    return m[a]
NAMES = {0: "crop", 1: "built", 2: "tree", 3: "water", 4: "nodata", 5: "other", 6: "shrub_grass", 7: "wetland"}

def zonal(path, fn, rows=1500):
    with rasterio.open(path) as r:
        acc = np.zeros((2, NS, 8))
        for r0 in range(0, r.height, rows):
            h = min(rows, r.height - r0); w = Window(0, r0, r.width, h); tr = r.window_transform(w)
            a = r.read(1, window=w)
            sid = rasterize(zip(sec.geometry, sec.sector_id), out_shape=a.shape, transform=tr, fill=0, dtype="int32")
            pk = rasterize([(park, 1)], out_shape=a.shape, transform=tr, fill=0, dtype="uint8")
            lat = tr.f + tr.e * (np.arange(h) + 0.5)
            pxha = (abs(tr.a) * 111320 * np.cos(np.radians(lat))) * (abs(tr.e) * 110574) / 1e4
            ar = np.broadcast_to(pxha[:, None], a.shape)
            c = fn(a); ok = sid > 0
            for p in (0, 1):
                m = ok & (pk == p)
                np.add.at(acc[p], (sid[m], c[m]), ar[m])
    rows_ = []
    for p, lab in ((0, "out"), (1, "park")):
        d = pd.DataFrame(acc[p], columns=[NAMES[i] for i in range(8)]); d["sector_id"] = d.index; d["zone"] = lab
        rows_.append(d)
    d = pd.concat(rows_); d = d[d.sector_id.isin(sec.sector_id)]
    return d.pivot(index="sector_id", columns="zone").pipe(lambda x: x.set_axis([f"{a}_{b}_ha" for a, b in x.columns], axis=1))

out = []
for y in [2000, 2005, 2010, 2015, 2020]:
    d = zonal(RAS / f"glclu_v2_{y}_rwanda.tif", classes_glclu)
    d = d.loc[:, (d != 0).any()]; d["year"] = y; out.append(d.reset_index()); print(y, "done")
gl = pd.concat(out); gl.to_csv(OUT_D / "sector_landcover_glclu.csv", index=False)

# ---- pixel transitions 2000 -> 2020 by treatment group, outside parks (ha) ----
tg = pd.read_csv(OUT_D / "treatment_groups.csv")
gcode = {"Gates": 1, "Gates+": 2, "Bordering": 3, "Control": 4, "Towns": 5, "Kigali": 6}
lut = np.zeros(NS, np.uint8); lut[tg.sid.values] = tg.group.map(gcode).values
T = np.zeros((7, 6, 6))
with rasterio.open(RAS / "glclu_v2_2000_rwanda.tif") as r0, rasterio.open(RAS / "glclu_v2_2020_rwanda.tif") as r1:
    for r_ in range(0, r0.height, 1500):
        h = min(1500, r0.height - r_); w = Window(0, r_, r0.width, h); tr = r0.window_transform(w)
        a0 = classes_glclu(r0.read(1, window=w)); a1 = classes_glclu(r1.read(1, window=w))
        sid = rasterize(zip(sec.geometry, sec.sector_id), out_shape=a0.shape, transform=tr, fill=0, dtype="int32")
        pk = rasterize([(park, 1)], out_shape=a0.shape, transform=tr, fill=0, dtype="uint8")
        lat = tr.f + tr.e * (np.arange(h) + 0.5)
        ar = np.broadcast_to(((abs(tr.a) * 111320 * np.cos(np.radians(lat))) * (abs(tr.e) * 110574) / 1e4)[:, None], a0.shape)
        m = (sid > 0) & (pk == 0)
        np.add.at(T, (lut[sid[m]], a0[m], a1[m]), ar[m])
rows = []
for gname, gc in gcode.items():
    for i in range(6):
        for j in range(6):
            rows.append(dict(group=gname, from_=NAMES[i], to=NAMES[j], ha=T[gc, i, j]))
pd.DataFrame(rows).rename(columns={"from_": "from"}).to_csv(OUT_D / "glclu_transitions_2000_2020.csv", index=False)
print("transitions written")
wc = zonal(RAS / "worldcover_2021_v200_rwanda.tif", classes_wc, rows=1200).reset_index()
wc.to_csv(OUT_D / "sector_landcover_worldcover2021.csv", index=False)
for nm, d in (("GLCLU", gl.groupby("year").sum(numeric_only=True)), ("WorldCover", wc.sum(numeric_only=True).to_frame("2021").T)):
    print(nm); print((d.filter(like="_ha") / 1e3).round(1).T.to_string())
