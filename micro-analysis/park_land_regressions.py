"""
park_land_regressions.py -- land use around the parks, tourism-exposure regressions and the Gishwati-Mukura opening.

Sample: the 381 sectors outside Kigali City (districts 11, 12, 13). Sector and year fixed effects throughout; standard
errors clustered by district, wild cluster restricted bootstrap p-values (helpers/regression.py::fe_ols).
Park_s = 1 if the sector borders a national park (model_sector_cross.csv, column border); nearest_park names the park.

Sections (python micro-analysis/park_land_regressions.py --list)

  land     Regression 3. y_st = a_s + g_t + sum_{t > 2000} b_t Park_s 1[t] + e_st on the GLAD / GHSL land panels.
           Years 2000, 2010, 2020 (a pair of years from the Census waves; --all-years uses 2000, 2005, ..., 2020).
           Outcomes: cropland share and built-up share of the sector's usable (non-park) land, in percentage points
           (sector_cropland_builtup_glclu.csv, columns crop_sh, built_sh); log(1 + built-up hectares), GHSL
           (sector_ghsl_built.csv, built_total_ha). b_t = change since 2000 in the park-adjacent minus interior gap.

  shift    Regression 4, one common shock. Exposure E_s = omega_p for a sector whose nearest park p is Volcanoes,
           Akagera or Nyungwe, 0 for interior sectors. omega_p = park p's share of the three parks' visits, summed over
           SHARE_YEARS (fixed, not updated by year; visits, not revenue). Gishwati and Mukura sectors are dropped here
           (no visit data; see section opening). T_t = national park visits in year t, in 100,000s (the 'All parks
           (published)' column of the RDB / NISR workbook), 2005-2023.
             annual   y_st = a_s + g_t + beta E_s T_t + e_st, land panel years 2005, 2010, 2015, 2020. beta = change in y
                      per 100,000 more national visits, for a sector with all of the exposure (E = 1).
                      Only four years (2005, 2010, 2015, 2020) carry a land observation and T_t is 0.24, 0.45, 0.73
                      and 0.36 (2020 is the COVID year), so beta rests on four points of one national series and
                      cannot separate tourism from anything else that moves with E_s.
             by year  y_st = a_s + g_t + sum_{t > 2005} b_t E_s 1[t] + e_st, same years, 2005 the base.
             census   y_st = a_s + g_t + sum_{t in 2012, 2022} b_t E_s 1[t] + e_st, workers per 100 adults (Census panel).
           A sector's park is its nearest park, so a sector bordering two parks gets one exposure value.

  opening  Gishwati-Mukura National Park was created in 2015. Treated: the sectors bordering Gishwati or Mukura (20),
           control: interior sectors (border = 0). The land panel has 2000, 2005, 2010 before the opening, 2015 in the
           opening year and 2020 after it.
             post     y_st = a_s + g_t + b GM_s 1[t >= 2016] + e_st (2020 is the only post year on the 5-year grid).
             by year  y_st = a_s + g_t + sum_{t != 2010} b_t GM_s 1[t] + e_st, 2010 (last year before) the base.
             census   y_st = a_s + g_t + b GM_s 1[2022] + e_st, workers per 100 adults, 2002 and 2012 before.
           The treated sectors lie in four districts (Rutsiro, Nyabihu, Rubavu, Ngororero), so district-clustered
           inference rests on very few treated clusters.

Output: output/tables/regressions/park_land_<section>.csv (one row per coefficient).

Usage
    python micro-analysis/park_land_regressions.py
    python micro-analysis/park_land_regressions.py --only shift
    python micro-analysis/park_land_regressions.py --only land --all-years
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "helpers"))
import paths as P  # noqa: E402
from regression import fe_ols  # noqa: E402

KIGALI = {11, 12, 13}
SECTORS = P.HARMONIZED / "model_sector_cross.csv"
LAND = P.HARM_PANELS / "sector_cropland_builtup_glclu.csv"
GHSL = P.HARM_PANELS / "sector_ghsl_built.csv"
CENSUS_PANEL = P.HARMONIZED / "census_sector_work_per_adult.csv"
RDB = P.HARMONIZED / "rwanda-parks-tourism-rdb.xlsx"

SHARE_YEARS = (2005, 2019)                  # years of visits that set omega_p (before the 2020-21 collapse)
TOURIST_PARKS = {"Volcanoes National Park": "Volcanoes", "Akagera National Park": "Akagera",
                 "Nyungwe National Park": "Nyungwe"}
GM_PARKS = ("Gishwati", "Mukura")
OPENING_YEAR = 2015                         # Gishwati-Mukura National Park created
LAND_OUTCOMES = [("crop_pp", "Cropland share (pp)"), ("built_pp", "Built-up share (pp)"),
                 ("log_built", "Log built-up area (ha)")]
CENSUS_OUTCOMES = [("nonfarm_per100", "Non-farm workers"), ("services_per100", "Services workers"),
                   ("tourism_per100", "Tourism workers")]


def _log(msg: str) -> None:
    print(f"[park-land] {msg}", flush=True)


def sectors() -> pd.DataFrame:
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
    a = pd.read_csv(LAND, usecols=["sid", "year", "crop_sh", "built_sh"])
    g = pd.read_csv(GHSL, usecols=["sid", "year", "built_total_ha"])
    d = a.merge(g, on=["sid", "year"], how="inner", validate="1:1")
    d["crop_pp"], d["built_pp"] = 100 * d.crop_sh, 100 * d.built_sh
    d["log_built"] = np.log1p(d.built_total_ha)
    return d.merge(sectors(), on="sid", how="inner")


def census_panel() -> pd.DataFrame:
    d = pd.read_csv(CENSUS_PANEL).rename(columns={"wave": "year"})
    return d.merge(sectors(), on="sid", how="inner")


def run(d, outcomes, terms, section, spec, rows):
    """One regression per outcome; every term gets a wild-bootstrap p-value."""
    for y, label in outcomes:
        est, n, G = fe_ols(d, y, terms, ["sid", "year"], "district_id", test=terms)
        for t in terms:
            e = est.loc[t]
            rows.append({"section": section, "spec": spec, "outcome": y, "label": label, "term": t, "coef": e.coef,
                         "se": e.se, "p_wcb": e.p_wcb, "obs": n, "sectors": d.sid.nunique(), "clusters": G})
        _log(f"  {spec}, {label}: " + ", ".join(f"{t} {est.loc[t, 'coef']:+.3f} [{est.loc[t, 'p_wcb']:.3f}]" for t in terms))


def save(rows, name):
    P.TABLES_REG.mkdir(parents=True, exist_ok=True)
    path = P.TABLES_REG / f"park_land_{name}.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    _log(f"-> {path}")


def section_land(all_years: bool = False):
    d = land_panel()
    years = (2000, 2005, 2010, 2015, 2020) if all_years else (2000, 2010, 2020)
    d = d[d.year.isin(years)].copy()
    terms = []
    for t in years[1:]:
        d[f"park_x_{t}"] = d.border * (d.year == t)
        terms.append(f"park_x_{t}")
    _log(f"land: {d.sid.nunique()} sectors, {int(d.drop_duplicates('sid').border.sum())} park-adjacent, years {years}")
    rows = []
    run(d, LAND_OUTCOMES, terms, "land", "five-year panel" if all_years else "2000-2010-2020", rows)
    save(rows, "land_all_years" if all_years else "land")


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
    run(d, LAND_OUTCOMES, ["E_x_T"], "shift", "annual, E x national visits", rows)
    ts = [t for t in sorted(d.year.unique()) if t > 2005]
    for t in ts:
        d[f"E_x_{t}"] = d.exposure * (d.year == t)
    run(d, LAND_OUTCOMES, [f"E_x_{t}" for t in ts], "shift", "by year, 2005 base", rows)
    # census waves
    c = census_panel()
    c = c[c.gm == 0].copy()
    for t in (2012, 2022):
        c[f"E_x_{t}"] = c.exposure * (c.year == t)
    run(c, CENSUS_OUTCOMES, ["E_x_2012", "E_x_2022"], "shift", "census waves, 2002 base", rows)
    save(rows, "shift")


def section_opening():
    rows = []
    d = land_panel()
    d = d[(d.border == 0) | (d.gm == 1)].copy()            # interior sectors and the Gishwati-Mukura sectors
    _log(f"opening: {d.sid.nunique()} sectors, {int(d.drop_duplicates('sid').gm.sum())} bordering Gishwati or Mukura")
    d["gm_post"] = d.gm * (d.year > OPENING_YEAR)
    run(d, LAND_OUTCOMES, ["gm_post"], "opening", f"land, post = year > {OPENING_YEAR}", rows)
    ts = [t for t in sorted(d.year.unique()) if t != 2010]
    for t in ts:
        d[f"gm_x_{t}"] = d.gm * (d.year == t)
    run(d, LAND_OUTCOMES, [f"gm_x_{t}" for t in ts], "opening", "land, by year, 2010 base", rows)
    c = census_panel()
    c = c[(c.border == 0) | (c.gm == 1)].copy()
    c["gm_post"] = c.gm * (c.year == 2022)
    run(c, CENSUS_OUTCOMES, ["gm_post"], "opening", "census waves, post = 2022", rows)
    save(rows, "opening")


SECTIONS = {"land": section_land, "shift": section_shift, "opening": section_opening}


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--only", nargs="+", choices=list(SECTIONS))
    a.add_argument("--list", action="store_true")
    a.add_argument("--all-years", action="store_true", help="land: use 2000, 2005, ..., 2020 instead of 2000, 2010, 2020")
    args = a.parse_args(argv)
    if args.list:
        print("\n".join(SECTIONS)); return 0
    for k in args.only or SECTIONS:
        section_land(args.all_years) if k == "land" else SECTIONS[k]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
