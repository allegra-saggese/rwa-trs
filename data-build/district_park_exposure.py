"""
district_park_exposure.py -- district exposure to park tourism: population share living in park-adjacent sectors.

For district d and Census wave t (2002, 2012, 2022):

    exposure_dt = sum over sectors s in d of  pop_st * Park_s  /  sum over sectors s in d of pop_st

  Park_s   1 if the sector borders a national park: model_sector_cross.csv, column border (62 sectors outside Kigali).
  pop_st   total population of the sector in the Census wave (analysis-panels/sector_pop_total.csv).

This reproduces the construction of district-park-exposure.csv exactly, except for the park flag. That file uses an
older flag that marks 51 sectors (it misses 9 Gishwati, 1 Nyungwe and 1 Akagera sector) and labels Gishwati sectors in
Nyabihu and Rubavu as Volcanoes. Here the flag is `border`, and the parks column names every park a district borders.
Per-park exposure (population share in sectors whose nearest park is that park) is added for regressions with one
dummy per park. Gishwati and Mukura are one park (Gishwati-Mukura National Park, created 2015).

Kigali City districts (11, 12, 13) are dropped: 27 districts. The old file is left as it is.

Usage
    python data-build/district_park_exposure.py
Output: data/harmonized/district/district-park-exposure-border.csv
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import paths as P  # noqa: E402

KIGALI = {11, 12, 13}
WAVES = (2002, 2012, 2022)
PARK_NAME = {"Volcanoes National Park": "volcanoes", "Akagera National Park": "akagera", "Nyungwe National Park": "nyungwe",
             "Gishwati": "gishwati_mukura", "Mukura": "gishwati_mukura"}
PARKS = ["volcanoes", "akagera", "nyungwe", "gishwati_mukura"]


def main() -> int:
    cross = pd.read_csv(P.HARMONIZED / "model_sector_cross.csv")[["sid", "district_id", "district", "border", "nearest_park"]]
    cross = cross[~cross.district_id.isin(KIGALI)].copy()
    cross["park"] = cross.nearest_park.map(PARK_NAME).where(cross.border == 1)
    pop = pd.read_csv(P.HARM_PANELS / "sector_pop_total.csv")
    d = pop.merge(cross, on="sid", how="inner", validate="m:1")
    assert d.sid.nunique() == len(cross) == 381, "expected 381 sectors outside Kigali"

    rows = []
    for k, g in d.groupby("district_id"):
        one = g[g.wave == WAVES[0]]
        r = {"district_id": k, "district": one.district.iloc[0], "n_sectors": len(one), "n_adjacent_sectors": int(one.border.sum()),
             "n_parks": one.park.nunique(), "parks": "-".join(sorted(one.park.dropna().unique())),
             "adj_share_sectors": one.border.mean()}
        for t in WAVES:
            w = g[g.wave == t]
            r[f"adj_share_pop_{t}"] = (w.pop_total * w.border).sum() / w.pop_total.sum()
            for p in PARKS:
                r[f"pop_share_{p}_{t}"] = (w.pop_total * (w.park == p)).sum() / w.pop_total.sum()
        rows.append(r)
    out = pd.DataFrame(rows).sort_values("district_id")
    path = P.HARM_DISTRICT / "district-park-exposure-border.csv"
    out.to_csv(path, index=False)
    exposed = out[out.n_parks > 0]
    print(f"[district-exposure] {len(out)} districts, {len(exposed)} with a park-adjacent sector, "
          f"{int(out.n_adjacent_sectors.sum())} park-adjacent sectors")
    print(exposed[["district", "n_adjacent_sectors", "parks", "adj_share_pop_2002", "adj_share_pop_2022"]].round(3).to_string(index=False))
    print(f"-> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
