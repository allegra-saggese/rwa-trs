"""
prelim_public_figures.py — every preliminary descriptive figure and map.

ALL outputs here are built from PUBLIC data only: NISR public-use microdata,
Dynamic World, Hansen GFC, JRC TMF, RADD, WRI SDPT, CHIRPS, WDPA/geodata.rw,
GRID3, Google Open Buildings, gridfinder, OpenStreetMap. Nothing here uses
restricted RDB programme data, and nothing here is a causal estimate — these
are descriptives for memos and grant applications.

Usage
-----
    python prelim_public_figures.py --all
    python prelim_public_figures.py --list
    python prelim_public_figures.py --only tourism_employment distance_decay
    python prelim_public_figures.py --group forest

Groups: forest, landcover, labour, infrastructure, spatial, cell

Outputs land in output/figures/ and output/maps/ (both gitignored — they are
reproducible from this script). Inputs are read from the Dropbox geo-data and
NISR folders; see viz_style.py for those paths.
"""

from __future__ import annotations

import argparse
import ast
import sys
import warnings
from pathlib import Path

import geopandas as gpd
import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import viz_style as V

warnings.filterwarnings("ignore")
V.apply_style()

ORDER = ["trees", "shrub_scrub", "crops", "grass", "built", "bare", "water", "flooded_veg"]
SHORT = {"trees": "trees", "shrub_scrub": "shrub", "crops": "crops", "grass": "grass",
         "built": "built", "bare": "bare", "water": "water", "flooded_veg": "flood.veg"}
FLOWCOL = {"trees": "#2a9d8f", "shrub_scrub": "#a3b18a", "crops": "#e9c46a",
           "grass": "#cbd5c0", "built": "#8b5fbf", "bare": "#d4a373",
           "water": "#457b9d", "flooded_veg": "#6a994e"}


def _boot(x, n=800):
    """Bootstrap CI for a mean. Small n in some distance bands, so report it."""
    x = np.asarray(x, float)
    if len(x) < 3:
        return np.nan, np.nan
    d = [np.mean(x[np.random.randint(0, len(x), len(x))]) for _ in range(n)]
    return np.percentile(d, 2.5), np.percentile(d, 97.5)


def _parkiness():
    """Share of a district's sectors that border a park (0-1)."""
    ex = V.csv("protected-areas/sectors_park_exposure_geodatarw.csv")
    return (ex.groupby("district_id")
              .agg(parkiness=("border", "mean"), dname=("district", "first"))
              .reset_index().rename(columns={"district_id": "dist"}))


# ==========================================================================
# FOREST
# ==========================================================================

def fig_hazard_vs_tmf():
    """Hansen loss hazard against TMF stocks — the plantation signature.

    Hansen counts plantation harvest as loss; TMF's humid-forest mask largely
    excludes plantations. Plotting them together is the clearest evidence that
    the post-2013 surge is rotation rather than deforestation.
    """
    p = V.csv("forest/sector_year_panel.csv")
    t = V.csv("forest/tmf_by_sector.csv")
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.4))
    n = p.groupby("year").agg(loss=("loss_ha", "sum"), rem=("forest_start_ha", "sum"))
    n["hz"] = 100 * n.loss / n.rem
    ax[0].bar(n.index, n.hz, color=V.PARK, width=.7)
    ax[0].axvline(2012.5, color="0.4", ls="--", lw=1)
    ax[0].set_title("Hansen: annual loss hazard\n(loss ÷ forest remaining)")
    ax[0].set_ylabel("% per year"); ax[0].set_xlabel("year")

    tn = t.groupby("year")[["tmf_undisturbed_forest_ha", "tmf_degraded_forest_ha",
                            "tmf_regrowth_ha"]].sum()
    ax[1].plot(tn.index, tn.tmf_undisturbed_forest_ha, color=V.NONPARK, lw=2, label="undisturbed")
    ax[1].plot(tn.index, tn.tmf_degraded_forest_ha, color="#e76f51", lw=2, label="degraded")
    ax[1].plot(tn.index, tn.tmf_regrowth_ha, color="#2a9d8f", lw=2, label="regrowth")
    ax[1].set_title("TMF: humid-forest stocks"); ax[1].set_ylabel("ha")
    ax[1].set_xlabel("year"); ax[1].legend(fontsize=8)

    tn["forest"] = tn.tmf_undisturbed_forest_ha + tn.tmf_degraded_forest_ha
    cum = n.loss.cumsum()
    ax[2].plot(n.index, 100 * cum / cum.iloc[-1], color=V.PARK, lw=2, label="Hansen cumulative loss")
    den = tn.forest.iloc[0] - tn.forest.iloc[-1]
    ax[2].plot(tn.index, 100 * (tn.forest.iloc[0] - tn.forest) / den,
               color=V.NONPARK, lw=2, label="TMF cumulative net decline")
    ax[2].set_title("The two sources diverge"); ax[2].set_ylabel("% of total")
    ax[2].set_xlabel("year"); ax[2].legend(fontsize=8)
    for a in ax:
        V.year_axis(a)
    fig.suptitle("Hansen loss accelerates while TMF natural forest stabilises",
                 fontsize=12, y=1.03)
    V.save(fig, "hazard_vs_tmf")


def fig_distance_decay():
    """Cell-level loss by distance band, with bootstrap CIs.

    Cells with almost no 2000 tree cover give unstable rates, so the sample is
    restricted to >20 ha. The relationship is U-shaped, not monotone decay.
    """
    c = V.csv("forest/hansen_by_cell.csv", "cell_id")
    c["loss_rate"] = 100 * c.loss_total_ha / c.treecover2000_ha.replace(0, np.nan)
    c = c[c.treecover2000_ha > 20]
    labs = ["in park", "0-1", "1-2", "2-3", "3-5", "5-7.5", "7.5-10", "10-15", "15-20", ">20"]
    c["band"] = pd.cut(c.dist_to_park_km, [-.01, .001, 1, 2, 3, 5, 7.5, 10, 15, 20, 1e9], labels=labs)
    rows = []
    for b, x in c.groupby("band"):
        v = x.loss_rate.dropna().values
        if len(v) < 5:
            continue
        lo, hi = _boot(v)
        rows.append(dict(band=b, mean=v.mean(), lo=lo, hi=hi, n=len(v)))
    dd = pd.DataFrame(rows)
    fig, ax = plt.subplots(1, 2, figsize=(12.5, 4.6))
    x = np.arange(len(dd))
    ax[0].errorbar(x, dd["mean"], yerr=[dd["mean"] - dd.lo, dd.hi - dd["mean"]],
                   fmt="o-", color=V.PARK, capsize=3, lw=1.8, ms=6)
    ax[0].set_xticks(x); ax[0].set_xticklabels(dd.band, rotation=45, ha="right", fontsize=8)
    ax[0].set_ylabel("forest loss 2006–2024, % of 2000 cover")
    ax[0].set_xlabel("distance to nearest national park (km)")
    ax[0].set_title("Forest-loss gradient by distance\n(cell level, 95% bootstrap CI)")
    ax[1].bar(x, dd.n, color=V.NONPARK, width=.7)
    ax[1].set_xticks(x); ax[1].set_xticklabels(dd.band, rotation=45, ha="right", fontsize=8)
    ax[1].set_ylabel("cells"); ax[1].set_xlabel("distance band (km)"); ax[1].set_title("Cells per band")
    V.save(fig, "distance_decay")


def fig_firewood_trend():
    """Firewood foraging time, and its relationship to grid density.

    EICV4 and EICV7 use the same question; EICV5's wording is broader
    ("gather, collect or purchase"), so its level is not directly comparable.
    """
    fw = V.csv("forest/eicv_firewood_by_district.csv")
    fw["dist"] = fw.district.astype(int)          # numeric NISR code, not a name
    ele = V.csv("electricity/gridfinder_by_sector.csv", "sector_id")
    ex = V.csv("protected-areas/sectors_park_exposure_geodatarw.csv", "sector_id")
    ele = ele.merge(ex[["sector_id", "district_id", "unit_km2"]], on="sector_id", how="left")
    gd = (ele.groupby("district_id")
            .apply(lambda x: pd.Series({"grid_km_per_km2": x.grid_km.sum() / x.unit_km2.sum()}))
            .reset_index().rename(columns={"district_id": "dist"}))
    m = fw.merge(gd, on="dist", how="left")
    fig, ax = plt.subplots(1, 2, figsize=(12.5, 4.6))
    for yr, c in [(2014, V.PARK), (2017, "#e76f51"), (2024, V.NONPARK)]:
        s = m[m.year == yr]
        ax[0].scatter(s.grid_km_per_km2, s.mean_hours, s=34, color=c, alpha=.8,
                      label=str(yr), edgecolor="white", linewidth=.5)
    r = m.dropna(subset=["grid_km_per_km2", "mean_hours"])
    ax[0].set_xlabel("district grid density (km per km²)")
    ax[0].set_ylabel("mean hours/week foraging")
    ax[0].set_title(f"Firewood time vs grid density\npooled r = "
                    f"{r.grid_km_per_km2.corr(r.mean_hours):.3f}")
    ax[0].legend(fontsize=8, title="EICV wave")
    for _, g in m.sort_values("year").groupby("dist"):
        ax[1].plot(g.year, g.mean_hours, color="0.7", lw=1, alpha=.7)
    mn = m.groupby("year").apply(lambda x: np.average(x.mean_hours, weights=x.n))
    ax[1].plot(mn.index, mn.values, color=V.PARK, lw=3, marker="o", ms=7, label="national (weighted)")
    ax[1].set_xticks([2014, 2017, 2024]); V.year_axis(ax[1])
    ax[1].set_xlabel("EICV wave"); ax[1].set_ylabel("mean hours/week foraging")
    ax[1].set_title("Firewood foraging time by district"); ax[1].legend(fontsize=8)
    V.save(fig, "firewood_trend")


