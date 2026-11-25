"""
census_park_regressions.py -- park-adjacent vs interior sectors across the 2002, 2012 and 2022 Censuses. All sector-level
regressions live here (one file; the former census_park_questions, census_park_status, census_park_logs and
park_land_regressions scripts are sections below).

DEFAULT SECTIONS (python micro-analysis/census_park_regressions.py [--drop-ring])
  outcomes   sector x wave counts and rates from the Census microdata -> data/harmonized/census_sector_work_per_adult.csv
  questions  Q1-Q4, one OLS per Census wave (land: per land-cover year), no sector fixed effects and no base year:
               ln(workers_s) = a_district + b Park_s + lam ln(adults_s) [+ geography controls] + e_s
             Q1 park-adjacent vs interior; Q2 distance to the nearest park gate (bins, nearest-park FE); Q3 visit-share
             exposure E_s; Q4 land use (cropland, built-up). Every regression has a column without and a column with the
             geography controls (log area, log distance to road and to Kigali, elevation, slope, rainfall; z-scored).
             -> census_park_questions[_no_ring].csv and docs/sector_question_tables.tex (AER tables). Specification, controls
             and fixed effects of every row are columns of the CSV; docs/sector_level_regressions.md lists them.
RETIRED SECTIONS (change-from-baseline designs with sector fixed effects; --legacy or --only <name>)
  gap person migration levels eicv_check status logs land shift opening -- described below and in each section's comments.

Usage
    python micro-analysis/census_park_regressions.py                 # outcomes + questions
    python micro-analysis/census_park_regressions.py --only questions --drop-ring
    python micro-analysis/census_park_regressions.py --legacy        # also the retired sections
    python micro-analysis/census_park_regressions.py --list

----------------------------------------------------------------------------------------------------------------
Retired design (sections gap, person, migration, levels, eicv_check; status, logs, land, shift, opening follow the same logic).
Question: do park-adjacent and interior sectors follow parallel paths in non-farm work, services work and
tourism work, or does the gap between them change from wave to wave? This is a descriptive comparison
across waves, not a design built on a shock.

    y_st = a_s + g_t + b_2012 Park_s 1[t = 2012] + b_2022 Park_s 1[t = 2022] + e_st

  a_s   sector fixed effects       g_t   wave fixed effects (2002 omitted)
  b_t   change in the park-adjacent minus interior gap between 2002 and wave t (zero = parallel paths)

Sample: the 381 sectors outside Kigali City (Nyarugenge, Gasabo, Kicukiro dropped), three Census waves.
Park_s = 1 if the sector borders a national park (data/harmonized/model_sector_cross.csv, column border).
Standard errors clustered by district; wild cluster restricted bootstrap p-values (Webb weights).

Outcomes are counts per 100 adults (residents aged 16+), not shares of workers: the denominator does not
depend on what counts as work, so the 2022 change (farming counts as work only if mainly for the market)
does not move it. A person counts in a numerator if their stated industry is in the group; people with no
industry or industry not stated count in the denominator only.
  non-farm   every industry except agriculture, forestry and fishing (ISIC A-B in Rev. 3, A in Rev. 4)
  services   ISIC Rev. 4 sections G-U; Rev. 3 (2002) divisions 50-99
  tourism    accommodation and food (Rev. 4 section I; Rev. 3 division 55) and arts, entertainment and
             recreation (Rev. 4 section R; Rev. 3 division 92)

Sections (python micro-analysis/census_park_regressions.py --list):
  outcomes   sector x wave counts and rates -> data/harmonized/census_sector_work_per_adult.csv
  gap        the regression above -> output/tables/regressions/census_park_gap.csv and .tex
  person     the same comparison at the person level, without and with person and household controls
             -> census_park_gap_person.csv and .tex (see section_person)
  migration  2012 and 2022 only (2002 records previous residence in the pre-2006 districts): the gap with a control
             for having moved in from another district or from abroad (a lower bound: moves within a district are
             missed). Person level: no controls / person and household controls / plus mover x wave. Sector level:
             plus the sector's in-mover share x wave. The park coefficient is the change in the gap from 2012 to 2022.
             -> census_park_gap_migration.csv and .tex
  levels     worker counts (non-farm, services, tourism, farm) instead of rates, controlling for log adults, with and
             without the park-share interaction; farm workers on 2002-2012 (2022 changes what counts as farm work)
             and on all three waves -> census_park_levels.csv
  eicv_check validation of the Census measure against EICV, by district (Kigali excluded): non-farm workers
             per 100 adults in Census 2002 / 2012 / 2022 against EICV 2005/06 / 2013/14 / 2023/24 (the rounds
             whose pooled person file carries the industry of the main job) -> census_eicv_nonfarm_check.csv

Ring option (--drop-ring): drop from the comparison group the sectors that touch a park-adjacent sector without
bordering a park themselves (82 sectors outside Kigali), leaving 237 interior sectors. Outputs then carry _no_ring.

Usage
    python micro-analysis/census_park_regressions.py
    python micro-analysis/census_park_regressions.py --only gap
    python micro-analysis/census_park_regressions.py --only gap person --drop-ring
"""
import argparse
import os
import sys
from pathlib import Path

import types

import numpy as np
import pandas as pd
import pyreadstat
import statsmodels.api as sm

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "helpers"))
import paths as P  # noqa: E402
from regression import fe_ols  # noqa: E402

sys.modules.setdefault("adjustText", types.SimpleNamespace(adjust_text=lambda *a, **k: None))  # label placement only; not used here
import treatment_groups as TG  # noqa: E402  (GATE_XY: the four park gates)

CENSUS = P.NISR / "Census-PHC/3_Final/Census_pooled_person.dta"
SECTORS = P.HARMONIZED / "model_sector_cross.csv"
PANEL = P.HARMONIZED / "census_sector_work_per_adult.csv"
KIGALI = {11, 12, 13}
WAVES = (2002, 2012, 2022)
OUTCOMES = [("nonfarm_per100", "Non-farm workers"), ("services_per100", "Services workers"),
            ("tourism_per100", "Tourism workers")]
SECTOR_ONLY = [("log_adults", "Log adults")]   # sector regression only: population growth, not composition


DROP_RING = False                       # set by --drop-ring
SECTOR_BOUNDARIES = P.NISR / "geodata-nisr" / "Sector_Boundary_2022_956146177651063157.geojson"


def _suffix() -> str:
    return "_no_ring" if DROP_RING else ""


def ring_sectors() -> set:
    """Sectors that touch a park-adjacent sector but do not border a park themselves (shared boundary or corner;
    1 m tolerance for slivers between the NISR polygons)."""
    import geopandas as gpd
    from shapely.validation import make_valid
    g = gpd.read_file(SECTOR_BOUNDARIES)
    g["sid"] = g.sector_id.astype(int)
    g["geometry"] = g.geometry.apply(make_valid)
    g = g[["sid", "geometry"]].dissolve("sid").reset_index().to_crs(32736)
    g = g.merge(pd.read_csv(SECTORS)[["sid", "border"]], on="sid")
    adj = g[g.border == 1].geometry.buffer(1).union_all()
    return set(g.sid[(g.border == 0) & g.geometry.intersects(adj)])


def _log(msg):
    print(f"[census-park] {msg}", flush=True)


# ---------------------------------------------------------------------------- outcomes
def classify(d: pd.DataFrame) -> pd.DataFrame:
    """0/1 columns nonfarm, services, tourism, farm for each person, by wave-specific industry coding.
    farm = stated industry in agriculture, forestry and fishing (the complement of nonfarm among stated industries)."""
    out = pd.DataFrame(0, index=d.index, columns=["nonfarm", "services", "tourism", "farm"], dtype="int8")
    # 2002: ISIC Rev. 3 three-digit groups (11-50 agriculture and fishing, 101+ everything else, 999 not stated)
    m = d.census_year == 2002
    g = d.loc[m, "census_industry_isic3_2002"]
    div = g // 10
    stated = g.notna() & (g != 999)
    out.loc[m, "nonfarm"] = (stated & (g >= 101)).astype("int8")
    out.loc[m, "services"] = (stated & (div >= 50)).astype("int8")
    out.loc[m, "tourism"] = (div.isin([55, 92])).astype("int8")
    out.loc[m, "farm"] = (stated & (g < 101)).astype("int8")
    # 2012 and 2022: ISIC Rev. 4 sections 1 = A ... 21 = U (22 not stated, 23 not applicable)
    for y in (2012, 2022):
        m = d.census_year == y
        s = d.loc[m, f"census_isic_section_{y}"]
        ok = s.between(1, 21)
        out.loc[m, "nonfarm"] = (ok & (s >= 2)).astype("int8")
        out.loc[m, "services"] = (ok & (s >= 7)).astype("int8")
        out.loc[m, "tourism"] = s.isin([9, 18]).astype("int8")
        out.loc[m, "farm"] = (s == 1).astype("int8")
    return out


def section_outcomes():
    """Weighted counts per sector and wave: adults 16+, non-farm, services and tourism workers."""
    cols = ["census_year", "census_sector", "census_district", "census_age", "census_weight",
            "census_industry_isic3_2002", "census_isic_section_2012", "census_isic_section_2022"]
    parts = []
    for chunk, _ in pyreadstat.read_file_in_chunks(pyreadstat.read_dta, str(CENSUS), chunksize=500_000, usecols=cols):
        chunk = chunk[(chunk.census_age >= 16) & chunk.census_year.isin(WAVES)]
        c = classify(chunk)
        w = chunk.census_weight.to_numpy()
        parts.append(pd.DataFrame({"sid": chunk.census_sector.astype(int).to_numpy(), "wave": chunk.census_year.astype(int).to_numpy(),
                                   "adults": w, "nonfarm": w * c.nonfarm, "services": w * c.services,
                                   "tourism": w * c.tourism, "farm": w * c.farm}))
    p = pd.concat(parts).groupby(["sid", "wave"], as_index=False).sum()
    for k in ("nonfarm", "services", "tourism", "farm"):
        p[f"{k}_per100"] = 100 * p[k] / p.adults
    p["log_adults"] = np.log(p.adults)
    assert len(p) == 3 * 416, f"expected 416 sectors x 3 waves, got {len(p)}"
    P.HARMONIZED.mkdir(parents=True, exist_ok=True)
    p.to_csv(PANEL, index=False)
    nat = p.groupby("wave")[["adults", "nonfarm", "services", "tourism", "farm"]].sum()
    for k in ("nonfarm", "services", "tourism", "farm"):
        nat[k] = (100 * nat[k] / nat.adults).round(2)
    _log(f"-> {PANEL}\nnational, per 100 adults:\n{nat.drop(columns='adults').to_string()}")


