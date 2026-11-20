"""Sector panel for the 2x2 model: survey subsets, treatment groups and every sector-level panel the
analysis reads. Writes data/harmonized/extracts/ and data/harmonized/prelim/.

Run every section in order:   python micro-analysis/sector_panel.py
Run some sections:            python micro-analysis/sector_panel.py --only <name> [<name> ...]
List the sections:            python micro-analysis/sector_panel.py --list

Sections, in run order:
  survey_extracts        (was 00_extracts.py) Column subsets of the cleaned survey files, saved once so the analysis scripts open them quickly.
  treatment_groups       (was 00_treatment_groups.py) Treatment groups, taken from helpers/treatment_groups.py::classify() so they match
  jobs                   (was 01_jobs.py) Jobs: Census 2002/2012/2022 sector-level employment by tradable/non-tradable services,
  output                 (was 02_output.py) Output over time, by economic sector and location.
  landcover_crop         (was 03a_landcover_crop.py) Crop GLAD GLCLU v2 (2000/2005/2010/2015/2020, 30 m) and ESA WorldCover 2021 v200 (10 m) tiles to Rwanda.
  landcover_sectors      (was 03b_landcover_sectors.py) Sector-level land use (hectares) from GLCLU v2 2000/2010/2020 and WorldCover 2021, total and outside parks.
  panel                  (was 04_build_panel.py) One sector panel for all descriptives, on the repo's treatment groups (section treatment_groups).
  forest_outcomes        (was 11a_forest_outcomes.py) Hansen GFC tree-cover loss by sector and year, outside parks, from the Rwanda crops in geo-data/forest.
  built_up               (was 11b_ghsl_built.py) GHSL built-up surface (GHS-BUILT-S R2023A, 3 arc-second ~90 m, EPSG:4326), total and non-residential (NRES),
  land_rent              (was 11c_land_rent.py) District land rent per hectare, the model's r, from rented parcels.
  pop_density            (was 16_pop_density.py) Population density by sector, Census 2002, 2012, 2022.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
from common import *  # noqa: F401,F403  paths, ISIC groups, figure/table names, LaTeX tables (helpers/common.py)


def section_survey_extracts():
    """Column subsets of the cleaned survey files, saved once so the analysis scripts open them quickly.

Reads Matteo's cleaned NISR files in Dropbox (nothing about the cleaning changes) and writes one
parquet file per subset to data/harmonized/extracts/. Every row is kept; the analysis scripts apply
their own age, year and industry filters.

    python micro-analysis/sector_panel.py --only survey_extracts            # build any subset that is missing
    REDO=1 python micro-analysis/sector_panel.py --only survey_extracts     # rebuild all of them
"""
    import os
    import sys
    from pathlib import Path

    import pyreadstat

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    N = P.NISR
    SUBSETS = {
        # name: (source file, columns)
        "census_sub": (N / "Census-PHC/4_Harmonized/H_Census_person.dta",
                       ["census_year", "census_sector", "census_age", "census_weight", "census_urban",
                        "census_industry_isic", "census_industry_isic4_2012"]),
        "lfs_sub": (N / "Labour-Force-Survey-LFS/4_Harmonized/H_LFS_person.dta",
                    ["lfs_year", "lfs_district", "lfs_age", "lfs_weight", "lfs_employment_status", "lfs_industry_isic",
                     "lfs_monthly_cash_income"]),
        "lfs_demo": (N / "Labour-Force-Survey-LFS/4_Harmonized/H_LFS_person.dta",
                     ["lfs_sex", "lfs_education_level_highest"]),
        "lfs_isic": (N / "Labour-Force-Survey-LFS/4_Harmonized/H_LFS_person.dta",
                     ["lfs_year", "lfs_district", "lfs_age", "lfs_weight", "lfs_isic_section_main_job",
                      "lfs_isic_2digit_main_2017_2018", "lfs_isic_main_job_2019_2021", "lfs_isic_main_job_2020",
                      "lfs_isic_two_digit_main_job"]),
        "eicv_sub": (N / "Household-Living-Conditions-EICV/4_Harmonized/H_EICV_person.dta",
                     ["eicv_year", "eicv_district", "eicv_age", "eicv_weight", "eicv_employed", "eicv_industry_isic",
                      "eicv_industry_isic_approx"]),
        "eicv_parcels": (N / "Household-Living-Conditions-EICV/2_Intermediate/appended/EICV_pooled_parcels.dta",
                         ["eicv_year", "eicv_district", "eicv_weight", "eicv_household_weight", "eicv_area_hectares_2001",
                          "eicv_surface_area", "eicv_surface_area_2006_2011", "eicv_cost_include_renting_2001",
                          "eicv_cost_rental_2006", "eicv_cost_renting_2011", "eicv_cost_renting_months_2014",
                          "eicv_cost_renting_2017"]),
        "ahs_land": (N / "Agriculture-Survey-AHS/2_Intermediate/appended/AHS_pooled_land.dta",
                     ["ahs_year", "ahs_district", "ahs_weight", "ahs_household_weight", "ahs_area_sqm_2024",
                      "ahs_pay_cash_renting_plot_2024"]),
        "sas_sub": (N / "Season-Agriculture-Survey-SAS/4_Harmonized/H_SAS_plotcrop.dta",
                    ["sas_year", "sas_district", "sas_weight", "sas_crop_name", "sas_crop_area_ha", "sas_harvested_area_ha",
                     "sas_production_kg", "sas_selling_price_2018_2022", "sas_selling_price_2023_2025"]),
        "ec_sub": (N / "Establishment-Census-EC/4_Harmonized/H_EC_establishment.dta",
                   ["ec_year", "ec_district", "ec_isic_section_comparable_2011", "ec_main_activity_section",
                    "ec_total_workers", "ec_total_workers_2011", "ec_total_workers_2014", "ec_annual_turnover_2014",
                    "ec_annual_turnover_2017_2020", "ec_annual_total_turnover_2023"]),
    }

    # The scripts read EICV age as eicv_age_years. The column of that name in the cleaned file is filled for 2001
    # only; eicv_age (the cross-survey age in the key block) covers every round, and is what the scripts need.
    RENAME = {"eicv_sub": {"eicv_age": "eicv_age_years"}}


    def main():
        P.HARM_EXTRACTS.mkdir(parents=True, exist_ok=True)
        redo = os.environ.get("REDO") == "1"
        for name, (src, cols) in SUBSETS.items():
            out = P.HARM_EXTRACTS / f"{name}.parquet"
            if out.exists() and not redo:
                continue
            # apply_value_formats=False keeps codes, not labels; the scripts work with codes.
            df, _ = pyreadstat.read_dta(str(src), usecols=cols)
            df = df[cols].rename(columns=RENAME.get(name, {}))
            df.to_parquet(out, index=False)
            print(f"{name:13s} {len(df):>9,} rows x {len(cols):>2} columns  <- {src.relative_to(P.DATA)}")

        # Census population and urban share by sector and wave (all ages, Census weights; census_urban 1 = urban).
        import pandas as pd
        P.HARM_PRELIM.mkdir(parents=True, exist_ok=True)
        c = pd.read_parquet(P.HARM_EXTRACTS / "census_sub.parquet",
                            columns=["census_year", "census_sector", "census_weight", "census_urban"])
        c["w_urban"] = c.census_weight * (c.census_urban == 1)
        g = c.groupby(["census_sector", "census_year"])[["census_weight", "w_urban"]].sum()
        g.index.names = ["sid", "wave"]
        g.census_weight.rename("pop_total").reset_index().to_csv(P.HARM_PRELIM / "sector_pop_total.csv", index=False)
        (g.w_urban / g.census_weight).rename("urban_sh").reset_index().to_csv(P.HARM_PRELIM / "sector_urban_share.csv", index=False)
        print("sector_pop_total.csv, sector_urban_share.csv ->", P.HARM_PRELIM)


    main()


def section_treatment_groups():
    """Treatment groups, taken from helpers/treatment_groups.py::classify() so they match
map1-map3 exactly (Bordering 42, Gates 4, Gates+ 21 after the settled-land rule, control 322,
Kigali 35 + four 2002 towns (9 sectors) excluded, Gishwati-Mukura neighbours flagged).
Writes data/harmonized/prelim/treatment_groups.csv with one row per sector:
  group: Gates | Gates+ (near_gates not gates) | Bordering (border only) | Kigali | Towns | Control