# ==========================================================================
# LAND COVER
# ==========================================================================

def fig_transition_matrices_yoy():
    """Year-on-year land-cover transition matrices, national.

    Built from Dynamic World's discrete `label` band in Earth Engine (see
    gee_extract.py): sector-level class fractions give composition, not flows.
    The diagonal (no change) dominates and is hidden so the flows are visible.
    """
    nat = V.csv("land-cover/dw_transitions_national.csv")
    prs = sorted(nat.y0.unique())
    fig, axes = plt.subplots(2, 4, figsize=(19, 9))
    vmax = nat[nat.frm != nat.to].pct.quantile(.995)
    im = None
    for a, y in zip(axes.flat, prs):
        M = (nat[nat.y0 == y].pivot_table(index="frm", columns="to", values="pct", aggfunc="sum")
             .reindex(index=ORDER, columns=ORDER).fillna(0))
        A = M.values.astype(float).copy()
        np.fill_diagonal(A, np.nan)
        im = a.imshow(A, cmap="RdPu", vmin=0, vmax=vmax)
        a.set_xticks(range(len(ORDER))); a.set_xticklabels([SHORT[c] for c in ORDER],
                                                          rotation=45, ha="right", fontsize=7)
        a.set_yticks(range(len(ORDER))); a.set_yticklabels([SHORT[c] for c in ORDER], fontsize=7)
        for i in range(len(ORDER)):
            for j in range(len(ORDER)):
                v = A[i, j]
                if not np.isnan(v) and v >= .25:
                    a.text(j, i, f"{v:.1f}", ha="center", va="center", fontsize=6,
                           color="white" if v > vmax * .6 else "0.2")
        a.set_title(f"{y}–{y + 1}", fontsize=10); a.grid(False)
    cb = fig.colorbar(im, ax=axes, fraction=.014, pad=.015)
    cb.set_label("% of national land area", fontsize=9)
    fig.suptitle("Year-on-year land-cover transitions (diagonal = no change, hidden)",
                 fontsize=13, y=.99)
    V.save(fig, "transition_matrices_yoy")


def fig_transition_flows():
    """Gross gains and losses per class per year.

    Gross flows are far larger than net change — the landscape churns. Net
    composition alone hides that.
    """
    nat = V.csv("land-cover/dw_transitions_national.csv")
    off = nat[nat.frm != nat.to]
    gain = off.groupby(["y0", "to"]).pct.sum().rename("gain").reset_index().rename(columns={"to": "cls"})
    loss = off.groupby(["y0", "frm"]).pct.sum().rename("loss").reset_index().rename(columns={"frm": "cls"})
    fl = gain.merge(loss, on=["y0", "cls"], how="outer").fillna(0)
    fl["net"] = fl.gain - fl.loss
    fig, ax = plt.subplots(1, 3, figsize=(17, 4.8))
    for c in ORDER:
        s = fl[fl.cls == c].sort_values("y0")
        ax[0].plot(s.y0, s.net, marker="o", lw=2, color=FLOWCOL[c], label=SHORT[c])
        ax[1].plot(s.y0, s.gain, marker="o", lw=1.8, color=FLOWCOL[c])
        ax[2].plot(s.y0, s.loss, marker="o", lw=1.8, color=FLOWCOL[c])
    ax[0].axhline(0, color="0.4", lw=1)
    for a, t in zip(ax, ["Net change", "Gross gains (land entering)", "Gross losses (land leaving)"]):
        a.set_title(t); a.set_ylabel("% of land / yr"); a.set_xlabel("year"); V.year_axis(a)
    ax[0].legend(fontsize=7.5, ncol=4)
    fig.suptitle("Land-cover flows by class and year (gross, not net)", fontsize=12, y=1.02)
    V.save(fig, "transition_flows")


def fig_transition_flows_district():
    """Major flows by district — a compact alternative to 30 small matrices."""
    d = V.csv("land-cover/dw_transitions_district.csv")
    pk = _parkiness().set_index("dist").parkiness
    d["parkiness"] = d.dist.map(pk)
    flows = ["shrub_scrub>trees", "shrub_scrub>crops", "shrub_scrub>built",
             "trees>shrub_scrub", "trees>crops", "crops>trees", "crops>built", "grass>trees"]
    d["flow"] = d.frm + ">" + d.to
    piv = (d[d.flow.isin(flows)]
           .pivot_table(index="dname", columns="flow", values="pct", aggfunc="sum")
           .fillna(0).reindex(columns=flows))
    order = d.groupby("dname").parkiness.first().sort_values(ascending=False)
    piv = piv.loc[[n for n in order.index if n in piv.index]]
    fig, ax = plt.subplots(figsize=(11, 9))
    im = ax.imshow(piv.values, cmap="RdPu", aspect="auto", vmin=0,
                   vmax=np.percentile(piv.values, 97))
    ax.set_xticks(range(len(flows)))
    ax.set_xticklabels([f.replace("_", " ").replace(">", " → ") for f in flows],
                       rotation=40, ha="right", fontsize=8)
    ax.set_yticks(range(len(piv)))
    ax.set_yticklabels([f"{n} *" if order.get(n, 0) > 0 else n for n in piv.index], fontsize=7.5)
    for i, n in enumerate(piv.index):
        if order.get(n, 0) > 0:
            ax.get_yticklabels()[i].set_color(V.PARK)
    for i in range(piv.shape[0]):
        for j in range(piv.shape[1]):
            v = piv.values[i, j]
            if v >= 1:
                ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=6,
                        color="white" if v > np.percentile(piv.values, 80) else "0.25")
    ax.grid(False)
    fig.colorbar(im, ax=ax, fraction=.03, pad=.02).set_label("% of district area", fontsize=9)
    ax.set_title("Major land-cover flows by district, 2016→2024\n(* = park-bordering)", fontsize=11)
    V.save(fig, "transition_flows_district")


def fig_landuse_stacked_district():
    """Land-cover composition by district, park-bordering ordered first."""
    dw = V.csv("land-cover/dw_by_sector.csv", "sector_id")
    ex = V.csv("protected-areas/sectors_park_exposure_geodatarw.csv", "sector_id")
    # dw already carries a `district` column from an earlier build; drop it so the
    # merge does not produce district_x / district_y.
    dw = dw.drop(columns=[c for c in ("district", "unit_km2", "border") if c in dw.columns])
    dw = dw.merge(ex[["sector_id", "district", "unit_km2", "border"]], on="sector_id", how="left")
    late = dw[dw.year == dw.year.max()].dropna(subset=["district"]).copy()
    for b in V.LANDCOVER:
        late[b] = late[b] * late.unit_km2
    g = late.groupby("district").agg({**{b: "sum" for b in V.LANDCOVER}, "border": "max"})
    frac = g[list(V.LANDCOVER)].div(g[list(V.LANDCOVER)].sum(axis=1), axis=0) * 100
    frac["border"] = g.border
    frac = frac.sort_values(["border", "dw_trees"], ascending=[False, False]).reset_index()
    fig, ax = plt.subplots(figsize=(14, 6.5))
    bottom = np.zeros(len(frac))
    for b, (lab, col) in V.LANDCOVER.items():
        ax.bar(range(len(frac)), frac[b], bottom=bottom, color=col, label=lab, width=.82)
        bottom += frac[b].values
    ax.set_xticks(range(len(frac)))
    ax.set_xticklabels([f"{r.district}{' *' if r.border == 1 else ''}" for r in frac.itertuples()],
                       rotation=60, ha="right", fontsize=8)
    ax.set_ylabel("% of district area"); ax.set_ylim(0, 100)
    ax.legend(fontsize=8, ncol=8, loc="upper center", bbox_to_anchor=(.5, 1.11))
    ax.set_title(f"Land cover by district, {int(dw.year.max())}   —   * = park-bordering", pad=30)
    ax.grid(axis="x", visible=False)
    V.save(fig, "landuse_stacked_district")


# ==========================================================================
# LABOUR
# ==========================================================================

def fig_tourism_employment():
    """Tourism concentration near parks: firms vs workers.

    EC counts registered establishments (which exclude farms); LFS counts all
    workers (including subsistence agriculture). The two disagree in sign, and
    the reason is the denominator, not a data error.
    """
    ec = V.csv("labour/ec_establishments_long.csv")
    lfs = V.csv("labour/lfs_tourism_share.csv")
    rec = []
    for (y, b), x in ec.dropna(subset=["border_dist", "isic"]).groupby(["year", "border_dist"]):
        lo, hi = _boot(x.tourism.values * 100)
        rec.append(dict(year=y, border=b, share=(x.tourism * x.wt).sum() / x.wt.sum() * 100,
                        lo=lo, hi=hi))
    r = pd.DataFrame(rec)
    fig, ax = plt.subplots(1, 3, figsize=(15.5, 4.8))
    for b, lab, c in [(1.0, "park-bordering district", V.PARK), (0.0, "other districts", V.NONPARK)]:
        s = r[r.border == b].sort_values("year")
        ax[0].plot(s.year, s.share, marker="o", color=c, lw=2, label=lab)
        ax[0].fill_between(s.year, s.lo, s.hi, color=c, alpha=.15)
        t = lfs[lfs.border_dist == b].sort_values("year")
        ax[1].plot(t.year, t.share, marker="o", color=c, lw=2, label=lab)
    ax[0].set_title("Establishment Census"); ax[0].set_ylabel("% of all establishments")
    ax[0].set_xlabel("census round"); ax[0].set_xticks(sorted(r.year.unique()))
    ax[0].legend(fontsize=8, loc="lower left")
    ax[1].set_title("Labour Force Survey"); ax[1].set_ylabel("% of workers with an industry code")
    ax[1].set_xlabel("year"); ax[1].legend(fontsize=8, loc="upper left")
    ge = r.pivot(index="year", columns="border", values="share"); ge["gap"] = ge[1.0] - ge[0.0]
    gl = lfs.pivot(index="year", columns="border_dist", values="share"); gl["gap"] = gl[1.0] - gl[0.0]
    ax[2].axhline(0, color="0.5", lw=1)
    ax[2].plot(ge.index, ge.gap, marker="s", color="#8b5fbf", lw=2, label="establishments (EC)")
    ax[2].plot(gl.index, gl.gap, marker="o", color="#2a9d8f", lw=2, label="workers (LFS)")
    ax[2].set_title("Park minus non-park gap"); ax[2].set_ylabel("percentage points")
    ax[2].set_xlabel("year"); ax[2].legend(fontsize=8)
    for a in ax:
        V.year_axis(a)
    fig.suptitle("Accommodation, food & recreation near parks: concentrated among firms, not workers",
                 fontsize=12, y=1.04)
    V.save(fig, "tourism_employment")


