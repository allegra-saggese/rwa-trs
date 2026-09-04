"""
summary.py — descriptive tables, figures, and graphs.

Reads only from data/processed/ (built by extract.py) and writes to
output/tables/ and output/figures/. Computes no new analysis variables: if a
figure needs a variable that does not exist, add it in extract.py so every
output uses the same definition.

Usage
-----
    python summary.py --all
    python summary.py --only rainfall_climatology drought_frequency
    python summary.py --all --format pdf
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
PROC = ROOT / "data" / "processed"
FIGS = ROOT / "output" / "figures"
TABLES = ROOT / "output" / "tables"

# Publication defaults. Serif to sit comfortably in a LaTeX paper; restrained
# grid; no chartjunk.
mpl.rcParams.update({
    "figure.dpi": 150,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "font.family": "serif",
    "font.size": 9,
    "axes.titlesize": 10,
    "axes.labelsize": 9,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "grid.linewidth": 0.5,
    "legend.frameon": False,
})

PROVINCE_COLORS = {
    "Kigali City": "#1b4965", "North": "#5fa8d3", "South": "#c98b3a",
    "East": "#8b5a3c", "West": "#4a7c59",
}

FMT = "png"  # overridden by --format


def _log(msg: str) -> None:
    print(f"[summary] {msg}", flush=True)


def save_fig(fig, name: str) -> None:
    FIGS.mkdir(parents=True, exist_ok=True)
    path = FIGS / f"{name}.{FMT}"
    fig.savefig(path)
    plt.close(fig)
    _log(f"  -> figures/{path.name}")


def save_table(df: pd.DataFrame, name: str, float_fmt: str = "%.2f") -> None:
    """Write each table twice: CSV to read, LaTeX to paste into the paper."""
    TABLES.mkdir(parents=True, exist_ok=True)
    df.to_csv(TABLES / f"{name}.csv", index=False)
    # LaTeX export needs jinja2; if it is absent the CSV is still written rather
    # than losing the whole table to a formatting dependency.
    try:
        (TABLES / f"{name}.tex").write_text(
            df.to_latex(index=False, float_format=lambda v: float_fmt % v, escape=True)
        )
        _log(f"  -> tables/{name}.csv + .tex ({len(df)} rows)")
    except ImportError:
        _log(f"  -> tables/{name}.csv ({len(df)} rows; .tex skipped, pip install jinja2)")


def _require(fname: str) -> pd.DataFrame | None:
    fp = PROC / fname
    if not fp.exists():
        _log(f"  ! {fname} not found - run extract.py first; skipping")
        return None
    return pd.read_csv(fp)


# --------------------------------------------------------------------------
# Tables
# --------------------------------------------------------------------------

def table_district_summary() -> None:
    """District-level rainfall summary: level, variability, drought frequency."""
    panel = _require("district_panel.csv")
    if panel is None:
        return

    t = (panel.groupby(["province", "district"], as_index=False)
         .agg(years=("year", "nunique"),
              rain_mean=("rain_mm", "mean"),
              rain_sd=("rain_mm", "std"),
              rain_min=("rain_mm", "min"),
              rain_max=("rain_mm", "max"),
              drought_yrs=("drought", "sum"),
              area_km2=("area_km2", "first")))
    t["rain_cv"] = t["rain_sd"] / t["rain_mean"]           # unitless variability
    t["drought_rate"] = t["drought_yrs"] / t["years"]
    t = t.sort_values(["province", "district"])
    save_table(t, "district_summary")


def table_balance_by_province() -> None:
    """Province means with an F-test for equality across provinces.

    Reported because the west-east rainfall gradient is the dominant source of
    cross-sectional variation, and any specification using cross-district
    comparisons has to reckon with it.
    """
    panel = _require("district_panel.csv")
    if panel is None:
        return

    rows = []
    for var in ["rain_mm", "rain_sd", "drought", "area_km2"]:
        if var not in panel.columns:
            continue
        by_prov = panel.groupby("province")[var].mean()
        groups = [g[var].dropna().values for _, g in panel.groupby("province")]
        groups = [g for g in groups if len(g) > 1]

        f_stat = p_val = np.nan
        if len(groups) > 1:
            from scipy import stats
            f_stat, p_val = stats.f_oneway(*groups)

        rows.append({"variable": var, **by_prov.round(2).to_dict(),
                     "F": f_stat, "p": p_val})

    save_table(pd.DataFrame(rows), "balance_by_province", float_fmt="%.3f")


def table_wdi_trends() -> None:
    """National indicators at ten-year marks, for context in the paper's intro."""
    wdi = _require("wdi.csv")
    if wdi is None:
        return
    marks = [y for y in [1995, 2000, 2005, 2010, 2015, 2020, 2023] if y in set(wdi.year)]
    save_table(wdi[wdi.year.isin(marks)].reset_index(drop=True), "wdi_trends")


