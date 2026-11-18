"""Summary-stat tables T1-T7 on the repo treatment groups. Writes to output/tables/summary_statistics (names in _common.TABLE_NAMES).
Treated = bordering Volcanoes/Nyungwe/Akagera or near a pre-2005 gate (44); Control = 328; Urban = Kigali (35) + 2002 towns (9)."""
import os, numpy as np, pandas as pd, statsmodels.formula.api as smf
from _common import *

d = pd.read_csv(OUT_D / "sector_panel_desc.csv")
cb = pd.read_csv(OUT_D / "sector_cropland_builtup_glclu.csv")
tg = pd.read_csv(OUT_D / "treatment_groups.csv")
cross = pd.read_csv(ANA / "model_sector_cross.csv")[["sid", "district_id"]]
tg = tg.merge(cross, on="sid")
d["sample"] = np.select([d.treated_any == 1, d.control == 1], ["Treated", "Control"], "Urban")
d["near_gate"] = d.group.isin(["Gates", "Gates+"]).astype(int)

def tex(df, name, cap, fmt="{:,.3f}", idx=True):
    df.to_csv(OUT_T / f"{name}.csv", index=idx)
    s = df.to_latex(float_format=lambda x: fmt.format(x), na_rep="--", caption=cap, label=f"tab:{name}", position="htbp", index=idx, escape=True)
    (OUT_T / f"{name}.tex").write_text(s)

# ---------- T1 national employment ----------
j = pd.read_csv(OUT_D / "sector_jobs_panel.csv")
n = j.groupby("wave")[["AG", "IND", "S_tour", "S_bus", "S_loc", "S_broad", "workers"]].sum()
lab = {"AG": "Agriculture", "IND": "Industry (B-F)", "S_tour": "Tourism services (I, R)", "S_bus": "Business services (J, K, M)",
       "S_loc": "Local services (G, H, L, N-Q, S-U)", "S_broad": "Services excl. trade and govt (memo)", "workers": "Total"}
t1 = pd.DataFrame(index=[lab[c] for c in n.columns])
for w in [2002, 2012, 2022]:
    t1[f"{w} (000s)"] = (n.loc[w] / 1e3).values
for w in [2002, 2012, 2022]:
    t1[f"{w} share"] = (n.loc[w] / n.loc[w, "workers"]).values
t1["growth p.a. 02-12"] = ((n.loc[2012] / n.loc[2002]) ** 0.1 - 1).values
t1["growth p.a. 12-22"] = ((n.loc[2022] / n.loc[2012]) ** 0.1 - 1).values
tex(t1, "T1_national_employment", "Workers aged 20--64 by sector, Census 2002/2012/2022 (10\\% public-use samples, weighted). 2022 agriculture is the reconstructed own-use-inclusive count (recorded: 1.69M).")

# ---------- T2 model objects by group x wave ----------
V = [("workers", "Workers (H)"), ("density", "Workers per km2 usable land"), ("lam", "lambda: ag / (ag + svc excl. G,O)"),
     ("sh_ag", "Agriculture share of workers"), ("sh_tour", "Tourism svc share"), ("sh_svc", "Svc excl. G,O share"),
     ("crop_sh", "Cropland share of usable land"), ("built_sh", "Built-up share"), ("tree_sh", "Tree-cover share"),
     ("ell", "ell: crop / (crop + built)"), ("k_a", "k_a: crop ha per farm worker"), ("k_s", "k_s: built ha per svc worker"),
     ("c", "c = k_a / k_s"), ("eps_model", "eps_L implied (1-ell)/(1-lambda)"), ("inmig_share", "In-migrant share"),
     ("ntl_chen_asinh", "Night lights asinh(sum)")]
rows = []
for gname, m in [("Treated (44)", d["sample"] == "Treated"), ("  of which near gate (12)", d.near_gate == 1), ("Control (328)", d["sample"] == "Control"), ("Urban (44)", d["sample"] == "Urban")]:
    for v, vl in V:
        r = {"Variable": vl, "Group": gname}
        for w in [2002, 2012, 2022]:
            x = d[m & (d.wave == w)][v].replace([np.inf, -np.inf], np.nan).dropna()
            r.update({f"{w} mean": x.mean(), f"{w} sd": x.std(), f"{w} p10": x.quantile(.1), f"{w} p50": x.median(), f"{w} p90": x.quantile(.9)})
        rows.append(r)
