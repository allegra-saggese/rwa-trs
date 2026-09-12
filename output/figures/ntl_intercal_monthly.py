"""
ntl_intercal_monthly.py -- the per-satellite DMSP intercalibration refitted on MONTHLY overlaps, the
test that says whether it worked, and the check that licenses joining F18 to VIIRS.

    python ntl_intercal_monthly.py
    Analysis/ntl_intercal_monthly_lookup.csv      DN -> F15-scale DN, one column per satellite
    Analysis/ntl_intercal_monthly_validation.csv  test-retest of the treated-control gap, raw vs calibrated
    Analysis/ntl_f18_viirs_overlap.csv            the F18 / VIIRS gap, month by month, 2012-04 to 2014-02
    output/figures/ntl_intercal_monthly.pdf

SAME METHOD AS THE ANNUAL FIT (ntl_intercal.py), MORE DATA. Where two satellites flew in the same
month the ground is identical, so any difference is instrument. A monotone DN -> DN map is fitted by
quantile matching on the pooled overlap months of each pair and chained onto F15:

    F14 -> F15  2000-01..2003-12     F16 -> F15  2004-01..2007-12
    F12 -> F14  1997-04..1999-12     F10 -> F12  1994-09..1994-12

The annual fit had 12 overlap YEARS; this has about 133 overlap MONTHS.

ONLY OBSERVED PIXELS ENTER THE FIT. A monthly composite records a value for every pixel whether or not
any cloud-free night went into it. A pixel is used for a pair in a month only when BOTH satellites
saw it at least once that month (cf_cvg >= 1), so the map is fitted on measurements, not on fill.
A month whose cf_cvg clip is missing for either satellite is left out of the fit, not fitted unmasked.

F18 HAS NO DMSP PARTNER. F16 ends 2009-12 and F18 starts 2010-01, so F18 cannot be chained onto F15 by
measurement and is left uncalibrated. That seam is why the headline pre/post estimate is taken inside
the calibrated F10-F16 block (1992-2009), which holds the whole pre-period and five post years. What
F18 DOES overlap is VIIRS, 2012-04 to 2014-02. Over those months both sensors observe the same sectors,
so if the treated-control gap agrees between them, joining VIIRS onto F18 is a measurement, not an
assumption. Each sensor's gap is put in its own control-SD units for that comparison, because DN and
radiance are different quantities.

THE TEST. For every overlap month the treated-control gap is computed from each satellite. If the
calibration works, the two readings of the same month agree more after it than before: the test-retest
correlation rises and noise_to_signal (spread of the disagreement over spread of the gap) falls. The
numbers are reported whichever way they come out.
"""
import sys, re, collections
from pathlib import Path
import numpy as np, pandas as pd, geopandas as gpd, rasterio, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
from rasterio.features import rasterize
from scipy import stats
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Nighttime-Lights"))
import ntl_helpers as H
import bar_chart_housing as B
from event_ntl_monthly_prepost import setup

OUT, ANALYSIS = str(B.FIG), B.ANALYSIS
REFSAT, DNMAX, MIN_CF = "F15", 63, 1.0
CHAIN = [("F14", "F15"), ("F16", "F15"), ("F12", "F14"), ("F10", "F12")]


def by_sat_month(layer):
    out = collections.defaultdict(dict)
    for p in sorted(H.CLIPS.glob(f"ntl_dmsp_m_{layer}_F*_*.tif")):
        m = re.match(rf"ntl_dmsp_m_{layer}_(F\d\d)_(\d{{6}})_rwanda\.tif$", p.name)
        if m: out[m.group(1)][m.group(2)] = p
    return out


def read(p):
    with rasterio.open(p) as r:
        a = r.read(1).astype(float)
        return np.where(a == r.nodata, 0.0, a) if r.nodata is not None else a


def blank(p):
    """one value over all of Rwanda: not a measurement (F18 2012-12 is zero everywhere)"""
    a = read(p)
    return a.min() == a.max()


