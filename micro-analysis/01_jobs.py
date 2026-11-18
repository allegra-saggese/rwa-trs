"""Jobs: Census 2002/2012/2022 sector-level employment by tradable/non-tradable services,
LFS 2017-2025 annual national trends, park-distance gradients.
Workers aged 20-64, Census weights. 2022 agriculture = reconstructed count (n_AG_pt) from
model_sector_panel.csv because the 2022 Census follows the 19th ICLS and records most
own-use farmers as not employed (recorded ISIC A falls 2.80M -> 1.69M)."""
import os, numpy as np, pandas as pd, matplotlib.pyplot as plt
from _common import *

cs = pd.read_parquet(os.path.expanduser("~/census_sub.parquet"),
                     columns=["census_year", "census_sector", "census_age", "census_weight", "census_industry_isic"])
cs = cs[cs.census_industry_isic.notna() & cs.census_age.between(20, 64)]
cs["sec"] = cs.census_industry_isic.astype(int).map(SEC)
cs["grp"] = cs.sec.map(GROUP)
cs["broad"] = (~cs.sec.isin(BROAD_EXCL) & cs.grp.str.startswith("S")).astype(int)

g = cs.pivot_table(index=["census_sector", "census_year"], columns="grp", values="census_weight", aggfunc="sum", fill_value=0)
g["S_broad"] = cs[cs.broad == 1].groupby(["census_sector", "census_year"]).census_weight.sum()
sec_detail = cs.pivot_table(index=["census_sector", "census_year"], columns="sec", values="census_weight", aggfunc="sum", fill_value=0).add_prefix("n_")
g = g.join(sec_detail).fillna(0).reset_index().rename(columns={"census_sector": "sid", "census_year": "wave"})

panel = pd.read_csv(ANA / "model_sector_panel.csv")
cross = pd.read_csv(ANA / "model_sector_cross.csv")
g = g.merge(panel[["sid", "wave", "adults", "n_AG_pt", "H_pop", "inmig_share", "inmig_recent5_share"]], on=["sid", "wave"], how="left")
g["AG_recorded"] = g["AG"]
g.loc[g.wave == 2022, "AG"] = g.loc[g.wave == 2022, "n_AG_pt"]
S = ["S_tour", "S_bus", "S_loc"]
g["S_all"] = g[S].sum(1)
g["workers"] = g[["AG", "IND"] + S].sum(1)
for c in ["AG", "IND", "S_all", "S_tour", "S_bus", "S_loc", "S_broad"]:
    g["sh_" + c] = g[c] / g.workers
g["lambda_model"] = g.AG / (g.AG + g.S_broad)          # model 2x2: agriculture vs (fallback) services
g["lambda_tour"] = g.AG / (g.AG + g.S_tour)
g = g.merge(cross[["sid", "district", "district_id", "province_id", "border", "dist_to_park_km", "nearest_park"]], on="sid")
g["band"] = band(g)
g.to_csv(OUT_D / "sector_jobs_panel.csv", index=False)
print("sectors per wave", g.groupby("wave").sid.nunique().to_dict())

# ---------- T1: national composition ----------
nat = g.groupby("wave")[["AG", "AG_recorded", "IND", "S_tour", "S_bus", "S_loc", "S_broad", "workers"]].sum()
t1 = pd.concat({"Workers (000s)": (nat / 1e3).T,
                "Share of workers": nat[["AG", "IND", "S_tour", "S_bus", "S_loc", "S_broad"]].div(nat.workers, axis=0).T})
t1 = t1.rename(index={"AG": "Agriculture", "AG_recorded": "Agriculture (recorded)", "IND": "Industry",
                      "S_tour": "Tourism services (I,R)", "S_bus": "Business services (J,K,M)",
                      "S_loc": "Local services (G,H,L,N-Q,S-U)", "S_broad": "Services excl. trade, govt", "workers": "Total"})