t2 = pd.DataFrame(rows).set_index(["Variable", "Group"]).sort_index(level=0, sort_remaining=False)
t2 = t2.loc[[vl for _, vl in V]]
t2.to_csv(OUT_T / "T2_model_objects_full.csv")
t2s = t2[[c for c in t2.columns if c.endswith(("mean", "sd", "p50"))]]
tex(t2s, "T2_model_objects", "Model objects by group and Census wave: mean, SD and median across sectors (p10/p90 in the CSV). Land is GLCLU 2000/2010/2020 matched to the 2002/2012/2022 waves; in-migrant share is missing in 2002.")

# ---------- T3 balance: three treatment definitions vs control ----------
w = d.pivot_table(index="sid", columns="wave", values=["lam", "sh_tour", "sh_svc", "log_workers", "crop_sh", "built_sh", "tree_sh", "ell", "ntl_chen_asinh", "density"])
B = pd.DataFrame(index=w.index)
for v in ["lam", "sh_tour", "sh_svc", "log_workers", "crop_sh", "built_sh", "tree_sh", "ell", "ntl_chen_asinh", "density"]:
    B[f"{v} 2002"] = w[v][2002]; B[f"d {v} 02-12"] = w[v][2012] - w[v][2002]; B[f"d {v} 12-22"] = w[v][2022] - w[v][2012]
B = B.join(tg.set_index("sid")[["gates", "near_gates", "border", "treated_any", "control", "district_id"]])
defs = [("Bordering or near gate (44)", B.treated_any == 1), ("Near a gate (12)", B.near_gates == 1), ("Gate sectors (4)", B.gates == 1)]
rows = []
for col in [c for c in B.columns if c.endswith(("2002", "02-12", "12-22")) and not c.startswith("d ") or c.startswith("d ")]:
    r = {"Variable": col, "Control mean": B.loc[B.control == 1, col].mean()}
    for dn, m in defs:
        s = B[(m) | (B.control == 1)].copy(); s["T"] = m[s.index].astype(int); s = s.dropna(subset=[col])
        f = smf.ols(f"Q('{col}') ~ T", s).fit(cov_type="cluster", cov_kwds={"groups": s.district_id})
        r[f"{dn}: mean"] = s.loc[s["T"] == 1, col].mean(); r[f"{dn}: diff"] = f.params["T"]; r[f"{dn}: se"] = f.bse["T"]
    rows.append(r)
t3 = pd.DataFrame(rows).set_index("Variable")
order = [f"{v} 2002" for v in ["lam", "sh_tour", "sh_svc", "log_workers", "density", "crop_sh", "built_sh", "tree_sh", "ell", "ntl_chen_asinh"]] + \
        [f"d {v} {p}" for p in ["02-12", "12-22"] for v in ["lam", "sh_tour", "sh_svc", "log_workers", "density", "crop_sh", "built_sh", "tree_sh", "ell", "ntl_chen_asinh"]]
t3 = t3.loc[order]
tex(t3, "T3_balance_treated_control", "Treated vs control (328 sectors, Kigali and the four 2002 towns excluded), three treatment definitions as in map3. Diff = OLS on a treatment dummy, SE clustered by district. With 4 gate sectors in 3 districts the gate-sector SEs are not reliable. Land and lights use 2000/2010/2020 for the 2002/2012/2022 columns.")

