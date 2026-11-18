"""Section B: preliminary reduced form. Sector x Census wave (2002 base, 2012, 2022).
 y_nt = a_n + d_{province x t} + sum_{t in 2012,2022} [ thG_t NearGate_n 1{t} + thB_t BorderOnly_n 1{t} ] + e_nt
 NearGate = Gates + Gates+ (12 sectors, tourism + TRS); BorderOnly = bordering, not near a gate (32, TRS + conservation).
 Comparison = clean control (257): control minus the spillover ring (62 sectors touching a treated sector) and the
 9 Gishwati-Mukura neighbours. Kigali and the four 2002 towns excluded throughout.
 Province x wave FE in the main spec: within-district comparisons are too thin (Kayonza and Nyamasheke keep one clean control each).
 SEs clustered by district; p-values from the wild cluster restricted bootstrap (9,999 draws, Webb six-point weights).
 Land outcomes (T11) use GLCLU's own years 2000 (base), 2005, 2010, 2015, 2020, so land is never measured before the period it describes. Near-gate sectors
 sit in 5 districts, so the bootstrap rests on few treated clusters (MacKinnon and Webb 2017): read near-gate p-values with care.
 Park-border x wave terms cannot enter alongside a bordering treatment (they mark the same sectors); park differences enter
 as park-specific treatment effects instead (T13).
 Robustness (T12): district x wave FE; + 2000 cropland and tree shares x wave; continuous exposure
 = ln(1 + visitors to nearest park, 000s) x exp(-km to nearest pre-2005 gate / 10), visitors for 2002/2012/2022 = 2005/2012/2019.
 Wages (T14): LFS employees 16-64, ln real monthly cash earnings on sector group, district x year FE, age, age^2, sex, education."""
import os, numpy as np, pandas as pd
from _common import *
from _reg import fe_ols

d = pd.read_csv(OUT_D / "sector_panel_desc.csv")
tg = pd.read_csv(OUT_D / "treatment_groups.csv")
pop = pd.read_csv(OUT_D / "sector_pop_total.csv")
cross = pd.read_csv(ANA / "model_sector_cross.csv")[["sid", "lon", "lat"]]
d = d.drop(columns=[c for c in d.columns if c in ("ring1", "control_clean", "gish")], errors="ignore").merge(
    tg[["sid", "ring1", "control_clean", "gish"]], on="sid").merge(pop, on=["sid", "wave"]).merge(cross, on="sid")
d["NG"] = d.group.isin(["Gates", "Gates+"]).astype(int); d["BO"] = (d.group == "Bordering").astype(int)
d["ln_pop"] = np.log(d.pop_total); d["ln_Na"] = np.log(d.AG); d["ln_Ns"] = np.log(d.S_broad.replace(0, np.nan))
d["sh_tour"] = (d.n_I + d.n_H + d.n_R) / d.workers      # tourism-characteristic, section level (I + H + R)
d["pw"] = d.province_id.astype(str) + "_" + d.wave.astype(str); d["dw"] = d.district_id.astype(str) + "_" + d.wave.astype(str)
for w in (2012, 2022):
    d[f"NG_{w}"] = d.NG * (d.wave == w); d[f"BO_{w}"] = d.BO * (d.wave == w); d[f"T_{w}"] = (d.NG | d.BO) * (d.wave == w)
# baseline land x wave (robustness)
base = d[d.wave == 2002].set_index("sid")[["crop_sh", "tree_sh"]].rename(columns=lambda c: c + "0")
d = d.merge(base, left_on="sid", right_index=True)
for w in (2012, 2022):
    d[f"crop0_{w}"] = d.crop_sh0 * (d.wave == w); d[f"tree0_{w}"] = d.tree_sh0 * (d.wave == w)
# continuous exposure
GATE_XY = {4307: (29.59528, -1.43165), 3701: (29.09228, -2.44059), 2509: (29.41697, -2.52640), 5407: (30.68178, -1.89912)}
GPARK = {4307: "volcanoes", 3701: "nyungwe", 2509: "nyungwe", 5407: "akagera"}
def hav(lon1, lat1, lon2, lat2):
    r = np.radians; a = np.sin(r(lat2 - lat1) / 2) ** 2 + np.cos(r(lat1)) * np.cos(r(lat2)) * np.sin(r(lon2 - lon1) / 2) ** 2
    return 6371 * 2 * np.arcsin(np.sqrt(a))
