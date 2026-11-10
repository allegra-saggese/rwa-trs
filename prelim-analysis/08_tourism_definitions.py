"""Tourism employment under three definitions.
 Narrow (Census panel)      : ISIC sections I + R
 Section-broad (Census)     : I + H + R   (transport kept whole; freight is small in Rwanda)
 TSA-broad (divisions)      : 49, 50, 51 (transport), 55, 56 (accommodation, food), 79 (travel agencies, tour operators),
                              90-93 (culture, recreation) -- the UN tourism-characteristic industries at 2-digit
A) 2012 Census, 4-digit ISIC4: how much of TSA-broad employment the section definitions capture, by group.
B) LFS 2017-2025, 2-digit, district x year: TSA-broad share of employed (16+), by district group."""
import os, numpy as np, pandas as pd, matplotlib.pyplot as plt
from _common import *

TSA = [49, 50, 51, 55, 56, 79, 90, 91, 92, 93]
tg = pd.read_csv(OUT_D / "treatment_groups.csv")
grp = tg.set_index("sid").group.map(lambda g: "Treated: near gate" if g in ("Gates", "Gates+") else ("Treated: bordering only" if g == "Bordering" else ("Urban" if g in ("Kigali", "Towns") else "Control")))
cc = tg.set_index("sid").control_clean

# ---- A) Census 2012 4-digit ----
c = pd.read_parquet(os.path.expanduser("~/census_sub.parquet"), columns=["census_year", "census_sector", "census_age", "census_weight", "census_industry_isic4_2012"])
c = c[(c.census_year == 2012) & c.census_age.between(20, 64) & c.census_industry_isic4_2012.between(100, 9900)].copy()
c["div"] = (c.census_industry_isic4_2012 // 100).astype(int)
c["grp"] = c.census_sector.map(grp)
def agg(x):
    w = x.census_weight; tot = w.sum()
    tsa = w[x["div"].isin(TSA)].sum(); ir = w[x["div"].isin([55, 56, 90, 91, 92, 93])].sum(); ihr = w[x["div"].between(49, 53) | x["div"].isin([55, 56, 90, 91, 92, 93])].sum()
    return pd.Series({"Workers (000s)": tot / 1e3, "TSA-broad share": tsa / tot, "I+R share": ir / tot, "I+H+R share": ihr / tot,
                      "I+R / TSA-broad": ir / tsa, "I+H+R / TSA-broad": ihr / tsa,
                      "of TSA: accommodation (55)": w[x["div"] == 55].sum() / tsa, "of TSA: food & beverage (56)": w[x["div"] == 56].sum() / tsa,
                      "of TSA: transport (49-51)": w[x["div"].between(49, 51)].sum() / tsa, "of TSA: tour operators (79)": w[x["div"] == 79].sum() / tsa,
                      "of TSA: culture & recreation (90-93)": w[x["div"].between(90, 93)].sum() / tsa})
A = pd.concat([c.groupby("grp").apply(agg, include_groups=False), agg(c).to_frame("National").T])
A = A.loc[["Treated: near gate", "Treated: bordering only", "Control", "Urban", "National"]]
A.to_csv(OUT_T / "T9a_tourism_definitions_census2012.csv")
(OUT_T / "T9a_tourism_definitions_census2012.tex").write_text(A.T.to_latex(float_format=lambda v: f"{v:,.3f}", caption="Tourism employment under three definitions, Census 2012 (4-digit ISIC Rev.4), workers 20--64. TSA-broad = divisions 49--51, 55, 56, 79, 90--93.", label="tab:T9a", position="htbp"))

# ---- B) LFS 2-digit district panel ----
l = pd.read_parquet(os.path.expanduser("~/lfs_isic.parquet"))
l = l[l.lfs_isic_section_main_job.notna() & (l.lfs_age >= 16)].copy()
l["div"] = l.lfs_isic_2digit_main_2017_2018.fillna(l.lfs_isic_main_job_2020).fillna(l.lfs_isic_two_digit_main_job)
l["div"] = l["div"].fillna(l.lfs_isic_main_job_2019_2021 // 100)
print("2-digit coverage by year:", l.groupby("lfs_year")["div"].apply(lambda s: s.notna().mean()).round(3).to_dict())
cross = pd.read_csv(ANA / "model_sector_cross.csv")[["sid", "district_id"]]
park_d = set(tg.merge(cross, on="sid").query("treated_any == 1").district_id)
l["dg"] = l.lfs_district.map(lambda di: "Kigali" if di in (11, 12, 13) else ("Park districts" if di in park_d else "Other districts"))
l["w"] = l.lfs_weight
for k, codes in {"tsa": TSA, "ir": [55, 56, 90, 91, 92, 93], "ihr": [49, 50, 51, 52, 53, 55, 56, 90, 91, 92, 93]}.items():
    l[k] = l["div"].isin(codes) * l.w
dp = l.groupby(["lfs_district", "lfs_year"])[["w", "tsa", "ir", "ihr"]].sum()
dp = dp[["tsa", "ir", "ihr"]].div(dp.w, axis=0).rename(columns=lambda x: f"sh_{x}").reset_index()
dp.to_csv(OUT_D / "district_tourism_lfs.csv", index=False)
gp = l.groupby(["dg", "lfs_year"])[["w", "tsa", "ir", "ihr", ]].sum()
B = pd.DataFrame({"TSA-broad": gp.tsa / gp.w, "I+R": gp.ir / gp.w, "I+H+R": gp.ihr / gp.w}).unstack(0)
nat = l.groupby("lfs_year")[["w", "tsa", "ir"]].sum(); B[("TSA-broad", "National")] = nat.tsa / nat.w; B[("TSA-broad", "National (000s)")] = nat.tsa / 1e3
B = B.sort_index(axis=1)
B.to_csv(OUT_T / "T9b_tourism_lfs_district_groups.csv")
(OUT_T / "T9b_tourism_lfs_district_groups.tex").write_text(B.to_latex(float_format=lambda v: f"{v:,.3f}", caption="Tourism share of employed (16+), LFS, by district group. Park districts contain a treated sector.", label="tab:T9b", position="htbp"))

fig, ax = plt.subplots(1, 2, figsize=(9, 3.2))
for i, g in enumerate(["Park districts", "Other districts", "Kigali"]):
    ax[0].plot(B.index, B[("TSA-broad", g)], marker="o", ms=3, color=["#c1121f", "#1b4965", "#9e9e9e"][i], label=g)
    ax[1].plot(B.index, B[("I+R", g)], marker="o", ms=3, color=["#c1121f", "#1b4965", "#9e9e9e"][i], label=g)
for a, t in zip(ax, ["TSA-broad (49-51, 55, 56, 79, 90-93)", "Narrow (I + R)"]):
    a.axvspan(2019.6, 2021.4, color="#eee", zorder=0); a.set_title(t + ", share of employed", loc="left", fontsize=8.5)
    a.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
ax[0].legend(fontsize=7, frameon=False); fig.tight_layout(); fig.savefig(OUT_F / "fig13_tourism_definitions_lfs.png"); plt.close(fig)
pd.set_option("display.width", 220); print(A.round(3).T.to_string()); print(B.round(3).to_string())
