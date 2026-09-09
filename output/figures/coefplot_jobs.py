"""
coefplot_jobs.py -- three-sector employment, drawn as the housing coefplots.

    python coefplot_jobs.py
    output/figures/coefplot_jobs.pdf         no controls beyond the 2002 level, park and district FE
    output/figures/coefplot_jobs_lasso.pdf   controls chosen by cluster-robust PDS lasso
    output/figures/coefplot_jobs.csv

Same specification as coefplot_housing.py:

    Y(s,t) = a + b treated(s) + c Y(s,2002) + park FE + district FE        t = 2012, or 2022
    Y(s,t) = a + b treated(s) + c Y(s,2002) + park FE + district x wave FE t = pooled

Outcomes are asinh(count of workers aged 20-64), so coefficients read as proportional changes, in
units of the 2002 control standard deviation. Mining sits in primary (Fisher-Clark).

The 2022 primary count is RECONSTRUCTED. That census counts agricultural self-employment only if
"mainly for market", so subsistence farmers leave the recorded workforce entirely; they are added
back as adults with no recorded industry living in a crop-growing household, less the 14.1 point
false-positive rate that same rule produces in 2012, where subsistence farmers ARE recorded.
"""
import sys, numpy as np, pandas as pd, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
import statsmodels.formula.api as smf, textwrap
import bar_chart_housing as B          # never alias to C: shadows patsy C()
import build_controls as CTL
import coefplot_housing_lasso as L
OUT=str(B.FIG)
ANALYSIS=B.ANALYSIS
S="n PRIMARY"
OUTCOMES=[("primary","a_primary_pt_"+S,"Primary\n(agriculture, forestry,\nfishing, mining)"),
          ("secondary","a_secondary_"+S,"Secondary\n(manufacturing, utilities,\nconstruction)"),
          ("tertiary","a_tertiary_"+S,"Tertiary\n(all services)")]
WAVES=(("2012",[2012],"district"),("2022",[2022],"district"),("pooled",[2012,2022],"dw"))
p=pd.read_csv(ANALYSIS/"census_sector_jobs_panel.csv")
g,T,X,never=B.geography()
ctrl=set(p.sid.unique())-never-X["Kigali all + cities"]

def frame(o,tset):
    base=p[(p.wave==2002)&p.sid.isin(ctrl)][o]; mu,sd=base.mean(),base.std(ddof=1)
    d=p[p.sid.isin(set(tset)|ctrl)].copy()
    d["y"]=(d[o]-mu)/sd
    d["base"]=d.sid.map(d[d.wave==2002].set_index("sid")["y"])
    d["treat"]=d.sid.isin(tset).astype(int); d["dw"]=d.district+"_"+d.wave.astype(str)
    return d.dropna(subset=["y","base"]+list(CTL.CONTROLS))

rows=[]
for key,o,_ in OUTCOMES:
    for tn,tset in T.items():
        d=frame(o,tset)
        for wl,waves,fe in WAVES:
            sub=d[d.wave.isin(waves)].reset_index(drop=True)
            r=smf.ols(f"y ~ treat + base + C(park) + C({fe})",data=sub).fit(
                cov_type="cluster",cov_kwds={"groups":sub.sid})
            b,se=r.params["treat"],r.bse["treat"]
            rl,_,_=L.select_and_fit(d,waves,fe)
            rows.append(dict(outcome=key,treatment=tn,wave=wl,spec="main",b=b,se=se,
                             p=r.pvalues["treat"],lo90=b-1.645*se,hi90=b+1.645*se,k=np.nan))
            rows.append(dict(outcome=key,treatment=tn,wave=wl,spec="lasso",b=rl["b"],se=rl["se"],
                             p=rl["p"],lo90=rl["lo90"],hi90=rl["hi90"],k=rl["k_selected"]))
res=pd.DataFrame(rows); res.to_csv(ANALYSIS/"reg_jobs_threesector.csv",index=False)

