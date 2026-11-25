"""
sector_descriptive_plots.py -- descriptive scatterplots, histograms and group plots for the 381 sectors outside Kigali City
(AER style, one figure per file: output/figures/sector-descriptive/, and docs/sector_descriptive_figures.tex with --tex).

Three categories of sector throughout (counts in every legend):
  Park-adjacent   the sector borders a national park or touches a park gate (64 sectors; 62 border a park, 2 more touch a gate)
  Ring            touches a park-adjacent sector, does not border a park or touch a gate (80)
  Interior        every other sector (237)

Variables (Census sector x wave unless stated)
  Services share        services / (farm + non-farm) workers, %, recorded workers (census_sector_work_per_adult.csv)
  Agriculture share     agriculture, forestry and fishing workers aged 20-64 per 100 adults aged 20-64, including estimated
                        subsistence farmers in 2022 (census_sector_jobs_panel.csv, n_AG_pt; the 2022 Census records farming as work
                        only if mainly for the market, so the point estimate adds farm-household adults with no recorded industry,
                        less a false-positive rate measured in 2012: micro-analysis/census/build_jobs_panel.py)
  Subsistence share     (n_AG_pt - n_AG) / adults 20-64, % : the 2022 add-back only (zero by construction in 2002, 2012, when
                        subsistence farming is recorded inside agriculture)
  Non-farm share        100 - farm share of recorded workers
  Service-and-sales occupation share   ISCO major group 5 among adults 16+ with a stated occupation (data-build/sector_work_type.py)
  Household size        mean persons per household (household-weighted), same script
  Schooling             mean years of schooling, secondary completion (census_sector_education_panel.csv)
  Housing quality       mean of four household shares: improved floor, improved water, private toilet, brick wall
                        (census_sector_housing_panel.csv)
  In-migration share    share of residents whose previous residence was another district or abroad (2012, 2022; model_sector_panel.csv)
  Urban share           share of the sector's population in urban areas (sector_urban_share.csv)
  Density               residents per km2 of sector area (log scale)
  Other                 distances to park, gate, road and Kigali; elevation, slope, rainfall; GLAD land cover; Hansen tree cover and
                        loss; Establishment Census 2011 accommodation and food; OSM accommodation; RDB visits; district labour
                        status, agricultural output and land rent (see each caption).

Usage: python results-scripts/sector_descriptive_plots.py [--tex]
"""
import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import FixedLocator, NullFormatter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "helpers"))
sys.path.insert(0, str(ROOT / "micro-analysis"))
sys.path.insert(0, str(ROOT / "results-scripts"))
import paths as P  # noqa: E402
import sector_gate_plots as S  # noqa: E402  (load, style)
import census_park_regressions as C  # noqa: E402

OUT = P.FIGS / "sector-descriptive"
H, A, GEO = P.HARMONIZED, P.HARM_PANELS, P.GEO
DARK, MID, LIGHT = S.DARK, S.MID, S.LIGHT
CATS = [("park", "Park-adjacent"), ("ring", "Ring"), ("interior", "Interior")]
STY = {"park": dict(marker="^", s=26, fc="none", ec=DARK, ls="-", lc=DARK),
       "ring": dict(marker="s", s=14, fc="#8F8F8F", ec="#8F8F8F", ls="-.", lc="#4F4F4F"),
       "interior": dict(marker="o", s=11, fc="none", ec=MID, ls=":", lc=MID)}
CAP = {}


def save(fig, name, caption):
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / f"{name}.pdf", bbox_inches="tight")
    plt.close(fig)
    CAP[name] = caption


