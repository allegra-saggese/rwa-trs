"""build_jobs_panel.py -- sector x wave counts of workers by broad sector.

    python build_jobs_panel.py
    Analysis/census_sector_jobs_panel.csv

Three-sector employment, Counts (asinh) of workers aged 20-64.

PRIMARY 2022 IS RECONSTRUCTED. The 2022 census counts agricultural self-employment only if "mainly
for market", so subsistence farmers leave the recorded workforce. They are added back as: adults
with no recorded industry who live in a crop-growing household, LESS the false-positive rate of that
rule measured in 2012, where subsistence farmers ARE recorded and so anyone the rule adds is a
non-working adult who merely lives on a farm. That rate is 14.1 points. The rule is trustworthy
because the composition of unrecorded adults is near-identical across waves: 67.5% of them live in
farm households in 2012 and 67.8% in 2022. Bounds are reported alongside.

MINING is run three ways -- in primary, in secondary, and as its own category -- because the
classic Fisher-Clark split puts extraction in primary while development accounting usually calls it
industry, and Rwanda's mining is small enough that the choice may not matter.
"""
import sys, numpy as np, pandas as pd, pyreadstat, statsmodels.formula.api as smf
sys.path.insert(0,"/Users/matteo/Documents/GitHub/rwa-trs/output/figures")
import bar_chart_housing as B          # never alias to C: shadows patsy C()
import build_controls as CTL
from scipy import stats
OUT=str(B.ANALYSIS)
FP_RATE=0.141      # false positives of the farm-household rule, measured in 2012
d,_=pyreadstat.read_dta(B.NISR/"Census-PHC/3_Final/Census_pooled_person.dta",
  usecols=["census_wave","census_sector","census_weight","census_age","census_household_id",
           "census_industry_isic3_2002","census_isic_section_2012","census_isic_section_2022"])
h,_=pyreadstat.read_dta(B.NISR/"Census-PHC/3_Final/Census_pooled_household.dta",
  usecols=["census_wave","census_household_id","census_land_2012","census_grew_crops_2022"])
