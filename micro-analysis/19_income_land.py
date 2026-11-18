"""First Stage II: national income x baseline agricultural wage -> tree-cover loss, 2001-2024.
D_st = beta (ln Ybar_t x w_ag_{d(s),2001}) + mu_s + lambda_t + X_st'gamma + e_st
D_st: Hansen loss outside parks, % of 2000 tree cover per year; sectors with >= 10 ha cover in 2000.
Ybar_t: WDI GDP per capita, constant 2015 US$ (NY.GDP.PCAP.KD).
w_ag: EICV 2001 median daily cash wage of paid crop/livestock workers (trade codes 111, 121), by district;
      day/week/month/year units converted with reported days per week (4.33 weeks per month). Standardised (z) across districts.
X_st: near-gate x year and bordering-only x year dummies. SE clustered by district; wild cluster restricted bootstrap p."""
import numpy as np, pandas as pd
from _common import *
from _reg import fe_ols

E = DATA / "Publicly-Available-NISR/Household-Living-Conditions-EICV/2_Intermediate/EICV_EICV1_s4_occupation_clean.dta"
d = pd.read_stata(E, convert_categoricals=False)
w = d[d.eicv_trade_service_industry_2001.isin([111, 121]) & (d.eicv_receive_money_work_2001 == 1)
      & d.eicv_last_amount_renumeration.gt(0) & d.eicv_time_unit_amount_received.notna()].copy()
dpw = w.eicv_weeks_days_worked_2001.clip(1, 7).fillna(5)
den = np.select([w.eicv_time_unit_amount_received == 1, w.eicv_time_unit_amount_received == 2,
                 w.eicv_time_unit_amount_received == 3, w.eicv_time_unit_amount_received == 4], [1, dpw, dpw * 4.33, dpw * 52])
w["daily"] = w.eicv_last_amount_renumeration / den
W = w.groupby("eicv_district").agg(n=("daily", "size"), w_ag=("daily", "median")).reset_index().rename(columns={"eicv_district": "district_id"})
W.to_csv(OUT_D / "district_ag_wage_eicv2001.csv", index=False)
print("paid ag wage obs:", len(w), "| districts:", len(W), "| median obs/district:", W.n.median(), "| districts <10 obs:", (W.n < 10).sum())

Y = {2001: 356.02, 2002: 397.56, 2003: 397.48, 2004: 415.94, 2005: 443.01, 2006: 471.15, 2007: 493.80, 2008: 534.68, 2009: 553.62,
     2010: 579.42, 2011: 610.38, 2012: 647.44, 2013: 661.89, 2014: 682.71, 2015: 725.69, 2016: 748.80, 2017: 765.85, 2018: 808.70,
     2019: 863.87, 2020: 821.26, 2021: 871.04, 2022: 935.89, 2023: 993.91, 2024: 1043.16}
h = pd.read_csv(OUT_D / "sector_hansen_annual.csv")
h = h[h.treecover2000_ha >= 10].copy(); h["D"] = 100 * h.loss_ha / h.treecover2000_ha
tg = pd.read_csv(OUT_D / "treatment_groups.csv")[["sid", "group"]]
p = pd.read_csv(OUT_D / "sector_panel_desc.csv").query("wave == 2002")[["sid", "district_id"]]
h = h.merge(tg, on="sid").merge(p, on="sid").merge(W, on="district_id")
h = h[~h.group.isin(["Kigali", "Towns"])].copy()
h["lnY"] = np.log(h.year.map(Y))
h["w_z"] = (h.w_ag - W.w_ag.mean()) / W.w_ag.std()
h["ln_w"] = np.log(h.w_ag)
h["lnYxw"] = h.lnY * h.w_z; h["lnYxlnw"] = h.lnY * h.ln_w
NG = h.group.isin(["Gates", "Gates+"]); BO = h.group == "Bordering"
for y in range(2002, 2025):
    h[f"NG_{y}"] = (NG & (h.year == y)).astype(float); h[f"BO_{y}"] = (BO & (h.year == y)).astype(float)
XC = [f"{g}_{y}" for g in ("NG", "BO") for y in range(2002, 2025)]
print("sectors:", h.sid.nunique(), "obs:", len(h), "districts:", h.district_id.nunique(), "| mean D:", round(h.D.mean(), 3))
rows = []
for lab, x in [("w standardised", "lnYxw"), ("ln w", "lnYxlnw")]:
    for ctl, xs in [("no X", []), ("with X", XC)]:
        r, n, g = fe_ols(h, "D", [x] + xs, ["sid", "year"], "district_id")
        rows.append(dict(wage=lab, controls=ctl, coef=r.loc[x, "coef"], se=r.loc[x, "se"], p_wcb=r.loc[x, "p_wcb"], N=n, G=g))
R = pd.DataFrame(rows); R.to_csv(OUT_T / "T19_income_land_long.csv", index=False)
print(R.round(4).to_string(index=False))
# pre-trend style check: split periods
for a, b in [(2001, 2012), (2013, 2024)]:
    s = h[h.year.between(a, b)]
    r, n, g = fe_ols(s, "D", ["lnYxw"] + [c for c in XC if a < int(c[-4:]) <= b], ["sid", "year"], "district_id")
    print(a, b, r.loc["lnYxw"].round(4).to_dict(), n)
