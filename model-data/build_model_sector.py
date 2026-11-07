"""build_model_sector.py -- sector-level inputs for the 2x2 tourism / land model.

    RWA_ROOT=<Rwanda - TRS folder> python model-data/build_model_sector.py

The geographic unit is the NISR administrative SECTOR (416), the finest unit at which
public labour data exist (Census 2002/2012/2022). Writes to Publicly-Available-NISR/Analysis/:

  model_sector_panel.csv      sector x census wave: population, labour by economic sector,
                              lambda (agriculture share of labour), in-migration shares,
                              land split from Dynamic World (2022 wave only; DW starts 2015)
  model_sector_cross.csv      sector cross-section: area, park exposure, land, OSM tourism
                              exposure (accommodation shares), centroid, distances
  model_sector_distances.csv  416 x 416 centroid distances (km), long format, for migration cost
  model_district_migration.csv  district-to-district flows (previous residence), 2012 and 2022

Model objects (see theory/TRS-2x2-model-derivation.pdf):
  lambda   = N_a / (N_a + N_s)       agriculture vs services (tertiary) workers aged 20-64;
             lambda_all uses all sectors in the denominator. 2022 uses the reconstructed
             subsistence count (n_AG_pt) from build_jobs_panel.py.
  L_a, L_s  land in agriculture and services, hectares. Preferred source ESA WorldCover 2021
             (10 m, one class per pixel): L_a = cropland, L_s = built-up; Open Buildings
             footprints as a second L_s. Dynamic World mean probabilities are kept only for
             reference: in Rwanda DW detects ~27% of cropland (Kerner et al. 2023), so it
             understates L_a and overstates built-up.
  k_a, k_s  land per worker, L_a/N_a and L_s/N_s (Census 2022). Model: k_a/k_s = c.
  ell       = L_a / (L_a + L_s); eps_L = (1 - ell)/(1 - lambda), model eq. (3).
  Lbar     = sector area net of protected area (geodata.rw park polygons).
  A_s      = OSM accommodation exposure: sector share of national accommodation points
             (and share excluding the City of Kigali, and a park-tourism variant).
  tau      = function of centroid distance; calibrated later against migration shares.
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd, pyreadstat, geopandas as gpd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import paths as P

AN = P.NISR / "Analysis"
WAVES = (2002, 2012, 2022)
ACCOM = {"hotel", "guest_house", "lodge", "hostel", "chalet", "camp_site", "motel",
         "apartment", "resort", "alpine_hut", "wilderness_hut"}

# ---- geography --------------------------------------------------------------
sec = gpd.read_file(next((P.NISR / "geodata-nisr").glob("Sector_Boundary_2022*.geojson")))
idcol = next(c for c in sec.columns if c.lower().replace(" ", "_") in ("sector_id", "sect_id", "sector_code"))
sec["sid"] = sec[idcol].astype(int)
sec = sec.dissolve("sid").reset_index().to_crs(32736)          # UTM 36S, metres
cen = sec.geometry.centroid
sec["cx_km"], sec["cy_km"] = cen.x / 1e3, cen.y / 1e3
cen_ll = gpd.GeoSeries(cen, crs=32736).to_crs(4326)
sec["lon"], sec["lat"] = cen_ll.x, cen_ll.y

park = pd.read_csv(P.GEO / "protected-areas/sectors_park_exposure_geodatarw.csv")
park = park.rename(columns={"sector_id": "sid"})
X = park[["sid", "province", "province_id", "district", "district_id", "sector", "unit_km2",
          "park_overlap_km2", "park_share", "dist_to_park_km", "nearest_park", "in_park",
          "border", "near_5km"]].merge(sec[["sid", "cx_km", "cy_km", "lon", "lat"]], on="sid", how="left")
X["Lbar_km2"] = X.unit_km2 - X.park_overlap_km2

kig = X.loc[X.district_id.isin([11, 12, 13]), ["cx_km", "cy_km"]].mean()
X["dist_kigali_km"] = np.hypot(X.cx_km - kig.cx_km, X.cy_km - kig.cy_km)

# ---- tourism exposure from OSM accommodation --------------------------------
o = pd.read_csv(P.GEO / "tourism/rwanda_tourism_osm.csv").dropna(subset=["sector_id"])
o["sid"] = o.sector_id.astype(int)
o["accom"] = o.category.isin(ACCOM)
o["park_accom"] = o.accom & (o.dist_to_park_km <= 10)            # nature-tourism lodging
t = o.groupby("sid").agg(osm_poi=("category", "size"), osm_accom=("accom", "sum"),
                         osm_park_accom=("park_accom", "sum")).reset_index()
X = X.merge(t, on="sid", how="left")
for c in ("osm_poi", "osm_accom", "osm_park_accom"):
    X[c] = X[c].fillna(0).astype(int)
X["As_share_nat"] = X.osm_accom / X.osm_accom.sum()
nk = X.province_id != 1
X["As_share_exKigali"] = np.where(nk, X.osm_accom / X.loc[nk, "osm_accom"].sum(), np.nan)
X["As_share_park"] = X.osm_park_accom / max(X.osm_park_accom.sum(), 1)
X["accom_per_km2"] = X.osm_accom / X.Lbar_km2

# ---- land split from Dynamic World (2015-2024) ------------------------------
dw = pd.read_csv(P.GEO / "land-cover/dw_by_sector_full.csv").rename(columns={"sector_id": "sid"})
dw = dw.merge(X[["sid", "park_share"]], on="sid")
dw["ell"] = dw.dw_crops / (dw.dw_crops + dw.dw_built)
dw["crop_share_nonpark"] = dw.dw_crops / (1 - dw.park_share).clip(lower=1e-6)
dw["built_share_nonpark"] = dw.dw_built / (1 - dw.park_share).clip(lower=1e-6)
dwc = dw[dw.year.between(2016, 2024)].groupby("sid")[["ell", "dw_crops", "dw_built", "dw_trees"]].mean()
X = X.merge(dwc.add_suffix("_dw1624").reset_index(), on="sid", how="left")

# ---- land in hectares: WorldCover (if extracted) and Open Buildings -----------
bld = pd.read_csv(P.GEO / "buildings/gob_buildings_by_sector.csv")[["sector_id", "building_area_m2"]]
X = X.merge(bld.rename(columns={"sector_id": "sid"}), on="sid", how="left")
X["Ls_buildings_ha"] = X.building_area_m2 / 1e4
WC = P.GEO / "land-cover/worldcover_by_sector.csv"
if WC.exists():
    wc = pd.read_csv(WC).rename(columns={"sector_id": "sid"})
    wc = wc[wc.year == 2021][["sid", "wc_cropland_ha", "wc_built_ha", "wc_tree_ha", "wc_grass_ha", "wc_shrub_ha"]]
    X = X.merge(wc, on="sid", how="left")
    print("WorldCover 2021 merged")
else:
    print("WorldCover not yet extracted: run data-build-scripts/gee_extract.py --datasets worldcover")

# ---- labour from the census jobs panel ---------------------------------------
j = pd.read_csv(AN / "census_sector_jobs_panel.csv")[
    ["sid", "wave", "adults", "n_AG", "n_AG_pt", "n_AG_hi", "n_MIN", "n_MAN", "n_TER"]]
j["N_a"] = np.where(j.wave == 2022, j.n_AG_pt, j.n_AG)
j["N_s"] = j.n_TER
j["lambda"] = j.N_a / (j.N_a + j.N_s)
j["lambda_all"] = j.N_a / (j.N_a + j.n_MIN + j.n_MAN + j.n_TER)
j["lambda_2022_recorded"] = np.where(j.wave == 2022, j.n_AG / (j.n_AG + j.N_s), np.nan)

# ---- population and in-migration from the census -----------------------------
d, _ = pyreadstat.read_dta(P.NISR / "Census-PHC/3_Final/Census_pooled_person.dta", usecols=[
    "census_wave", "census_sector", "census_district", "census_weight",
    "census_previous_residence_2012", "census_previous_district_2022",
    "census_residence_duration_2012", "census_residence_duration_2022"])
d["wave"] = d.census_wave.astype(str).astype(int)
d = d[d.wave.isin([2012, 2022])].copy()
d["sid"] = pd.to_numeric(d.census_sector, errors="coerce")
d["did"] = pd.to_numeric(d.census_district, errors="coerce")
d["w"] = d.census_weight.fillna(1.0)
prev = np.where(d.wave == 2012, pd.to_numeric(d.census_previous_residence_2012, errors="coerce"),
                pd.to_numeric(d.census_previous_district_2022, errors="coerce"))
dur = np.where(d.wave == 2012, pd.to_numeric(d.census_residence_duration_2012, errors="coerce"),
               pd.to_numeric(d.census_residence_duration_2022, errors="coerce"))
d["prev"] = prev
d["mover"] = pd.Series(prev).between(11, 57).values & (prev != d.did.values)   # other district
d["recent"] = d.mover & (pd.Series(dur).between(0, 5).values)                   # moved <=5 yrs ago
pop = d.groupby(["sid", "wave"]).apply(lambda q: pd.Series({
    "H_pop": q.w.sum(), "inmig_share": (q.w * q.mover).sum() / q.w.sum(),
    "inmig_recent5_share": (q.w * q.recent).sum() / q.w.sum()}), include_groups=False).reset_index()
flows = (d[d.mover].groupby(["wave", "prev", "did"]).w.sum().reset_index()
         .rename(columns={"prev": "origin_district", "did": "dest_district", "w": "movers"}))

# ---- assemble -----------------------------------------------------------------
Pn = j.merge(pop, on=["sid", "wave"], how="left")
dw22 = dw[dw.year == 2022][["sid", "ell", "dw_crops", "dw_built", "crop_share_nonpark", "built_share_nonpark"]]
Pn = Pn.merge(dw22.assign(wave=2022), on=["sid", "wave"], how="left")
Pn = Pn.merge(X[["sid", "district_id", "Lbar_km2", "border", "near_5km"]], on="sid", how="left")
Pn = Pn.rename(columns={"ell": "ell_dw", "dw_crops": "dw_crops_prob", "dw_built": "dw_built_prob"})
Pn = Pn.merge(X[["sid", "Ls_buildings_ha"] + [c for c in ("wc_cropland_ha", "wc_built_ha") if c in X]],
              on="sid", how="left")
if "wc_cropland_ha" in Pn:
    is22 = Pn.wave == 2022
    Pn.loc[~is22, ["wc_cropland_ha", "wc_built_ha", "Ls_buildings_ha"]] = np.nan   # 2021 land vs 2022 census only
    Pn["k_a_ha"] = Pn.wc_cropland_ha / Pn.N_a                    # cropland per farm worker
    Pn["k_s_ha"] = Pn.wc_built_ha / Pn.N_s                       # built-up per services worker
    Pn["k_s_bld_ha"] = Pn.Ls_buildings_ha / Pn.N_s               # building footprint per services worker
    Pn["c_hat"] = Pn.k_a_ha / Pn.k_s_ha                          # model: k_a/k_s = c
    Pn["ell"] = Pn.wc_cropland_ha / (Pn.wc_cropland_ha + Pn.wc_built_ha)
    Pn["eps_L"] = (1 - Pn.ell) / (1 - Pn["lambda"])              # land elasticity, model eq. (3)
Pn = Pn.sort_values(["sid", "wave"])

D = np.hypot(X.cx_km.values[:, None] - X.cx_km.values[None, :],
             X.cy_km.values[:, None] - X.cy_km.values[None, :])
ids = X.sid.values
dist = pd.DataFrame({"origin_sid": np.repeat(ids, len(ids)), "dest_sid": np.tile(ids, len(ids)),
                     "dist_km": D.ravel()})

Pn.to_csv(AN / "model_sector_panel.csv", index=False)
X.to_csv(AN / "model_sector_cross.csv", index=False)
dist.to_csv(AN / "model_sector_distances.csv", index=False)
flows.to_csv(AN / "model_district_migration.csv", index=False)
print("panel", Pn.shape, "cross", X.shape, "dist", dist.shape, "flows", flows.shape)
