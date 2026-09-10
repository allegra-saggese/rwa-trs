"""
ntl_monthly_groups.py -- the three-group design on MONTHLY VIIRS, 2012-04 to 2025-12.

    python ntl_monthly_groups.py
    Analysis/nightlights_monthly_settled_sector.csv   settled-land monthly panel
    Analysis/reg_nightlights_monthly.csv              event-study and seasonal coefficients
    output/figures/event_ntl_monthly.pdf / .png

WHAT THIS CAN AND CANNOT DO. VIIRS monthly begins in April 2012, seven years after revenue sharing
started, so there is no pre-treatment period and a post-2005 difference-in-differences is NOT
estimable here. Two things are:

  levels    Y(u,m) = a_u + d_{district(u),m} + SUM_m b1_m [G1 x 1(month=m)]
                                             + SUM_m b2_m [G2 x 1(month=m)] + e
            read against April 2012. This is the annual event study repeated at monthly frequency:
            it describes the path since 2012, not an effect of the 2005 treatment.

  seasonal  Y(u,m) = a_u + d_{district(u),m} + SUM_k g1_k [G1 x 1(calendar month=k)]
                                             + SUM_k g2_k [G2 x 1(calendar month=k)] + e
            the amplitude of the within-year cycle, by group, against December. If tourism drives
            lighting at the gates, G1 should show a cycle that G2 and the controls do not. This is
            the genuinely new thing monthly data buys.

THE CLOUD CONFOUND, WHICH IS WHY cf_cvg IS CARRIED. Rwanda has two rainy seasons. In a cloudy month
the composite is built from fewer cloud-free nights, so a dark month and a barely-observed month look
alike. Every specification therefore controls for the sector's cloud-free observation count, and the
seasonal specification is also reported on the subsample of unit-months with at least 3 cloud-free
nights. Without this, cloud seasonality would masquerade as a tourism season.

Park area is removed from every unit before the lights are counted, as in the annual design: treated
sectors lose 31.6% of their area to park against 0.2% for controls.
"""
import sys, re, textwrap
from pathlib import Path
import numpy as np, pandas as pd, geopandas as gpd, rasterio, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
from rasterio.features import rasterize
from scipy import stats
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Nighttime-Lights"))
import ntl_helpers as H
import bar_chart_housing as B          # never alias to C: shadows patsy C()
import ntl_engine_gates as E

OUT, ANALYSIS = str(B.FIG), B.ANALYSIS
SS, MIN_KM2 = H.SUPERSAMPLE, 0.5
REF = 201204


def settled(gdf, parks):
    g = gdf.to_crs(4326).copy()
    g["land"] = g.geometry.difference(parks)
    km2 = gpd.GeoSeries(g.land, crs=4326).to_crs(32736).area / 1e6
    keep = (~g.land.is_empty) & (km2 >= MIN_KM2)
    g = g[keep].copy(); g["land_km2"] = km2[keep].to_numpy()
    return g.set_geometry("land")


def zonal_monthly(gdf, idcol):
    """asinh(sum of radiance) and mean cloud-free count per unit-month, on settled land"""
    files = {}
    for p in sorted(H.CLIPS.glob("ntl_viirs_m_avg_*.tif")):
        m = re.match(r"ntl_viirs_m_avg_(\d{6})_rwanda\.tif$", p.name)
        if m: files.setdefault(int(m.group(1)), {})["avg"] = p
    for p in sorted(H.CLIPS.glob("ntl_viirs_m_cfcvg_*.tif")):
        m = re.match(r"ntl_viirs_m_cfcvg_(\d{6})_rwanda\.tif$", p.name)
        if m: files.setdefault(int(m.group(1)), {})["cf"] = p
    ref = files[sorted(files)[0]]["avg"]
    with rasterio.open(ref) as r: tr, shape = r.transform, r.shape
    fine = rasterio.Affine(tr.a / SS, tr.b, tr.c, tr.d, tr.e / SS, tr.f)
    lab = rasterize([(gm, i + 1) for i, gm in enumerate(gdf.geometry)],
                    out_shape=(shape[0] * SS, shape[1] * SS), transform=fine, fill=0, dtype="int32")
    f = lab.ravel(); keep = f > 0; fk = f[keep]; k = len(gdf)
    n = np.bincount(fk, minlength=k + 1)[1:].astype(float)
    rows = []
    for ym in sorted(files):
        d = files[ym]
        if "avg" not in d: continue
        with rasterio.open(d["avg"]) as r:
            a = r.read(1).astype(float)
            if r.nodata is not None: a = np.where(a == r.nodata, 0.0, a)
        v = np.repeat(np.repeat(a, SS, axis=0), SS, axis=1).ravel()[keep]
        tot = np.bincount(fk, weights=v, minlength=k + 1)[1:] / (SS * SS)
        cf = np.full(k, np.nan)
        if "cf" in d:
            with rasterio.open(d["cf"]) as r:
                c = r.read(1).astype(float)
                if r.nodata is not None: c = np.where(c == r.nodata, 0.0, c)
            cv = np.repeat(np.repeat(c, SS, axis=0), SS, axis=1).ravel()[keep]
            cf = np.bincount(fk, weights=cv, minlength=k + 1)[1:] / np.maximum(n, 1)
        rows.append(pd.DataFrame({idcol: gdf[idcol].to_numpy(), "ym": ym,
                                  "asinh_sum": np.arcsinh(tot), "cfcvg": cf}))
    return pd.concat(rows, ignore_index=True)


