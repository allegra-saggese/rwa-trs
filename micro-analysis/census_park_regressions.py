"""
census_park_regressions.py -- park-adjacent vs interior sectors across the 2002, 2012 and 2022 Censuses.

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
  eicv_check validation of the Census measure against EICV, by district (Kigali excluded): non-farm workers
             per 100 adults in Census 2002 / 2012 / 2022 against EICV 2005/06 / 2013/14 / 2023/24 (the rounds
             whose pooled person file carries the industry of the main job) -> census_eicv_nonfarm_check.csv

Usage
    python micro-analysis/census_park_regressions.py
    python micro-analysis/census_park_regressions.py --only gap
"""
import argparse
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyreadstat

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "helpers"))
import paths as P  # noqa: E402
from regression import fe_ols  # noqa: E402

CENSUS = P.NISR / "Census-PHC/3_Final/Census_pooled_person.dta"
SECTORS = P.HARMONIZED / "model_sector_cross.csv"
PANEL = P.HARMONIZED / "census_sector_work_per_adult.csv"
KIGALI = {11, 12, 13}
WAVES = (2002, 2012, 2022)
OUTCOMES = [("nonfarm_per100", "Non-farm workers"), ("services_per100", "Services workers"),
            ("tourism_per100", "Tourism workers")]


def _log(msg):
    print(f"[census-park] {msg}", flush=True)


# ---------------------------------------------------------------------------- outcomes
def classify(d: pd.DataFrame) -> pd.DataFrame:
    """0/1 columns nonfarm, services, tourism for each person, by wave-specific industry coding."""
    out = pd.DataFrame(0, index=d.index, columns=["nonfarm", "services", "tourism"], dtype="int8")
    # 2002: ISIC Rev. 3 three-digit groups (11-50 agriculture and fishing, 101+ everything else, 999 not stated)
    m = d.census_year == 2002
    g = d.loc[m, "census_industry_isic3_2002"]
    div = g // 10
    stated = g.notna() & (g != 999)
    out.loc[m, "nonfarm"] = (stated & (g >= 101)).astype("int8")
    out.loc[m, "services"] = (stated & (div >= 50)).astype("int8")
    out.loc[m, "tourism"] = (div.isin([55, 92])).astype("int8")
    # 2012 and 2022: ISIC Rev. 4 sections 1 = A ... 21 = U (22 not stated, 23 not applicable)
    for y in (2012, 2022):
        m = d.census_year == y
        s = d.loc[m, f"census_isic_section_{y}"]
        ok = s.between(1, 21)
        out.loc[m, "nonfarm"] = (ok & (s >= 2)).astype("int8")
        out.loc[m, "services"] = (ok & (s >= 7)).astype("int8")
        out.loc[m, "tourism"] = s.isin([9, 18]).astype("int8")
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
                                   "tourism": w * c.tourism}))
    p = pd.concat(parts).groupby(["sid", "wave"], as_index=False).sum()
    for k in ("nonfarm", "services", "tourism"):
        p[f"{k}_per100"] = 100 * p[k] / p.adults
    assert len(p) == 3 * 416, f"expected 416 sectors x 3 waves, got {len(p)}"
    P.HARMONIZED.mkdir(parents=True, exist_ok=True)
    p.to_csv(PANEL, index=False)
    nat = p.groupby("wave")[["adults", "nonfarm", "services", "tourism"]].sum()
    for k in ("nonfarm", "services", "tourism"):
        nat[k] = (100 * nat[k] / nat.adults).round(2)
    _log(f"-> {PANEL}\nnational, per 100 adults:\n{nat.drop(columns='adults').to_string()}")


# ---------------------------------------------------------------------------- gap regression
def section_gap():
    p = pd.read_csv(PANEL)
    s = pd.read_csv(SECTORS)[["sid", "district_id", "border"]]
    d = p.merge(s, on="sid", how="left")
    assert d.border.notna().all()
    d = d[~d.district_id.isin(KIGALI)].copy()
    for t in (2012, 2022):
        d[f"park_x_{t}"] = d.border * (d.wave == t)
    n_sec, n_park, n_dist = d.sid.nunique(), int(d.drop_duplicates("sid").border.sum()), d.district_id.nunique()
    _log(f"{n_sec} sectors ({n_park} park-adjacent), {n_dist} districts")
    rows = []
    for y, label in OUTCOMES:
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
    res.to_csv(P.TABLES_REG / "census_park_gap.csv", index=False)
    tex(res)
    _log(f"-> {P.TABLES_REG / 'census_park_gap.csv'} and .tex")


