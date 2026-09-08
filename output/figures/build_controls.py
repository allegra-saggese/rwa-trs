"""
build_controls.py -- the 2002 sector-level control block the lasso chooses from.

    python build_controls.py

    Analysis/census_sector_controls_2002.csv    416 sectors x 46 controls
    geo-data/raster/rwanda_dem_z11_3857.tif     elevation mosaic, ~38 m, EPSG:3857
    geo-data/raster/sector_terrain.csv          elevation, ruggedness and slope per sector
    geo-data/roads/osm_trunk_primary.gpkg       Rwanda trunk and primary roads
    geo-data/roads/sector_distances.csv         distance to the trunk network and to Kigali

The two geographic layers are downloaded once and reused; delete them to force a refresh.

Everything here is measured in 2002 or earlier, so nothing can respond to Tourism Revenue Sharing,
which starts in 2005. Two blocks are deliberately absent:

  human capital and employment   literacy, schooling, activity status, occupation, industry. These
                                 become outcomes later in the project, so they stay out of the
                                 control set. The hotel and restaurant share is doubly out: the parks
                                 are long-standing (Volcanoes 1925, Nyungwe 1933), so the 2002 level
                                 is already partly treated by pre-2002 tourism.
  anything measured after 2002   the electricity grid, Google Open Buildings, Dynamic World land
                                 cover, forest loss years, settlement extents, tourism points of
                                 interest. All of them could be consequences of the treatment.

Three coding traps in the 2002 census, all handled below:
  "Not stated" is a code, not a blank: 9 or 99 depending on the item, and counting it as a No would
  quietly bias every share. The births in the last twelve months use 9 for not stated where the real
  maximum is 3, which inflates fertility fivefold if it is missed.
  Place of birth and previous residence use the twelve pre-2006 prefectures, while the pooled file's
  district code is the modern thirty, so "born in another district" cannot be built. Born abroad can.
  Collective households are not in the public-use file, so that share is identically zero.
"""
import io
import json
import math
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyreadstat
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_origin
from shapely.geometry import LineString

DB = Path("/Users/matteo/Library/CloudStorage/Dropbox/1-Ongoing Projects/Rwanda - TRS")
NISR = DB / "data/Publicly-Available-NISR"
GEO = DB / "data/geo-data"
ANALYSIS = NISR / "Analysis"
CENSUS = NISR / "Census-PHC/3_Final"
SECTORS = GEO / "protected-areas/sectors_park_exposure_wdpa.gpkg"

KIGALI = (30.0925, -1.9536)                 # the Convention Centre, the same anchor as the maps
DEM_ZOOM = 11
DEM_BOX = (28.80, -2.90, 30.95, -1.00)      # Rwanda with a margin


# ------------------------------------------------------------------ small helpers
def wmean(v, w):
    ok = v.notna() & w.notna()
    return float((v[ok] * w[ok]).sum() / w[ok].sum()) if w[ok].sum() > 0 else np.nan


def wsum(v, w):
    ok = v.notna() & w.notna()
    return float((v[ok] * w[ok]).sum())


def share(s, keep, na=()):
    """1 if the code is in keep, 0 if it is another real code, missing if it is a not-stated code"""
    v = pd.to_numeric(s, errors="coerce")
    return pd.Series(np.where(v.isna() | v.isin(na), np.nan, v.isin(keep).astype(float)), index=s.index)


def sectors():
    g = gpd.read_file(SECTORS)
    g["sid"] = g.sector_id.astype(int)
    return g


