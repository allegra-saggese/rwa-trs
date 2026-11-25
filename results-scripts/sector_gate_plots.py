"""
sector_gate_plots.py -- sector descriptives ordered by distance to the nearest park gate (AER style, one figure per file).

Sample: the 381 sectors outside Kigali City (all of them; no distance cut-off), Census 2002, 2012, 2022.

  Distance to gate   great-circle km from the sector centroid (model_sector_cross.csv lon, lat) to the nearest of the four
                     park entrances in use in 2005: Kinigi (Volcanoes), Gisakura and Kitabi (Nyungwe), Akagera South Gate
                     (helpers/treatment_groups.py::GATE_XY, from OpenStreetMap). Gishwati-Mukura has no gate.
  Touching a gate    the 12 sectors in treatment_groups.csv group Gates (contain a gate, 4) or Gates+ (next to one, 8).
  Worker shares      farm / (farm + non-farm) and services / (farm + non-farm), % of workers with a stated industry
                     (census_sector_work_per_adult.csv). Farm = agriculture, forestry and fishing. In 2022 farming counts as
                     work only if mainly for the market, so the 2022 farm share is not comparable with earlier waves.

Figures (python results-scripts/sector_gate_plots.py; files in output/figures/sector-gate/)
  ranked_{farm,services}_{dot,bar}_{2002,2012,2022}.pdf   sectors ordered along the x-axis by distance to the nearest gate,
                     share of workers on the y-axis; gate-touching sectors are dark diamonds / dark bars.
  scatter_land_density_{2002,2012,2022}.pdf   land area (km2) against population density (residents per km2), log scales,
                     one point per sector; gate-touching sectors are filled diamonds, other park-adjacent sectors open triangles.
"""
import sys
import types
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "helpers"))
import paths as P  # noqa: E402

sys.modules.setdefault("adjustText", types.SimpleNamespace(adjust_text=lambda *a, **k: None))  # label placement only
import treatment_groups as TG  # noqa: E402  (GATE_XY)

KIGALI = {11, 12, 13}
WAVES = (2002, 2012, 2022)
OUTDIR = P.FIGS / "sector-gate"
DARK, LIGHT, MID = "#111111", "#C8C8C8", "#6E6E6E"
plt.rcParams.update({"font.family": "sans-serif", "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"], "font.size": 10,
                     "axes.labelsize": 10, "xtick.labelsize": 9, "ytick.labelsize": 9, "legend.fontsize": 9, "pdf.fonttype": 42,
                     "axes.spines.top": False, "axes.spines.right": False, "axes.linewidth": 0.8})


def hav(lon1, lat1, lon2, lat2):
    r = np.radians
    a = np.sin(r(lat2 - lat1) / 2) ** 2 + np.cos(r(lat1)) * np.cos(r(lat2)) * np.sin(r(lon2 - lon1) / 2) ** 2
    return 6371 * 2 * np.arcsin(np.sqrt(a))


def load() -> pd.DataFrame:
    c = pd.read_csv(P.HARMONIZED / "model_sector_cross.csv")[["sid", "district_id", "sector", "lon", "lat", "unit_km2", "border"]]
    c = c[~c.district_id.isin(KIGALI)].copy()
    D = np.column_stack([hav(c.lon, c.lat, *xy) for xy in TG.GATE_XY.values()])
    c["km_gate"] = D.min(axis=1)
    g = pd.read_csv(P.HARM_PANELS / "treatment_groups.csv")[["sid", "group"]]
    c = c.merge(g, on="sid", how="left")
    c["gate"] = c.group.isin(["Gates", "Gates+"]).astype(int)
    w = pd.read_csv(P.HARMONIZED / "census_sector_work_per_adult.csv")[["sid", "wave", "nonfarm", "services", "farm"]]
    pop = pd.read_csv(P.HARM_PANELS / "sector_pop_total.csv")
    d = c.merge(w, on="sid").merge(pop, on=["sid", "wave"])
    workers = d.farm + d.nonfarm
    d["farm_sh"], d["services_sh"] = 100 * d.farm / workers, 100 * d.services / workers
    d["density"] = d.pop_total / d.unit_km2
    assert d.sid.nunique() == 381 and d.gate.groupby(d.wave).sum().eq(12).all()
    return d


def save(fig, name):
    OUTDIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTDIR / name, bbox_inches="tight")
    plt.close(fig)


def ranked(d, wave, col, ylabel, kind):
    x = d[d.wave == wave].sort_values("km_gate").reset_index(drop=True)
    n, pos = len(x), np.arange(len(x))
    fig, ax = plt.subplots(figsize=(6.5, 3.4))
    touch = x.gate.values == 1
    if kind == "bar":
        ax.bar(pos[~touch], x[col][~touch], width=1.0, color=LIGHT, linewidth=0, label="Other sectors")
        ax.bar(pos[touch], x[col][touch], width=1.0, color=DARK, linewidth=0, label="Sectors touching a park gate")
    else:
        ax.scatter(pos[~touch], x[col][~touch], s=9, facecolor="none", edgecolor=MID, linewidth=0.6, label="Other sectors")
        ax.scatter(pos[touch], x[col][touch], s=34, marker="D", color=DARK, linewidth=0, label="Sectors touching a park gate", zorder=3)
    ticks = [0, n // 5, 2 * n // 5, 3 * n // 5, 4 * n // 5, n - 1]
    ax.set_xticks(ticks)
    ax.set_xticklabels([f"{x.km_gate[i]:.0f}" for i in ticks])
    ax.set_xlim(-1, n)
    ax.set_xlabel(f"Distance to nearest park gate, km (sectors ranked from nearest to farthest, n = {n})")
    ax.set_ylabel(ylabel)
    ax.set_ylim(0, 100 if kind == "bar" or col == "farm_sh" else None)
    ax.legend(frameon=False, loc="best")
    return fig


def scatter(d, wave):
    x = d[d.wave == wave]
    fig, ax = plt.subplots(figsize=(5.2, 4.2))
    o = x[(x.gate == 0) & (x.border == 0)]; b = x[(x.gate == 0) & (x.border == 1)]; g = x[x.gate == 1]
    ax.scatter(o.unit_km2, o.density, s=11, color=LIGHT, edgecolor=MID, linewidth=0.3, label=f"Other sectors ({len(o)})")
    ax.scatter(b.unit_km2, b.density, s=26, marker="^", facecolor="none", edgecolor=DARK, linewidth=0.8, label=f"Other park-adjacent sectors ({len(b)})")
    ax.scatter(g.unit_km2, g.density, s=40, marker="D", color=DARK, linewidth=0, label=f"Sectors touching a park gate ({len(g)})", zorder=3)
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlabel("Land area of the sector (km$^2$, log scale)")
    ax.set_ylabel("Population density (residents per km$^2$, log scale)")
    ax.legend(frameon=False, loc="best")
    return fig


def main() -> int:
    d = load()
    for w in WAVES:
        for col, lab, nm in (("farm_sh", "Workers in agriculture, forestry and fishing (%)", "farm"),
                             ("services_sh", "Workers in services (%)", "services")):
            for kind in ("dot", "bar"):
                save(ranked(d, w, col, lab, kind), f"ranked_{nm}_{kind}_{w}.pdf")
        save(scatter(d, w), f"scatter_land_density_{w}.pdf")
    print(f"[gate-plots] 15 figures -> {OUTDIR}")
    print(d[d.wave == 2022].groupby("gate")[["km_gate", "farm_sh", "services_sh", "density", "unit_km2"]].median().round(1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