Precedence for the single label: Kigali > Towns > Gates > Gates+ > Bordering > Control.
Gishwati-Mukura neighbours stay in Control, as in map3 (flag `gish`).
Flags for every set are kept so any definition from map3 can be rebuilt."""
    import importlib.util, os, sys, types
    from pathlib import Path
    import pandas as pd
    sys.modules.setdefault("adjustText", types.SimpleNamespace(adjust_text=lambda *a, **k: None))  # labels only, not needed here
    import treatment_groups as mts  # helpers/treatment_groups.py
    sec, dist, pk, parks = mts.load()
    L = mts.classify(sec, parks, pk)

    df = sec[["sid", "sector", "district"]].copy()
    for k in ["border", "gates", "near_gates", "gish", "kig_all", "kig_core", "towns"]:
        df[k] = df.sid.isin(L[k]).astype(int)
    def grp(r):
        if r.kig_all: return "Kigali"
        if r.towns: return "Towns"
        if r.gates: return "Gates"
        if r.near_gates: return "Gates+"
        if r.border: return "Bordering"
        return "Control"
    df["group"] = df.apply(grp, axis=1)
    df["treated_any"] = ((df.border | df.near_gates) & ~df.kig_all.astype(bool) & ~df.towns.astype(bool)).astype(int)
    df["control"] = (~(df.border | df.near_gates).astype(bool) & ~df.kig_all.astype(bool) & ~df.towns.astype(bool)).astype(int)
    # spillover ring: non-treated, non-urban sectors whose polygon touches a treated sector (10 m tolerance)
    tr_union = sec[sec.sid.isin(L["border"] | L["near_gates"])].union_all().buffer(10)
    df["ring1"] = (sec.geometry.intersects(tr_union).values & (df.treated_any == 0) & (df.control == 1)).astype(int)
    # clean control (main): control, not a Gishwati-Mukura neighbour, not in the spillover ring
    df["control_clean"] = ((df.control == 1) & (df.gish == 0) & (df.ring1 == 0)).astype(int)
    # park-border dummies for park x wave terms (sector touches that park; Gishwati-Mukura included)
    for name in ["Volcanoes", "Nyungwe", "Akagera", "Gishwati-Mukura"]:
        df["border_" + name.split("-")[0].lower()] = (sec.geometry.distance(parks[name]) == 0).astype(int).values
    # nearest long-standing park for park-specific panels
    park_of = {}
    for name in ["Volcanoes", "Nyungwe", "Akagera"]:
        d = sec.geometry.distance(parks[name]); park_of[name] = d
    dd = pd.DataFrame(park_of); df["park"] = dd.idxmin(axis=1).values
    df.to_csv(OUT_D / "treatment_groups.csv", index=False)
    print({k: len(v) for k, v in L.items()})
    print(df.group.value_counts().to_dict()); print("treated_any", df.treated_any.sum(), "control", df.control.sum(), "ring1", df.ring1.sum(), "control_clean", df.control_clean.sum())
    print(df[[c for c in df if c.startswith("border_")]].sum().to_dict())
    print(df[df.group.isin(["Gates", "Gates+"])].groupby(["park", "group"]).sector.apply(list).to_string())


def section_jobs():
    """Jobs: Census 2002/2012/2022 sector-level employment by tradable/non-tradable services,
