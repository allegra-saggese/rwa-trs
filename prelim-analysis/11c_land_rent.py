"""District land rent per hectare, the model's r, from rented parcels.
 EICV parcels: 2001 (area in ha), 2006/2011 (area in ares), 2014/2017 (area in ares); rent paid over 12 months
   (2014 is labelled 12 months; other waves are taken as annual -- an assumption). Rented = rent > 0.
 AHS 2024 plots: cash rent for the plot, area in m2 (different instrument; reported separately).
 Codes >= 999,999 dropped; rent per ha winsorized at 1/99% within year; CPI-deflated to 2014 RWF (WDI).
 Output: Analysis/prelim/district_land_rent.csv (district x year weighted median, N parcels)."""
import os, numpy as np, pandas as pd
from _common import *
cpi = pd.read_csv(DATA / "Tourism Data" / "world_bank_wdi.csv").query("country=='RWA' and indicator_code=='FP.CPI.TOTL'").set_index("year").value
defl = lambda y: cpi.get(min(y, cpi.dropna().index.max())) / cpi[2014]
e = pd.read_parquet(os.path.expanduser("~/eicv_parcels.parquet"))
num = lambda c: pd.to_numeric(e[c], errors="coerce")
e["area_ha"] = np.where(e.eicv_year == 2001, num("eicv_area_hectares_2001"), num("eicv_surface_area_2006_2011").fillna(num("eicv_surface_area")) / 100)
e["rent"] = num("eicv_cost_include_renting_2001").fillna(num("eicv_cost_rental_2006")).fillna(num("eicv_cost_renting_2011")).fillna(num("eicv_cost_renting_months_2014")).fillna(num("eicv_cost_renting_2017"))
e = e[(e.rent > 0) & (e.rent < 999999) & (e.area_ha > 0)].copy()
E = pd.DataFrame({"year": e.eicv_year, "district_id": e.eicv_district, "w": e.eicv_household_weight.fillna(e.eicv_weight), "rent": e.rent, "area_ha": e.area_ha, "src": "EICV"})
a = pd.read_parquet(os.path.expanduser("~/ahs_land.parquet"))
a = a[a.ahs_year == 2024].copy(); a["rent"] = pd.to_numeric(a.ahs_pay_cash_renting_plot_2024, errors="coerce"); a["area_ha"] = pd.to_numeric(a.ahs_area_sqm_2024, errors="coerce") / 1e4
a = a[(a.rent > 0) & (a.area_ha > 0)]
A = pd.DataFrame({"year": 2024, "district_id": a.ahs_district, "w": a.ahs_household_weight.fillna(a.ahs_weight), "rent": a.rent, "area_ha": a.area_ha, "src": "AHS"})
P = pd.concat([E, A]); P["r_ha"] = P.rent / P.area_ha / P.year.map(defl)
P["r_ha"] = P.groupby("year").r_ha.transform(lambda s: s.clip(s.quantile(.01), s.quantile(.99)))
def wmed(x):
    o = np.argsort(x.r_ha.values); cw = np.cumsum(x.w.values[o]); return x.r_ha.values[o][np.searchsorted(cw, .5 * cw[-1])]
D = P.groupby(["district_id", "year", "src"]).apply(lambda x: pd.Series({"rent_ha_median": wmed(x), "n_parcels": len(x), "median_area_ha": x.area_ha.median()}), include_groups=False).reset_index()
D.to_csv(OUT_D / "district_land_rent.csv", index=False)
tg = pd.read_csv(OUT_D / "treatment_groups.csv").merge(pd.read_csv(ANA / "model_sector_cross.csv")[["sid", "district_id"]], on="sid")
park_d = set(tg[tg.treated_any == 1].district_id)
D["dg"] = D.district_id.map(lambda d: "Kigali" if d in (11, 12, 13) else ("Park districts" if d in park_d else "Other districts"))
P["dg"] = P.district_id.map(lambda d: "Kigali" if d in (11, 12, 13) else ("Park districts" if d in park_d else "Other districts"))
T = P.groupby(["year", "dg"]).apply(wmed, include_groups=False).unstack() / 1e3
T["N parcels"] = P.groupby("year").size()
T.to_csv(OUT_T / "T15_land_rent_by_group.csv")
(OUT_T / "T15_land_rent_by_group.tex").write_text(T.to_latex(float_format=lambda v: f"{v:,.1f}", caption="Median real land rent per hectare per year (000 2014 RWF), rented parcels, by district group. EICV 2001--2017; AHS 2024.", label="tab:T15", position="htbp"))
print(P.groupby("year").agg(n=("rent", "size"), med_rent=("rent", "median"), med_area=("area_ha", "median")).round(3)); print(T.round(1))
