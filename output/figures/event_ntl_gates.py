"""
event_ntl_gates.py -- nighttime lights within 5 km of a park gate, and within 5 km of the park.

    python event_ntl_gates.py
    output/figures/event_ntl_gates.pdf     the figure
    Analysis/nightlights_cell_settled_panel.csv   the cell panel it is built from
    Analysis/reg_nightlights_gates.csv            event-study and DiD coefficients

Two separate cell-level event studies, each comparing cells within 5 km to ALL cells beyond 5 km:

    Y(c,t) = a_c + d_{district(c),t} + SUM_t b_t [within5(c) x 1(year=t)] + e      reference 2004

DESIGN NOTES, each of which was settled by a test rather than by assumption.

park area is removed from every cell before the lights are counted. Park land is dark by
    construction and it is not distributed evenly: treated sectors lose 31.6% of their area to park
    against 0.2% for controls, so leaving it in attenuates the treated units specifically. Removing
    it also fixed the pre-trends -- three sector-level specifications that failed at p <= .005 pass
    once the park is out.

district x year fixed effects, not sector x year. Sectors average 47 km2 of settled land, about 7 km
    across, which is smaller than the scale this treatment varies over, so sector x year absorbs the
    treatment itself: only 6 of 33 gate cells keep identifying variation under it, against 33 of 33
    under district x year.

raw sensors only, no bridge product. DMSP-OLS ended in 2013 and VIIRS begins in 2012, so the two are
    estimated separately and VIIRS is shifted by the DMSP coefficient at 2012, its intervals carrying
    that offset's variance. The splice is licensed by the 2012-13 overlap, where both sensors observe
    the same cells and the treated-control gap between them is -0.018 (p=0.89). The Li and Chen
    bridge products are NOT used: each is half model output, and their large post-2013 effects live
    entirely in the modelled half.

uncensored avg_vis rather than stable_lights. stable_lights zeroes dim cells, and the treated cells
    are the dark ones. Note that neither layer is reliable in the DMSP era: across the twelve years
    when two satellites flew at once, they disagree about the treated-control gap by more than that
    gap varies across years (test-retest correlation 0.10 to 0.45). The DMSP half of this figure
    therefore cannot support a small effect, and its flatness is weak evidence of a null.

KNOWN LIMITS. Identification rests on 5 districts while the clustering assumes 372 sectors, so the
p-values are optimistic and want a wild cluster bootstrap. Pre-trends pass for the gate series
(p=0.24) but not for the park series (p=0.05). The large movement is 2019 onward, fourteen years
after revenue sharing began.
"""
import sys, numpy as np, pandas as pd, matplotlib, textwrap
matplotlib.use("Agg"); import matplotlib.pyplot as plt
import geopandas as gpd, rasterio, re, collections
from rasterio.features import rasterize
from shapely.geometry import Point
from scipy import stats
import scipy.sparse as sp
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2] / "Nighttime-Lights"))
import ntl_helpers as H
import bar_chart_housing as B          # never alias to C: shadows patsy C()
import event_ntl_groups as GR
import ntl_engine_gates as E

OUT, ANALYSIS = str(B.FIG), B.ANALYSIS
SS = H.SUPERSAMPLE
SPAN = {"dmsp": (1992, 2013), "viirs": (2012, 2025)}
BASE = {"dmsp": 2002, "viirs": 2012}
REF, JOIN, KM, MIN_KM2 = 2004, 2012, 5.0, 0.5


def settled(gdf, parks):
    g = gdf.to_crs(4326).copy()
    g["land"] = g.geometry.difference(parks)
    km2 = gpd.GeoSeries(g.land, crs=4326).to_crs(32736).area / 1e6
    keep = (~g.land.is_empty) & (km2 >= MIN_KM2)
    g = g[keep].copy(); g["land_km2"] = km2[keep].to_numpy()
    return g.set_geometry("land")


