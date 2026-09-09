"""
event_ntl_groups.py -- nighttime lights, separating the tourism channel from revenue sharing alone.

    python event_ntl_groups.py
    output/figures/event_ntl_groups.pdf / .png       the figure
    Analysis/nightlights_settled_panel_sector.csv    sector panel, settled land
    Analysis/nightlights_settled_panel_cell.csv      cell panel, settled land
    Analysis/reg_nightlights_groups.csv              event-study and DiD coefficients

THE THREE GROUPS. Sectors bordering a long-standing national park receive tourism revenue sharing.
Only a few of them also sit at an entrance, where tourists actually arrive and spend. Splitting them
separates the two channels:

    G1  Gates+, 12 sectors ....... revenue sharing AND tourism
    G2  the other 32 of the 44 ... revenue sharing ONLY
    G0  328 sectors .............. neither, the comparison group

    Excluded: the City of Kigali and the four largest towns of 2002 (44 sectors), and the 9 sectors
    bordering Gishwati-Mukura. That park was gazetted in 2015-16, so those sectors enter the
    revenue-sharing zone a decade after the others; leaving them among the controls would put nine
    treated units in the comparison group exactly in the years where the estimates move. Control is
    therefore 319 sectors, and 12 + 32 + 319 + 9 + 44 = 416.

THE REGRESSION. One equation, both groups at once, so they share a comparison group:

    Y(u,t) = a_u + d_{district(u),t} + SUM_t b1_t [G1(u) x 1(year=t)]
                                    + SUM_t b2_t [G2(u) x 1(year=t)] + e

    b1_t is tourism plus revenue sharing, b2_t is revenue sharing alone, and b1_t - b2_t is what
    tourism adds. The difference is estimated directly, with its own standard error, by re-running
    the same equation on [G1 or G2] and [G1]: the coefficient on the second is then b1 - b2.

    Unit fixed effects a_u absorb everything fixed about a place. District-by-year fixed effects
    d_{district,t} absorb every district-level shock, so the comparison is between sectors in the
    same district in the same year. Reference year 2004, the last before revenue sharing began.
    Errors clustered at sector.

RESTRICTIONS, each settled by a test rather than assumed.

park area removed from every unit before the lights are counted. Park land is dark by construction
    and it is not evenly spread: treated sectors lose 31.6% of their area to park against 0.2% for
    controls, so leaving it in attenuates the treated units specifically. Removing it also fixed the
    pre-trends -- three specifications that failed at p <= .005 pass once the park is out.

raw sensors only, no bridge product. DMSP-OLS ended in 2013 and VIIRS begins in 2012, so the two are
    estimated separately and VIIRS is shifted by the DMSP coefficient at 2012, its intervals carrying
    that offset's variance. The splice is licensed by the 2012-13 overlap, where both sensors observe
    the same units and the treated-control gap between them is -0.018 (p=0.89). The Li and Chen
    harmonised products are not used: each is half model output and their large post-2013 effects
    live entirely in the modelled half.

uncensored avg_vis rather than stable_lights, which zeroes dim cells, and the treated units are the
    dark ones. Neither layer is reliable in the DMSP era: across the twelve years when two satellites
    flew at once they disagree about the treated-control gap by more than that gap varies across
    years (test-retest correlation 0.10 to 0.45), so the DMSP half cannot support a small effect.

sector is the headline unit because treatment is assigned at sector level; the cell panel is shown
    beside it to confirm the weighting does not drive the result, not as extra identification.

KNOWN LIMITS. G1 is identified off 5 districts and G2 off 12, while the clustering assumes 372
sectors, so the p-values are optimistic and want a wild cluster bootstrap. The large movement is 2019
onward, fourteen years after revenue sharing began.
"""
import sys, re, collections, textwrap
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
SS = H.SUPERSAMPLE
SPAN = {"dmsp": (1992, 2013), "viirs": (2012, 2025)}
BASE = {"dmsp": 2002, "viirs": 2012}
REF, JOIN, MIN_KM2 = 2004, 2012, 0.5


def settled(gdf, parks):
    """unit geometry minus the parks; tiny remnants dropped"""
    g = gdf.to_crs(4326).copy()
    g["land"] = g.geometry.difference(parks)
    km2 = gpd.GeoSeries(g.land, crs=4326).to_crs(32736).area / 1e6
    keep = (~g.land.is_empty) & (km2 >= MIN_KM2)
    g = g[keep].copy(); g["land_km2"] = km2[keep].to_numpy()
    return g.set_geometry("land")