D = pd.DataFrame({g: hav(d.lon, d.lat, *xy) for g, xy in GATE_XY.items()})
d["gate"] = D.idxmin(axis=1).values; d["km_gate"] = D.min(axis=1).values
vis = pd.read_csv(DATA / "Tourism Data" / "park_visitors_by_park.csv").set_index("year")
vy = {2002: 2005, 2012: 2012, 2022: 2019}
d["visitors"] = [vis.loc[vy[w], GPARK[g]] / 1e3 for w, g in zip(d.wave, d.gate)]
d["exposure"] = np.log1p(d.visitors) * np.exp(-d.km_gate / 10)

S = d[(d.urban == 0) & ((d.NG == 1) | (d.BO == 1) | (d.control_clean == 1))].copy()
print("sample sectors:", S.sid.nunique(), "near gate", S[S.NG == 1].sid.nunique(), "border only", S[S.BO == 1].sid.nunique(), "clean control", S[S.control_clean == 1].sid.nunique())
TX = ["NG_2012", "NG_2022", "BO_2012", "BO_2022"]
JOBS = {"lam": "lambda", "sh_tour": "Tourism share (I,H,R)", "sh_svc": "Services share (excl. G,O)", "ln_pop": "ln total population",
        "ln_Na": "ln farm workers", "ln_Ns": "ln services workers", "ntl_chen_asinh": "Night lights asinh(sum)"}
LAND = {"crop_sh": "Cropland share", "built_sh": "Built-up share", "tree_sh": "Tree-cover share", "other_sh": "Short veg./bare share"}

def est(df, y, xs, fes, extra=()):
    r, n, G = fe_ols(df, y, list(xs) + list(extra), fes, "district_id")
    return r.loc[list(xs)], n, G
def table(outcomes, fes, xs=TX, extra=(), df=S):
    rows = []
    for y, lab in outcomes.items():
        r, n, G = est(df, y, xs, fes, extra)
        cm = df[(df.control_clean == 1) & (df.wave == 2002)][y].mean()
        for x in xs: rows.append(dict(outcome=lab, term=x, coef=r.loc[x, "coef"], se=r.loc[x, "se"], p_wcb=r.loc[x, "p_wcb"], N=n, clusters=G, control_mean_2002=cm))
    return pd.DataFrame(rows)
def fmt(R, name, cap):
    R.to_csv(OUT_T / f"{name}_long.csv", index=False)
    st = lambda p: "***" if p < .01 else "**" if p < .05 else "*" if p < .1 else ""
    W = {}
    for o, g in R.groupby("outcome", sort=False):
        col = []
        for r in g.itertuples(): col += [f"{r.coef:.3f}{st(r.p_wcb)}", f"({r.se:.3f})", f"[{r.p_wcb:.3f}]"]
        col += [f"{g.control_mean_2002.iloc[0]:.3f}", str(g.N.iloc[0])]
        W[o] = col
    idx = []
    for t in R.term.unique(): idx += [t, "", ""]
    idx += ["Control mean 2002", "N"]
    T = pd.DataFrame(W, index=idx); T.to_csv(OUT_T / f"{name}.csv")
    (OUT_T / f"{name}.tex").write_text(T.to_latex(caption=cap, label=f"tab:{name}", position="htbp"))
    return T
note = " Sector FE and province x wave FE; 2002 is the base wave. SE clustered by district in parentheses; wild cluster restricted bootstrap p in brackets (stars from it)."
T10 = fmt(table(JOBS, ["sid", "pw"]), "T10_B_jobs", "Near-gate and bordering-only sectors vs clean control: jobs, population and night lights (Census waves)." + note)