# ---------------------------------------------------------------------------- data
def build() -> pd.DataFrame:
    d = S.load()
    d["cat"] = np.where((d.border == 1) | (d.gate == 1), "park", np.where(d.zone == "ring", "ring", "interior"))
    d["urban"] = 100 * d.merge(pd.read_csv(A / "sector_urban_share.csv"), on=["sid", "wave"], how="left").urban_sh.values
    e = pd.read_csv(H / "census_sector_education_panel.csv")[["sid", "wave", "years", "secondary", "literacy"]]
    h = pd.read_csv(H / "census_sector_housing_panel.csv")[["sid", "wave", "improved_floor", "improved_water", "private_toilet", "wall_brick"]]
    h["housing"] = 100 * h[["improved_floor", "improved_water", "private_toilet", "wall_brick"]].mean(axis=1)
    m = pd.read_csv(H / "model_sector_panel.csv")[["sid", "wave", "inmig_share"]]
    j = pd.read_csv(H / "census_sector_jobs_panel.csv", usecols=["sid", "wave", "adults", "n_AG", "n_AG_pt"]).rename(columns={"adults": "adults2064"})
    w = pd.read_csv(A / "sector_work_type.csv")
    lj = pd.read_csv(A / "sector_land_jobs_panel.csv", usecols=["sid", "wave"] + [f"n_{c}" for c in "GHIJKLMNOPQRSTU"])
    for t in (e, h, m, j, w, lj):
        d = d.merge(t, on=["sid", "wave"], how="left", validate="1:1")
    d["ag"] = 100 * d.n_AG_pt / d.adults2064
    d["subsistence"] = np.where(d.wave == 2022, 100 * (d.n_AG_pt - d.n_AG) / d.adults2064, 0.0)
    d["nonfarm_sh"] = 100 - d.farm_sh
    d["inmig"] = 100 * d.inmig_share
    d["occ_service"] = 100 * d.occ_service_sales / d.occ_total
    x = pd.read_csv(C.SECTORS)[["sid", "dist_to_park_km", "nearest_park", "dist_kigali_km", "osm_accom"]]
    geo = (pd.read_csv(GEO / "raster/sector_terrain.csv")[["sid", "elev_mean", "slope_mean"]]
           .merge(pd.read_csv(GEO / "raster/sector_rainfall.csv")[["sid", "rain_mean"]], on="sid")
           .merge(pd.read_csv(GEO / "roads/sector_distances.csv")[["sid", "log_dist_road"]], on="sid"))
    geo["dist_road_km"] = np.exp(geo.log_dist_road)
    d = d.merge(x, on="sid", validate="m:1").merge(geo.drop(columns="log_dist_road"), on="sid", validate="m:1")
    return d


def counts(d):
    s = d.drop_duplicates("sid").cat.value_counts()
    return {k: int(s.get(k, 0)) for k, _ in CATS}


# ---------------------------------------------------------------------------- generic plots
def scatter(d, x, y, xl, yl, name, cap, wave=2022, xlog=False, fit=True, ylog=False):
    w = d[d.wave == wave].dropna(subset=[x, y]) if wave else d.drop_duplicates("sid").dropna(subset=[x, y])
    fig, ax = plt.subplots(figsize=(5.4, 4.1))
    for k, lab in CATS[::-1]:
        z = w[w.cat == k]
        st = STY[k]
        ax.scatter(z[x], z[y], s=st["s"], marker=st["marker"], facecolor=st["fc"], edgecolor=st["ec"], linewidth=0.7, label=f"{lab} ({len(z)})", zorder=3 if k == "park" else 2)
    xv = np.log(w[x]) if xlog else w[x]
    yv = np.log(w[y]) if ylog else w[y]
    r = np.corrcoef(xv, yv)[0, 1]
    if fit:
        b = np.polyfit(xv, yv, 1)
        g = np.linspace(xv.min(), xv.max(), 50)
        ax.plot(np.exp(g) if xlog else g, np.exp(np.polyval(b, g)) if ylog else np.polyval(b, g), color="black", linewidth=0.9, linestyle="--", label="Linear fit, all sectors", zorder=4)
    if xlog:
        ax.set_xscale("log")
    if ylog:
        ax.set_yscale("log")
    ax.set_xlabel(xl); ax.set_ylabel(yl)
    ax.text(0.98, 0.03, f"correlation {r:.2f}, n = {len(w)}", transform=ax.transAxes, ha="right", va="bottom", fontsize=8)
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=2, fontsize=8)
    save(fig, name, cap + (f" Census {wave}." if wave else "") + " Markers: park-adjacent (open triangles), ring (grey squares), interior (open circles); dashed line is a linear fit over all sectors.")


