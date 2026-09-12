"""
event_ntl_monthly_prepost.py -- the three-group design on MONTHLY lights, 1992-2025.

    python event_ntl_monthly_prepost.py [--perm N]
    output/figures/event_ntl_monthly_prepost.pdf / .png
    Analysis/nightlights_monthly_settled_sector.csv    sector-month panel, settled land, every series
    Analysis/reg_nightlights_monthly_prepost.csv       event-study, pre/post and randomisation results

WHY MONTHLY. The annual design has thirteen pre-treatment observations per sector. The monthly
composites give about 150, which is what makes a pre-trend test informative rather than decorative.
Nothing else changes: same three groups, same settled land, same reference year, same clustering. If
monthly and annual disagree, the annual series was fitting noise.

    G1  Gates+ (12) ........ revenue sharing AND tourism
    G2  the other 32 ....... revenue sharing ONLY
    G0  319 ................ comparison group
    dropped: Kigali and the four largest towns of 2002 (44), and the 9 Gishwati-Mukura sectors,
    whose park was gazetted in 2015-16 and which would otherwise be treated units among the controls.

THE REGRESSION, on sector-MONTH rows:

    Y(u,m) = a_u + d_{district(u),m} + SUM_t b1_t [G1(u) x 1(year(m)=t)]
                                     + SUM_t b2_t [G2(u) x 1(year(m)=t)] + e

    a_u       sector fixed effects
    d_{d,m}   district-by-MONTH fixed effects: sectors are compared inside the same district in the
              same calendar month. This absorbs the seasonal cloud cycle -- Rwanda's cloud-free night
              count runs from 2.5 in April to 8.8 in July -- and any shock common to a district-month.
    b_t       by YEAR. Month-by-month coefficients would be four hundred numbers with the precision of
              one composite each; the year dummies are coarser than the fixed effects, so the monthly
              rows buy precision without buying unreadable estimates.
    reference year 2004, the last before revenue sharing. Errors clustered at sector.
    pre/post: the same equation with [G1 x post] and [G2 x post], post = year >= 2005.

THE OUTCOME. asinh of the sum of lights over each sector's SETTLED land -- park removed, because park
is dark by construction and treated sectors lose 31.6% of their area to it against 0.2% for controls.
Only observed pixels count: a pixel with no cloud-free night that month (cf_cvg = 0) is not a dark
pixel, it is a missing one, so it is dropped from the sum rather than added as zero, and a sector-month
seen over less than 90% of its settled land is dropped. Each series is put in its own control-SD units.

THREE SERIES, BECAUSE OF ONE SEAM.
    dmsp_cal   F10-F16 intercalibrated onto F15, 1992-2009       HEADLINE
    dmsp_all   F10-F18, F18 uncalibrated, 1992-2014               robustness
    viirs_m    VIIRS, 2012-2025, shown joined to dmsp_all at 2013
F16 ends in 2009 and F18 starts in 2010, with no month where both flew, so F18 cannot be put on the
F15 scale by measurement. The headline therefore stays inside the calibrated block, which holds the
whole pre-period and five post-treatment years, and never crosses that seam. dmsp_all crosses it and
relies on the district-by-month effects to absorb it; if the two agree, the seam is not driving
anything. VIIRS is joined at 2013 inside the F18/VIIRS overlap (2012-04 to 2014-02), the join tested in
ntl_intercal_monthly.py; that join is a plotting convention with its own variance carried, never used
to identify a coefficient.

INFERENCE WITH TWELVE TREATED SECTORS. Clustered errors assume many treated clusters. G1 has twelve,
in five districts, so its clustered p-value is optimistic. Each pre/post coefficient is therefore also
tested by randomisation: the group's label is reassigned at random among that group and the controls,
holding the other group fixed, the equation is re-estimated, and p_ri is the share of reassignments
with an estimate at least as large in absolute value. That p-value makes no large-sample assumption.
"""
import sys, re, collections
from pathlib import Path
import numpy as np, pandas as pd, geopandas as gpd, rasterio, matplotlib
import scipy.sparse as sp
matplotlib.use("Agg"); import matplotlib.pyplot as plt
from rasterio.features import rasterize
from scipy import stats
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Nighttime-Lights"))
import ntl_helpers as H
import bar_chart_housing as B
import ntl_engine_gates as E
from event_ntl_groups import settled

