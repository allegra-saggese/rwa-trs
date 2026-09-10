"""
ntl_intercal.py -- a Rwanda-local per-satellite intercalibration of DMSP, and the test that says
whether it worked.

    python ntl_intercal.py
    Analysis/ntl_intercal_lookup.csv     the fitted DN -> DN maps, one per satellite
    Analysis/ntl_intercal_validation.csv the before/after reliability test
    output/figures/ntl_intercal.pdf/.png

WHY NOT LI OR CHEN. Both are global fits dominated by bright cities, then applied to Rwanda's dim
range as an extrapolation. This fits on Rwanda's own pixels instead, which is interpolation inside
the range we care about.

WHAT IS FITTED. In twelve years two DMSP satellites flew at once over Rwanda. In those years the
ground truth is identical by construction, so any difference between the two readings is instrument.
For each satellite S with an overlap partner R, all overlap years are pooled and a monotone
DN -> DN map is fitted by quantile matching: the q-th quantile of S is sent to the q-th quantile of
R. Quantile matching is monotone by construction, so it cannot reorder sectors, and with avg_vis on
a 0-63 digital-number scale it reduces to a 64-entry lookup table.

THE CHAIN. F15 is the reference (identity): it spans 2000-2007 and overlaps both its neighbours.
    F14 -> F15   via 2000-2003        F16 -> F15   via 2004-2007
    F12 -> F14   via 1997-1999        F10 -> F12   via 1994
composed to give every satellite a map onto the F15 scale. F18 (2010-2013) NEVER overlaps another
satellite -- F16 ends in 2009 - so it cannot be chained by measurement and is left uncalibrated and
reported separately. The seam sits in the tail: the whole pre-period and the first five post-treatment
years are inside the chained block.

THE TEST, WHICH IS THE POINT. Uncalibrated, two satellites observing the same sectors in the same
year disagree about the treated-control gap by more than that gap varies across years -- test-retest
correlation 0.45 at best and about 0.10 for Gates+. The same statistic is recomputed on the
calibrated series. If it rises, the DMSP era becomes usable. If it does not, the instability is not
a calibration problem and I stop claiming it can be fixed. Both answers are reported.
"""
import sys, re, collections, textwrap
from pathlib import Path
import numpy as np, pandas as pd, geopandas as gpd, rasterio, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
from rasterio.features import rasterize
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Nighttime-Lights"))
import ntl_helpers as H
import bar_chart_housing as B          # never alias to C: shadows patsy C()

OUT, ANALYSIS = str(B.FIG), B.ANALYSIS
REFSAT = "F15"
CHAIN = [("F14", "F15"), ("F16", "F15"), ("F12", "F14"), ("F10", "F12")]
DNMAX = 63


def satellite_years():
    sat = collections.defaultdict(dict)
    for p in sorted(H.CLIPS.glob("ntl_dmsp_avgvis_F*_*.tif")):
        m = re.match(r"ntl_dmsp_avgvis_(F\d\d)_(\d{4})_rwanda\.tif$", p.name)
        if m: sat[m.group(1)][int(m.group(2))] = p
    return sat


def read(p):
    with rasterio.open(p) as r:
        a = r.read(1).astype(float)
        if r.nodata is not None: a = np.where(a == r.nodata, 0.0, a)
    return a


def quantile_map(src, dst):
    """monotone DN->value lookup sending the q-th quantile of src to the q-th quantile of dst"""
    qs = np.linspace(0, 1, 1001)
    sq, dq = np.quantile(src, qs), np.quantile(dst, qs)
    grid = np.arange(DNMAX + 1, dtype=float)
    out = np.interp(grid, sq, dq)
    return np.maximum.accumulate(out)          # enforce monotonicity against quantile ties


