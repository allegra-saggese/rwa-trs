"""
sector_work_type.py -- sector x wave occupation mix and household size from the Census microdata (2002, 2012, 2022).

  Occupation   ISCO major group of main work, adults aged 16 and over with an occupation stated (Census-weighted counts).
               1 managers, 2 professionals, 3 technicians, 4 clerical, 5 service and sales, 6 skilled agriculture, 7 craft,
               8 plant and machine operators, 9 elementary. 2002 uses the first digit of the three-digit ISCO-88 code
               (999 = not stated, dropped); 2012 and 2022 use the published ISCO-08 major group (11, 12, 99 dropped).
               ISCO-88 and ISCO-08 major groups are close at one digit but not identical. In 2022 farming counts as work only
               if mainly for the market, so group 6 is undercounted in 2022.
  Household size   mean persons per household in the sector (household-weighted), from Census_pooled_household.dta:
               persons counted (2002), household size (2012, 2022; occupants in 2012 if size is missing).

Usage:  python data-build/sector_work_type.py
Output: data/harmonized/analysis-panels/sector_work_type.csv
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyreadstat

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import paths as P  # noqa: E402

PERSON = P.NISR / "Census-PHC/3_Final/Census_pooled_person.dta"
HOUSE = P.NISR / "Census-PHC/3_Final/Census_pooled_household.dta"
OCC = {1: "managers", 2: "professionals", 3: "technicians", 4: "clerical", 5: "service_sales", 6: "skilled_ag",
       7: "craft", 8: "operators", 9: "elementary"}


def occupation(d: pd.DataFrame) -> pd.Series:
    out = pd.Series(np.nan, index=d.index)
    m = d.census_year == 2002
    c = pd.to_numeric(d.loc[m, "census_occupation_isco88_2002"], errors="coerce")
    out[m] = (c // 100).where(c.between(100, 998))
    for y in (2012, 2022):
        m = d.census_year == y
        g = pd.to_numeric(d.loc[m, f"census_isco_major_group_{y}"], errors="coerce")
        out[m] = g.where(g.between(1, 9))
    return out


def main() -> int:
    cols = ["census_year", "census_sector", "census_age", "census_weight", "census_occupation_isco88_2002",
            "census_isco_major_group_2012", "census_isco_major_group_2022"]
    p, _ = pyreadstat.read_dta(str(PERSON), usecols=cols)
    p = p[(p.census_age >= 16) & p.census_year.isin((2002, 2012, 2022))].copy()
    p["occ"] = occupation(p)
    p["w"] = p.census_weight.fillna(1.0)
    p["wave"] = p.census_year.astype(int)
    p["sid"] = p.census_sector.astype(int)
    adults = p.groupby(["sid", "wave"]).w.sum().rename("adults16")
    occ = p[p.occ.notna()].pivot_table(index=["sid", "wave"], columns="occ", values="w", aggfunc="sum", fill_value=0.0)
    occ.columns = [f"occ_{OCC[int(c)]}" for c in occ.columns]
    occ["occ_total"] = occ.sum(axis=1)

    h, _ = pyreadstat.read_dta(str(HOUSE), usecols=["census_wave", "census_sector", "census_household_weight", "census_weight",
                                                    "census_persons_counted_2002", "census_household_size", "census_occupants_2012"])
    h["wave"] = h.census_wave.astype(str).astype(int)
    size = pd.to_numeric(h.census_household_size, errors="coerce")
    size = size.fillna(pd.to_numeric(h.census_persons_counted_2002, errors="coerce")).fillna(pd.to_numeric(h.census_occupants_2012, errors="coerce"))
    h["hsize"] = size.where(size.between(1, 40))
    hw = h.census_household_weight.fillna(h.census_weight).fillna(1.0)
    h["w"] = hw
    h = h[h.hsize.notna() & h.wave.isin((2002, 2012, 2022))]
    h["sid"] = h.census_sector.astype(int)
    hh = h.groupby(["sid", "wave"]).apply(lambda g: np.average(g["hsize"], weights=g.w), include_groups=False).rename("hh_size")
    out = pd.concat([adults, occ, hh], axis=1).reset_index()
    path = P.HARM_PANELS / "sector_work_type.csv"
    out.to_csv(path, index=False)
    print(f"[work-type] {out.sid.nunique()} sectors x {out.wave.nunique()} waves; hh_size missing {int(out.hh_size.isna().sum())}; occupation coverage:")
    print(out.groupby("wave")[["adults16", "occ_total", "occ_service_sales", "occ_skilled_ag"]].sum().round(0))
    print(out.groupby("wave").hh_size.describe().round(2))
    print(f"-> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