def fig_economy_composition():
    """Rwanda's economy by ISIC section, both sources."""
    ec = pd.read_csv(V.GEO / "labour/ec_isic_shares_wide.csv", index_col=0)
    lf = pd.read_csv(V.GEO / "labour/lfs_isic_shares_wide.csv", index_col=0)
    ec.index = [int(str(i).split()[0]) for i in ec.index]
    lf.index = [int(str(i).split()[0]) for i in lf.index]
    fig, ax = plt.subplots(1, 2, figsize=(15, 6.2))
    for a, (df, title, yr) in zip(ax, [(ec, "Establishment Census — share of establishments",
                                        str(max(int(c) for c in ec.columns))),
                                       (lf, "Labour Force Survey — share of workers",
                                        str(max(int(c) for c in lf.columns)))]):
        s = df[yr].sort_values(ascending=True)
        s = s[s > .05]
        cols = [V.PARK if i == 9 else ("#8b5fbf" if i == 18 else V.NONPARK) for i in s.index]
        a.barh([V.ISIC.get(i, "?")[:34] for i in s.index], s.values, color=cols)
        for y, (i, v) in enumerate(s.items()):
            a.text(v + max(s) * .012, y, f"{v:.1f}", va="center", fontsize=7.5,
                   color=V.PARK if i == 9 else "0.3")
        a.set_title(f"{title}, {yr}"); a.set_xlabel("%"); a.grid(axis="y", visible=False)
    fig.suptitle("Rwanda's economy by ISIC section — accommodation & food in red",
                 fontsize=11.5, y=1.01)
    V.save(fig, "economy_composition")


def fig_district_trajectories():
    """Every district as a thin line, group means thick."""
    dw = V.csv("labour/district_workers_forest_panel.csv")
    ec = V.csv("labour/ec_district_isic.csv")
    pk = _parkiness()
    dw = dw.merge(pk, on="dist", how="left"); ec = ec.merge(pk, on="dist", how="left")
    dw["grp"] = np.where(dw.parkiness > 0, "park-bordering", "other")
    ec["grp"] = np.where(ec.parkiness > 0, "park-bordering", "other")
    fig, ax = plt.subplots(1, 3, figsize=(16, 4.8))
    for grp, c in [("park-bordering", V.PARK), ("other", V.NONPARK)]:
        s = dw[dw.grp == grp]
        for v, a in [("lfs_isic9_pct", ax[0]), ("lfs_isic1_pct", ax[1])]:
            for _, g in s.groupby("dist"):
                a.plot(g.year, g[v], color=c, alpha=.22, lw=.9)
            mn = s.groupby("year")[v].mean()
            a.plot(mn.index, mn.values, color=c, lw=2.6, label=grp, zorder=5)
        e = ec[(ec.grp == grp) & (ec.isic == 9)]
        for _, g in e.groupby("dist"):
            ax[2].plot(g.year, g.share, color=c, alpha=.22, lw=.9)
        mn = e.groupby("year").share.mean()
        ax[2].plot(mn.index, mn.values, color=c, lw=2.6, label=grp, zorder=5)
    ax[0].set_title("LFS: accommodation & food workers"); ax[0].set_ylabel("% of workers")
    ax[1].set_title("LFS: agriculture workers"); ax[1].set_ylabel("% of workers")
    ax[2].set_title("EC: accommodation & food establishments"); ax[2].set_ylabel("% of establishments")
    for a in ax:
        a.set_xlabel("year"); a.legend(fontsize=8); V.year_axis(a)
    fig.suptitle("District trajectories (thin = districts, thick = group mean)", fontsize=12, y=1.02)
    V.save(fig, "district_trajectories")


def fig_agriculture_workers_forest():
    """District labour composition against forest loss.

    Agricultural districts sit near parks; tourism-worker districts sit far
    from them. Both correlations are spatial sorting, not effects.
    """
    dw = V.csv("labour/district_workers_forest_panel.csv")
    avg = dw.groupby("dist").mean(numeric_only=True).reset_index()
    avg["parkiness"] = avg.border_sectors / avg.n_sectors
    fig, ax = plt.subplots(2, 3, figsize=(16, 9))
    P = [("lfs_isic1_pct", "loss_rate", "agriculture workers, %", "loss, % of 2000 cover"),
         ("lfs_isic1_pct", "loss_per_km2", "agriculture workers, %", "loss, ha/km²"),
         ("lfs_isic1_pct", "meandist", "agriculture workers, %", "mean distance to park, km"),
         ("lfs_isic9_pct", "loss_rate", "accommodation & food, %", "loss, % of 2000 cover"),
         ("lfs_isic9_pct", "meandist", "accommodation & food, %", "mean distance to park, km"),
         ("lfs_isic1_pct", "lfs_isic9_pct", "agriculture workers, %", "accommodation & food, %")]
    sc = None
    for a, (x, y, xl, yl) in zip(ax.flat, P):
        v = avg[[x, y, "parkiness"]].dropna()
        sc = a.scatter(v[x], v[y], s=18 + 120 * v.parkiness, c=v.parkiness, cmap="Reds",
                       edgecolor="0.3", linewidth=.4, vmin=0, vmax=1)
        z = np.polyfit(v[x], v[y], 1); xs = np.linspace(v[x].min(), v[x].max(), 50)
        a.plot(xs, np.polyval(z, xs), color="0.35", ls="--", lw=1.2)
        a.set_xlabel(xl); a.set_ylabel(yl); a.set_title(f"r = {v[x].corr(v[y]):.3f}")
    cb = fig.colorbar(sc, ax=ax, fraction=.014, pad=.01)
    cb.set_label("share of district's sectors bordering a park", fontsize=8)
    fig.suptitle("District labour composition and forest loss (LFS means, 30 districts)",
                 fontsize=12, y=.98)
    V.save(fig, "agriculture_workers_forest")


# ==========================================================================
# INFRASTRUCTURE / MAPS
# ==========================================================================

def map_infrastructure_vs_forest():
    """Buildings, grid and tourism POIs against TMF forest cover."""
    sec, pk = V.sectors(), V.parks()
    bld = V.csv("buildings/gob_buildings_by_sector.csv", "sector_id")
    ele = V.csv("electricity/gridfinder_by_sector.csv", "sector_id")
    tmf = V.csv("forest/tmf_by_sector.csv", "sector_id")
    t = tmf[tmf.year == tmf.year.max()].set_index("sector_id")
    grid = gpd.read_file(V.GEO / "electricity/gridfinder_rwanda.gpkg").to_crs(32735)
    poi = gpd.read_file(V.GEO / "tourism/rwanda_tourism_osm.gpkg").to_crs(32735)
    s = (sec.merge(bld[["sector_id", "n_buildings", "mean_building_m2"]], on="sector_id", how="left")
            .merge(ele[["sector_id", "grid_km_per_km2"]], on="sector_id", how="left"))
    s["bld_density"] = s.n_buildings / s.unit_km2
    s["tmf_pct"] = 100 * s.sector_id.map(t.tmf_undisturbed_forest_ha + t.tmf_degraded_forest_ha) / (s.unit_km2 * 100)
    fig, ax = plt.subplots(2, 3, figsize=(16, 10))
    for a, (c, cm, ttl) in zip(ax.flat[:2] .tolist() + [ax[1, 0], ax[1, 2]],
                               [("bld_density", "Purples", "Building density (per km²)"),
                                ("mean_building_m2", "Oranges", "Mean building footprint (m²)"),
                                ("grid_km_per_km2", "BuPu", "Grid density (km per km²)"),
                                ("tmf_pct", "Greens", "TMF humid forest cover (%)")]):
        s.plot(column=c, cmap=cm, scheme="quantiles", k=6, ax=a, edgecolor="white", linewidth=.2,
               legend=True, legend_kwds=dict(fontsize=6.5, loc="lower left"),
               missing_kwds=dict(color="0.93"))
        V.frame_map(a, ttl, pk)
    s.plot(ax=ax[0, 2], color="0.94", edgecolor="white", linewidth=.2)
    grid.plot(ax=ax[0, 2], color="#8b5fbf", linewidth=.5)
    V.frame_map(ax[0, 2], "Electricity grid (gridfinder)", pk)
    s.plot(ax=ax[1, 1], color="0.94", edgecolor="white", linewidth=.2)
    for k, c in [("hotel", V.PARK), ("guest_house", "#e76f51"), ("lodge", "#f4a261"),
                 ("camp_site", "#2a9d8f"), ("attraction", "#8b5fbf"), ("restaurant", "0.55")]:
        p = poi[poi.category == k]
        if len(p):
            p.plot(ax=ax[1, 1], color=c, markersize=9, label=k.replace("_", " "))
    ax[1, 1].legend(fontsize=6.5, loc="lower left", ncol=2)
    V.frame_map(ax[1, 1], "Tourism points of interest (OSM)", pk)
    fig.suptitle("Physical infrastructure and forest cover around the national parks",
                 fontsize=12, y=.97)
    V.save(fig, "infrastructure_vs_forest", "map")