# ---------- T4 per park ----------
pk_rows = []
for p in ["Volcanoes", "Nyungwe", "Akagera"]:
    for gname, m in [("Near gate (Gates + Gates+)", d.near_gate == 1), ("Bordering only", d.group == "Bordering"), ("Control, same park side", d.control == 1)]:
        s = d[(d.park == p) & m]
        if not len(s): continue
        r = {"Park": p, "Group": gname, "Sectors": s.sid.nunique()}
        for wv in [2002, 2012, 2022]:
            x = s[s.wave == wv]; A = x[["AG", "S_tour", "S_broad", "workers", "crop", "built", "tree", "other"]].sum()
            r[f"Workers {wv} (000s)"] = A.workers / 1e3; r[f"lambda {wv}"] = A.AG / (A.AG + A.S_broad); r[f"Tourism sh {wv}"] = A.S_tour / A.workers
            u = A[["crop", "built", "tree", "other"]].sum(); r[f"Crop sh {wv-2}"] = A.crop / u; r[f"Built sh {wv-2}"] = A.built / u; r[f"Tree sh {wv-2}"] = A.tree / u
        pk_rows.append(r)
t4 = pd.DataFrame(pk_rows).set_index(["Park", "Group"])
tex(t4[[c for c in t4.columns if c.startswith(("Sectors", "Workers", "lambda", "Tourism"))]], "T4a_parks_jobs", "Jobs by park side and group, aggregated within group (Census).")
tex(t4[[c for c in t4.columns if c.startswith(("Crop", "Built", "Tree"))]], "T4b_parks_land", "Land use by park side and group, share of usable land outside parks, aggregated within group (GLCLU).")
vis = pd.read_csv(DATA / "Tourism Data" / "park_visitors_by_park.csv").set_index("year")
t4c = pd.DataFrame({p.capitalize(): [vis.loc[2005, p], vis.loc[2012, p], vis.loc[2019, p], vis.loc[2020, p], vis.loc[2023, p]] for p in ["volcanoes", "nyungwe", "akagera"]},
                   index=["2005", "2012", "2019", "2020", "2023"]).T
t4c["growth 2005-19 p.a."] = (t4c["2019"] / t4c["2005"]) ** (1 / 14) - 1
tex(t4c, "T4c_park_visitors", "Park visitors (RDB annual reports).", "{:,.3f}")

# ---------- T5 transitions ----------
T = pd.read_csv(OUT_D / "glclu_transitions_2000_2020.csv")
T["agg_"] = T.group.map({"Gates": "Treated", "Gates+": "Treated", "Bordering": "Treated", "Control": "Control", "Towns": "Urban", "Kigali": "Urban"})
cl = ["crop", "built", "tree", "other"]; out = []
for a in ["Treated", "Control", "Urban"]:
    M = T[(T.agg_ == a) & T["from"].isin(cl) & T.to.isin(cl)].pivot_table(index="from", columns="to", values="ha", aggfunc="sum").loc[cl, cl]
    R = M.div(M.sum(1), axis=0)
    for f_ in cl:
        out.append({"Group": a, "2000 class": f_, "2000 ha (000s)": M.loc[f_].sum() / 1e3, **{f"to {t} (row share)": R.loc[f_, t] for t in cl}})
    # source of new cropland
    newcrop = M.loc[["built", "tree", "other"], "crop"]; out.append({"Group": a, "2000 class": "memo: sources of 2020 cropland not cropland in 2000",
              **{f"to {t} (row share)": (newcrop.get(t, np.nan) / newcrop.sum()) if t != "crop" else np.nan for t in cl}, "2000 ha (000s)": newcrop.sum() / 1e3})
t5 = pd.DataFrame(out).set_index(["Group", "2000 class"])
tex(t5, "T5_land_transitions", "GLCLU land transitions 2000 to 2020, outside parks. Rows: 2000 class; columns: share of that land in each 2020 class. Built-up loss is not mapped in GLCLU v2.")

