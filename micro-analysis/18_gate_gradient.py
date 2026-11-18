"""Distance-to-gate gradient, park by park (pooled estimation).
Sample: sectors whose nearest pre-2005 gate is within 40 km, excluding the City of Kigali and the four largest towns of 2002.
  Volcanoes: Kinigi HQ; Nyungwe: Kitabi and Bushekeri (nearest); Akagera: Mwiri (southern entrance).
Model: dy_n = sum_p sum_{b in 0-10, 10-20} beta_pb 1{park p, bin b} + park FE + gamma dln Pop_n + e_n,
  reference bin 20-40 km within each park. Census outcomes: change 2002->2022. Land: GLCLU 2005->2020, share of usable land.
  dln Pop: Census 2002->2022, all residents. SE clustered by district; wild cluster restricted bootstrap p (Webb, 9,999)."""
import numpy as np, pandas as pd, matplotlib.pyplot as plt
from _common import *
from _reg import fe_ols

d = pd.read_csv(OUT_D / "sector_panel_desc.csv")
pop = pd.read_csv(OUT_D / "sector_pop_total.csv")
cross = pd.read_csv(ANA / "model_sector_cross.csv")[["sid", "lon", "lat"]]
d = d.merge(pop, on=["sid", "wave"]).merge(cross, on="sid")
d["sh_tour"] = (d.n_I + d.n_H + d.n_R) / d.workers
w = d.pivot(index="sid", columns="wave")
X = pd.DataFrame(index=w.index)
for v in ["lam", "sh_tour", "sh_svc"]: X[f"d_{v}"] = 100 * (w[v][2022] - w[v][2002])          # pp
X["dlnpop"] = np.log(w.pop_total[2022] / w.pop_total[2002])
lnd = pd.read_csv(OUT_D / "sector_cropland_builtup_glclu.csv").pivot(index="sid", columns="year")
for v in ["crop_sh", "built_sh"]: X[f"d_{v}"] = 100 * (lnd[v][2020] - lnd[v][2005])          # pp of usable land
f = w.xs(2002, axis=1, level=1)
X["district_id"] = f.district_id; X["group"] = f.group; X["sector"] = f.sector

def hav(lon1, lat1, lon2, lat2):
    r = np.radians; a = np.sin(r(lat2 - lat1) / 2) ** 2 + np.cos(r(lat1)) * np.cos(r(lat2)) * np.sin(r(lon2 - lon1) / 2) ** 2
    return 6371 * 2 * np.arcsin(np.sqrt(a))
GATES = {"Volcanoes": [(29.59528, -1.43165)], "Nyungwe": [(29.09228, -2.44059), (29.41697, -2.52640)], "Akagera": [(30.68178, -1.89912)]}
K = pd.DataFrame({p: np.min([hav(f.lon, f.lat, *g) for g in xy], axis=0) for p, xy in GATES.items()}, index=f.index)
X["park"] = K.idxmin(axis=1); X["km"] = K.min(axis=1)
X = X[(X.km <= 40) & ~X.group.isin(["Kigali", "Towns"])].copy()
BINS = [(0, 10), (10, 20), (20, 40)]; BL = ["0-10", "10-20", "20-40"]
X["bin"] = pd.cut(X.km, [b[0] for b in BINS] + [40.001], labels=BL, right=False)
print(pd.crosstab(X.park, X.bin)); print("districts:", X.district_id.nunique())
print("0-10 km sectors:", X[X.bin == "0-10"].groupby("park").sector.apply(list).to_dict())
REG = []
for p in GATES:
    for b in BL[:2]:
        c = f"{p}_{b}"; X[c] = ((X.park == p) & (X.bin == b)).astype(float); REG.append(c)
X.to_csv(OUT_D / "gate_gradient_sample.csv")

OUT = {"d_lam": "$\\lambda$ (pp)", "d_sh_tour": "Tourism share (pp)", "d_sh_svc": "Services share (pp)",
       "d_crop_sh": "Cropland share (pp)", "d_built_sh": "Built-up share (pp)"}
rows = []
for y, lab in OUT.items():
    r, n, g = fe_ols(X, y, REG + ["dlnpop"], ["park"], "district_id")
    for c in REG + ["dlnpop"]:
        p, b = (c.split("_", 1) + [""])[:2] if c != "dlnpop" else ("", "")
        rows.append(dict(outcome=lab, term=c, park=p, bin=b, coef=r.loc[c, "coef"], se=r.loc[c, "se"], p_wcb=r.loc[c, "p_wcb"], N=n, G=g,
                         ref_mean=X[X.bin == "20-40"][y].mean()))
R = pd.DataFrame(rows); R.to_csv(OUT_T / "T18_gate_gradient_long.csv", index=False)
print(R.pivot_table(index=["park", "bin"], columns="outcome", values="coef").round(2).to_string())
print(R.pivot_table(index=["park", "bin"], columns="outcome", values="p_wcb").round(3).to_string())

# figure
PC = {"Volcanoes": "#c1121f", "Nyungwe": "#2a9d8f", "Akagera": "#e9a03b"}
xs = {"0-10": 5, "10-20": 15, "20-40": 30}
fig, axes = plt.subplots(1, 5, figsize=(16, 3.6), sharex=True)
for ax, (y, lab) in zip(axes, OUT.items()):
    for k, p in enumerate(GATES):
        s = R[(R.outcome == lab) & (R.park == p)].set_index("bin")
        xx = [xs[b] + (k - 1) * 0.6 for b in BL]; cc = [s.coef.get(b, 0.0) for b in BL[:2]] + [0.0]
        ee = [1.96 * s.se.get(b, 0.0) for b in BL[:2]] + [0.0]
        ax.errorbar(xx, cc, yerr=ee, color=PC[p], marker="o", ms=4, lw=1.3, capsize=2, label=p)
        for xi, b in zip(xx[:2], BL[:2]):
            if s.p_wcb.get(b, 1) < .1: ax.plot(xi, s.coef[b], marker="o", ms=8, mfc="none", mec=PC[p], mew=1.2)
    ax.axhline(0, color="0.4", lw=0.8); ax.set_title(lab, fontsize=9)
    ax.set_xticks([5, 15, 30]); ax.set_xticklabels(["0-10", "10-20", "20-40\n(ref.)"], fontsize=7.5)
    ax.tick_params(labelsize=7.5); ax.grid(axis="y", alpha=.3)
axes[0].set_ylabel("Difference vs 20-40 km (pp)", fontsize=8.5); axes[2].set_xlabel("km to nearest pre-2005 gate", fontsize=8.5)
axes[0].legend(fontsize=7.5, frameon=False, loc="best")
fig.suptitle("Change 2002-2022 (land: 2005-2020) by distance to the park gate, relative to sectors 20-40 km away, at equal population growth",
             fontsize=9.5, x=0.01, ha="left")
fig.text(0.01, -0.06, "Bars: 95% CI, SE clustered by district. Open circle: wild cluster bootstrap p < 0.10. Park fixed effects; control for change in log population. "
         "Kigali and the four largest 2002 towns excluded.", fontsize=7, color="0.35")
fig.tight_layout()
fig.savefig(OUT_F / "fig18_gate_gradient.pdf", bbox_inches="tight"); fig.savefig(OUT_F / "fig18_gate_gradient.png", dpi=250, bbox_inches="tight")