# ------------------------------------------------------------------ terrain
def dem_mosaic(path):
    """AWS open terrain tiles (Tilezen, no key) stitched into one GeoTIFF"""
    z, (W, S, E, N) = DEM_ZOOM, DEM_BOX

    def deg2num(lon, lat):
        n = 2 ** z
        lr = math.radians(lat)
        return (int((lon + 180.0) / 360.0 * n),
                int((1.0 - math.log(math.tan(lr) + 1 / math.cos(lr)) / math.pi) / 2.0 * n))

    x0, y0 = deg2num(W, N)
    x1, y1 = deg2num(E, S)
    tiles = [(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]
    url = "https://s3.amazonaws.com/elevation-tiles-prod/geotiff/{z}/{x}/{y}.tif"
    print(f"  downloading {len(tiles)} elevation tiles at zoom {z}")

    def get(t):
        x, y = t
        for _ in range(3):
            try:
                with urllib.request.urlopen(url.format(z=z, x=x, y=y), timeout=60) as r:
                    b = r.read()
                with rasterio.open(io.BytesIO(b)) as src:
                    return t, src.read(1).astype("float32")
            except Exception:
                pass
        return t, None

    with ThreadPoolExecutor(max_workers=12) as ex:
        got = dict(ex.map(get, tiles))
    missing = [t for t, a in got.items() if a is None]
    if missing:
        raise RuntimeError(f"{len(missing)} elevation tiles failed to download")
    ts = next(iter(got.values())).shape[0]
    h, w = (y1 - y0 + 1) * ts, (x1 - x0 + 1) * ts
    mos = np.full((h, w), np.nan, "float32")
    for (x, y), a in got.items():
        mos[(y - y0) * ts:(y - y0 + 1) * ts, (x - x0) * ts:(x - x0 + 1) * ts] = a
    R = 6378137.0

    def num2merc(x, y):
        n = 2 ** z
        return (x / n * 2 - 1) * math.pi * R, (1 - y / n * 2) * math.pi * R

    left, top = num2merc(x0, y0)
    right, _ = num2merc(x1 + 1, y1 + 1)
    res = (right - left) / w
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", driver="GTiff", height=h, width=w, count=1, dtype="float32",
                       crs="EPSG:3857", transform=from_origin(left, top, res, res),
                       nodata=np.nan, compress="deflate") as dst:
        dst.write(mos, 1)
    print(f"  mosaic {mos.shape}, {res:.0f} m pixels -> {path.name}")


def terrain():
    """mean elevation, its standard deviation (ruggedness) and mean slope, per sector"""
    out = GEO / "raster/sector_terrain.csv"
    if out.exists():
        return pd.read_csv(out)
    dem = GEO / "raster/rwanda_dem_z11_3857.tif"
    if not dem.exists():
        dem_mosaic(dem)
    g = sectors()
    with rasterio.open(dem) as src:
        z = src.read(1)
        gm = g.to_crs(src.crs)
        lab = rasterize([(geom, i + 1) for i, geom in enumerate(gm.geometry)], out_shape=z.shape,
                        transform=src.transform, fill=0, dtype="int32")
        res = src.transform.a
    dy, dx = np.gradient(z, res, res)          # Web Mercator scale error at 2 degrees south is 0.06%
    slope = np.degrees(np.arctan(np.hypot(dx, dy)))
    ok = (lab > 0) & np.isfinite(z)
    df = pd.DataFrame({"i": lab[ok] - 1, "elev": z[ok], "slope": slope[ok]})
    agg = df.groupby("i").agg(elev_mean=("elev", "mean"), elev_sd=("elev", "std"),
                              slope_mean=("slope", "mean"))
    t = gm[["sid"]].reset_index(drop=True).join(agg)
    t.to_csv(out, index=False)
    print("  terrain ->", out.name)
    return t