t1.columns = t1.columns.astype(str)
to_tex(t1, OUT_T / "jobs_national_census", "Employment by sector, Census, ages 20--64. 2022 agriculture is the reconstructed own-use-inclusive count; recorded count shown separately.", "tab:jobs_nat", "{:,.3f}")

# detailed section table (national, 000s)
det = g.groupby("wave")[[f"n_{s}" for s in SEC.values() if f"n_{s}" in g]].sum().T / 1e3
det.index = det.index.str[2:]
det["group"] = det.index.map(GROUP)
det["growth_2012_22"] = det[2022] / det[2012] - 1
det.columns = det.columns.astype(str)
det.to_csv(OUT_T / "jobs_isic_sections_census.csv")

# ---------- T2: by park-distance band ----------
bw = g.groupby(["band", "wave"], observed=True)[["AG", "IND", "S_tour", "S_bus", "S_loc", "S_broad", "workers", "H_pop"]].sum()
t2 = bw[["AG", "S_tour", "S_broad"]].div(bw.workers, axis=0)
t2["workers (000s)"] = bw.workers / 1e3
t2["n_sectors"] = g.groupby(["band", "wave"], observed=True).sid.nunique()
inm = g.groupby(["band", "wave"], observed=True)[["inmig_share","workers"]].apply(lambda d: np.average(d.inmig_share, weights=d.workers) if d.inmig_share.notna().any() else np.nan)
t2["in-migrant share"] = inm
t2.columns = ["Agriculture share", "Tourism-services share", "Services excl. G,O share", "Workers (000s)", "Sectors", "In-migrant share"]
to_tex(t2, OUT_T / "jobs_by_park_band", "Employment shares by distance to the nearest national park, Census waves.", "tab:jobs_band")

# change 2012 -> 2022 sector-level (unweighted mean and sd), by band
w = g.pivot_table(index=["sid", "band"], columns="wave", values=["sh_AG", "sh_S_tour", "sh_S_broad", "workers"], observed=True)
d = pd.DataFrame({"d_sh_AG": w["sh_AG"][2022] - w["sh_AG"][2012],
                  "d_sh_S_tour": w["sh_S_tour"][2022] - w["sh_S_tour"][2012],
                  "d_sh_S_broad": w["sh_S_broad"][2022] - w["sh_S_broad"][2012],
                  "dlog_workers": np.log(w["workers"][2022] / w["workers"][2012]),
                  "d_sh_AG_0212": w["sh_AG"][2012] - w["sh_AG"][2002]}).reset_index()
d = d.merge(cross[["sid", "dist_to_park_km", "province_id"]], on="sid")
d.to_csv(OUT_D / "sector_jobs_changes.csv", index=False)
t3 = d.groupby("band", observed=True)[["d_sh_AG_0212", "d_sh_AG", "d_sh_S_tour", "d_sh_S_broad", "dlog_workers"]].agg(["mean", "std"])
t3.columns = [f"{a} {b}" for a, b in t3.columns]
to_tex(t3, OUT_T / "jobs_changes_by_band", "Sector-level changes in employment shares and log workers, by park-distance band (unweighted across sectors).", "tab:jobs_chg")

# ---------- LFS annual ----------
lfs = pd.read_csv(DATA / "geo-data" / "labour" / "lfs_district_isic.csv")
lfs["grp"] = lfs.isic.astype(int).map(SEC).map(GROUP)
ly = lfs.pivot_table(index="year", columns="grp", values="workers", aggfunc="sum")
ly_sh = ly.div(ly.sum(1), axis=0)
ly_sh.to_csv(OUT_T / "jobs_lfs_national_shares.csv")

# ---------- figures ----------
fig, ax = plt.subplots(1, 2, figsize=(8.2, 3.2))
cen = nat[["AG", "IND", "S_tour", "S_bus", "S_loc"]].div(nat.workers, axis=0)
lab = {"AG": "Agriculture", "IND": "Industry", "S_tour": "Tourism svc", "S_bus": "Business svc", "S_loc": "Local svc"}
for i, c in enumerate(lab):
    ax[0].plot(cen.index, cen[c], marker="o", ms=4, color=PAL[i], label=lab[c])
    ax[0].annotate(lab[c], (2022, cen[c].iloc[-1]), xytext=(4, 0), textcoords="offset points", va="center", fontsize=7, color="#333")
