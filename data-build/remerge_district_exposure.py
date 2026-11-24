"""
remerge_district_exposure.py -- replace the old park-exposure columns in four district panels with the corrected ones.

The panels district-ag-productivity, district-household-crop-value, district-labour-status and district-land-prices
carry the exposure columns of district-park-exposure.csv (51-sector park flag). This script overwrites those columns
with district-park-exposure-border.csv (built by district_park_exposure.py from the 62-sector `border` flag) and
appends the per-park columns pop_share_<park>_<year>. Every other column and every row is left as it was (checked).
Originals are copied first to data/harmonized/district/_old-exposure/.

Usage
    python data-build/remerge_district_exposure.py
"""
import shutil
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import paths as P  # noqa: E402

PANELS = ["district-ag-productivity", "district-household-crop-value", "district-labour-status", "district-land-prices"]
EXPOSURE_COLS = ["district", "n_sectors", "n_adjacent_sectors", "n_parks", "parks", "adj_share_sectors",
                 "adj_share_pop_2002", "adj_share_pop_2012", "adj_share_pop_2022"]


def main() -> int:
    new = pd.read_csv(P.HARM_DISTRICT / "district-park-exposure-border.csv").set_index("district_id")
    extra = [c for c in new.columns if c.startswith("pop_share_")]
    backup = P.HARM_DISTRICT / "_old-exposure"
    backup.mkdir(exist_ok=True)
    for name in PANELS:
        path = P.HARM_DISTRICT / f"{name}.csv"
        old = pd.read_csv(path)
        assert all(c in old for c in EXPOSURE_COLS), f"{name}: expected exposure columns missing"
        if not (backup / path.name).exists():
            shutil.copy2(path, backup / path.name)            # keep the first original, never overwrite it
        d = old.copy()
        for c in EXPOSURE_COLS + extra:
            d[c] = d.district_id.map(new[c])
        assert list(old.columns[-len(EXPOSURE_COLS):]) == EXPOSURE_COLS, f"{name}: exposure columns are not the last block"
        d = d[list(old.columns) + extra]
        other = [c for c in old.columns if c not in EXPOSURE_COLS]
        assert len(d) == len(old) and d[other].equals(old[other]), f"{name}: non-exposure content changed"
        assert d.district_id.isin(new.index).all(), f"{name}: district missing from the new exposure file"
        d.to_csv(path, index=False)
        changed = (old.adj_share_pop_2022 - d.adj_share_pop_2022).abs().gt(1e-9).sum()
        print(f"[remerge] {name}: {len(d)} rows, exposure changed on {changed} rows, {len(extra)} per-park columns added")
    print(f"[remerge] originals in {backup}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
