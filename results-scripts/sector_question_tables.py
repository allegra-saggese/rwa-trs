"""
sector_question_tables.py -- AER-style tables for census_park_questions.py (docs/sector_question_tables.tex).

One table per question, one panel per Census wave (land: per land-cover year); columns are outcomes, with spec (1) without
and spec (2) with the geography controls side by side. Standard errors in parentheses, bootstrap p-values in brackets.
Stars come from the bracketed p-values: *** 1%, ** 5%, * 10%. Reads output/tables/regressions/census_park_questions[_no_ring].csv.

Usage: python results-scripts/sector_question_tables.py   (then pdflatex docs/sector_question_tables.tex)
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import paths as P  # noqa: E402

GEO = "log area, log distance to the nearest trunk or primary road, log distance to Kigali, mean elevation, mean slope and mean rainfall (each standardised)"
OUTS = [("nonfarm", "Non-farm"), ("services", "Services"), ("tourism", "Tourism"), ("farm", "Farm")]
LAND = [("built_pp", "Built-up share"), ("crop_pp", "Cropland share"), ("log_built", "ln(1 + built-up ha)")]
WAVES = (2002, 2012, 2022)


def star(p):
    return "***" if p < .01 else "**" if p < .05 else "*" if p < .1 else ""


def fmt(v, d=3):
    return ("$-$" if v < 0 and round(abs(v), d) != 0 else "") + f"{abs(v):,.{d}f}"


def cells(row):
    if row is None:
        return "", "", ""
    return f"{fmt(row.coef)}$^{{{star(row.p)}}}$" if star(row.p) else fmt(row.coef), f"({fmt(row.se)})", f"[{row.p:.3f}]"


def pick(df, **kw):
    for k, v in kw.items():
        df = df[df[k] == v]
    return df.iloc[0] if len(df) else None


def block(label, rows):
    c = [cells(r) for r in rows]
    return [f"{label} & " + " & ".join(x[0] for x in c) + r" \\", " & " + " & ".join(x[1] for x in c) + r" \\",
            " & " + " & ".join(x[2] for x in c) + r" \\"]


def table(caption, label, groups, panels, footer, notes, ncols):
    head1 = " & " + " & ".join(rf"\multicolumn{{2}}{{c}}{{{g}}}" for g in groups) + r" \\"
    cm = " ".join(rf"\cmidrule(lr){{{2 * i + 2}-{2 * i + 3}}}" for i in range(len(groups)))
    head2 = " & " + " & ".join(f"({i + 1})" for i in range(ncols)) + r" \\"
    return "\n".join([r"\begin{table}[H]", r"\centering\footnotesize\setlength{\tabcolsep}{3pt}", rf"\caption{{{caption}}}", rf"\label{{{label}}}",
                      r"\resizebox{\textwidth}{!}{%", rf"\begin{{tabular}}{{l{'c' * ncols}}}", r"\toprule", head1, cm, head2, r"\midrule", *panels, r"\midrule", *footer, r"\bottomrule",
                      r"\end{tabular}}", r"\begin{minipage}{0.97\textwidth}\scriptsize", rf"\textit{{Notes:}} {notes}", r"\end{minipage}", r"\end{table}"])


SE_NOTE = (r"Standard errors clustered by district (27 clusters) in parentheses. In OLS columns, brackets give wild cluster restricted bootstrap p-values "
           r"(Webb weights, 9,999 draws); in the tourism columns (Poisson), cluster-robust normal p-values. Stars follow the bracketed p-values: *** $p<0.01$, ** $p<0.05$, * $p<0.1$.")


def count_table(df, q, terms, caption, label, fe, extra_note, sample_note):
    """Count outcomes, one panel per wave. terms: [(term, row label)]."""
    panels = []
    for t in WAVES:
        panels.append(rf"\multicolumn{{9}}{{l}}{{\textit{{Panel {'ABC'[WAVES.index(t)]}. Census {t}}}}} \\")
        for term, lab in terms:
            panels += block(lab, [pick(df, question=q, wave=t, term=term, outcome=o, spec=s)
                                  for o, _ in OUTS for s in (df[df.question == q].spec.unique()[:2])])
        la = [pick(df, question=q, wave=t, outcome=o, spec=s, term=terms[0][0]) for o, _ in OUTS for s in df[df.question == q].spec.unique()[:2]]
        panels += [r"ln(adults) & " + " & ".join(fmt(r.log_adults_coef, 2) for r in la) + r" \\",
                   "Observations & " + " & ".join(f"{int(r.obs):,}" for r in la) + r" \\"]
        if t != WAVES[-1]:
            panels.append(r"\addlinespace")
    footer = ["Geography controls & " + " & ".join(["No", "Yes"] * 4) + r" \\", f"Fixed effects & " + " & ".join([fe] * 8) + r" \\",
              "Estimator & " + " & ".join(["OLS", "OLS", "OLS", "OLS", "Poisson", "Poisson", "OLS", "OLS"]) + r" \\"]
    notes = (sample_note + r" Dependent variable: ln(number of workers) by industry of main work (non-farm, services, farm; Census-weighted); "
             r"for tourism, the number of workers (Poisson, log link, so coefficients are also proportional differences). One OLS regression per wave and column, "
             rf"on sectors outside Kigali City. ln(adults) is the log of residents aged 16 and over; its coefficient is an elasticity. Geography controls: {GEO}. " + extra_note + " " + SE_NOTE)
    return table(caption, label, [n for _, n in OUTS], panels, footer, notes, 8)


def land_table(df, caption, label, sample_note):
    panels = []
    for t in (2000, 2010, 2020):
        panels.append(rf"\multicolumn{{7}}{{l}}{{\textit{{Panel {'ABC'[(2000, 2010, 2020).index(t)]}. {t}}}}} \\")
        panels += block("Park-adjacent", [pick(df, question="Q4", wave=t, term="border", outcome=o, spec=s) for o, _ in LAND for s in ("(1) none", "(2) X")])
        panels.append("Observations & " + " & ".join(f"{int(pick(df, question='Q4', wave=t, term='border', outcome=o, spec=s).obs):,}" for o, _ in LAND for s in ("(1) none", "(2) X")) + r" \\")
        if t != 2020:
            panels.append(r"\addlinespace")
    footer = ["Geography controls & " + " & ".join(["No", "Yes"] * 3) + r" \\", "Fixed effects & " + " & ".join(["District"] * 6) + r" \\"]
    notes = (sample_note + r" Dependent variables: built-up share and cropland share of the sector's usable (non-park) land, in percentage points (GLAD land cover), and ln(1 + built-up hectares) (GHSL). "
             rf"One OLS regression per year and column. Geography controls: {GEO}. " + SE_NOTE.replace("; in the tourism columns (Poisson), cluster-robust normal p-values", ""))
    return table(caption, label, [n for _, n in LAND], panels, footer, notes, 6)


def build(suffix, ring):
    df = pd.read_csv(P.TABLES_REG / f"census_park_questions{suffix}.csv")
    samp = (r"Sample: 299 sectors outside Kigali City, dropping the 82 that touch a park-adjacent sector without bordering a park." if ring
            else r"Sample: 381 sectors outside Kigali City, of which 62 border a national park.")
    tag = " (Ring Dropped)" if ring else ""
    out = []
    out.append(count_table(df, "Q1", [("border", "Park-adjacent")], "Workers in Park-Adjacent vs Interior Sectors, by Census Wave" + tag, "tab:q1" + suffix, "District",
                           r"Park-adjacent = the sector borders a national park; the coefficient is the proportional difference in workers relative to interior sectors of the same district, at the same number of adults.", samp))
    out.append(count_table(df, "Q3", [("exposure", "Visit-share exposure")], "Exposure to Park Tourism and Workers, by Census Wave" + tag, "tab:q3" + suffix, "District",
                           r"Exposure = the nearest park's share of three-park visits 2005--2019 (Volcanoes 0.40, Akagera 0.46, Nyungwe 0.14) for park-adjacent sectors, 0 for others; Gishwati--Mukura sectors dropped (no visit data).",
                           (r"Sample: 279 sectors outside Kigali City, excluding the ring and the Gishwati--Mukura sectors." if ring else r"Sample: 361 sectors outside Kigali City, excluding the Gishwati--Mukura sectors.")))
    # gate bins: three panels, rows are bins (+ Park in even columns)
    g = df[df.question == "Q2"]
    for t in WAVES:
        panels = [rf"\multicolumn{{9}}{{l}}{{\textit{{Census {t}}}}} \\"]
        for term, lab in (("gate_lt10", r"Within 10 km of a gate"), ("gate_10_20", "10--20 km"), ("gate_20_40", "20--40 km"), ("border", "Park-adjacent")):
            panels += block(lab, [pick(g, wave=t, term=term, outcome=o, spec=s) for o, _ in OUTS for s in ("(1) bins", "(2) bins + Park")])
        la = [pick(g, wave=t, term="gate_lt10", outcome=o, spec=s) for o, _ in OUTS for s in ("(1) bins", "(2) bins + Park")]
        panels += [r"ln(adults) & " + " & ".join(fmt(r.log_adults_coef, 2) for r in la) + r" \\", "Observations & " + " & ".join(f"{int(r.obs):,}" for r in la) + r" \\"]
        footer = [r"Park-adjacent indicator & " + " & ".join(["No", "Yes"] * 4) + r" \\", "Geography controls & " + " & ".join(["Yes"] * 8) + r" \\",
                  "Fixed effects & " + " & ".join(["Nearest park"] * 8) + r" \\", "Estimator & " + " & ".join(["OLS", "OLS", "OLS", "OLS", "Poisson", "Poisson", "OLS", "OLS"]) + r" \\"]
        notes = (samp + r" Distance bins are from the sector centroid to the nearest of four park gates (Kinigi, Gisakura, Kitabi, Akagera South Gate); the omitted bin is 40 km or more (196 sectors; bin sizes 17, 43 and 125 sectors). "
                 r"Dependent variable: ln(number of workers) by industry of main work (tourism: number of workers, Poisson). One regression per wave and column; the fixed effect is the nearest park (five groups). "
                 rf"Geography controls: {GEO}. " + SE_NOTE)
        out.append(table(f"Distance to a Park Gate and Workers, Census {t}" + tag, f"tab:q2_{t}" + suffix, [n for _, n in OUTS], panels, footer, notes, 8))
    out.append(land_table(df, "Land Use in Park-Adjacent vs Interior Sectors, by Year" + tag, "tab:q4" + suffix, samp))
    return out


def main() -> int:
    body = build("", False) + [r"\clearpage"] + build("_no_ring", True)
    tex = "\n".join([r"\documentclass[11pt]{article}", r"\usepackage[margin=0.8in]{geometry}", r"\usepackage{booktabs,float,amsmath,graphicx}",
                     r"\usepackage[font=small,labelfont=bf]{caption}", r"\captionsetup[table]{position=top}", r"\begin{document}", *body, r"\end{document}"])
    p = ROOT / "docs" / "sector_question_tables.tex"
    p.write_text(tex)
    print(f"[question-tables] -> {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
