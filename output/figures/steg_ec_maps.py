"""
steg_ec_maps.py -- services establishments with paid staff per 1,000 residents by sector, 2014, for the STEG appendix.

    python steg_ec_maps.py
    output/figures/steg_ec2014_services_map.pdf

One map (Matteo, 2026-09-15): establishments whose main activity is in services, ISIC sections G-S, with at
least one paid employee, per 1,000 residents, in quartiles of the 416 sectors, shades of blue (red until
2026-09-15). Lakes are drawn paler than the lightest blue class so they cannot be read as a sector.

Establishments: NISR Establishment Census 2014, main activity section, weighted with the file's sampling
weight (the public file keeps about one establishment in two, weight 2). 2014 is the last round with sector
codes; 2017-2023 carry the district only.

Paid employees stand in for employees outside the family. EC 2014 splits an establishment's workers into
working owners, unpaid workers, apprentices and paid workers by contract length (under 1 month, 1-6 months,
over 6 months, open-ended), and these add up to total workers in 99.9% of records. It has no family
variable, so owners, unpaid helpers and apprentices are left out. 23% of establishments have at least one
paid worker.

Residents: 2012 Population and Housing Census, persons summed with the census weight by sector.

Boundaries: NISR 2022 sector boundaries, all 416 sectors, six invalid rings repaired with make_valid; the
Establishment Census codes match all 416. Parks: the national-park polygons of the Government of Rwanda
protected-areas layer, drawn in green over the sectors with no sector borders on top. Lakes in blue from
OpenStreetMap (geo-data/water, see its README), cut to the frame of the sectors.

Tried and dropped, all in git history: all establishments per 1,000 residents (in 2014, 88% of accommodation
and food establishments have one or two workers, so rural bars dominate), at least four paid employees, a
tourism-only map on sections I and R, and a 2011 map of hotels, travel agencies and museums (504
establishments in 105 sectors, too sparse).
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

EC = P.NISR / "Establishment-Census-EC" / "4_Harmonized" / "H_EC_establishment.dta"
CENSUS = P.NISR / "Census-PHC" / "4_Harmonized" / "H_Census_person.dta"
SECTORS = P.NISR / "geodata-nisr" / "Sector_Boundary_2022_956146177651063157.geojson"
PARKS = P.DATA / "geo-data" / "protected-areas" / "rwanda_protected_areas_geodata_rw.gpkg"
LAKES = P.DATA / "geo-data" / "water" / "rwanda_lakes_osm.geojson"
CRS = 32736
SERVICES = list(range(7, 20))          # ISIC sections G-S
PAID = ["ec_contract_under_1m_total_2014", "ec_contract_1_6m_total_2014", "ec_contract_over_6m_total_2014",
        "ec_open_contract_total_2014"]
MIN_PAID = 1
PARK, PARK_EDGE, EDGE = "#2E6B3E", "#1C4527", "#9a9a9a"
WATER, WATER_EDGE = "#9ecae1", "#6baed6"
num = lambda s: pd.to_numeric(s, errors="coerce")


def data():
    s = gpd.read_file(SECTORS)
    s["geometry"] = s.geometry.apply(make_valid)
    s["sid"] = s.sector_id.astype(int)
    s = s.to_crs(CRS)
    assert len(s) == 416 and s.sid.nunique() == 416 and s.is_valid.all()

    e, _ = pyreadstat.read_dta(str(EC), usecols=["ec_year", "ec_sector", "ec_weight", "ec_main_activity_section_2014"] + PAID)
    e = e[e.ec_year == 2014].copy()
    e["sid"], e["sec"], e["w"] = num(e.ec_sector).astype(int), num(e.ec_main_activity_section_2014), num(e.ec_weight)
    e["paid"] = e[PAID].apply(num).fillna(0).sum(axis=1)
    est = e[e.sec.isin(SERVICES) & (e.paid >= MIN_PAID)].groupby("sid").w.sum().rename("services")

    c, _ = pyreadstat.read_dta(str(CENSUS), usecols=["census_year", "census_sector", "census_weight"])
    c = c[c.census_year == 2012]
    pop = c.groupby(num(c.census_sector).astype(int)).census_weight.sum().rename("pop2012")

    s = s.merge(est, left_on="sid", right_index=True, how="left").merge(pop, left_on="sid", right_index=True, how="left")
    s["services"] = s.services.fillna(0)
    assert s.pop2012.notna().all() and len(s) == 416
    s["per_1000"] = s.services / s.pop2012 * 1000
    return s


def main():
    s = data()
    pk = gpd.read_file(PARKS)
    pk = pk[pk.designate.astype(str).str.contains("National Park", case=False, na=False)].to_crs(CRS)
    lk = gpd.clip(gpd.read_file(LAKES).to_crs(CRS), box(*s.total_bounds))
    print(f"sectors {len(s)} | residents 2012 {s.pop2012.sum():,.0f} | services establishments with >= {MIN_PAID} paid "
          f"employee: {s.services.sum():,.0f}, sectors with none {(s.services == 0).sum()} | top 5: " +
          ", ".join(f"{r.sector} ({r.district}) {r.per_1000:.1f}" for _, r in s.nlargest(5, "per_1000").iterrows()))

    v = s.per_1000.to_numpy()
    assert (v > 0).all()
    edges = np.quantile(v, [0, .25, .5, .75, 1])
    k = np.clip(np.searchsorted(edges, v, side="right") - 1, 0, 3)
    colours = [matplotlib.colors.to_hex(c) for c in plt.get_cmap("Blues")(np.linspace(.45, 1.0, 4))]
    water = "#dcecf7"                  # paler than the lightest class, so a lake never reads as a sector
    fmt = lambda x: f"{x:.2f}" if x < 1 else (f"{x:.1f}" if x < 10 else f"{x:.0f}")
    names = ["Bottom 25%", "25–50%", "50–75%", "Top 25%"]

    fig, ax = plt.subplots(figsize=(7.5, 7))
    s.plot(ax=ax, color=[colours[i] for i in k], edgecolor=EDGE, linewidth=.25, zorder=1)
    pk.plot(ax=ax, facecolor=PARK, edgecolor=PARK_EDGE, linewidth=.5, zorder=2)
    lk.plot(ax=ax, facecolor=water, edgecolor=WATER_EDGE, linewidth=.3, zorder=3)
    handles = [Patch(facecolor=colours[i], edgecolor=EDGE, label=f"{names[i]}:  {fmt(edges[i])} – {fmt(edges[i + 1])}")
               for i in range(4)] + [Patch(facecolor=PARK, edgecolor=PARK_EDGE, label="National park"),
                                     Patch(facecolor=water, edgecolor=WATER_EDGE, label="Lake")]
    ax.legend(handles=handles, title="Establishments per\n1,000 residents", loc="center left", bbox_to_anchor=(1.0, .3),
              frameon=False, fontsize=8.5, title_fontsize=9, alignment="left")
    ax.set_axis_off()
    out = P.FIGS / "steg_ec2014_services_map.pdf"
    fig.savefig(out, bbox_inches="tight"); plt.close(fig)
    print(f"written {out}")


if __name__ == "__main__":
    main()