# ---- land event study on GLCLU years (2000 base) ----
cb = pd.read_csv(OUT_D / "sector_cropland_builtup_glclu.csv").rename(columns={"year": "wave"}).drop(columns=["urban", "control", "treated_any", "group", "park", "sector", "district"], errors="ignore")
LS = cb.merge(d[d.wave == 2002][["sid", "NG", "BO", "control_clean", "urban", "province_id", "district_id", "park", "crop_sh0", "tree_sh0"]], on="sid")
LS = LS[(LS.urban == 0) & ((LS.NG == 1) | (LS.BO == 1) | (LS.control_clean == 1))].copy()
LY = [2005, 2010, 2015, 2020]
for w in LY:
    LS[f"NG_{w}"] = LS.NG * (LS.wave == w); LS[f"BO_{w}"] = LS.BO * (LS.wave == w)
    LS[f"crop0_{w}"] = LS.crop_sh0 * (LS.wave == w); LS[f"tree0_{w}"] = LS.tree_sh0 * (LS.wave == w)
    for p in ["volcanoes", "nyungwe", "akagera"]: LS[f"T_{p}_{w}"] = ((LS.NG | LS.BO) & (LS.park.str.lower() == p)) * (LS.wave == w)
LS["pw"] = LS.province_id.astype(str) + "_" + LS.wave.astype(str); LS["dw"] = LS.district_id.astype(str) + "_" + LS.wave.astype(str)
LTX = [f"{g}_{w}" for g in ["NG", "BO"] for w in LY]
def ltable(fes, xs=LTX, extra=()):
    rows = []
    for y, lab in LAND.items():
        r, n, G = fe_ols(LS, y, list(xs) + list(extra), fes, "district_id")
        cm = LS[(LS.control_clean == 1) & (LS.wave == 2000)][y].mean()
        for x in xs: rows.append(dict(outcome=lab, term=x, coef=r.loc[x, "coef"], se=r.loc[x, "se"], p_wcb=r.loc[x, "p_wcb"], N=n, clusters=G, control_mean_2002=cm))
    return pd.DataFrame(rows)
T11 = fmt(ltable(["sid", "pw"]), "T11_B_land", "Near-gate and bordering-only sectors vs clean control: land use, GLCLU 2000 (base) to 2020. Sector FE and province x year FE." + note)
L1 = ltable(["sid", "dw"]).assign(spec="District x year FE")
L2 = ltable(["sid", "pw"], extra=[f"{v}0_{w}" for v in ["crop", "tree"] for w in LY]).assign(spec="+ 2000 land shares x year")
L3 = ltable(["sid", "pw"], xs=[f"T_{p}_{w}" for p in ["volcanoes", "nyungwe", "akagera"] for w in LY]).assign(spec="By park")
pd.concat([L1, L2, L3]).to_csv(OUT_T / "T11b_B_land_robustness_long.csv", index=False)
# robustness on headline outcomes
HEAD = {"lam": "lambda", "sh_tour": "Tourism share (I,H,R)", "ln_pop": "ln total population", "ntl_chen_asinh": "Night lights"}
r1 = table(HEAD, ["sid", "dw"]).assign(spec="District x wave FE")
r2 = table(HEAD, ["sid", "pw"], extra=["crop0_2012", "crop0_2022", "tree0_2012", "tree0_2022"]).assign(spec="+ 2000 land shares x wave")
SE = d[(d.urban == 0) & (d.gish == 0)].copy()     # continuous exposure on all non-urban sectors
r3 = table(HEAD, ["sid", "pw"], xs=["exposure"], df=SE).assign(spec="Continuous exposure (all non-urban)")
R12 = pd.concat([r1, r2, r3]); R12.to_csv(OUT_T / "T12_B_robustness_long.csv", index=False)
piv = R12.assign(cell=lambda x: x.coef.map("{:.3f}".format) + " [" + x.p_wcb.map("{:.3f}".format) + "]").pivot_table(index=["spec", "term"], columns="outcome", values="cell", aggfunc="first")
piv.to_csv(OUT_T / "T12_B_robustness.csv"); (OUT_T / "T12_B_robustness.tex").write_text(piv.to_latex(caption="Robustness: coefficient [wild cluster bootstrap p].", label="tab:T12", position="htbp"))
# park heterogeneity: pooled treated x park x wave
for p in ["volcanoes", "nyungwe", "akagera"]:
    for w in (2012, 2022):
        S[f"T_{p}_{w}"] = ((S.NG | S.BO) & (S.park.str.lower() == p)) * (S.wave == w)