# ---------------------------------------------------------------------------- gap regression
def section_gap():
    p = pd.read_csv(PANEL)
    s = pd.read_csv(SECTORS)[["sid", "district_id", "border"]]
    d = p.merge(s, on="sid", how="left")
    if "log_adults" not in d:
        d["log_adults"] = np.log(d.adults)
    assert d.border.notna().all()
    d = d[~d.district_id.isin(KIGALI)].copy()
    if DROP_RING:
        d = d[~d.sid.isin(ring_sectors())].copy()
    for t in (2012, 2022):
        d[f"park_x_{t}"] = d.border * (d.wave == t)
    n_sec, n_park, n_dist = d.sid.nunique(), int(d.drop_duplicates("sid").border.sum()), d.district_id.nunique()
    _log(f"{n_sec} sectors ({n_park} park-adjacent), {n_dist} districts")
    rows = []
    for y, label in OUTCOMES + SECTOR_ONLY:
        est, n, G = fe_ols(d, y, ["park_x_2012", "park_x_2022"], ["sid", "wave"], "district_id")
        means = d.groupby(["wave", "border"])[y].mean().unstack()
        for t in (2012, 2022):
            r = est.loc[f"park_x_{t}"]
            rows.append({"outcome": y, "label": label, "wave": t, "coef": r.coef, "se": r.se, "p_wcb": r.p_wcb,
                         "mean_park_2002": means.loc[2002, 1], "mean_interior_2002": means.loc[2002, 0],
                         "mean_park_wave": means.loc[t, 1], "mean_interior_wave": means.loc[t, 0],
                         "obs": n, "sectors": n_sec, "park_sectors": n_park, "clusters": G})
        _log(f"  {label}: 2012 {est.loc['park_x_2012', 'coef']:+.2f} (p {est.loc['park_x_2012', 'p_wcb']:.3f}), "
             f"2022 {est.loc['park_x_2022', 'coef']:+.2f} (p {est.loc['park_x_2022', 'p_wcb']:.3f})")
    res = pd.DataFrame(rows)
    P.TABLES_REG.mkdir(parents=True, exist_ok=True)
    res.to_csv(P.TABLES_REG / f"census_park_gap{_suffix()}.csv", index=False)
    tex(res)
    _log(f"-> {P.TABLES_REG / f'census_park_gap{_suffix()}.csv'} and .tex")


def _stars(p):
    return "^{***}" if p < .01 else "^{**}" if p < .05 else "^{*}" if p < .1 else ""


def tex(res: pd.DataFrame):
    labels = [l for _, l in OUTCOMES + SECTOR_ONLY]
    cell = lambda l, t, k: res[(res.label == l) & (res.wave == t)].iloc[0][k]
    L = [r"\begin{table}[htbp]", r"\centering",
         r"\caption{Park-Adjacent and Interior Sectors across Census Waves" + (", Excluding the Ring of Neighbouring Sectors}" if DROP_RING else "}"),
         r"\label{tab:census_park_gap" + _suffix().replace("_", "-") + "}",
         r"\begin{tabular}{l" + "c" * len(labels) + "}", r"\toprule",
         " & " + " & ".join(labels) + r" \\", " & " + " & ".join(f"({i + 1})" for i in range(len(labels))) + r" \\",
         r"\midrule"]
    for t in (2012, 2022):
        L.append(f"Park-adjacent $\\times$ {t} & " + " & ".join(
            f"${cell(l, t, 'coef'):.2f}{_stars(cell(l, t, 'p_wcb'))}$" for l in labels) + r" \\")
        L.append(" & " + " & ".join(f"$({cell(l, t, 'se'):.2f})$" for l in labels) + r" \\")
        L.append(" & " + " & ".join(f"$[{cell(l, t, 'p_wcb'):.3f}]$" for l in labels) + r" \\")
    L.append(r"\midrule")
    L.append("2002 mean, park-adjacent & " + " & ".join(f"{cell(l, 2012, 'mean_park_2002'):.2f}" for l in labels) + r" \\")
    L.append("2002 mean, interior & " + " & ".join(f"{cell(l, 2012, 'mean_interior_2002'):.2f}" for l in labels) + r" \\")
    r0 = res.iloc[0]
    L.append(f"Sectors (park-adjacent) & " + " & ".join(f"{int(r0.sectors)} ({int(r0.park_sectors)})" for _ in labels) + r" \\")
    L.append("Observations & " + " & ".join(f"{int(r0.obs):,}" for _ in labels) + r" \\")
    L.append("Districts (clusters) & " + " & ".join(f"{int(r0.clusters)}" for _ in labels) + r" \\")
    L += [r"\bottomrule", r"\end{tabular}", r"\begin{minipage}{0.95\textwidth}\footnotesize",
          r"\textit{Notes:} Sector-by-wave panel from the 2002, 2012 and 2022 Population and Housing Census public-use "
          r"samples, on 2022 sector boundaries, excluding Kigali City" + (" and the sectors that touch a park-adjacent sector "
          r"without bordering a park" if DROP_RING else "") + r". Outcomes are workers per 100 residents aged 16 and "
          r"over, by industry of main work: non-farm (all industries except agriculture, forestry and fishing), services "
          r"(ISIC Rev.~4 sections G--U; Rev.~3 divisions 50--99 in 2002) and tourism (accommodation and food, and arts, "
          r"entertainment and recreation; Rev.~3 divisions 55 and 92 in 2002). Column (4) is the log of the number of "
          r"residents aged 16 and over (Census-weighted), so its coefficients give the difference in adult population "
          r"growth since 2002, in log points. Park-adjacent sectors border a national "
          r"park. Each column is one regression with sector and wave fixed effects; the coefficients give the change in "
          r"the park-adjacent minus interior gap relative to 2002. Standard errors clustered by district in parentheses; "
          r"wild cluster restricted bootstrap p-values (Webb weights, 9,999 draws) in brackets; stars from the bootstrap "
          r"p-values: *** 1\%, ** 5\%, * 10\%.", r"\end{minipage}", r"\end{table}", ""]
    (P.TABLES_REG / f"census_park_gap{_suffix()}.tex").write_text("\n".join(L))


# ---------------------------------------------------------------------------- person level, with controls
PERSON_COLS = ["census_year", "census_sector", "census_district", "census_household_id", "census_age", "census_sex",
               "census_urban", "census_weight", "census_industry_isic3_2002", "census_isic_section_2012",
               "census_isic_section_2022", "census_ever_attended_school_2002", "census_education_grouped_2002",
               "census_school_attendance_2012", "census_education_level_2012", "census_school_attendance_2022",
               "census_education_level_2022", "census_marital_status_2002", "census_marital_status_2012",
               "census_marital_status_2022", "census_previous_residence_2012", "census_previous_in_rwanda_2022",
               "census_previous_district_2022"]


def education_group(d: pd.DataFrame) -> pd.Series:
    """none / primary / secondary / tertiary / not stated, on the same footing in all three waves.
    2002: first digit of the grouped code is the level (1 primary, 2 post-primary, 3 secondary, 4+ university).
    Post-primary and 2022 vocational (INGOBOKA) count as primary; 2012 preschool and 2022 ECD / nursery as none."""
    g = pd.Series("not stated", index=d.index)
    y = d.census_year
    lv = d.census_education_grouped_2002 // 10
    g[(y == 2002) & lv.isin([1, 2])] = "primary"
    g[(y == 2002) & (lv == 3)] = "secondary"
    g[(y == 2002) & lv.between(4, 8)] = "tertiary"
    g[(y == 2002) & (d.census_ever_attended_school_2002 == 2)] = "none"
    e = d.census_education_level_2012
    g[(y == 2012) & e.isin([1, 2])] = "primary"
    g[(y == 2012) & (e == 3)] = "secondary"
    g[(y == 2012) & (e == 4)] = "tertiary"
    g[(y == 2012) & ((d.census_school_attendance_2012 == 1) | (e == 0))] = "none"
    e = d.census_education_level_2022
    g[(y == 2022) & e.isin([3, 4])] = "primary"
    g[(y == 2022) & e.isin([5, 6])] = "secondary"
    g[(y == 2022) & (e == 7)] = "tertiary"
    g[(y == 2022) & ((d.census_school_attendance_2022 == 3) | e.isin([1, 2]))] = "none"
    return g


def marital_group(d: pd.DataFrame) -> pd.Series:
    """never married / married or cohabiting / divorced or separated / widowed / not stated."""
    g = pd.Series("not stated", index=d.index)
    codes = {2002: {"never": [1], "married": [2, 3, 4, 5, 6, 7], "divorced": [8], "widowed": [9]},
             2012: {"never": [1], "married": [2], "divorced": [3, 5], "widowed": [4]},
             2022: {"never": [6], "married": [1, 2, 3], "divorced": [4, 5], "widowed": [7]}}
    for y, cmap in codes.items():
        v = d[f"census_marital_status_{y}"]
        for k, c in cmap.items():
            g[(d.census_year == y) & v.isin(c)] = k
    return g


def _demean(A: np.ndarray, groups: list[np.ndarray], w: np.ndarray, tol=1e-10, it=200) -> np.ndarray:
    """Weighted within transformation for several sets of fixed effects (alternating projections)."""
    A = np.array(A, dtype=float)                   # one working copy; convergence tracked without a second copy
    sws = [np.bincount(g, weights=w) for g in groups]
    for _ in range(it):
        step = 0.0
        for g, sw in zip(groups, sws):
            for j in range(A.shape[1]):
                m = np.bincount(g, weights=w * A[:, j]) / sw
                step = max(step, np.abs(m).max())
                A[:, j] -= m[g]
        if step < tol:
            break
    return A