def hist(d, col, xl, name, cap, wave=2022, bins=22, rng=None):
    w = d[d.wave == wave] if wave else d.drop_duplicates("sid")
    w = w.dropna(subset=[col])
    lo, hi = (w[col].min(), w[col].max()) if rng is None else rng
    edges = np.linspace(lo, hi, bins + 1)
    fig, ax = plt.subplots(figsize=(5.4, 3.8))
    for k, lab in CATS:
        z = w[w.cat == k][col].clip(lo, hi)
        n, _ = np.histogram(z, bins=edges)
        ax.stairs(100 * n / len(z), edges, color=STY[k]["lc"], linestyle=STY[k]["ls"], linewidth=1.5, label=f"{lab} ({len(z)}), mean {z.mean():.1f}")
    ax.set_xlabel(xl); ax.set_ylabel("Share of sectors in the category in each bin (%)")
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=1, fontsize=8, handlelength=3.5)
    save(fig, name, cap + (f" Census {wave}." if wave else "") + " Each line is the distribution of one category of sector, as a percentage of the sectors in that category, so categories of different size are comparable. Line styles: park-adjacent solid, ring dash-dotted, interior dotted.")


def group_lines(d, col, yl, name, cap, waves=None):
    fig, ax = plt.subplots(figsize=(5.3, 3.8))
    xs = waves or sorted(d.wave.unique())
    for k, lab in CATS:
        z = d[(d.cat == k) & d.wave.isin(xs)].groupby("wave")[col].agg(["mean", "std", "count"])
        ax.errorbar(z.index, z["mean"], yerr=1.96 * z["std"] / np.sqrt(z["count"]), fmt="o", linestyle=STY[k]["ls"], color=STY[k]["lc"], markersize=5,
                    linewidth=1.4, capsize=2, elinewidth=0.7, label=f"{lab} ({int(z['count'].iloc[0])})")
    ax.set_xticks(xs); ax.set_xticklabels([str(int(t)) for t in xs]); ax.set_xlabel("Year"); ax.set_ylabel(yl)
    ax.legend(frameon=False, loc="best", fontsize=8, handlelength=3.5)
    save(fig, name, cap + " Mean over sectors in each category; bars are 95% intervals (unclustered). Line styles: park-adjacent solid, ring dash-dotted, interior dotted.")


def stacked(parts, labels, xl, name, cap, shades):
    """parts: DataFrame rows = categories, columns = components (percent summing to 100)."""
    fig, ax = plt.subplots(figsize=(5.6, 4.0))
    bottom = np.zeros(len(parts))
    for c, lab, sh in zip(parts.columns, labels, shades):
        ax.bar(range(len(parts)), parts[c], bottom=bottom, color=sh, edgecolor="white", linewidth=0.6, label=lab, width=0.62)
        bottom += parts[c].values
    ax.set_xticks(range(len(parts))); ax.set_xticklabels(parts.index)
    ax.set_ylabel(xl); ax.set_ylim(0, 100)
    ax.legend(frameon=False, loc="upper left", bbox_to_anchor=(1.0, 1.0), fontsize=8)
    save(fig, name, cap)


# ---------------------------------------------------------------------------- figures
def distributions(d):
    for t in (2002, 2012, 2022):
        hist(d, "services_sh", "Workers in services (% of recorded workers)", f"hist_services_share_{t}", "Distribution of the services share of workers across sectors.", wave=t, rng=(0, 60))
        hist(d, "ag", "Agriculture workers per 100 adults aged 20-64 (including estimated subsistence in 2022)", f"hist_agriculture_share_{t}", "Distribution of the agriculture share of adults across sectors.", wave=t, rng=(0, 100))
    for t in (2012, 2022):
        hist(d, "occ_service", "Service and sales occupations (% of workers with a stated occupation)", f"hist_occ_service_sales_{t}", "Distribution of the service-and-sales occupation share (ISCO major group 5).", wave=t, rng=(0, 30))
    for t in (2002, 2022):
        hist(d, "years", "Mean years of schooling", f"hist_schooling_years_{t}", "Distribution of mean years of schooling.", wave=t)
    hist(d, "housing", "Housing quality index (0-100)", "hist_housing_2022", "Distribution of the housing-quality index (mean of the household shares with an improved floor, improved water, a private toilet and brick walls).", wave=2022)
    hist(d, "hh_size", "Mean household size (persons)", "hist_household_size_2022", "Distribution of mean household size.", wave=2022)
    for col, xl, nm in (("elev_mean", "Mean elevation (m)", "elevation"), ("slope_mean", "Mean slope (degrees)", "slope"), ("rain_mean", "Mean annual rainfall (mm)", "rainfall"),
                        ("dist_road_km", "Distance to nearest trunk or primary road (km)", "dist_road"), ("dist_kigali_km", "Distance to Kigali (km)", "dist_kigali"),
                        ("km_gate", "Distance to nearest park gate (km)", "dist_gate")):
        hist(d, col, xl, f"hist_geo_{nm}", "Geography of the three categories of sector (the controls used in the regressions).", wave=None)


