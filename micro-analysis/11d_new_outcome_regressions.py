"""Regressions on the new outcomes. All outcomes are measured after the period they describe.
 A) Table-1 specification (sector FE, district x wave FE, park-border x wave; services share and ln total population):
    (i)  Hansen tree-cover loss, mean annual % of 2000 cover, in the years after each Census (2003-05, 2013-15, 2023-24);
         sectors with >= 10 ha tree cover outside parks in 2000. Three waves.
    (ii) GHSL built-up surface, share of usable land, three years after the Census (2005 for 2002, 2015 for 2012). Two waves.
 B) Section-B specification (near gate / bordering only vs clean control, sector FE, province x period FE):
    (i)  Hansen loss rate in five-year bins 2001-04 (base), 2005-09, 2010-14, 2015-19, 2020-24;
    (ii) GHSL built-up surface share, 2000 (base), 2005, 2010, 2015, 2020.
 C) District land rent (EICV 2001-2017): ln median real rent per ha on park-district x year, district and year FE, Kigali excluded.
 Wild cluster restricted bootstrap (Webb, 9,999), clusters = districts."""
import numpy as np, pandas as pd
from _common import *
from _reg import fe_ols
tg = pd.read_csv(OUT_D / "treatment_groups.csv").merge(pd.read_csv(ANA / "model_sector_cross.csv")[["sid", "district_id", "province_id"]], on="sid")
pan = pd.read_csv(OUT_D / "sector_panel_desc.csv")[["sid", "wave", "sh_svc", "urban"]].merge(pd.read_csv(OUT_D / "sector_pop_total.csv"), on=["sid", "wave"])
pan["ln_pop"] = np.log(pan.pop_total)
cb = pd.read_csv(OUT_D / "sector_cropland_builtup_glclu.csv")[["sid", "year", "usable"]]
gh = pd.read_csv(OUT_D / "sector_ghsl_built.csv").merge(cb, on=["sid", "year"])
gh["ghsl_built_sh"] = 100 * gh.built_total_ha / gh.usable           # percent of usable land
fo = pd.read_csv(OUT_D / "sector_forest_census.csv")
ha = pd.read_csv(OUT_D / "sector_hansen_annual.csv")
BC = [c for c in tg.columns if c.startswith("border_")]
def addfe(df, per):
    df = df.merge(tg[["sid", "district_id", "province_id", "group", "control_clean", "park"] + BC], on="sid")
    df["dw"] = df.district_id.astype(str) + "_" + df[per].astype(str); df["pw"] = df.province_id.astype(str) + "_" + df[per].astype(str)
    return df
rows = []
def rec(tag, y, r, n, G, terms, cm=np.nan):
    for t in terms: rows.append(dict(block=tag, outcome=y, term=t, coef=r.loc[t, "coef"], se=r.loc[t, "se"], p_wcb=r.loc[t, "p_wcb"], N=n, clusters=G, control_mean=cm))

# ---- A(i) forest, Table-1 spec, three waves ----
A1 = addfe(pan.merge(fo[["sid", "wave", "loss_rate", "tc"]], on=["sid", "wave"]), "wave")
A1 = A1[(A1.urban == 0) & (A1.tc >= 10)].copy()
pk = []
for p in ["volcanoes", "nyungwe", "akagera", "gishwati"]:
    for w in (2012, 2022): A1[f"b_{p}_{w}"] = A1[f"border_{p}"] * (A1.wave == w); pk.append(f"b_{p}_{w}")
r, n, G = fe_ols(A1, "loss_rate", ["sh_svc", "ln_pop"] + pk, ["sid", "dw"], "district_id"); rec("A_forest", "Tree-cover loss (% of 2000 cover per year)", r, n, G, ["sh_svc", "ln_pop"], A1[A1.wave == 2002].loss_rate.mean())
# ---- A(ii) GHSL built share after the census, two waves ----
A2 = addfe(pan[pan.wave.isin([2002, 2012])].merge(gh.assign(wave=gh.year.map({2005: 2002, 2015: 2012})).dropna(subset=["wave"])[["sid", "wave", "ghsl_built_sh"]], on=["sid", "wave"]), "wave")
A2 = A2[A2.urban == 0].copy(); pk2 = []
for p in ["volcanoes", "nyungwe", "akagera", "gishwati"]: A2[f"b_{p}"] = A2[f"border_{p}"] * (A2.wave == 2012); pk2.append(f"b_{p}")
r, n, G = fe_ols(A2, "ghsl_built_sh", ["sh_svc", "ln_pop"] + pk2, ["sid", "dw"], "district_id"); rec("A_ghsl", "Built-up surface, % of usable land (GHSL)", r, n, G, ["sh_svc", "ln_pop"], A2[A2.wave == 2002].ghsl_built_sh.mean())