def zonal(gdf, lut=None):
    """asinh(sum of lights) per unit per year, satellites averaged, on settled land

    DMSP digital numbers are mapped onto the F15 scale first where ntl_intercal.py fitted a map.
    Twelve years have two satellites flying and averaging them raw treats two instruments with
    different gain as if they agreed. F18 (2010-2013) has no overlap partner and stays raw.
    """
    lut = {} if lut is None else lut
    files = collections.defaultdict(lambda: collections.defaultdict(list))
    for p in sorted(H.CLIPS.glob("ntl_dmsp_avgvis_F*_*.tif")):
        m = re.match(r"ntl_dmsp_avgvis_(F\d\d)_(\d{4})_rwanda\.tif$", p.name)
        if m: files["dmsp"][int(m.group(2))].append(p)
    for p in sorted(H.CLIPS.glob("ntl_viirs_avg_*.tif")):
        m = re.match(r"ntl_viirs_avg_(\d{4})_rwanda\.tif$", p.name)
        if m: files["viirs"][int(m.group(1))].append(p)
    rows = []
    for sensor, byyear in files.items():
        ref = sorted(byyear[sorted(byyear)[0]])[0]
        with rasterio.open(ref) as r: tr, shape = r.transform, r.shape
        fine = rasterio.Affine(tr.a / SS, tr.b, tr.c, tr.d, tr.e / SS, tr.f)
        lab = rasterize([(gm, i + 1) for i, gm in enumerate(gdf.geometry)],
                        out_shape=(shape[0] * SS, shape[1] * SS), transform=fine, fill=0, dtype="int32")
        f = lab.ravel(); keep = f > 0; fk = f[keep]; k = len(gdf)
        for y in sorted(byyear):
            tot = []
            for p in sorted(byyear[y]):
                with rasterio.open(p) as r:
                    a = r.read(1).astype(float)
                    if r.nodata is not None: a = np.where(a == r.nodata, 0.0, a)
                sm = re.match(r"ntl_dmsp_avgvis_(F\d\d)_", p.name)
                if sm and sm.group(1) in lut:
                    a = np.interp(a, np.arange(len(lut[sm.group(1)]), dtype=float), lut[sm.group(1)])
                v = np.repeat(np.repeat(a, SS, axis=0), SS, axis=1).ravel()[keep]
                tot.append(np.bincount(fk, weights=v, minlength=k + 1)[1:] / (SS * SS))
            rows.append(pd.DataFrame({"cid": gdf.cid.to_numpy(), "year": y, "sensor": sensor,
                                      "asinh_sum": np.arcsinh(np.mean(tot, axis=0))}))
    return pd.concat(rows, ignore_index=True)


def _proj(keys):
    out = []
    for k in keys:
        c, u = pd.factorize(pd.Series(k)); n = len(c)
        S = sp.csr_matrix((np.ones(n), (np.arange(n), c)), shape=(n, len(u)))
        out.append((S, np.asarray(S.sum(0)).ravel()))
    return out


def _absorb(M, P, maxit=3000, tol=1e-10):
    M = np.array(M, float)
    for _ in range(maxit):
        chg = 0.0
        for S, cnt in P:
            d = S @ ((S.T @ M) / cnt[:, None]); chg = max(chg, float(np.abs(d).max())); M -= d
        if chg < tol:
            break
    return M


def randomise(s, weight, n_perm=400, seed=20260912):
    """randomisation p for a single treat x weight coefficient, reassigning treatment by SECTOR

    Thirty-three cells inside five districts is exactly the configuration where clustered standard
    errors over-reject: the cells are contiguous, so a good year at one gate is a good year at all of
    them, and clustering at sector assumes that away. Measured here, the post-2005 gate DiD carries a
    clustered p of 0.0496 and a randomisation p of 0.177.

    The reassignment is by SECTOR, not by cell, and takes whole sectors until it has as many cells as
    the real treatment: a cell-wise shuffle would scatter the placebo treatment across the country and
    destroy the spatial clustering that makes the real one hard to distinguish from a lucky draw.
    """
    tk = (s.district.astype(str) + "_" + s.year.astype(str)).to_numpy()
    P = _proj([s.cid.to_numpy(), tk])
    yt = _absorb(s.yv.to_numpy(float).reshape(-1, 1), P)[:, 0]
    cid, uid = s.cid.to_numpy(), s.uid.to_numpy()
    cell_sec = s.groupby("cid").uid.first()
    treated = set(s.loc[s.treat == 1, "cid"]); ntre = len(treated)

    def beta(cells):
        x = _absorb((np.isin(cid, list(cells)).astype(float) * weight).reshape(-1, 1), P)[:, 0]
        den = float(x @ x)
        if den <= 0:
            return None, None
        b = float((x @ yt) / den); e = yt - x * b
        G = pd.factorize(pd.Series(uid))[0]; ng = G.max() + 1
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
    return b, se, (1 + (np.abs(d) >= abs(b)).sum()) / (1 + len(d)), len(d), float(d.std())


