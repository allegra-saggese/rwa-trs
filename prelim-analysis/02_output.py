"""Output over time, by economic sector and location.
 (a) Agriculture: SAS 2019-2025, district x year. Quantity in kg; value at fixed prices
     (crop-specific median RWF/kg selling price, pooled 2018-2024), so changes are real.
     2017-2018 are dropped: their weights sum to about half the crop area of 2019+ (1.15M vs 2.1M ha),
     a harmonization break, not a real change. Area = crop area, else harvested area; 2021 and 2024
     report neither, so value per ha is missing in those years.
 (b) Services: Establishment Census turnover by ISIC group, district x {2014,2017,2020,2023}
     (public 2017+ files have no sub-district code). Turnover is reported in nominal brackets; we impute
     midpoints (top bracket >50M RWF set to 100M; 2023 brackets 5-7 collapsed to >50M for comparability)
     and deflate by CPI (WDI) to 2014 RWF. Inflation moves firms up fixed nominal brackets, so the real
     series is coarse.
 (c) Local activity: nightlights (intercalibrated DMSP/VIIRS, settled pixels), sector x year.
 (d) National tourism: park visitors by park, park and total tourism revenue.
Measurement is rough by construction; these are descriptive moments, not value added."""
import os, numpy as np, pandas as pd, matplotlib.pyplot as plt
from _common import *

cross = pd.read_csv(ANA / "model_sector_cross.csv")
cross["band"] = band(cross)
# district-level park exposure: share of district land in sectors on a park border
dexp = cross.groupby("district_id").apply(lambda d: np.average(d.border, weights=d.unit_km2), include_groups=False).rename("border_land_share")
dname = cross.groupby("district_id").district.first()
dgrp = pd.Series(np.where(dexp > 0, "Park-border district", "No park border"), index=dexp.index)
dgrp[cross.groupby("district_id").province_id.first() == 1] = "Kigali"
dgrp = dgrp.rename("park_group")

# ---------------- (a) agriculture ----------------
sas = pd.read_parquet(os.path.expanduser("~/sas_sub.parquet"))
sas = sas[sas.sas_year >= 2019]
sas["price"] = sas.sas_selling_price_2018_2022.fillna(sas.sas_selling_price_2023_2025)
pr = sas[(sas.price > 0) & sas.sas_year.between(2018, 2024)].groupby("sas_crop_name").price.median().rename("p_fix")
sas = sas.merge(pr, left_on="sas_crop_name", right_index=True, how="left")
sas["q"] = sas.sas_production_kg * sas.sas_weight
sas["v"] = sas.q * sas.p_fix
sas["ha"] = sas.sas_crop_area_ha.fillna(sas.sas_harvested_area_ha) * sas.sas_weight
has_area = sas.groupby("sas_year").apply(lambda d: d.ha.notna().mean() > 0.8, include_groups=False)
cover = sas.groupby("sas_year").apply(lambda d: d.v.notna().mul(d.q).sum() / d.q.sum(), include_groups=False)
print("share of kg with a fixed price:", cover.round(3).to_dict())
ag = sas.groupby(["sas_year", "sas_district"])[["q", "v", "ha"]].sum().reset_index().rename(columns={"sas_year": "year", "sas_district": "district_id"})
ag = ag.merge(dgrp, left_on="district_id", right_index=True, how="left").merge(dname, left_on="district_id", right_index=True, how="left")
ag.loc[~ag.year.map(has_area).astype(bool), "ha"] = np.nan
ag["v_per_ha"] = ag.v / ag.ha
ag.to_csv(OUT_D / "district_ag_output.csv", index=False)
agn = ag.groupby("year")[["q", "v", "ha"]].sum()
agn.loc[~has_area.reindex(agn.index).values, "ha"] = np.nan
agn["v_per_ha"] = agn.v / agn.ha
agn_t = pd.DataFrame({"Production (000 t)": agn.q / 1e6, "Value, fixed prices (bn RWF)": agn.v / 1e9,
                      "Crop area (000 ha, all seasons)": agn.ha / 1e3, "Value per ha (000 RWF)": agn.v_per_ha / 1e3})
to_tex(agn_t, OUT_T / "output_ag_national", "Crop output, Seasonal Agricultural Survey (seasons A+B+C), national.", "tab:ag_nat", "{:,.1f}")
crop = sas.groupby(["sas_year", "sas_crop_name"]).q.sum().unstack(0) / 1e6
crop = crop.loc[crop.sum(1).sort_values(ascending=False).index[:10]]
crop.columns = crop.columns.astype(str)
crop.to_csv(OUT_T / "output_ag_top_crops_kt.csv")