# ------------------------------------------------------------------ distances
def distances():
    """distance from the sector centroid to the trunk road network and to Kigali"""
    out = GEO / "roads/sector_distances.csv"
    if out.exists():
        return pd.read_csv(out)
    roads_path = GEO / "roads/osm_trunk_primary.gpkg"
    if roads_path.exists():
        roads = gpd.read_file(roads_path)
    else:
        q = ('[out:json][timeout:180];area["ISO3166-1"="RW"][admin_level=2]->.rw;'
             'way(area.rw)["highway"~"^(trunk|primary)$"];out geom;')
        req = urllib.request.Request("https://overpass-api.de/api/interpreter",
                                     data=urllib.parse.urlencode({"data": q}).encode(),
                                     headers={"User-Agent": "rwa-trs-research"})
        with urllib.request.urlopen(req, timeout=300) as r:
            js = json.loads(r.read())
        lines = [LineString([(p["lon"], p["lat"]) for p in e["geometry"]])
                 for e in js["elements"] if e.get("geometry") and len(e["geometry"]) > 1]
        roads = gpd.GeoDataFrame(geometry=lines, crs=4326)
        roads_path.parent.mkdir(parents=True, exist_ok=True)
        roads.to_file(roads_path, driver="GPKG")
        print(f"  {len(lines)} trunk and primary road ways -> {roads_path.name}")
    # only the trunk network: it is essentially colonial-era and stable, so it is pre-treatment,
    # while the secondary network that was built or upgraded after 2002 is not
    g = sectors().to_crs(32736)
    net = roads.to_crs(32736).union_all()
    kgl = gpd.GeoSeries.from_xy([KIGALI[0]], [KIGALI[1]], crs=4326).to_crs(32736).iloc[0]
    cen = g.geometry.centroid
    d = pd.DataFrame({"sid": g.sid.values,
                      "log_dist_road": np.log1p(cen.distance(net).values / 1000),
                      "log_dist_kigali": np.log(cen.distance(kgl).values / 1000)})
    d.to_csv(out, index=False)
    print("  distances ->", out.name)
    return d


# ------------------------------------------------------------------ census, household file
def household_block():
    h, _ = pyreadstat.read_dta(CENSUS / "Census_pooled_household.dta", usecols=[
        "census_wave", "census_sector", "census_household_weight", "census_household_size",
        "census_head_sex", "census_head_age", "census_urban", "census_lighting_source_2002",
        "census_cooking_energy_2002", "census_tenure_2002", "census_settlement_2002_2012",
        "census_dwelling_type_2002_2012", "census_living_rooms_2002", "census_radio_television_2002",
        "census_telephone_2002", "census_bicycles_2002", "census_death_last_12m_2002"])
    h = h[h.census_wave.astype(str) == "2002"].rename(columns=lambda c: c.replace("census_", ""))
    h["w"] = h.household_weight.fillna(1.0)
    h["female_head"] = (h.head_sex == 2).astype(float)
    h["urban02"] = (h.urban == 1).astype(float)
    h["electric02"] = share(h.lighting_source_2002, [1, 2], [9])
    h["firewood02"] = share(h.cooking_energy_2002, [4], [9])
    h["owner02"] = share(h.tenure_2002, [1], [9])
    h["planned02"] = share(h.settlement_2002_2012, [1, 4], [9])
    h["onehh_house02"] = share(h.dwelling_type_2002_2012, [1], [9])
    lr = pd.to_numeric(h.living_rooms_2002, errors="coerce")
    h["rooms02"] = lr.where(lr < 90)                          # 99 is not stated
    h["radiotv02"] = share(h.radio_television_2002, [1, 2, 3], [9])
    h["phone02"] = share(h.telephone_2002, [1, 2, 3], [9])
    h["bicycle02"] = (pd.to_numeric(h.bicycles_2002, errors="coerce") > 0).astype(float)
    h["death02"] = share(h.death_last_12m_2002, [1], [9])
    h["hh_size"] = h.household_size
    h["head_age"] = h.head_age
    cols = ["hh_size", "female_head", "head_age", "urban02", "electric02", "firewood02", "owner02",
            "planned02", "onehh_house02", "rooms02", "radiotv02", "phone02", "bicycle02", "death02"]
    return h.groupby("sector").apply(lambda g: pd.Series({c: wmean(g[c], g.w) for c in cols}))