OUT, ANALYSIS = str(B.FIG), B.ANALYSIS
SS = H.SUPERSAMPLE
REF, JOIN, POST, MIN_CF, MIN_OBS = 2004, 2013, 2005, 1.0, 0.90
N_PERM = int(sys.argv[sys.argv.index("--perm") + 1]) if "--perm" in sys.argv else 999
SERIES = {
    "dmsp_cal": dict(kind="dmsp", sats=("F10", "F12", "F14", "F15", "F16"), span=(1992, 2009), base=2002),
    "dmsp_all": dict(kind="dmsp", sats=("F10", "F12", "F14", "F15", "F16", "F18"), span=(1992, 2014), base=2002),
    "viirs_m": dict(kind="viirs", sats=None, span=(2012, 2025), base=2013),
}
HEADLINE = "dmsp_cal"
RX = {"dmsp": re.compile(r"^ntl_dmsp_m_(avgvis|cfcvg)_(F\d\d)_(\d{6})_rwanda\.tif$"),
      "viirs": re.compile(r"^ntl_viirs_m_(avg|cfcvg)_(\d{6})_rwanda\.tif$")}


def setup():
    """settled-land sectors and the three groups, built exactly as event_ntl_groups.py builds them"""
    g, T, X, never = B.geography()
    G1 = set(T["Gates+"]); G2 = set(T["Bordering or Gates+"]) - G1
    pk = gpd.read_file(B.GEO / "protected-areas/rwanda_protected_areas_geodata_rw.gpkg")
    pk = pk[pk.designate.astype(str).str.contains("National Park", case=False, na=False)]
    pk32 = pk.to_crs(32736)
    allpark = pk32[pk32.geometry.area > 1e5].to_crs(4326).union_all()
    gm = pk32[pk32.areaname.astype(str).str.contains("Gishwati|Mukura", case=False, na=False)].union_all()
    g32 = g.to_crs(32736)
    GISH = set(g32.sid[g32.geometry.distance(gm) == 0])
    G0 = set(g.sid) - G1 - G2 - X["Kigali all + cities"] - GISH
    sec = gpd.read_file(H.SECTORS); sec["uid"] = sec.sector_id.astype(int)
    L = settled(sec, allpark)
    return L, G1, G2, G0


def inventory(kind):
    """{(sat, ym): {layer: path}}; sat is '' for VIIRS"""
    inv = collections.defaultdict(dict)
    for p in sorted(H.CLIPS.glob("*.tif")):
        m = RX[kind].match(p.name)
        if not m: continue
        if kind == "dmsp":
            inv[(m.group(2), m.group(3))]["cf" if m.group(1) == "cfcvg" else "y"] = p
        else:
            inv[("", m.group(2))]["cf" if m.group(1) == "cfcvg" else "y"] = p
    return {k: v for k, v in inv.items() if "y" in v}


def read(p):
    with rasterio.open(p) as r:
        a = r.read(1).astype(float)
        return np.where(a == r.nodata, 0.0, a) if r.nodata is not None else a