def zonal(gdf, idcol):
    """asinh(sum of lights) per unit per year, satellites averaged, on settled land"""
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
                v = np.repeat(np.repeat(a, SS, axis=0), SS, axis=1).ravel()[keep]
                tot.append(np.bincount(fk, weights=v, minlength=k + 1)[1:] / (SS * SS))
            rows.append(pd.DataFrame({idcol: gdf[idcol].to_numpy(), "year": y, "sensor": sensor,
                                      "asinh_sum": np.arcsinh(np.mean(tot, axis=0))}))
    return pd.concat(rows, ignore_index=True)


def fit(panel, unitcol, terms, sensor, ref):
    """event study and post-2005 DiD on the listed 0/1 group columns, jointly"""
    s = panel[(panel.sensor == sensor) & panel.year.between(*SPAN[sensor])
              & panel.asinh_sum.notna()].copy()
    ctrl = np.logical_and.reduce([s[t] == 0 for t in terms])
    sd = s[(s.year == BASE[sensor]) & ctrl].asinh_sum.std(ddof=1)
    s["yv"] = s.asinh_sum / sd if np.isfinite(sd) and sd > 0 else s.asinh_sum
    tk = (s.district.astype(str) + "_" + s.year.astype(str)).to_numpy()
    per = sorted(s.year.unique()); use = [p for p in per if p != ref]
    cols = [(t, p) for t in terms for p in use]
    R = E.absorb(np.column_stack([s.yv.to_numpy(float)] +
                                 [(s[t] * (s.year == p)).to_numpy(float) for t, p in cols]),
                 [s[unitcol].to_numpy(), tk])
    r = E.ols(R[:, 0], R[:, 1:], s.uid.to_numpy())
    ev = None
    if r is not None:
        b, se, _, _ = r
        ev = pd.concat([
            pd.DataFrame({"term": [t for t, _ in cols], "period": [p for _, p in cols], "b": b, "se": se}),
            pd.DataFrame({"term": terms, "period": ref, "b": 0.0, "se": 0.0})]).sort_values(["term", "period"])
    did = None
    if (s.year < 2005).any() and (s.year >= 2005).any():
        R2 = E.absorb(np.column_stack([s.yv.to_numpy(float)] +
                                      [(s[t] * (s.year >= 2005)).to_numpy(float) for t in terms]),
                      [s[unitcol].to_numpy(), tk])
        r2 = E.ols(R2[:, 0], R2[:, 1:], s.uid.to_numpy())
        if r2 is not None:
            b2, se2, _, ng = r2
            did = pd.DataFrame({"term": terms, "b": b2, "se": se2,
                                "p": 2 * (1 - stats.norm.cdf(np.abs(b2 / np.maximum(se2, 1e-12)))),
                                "n": len(s), "clusters": ng})
    return ev, did


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
    DROP = X["Kigali all + cities"] | GISH
    G0 = set(g.sid) - G1 - G2 - DROP
    print(f"G1 {len(G1)}  G2 {len(G2)}  G0 {len(G0)}  Gishwati dropped {len(GISH)}  "
          f"Kigali+towns {len(X['Kigali all + cities'])}  total {len(G1)+len(G2)+len(G0)+len(DROP)}")

    sec = gpd.read_file(H.SECTORS); sec["uid"] = sec.sector_id.astype(int); sec["idc"] = sec.uid
    cel = gpd.read_file(H.CELLS); cel["cid"] = cel.cell_id.astype(int)
    cel["uid"] = cel.sector_id.astype(int); cel["idc"] = cel.cid
    panels = {}
    for name, gdf, idcol in (("sector", sec, "uid"), ("cell", cel, "cid")):
        L = settled(gdf, allpark)
        keep = list(dict.fromkeys([idcol, "uid", "district", "land_km2"]))   # idcol IS uid for sectors
        p = zonal(L, idcol).merge(L[keep].drop_duplicates(idcol), on=idcol, how="left")
        p = p[p.uid.isin(G1 | G2 | G0)].copy()
        p["G1"] = p.uid.isin(G1).astype(float); p["G2"] = p.uid.isin(G2).astype(float)
        p["ANY"] = ((p.G1 + p.G2) > 0).astype(float)
        p.to_csv(ANALYSIS / f"nightlights_settled_panel_{name}.csv", index=False)
        panels[name] = (p, idcol)
        print(f"  {name}: {p[idcol].nunique()} units, {len(p)} rows")

    rows, EV = [], {}
    for name, (p, idcol) in panels.items():
        for sensor in ("dmsp", "viirs"):
            ref = REF if sensor == "dmsp" else JOIN
            ev, did = fit(p, idcol, ["G1", "G2"], sensor, ref)
            if ev is not None:
                EV[(name, sensor)] = ev
                rows += [dict(unit=name, sensor=sensor, kind="event", term=r.term,
                              year=int(r.period), b=r.b, se=r.se) for r in ev.itertuples()]
            if did is not None:
                rows += [dict(unit=name, sensor=sensor, kind="did", term=r.term, year=np.nan,
                              b=r.b, se=r.se, p=r.p, n=r.n, clusters=r.clusters) for r in did.itertuples()]
            # reparametrised: coefficient on G1 is now b1 - b2, the tourism increment
            _, dinc = fit(p, idcol, ["ANY", "G1"], sensor, ref)
            if dinc is not None:
                r = dinc[dinc.term == "G1"].iloc[0]
                rows.append(dict(unit=name, sensor=sensor, kind="did_increment", term="G1 minus G2",
                                 year=np.nan, b=r.b, se=r.se, p=r.p, n=r.n, clusters=r.clusters))
    res = pd.DataFrame(rows); res.to_csv(ANALYSIS / "reg_nightlights_groups.csv", index=False)

    LBL = {"G1": ("Gates+ (12): revenue sharing and tourism", "#B4501E", "o"),
           "G2": ("The other 32: revenue sharing only", "#3E6E8E", "s")}
    fig, axes = plt.subplots(1, 2, figsize=(15.5, 5.8), sharey=True)
    for ax, (name, title) in zip(axes, (("sector", "Sector level (headline)"),
                                        ("cell", "Cell level (robustness)"))):
        ax.axvspan(2004.5, 2025.5, color="#EDE6D6", alpha=.7, lw=0, zorder=0)
        ax.axvline(JOIN, color="#8C8C8C", lw=1.0, ls="--"); ax.axhline(0, color="#333", lw=1.0)
        notes = []
        for term, (lab, col, mk) in LBL.items():
            D = EV[(name, "dmsp")]; D = D[D.term == term].sort_values("period")
            V = EV[(name, "viirs")]; V = V[V.term == term].sort_values("period").copy()
            off = float(D.loc[D.period == JOIN, "b"].iloc[0]); ose = float(D.loc[D.period == JOIN, "se"].iloc[0])
            V["b"] = V.b + off; V["se"] = np.sqrt(V.se ** 2 + ose ** 2)
            both = pd.concat([D, V[V.period > JOIN]])
            ax.errorbar(both.period, both.b, yerr=1.96 * both.se, fmt=mk, ms=4.0, color=col,
                        ecolor=col, elinewidth=1.05, capsize=1.9, zorder=3, label=lab)
            ax.plot(both.period, both.b, color=col, lw=1.05, alpha=.45, zorder=2)
            pre = D[(D.period < 2005) & (D.period != REF)]
            z = (pre.b / pre.se.replace(0, np.nan)).dropna()
            pj = 1 - stats.chi2.cdf(float((z ** 2).sum()), len(z))
            d = res[(res.unit == name) & (res.kind == "did") & (res.term == term) & (res.sensor == "dmsp")]
            notes.append(f"{term}  placebo p={pj:.2f}" +
                         (f"   DiD {d.iloc[0].b:+.3f} (p={d.iloc[0].p:.2f})" if len(d) else ""))
        di = res[(res.unit == name) & (res.kind == "did_increment") & (res.sensor == "dmsp")]
        if len(di):
            notes.append(f"G1 - G2  {di.iloc[0].b:+.3f} (p={di.iloc[0].p:.2f})")
        ax.text(.015, .015, "\n".join(notes), transform=ax.transAxes, fontsize=7.6, va="bottom",
                bbox=dict(fc="white", ec="#CCC", lw=.6, pad=4))
        ax.set_title(title, fontsize=11, pad=8)
        ax.set_xticks(np.arange(1992, 2026, 2))
        ax.set_xticklabels(np.arange(1992, 2026, 2), rotation=55, fontsize=7.6)
        ax.set_xlim(1991, 2026); ax.grid(axis="y", lw=.35, color="#DDD"); ax.set_axisbelow(True)
        y0, y1 = ax.get_ylim()
        ax.text(1992.4, y1 - .04 * (y1 - y0), "DMSP", fontsize=8.4, color="#777", va="top")
        ax.text(2012.4, y1 - .04 * (y1 - y0), "VIIRS", fontsize=8.4, color="#777", va="top")
    axes[0].set_ylabel("asinh(sum of lights), SD units, relative to 2004", fontsize=9.5)
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, fontsize=9.0, loc="upper center", ncol=2, frameon=False, bbox_to_anchor=(.5, 1.045))
    fig.tight_layout()
    for ext in ("pdf", "png"):
        fig.savefig(f"{OUT}/event_ntl_groups.{ext}", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"written {OUT}/event_ntl_groups.pdf/.png")
    show = res[res.kind.isin(["did", "did_increment"]) & (res.sensor == "dmsp")]
    for r in show.itertuples():
        print(f"  {r.unit:6s} {r.term:12s} b={r.b:+.4f} se={r.se:.4f} p={r.p:.4f} clusters={int(r.clusters)}")


if __name__ == "__main__":
    main()