PX = [f"T_{p}_{w}" for p in ["volcanoes", "nyungwe", "akagera"] for w in (2012, 2022)]
T13 = fmt(table(HEAD, ["sid", "pw"], xs=PX), "T13_B_by_park", "Treated (near gate or bordering) by park vs clean control." + note)

# ---- wages ----
l = pd.read_parquet(os.path.expanduser("~/lfs_sub.parquet")).join(pd.read_parquet(os.path.expanduser("~/lfs_demo.parquet"))[["lfs_sex", "lfs_education_level_highest"]])
l = l[(l.lfs_employment_status == 1) & l.lfs_monthly_cash_income.gt(0) & l.lfs_age.between(16, 64) & l.lfs_industry_isic.notna()].copy()
l["sec"] = l.lfs_industry_isic.astype(int).map(SEC)
l["g"] = np.select([l.sec == "A", l.sec.isin(list("IHR")), l.sec.isin(list("JKM")), l.sec.isin(list("BCDEF"))], ["AG", "TOUR", "BUS", "IND"], "LOC")
cpi = pd.read_csv(DATA / "Tourism Data" / "world_bank_wdi.csv").query("country=='RWA' and indicator_code=='FP.CPI.TOTL'").set_index("year").value
l["lnw"] = np.log(l.lfs_monthly_cash_income / l.lfs_year.map(lambda y: cpi.get(min(y, cpi.dropna().index.max())) / cpi[2014]))
for g in ["TOUR", "LOC", "BUS", "IND"]: l[g] = (l.g == g).astype(float)
l["age2"] = l.lfs_age ** 2 / 100; l["female"] = (l.lfs_sex == 2).astype(float)
l["dy"] = l.lfs_district.astype(str) + "_" + l.lfs_year.astype(str); l["edu"] = l.lfs_education_level_highest.fillna(0).astype(int).astype(str)
l["district_id"] = l.lfs_district
cross_d = pd.read_csv(ANA / "model_sector_cross.csv")[["sid", "district_id"]]
park_d = set(tg.merge(cross_d, on="sid").query("treated_any == 1").district_id)
rows = []
for lab, sub in [("All districts", l), ("Excl. Kigali", l[~l.lfs_district.isin([11, 12, 13])]), ("Park districts", l[l.lfs_district.isin(park_d)])]:
    r, n, G = fe_ols(sub, "lnw", ["TOUR", "LOC", "BUS", "IND", "lfs_age", "age2", "female"], ["dy", "edu"], "district_id", B=4999)
    for x in ["TOUR", "LOC", "BUS", "IND"]: rows.append(dict(sample=lab, term=x, coef=r.loc[x, "coef"], se=r.loc[x, "se"], p_wcb=r.loc[x, "p_wcb"], ratio=np.exp(r.loc[x, "coef"]), N=n, clusters=G))
T14 = pd.DataFrame(rows); T14.to_csv(OUT_T / "T14_B_wage_gaps.csv", index=False)
(OUT_T / "T14_B_wage_gaps.tex").write_text(T14.pivot_table(index="term", columns="sample", values=["coef", "se", "p_wcb", "ratio"]).to_latex(float_format=lambda v: f"{v:.3f}",
    caption="Within district-year earnings gaps relative to agriculture, LFS employees 16--64, ln real monthly cash earnings. District x year and education FE; age, age squared, female. Unweighted. SE clustered by district; wild cluster bootstrap p.", label="tab:T14", position="htbp"))
pd.set_option("display.width", 230, "display.max_columns", 20)
print(T10.to_string()); print(T11.to_string()); print(pd.concat([L1, L2, L3]).round(3).to_string()); print(piv.to_string()); print(T13.to_string()); print(T14.round(3).to_string(index=False))
