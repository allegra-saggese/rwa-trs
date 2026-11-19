"""Inputs of the 2x2 model: the sector model panel and the land moments.

Run order: section model_panel first (micro-analysis/sector_panel.py reads its output), then
micro-analysis/sector_panel.py, then section land_moments (it reads the jobs and land-cover panels).

Run every section in order:   python model/model_inputs.py
Run some sections:            python model/model_inputs.py --only <name> [<name> ...]
List the sections:            python model/model_inputs.py --list

Sections, in run order:
  model_panel            (was build_model_sector.py) build_model_sector.py -- sector-level inputs for the 2x2 tourism / land model.
  land_moments           (was 03c_land_moments.py) Land moments for the 2x2 model, merged with Census jobs.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
from common import *  # noqa: F401,F403  paths, ISIC groups, figure/table names, LaTeX tables (helpers/common.py)


def section_model_panel():
    """build_model_sector.py -- sector-level inputs for the 2x2 tourism / land model.

    RWA_ROOT=<Rwanda - TRS folder> python model/build_model_sector.py

The geographic unit is the NISR administrative SECTOR (416), the finest unit at which
public labour data exist (Census 2002/2012/2022). Writes to data/harmonized/:

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

    AN = P.HARMONIZED
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


def section_land_moments():
    """Land moments for the 2x2 model, merged with Census jobs.
Census 2002/2012/2022 matched to GLCLU 2000/2010/2020. WorldCover 2021 is matched to Census 2022 for levels.
 ell     = L_a / (L_a + L_s), cropland over cropland + built-up (the model's two land uses), outside parks
 crop_sh = cropland / usable land outside parks (all classes)
 k_a     = cropland ha per agricultural worker;  k_s = built-up ha per services worker (services excl. G,O)
 c       = k_a / k_s  (model eq. 6, technology only; expected > 1)
 eps_L   = d ln L_a / d ln N_a (eq. 11): empirical long-difference slope vs model-implied (1-ell)/(1-lambda)
Built-up land includes housing for all workers, not only services premises, so k_s is an upper bound
and c a lower bound on the model object."""
    import numpy as np, pandas as pd, matplotlib.pyplot as plt
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))

    gl = pd.read_csv(OUT_D / "sector_landcover_glclu.csv")
    wc = pd.read_csv(OUT_D / "sector_landcover_worldcover2021.csv")
    jobs = pd.read_csv(OUT_D / "sector_jobs_panel.csv")
    gl["wave"] = gl.year.map({2000: 2002, 2010: 2012, 2020: 2022})
    usable = [c for c in gl.columns if c.endswith("_out_ha") and not c.startswith(("water", "nodata"))]
    gl["usable_ha"] = gl[usable].sum(1)
    d = jobs.merge(gl[["sector_id", "wave", "crop_out_ha", "built_out_ha", "tree_out_ha", "usable_ha"]], left_on=["sid", "wave"], right_on=["sector_id", "wave"])
    d["ell"] = d.crop_out_ha / (d.crop_out_ha + d.built_out_ha)
    d["crop_sh"] = d.crop_out_ha / d.usable_ha
    d["built_sh"] = d.built_out_ha / d.usable_ha
    d["tree_sh"] = d.tree_out_ha / d.usable_ha
    d["lam"] = d.lambda_model
    d["k_a"] = d.crop_out_ha / d.AG
    d["k_s"] = d.built_out_ha / d.S_broad.replace(0, np.nan)
    d["c"] = d.k_a / d.k_s
    d["eps_model"] = (1 - d.ell) / (1 - d.lam)
    d.to_csv(OUT_D / "sector_land_jobs_panel.csv", index=False)

    # WorldCover 2021 levels with Census 2022
    w = jobs[jobs.wave == 2022].merge(wc, left_on="sid", right_on="sector_id")
    w["usable_ha"] = w[["crop_out_ha", "built_out_ha", "tree_out_ha", "other_out_ha", "shrub_grass_out_ha", "wetland_out_ha"]].sum(1)
    w["ell"] = w.crop_out_ha / (w.crop_out_ha + w.built_out_ha)
    w["crop_sh"] = w.crop_out_ha / w.usable_ha
    w["k_a"] = w.crop_out_ha / w.AG
    w["k_s"] = w.built_out_ha / w.S_broad.replace(0, np.nan)
    w["c"] = w.k_a / w.k_s
    w["eps_model"] = (1 - w.ell) / (1 - w.lambda_model)
    pan = pd.read_csv(ANA / "model_sector_panel.csv").query("wave==2022")[["sid", "Ls_buildings_ha"]]
    w = w.merge(pan, on="sid", how="left")
    w["k_s_bldg"] = w.Ls_buildings_ha / w.S_broad.replace(0, np.nan)
    w["c_bldg"] = w.k_a / w.k_s_bldg
    w.to_csv(OUT_D / "sector_land_jobs_wc2021.csv", index=False)

    def summ(df, cols):
        return df[cols].describe(percentiles=[.1, .5, .9]).T[["mean", "10%", "50%", "90%"]]
    cols = ["lam", "ell", "crop_sh", "built_sh", "tree_sh", "k_a", "k_s", "c", "eps_model"]
    lab = {"lam": "lambda (ag share of workers, ag+svc)", "ell": "ell (crop / crop+built)", "crop_sh": "Cropland share of usable land",
           "built_sh": "Built-up share of usable land", "tree_sh": "Tree-cover share of usable land", "k_a": "k_a: crop ha per farm worker",
           "k_s": "k_s: built ha per services worker", "c": "c = k_a/k_s", "eps_model": "eps_L implied (1-ell)/(1-lambda)",
           "k_s_bldg": "k_s: building footprint ha per services worker", "c_bldg": "c using building footprints"}
    t = pd.concat({str(wv): summ(d[(d.wave == wv) & (d.province_id != 1)], cols) for wv in [2002, 2012, 2022]})
    t = t.rename(index=lab)
    to_tex(t, OUT_T / "land_moments_glclu", "Land moments by Census wave, GLCLU land cover, sectors outside Kigali (unweighted across sectors).", "tab:land_glclu")
    w2 = w[w.province_id != 1].copy()
    tw = summ(w2, ["ell", "crop_sh", "k_a", "k_s", "c", "k_s_bldg", "c_bldg", "eps_model"]).rename(index=lab)
    to_tex(tw, OUT_T / "land_moments_worldcover", "Land moments, WorldCover 2021 with Census 2022, sectors outside Kigali.", "tab:land_wc")

    # by park band
    bb = d.groupby(["band", "wave"], observed=True)[["crop_out_ha", "built_out_ha", "tree_out_ha", "usable_ha", "AG", "S_broad"]].sum()
    tb = pd.DataFrame({"Cropland share": bb.crop_out_ha / bb.usable_ha, "Built-up share": bb.built_out_ha / bb.usable_ha,
                       "Tree share": bb.tree_out_ha / bb.usable_ha, "ell": bb.crop_out_ha / (bb.crop_out_ha + bb.built_out_ha),
                       "k_a (ha/worker)": bb.crop_out_ha / bb.AG, "k_s (ha/worker)": bb.built_out_ha / bb.S_broad})
    tb["c"] = tb["k_a (ha/worker)"] / tb["k_s (ha/worker)"]
    to_tex(tb, OUT_T / "land_by_park_band", "Land use by park-distance band, GLCLU matched to Census waves (aggregated within band).", "tab:land_band")

    # empirical land elasticity: long differences, outside Kigali, sectors with positive crop and ag workers
    import statsmodels.formula.api as smf
    L = d.pivot_table(index=["sid", "district_id", "band"], columns="wave", values=["crop_out_ha", "AG", "workers", "ell", "lam", "built_out_ha", "S_broad"], observed=True)
    res = []
    for a, b in [(2002, 2012), (2012, 2022), (2002, 2022)]:
        x = pd.DataFrame({"dlnLa": np.log(L.crop_out_ha[b] / L.crop_out_ha[a]), "dlnNa": np.log(L.AG[b] / L.AG[a]),
                          "dlnH": np.log(L.workers[b] / L.workers[a]), "dlnLs": np.log(L.built_out_ha[b] / L.built_out_ha[a]),
                          "dlnNs": np.log(L.S_broad[b] / L.S_broad[a]),
                          "eps_model": ((1 - L.ell[a]) / (1 - L.lam[a]))}).reset_index()
        x = x[np.isfinite(x[["dlnLa", "dlnNa", "dlnLs", "dlnNs"]]).all(1) & (x.district_id > 13)]
        for spec, f in [("raw", "dlnLa ~ dlnNa"), ("district FE", "dlnLa ~ dlnNa + C(district_id)"), ("district FE + dlnH", "dlnLa ~ dlnNa + dlnH + C(district_id)")]:
            m = smf.ols(f, x).fit(cov_type="cluster", cov_kwds={"groups": x.district_id})
            res.append(dict(period=f"{a}-{b}", spec=spec, outcome="ln cropland", beta=m.params["dlnNa"], se=m.bse["dlnNa"], n=int(m.nobs), eps_model_median=x.eps_model.median()))
        m = smf.ols("dlnLs ~ dlnNs + C(district_id)", x).fit(cov_type="cluster", cov_kwds={"groups": x.district_id})
        res.append(dict(period=f"{a}-{b}", spec="district FE", outcome="ln built-up on ln svc workers", beta=m.params["dlnNs"], se=m.bse["dlnNs"], n=int(m.nobs), eps_model_median=np.nan))
        if (a, b) == (2012, 2022): x12 = x
    er = pd.DataFrame(res).set_index(["period", "outcome", "spec"])
    to_tex(er, OUT_T / "land_elasticity", "Long-difference elasticity of land on labor by sector, sectors outside Kigali, SEs clustered by district. Model benchmark: eps_L = (1-ell)/(1-lambda) at the start of the period.", "tab:epsL")

    # ---------- figures ----------
    fig, ax = plt.subplots(1, 3, figsize=(9, 3))
    for j, (c, ttl) in enumerate([("Cropland share", "Cropland share of usable land"), ("Built-up share", "Built-up share"), ("Tree share", "Tree-cover share")]):
        s = tb[c].unstack("band")[["Park border", "0-10 km", "10-30 km", ">30 km", "Kigali"]]
        for i, b in enumerate(s.columns): ax[j].plot(s.index, s[b], marker="o", ms=3, color=PAL[i], label=b)
        ax[j].set_xticks([2002, 2012, 2022]); ax[j].set_xticklabels(["2000", "2010", "2020"]); ax[j].set_title(ttl + " (GLCLU)", loc="left", fontsize=8.5)
    ax[0].legend(fontsize=7, frameon=False); fig.tight_layout(); fig.savefig(OUT_F / "land_by_park_band.png"); plt.close(fig)

    fig, ax = plt.subplots(1, 2, figsize=(8, 3.2))
    x = x12.copy(); x["bin"] = pd.qcut(x.dlnNa.rank(method="first"), 20, labels=False)
    bs = x.groupby("bin")[["dlnNa", "dlnLa"]].mean()
    ax[0].scatter(bs.dlnNa, bs.dlnLa, s=18, color=PAL[0]); b1 = np.polyfit(x.dlnNa, x.dlnLa, 1); xs = np.linspace(x.dlnNa.quantile(.02), x.dlnNa.quantile(.98), 10)
    ax[0].plot(xs, np.polyval(b1, xs), color=PAL[1], lw=1.5); ax[0].set_xlabel("d ln farm workers, 2012-22"); ax[0].set_ylabel("d ln cropland, 2010-20")
    ax[0].set_title(f"Land follows labor? slope {b1[0]:.2f}", loc="left", fontsize=9)
    ww = w2[(w2.c > 0) & np.isfinite(w2.c)]
    ax[1].hist(np.log10(ww.c), bins=30, color=PAL[0], alpha=.85); ax[1].axvline(0, color="#333", lw=1, ls="--")
    ax[1].set_xlabel("log10 c = k_a / k_s (WorldCover 2021, Census 2022)"); ax[1].set_title(f"c > 1 in {(ww.c > 1).mean():.0%} of sectors (median {ww.c.median():.1f})", loc="left", fontsize=9)
    fig.tight_layout(); fig.savefig(OUT_F / "land_elasticity_and_c.png"); plt.close(fig)

    pd.set_option("display.width", 200)
    print(t.round(3).to_string()); print(tw.round(3).to_string()); print(tb.round(3).to_string()); print(er.round(3).to_string())

SECTIONS = {
    "model_panel": section_model_panel,
    "land_moments": section_land_moments,
}


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", nargs="+", choices=list(SECTIONS), help="run only these sections, in run order")
    ap.add_argument("--list", action="store_true", help="list the sections and exit")
    a = ap.parse_args(argv)
    if a.list:
        print("\n".join(SECTIONS)); return
    for name, fn in SECTIONS.items():
        if a.only and name not in a.only:
            continue
        print(f"\n==== {name}", flush=True)
        fn()


if __name__ == "__main__":
    main()