# --------------------------------------------------------------------------
# Figures
# --------------------------------------------------------------------------

def fig_rainfall_climatology() -> None:
    """Mean monthly rainfall by province — shows Rwanda's bimodal seasons.

    Rwanda has two rainy seasons: the long rains (Feb-May) and the short rains
    (Sep-Dec), split by a dry June-August. Any agricultural-season variable has
    to respect this; a calendar-year aggregate cuts the short rains in half.
    """
    m = _require("rainfall_monthly.csv")
    if m is None:
        return

    districts = pd.read_csv(PROC / "district_panel.csv")[["district_id", "province"]].drop_duplicates()
    m = m.merge(districts, on="district_id", how="left")
    clim = m.groupby(["province", "month"], as_index=False)["rain_mm"].mean()

    fig, ax = plt.subplots(figsize=(6.5, 3.6))
    for prov, g in clim.groupby("province"):
        ax.plot(g["month"], g["rain_mm"], marker="o", ms=3, lw=1.4,
                label=prov, color=PROVINCE_COLORS.get(prov))

    # Shade the long dry season. The label sits inside the trough rather than
    # at the top of the axes, where it collided with the legend.
    ax.axvspan(6, 8, color="0.85", alpha=0.5, zorder=0)
    ax.text(7, ax.get_ylim()[1] * 0.30, "dry\nseason", ha="center", va="center",
            fontsize=7.5, color="0.45")

    ax.set_xticks(range(1, 13))
    ax.set_xticklabels(list("JFMAMJJASOND"))
    ax.set_xlabel("Month")
    ax.set_ylabel("Mean rainfall (mm)")
    ax.set_title("Monthly rainfall climatology by province, CHIRPS")
    # Below the axes: the two rainfall peaks leave no clear space inside them.
    ax.legend(ncol=5, fontsize=7.5, loc="upper center",
              bbox_to_anchor=(0.5, -0.18))
    save_fig(fig, "rainfall_climatology")


def fig_rainfall_gradient() -> None:
    """Districts ranked by mean annual rainfall, coloured by province."""
    panel = _require("district_panel.csv")
    if panel is None:
        return

    d = (panel.groupby(["district", "province"], as_index=False)
         .agg(rain=("rain_mm", "mean"), sd=("rain_mm", "std"))
         .sort_values("rain"))

    fig, ax = plt.subplots(figsize=(5.5, 6.5))
    y = np.arange(len(d))
    ax.barh(y, d["rain"], xerr=d["sd"].fillna(0),
            color=[PROVINCE_COLORS.get(p, "0.5") for p in d["province"]],
            error_kw=dict(lw=0.7, ecolor="0.35"), height=0.75)
    ax.set_yticks(y)
    ax.set_yticklabels(d["district"], fontsize=7.5)
    ax.set_xlabel("Mean annual rainfall (mm), bars show SD across years")
    ax.set_title("Rainfall gradient across districts")
    ax.grid(axis="y", visible=False)

    handles = [mpl.patches.Patch(color=c, label=p) for p, c in PROVINCE_COLORS.items()
               if p in set(d["province"])]
    ax.legend(handles=handles, fontsize=7.5, loc="lower right")
    save_fig(fig, "rainfall_gradient")


