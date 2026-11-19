"""Regressions on the sector panel (2x2 model, reduced form). Writes regression tables to
output/tables/regressions/. Run sector_panel.py first.

Run every section in order:   python micro-analysis/sector_regressions.py
Run some sections:            python micro-analysis/sector_regressions.py --only <name> [<name> ...]
List the sections:            python micro-analysis/sector_regressions.py --list

Sections, in run order:
  land                   (was 07_land_regressions.py) Four land-use regressions (one per use) on the services share of workers and log total population.
  land_timing_fe         (was 07b_land_timing_fe.py) Table 1b: fixed-effect variants of Table 1 (Census 2002/2012, land after = GLCLU 2005/2015): wave only, province x wave,
  section_b              (was 09_section_b.py) Section B: preliminary reduced form. Sector x Census wave (2002 base, 2012, 2022).
  jobs_popctrl           (was 09b_jobs_popctrl.py) Table 5 variant: drop night lights, control for ln total population (time-varying, sector FE and province x wave FE).
  jobs_separate          (was 09c_jobs_separate.py) Table 5 (population control) estimated as two separate regressions:
  new_outcomes           (was 11d_new_outcome_regressions.py) Regressions on the new outcomes. All outcomes are measured after the period they describe.
  shift_share            (was 17_shift_share.py) Park-visitor shift-share (Bartik) exposure, stacked first differences.
  gate_gradient          (was 18_gate_gradient.py) Distance-to-gate gradient, park by park (pooled estimation).
  income_land            (was 19_income_land.py) First Stage II: national income x baseline agricultural wage -> tree-cover loss, 2001-2024.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
from common import *  # noqa: F401,F403  paths, ISIC groups, figure/table names, LaTeX tables (helpers/common.py)


def _section_b_data():
    """Data set-up shared by the section-B job regressions (sample, treatment terms, helpers)."""
    import os, numpy as np, pandas as pd
    from regression import fe_ols

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
    vis = pd.read_csv(P.tourism("park_visitors_by_park.csv")).set_index("year")
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
    return dict(locals())


def section_land():
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
    from regression import fe_ols

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


def section_land_timing_fe():
    """Table 1b: fixed-effect variants of Table 1 (Census 2002/2012, land after = GLCLU 2005/2015): wave only, province x wave,
district x wave (Table 1), all with sector FE and park-border x wave."""
    import numpy as np, pandas as pd
    from regression import fe_ols
    d = pd.read_csv(OUT_D / "sector_panel_desc.csv"); tg = pd.read_csv(OUT_D / "treatment_groups.csv"); pop = pd.read_csv(OUT_D / "sector_pop_total.csv")
    cb = pd.read_csv(OUT_D / "sector_cropland_builtup_glclu.csv")
    d = d[[c for c in d.columns if not c.endswith("_sh") and c not in ("crop", "built", "tree", "other", "usable", "ell")]]
    d = d.merge(tg[["sid"] + [c for c in tg.columns if c.startswith("border_") and c not in d.columns]], on="sid").merge(pop, on=["sid", "wave"])
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
    from regression import fe_matrix, _resid
    for lab, fe in [("Wave", ["sid", "wave"]), ("Province x wave", ["sid", "pw"]), ("District x wave", ["sid", "dw"])]:
        D = fe_matrix(s, fe); v = _resid(s[["sh_svc"]].values, fe_matrix(s, ["sid"]))[:, 0]; w = _resid(s[["sh_svc"]].values, D)[:, 0]
        print(f"{lab}: share of within-sector variance in services share left after FE = {w.var() / v.var():.2f}")


def section_section_b():
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
    global D, GATE_XY, GPARK, JOBS, LAND, S, TX, base, c, cross, d, est, fe_ols, fmt, g, hav, note, np, os, pd, pop, table, tg, vis, vy, w, xy
    globals().update(_section_b_data())
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
    l = pd.read_parquet(P.HARM_EXTRACTS / "lfs_sub.parquet").join(pd.read_parquet(P.HARM_EXTRACTS / "lfs_demo.parquet")[["lfs_sex", "lfs_education_level_highest"]])
    l = l[(l.lfs_employment_status == 1) & l.lfs_monthly_cash_income.gt(0) & l.lfs_age.between(16, 64) & l.lfs_industry_isic.notna()].copy()
    l["sec"] = l.lfs_industry_isic.astype(int).map(SEC)
    l["g"] = np.select([l.sec == "A", l.sec.isin(list("IHR")), l.sec.isin(list("JKM")), l.sec.isin(list("BCDEF"))], ["AG", "TOUR", "BUS", "IND"], "LOC")
    cpi = pd.read_csv(P.tourism("world_bank_wdi.csv")).query("country=='RWA' and indicator_code=='FP.CPI.TOTL'").set_index("year").value
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


def section_jobs_popctrl():
    """Table 5 variant: drop night lights, control for ln total population (time-varying, sector FE and province x wave FE).
