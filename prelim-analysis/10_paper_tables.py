"""Publication-style LaTeX tables (booktabs + threeparttable) from the saved regression output of 07 and 09.
Writes output/tables/regressions/journal_format/*.tex and all_regression_tables.tex (names in _common.JOURNAL_NAMES)."""
import numpy as np, pandas as pd
from _common import *
P = OUT_T / "paper"; P.mkdir(exist_ok=True)
star = lambda p: "^{***}" if p < .01 else "^{**}" if p < .05 else "^{*}" if p < .1 else ""
def three(c, s, p, nd=3):
    return [f"${c:.{nd}f}{star(p)}$", f"$({s:.{nd}f})$", f"$[{p:.3f}]$"]
def table(name, title, cols, body_rows, foot_rows, notes, label, colsep=None, size="small"):
    """cols: list of column headers (outcome names). body_rows: list of ("label", [cells]) or ("\\midrule-ish panel", None)."""
    k = len(cols)
    L = [r"\begin{table}[!htbp]\centering" + ("\\" + size) + (r"\renewcommand{\arraystretch}{0.92}" if size != "small" else ""), r"\begin{threeparttable}", rf"\caption{{{title}}}\label{{{label}}}",
         r"\begin{tabular}{l" + "c" * k + "}", r"\toprule",
         " & " + " & ".join(f"({i+1})" for i in range(k)) + r" \\",
         " & " + " & ".join(r"\shortstack{" + c + "}" for c in cols) + r" \\", r"\midrule"]
    for lab, cells in body_rows:
        if cells is None:
            L.append(rf"\multicolumn{{{k+1}}}{{l}}{{\textit{{{lab}}}}} \\"); continue
        L.append(lab + " & " + " & ".join(cells) + r" \\")
    L.append(r"\midrule")
    for lab, cells in foot_rows: L.append(lab + " & " + " & ".join(cells) + r" \\")
    L += [r"\bottomrule", r"\end{tabular}", r"\begin{tablenotes}[flushleft]\footnotesize", r"\item \textit{Notes:} " + notes,
          r"\end{tablenotes}", r"\end{threeparttable}", r"\end{table}"]
    (P / f"{name}.tex").write_text("\n".join(L)); return name

def rows_for(R, terms, labels, outcomes):
    out = []
    for t in terms:
        blocks = []
        for o in outcomes:
            x = R[(R.term == t) & (R.outcome == o)] if "term" in R else R[(R.regressor == t) & (R.outcome == o)]
            blocks.append(three(*x.iloc[0][["coef", "se", "p_wcb"]]) if len(x) else ["", "", ""])
        for i in range(3): out.append((labels[t] if i == 0 else "", [b[i] for b in blocks]))
    return out
yes = lambda k: ["Yes"] * k
STD = ("Standard errors clustered by district in parentheses. $p$-values from the wild cluster restricted bootstrap "
       "(Webb six-point weights, 9,999 replications) in brackets; stars refer to these $p$-values: $^{***}p<0.01$, $^{**}p<0.05$, $^{*}p<0.1$.")
made = []

# ---------------- Table 1: land use on services share (T8) ----------------
R = pd.read_csv(OUT_T / "T8_land_regressions_long.csv")
d = pd.read_csv(OUT_D / "sector_panel_desc.csv")
cbl = pd.read_csv(OUT_D / "sector_cropland_builtup_glclu.csv"); d0 = cbl[(cbl.urban == 0) & (cbl.year == 2005)]
outs = ["Cropland share", "Built-up share", "Tree-cover share", "Short veg./bare share"]
M = R[R.spec == "Main"]; TS = R[R.spec == "Tourism split"]; MC = R[R.spec == "Model check"]
lab = {"sh_svc": "Services share of workers", "ln_pop": "ln total population", "sh_tsa": "Tourism-industry share (I, H, R)",
       "sh_svc_other": "Other services share", "lam": r"$\lambda$ (agriculture share, ag.\ + services)"}
