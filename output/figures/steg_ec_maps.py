"""
steg_ec_maps.py -- services and tourism establishments per 1,000 residents by sector, 2014, for the STEG appendix.

    python steg_ec_maps.py
    output/figures/steg_ec2014_services_map.pdf    ISIC sections G-S
    output/figures/steg_ec2014_tourism_map.pdf     ISIC sections I (accommodation & food) and R (arts,
                                                   entertainment & recreation)

Establishments: NISR Establishment Census 2014, main activity section, weighted with the file's sampling
weight (the public file keeps about one establishment in two, weight 2). 2014 records only the one-digit
ISIC section, so travel agencies and tour operators (inside N) cannot be separated, and I is mostly
restaurants and bars. It is the last round with sector codes; 2017-2023 carry the district only.

Residents: 2012 Population and Housing Census, persons summed with the census weight by sector.

Boundaries: NISR 2022 sector boundaries, all 416 sectors, six invalid rings repaired with make_valid;
the Establishment Census codes match all 416. Parks: the national-park polygons of the Government of
Rwanda protected-areas layer, drawn in green over the sectors, with the sector edges drawn again on top
so no sector disappears under a park. Lakes in blue from OpenStreetMap (geo-data/water, see its README),
cut to the frame of the sectors.

Colours are quintiles of the 416 sectors, so each class holds about 83 sectors.
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
SERVICES = list(range(7, 20))          # G-S
TOURISM = [9, 18]                      # I, R
PARK, PARK_EDGE, EDGE = "#2E6B3E", "#1C4527", "#9a9a9a"
WATER, WATER_EDGE = "#9ecae1", "#6baed6"
num = lambda s: pd.to_numeric(s, errors="coerce")


def data():
    s = gpd.read_file(SECTORS)
    s["geometry"] = s.geometry.apply(make_valid)
    s["sid"] = s.sector_id.astype(int)
    s = s.to_crs(CRS)
    assert len(s) == 416 and s.sid.nunique() == 416 and s.is_valid.all()

    e, _ = pyreadstat.read_dta(str(EC), usecols=["ec_year", "ec_sector", "ec_weight", "ec_main_activity_section_2014"])
    e = e[e.ec_year == 2014]
    e["sid"], e["sec"], e["w"] = num(e.ec_sector).astype(int), num(e.ec_main_activity_section_2014), num(e.ec_weight)
    counts = pd.DataFrame({"services": e[e.sec.isin(SERVICES)].groupby("sid").w.sum(),
                           "tourism": e[e.sec.isin(TOURISM)].groupby("sid").w.sum()})

    c, _ = pyreadstat.read_dta(str(CENSUS), usecols=["census_year", "census_sector", "census_weight"])
    c = c[c.census_year == 2012]
    pop = c.groupby(num(c.census_sector).astype(int)).census_weight.sum().rename("pop2012")

    s = s.merge(counts, left_on="sid", right_index=True, how="left").merge(pop, left_on="sid", right_index=True, how="left")
    s[["services", "tourism"]] = s[["services", "tourism"]].fillna(0)
    assert s.pop2012.notna().all() and len(s) == 416
    for k in ("services", "tourism"):
        s[f"{k}_per_1000"] = s[k] / s.pop2012 * 1000
    return s


def parks():
    pk = gpd.read_file(PARKS)
    return pk[pk.designate.astype(str).str.contains("National Park", case=False, na=False)].to_crs(CRS)


def lakes(s):
    """OSM lakes, cut to the map's frame so Kivu's DRC shore does not widen the map"""
    x0, y0, x1, y1 = s.total_bounds
    return gpd.clip(gpd.read_file(LAKES).to_crs(CRS), box(x0, y0, x1, y1))


def draw(s, pk, lk, col, fname, cmap):
    v = s[col]
    edges = np.unique(np.quantile(v, np.linspace(0, 1, 6)))
    k = np.clip(np.searchsorted(edges, v, side="right") - 1, 0, len(edges) - 2)
    colours = plt.get_cmap(cmap)(np.linspace(.15, .9, len(edges) - 1))
    fig, ax = plt.subplots(figsize=(7.5, 7))
    s.plot(ax=ax, color=[matplotlib.colors.to_hex(colours[i]) for i in k], edgecolor=EDGE, linewidth=.25, zorder=1)
    pk.plot(ax=ax, facecolor=PARK, edgecolor=PARK_EDGE, linewidth=.5, alpha=.85, zorder=2)
    lk.plot(ax=ax, facecolor=WATER, edgecolor=WATER_EDGE, linewidth=.3, zorder=2.5)
    s.boundary.plot(ax=ax, color=EDGE, linewidth=.2, zorder=3)
    fmt = lambda x: f"{x:.1f}" if x < 10 else f"{x:.0f}"
    handles = [Patch(facecolor=colours[i], edgecolor=EDGE, label=f"{fmt(edges[i])} – {fmt(edges[i + 1])}")
               for i in range(len(edges) - 1)] + [Patch(facecolor=PARK, edgecolor=PARK_EDGE, label="National park"),
                                                  Patch(facecolor=WATER, edgecolor=WATER_EDGE, label="Lake")]
    ax.legend(handles=handles, title="Establishments per\n1,000 residents", loc="center left", bbox_to_anchor=(1.0, .3),
              frameon=False, fontsize=8.5, title_fontsize=9, alignment="left")
    ax.set_axis_off()
    fig.savefig(P.FIGS / fname, bbox_inches="tight"); plt.close(fig)
    print(f"written {P.FIGS / fname}")


def main():
    s, pk = data(), parks()
    lk = lakes(s)
    print(f"sectors {len(s)} | residents 2012 {s.pop2012.sum():,.0f} | establishments 2014: services {s.services.sum():,.0f}, "
          f"tourism {s.tourism.sum():,.0f}")
    for k in ("services", "tourism"):
        c = f"{k}_per_1000"
        print(f"{k}: per 1,000 median {s[c].median():.1f}, national {s[k].sum() / s.pop2012.sum() * 1000:.1f}, "
              f"zero sectors {(s[k] == 0).sum()} | top 5: " +
              ", ".join(f"{r.sector} ({r.district}) {r[c]:.0f}" for _, r in s.nlargest(5, c).iterrows()))
    draw(s, pk, lk, "services_per_1000", "steg_ec2014_services_map.pdf", "Blues")
    draw(s, pk, lk, "tourism_per_1000", "steg_ec2014_tourism_map.pdf", "Oranges")


if __name__ == "__main__":
    main()