# ---------- T6 output panel ----------
park_d = set(tg[tg.treated_any == 1].district_id); kig = {11, 12, 13}
dg = lambda di: "Kigali" if di in kig else ("Park districts" if di in park_d else "Other districts")
ag = pd.read_csv(OUT_D / "district_ag_output.csv"); ag["dg"] = ag.district_id.map(dg)
a6 = ag.groupby(["dg", "year"])[["v", "ha"]].sum(min_count=1); a6 = pd.DataFrame({"Crop value (bn RWF, fixed prices)": a6.v / 1e9, "Value per ha (000 RWF)": a6.v / a6.ha / 1e3}).unstack(0)
ec = pd.read_csv(OUT_D / "district_ec_output.csv"); ec["dg"] = ec.district_id.map(dg); ec = ec[ec.year > 2011]
e6 = ec.groupby(["year", "dg", "grp"])[["turnover", "emp_rep", "emp"]].sum()
e6 = pd.DataFrame({"Turnover per reporting worker (m 2014 RWF)": e6.turnover / e6.emp_rep / 1e6, "Workers (000s)": e6.emp / 1e3}).unstack("grp")
nl = pd.read_csv(OUT_D / "sector_ntl.csv").merge(d[["sid", "sample"]].drop_duplicates(), on="sid")
n6 = nl[nl.year.isin([2000, 2005, 2010, 2015, 2020, 2025])].groupby(["year", "sample"])[["ntl_chen_asinh", "ntl_li_asinh"]].mean().unstack("sample")
tex(a6, "T6a_output_agriculture", "SAS crop output by district group. Park districts = districts containing a treated sector (13). 2021 and 2024 have no area variable.", "{:,.1f}")
tex(e6, "T6b_output_services", "Establishment Census by district group and ISIC group. Turnover is bracketed (midpoints; >50M RWF top-coded at 100M), CPI-deflated.", "{:,.2f}")
tex(n6, "T6c_output_nightlights", "Mean night lights per sector, asinh(sum), Chen (VIIRS-like) and Li (DMSP-like) harmonised products.", "{:,.2f}")

# ---------- T7 earnings ----------
l = pd.read_parquet(os.path.expanduser("~/lfs_sub.parquet"))
l = l[(l.lfs_employment_status == 1) & l.lfs_monthly_cash_income.gt(0) & l.lfs_age.between(16, 64)]
l["sec"] = l.lfs_industry_isic.map(lambda x: SEC.get(int(x)) if pd.notna(x) and int(x) in SEC else None)
l["grp"] = l.sec.map(GROUP); l = l.dropna(subset=["grp"])
cpi = pd.read_csv(DATA / "Tourism Data" / "world_bank_wdi.csv").query("country=='RWA' and indicator_code=='FP.CPI.TOTL'").set_index("year").value
l["real"] = l.lfs_monthly_cash_income / l.lfs_year.map(lambda y: cpi.get(min(y, cpi.dropna().index.max())) / cpi[2014])
l["dg"] = l.lfs_district.map(dg)
l["period"] = pd.cut(l.lfs_year, [2016, 2019, 2021, 2025], labels=["2017-19", "2020-21", "2022-25"])
def wq(x, w, q):
    o = np.argsort(x.values); cx = np.cumsum(w.values[o]); return x.values[o][np.searchsorted(cx, q * cx[-1])]
rows = []
for (p, g_, s), x in l.groupby(["period", "dg", "grp"], observed=True):
    rows.append({"Period": p, "District group": g_, "Sector": s, "N": len(x), "Median (000 2014 RWF/month)": wq(x.real, x.lfs_weight, .5) / 1e3,
                 "Mean": np.average(x.real, weights=x.lfs_weight) / 1e3})
t7 = pd.DataFrame(rows)
piv = t7.pivot_table(index=["Period", "District group"], columns="Sector", values="Median (000 2014 RWF/month)")
piv["Tourism / Agriculture"] = piv.S_tour / piv.AG; piv["Local svc / Agriculture"] = piv.S_loc / piv.AG
t7.to_csv(OUT_T / "T7_earnings_long.csv", index=False)
tex(piv, "T7_earnings_ratios", "Median real monthly cash earnings of employees aged 16--64 (000 2014 RWF, LFS, weighted) by sector and district group, with ratios to agriculture. Employees only: own-account farmers have no wage, so these are wages of hired workers.", "{:,.2f}")

pd.set_option("display.width", 220, "display.max_columns", 30)
for nme, t in [("T1", t1), ("T3", t3), ("T4a", t4.iloc[:, :10]), ("T5", t5), ("T7", piv)]:
    print("=====", nme); print(t.round(3).to_string())