# ---- B(i) forest loss event study, five-year bins ----
ha["bin"] = pd.cut(ha.year, [2000, 2004, 2009, 2014, 2019, 2024], labels=[2001, 2005, 2010, 2015, 2020]).astype(int)
B1 = ha.groupby(["sid", "bin"]).agg(loss=("loss_ha", "mean"), tc=("treecover2000_ha", "first")).reset_index()
B1["loss_rate"] = 100 * B1.loss / B1.tc.where(B1.tc >= 10)
B1 = addfe(B1, "bin"); B1 = B1[B1.group.isin(["Gates", "Gates+", "Bordering"]) | (B1.control_clean == 1)].dropna(subset=["loss_rate"]).copy()
B1["NG"] = B1.group.isin(["Gates", "Gates+"]).astype(int); B1["BO"] = (B1.group == "Bordering").astype(int)
T1 = []
for g in ["NG", "BO"]:
    for b in [2005, 2010, 2015, 2020]: B1[f"{g}_{b}"] = B1[g] * (B1["bin"] == b); T1.append(f"{g}_{b}")
r, n, G = fe_ols(B1, "loss_rate", T1, ["sid", "pw"], "district_id"); rec("B_forest", "Tree-cover loss (% of 2000 cover per year)", r, n, G, T1, B1[(B1.control_clean == 1) & (B1["bin"] == 2001)].loss_rate.mean())
# ---- B(ii) GHSL built share event study ----
B2 = addfe(gh[["sid", "year", "ghsl_built_sh"]].copy(), "year")
B2 = B2[B2.group.isin(["Gates", "Gates+", "Bordering"]) | (B2.control_clean == 1)].copy()
B2["NG"] = B2.group.isin(["Gates", "Gates+"]).astype(int); B2["BO"] = (B2.group == "Bordering").astype(int)
T2 = []
for g in ["NG", "BO"]:
    for y in [2005, 2010, 2015, 2020]: B2[f"{g}_{y}"] = B2[g] * (B2.year == y); T2.append(f"{g}_{y}")
r, n, G = fe_ols(B2, "ghsl_built_sh", T2, ["sid", "pw"], "district_id"); rec("B_ghsl", "Built-up surface, % of usable land (GHSL)", r, n, G, T2, B2[(B2.control_clean == 1) & (B2.year == 2000)].ghsl_built_sh.mean())

# ---- C) district land rent ----
D = pd.read_csv(OUT_D / "district_land_rent.csv"); D = D[(D.src == "EICV") & ~D.district_id.isin([11, 12, 13])].copy()
park_d = set(tg[tg.treated_any == 1].district_id); D["park"] = D.district_id.isin(park_d).astype(int); D["ln_r"] = np.log(D.rent_ha_median)
TC = []
for y in [2006, 2011, 2014, 2017]: D[f"P_{y}"] = D.park * (D.year == y); TC.append(f"P_{y}")
r, n, G = fe_ols(D, "ln_r", TC, ["district_id", "year"], "district_id"); rec("C_rent", "ln real rent per ha", r, n, G, TC, D[(D.park == 0) & (D.year == 2001)].ln_r.mean())
R = pd.DataFrame(rows); R.to_csv(OUT_T / "T16_new_outcomes_long.csv", index=False)
pd.set_option("display.width", 220); print(R.round(4).to_string(index=False))
print("rent sample: districts", D.district_id.nunique(), "park districts", D[D.park == 1].district_id.nunique(), "years", sorted(D.year.unique()))