def services_breakdown(d):
    groups = [("Trade (G)", ["n_G"]), ("Transport (H)", ["n_H"]), ("Accommodation and food (I)", ["n_I"]), ("Information, finance, real estate, professional (J-N)", [f"n_{c}" for c in "JKLMN"]),
              ("Public administration, education, health (O-Q)", ["n_O", "n_P", "n_Q"]), ("Arts and other personal services (R-U)", [f"n_{c}" for c in "RSTU"])]
    shades = ["#111111", "#4A4A4A", "#7A7A7A", "#A5A5A5", "#CFCFCF", "#EDEDED"]
    for t in (2002, 2012, 2022):
        w = d[d.wave == t]
        tot = w.groupby("cat")[[c for _, cs in groups for c in cs]].sum()
        parts = pd.DataFrame({lab: tot[cs].sum(axis=1) for lab, cs in groups})
        parts = 100 * parts.div(parts.sum(axis=1), axis=0)
        parts.index = [f"{dict(CATS)[k]}\n({counts(d)[k]})" for k in parts.index]
        parts = parts.loc[[f"{dict(CATS)[k]}\n({counts(d)[k]})" for k, _ in CATS]]
        stacked(parts, [g[0] for g in groups], "% of services workers", f"services_breakdown_{t}",
                f"Composition of services employment (ISIC Rev. 4 sections G-U; 2002 mapped from Rev. 3) by category of sector, Census {t}: counts summed over the sectors in each category.", shades)


def occupation_mix(d):
    comp = [("skilled_ag", "Skilled agriculture"), ("elementary", "Elementary"), ("craft", "Craft trades"), ("service_sales", "Service and sales"), ("operators", "Machine operators"),
            ("technicians", "Technicians"), ("professionals", "Professionals"), ("clerical", "Clerical"), ("managers", "Managers")]
    shades = ["#EDEDED", "#CFCFCF", "#A5A5A5", "#111111", "#7A7A7A", "#4A4A4A", "#8F8F8F", "#BDBDBD", "#2E2E2E"]
    for t in (2012, 2022):
        w = d[d.wave == t]
        tot = w.groupby("cat")[[f"occ_{c}" for c, _ in comp]].sum()
        parts = 100 * tot.div(tot.sum(axis=1), axis=0)
        parts.columns = [c for c, _ in comp]
        parts = parts.loc[[k for k, _ in CATS]]
        parts.index = [f"{dict(CATS)[k]}\n({counts(d)[k]})" for k in parts.index]
        stacked(parts, [l for _, l in comp], "% of workers with a stated occupation", f"occupation_mix_{t}",
                f"Occupation (ISCO major group) of workers by category of sector, Census {t}. In 2022 farming counts as work only if mainly for the market, so skilled agriculture is undercounted.", shades)


