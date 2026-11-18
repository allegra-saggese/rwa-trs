"""Park-visitor shift-share (Bartik) exposure, stacked first differences.

Shares   s_np = exp(-km from sector n's centroid to park p's nearest pre-2005 gate / 10), p in {Volcanoes, Nyungwe, Akagera}
         (Nyungwe has two gates: Kitabi, Bushekeri; nearest used). Fixed over time.
Shocks   g_pt = change in ln visitors to park p. Period 1 (Census 2002->2012): ln V_2012 - ln V_2005 (series starts 2005).
         Period 2 (2012->2022): ln V_2019 - ln V_2012 (2020-22 are COVID years).
Bartik   B_nt = sum_p s_np g_pt.
Model    dy_nt = beta B_nt + gamma_t S_n + province x period FE + e_nt,   S_n = sum_p s_np (incomplete-shares control, BHJ 2022).
Outcomes: Census changes over each period (lambda, tourism share I+H+R, services share, ln pop, ln farm workers, ln services workers,
         night lights) and land changes measured after each Census (GLCLU 2005->2015 and 2015->2020).
Sample:  non-urban sectors excluding Kigali, the four 2002 towns and the nine Gishwati-Mukura neighbours (as Table 6, Panel C).
Inference: clustered by district; wild cluster restricted bootstrap (Webb, 9,999). Only 3 parks x 2 periods = 6 shocks."""
import numpy as np, pandas as pd
from _common import *
from _reg import fe_ols

d = pd.read_csv(OUT_D / "sector_panel_desc.csv")
tg = pd.read_csv(OUT_D / "treatment_groups.csv")[["sid", "gish"]]
pop = pd.read_csv(OUT_D / "sector_pop_total.csv")
cross = pd.read_csv(ANA / "model_sector_cross.csv")[["sid", "lon", "lat"]]
d = d.drop(columns=["gish"], errors="ignore").merge(tg, on="sid").merge(pop, on=["sid", "wave"]).merge(cross, on="sid")
d["ln_pop"] = np.log(d.pop_total); d["ln_Na"] = np.log(d.AG); d["ln_Ns"] = np.log(d.S_broad.replace(0, np.nan))
d["sh_tour"] = (d.n_I + d.n_H + d.n_R) / d.workers

def hav(lon1, lat1, lon2, lat2):
    r = np.radians; a = np.sin(r(lat2 - lat1) / 2) ** 2 + np.cos(r(lat1)) * np.cos(r(lat2)) * np.sin(r(lon2 - lon1) / 2) ** 2
    return 6371 * 2 * np.arcsin(np.sqrt(a))
GATES = {"volcanoes": [(29.59528, -1.43165)], "nyungwe": [(29.09228, -2.44059), (29.41697, -2.52640)], "akagera": [(30.68178, -1.89912)]}
for p, xy in GATES.items():
    d[f"km_{p}"] = np.min([hav(d.lon, d.lat, *g) for g in xy], axis=0)
    d[f"s_{p}"] = np.exp(-d[f"km_{p}"] / 10)

vis = pd.read_csv(DATA / "Tourism Data" / "park_visitors_by_park.csv").set_index("year")
G = {1: {p: np.log(vis.loc[2012, p] / vis.loc[2005, p]) for p in GATES},
     2: {p: np.log(vis.loc[2019, p] / vis.loc[2012, p]) for p in GATES}}
print("shocks (dln visitors):", {t: {p: round(v, 3) for p, v in g.items()} for t, g in G.items()})

