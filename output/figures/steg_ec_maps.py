"""
steg_ec_maps.py -- services and tourism establishments per 1,000 residents by sector, 2014, for the STEG appendix.

    python steg_ec_maps.py
    output/figures/steg_ec2014_services_map.pdf    ISIC sections G-S
    output/figures/steg_ec2014_tourism_map.pdf     ISIC sections I (accommodation & food) and R (arts,
                                                   entertainment & recreation)
    output/figures/steg_ec2014_{services,tourism}_map_paid{1,4}.pdf
                                                   the same two 2014 maps, counting only establishments with at
                                                   least 1 / at least 4 paid employees
    output/figures/steg_ec2011_tourism_map.pdf     2011, number of tourist establishments: hotels and lodges
                                                   (ISIC 55), travel agencies and tour operators (79), arts,
                                                   museums, parks and recreation (90, 91, 93)

2011 replaces the per-resident 2014 measure for tourism (Matteo, 2026-09-15): in 2014, 88% of section I and
R establishments have one or two workers, so per 1,000 residents the map shows rural bars, not tourism.
EC 2011 is a full count (weight 1) with ISIC codes, so restaurants and bars (56) and gambling (92) can be
left out. Codes are three or four digits; three-digit codes are read as their four-digit class.

Establishments: NISR Establishment Census 2014, main activity section, weighted with the file's sampling
weight (the public file keeps about one establishment in two, weight 2). 2014 records only the one-digit
ISIC section, so travel agencies and tour operators (inside N) cannot be separated, and I is mostly
restaurants and bars. It is the last round with sector codes; 2017-2023 carry the district only.

Employees outside the family (Matteo, 2026-09-15): EC 2014 splits an establishment's workers into working
owners, unpaid workers, apprentices and paid workers by contract length (under 1 month, 1-6 months, over
6 months, open-ended), and these add up to total workers in 99.9% of records. It has no family variable,
so paid workers on any contract stand in for employees outside the family; owners, unpaid helpers and
apprentices are left out. 23% of establishments have at least one, 8% at least four.

Residents: 2012 Population and Housing Census, persons summed with the census weight by sector.

Boundaries: NISR 2022 sector boundaries, all 416 sectors, six invalid rings repaired with make_valid;
the Establishment Census codes match all 416. Parks: the national-park polygons of the Government of
Rwanda protected-areas layer, drawn in green over the sectors, with the sector edges drawn again on top
so no sector disappears under a park. Lakes in blue from OpenStreetMap (geo-data/water, see its README),
cut to the frame of the sectors.

Colours are quintiles of the 416 sectors, so each class holds about 83 sectors; where some sectors have
none, they get their own grey class and the quintiles are taken over the rest.
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
TOURISM_2011 = [55, 79, 90, 91, 93]    # ISIC divisions
PAID = ["ec_contract_under_1m_total_2014", "ec_contract_1_6m_total_2014", "ec_contract_over_6m_total_2014",
        "ec_open_contract_total_2014"]
MIN_PAID = (1, 4)
COUNT_BINS = [0, 1, 2, 5, 10, 20]      # 0 | 1 | 2-4 | 5-9 | 10-19 | 20+
NONE = "#f2f2f2"
PARK, PARK_EDGE, EDGE = "#2E6B3E", "#1C4527", "#9a9a9a"
WATER, WATER_EDGE = "#9ecae1", "#6baed6"
num = lambda s: pd.to_numeric(s, errors="coerce")


def data():
    s = gpd.read_file(SECTORS)
    s["geometry"] = s.geometry.apply(make_valid)
    s["sid"] = s.sector_id.astype(int)
    s = s.to_crs(CRS)
    assert len(s) == 416 and s.sid.nunique() == 416 and s.is_valid.all()

    e, _ = pyreadstat.read_dta(str(EC), usecols=["ec_year", "ec_sector", "ec_weight", "ec_main_activity_section_2014",
                                                 "ec_main_activity_isic_2011"] + PAID)
    o = e[e.ec_year == 2011].copy()
    e = e[e.ec_year == 2014].copy()
    e["sid"], e["sec"], e["w"] = num(e.ec_sector).astype(int), num(e.ec_main_activity_section_2014), num(e.ec_weight)
    e["paid"] = e[PAID].apply(num).fillna(0).sum(axis=1)
    code = num(o.ec_main_activity_isic_2011)
    code = code.where(code >= 1000, code * 10)
    o["sid"], o["div"] = num(o.ec_sector).astype(int), code // 100
    assert num(o.ec_weight).eq(1).all()
    counts = pd.DataFrame({"services": e[e.sec.isin(SERVICES)].groupby("sid").w.sum(),
                           "tourism": e[e.sec.isin(TOURISM)].groupby("sid").w.sum(),
                           "tourism2011": o[o["div"].isin(TOURISM_2011)].groupby("sid").size()})
    for k in MIN_PAID:
        p = e[e.paid >= k]
        counts[f"services_paid{k}"] = p[p.sec.isin(SERVICES)].groupby("sid").w.sum()
        counts[f"tourism_paid{k}"] = p[p.sec.isin(TOURISM)].groupby("sid").w.sum()

    c, _ = pyreadstat.read_dta(str(CENSUS), usecols=["census_year", "census_sector", "census_weight"])
    c = c[c.census_year == 2012]
    pop = c.groupby(num(c.census_sector).astype(int)).census_weight.sum().rename("pop2012")

    s = s.merge(counts, left_on="sid", right_index=True, how="left").merge(pop, left_on="sid", right_index=True, how="left")
    s[list(counts.columns)] = s[list(counts.columns)].fillna(0)
    assert s.pop2012.notna().all() and len(s) == 416
    for k in ["services", "tourism"] + [f"{m}_paid{n}" for m in ("services", "tourism") for n in MIN_PAID]:
        s[f"{k}_per_1000"] = s[k] / s.pop2012 * 1000
    return s


def parks():
    pk = gpd.read_file(PARKS)
    return pk[pk.designate.astype(str).str.contains("National Park", case=False, na=False)].to_crs(CRS)


def lakes(s):
    """OSM lakes, cut to the map's frame so Kivu's DRC shore does not widen the map"""
    x0, y0, x1, y1 = s.total_bounds
    return gpd.clip(gpd.read_file(LAKES).to_crs(CRS), box(x0, y0, x1, y1))


def render(s, pk, lk, fill, classes, title, fname):
    """fill: one colour per sector; classes: (colour, label) for the legend"""
    fig, ax = plt.subplots(figsize=(7.5, 7))
    s.plot(ax=ax, color=fill, edgecolor=EDGE, linewidth=.25, zorder=1)
    pk.plot(ax=ax, facecolor=PARK, edgecolor=PARK_EDGE, linewidth=.5, alpha=.85, zorder=2)
    lk.plot(ax=ax, facecolor=WATER, edgecolor=WATER_EDGE, linewidth=.3, zorder=2.5)
    s.boundary.plot(ax=ax, color=EDGE, linewidth=.2, zorder=3)
    handles = [Patch(facecolor=c, edgecolor=EDGE, label=l) for c, l in classes] + [
        Patch(facecolor=PARK, edgecolor=PARK_EDGE, label="National park"),
        Patch(facecolor=WATER, edgecolor=WATER_EDGE, label="Lake")]
    ax.legend(handles=handles, title=title, loc="center left", bbox_to_anchor=(1.0, .3),
              frameon=False, fontsize=8.5, title_fontsize=9, alignment="left")
    ax.set_axis_off()
    fig.savefig(P.FIGS / fname, bbox_inches="tight"); plt.close(fig)
    print(f"written {P.FIGS / fname}")


def draw(s, pk, lk, col, fname, cmap):
    """quintiles of the 416 sectors; sectors with none get their own grey class and the quintiles cover the rest"""
    v = s[col].to_numpy()
    pos = v > 0
    edges = np.unique(np.quantile(v[pos], np.linspace(0, 1, 6)))
    k = np.clip(np.searchsorted(edges, v, side="right") - 1, 0, len(edges) - 2)
    colours = [matplotlib.colors.to_hex(c) for c in plt.get_cmap(cmap)(np.linspace(.15, .9, len(edges) - 1))]
    fmt = lambda x: f"{x:.2f}" if x < 1 else (f"{x:.1f}" if x < 10 else f"{x:.0f}")
    classes = [(colours[i], f"{fmt(edges[i])} – {fmt(edges[i + 1])}") for i in range(len(edges) - 1)]
    fill =[colours[i] if p else NONE for i, p in zip(k, pos)]
    if (~pos).any():
        classes = [(NONE, f"0  ({int((~pos).sum())} sectors)")] + classes
    render(s, pk, lk, fill, classes, "Establishments per\n1,000 residents", fname)


def draw_counts(s, pk, lk, col, fname, cmap, title):
    """fixed count classes, zero in light grey"""
    v = s[col].to_numpy()
    k = np.searchsorted(COUNT_BINS, v, side="right") - 1
    colours = [NONE] + [matplotlib.colors.to_hex(c) for c in plt.get_cmap(cmap)(np.linspace(.3, .95, len(COUNT_BINS) - 1))]
    labels = []
    for lo, hi in zip(COUNT_BINS, COUNT_BINS[1:] + [None]):
        labels.append(f"{lo}+" if hi is None else (f"{lo}" if hi - lo == 1 else f"{lo} – {hi - 1}"))
    classes = [(c, f"{l}  ({int((k == i).sum())} sectors)") for i, (c, l) in enumerate(zip(colours, labels))]
    render(s, pk, lk, [colours[i] for i in k], classes, title, fname)


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
    for n in MIN_PAID:
        for k, cmap in (("services", "Blues"), ("tourism", "Oranges")):
            c = f"{k}_paid{n}_per_1000"
            print(f"{k}, >= {n} paid: {s[f'{k}_paid{n}'].sum():,.0f} establishments, {(s[c] == 0).sum()} sectors with none | top 5: " +
                  ", ".join(f"{r.sector} ({r.district}) {r[c]:.1f}" for _, r in s.nlargest(5, c).iterrows()))
            draw(s, pk, lk, c, f"steg_ec2014_{k}_map_paid{n}.pdf", cmap)
    t = s.tourism2011
    print(f"tourism 2011: {t.sum():,.0f} establishments, {(t > 0).sum()} sectors with any | top 8: " +
          ", ".join(f"{r.sector} ({r.district}) {r.tourism2011:.0f}" for _, r in s.nlargest(8, "tourism2011").iterrows()))
    draw_counts(s, pk, lk, "tourism2011", "steg_ec2011_tourism_map.pdf", "Oranges", "Tourism establishments")


if __name__ == "__main__":
    main()
