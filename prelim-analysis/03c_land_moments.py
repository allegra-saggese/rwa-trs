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
from _common import *

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