def fig_rainfall_timeseries() -> None:
    """National annual rainfall with each district as a faint line behind it."""
    panel = _require("district_panel.csv")
    if panel is None:
        return

    fig, ax = plt.subplots(figsize=(6.5, 3.6))
    for _, g in panel.groupby("district_id"):
        ax.plot(g["year"], g["rain_mm"], color="0.7", lw=0.5, alpha=0.6, zorder=1)

    nat = panel.groupby("year", as_index=False)["rain_mm"].mean()
    ax.plot(nat["year"], nat["rain_mm"], color="#1b4965", lw=2, zorder=3,
            label="National mean")
    ax.axhline(nat["rain_mm"].mean(), color="#c1121f", ls="--", lw=1, zorder=2,
               label="Period mean")

    ax.set_xlabel("Year")
    ax.set_ylabel("Annual rainfall (mm)")
    ax.set_title("Annual rainfall, all districts")
    ax.legend(fontsize=7.5)
    save_fig(fig, "rainfall_timeseries")


def fig_drought_frequency() -> None:
    """Heatmap of district-year rainfall z-scores.

    Reads as a shock-exposure matrix: rows are districts, columns years, red is
    a dry anomaly. Makes clear whether droughts are national or idiosyncratic —
    which determines whether district fixed effects plus year fixed effects
    leave any usable variation.
    """
    panel = _require("district_panel.csv")
    if panel is None:
        return
    if panel["year"].nunique() < 5:
        _log("  ! fewer than 5 years; z-scores unstable, skipping heatmap")
        return

    order = (panel.groupby(["district", "province"])["rain_mm"].mean()
             .reset_index().sort_values(["province", "rain_mm"]))
    wide = (panel.pivot_table(index="district", columns="year", values="rain_z")
            .reindex(order["district"]))

    fig, ax = plt.subplots(figsize=(max(6.5, 0.22 * wide.shape[1] + 3), 6.5))
    vmax = float(np.nanmax(np.abs(wide.values)))
    im = ax.imshow(wide.values, aspect="auto", cmap="RdBu",
                   vmin=-vmax, vmax=vmax, interpolation="nearest")

    ax.set_yticks(range(len(wide)))
    ax.set_yticklabels(wide.index, fontsize=6.5)
    step = max(1, wide.shape[1] // 20)
    ax.set_xticks(range(0, wide.shape[1], step))
    ax.set_xticklabels(wide.columns[::step], fontsize=7, rotation=90)
    ax.set_title("Rainfall anomalies by district-year (SD from district mean)")
    ax.grid(False)

    cb = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cb.set_label("z-score", fontsize=8)
    cb.ax.tick_params(labelsize=7)
    save_fig(fig, "drought_frequency")


def fig_wdi_context() -> None:
    """Small-multiple panel of national indicators over time."""
    wdi = _require("wdi.csv")
    if wdi is None:
        return

    cols = [c for c in wdi.columns if c != "year" and wdi[c].notna().sum() > 3]
    if not cols:
        return

    ncol = 3
    nrow = int(np.ceil(len(cols) / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(2.6 * ncol, 2.1 * nrow), squeeze=False)

    for ax, col in zip(axes.flat, cols):
        s = wdi[["year", col]].dropna()
        ax.plot(s["year"], s[col], color="#1b4965", lw=1.4)
        ax.set_title(col.replace("_", " "), fontsize=8)
        ax.tick_params(labelsize=7)
    for ax in axes.flat[len(cols):]:
        ax.axis("off")

    fig.suptitle("Rwanda national indicators (World Bank WDI)", fontsize=10)
    fig.tight_layout()
    save_fig(fig, "wdi_context")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

OUTPUTS = {
    "district_summary": table_district_summary,
    "balance_by_province": table_balance_by_province,
    "wdi_trends": table_wdi_trends,
    "rainfall_climatology": fig_rainfall_climatology,
    "rainfall_gradient": fig_rainfall_gradient,
    "rainfall_timeseries": fig_rainfall_timeseries,
    "drought_frequency": fig_drought_frequency,
    "wdi_context": fig_wdi_context,
}


def main(argv=None) -> int:
    global FMT
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--all", action="store_true", help="produce every output")
    p.add_argument("--only", nargs="+", choices=list(OUTPUTS), help="a subset")
    p.add_argument("--format", default="png", choices=["png", "pdf", "svg"])
    args = p.parse_args(argv)

    if not args.all and not args.only:
        p.print_help()
        return 1

    FMT = args.format
    for name in (list(OUTPUTS) if args.all else args.only):
        _log(name)
        OUTPUTS[name]()

    _log("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