def section_person():
    """Person-level version of the gap regression, without and with controls.
    Every resident aged 16+ outside Kigali, three waves pooled. Outcome: 1 if the person's main work is in the
    group (non-farm, services, tourism), else 0 (people who do not work included), times 100.
    Weights: Census person weight divided by the sector-wave total, so every sector-wave counts equally and the
    no-controls column reproduces the sector regression (section gap) exactly.
    Controls (each interacted with wave): age band, female, education group, marital group, urban, household size,
    lives in collective quarters (no household identifier; household size set to 0).
    Birthplace is left out: 2002 records it in the pre-2006 districts, which do not map onto today's."""
    parts = []
    for chunk, _ in pyreadstat.read_file_in_chunks(pyreadstat.read_dta, str(CENSUS), chunksize=500_000, usecols=PERSON_COLS):
        chunk = chunk[chunk.census_year.isin(WAVES)]
        parts.append(chunk)
    d = pd.concat(parts, ignore_index=True)
    # Household size = residents sharing wave and household identifier (all ages). Residents with no household
    # identifier live in collective quarters (boarding schools, barracks, prisons; 2002 only): household size 0
    # and their own indicator, so they stay in the sample. Grouping drops missing identifiers the same way in
    # pandas 2 and 3.
    size = d.groupby(["census_year", "census_household_id"], dropna=True).census_age.transform("size")
    d["collective"] = size.isna()
    d["hh_size"] = size.astype(float).fillna(0.0)
    d = d[(d.census_age >= 16) & ~d.census_district.isin(KIGALI)].reset_index(drop=True)
    if DROP_RING:
        d = d[~d.census_sector.astype(int).isin(ring_sectors())].reset_index(drop=True)
    frac = float(os.environ.get("CENSUS_PARK_SAMPLE", 0) or 0)   # test switch: keep this share of sectors
    if frac:
        keep = np.random.default_rng(0).choice(d.census_sector.unique(), int(d.census_sector.nunique() * frac), replace=False)
        d = d[d.census_sector.isin(keep)].reset_index(drop=True)
    d = d.join(classify(d))
    d["sid"], d["wave"] = d.census_sector.astype(int), d.census_year.astype(int)
    park = pd.read_csv(SECTORS).set_index("sid").border
    d["park"] = d.sid.map(park)
    d["w"] = d.census_weight / d.groupby(["sid", "wave"]).census_weight.transform("sum")
    edu, mar = education_group(d).astype(object), marital_group(d).astype(object)
    bands = pd.cut(d.census_age, [15, 19, 24, 29, 34, 39, 44, 49, 54, 59, 64, 200], labels=False)
    base = {"female": (d.census_sex == 2), "urban": (d.census_urban == 1), "household size": d.hh_size,
            "collective quarters": d.collective}
    for b in range(11):
        if b != 3:                                  # 30-34 omitted
            base[f"age band {b}"] = bands == b
    for k in ("none", "secondary", "tertiary", "not stated"):
        base[f"education {k}"] = edu == k        # primary omitted
    for k in ("never", "divorced", "widowed", "not stated"):
        base[f"marital {k}"] = mar == k          # married omitted
    X = {f"{k} x {t}": np.asarray(pd.Series(v).to_numpy(dtype=float, na_value=np.nan)) * (d.wave == t).to_numpy(dtype=float)
         for k, v in base.items() for t in WAVES}
    X = pd.DataFrame(X).loc[:, lambda x: x.std() > 0]
    T = pd.DataFrame({f"park_x_{t}": (d.park * (d.wave == t)).to_numpy(float) for t in (2012, 2022)})
    _log(f"{len(d):,} residents aged 16+ in {d.sid.nunique()} sectors; {X.shape[1]} control terms")
    gi = [pd.factorize(d.sid)[0], pd.factorize(d.wave)[0]]
    w = d.w.to_numpy()
    r = np.sqrt(w / w.mean())
    rows = []
    for y, label in OUTCOMES:
        yv = 100 * d[y.replace("_per100", "")].to_numpy(float)
        for spec, Z in (("no controls", T), ("controls", pd.concat([T, X], axis=1))):
            Zn = Z.to_numpy(dtype=float, na_value=np.nan)
            bad = [c for c, ok in zip(Z.columns, np.isfinite(Zn).all(axis=0)) if not ok]
            if bad or not np.isfinite(yv).all():
                raise ValueError(f"{label}, {spec}: missing or infinite values before demeaning in {bad or ['outcome']}")
            A = _demean(np.column_stack([yv, Zn]), gi, w) * r[:, None]
            if not np.isfinite(A).all():
                cols = ["outcome"] + list(Z.columns)
                raise ValueError(f"{label}, {spec}: demeaning produced missing values in "
                                 f"{[c for c, ok in zip(cols, np.isfinite(A).all(axis=0)) if not ok][:10]}")
            df = pd.DataFrame(A[:, 1:], columns=Z.columns)
            df["y"], df["district"] = A[:, 0], d.census_district.to_numpy()
            est, n, G = fe_ols(df, "y", list(Z.columns), [], "district", test=["park_x_2012", "park_x_2022"])
            if n != len(d):
                raise ValueError(f"{label}, {spec}: regression used {n:,} of {len(d):,} observations")
            for t in (2012, 2022):
                e = est.loc[f"park_x_{t}"]
                rows.append({"outcome": y, "label": label, "spec": spec, "wave": t, "coef": e.coef, "se": e.se,
                             "p_wcb": e.p_wcb, "obs": n, "clusters": G})
            _log(f"  {label}, {spec}: 2012 {est.loc['park_x_2012', 'coef']:+.2f} [{est.loc['park_x_2012', 'p_wcb']:.3f}], "
                 f"2022 {est.loc['park_x_2022', 'coef']:+.2f} [{est.loc['park_x_2022', 'p_wcb']:.3f}]")
    res = pd.DataFrame(rows)
    res.to_csv(P.TABLES_REG / f"census_park_gap_person{_suffix()}.csv", index=False)
    tex_person(res, len(d), d.sid.nunique(), int(d.drop_duplicates("sid").park.sum()))
    _log(f"-> {P.TABLES_REG / f'census_park_gap_person{_suffix()}.csv'} and .tex")


def tex_person(res: pd.DataFrame, n: int, n_sec: int, n_park: int):
    cols = [(l, sp) for _, l in OUTCOMES for sp in ("no controls", "controls")]
    get = lambda l, sp, t, k: res[(res.label == l) & (res.spec == sp) & (res.wave == t)].iloc[0][k]
    L = [r"\begin{table}[htbp]", r"\centering",
         r"\caption{Park-Adjacent and Interior Sectors: Person-Level Estimates" + (", Excluding the Ring of Neighbouring Sectors}" if DROP_RING else "}"),
         r"\label{tab:census_park_gap_person" + _suffix().replace("_", "-") + "}", r"\begin{tabular}{l" + "c" * len(cols) + "}", r"\toprule",
         " & " + " & ".join(f"\\multicolumn{{2}}{{c}}{{{l}}}" for _, l in OUTCOMES) + r" \\",
         " & " + " & ".join(f"({i + 1})" for i in range(len(cols))) + r" \\", r"\midrule"]
    for t in (2012, 2022):
        L.append(f"Park-adjacent $\\times$ {t} & " + " & ".join(f"${get(l, sp, t, 'coef'):.2f}{_stars(get(l, sp, t, 'p_wcb'))}$" for l, sp in cols) + r" \\")
        L.append(" & " + " & ".join(f"$({get(l, sp, t, 'se'):.2f})$" for l, sp in cols) + r" \\")
        L.append(" & " + " & ".join(f"$[{get(l, sp, t, 'p_wcb'):.3f}]$" for l, sp in cols) + r" \\")
    L += [r"\midrule", "Person and household controls $\\times$ wave & " + " & ".join("No" if sp == "no controls" else "Yes" for _, sp in cols) + r" \\",
          f"Residents aged 16+ & \\multicolumn{{{len(cols)}}}{{c}}{{{n:,}}} \\\\",
          f"Sectors (park-adjacent) & \\multicolumn{{{len(cols)}}}{{c}}{{{n_sec} ({n_park})}} \\\\",
          f"Districts (clusters) & \\multicolumn{{{len(cols)}}}{{c}}{{{int(res.clusters.iloc[0])}}} \\\\",
          r"\bottomrule", r"\end{tabular}", r"\begin{minipage}{0.95\textwidth}\footnotesize",
          r"\textit{Notes:} Residents aged 16 and over in the 2002, 2012 and 2022 Census public-use samples, outside Kigali "
          r"City" + (" and the sectors that touch a park-adjacent sector without bordering a park" if DROP_RING else "") + r". Outcome: 100 if the person's main work is in the group (non-farm, services, tourism; definitions as in "
          r"Table~\ref{tab:census_park_gap" + _suffix().replace("_", "-") + r"}), 0 otherwise, including people who do not work. All columns include sector and "
          r"wave fixed effects; observations are weighted so that every sector-wave carries equal weight, so the odd "
          r"columns reproduce Table~\ref{tab:census_park_gap" + _suffix().replace("_", "-") + r"}. Even columns add, each interacted with wave: age band, sex, "
          r"education (none, primary, secondary, tertiary), marital status, urban residence, household size and residence "
          r"in collective quarters. Standard "
          r"errors clustered by district in parentheses; wild cluster restricted bootstrap p-values (Webb weights, 9,999 "
          r"draws) in brackets; stars from the bootstrap p-values: *** 1\%, ** 5\%, * 10\%.",
          r"\end{minipage}", r"\end{table}", ""]
    (P.TABLES_REG / f"census_park_gap_person{_suffix()}.tex").write_text("\n".join(L))


def mover(d: pd.DataFrame) -> pd.Series:
    """1 if previous residence was another district or abroad (2012, 2022). NaN in 2002, where previous residence
    is recorded in the pre-2006 districts. A lower bound on in-migration: moves within a district are missed."""
    out = pd.Series(np.nan, index=d.index)
    m = d.census_year == 2012
    pr = d.loc[m, "census_previous_residence_2012"]
    out[m] = (pr.notna() & (pr != d.loc[m, "census_district"]) & (pr != 0)).astype(float)
    m = d.census_year == 2022
    ab = d.loc[m, "census_previous_in_rwanda_2022"] == 2
    pdist = d.loc[m, "census_previous_district_2022"]
    out[m] = (ab | (pdist.notna() & (pdist != d.loc[m, "census_district"]))).astype(float)
    return out


def _person_data():
    """Residents aged 16+ outside Kigali (and outside the ring with --drop-ring), with outcomes, household size,
    the collective-quarters flag, the mover flag and the equal-sector-wave weights."""
    parts = []
    for chunk, _ in pyreadstat.read_file_in_chunks(pyreadstat.read_dta, str(CENSUS), chunksize=500_000, usecols=PERSON_COLS):
        parts.append(chunk[chunk.census_year.isin(WAVES)])
    d = pd.concat(parts, ignore_index=True)
    size = d.groupby(["census_year", "census_household_id"], dropna=True).census_age.transform("size")
    d["collective"] = size.isna()
    d["hh_size"] = size.astype(float).fillna(0.0)
    d = d[(d.census_age >= 16) & ~d.census_district.isin(KIGALI)].reset_index(drop=True)
    if DROP_RING:
        d = d[~d.census_sector.astype(int).isin(ring_sectors())].reset_index(drop=True)
    d = d.join(classify(d))
    d["sid"], d["wave"] = d.census_sector.astype(int), d.census_year.astype(int)
    d["park"] = d.sid.map(pd.read_csv(SECTORS).set_index("sid").border)
    d["mover"] = mover(d)
    return d


def _person_controls(d: pd.DataFrame, waves) -> pd.DataFrame:
    edu, mar = education_group(d).astype(object), marital_group(d).astype(object)
    bands = pd.cut(d.census_age, [15, 19, 24, 29, 34, 39, 44, 49, 54, 59, 64, 200], labels=False)
    base = {"female": (d.census_sex == 2), "urban": (d.census_urban == 1), "household size": d.hh_size,
            "collective quarters": d.collective}
    for b in range(11):
        if b != 3:
            base[f"age band {b}"] = bands == b
    for k in ("none", "secondary", "tertiary", "not stated"):
        base[f"education {k}"] = edu == k
    for k in ("never", "divorced", "widowed", "not stated"):
        base[f"marital {k}"] = mar == k
    X = {f"{k} x {t}": np.asarray(pd.Series(v).to_numpy(dtype=float, na_value=np.nan)) * (d.wave == t).to_numpy(dtype=float)
         for k, v in base.items() for t in waves}
    return pd.DataFrame(X).loc[:, lambda x: x.std() > 0]


