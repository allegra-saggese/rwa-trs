"""
maps-treat-sectors.py -- the sector maps for the TRS analysis.

    python maps-treat-sectors.py

Writes to the Dropbox output folder (not to the repository):
    Rwanda - TRS/output/maps/map1_treatment_definitions.pdf
    Rwanda - TRS/output/maps/map2_exclusion_definitions.pdf
    Rwanda - TRS/output/maps/map3_estimation_samples.pdf

Map 1: the sectors bordering the three long-established national parks, the four park entrances
that already existed in 2005, and the sectors next to those entrances.
Map 2: the places set aside from the comparison -- Kigali, the four largest towns of 2002, and
the neighbours of Gishwati-Mukura, the park created in 2015.
Map 3: the estimation sample itself, one panel per treatment definition. What the regression
actually sees: which sectors are treated, which form the comparison group, and which are in
neither. The control group is the same 322 sectors in all three panels, by design.

Both maps are written for an audience that knows nothing about Rwanda: no internal list numbers,
no references to project files. The definitions and their justification live in the memo
TRS-Border-Sectors.md; this script re-derives every set from the geometry so the two cannot drift.

Note on the park layer: it also contains a "Gishwati Forest Reserve" polygon of 223 km2, five times
the size of the national park. Filtering on designate == National Park is what keeps it out.
"""
import textwrap
from pathlib import Path

import geopandas as gpd
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
from adjustText import adjust_text
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle
from shapely.geometry import Point

DB = Path("/Users/matteo/Library/CloudStorage/Dropbox/1-Ongoing Projects/Rwanda - TRS")
GEO = DB / "data/geo-data"
OUT = DB / "output/maps"
CRS = 32736                                    # UTM 36S, metres

C = {"park": "#2E6B3E", "park_edge": "#1C4527", "border": "#E0A33E", "gate": "#C0392B",
     "gate_fill": "#E8701A", "kig_out": "#B8D4E8", "kig_in": "#2E75A8", "urban": "#8E6BAF",
     "gish": "#B0672C", "sector_edge": "#C8C8C8", "district_edge": "#8C8C8C", "empty": "#FBFBFB",
     "treated": "#3C9A5F", "control": "#F0C74A", "dropped": "#BFBFBF"}

CITY9 = [2708, 2712, 2409, 2414, 4308, 4302, 3304, 3311, 3312]     # the four largest towns of 2002
GATES = {4307: "Kinigi", 3701: "Bushekeri", 2509: "Kitabi", 5407: "Mwiri"}

# The entrances themselves, longitude and latitude, from OpenStreetMap. Marking a gate at the
# sector's representative point put Mwiri 5 km inside Akagera and Kitabi 1.4 km inside Nyungwe,
# because a representative point only promises to fall somewhere in the polygon and these sectors
# are mostly park. These are the real features, and each one independently confirms the sector it
# is supposed to be in.
GATE_KM = 5.0                  # how far settled land may sit from an entrance, see classify()
GATE_XY = {
    4307: (29.59528, -1.43165),    # Volcanoes National Park Headquarters, Kinigi
    3701: (29.09228, -2.44059),    # Gisakura Ranger Station, the western Nyungwe entrance
    2509: (29.41697, -2.52640),    # Kitabi visitor centre, the eastern Nyungwe entrance
    5407: (30.68178, -1.89912),    # Akagera South Gate
}
KIG_RURAL = ["Gikomero", "Rutunga", "Rusororo", "Masaka", "Mageregere", "Nduba", "Jali",
             "Kanyinya", "Bumbogo", "Ndera", "Jabana"]      # >= 10 km from the Convention Centre
STARS_CITY = {"Kigali": 1109, "Gitarama": 2708, "Butare": 2409, "Ruhengeri": 4308, "Gisenyi": 3304}
PARK_NUDGE = {"Volcanoes": (0, 0), "Nyungwe": (0, -2000),
              "Akagera": (9000, 0), "Gishwati-Mukura": (-8500, 1500)}