LFS 2017-2025 annual national trends, park-distance gradients.
Workers aged 20-64, Census weights. 2022 agriculture = reconstructed count (n_AG_pt) from
model_sector_panel.csv because the 2022 Census follows the 19th ICLS and records most
own-use farmers as not employed (recorded ISIC A falls 2.80M -> 1.69M)."""
    import os, numpy as np, pandas as pd, matplotlib.pyplot as plt

    cs = pd.read_parquet(P.HARM_EXTRACTS / "census_sub.parquet",
                         columns=["census_year", "census_sector", "census_age", "census_weight", "census_industry_isic"])
    cs = cs[cs.census_industry_isic.notna() & cs.census_age.between(20, 64)]
    cs["sec"] = cs.census_industry_isic.astype(int).map(SEC)
    cs["grp"] = cs.sec.map(GROUP)
    cs["broad"] = (~cs.sec.isin(BROAD_EXCL) & cs.grp.str.startswith("S")).astype(int)

    g = cs.pivot_table(index=["census_sector", "census_year"], columns="grp", values="census_weight", aggfunc="sum", fill_value=0)
    g["S_broad"] = cs[cs.broad == 1].groupby(["census_sector", "census_year"]).census_weight.sum()
    sec_detail = cs.pivot_table(index=["census_sector", "census_year"], columns="sec", values="census_weight", aggfunc="sum", fill_value=0).add_prefix("n_")
    g = g.join(sec_detail).fillna(0).reset_index().rename(columns={"census_sector": "sid", "census_year": "wave"})

    panel = pd.read_csv(ANA / "model_sector_panel.csv")
    cross = pd.read_csv(ANA / "model_sector_cross.csv")
    g = g.merge(panel[["sid", "wave", "adults", "n_AG_pt", "H_pop", "inmig_share", "inmig_recent5_share"]], on=["sid", "wave"], how="left")
    g["AG_recorded"] = g["AG"]
    g.loc[g.wave == 2022, "AG"] = g.loc[g.wave == 2022, "n_AG_pt"]
    S = ["S_tour", "S_bus", "S_loc"]
    g["S_all"] = g[S].sum(1)
    g["workers"] = g[["AG", "IND"] + S].sum(1)
    for c in ["AG", "IND", "S_all", "S_tour", "S_bus", "S_loc", "S_broad"]:
        g["sh_" + c] = g[c] / g.workers
    g["lambda_model"] = g.AG / (g.AG + g.S_broad)          # model 2x2: agriculture vs (fallback) services
    g["lambda_tour"] = g.AG / (g.AG + g.S_tour)
    g = g.merge(cross[["sid", "district", "district_id", "province_id", "border", "dist_to_park_km", "nearest_park"]], on="sid")
    g["band"] = band(g)
    g.to_csv(OUT_D / "sector_jobs_panel.csv", index=False)
    print("sectors per wave", g.groupby("wave").sid.nunique().to_dict())

    # ---------- T1: national composition ----------
    nat = g.groupby("wave")[["AG", "AG_recorded", "IND", "S_tour", "S_bus", "S_loc", "S_broad", "workers"]].sum()
    t1 = pd.concat({"Workers (000s)": (nat / 1e3).T,
                    "Share of workers": nat[["AG", "IND", "S_tour", "S_bus", "S_loc", "S_broad"]].div(nat.workers, axis=0).T})
    t1 = t1.rename(index={"AG": "Agriculture", "AG_recorded": "Agriculture (recorded)", "IND": "Industry",
                          "S_tour": "Tourism services (I,R)", "S_bus": "Business services (J,K,M)",
                          "S_loc": "Local services (G,H,L,N-Q,S-U)", "S_broad": "Services excl. trade, govt", "workers": "Total"})
    t1.columns = t1.columns.astype(str)
    to_tex(t1, OUT_T / "jobs_national_census", "Employment by sector, Census, ages 20--64. 2022 agriculture is the reconstructed own-use-inclusive count; recorded count shown separately.", "tab:jobs_nat", "{:,.3f}")

    # detailed section table (national, 000s)
    det = g.groupby("wave")[[f"n_{s}" for s in SEC.values() if f"n_{s}" in g]].sum().T / 1e3
    det.index = det.index.str[2:]
    det["group"] = det.index.map(GROUP)
    det["growth_2012_22"] = det[2022] / det[2012] - 1
    det.columns = det.columns.astype(str)
    det.to_csv(OUT_T / "jobs_isic_sections_census.csv")

    # ---------- T2: by park-distance band ----------
    bw = g.groupby(["band", "wave"], observed=True)[["AG", "IND", "S_tour", "S_bus", "S_loc", "S_broad", "workers", "H_pop"]].sum()
    t2 = bw[["AG", "S_tour", "S_broad"]].div(bw.workers, axis=0)
    t2["workers (000s)"] = bw.workers / 1e3
    t2["n_sectors"] = g.groupby(["band", "wave"], observed=True).sid.nunique()
    inm = g.groupby(["band", "wave"], observed=True)[["inmig_share","workers"]].apply(lambda d: np.average(d.inmig_share, weights=d.workers) if d.inmig_share.notna().any() else np.nan)
    t2["in-migrant share"] = inm
    t2.columns = ["Agriculture share", "Tourism-services share", "Services excl. G,O share", "Workers (000s)", "Sectors", "In-migrant share"]
    to_tex(t2, OUT_T / "jobs_by_park_band", "Employment shares by distance to the nearest national park, Census waves.", "tab:jobs_band")

    # change 2012 -> 2022 sector-level (unweighted mean and sd), by band
    w = g.pivot_table(index=["sid", "band"], columns="wave", values=["sh_AG", "sh_S_tour", "sh_S_broad", "workers"], observed=True)
    d = pd.DataFrame({"d_sh_AG": w["sh_AG"][2022] - w["sh_AG"][2012],
                      "d_sh_S_tour": w["sh_S_tour"][2022] - w["sh_S_tour"][2012],
                      "d_sh_S_broad": w["sh_S_broad"][2022] - w["sh_S_broad"][2012],
                      "dlog_workers": np.log(w["workers"][2022] / w["workers"][2012]),
                      "d_sh_AG_0212": w["sh_AG"][2012] - w["sh_AG"][2002]}).reset_index()
    d = d.merge(cross[["sid", "dist_to_park_km", "province_id"]], on="sid")
    d.to_csv(OUT_D / "sector_jobs_changes.csv", index=False)
    t3 = d.groupby("band", observed=True)[["d_sh_AG_0212", "d_sh_AG", "d_sh_S_tour", "d_sh_S_broad", "dlog_workers"]].agg(["mean", "std"])
    t3.columns = [f"{a} {b}" for a, b in t3.columns]
    to_tex(t3, OUT_T / "jobs_changes_by_band", "Sector-level changes in employment shares and log workers, by park-distance band (unweighted across sectors).", "tab:jobs_chg")

    # ---------- LFS annual ----------
    lfs = pd.read_csv(P.HARM_LABOUR / "lfs_district_isic.csv")
    lfs["grp"] = lfs.isic.astype(int).map(SEC).map(GROUP)
    ly = lfs.pivot_table(index="year", columns="grp", values="workers", aggfunc="sum")
    ly_sh = ly.div(ly.sum(1), axis=0)
    ly_sh.to_csv(OUT_T / "jobs_lfs_national_shares.csv")

    # ---------- figures ----------
    fig, ax = plt.subplots(1, 2, figsize=(8.2, 3.2))
    cen = nat[["AG", "IND", "S_tour", "S_bus", "S_loc"]].div(nat.workers, axis=0)
    lab = {"AG": "Agriculture", "IND": "Industry", "S_tour": "Tourism svc", "S_bus": "Business svc", "S_loc": "Local svc"}
    for i, c in enumerate(lab):
        ax[0].plot(cen.index, cen[c], marker="o", ms=4, color=PAL[i], label=lab[c])
        ax[0].annotate(lab[c], (2022, cen[c].iloc[-1]), xytext=(4, 0), textcoords="offset points", va="center", fontsize=7, color="#333")
    ax[0].plot([2022], [nat.AG_recorded[2022] / nat.workers[2022]], marker="x", color=PAL[0], ls="none")
    ax[0].annotate("recorded", (2022, nat.AG_recorded[2022] / nat.workers[2022]), xytext=(-40, -2), textcoords="offset points", fontsize=7, color="#333")
    ax[0].set_xticks([2002, 2012, 2022]); ax[0].set_xlim(2000, 2028); ax[0].set_title("Census, share of workers 20-64", loc="left", fontsize=9)
    for i, c in enumerate(lab):
        if c in ly_sh: ax[1].plot(ly_sh.index, ly_sh[c], marker="o", ms=3, color=PAL[i], label=lab[c])
    ax[1].axvspan(2019.6, 2021.4, color="#eee", zorder=0); ax[1].text(2020.5, ax[1].get_ylim()[1] * 0.95, "COVID", ha="center", fontsize=7, color="#666")
    ax[1].set_title("LFS, share of employed (recorded)", loc="left", fontsize=9); ax[1].legend(fontsize=7, frameon=False, ncol=2)
    for a in ax: a.set_yscale("log"); a.set_yticks([0.01, 0.03, 0.1, 0.3, 0.9]); a.set_yticklabels(["1%", "3%", "10%", "30%", "90%"])
    fig.tight_layout(); fig.savefig(OUT_F / "jobs_national_trend.png"); plt.close(fig)

    fig, ax = plt.subplots(1, 3, figsize=(9, 3))
    for j, (c, ttl) in enumerate([("AG", "Agriculture share"), ("S_tour", "Tourism-services share"), ("S_broad", "Services excl. G,O share")]):
        sh = (bw[c] / bw.workers).unstack("band")
        for i, b in enumerate(sh.columns):
            ax[j].plot(sh.index, sh[b], marker="o", ms=3, color=PAL[i], label=b)
        ax[j].set_xticks([2002, 2012, 2022]); ax[j].set_title(ttl, loc="left", fontsize=9)
    ax[0].legend(fontsize=7, frameon=False)
    fig.tight_layout(); fig.savefig(OUT_F / "jobs_by_park_band.png"); plt.close(fig)

    # binned scatter of 2012-22 changes on distance (excl. Kigali)
    dd = d[d.province_id != 1].copy(); dd["bin"] = pd.qcut(dd.dist_to_park_km.rank(method="first"), 20, labels=False)
    bs = dd.groupby("bin").agg(x=("dist_to_park_km", "mean"), ag=("d_sh_AG", "mean"), tour=("d_sh_S_tour", "mean"), wk=("dlog_workers", "mean"))
    fig, ax = plt.subplots(1, 3, figsize=(9, 2.9))
    for a, (c, t) in zip(ax, [("ag", "Change in agriculture share"), ("tour", "Change in tourism-svc share"), ("wk", "Change in log workers")]):
        a.scatter(bs.x, bs[c], s=18, color=PAL[0]); b1 = np.polyfit(dd.dist_to_park_km, dd[{"ag": "d_sh_AG", "tour": "d_sh_S_tour", "wk": "dlog_workers"}[c]], 1)
        xs = np.linspace(0, dd.dist_to_park_km.max(), 10); a.plot(xs, np.polyval(b1, xs), color=PAL[1], lw=1.5)
        a.set_title(t + ", 2012-22", loc="left", fontsize=8.5); a.set_xlabel("km to nearest park")
    fig.tight_layout(); fig.savefig(OUT_F / "jobs_change_distance_binscatter.png"); plt.close(fig)

    print(t1.round(3).to_string()); print(t2.round(3).to_string()); print(t3.round(3).to_string()); print(ly_sh.round(3).to_string())
    print(det.round(1).to_string())


def section_output():
    """Output over time, by economic sector and location.
 (a) Agriculture: SAS 2019-2025, district x year. Quantity in kg; value at fixed prices
     (crop-specific median RWF/kg selling price, pooled 2018-2024), so changes are real.
     2017-2018 are dropped: their weights sum to about half the crop area of 2019+ (1.15M vs 2.1M ha),
     a harmonization break, not a real change. Area = crop area, else harvested area; 2021 and 2024
     report neither, so value per ha is missing in those years.
 (b) Services: Establishment Census turnover by ISIC group, district x {2014,2017,2020,2023}
     (public 2017+ files have no sub-district code). Turnover is reported in nominal brackets; we impute
     midpoints (top bracket >50M RWF set to 100M; 2023 brackets 5-7 collapsed to >50M for comparability)
     and deflate by CPI (WDI) to 2014 RWF. Inflation moves firms up fixed nominal brackets, so the real
     series is coarse.
 (c) Local activity: nightlights (intercalibrated DMSP/VIIRS, settled pixels), sector x year.
 (d) National tourism: park visitors by park, park and total tourism revenue.