def note(extra=""):
    return textwrap.fill(
    "Each point is the coefficient on the treatment indicator from a separate regression of the outcome on treatment, the sector's own 2002 level of that outcome, park "
    "fixed effects and district fixed effects, run on 2012, on 2022, and on the two pooled with district by wave fixed effects. " + extra +
    "Estimated at sector level, unweighted, with errors clustered at sector. Bars are 90% confidence intervals. Outcomes are the inverse hyperbolic sine of the count of "
    "workers aged 20 to 64 in each sector, expressed in standard deviations of the 2002 control distribution, so they read as proportional changes in the number of jobs. "
    "Mining is placed in the primary sector; moving it to secondary changes the estimates in the third decimal. The 2022 primary count is reconstructed: that census counts "
    "agricultural self-employment only when it is mainly for market, so subsistence farmers leave the recorded workforce and are added back as adults with no recorded "
    "industry living in a crop-growing household, less the 14.1 point false-positive rate the same rule produces in 2012. The upper bound, which adds all such adults back "
    "with no correction, gives the same answer. Controls are the 328 sectors that neither border a long-standing national park nor sit within 5 km of a park entrance, "
    "less the City of Kigali and the four largest towns of 2002. "
    "Source: Rwanda Population and Housing Census 2002, 2012 and 2022, 10% public-use samples.", width=250)

def draw(spec,path,title,extra=""):
    q=res[res.spec==spec]
    fig,axes=plt.subplots(1,len(T),figsize=(11,4.8),sharex=True,sharey=True)
    ys=np.arange(len(OUTCOMES))[::-1]
    for ax,(tn,tset) in zip(np.atleast_1d(axes),T.items()):
        x=q[q.treatment==tn]
        for k,(wl,col,mk) in enumerate([("2012","#8C8C8C","o"),("2022","#E0A33E","s"),("pooled","#2E75A8","D")]):
            xx=x[x.wave==wl].set_index("outcome").reindex([o[0] for o in OUTCOMES])
            ax.errorbar(xx.b,ys+(1-k)*0.22,xerr=[xx.b-xx.lo90,xx.hi90-xx.b],fmt=mk,ms=5,
                        color=col,ecolor=col,elinewidth=1.4,capsize=2.5,
                        label=wl if tn==list(T)[0] else None)
        ax.axvline(0,color="#333333",lw=.8)
        ax.set_yticks(ys); ax.set_yticklabels([o[2] for o in OUTCOMES],fontsize=8.5)
        ax.set_title(f"{tn} ({len(tset)} treated)",fontsize=10)
        ax.set_xlabel("effect on job counts, 2002 control standard deviations",fontsize=9)
        ax.grid(axis="x",lw=.3,color="#DDDDDD"); ax.set_axisbelow(True)
    np.atleast_1d(axes)[0].legend(fontsize=9,frameon=False,loc="lower right")
    fig.suptitle(title,fontsize=12,x=.008,ha="left",y=.995)
    fig.text(.005,.005,note(extra),fontsize=6.6,va="bottom",ha="left",color="#333333",linespacing=1.6)
    fig.tight_layout(rect=[0,.20,1,.96])
    fig.savefig(path,bbox_inches="tight"); plt.close(fig)
    print("written:",path)

draw("main",f"{OUT}/coefplot_jobs.pdf",
     "Employment by broad sector: no controls beyond the 2002 level, park and district fixed effects")
draw("lasso",f"{OUT}/coefplot_jobs_lasso.pdf",
     "Employment by broad sector: controls chosen by cluster-robust post-double-selection lasso",
     "Controls beyond those are chosen by post-double-selection lasso from 1,484 candidate terms: 53 sector characteristics measured in 2002, their squares and every "
     "pairwise product. With twelve treated sectors the cluster-robust penalty selects at most one term in the Gates+ panel, so that panel is close to the unadjusted "
     "specification and should not be read as an independent check. ")