def load():
    sec = gpd.read_file(GEO / "protected-areas/sectors_park_exposure_wdpa.gpkg").to_crs(CRS)
    sec["sid"] = sec.sector_id.astype(int)
    dist = gpd.read_file(GEO / "admin-boundaries/geodatarw_district_boundary.gpkg").to_crs(CRS)
    pk = gpd.read_file(GEO / "protected-areas/rwanda_protected_areas_geodata_rw.gpkg")
    pk = pk[pk.designate.astype(str).str.contains("National Park", case=False, na=False)].to_crs(CRS)
    parks = {n: pk[pk.areaname.astype(str).str.contains(p, case=False, na=False)].union_all()
             for n, p in [("Volcanoes", "Volcanoes"), ("Nyungwe", "Nyungwe"),
                          ("Akagera", "Akagera"), ("Gishwati-Mukura", "Gishwati|Mukura")]}
    return sec, dist, pk, parks


def classify(sec, parks, pk_all):
    long_standing = parks["Volcanoes"].union(parks["Nyungwe"]).union(parks["Akagera"])
    L = {}
    L["border"] = set(sec.sid[sec.geometry.distance(long_standing) == 0])
    L["gish"] = set(sec.sid[sec.geometry.distance(parks["Gishwati-Mukura"]) == 0])
    kig = sec[sec.province.str.contains("Kigali", na=False)]
    L["kig_all"] = set(kig.sid)
    L["kig_core"] = set(kig.sid[~kig.sector.isin(KIG_RURAL)])
    L["towns"] = set(CITY9)
    L["gates"] = set(GATES)
    # Neighbours of a gate sector, but the adjacency is measured on SETTLED LAND, not on the whole
    # polygon (Matteo, 2026-09-08). Nyungwe and Akagera are large enough that two sectors can share
    # a long boundary lying entirely inside the park, with no road, no settlement and no way for
    # traffic through the gate to reach either. Clipping each sector to its non-park part before
    # testing adjacency removes exactly four: Bweyeye (87% park) and Butare (73%) in Rusizi and
    # Karengera in Nyamasheke, all three meeting their gate inside Nyungwe, and Murundi in Kayonza,
    # which meets Mwiri across 221 km2 of Akagera. It adds none, taking the set from 25 to 21.
    # Note it is not a park-share threshold: Kivu stays at 58% park and Bushekeri at 55%, because
    # their settled land genuinely touches.
    allpark = pk_all.union_all()
    land = sec.geometry.difference(allpark)
    nb = set()
    for sid in GATES:
        gate_land = land[sec.sid == sid].iloc[0].buffer(10)
        nb |= set(sec.sid[land.buffer(10).intersects(gate_land)])

    # Second condition: the settled land must also lie within GATE_KM of the entrance itself
    # (Matteo, 2026-09-08). Adjacency alone means different things at different parks because
    # sectors are not the same size: Kayonza's average 173 km2 against 56 to 81 at the other three
    # gates, so a neighbour of Mwiri can sit 13 km from the gate while every neighbour of Kinigi is
    # within 7. The cap binds only at Akagera, which is its purpose, and it is not knife-edge --
    # anything from 9 to 11 km gives the same 19 sectors. It drops Mukarange (13.5 km) and
    # Nyamirama (11.6 km).
    #
    # It is a cap ON TOP of adjacency, not a replacement for it. Distance alone would re-admit
    # exactly what the other rules exclude: Muhoza, which is Musanze town and one of the four 2002
    # towns held out as urban; Gataraga, a trailhead rather than an entrance; and Butare and
    # Karengera, which reach their gate only through the park.
    gate_pts = gpd.GeoSeries([Point(*GATE_XY[g]) for g in GATES], crs=4326).to_crs(CRS).union_all()
    within = {int(r.sid) for r, l in zip(sec.itertuples(), land)
              if not l.is_empty and l.distance(gate_pts) <= GATE_KM * 1000}
    L["near_gates"] = nb & (within | set(GATES))
    return L


def base(ax, sec, dist, pk):
    sec.plot(ax=ax, facecolor=C["empty"], edgecolor=C["sector_edge"], linewidth=0.15, zorder=1)
    dist.boundary.plot(ax=ax, color=C["district_edge"], linewidth=0.45, zorder=6)
    pk.plot(ax=ax, facecolor=C["park"], edgecolor=C["park_edge"], linewidth=0.6, alpha=0.85, zorder=5)
    # sector edges again on top: inside a park the fill would otherwise hide which sectors adjoin
    sec.boundary.plot(ax=ax, color="#6E6E6E", linewidth=0.18, alpha=0.7, zorder=7)