Measurement is rough by construction; these are descriptive moments, not value added."""
    import os, numpy as np, pandas as pd, matplotlib.pyplot as plt

    cross = pd.read_csv(ANA / "model_sector_cross.csv")
    cross["band"] = band(cross)
    # district-level park exposure: share of district land in sectors on a park border
    dexp = cross.groupby("district_id").apply(lambda d: np.average(d.border, weights=d.unit_km2), include_groups=False).rename("border_land_share")
    dname = cross.groupby("district_id").district.first()
    dgrp = pd.Series(np.where(dexp > 0, "Park-border district", "No park border"), index=dexp.index)
    dgrp[cross.groupby("district_id").province_id.first() == 1] = "Kigali"
    dgrp = dgrp.rename("park_group")

    # ---------------- (a) agriculture ----------------
    sas = pd.read_parquet(P.HARM_EXTRACTS / "sas_sub.parquet")
    sas = sas[sas.sas_year >= 2019]
    sas["price"] = sas.sas_selling_price_2018_2022.fillna(sas.sas_selling_price_2023_2025)
    pr = sas[(sas.price > 0) & sas.sas_year.between(2018, 2024)].groupby("sas_crop_name").price.median().rename("p_fix")
    sas = sas.merge(pr, left_on="sas_crop_name", right_index=True, how="left")
    sas["q"] = sas.sas_production_kg * sas.sas_weight
    sas["v"] = sas.q * sas.p_fix
    sas["ha"] = sas.sas_crop_area_ha.fillna(sas.sas_harvested_area_ha) * sas.sas_weight
    has_area = sas.groupby("sas_year").apply(lambda d: d.ha.notna().mean() > 0.8, include_groups=False)
    cover = sas.groupby("sas_year").apply(lambda d: d.v.notna().mul(d.q).sum() / d.q.sum(), include_groups=False)
    print("share of kg with a fixed price:", cover.round(3).to_dict())
    ag = sas.groupby(["sas_year", "sas_district"])[["q", "v", "ha"]].sum().reset_index().rename(columns={"sas_year": "year", "sas_district": "district_id"})
    ag = ag.merge(dgrp, left_on="district_id", right_index=True, how="left").merge(dname, left_on="district_id", right_index=True, how="left")
    ag.loc[~ag.year.map(has_area).astype(bool), "ha"] = np.nan
    ag["v_per_ha"] = ag.v / ag.ha
    ag.to_csv(OUT_D / "district_ag_output.csv", index=False)
    agn = ag.groupby("year")[["q", "v", "ha"]].sum()
    agn.loc[~has_area.reindex(agn.index).values, "ha"] = np.nan
    agn["v_per_ha"] = agn.v / agn.ha
    agn_t = pd.DataFrame({"Production (000 t)": agn.q / 1e6, "Value, fixed prices (bn RWF)": agn.v / 1e9,
                          "Crop area (000 ha, all seasons)": agn.ha / 1e3, "Value per ha (000 RWF)": agn.v_per_ha / 1e3})
    to_tex(agn_t, OUT_T / "output_ag_national", "Crop output, Seasonal Agricultural Survey (seasons A+B+C), national.", "tab:ag_nat", "{:,.1f}")
    crop = sas.groupby(["sas_year", "sas_crop_name"]).q.sum().unstack(0) / 1e6
    crop = crop.loc[crop.sum(1).sort_values(ascending=False).index[:10]]
    crop.columns = crop.columns.astype(str)
    crop.to_csv(OUT_T / "output_ag_top_crops_kt.csv")

    # ---------------- (b) services turnover ----------------
    ec = pd.read_parquet(P.HARM_EXTRACTS / "ec_sub.parquet")
    ec["sec_n"] = ec.ec_main_activity_section.fillna(ec.ec_isic_section_comparable_2011)
    lw = pd.read_csv(P.HARM_LABOUR / "ec_establishments_long.csv", usecols=["year", "isic"])  # 2014 section
    ec.loc[ec.ec_year == 2014, "sec_n"] = lw.loc[lw.year == 2014, "isic"].values
    ec["grp"] = ec.sec_n.where(ec.sec_n.between(1, 21)).map(SEC).map(GROUP)
    br = ec.ec_annual_turnover_2014.fillna(ec.ec_annual_turnover_2017_2020).fillna(ec.ec_annual_total_turnover_2023)
    br = br.where(br.between(1, 7)).clip(upper=5)  # 9 = not stated; 2023 brackets 5-7 -> >50M
    MID = {1: 0.15e6, 2: 6.15e6, 3: 16e6, 4: 35e6, 5: 100e6}
    ec["bracket"] = br
    ec["turn"] = br.map(MID)
    print("bracket distribution:"); print(ec.groupby("ec_year").bracket.value_counts(normalize=True).unstack().round(3))
    ec["emp"] = ec.ec_total_workers.fillna(ec.ec_total_workers_2014).fillna(ec.ec_total_workers_2011)
    cpi = pd.read_csv(P.tourism("world_bank_wdi.csv")).query("country=='RWA' and indicator_code=='FP.CPI.TOTL'").set_index("year").value
    last = cpi.dropna().index.max()
    print("CPI last year", last)
    ec["defl"] = ec.ec_year.map(lambda y: cpi.get(min(y, last)) / cpi[2014])
    ec["turn_r"] = ec.turn / ec.defl
    ec["has_turn"] = ec.turn.notna()
    ec["emp_rep"] = ec.emp.where(ec.has_turn)
    sv = ec.groupby(["ec_year", "ec_district", "grp"]).agg(turnover=("turn_r", "sum"), emp=("emp", "sum"), emp_rep=("emp_rep", "sum"), est=("emp", "size"),
                                                         turn_cov=("has_turn", "mean")).reset_index()
    sv = sv.rename(columns={"ec_year": "year", "ec_district": "district_id"}).merge(dgrp, left_on="district_id", right_index=True, how="left")
    sv.to_csv(OUT_D / "district_ec_output.csv", index=False)
    svn = sv.groupby(["year", "grp"])[["turnover", "emp", "emp_rep", "est"]].sum().unstack("grp")
    svt = pd.concat({"Real turnover (bn 2014 RWF)": svn.turnover / 1e9, "Reporting est. (000s)": svn.est / 1e3, "Workers (000s)": svn.emp / 1e3}, axis=1)
    svt = svt.drop(index=2011, errors="ignore").drop(columns=[c for c in svt.columns if c[1] == "AG"])
    svt.columns = [f"{a}: {b}" for a, b in svt.columns]
    to_tex(svt.T, OUT_T / "output_ec_national", "Establishment Census turnover (CPI-deflated, 2014 RWF) and workers by ISIC group. Turnover is self-reported and missing for informal units in some waves.", "tab:ec_nat", "{:,.1f}")
    cov = ec.groupby("ec_year").has_turn.mean(); print("turnover reported share:", cov.round(3).to_dict())

    # turnover per worker by group and district park group
    pw = sv.groupby(["year", "park_group", "grp"])[["turnover", "emp_rep"]].sum()
    pw["turn_per_worker_m"] = pw.turnover / pw.emp_rep / 1e6
    pwt = pw.turn_per_worker_m.unstack("grp")[["IND", "S_tour", "S_bus", "S_loc"]].drop(index=2011, level=0, errors="ignore")
    pwt.index = pwt.index.set_names(["year", "district group"])
    to_tex(pwt, OUT_T / "output_ec_turnover_per_worker", "Real turnover per worker (million 2014 RWF), Establishment Census, by district park exposure.", "tab:ec_tpw", "{:,.2f}")

    # ---------------- (c) nightlights ----------------
    nl = pd.read_csv(ANA / "nightlights_settled_panel_sector.csv").rename(columns={"uid": "sid"})
    nl = nl.merge(cross[["sid", "band"]], on="sid")
    nlb = nl.groupby(["year", "band"], observed=True).asinh_sum.mean().unstack()
    nlb.to_csv(OUT_T / "output_nightlights_by_band.csv")

    # ---------------- (d) tourism ----------------
    vis = pd.read_csv(P.tourism("park_visitors_by_park.csv")).set_index("year")
    prev = pd.read_csv(P.tourism("park_revenue_usd_million.csv")).set_index("year").park_revenue_usd_million_nominal
    trev = pd.read_csv(P.tourism("rdb_tourism_revenue_usd_million.csv")); trev = trev.set_index(trev.columns[0]).iloc[:, 0]
    tt = pd.DataFrame({"Park visitors (000s)": vis.total / 1e3, "Volcanoes": vis.volcanoes / 1e3, "Akagera": vis.akagera / 1e3,
                       "Nyungwe": vis.nyungwe / 1e3, "Park revenue (US$ m)": prev, "Tourism revenue (US$ m)": trev})
    tt["Park revenue per visitor (US$)"] = tt["Park revenue (US$ m)"] * 1e3 / tt["Park visitors (000s)"]
    tt.to_csv(OUT_T / "output_tourism_national.csv")

    # ---------------- figures ----------------
    fig, ax = plt.subplots(2, 2, figsize=(8.4, 5.6))
    a = ax[0, 0]
    a.plot(agn.index, agn.v / agn.v.loc[2019] * 100, marker="o", ms=3, color=PAL[0])
    a.set_title("Crop output value at fixed prices, SAS (2019 = 100)", loc="left", fontsize=9)
    a = ax[0, 1]
    tpw = (svn.turnover / svn.emp_rep / 1e6).drop(index=2011, errors="ignore")
    for i, c in enumerate(["IND", "S_tour", "S_bus", "S_loc"]):
        a.plot(tpw.index, tpw[c], marker="o", ms=3, color=PAL[i], label={"IND": "Industry", "S_tour": "Tourism svc (I,R)", "S_bus": "Business svc", "S_loc": "Local svc"}[c])
    a.set_xticks([2014, 2017, 2020, 2023]); a.set_title("Real turnover per reporting worker (m 2014 RWF)", loc="left", fontsize=9); a.legend(fontsize=7, frameon=False)
    a = ax[1, 0]
    nv = nlb.loc[nlb.index >= 2014]
    for i, b in enumerate(["Park border", "0-10 km", "10-30 km", ">30 km"]):
        a.plot(nv.index, nv[b], color=PAL[i], label=b, lw=1.5)
    a.set_title("Nightlights (VIIRS), mean asinh(sum) per sector", loc="left", fontsize=9); a.legend(fontsize=7, frameon=False)
    a = ax[1, 1]
    for i, c in enumerate(["Volcanoes", "Akagera", "Nyungwe"]):
        a.plot(tt.index, tt[c], marker="o", ms=3, color=PAL[i], label=c)
    a.axvline(2017, color="#999", lw=0.8, ls="--"); a.text(2017.2, a.get_ylim()[1] * 0.9, "Gorilla permit\n\\$750 to \\$1,500", fontsize=6.5, color="#555")
    a.set_title("Park visitors (000s)", loc="left", fontsize=9); a.xaxis.set_major_locator(plt.MaxNLocator(integer=True)); a.legend(fontsize=7, frameon=False)
    fig.tight_layout(); fig.savefig(OUT_F / "output_trends.png"); plt.close(fig)

    # agricultural value per ha by district group
    agg = ag.groupby(["year", "park_group"])[["v", "ha"]].sum(min_count=1); agg = (agg.v / agg.ha / 1e3).unstack()
    agg.to_csv(OUT_T / "output_ag_value_per_ha_by_group.csv")
    fig, a = plt.subplots(figsize=(4.4, 3))
    for i, c in enumerate(["No park border", "Park-border district", "Kigali"]):
        if c in agg: a.plot(agg.index, agg[c], marker="o", ms=3, color=PAL[i], label=c)
    a.set_title("Crop value per ha (000 RWF, fixed prices)\nby district share of land on a park border", loc="left", fontsize=8.5); a.legend(fontsize=7, frameon=False)
    fig.tight_layout(); fig.savefig(OUT_F / "output_ag_value_per_ha_by_group.png"); plt.close(fig)

    print(agn_t.round(1).to_string()); print(svt.round(1).T.to_string()); print(pwt.round(2).to_string()); print(tt.round(1).to_string())
    print(dgrp.value_counts().to_dict()); print(agg.round(0).to_string())


def section_landcover_crop():
    """Crop GLAD GLCLU v2 (2000/2005/2010/2015/2020, 30 m) and ESA WorldCover 2021 v200 (10 m) tiles to Rwanda.