def scatters(d):
    D, AGL = "Population density (residents per km$^2$, log scale)", "Agriculture workers per 100 adults aged 20-64"
    scatter(d, "density", "services_sh", D, "Workers in services (% of recorded workers)", "scatter_density_services", "Population density against the services share.", xlog=True)
    scatter(d, "density", "ag", D, AGL + " (incl. subsistence)", "scatter_density_agriculture", "Population density against the agriculture share of adults.", xlog=True)
    scatter(d, "density", "urban", D, "Urban share of the sector's population (%)", "scatter_density_urban", "Population density against the urban share.", xlog=True)
    scatter(d, "density", "subsistence", D, "Estimated subsistence farmers per 100 adults aged 20-64", "scatter_density_subsistence", "Population density against estimated subsistence farming (the 2022 add-back).", xlog=True)
    scatter(d, "density", "farm_sh", D, "Farm workers (% of recorded workers)", "scatter_density_farm_recorded", "Population density against the recorded farm share of workers.", xlog=True)
    HH = "Mean household size (persons)"
    scatter(d, "hh_size", "subsistence", HH, "Estimated subsistence farmers per 100 adults", "scatter_hhsize_subsistence", "Household size against estimated subsistence farming.")
    scatter(d, "hh_size", "ag", HH, AGL + " (incl. subsistence)", "scatter_hhsize_agriculture", "Household size against the agriculture share of adults.")
    scatter(d, "hh_size", "services_sh", HH, "Workers in services (% of recorded workers)", "scatter_hhsize_services", "Household size against the services share.")
    scatter(d, "years", "nonfarm_sh", "Mean years of schooling", "Non-farm workers (% of recorded workers)", "scatter_schooling_nonfarm", "Schooling against the non-farm share of workers.")
    scatter(d, "secondary", "nonfarm_sh", "Share of adults with secondary schooling", "Non-farm workers (% of recorded workers)", "scatter_secondary_nonfarm", "Secondary schooling against the non-farm share of workers.")
    scatter(d, "urban", "nonfarm_sh", "Urban share of the sector's population (%)", "Non-farm workers (% of recorded workers)", "scatter_urban_nonfarm", "Urban share against the non-farm share of workers.")
    HQ = "Housing quality index (0-100)"
    scatter(d, "housing", "services_sh", HQ, "Workers in services (% of recorded workers)", "scatter_housing_services", "Housing quality index (mean of the household shares with improved floor, improved water, private toilet and brick walls) against the services share.")
    scatter(d, "dist_to_park_km", "housing", "Distance from the sector to the nearest park boundary (km)", HQ, "scatter_housing_distance_park", "Housing quality index (mean of the household shares with improved floor, improved water, private toilet and brick walls) against distance to the nearest park.")
    scatter(d, "km_gate", "housing", "Distance from sector centroid to the nearest park gate (km)", HQ, "scatter_housing_distance_gate", "Housing quality index (mean of the household shares with improved floor, improved water, private toilet and brick walls) against distance to the nearest park gate.")
    scatter(d, "inmig", "services_sh", "In-migrants (% of residents)", "Workers in services (% of recorded workers)", "scatter_migration_services", "In-migration share against the services share.")
    scatter(d, "inmig", "ag", "In-migrants (% of residents)", AGL + " (incl. subsistence)", "scatter_migration_agriculture", "In-migration share against the agriculture share of adults.")
    scatter(d, "rain_mean", "ag", "Mean annual rainfall (mm)", AGL + " (incl. subsistence)", "scatter_rainfall_agriculture", "Rainfall against the agriculture share of adults.")
    scatter(d, "elev_mean", "services_sh", "Mean elevation (m)", "Workers in services (% of recorded workers)", "scatter_elevation_services", "Elevation against the services share.")
    scatter(d, "occ_service", "services_sh", "Service and sales occupations (% of workers with a stated occupation)", "Workers in services (% of recorded workers)", "scatter_occupation_vs_industry",
            "Two measures of service work: occupation (ISCO group 5) against industry (ISIC G-U).")