def map_firewood_vs_grid():
    """Firewood foraging by district with the grid overlaid.

    The EICV district field is a NUMERIC NISR code, not a name — joining on
    name silently produces an empty map.
    """
    fw = V.csv("forest/eicv_firewood_by_district.csv")
    fw["dist"] = fw.district.astype(int)
    dg, pk = V.districts(), V.parks()
    grid = gpd.read_file(V.GEO / "electricity/gridfinder_rwanda.gpkg").to_crs(32735)
    vmax = float(fw.mean_hours.max())
    fig, ax = plt.subplots(1, 3, figsize=(16.5, 5.6))
    for a, yr in zip(ax, sorted(fw.year.unique())):
        d = dg.merge(fw[fw.year == yr][["dist", "mean_hours"]], on="dist", how="left")
        d.plot(column="mean_hours", cmap="YlOrBr", vmin=0, vmax=vmax, ax=a,
               edgecolor="white", linewidth=.6, missing_kwds=dict(color="0.9", hatch="///"))
        grid.plot(ax=a, color=V.NONPARK, linewidth=.5, alpha=.9)
        pk.boundary.plot(ax=a, color=V.PARK, linewidth=1.3)
        nat = np.average(fw[fw.year == yr].mean_hours, weights=fw[fw.year == yr].n)
        a.set_title(f"EICV {int(yr)}   —   national mean {nat:.2f} h/week")
        a.set_axis_off(); a.set_aspect("equal")
    sm = mpl.cm.ScalarMappable(cmap="YlOrBr", norm=mpl.colors.Normalize(0, vmax))
    fig.colorbar(sm, ax=ax, fraction=.020, pad=.015).set_label(
        "mean hours per week foraging firewood", fontsize=9)
    fig.legend(handles=[mpl.lines.Line2D([], [], color=V.NONPARK, lw=1.5, label="electricity grid"),
                        mpl.lines.Line2D([], [], color=V.PARK, lw=1.8, label="national park")],
               loc="lower center", ncol=2, fontsize=9, bbox_to_anchor=(.45, -.02))
    fig.suptitle("Firewood foraging time by district, with the electricity grid", fontsize=12, y=1.0)
    V.save(fig, "firewood_vs_grid", "map")


def map_dw_all_classes():
    """All nine Dynamic World classes over time."""
    sec, pk = V.sectors(), V.parks()
    dw = V.csv("land-cover/dw_by_sector.csv", "sector_id")
    yrs = [2016, 2019, 2022, 2024]
    fig, axes = plt.subplots(9, len(yrs), figsize=(3.0 * len(yrs), 2.55 * 9))
    for i, (band, (lab, _)) in enumerate(V.LANDCOVER.items()):
        vmax = float(np.nanpercentile(dw[dw.year.isin(yrs)][band], 99)) or 1e-6
        for j, yr in enumerate(yrs):
            a = axes[i, j]
            t = sec.copy()
            t["v"] = t.sector_id.map(dw[dw.year == yr].set_index("sector_id")[band])
            t.plot(column="v", cmap="viridis", vmin=0, vmax=vmax, ax=a, edgecolor="white", linewidth=.1)
            pk.boundary.plot(ax=a, color=V.PARK, linewidth=.55)
            a.set_axis_off(); a.set_aspect("equal")
            if i == 0:
                a.set_title(str(yr), fontsize=11)
            if j == 0:
                a.text(-.07, .5, lab, transform=a.transAxes, rotation=90,
                       va="center", ha="center", fontsize=9.5)
        sm = mpl.cm.ScalarMappable(cmap="viridis", norm=mpl.colors.Normalize(0, vmax))
        fig.colorbar(sm, ax=axes[i, :].tolist(), fraction=.013, pad=.006).ax.tick_params(labelsize=6.5)
    fig.suptitle("All nine Dynamic World land-cover classes (mean per-pixel probability by sector)",
                 fontsize=13, y=.995)
    V.save(fig, "dw_all_classes", "map")


def map_cell_quadrants():
    """Quadrant maps at cell level (median splits)."""
    cm_ = V.cells()
    m = V.csv("forest/cell_master.csv", "cell_id")
    m.loc[m.treecover2000_ha < 20, ["loss_rate", "planted_share"]] = np.nan
    m["planted_share"] = m.planted_share.clip(upper=100)
    cm_ = cm_[["cell_id", "geometry"]].merge(m, on="cell_id", how="left")
    pk = V.parks()

    def quad(a, xv, yv, xl, yl, t):
        d = cm_.dropna(subset=[xv, yv]).copy()
        hx, hy = d[xv] > d[xv].median(), d[yv] > d[yv].median()
        d["q"] = np.select([hx & hy, hx & ~hy, ~hx & hy],
                           ["high/high", f"high {xl} / low {yl}", f"low {xl} / high {yl}"], "low/low")
        col = {"high/high": "#6a4c93", f"high {xl} / low {yl}": V.PARK,
               f"low {xl} / high {yl}": "#2a9d8f", "low/low": "0.88"}
        cm_.plot(ax=a, color="0.95", edgecolor="none")
        for k, c in col.items():
            s = d[d.q == k]
            if len(s):
                s.plot(ax=a, color=c, edgecolor="none", label=k)
        a.legend(fontsize=6.5, loc="lower left")
        V.frame_map(a, t, pk)

    fig, ax = plt.subplots(1, 3, figsize=(16.5, 5.6))
    quad(ax[0], "bld_density", "loss_rate", "buildings", "loss", "Building density × forest loss")
    quad(ax[1], "grid_km_per_km2", "loss_rate", "grid", "loss", "Grid density × forest loss")
    quad(ax[2], "planted_share", "loss_rate", "planted", "loss", "Planted share × forest loss")
    fig.suptitle("Quadrant maps, cell level (median splits)", fontsize=12, y=1.02)
    V.save(fig, "cell_quadrants", "map")


# ==========================================================================
# SPATIAL STATISTICS
# ==========================================================================

def fig_correlation_heatmap():
    """Spearman correlation structure, cell and sector side by side."""
    VARC = {"loss_rate": "forest loss %", "loss_per_km2": "loss ha/km²",
            "planted_share": "planted %", "treecover2000_ha": "tree cover 2000",
            "bld_density": "building density", "mean_building_m2": "mean building m²",
            "pop_density": "population density", "grid_km_per_km2": "grid density",
            "dist_to_park_km": "distance to park", "park_share": "share inside park"}
    m = V.csv("forest/cell_master.csv", "cell_id")
    m.loc[m.treecover2000_ha < 20, ["loss_rate", "planted_share"]] = np.nan
    sec = V.csv("forest/pop_vs_forest_by_sector.csv", "sector_id")
    SV = {**VARC, "pop_growth_pct": "pop growth 12→22", "tmf_undist_loss": "TMF undisturbed lost",
          "dw_tree_chg": "DW tree change", "radd_per_km2": "RADD ha/km²"}
    fig, axes = plt.subplots(1, 2, figsize=(17, 7.2))
    im = None
    for a, (df, vs, t) in zip(axes, [(m, VARC, f"Cell level (n={len(m):,})"),
                                     (sec, SV, f"Sector level (n={len(sec)})")]):
        cols = [c for c in vs if c in df.columns]
        C = df[cols].corr(method="spearman")
        im = a.imshow(C, cmap="RdBu_r", vmin=-1, vmax=1)
        a.set_xticks(range(len(cols))); a.set_xticklabels([vs[c] for c in cols],
                                                         rotation=45, ha="right", fontsize=7.5)
        a.set_yticks(range(len(cols))); a.set_yticklabels([vs[c] for c in cols], fontsize=7.5)
        for i in range(len(cols)):
            for k in range(len(cols)):
                v = C.iloc[i, k]
                a.text(k, i, f"{v:.2f}", ha="center", va="center", fontsize=6.2,
                       color="white" if abs(v) > .55 else "0.2")
        a.set_title(t); a.grid(False)
    fig.colorbar(im, ax=axes, fraction=.016, pad=.02).set_label("Spearman ρ", fontsize=9)
    fig.suptitle("Correlation structure of the sector and cell variables", fontsize=12, y=1.0)
    V.save(fig, "correlation_heatmap")


def map_lisa_clusters():
    """LISA cluster maps with Moran's I. Legend sits below, clear of the maps."""
    from esda.moran import Moran, Moran_Local
    from libpysal.weights import Queen
    sec = V.sectors()
    d = V.csv("forest/pop_vs_forest_by_sector.csv", "sector_id")
    s = sec[["sector_id", "geometry"]].merge(d, on="sector_id", how="left")
    pk = V.parks()
    w = Queen.from_dataframe(s, use_index=False); w.transform = "r"
    CAT = {1: ("High–High", V.PARK), 2: ("Low–High", "#a8c6e8"),
           3: ("Low–Low", V.NONPARK), 4: ("High–Low", "#f4a261")}
    VARS = [("loss_per_km2", "Hansen loss ha/km²"), ("pop_density", "population density"),
            ("tmf_undist_loss", "TMF undisturbed loss"), ("dw_tree_chg", "DW tree change")]
    fig, axes = plt.subplots(1, 4, figsize=(18, 5.6))
    for a, (c, lab) in zip(axes, VARS):
        x = s[c].fillna(s[c].median()).values
        li = Moran_Local(x, w, permutations=999); mi = Moran(x, w, permutations=999)
        s["q"] = np.where(li.p_sim <= 0.05, li.q, 0)
        s[s.q == 0].plot(ax=a, color="0.92", edgecolor="white", linewidth=.2)
        for k, (_nm, col) in CAT.items():
            sub = s[s.q == k]
            if len(sub):
                sub.plot(ax=a, color=col, edgecolor="white", linewidth=.2)
        V.frame_map(a, f"{lab}\nMoran's I = {mi.I:.3f}  (p = {mi.p_sim:.3f})", pk)
    handles = [mpl.patches.Patch(color=c, label=n) for n, c in CAT.values()] + \
              [mpl.patches.Patch(color="0.92", label="not significant")]
    fig.legend(handles=handles, loc="lower center", ncol=5, fontsize=9, bbox_to_anchor=(.5, -.02))
    fig.suptitle("Local spatial clustering (LISA, queen contiguity, p ≤ 0.05)", fontsize=12, y=1.02)
    V.save(fig, "lisa_clusters", "map")