# ------------------------------------------------------------------ census, person file
ENGLISH = [8, 9, 10, 11, 12, 13, 14, 15, 24, 25, 26, 27, 28, 29, 30, 31]
FRENCH = [2, 3, 6, 7, 10, 11, 14, 15, 18, 19, 22, 23, 26, 27, 30, 31]
SWAHILI = [4, 5, 6, 7, 12, 13, 14, 15, 20, 21, 22, 23, 28, 29, 30, 31]


def person_block():
    p, _ = pyreadstat.read_dta(CENSUS / "Census_pooled_person.dta", usecols=[
        "census_wave", "census_sector", "census_weight", "census_sex", "census_age",
        "census_marital_grouped_2002", "census_handicap_type_2002", "census_handicap_cause_2002",
        "census_residence_duration_2002", "census_birth_place_2002", "census_previous_residence_2002",
        "census_parents_survival_2002", "census_languages_spoken_2002", "census_nationality_2002",
        "census_religion_2002", "census_relation_head_2002_2012",
        "census_births_boys_2002", "census_births_girls_2002",
        "census_children_alive_boys_2002", "census_children_alive_girls_2002",
        "census_births_12m_boys_2002", "census_births_12m_girls_2002",
        "census_surviving_12m_boys_2002", "census_surviving_12m_girls_2002"])
    p = p[p.census_wave.astype(str) == "2002"].rename(
        columns=lambda c: c.replace("census_", "").replace("_2002_2012", "").replace("_2002", ""))
    p["w"] = p.weight.fillna(1.0)
    num = lambda c: pd.to_numeric(p[c], errors="coerce")
    age = num("age")

    p["share_u15"] = (age < 15).astype(float)
    p["share_65p"] = (age >= 65).astype(float)
    p["widowed"] = share(p.marital_grouped, [9], [99])
    p["never_married"] = share(p.marital_grouped, [1], [99])
    p["divorced"] = share(p.marital_grouped, [8], [99])
    p["handicap"] = share(p.handicap_type, [2, 3, 4, 5, 6, 7, 8], [9])       # 1 is no handicap
    p["war_disab"] = num("handicap_cause").isin([4, 5, 6]).astype(float)     # war, genocide, mines
    rd = num("residence_duration")
    p["newcomer5"] = np.where(rd.isna(), np.nan, rd.between(0, 4).astype(float))  # 98, 99 long-term
    p["foreign_born"] = share(p.birth_place, list(range(2000, 10000)))
    p["prev_abroad"] = share(p.previous_residence, list(range(2000, 10000)))
    p["orphan_double"] = share(p.parents_survival, [4])
    p["orphan_any"] = share(p.parents_survival, [2, 3, 4])
    p["english"] = share(p.languages_spoken, ENGLISH)
    p["french"] = share(p.languages_spoken, FRENCH)
    p["swahili"] = share(p.languages_spoken, SWAHILI)
    p["nonrwandan"] = np.where(num("nationality").isna(), np.nan,
                               num("nationality").ne(100).astype(float))
    p["catholic"] = share(p.religion, [1])
    p["protestant"] = share(p.religion, [2])
    p["muslim"] = share(p.religion, [6])
    p["extended"] = share(p.relation_head, [7, 8])                # grandchild, other relative
    p["nonrelative"] = share(p.relation_head, [9])
    p["child_head"] = np.where(num("relation_head").eq(1), (age < 18).astype(float), np.nan)

    cap = lambda c: num(c).where(lambda x: x < 30)                # 99 is not stated
    cap12 = lambda c: num(c).where(lambda x: x < 9)               # 9 is not stated, real maximum 3
    births = cap("births_boys").fillna(0) + cap("births_girls").fillna(0)
    alive = cap("children_alive_boys").fillna(0) + cap("children_alive_girls").fillna(0)
    had = (cap("births_boys").notna() | cap("births_girls").notna()) & (births > 0)
    p["_births"], p["_alive"] = births.where(had), alive.where(had)
    w49 = (num("sex") == 2) & age.between(15, 49)
    p["_b12"] = (cap12("births_12m_boys").fillna(0) + cap12("births_12m_girls").fillna(0)).where(w49)
    p["_s12"] = (cap12("surviving_12m_boys").fillna(0) + cap12("surviving_12m_girls").fillna(0)).where(w49)
    p["_w49"] = w49.astype(float)
    asked = cap("births_boys").notna() | cap("births_girls").notna()
    p["_ceb"] = births.where(w49 & asked)      # children ever born per woman 15-49, zero parity in

    simple = ["share_u15", "share_65p", "widowed", "never_married", "divorced", "handicap",
              "war_disab", "newcomer5", "foreign_born", "prev_abroad", "orphan_double", "orphan_any",
              "english", "french", "swahili", "nonrwandan", "catholic", "protestant", "muslim",
              "extended", "nonrelative", "child_head"]

    def agg(g):
        r = {c: wmean(g[c], g.w) for c in simple}
        b, a = wsum(g._births, g.w), wsum(g._alive, g.w)
        r["child_mort"] = (b - a) / b if b > 0 else np.nan
        b12, s12, n49 = wsum(g._b12, g.w), wsum(g._s12, g.w), wsum(g._w49, g.w)
        r["fert_12m"] = b12 / n49 if n49 > 0 else np.nan
        r["infant_mort"] = (b12 - s12) / b12 if b12 > 0 else np.nan
        r["fertility02"] = wmean(g._ceb, g.w)
        r["log_pop"] = np.log(g.w.sum())
        return pd.Series(r)

    return p.groupby("sector").apply(agg)