Raw tiles live in data/geo-data/land-cover/raw-tiles/ under the names below; the Rwanda crops go to
data/geo-data/land-cover/rasters/. A crop that already exists is skipped (REDO=1 rebuilds it), so the raw
tiles are only needed to rebuild a crop. A missing tile stops the script with the file name and URL to fetch.
Sources:
  GLCLU:      https://storage.googleapis.com/earthenginepartners-hansen/GLCLU2000-2020/v2/{year}/{tile}.tif
  WorldCover: https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_{tile}_Map.tif"""
    import os, rasterio
    from rasterio.merge import merge
    RAW = DATA / "geo-data" / "land-cover" / "raw-tiles"
    OUT = DATA / "geo-data" / "land-cover" / "rasters"
    BBOX = (28.80, -2.90, 30.95, -1.00)
    GLCLU_URL = "https://storage.googleapis.com/earthenginepartners-hansen/GLCLU2000-2020/v2/{y}/{t}.tif"
    WC_URL = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_{t}_Map.tif"
    REDO = os.environ.get("REDO") == "1"


    def tiles(names_urls):
        missing = [(n, u) for n, u in names_urls if not (RAW / n).exists()]
        if missing:
            raise SystemExit("Missing raw tiles in " + str(RAW) + ":\n" + "\n".join(f"  {n}  <-  {u}" for n, u in missing))
        return [RAW / n for n, _ in names_urls]


    def write(srcs, out):
        ds = [rasterio.open(s) for s in srcs]
        arr, tr = merge(ds, bounds=BBOX)
        prof = ds[0].profile | dict(driver="GTiff", height=arr.shape[1], width=arr.shape[2], transform=tr, compress="deflate",
                                   tiled=True, blockxsize=512, blockysize=512, count=1, BIGTIFF="IF_SAFER")
        with rasterio.open(out, "w", **prof) as o: o.write(arr)
        print(out.name, arr.shape, round(os.path.getsize(out) / 1e6, 1), "MB")
    for y in ["2000", "2005", "2010", "2015", "2020"]:
        out = OUT / f"glclu_v2_{y}_rwanda.tif"
        if out.exists() and not REDO: continue
        write(tiles([(f"glclu_v2_{y}_tile_{t}.tif", GLCLU_URL.format(y=y, t=t)) for t in ["00N_020E", "00N_030E"]]), out)
    out = OUT / "worldcover_2021_v200_rwanda.tif"
    if not out.exists() or REDO:
        write(tiles([(f"worldcover_2021_v200_tile_{t}.tif", WC_URL.format(t=t)) for t in ["S03E027", "S03E030"]]), out)


def section_landcover_sectors():
    """Sector-level land use (hectares) from GLCLU v2 2000/2010/2020 and WorldCover 2021, total and outside parks.
GLCLU legend: 244 cropland; 250 built-up (any man-made surface in a 30 m pixel, so rural homesteads count);
25-48 and 125-148 tree height 3 to >25 m (terra firma / wetland); 200-211 and 254 water; rest = other
(short vegetation, bare). WorldCover: 10 tree, 20 shrub, 30 grass, 40 cropland, 50 built-up, 60 bare,
80 water, 90 wetland. Pixel area varies with latitude and is computed per row.
Park mask = RDB national parks + Gishwati/Mukura forest reserves (geodata.rw), wetlands excluded."""
    import numpy as np, pandas as pd, geopandas as gpd, rasterio
    from rasterio.features import rasterize
    from rasterio.windows import Window
    GEO = DATA / "geo-data"; RAS = GEO / "land-cover" / "rasters"
    sec = gpd.read_file(GEO / "protected-areas" / "sectors_park_exposure_geodatarw.gpkg")[["sector_id", "geometry"]]
    sec["sector_id"] = sec.sector_id.astype(int)
    pa = gpd.read_file(GEO / "protected-areas" / "rwanda_protected_areas_geodata_rw.gpkg")
    park = pa[pa["type"].isin(["National Park", "Volcanoes National Park", "Forest Reserve"])].union_all()
    NS = int(sec.sector_id.max()) + 1

    def classes_glclu(a):
        c = np.full(a.shape, 5, np.uint8)            # 5 other
        c[a == 244] = 0                               # crop
        c[a == 250] = 1                               # built
        c[((a >= 25) & (a <= 48)) | ((a >= 125) & (a <= 148))] = 2  # tree
        c[((a >= 200) & (a <= 211)) | (a == 254)] = 3                # water
        c[a == 255] = 4                               # nodata
        return c
    def classes_wc(a):
        m = np.full(256, 5, np.uint8); m[40] = 0; m[50] = 1; m[10] = 2; m[80] = 3; m[0] = 4; m[[20, 30]] = 6; m[90] = 7
        return m[a]
    NAMES = {0: "crop", 1: "built", 2: "tree", 3: "water", 4: "nodata", 5: "other", 6: "shrub_grass", 7: "wetland"}

    def zonal(path, fn, rows=1500):
        with rasterio.open(path) as r:
            acc = np.zeros((2, NS, 8))
            for r0 in range(0, r.height, rows):
                h = min(rows, r.height - r0); w = Window(0, r0, r.width, h); tr = r.window_transform(w)
                a = r.read(1, window=w)
                sid = rasterize(zip(sec.geometry, sec.sector_id), out_shape=a.shape, transform=tr, fill=0, dtype="int32")
                pk = rasterize([(park, 1)], out_shape=a.shape, transform=tr, fill=0, dtype="uint8")
                lat = tr.f + tr.e * (np.arange(h) + 0.5)
                pxha = (abs(tr.a) * 111320 * np.cos(np.radians(lat))) * (abs(tr.e) * 110574) / 1e4
                ar = np.broadcast_to(pxha[:, None], a.shape)
                c = fn(a); ok = sid > 0
                for p in (0, 1):
                    m = ok & (pk == p)
                    np.add.at(acc[p], (sid[m], c[m]), ar[m])
        rows_ = []
        for p, lab in ((0, "out"), (1, "park")):
            d = pd.DataFrame(acc[p], columns=[NAMES[i] for i in range(8)]); d["sector_id"] = d.index; d["zone"] = lab
            rows_.append(d)
        d = pd.concat(rows_); d = d[d.sector_id.isin(sec.sector_id)]
        return d.pivot(index="sector_id", columns="zone").pipe(lambda x: x.set_axis([f"{a}_{b}_ha" for a, b in x.columns], axis=1))

    out = []
    for y in [2000, 2005, 2010, 2015, 2020]:
        d = zonal(RAS / f"glclu_v2_{y}_rwanda.tif", classes_glclu)
        d = d.loc[:, (d != 0).any()]; d["year"] = y; out.append(d.reset_index()); print(y, "done")
    gl = pd.concat(out); gl.to_csv(OUT_D / "sector_landcover_glclu.csv", index=False)

    # ---- pixel transitions 2000 -> 2020 by treatment group, outside parks (ha) ----
    tg = pd.read_csv(OUT_D / "treatment_groups.csv")
    gcode = {"Gates": 1, "Gates+": 2, "Bordering": 3, "Control": 4, "Towns": 5, "Kigali": 6}
    lut = np.zeros(NS, np.uint8); lut[tg.sid.values] = tg.group.map(gcode).values
    T = np.zeros((7, 6, 6))
    with rasterio.open(RAS / "glclu_v2_2000_rwanda.tif") as r0, rasterio.open(RAS / "glclu_v2_2020_rwanda.tif") as r1:
        for r_ in range(0, r0.height, 1500):
            h = min(1500, r0.height - r_); w = Window(0, r_, r0.width, h); tr = r0.window_transform(w)
            a0 = classes_glclu(r0.read(1, window=w)); a1 = classes_glclu(r1.read(1, window=w))
            sid = rasterize(zip(sec.geometry, sec.sector_id), out_shape=a0.shape, transform=tr, fill=0, dtype="int32")
            pk = rasterize([(park, 1)], out_shape=a0.shape, transform=tr, fill=0, dtype="uint8")
            lat = tr.f + tr.e * (np.arange(h) + 0.5)
            ar = np.broadcast_to(((abs(tr.a) * 111320 * np.cos(np.radians(lat))) * (abs(tr.e) * 110574) / 1e4)[:, None], a0.shape)
            m = (sid > 0) & (pk == 0)
            np.add.at(T, (lut[sid[m]], a0[m], a1[m]), ar[m])
    rows = []
    for gname, gc in gcode.items():
        for i in range(6):
            for j in range(6):
                rows.append(dict(group=gname, from_=NAMES[i], to=NAMES[j], ha=T[gc, i, j]))
    pd.DataFrame(rows).rename(columns={"from_": "from"}).to_csv(OUT_D / "glclu_transitions_2000_2020.csv", index=False)
    print("transitions written")
    wc = zonal(RAS / "worldcover_2021_v200_rwanda.tif", classes_wc, rows=1200).reset_index()
    wc.to_csv(OUT_D / "sector_landcover_worldcover2021.csv", index=False)
    for nm, d in (("GLCLU", gl.groupby("year").sum(numeric_only=True)), ("WorldCover", wc.sum(numeric_only=True).to_frame("2021").T)):
        print(nm); print((d.filter(like="_ha") / 1e3).round(1).T.to_string())


def section_panel():
    """One sector panel for all descriptives, on the repo's treatment groups (section treatment_groups).
 jobs  : Census 2002/2012/2022 (section jobs), workers 20-64; 2022 agriculture reconstructed
 land  : GLCLU 2000/2005/2010/2015/2020, outside parks; Census waves matched to 2000/2010/2020
 ntl   : Chen et al. VIIRS-like sum (calibrated across sensors), asinh, Census waves matched to 2002/2012/2022