def _stars(p):
    return "^{***}" if p < .01 else "^{**}" if p < .05 else "^{*}" if p < .1 else ""


def tex(res: pd.DataFrame):
    labels = [l for _, l in OUTCOMES]
    cell = lambda l, t, k: res[(res.label == l) & (res.wave == t)].iloc[0][k]
    L = [r"\begin{table}[htbp]", r"\centering",
         r"\caption{Park-Adjacent and Interior Sectors across Census Waves}", r"\label{tab:census_park_gap}",
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
          r"samples, on 2022 sector boundaries, excluding Kigali City. Outcomes are workers per 100 residents aged 16 and "
          r"over, by industry of main work: non-farm (all industries except agriculture, forestry and fishing), services "
          r"(ISIC Rev.~4 sections G--U; Rev.~3 divisions 50--99 in 2002) and tourism (accommodation and food, and arts, "
          r"entertainment and recreation; Rev.~3 divisions 55 and 92 in 2002). Park-adjacent sectors border a national "
          r"park. Each column is one regression with sector and wave fixed effects; the coefficients give the change in "
          r"the park-adjacent minus interior gap relative to 2002. Standard errors clustered by district in parentheses; "
          r"wild cluster restricted bootstrap p-values (Webb weights, 9,999 draws) in brackets; stars from the bootstrap "
          r"p-values: *** 1\%, ** 5\%, * 10\%.", r"\end{minipage}", r"\end{table}", ""]
    (P.TABLES_REG / "census_park_gap.tex").write_text("\n".join(L))