def land_forest(d):
    g = pd.read_csv(A / "sector_landcover_glclu.csv").rename(columns={"sector_id": "sid"})
    for c in ("crop", "built", "tree"):
        g[f"{c}_sh"] = 100 * g[f"{c}_out_ha"] / g[[f"{k}_out_ha" for k in ("crop", "built", "tree", "water", "other")]].sum(axis=1)
    cat = d.drop_duplicates("sid")[["sid", "cat", "density", "unit_km2"]]
    g = g.merge(cat, on="sid", how="inner").rename(columns={"year": "wave"})
    for c, lab, nm in (("crop_sh", "Cropland share of usable land (%)", "cropland"), ("built_sh", "Built-up share of usable land (%)", "builtup"), ("tree_sh", "Tree cover share of usable land (%)", "tree")):
        group_lines(g, c, lab, f"land_{nm}_by_category", f"{lab.split(' (')[0]} by category of sector, GLAD land cover 2000-2020 (usable = outside the park).", waves=[2000, 2005, 2010, 2015, 2020])
    ch = g[g.wave == 2020].set_index("sid").built_sh - g[g.wave == 2000].set_index("sid").built_sh
    z = cat.merge(ch.rename("built_change"), left_on="sid", right_index=True).assign(wave=2022)
    hist(z, "built_change", "Change in built-up share of usable land, 2000-2020 (percentage points)", "hist_builtup_change", "Distribution of built-up change.", wave=None, rng=(0, 20))
    # agriculture and land cover
    y = d[d.wave == 2022][["sid", "ag", "cat"]].merge(g[g.wave == 2020][["sid", "crop_sh"]], on="sid").assign(wave=2022)
    scatter(y.assign(), "crop_sh", "ag", "Cropland share of usable land, 2020 (%)", "Agriculture workers per 100 adults (incl. subsistence)", "scatter_cropland_agriculture", "Cropland share against the agriculture share of adults.")
    hs = pd.read_csv(A / "sector_hansen_annual.csv")
    tc = hs.groupby("sid").agg(tc=("treecover2000_ha", "first"), loss=("loss_ha", lambda v: v[hs.loc[v.index, "year"].between(2001, 2020)].sum())).reset_index()
    tc = tc.merge(d.drop_duplicates("sid")[["sid", "cat", "dist_to_park_km", "unit_km2"]], on="sid").assign(wave=2022)
    tc["loss_pct"] = 100 * tc.loss / tc.tc
    tc["tc_pct"] = 100 * tc.tc / (100 * tc.unit_km2)
    scatter(tc[tc.tc >= 50], "dist_to_park_km", "loss_pct", "Distance from the sector to the nearest park boundary (km)", "Tree cover lost 2001-2020 (% of 2000 tree cover)", "scatter_forest_loss_distance_park",
            "Forest loss against distance to the nearest park (Hansen; sectors with at least 50 ha of tree cover in 2000).", wave=None)
    ag22 = d[d.wave == 2022][["sid", "ag"]]
    scatter(tc.merge(ag22, on="sid"), "tc_pct", "ag", "Tree cover in 2000 (% of sector area)", "Agriculture workers per 100 adults (incl. subsistence)", "scatter_treecover_agriculture", "Tree cover in 2000 against the agriculture share of adults.", wave=None)
    # transition matrix
    t = pd.read_csv(A / "glclu_transitions_2000_2020.csv")
    m = t.groupby(["from", "to"]).ha.sum().unstack(fill_value=0)
    keep = [c for c in ("crop", "built", "tree", "water") if c in m.index and c in m.columns]
    m = m.loc[keep, keep]
    m = 100 * m.div(m.sum(axis=1), axis=0)
    fig, ax = plt.subplots(figsize=(4.8, 4.0))
    ax.imshow(m.values, cmap="Greys", vmin=0, vmax=100)
    ax.set_xticks(range(len(keep))); ax.set_xticklabels(keep); ax.set_yticks(range(len(keep))); ax.set_yticklabels(keep)
    for i in range(len(keep)):
        for j in range(len(keep)):
            ax.text(j, i, f"{m.values[i, j]:.1f}", ha="center", va="center", color="white" if m.values[i, j] > 55 else "black", fontsize=9)
    ax.set_xlabel("Land cover in 2020"); ax.set_ylabel("Land cover in 2000")
    for s_ in ax.spines.values():
        s_.set_visible(True)
    save(fig, "land_transitions_2000_2020", "Share of 2000 land in each class (rows) that was in each class in 2020 (columns), %, all sectors in treatment_groups.csv (GLAD land cover).")