ax[0].plot([2022], [nat.AG_recorded[2022] / nat.workers[2022]], marker="x", color=PAL[0], ls="none")
ax[0].annotate("recorded", (2022, nat.AG_recorded[2022] / nat.workers[2022]), xytext=(-40, -2), textcoords="offset points", fontsize=7, color="#333")
ax[0].set_xticks([2002, 2012, 2022]); ax[0].set_xlim(2000, 2028); ax[0].set_title("Census, share of workers 20-64", loc="left", fontsize=9)
for i, c in enumerate(lab):
    if c in ly_sh: ax[1].plot(ly_sh.index, ly_sh[c], marker="o", ms=3, color=PAL[i], label=lab[c])
ax[1].axvspan(2019.6, 2021.4, color="#eee", zorder=0); ax[1].text(2020.5, ax[1].get_ylim()[1] * 0.95, "COVID", ha="center", fontsize=7, color="#666")
ax[1].set_title("LFS, share of employed (recorded)", loc="left", fontsize=9); ax[1].legend(fontsize=7, frameon=False, ncol=2)
for a in ax: a.set_yscale("log"); a.set_yticks([0.01, 0.03, 0.1, 0.3, 0.9]); a.set_yticklabels(["1%", "3%", "10%", "30%", "90%"])
fig.tight_layout(); fig.savefig(OUT_F / "jobs_national_trend.png"); plt.close(fig)

fig, ax = plt.subplots(1, 3, figsize=(9, 3))
for j, (c, ttl) in enumerate([("AG", "Agriculture share"), ("S_tour", "Tourism-services share"), ("S_broad", "Services excl. G,O share")]):
    sh = (bw[c] / bw.workers).unstack("band")
    for i, b in enumerate(sh.columns):
        ax[j].plot(sh.index, sh[b], marker="o", ms=3, color=PAL[i], label=b)
    ax[j].set_xticks([2002, 2012, 2022]); ax[j].set_title(ttl, loc="left", fontsize=9)
ax[0].legend(fontsize=7, frameon=False)
fig.tight_layout(); fig.savefig(OUT_F / "jobs_by_park_band.png"); plt.close(fig)

# binned scatter of 2012-22 changes on distance (excl. Kigali)
dd = d[d.province_id != 1].copy(); dd["bin"] = pd.qcut(dd.dist_to_park_km.rank(method="first"), 20, labels=False)
bs = dd.groupby("bin").agg(x=("dist_to_park_km", "mean"), ag=("d_sh_AG", "mean"), tour=("d_sh_S_tour", "mean"), wk=("dlog_workers", "mean"))
fig, ax = plt.subplots(1, 3, figsize=(9, 2.9))
for a, (c, t) in zip(ax, [("ag", "Change in agriculture share"), ("tour", "Change in tourism-svc share"), ("wk", "Change in log workers")]):
    a.scatter(bs.x, bs[c], s=18, color=PAL[0]); b1 = np.polyfit(dd.dist_to_park_km, dd[{"ag": "d_sh_AG", "tour": "d_sh_S_tour", "wk": "dlog_workers"}[c]], 1)
    xs = np.linspace(0, dd.dist_to_park_km.max(), 10); a.plot(xs, np.polyval(b1, xs), color=PAL[1], lw=1.5)
    a.set_title(t + ", 2012-22", loc="left", fontsize=8.5); a.set_xlabel("km to nearest park")
fig.tight_layout(); fig.savefig(OUT_F / "jobs_change_distance_binscatter.png"); plt.close(fig)

print(t1.round(3).to_string()); print(t2.round(3).to_string()); print(t3.round(3).to_string()); print(ly_sh.round(3).to_string())
print(det.round(1).to_string())