# The 46 candidates, in the order the lasso sees them.
BLOCKS = {
    "household composition": ["hh_size", "female_head", "head_age", "share_u15", "share_65p",
                              "extended", "nonrelative", "child_head", "never_married", "divorced"],
    "war and genocide legacy": ["widowed", "handicap", "war_disab", "orphan_double", "orphan_any"],
    "resettlement": ["newcomer5", "foreign_born", "prev_abroad", "nonrwandan",
                     "english", "french", "swahili"],
    "health and fertility": ["child_mort", "fert_12m", "infant_mort", "fertility02", "death02"],
    "religion": ["catholic", "protestant", "muslim"],
    "settlement and structure": ["urban02", "log_pop", "planned02", "onehh_house02", "owner02"],
    "baseline amenities and assets": ["electric02", "firewood02", "rooms02", "radiotv02", "phone02",
                                      "bicycle02"],
    "terrain and access": ["elev_mean", "elev_sd", "slope_mean", "log_dist_road", "log_dist_kigali"],
}
CONTROLS = [c for cols in BLOCKS.values() for c in cols]


def build():
    print("terrain and distances")
    t, d = terrain(), distances()
    print("census 2002")
    X = household_block().join(person_block())
    X.index = X.index.astype(int)
    X.index.name = "sid"
    X = X.reset_index().merge(t, on="sid", how="left").merge(d, on="sid", how="left")
    missing = [c for c in CONTROLS if c not in X.columns]
    if missing:
        raise RuntimeError(f"not built: {missing}")
    return X[["sid"] + CONTROLS]


if __name__ == "__main__":
    ANALYSIS.mkdir(exist_ok=True)
    X = build()
    out = ANALYSIS / "census_sector_controls_2002.csv"
    X.to_csv(out, index=False)
    print(f"\n{len(X)} sectors x {len(CONTROLS)} controls -> {out}")
    for name, cols in BLOCKS.items():
        print(f"  {name:32s} {len(cols):2d}")
    bad = X[CONTROLS].isna().sum()
    print("\nmissing cells:", int(bad.sum()), "" if bad.sum() == 0 else dict(bad[bad > 0]))
    print(X[CONTROLS].describe().T[["mean", "std", "min", "max"]].round(3).to_string())