def main():
    g, T, X, never = B.geography()
    sec = gpd.read_file(H.SECTORS); sec["uid"] = sec.sector_id.astype(int)
    sat = satellite_years()

    ref = sat[REFSAT][sorted(sat[REFSAT])[0]]
    with rasterio.open(ref) as r: tr, shape = r.transform, r.shape
    lab = rasterize([(gm, i + 1) for i, gm in enumerate(sec.geometry)], out_shape=shape,
                    transform=tr, fill=0, all_touched=True, dtype="int32")
    flat = lab.ravel(); inside = flat > 0; fk = flat[inside]; k = len(sec)

    # ---- fit one lookup per satellite pair, pooling that pair's overlap years ----
    pair_lut, pair_years = {}, {}
    for s, r_ in CHAIN:
        yrs = sorted(set(sat[s]) & set(sat[r_]))
        if not yrs:
            print(f"  {s} -> {r_}: NO OVERLAP, cannot fit"); continue
        S = np.concatenate([read(sat[s][y]).ravel()[inside] for y in yrs])
        R = np.concatenate([read(sat[r_][y]).ravel()[inside] for y in yrs])
        pair_lut[s] = quantile_map(S, R); pair_years[s] = yrs
        print(f"  {s} -> {r_}: fitted on {len(yrs)} overlap year(s) {yrs}, {len(S):,} pixels")

    # ---- compose along the chain onto the F15 scale ----
    lut = {REFSAT: np.arange(DNMAX + 1, dtype=float)}
    for s, r_ in CHAIN:
        if s not in pair_lut: continue
        base = pair_lut[s]
        if r_ == REFSAT:
            lut[s] = base
        else:
            grid = np.arange(DNMAX + 1, dtype=float)
            lut[s] = np.interp(base, grid, lut[r_])
    uncalibrated = [s for s in sat if s not in lut]
    print(f"  calibrated onto {REFSAT}: {sorted(lut)}")
    print(f"  NOT calibrated (no overlap partner): {uncalibrated}")

    pd.DataFrame({"dn": np.arange(DNMAX + 1), **{s: lut[s] for s in sorted(lut)}}) \
      .to_csv(ANALYSIS / "ntl_intercal_lookup.csv", index=False)

    # ---- sector asinh(sum) before and after, per satellite-year ----
    def sector_sums(a, s):
        v = a.ravel()[inside]
        if s in lut: v = np.interp(v, np.arange(DNMAX + 1, dtype=float), lut[s])
        return np.arcsinh(np.bincount(fk, weights=v, minlength=k + 1)[1:])

    ctrl = sec.uid.isin(set(sec.uid) - never - X["Kigali all + cities"]).to_numpy()
    rows = []
    byyear = collections.defaultdict(list)
    for s, yy in sat.items():
        for y in yy: byyear[y].append(s)
    for y, ss in sorted(byyear.items()):
        if len(ss) < 2: continue
        a, b_ = sorted(ss)[:2]
        for mode in ("raw", "calibrated"):
            va = sector_sums(read(sat[a][y]), a if mode == "calibrated" else "__none__")
            vb = sector_sums(read(sat[b_][y]), b_ if mode == "calibrated" else "__none__")
            for tn, tset in T.items():
                istr = sec.uid.isin(set(tset)).to_numpy()
                rows.append(dict(year=y, satA=a, satB=b_, mode=mode, treatment=tn,
                                 gapA=va[istr].mean() - va[ctrl].mean(),
                                 gapB=vb[istr].mean() - vb[ctrl].mean()))
    D = pd.DataFrame(rows)

    val = []
    for (mode, tn), q in D.groupby(["mode", "treatment"]):
        g1, g2 = q.gapA.to_numpy(), q.gapB.to_numpy()
        gm, dis = (g1 + g2) / 2, g1 - g2
        val.append(dict(mode=mode, treatment=tn, n_overlap_years=len(q),
                        test_retest_corr=np.corrcoef(g1, g2)[0, 1],
                        sd_gap=gm.std(ddof=1), sd_disagreement=dis.std(ddof=1),
                        noise_to_signal=dis.std(ddof=1) / gm.std(ddof=1)))
    V = pd.DataFrame(val).sort_values(["treatment", "mode"])
    V.to_csv(ANALYSIS / "ntl_intercal_validation.csv", index=False)
    print("\nVALIDATION -- test-retest of the treated-control gap")
    print(V.to_string(index=False, float_format=lambda x: f"{x:.4f}"))

    fig, axes = plt.subplots(1, 2, figsize=(13.5, 5.0))
    a0 = axes[0]
    for s in sorted(lut):
        a0.plot(np.arange(DNMAX + 1), lut[s], lw=1.4, label=f"{s} -> {REFSAT}")
    a0.plot([0, DNMAX], [0, DNMAX], color="#999", lw=.8, ls="--")
    a0.set_xlabel("observed digital number", fontsize=9)
    a0.set_ylabel(f"calibrated onto {REFSAT}", fontsize=9)
    a0.set_title("Fitted per-satellite maps", fontsize=11, pad=8)
    a0.legend(fontsize=8); a0.grid(lw=.3, color="#DDD"); a0.set_axisbelow(True)
    a1 = axes[1]
    w = 0.35; ts = sorted(V["treatment"].unique())
    xs = np.arange(len(ts))
    for i, mode in enumerate(("raw", "calibrated")):
        # V["mode"], never V.mode: that attribute is pandas' DataFrame.mode() method
        vals = [V[(V["treatment"] == t) & (V["mode"] == mode)]["test_retest_corr"].iloc[0] for t in ts]
        a1.bar(xs + (i - .5) * w, vals, w, label=mode,
               color="#9AA6AE" if mode == "raw" else "#B4501E")
    a1.set_xticks(xs); a1.set_xticklabels(ts, fontsize=9)
    a1.set_ylabel("test-retest correlation of the treated-control gap", fontsize=9)
    a1.set_title("Does calibration make the gap reproducible?", fontsize=11, pad=8)
    a1.axhline(0, color="#333", lw=.8); a1.legend(fontsize=8)
    a1.grid(axis="y", lw=.3, color="#DDD"); a1.set_axisbelow(True)
    fig.tight_layout()
    for ext in ("pdf", "png"):
        fig.savefig(f"{OUT}/ntl_intercal.{ext}", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"\nwritten {OUT}/ntl_intercal.pdf/.png")


if __name__ == "__main__":
    main()