body = [("Panel A. Services pooled", None)] + rows_for(M, ["sh_svc", "ln_pop"], lab, outs)
body += [("Panel B. Tourism industries separated", None)] + rows_for(TS, ["sh_tsa", "sh_svc_other", "ln_pop"], lab, outs)
foot = [("Mean of outcome, 2005", [f"{d0[c].mean():.3f}" for c in ["crop_sh", "built_sh", "tree_sh", "other_sh"]]),
        ("Sector FE", yes(4)), (r"District $\times$ wave FE", yes(4)), (r"Park-border $\times$ wave FE", yes(4)),
        ("Observations", [str(int(M.N.iloc[0]))] * 4), ("Sectors", [str(int(M.N.iloc[0] // 2))] * 4), ("Clusters (districts)", [str(int(M.clusters.iloc[0]))] * 4)]
made.append(table("tab1_land_services", "Land Use and the Sectoral Composition of Employment", [o.replace(" share", r"\\share") for o in outs], body, foot,
    "Each column is a separate regression of the share of usable land outside national parks in the stated use on the services share of workers "
    "(all tertiary employment except trade, G, and public administration, O; Census, workers 20--64) and log total resident population. Land is measured "
    "three years after employment: GLCLU v2 2005 for the 2002 Census and 2015 for the 2012 Census. The 2022 Census is not used because no GLCLU year follows it. Sample: all sectors outside the City of Kigali and the four largest towns of 2002. "
    "Park-border $\\times$ wave terms are separate dummies for sectors bordering Volcanoes, Nyungwe, Akagera and Gishwati-Mukura, interacted with wave. "
    "Because the four shares sum to one, coefficients sum to zero across columns (1)--(4). " + STD, "tab:land"))

# ---------------- Table 2: contract curve ----------------
body = rows_for(MC, ["lam", "ln_pop"], lab, ["ell = crop/(crop+built)"])
foot = [("Mean of outcome, 2005", [f"{d0.ell.mean():.3f}"]), ("Sector FE", ["Yes"]), (r"District $\times$ wave FE", ["Yes"]), (r"Park-border $\times$ wave FE", ["Yes"]),
        ("Observations", [str(int(MC.N.iloc[0]))]), ("Clusters (districts)", [str(int(MC.clusters.iloc[0]))])]
made.append(table("tab2_contract_curve", r"The Land--Labor Contract Curve: $\ell$ on $\lambda$", [r"$\ell$ = cropland /\\(cropland + built-up)"], body, foot,
    r"Tests equation (7) of the model, $\ell(\lambda)=c\lambda/(1-\lambda+c\lambda)$, which implies a positive slope on $\lambda$ and no role for population. "
    r"$\lambda$ is agriculture's share of agricultural plus services workers (services exclude G and O). Sample and specification as in Table~\ref{tab:land}. "
    r"At the sample means ($\lambda\approx0.92$, $\ell\approx0.70$) the model's slope $d\ell/d\lambda$ is about 2.9. " + STD, "tab:cc"))

# ---------------- Table 2b: fixed-effect variants of Table 1 ----------------
F = pd.read_csv(OUT_T / "T8b_land_timing_fe_long.csv"); F["outcome"] = F.outcome.map({"Cropland": "Cropland share", "Built-up": "Built-up share", "Tree cover": "Tree-cover share", "Short veg./bare": "Short veg./bare share"})
body = []
for spec, pl in [("Wave FE", r"Panel A. Wave fixed effects"), ("Province x wave FE", r"Panel B. Province $\times$ wave fixed effects"),
                 ("District x wave FE (Table 1)", r"Panel C. District $\times$ wave fixed effects (Table~\ref{tab:land})")]:
    body.append((pl, None)); body += rows_for(F[F.spec == spec], ["sh_svc", "ln_pop"], lab, outs)
foot = [("Sector FE", yes(4)), (r"Park-border $\times$ wave FE", yes(4)), ("Observations", [str(int(F.N.iloc[0]))] * 4), ("Clusters (districts)", [str(int(F.clusters.iloc[0]))] * 4)]
made.insert(1, table("tab1b_land_fe", "Land Use and Employment Composition: Alternative Fixed Effects", [o.replace(" share", r"\\share") for o in outs], body, foot,
    r"Specification and sample as in Table~\ref{tab:land} (Census 2002 and 2012, land in 2005 and 2015), varying only the time fixed effects. "
    r"Province $\times$ wave and wave fixed effects use variation across districts that district $\times$ wave fixed effects absorb, including district-implemented "
    r"agricultural programmes. " + STD, "tab:landfe"))

# ---------------- Tables 3-4: section B ----------------
TL = {"NG_2012": r"Near gate $\times$ 2012", "NG_2022": r"Near gate $\times$ 2022", "BO_2012": r"Bordering only $\times$ 2012", "BO_2022": r"Bordering only $\times$ 2022",
      "exposure": "Tourism exposure"}
for w in (2005, 2010, 2015, 2020):
    TL[f"NG_{w}"] = rf"Near gate $\times$ {w}"; TL[f"BO_{w}"] = rf"Bordering only $\times$ {w}"
for p in ["volcanoes", "nyungwe", "akagera"]:
    for w in (2005, 2010, 2012, 2015, 2020, 2022): TL[f"T_{p}_{w}"] = rf"Treated $\times$ {p.capitalize()} $\times$ {w}"
BNOTE = ("Sample: 12 sectors containing or adjacent to a pre-2005 park entrance (near gate), 32 sectors bordering Volcanoes, Nyungwe or Akagera but not near a gate "
         "(bordering only), and 257 clean control sectors (neither, excluding sectors that touch a treated sector, the nine Gishwati-Mukura neighbours, the City of Kigali "
         "and the four largest towns of 2002). Census waves 2002 (omitted base), 2012 and 2022. Near-gate sectors lie in five districts, so inference for those coefficients "
         "rests on few treated clusters. ")
def btable(fname, title, R, outs, colnames, terms, note, label, fe="Province", base="2002", per="wave"):
    body = rows_for(R, terms, TL, outs)
    g = R.groupby("outcome", sort=False).first()
    foot = [(f"Control mean, {base}", [f"{g.loc[o, 'control_mean_2002']:.3f}" for o in outs]), ("Sector FE", yes(len(outs))),
            (rf"{fe} $\times$ {per} FE", yes(len(outs))), ("Observations", [str(int(g.loc[o, "N"])) for o in outs]),
            ("Clusters (districts)", [str(int(g.loc[o, "clusters"])) for o in outs])]
    return table(fname, title, colnames, body, foot, note, label)
R10 = pd.read_csv(OUT_T / "T10p_B_jobs_popctrl_long.csv")
P10 = pd.read_csv(OUT_T / "T10p_B_jobs_popctrl_popcoef.csv").assign(term="ln_pop")
R10 = pd.concat([R10, P10.merge(R10.groupby("outcome").first()[["N", "clusters", "control_mean_2002"]].reset_index(), on="outcome")])
TL["ln_pop"] = r"ln total population"
o10 = ["lambda", "Tourism share (I,H,R)", "Services share (excl. G,O)", "ln farm workers", "ln services workers"]
c10 = [r"$\lambda$", r"Tourism\\share", r"Services\\share", r"ln farm\\workers", r"ln services\\workers"]
made.append(btable("tab3_B_jobs", "Park Proximity and Employment Composition, Controlling for Population", R10, o10, c10, ["NG_2012", "NG_2022", "BO_2012", "BO_2022", "ln_pop"],
    r"Each column regresses the outcome on near-gate and bordering-only indicators interacted with wave and on log total population (all residents) in the same wave. "
    r"$\lambda$ = agriculture / (agriculture + services excluding G and O). Tourism share = ISIC sections I, H and R over all workers. Workers are aged 20--64. "
    r"Population is itself affected by park proximity, so the indicator coefficients measure differences at a given population. " + BNOTE + STD, "tab:Bjobs"))
_f = OUT_T / "paper" / "tab3_B_jobs.tex"; _t = _f.read_text()
_t = _t.replace("\nBordering only $\\times$ 2012", "\n\\midrule\nBordering only $\\times$ 2012", 1).replace("\nln total population", "\n\\midrule\nln total population", 1)
_f.write_text(_t)
R11 = pd.read_csv(OUT_T / "T11_B_land_long.csv")
o11 = ["Cropland share", "Built-up share", "Tree-cover share", "Short veg./bare share"]
c11 = [r"Cropland\\share", r"Built-up\\share", r"Tree-cover\\share", r"Short veg./bare\\share"]
LT = [f"{g}_{w}" for g in ["NG", "BO"] for w in (2005, 2010, 2015, 2020)]
LNOTE = (r"Land shares are of usable land outside parks, GLCLU v2, in its own years: 2000 (omitted base, before Tourism Revenue Sharing began in 2005), 2005, 2010, "
         r"2015 and 2020. Sample: the 301 sectors of Table~\ref{tab:Bjobs}, five years each. Near-gate sectors lie in five districts, so inference for those coefficients "
         r"rests on few treated clusters. ")
made.append(btable("tab4_B_land", "Park Proximity and Land Use, 2000--2020", R11, o11, c11, LT, LNOTE + STD, "tab:Bland", base="2000", per="year"))
L = pd.read_csv(OUT_T / "T11b_B_land_robustness_long.csv")
body = []
for spec, pl, terms in [("District x year FE", r"Panel A. District $\times$ year fixed effects", LT),
                        ("+ 2000 land shares x year", r"Panel B. Adding 2000 cropland and tree-cover shares $\times$ year", LT)]:
    body.append((pl, None)); body += rows_for(L[L.spec == spec], terms, TL, o11)
foot = [("Sector FE", yes(4)), ("Observations", [str(int(L.N.iloc[0]))] * 4), ("Clusters (districts)", [str(int(L.clusters.iloc[0]))] * 4)]
made.append(table("tab4b_B_land_robustness", "Park Proximity and Land Use: Robustness", c11, body, foot,
    r"Panel A replaces province $\times$ year with district $\times$ year fixed effects. Panel B keeps province $\times$ year fixed effects and adds the 2000 cropland and "
    r"tree-cover shares interacted with year. " + LNOTE + STD, "tab:Blandrob", size="footnotesize"))
LP = L[L.spec == "By park"]
made.append(btable("tab4c_B_land_parks", "Park Proximity and Land Use by Park", LP, o11, c11,
    [f"T_{p}_{w}" for p in ["volcanoes", "nyungwe", "akagera"] for w in (2005, 2010, 2015, 2020)],
    r"Treated = near gate or bordering only, interacted with the park the sector borders and with year; the comparison group is the clean control. " + LNOTE + STD,
    "tab:Blandpark", base="2000", per="year"))

# ---------------- Table 5: robustness (panels) ----------------
R12 = pd.read_csv(OUT_T / "T12_B_robustness_long.csv")
o12 = ["lambda", "Tourism share (I,H,R)", "ln total population", "Night lights"]
c12 = [r"$\lambda$", r"Tourism\\share", r"ln total\\population", r"Night\\lights"]
body = []
for spec, pl in [("District x wave FE", r"Panel A. District $\times$ wave fixed effects"), ("+ 2000 land shares x wave", r"Panel B. Adding 2000 cropland and tree-cover shares $\times$ wave"),
                 ("Continuous exposure (all non-urban)", "Panel C. Continuous exposure, all non-urban sectors")]:
    sub = R12[R12.spec == spec]; body.append((pl, None))
    body += rows_for(sub, list(dict.fromkeys(sub.term)), TL, o12)
foot = [("Sector FE", yes(4)), ("Observations, Panels A--B", [str(int(R12[(R12.spec == 'District x wave FE') & (R12.outcome == o)].N.iloc[0])) for o in o12]),
        ("Observations, Panel C", [str(int(R12[(R12.spec.str.startswith('Continuous')) & (R12.outcome == o)].N.iloc[0])) for o in o12])]
made.append(table("tab5_B_robustness", "Robustness of the Park-Proximity Estimates", c12, body, foot,
    r"Panel A replaces province $\times$ wave with district $\times$ wave fixed effects. Panel B keeps province $\times$ wave fixed effects and adds the 2000 cropland and "
    r"tree-cover shares interacted with wave. Panel C replaces the indicators with exposure = ln(1 + visitors to the nearest park, thousands) $\times$ exp($-$km to the nearest "
    r"pre-2005 entrance / 10), using 2005, 2012 and 2019 visitors for the 2002, 2012 and 2022 waves, on all non-urban sectors except the Gishwati-Mukura neighbours, with "
    r"province $\times$ wave fixed effects. " + BNOTE + STD, "tab:Brob"))

# ---------------- Table 6: by park ----------------
R13 = pd.read_csv(OUT_T / "T13_B_by_park_long.csv")
made.append(btable("tab6_B_parks", "Heterogeneity by Park", R13, o12, c12, [f"T_{p}_{w}" for p in ["volcanoes", "nyungwe", "akagera"] for w in (2012, 2022)],
    r"Treated = near gate or bordering only, interacted with the park the sector borders and with wave; the comparison group is the clean control. " + BNOTE + STD, "tab:Bpark"))

# ---------------- Table 7: wages ----------------
W = pd.read_csv(OUT_T / "T14_B_wage_gaps.csv")
samples = ["All districts", "Excl. Kigali", "Park districts"]
WL = {"TOUR": "Tourism industries (I, H, R)", "LOC": "Local services", "BUS": "Business services (J, K, M)", "IND": "Industry (B--F)"}
body = []
for t in ["TOUR", "LOC", "BUS", "IND"]:
    bl = [three(*W[(W.term == t) & (W["sample"] == s)].iloc[0][["coef", "se", "p_wcb"]]) for s in samples]
    for i in range(3): body.append((WL[t] if i == 0 else "", [b[i] for b in bl]))
foot = [("Omitted sector", ["Agriculture"] * 3), (r"District $\times$ year FE", yes(3)), ("Education FE", yes(3)), (r"Age, age$^2$, female", yes(3)),
        ("Observations", [f"{int(W[W['sample'] == s].N.iloc[0]):,}" for s in samples]), ("Clusters (districts)", [str(int(W[W['sample'] == s].clusters.iloc[0])) for s in samples])]
made.append(table("tab7_B_wages", "Within-District Earnings Gaps by Sector", [r"All\\districts", r"Excluding\\Kigali", r"Park\\districts"], body, foot,
    r"Dependent variable: log real monthly cash earnings in the main job (2014 RWF, CPI-deflated), employees aged 16--64, Labour Force Survey 2017--2025, unweighted. "
    r"Park districts contain at least one treated sector. The model implies a common wage within a location, i.e.\ zero coefficients; own-account farmers have no wage "
    r"and are not in the sample. Bootstrap uses 4,999 replications. " + STD.replace("9,999", "4,999"), "tab:wages"))

# ---------------- Tables 11-13: additional outcomes (11d) ----------------
N = pd.read_csv(OUT_T / "T16_new_outcomes_long.csv")
def cellrows(sub_by_col, terms, labels):
    out = []
    for t in terms:
        bl = []
        for sub in sub_by_col:
            x = sub[sub.term == t]; bl.append(three(*x.iloc[0][["coef", "se", "p_wcb"]]) if len(x) else ["", "", ""])
        for i in range(3): out.append((labels[t] if i == 0 else "", [b[i] for b in bl]))
    return out
af, ag = N[N.block == "A_forest"], N[N.block == "A_ghsl"]
body = cellrows([af, ag], ["sh_svc", "ln_pop"], lab)
foot = [("Mean of outcome, first wave", [f"{af.control_mean.iloc[0]:.3f}", f"{ag.control_mean.iloc[0]:.3f}"]), ("Census waves", ["2002, 2012, 2022", "2002, 2012"]),
        ("Outcome measured", ["2003--05, 2013--15, 2023--24", "2005, 2015"]), ("Sector FE", yes(2)), (r"District $\times$ wave FE", yes(2)),
        (r"Park-border $\times$ wave FE", yes(2)), ("Observations", [str(int(af.N.iloc[0])), str(int(ag.N.iloc[0]))]), ("Clusters (districts)", [str(int(af.clusters.iloc[0])), str(int(ag.clusters.iloc[0]))])]
made.append(table("tab8_land_other_outcomes", "Employment Composition and Other Land Outcomes", [r"Tree-cover loss\\(\% of 2000 cover/yr)", r"Built-up surface\\(\% of land, GHSL)"], body, foot,
    r"Specification as in Table~\ref{tab:land}. Column (1): Hansen et al.\ tree-cover loss outside parks (canopy $\geq$30\% in 2000), mean annual loss in the years after each "
    r"Census as a percentage of 2000 tree cover; sectors with at least 10 ha of tree cover. Column (2): GHSL R2023A built-up surface (m$^2$ of roofs and paved surface per "
    r"$\sim$90 m cell, residential and non-residential) as a percentage of usable land outside parks, three years after the Census. GHSL's non-residential layer is not used: "
    r"it classifies under 1\% of Kigali's built surface as non-residential. Hansen loss outside parks largely reflects plantation harvest. " + STD, "tab:landother"))
bf, bg = N[N.block == "B_forest"], N[N.block == "B_ghsl"]
TLn = {**{f"NG_{y}": rf"Near gate $\times$ {y}" for y in (2005, 2010, 2015, 2020)}, **{f"BO_{y}": rf"Bordering only $\times$ {y}" for y in (2005, 2010, 2015, 2020)}}
body = cellrows([bf, bg], [f"{g}_{y}" for g in ["NG", "BO"] for y in (2005, 2010, 2015, 2020)], TLn)
foot = [("Control mean, base period", [f"{bf.control_mean.iloc[0]:.3f}", f"{bg.control_mean.iloc[0]:.3f}"]), ("Base period", ["2001--04", "2000"]),
        ("Sector FE", yes(2)), (r"Province $\times$ period FE", yes(2)), ("Observations", [str(int(bf.N.iloc[0])), str(int(bg.N.iloc[0]))]), ("Clusters (districts)", [str(int(bf.clusters.iloc[0])), str(int(bg.clusters.iloc[0]))])]
made.append(table("tab9_B_other_land", "Park Proximity, Tree-Cover Loss and Built-Up Surface", [r"Tree-cover loss\\(\% of 2000 cover/yr)", r"Built-up surface\\(\% of land, GHSL)"], body, foot,
    r"Column (1): mean annual Hansen tree-cover loss outside parks in five-year periods 2001--04 (omitted), 2005--09, 2010--14, 2015--19 and 2020--24, labelled by first year; "
    r"sectors with at least 10 ha of tree cover in 2000. Column (2): GHSL built-up surface, percent of usable land, in 2000 (omitted), 2005, 2010, 2015 and 2020. Sample: near-gate, bordering-only "
    r"and clean-control sectors as in Table~\ref{tab:Bjobs}. " + STD, "tab:Bother"))
cr = N[N.block == "C_rent"]
TLr = {f"P_{y}": rf"Park district $\times$ {y}" for y in (2006, 2011, 2014, 2017)}
body = cellrows([cr], [f"P_{y}" for y in (2006, 2011, 2014, 2017)], TLr)
foot = [("Mean of outcome, other districts, 2001", [f"{cr.control_mean.iloc[0]:.2f}"]), ("District FE", ["Yes"]), ("Year FE", ["Yes"]),
        ("Observations (district-years)", [str(int(cr.N.iloc[0]))]), ("Clusters (districts)", [str(int(cr.clusters.iloc[0]))])]
made.append(table("tab10_land_rent", "Land Rent in Park Districts", [r"ln real rent\\per hectare"], body, foot,
    r"District-year panel, EICV 2001 (omitted), 2006, 2011, 2014 and 2017, City of Kigali excluded (27 districts, 12 park districts). Outcome: log of the weighted median "
    r"annual cash rent per hectare across rented parcels, CPI-deflated to 2014 RWF, winsorized at 1/99\%. Park districts contain at least one treated sector. Parcel area is "
    r"recorded in hectares in 2001 and ares thereafter; rent is over 12 months in 2014 and taken as annual in other waves. The 2001 base rests on about 60 rented parcels "
    r"per district. " + STD, "tab:rent"))

doc = [r"\documentclass[11pt]{article}", r"\usepackage[margin=0.75in,top=0.45in,bottom=0.55in]{geometry}", r"\usepackage{booktabs,threeparttable,amsmath,lmodern}",
       r"\usepackage[T1]{fontenc}", r"\renewcommand{\arraystretch}{1.05}", r"\begin{document}"]
doc += [rf"\input{{{m}.tex}}" + "\n\\clearpage" for m in made] + [r"\end{document}"]
(P / "regression_tables.tex").write_text("\n".join(doc)); print(made)