def tourism(d):
    ec = pd.read_csv(A / "sector_ec2011_accommodation_food.csv").rename(columns={"ec_sector": "sid"})
    ec["est"] = ec.n_55.fillna(0) + ec.n_56.fillna(0)
    ec["wk"] = ec.wk_55.fillna(0) + ec.wk_56.fillna(0)
    ec["acc"] = ec.n_55.fillna(0)
    z = d.drop_duplicates("sid")[["sid", "km_gate", "cat"]].merge(ec, on="sid", how="left").fillna({"est": 0, "wk": 0, "acc": 0})
    edges = list(range(0, 100, 10))
    z["bin"] = pd.cut(z.km_gate, edges, right=False)
    for col, yl, nm in (("acc", "Accommodation establishments per sector, 2011", "ec_accommodation_by_gate"), ("est", "Accommodation and food establishments per sector, 2011", "ec_accfood_by_gate"),
                        ("wk", "Workers in accommodation and food per sector, 2011", "ec_workers_by_gate")):
        g = z.groupby("bin", observed=True)[col].agg(["mean", "std", "count"])
        mid = np.array([b.left + 5 for b in g.index])
        fig, ax = plt.subplots(figsize=(5.4, 3.6))
        ax.errorbar(mid, g["mean"], yerr=1.96 * g["std"] / np.sqrt(g["count"]), fmt="o", color=DARK, ecolor=MID, capsize=2, elinewidth=0.8, markersize=5)
        ax.set_xlabel("Distance from sector centroid to nearest park gate, km (10-km bins)"); ax.set_ylabel(yl)
        save(fig, nm, "Mean over sectors in 10-km bins of distance to the nearest gate; bars are 95% intervals (unclustered). Establishment Census 2011 (ISIC 55 accommodation, 56 food and beverage); sectors with none count as zero.")
    # OSM accommodation by park
    o = d.drop_duplicates("sid").assign(park=lambda v: np.where((v.border == 1), v.nearest_park.str.replace(" National Park", ""), "Not park-adjacent"))
    b = o.groupby("park").osm_accom.sum().sort_values(ascending=False)
    fig, ax = plt.subplots(figsize=(5.4, 3.6))
    ax.bar(range(len(b)), b.values, color="#6E6E6E", width=0.6)
    ax.set_xticks(range(len(b))); ax.set_xticklabels(b.index, rotation=0, fontsize=8)
    ax.set_ylabel("OpenStreetMap accommodation points")
    save(fig, "osm_accommodation_by_park", "OpenStreetMap accommodation points located in sectors that border each park, and in all other sectors (OSM tourism extract).")
    # visits vs services share, park level
    v = pd.read_excel(H / "rwanda-parks-tourism-rdb.xlsx", sheet_name="visits_by_park")
    v = v[pd.to_numeric(v.year, errors="coerce") == 2019].iloc[0]
    rows = []
    for park, col in (("Volcanoes National Park", "Volcanoes"), ("Akagera National Park", "Akagera"), ("Nyungwe National Park", "Nyungwe")):
        s_ = d[(d.wave == 2022) & (d.border == 1) & (d.nearest_park == park)]
        rows.append((col, v[col] / 1e3, s_.services_sh.mean(), len(s_)))
    fig, ax = plt.subplots(figsize=(5.0, 3.6))
    for nm_, x_, y_, n_ in rows:
        ax.scatter(x_, y_, s=40, color=DARK)
        ax.annotate(f"{nm_} ({n_} sectors)", (x_, y_), textcoords="offset points", xytext=(6, 4), fontsize=8)
    ax.set_xlabel("Park visits in 2019 (thousands)"); ax.set_ylabel("Mean services share of workers in bordering sectors, 2022 (%)")
    ax.set_xlim(left=0)
    save(fig, "visits_vs_services_by_park", "Visits in 2019 (RDB) against the mean 2022 services share of the sectors that border each of the three tourist parks. Three observations: descriptive only.")


