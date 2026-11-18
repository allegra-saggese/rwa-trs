"""Four land-use regressions (one per use) on the services share of workers and log total population.
 y_k,nt = a_n + d_{district x wave} + sum_p g_{p,t} Border_p + b1 s_nt + b2 ln Pop_nt + e,  k in {crop, built, tree, other}
 Shares of usable land outside parks, measured AFTER the Census: GLCLU 2005 for the 2002 Census and GLCLU 2015 for the
 2012 Census (land three years after jobs). The 2022 Census is not used: no GLCLU year postdates it.
 s = services share of workers (all tertiary excl. G and O), Census workers 20-64. Pop = total resident population (Census).
 Border_p x wave for Volcanoes, Nyungwe, Akagera, Gishwati-Mukura (absorbs park-specific paths, e.g. Akagera resettlement).
 Sample: all non-urban sectors (Kigali and the four 2002 towns excluded). SEs clustered by district; p-values from the
 wild cluster restricted bootstrap (9,999 Rademacher draws).
 Model check: the contract curve ell(lambda) does not depend on H, so b2 = 0 for ell; land shares sum to 1, so b's sum to 0.
 Robustness column: services split into tourism-characteristic (I + H + R) and other services."""
import numpy as np, pandas as pd
from _common import *
from _reg import fe_ols

d = pd.read_csv(OUT_D / "sector_panel_desc.csv")
cb = pd.read_csv(OUT_D / "sector_cropland_builtup_glclu.csv")
LAND_AFTER = {2005: 2002, 2015: 2012}
d = d[d.wave.isin([2002, 2012])].drop(columns=["crop_sh", "built_sh", "tree_sh", "other_sh", "ell", "crop", "built", "tree", "other", "usable"])
L = cb[["sid", "year", "crop_sh", "built_sh", "tree_sh", "other_sh", "ell"]].assign(wave=lambda x: x.year.map(LAND_AFTER)).dropna(subset=["wave"]).drop(columns="year")
d = d.merge(L, on=["sid", "wave"])
tg = pd.read_csv(OUT_D / "treatment_groups.csv")
pop = pd.read_csv(OUT_D / "sector_pop_total.csv")
d = d.drop(columns=[c for c in d.columns if c.startswith("border_")], errors="ignore").merge(
    tg[["sid"] + [c for c in tg.columns if c.startswith("border_")] + ["ring1", "control_clean", "gish"]], on="sid").merge(pop, on=["sid", "wave"])
d = d[d.urban == 0].copy()
d["ln_pop"] = np.log(d.pop_total)
d["sh_tsa"] = (d.n_I + d.n_H + d.n_R) / d.workers
d["sh_svc_other"] = d.sh_svc - (d.n_I + d.n_H + d.n_R - d.n_H * 0) / d.workers + 0   # svc excl. G,O minus I,R ...
d["sh_svc_other"] = (d.S_broad - d.n_I - d.n_R - d.n_H) / d.workers              # H is inside S_broad (only G and O are excluded)
d["dw"] = d.district_id.astype(str) + "_" + d.wave.astype(str)
fes = ["sid", "dw"]
for p in ["volcanoes", "nyungwe", "akagera", "gishwati"]:
    d[f"b_{p}_2012"] = d[f"border_{p}"] * (d.wave == 2012)
pk = [f"b_{p}_2012" for p in ["volcanoes", "nyungwe", "akagera", "gishwati"]]

def run(y, xs, label):
    r, n, G = fe_ols(d, y, xs + pk, fes, "district_id")
    r = r.loc[xs]; r["outcome"] = label; r["N"] = n; r["clusters"] = G
    return r.reset_index().rename(columns={"index": "regressor"})

OUT = {"crop_sh": "Cropland share", "built_sh": "Built-up share", "tree_sh": "Tree-cover share", "other_sh": "Short veg./bare share"}
res = [run(y, ["sh_svc", "ln_pop"], lab).assign(spec="Main") for y, lab in OUT.items()]
res += [run("ell", ["lam", "ln_pop"], "ell = crop/(crop+built)").assign(spec="Model check")]
res += [run(y, ["sh_tsa", "sh_svc_other", "ln_pop"], lab).assign(spec="Tourism split") for y, lab in OUT.items()]
R = pd.concat(res)
R.to_csv(OUT_T / "T8_land_regressions_long.csv", index=False)

# adding-up check for the main spec
m = R[R.spec == "Main"].groupby("regressor").coef.sum()
print("sum of b across the four shares (should be ~0):", m.round(6).to_dict())

def cell(r): 
    stars = "***" if r.p_wcb < .01 else "**" if r.p_wcb < .05 else "*" if r.p_wcb < .1 else ""
    return f"{r.coef:.3f}{stars}"
lab = {"sh_svc": "Services share of workers", "ln_pop": "ln total population", "lam": "lambda", "sh_tsa": "Tourism-char. share (I,H,R)", "sh_svc_other": "Other services share"}
rows = []
for spec in ["Main", "Tourism split", "Model check"]:
    sub = R[R.spec == spec]
    for reg in sub.regressor.unique():
        row = {"Spec": spec, "Regressor": lab[reg]}
        for o in sub.outcome.unique():
            x = sub[(sub.regressor == reg) & (sub.outcome == o)]
            if len(x): x = x.iloc[0]; row[o] = cell(x); row[o + " se"] = f"({x.se:.3f})"; row[o + " p_wcb"] = f"[{x.p_wcb:.3f}]"
        rows.append(row)
T = pd.DataFrame(rows).set_index(["Spec", "Regressor"]).fillna("")
T.to_csv(OUT_T / "T8_land_regressions.csv")
tex = T.to_latex(caption="Land use on services share and log total population. Sector FE, district x wave FE, park-border x wave FE. "
                 f"N = {int(R.N.iloc[0])} sector-waves, {int(R.clusters.iloc[0])} district clusters. SE clustered by district in parentheses; "
                 "wild cluster restricted bootstrap p-values in brackets (9,999 draws); stars from the bootstrap p.", label="tab:T8", position="htbp")
(OUT_T / "T8_land_regressions.tex").write_text(tex)
pd.set_option("display.width", 250); print(R.round(4).to_string(index=False))