def label(ax, rows, size=4.6, color="#1A1A1A"):
    """sector names, then pushed apart so none overlaps; a leader line where a name had to move"""
    texts = []
    for _, r in rows.iterrows():
        c = r.geometry.representative_point()
        texts.append(ax.text(c.x, c.y, r.sector, ha="center", va="center", fontsize=size,
                             color=color, zorder=9,
                             path_effects=[pe.withStroke(linewidth=1.4, foreground="white")]))
    return texts


def settle(ax, texts):
    adjust_text(texts, ax=ax, expand=(1.15, 1.3), force_text=(0.3, 0.5), max_move=28,
                arrowprops=dict(arrowstyle="-", color="#777777", lw=0.25, shrinkA=1, shrinkB=1))


def stars(ax, sec, mapping):
    texts = []
    for name, sid in mapping.items():
        c = sec.loc[sec.sid == sid, "geometry"].iloc[0].representative_point()
        ax.scatter([c.x], [c.y], marker="*", s=34, color=C["gate"], linewidth=0, zorder=11)
        texts.append(ax.text(c.x, c.y, name, ha="center", va="top", fontsize=6.5, color=C["gate"],
                             fontweight="bold", zorder=11,
                             path_effects=[pe.withStroke(linewidth=1.8, foreground="white")]))
    return texts


ON_GREEN = {"Nyungwe", "Akagera", "Volcanoes"}          # labels that sit on the park itself, so they go white

def park_labels(ax, parks):
    for n, g in parks.items():
        c = g.representative_point()
        dx, dy = PARK_NUDGE.get(n, (0, 0))
        on = n in ON_GREEN
        ax.annotate(n, (c.x + dx, c.y + dy), ha="center", va="center", fontsize=7.5,
                    color="white" if on else C["park_edge"], fontstyle="italic", fontweight="bold",
                    zorder=10, path_effects=[pe.withStroke(linewidth=2,
                    foreground=C["park_edge"] if on else "white")])


def finish(ax, sec, legend, note):
    """no title: the note carries everything. The bottom band is sized to its own text."""
    ax.set_axis_off()
    x0, y0, x1, y1 = sec.total_bounds
    ax.set_xlim(x0 - 4000, x1 + 4000)
    ax.set_ylim(y0 - 30000, y1 + 4000)
    ax.legend(handles=legend, loc="upper left", frameon=True, fontsize=8.5, framealpha=1.0,
              borderpad=0.9, labelspacing=0.75)
    pad = 0.008
    txt = ax.text(0.008, pad, note, transform=ax.transAxes, fontsize=5.8, va="bottom", ha="left",
                  color="#333333", linespacing=1.7, zorder=13)
    ax.figure.canvas.draw()                                   # measure the text, then fit the box
    bb = txt.get_window_extent().transformed(ax.transAxes.inverted())
    ax.add_patch(Rectangle((0, 0), 1, bb.y1 + pad, transform=ax.transAxes, facecolor="white",
                           edgecolor="#BBBBBB", linewidth=0.5, zorder=12, clip_on=False))
    txt.set_zorder(13)


NOTE1 = """CRITERIA
Bordering     Sectors next to the park and/or containing area of the park. Excludes sectors bordering Gishwati-Mukura, which became a park only in 2015.
Gates           Sectors containing the entry points to the park before 2005.
Gates+         Sectors containing entry points to the park, and neighbouring sectors.
Rwanda is divided into 5 provinces, 30 districts and 416 sectors."""

NOTE2 = """CRITERIA
Inner Kigali            Sectors of the City of Kigali within 10 km of the Kigali Convention Centre.
City of Kigali          All 35 sectors of the City of Kigali.
Other Urban Areas   Sectors covering Gitarama, Butare, Ruhengeri and Gisenyi, the four largest towns in 2002.
Gishwati Mukura     Sectors bordering Gishwati-Mukura, which became a park only in 2015.
Rwanda is divided into 5 provinces, 30 districts and 416 sectors."""