def district(d):
    e = pd.read_csv(P.HARM_DISTRICT / "district-park-exposure-border.csv")[["district_id", "district", "n_adjacent_sectors", "adj_share_pop_2022"]]
    lab = pd.read_csv(P.HARM_DISTRICT / "district-labour-status.csv").drop(columns=[c for c in ("district", "n_adjacent_sectors") if c in ()])
    lab = lab[["district_id", "year", "share_wage", "share_self", "share_family"]].merge(e, on="district_id")
    lab["exposed"] = lab.n_adjacent_sectors > 0
    for col, nm, t in (("share_wage", "wage", "Wage employees"), ("share_self", "self", "Self-employed"), ("share_family", "family", "Contributing family workers")):
        fig, ax = plt.subplots(figsize=(5.3, 3.8))
        for flag, ls, colr, name in ((True, "-", DARK, "Districts with a park-adjacent sector"), (False, "--", MID, "Other districts")):
            z = lab[lab.exposed == flag].groupby("year")[col].agg(["mean", "std", "count"])
            ax.errorbar(z.index, 100 * z["mean"], yerr=100 * 1.96 * z["std"] / np.sqrt(z["count"]), fmt="o", linestyle=ls, color=colr, markersize=5, linewidth=1.4, capsize=2, elinewidth=0.7,
                        label=f"{name} ({int(z['count'].iloc[0])})")
        ax.set_xticks(sorted(lab.year.unique())); ax.set_xlabel("Survey year"); ax.set_ylabel(f"{t} (% of workers)")
        ax.legend(frameon=False, loc="best", fontsize=8, handlelength=3.5)
        save(fig, f"district_status_{nm}", f"{t} as a share of workers, mean over districts (Labour Force Survey district labour-status panel, 2017-2025). Bars: 95% intervals. Solid: 14 districts with a park-adjacent sector; dashed: 13 others.")
    ag = pd.read_csv(P.HARM_DISTRICT / "district-ag-productivity.csv")[["district_id", "year", "value_per_ha_dprice", "output_per_worker_dprice"]].merge(e, on="district_id")
    yr = ag.year.max()
    ag = ag[ag.year == yr]
    for col, yl, nm in (("value_per_ha_dprice", "Agricultural output value per hectare (RWF)", "ag_value_per_ha"), ("output_per_worker_dprice", "Agricultural output value per ag worker (RWF)", "ag_output_per_worker")):
        fig, ax = plt.subplots(figsize=(5.2, 3.8))
        x_, y_ = 100 * ag.adj_share_pop_2022, ag[col]
        ax.scatter(x_[ag.n_adjacent_sectors > 0], y_[ag.n_adjacent_sectors > 0], s=26, marker="^", facecolor="none", edgecolor=DARK, linewidth=0.8, label="Districts with a park-adjacent sector")
        ax.scatter(x_[ag.n_adjacent_sectors == 0], y_[ag.n_adjacent_sectors == 0], s=14, facecolor="none", edgecolor=MID, linewidth=0.7, label="Other districts")
        ax.set_xlabel("Population share living in park-adjacent sectors, 2022 (%)"); ax.set_ylabel(yl + f", {int(yr)}")
        ax.legend(frameon=False, loc="best", fontsize=8)
        save(fig, f"district_{nm}_exposure", f"{yl} in the {int(yr)} survey round against district exposure, one point per district (EICV agricultural module).")
    lp = pd.read_csv(P.HARM_DISTRICT / "district-land-prices.csv")
    lp = lp[(lp.measure == "rent") & (lp.source == "EICV")][["district_id", "round", "median_per_ha_2014rwf", "n_parcels"]].merge(e, on="district_id")
    for rd in (2001, int(lp["round"].max())):
        z = lp[lp["round"] == rd]
        fig, ax = plt.subplots(figsize=(5.2, 3.8))
        ex = z.n_adjacent_sectors > 0
        ax.scatter(100 * z.adj_share_pop_2022[ex], z.median_per_ha_2014rwf[ex], s=26, marker="^", facecolor="none", edgecolor=DARK, linewidth=0.8, label="Districts with a park-adjacent sector")
        ax.scatter(100 * z.adj_share_pop_2022[~ex], z.median_per_ha_2014rwf[~ex], s=14, facecolor="none", edgecolor=MID, linewidth=0.7, label="Other districts")
        ax.set_yscale("log"); ticks = [10000, 20000, 50000, 100000, 200000, 500000, 1000000]
        ax.yaxis.set_major_locator(FixedLocator(ticks)); ax.set_yticklabels([f"{t:,}" for t in ticks]); ax.yaxis.set_minor_formatter(NullFormatter())
        ax.set_xlabel("Population share living in park-adjacent sectors, 2022 (%)"); ax.set_ylabel(f"Median land rent per hectare, {rd} (2014 RWF, log scale)")
        ax.legend(frameon=False, loc="best", fontsize=8)
        save(fig, f"district_rent_exposure_{rd}", f"Median land rent per hectare against district exposure, EICV round {rd}; one point per district. District-round cells have as few as 19 parcels.")


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--tex", action="store_true")
    args = a.parse_args(argv)
    d = build()
    print("[descriptive] categories:", counts(d), flush=True)
    distributions(d); services_breakdown(d); occupation_mix(d); scatters(d); land_forest(d); tourism(d); district(d)
    print(f"[descriptive] {len(CAP)} figures -> {OUT}")
    if args.tex:
        names = sorted(CAP)
        esc = lambda s: s.replace("%", "\\%").replace("&", "\\&").replace("_", " ").replace("#", "\\#")
        body = "\n".join(f"\\begin{{figure}}[H]\\centering\\includegraphics[width=0.78\\textwidth]{{{OUT / (n + '.pdf')}}}\n\\caption{{\\small {esc(CAP[n])}}}\n\\end{{figure}}" for n in names)
        tex = ("\\documentclass[11pt]{article}\n\\usepackage[margin=1in]{geometry}\n\\usepackage{graphicx,float}\n\\usepackage[font=small,labelfont=bf]{caption}\n\\begin{document}\n" + body + "\n\\end{document}\n")
        (ROOT / "docs" / "sector_descriptive_figures.tex").write_text(tex)
        print("[descriptive] -> docs/sector_descriptive_figures.tex")
    return 0


if __name__ == "__main__":
    sys.exit(main())