# ---------------------------------------------------------------------------- person level, with controls
PERSON_COLS = ["census_year", "census_sector", "census_district", "census_household_id", "census_age", "census_sex",
               "census_urban", "census_weight", "census_industry_isic3_2002", "census_isic_section_2012",
               "census_isic_section_2022", "census_ever_attended_school_2002", "census_education_grouped_2002",
               "census_school_attendance_2012", "census_education_level_2012", "census_school_attendance_2022",
               "census_education_level_2022", "census_marital_status_2002", "census_marital_status_2012",
               "census_marital_status_2022"]


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
    Controls (each interacted with wave): age band, female, education group, marital group, urban, household size.
    Birthplace is left out: 2002 records it in the pre-2006 districts, which do not map onto today's."""
    parts = []
    for chunk, _ in pyreadstat.read_file_in_chunks(pyreadstat.read_dta, str(CENSUS), chunksize=500_000, usecols=PERSON_COLS):
        chunk = chunk[chunk.census_year.isin(WAVES)]
        chunk["hh_key"] = chunk.census_year.astype(int).astype(str) + "_" + chunk.census_household_id.astype(str)
        parts.append(chunk)
    d = pd.concat(parts, ignore_index=True)
    d["hh_size"] = d.hh_key.map(d.hh_key.value_counts()).astype(float)
    d = d[(d.census_age >= 16) & ~d.census_district.isin(KIGALI)].reset_index(drop=True)
    frac = float(os.environ.get("CENSUS_PARK_SAMPLE", 0) or 0)   # test switch: keep this share of sectors
    if frac:
        keep = np.random.default_rng(0).choice(d.census_sector.unique(), int(d.census_sector.nunique() * frac), replace=False)
        d = d[d.census_sector.isin(keep)].reset_index(drop=True)
    d = d.join(classify(d))
    d["sid"], d["wave"] = d.census_sector.astype(int), d.census_year.astype(int)
    park = pd.read_csv(SECTORS).set_index("sid").border
    d["park"] = d.sid.map(park)
    d["w"] = d.census_weight / d.groupby(["sid", "wave"]).census_weight.transform("sum")
    edu, mar = education_group(d), marital_group(d)
    bands = pd.cut(d.census_age, [15, 19, 24, 29, 34, 39, 44, 49, 54, 59, 64, 200], labels=False)
    base = {"female": (d.census_sex == 2), "urban": (d.census_urban == 1), "household size": d.hh_size}
    for b in range(11):
        if b != 3:                                  # 30-34 omitted
            base[f"age band {b}"] = bands == b
    for k in ("none", "secondary", "tertiary", "not stated"):
        base[f"education {k}"] = edu == k        # primary omitted
    for k in ("never", "divorced", "widowed", "not stated"):
        base[f"marital {k}"] = mar == k          # married omitted
    X = {f"{k} x {t}": np.asarray(v, float) * (d.wave == t).to_numpy() for k, v in base.items() for t in WAVES}
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
            A = _demean(np.column_stack([yv, Z.to_numpy(float)]), gi, w) * r[:, None]
            df = pd.DataFrame(A[:, 1:], columns=Z.columns)
            df["y"], df["district"] = A[:, 0], d.census_district.to_numpy()
            est, n, G = fe_ols(df, "y", list(Z.columns), [], "district", test=["park_x_2012", "park_x_2022"])
            for t in (2012, 2022):
                e = est.loc[f"park_x_{t}"]
                rows.append({"outcome": y, "label": label, "spec": spec, "wave": t, "coef": e.coef, "se": e.se,
                             "p_wcb": e.p_wcb, "obs": n, "clusters": G})
            _log(f"  {label}, {spec}: 2012 {est.loc['park_x_2012', 'coef']:+.2f} [{est.loc['park_x_2012', 'p_wcb']:.3f}], "
                 f"2022 {est.loc['park_x_2022', 'coef']:+.2f} [{est.loc['park_x_2022', 'p_wcb']:.3f}]")
    res = pd.DataFrame(rows)
    res.to_csv(P.TABLES_REG / "census_park_gap_person.csv", index=False)
    tex_person(res, len(d), d.sid.nunique(), int(d.drop_duplicates("sid").park.sum()))
    _log(f"-> {P.TABLES_REG / 'census_park_gap_person.csv'} and .tex")


def tex_person(res: pd.DataFrame, n: int, n_sec: int, n_park: int):
    cols = [(l, sp) for _, l in OUTCOMES for sp in ("no controls", "controls")]
    get = lambda l, sp, t, k: res[(res.label == l) & (res.spec == sp) & (res.wave == t)].iloc[0][k]
    L = [r"\begin{table}[htbp]", r"\centering", r"\caption{Park-Adjacent and Interior Sectors: Person-Level Estimates}",
         r"\label{tab:census_park_gap_person}", r"\begin{tabular}{l" + "c" * len(cols) + "}", r"\toprule",
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
          r"City. Outcome: 100 if the person's main work is in the group (non-farm, services, tourism; definitions as in "
          r"Table~\ref{tab:census_park_gap}), 0 otherwise, including people who do not work. All columns include sector and "
          r"wave fixed effects; observations are weighted so that every sector-wave carries equal weight, so the odd "
          r"columns reproduce Table~\ref{tab:census_park_gap}. Even columns add, each interacted with wave: age band, sex, "
          r"education (none, primary, secondary, tertiary), marital status, urban residence and household size. Standard "
          r"errors clustered by district in parentheses; wild cluster restricted bootstrap p-values (Webb weights, 9,999 "
          r"draws) in brackets; stars from the bootstrap p-values: *** 1\%, ** 5\%, * 10\%.",
          r"\end{minipage}", r"\end{table}", ""]
    (P.TABLES_REG / "census_park_gap_person.tex").write_text("\n".join(L))


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


SECTIONS = {"outcomes": section_outcomes, "gap": section_gap, "person": section_person, "eicv_check": section_eicv_check}


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--only", nargs="+", choices=list(SECTIONS))
    a.add_argument("--list", action="store_true")
    args = a.parse_args(argv)
    if args.list:
        print("\n".join(SECTIONS)); return 0
    for k in args.only or SECTIONS:
        SECTIONS[k]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