def quantile_map(src, dst):
    """monotone DN -> value lookup sending the q-th quantile of src to the q-th quantile of dst"""
    qs = np.linspace(0, 1, 1001)
    out = np.interp(np.arange(DNMAX + 1, dtype=float), np.quantile(src, qs), np.quantile(dst, qs))
    return np.maximum.accumulate(out)


def apply(lut, a):
    return np.interp(a, np.arange(DNMAX + 1, dtype=float), lut)


def main():
    L, G1, G2, G0 = setup()
    av, cf = by_sat_month("avgvis"), by_sat_month("cfcvg")
    dropped = []
    for s in av:
        for ym in [ym for ym, p in av[s].items() if blank(p)]:
            del av[s][ym]; dropped.append(f"{s}_{ym}")
    print(f"  dropped {len(dropped)} blank avg_vis composite(s): {', '.join(dropped) if dropped else 'none'}")
    ref = next(iter(av[REFSAT].values()))
    with rasterio.open(ref) as r: tr, shape = r.transform, r.shape
    lab = rasterize([(gm, i + 1) for i, gm in enumerate(L.geometry)], out_shape=shape,
                    transform=tr, fill=0, all_touched=True, dtype="int32")
    flat = lab.ravel(); inside = flat > 0; fk = flat[inside]; k = len(L)
    uid = L.uid.to_numpy()
    in1, inA, in0 = (np.isin(uid, list(s)) for s in (G1, G1 | G2, G0))

    def seen(s, ym):
        """pixels observed at least once that month; None if the cf_cvg clip is missing"""
        p = cf.get(s, {}).get(ym)
        return None if p is None else read(p).ravel()[inside] >= MIN_CF

    # ---- fit each pair on its pooled overlap months, observed pixels only ----
    pair_lut, used = {}, {}
    for s, r_ in CHAIN:
        months = sorted(set(av[s]) & set(av[r_]))
        S, R, n_ok = [], [], 0
        for ym in months:
            ms, mr = seen(s, ym), seen(r_, ym)
            if ms is None or mr is None:
                continue
            both = ms & mr
            S.append(read(av[s][ym]).ravel()[inside][both]); R.append(read(av[r_][ym]).ravel()[inside][both])
            n_ok += 1
        if not S:
            print(f"  {s} -> {r_}: {len(months)} overlap months, none with cf_cvg for both -- NOT FITTED")
            continue
        S, R = np.concatenate(S), np.concatenate(R)
        pair_lut[s] = quantile_map(S, R); used[s] = (len(months), n_ok, len(S))
        print(f"  {s} -> {r_}: {n_ok} of {len(months)} overlap months usable, {len(S):,} jointly observed pixels")

    lut = {REFSAT: np.arange(DNMAX + 1, dtype=float)}
    for s, r_ in CHAIN:
        if s in pair_lut:
            lut[s] = pair_lut[s] if r_ == REFSAT else apply(lut[r_], pair_lut[s]) if r_ in lut else None
    lut = {s: v for s, v in lut.items() if v is not None}
    print(f"  calibrated onto {REFSAT}: {sorted(lut)}   uncalibrated: {sorted(set(av) - set(lut))}")
    pd.DataFrame({"dn": np.arange(DNMAX + 1), **{s: lut[s] for s in sorted(lut)}}) \
      .to_csv(ANALYSIS / "ntl_intercal_monthly_lookup.csv", index=False)

    # ---- validation: the treated-control gap read by two satellites in the same month ----
    def gaps(a, s, mask, calibrated):
        v = a.ravel()[inside]
        if calibrated and s in lut: v = apply(lut[s], v)
        if mask is not None: v = np.where(mask, v, 0.0)
        y = np.arcsinh(np.bincount(fk, weights=v, minlength=k + 1)[1:])
        return {"Gates+": y[in1].mean() - y[in0].mean(), "Bordering or Gates+": y[inA].mean() - y[in0].mean()}

    rows = []
    months = collections.defaultdict(list)
    for s, mm in av.items():
        for ym in mm: months[ym].append(s)
    for ym, ss in sorted(months.items()):
        if len(ss) < 2 or "F18" in ss: continue
        a, b = sorted(ss)[:2]
        ma, mb = seen(a, ym), seen(b, ym)
        both = (ma & mb) if (ma is not None and mb is not None) else None
        for mode in ("raw", "calibrated"):
            ga = gaps(read(av[a][ym]), a, both, mode == "calibrated")
            gb = gaps(read(av[b][ym]), b, both, mode == "calibrated")
            for t in ga:
                rows.append(dict(ym=int(ym), satA=a, satB=b, mode=mode, treatment=t,
                                 masked=both is not None, gapA=ga[t], gapB=gb[t]))
    D = pd.DataFrame(rows)
    D["pair"] = D.satA + "/" + D.satB; D["year"] = D.ym // 100; D["moy"] = D.ym % 100
    # Three versions of the same statistic, because the plain monthly one flatters. Both satellites
    # in an overlap month are read over the SAME observed pixels, so month-to-month swings in which
    # pixels were cloud-free move both readings together; that common swing inflates the correlation
    # without saying anything about whether the instrument can see a treatment effect.
    #   monthly         as computed, for the record
    #   deseasonalised  each reading minus its pair x calendar-month mean: the seasonal composition
    #                   is gone, only departures from it remain
    #   annualised      monthly gaps averaged within pair-year, the unit the annual fit used -- this is
    #                   the one directly comparable with ntl_intercal.py
    val = []
    for (mode, t), q in D.groupby(["mode", "treatment"]):
        q = q.copy()
        for c in ("gapA", "gapB"):
            q[c + "_ds"] = q[c] - q.groupby(["pair", "moy"])[c].transform("mean")
        yr = q.groupby(["pair", "year"])[["gapA", "gapB"]].mean()
        for version, g1, g2 in (("monthly", q.gapA, q.gapB),
                                ("deseasonalised", q.gapA_ds, q.gapB_ds),
                                ("annualised", yr.gapA, yr.gapB)):
            g1, g2 = np.asarray(g1, float), np.asarray(g2, float)
            gm, dis = (g1 + g2) / 2, g1 - g2
            val.append(dict(version=version, mode=mode, treatment=t, n=len(g1),
                            share_masked=q.masked.mean(), test_retest_corr=np.corrcoef(g1, g2)[0, 1],
                            sd_gap=gm.std(ddof=1), sd_disagreement=dis.std(ddof=1),
                            noise_to_signal=dis.std(ddof=1) / gm.std(ddof=1)))
    V = pd.DataFrame(val).sort_values(["version", "treatment", "mode"])
    V.to_csv(ANALYSIS / "ntl_intercal_monthly_validation.csv", index=False)
    print("\nVALIDATION -- test-retest of the treated-control gap across overlap MONTHS")
    print(V.to_string(index=False, float_format=lambda x: f"{x:.4f}"))

    # ---- F18 vs VIIRS over their overlap: does the gap agree? ----
    vi = {m.group(1): p for p in sorted(H.CLIPS.glob("ntl_viirs_m_avg_*.tif"))
          if (m := re.match(r"ntl_viirs_m_avg_(\d{6})_rwanda\.tif$", p.name))}
    vcf = {m.group(1): p for p in sorted(H.CLIPS.glob("ntl_viirs_m_cfcvg_*.tif"))
           if (m := re.match(r"ntl_viirs_m_cfcvg_(\d{6})_rwanda\.tif$", p.name))}
    ov = sorted(set(av.get("F18", {})) & set(vi))
    O = pd.DataFrame()
    if ov:
        with rasterio.open(vi[ov[0]]) as r: vtr, vshape = r.transform, r.shape
        vlab = rasterize([(gm, i + 1) for i, gm in enumerate(L.geometry)], out_shape=vshape,
                         transform=vtr, fill=0, all_touched=True, dtype="int32").ravel()
        vin = vlab > 0; vk = vlab[vin]
        orow = []
        for ym in ov:
            f = read(av["F18"][ym]).ravel()[inside]; mf = seen("F18", ym)
            if mf is not None: f = np.where(mf, f, 0.0)
            yf = np.arcsinh(np.bincount(fk, weights=f, minlength=k + 1)[1:])
            v = read(vi[ym]).ravel()[vin]
            if ym in vcf: v = np.where(read(vcf[ym]).ravel()[vin] >= MIN_CF, v, 0.0)
            yv = np.arcsinh(np.bincount(vk, weights=v, minlength=k + 1)[1:])   # built exactly as the outcome is
            for t, it in (("Gates+", in1), ("Bordering or Gates+", inA)):
                sf, sv = yf[in0].std(ddof=1), yv[in0].std(ddof=1)
                orow.append(dict(ym=int(ym), treatment=t,
                                 gap_f18=(yf[it].mean() - yf[in0].mean()) / sf,
                                 gap_viirs=(yv[it].mean() - yv[in0].mean()) / sv))
        O = pd.DataFrame(orow); O.to_csv(ANALYSIS / "ntl_f18_viirs_overlap.csv", index=False)
        print(f"\nF18 vs VIIRS over {len(ov)} overlap months ({ov[0]}-{ov[-1]}), gaps in control-SD units")
        for t, q in O.groupby("treatment"):
            d = q.gap_viirs - q.gap_f18
            tt = stats.ttest_1samp(d, 0.0)
            print(f"  {t:20s} corr={np.corrcoef(q.gap_f18, q.gap_viirs)[0,1]:+.3f}  "
                  f"mean(VIIRS-F18)={d.mean():+.4f}  p={tt.pvalue:.3f}  n={len(q)}")
    else:
        print("\nF18 vs VIIRS: no overlap months on disk yet")

    # ---- figure ----
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.8))
    a0 = axes[0]
    for s in sorted(lut):
        a0.plot(np.arange(DNMAX + 1), lut[s], lw=1.4, label=f"{s} -> {REFSAT}")
    a0.plot([0, DNMAX], [0, DNMAX], color="#999", lw=.8, ls="--")
    a0.set_xlabel("observed digital number"); a0.set_ylabel(f"calibrated onto {REFSAT}")
    a0.legend(fontsize=8); a0.grid(lw=.3, color="#DDD"); a0.set_axisbelow(True)
    a1 = axes[1]; ts = sorted(V["treatment"].unique()); xs = np.arange(len(ts)); w = .35
    VA = V[V["version"] == "annualised"]
    for i, mode in enumerate(("raw", "calibrated")):
        vals = [VA[(VA["treatment"] == t) & (VA["mode"] == mode)]["test_retest_corr"].iloc[0] for t in ts]
        a1.bar(xs + (i - .5) * w, vals, w, label=mode, color="#9AA6AE" if mode == "raw" else "#B4501E")
    a1.set_xticks(xs); a1.set_xticklabels(ts, fontsize=9)
    a1.set_ylabel("test-retest correlation of the gap, annualised"); a1.axhline(0, color="#333", lw=.8)
    a1.legend(fontsize=8); a1.grid(axis="y", lw=.3, color="#DDD"); a1.set_axisbelow(True)
    a2 = axes[2]
    if len(O):
        for t, colr in (("Gates+", "#B4501E"), ("Bordering or Gates+", "#28506E")):
            q = O[O.treatment == t]
            a2.scatter(q.gap_f18, q.gap_viirs, s=14, color=colr, label=t)
        lo = np.nanmin(O[["gap_f18", "gap_viirs"]].to_numpy()); hi = np.nanmax(O[["gap_f18", "gap_viirs"]].to_numpy())
        a2.plot([lo, hi], [lo, hi], color="#999", lw=.8, ls="--")
        a2.set_xlabel("gap read by F18 (control SD)"); a2.set_ylabel("gap read by VIIRS (control SD)")
        a2.legend(fontsize=8)
    a2.grid(lw=.3, color="#DDD"); a2.set_axisbelow(True)
    fig.tight_layout()
    for ext in ("pdf",):                       # PDF only: the PNG twin was pure duplication
        fig.savefig(f"{OUT}/ntl_intercal_monthly.{ext}", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"\nwritten {OUT}/ntl_intercal_monthly.pdf")


if __name__ == "__main__":
    main()