def _run_person(d, specs: dict, test: list) -> pd.DataFrame:
    """Weighted within regression (sector and wave fixed effects) of each outcome on each spec's columns."""
    w = (d.census_weight / d.groupby(["sid", "wave"]).census_weight.transform("sum")).to_numpy()
    r = np.sqrt(w / w.mean())
    gi = [pd.factorize(d.sid)[0], pd.factorize(d.wave)[0]]
    rows = []
    for y, label in OUTCOMES:
        yv = 100 * d[y.replace("_per100", "")].to_numpy(float)
        for spec, Z in specs.items():
            Zn = Z.to_numpy(dtype=float, na_value=np.nan)
            bad = [c for c, ok in zip(Z.columns, np.isfinite(Zn).all(axis=0)) if not ok]
            if bad:
                raise ValueError(f"{label}, {spec}: missing values in {bad}")
            A = _demean(np.column_stack([yv, Zn]), gi, w) * r[:, None]
            df = pd.DataFrame(A[:, 1:], columns=Z.columns)
            df["y"], df["district"] = A[:, 0], d.census_district.to_numpy()
            est, n, G = fe_ols(df, "y", list(Z.columns), [], "district", test=test)
            if n != len(d):
                raise ValueError(f"{label}, {spec}: regression used {n:,} of {len(d):,} observations")
            for v in test:
                e = est.loc[v]
                rows.append({"outcome": y, "label": label, "spec": spec, "term": v, "coef": e.coef, "se": e.se,
                             "p_wcb": e.p_wcb, "obs": n, "clusters": G})
            _log(f"  {label}, {spec}: " + ", ".join(f"{v} {est.loc[v, 'coef']:+.2f} [{est.loc[v, 'p_wcb']:.3f}]" for v in test))
    return pd.DataFrame(rows)


def section_migration():
    """2012 and 2022 only. Park coefficient = change in the park-adjacent minus interior gap from 2012 to 2022."""
    d = _person_data()
    d = d[d.wave.isin([2012, 2022])].reset_index(drop=True)
    _log(f"{len(d):,} residents aged 16+ in {d.sid.nunique()} sectors, 2012 and 2022; "
         f"moved in from another district or abroad: {np.average(d.mover, weights=d.census_weight):.1%}")
    T = pd.DataFrame({"park_x_2022": (d.park * (d.wave == 2022)).to_numpy(float)})
    X = _person_controls(d, (2012, 2022))
    M = pd.DataFrame({f"mover x {t}": (d.mover * (d.wave == t)).to_numpy(float) for t in (2012, 2022)})
    res = _run_person(d, {"no controls": T, "controls": pd.concat([T, X], axis=1),
                          "controls and mover": pd.concat([T, X, M], axis=1)}, ["park_x_2022"])
    res["level"] = "person"
    # sector level: in-mover share x wave
    sec = d.assign(wm=d.mover * d.census_weight).groupby(["sid", "wave"]).agg(
        movers=("wm", "sum"), adults=("census_weight", "sum")).reset_index()
    sec["mover_share"] = 100 * sec.movers / sec.adults
    p = pd.read_csv(PANEL).merge(sec[["sid", "wave", "mover_share"]], on=["sid", "wave"])
    p = p.merge(pd.read_csv(SECTORS)[["sid", "district_id", "border"]], on="sid")
    p["park_x_2022"] = p.border * (p.wave == 2022)
    p["mover_share_x_2022"] = p.mover_share * (p.wave == 2022)
    srows = []
    for y, label in OUTCOMES:
        for spec, xs in (("no controls", ["park_x_2022"]), ("mover share", ["park_x_2022", "mover_share", "mover_share_x_2022"])):
            est, n, G = fe_ols(p, y, xs, ["sid", "wave"], "district_id", test=["park_x_2022"])
            e = est.loc["park_x_2022"]
            srows.append({"outcome": y, "label": label, "spec": spec, "term": "park_x_2022", "coef": e.coef, "se": e.se,
                          "p_wcb": e.p_wcb, "obs": n, "clusters": G, "level": "sector"})
            _log(f"  sector, {label}, {spec}: park_x_2022 {e.coef:+.2f} [{e.p_wcb:.3f}]")
    res = pd.concat([res, pd.DataFrame(srows)], ignore_index=True)
    res.to_csv(P.TABLES_REG / f"census_park_gap_migration{_suffix()}.csv", index=False)
    tex_migration(res, p.sid.nunique(), int(p.drop_duplicates("sid").border.sum()))
    _log(f"-> {P.TABLES_REG / f'census_park_gap_migration{_suffix()}.csv'} and .tex")


def tex_migration(res: pd.DataFrame, n_sec: int, n_park: int):
    labels = [l for _, l in OUTCOMES]
    cols = [("person", "no controls"), ("person", "controls"), ("person", "controls and mover"),
            ("sector", "no controls"), ("sector", "mover share")]
    get = lambda l, lev, sp, k: res[(res.label == l) & (res.level == lev) & (res.spec == sp)].iloc[0][k]
    L = [r"\begin{table}[htbp]", r"\centering",
         r"\caption{Change in the Park-Adjacent Gap, 2012--2022, Controlling for In-Migration" + (", Excluding the Ring}" if DROP_RING else "}"),
         r"\label{tab:census_park_gap_migration" + _suffix().replace("_", "-") + "}",
         r"\begin{tabular}{l" + "c" * len(cols) + "}", r"\toprule",
         r" & \multicolumn{3}{c}{Person level} & \multicolumn{2}{c}{Sector level} \\",
         r"\cmidrule(lr){2-4} \cmidrule(lr){5-6}",
         " & " + " & ".join(f"({i + 1})" for i in range(len(cols))) + r" \\", r"\midrule"]
    for l in labels:
        L.append(f"\\textit{{{l}}} & & & & & \\\\")
        L.append("Park-adjacent $\\times$ 2022 & " + " & ".join(f"${get(l, lev, sp, 'coef'):.2f}{_stars(get(l, lev, sp, 'p_wcb'))}$" for lev, sp in cols) + r" \\")
        L.append(" & " + " & ".join(f"$({get(l, lev, sp, 'se'):.2f})$" for lev, sp in cols) + r" \\")
        L.append(" & " + " & ".join(f"$[{get(l, lev, sp, 'p_wcb'):.3f}]$" for lev, sp in cols) + r" \\")
    L += [r"\midrule",
          r"Person and household controls $\times$ wave & No & Yes & Yes & -- & -- \\",
          r"Moved in from another district or abroad $\times$ wave & No & No & Yes & -- & -- \\",
          r"Sector share of in-movers $\times$ wave & -- & -- & -- & No & Yes \\",
          f"Sectors (park-adjacent) & \\multicolumn{{5}}{{c}}{{{n_sec} ({n_park})}} \\\\",
          r"\bottomrule", r"\end{tabular}", r"\begin{minipage}{0.95\textwidth}\footnotesize",
          r"\textit{Notes:} 2012 and 2022 Census public-use samples, residents aged 16 and over outside Kigali City"
          + (" and the ring of sectors touching a park-adjacent sector" if DROP_RING else "") + r". 2002 is left out because "
          r"it records previous residence in the pre-2006 districts. Outcomes as in Table~\ref{tab:census_park_gap}; "
          r"the coefficient is the change in the park-adjacent minus interior gap from 2012 to 2022. A mover is a resident "
          r"whose previous residence was another district or abroad; moves within a district are not recorded, so this is a "
          r"lower bound on in-migration. All columns include sector and wave fixed effects. Columns (1)--(3): person level, "
          r"each sector-wave weighted equally; column (2) adds age band, sex, education, marital status, urban residence, "
          r"household size and collective quarters, each by wave. Columns (4)--(5): sector level, workers per 100 adults; "
          r"column (5) adds the sector's share of adults who moved in, by wave. Migration may itself respond to jobs, so "
          r"columns (3) and (5) show the gap net of who moved in. Standard errors clustered by district in parentheses; wild "
          r"cluster restricted bootstrap p-values in brackets; *** 1\%, ** 5\%, * 10\%.",
          r"\end{minipage}", r"\end{table}", ""]
    (P.TABLES_REG / f"census_park_gap_migration{_suffix()}.tex").write_text("\n".join(L))


EICV = P.NISR / "Household-Living-Conditions-EICV/3_Final/EICV_pooled_person.dta"
EICV_PAIRS = {2002: ("EICV2", "eicv_industry_group"), 2012: ("EICV4_CS", "eicv_industry_isic_shipped"),
              2022: ("EICV7_CS", "eicv_isic_level1_2024")}


def eicv_nonfarm(d: pd.DataFrame, col: str) -> pd.Series:
    """1 if the main job is outside agriculture, forestry and fishing. EICV2 uses NISR's two-digit industry
    groups (11-14 farm, 0 inadequately described); EICV4 and EICV7 use ISIC Rev. 4 sections (1 = A)."""
    v = d[col]
    if col == "eicv_industry_group":
        return (v >= 21).astype(int)
    return v.between(2, 21).astype(int)


def section_eicv_check():
    cols = ["eicv_wave", "eicv_district", "eicv_age", "eicv_weight"] + [c for _, c in EICV_PAIRS.values()]
    e, _ = pyreadstat.read_dta(str(EICV), usecols=cols)
    e = e[e.eicv_age >= 16]
    rows = []
    for year, (wave, col) in EICV_PAIRS.items():
        g = e[e.eicv_wave == wave].copy()
        g["nf"] = eicv_nonfarm(g, col) * g.eicv_weight
        r = g.groupby("eicv_district").agg(nf=("nf", "sum"), adults=("eicv_weight", "sum"), n=("eicv_age", "size"))
        r["eicv_nonfarm_per100"] = 100 * r.nf / r.adults
        r["census_year"], r["eicv_round"], r["eicv_respondents"] = year, wave, r.n
        rows.append(r.reset_index().rename(columns={"eicv_district": "district_id"}))
    ev = pd.concat(rows)[["district_id", "census_year", "eicv_round", "eicv_respondents", "eicv_nonfarm_per100"]]
    p = pd.read_csv(PANEL).merge(pd.read_csv(SECTORS)[["sid", "district_id"]], on="sid")
    c = p.groupby(["district_id", "wave"])[["nonfarm", "adults"]].sum().reset_index()
    c["census_nonfarm_per100"] = 100 * c.nonfarm / c.adults
    m = c.rename(columns={"wave": "census_year"})[["district_id", "census_year", "census_nonfarm_per100"]].merge(
        ev, on=["district_id", "census_year"])
    m = m[~m.district_id.isin(KIGALI)]
    m.to_csv(P.TABLES_REG / "census_eicv_nonfarm_check.csv", index=False)
    for y, g in m.groupby("census_year"):
        _log(f"Census {y} vs {g.eicv_round.iloc[0]}: {len(g)} districts; correlation "
             f"{g.census_nonfarm_per100.corr(g.eicv_nonfarm_per100):.2f}; mean per 100 adults, Census "
             f"{g.census_nonfarm_per100.mean():.1f} vs EICV {g.eicv_nonfarm_per100.mean():.1f}")
    w = m.pivot(index="district_id", columns="census_year", values=["census_nonfarm_per100", "eicv_nonfarm_per100"])
    for a, b in ((2002, 2012), (2012, 2022)):
        dc = w["census_nonfarm_per100"][b] - w["census_nonfarm_per100"][a]
        de = w["eicv_nonfarm_per100"][b] - w["eicv_nonfarm_per100"][a]
        _log(f"change {a}-{b}: correlation of district changes, Census vs EICV {dc.corr(de):.2f}; "
             f"mean change Census {dc.mean():+.1f}, EICV {de.mean():+.1f}")
    _log(f"-> {P.TABLES_REG / 'census_eicv_nonfarm_check.csv'}")