# ---------------- (b) services turnover ----------------
ec = pd.read_parquet(os.path.expanduser("~/ec_sub.parquet"))
ec["sec_n"] = ec.ec_main_activity_section.fillna(ec.ec_isic_section_comparable_2011)
lw = pd.read_csv(DATA / "geo-data" / "labour" / "ec_establishments_long.csv", usecols=["year", "isic"])  # 2014 section
ec.loc[ec.ec_year == 2014, "sec_n"] = lw.loc[lw.year == 2014, "isic"].values
ec["grp"] = ec.sec_n.where(ec.sec_n.between(1, 21)).map(SEC).map(GROUP)
br = ec.ec_annual_turnover_2014.fillna(ec.ec_annual_turnover_2017_2020).fillna(ec.ec_annual_total_turnover_2023)
br = br.where(br.between(1, 7)).clip(upper=5)  # 9 = not stated; 2023 brackets 5-7 -> >50M
MID = {1: 0.15e6, 2: 6.15e6, 3: 16e6, 4: 35e6, 5: 100e6}
ec["bracket"] = br
ec["turn"] = br.map(MID)
print("bracket distribution:"); print(ec.groupby("ec_year").bracket.value_counts(normalize=True).unstack().round(3))
ec["emp"] = ec.ec_total_workers.fillna(ec.ec_total_workers_2014).fillna(ec.ec_total_workers_2011)
cpi = pd.read_csv(DATA / "Tourism Data" / "world_bank_wdi.csv").query("country=='RWA' and indicator_code=='FP.CPI.TOTL'").set_index("year").value
last = cpi.dropna().index.max()
print("CPI last year", last)
ec["defl"] = ec.ec_year.map(lambda y: cpi.get(min(y, last)) / cpi[2014])
ec["turn_r"] = ec.turn / ec.defl
ec["has_turn"] = ec.turn.notna()
ec["emp_rep"] = ec.emp.where(ec.has_turn)
sv = ec.groupby(["ec_year", "ec_district", "grp"]).agg(turnover=("turn_r", "sum"), emp=("emp", "sum"), emp_rep=("emp_rep", "sum"), est=("emp", "size"),
                                                     turn_cov=("has_turn", "mean")).reset_index()
sv = sv.rename(columns={"ec_year": "year", "ec_district": "district_id"}).merge(dgrp, left_on="district_id", right_index=True, how="left")
sv.to_csv(OUT_D / "district_ec_output.csv", index=False)
svn = sv.groupby(["year", "grp"])[["turnover", "emp", "emp_rep", "est"]].sum().unstack("grp")
svt = pd.concat({"Real turnover (bn 2014 RWF)": svn.turnover / 1e9, "Reporting est. (000s)": svn.est / 1e3, "Workers (000s)": svn.emp / 1e3}, axis=1)
svt = svt.drop(index=2011, errors="ignore").drop(columns=[c for c in svt.columns if c[1] == "AG"])
svt.columns = [f"{a}: {b}" for a, b in svt.columns]
to_tex(svt.T, OUT_T / "output_ec_national", "Establishment Census turnover (CPI-deflated, 2014 RWF) and workers by ISIC group. Turnover is self-reported and missing for informal units in some waves.", "tab:ec_nat", "{:,.1f}")
cov = ec.groupby("ec_year").has_turn.mean(); print("turnover reported share:", cov.round(3).to_dict())

# turnover per worker by group and district park group
pw = sv.groupby(["year", "park_group", "grp"])[["turnover", "emp_rep"]].sum()
pw["turn_per_worker_m"] = pw.turnover / pw.emp_rep / 1e6
pwt = pw.turn_per_worker_m.unstack("grp")[["IND", "S_tour", "S_bus", "S_loc"]].drop(index=2011, level=0, errors="ignore")
pwt.index = pwt.index.set_names(["year", "district group"])
to_tex(pwt, OUT_T / "output_ec_turnover_per_worker", "Real turnover per worker (million 2014 RWF), Establishment Census, by district park exposure.", "tab:ec_tpw", "{:,.2f}")

# ---------------- (c) nightlights ----------------
nl = pd.read_csv(ANA / "nightlights_settled_panel_sector.csv").rename(columns={"uid": "sid"})
nl = nl.merge(cross[["sid", "band"]], on="sid")
nlb = nl.groupby(["year", "band"], observed=True).asinh_sum.mean().unstack()
nlb.to_csv(OUT_T / "output_nightlights_by_band.csv")