def fit(panel, unitcol, terms, keycol, ref, extra=None, sub=None):
    s = panel if sub is None else panel[sub].copy()
    s = s[s.asinh_sum.notna()].copy()
    ctrl = np.logical_and.reduce([s[t] == 0 for t in terms])
    sd = s[(s[keycol] == ref) & ctrl].asinh_sum.std(ddof=1)
    s["yv"] = s.asinh_sum / sd if np.isfinite(sd) and sd > 0 else s.asinh_sum
    tk = (s.district.astype(str) + "_" + s.ym.astype(str)).to_numpy()
    per = sorted(s[keycol].unique()); use = [p for p in per if p != ref]
    cols = [(t, p) for t in terms for p in use]
    X = [(s[t] * (s[keycol] == p)).to_numpy(float) for t, p in cols]
    names = [(t, p) for t, p in cols]
    if extra is not None:
        for e in extra:
            X.append(s[e].fillna(s[e].mean()).to_numpy(float)); names.append((e, np.nan))
    R = E.absorb(np.column_stack([s.yv.to_numpy(float)] + X), [s[unitcol].to_numpy(), tk])
    r = E.ols(R[:, 0], R[:, 1:], s.uid.to_numpy())
    if r is None: return None
    b, se, _, ng = r
    out = pd.DataFrame({"term": [t for t, _ in names], "period": [p for _, p in names],
                        "b": b, "se": se})
    out["p"] = 2 * (1 - stats.norm.cdf(np.abs(out.b / np.maximum(out.se, 1e-12))))
    out = pd.concat([out, pd.DataFrame({"term": terms, "period": ref, "b": 0.0, "se": 0.0, "p": np.nan})])
    out["n"] = len(s); out["clusters"] = ng
    return out.sort_values(["term", "period"])


def main():
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
    print(f"G1 {len(G1)}  G2 {len(G2)}  G0 {len(G0)}  Gishwati dropped {len(GISH)}")

    sec = gpd.read_file(H.SECTORS); sec["uid"] = sec.sector_id.astype(int)
    L = settled(sec, allpark)
    p = zonal_monthly(L, "uid").merge(L[["uid", "district", "land_km2"]], on="uid", how="left")
    p = p[p.uid.isin(G1 | G2 | G0)].copy()
    p["G1"] = p.uid.isin(G1).astype(float); p["G2"] = p.uid.isin(G2).astype(float)
    p["moy"] = p.ym % 100
    p.to_csv(ANALYSIS / "nightlights_monthly_settled_sector.csv", index=False)
    print(f"  panel: {p.uid.nunique()} sectors x {p.ym.nunique()} months = {len(p)} rows")

    res = []
    ev = fit(p, "uid", ["G1", "G2"], "ym", REF, extra=["cfcvg"])
    if ev is not None: res.append(ev.assign(spec="event_monthly"))
    se_all = fit(p, "uid", ["G1", "G2"], "moy", 12, extra=["cfcvg"])
    if se_all is not None: res.append(se_all.assign(spec="seasonal"))
    se_cl = fit(p, "uid", ["G1", "G2"], "moy", 12, extra=["cfcvg"], sub=(p.cfcvg >= 3))
    if se_cl is not None: res.append(se_cl.assign(spec="seasonal_cf3"))
    R = pd.concat(res, ignore_index=True)
    R.to_csv(ANALYSIS / "reg_nightlights_monthly.csv", index=False)

    LBL = {"G1": ("Gates+ (12): revenue sharing and tourism", "#B4501E", "o"),
           "G2": ("The other 32: revenue sharing only", "#3E6E8E", "s")}
    fig, axes = plt.subplots(1, 2, figsize=(15.5, 5.4))
    a = axes[0]
    a.axhline(0, color="#333", lw=1.0)
    for t, (lab, col, mk) in LBL.items():
        q = R[(R.spec == "event_monthly") & (R.term == t)].sort_values("period")
        xs = pd.to_datetime(q.period.astype(int).astype(str) + "01", format="%Y%m%d")
        a.plot(xs, q.b, color=col, lw=1.0, label=lab)
        a.fill_between(xs, q.b - 1.96 * q.se, q.b + 1.96 * q.se, color=col, alpha=.16, lw=0)
    a.set_title("Monthly path since April 2012", fontsize=11, pad=8)
    a.set_ylabel("asinh(sum of radiance), SD units, vs 2012-04", fontsize=9)
    a.grid(axis="y", lw=.3, color="#DDD"); a.set_axisbelow(True); a.legend(fontsize=8, loc="upper left")
    b_ = axes[1]
    b_.axhline(0, color="#333", lw=1.0)
    MON = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    for t, (lab, col, mk) in LBL.items():
        q = R[(R.spec == "seasonal") & (R.term == t)].sort_values("period")
        b_.errorbar(q.period, q.b, yerr=1.96 * q.se, fmt=mk, ms=4, color=col, ecolor=col,
                    elinewidth=1.0, capsize=2, label=lab)
        b_.plot(q.period, q.b, color=col, lw=1.0, alpha=.5)
    b_.set_xticks(range(1, 13)); b_.set_xticklabels(MON, fontsize=8)
    b_.set_title("Within-year cycle, against December", fontsize=11, pad=8)
    b_.grid(axis="y", lw=.3, color="#DDD"); b_.set_axisbelow(True)
    fig.tight_layout()
    for ext in ("pdf", "png"):
        fig.savefig(f"{OUT}/event_ntl_monthly.{ext}", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"written {OUT}/event_ntl_monthly.pdf/.png")
    for spec in ("seasonal", "seasonal_cf3"):
        q = R[R.spec == spec]
        for t in ("G1", "G2"):
            qq = q[(q.term == t) & q.period.notna()]
            if len(qq):
                print(f"  {spec:14s} {t}: range {qq.b.min():+.3f} to {qq.b.max():+.3f}, "
                      f"significant months {int((qq.p < .05).sum())}/{len(qq)}")


if __name__ == "__main__":
    main()