def map1(sec, dist, pk, parks, L):
    fig, ax = plt.subplots(figsize=(16.5, 11.7))
    base(ax, sec, dist, pk)
    sec[sec.sid.isin(L["border"])].plot(ax=ax, facecolor=C["border"], edgecolor="#9A6E1E",
                                        linewidth=0.3, alpha=0.85, zorder=2)
    sec[sec.sid.isin(L["near_gates"])].plot(ax=ax, facecolor="none", edgecolor="#4D4D4D",
                                            hatch="////", linewidth=0.35, zorder=3)
    sec[sec.sid.isin(L["gates"])].plot(ax=ax, facecolor=C["gate_fill"], edgecolor="#8C3F09",
                                       linewidth=0.8, zorder=4)
    park_labels(ax, parks)
    txt = label(ax, sec[sec.sid.isin(L["border"] | L["near_gates"]) & ~sec.sid.isin(L["gates"])])
    txt += stars(ax, sec, {v: k for k, v in GATES.items()})
    settle(ax, txt)
    legend = [Patch(facecolor=C["border"], edgecolor="#9A6E1E", alpha=0.85,
                    label="Bordering  (42 sectors)"),
              Patch(facecolor=C["gate_fill"], edgecolor="#8C3F09", label="Gates  (4)"),
              Patch(facecolor="white", edgecolor="#4D4D4D", hatch="////", label="Gates+  (25)"),
              Patch(facecolor=C["park"], edgecolor=C["park_edge"], alpha=0.85, label="National park")]
    finish(ax, sec, legend, NOTE1)
    fig.savefig(OUT / "map1_treatment_definitions.pdf", bbox_inches="tight")
    plt.close(fig)


def map2(sec, dist, pk, parks, L):
    fig, ax = plt.subplots(figsize=(16.5, 11.7))
    base(ax, sec, dist, pk)
    sec[sec.sid.isin(L["kig_all"] - L["kig_core"])].plot(ax=ax, facecolor=C["kig_out"],
                                                         edgecolor="#7FA8C4", linewidth=0.3, zorder=2)
    sec[sec.sid.isin(L["kig_core"])].plot(ax=ax, facecolor=C["kig_in"], edgecolor="#1B5580",
                                          linewidth=0.3, alpha=0.9, zorder=3)
    sec[sec.sid.isin(L["towns"])].plot(ax=ax, facecolor=C["urban"], edgecolor="#6B4B87",
                                       linewidth=0.3, alpha=0.9, zorder=3)
    sec[sec.sid.isin(L["gish"])].plot(ax=ax, facecolor=C["gish"], edgecolor="#7D4A1F",
                                      linewidth=0.3, alpha=0.85, zorder=3)
    park_labels(ax, parks)
    txt = label(ax, sec[sec.sid.isin(L["gish"] | L["kig_all"] | L["towns"])])
    txt += stars(ax, sec, STARS_CITY)
    settle(ax, txt)
    legend = [Patch(facecolor=C["kig_in"], edgecolor="#1B5580", alpha=0.9,
                    label="Inner Kigali  (24 sectors)"),
              Patch(facecolor=C["kig_out"], edgecolor="#7FA8C4", label="City of Kigali  (35)"),
              Patch(facecolor=C["urban"], edgecolor="#6B4B87", alpha=0.9, label="Other Urban Areas  (9)"),
              Patch(facecolor=C["gish"], edgecolor="#7D4A1F", alpha=0.85, label="Gishwati Mukura  (9)"),
              Patch(facecolor=C["park"], edgecolor=C["park_edge"], alpha=0.85, label="National Parks")]
    finish(ax, sec, legend, NOTE2)
    fig.savefig(OUT / "map2_exclusion_definitions.pdf", bbox_inches="tight")
    plt.close(fig)


NOTE3 = (
    "One panel per treatment definition, showing the sample each regression actually uses. Treated "
    "sectors are those the definition selects: sectors sharing a boundary with Volcanoes, Nyungwe or "
    "Akagera; the four sectors holding a park entrance that already existed in 2005; and the sectors "
    "adjacent to those four. The comparison group is identical in all three panels by construction -- "
    "the 322 sectors that neither border a park nor sit next to an entrance, less the City of Kigali "
    "and the four largest towns of 2002 -- so the three estimates differ only in whom they treat, "
    "never in whom they are compared against. Grey covers everything in neither group: Kigali and the "
    "four towns, which are set aside as urban outliers, together with any park-adjacent sector that "
    "belongs to one of the other two definitions and is therefore withheld from the comparison rather "
    "than counted in it. That is why the grey ring around the parks is widest in the middle panel, "
    "where only four sectors are treated but fifty are park-adjacent. Park outlines are drawn in dark "
    "green, district boundaries in grey, and the four park entrances as red dots, shown in every "
    "panel so their position can be compared against each definition. Rwanda is divided into 5 "
    "provinces, 30 districts and 416 sectors."
)


