"""
event_ntl_gates_monthly.py -- the 5 km gate design on MONTHLY lights, 1992-2025.

    python event_ntl_gates_monthly.py [--perm N]
    output/figures/event_ntl_gates_monthly.pdf
    Analysis/nightlights_gates_monthly_cell.csv    cell-month panel, settled land
    Analysis/reg_nightlights_gates_monthly.csv     coefficients

The annual version of this design (event_ntl_gates.py) compares cells within 5 km of a park gate
against every cell beyond 5 km, and separately cells within 5 km of the park itself. This repeats it
on the monthly composites: 33 gate cells over roughly 400 months instead of 34 years.

    Y(c,m) = a_c + d_{district(c),m} + SUM_t b_t [within5(c) x 1(year(m)=t)] + e

Cell fixed effects, district-BY-MONTH fixed effects -- so cells are compared inside the same district
in the same calendar month, which absorbs the seasonal cloud cycle. Coefficients are reported by
year: month-by-month would be four hundred numbers each carrying one composite's precision.

Sector-by-year effects are NOT used, and that is deliberate: sectors average 47 km2 of settled land,
smaller than the scale this treatment varies over, so sector-by-time absorbs the treatment itself.

WHAT THIS ADDS OVER THE ANNUAL VERSION. The VIIRS-era growth result -- gate cells brightening about
0.147 control SD a year faster than the rest of the country -- sits entirely after treatment, so it
cannot test parallel trends. The monthly DMSP block has around 150 pre-2005 observations per cell,
enough to ask whether gate cells were already on a steeper path before revenue sharing began.

INFERENCE. Thirty-three treated cells in five districts is where clustered standard errors fail:
the cells are contiguous, so a good year at one gate is a good year at all of them, and clustering at
sector assumes that away. Every headline coefficient therefore carries a randomisation p-value, with
treatment reassigned BY SECTOR in whole blocks until it covers as many cells as the real treatment --
a cell-wise shuffle would scatter the placebo across the country and destroy the spatial clustering
that makes the real assignment hard to tell from a lucky draw. On the annual panel that correction
moved the post-2005 gate DiD from a clustered p of 0.089 to a randomisation p of 0.247.
"""
import sys, collections, re
from pathlib import Path
import numpy as np, pandas as pd, geopandas as gpd, rasterio, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
from shapely.geometry import Point
from scipy import stats
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Nighttime-Lights"))
import ntl_helpers as H
import bar_chart_housing as B
import event_ntl_monthly_prepost as M
import event_ntl_groups as GR
from event_ntl_gates import settled

OUT, ANALYSIS = str(B.FIG), B.ANALYSIS
REF, JOIN, KM, POST = 2004, 2013, 5.0, 2005
N_PERM = int(sys.argv[sys.argv.index("--perm") + 1]) if "--perm" in sys.argv else 400


def geometry():
    """cells with at least 0.5 km2 of settled land, and their distance to a gate and to a park"""
    g, T, X, never = B.geography()
    pk = gpd.read_file(B.GEO / "protected-areas/rwanda_protected_areas_geodata_rw.gpkg")
    pk = pk[pk.designate.astype(str).str.contains("National Park", case=False, na=False)]
    pk32 = pk.to_crs(32736)
    allpark = pk32[pk32.geometry.area > 1e5].to_crs(4326).union_all()
    blk = lambda s: pk32[pk32.areaname.astype(str).str.contains(s, case=False, na=False)].union_all()
    longstanding = blk("Volcanoes").union(blk("Nyungwe")).union(blk("Akagera"))
    gate = gpd.GeoSeries([Point(*B.GATE_XY[s]) for s in B.GATES], crs=4326).to_crs(32736).union_all()
    cel = gpd.read_file(H.CELLS)
    cel["cid"] = cel.cell_id.astype(int); cel["uid"] = cel.sector_id.astype(int)
    L = settled(cel, allpark)
    L32 = L.to_crs(32736)
    L["d_gate"] = L32.geometry.distance(gate).to_numpy() / 1000
    L["d_park"] = L32.geometry.distance(longstanding).to_numpy() / 1000
    return L, X["Kigali all + cities"]


def prep(panel, series, dcol):
    s = panel[(panel.series == series) & panel.asinh_sum.notna()].copy()
    s["treat"] = (s[dcol] <= KM).astype(float)
    base = M.SERIES[series]["base"]
    sd = s[(s.year == base) & (s.treat == 0)].asinh_sum.std(ddof=1)
    s["yv"] = s.asinh_sum / sd if np.isfinite(sd) and sd > 0 else s.asinh_sum
    s["dm"] = s.district.astype(str) + "_" + s.ym.astype(str)
    return s