def sector_sums(L, kind, lut):
    """per satellite-month: sum of lights on settled land (observed pixels only) and share observed"""
    inv = inventory(kind)
    if not inv:
        return None, False
    use_cf = all("cf" in v for v in inv.values())
    print(f"  {kind}: {len(inv)} satellite-months, cf_cvg for "
          f"{sum('cf' in v for v in inv.values())} -> masking {'ON' if use_cf else 'OFF (cf_cvg incomplete)'}")
    with rasterio.open(next(iter(inv.values()))["y"]) as r: tr, shape = r.transform, r.shape
    fine = rasterio.Affine(tr.a / SS, tr.b, tr.c, tr.d, tr.e / SS, tr.f)
    lab = rasterize([(gm, i + 1) for i, gm in enumerate(L.geometry)],
                    out_shape=(shape[0] * SS, shape[1] * SS), transform=fine, fill=0, dtype="int32")
    f = lab.ravel(); keep = f > 0; fk = f[keep]; k = len(L)
    up = lambda a: np.repeat(np.repeat(a, SS, axis=0), SS, axis=1).ravel()[keep]
    allp = np.bincount(fk, minlength=k + 1)[1:]
    grid = np.arange(64, dtype=float)
    rows, blank = [], []
    for (sat, ym), v in sorted(inv.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        a = read(v["y"])
        # A composite with one value over all of Rwanda is not a measurement. F18 2012-12 is zero
        # everywhere while its own cf_cvg says 99.9% of pixels were seen. Kept, it would enter as a
        # month in which every sector is exactly dark.
        if a.min() == a.max():
            blank.append(f"{sat}{'_' if sat else ''}{ym}"); continue
        if kind == "dmsp" and sat in lut:
            a = np.interp(a, grid, lut[sat])
        ok = up(read(v["cf"]) >= MIN_CF) if use_cf else np.ones(keep.sum(), bool)
        x = up(a)
        rows.append(pd.DataFrame({"uid": L.uid.to_numpy(), "sat": sat, "ym": int(ym),
                                  "sum": np.bincount(fk, weights=np.where(ok, x, 0.0), minlength=k + 1)[1:] / SS**2,
                                  "obs": np.bincount(fk, weights=ok.astype(float), minlength=k + 1)[1:] / np.maximum(allp, 1)}))
    if blank:
        print(f"  {kind}: dropped {len(blank)} blank composite(s): {', '.join(blank)}")
    return pd.concat(rows, ignore_index=True), use_cf


def build_series(raw, name):
    """average the satellites flying in each month, then asinh; drop barely-observed sector-months

    The total is scaled to the sector's WHOLE settled area before averaging. Summing only the
    observed pixels would otherwise measure coverage as much as light: a sector seen at 85% carries a
    smaller total than the identical sector seen in full. That is not neutral across groups -- treated
    sectors border parks, sit in cloudier terrain, and are observed less (0.79 of sector-months clear
    the threshold against 0.86 for controls) -- and the shortfall SHRANK from 10 points in 1992-94 to
    4 by 2005-09, so the treated totals drifted upward against controls for purely instrumental
    reasons. That drift is what the pre-trend test was picking up. Scaling by the observed share
    estimates the full-area total, assuming the unseen part of a sector resembles the seen part.
    """
    s = SERIES[name]
    r = raw[raw.kind == s["kind"]].copy()
    if s["sats"] is not None:
        r = r[r.sat.isin(s["sats"])]
    r = r[(r.ym // 100).between(*s["span"])]
    r["scaled"] = np.where(r.obs > 0, r["sum"] / r.obs, np.nan)
    g = r.groupby(["uid", "ym"], as_index=False).agg(total=("scaled", "mean"), raw_total=("sum", "mean"),
                                                     obs=("obs", "min"), n_sat=("sat", "nunique"))
    g["asinh_sum"] = np.where(g.obs >= MIN_OBS, np.arcsinh(g.total), np.nan)
    g["asinh_unscaled"] = np.where(g.obs >= MIN_OBS, np.arcsinh(g.raw_total), np.nan)
    g["series"] = name
    return g


def ols_v(yv, Xm, sid):
    """OLS with the full cluster-robust covariance, which a joint pre-trend test needs"""
    XtX = Xm.T @ Xm
    if np.linalg.matrix_rank(XtX) < XtX.shape[0]:
        return None
    inv = np.linalg.inv(XtX); b = inv @ (Xm.T @ yv); e = yv - Xm @ b
    G = pd.factorize(pd.Series(sid))[0]; ng = G.max() + 1
    S = np.zeros((ng, Xm.shape[1])); np.add.at(S, G, Xm * e[:, None])
    return b, inv @ (S.T @ S) @ inv * (ng / max(ng - 1.0, 1)), ng


def prep(panel, name, terms):
    s = panel[(panel.series == name) & panel.asinh_sum.notna()].copy()
    ctrl = np.logical_and.reduce([s[t] == 0 for t in terms])
    sd = s[(s.year == SERIES[name]["base"]) & ctrl].asinh_sum.std(ddof=1)
    s["yv"] = s.asinh_sum / sd
    s["dm"] = s.district.astype(str) + "_" + s.ym.astype(str)
    return s


def event(panel, name, terms, ref):
    s = prep(panel, name, terms)
    per = sorted(s.year.unique()); use = [p for p in per if p != ref]
    # Without the reference year in the data every year dummy is present, their sum reproduces the
    # group indicator, and the sector effects absorb it: the design is singular. Say so, rather than
    # hand back nothing and let the caller draw an empty figure.
    if ref not in per:
        raise RuntimeError(f"{name}: reference year {ref} has no observations (years present {per[0]}-{per[-1]}, "
                           f"{len(per)} of {per[-1] - per[0] + 1}); the clips for it are missing")
    cols = [(t, p) for t in terms for p in use]
    R = E.absorb(np.column_stack([s.yv.to_numpy(float)] +
                                 [(s[t] * (s.year == p)).to_numpy(float) for t, p in cols]),
                 [s.uid.to_numpy(), s.dm.to_numpy()])
    r = ols_v(R[:, 0], R[:, 1:], s.uid.to_numpy())
    if r is None:
        raise RuntimeError(f"{name}: event-study design is rank-deficient after absorbing the fixed effects")
    b, V, _ = r
    ev = pd.concat([pd.DataFrame({"term": [t for t, _ in cols], "period": [p for _, p in cols],
                                  "b": b, "se": np.sqrt(np.maximum(np.diag(V), 0))}),
                    pd.DataFrame({"term": terms, "period": ref, "b": 0.0, "se": 0.0})]).sort_values(["term", "period"])
    pre = {}
    for t in terms:
        idx = [i for i, (tt, p) in enumerate(cols) if tt == t and p < POST]
        if idx:
            bb, VV = b[idx], V[np.ix_(idx, idx)]
            w = float(bb @ np.linalg.pinv(VV) @ bb)
            pre[t] = (w, len(idx), 1 - stats.chi2.cdf(w, len(idx)))
    return ev, pre


def pretrend_ri(panel, name, term, n_perm, seed=20260912):
    """randomisation p-value for the joint pre-trend test

    The chi-square version of this test over-rejects here and not mildly. The year coefficients are
    group-by-year common shocks, and these sectors are adjacent, strung along park borders in a few
    districts; clustering at sector assumes independence across sectors within a year, which is what
    spatially correlated shocks violate. Measured on this panel, random 12-sector groups produce a
    MEDIAN pre-trend Wald of 32.5 against the real Gates+ value of 20.6, so chi-square called
    p=0.057 where the randomisation distribution says 0.81. The label is therefore reassigned at
    random among that group and the controls and the same statistic recomputed; p_ri is the share of
    reassignments reaching the observed value. It assumes nothing about the error structure.
    """
    s = prep(panel, name, ["G1", "G2"])
    per = sorted(s.year.unique()); use = [q for q in per if q != REF]
    pre = [i for i, q in enumerate(use) if q < POST]
    uid = s.uid.to_numpy(); yr = s.year.to_numpy()
    P = fast_proj([uid, s.dm.to_numpy()])
    yt = fast_absorb(s.yv.to_numpy(float).reshape(-1, 1), P)[:, 0]
    G = pd.factorize(pd.Series(uid))[0]; ng = G.max() + 1

    def wald(units):
        ind = np.isin(uid, list(units)).astype(float)
        X = fast_absorb(np.column_stack([ind * (yr == q) for q in use]), P)
        XtX = X.T @ X
        if np.linalg.matrix_rank(XtX) < XtX.shape[0]:
            return None
        inv = np.linalg.inv(XtX); b = inv @ (X.T @ yt); e = yt - X @ b
        S = np.zeros((ng, X.shape[1])); np.add.at(S, G, X * e[:, None])
        V = inv @ (S.T @ S) @ inv * (ng / (ng - 1))
        bb, VV = b[pre], V[np.ix_(pre, pre)]
        try:
            return float(bb @ np.linalg.solve(VV, bb))
        except np.linalg.LinAlgError:
            return None

    tu = set(s.loc[s[term] == 1, "uid"])
    pool = np.array(sorted(tu | set(s.loc[(s.G1 == 0) & (s.G2 == 0), "uid"])))
    obs = wald(tu)
    rng = np.random.default_rng(seed)
    draws = [w for w in (wald(set(rng.choice(pool, size=len(tu), replace=False))) for _ in range(n_perm))
             if w is not None]
    d = np.asarray(draws)
    return obs, (1 + (d >= obs).sum()) / (1 + len(d)), len(d), float(np.median(d))


def fast_proj(keys):
    out = []
    for k in keys:
        c, u = pd.factorize(pd.Series(k)); n = len(c)
        S = sp.csr_matrix((np.ones(n), (np.arange(n), c)), shape=(n, len(u)))
        out.append((S, np.asarray(S.sum(0)).ravel()))
    return out


def fast_absorb(M, P, maxit=2000, tol=1e-10):
    M = np.array(M, float)
    for _ in range(maxit):
        chg = 0.0
        for S, cnt in P:
            d = S @ ((S.T @ M) / cnt[:, None]); chg = max(chg, float(np.abs(d).max())); M -= d
        if chg < tol: break
    return M


def prepost(panel, name, terms, n_perm, seed=20260911):
    s = prep(panel, name, terms)
    if not ((s.year < POST).any() and (s.year >= POST).any()):
        return None
    post = (s.year >= POST).to_numpy(float); uid = s.uid.to_numpy()
    R = E.absorb(np.column_stack([s.yv.to_numpy(float)] + [(s[t].to_numpy() * post) for t in terms]),
                 [uid, s.dm.to_numpy()])
    r = ols_v(R[:, 0], R[:, 1:], uid)
    if r is None:
        raise RuntimeError(f"{name}: pre/post design is rank-deficient after absorbing the fixed effects")
    b, V, ng = r
    se = np.sqrt(np.maximum(np.diag(V), 0))
    res = pd.DataFrame({"term": terms, "b": b, "se": se,
                        "p": 2 * (1 - stats.norm.cdf(np.abs(b / np.maximum(se, 1e-12)))),
                        "n": len(s), "months": s.ym.nunique(), "clusters": ng, "p_ri": np.nan, "n_perm": 0})
    if n_perm and set(terms) == {"G1", "G2"}:
        P = fast_proj([uid, s.dm.to_numpy()])
        yt = R[:, 0]
        units = np.array(sorted(s.uid.unique()))
        rng = np.random.default_rng(seed)
        for j, t in enumerate(terms):
            other = terms[1 - j]
            tu = set(s.loc[s[t] == 1, "uid"]); pool = np.array(sorted(tu | set(s.loc[s[other] + s[t] == 0, "uid"])))
            xo = R[:, 1 + (1 - j)]
            draws = []
            for start in range(0, n_perm, 100):
                m = min(100, n_perm - start)
                cols = np.empty((len(s), m))
                for c in range(m):
                    pick = set(rng.choice(pool, size=len(tu), replace=False))
                    cols[:, c] = np.isin(uid, list(pick)) * post
                Xt = fast_absorb(cols, P)
                for c in range(m):
                    Xm = np.column_stack([Xt[:, c], xo])
                    draws.append(np.linalg.solve(Xm.T @ Xm, Xm.T @ yt)[0])
            draws = np.asarray(draws)
            res.loc[res.term == t, "p_ri"] = (1 + (np.abs(draws) >= abs(b[j])).sum()) / (1 + len(draws))
            res.loc[res.term == t, "n_perm"] = len(draws)
            print(f"    randomisation {name} {t}: {len(draws)} draws, p_ri={res.loc[res.term == t, 'p_ri'].iloc[0]:.4f}")
    return res


def main():
    import os
    rp = ANALYSIS / "reg_nightlights_monthly_prepost.csv"
    if os.environ.get("NTL_REUSE") and rp.exists():
        # redraw only, from the saved estimates: make_tex_figures.py needs the picture, not a second
        # hour of estimation and 999 fresh randomisation draws
        print(f"  NTL_REUSE: drawing from {rp.name}")
        return draw(pd.read_csv(rp))
    L, G1, G2, G0 = setup()
    print(f"G1 {len(G1)}  G2 {len(G2)}  G0 {len(G0)}")
    lp = ANALYSIS / "ntl_intercal_monthly_lookup.csv"
    lut = {}
    if lp.exists():
        lk = pd.read_csv(lp); lut = {c: lk[c].to_numpy(float) for c in lk.columns if c != "dn"}
    print(f"  intercalibration lookup: {sorted(lut) if lut else 'NONE -- run ntl_intercal_monthly.py first'}")
    if not lut:
        sys.exit("refusing to build dmsp_cal without the intercalibration lookup")

    parts, cfused = [], {}
    for kind in ("dmsp", "viirs"):
        z, cfused[kind] = sector_sums(L, kind, lut)
        if z is not None:
            z["kind"] = kind; parts.append(z)
    raw = pd.concat(parts, ignore_index=True)
    panel = pd.concat([build_series(raw, n) for n in SERIES], ignore_index=True)
    panel = panel.merge(L[["uid", "district", "land_km2"]].drop_duplicates("uid"), on="uid", how="left")
    panel = panel[panel.uid.isin(G1 | G2 | G0)].copy()
    panel["year"] = panel.ym // 100; panel["month"] = panel.ym % 100
    panel["G1"] = panel.uid.isin(G1).astype(float); panel["G2"] = panel.uid.isin(G2).astype(float)
    panel["ANY"] = ((panel.G1 + panel.G2) > 0).astype(float)
    panel.to_csv(ANALYSIS / "nightlights_monthly_settled_sector.csv", index=False)
    for n, q in panel.groupby("series"):
        print(f"  {n:9s}: {q.uid.nunique()} sectors x {q.ym.nunique()} months ({q.ym.min()}-{q.ym.max()}), "
              f"{q.asinh_sum.notna().sum():,} observed of {len(q):,}")

    rows, EV, PRE = [], {}, {}
    cf = lambda n: "on" if cfused[SERIES[n]["kind"]] else "off"
    for name in SERIES:
        ref = REF if SERIES[name]["kind"] == "dmsp" else JOIN
        ev, pre = event(panel, name, ["G1", "G2"], ref)
        if ev is not None:
            EV[name], PRE[name] = ev, pre
            rows += [dict(series=name, kind="event", term=r.term, year=int(r.period), b=r.b, se=r.se, cfcvg=cf(name))
                     for r in ev.itertuples()]
            rows += [dict(series=name, kind="pretrend_wald", term=t, b=w, se=np.nan, p=pv, n=df, cfcvg=cf(name))
                      for t, (w, df, pv) in pre.items()]
        if name == HEADLINE:
            for term in ("G1", "G2"):
                o, pri, nd, med = pretrend_ri(panel, name, term, max(200, N_PERM // 5))
                rows.append(dict(series=name, kind="pretrend_ri", term=term, b=o, p_ri=pri,
                                 n_perm=nd, se=med, cfcvg=cf(name)))
                print(f"    pre-trend randomisation {term}: Wald {o:.2f}, p_ri={pri:.3f} "
                      f"({nd} draws, median draw {med:.1f})")
        pp = prepost(panel, name, ["G1", "G2"], N_PERM if name == HEADLINE else 0)
        if pp is not None:
            rows += [dict(series=name, kind="prepost", term=r.term, b=r.b, se=r.se, p=r.p, p_ri=r.p_ri,
                          n_perm=r.n_perm, n=r.n, months=r.months, clusters=r.clusters, cfcvg=cf(name))
                     for r in pp.itertuples()]
            inc = prepost(panel, name, ["ANY", "G1"], 0)          # G1 here is b1 - b2
            r = inc[inc.term == "G1"].iloc[0]
            rows.append(dict(series=name, kind="prepost", term="G1 minus G2", b=r.b, se=r.se, p=r.p,
                             n=r.n, months=r.months, clusters=r.clusters, cfcvg=cf(name)))
    R = pd.DataFrame(rows)
    R.to_csv(ANALYSIS / "reg_nightlights_monthly_prepost.csv", index=False)
    print()
    for r in R[R.kind == "pretrend_wald"].itertuples():
        print(f"  pre-trend  {r.series:9s} {r.term}: Wald {r.b:.2f} on {int(r.n)} df, p={r.p:.4f}")
    for r in R[R.kind == "prepost"].itertuples():
        ri = f"  p_ri={r.p_ri:.4f}" if pd.notna(r.p_ri) else ""
        print(f"  pre/post   {r.series:9s} {r.term:12s} b={r.b:+.4f} se={r.se:.4f} p={r.p:.4f}{ri}  "
              f"n={int(r.n):,} months={int(r.months)} clusters={int(r.clusters)}")

    draw(R)


def draw(R):
    """the figure, in the style of event_ntl_groups.py, built only from the saved results table"""
    ev = lambda n, term: (R[(R.series == n) & (R.kind == "event") & (R.term == term)]
                          .rename(columns={"year": "period"}).sort_values("period"))
    LBL = {"G1": ("Gates+ (12): revenue sharing and tourism", "#B4501E", "o"),
           "G2": ("The other 32: revenue sharing only", "#3E6E8E", "s")}
    fig, ax = plt.subplots(figsize=(10.5, 5.8))
    ax.axvspan(2004.5, 2025.5, color="#EDE6D6", alpha=.7, lw=0, zorder=0)
    ax.axvline(JOIN, color="#8C8C8C", lw=1.0, ls="--"); ax.axhline(0, color="#333", lw=1.0)
    notes = []
    for term, (lab, col, mk) in LBL.items():
        D = ev("dmsp_all", term); V = ev("viirs_m", term).copy()
        off = float(D.loc[D.period == JOIN, "b"].iloc[0]); ose = float(D.loc[D.period == JOIN, "se"].iloc[0])
        V["b"] = V.b + off; V["se"] = np.sqrt(V.se ** 2 + ose ** 2)
        both = pd.concat([D, V[V.period > JOIN]])
        ax.errorbar(both.period, both.b, yerr=1.96 * both.se, fmt=mk, ms=4.0, color=col, ecolor=col,
                    elinewidth=1.05, capsize=1.9, zorder=3, label=lab)
        ax.plot(both.period, both.b, color=col, lw=1.05, alpha=.45, zorder=2)
        h = R[(R.series == HEADLINE) & (R.kind == "prepost") & (R.term == term)].iloc[0]
        wr = R[(R.series == HEADLINE) & (R.kind == "pretrend_ri") & (R.term == term)]
        pt = f"pre-trend randomisation p={wr.p_ri.iloc[0]:.2f}" if len(wr) else "pre-trend n/a"
        notes.append(f"{term}  {pt}   pre/post {h.b:+.3f} (p={h.p:.2f}, randomisation p={h.p_ri:.2f})")
    hi = R[(R.series == HEADLINE) & (R.kind == "prepost") & (R.term == "G1 minus G2")].iloc[0]
    notes.append(f"G1 - G2  {hi.b:+.3f} (p={hi.p:.2f})        pre/post on calibrated F10-F16, 1992-2009")
    # fig.text, not ax.text: make_tex_figures.py silences Figure.text, so the numbers appear on the
    # working figure and are left out of the paper's, where they belong in the note under it
    fig.text(.015, .015, "\n".join(notes), transform=ax.transAxes, fontsize=7.6, va="bottom",
             bbox=dict(fc="white", ec="#CCC", lw=.6, pad=4))
    ax.set_xticks(np.arange(1992, 2026, 2))
    ax.set_xticklabels(np.arange(1992, 2026, 2), rotation=55, fontsize=7.6)
    ax.set_xlim(1991, 2026); ax.grid(axis="y", lw=.35, color="#DDD"); ax.set_axisbelow(True)
    y0, y1 = ax.get_ylim()
    ax.text(1992.4, y1 - .04 * (y1 - y0), "DMSP", fontsize=8.4, color="#777", va="top")
    ax.text(2013.4, y1 - .04 * (y1 - y0), "VIIRS", fontsize=8.4, color="#777", va="top")
    ax.set_ylabel("asinh(sum of lights), SD units, relative to 2004", fontsize=9.5)
    ax.legend(fontsize=9.0, loc="upper center", ncol=2, frameon=False, bbox_to_anchor=(.5, 1.10))
    fig.tight_layout()
    for ext in ("pdf", "png"):
        fig.savefig(f"{OUT}/event_ntl_monthly_prepost.{ext}", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"written {OUT}/event_ntl_monthly_prepost.pdf/.png")


if __name__ == "__main__":
    main()