# ==========================================================================
# LABOUR — district maps and the full ISIC breakdown
# ==========================================================================

# Fixed six so the establishment and worker panels are read side by side.
# Agriculture is included precisely because it is huge in the LFS and tiny in
# the EC: Rwandan farming is cooperatives and households, not registered firms.
SIX = [1, 3, 6, 7, 9, 16]


def _dgeo():
    """District geometry with a clean integer `dist` key for merging."""
    g = V.districts()
    g = g[g.dist.notna()].copy()
    g["dist"] = g.dist.astype("int64")
    return g


def _isic_shares(source: str) -> pd.DataFrame:
    """District x year x ISIC shares, recomputed from counts, as percentages.

    The two files publish `share` on different scales (EC a fraction, LFS a
    percentage), so both are rebuilt from the raw counts rather than trusted.
    Sections 1-21 only; 99 "not stated" is dropped before shares are taken.
    """
    if source == "ec":
        d = V.csv("labour/ec_district_isic.csv").rename(columns={"n": "v"})
    else:
        d = V.csv("labour/lfs_district_isic.csv").rename(columns={"workers": "v"})
    d = d[d.isic.between(1, 21)].copy()
    d["dist"] = d.dist.astype("int64")
    d["isic"] = d.isic.astype(int)
    d["pct"] = 100 * d.v / d.groupby(["year", "dist"])["v"].transform("sum")
    return d


def _cbar(fig, axes, cmap, vmin, vmax, label):
    """Colourbar placed outside the map axes, never over the geography."""
    sm = mpl.cm.ScalarMappable(cmap=cmap,
                               norm=mpl.colors.Normalize(vmin=vmin, vmax=vmax))
    cb = fig.colorbar(sm, ax=axes, fraction=0.020, pad=0.012)
    cb.set_label(label, fontsize=8)
    cb.ax.tick_params(labelsize=7)
    return cb


def map_accommodation_district():
    """Accommodation & food service (ISIC 9) by district over time, both sources.

    Top row: Establishment Census, share of establishments. Bottom row: Labour
    Force Survey, share of workers. LFS years are thinned to the EC column
    count. The rows carry independent colour scales because a share of firms
    and a share of workers are not the same quantity and must not be read off
    a common bar.
    """
    dg, pk = _dgeo(), V.parks()
    ec = _isic_shares("ec"); lfs = _isic_shares("lfs")
    ec9, lf9 = ec[ec.isic == 9], lfs[lfs.isic == 9]
    ecy = sorted(ec9.year.unique())
    lfa = sorted(lf9.year.unique())
    idx = np.linspace(0, len(lfa) - 1, len(ecy)).round().astype(int)
    lfy = [lfa[i] for i in idx]

    fig, axes = plt.subplots(2, len(ecy), figsize=(2.9 * len(ecy), 7.4))
    rows = [(ec9, ecy, "Establishment Census\nshare of establishments (%)"),
            (lf9, lfy, "Labour Force Survey\nshare of workers (%)")]
    for r, (d, yrs, lab) in enumerate(rows):
        vmax = float(d[d.year.isin(yrs)].pct.quantile(0.97))
        for c, y in enumerate(yrs):
            ax = axes[r, c]
            g = dg.merge(d[d.year == y][["dist", "pct"]], on="dist", how="left")
            g.plot(column="pct", ax=ax, cmap="RdPu", vmin=0, vmax=vmax,
                   edgecolor="white", linewidth=0.2,
                   missing_kwds={"color": "0.92"})
            V.frame_map(ax, str(int(y)), pk)
        _cbar(fig, list(axes[r, :]), "RdPu", 0, vmax, lab)
    fig.suptitle("Accommodation & food service by district, 2011-2025", y=0.97)
    V.save(fig, "accommodation_district", "map")


def _six_panel(source: str, label: str, name: str, cmap: str):
    """Six ISIC sections mapped across districts, latest year of the source.

    Each panel gets its own colour scale: agriculture and mining differ by
    two orders of magnitude, so a shared scale would render four of the six
    panels flat.
    """
    d = _isic_shares(source)
    yr = int(d.year.max())
    d = d[(d.year == yr) & (d.isic.isin(SIX))]
    dg, pk = _dgeo(), V.parks()

    fig, axes = plt.subplots(2, 3, figsize=(12.0, 8.2))
    for ax, code in zip(axes.ravel(), SIX):
        g = dg.merge(d[d.isic == code][["dist", "pct"]], on="dist", how="left")
        vmax = float(np.nanmax([g.pct.max(), 0.1]))
        g.plot(column="pct", ax=ax, cmap=cmap, vmin=0, vmax=vmax,
               edgecolor="white", linewidth=0.2, missing_kwds={"color": "0.92"})
        V.frame_map(ax, f"{code}. {V.ISIC[code]}", pk)
        _cbar(fig, ax, cmap, 0, vmax, "%")
    fig.suptitle(f"{label} by district and ISIC section, {yr}", y=0.97)
    V.save(fig, name, "map")


def map_establishments_six_sectors():
    """Six ISIC sections, share of establishments by district (EC, latest round)."""
    _six_panel("ec", "Share of establishments", "establishments_six_sectors", "YlGnBu")


def map_workers_six_sectors():
    """Six ISIC sections, share of workers by district (LFS, latest round)."""
    _six_panel("lfs", "Share of workers", "workers_six_sectors", "YlOrBr")


def fig_isic_composition_full():
    """All 21 ISIC sections, establishments vs workers, latest year of each.

    The gap between the two bars is the point: sections where firms are many
    but employment is thin (retail) versus where employment is overwhelming
    but registered firms are few (agriculture).
    """
    out = {}
    for src, key in (("ec", "Establishments"), ("lfs", "Workers")):
        d = _isic_shares(src)
        y = d.year.max()
        d = d[d.year == y]
        s = d.groupby("isic")["v"].sum()
        out[f"{key} ({int(y)})"] = 100 * s / s.sum()
    t = pd.DataFrame(out).reindex(range(1, 22)).fillna(0)
    t.index = [f"{i}. {V.ISIC[i]}" for i in t.index]
    t = t.sort_values(t.columns[1])

    fig, ax = plt.subplots(figsize=(8.4, 8.0))
    y = np.arange(len(t))
    ax.barh(y - 0.2, t.iloc[:, 0], height=0.4, color=V.NONPARK, label=t.columns[0])
    ax.barh(y + 0.2, t.iloc[:, 1], height=0.4, color=V.PARK, label=t.columns[1])
    ax.set_yticks(y); ax.set_yticklabels(t.index, fontsize=8)
    ax.set_xlabel("share of national total (%)")
    ax.set_title("Economic composition by ISIC section, both sources")
    ax.legend(loc="lower right")
    ax.grid(axis="y", alpha=0)
    V.save(fig, "isic_composition_full")
    V.save_table(t, "isic_composition_full")


def fig_isic_trends_full():
    """Every ISIC section's share over time, both sources, as small multiples.

    EC (5 rounds, 2011-2023) and LFS (annual, 2017-2025) are drawn on one axis
    per section. They measure different things, so they are not expected to
    coincide; divergence in level with agreement in slope is the readable
    signal.
    """
    ec, lfs = _isic_shares("ec"), _isic_shares("lfs")
    nat = {}
    for k, d in (("ec", ec), ("lfs", lfs)):
        g = d.groupby(["year", "isic"])["v"].sum().reset_index()
        g["pct"] = 100 * g.v / g.groupby("year")["v"].transform("sum")
        nat[k] = g

    fig, axes = plt.subplots(7, 3, figsize=(11.0, 15.0), sharex=True)
    for ax, code in zip(axes.ravel(), range(1, 22)):
        for k, col, mk in (("ec", V.NONPARK, "o"), ("lfs", V.PARK, None)):
            s = nat[k][nat[k].isic == code].sort_values("year")
            if s.empty:
                continue
            ax.plot(s.year, s.pct, color=col, marker=mk, ms=3, lw=1.2,
                    label={"ec": "Establishments", "lfs": "Workers"}[k])
        ax.set_title(f"{code}. {V.ISIC[code]}", fontsize=8)
        ax.tick_params(labelsize=7)
        V.year_axis(ax)
    for ax in axes.ravel()[21:]:
        ax.set_axis_off()
    axes[0, 0].legend(fontsize=7, loc="upper left")
    fig.suptitle("ISIC section shares over time (%), Establishment Census vs LFS",
                 y=0.995)
    fig.tight_layout()
    V.save(fig, "isic_trends_full")
    for src in ("ec", "lfs"):
        w = nat[src].pivot(index="isic", columns="year", values="pct")
        w.index = [f"{i}. {V.ISIC[i]}" for i in w.index]
        V.save_table(w, f"{src}_isic_shares_wide")


# ==========================================================================
# FOREST — divergence, confounds, quality, alerts, cell-level proximity
# ==========================================================================

def _border_map():
    """sector_id -> border flag, from the geodata.rw park exposure table."""
    ex = V.csv("protected-areas/sectors_park_exposure_geodatarw.csv", "sector_id")
    return ex.set_index("sector_id").border