d["wave"]=d.census_wave.astype(str).astype(int); h["wave"]=h.census_wave.astype(str).astype(int)
h["farm_hh"]=np.nan
l=pd.to_numeric(h.census_land_2012,errors="coerce")
h.loc[h.wave==2012,"farm_hh"]=l.isin([1,2,3,5,6,7]).astype(float)[h.wave==2012]
gc=pd.to_numeric(h.census_grew_crops_2022,errors="coerce")
h.loc[h.wave==2022,"farm_hh"]=gc.eq(1).astype(float)[h.wave==2022]
d=d.merge(h[["census_household_id","wave","farm_hh"]],on=["census_household_id","wave"],how="left")
d=d[d.census_age.between(20,64)].copy()
num=lambda c: pd.to_numeric(d[c],errors="coerce"); w=d.census_weight.fillna(1.0)
dv=(num("census_industry_isic3_2002").where(lambda s:s<999)//10)
sec=pd.Series(np.nan,index=d.index)
sec[d.wave==2012]=num("census_isic_section_2012").where(lambda s:s<=21)[d.wave==2012]
sec[d.wave==2022]=num("census_isic_section_2022").where(lambda s:s<=21)[d.wave==2022]
m02=d.wave==2002; mlt=d.wave.isin([2012,2022])
AG=pd.Series(False,index=d.index); MIN=AG.copy(); MAN=AG.copy(); TER=AG.copy(); rec=AG.copy()
AG[m02]=dv[m02].isin([1,2,5]);                    AG[mlt]=sec[mlt].eq(1)
MIN[m02]=dv[m02].between(10,14);                  MIN[mlt]=sec[mlt].eq(2)
MAN[m02]=dv[m02].isin(list(range(15,38))+[40,41,45]); MAN[mlt]=sec[mlt].isin([3,4,5,6])
TER[m02]=dv[m02].between(50,99);                  TER[mlt]=sec[mlt].between(7,21)
rec[m02]=dv[m02].notna();                         rec[mlt]=sec[mlt].notna()
unrec_farm = (~rec) & d.farm_hh.eq(1) & (d.wave==2022)   # reconstructed subsistence farmers
d["AG"],d["MIN"],d["MAN"],d["TER"],d["rec"],d["addback"]=(AG.astype(float),MIN.astype(float),
    MAN.astype(float),TER.astype(float),rec.astype(float),unrec_farm.astype(float))
print("NATIONAL, adults 20-64, share of adults:")
for lab,col in (("agriculture","AG"),("mining","MIN"),("manuf+util+constr","MAN"),("tertiary","TER")):
    print(f"  {lab:20s} "+"  ".join(f"{y}={100*float((d.loc[d.wave==y,col]*w[d.wave==y]).sum()/w[d.wave==y].sum()):5.1f}%"
                                     for y in (2002,2012,2022)))
ab=float((d.loc[d.wave==2022,"addback"]*w[d.wave==2022]).sum()/w[d.wave==2022].sum())
ag22=float((d.loc[d.wave==2022,"AG"]*w[d.wave==2022]).sum()/w[d.wave==2022].sum())
print(f"\n  2022 agriculture: recorded {100*ag22:.1f}% | +farm-hh addback {100*(ag22+ab):.1f}%"
      f" | point estimate (less {100*FP_RATE:.1f}pp false positives) {100*(ag22+ab-FP_RATE):.1f}%")
rows=[]
for (sid,y),q in d.groupby(["census_sector","wave"]):
    ww=w[q.index]; tot=float(ww.sum())
    r={"sid":int(sid),"wave":int(y),"adults":tot}
    for c in ("AG","MIN","MAN","TER"): r["n_"+c]=float(ww[q[c]==1].sum())
    add=float(ww[q.addback==1].sum())
    r["n_AG_hi"]=r["n_AG"]+add                                  # upper bound
    r["n_AG_pt"]=r["n_AG"]+max(add-FP_RATE*tot,0.0)             # point estimate
    rows.append(r)
p=pd.DataFrame(rows)
VARIANTS={"mining in PRIMARY":   (["AG","MIN"],["MAN"],["TER"]),
          "mining in SECONDARY": (["AG"],["MIN","MAN"],["TER"]),
          "mining SEPARATE":     (["AG"],["MAN"],["TER"])}
for v,(pr,se_,te) in VARIANTS.items():
    for agv,tag in (("n_AG","rec"),("n_AG_pt","pt"),("n_AG_hi","hi")):
        cols=[agv if c=="AG" else "n_"+c for c in pr]
        p[f"a_primary_{tag}_{v[-9:]}"]=np.arcsinh(p[cols].sum(axis=1))
    p[f"a_secondary_{v[-9:]}"]=np.arcsinh(p[["n_"+c for c in se_]].sum(axis=1))
    p[f"a_tertiary_{v[-9:]}"]=np.arcsinh(p[["n_"+c for c in te]].sum(axis=1))
p["a_mining"]=np.arcsinh(p.n_MIN)
g,T,X,never=B.geography(); g=g.assign(park=g.nearest_park.astype(str).str.split().str[0])
z=pd.read_csv(B.ANALYSIS/"census_sector_controls_2002.csv")
for c in CTL.CONTROLS: z[c]=(z[c]-z[c].mean())/z[c].std(ddof=1)
p=p.merge(g[["sid","district","park"]],on="sid",how="left").merge(z,on="sid",how="left")
p.to_csv(f"{OUT}/census_sector_jobs_panel.csv",index=False)
ctrl=set(p.sid.unique())-never-X["Kigali all + cities"]
GEO=["elev_mean","elev_sd","slope_mean","rain_mean","rain_cv","dry_months","drought_freq",
     "log_area","log_dist_kigali","log_dist_town","log_dist_border","compactness","log_pop"]
def run(o,tset,waves,fe,extra):
    base=p[(p.wave==2002)&p.sid.isin(ctrl)][o]; mu,sd=base.mean(),base.std(ddof=1)
    dd=p[p.sid.isin(set(tset)|ctrl)].copy()
    dd["y"]=(dd[o]-mu)/sd
    dd["base"]=dd.sid.map(dd[dd.wave==2002].set_index("sid")["y"])
    dd["treat"]=dd.sid.isin(tset).astype(int); dd["dw"]=dd.district+"_"+dd.wave.astype(str)
    dd=dd.dropna(subset=["y","base"]+GEO)
    sub=dd[dd.wave.isin(waves)].reset_index(drop=True)
    f=f"y ~ treat + base + C(park) + C({fe})"+"".join(" + "+v for v in extra)
    r=smf.ols(f,data=sub).fit(cov_type="cluster",cov_kwds={"groups":sub.sid})
    return r.params["treat"],r.pvalues["treat"]
st=lambda x:"***" if x<.01 else "**" if x<.05 else "*" if x<.1 else ""
print("\n"+"="*104)
print("ANCOVA, counts (asinh). Left of | is the housing spec; right adds 13 geography/climate controls.")
print("="*104)
for v in VARIANTS:
    sfx=v[-9:]
    print(f"\n##### {v} #####")
    for lab,o in ([("primary (recorded)",f"a_primary_rec_{sfx}"),
                   ("primary (POINT EST)",f"a_primary_pt_{sfx}"),
                   ("primary (upper bnd)",f"a_primary_hi_{sfx}"),
                   ("secondary",f"a_secondary_{sfx}"),("tertiary",f"a_tertiary_{sfx}")]
                  +([("mining",'a_mining')] if v=="mining SEPARATE" else [])):
        for tn,tset in T.items():
            cells=[]
            for wl,waves,fe in (("2012",[2012],"district"),("2022",[2022],"district"),("pooled",[2012,2022],"dw")):
                b0,p0=run(o,tset,waves,fe,[]); b1,p1=run(o,tset,waves,fe,GEO)
                cells.append(f"{wl}: {b0:+.3f}[{p0:.3f}]{st(p0):3s}|{b1:+.3f}[{p1:.3f}]{st(p1):3s}")
            print(f"  {lab:20s} {tn:20s} " + "  ".join(cells))