urb = pd.read_csv(OUT_D / "sector_urban_share.csv")
den = pd.read_csv(OUT_D / "sector_pop_density.csv", index_col=0).rename(columns=int).stack().rename("dens").reset_index()
den.columns = ["sid", "wave", "dens"]
d = d.merge(urb, on=["sid", "wave"]).merge(den, on=["sid", "wave"])
import geopandas as gpd
sg = gpd.read_file(DATA / "geo-data" / "protected-areas" / "sectors_park_exposure_geodatarw.gpkg").to_crs(32736)
sg["sid"] = sg.sector_id.astype(int); sg = sg.set_index("sid")
towns = sg.loc[sg.index.isin(d[d.group.isin(["Kigali", "Towns"])].sid.unique())].union_all()
d["adj_town"] = d.sid.map(sg.geometry.buffer(50).intersects(towns).astype(int))
w = d.pivot(index="sid", columns="wave")
lnd = pd.read_csv(OUT_D / "sector_cropland_builtup_glclu.csv").pivot(index="sid", columns="year")
rows = []
for t, (a, b), (la, lb) in [(1, (2002, 2012), (2005, 2015)), (2, (2012, 2022), (2015, 2020))]:
    x = pd.DataFrame(index=w.index)
    for v in ["lam", "sh_tour", "sh_svc", "ln_pop", "ln_Na", "ln_Ns", "ntl_chen_asinh"]:
        x[f"d_{v}"] = w[v][b] - w[v][a]
    for v in ["crop_sh", "built_sh"]:
        x[f"d_{v}"] = lnd[v][lb] - lnd[v][la]
    first = w.xs(a, axis=1, level=1)
    x["B"] = sum(first[f"s_{p}"] * G[t][p] for p in GATES)
    x["S"] = sum(first[f"s_{p}"] for p in GATES)
    x["ln_dens0"] = np.log(first.dens); x["town0"] = (first.urban_sh > 0).astype(int); x["adj_town"] = first.adj_town
    x["period"] = t; x["district_id"] = first.district_id; x["prov_t"] = first.province_id.astype(str) + f"_{t}"
    x["keep"] = (first.urban == 0) & (first.gish == 0) & ~first.group.isin(["Kigali", "Towns"])
    rows.append(x.reset_index())
X = pd.concat(rows); X = X[X.keep]
for t in (1, 2):
    for c in ("S", "ln_dens0", "town0", "adj_town"): X[f"{c}_{t}"] = X[c] * (X.period == t)
print("town0 share:", X.groupby("period").town0.mean().round(2).to_dict(), "adj_town sectors:", X[X.adj_town == 1].sid.nunique())
X.to_csv(OUT_D / "shift_share_stacked.csv", index=False)
print("sectors:", X.sid.nunique(), "obs:", len(X), "| B: mean", X.B.mean().round(3), "p99", X.B.quantile(.99).round(3), "max", X.B.max().round(3),
      "| share of obs with B>0.1:", (X.B > 0.1).mean().round(3))

OUT = {"d_lam": "$\\Delta\\lambda$", "d_sh_tour": "$\\Delta$ Tourism share", "d_sh_svc": "$\\Delta$ Services share",
       "d_ln_pop": "$\\Delta$ ln population", "d_ln_Na": "$\\Delta$ ln farm workers", "d_ln_Ns": "$\\Delta$ ln services workers",
       "d_ntl_chen_asinh": "$\\Delta$ Night lights", "d_crop_sh": "$\\Delta$ Cropland share", "d_built_sh": "$\\Delta$ Built-up share"}
SPECS = {"A": [], "B": ["ln_dens0_1", "ln_dens0_2", "town0_1", "town0_2"],
         "C": ["ln_dens0_1", "ln_dens0_2", "town0_1", "town0_2", "adj_town_1", "adj_town_2"]}
res = []
for sp, ctl in SPECS.items():
    for y, lab in OUT.items():
        r, n, g = fe_ols(X, y, ["B", "S_1", "S_2"] + ctl, ["prov_t"], "district_id")
        res.append(dict(spec=sp, outcome=lab, coef=r.loc["B", "coef"], se=r.loc["B", "se"], p=r.loc["B", "p_wcb"], N=n, G=g, mean=X[y].mean()))
R = pd.DataFrame(res); R.to_csv(OUT_T / "T17_shift_share_long.csv", index=False)
print(R.pivot(index="outcome", columns="spec", values=["coef", "p"]).round(3).to_string())