# ---------------------------------------------------------------------------- levels, controlling for population
def section_levels():
    """Worker counts (not rates) by sector and wave, controlling for log adults.
        y_st = a_s + g_t + sum_t b_t Park_s 1[t] (+ sum_t d_t Park_s (Share_s - mean) 1[t]) + lam log(adults_st) + e_st
    y = number of non-farm, services, tourism and farm workers (Census-weighted). Share = park_overlap / sector area
    (model_sector_cross.csv, park_share), centred at its mean among the park-adjacent sectors in the sample.
    Farm workers: in 2022 farming counts as work only if mainly for the market, so farm counts fall in every sector.
    Wave fixed effects absorb a common fall but not one that differs by sector, so farm is run on 2002 and 2012 only
    (main) and on all three waves (flagged). Log adults is itself an outcome of the programme (see section gap), so
    b_t is the gap in workers at a given population, net of the population channel."""
    p = pd.read_csv(PANEL)
    if "farm" not in p:
        raise SystemExit("panel has no farm column: run --only outcomes first")
    s = pd.read_csv(SECTORS)[["sid", "district_id", "border", "park_share"]]
    d = p.merge(s, on="sid", how="left")
    d["log_adults"] = np.log(d.adults)
    d = d[~d.district_id.isin(KIGALI)].copy()
    if DROP_RING:
        d = d[~d.sid.isin(ring_sectors())].copy()
    centre = d.loc[d.border == 1, "park_share"].mean()
    d["share_c"] = d.border * (d.park_share - centre)
    for t in (2012, 2022):
        d[f"park_x_{t}"] = d.border * (d.wave == t)
        d[f"share_x_{t}"] = d.share_c * (d.wave == t)
    _log(f"{d.sid.nunique()} sectors ({int(d.drop_duplicates('sid').border.sum())} park-adjacent); park share centred at {centre:.3f}")
    runs = [("nonfarm", "Non-farm workers", (2002, 2012, 2022)), ("services", "Services workers", (2002, 2012, 2022)),
            ("tourism", "Tourism workers", (2002, 2012, 2022)), ("farm", "Farm workers", (2002, 2012)),
            ("farm", "Farm workers", (2002, 2012, 2022))]
    rows = []
    for y, label, waves in runs:
        g = d[d.wave.isin(waves)]
        ts = [t for t in (2012, 2022) if t in waves]
        sample = "-".join(str(w) for w in (waves[0], waves[-1])) if len(waves) == 2 else "all three waves"
        for spec, terms in (("border", [f"park_x_{t}" for t in ts]),
                            ("border and share", [f"{k}_x_{t}" for t in ts for k in ("park", "share")])):
            xs = terms + ["log_adults"]
            est, n, G = fe_ols(g, y, xs, ["sid", "wave"], "district_id", test=terms)
            means = g.groupby(["wave", "border"])[y].mean().unstack()
            for term in terms:
                e = est.loc[term]
                t = int(term[-4:])
                rows.append({"outcome": y, "label": label, "sample": sample, "spec": spec, "term": term, "coef": e.coef,
                             "se": e.se, "p_wcb": e.p_wcb,
                             "mean_park_2002": means.loc[2002, 1], "mean_interior_2002": means.loc[2002, 0],
                             "mean_park_wave": means.loc[t, 1], "mean_interior_wave": means.loc[t, 0],
                             "log_adults_coef": est.loc["log_adults", "coef"],
                             "log_adults_se": est.loc["log_adults", "se"], "obs": n, "clusters": G})
            _log("  " + f"{label}, {sample}, {spec}: " + ", ".join(
                f"{t} {est.loc[t, 'coef']:+.1f} [{est.loc[t, 'p_wcb']:.3f}]" for t in terms)
                 + f"; log adults {est.loc['log_adults', 'coef']:.0f}")
    res = pd.DataFrame(rows)
    P.TABLES_REG.mkdir(parents=True, exist_ok=True)
    res.to_csv(P.TABLES_REG / f"census_park_levels{_suffix()}.csv", index=False)
    _log(f"-> {P.TABLES_REG / f'census_park_levels{_suffix()}.csv'}")

    # Level gap within each wave: no sector fixed effects, so the coefficient compares park-adjacent with interior
    # sectors in the same wave at the same population (not a change since 2002). Wave fixed effects absorb anything
    # common to a wave, including the 2022 change in what counts as farm work; district fixed effects in the second
    # specification compare sectors within the same district.
    for t in WAVES:
        d[f"parkw_{t}"] = d.border * (d.wave == t)
    terms = [f"parkw_{t}" for t in WAVES]
    gap_rows = []
    for y, label in [(r[0], r[1]) for r in runs[:4]]:
        for spec, fes in (("wave FE", ["wave"]), ("wave and district FE", ["wave", "district_id"])):
            est, n, G = fe_ols(d, y, terms + ["log_adults"], fes, "district_id", test=terms)
            for t, term in zip(WAVES, terms):
                m = d[d.wave == t].groupby("border")[y].mean()
                e = est.loc[term]
                gap_rows.append({"outcome": y, "label": label, "spec": spec, "wave": t, "coef": e.coef, "se": e.se,
                                 "p_wcb": e.p_wcb, "mean_park": m[1], "mean_interior": m[0],
                                 "log_adults_coef": est.loc["log_adults", "coef"], "obs": n, "clusters": G})
            _log("  level gap " + f"{label}, {spec}: " + ", ".join(
                f"{t} {est.loc[f'parkw_{t}', 'coef']:+.0f} [{est.loc[f'parkw_{t}', 'p_wcb']:.3f}]" for t in WAVES))
    pd.DataFrame(gap_rows).to_csv(P.TABLES_REG / f"census_park_levels_gap{_suffix()}.csv", index=False)
    _log(f"-> {P.TABLES_REG / f'census_park_levels_gap{_suffix()}.csv'}")



# ============================================================================ geography, per-wave questions (default), tables, legacy designs
# Everything below was split over census_park_questions.py, census_park_status.py, census_park_logs.py, park_land_regressions.py
# and sector_question_tables.py; one file now. Default sections: outcomes, questions. Retired change-from-baseline designs
# (sector fixed effects, 2002 / 2000 base): gap, person, migration, levels, eicv_check, status, logs, land, shift, opening --
# run with --legacy or --only <name>.

LAND_PATH = P.HARM_PANELS / "sector_cropland_builtup_glclu.csv"
GHSL_PATH = P.HARM_PANELS / "sector_ghsl_built.csv"
RDB = P.HARMONIZED / "rwanda-parks-tourism-rdb.xlsx"
ALL_YEARS = False                       # set by --all-years (section land)

STATUS = P.HARMONIZED / "district" / "sector-labour-status.csv"
STATUS_OUTCOMES = [("wage100", "Wage employees"), ("self100", "Self-employed"), ("family100", "Family workers"),
                   ("other100", "Other status"), ("workers100", "All workers")]

LOG_TERMS = ["park_x_2012", "park_x_2022"]
STAT = [("wage", "Wage employees"), ("self", "Self-employed"), ("family", "Family workers"), ("other", "Other status")]
LOG_ROWS = []

XVARS = ["log_area", "log_dist_road", "log_dist_kigali", "elev_mean", "slope_mean", "rain_mean"]
X_LABEL = "log area, log distance to road, log distance to Kigali, elevation, slope, rainfall (z-scored)"
INDUSTRY = [("nonfarm", "Non-farm workers"), ("services", "Services workers"), ("tourism", "Tourism workers"), ("farm", "Farm workers")]
LAND_Y = [("crop_pp", "Cropland share (pp)"), ("built_pp", "Built-up share (pp)"), ("log_built", "ln(1 + built-up ha)")]
BINS = [("gate_lt10", 0, 10), ("gate_10_20", 10, 20), ("gate_20_40", 20, 40)]

Q_ROWS = []



def hav(lon1, lat1, lon2, lat2):
    r = np.radians
    a = np.sin(r(lat2 - lat1) / 2) ** 2 + np.cos(r(lat1)) * np.cos(r(lat2)) * np.sin(r(lon2 - lon1) / 2) ** 2
    return 6371 * 2 * np.arcsin(np.sqrt(a))



def controls() -> pd.DataFrame:
    """Sector attributes and z-scored controls for the 381 sectors outside Kigali, plus distance to the nearest gate."""
    c = pd.read_csv(SECTORS)[["sid", "district_id", "border", "nearest_park", "unit_km2", "lon", "lat"]]
    c = c[~c.district_id.isin(KIGALI)].copy()
    c["log_area"] = np.log(c.unit_km2)
    for f, cols in [("roads/sector_distances.csv", ["log_dist_road", "log_dist_kigali"]),
                    ("raster/sector_terrain.csv", ["elev_mean", "slope_mean"]), ("raster/sector_rainfall.csv", ["rain_mean"])]:
        c = c.merge(pd.read_csv(P.GEO / f)[["sid"] + cols], on="sid", how="left", validate="1:1")
    assert c[XVARS].notna().all().all() and len(c) == 381
    c[XVARS] = (c[XVARS] - c[XVARS].mean()) / c[XVARS].std()
    km = np.column_stack([hav(c.lon, c.lat, *xy) for xy in TG.GATE_XY.values()]).min(axis=1)
    for name, lo, hi in BINS:
        c[name] = ((km > lo) & (km <= hi)).astype(int) if lo else (km <= hi).astype(int)
    c["km_gate"] = km
    return c.drop(columns=["lon", "lat", "unit_km2"])