def map3(sec, dist, pk, parks, L):
    """the estimation sample, one panel per treatment definition"""
    allpark3 = pk[pk.geometry.area > 1e5].union_all()
    never = L["border"] | L["near_gates"]                  # never a control, whatever is treated
    dropped_by_design = L["kig_all"] | L["towns"]
    control = set(sec.sid) - never - dropped_by_design
    # Ordered from the widest definition to the narrowest, left to right (Matteo, 2026-09-08).
    panels = [("Bordering a park or near an entrance", L["border"] | L["near_gates"]),
              ("Near a park entrance", L["near_gates"]),
              ("Park entrance sectors", L["gates"])]

    fig, axes = plt.subplots(1, 3, figsize=(19, 8.2))
    for ax, (title, treated) in zip(axes, panels):
        excluded = set(sec.sid) - treated - control
        cls = sec.sid.map(lambda s: "treated" if s in treated
                          else ("control" if s in control else "dropped"))
        for key, z in (("dropped", 2), ("control", 3), ("treated", 4)):
            part = sec[cls == key]
            if len(part):
                part.plot(ax=ax, facecolor=C[key], edgecolor=C["sector_edge"],
                          linewidth=0.12, zorder=z)
        dist.boundary.plot(ax=ax, color=C["district_edge"], linewidth=0.4, zorder=6)
        # park outlines only: a filled park would hide the very sectors the panel is about
        pk.boundary.plot(ax=ax, color=C["park_edge"], linewidth=1.0, zorder=7)
        # the four park entrances, marked identically in every panel so the eye can compare them
        gx = gpd.GeoSeries([Point(*GATE_XY[g]) for g in GATES], crs=4326).to_crs(CRS)
        ax.scatter(gx.x, gx.y, s=46, color=C["gate"],
                   edgecolor="white", linewidth=0.6, zorder=11)
        ax.set_title(title, fontsize=11, pad=8)
        ax.set_axis_off()
        x0, y0, x1, y1 = sec.total_bounds
        ax.set_xlim(x0 - 4000, x1 + 4000)
        ax.set_ylim(y0 - 4000, y1 + 4000)
        ax.legend(handles=[
            Patch(facecolor=C["treated"], edgecolor="#2A6E43", label=f"Treated  ({len(treated)})"),
            Patch(facecolor=C["control"], edgecolor="#C2A03A", label=f"Control  ({len(control)})"),
            Patch(facecolor=C["dropped"], edgecolor="#9A9A9A", label=f"Excluded  ({len(excluded)})"),
            Line2D([], [], marker="o", linestyle="none", markersize=7, color=C["gate"],
                   markeredgecolor="white", label="Park entrance  (4)")],
            loc="upper left", frameon=True, fontsize=8.5, framealpha=1.0, borderpad=0.7,
            labelspacing=0.6)
    fig.subplots_adjust(left=0.004, right=0.996, top=0.94, bottom=0.13, wspace=0.02)
    fig.text(0.006, 0.012, "\n".join(textwrap.wrap(NOTE3, 200)), fontsize=6.6, va="bottom",
             ha="left", color="#333333", linespacing=1.7)
    fig.savefig(OUT / "map3_estimation_samples.pdf", bbox_inches="tight")
    plt.close(fig)


def gate_point(sec, park, sid):
    """the entrance itself, from GATE_XY, reprojected to the map's CRS"""
    return gpd.GeoSeries([Point(*GATE_XY[sid])], crs=4326).to_crs(CRS).iloc[0]


if __name__ == "__main__":
    sec, dist, pk, parks = load()
    L = classify(sec, parks, pk[pk.geometry.area > 1e5])
    print({k: len(v) for k, v in sorted(L.items())})
    map1(sec, dist, pk, parks, L)
    map2(sec, dist, pk, parks, L)
    map3(sec, dist, pk, parks, L)
    print("written to", OUT)
