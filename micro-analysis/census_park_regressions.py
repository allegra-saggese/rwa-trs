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

Usage
    python micro-analysis/census_park_regressions.py
    python micro-analysis/census_park_regressions.py --only gap
"""
import argparse
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


SECTIONS = {"outcomes": section_outcomes, "gap": section_gap}


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