Reuses the section-B data set-up (_section_b_data)."""
    global D, GATE_XY, GPARK, JOBS, LAND, S, TX, base, c, cross, d, est, fe_ols, fmt, g, hav, note, np, os, pd, pop, table, tg, vis, vy, w, xy
    globals().update(_section_b_data())

    JOBS_P = {k: v for k, v in JOBS.items() if k not in ("ln_pop", "ntl_chen_asinh")}
    R = table(JOBS_P, ["sid", "pw"], extra=["ln_pop"])
    # population coefficient for each outcome
    rows = []
    for y, lab in JOBS_P.items():
        r, n, G = fe_ols(S, y, TX + ["ln_pop"], ["sid", "pw"], "district_id")
        rows.append(dict(outcome=lab, coef=r.loc["ln_pop", "coef"], se=r.loc["ln_pop", "se"], p_wcb=r.loc["ln_pop", "p_wcb"]))
    P = pd.DataFrame(rows)
    R.to_csv(OUT_T / "T10p_B_jobs_popctrl_long.csv", index=False); P.to_csv(OUT_T / "T10p_B_jobs_popctrl_popcoef.csv", index=False)
    print(R.pivot(index="term", columns="outcome", values="coef").round(3).to_string())
    print(R.pivot(index="term", columns="outcome", values="p_wcb").round(3).to_string())
    print(P.round(3).to_string(index=False))


def section_jobs_separate():
    """Table 5 (population control) estimated as two separate regressions:
(a) near-gate vs clean control only, (b) bordering-only vs clean control only."""
    global D, GATE_XY, GPARK, JOBS, LAND, S, TX, base, c, cross, d, est, fe_ols, fmt, g, hav, note, np, os, pd, pop, table, tg, vis, vy, w, xy
    globals().update(_section_b_data())

    JOBS_P = {k: v for k, v in JOBS.items() if k not in ("ln_pop", "ntl_chen_asinh")}
    out = []
    for grp, xs, sub in [("near gate", ["NG_2012", "NG_2022"], S[S.BO == 0]), ("bordering only", ["BO_2012", "BO_2022"], S[S.NG == 0])]:
        for y, lab in JOBS_P.items():
            r, n, G = fe_ols(sub, y, xs + ["ln_pop"], ["sid", "pw"], "district_id")
            for x in xs: out.append(dict(regression=grp, outcome=lab, term=x, coef=r.loc[x, "coef"], se=r.loc[x, "se"], p=r.loc[x, "p_wcb"], N=n))
    R = pd.DataFrame(out); R.to_csv(OUT_T / "T10s_B_jobs_separate_long.csv", index=False)
    J = pd.read_csv(OUT_T / "T10p_B_jobs_popctrl_long.csv")[["outcome", "term", "coef", "p_wcb"]].rename(columns={"coef": "joint", "p_wcb": "p_joint"})
    M = R.merge(J, on=["outcome", "term"])
    print(M[["term", "outcome", "joint", "coef", "p_joint", "p", "N"]].round(3).to_string(index=False))


def section_new_outcomes():
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
    from regression import fe_ols
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


def section_shift_share():
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
    from regression import fe_ols

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

    vis = pd.read_csv(P.tourism("park_visitors_by_park.csv")).set_index("year")
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


def section_gate_gradient():
    """Distance-to-gate gradient, park by park (pooled estimation).
Sample: sectors whose nearest pre-2005 gate is within 40 km, excluding the City of Kigali and the four largest towns of 2002.
  Volcanoes: Kinigi HQ; Nyungwe: Kitabi and Bushekeri (nearest); Akagera: Mwiri (southern entrance).
Model: dy_n = sum_p sum_{b in 0-10, 10-20} beta_pb 1{park p, bin b} + park FE + gamma dln Pop_n + e_n,
  reference bin 20-40 km within each park. Census outcomes: change 2002->2022. Land: GLCLU 2005->2020, share of usable land.
  dln Pop: Census 2002->2022, all residents. SE clustered by district; wild cluster restricted bootstrap p (Webb, 9,999)."""
    import numpy as np, pandas as pd, matplotlib.pyplot as plt
    from regression import fe_ols

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


def section_income_land():
    """First Stage II: national income x baseline agricultural wage -> tree-cover loss, 2001-2024.
D_st = beta (ln Ybar_t x w_ag_{d(s),2001}) + mu_s + lambda_t + X_st'gamma + e_st
D_st: Hansen loss outside parks, % of 2000 tree cover per year; sectors with >= 10 ha cover in 2000.
Ybar_t: WDI GDP per capita, constant 2015 US$ (NY.GDP.PCAP.KD).
w_ag: EICV 2001 median daily cash wage of paid crop/livestock workers (trade codes 111, 121), by district;
      day/week/month/year units converted with reported days per week (4.33 weeks per month). Standardised (z) across districts.
X_st: near-gate x year and bordering-only x year dummies. SE clustered by district; wild cluster restricted bootstrap p."""
    import numpy as np, pandas as pd
    from regression import fe_ols

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

SECTIONS = {
    "land": section_land,
    "land_timing_fe": section_land_timing_fe,
    "section_b": section_section_b,
    "jobs_popctrl": section_jobs_popctrl,
    "jobs_separate": section_jobs_separate,
    "new_outcomes": section_new_outcomes,
    "shift_share": section_shift_share,
    "gate_gradient": section_gate_gradient,
    "income_land": section_income_land,
}


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", nargs="+", choices=list(SECTIONS), help="run only these sections, in run order")
    ap.add_argument("--list", action="store_true", help="list the sections and exit")
    a = ap.parse_args(argv)
    if a.list:
        print("\n".join(SECTIONS)); return
    for name, fn in SECTIONS.items():
        if a.only and name not in a.only:
            continue
        print(f"\n==== {name}", flush=True)
        fn()


if __name__ == "__main__":
    main()