def fig_hansen_tmf_divergence():
    """Hansen tree-cover loss against JRC TMF forest decline, 2006-2024.

    The two products disagree by construction. Hansen counts any loss of tree
    cover, including harvest of plantations; TMF tracks the moist-forest area
    itself and treats plantation cycling as land already deforested. Where the
    Hansen series runs far above the TMF series, the extra loss is plantation
    turnover, not forest conversion — the plantation confound in one figure.
    """
    p = V.csv("forest/sector_year_panel.csv", "sector_id")
    han = p.groupby("year")["loss_ha"].sum()

    tmf = V.csv("forest/tmf_by_sector.csv", "sector_id")
    stock = (tmf.assign(f=tmf.tmf_undisturbed_forest_ha + tmf.tmf_degraded_forest_ha)
                .groupby("year")["f"].sum().sort_index())
    tmf_loss = (-stock.diff()).dropna()

    yrs = sorted(set(han.index) & set(tmf_loss.index))
    han, tmf_loss = han.reindex(yrs), tmf_loss.reindex(yrs)

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11.0, 4.2))
    a1.plot(yrs, han, color=V.PARK, marker="o", ms=3, label="Hansen GFC tree-cover loss")
    a1.plot(yrs, tmf_loss, color=V.NONPARK, marker="s", ms=3, label="JRC TMF forest decline")
    a1.fill_between(yrs, tmf_loss, han, where=(han > tmf_loss), color=V.PARK,
                    alpha=0.12, label="excess Hansen loss")
    a1.set_ylabel("hectares per year"); a1.set_title("Annual flows")
    # The 2009 TMF spike runs through the usual upper-left corner, so the
    # legend goes above the axes rather than over the series.
    a1.legend(fontsize=7, loc="lower center", bbox_to_anchor=(0.5, 1.06), ncol=3)
    V.year_axis(a1)

    a2.plot(yrs, han.cumsum(), color=V.PARK, lw=1.6, label="Hansen, cumulative")
    a2.plot(yrs, tmf_loss.cumsum(), color=V.NONPARK, lw=1.6, label="TMF, cumulative")
    a2.set_ylabel("cumulative hectares"); a2.set_title("Cumulative since 2006")
    a2.legend(fontsize=7); V.year_axis(a2)
    fig.suptitle("Hansen and TMF measure different things", y=1.0)
    V.save(fig, "hansen_tmf_divergence")


def fig_sdpt_confound():
    """The plantation confound test, at cell level.

    If Hansen loss were forest conversion, it would not track planted-tree
    area. It does: loss rates rise steeply across the planted-share
    distribution. Bars are bootstrap 95% CIs over cells within each bin.
    """
    c = V.csv("forest/cell_master.csv", "cell_id")
    c = c[c.treecover2000_ha > 0].copy()
    QL = ["Q1 (least planted)", "Q2", "Q3", "Q4", "Q5 (most planted)"]
    c["q"] = pd.qcut(c.planted_share.rank(method="first"), 5, labels=QL)

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11.0, 4.2))
    for br, col, lab in ((0, V.NONPARK, "interior"), (1, V.PARK, "park-bordering")):
        s = c[c.border == br]
        # Reindex onto the full quintile set: park-bordering cells do not
        # populate every bin, and a short series would desync the tick labels.
        m = s.groupby("q", observed=False)["loss_rate"].mean().reindex(QL)
        ci = [_boot(s[s.q == q].loss_rate.dropna()) for q in QL]
        lo = np.array([a for a, _ in ci]); hi = np.array([b for _, b in ci])
        x = np.arange(len(QL)) + (0.12 if br else -0.12)
        a1.errorbar(x, m.values, yerr=[m.values - lo, hi - m.values],
                    fmt="o", ms=4, color=col, capsize=2, lw=1, label=lab)
    a1.set_xticks(range(len(QL)))
    a1.set_xticklabels(QL, rotation=25, ha="right", fontsize=7)
    a1.set_ylabel("Hansen loss / tree cover 2000 (%)")
    a1.set_title("Loss rate by planted-tree quintile"); a1.legend(fontsize=7)

    a2.scatter(c.planted_share * 100, c.loss_rate, s=4, alpha=0.25,
               c=np.where(c.border == 1, V.PARK, V.NONPARK), lw=0)
    a2.set_xlabel("planted trees, share of cell (%)")
    a2.set_ylabel("loss rate (%)")
    a2.set_title(f"All {len(c):,} cells with tree cover in 2000")
    fig.suptitle("Hansen loss tracks plantation area, not park proximity", y=1.0)
    V.save(fig, "sdpt_confound")


def fig_tmf_forest_quality():
    """TMF forest quality over time: undisturbed, degraded, regrowth.

    Quality, not just extent. A stable total forest area can still be a
    forest moving from undisturbed to degraded, and TMF is the only product
    here that separates the two.
    """
    tmf = V.csv("forest/tmf_by_sector.csv", "sector_id")
    tmf["border"] = tmf.sector_id.map(_border_map())
    cols = [("tmf_undisturbed_forest_ha", "undisturbed", "#1b4332"),
            ("tmf_degraded_forest_ha", "degraded", "#e9c46a"),
            ("tmf_regrowth_ha", "regrowth", "#2a9d8f")]

    fig, axes = plt.subplots(1, 3, figsize=(12.5, 4.0))
    g = tmf.groupby("year")[[c for c, _, _ in cols]].sum().sort_index()
    for c, lab, col in cols:
        axes[0].plot(g.index, g[c] / 1000, color=col, lw=1.6, label=lab)
    axes[0].set_ylabel("thousand hectares"); axes[0].set_title("National stocks")
    axes[0].legend(fontsize=7); V.year_axis(axes[0])

    for ax, br, lab in ((axes[1], 1, "Park-bordering sectors"),
                        (axes[2], 0, "Interior sectors")):
        s = tmf[tmf.border == br].groupby("year")[[c for c, _, _ in cols]].sum()
        tot = s.sum(axis=1).replace(0, np.nan)
        for c, l2, col in cols:
            ax.plot(s.index, 100 * s[c] / tot, color=col, lw=1.6, label=l2)
        ax.set_ylabel("share of TMF forest (%)"); ax.set_title(lab)
        V.year_axis(ax)
    fig.suptitle("Forest quality from JRC Tropical Moist Forest", y=1.02)
    V.save(fig, "tmf_forest_quality")


def fig_radd_annual():
    """Annual RADD deforestation alerts, park-bordering vs interior.

    RADD is radar-based and near-real-time, so it catches disturbance under
    cloud that optical products miss. Coverage starts in 2020; earlier years
    are absent by design, not by data loss.
    """
    r = V.csv("forest/radd_by_sector.csv", "sector_id")
    r["border"] = r.sector_id.map(_border_map())
    g = r.groupby(["year", "border"])["radd_alert_ha"].sum().unstack(fill_value=0)

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10.5, 4.0))
    w, x = 0.38, np.arange(len(g))
    if 0 in g:
        a1.bar(x - w / 2, g[0], w, color=V.NONPARK, label="interior")
    if 1 in g:
        a1.bar(x + w / 2, g[1], w, color=V.PARK, label="park-bordering")
    a1.set_xticks(x); a1.set_xticklabels([int(y) for y in g.index])
    a1.set_ylabel("alert area (ha)"); a1.set_title("Total alert area")
    a1.legend(fontsize=7)

    n = r.groupby("border").sector_id.nunique()
    per = g.div(n, axis=1)
    for br, col, lab in ((0, V.NONPARK, "interior"), (1, V.PARK, "park-bordering")):
        if br in per:
            a2.plot(per.index, per[br], color=col, marker="o", ms=4, label=lab)
    a2.set_ylabel("alert ha per sector"); a2.set_title("Per sector, size-adjusted")
    a2.legend(fontsize=7); V.year_axis(a2)
    fig.suptitle("RADD radar deforestation alerts, 2020 onward", y=1.0)
    V.save(fig, "radd_annual")


def fig_pop_vs_forest_loss():
    """Population and population growth against forest loss, sector level.

    The headline null of the descriptive work: neither population level nor
    population growth orders forest loss across sectors. Whatever drives loss
    is not simply where people are.
    """
    d = V.csv("forest/pop_vs_forest_by_sector.csv", "sector_id")
    d = d[d.treecover2000_ha > 0].copy()

    fig, axes = plt.subplots(1, 3, figsize=(13.0, 4.0))
    specs = [("log_pop", "log population (2022)", None),
             ("pop_growth_pct", "population growth 2012-2022 (%)", None),
             ("pop_density", "population per km$^2$", "log")]
    for ax, (col, lab, scale) in zip(axes, specs):
        s = d[[col, "loss_rate", "border"]].dropna()
        for br, c, l in ((0, V.NONPARK, "interior"), (1, V.PARK, "park-bordering")):
            q = s[s.border == br]
            ax.scatter(q[col], q.loss_rate, s=10, alpha=0.55, color=c, lw=0, label=l)
        if len(s) > 5:
            b = np.polyfit(s[col], s.loss_rate, 1)
            xx = np.linspace(s[col].min(), s[col].max(), 50)
            ax.plot(xx, np.polyval(b, xx), color="0.25", lw=1.2, ls="--")
            rho = s[col].corr(s.loss_rate, method="spearman")
            ax.set_title(f"{lab}\nSpearman $\\rho$ = {rho:.2f}", fontsize=9)
        if scale:
            ax.set_xscale(scale)
        ax.set_xlabel(lab); ax.set_ylabel("loss rate (%)")
    axes[0].legend(fontsize=7)
    fig.suptitle("Population does not order forest loss across sectors", y=1.02)
    V.save(fig, "pop_vs_forest_loss")