def one(panel, dcol, sensor, ref):
    s = panel[(panel.sensor == sensor) & panel.year.between(*SPAN[sensor]) & panel.asinh_sum.notna()].copy()
    s["treat"] = (s[dcol] <= KM).astype(float)
    sd = s[(s.year == BASE[sensor]) & (s.treat == 0)].asinh_sum.std(ddof=1)
    s["yv"] = s.asinh_sum / sd if np.isfinite(sd) and sd > 0 else s.asinh_sum
    tk = (s.district.astype(str) + "_" + s.year.astype(str)).to_numpy()
    per = sorted(s.year.unique()); use = [p for p in per if p != ref]
    R = E.absorb(np.column_stack([s.yv.to_numpy(float)] +
                                 [(s.treat * (s.year == p)).to_numpy(float) for p in use]),
                 [s.cid.to_numpy(), tk])
    r = E.ols(R[:, 0], R[:, 1:], s.uid.to_numpy())
    ev = None
    if r is not None:
        b, se, _, _ = r
        ev = pd.concat([pd.DataFrame({"period": use, "b": b, "se": se}),
                        pd.DataFrame({"period": [ref], "b": [0.0], "se": [0.0]})]).sort_values("period")
    did = None
    if (s.year < 2005).any() and (s.year >= 2005).any():
        R2 = E.absorb(np.column_stack([s.yv.to_numpy(float), (s.treat * (s.year >= 2005)).to_numpy()]),
                      [s.cid.to_numpy(), tk])
        r2 = E.ols(R2[:, 0], R2[:, 1:], s.uid.to_numpy())
        if r2 is not None:
            b2, se2, _, ng = r2
            did = dict(b=float(b2[0]), se=float(se2[0]),
                       p=float(2 * (1 - stats.norm.cdf(abs(b2[0] / se2[0])))) if se2[0] > 0 else np.nan,
                       n=len(s), clusters=ng,
                       treated_cells=int(s[s.treat == 1].cid.nunique()),
                       control_cells=int(s[s.treat == 0].cid.nunique()),
                       id_districts=int(s.groupby("district").treat.nunique().gt(1).sum()))
    return ev, did


