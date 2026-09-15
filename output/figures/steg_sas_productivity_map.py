"""
steg_sas_productivity_map.py -- crop output per hectare by district, 2025, for the STEG appendix.

    python steg_sas_productivity_map.py
    output/figures/steg_sas_productivity_map_2025.pdf

MEASURE. NISR Seasonal Agricultural Survey 2025 (the latest wave; 2023 until 2026-09-15), seasons A and B, small-scale farms, ten staples (maize, bush
and climbing bean, cassava, the three bananas, sweet and Irish potato, sorghum). Output is valued at fixed
prices, each crop's national median selling price over 2018-2025, and divided by harvested area; each district
value is the weighted sum of output value over the weighted sum of area. Plot-crop records above their crop's
99th percentile of value per hectare are dropped. District is the finest geography SAS releases.

DATA NOTES, each found in the data rather than assumed.
    999 and 9999 are don't-know codes in the selling price, 30-40% of recorded prices; they are excluded, or
        maize, beans and sweet potato would be priced at 999 RWF/kg.
    Area is harvested area, recorded in 2018-2019, 2022-2023 and 2025 (2025 also records crop area, of which
        harvested area is 79%); 2021 crop area is about three times the 2020 distribution and 2024 has no area
        at all, which is why this is a single-year map.

SEASONS. Seasons A and B are the two main rain-fed seasons. Season C is the small mid-year dry-season crop,
mostly in marshlands and valley bottoms, with 2.7% of the 2025 plot-crop records (1,884 of 69,173; 4.5% in
2023), so it is left out. A and B are not averaged: output value is summed over both seasons and
divided by harvested area summed over both, so a hectare cropped in both seasons counts twice.

Colours split the 30 districts into three groups of ten, in shades of yellow (Matteo, 2026-09-15; quartiles
before). District boundaries are the NISR 2022 sectors dissolved by district; parks and lakes as in
steg_ec_maps.py.
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd, geopandas as gpd, pyreadstat, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from shapely.geometry import box
from shapely.validation import make_valid
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import paths as P
import steg_ec_maps as M

SAS = P.NISR / "Season-Agriculture-Survey-SAS" / "4_Harmonized" / "H_SAS_plotcrop.dta"
YEAR = 2025                            # latest wave; 2023 until 2026-09-15
BASKET = ["Maize", "Bush bean", "Climbing bean", "Cassava", "Banana for beer", "Cooking banana", "Dessert banana",
          "Sweet potato", "Irish potato", "Sorghum"]
PRICES = ["sas_selling_price_2018_2022", "sas_selling_price_2023_2025"]
DONT_KNOW = [999, 9999, 99999]
COLOURS = ["#fff0a0", "#f7c52b", "#b98500"]                      # light to dark yellow
NAMES = ["Bottom 10 districts", "Middle 10", "Top 10"]


def district_values():
    d, _ = pyreadstat.read_dta(str(SAS), usecols=["sas_year", "sas_season", "sas_district", "sas_farm_type", "sas_weight",
                                                  "sas_crop_name", "sas_production_kg", "sas_harvested_area_ha"] + PRICES)
    d = d[d.sas_season.isin(["A", "B"]) & (d.sas_farm_type == 1) & d.sas_crop_name.isin(BASKET)].copy()
    pr = pd.concat([d[["sas_crop_name", c]].rename(columns={c: "p"}) for c in PRICES]).dropna()
    pr = pr[(pr.p > 0) & ~pr.p.isin(DONT_KNOW)]
    price = pr.groupby("sas_crop_name").p.apply(lambda s: s[(s >= s.quantile(.01)) & (s <= s.quantile(.99))].median())
    print("fixed prices, RWF/kg:", price.round(0).to_dict())

    g = d[d.sas_year == YEAR].copy()
    g["area"], g["price"] = g.sas_harvested_area_ha, g.sas_crop_name.map(price)
    g = g[(g.area > 0) & (g.sas_production_kg >= 0)]
    g["v"] = g.sas_production_kg * g.price
    g["vha"] = g.v / g.area
    g = g[g.vha <= g.groupby("sas_crop_name").vha.transform(lambda s: s.quantile(.99))]
    g["did"] = pd.to_numeric(g.sas_district, errors="coerce").astype(int)
    return g.groupby("did").apply(lambda h: pd.Series({
        "value_ha": (h.v * h.sas_weight).sum() / (h.area * h.sas_weight).sum() / 1e3, "records": len(h)}))


def main():
    dist = district_values()
    s = gpd.read_file(M.SECTORS)
    s["geometry"] = s.geometry.apply(make_valid)
    s["did"] = s.district_id.astype(int)
    dm = s.to_crs(M.CRS).dissolve("did", as_index=False)[["did", "district", "geometry"]].merge(dist, on="did", how="left")
    assert len(dm) == 30 and dm.value_ha.notna().all()
    print(dm.sort_values("value_ha", ascending=False)[["district", "value_ha", "records"]].round(0).to_string(index=False))
    pk = gpd.read_file(M.PARKS)
    pk = pk[pk.designate.astype(str).str.contains("National Park", case=False, na=False)].to_crs(M.CRS)
    lk = gpd.clip(gpd.read_file(M.LAKES).to_crs(M.CRS), box(*dm.total_bounds))

    rank = dm.value_ha.rank(method="first").astype(int) - 1          # 0..29, ties broken by order
    k = (rank // 10).to_numpy()
    edges = [dm.value_ha[k == i].min() for i in range(3)] + [dm.value_ha.max()]
    bounds = [(dm.value_ha[k == i].min(), dm.value_ha[k == i].max()) for i in range(3)]
    fig, ax = plt.subplots(figsize=(7.5, 7))
    dm.plot(ax=ax, color=[COLOURS[i] for i in k], edgecolor="#9a9a9a", linewidth=.6, zorder=1)
    pk.plot(ax=ax, facecolor=M.PARK, edgecolor=M.PARK_EDGE, linewidth=.5, zorder=2)
    lk.plot(ax=ax, facecolor=M.WATER, edgecolor=M.WATER_EDGE, linewidth=.3, zorder=3)
    handles = [Patch(facecolor=COLOURS[i], edgecolor="#9a9a9a", label=f"{NAMES[i]}:  {bounds[i][0]:,.0f} – {bounds[i][1]:,.0f}")
               for i in range(3)]
    handles += [Patch(facecolor=M.PARK, edgecolor=M.PARK_EDGE, label="National park"),
                Patch(facecolor=M.WATER, edgecolor=M.WATER_EDGE, label="Lake")]
    ax.legend(handles=handles, title=f"Crop output per hectare, {YEAR},\nthousand RWF at fixed prices",
              loc="center left", bbox_to_anchor=(1.0, .3), frameon=False, fontsize=8.5, title_fontsize=9, alignment="left")
    ax.set_axis_off()
    out = P.FIGS / f"steg_sas_productivity_map_{YEAR}.pdf"
    fig.savefig(out, bbox_inches="tight"); plt.close(fig)
    print(f"written {out}")


if __name__ == "__main__":
    main()