Shares of land use 'usable' land outside parks = crop + built + tree + other (water excluded).
ell = crop / (crop + built), the model's two-use land share.
Writes harmonized/prelim/sector_panel_desc.csv (sector x wave) and sector_cropland_builtup_glclu.csv (sector x year)."""
    import numpy as np, pandas as pd

    tg = pd.read_csv(OUT_D / "treatment_groups.csv")
    cross = pd.read_csv(ANA / "model_sector_cross.csv")[["sid", "district_id", "province_id", "Lbar_km2", "dist_to_park_km", "dist_kigali_km"]]
    tg = tg.merge(cross, on="sid")
    tg["urban"] = tg.group.isin(["Kigali", "Towns"]).astype(int)

    # ---------- land, sector x year ----------
    gl = pd.read_csv(OUT_D / "sector_landcover_glclu.csv").rename(columns={"sector_id": "sid"})
    for c in ["crop", "built", "tree", "other", "water"]:
        gl[c] = gl[f"{c}_out_ha"]
    gl["usable"] = gl[["crop", "built", "tree", "other"]].sum(1)
    for c in ["crop", "built", "tree", "other"]:
        gl[f"{c}_sh"] = gl[c] / gl.usable
    gl["ell"] = gl.crop / (gl.crop + gl.built)
    land = gl[["sid", "year", "crop", "built", "tree", "other", "water", "usable", "crop_sh", "built_sh", "tree_sh", "other_sh", "ell"]]
    wc = pd.read_csv(OUT_D / "sector_landcover_worldcover2021.csv").rename(columns={"sector_id": "sid"})
    wc["usable_wc"] = wc[["crop_out_ha", "built_out_ha", "tree_out_ha", "other_out_ha", "shrub_grass_out_ha", "wetland_out_ha"]].sum(1)
    wc = pd.DataFrame({"sid": wc.sid, "wc_crop_sh": wc.crop_out_ha / wc.usable_wc, "wc_built_sh": wc.built_out_ha / wc.usable_wc,
                       "wc_ell": wc.crop_out_ha / (wc.crop_out_ha + wc.built_out_ha), "wc_crop_ha": wc.crop_out_ha, "wc_built_ha": wc.built_out_ha})
    cb = tg[["sid", "sector", "district", "group", "park", "treated_any", "control", "urban"]].merge(land, on="sid").merge(wc, on="sid", how="left")
    cb.to_csv(OUT_D / "sector_cropland_builtup_glclu.csv", index=False)

    # ---------- nightlights ----------
    nl = pd.read_csv(P.HARM_NTL / "Nightlights_pooled_sector.csv",
                     usecols=["ntl_sector_id", "ntl_year", "ntl_chen_sum", "ntl_chen_asinh", "ntl_li_sum", "ntl_li_asinh"]).rename(columns={"ntl_sector_id": "sid", "ntl_year": "year"})
    nl.to_csv(OUT_D / "sector_ntl.csv", index=False)

    # ---------- jobs x land x ntl, sector x wave ----------
    jobs = pd.read_csv(OUT_D / "sector_jobs_panel.csv").drop(columns=["band", "district", "district_id", "province_id", "border", "dist_to_park_km", "nearest_park"], errors="ignore")
    d = tg.merge(jobs, on="sid")
    d = d.merge(land.assign(wave=land.year.map({2000: 2002, 2010: 2012, 2020: 2022})).dropna(subset=["wave"]).drop(columns="year"), on=["sid", "wave"], how="left")
    d = d.merge(nl[["sid", "year", "ntl_chen_asinh", "ntl_li_asinh"]].rename(columns={"year": "wave"}), on=["sid", "wave"], how="left")
    d["lam"] = d.AG / (d.AG + d.S_broad)                     # model lambda, services = all tertiary excl. G and O
    d["sh_tour"] = d.S_tour / d.workers
    d["sh_svc"] = d.S_broad / d.workers
    d["sh_ag"] = d.AG / d.workers
    d["density"] = d.workers / (d.usable / 100)              # workers per km2 of usable land
    d["k_a"] = d.crop / d.AG
    d["k_s"] = d.built / d.S_broad.replace(0, np.nan)
    d["c"] = d.k_a / d.k_s
    d["eps_model"] = (1 - d.ell) / (1 - d.lam)
    d["log_workers"] = np.log(d.workers)
    d.to_csv(OUT_D / "sector_panel_desc.csv", index=False)
    print(d.groupby(["group", "wave"]).sid.nunique().unstack())
    print(d[["lam", "ell", "sh_tour", "k_a", "k_s", "c", "ntl_chen_asinh"]].describe().round(3).T)


def section_forest_outcomes():
    """Hansen GFC tree-cover loss by sector and year, outside parks, from the Rwanda crops in geo-data/forest.
Tree cover = canopy >= 30% in 2000 (Hansen convention). Loss year 1-24 = 2001-2024. Pixel area by latitude.
Writes harmonized/prelim/sector_hansen_annual.csv (sector x year: loss_ha, treecover2000_ha) and
sector_forest_census.csv: for each Census wave, mean annual loss over the years AFTER it, as % of 2000 tree cover:
  2002 -> 2003-2005, 2012 -> 2013-2015, 2022 -> 2023-2024 (only two years exist after 2022)."""
    import numpy as np, pandas as pd, geopandas as gpd, rasterio
    from rasterio.features import rasterize
    F = DATA / "geo-data" / "forest"
    sec = gpd.read_file(DATA / "geo-data/protected-areas/sectors_park_exposure_geodatarw.gpkg")[["sector_id", "geometry"]]; sec["sector_id"] = sec.sector_id.astype(int)
    pa = gpd.read_file(DATA / "geo-data/protected-areas/rwanda_protected_areas_geodata_rw.gpkg")
    park = pa[pa["type"].isin(["National Park", "Volcanoes National Park", "Forest Reserve"])].union_all()
    with rasterio.open(F / "hansen_rwanda_lossyear.tif") as r1, rasterio.open(F / "hansen_rwanda_treecover2000.tif") as r2:
        ly = r1.read(1); tc = r2.read(1); tr = r1.transform; shp = ly.shape
    sid = rasterize(zip(sec.geometry, sec.sector_id), out_shape=shp, transform=tr, fill=0, dtype="int32")
    pk = rasterize([(park, 1)], out_shape=shp, transform=tr, fill=0, dtype="uint8")
    lat = tr.f + tr.e * (np.arange(shp[0]) + 0.5)
    ha = np.broadcast_to((((abs(tr.a) * 111320 * np.cos(np.radians(lat))) * (abs(tr.e) * 110574)) / 1e4)[:, None], shp)
    m = (sid > 0) & (pk == 0) & (tc >= 30) & (tc <= 100)
    NS = sid.max() + 1
    tc_ha = np.bincount(sid[m], weights=ha[m], minlength=NS)
    rows = []
    for y in range(1, 25):
        mm = m & (ly == y); loss = np.bincount(sid[mm], weights=ha[mm], minlength=NS)
        rows += [dict(sid=s, year=2000 + y, loss_ha=loss[s], treecover2000_ha=tc_ha[s]) for s in sec.sector_id]
    A = pd.DataFrame(rows); A.to_csv(OUT_D / "sector_hansen_annual.csv", index=False)
    W = {2002: [2003, 2004, 2005], 2012: [2013, 2014, 2015], 2022: [2023, 2024]}
    C = pd.concat([A[A.year.isin(ys)].groupby("sid").agg(loss_ha=("loss_ha", "mean"), tc=("treecover2000_ha", "first")).assign(wave=w) for w, ys in W.items()]).reset_index()
    C["loss_rate"] = 100 * C.loss_ha / C.tc.where(C.tc >= 10)          # % of 2000 cover per year; sectors with >= 10 ha cover
    C["asinh_loss"] = np.arcsinh(C.loss_ha)
    C.to_csv(OUT_D / "sector_forest_census.csv", index=False)
    print("national tree cover 2000 outside parks (000 ha):", round(tc_ha.sum() / 1e3, 1))
    print(A.groupby("year").loss_ha.sum().round(0).to_dict())
    print(C.groupby("wave")[["loss_rate", "loss_ha"]].describe().round(2).T)


def section_built_up():
    """GHSL built-up surface (GHS-BUILT-S R2023A, 3 arc-second ~90 m, EPSG:4326), total and non-residential (NRES),
