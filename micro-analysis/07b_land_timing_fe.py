"""Table 1b: fixed-effect variants of Table 1 (Census 2002/2012, land after = GLCLU 2005/2015): wave only, province x wave,
district x wave (Table 1), all with sector FE and park-border x wave."""
import numpy as np, pandas as pd
from _common import *
from _reg import fe_ols
d = pd.read_csv(OUT_D / "sector_panel_desc.csv"); tg = pd.read_csv(OUT_D / "treatment_groups.csv"); pop = pd.read_csv(OUT_D / "sector_pop_total.csv")
cb = pd.read_csv(OUT_D / "sector_cropland_builtup_glclu.csv")
d = d[[c for c in d.columns if not c.endswith("_sh") and c not in ("crop", "built", "tree", "other", "usable", "ell")]]
d = d.merge(tg[["sid"] + [c for c in tg.columns if c.startswith("border_")]], on="sid").merge(pop, on=["sid", "wave"])
d = d[d.urban == 0].copy(); d["ln_pop"] = np.log(d.pop_total)
d["dw"] = d.district_id.astype(str) + "_" + d.wave.astype(str); d["pw"] = d.province_id.astype(str) + "_" + d.wave.astype(str)
pk = []
for p in ["volcanoes", "nyungwe", "akagera", "gishwati"]:
    for w in [2012, 2022]: d[f"b_{p}_{w}"] = d[f"border_{p}"] * (d.wave == w); pk.append(f"b_{p}_{w}")
Y = {"crop_sh": "Cropland", "built_sh": "Built-up", "tree_sh": "Tree cover", "other_sh": "Short veg./bare"}
def merge_land(df, m):
    L = cb[["sid", "year"] + list(Y)].copy(); L["wave"] = L.year.map(m)
    return df.merge(L.dropna(subset=["wave"]).drop(columns="year"), on=["sid", "wave"])
rows = []
# fixed-effect variants on the Table 1 sample: Census 2002/2012, land after (GLCLU 2005/2015)
s = merge_land(d[d.wave.isin([2002, 2012])], {2005: 2002, 2015: 2012})
pk12 = [c for c in pk if c.endswith("2012")]
for lab, fe in [("Wave FE", ["sid", "wave"]), ("Province x wave FE", ["sid", "pw"]), ("District x wave FE (Table 1)", ["sid", "dw"])]:
    for y, yl in Y.items():
        r, n, G = fe_ols(s, y, ["sh_svc", "ln_pop"] + pk12, fe, "district_id")
        for x in ["sh_svc", "ln_pop"]: rows.append(dict(check="Fixed effects", spec=lab, outcome=yl, term=x, coef=r.loc[x, "coef"], se=r.loc[x, "se"], p_wcb=r.loc[x, "p_wcb"], N=n, clusters=G))
R = pd.DataFrame(rows); R.to_csv(OUT_T / "T8b_land_timing_fe_long.csv", index=False)
R["cell"] = R.coef.map("{:.3f}".format) + " (" + R.se.map("{:.3f}".format) + ") [" + R.p_wcb.map("{:.3f}".format) + "]"
pd.set_option("display.width", 250); print(R.pivot_table(index=["check", "term", "spec"], columns="outcome", values="cell", aggfunc="first")[list(Y.values())].to_string())
# share of variation absorbed: within-R2 of sh_svc after each FE set
from _reg import fe_matrix, _resid
for lab, fe in [("Wave", ["sid", "wave"]), ("Province x wave", ["sid", "pw"]), ("District x wave", ["sid", "dw"])]:
    D = fe_matrix(s, fe); v = _resid(s[["sh_svc"]].values, fe_matrix(s, ["sid"]))[:, 0]; w = _resid(s[["sh_svc"]].values, D)[:, 0]
    print(f"{lab}: share of within-sector variance in services share left after FE = {w.var() / v.var():.2f}")