def randomise(s, weight, n_perm, seed=20260912):
    """observed coefficient, clustered se, and the randomisation p from sector-block reassignment"""
    P = M.fast_proj([s.cid.to_numpy(), s.dm.to_numpy()])
    yt = M.fast_absorb(s.yv.to_numpy(float).reshape(-1, 1), P)[:, 0]
    cid, uid = s.cid.to_numpy(), s.uid.to_numpy()
    cell_sec = s.groupby("cid").uid.first()
    treated = set(s.loc[s.treat == 1, "cid"]); ntre = len(treated)
    G = pd.factorize(pd.Series(uid))[0]; ng = G.max() + 1

    def beta(cells):
        x = M.fast_absorb((np.isin(cid, list(cells)).astype(float) * weight).reshape(-1, 1), P)[:, 0]
        den = float(x @ x)
        if den <= 0:
            return None, None
        b = float((x @ yt) / den); e = yt - x * b
        num = np.zeros(ng); np.add.at(num, G, x * e)
        return b, float(np.sqrt((num @ num) * (ng / (ng - 1))) / den)

    b, se = beta(treated)
    secs = sorted(cell_sec.unique()); rng = np.random.default_rng(seed)
    draws = []
    for _ in range(n_perm):
        rng.shuffle(secs); pick, n = set(), 0
        for sc in secs:
            cs = set(cell_sec.index[cell_sec == sc]); pick |= cs; n += len(cs)
            if n >= ntre:
                break
        bb, _ = beta(pick)
        if bb is not None:
            draws.append(bb)
    d = np.asarray(draws)
    return b, se, (1 + (np.abs(d) >= abs(b)).sum()) / (1 + len(d)), len(d)


def event(s, ref):
    per = sorted(s.year.unique()); use = [q for q in per if q != ref]
    if ref not in per:
        raise RuntimeError(f"reference year {ref} absent (years {per[0]}-{per[-1]})")
    P = M.fast_proj([s.cid.to_numpy(), s.dm.to_numpy()])
    R = M.fast_absorb(np.column_stack([s.yv.to_numpy(float)] +
                                      [(s.treat * (s.year == q)).to_numpy(float) for q in use]), P)
    r = M.ols_v(R[:, 0], R[:, 1:], s.uid.to_numpy())
    if r is None:
        raise RuntimeError("event-study design is rank-deficient")
    b, V, _ = r
    ev = pd.concat([pd.DataFrame({"period": use, "b": b, "se": np.sqrt(np.maximum(np.diag(V), 0))}),
                    pd.DataFrame({"period": [ref], "b": [0.0], "se": [0.0]})]).sort_values("period")
    return ev


def main():
    L, kigali = geometry()
    print(f"{len(L)} cells with settled land; gate cells within {KM:.0f} km: "
          f"{(L.d_gate <= KM).sum()}, park cells: {(L.d_park <= KM).sum()}")
    lp = ANALYSIS / "ntl_intercal_monthly_lookup.csv"
    lut = {}
    if lp.exists():
        lk = pd.read_csv(lp); lut = {c: lk[c].to_numpy(float) for c in lk.columns if c != "dn"}
    print(f"  intercalibration onto F15: {sorted(lut) if lut else 'NONE'}")

    parts = []
    for kind in ("dmsp", "viirs"):
        z, _ = M.sector_sums(L, kind, lut, idcol="cid")
        if z is not None:
            z["kind"] = kind; parts.append(z)
    raw = pd.concat(parts, ignore_index=True)
    panel = pd.concat([M.build_series(raw, n, idcol="cid") for n in M.SERIES], ignore_index=True)
    panel = panel.merge(L[["cid", "uid", "district", "d_gate", "d_park", "land_km2"]], on="cid", how="left")
    panel = panel[~panel.uid.isin(kigali)].copy()
    panel["year"] = panel.ym // 100
    panel.to_csv(ANALYSIS / "nightlights_gates_monthly_cell.csv", index=False)
    for n, q in panel.groupby("series"):
        print(f"  {n:9s}: {q.cid.nunique()} cells x {q.ym.nunique()} months, {q.asinh_sum.notna().sum():,} observed")

    rows, EV = [], {}
    for what, dcol in (("gate", "d_gate"), ("park", "d_park")):
        for series in M.SERIES:
            s = prep(panel, series, dcol)
            if s.empty:
                continue
            ref = REF if series.startswith("dmsp") else JOIN
            ev = event(s, ref)
            EV[(what, series)] = ev
            rows += [dict(what=what, series=series, kind="event", year=int(r.period), b=r.b, se=r.se)
                     for r in ev.itertuples()]
        # pre/post on the calibrated DMSP block, and growth in the VIIRS era
        for series, mode, t0, lab in (("dmsp_cal", "post", POST, "DiD post-2005 (calibrated F10-F16)"),
                                      ("viirs_m", "trend", 2012, "growth/yr 2012-2025"),
                                      ("viirs_m", "trend", 2017, "growth/yr 2017-2025")):
            s = prep(panel, series, dcol)
            s = s[s.year >= t0] if mode == "trend" else s
            if s.empty or not ((s.year < POST).any() or mode == "trend"):
                continue
            w = (s.year - t0).to_numpy(float) if mode == "trend" else (s.year >= t0).to_numpy(float)
            b, se, pri, nd = randomise(s, w, N_PERM)
            rows.append(dict(what=what, series=series, kind="ri_" + mode, year=t0, b=b, se=se,
                             p=float(2 * (1 - stats.norm.cdf(abs(b / se)))) if se else np.nan,
                             p_ri=pri, n_perm=nd, n=len(s), months=s.ym.nunique()))
            print(f"  {what:4s} {lab:34s} b={b:+.4f} se={se:.4f} "
                  f"clustered p={2 * (1 - stats.norm.cdf(abs(b / se))):.4f}  randomisation p={pri:.3f}")
    R = pd.DataFrame(rows)
    R.to_csv(ANALYSIS / "reg_nightlights_gates_monthly.csv", index=False)
    draw(R)