epochs 2000/2005/2010/2015/2020, tiles R10_C21 and R10_C22. Cell values are m2 of built surface.

Uses the Rwanda crops in data/geo-data/land-cover/rasters/ (ghsl_built_{tot,nres}_{year}_rwanda.tif) when they exist
(REDO=1 rebuilds them); otherwise builds them from the zipped tiles in data/geo-data/land-cover/raw-tiles/, named
ghsl_built_{tot,nres}_{year}_tile_R10_{C21,C22}.zip. A missing tile stops the script with the file to fetch from
https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/GHS_BUILT_S_GLOBE_R2023A/ (original name in the message).
Writes harmonized/prelim/sector_ghsl_built.csv: sector x year, built_total_ha, built_nres_ha, built_res_ha, outside parks."""
    import os, zipfile, tempfile, numpy as np, pandas as pd, geopandas as gpd, rasterio
    from rasterio.merge import merge
    from rasterio.features import rasterize
    from pathlib import Path
    RAW = DATA / "geo-data" / "land-cover" / "raw-tiles"; RAS = DATA / "geo-data" / "land-cover" / "rasters"
    REDO = os.environ.get("REDO") == "1"
    SRC = "https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/GHS_BUILT_S_GLOBE_R2023A/"
    def orig_name(kind, y, c):
        return f"GHS_BUILT_S{'_NRES' if kind == 'NRES' else ''}_E{y}_GLOBE_R2023A_4326_3ss_V1_0_R10_{c}.zip"
    sec = gpd.read_file(DATA / "geo-data/protected-areas/sectors_park_exposure_geodatarw.gpkg")[["sector_id", "geometry"]]; sec["sector_id"] = sec.sector_id.astype(int)
    pa = gpd.read_file(DATA / "geo-data/protected-areas/rwanda_protected_areas_geodata_rw.gpkg")
    park = pa[pa["type"].isin(["National Park", "Volcanoes National Park", "Forest Reserve"])].union_all()
    BBOX = (28.80, -2.90, 30.95, -1.00); rows = []
    TMP = Path(tempfile.mkdtemp(prefix="ghsl_tiles_"))
    def open_tif(zf):
        z = zipfile.ZipFile(zf); n = [x for x in z.namelist() if x.endswith(".tif")][0]
        return rasterio.open(z.extract(n, TMP)), os.path.basename(n)
    def build_crop(kind, y, out):
        zs = [RAW / f"ghsl_built_{kind.lower()}_{y}_tile_R10_{c}.zip" for c in ["C21", "C22"]]
        miss = [(z.name, orig_name(kind, y, c)) for z, c in zip(zs, ["C21", "C22"]) if not z.exists()]
        if miss:
            raise SystemExit(f"Missing raw tiles in {RAW} (source {SRC}):\n" + "\n".join(f"  {n}  <-  {o}" for n, o in miss))
        ds = [open_tif(z) for z in zs]
        assert all(str(y) in n and (("NRES" in n) == (kind == "NRES")) for _, n in ds), [n for _, n in ds]
        arr, tr = merge([d for d, _ in ds], bounds=BBOX); nod = ds[0][0].nodata
        if nod is not None: arr[arr == nod] = 0
        arr[arr < 0] = 0
        prof = ds[0][0].profile | dict(driver="GTiff", height=arr.shape[1], width=arr.shape[2], transform=tr, compress="deflate", count=1)
        with rasterio.open(out, "w", **prof) as o: o.write(arr)
    for kind in ["TOT", "NRES"]:
        for y in [2000, 2005, 2010, 2015, 2020]:
            crop = RAS / f"ghsl_built_{kind.lower()}_{y}_rwanda.tif"
            if REDO or not crop.exists(): build_crop(kind, y, crop)
            with rasterio.open(crop) as r: a = r.read(1).astype("float64"); tr = r.transform; nod = r.nodata
            if nod is not None: a[a == nod] = 0
            a[a < 0] = 0
            sid = rasterize(zip(sec.geometry, sec.sector_id), out_shape=a.shape, transform=tr, fill=0, dtype="int32")
            pk = rasterize([(park, 1)], out_shape=a.shape, transform=tr, fill=0, dtype="uint8")
            m = (sid > 0) & (pk == 0)
            s = np.bincount(sid[m], weights=a[m], minlength=sid.max() + 1) / 1e4      # m2 -> ha
            rows += [dict(sid=i, year=y, kind=kind, ha=s[i]) for i in sec.sector_id]
            print(kind, y, "Rwanda total (000 ha):", round(s.sum() / 1e3, 1))
    G = pd.DataFrame(rows).pivot_table(index=["sid", "year"], columns="kind", values="ha").reset_index().rename(columns={"TOT": "built_total_ha", "NRES": "built_nres_ha"})
    G["built_res_ha"] = G.built_total_ha - G.built_nres_ha
    G.to_csv(OUT_D / "sector_ghsl_built.csv", index=False)
    print(G.groupby("year")[["built_total_ha", "built_nres_ha", "built_res_ha"]].sum().div(1e3).round(1))


def section_land_rent():
    """District land rent per hectare, the model's r, from rented parcels.
 EICV parcels: 2001 (area in ha), 2006/2011 (area in ares), 2014/2017 (area in ares); rent paid over 12 months
   (2014 is labelled 12 months; other waves are taken as annual -- an assumption). Rented = rent > 0.
 AHS 2024 plots: cash rent for the plot, area in m2 (different instrument; reported separately).
 Codes >= 999,999 dropped; rent per ha winsorized at 1/99% within year; CPI-deflated to 2014 RWF (WDI).
 Output: harmonized/prelim/district_land_rent.csv (district x year weighted median, N parcels)."""
    import os, numpy as np, pandas as pd
    cpi = pd.read_csv(P.tourism("world_bank_wdi.csv")).query("country=='RWA' and indicator_code=='FP.CPI.TOTL'").set_index("year").value
    defl = lambda y: cpi.get(min(y, cpi.dropna().index.max())) / cpi[2014]
    e = pd.read_parquet(P.HARM_EXTRACTS / "eicv_parcels.parquet")
    num = lambda c: pd.to_numeric(e[c], errors="coerce")
    e["area_ha"] = np.where(e.eicv_year == 2001, num("eicv_area_hectares_2001"), num("eicv_surface_area_2006_2011").fillna(num("eicv_surface_area")) / 100)
    e["rent"] = num("eicv_cost_include_renting_2001").fillna(num("eicv_cost_rental_2006")).fillna(num("eicv_cost_renting_2011")).fillna(num("eicv_cost_renting_months_2014")).fillna(num("eicv_cost_renting_2017"))
    e = e[(e.rent > 0) & (e.rent < 999999) & (e.area_ha > 0)].copy()
    E = pd.DataFrame({"year": e.eicv_year, "district_id": e.eicv_district, "w": e.eicv_household_weight.fillna(e.eicv_weight), "rent": e.rent, "area_ha": e.area_ha, "src": "EICV"})
    a = pd.read_parquet(P.HARM_EXTRACTS / "ahs_land.parquet")
    a = a[a.ahs_year == 2024].copy(); a["rent"] = pd.to_numeric(a.ahs_pay_cash_renting_plot_2024, errors="coerce"); a["area_ha"] = pd.to_numeric(a.ahs_area_sqm_2024, errors="coerce") / 1e4
    a = a[(a.rent > 0) & (a.area_ha > 0)]
    A = pd.DataFrame({"year": 2024, "district_id": a.ahs_district, "w": a.ahs_household_weight.fillna(a.ahs_weight), "rent": a.rent, "area_ha": a.area_ha, "src": "AHS"})
    parcels = pd.concat([E, A]); parcels["r_ha"] = parcels.rent / parcels.area_ha / parcels.year.map(defl)
    parcels["r_ha"] = parcels.groupby("year").r_ha.transform(lambda s: s.clip(s.quantile(.01), s.quantile(.99)))
    def wmed(x):
        o = np.argsort(x.r_ha.values); cw = np.cumsum(x.w.values[o]); return x.r_ha.values[o][np.searchsorted(cw, .5 * cw[-1])]
    D = parcels.groupby(["district_id", "year", "src"]).apply(lambda x: pd.Series({"rent_ha_median": wmed(x), "n_parcels": len(x), "median_area_ha": x.area_ha.median()}), include_groups=False).reset_index()
    D.to_csv(OUT_D / "district_land_rent.csv", index=False)
    tg = pd.read_csv(OUT_D / "treatment_groups.csv").merge(pd.read_csv(ANA / "model_sector_cross.csv")[["sid", "district_id"]], on="sid")
    park_d = set(tg[tg.treated_any == 1].district_id)
    D["dg"] = D.district_id.map(lambda d: "Kigali" if d in (11, 12, 13) else ("Park districts" if d in park_d else "Other districts"))
    parcels["dg"] = parcels.district_id.map(lambda d: "Kigali" if d in (11, 12, 13) else ("Park districts" if d in park_d else "Other districts"))
    T = parcels.groupby(["year", "dg"]).apply(wmed, include_groups=False).unstack() / 1e3
    T["N parcels"] = parcels.groupby("year").size()
    T.to_csv(OUT_T / "T15_land_rent_by_group.csv")
    (OUT_T / "T15_land_rent_by_group.tex").write_text(T.to_latex(float_format=lambda v: f"{v:,.1f}", caption="Median real land rent per hectare per year (000 2014 RWF), rented parcels, by district group. EICV 2001--2017; AHS 2024.", label="tab:T15", position="htbp"))
    print(parcels.groupby("year").agg(n=("rent", "size"), med_rent=("rent", "median"), med_area=("area_ha", "median")).round(3)); print(T.round(1))


def section_pop_density():
    """Population density by sector, Census 2002, 2012, 2022.