st = lambda p: "^{***}" if p < .01 else "^{**}" if p < .05 else "^{*}" if p < .1 else ""
def tab(R, outs, cap, lab, note):
    k = len(outs); L = []
    L += [r"\begin{table}[!htbp]\centering\footnotesize", rf"\caption{{{cap}}}\label{{{lab}}}", r"\begin{tabular}{l" + "c" * k + "}", r"\toprule"]
    L += [" & " + " & ".join(f"({i+1})" for i in range(k)) + r" \\"]
    L += [" & " + " & ".join(r"\shortstack{" + o.replace("$\\Delta$ ", "$\\Delta$ \\\\ ").replace(" share", " \\\\ share").replace(" workers", " \\\\ workers") + "}" for o in outs) + r" \\", r"\midrule"]
    PT = {"A": "Panel A. Baseline", "B": "Panel B. Adding ln population density and urban-area indicator, start of period $\\times$ period",
          "C": "Panel C. Panel B plus adjacent to a large town $\\times$ period"}
    for sp in "ABC":
        sub = R[(R.spec == sp)].set_index("outcome").loc[outs]
        L += [rf"\multicolumn{{{k+1}}}{{l}}{{\textit{{{PT[sp]}}}}} \\"]
        L += [r"Visitor shift-share $B_{nt}$ & " + " & ".join(f"${c:.3f}{st(p)}$" for c, p in zip(sub.coef, sub.p)) + r" \\"]
        L += [" & " + " & ".join(f"({x:.3f})" for x in sub.se) + r" \\", " & " + " & ".join(f"[{p:.3f}]" for p in sub.p) + r" \\"]
    sub = R[R.spec == "A"].set_index("outcome").loc[outs]
    L += [r"\midrule", r"Mean of outcome & " + " & ".join(f"{m:.3f}" for m in sub["mean"]) + r" \\"]
    L += [r"Sum of shares $\times$ period & " + " & ".join(["Yes"] * k) + r" \\", r"Province $\times$ period FE & " + " & ".join(["Yes"] * k) + r" \\"]
    L += [r"Observations & " + " & ".join(str(n) for n in sub.N) + r" \\", r"Clusters (districts) & " + " & ".join(str(g) for g in sub.G) + r" \\", r"\bottomrule\end{tabular}"]
    L += [r"\begin{minipage}{0.95\linewidth}\vspace{4pt}\footnotesize\textit{Notes:} " + note + r"\end{minipage}\end{table}"]
    return "\n".join(L)
NOTE = (r"Stacked first differences over two periods. $B_{nt}=\sum_p s_{np}\,g_{pt}$, where $s_{np}=\exp(-\text{km to park } p\text{'s nearest pre-2005 gate}/10)$ "
        r"and $g_{pt}$ is the change in log visitors to park $p$ (Volcanoes, Nyungwe, Akagera): 2005--2012 for the 2002--2012 Census period, "
        r"2012--2019 for 2012--2022. Shocks: Volcanoes 1.00, 0.20; Nyungwe 1.16, 0.85; Akagera 0.81, 0.84. Controls: the sum of shares interacted "
        r"with period (incomplete shares; Borusyak, Hull and Jaravel 2022) and province $\times$ period fixed effects. Land changes are measured after "
        r"each Census: GLCLU 2005--2015 and 2015--2020. Sample: non-urban sectors, excluding the City of Kigali, the four largest towns of 2002 and the "
        r"nine Gishwati-Mukura neighbours. Panel B adds, interacted with period, log population per km$^2$ of usable land and an indicator that the "
        r"Census classifies any of the sector's population as urban, both at the start of the period. Panel C adds an indicator that the sector touches "
        r"Kigali or one of the four largest towns. Identification rests on six park-period shocks. Standard errors clustered by district in parentheses; "
        r"wild cluster restricted bootstrap $p$-values (Webb, 9,999 replications) in brackets; stars refer to these $p$-values: "
        r"$^{***}p<0.01$, $^{**}p<0.05$, $^{*}p<0.1$.")
O = list(OUT.values())
t1 = tab(R, O[:7], "Park-Visitor Shift-Share: Employment, Population and Night Lights", "tab:ssjobs", NOTE)
t2 = tab(R, O[7:], "Park-Visitor Shift-Share: Land Use", "tab:ssland", NOTE)
(OUT_T / "paper").mkdir(exist_ok=True)
(OUT_T / "paper" / "tab11_shift_share_jobs.tex").write_text(t1.replace(r"\centering\small", r"\centering\footnotesize"))
(OUT_T / "paper" / "tab12_shift_share_land.tex").write_text(t2)