def main():
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
    print(f"{len(cel)} cells -> {len(L)} with >= {MIN_KM2} km2 of settled land")

    LUT = GR.intercal_lut()
    print(f"  intercalibration onto F15: {sorted(LUT) if LUT else 'NONE (raw DN)'}")
    panel = zonal(L, LUT).merge(L[["cid", "uid", "district", "d_gate", "d_park", "land_km2"]], on="cid", how="left")
    panel = panel[~panel.uid.isin(X["Kigali all + cities"])]
    panel.to_csv(ANALYSIS / "nightlights_cell_settled_panel.csv", index=False)

    PAN = [("gate", "d_gate", "distance to the nearest park GATE"),
           ("park", "d_park", "distance to the nearest PARK")]
    EV, rows = {}, []
    for what, dcol, _ in PAN:
        for sensor in ["dmsp", "viirs"]:
            ev, did = one(panel, dcol, sensor, REF if sensor == "dmsp" else JOIN)
            if ev is not None:
                EV[(what, sensor)] = ev
                rows += [dict(what=what, sensor=sensor, kind="event", year=int(r.period), b=r.b, se=r.se)
                         for r in ev.itertuples()]
            if did:
                rows.append(dict(what=what, sensor=sensor, kind="did", year=np.nan, **did))
        # randomisation inference: the clustered p-values here rest on 33 treated cells in 5
        # districts, and that is where they fail. Three coefficients get a permutation p:
        #   the post-2005 DiD, the joint pre-trend, and the VIIRS-era growth rate.
        for sensor, mode, t0, lab in (("dmsp", "post", 2005, "DiD post-2005"),
                                      ("viirs", "trend", 2012, "growth 2012-2025"),
                                      ("viirs", "trend", 2017, "growth 2017-2025")):
            s = panel[(panel.sensor == sensor) & panel.year.between(*SPAN[sensor])
                      & panel.asinh_sum.notna()].copy()
            s = s[s.year >= t0] if mode == "trend" else s
            if s.empty:
                continue
            s["treat"] = (s[dcol] <= KM).astype(float)
            sd = s[(s.year == max(BASE[sensor], t0)) & (s.treat == 0)].asinh_sum.std(ddof=1)
            s["yv"] = s.asinh_sum / sd if np.isfinite(sd) and sd > 0 else s.asinh_sum
            w = (s.year - t0).to_numpy(float) if mode == "trend" else (s.year >= t0).to_numpy(float)
            b, se, pri, nd, sdd = randomise(s, w)
            rows.append(dict(what=what, sensor=sensor, kind="ri_" + mode, year=t0, b=b, se=se,
                             p=float(2 * (1 - stats.norm.cdf(abs(b / se)))) if se else np.nan,
                             p_ri=pri, n_perm=nd))
            print(f"  {what:4s} {lab:17s} b={b:+.4f} se={se:.4f} "
                  f"clustered p={2 * (1 - stats.norm.cdf(abs(b / se))):.4f}  randomisation p={pri:.3f}")
    pd.DataFrame(rows).to_csv(ANALYSIS / "reg_nightlights_gates.csv", index=False)

    fig, axes = plt.subplots(1, 2, figsize=(15.5, 5.6), sharey=True)
    for ax, (what, _, title) in zip(axes, PAN):
        ax.axvspan(2004.5, 2025.5, color="#EDE6D6", alpha=.7, lw=0, zorder=0)
        ax.axvline(JOIN, color="#8C8C8C", lw=1.0, ls="--")
        ax.axhline(0, color="#333", lw=1.0)
        D = EV[(what, "dmsp")].sort_values("period")
        V = EV[(what, "viirs")].sort_values("period").copy()
        off = float(D.loc[D.period == JOIN, "b"].iloc[0]); ose = float(D.loc[D.period == JOIN, "se"].iloc[0])
        V["b"] = V.b + off; V["se"] = np.sqrt(V.se ** 2 + ose ** 2)
        both = pd.concat([D, V[V.period > JOIN]])
        ax.errorbar(both.period, both.b, yerr=1.96 * both.se, fmt="o", ms=4.2, color="#B4501E",
                    ecolor="#B4501E", elinewidth=1.05, capsize=1.9, zorder=3)
        ax.plot(both.period, both.b, color="#B4501E", lw=1.05, alpha=.45, zorder=2)
        d = [r for r in rows if r["what"] == what and r["kind"] == "did"]
        rd = [r for r in rows if r["what"] == what and r["kind"] == "ri_post"]
        rt = [r for r in rows if r["what"] == what and r["kind"] == "ri_trend" and r["year"] == 2012]
        note = ""
        if d:
            note += f"DiD 1992-2013  {d[0]['b']:+.3f}  (clustered p = {d[0]['p']:.3f}"
            note += f", randomisation p = {rd[0]['p_ri']:.3f})" if rd else ")"
        if rt:
            note += f"\nVIIRS growth/yr  {rt[0]['b']:+.3f}  (randomisation p = {rt[0]['p_ri']:.3f})"
        # fig.text, not ax.text: make_tex_figures.py silences Figure.text, so the numbers stay on the
        # working copy and are left out of the paper's, where they belong in the note beneath it
        fig.text(.015, .015, note, transform=ax.transAxes, fontsize=8.0, va="bottom",
                 bbox=dict(fc="white", ec="#CCC", lw=.6, pad=4))
        ax.set_title(title + "  —  within 5 km against all cells beyond", fontsize=10.5, pad=8)
        ax.set_xticks(np.arange(1992, 2026, 2))
        ax.set_xticklabels(np.arange(1992, 2026, 2), rotation=55, fontsize=7.6)
        ax.set_xlim(1991, 2026); ax.grid(axis="y", lw=.35, color="#DDD"); ax.set_axisbelow(True)
        y0, y1 = ax.get_ylim()
        ax.text(1992.4, y1 - .04 * (y1 - y0), "DMSP", fontsize=8.4, color="#777", va="top")
        ax.text(2012.4, y1 - .04 * (y1 - y0), "VIIRS", fontsize=8.4, color="#777", va="top")
    axes[0].set_ylabel("asinh(sum of lights), SD units, relative to 2004", fontsize=9.5)
    fig.suptitle("Nighttime lights within 5 km of a park gate, and within 5 km of the park itself",
                 fontsize=13.5, y=1.0)
    fig.text(.5, -.045, textwrap.fill(
        "Cell-level event studies. Each panel compares cells within 5 km to ALL cells beyond 5 km, with cell fixed effects and district x year fixed effects, so the "
        "comparison is between cells in the same district in the same year. Park area is removed from every cell before the lights are counted: it is dark by construction "
        "and treated sectors lose 31.6% of their area to it against 0.2% for controls. Errors are clustered at sector, bars are 95% intervals and the reference year is 2004, "
        "the last before revenue sharing. Raw sensors only, no bridge product: DMSP-OLS uncensored 1992-2013, then VIIRS 2012-2025 shifted by the DMSP coefficient at 2012 "
        "(dashed line), its intervals carrying that offset's uncertainty. The City of Kigali and the four largest towns of 2002 are dropped. Identification rests on five "
        "districts, so the reported p-values are optimistic and want a wild cluster bootstrap.", width=200),
        fontsize=7.0, ha="center", va="top", color="#333")
    fig.tight_layout()
    for ext in ("pdf",):                       # PDF only: the PNG twin was pure duplication
        fig.savefig(f"{OUT}/event_ntl_gates.{ext}", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"written {OUT}/event_ntl_gates.pdf")
    for r in rows:
        if r["kind"] == "did":
            print(f"  <= 5 km of {r['what']:5s}  b={r['b']:+.4f}  se={r['se']:.4f}  p={r['p']:.4f}  "
                  f"treated {r['treated_cells']}  control {r['control_cells']}  id districts {r['id_districts']}")


if __name__ == "__main__":
    main()