Population = weighted count of all persons in the Census 10% sample (census_weight), by sector.
Density = persons per km2 of usable land outside national parks and water (GLCLU, as in the panel)."""
    import numpy as np, pandas as pd, geopandas as gpd, matplotlib.pyplot as plt
    from matplotlib.colors import BoundaryNorm
    from matplotlib.patches import Patch

    C = DATA / "Publicly-Available-NISR/Census-PHC/2_Intermediate"
    pop = {}
    for y in (2002, 2012, 2022):
        c = pd.read_stata(C / f"Census_{y}_person_clean.dta", columns=["census_sector", "census_weight"], convert_categoricals=False)
        pop[y] = c.groupby("census_sector").census_weight.sum()
    pop = pd.DataFrame(pop); pop.index = pop.index.astype(int)
    print("national totals:", pop.sum().round(-3).to_dict())
    usable = pd.read_csv(OUT_D / "sector_cropland_builtup_glclu.csv").query("year == 2020").set_index("sid").usable / 100  # km2
    dens = pop.div(usable, axis=0)
    dens.to_csv(OUT_D / "sector_pop_density.csv")
    print(dens.describe().round(0))

    GEO = DATA / "geo-data"
    sec = gpd.read_file(GEO / "protected-areas" / "sectors_park_exposure_geodatarw.gpkg")[["sector_id", "geometry"]].to_crs(32736)
    sec["sid"] = sec.sector_id.astype(int); sec["geometry"] = sec.geometry.simplify(120)
    sec = sec.merge(dens, left_on="sid", right_index=True, how="left")
    sec["chg"] = 100 * (sec[2022] / sec[2002] - 1)
    pk = gpd.read_file(GEO / "protected-areas" / "rwanda_protected_areas_geodata_rw.gpkg")
    pk = pk[pk.designate.astype(str).str.contains("National Park", case=False, na=False)].to_crs(32736)
    lakes = gpd.read_file(GEO / "water" / "rwanda_lakes_osm.geojson").to_crs(32736)
    dist = gpd.read_file(GEO / "admin-boundaries" / "geodatarw_district_boundary.gpkg").to_crs(32736)
    xmin, ymin, xmax, ymax = sec.total_bounds

    def base(ax):
        lakes.plot(ax=ax, color="#cfe3f0", lw=0, zorder=0)
        pk.plot(ax=ax, facecolor="#dfe9df", edgecolor="#2E6B3E", lw=0.5, hatch="////", zorder=3)
        dist.boundary.plot(ax=ax, color="#7a7a7a", lw=0.25, zorder=4)
        ax.set_xlim(xmin, xmax); ax.set_ylim(ymin, ymax); ax.set_axis_off()

    fig = plt.figure(figsize=(15, 4.2))
    W = 0.205
    axes = [fig.add_axes([0.005 + k * W, 0.08, W, 0.84]) for k in range(3)] + [fig.add_axes([0.70, 0.08, W, 0.84])]
    def binbar(cax, cmap, bounds, labels, title):
        n = len(bounds) - 1
        cb = fig.colorbar(plt.cm.ScalarMappable(cmap=cmap, norm=BoundaryNorm(range(n + 1), n)), cax=cax, ticks=[k + 0.5 for k in range(n)])
        cb.ax.set_yticklabels(labels, fontsize=7); cb.ax.tick_params(length=0); cb.set_label(title, fontsize=8)
    B = [0, 250, 400, 600, 1000, 2500, 1e9]; cm1 = plt.get_cmap("YlOrRd", len(B) - 1); nrm = BoundaryNorm(B, cm1.N)
    for ax, y in zip(axes[:3], (2002, 2012, 2022)):
        sec.plot(ax=ax, column=y, cmap=cm1, norm=nrm, lw=0.05, edgecolor="white", zorder=1)
        base(ax); ax.set_title(f"{y}: {pop[y].sum()/1e6:.1f}m people", fontsize=9, loc="left")
    binbar(fig.add_axes([0.625, 0.18, 0.008, 0.64]), cm1, B, ["<250", "250-400", "400-600", "600-1,000", "1,000-2,500", ">2,500"],
           "persons per km$^2$ of usable land")
    B2 = [-1e9, 0, 25, 50, 100, 200, 1e9]; cm2 = plt.get_cmap("PuRd", len(B2) - 1); n2 = BoundaryNorm(B2, cm2.N)
    sec.plot(ax=axes[3], column="chg", cmap=cm2, norm=n2, lw=0.05, edgecolor="white", zorder=1)
    base(axes[3]); axes[3].set_title("Change in density, 2002-2022", fontsize=9, loc="left")
    binbar(fig.add_axes([0.915, 0.18, 0.008, 0.64]), cm2, B2, ["<0%", "0-25%", "25-50%", "50-100%", "100-200%", ">200%"], "% change")
    fig.legend(handles=[Patch(facecolor="#dfe9df", edgecolor="#2E6B3E", hatch="////", label="National park")],
               loc="lower left", fontsize=8, frameon=False, bbox_to_anchor=(0.01, -0.04))
    fig.text(0.93, -0.02, "Census 2002, 2012, 2022, all persons (weighted 10% sample). Usable land excludes parks and water (GLCLU).",
             ha="right", fontsize=7, color="0.35")
    fig.savefig(OUT_F / "fig17_map_pop_density.png", dpi=250, bbox_inches="tight")
    fig.savefig(OUT_F / "fig17_map_pop_density.pdf", bbox_inches="tight")

SECTIONS = {
    "survey_extracts": section_survey_extracts,
    "treatment_groups": section_treatment_groups,
    "jobs": section_jobs,
    "output": section_output,
    "landcover_crop": section_landcover_crop,
    "landcover_sectors": section_landcover_sectors,
    "panel": section_panel,
    "forest_outcomes": section_forest_outcomes,
    "built_up": section_built_up,
    "land_rent": section_land_rent,
    "pop_density": section_pop_density,
}


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", nargs="+", choices=list(SECTIONS), help="run only these sections, in run order")
    ap.add_argument("--list", action="store_true", help="list the sections and exit")
    a = ap.parse_args(argv)
    if a.list:
        print("\n".join(SECTIONS)); return
    for name, fn in SECTIONS.items():
        if a.only and name not in a.only:
            continue
        print(f"\n==== {name}", flush=True)
        fn()


if __name__ == "__main__":
    main()