def map_cell_deforestation_park():
    """Cell-level deforestation against park proximity — 2,148 cells.

    The cell is the finest geography on which both the forest measures and the
    park boundaries are defined, so this is the sharpest spatial view the
    public data supports.

    Two caveats drive the panel design. First, the loss *rate* divides by
    year-2000 tree cover, and 81 cells return rates above 100% because Hansen
    records loss on plantations established after 2000 — these sit mostly in
    the east, far from any park, and a plain mean over them is meaningless.
    The rate panel therefore restricts to cells with at least 10 ha of
    year-2000 cover and reports the median alongside the mean. Second, loss
    per km2 of land needs no forest denominator at all, so it is shown as the
    check that does not depend on that choice.
    """
    c = V.csv("forest/cell_master.csv", "cell_id")
    cg = V.cells().merge(c[["cell_id", "loss_rate", "dist_to_park_km",
                            "planted_share", "border"]], on="cell_id", how="left")
    pk = V.parks()

    fig = plt.figure(figsize=(14.5, 5.8))
    gs = fig.add_gridspec(2, 2, width_ratios=[1.35, 1], hspace=0.45, wspace=0.28)

    ax = fig.add_subplot(gs[:, 0])
    vmax = float(cg.loss_rate.quantile(0.96))
    cg.plot(column="loss_rate", ax=ax, cmap="OrRd", vmin=0, vmax=vmax,
            edgecolor="none", missing_kwds={"color": "0.92"})
    V.frame_map(ax, f"Hansen loss rate, {len(c):,} cells", pk)
    cb = _cbar(fig, ax, "OrRd", 0, vmax, "loss / tree cover 2000 (%)")
    cb.ax.yaxis.set_label_position("left")

    edges = [0, 1, 2, 5, 10, 20, 40, np.inf]
    lbl = ["0-1", "1-2", "2-5", "5-10", "10-20", "20-40", "40+"]
    b = c.dropna(subset=["dist_to_park_km"]).copy()
    b["band"] = pd.cut(b.dist_to_park_km, edges, labels=lbl, right=False)

    # (a) rate, on cells with a denominator worth dividing by
    a1 = fig.add_subplot(gs[0, 1])
    r = b[b.treecover2000_ha >= 10].dropna(subset=["loss_rate"])
    m = r.groupby("band", observed=True)["loss_rate"].agg(["mean", "median", "size"])
    ci = [_boot(r[r.band == k].loss_rate) for k in m.index]
    lo = np.array([x for x, _ in ci]); hi = np.array([x for _, x in ci])
    x = np.arange(len(m))
    a1.errorbar(x, m["mean"], yerr=[m["mean"] - lo, hi - m["mean"]], fmt="o", ms=5,
                color=V.PARK, capsize=3, lw=1.2, label="mean (95% CI)")
    a1.plot(x, m["median"], marker="D", ms=4, ls="--", lw=1, color=V.NONPARK,
            label="median")
    a1.set_xticks(x); a1.set_xticklabels(m.index, fontsize=8)
    a1.set_ylabel("loss / tree cover 2000 (%)")
    a1.set_title(f"Loss rate, cells with $\\geq$10 ha cover in 2000 "
                 f"(n = {len(r):,} of {len(b):,})", fontsize=9)
    a1.legend(fontsize=7)

    # (b) the denominator-free check
    a2 = fig.add_subplot(gs[1, 1])
    q = b.dropna(subset=["loss_per_km2"])
    m2 = q.groupby("band", observed=True)["loss_per_km2"].agg(["mean", "size"])
    ci2 = [_boot(q[q.band == k].loss_per_km2) for k in m2.index]
    lo2 = np.array([x for x, _ in ci2]); hi2 = np.array([x for _, x in ci2])
    x2 = np.arange(len(m2))
    a2.errorbar(x2, m2["mean"], yerr=[m2["mean"] - lo2, hi2 - m2["mean"]], fmt="o",
                ms=5, color=V.PARK, capsize=3, lw=1.2)
    for i, n in enumerate(m2["size"]):
        a2.annotate(f"n={n}", (i, m2["mean"].iloc[i]), textcoords="offset points",
                    xytext=(0, -14), ha="center", fontsize=6, color="0.45")
    a2.set_xticks(x2); a2.set_xticklabels(m2.index, fontsize=8)
    a2.set_xlabel("distance to nearest national park (km)")
    a2.set_ylabel("loss ha per km$^2$")
    a2.set_title("Loss per km$^2$ of land, all cells", fontsize=9)

    V.save(fig, "cell_deforestation_park", "map")


# ==========================================================================
# LAND COVER — biennial maps and change decompositions
# ==========================================================================

def map_dw_biennial():
    """Dynamic World tree cover by sector, every second year.

    Biennial rather than annual: at sector resolution the year-to-year
    differences are mostly classifier noise, and a two-year step makes the
    trend legible without implying precision the product does not have.
    """
    dw = V.csv("land-cover/dw_by_sector.csv", "sector_id")
    cls = [c for c in dw.columns if c.startswith("dw_")]
    dw["tree_pct"] = 100 * dw.dw_trees / dw[cls].sum(axis=1)
    yrs = sorted(dw.year.unique())[::2]
    sg, pk = V.sectors(), V.parks()

    n = len(yrs)
    ncol = min(n, 5)
    nrow = int(np.ceil(n / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(3.0 * ncol, 3.3 * nrow),
                             squeeze=False)
    vmax = float(dw[dw.year.isin(yrs)].tree_pct.quantile(0.97))
    for ax, y in zip(axes.ravel(), yrs):
        g = sg.merge(dw[dw.year == y][["sector_id", "tree_pct"]],
                     on="sector_id", how="left")
        g.plot(column="tree_pct", ax=ax, cmap="Greens", vmin=0, vmax=vmax,
               edgecolor="white", linewidth=0.1, missing_kwds={"color": "0.92"})
        V.frame_map(ax, str(int(y)), pk)
    for ax in axes.ravel()[n:]:
        ax.set_axis_off()
    _cbar(fig, list(axes.ravel()), "Greens", 0, vmax, "tree cover (% of sector)")
    fig.suptitle("Dynamic World tree cover by sector, biennial", y=0.99)
    V.save(fig, "dw_biennial", "map")


def fig_dw_landuse_change():
    """Net land-cover change by class, from Dynamic World pixel transitions.

    Built from the true pixel-level transition matrix, so gains and losses are
    gross flows between named classes rather than differences of two stocks.
    Net change is gain minus loss; the stacked panel shows what each class
    exchanged with.
    """
    t = V.csv("land-cover/dw_transitions_national.csv")
    t = t[t.frm != t.to].copy()
    gain = t.groupby(["y1", "to"]).px.sum().rename("gain")
    loss = t.groupby(["y1", "frm"]).px.sum().rename("loss")
    net = (pd.concat([gain, loss], axis=1).fillna(0)
             .assign(net=lambda d: d.gain - d.loss).reset_index()
             .rename(columns={"level_1": "cls"}))
    net["ha"] = net.net * 0.01   # 10 m pixels -> hectares

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12.0, 4.4))
    for cls in ORDER:
        s = net[net.cls == cls].sort_values("y1")
        if s.empty:
            continue
        a1.plot(s.y1, s.ha, color=FLOWCOL[cls], lw=1.5, marker="o", ms=3,
                label=SHORT[cls])
    a1.axhline(0, color="0.3", lw=0.8)
    a1.set_ylabel("net change (ha per year)")
    a1.set_title("Net annual change by class")
    a1.legend(fontsize=7, ncol=2); V.year_axis(a1)

    tot = net.groupby("cls").ha.sum().reindex(ORDER).dropna()
    a2.barh([SHORT[c] for c in tot.index], tot.values,
            color=[FLOWCOL[c] for c in tot.index])
    a2.axvline(0, color="0.3", lw=0.8)
    a2.set_xlabel("cumulative net change (ha)")
    a2.set_title(f"Cumulative, {int(net.y1.min())}-{int(net.y1.max())}")
    a2.grid(axis="y", alpha=0)
    fig.suptitle("Land-use change from Dynamic World pixel transitions", y=1.0)
    V.save(fig, "dw_landuse_change")


def fig_landcover_change_district():
    """District-level change in the three classes that move: trees, crops, built.

    First to last Dynamic World year, in percentage points of district area,
    ordered by tree change. Park-bordering districts are marked so the
    gradient can be read against park exposure.
    """
    dw = V.csv("land-cover/dw_by_sector.csv", "sector_id")
    ex = V.csv("protected-areas/sectors_park_exposure_geodatarw.csv", "sector_id")
    dw = dw.drop(columns=[c for c in ("district",) if c in dw.columns])
    dw = dw.merge(ex[["sector_id", "district", "district_id", "border"]],
                  on="sector_id", how="left")
    cls = [c for c in dw.columns if c.startswith("dw_")]
    y0, y1 = int(dw.year.min()), int(dw.year.max())

    rows = []
    for y in (y0, y1):
        s = dw[dw.year == y].groupby(["district_id", "district"])[cls].sum()
        s = 100 * s.div(s.sum(axis=1), axis=0)
        rows.append(s.assign(year=y))
    a, b = rows
    chg = (b[cls] - a[cls]).reset_index()
    park = ex.groupby("district_id").border.mean()

    fig, axes = plt.subplots(1, 3, figsize=(13.0, 6.2), sharey=True)
    chg = chg.sort_values("dw_trees")
    ypos = np.arange(len(chg))
    for ax, col in zip(axes, ["dw_trees", "dw_crops", "dw_built"]):
        name, colr = V.LANDCOVER[col]
        ax.barh(ypos, chg[col], color=colr, height=0.75)
        ax.axvline(0, color="0.3", lw=0.8)
        ax.set_title(f"{name}"); ax.set_xlabel("change (pp of district area)")
        ax.grid(axis="y", alpha=0)
    axes[0].set_yticks(ypos)
    axes[0].set_yticklabels(
        [f"{d}{' *' if park.get(i, 0) > 0 else ''}"
         for i, d in zip(chg.district_id, chg.district)], fontsize=7)
    fig.suptitle(f"Land-cover change by district, {y0}-{y1}  "
                 f"(* = district contains park-bordering sectors)", y=0.99)
    V.save(fig, "landcover_change_district")
    V.save_table(chg.set_index("district")[["dw_trees", "dw_crops", "dw_built"]],
                 "landcover_change_district")


# ==========================================================================
# PANEL — the sector-year analysis frame
# ==========================================================================