# ---------------- (d) tourism ----------------
TD = DATA / "Tourism Data"
vis = pd.read_csv(TD / "park_visitors_by_park.csv").set_index("year")
prev = pd.read_csv(TD / "park_revenue_usd_million.csv").set_index("year").park_revenue_usd_million_nominal
trev = pd.read_csv(TD / "rdb_tourism_revenue_usd_million.csv"); trev = trev.set_index(trev.columns[0]).iloc[:, 0]
tt = pd.DataFrame({"Park visitors (000s)": vis.total / 1e3, "Volcanoes": vis.volcanoes / 1e3, "Akagera": vis.akagera / 1e3,
                   "Nyungwe": vis.nyungwe / 1e3, "Park revenue (US$ m)": prev, "Tourism revenue (US$ m)": trev})
tt["Park revenue per visitor (US$)"] = tt["Park revenue (US$ m)"] * 1e3 / tt["Park visitors (000s)"]
tt.to_csv(OUT_T / "output_tourism_national.csv")

# ---------------- figures ----------------
fig, ax = plt.subplots(2, 2, figsize=(8.4, 5.6))
a = ax[0, 0]
a.plot(agn.index, agn.v / agn.v.loc[2019] * 100, marker="o", ms=3, color=PAL[0])
a.set_title("Crop output value at fixed prices, SAS (2019 = 100)", loc="left", fontsize=9)
a = ax[0, 1]
tpw = (svn.turnover / svn.emp_rep / 1e6).drop(index=2011, errors="ignore")
for i, c in enumerate(["IND", "S_tour", "S_bus", "S_loc"]):
    a.plot(tpw.index, tpw[c], marker="o", ms=3, color=PAL[i], label={"IND": "Industry", "S_tour": "Tourism svc (I,R)", "S_bus": "Business svc", "S_loc": "Local svc"}[c])
a.set_xticks([2014, 2017, 2020, 2023]); a.set_title("Real turnover per reporting worker (m 2014 RWF)", loc="left", fontsize=9); a.legend(fontsize=7, frameon=False)
a = ax[1, 0]
nv = nlb.loc[nlb.index >= 2014]
for i, b in enumerate(["Park border", "0-10 km", "10-30 km", ">30 km"]):
    a.plot(nv.index, nv[b], color=PAL[i], label=b, lw=1.5)
a.set_title("Nightlights (VIIRS), mean asinh(sum) per sector", loc="left", fontsize=9); a.legend(fontsize=7, frameon=False)
a = ax[1, 1]
for i, c in enumerate(["Volcanoes", "Akagera", "Nyungwe"]):
    a.plot(tt.index, tt[c], marker="o", ms=3, color=PAL[i], label=c)
a.axvline(2017, color="#999", lw=0.8, ls="--"); a.text(2017.2, a.get_ylim()[1] * 0.9, "Gorilla permit\n\\$750 to \\$1,500", fontsize=6.5, color="#555")
a.set_title("Park visitors (000s)", loc="left", fontsize=9); a.xaxis.set_major_locator(plt.MaxNLocator(integer=True)); a.legend(fontsize=7, frameon=False)
fig.tight_layout(); fig.savefig(OUT_F / "output_trends.png"); plt.close(fig)

# agricultural value per ha by district group
agg = ag.groupby(["year", "park_group"])[["v", "ha"]].sum(min_count=1); agg = (agg.v / agg.ha / 1e3).unstack()
agg.to_csv(OUT_T / "output_ag_value_per_ha_by_group.csv")
fig, a = plt.subplots(figsize=(4.4, 3))
for i, c in enumerate(["No park border", "Park-border district", "Kigali"]):
    if c in agg: a.plot(agg.index, agg[c], marker="o", ms=3, color=PAL[i], label=c)
a.set_title("Crop value per ha (000 RWF, fixed prices)\nby district share of land on a park border", loc="left", fontsize=8.5); a.legend(fontsize=7, frameon=False)
fig.tight_layout(); fig.savefig(OUT_F / "output_ag_value_per_ha_by_group.png"); plt.close(fig)

print(agn_t.round(1).to_string()); print(svt.round(1).T.to_string()); print(pwt.round(2).to_string()); print(tt.round(1).to_string())
print(dgrp.value_counts().to_dict()); print(agg.round(0).to_string())