def draw(R):
    fig, axes = plt.subplots(1, 2, figsize=(15.5, 5.6), sharey=True)
    for ax, (what, title) in zip(axes, (("gate", "Within 5 km of a park GATE"),
                                        ("park", "Within 5 km of the PARK"))):
        ev = lambda sname: (R[(R.what == what) & (R.kind == "event") & (R.series == sname)]
                            .rename(columns={"year": "period"}).sort_values("period"))
        ax.axvspan(2004.5, 2025.5, color="#EDE6D6", alpha=.7, lw=0, zorder=0)
        ax.axvline(JOIN, color="#8C8C8C", lw=1.0, ls="--"); ax.axhline(0, color="#333", lw=1.0)
        D, V = ev("dmsp_all"), ev("viirs_m").copy()
        off = float(D.loc[D.period == JOIN, "b"].iloc[0]); ose = float(D.loc[D.period == JOIN, "se"].iloc[0])
        V["b"] = V.b + off; V["se"] = np.sqrt(V.se ** 2 + ose ** 2)
        both = pd.concat([D, V[V.period > JOIN]])
        ax.errorbar(both.period, both.b, yerr=1.96 * both.se, fmt="o", ms=4.0, color="#B4501E",
                    ecolor="#B4501E", elinewidth=1.05, capsize=1.9, zorder=3)
        ax.plot(both.period, both.b, color="#B4501E", lw=1.05, alpha=.45, zorder=2)
        note = []
        for kind, t0, lab in (("ri_post", POST, "DiD post-2005"), ("ri_trend", 2012, "VIIRS growth/yr")):
            q = R[(R.what == what) & (R.kind == kind) & (R.year == t0)]
            if len(q):
                note.append(f"{lab}  {q.b.iloc[0]:+.3f}  (clustered p={q.p.iloc[0]:.3f}, "
                            f"randomisation p={q.p_ri.iloc[0]:.3f})")
        # fig.text: make_tex_figures.py silences it, so the paper's copy carries no note
        fig.text(.015, .015, "\n".join(note), transform=ax.transAxes, fontsize=8.0, va="bottom",
                 bbox=dict(fc="white", ec="#CCC", lw=.6, pad=4))
        ax.set_title(title + "  —  against all cells beyond", fontsize=10.5, pad=8)
        ax.set_xticks(np.arange(1992, 2026, 2))
        ax.set_xticklabels(np.arange(1992, 2026, 2), rotation=55, fontsize=7.6)
        ax.set_xlim(1991, 2026); ax.grid(axis="y", lw=.35, color="#DDD"); ax.set_axisbelow(True)
        y0, y1 = ax.get_ylim()
        ax.text(1992.4, y1 - .04 * (y1 - y0), "DMSP", fontsize=8.4, color="#777", va="top")
        ax.text(2013.4, y1 - .04 * (y1 - y0), "VIIRS", fontsize=8.4, color="#777", va="top")
    axes[0].set_ylabel("asinh(sum of lights), SD units, relative to 2004", fontsize=9.5)
    fig.tight_layout()
    for ext in ("pdf",):                       # PDF only: the PNG twin was pure duplication
        fig.savefig(f"{OUT}/event_ntl_gates_monthly.{ext}", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"written {OUT}/event_ntl_gates_monthly.pdf")


if __name__ == "__main__":
    main()