def question_panel(x) -> pd.DataFrame:
    d = pd.read_csv(PANEL)[["sid", "wave", "adults", "nonfarm", "services", "tourism", "farm"]]
    d = d.merge(x, on="sid", validate="m:1")
    d["log_adults"] = np.log(d.adults)
    return d[~d.sid.isin(_ring())].copy() if DROP_RING else d


# ---------------------------------------------------------------------------- estimators
def ols(d, y, xs, fes, test):
    est, n, g = fe_ols(d, y, xs, fes, "district_id", test=test)
    return est.rename(columns={"p_wcb": "p"}), n, g


def poisson(d, y, xs, fes):
    """Poisson, log link; FE as dummies; groups with no positive outcome dropped; cluster-robust (district) normal p."""
    d = d.copy()
    while True:
        keep = np.ones(len(d), bool)
        for f in fes:
            keep &= (d.groupby(f)[y].transform("sum") > 0).values
        if keep.all():
            break
        d = d[keep]
    X = pd.concat([d[xs]] + [pd.get_dummies(d[f], prefix=f, drop_first=True, dtype=float) for f in fes], axis=1)
    m = sm.GLM(d[y], sm.add_constant(X), family=sm.families.Poisson()).fit(
        cov_type="cluster", cov_kwds={"groups": pd.factorize(d.district_id)[0]}, maxiter=200)
    r = pd.DataFrame({"coef": m.params, "se": m.bse, "p": m.pvalues}).loc[xs]
    return r, int(len(d)), d.district_id.nunique()


def record(q, spec, y, label, est, n, g, focal, kind, ptype, controls_, fe, wave):
    for t in focal:
        e = est.loc[t]
        Q_ROWS.append({"question": q, "spec": spec, "outcome": y, "label": label, "estimator": kind, "p_type": ptype, "term": t,
                     "wave": wave, "coef": e.coef, "se": e.se, "p": e.p, "log_adults_coef": est.loc["log_adults", "coef"] if "log_adults" in est.index else np.nan,
                     "obs": n, "clusters": g, "controls": controls_, "fixed_effects": fe})
    _log(f"[questions]   {wave} | {spec} | {label} ({kind}): " + ", ".join(f"{t} {est.loc[t,'coef']:+.3f} [{est.loc[t,'p']:.3f}]" for t in focal))


def run_count(d, y, label, q, spec, terms, ctrl, fes, controls_, wave):
    """Count outcome, per wave: OLS on ln(y) (bootstrap p) if y > 0 everywhere, otherwise Poisson."""
    xs = terms + ["log_adults"] + ctrl
    if (d[y] > 0).all():
        est, n, g = ols(d.assign(ln_y=np.log(d[y])), "ln_y", xs, fes, terms)
        record(q, spec, y, label, est, n, g, terms, "OLS on ln(workers)", "wild cluster bootstrap", controls_, "+".join(fes), wave)
    else:
        est, n, g = poisson(d, y, xs, fes)
        record(q, spec, y, label, est, n, g, terms, "Poisson", "cluster-robust normal", controls_, "+".join(fes), wave)


# ---------------------------------------------------------------------------- questions
def q1(x):
    _log("[questions] Q1 per wave: ln workers on Park, ln adults, district FE [+ X]")
    d = question_panel(x)
    for t in WAVES:
        w = d[d.wave == t]
        _log(f"[questions]  Q1 {t}: {len(w)} sectors ({int(w.border.sum())} park-adjacent)")
        for spec, ctrl in [("(1) ln adults", []), ("(2) ln adults + X", XVARS)]:
            for y, lab in INDUSTRY:
                run_count(w, y, lab, "Q1", spec, ["border"], ctrl, ["district_id"], "ln(adults)" + (f"; {X_LABEL}" if ctrl else ""), t)


def q2(x):
    _log("[questions] Q2 per wave: gate-distance bins, nearest-park FE")
    d = question_panel(x)
    terms = [b[0] for b in BINS]
    for t in WAVES:
        w = d[d.wave == t]
        _log(f"[questions]  Q2 {t}: {len(w)} sectors; " + ", ".join(f"{b[0]} {int(w[b[0]].sum())}" for b in BINS))
        for spec, tm in [("(1) bins", terms), ("(2) bins + Park", terms + ["border"])]:
            for y, lab in INDUSTRY:
                run_count(w, y, lab, "Q2", spec, tm, XVARS, ["nearest_park"], f"ln(adults); {X_LABEL}", t)


def q3(x):
    _log("[questions] Q3 per wave: visit-share exposure E_s, district FE [+ X]")
    s = exposure_sectors()[["sid", "exposure", "gm"]]
    d = question_panel(x).merge(s, on="sid", validate="m:1")
    d = d[d.gm == 0]
    for t in WAVES:
        w = d[d.wave == t]
        _log(f"[questions]  Q3 {t}: {len(w)} sectors (Gishwati-Mukura dropped)")
        for spec, ctrl in [("(1) ln adults", []), ("(2) ln adults + X", XVARS)]:
            for y, lab in INDUSTRY:
                run_count(w, y, lab, "Q3", spec, ["exposure"], ctrl, ["district_id"], "ln(adults)" + (f"; {X_LABEL}" if ctrl else ""), t)


def q4(x):
    _log("[questions] Q4 per land-cover year: land outcomes on Park, district FE [+ X]")
    d = land_panel()
    d = d[d.year.isin((2000, 2010, 2020))].drop(columns=["border", "district_id", "nearest_park"]).merge(
        x[["sid", "district_id", "border", "nearest_park"] + XVARS], on="sid", validate="m:1")
    d = d[~d.sid.isin(_ring())] if DROP_RING else d
    for t in (2000, 2010, 2020):
        w = d[d.year == t]
        _log(f"[questions]  Q4 {t}: {len(w)} sectors ({int(w.border.sum())} park-adjacent)")
        for spec, ctrl in [("(1) none", []), ("(2) X", XVARS)]:
            for y, lab in LAND_Y:
                est, n, g = ols(w, y, ["border"] + ctrl, ["district_id"], ["border"])
                record("Q4", spec, y, lab, est, n, g, ["border"], "OLS, level", "wild cluster bootstrap",
                       "none" + "" if not ctrl else X_LABEL, "district_id", t)



_RING = None


def _ring() -> set:
    global _RING
    if _RING is None:
        _RING = ring_sectors()
    return _RING


QUESTIONS = {"Q1": q1, "Q2": q2, "Q3": q3, "Q4": q4}


def section_questions():
    x = controls()                                   # z-scored over all 381 sectors, also with --drop-ring
    _log(f"[questions] {len(x[~x.sid.isin(_ring())]) if DROP_RING else len(x)} sectors{' (ring dropped)' if DROP_RING else ''}")
    for k in QUESTIONS:
        QUESTIONS[k](x)
    P.TABLES_REG.mkdir(parents=True, exist_ok=True)
    out = P.TABLES_REG / f"census_park_questions{_suffix()}.csv"
    pd.DataFrame(Q_ROWS).to_csv(out, index=False)
    _log(f"-> {out}")
    tex_questions()



# ---- tables for the questions

GEO = "log area, log distance to the nearest trunk or primary road, log distance to Kigali, mean elevation, mean slope and mean rainfall (each standardised)"
OUTS = [("nonfarm", "Non-farm"), ("services", "Services"), ("tourism", "Tourism"), ("farm", "Farm")]
LAND_TAB = [("built_pp", "Built-up share"), ("crop_pp", "Cropland share"), ("log_built", "ln(1 + built-up ha)")]


def tex_star(p):
    return "***" if p < .01 else "**" if p < .05 else "*" if p < .1 else ""


def tex_fmt(v, d=3):
    return ("$-$" if v < 0 and round(abs(v), d) != 0 else "") + f"{abs(v):,.{d}f}"


def tex_cells(row):
    if row is None:
        return "", "", ""
    return f"{tex_fmt(row.coef)}$^{{{tex_star(row.p)}}}$" if tex_star(row.p) else tex_fmt(row.coef), f"({tex_fmt(row.se)})", f"[{row.p:.3f}]"


def tex_pick(df, **kw):
    for k, v in kw.items():
        df = df[df[k] == v]
    return df.iloc[0] if len(df) else None


def tex_block(label, rows):
    c = [tex_cells(r) for r in rows]
    return [f"{label} & " + " & ".join(x[0] for x in c) + r" \\", " & " + " & ".join(x[1] for x in c) + r" \\",
            " & " + " & ".join(x[2] for x in c) + r" \\"]


def tex_table(caption, label, groups, panels, footer, notes, ncols):
    head1 = " & " + " & ".join(rf"\multicolumn{{2}}{{c}}{{{g}}}" for g in groups) + r" \\"
    cm = " ".join(rf"\cmidrule(lr){{{2 * i + 2}-{2 * i + 3}}}" for i in range(len(groups)))
    head2 = " & " + " & ".join(f"({i + 1})" for i in range(ncols)) + r" \\"
    return "\n".join([r"\begin{table}[H]", r"\centering\footnotesize\setlength{\tabcolsep}{3pt}", rf"\caption{{{caption}}}", rf"\label{{{label}}}",
                      r"\resizebox{\textwidth}{!}{%", rf"\begin{{tabular}}{{l{'c' * ncols}}}", r"\toprule", head1, cm, head2, r"\midrule", *panels, r"\midrule", *footer, r"\bottomrule",
                      r"\end{tabular}}", r"\begin{minipage}{0.97\textwidth}\scriptsize", rf"\textit{{Notes:}} {notes}", r"\end{minipage}", r"\end{table}"])


SE_NOTE = (r"Standard errors clustered by district (27 clusters) in parentheses. In OLS columns, brackets give wild cluster restricted bootstrap p-values "
           r"(Webb weights, 9,999 draws); in the tourism columns (Poisson), cluster-robust normal p-values. Stars follow the bracketed p-values: *** $p<0.01$, ** $p<0.05$, * $p<0.1$.")


def tex_count_table(df, q, terms, caption, label, fe, extra_note, sample_note):
    """Count outcomes, one panel per wave. terms: [(term, row label)]."""
    panels = []
    for t in WAVES:
        panels.append(rf"\multicolumn{{9}}{{l}}{{\textit{{Panel {'ABC'[WAVES.index(t)]}. Census {t}}}}} \\")
        for term, lab in terms:
            panels += tex_block(lab, [tex_pick(df, question=q, wave=t, term=term, outcome=o, spec=s)
                                  for o, _ in OUTS for s in (df[df.question == q].spec.unique()[:2])])
        la = [tex_pick(df, question=q, wave=t, outcome=o, spec=s, term=terms[0][0]) for o, _ in OUTS for s in df[df.question == q].spec.unique()[:2]]
        panels += [r"ln(adults) & " + " & ".join(tex_fmt(r.log_adults_coef, 2) for r in la) + r" \\",
                   "Observations & " + " & ".join(f"{int(r.obs):,}" for r in la) + r" \\"]
        if t != WAVES[-1]:
            panels.append(r"\addlinespace")
    footer = ["Geography controls & " + " & ".join(["No", "Yes"] * 4) + r" \\", f"Fixed effects & " + " & ".join([fe] * 8) + r" \\",
              "Estimator & " + " & ".join(["OLS", "OLS", "OLS", "OLS", "Poisson", "Poisson", "OLS", "OLS"]) + r" \\"]
    notes = (sample_note + r" Dependent variable: ln(number of workers) by industry of main work (non-farm, services, farm; Census-weighted); "
             r"for tourism, the number of workers (Poisson, log link, so coefficients are also proportional differences). One OLS regression per wave and column, "
             rf"on sectors outside Kigali City. ln(adults) is the log of residents aged 16 and over; its coefficient is an elasticity. Geography controls: {GEO}. " + extra_note + " " + SE_NOTE)
    return tex_table(caption, label, [n for _, n in OUTS], panels, footer, notes, 8)