def fig_sector_panel_overview():
    """The sector-year panel that the analysis runs on: 416 sectors x 19 years.

    Four views of the same frame: the loss hazard rate (loss over forest still
    standing, which is the rate a duration model would use), year-on-year tree
    change from Dynamic World, rainfall anomaly, and variable coverage. The
    coverage panel matters — Dynamic World starts in 2016 and TMF ends before
    Hansen, so the usable window differs by variable.

    HAZARD DENOMINATOR: hazard_pct is loss over forest still standing, so it
    explodes where almost no forest remains. 162 sector-years carry under 1 ha
    in the denominator, and one (sector 1303, 2014) holds 1.4e-16 ha — floating
    point residue of zero — which returns a hazard of 1.9e17 and swamps every
    mean taken over the raw column. The panel restricts to sector-years with at
    least 10 ha of standing forest. Any model using this column needs the same
    guard.
    """
    p = V.csv("forest/sector_year_panel.csv", "sector_id")
    haz = p[p.forest_start_ha >= 10]

    fig, axes = plt.subplots(2, 2, figsize=(11.5, 7.6))
    a = axes.ravel()

    for br, col, lab in ((0, V.NONPARK, "interior"), (1, V.PARK, "park-bordering")):
        s = haz[haz.border == br].groupby("year")["hazard_pct"]
        m, se = s.mean(), s.sem()
        a[0].plot(m.index, m, color=col, lw=1.5, label=lab)
        a[0].fill_between(m.index, m - 1.96 * se, m + 1.96 * se, color=col, alpha=0.18)
    a[0].set_ylabel("loss / forest remaining (%)")
    a[0].set_title(f"Loss hazard rate, sector-years with $\\geq$10 ha standing\n"
                   f"(n = {len(haz):,} of {len(p):,}), mean with 95% CI", fontsize=9)
    a[0].legend(fontsize=7); V.year_axis(a[0])

    for br, col, lab in ((0, V.NONPARK, "interior"), (1, V.PARK, "park-bordering")):
        s = (p[p.border == br].dropna(subset=["tree_chg"])
               .assign(pp=lambda d: 100 * d.tree_chg).groupby("year")["pp"])
        m, se = s.mean(), s.sem()
        a[1].plot(m.index, m, color=col, lw=1.5, marker="o", ms=3, label=lab)
        a[1].fill_between(m.index, m - 1.96 * se, m + 1.96 * se, color=col, alpha=0.18)
    a[1].axhline(0, color="0.3", lw=0.8)
    a[1].set_ylabel("YoY change in tree share (pp of sector)")
    a[1].set_title("Dynamic World tree change (2016 onward)")
    a[1].legend(fontsize=7); V.year_axis(a[1])

    r = p.groupby("year")["rain_z"].mean()
    a[2].bar(r.index, r.values, color=np.where(r.values < 0, "#bc6c25", V.NONPARK))
    a[2].axhline(0, color="0.3", lw=0.8)
    a[2].set_ylabel("mean rainfall anomaly (z)")
    a[2].set_title("CHIRPS rainfall anomaly"); V.year_axis(a[2])

    cov = p.groupby("year")[["hazard_pct", "tree_chg", "tmf_forest", "rain_mm"]].apply(
        lambda g: 100 * g.notna().mean())
    for c, col in zip(cov.columns, [V.PARK, "#2a9d8f", "#e9c46a", V.NONPARK]):
        a[3].plot(cov.index, cov[c], lw=1.5, color=col, label=c)
    a[3].set_ylabel("% of sector-years non-missing")
    a[3].set_title("Variable coverage"); a[3].legend(fontsize=7); V.year_axis(a[3])

    fig.suptitle(f"Sector-year panel: {len(p):,} rows, "
                 f"{p.sector_id.nunique()} sectors, "
                 f"{int(p.year.min())}-{int(p.year.max())}", y=1.0)
    fig.tight_layout()
    V.save(fig, "sector_panel_overview")

    summ = haz.groupby("border")[["hazard_pct", "loss_ha", "tree_chg", "tmf_forest",
                                  "rain_mm", "rain_z", "dist_to_park_km"]].agg(
        ["mean", "std", "count"])
    V.save_table(summ, "sector_panel_summary")


# ==========================================================================
# REGISTRY / CLI
# ==========================================================================

OUTPUTS = {
    # forest
    "hazard_vs_tmf": (fig_hazard_vs_tmf, "forest"),
    "distance_decay": (fig_distance_decay, "forest"),
    "firewood_trend": (fig_firewood_trend, "forest"),
    "firewood_vs_grid": (map_firewood_vs_grid, "forest"),
    # land cover
    "transition_matrices_yoy": (fig_transition_matrices_yoy, "landcover"),
    "transition_flows": (fig_transition_flows, "landcover"),
    "transition_flows_district": (fig_transition_flows_district, "landcover"),
    "landuse_stacked_district": (fig_landuse_stacked_district, "landcover"),
    "dw_all_classes": (map_dw_all_classes, "landcover"),
    # labour
    "tourism_employment": (fig_tourism_employment, "labour"),
    "economy_composition": (fig_economy_composition, "labour"),
    "district_trajectories": (fig_district_trajectories, "labour"),
    "agriculture_workers_forest": (fig_agriculture_workers_forest, "labour"),
    # infrastructure
    "infrastructure_vs_forest": (map_infrastructure_vs_forest, "infrastructure"),
    # forest
    "hansen_tmf_divergence": (fig_hansen_tmf_divergence, "forest"),
    "sdpt_confound": (fig_sdpt_confound, "forest"),
    "tmf_forest_quality": (fig_tmf_forest_quality, "forest"),
    "radd_annual": (fig_radd_annual, "forest"),
    "pop_vs_forest_loss": (fig_pop_vs_forest_loss, "forest"),
    # land cover
    "dw_biennial": (map_dw_biennial, "landcover"),
    "dw_landuse_change": (fig_dw_landuse_change, "landcover"),
    "landcover_change_district": (fig_landcover_change_district, "landcover"),
    # labour
    "accommodation_district": (map_accommodation_district, "labour"),
    "establishments_six_sectors": (map_establishments_six_sectors, "labour"),
    "workers_six_sectors": (map_workers_six_sectors, "labour"),
    "isic_composition_full": (fig_isic_composition_full, "labour"),
    "isic_trends_full": (fig_isic_trends_full, "labour"),
    # panel
    "sector_panel_overview": (fig_sector_panel_overview, "panel"),
    # spatial
    "correlation_heatmap": (fig_correlation_heatmap, "spatial"),
    "lisa_clusters": (map_lisa_clusters, "spatial"),
    # cell level
    "cell_quadrants": (map_cell_quadrants, "cell"),
    "cell_deforestation_park": (map_cell_deforestation_park, "cell"),
}


def selfcheck() -> int:
    """Verify this file's own integrity before anything is rebuilt.

    Written after a bad edit duplicated ~800 lines and left two definitions of
    map_cell_deforestation_park; Python keeps the LAST definition, so the fixed
    version was silently shadowed by the stale one and the rebuilt figure came
    out byte-identical to the old one. Nothing failed and nothing warned.

    Parsing the file with ast catches that class of error immediately:
    duplicate definitions, registry entries with no function, and figure
    functions nobody registered. Run it before --all.
    """
    src = Path(__file__).read_text()
    tree = ast.parse(src)
    defs = [n.name for n in tree.body if isinstance(n, ast.FunctionDef)]

    problems = []

    dupes = sorted({d for d in defs if defs.count(d) > 1})
    for d in dupes:
        lines = [n.lineno for n in tree.body
                 if isinstance(n, ast.FunctionDef) and n.name == d]
        problems.append(f"duplicate definition of {d}() at lines "
                        f"{', '.join(map(str, lines))} — the last one wins")

    named = {f.__name__ for f, _ in OUTPUTS.values()}
    for key, (fn, _grp) in OUTPUTS.items():
        if fn.__name__ not in defs:
            problems.append(f"registry key {key!r} points at {fn.__name__}(), "
                            "which is not defined at module level")

    plotters = [d for d in defs if d.startswith(("fig_", "map_"))]
    for d in sorted(set(plotters) - named):
        problems.append(f"{d}() builds output but is not in OUTPUTS, so --all "
                        "will never run it")

    # Inputs live outside the repo; a missing folder should say so plainly
    # rather than surface as a stack trace inside one figure.
    for path, what in ((V.GEO, "geo-data"), (V.NISR, "NISR public-use data")):
        if not path.exists():
            problems.append(f"{what} not found at {path}")

    if problems:
        print("[check] FAILED")
        for p_ in problems:
            print(f"  ! {p_}")
        return 1
    print(f"[check] ok — {len(defs)} functions, {len(OUTPUTS)} registered "
          f"outputs, no duplicates")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--all", action="store_true")
    p.add_argument("--only", nargs="+", choices=list(OUTPUTS))
    p.add_argument("--group", nargs="+",
                   choices=sorted({g for _, g in OUTPUTS.values()}))
    p.add_argument("--list", action="store_true")
    p.add_argument("--check", action="store_true",
                   help="verify script integrity (duplicate defs, registry) and exit")
    a = p.parse_args(argv)

    if a.check:
        return selfcheck()

    if a.list:
        for g in sorted({g for _, g in OUTPUTS.values()}):
            print(f"\n{g}:")
            for k, (_f, gg) in OUTPUTS.items():
                if gg == g:
                    print(f"    {k}")
        return 0

    if a.only:
        todo = a.only
    elif a.group:
        todo = [k for k, (_f, g) in OUTPUTS.items() if g in a.group]
    elif a.all:
        todo = list(OUTPUTS)
    else:
        p.print_help()
        return 1

    fails = 0
    for k in todo:
        fn = OUTPUTS[k][0]
        print(f"[figures] {k}", flush=True)
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - one bad figure must not stop the rest
            fails += 1
            print(f"  ! {type(exc).__name__}: {str(exc)[:110]}", flush=True)
    print(f"[figures] done ({len(todo) - fails}/{len(todo)} built)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
