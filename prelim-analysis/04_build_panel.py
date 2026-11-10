"""One sector panel for all descriptives, on the repo's treatment groups (00_treatment_groups.py).
 jobs  : Census 2002/2012/2022 (01_jobs.py), workers 20-64; 2022 agriculture reconstructed
 land  : GLCLU 2000/2005/2010/2015/2020, outside parks; Census waves matched to 2000/2010/2020
 ntl   : Chen et al. VIIRS-like sum (calibrated across sensors), asinh, Census waves matched to 2002/2012/2022
Shares of land use 'usable' land outside parks = crop + built + tree + other (water excluded).
ell = crop / (crop + built), the model's two-use land share.
Writes Analysis/prelim/sector_panel_desc.csv (sector x wave) and sector_cropland_builtup_glclu.csv (sector x year)."""
import numpy as np, pandas as pd
from _common import *

tg = pd.read_csv(OUT_D / "treatment_groups.csv")
cross = pd.read_csv(ANA / "model_sector_cross.csv")[["sid", "district_id", "province_id", "Lbar_km2", "dist_to_park_km", "dist_kigali_km"]]
tg = tg.merge(cross, on="sid")
tg["urban"] = tg.group.isin(["Kigali", "Towns"]).astype(int)

# ---------- land, sector x year ----------
gl = pd.read_csv(OUT_D / "sector_landcover_glclu.csv").rename(columns={"sector_id": "sid"})
for c in ["crop", "built", "tree", "other", "water"]:
    gl[c] = gl[f"{c}_out_ha"]
gl["usable"] = gl[["crop", "built", "tree", "other"]].sum(1)
for c in ["crop", "built", "tree", "other"]:
    gl[f"{c}_sh"] = gl[c] / gl.usable
gl["ell"] = gl.crop / (gl.crop + gl.built)
land = gl[["sid", "year", "crop", "built", "tree", "other", "water", "usable", "crop_sh", "built_sh", "tree_sh", "other_sh", "ell"]]
wc = pd.read_csv(OUT_D / "sector_landcover_worldcover2021.csv").rename(columns={"sector_id": "sid"})
wc["usable_wc"] = wc[["crop_out_ha", "built_out_ha", "tree_out_ha", "other_out_ha", "shrub_grass_out_ha", "wetland_out_ha"]].sum(1)
wc = pd.DataFrame({"sid": wc.sid, "wc_crop_sh": wc.crop_out_ha / wc.usable_wc, "wc_built_sh": wc.built_out_ha / wc.usable_wc,
                   "wc_ell": wc.crop_out_ha / (wc.crop_out_ha + wc.built_out_ha), "wc_crop_ha": wc.crop_out_ha, "wc_built_ha": wc.built_out_ha})
cb = tg[["sid", "sector", "district", "group", "park", "treated_any", "control", "urban"]].merge(land, on="sid").merge(wc, on="sid", how="left")
cb.to_csv(OUT_D / "sector_cropland_builtup_glclu.csv", index=False)

# ---------- nightlights ----------
nl = pd.read_csv(DATA / "Nighttime-Lights" / "3_Final" / "Nightlights_pooled_sector.csv",
                 usecols=["ntl_sector_id", "ntl_year", "ntl_chen_sum", "ntl_chen_asinh", "ntl_li_sum", "ntl_li_asinh"]).rename(columns={"ntl_sector_id": "sid", "ntl_year": "year"})
nl.to_csv(OUT_D / "sector_ntl.csv", index=False)

# ---------- jobs x land x ntl, sector x wave ----------
jobs = pd.read_csv(OUT_D / "sector_jobs_panel.csv").drop(columns=["band", "district", "district_id", "province_id", "border", "dist_to_park_km", "nearest_park"], errors="ignore")
d = tg.merge(jobs, on="sid")
d = d.merge(land.assign(wave=land.year.map({2000: 2002, 2010: 2012, 2020: 2022})).dropna(subset=["wave"]).drop(columns="year"), on=["sid", "wave"], how="left")
d = d.merge(nl[["sid", "year", "ntl_chen_asinh", "ntl_li_asinh"]].rename(columns={"year": "wave"}), on=["sid", "wave"], how="left")
d["lam"] = d.AG / (d.AG + d.S_broad)                     # model lambda, services = all tertiary excl. G and O
d["sh_tour"] = d.S_tour / d.workers
d["sh_svc"] = d.S_broad / d.workers
d["sh_ag"] = d.AG / d.workers
d["density"] = d.workers / (d.usable / 100)              # workers per km2 of usable land
d["k_a"] = d.crop / d.AG
d["k_s"] = d.built / d.S_broad.replace(0, np.nan)
d["c"] = d.k_a / d.k_s
d["eps_model"] = (1 - d.ell) / (1 - d.lam)
d["log_workers"] = np.log(d.workers)
d.to_csv(OUT_D / "sector_panel_desc.csv", index=False)
print(d.groupby(["group", "wave"]).sid.nunique().unstack())
print(d[["lam", "ell", "sh_tour", "k_a", "k_s", "c", "ntl_chen_asinh"]].describe().round(3).T)