def tex_land_table(df, caption, label, sample_note):
    panels = []
    for t in (2000, 2010, 2020):
        panels.append(rf"\multicolumn{{7}}{{l}}{{\textit{{Panel {'ABC'[(2000, 2010, 2020).index(t)]}. {t}}}}} \\")
        panels += tex_block("Park-adjacent", [tex_pick(df, question="Q4", wave=t, term="border", outcome=o, spec=s) for o, _ in LAND_TAB for s in ("(1) none", "(2) X")])
        panels.append("Observations & " + " & ".join(f"{int(tex_pick(df, question='Q4', wave=t, term='border', outcome=o, spec=s).obs):,}" for o, _ in LAND_TAB for s in ("(1) none", "(2) X")) + r" \\")
        if t != 2020:
            panels.append(r"\addlinespace")
    footer = ["Geography controls & " + " & ".join(["No", "Yes"] * 3) + r" \\", "Fixed effects & " + " & ".join(["District"] * 6) + r" \\"]
    notes = (sample_note + r" Dependent variables: built-up share and cropland share of the sector's usable (non-park) land, in percentage points (GLAD land cover), and ln(1 + built-up hectares) (GHSL). "
             rf"One OLS regression per year and column. Geography controls: {GEO}. " + SE_NOTE.replace("; in the tourism columns (Poisson), cluster-robust normal p-values", ""))
    return tex_table(caption, label, [n for _, n in LAND_TAB], panels, footer, notes, 6)


def tex_build(suffix, ring):
    df = pd.read_csv(P.TABLES_REG / f"census_park_questions{suffix}.csv")
    samp = (r"Sample: 299 sectors outside Kigali City, dropping the 82 that touch a park-adjacent sector without bordering a park." if ring
            else r"Sample: 381 sectors outside Kigali City, of which 62 border a national park.")
    tag = " (Ring Dropped)" if ring else ""
    out = []
    out.append(tex_count_table(df, "Q1", [("border", "Park-adjacent")], "Workers in Park-Adjacent vs Interior Sectors, by Census Wave" + tag, "tab:q1" + suffix, "District",
                           r"Park-adjacent = the sector borders a national park; the coefficient is the proportional difference in workers relative to interior sectors of the same district, at the same number of adults.", samp))
    out.append(tex_count_table(df, "Q3", [("exposure", "Visit-share exposure")], "Exposure to Park Tourism and Workers, by Census Wave" + tag, "tab:q3" + suffix, "District",
                           r"Exposure = the nearest park's share of three-park visits 2005--2019 (Volcanoes 0.40, Akagera 0.46, Nyungwe 0.14) for park-adjacent sectors, 0 for others; Gishwati--Mukura sectors dropped (no visit data).",
                           (r"Sample: 279 sectors outside Kigali City, excluding the ring and the Gishwati--Mukura sectors." if ring else r"Sample: 361 sectors outside Kigali City, excluding the Gishwati--Mukura sectors.")))
    # gate bins: three panels, rows are bins (+ Park in even columns)
    g = df[df.question == "Q2"]
    for t in WAVES:
        panels = [rf"\multicolumn{{9}}{{l}}{{\textit{{Census {t}}}}} \\"]
        for term, lab in (("gate_lt10", r"Within 10 km of a gate"), ("gate_10_20", "10--20 km"), ("gate_20_40", "20--40 km"), ("border", "Park-adjacent")):
            panels += tex_block(lab, [tex_pick(g, wave=t, term=term, outcome=o, spec=s) for o, _ in OUTS for s in ("(1) bins", "(2) bins + Park")])
        la = [tex_pick(g, wave=t, term="gate_lt10", outcome=o, spec=s) for o, _ in OUTS for s in ("(1) bins", "(2) bins + Park")]
        panels += [r"ln(adults) & " + " & ".join(tex_fmt(r.log_adults_coef, 2) for r in la) + r" \\", "Observations & " + " & ".join(f"{int(r.obs):,}" for r in la) + r" \\"]
        footer = [r"Park-adjacent indicator & " + " & ".join(["No", "Yes"] * 4) + r" \\", "Geography controls & " + " & ".join(["Yes"] * 8) + r" \\",
                  "Fixed effects & " + " & ".join(["Nearest park"] * 8) + r" \\", "Estimator & " + " & ".join(["OLS", "OLS", "OLS", "OLS", "Poisson", "Poisson", "OLS", "OLS"]) + r" \\"]
        notes = (samp + r" Distance bins are from the sector centroid to the nearest of four park gates (Kinigi, Gisakura, Kitabi, Akagera South Gate); the omitted bin is 40 km or more (196 sectors; bin sizes 17, 43 and 125 sectors). "
                 r"Dependent variable: ln(number of workers) by industry of main work (tourism: number of workers, Poisson). One regression per wave and column; the fixed effect is the nearest park (five groups). "
                 rf"Geography controls: {GEO}. " + SE_NOTE)
        out.append(tex_table(f"Distance to a Park Gate and Workers, Census {t}" + tag, f"tab:q2_{t}" + suffix, [n for _, n in OUTS], panels, footer, notes, 8))
    out.append(tex_land_table(df, "Land Use in Park-Adjacent vs Interior Sectors, by Year" + tag, "tab:q4" + suffix, samp))
    return out



def tex_questions():
    """docs/sector_question_tables.tex: one table per question, a panel per wave, full sample then no ring (from the CSVs that exist)."""
    body = []
    for suffix, ring in (("", False), ("_no_ring", True)):
        if (P.TABLES_REG / f"census_park_questions{suffix}.csv").exists():
            body += tex_build(suffix, ring) + [r"\clearpage"]
    tex = "\n".join([r"\documentclass[11pt]{article}", r"\usepackage[margin=0.8in]{geometry}", r"\usepackage{booktabs,float,amsmath,graphicx}",
                     r"\usepackage[font=small,labelfont=bf]{caption}", r"\captionsetup[table]{position=top}", r"\begin{document}", *body, r"\end{document}"])
    p = ROOT / "docs" / "sector_question_tables.tex"
    p.write_text(tex)
    _log(f"-> {p}")



# ---- legacy: land use, tourism exposure and the Gishwati-Mukura opening (sector and year FE, 2000 / 2005 base)

SHARE_YEARS = (2005, 2019)                  # years of visits that set omega_p (before the 2020-21 collapse)
TOURIST_PARKS = {"Volcanoes National Park": "Volcanoes", "Akagera National Park": "Akagera",
                 "Nyungwe National Park": "Nyungwe"}
GM_PARKS = ("Gishwati", "Mukura")
OPENING_YEAR = 2015                         # Gishwati-Mukura National Park created
LAND_OUTCOMES = [("crop_pp", "Cropland share (pp)"), ("built_pp", "Built-up share (pp)"),
                 ("log_built", "Log built-up area (ha)")]
OUTCOMES = [("nonfarm_per100", "Non-farm workers"), ("services_per100", "Services workers"),
                   ("tourism_per100", "Tourism workers")]


def exposure_sectors() -> pd.DataFrame:
    """Sector attributes for the 381 sectors outside Kigali, with the exposure E_s and the Gishwati-Mukura flag."""
    s = pd.read_csv(SECTORS)[["sid", "district_id", "border", "nearest_park"]]
    s = s[~s.district_id.isin(KIGALI)].copy()
    v = pd.read_excel(RDB, sheet_name="visits_by_park")
    v = v[pd.to_numeric(v["year"], errors="coerce").between(*SHARE_YEARS)]
    tot = v[["Volcanoes", "Akagera", "Nyungwe"]].sum()
    omega = (tot / tot.sum()).to_dict()
    _log("omega_p (share of three-park visits, %d-%d): " % SHARE_YEARS + ", ".join(f"{k} {w:.3f}" for k, w in omega.items()))
    s["exposure"] = s.nearest_park.map(TOURIST_PARKS).map(omega).where(s.border == 1, 0.0)
    s["gm"] = ((s.border == 1) & s.nearest_park.isin(GM_PARKS)).astype(int)
    return s


def national_visits() -> pd.Series:
    """T_t: national park visits in 100,000s, 2005-2023, indexed by year."""
    v = pd.read_excel(RDB, sheet_name="visits_by_park")
    v = v[pd.to_numeric(v["year"], errors="coerce").notna()].copy()
    v["year"] = v["year"].astype(int)
    return (v.set_index("year")["All parks (published)"] / 1e5).dropna()


def land_panel() -> pd.DataFrame:
    """Sector x year (2000, 2005, ..., 2020): cropland and built-up shares in percentage points, log(1 + GHSL built ha)."""
    a = pd.read_csv(LAND_PATH, usecols=["sid", "year", "crop_sh", "built_sh"])
    g = pd.read_csv(GHSL_PATH, usecols=["sid", "year", "built_total_ha"])
    d = a.merge(g, on=["sid", "year"], how="inner", validate="1:1")
    d["crop_pp"], d["built_pp"] = 100 * d.crop_sh, 100 * d.built_sh
    d["log_built"] = np.log1p(d.built_total_ha)
    return d.merge(exposure_sectors(), on="sid", how="inner")


def exposure_census_panel() -> pd.DataFrame:
    d = pd.read_csv(PANEL).rename(columns={"wave": "year"})
    return d.merge(exposure_sectors(), on="sid", how="inner")


def land_run(d, outcomes, terms, section, spec, rows):
    """One regression per outcome; every term gets a wild-bootstrap p-value."""
    for y, label in outcomes:
        est, n, G = fe_ols(d, y, terms, ["sid", "year"], "district_id", test=terms)
        for t in terms:
            e = est.loc[t]
            rows.append({"section": section, "spec": spec, "outcome": y, "label": label, "term": t, "coef": e.coef,
                         "se": e.se, "p_wcb": e.p_wcb, "obs": n, "sectors": d.sid.nunique(), "clusters": G})
        _log(f"  {spec}, {label}: " + ", ".join(f"{t} {est.loc[t, 'coef']:+.3f} [{est.loc[t, 'p_wcb']:.3f}]" for t in terms))


