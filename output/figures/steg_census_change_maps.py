"""
steg_census_change_maps.py -- labour reallocation by sector, 2002-2022, for the STEG appendix.

    python steg_census_change_maps.py
    output/figures/steg_census_change_agriculture.pdf
    output/figures/steg_census_change_manufacturing.pdf
    output/figures/steg_census_change_services.pdf

MEASURE (Matteo, 2026-09-15). Each sector's share of workers aged 20-64 in each group, from the 2002, 2012
and 2022 Population and Housing Censuses, and the average of the two decade changes,
((2012 - 2002) + (2022 - 2012)) / 2, in percentage points per decade. The three groups are mutually
exclusive and add to 100% of workers with a recorded industry:

    agriculture     agriculture, forestry and fishing, plus mining (ISIC A-B)
    manufacturing   manufacturing, utilities and construction (C-F)
    services        all services (G-U)

Counts come from Analysis/census_sector_jobs_panel.csv (build_jobs_panel.py), where 2002 sits on the
2022 sector boundaries. The 2022 census counts farming as work only if it is mainly for market, so
subsistence farmers drop out of the workforce; 2022 agriculture uses that panel's reconstructed point
estimate (adults with no recorded industry in crop-growing households, less the 14.1-point false-positive
rate of the same rule in 2012). Without it services' national share would jump from 17% to 33% in 2012-2022
partly because farmers disappear from the count; with it the path is 9.5, 16.8, 23.6%.

COLOURS. Decreases red, increases green; on each side the split between strong and weak is the median
change of the sectors on that side. Parks are dark green with white hatching so they cannot be read as a
strong increase. Sector boundaries, parks and lakes are drawn as in steg_ec_maps.py.
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd, geopandas as gpd, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from shapely.geometry import box
from shapely.validation import make_valid
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import paths as P
import steg_ec_maps as M

PANEL = P.NISR / "Analysis" / "census_sector_jobs_panel.csv"
GROUPS = {"agriculture": (["n_AG_pt", "n_MIN"], "Agriculture"),
          "manufacturing": (["n_MAN"], "Manufacturing, utilities\n& construction"),
          "services": (["n_TER"], "Services")}
CLASS_COL = ["#b2182b", "#f4a582", "#a6dba0", "#1b7837"]     # strong decrease, weak decrease, weak increase, strong increase
CLASS_NAME = ["Strong decrease", "Weak decrease", "Weak increase", "Strong increase"]


def changes():
    p = pd.read_csv(PANEL)
    tot = p[["n_AG_pt", "n_MIN", "n_MAN", "n_TER"]].sum(axis=1)
    for g, (cols, _) in GROUPS.items():
        p[g] = p[cols].sum(axis=1) / tot * 100
    nat = pd.DataFrame({g: p[cols].sum(axis=1).groupby(p.wave).sum() / tot.groupby(p.wave).sum() * 100
                        for g, (cols, _) in GROUPS.items()})
    w = p.pivot(index="sid", columns="wave", values=list(GROUPS))
    ch = pd.DataFrame({g: ((w[g][2012] - w[g][2002]) + (w[g][2022] - w[g][2012])) / 2 for g in GROUPS})
    assert len(ch) == 416 and ch.notna().all().all()
    return ch, nat


def classify(v):
    neg, pos = v[v < 0], v[v >= 0]
    mn = np.median(neg) if len(neg) else -np.inf
    mp = np.median(pos) if len(pos) else np.inf
    k = np.select([(v < 0) & (v <= mn), v < 0, v <= mp], [0, 1, 2], default=3)
    bounds = [(v[k == i].min(), v[k == i].max()) if (k == i).any() else None for i in range(4)]
    return k, bounds


def main():
    ch, nat = changes()
    print("national share of workers, %:"); print(nat.round(1).to_string())
    s = gpd.read_file(M.SECTORS)
    s["geometry"] = s.geometry.apply(make_valid)
    s["sid"] = s.sector_id.astype(int)
    s = s.to_crs(M.CRS).merge(ch, left_on="sid", right_index=True, how="left")
    assert len(s) == 416 and s[list(GROUPS)].notna().all().all()
    pk = gpd.read_file(M.PARKS)
    pk = pk[pk.designate.astype(str).str.contains("National Park", case=False, na=False)].to_crs(M.CRS)
    lk = gpd.clip(gpd.read_file(M.LAKES).to_crs(M.CRS), box(*s.total_bounds))
    matplotlib.rcParams["hatch.linewidth"] = .6

    for g, (_, label) in GROUPS.items():
        v = s[g].to_numpy()
        k, bounds = classify(v)
        print(f"{g}: {int((v < 0).sum())} sectors down, {int((v >= 0).sum())} up | median {np.median(v):+.1f} pp/decade | "
              f"range {v.min():+.1f} to {v.max():+.1f} | class sizes {[int((k == i).sum()) for i in range(4)]}")
        fig, ax = plt.subplots(figsize=(7.5, 7))
        s.plot(ax=ax, color=[CLASS_COL[i] for i in k], edgecolor=M.EDGE, linewidth=.25, zorder=1)
        pk.plot(ax=ax, facecolor=M.PARK, edgecolor="white", hatch="////", linewidth=0, zorder=2)
        lk.plot(ax=ax, facecolor=M.WATER, edgecolor=M.WATER_EDGE, linewidth=.3, zorder=3)
        pp = lambda x: f"{x:+.2f}" if abs(x) < .05 else f"{x:+.1f}"
        handles = [Patch(facecolor=CLASS_COL[i], edgecolor=M.EDGE,
                         label=f"{CLASS_NAME[i]}:  {pp(bounds[i][0])} to {pp(bounds[i][1])}  ({int((k == i).sum())})")
                   for i in range(3, -1, -1) if bounds[i] is not None]
        handles += [Patch(facecolor=M.PARK, edgecolor="white", hatch="////", label="National park"),
                    Patch(facecolor=M.WATER, edgecolor=M.WATER_EDGE, label="Lake")]
        ax.legend(handles=handles, title=f"{label}: change in share of\nworkers, points per decade (sectors)",
                  loc="center left", bbox_to_anchor=(1.0, .3), frameon=False, fontsize=8.5, title_fontsize=9,
                  alignment="left")
        ax.set_axis_off()
        out = P.FIGS / f"steg_census_change_{g}.pdf"
        fig.savefig(out, bbox_inches="tight"); plt.close(fig)
        print(f"written {out}")


if __name__ == "__main__":
    main()