def land_save(rows, name):
    P.TABLES_REG.mkdir(parents=True, exist_ok=True)
    path = P.TABLES_REG / f"park_land_{name}.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    _log(f"-> {path}")


def section_land():
    all_years = ALL_YEARS
    d = land_panel()
    years = (2000, 2005, 2010, 2015, 2020) if all_years else (2000, 2010, 2020)
    d = d[d.year.isin(years)].copy()
    terms = []
    for t in years[1:]:
        d[f"park_x_{t}"] = d.border * (d.year == t)
        terms.append(f"park_x_{t}")
    _log(f"land: {d.sid.nunique()} sectors, {int(d.drop_duplicates('sid').border.sum())} park-adjacent, years {years}")
    rows = []
    land_run(d, LAND_OUTCOMES, terms, "land", "five-year panel" if all_years else "2000-2010-2020", rows)
    land_save(rows, "land_all_years" if all_years else "land")


def section_shift():
    T = national_visits()
    rows = []
    # annual: land panel, years with a visit count
    d = land_panel()
    d = d[(d.year >= 2005) & (d.gm == 0)].copy()
    d["T"] = d.year.map(T)
    d["E_x_T"] = d.exposure * d["T"]
    _log(f"shift: {d.sid.nunique()} sectors (Gishwati-Mukura dropped); exposed sectors {int((d.drop_duplicates('sid').exposure > 0).sum())}; "
         f"T (100,000 visits) = " + ", ".join(f"{y}: {T[y]:.2f}" for y in sorted(d.year.unique())))
    land_run(d, LAND_OUTCOMES, ["E_x_T"], "shift", "annual, E x national visits", rows)
    ts = [t for t in sorted(d.year.unique()) if t > 2005]
    for t in ts:
        d[f"E_x_{t}"] = d.exposure * (d.year == t)
    land_run(d, LAND_OUTCOMES, [f"E_x_{t}" for t in ts], "shift", "by year, 2005 base", rows)
    # census waves
    c = exposure_census_panel()
    c = c[c.gm == 0].copy()
    for t in (2012, 2022):
        c[f"E_x_{t}"] = c.exposure * (c.year == t)
    land_run(c, OUTCOMES, ["E_x_2012", "E_x_2022"], "shift", "census waves, 2002 base", rows)
    land_save(rows, "shift")


def section_opening():
    rows = []
    d = land_panel()
    d = d[(d.border == 0) | (d.gm == 1)].copy()            # interior sectors and the Gishwati-Mukura sectors
    _log(f"opening: {d.sid.nunique()} sectors, {int(d.drop_duplicates('sid').gm.sum())} bordering Gishwati or Mukura")
    d["gm_post"] = d.gm * (d.year > OPENING_YEAR)
    land_run(d, LAND_OUTCOMES, ["gm_post"], "opening", f"land, post = year > {OPENING_YEAR}", rows)
    ts = [t for t in sorted(d.year.unique()) if t != 2010]
    for t in ts:
        d[f"gm_x_{t}"] = d.gm * (d.year == t)
    land_run(d, LAND_OUTCOMES, [f"gm_x_{t}" for t in ts], "opening", "land, by year, 2010 base", rows)
    c = exposure_census_panel()
    c = c[(c.border == 0) | (c.gm == 1)].copy()
    c["gm_post"] = c.gm * (c.year == 2022)
    land_run(c, OUTCOMES, ["gm_post"], "opening", "census waves, post = 2022", rows)
    land_save(rows, "opening")





# ---- legacy: employment status of main work (sector and wave FE, 2002 base)

def section_status():
    suffix = _suffix()
    s = pd.read_csv(STATUS).rename(columns={"sector_id": "sid", "year": "wave"})
    s["wage100"], s["self100"] = 100 * s.per_adult_wage, 100 * s.per_adult_self
    s["family100"], s["other100"] = 100 * s.per_adult_family, 100 * s.per_adult_other
    s["workers100"] = 100 * s.workers / s.adults
    x = pd.read_csv(SECTORS)[["sid", "district_id", "border"]]
    d = s.drop(columns=["district_id"]).merge(x, on="sid", how="inner", validate="m:1")
    d = d[~d.district_id.isin(KIGALI)].copy()
    if DROP_RING:
        d = d[~d.sid.isin(ring_sectors())].copy()
    for t in (2012, 2022):
        d[f"park_x_{t}"] = d.border * (d.wave == t)
    terms = ["park_x_2012", "park_x_2022"]
    _log(f"[status] {d.sid.nunique()} sectors, {int(d.drop_duplicates('sid').border.sum())} park-adjacent", )

    rows = []
    for y, label in STATUS_OUTCOMES:
        est, n, G = fe_ols(d, y, terms, ["sid", "wave"], "district_id", test=terms)
        m = {t: d[(d.wave == t)].groupby("border")[y].mean() for t in (2002, 2012, 2022)}
        for t in (2012, 2022):
            e = est.loc[f"park_x_{t}"]
            rows.append({"outcome": y, "label": label, "wave": t, "coef": e.coef, "se": e.se, "p_wcb": e.p_wcb,
                         "mean_park_2002": m[2002][1], "mean_interior_2002": m[2002][0],
                         "mean_park_wave": m[t][1], "mean_interior_wave": m[t][0], "obs": n, "clusters": G})
        _log(f"[status]   {label}: 2012 {est.loc['park_x_2012','coef']:+.2f} [{est.loc['park_x_2012','p_wcb']:.3f}], "
              f"2022 {est.loc['park_x_2022','coef']:+.2f} [{est.loc['park_x_2022','p_wcb']:.3f}]", )
    P.TABLES_REG.mkdir(parents=True, exist_ok=True)
    out = P.TABLES_REG / f"census_park_status{suffix}.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    _log(f"-> {out}")





# ---- legacy: log outcomes with sector and wave FE (2002 base)

def logs_prepare(drop_ring: bool):
    x = pd.read_csv(SECTORS)[["sid", "district_id", "border"]]
    ind = pd.read_csv(PANEL)[["sid", "wave", "adults", "nonfarm", "services", "tourism", "farm"]]
    st = pd.read_csv(STATUS).rename(columns={"sector_id": "sid", "year": "wave"})
    for k, _ in STAT:
        st[k] = st[f"per_adult_{k}"] * st.adults
    st = st[["sid", "wave", "adults", "wage", "self", "family", "other"]]
    out = []
    for d in (ind, st):
        d = d.merge(x, on="sid", validate="m:1")
        d = d[~d.district_id.isin(KIGALI)].copy()
        if drop_ring:
            d = d[~d.sid.isin(ring_sectors())].copy()
        d["log_adults"] = np.log(d.adults)
        for t in (2012, 2022):
            d[f"park_x_{t}"] = d.border * (d.wave == t)
        out.append(d)
    return out


def logs_ppml(d, y):
    g = d.groupby("sid")[y].transform("sum") > 0                     # drop sectors with no workers in any wave
    d = d[g].copy()
    X = pd.concat([d[LOG_TERMS + ["log_adults"]], pd.get_dummies(d.sid, prefix="s", drop_first=True, dtype=float),
                   pd.get_dummies(d.wave, prefix="w", drop_first=True, dtype=float)], axis=1)
    m = sm.GLM(d[y], sm.add_constant(X), family=sm.families.Poisson()).fit(
        cov_type="cluster", cov_kwds={"groups": pd.factorize(d.district_id)[0]}, maxiter=200)
    r = pd.DataFrame({"coef": m.params, "se": m.bse, "p": m.pvalues}).loc[LOG_TERMS + ["log_adults"]]
    return r, int(len(d)), d.sid.nunique(), d.district_id.nunique()


def logs_run(d, y, label, spec):
    if (d[y] > 0).all():
        d = d.assign(ln_y=np.log(d[y]))
        est, n, G = fe_ols(d, "ln_y", LOG_TERMS + ["log_adults"], ["sid", "wave"], "district_id", test=LOG_TERMS)
        est = est.rename(columns={"p_wcb": "p"})
        kind, ns = "OLS, log workers", d.sid.nunique()
    else:
        est, n, ns, G = logs_ppml(d, y)
        kind = "Poisson, workers"
    for t in (2012, 2022):
        e = est.loc[f"park_x_{t}"]
        LOG_ROWS.append({"spec": spec, "outcome": y, "label": label, "estimator": kind, "wave": t, "coef": e.coef, "se": e.se,
                     "p": e.p, "log_adults_coef": est.loc["log_adults", "coef"], "obs": n, "sectors": ns, "clusters": G})
    _log(f"[logs]   {spec}, {label} ({kind}): 2012 {est.loc['park_x_2012','coef']:+.3f} [{est.loc['park_x_2012','p']:.3f}], "
          f"2022 {est.loc['park_x_2022','coef']:+.3f} [{est.loc['park_x_2022','p']:.3f}]; ln adults {est.loc['log_adults','coef']:.2f}")



def section_logs():
    ind, st = logs_prepare(DROP_RING)
    _log(f"[logs] {ind.sid.nunique()} sectors ({int(ind.drop_duplicates('sid').border.sum())} park-adjacent)")
    for y, lab in INDUSTRY:
        logs_run(ind, y, lab, "industry")
    for y, lab in STAT:
        logs_run(st, y, lab, "status")
    P.TABLES_REG.mkdir(parents=True, exist_ok=True)
    out = P.TABLES_REG / f"census_park_logs{'_no_ring' if DROP_RING else ''}.csv"
    pd.DataFrame(LOG_ROWS).to_csv(out, index=False)
    _log(f"-> {out}")


SECTIONS = {"outcomes": section_outcomes, "questions": section_questions}
LEGACY = {"gap": section_gap, "person": section_person, "migration": section_migration, "levels": section_levels,
          "eicv_check": section_eicv_check, "status": section_status, "logs": section_logs, "land": section_land,
          "shift": section_shift, "opening": section_opening}


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--only", nargs="+", choices=list(SECTIONS) + list(LEGACY))
    a.add_argument("--legacy", action="store_true", help="also run the retired change-from-baseline sections")
    a.add_argument("--list", action="store_true")
    a.add_argument("--drop-ring", action="store_true", help="drop the ring of sectors touching park-adjacent ones")
    a.add_argument("--all-years", action="store_true", help="land: use 2000, 2005, ..., 2020 instead of 2000, 2010, 2020")
    args = a.parse_args(argv)
    global DROP_RING, ALL_YEARS
    DROP_RING, ALL_YEARS = args.drop_ring, args.all_years
    allsec = {**SECTIONS, **LEGACY}
    if args.list:
        print("default: " + " ".join(SECTIONS) + "\nlegacy:  " + " ".join(LEGACY)); return 0
    for k in args.only or (list(SECTIONS) + (list(LEGACY) if args.legacy else [])):
        allsec[k]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
