"""
census_urban_maps.py -- where Rwanda's urban residents live: the share of each sector's residents in
urban areas, from the Population and Housing Census.

    python results-scripts/census_urban_maps.py

Writes, to Dropbox output/maps/ (one figure per file, vector PDF, no title inside the figure):
    census_urban_share_2012.pdf          share of residents in urban areas, 2012 (NISR's two-way urban flag)
    census_urban_share_2022.pdf          the same, 2022
    census_area_urban_share_2012.pdf     2012, four area types, one map each: urban,
    census_area_semi_urban_share_2012.pdf    semi-urban,
    census_area_peri_urban_share_2012.pdf    peri-urban,
    census_area_rural_share_2012.pdf         rural
    census_urban_maps_captions.tex       a LaTeX figure environment for each map: title, notes, source

HOW NISR CLASSIFIES AREAS. The classification is made for each village (umudugudu): a village is urban
when it has a substantial built-up area and major infrastructure (schools, electricity and water, a
market, banks or other financial institutions) -- 2012 Census atlas. Every household takes its village's
type. Villages are not released, so the maps show, for each of the 416 sectors, the weighted share of
residents living in each type of area. The two-way flag (census_urban) counts urban + semi-urban as urban
and peri-urban + rural as rural; it reproduces NISR's published urban shares (16.5% in 2012). Only 2012
ships the four types (census_area_residence_2012). 2002 is left out: its urban areas were 15 delineated
towns that took in a large amount of rural land, so its flag is not comparable.

Same classes on every map, so the maps can be compared: 0, 0-10, 10-25, 25-50, 50-75, 75-100 percent.
Parks, lakes and sector edges are drawn as in results-scripts/STEG/steg_ec_maps.py.
"""
import sys
from pathlib import Path

import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd
import pyreadstat
from shapely.geometry import box
from shapely.validation import make_valid

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "results-scripts" / "STEG"))
import paths as P  # noqa: E402
import steg_ec_maps as M  # noqa: E402  (map conventions: boundaries, parks, lakes, colours)

CENSUS = P.NISR / "Census-PHC" / "3_Final" / "Census_pooled_person.dta"
CUTS = [10, 25, 50, 75]                              # percent; 0 is its own class
CLASSES = [("0%", "#ffffff"), ("0–10%", "#fee6ce"), ("10–25%", "#fdc086"), ("25–50%", "#fd8d3c"),
           ("50–75%", "#d94801"), ("75–100%", "#7f2704")]
AREA_TYPES = {1: ("urban", "Urban"), 4: ("semi_urban", "Semi-urban"), 3: ("peri_urban", "Peri-urban"),
              2: ("rural", "Rural")}               # census_area_residence_2012 codes
SOURCE = ("\\textit{Source:} National Institute of Statistics of Rwanda, Population and Housing Census, "
          "public-use samples; sector boundaries from NISR (2022).")


def shares() -> pd.DataFrame:
    """Weighted share of residents by area type, per sector and wave (percent)."""
    cols = ["census_year", "census_sector", "census_weight", "census_urban", "census_area_residence_2012"]
    parts = []
    for chunk, _ in pyreadstat.read_file_in_chunks(pyreadstat.read_dta, str(CENSUS), chunksize=500_000,
                                                   usecols=cols):
        parts.append(chunk[chunk.census_year.isin([2012, 2022])])
    d = pd.concat(parts, ignore_index=True)
    d["sid"] = d.census_sector.astype(int)
    out = []
    for y, g in d.groupby("census_year"):
        tot = g.groupby("sid").census_weight.sum()
        r = pd.DataFrame({"urban": g[g.census_urban == 1].groupby("sid").census_weight.sum()
                          .reindex(tot.index, fill_value=0) / tot * 100})
        if y == 2012:
            for code, (key, _) in AREA_TYPES.items():
                r[f"area_{key}"] = (g[g.census_area_residence_2012 == code].groupby("sid").census_weight.sum()
                                    .reindex(tot.index, fill_value=0) / tot * 100)
        r["year"] = int(y)
        national = (g.census_weight * (g.census_urban == 1)).sum() / g.census_weight.sum() * 100
        print(f"{int(y)}: national urban share {national:.1f}% ({len(r)} sectors)")
        out.append(r.reset_index())
    return pd.concat(out, ignore_index=True)


def classes(v: np.ndarray) -> np.ndarray:
    """Class index: 0 for exactly 0%, then 0-10, 10-25, 25-50, 50-75, 75-100 (a value on a cut goes below)."""
    return np.where(v <= 0, 0, 1 + np.searchsorted(CUTS, v, side="left"))


def draw(s: gpd.GeoDataFrame, pk, lk, col: str, legend_title: str, out: Path) -> list[int]:
    k = classes(s[col].to_numpy())
    n = [int((k == i).sum()) for i in range(len(CLASSES))]
    fig, ax = plt.subplots(figsize=(7.5, 7))
    s.plot(ax=ax, color=[CLASSES[i][1] for i in k], edgecolor=M.EDGE, linewidth=.25, zorder=1)
    pk.plot(ax=ax, facecolor=M.PARK, edgecolor="white", hatch="////", linewidth=0, zorder=2)
    lk.plot(ax=ax, facecolor=M.WATER, edgecolor=M.WATER_EDGE, linewidth=.3, zorder=3)
    handles = [Patch(facecolor=c, edgecolor=M.EDGE, label=f"{name}  ({n[i]} sector{'' if n[i] == 1 else 's'})")
               for i, (name, c) in list(enumerate(CLASSES))[::-1]]
    handles += [Patch(facecolor=M.PARK, edgecolor="white", hatch="////", label="National park"),
                Patch(facecolor=M.WATER, edgecolor=M.WATER_EDGE, label="Lake")]
    ax.legend(handles=handles, title=legend_title, loc="center left", bbox_to_anchor=(1.0, .3),
              frameon=False, fontsize=8.5, title_fontsize=9, alignment="left")
    ax.set_axis_off()
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"written {out}  sectors per class {dict(zip([c[0] for c in CLASSES], n))}")
    return n


def caption(label: str, title: str, notes: str, file: str) -> str:
    return "\n".join([
        "\\begin{figure}[htbp]", "\\centering",
        f"\\caption{{{title}}}", f"\\label{{fig:{label}}}",
        f"\\includegraphics[width=\\textwidth]{{{file}}}",
        "\\begin{minipage}{\\textwidth}\\footnotesize",
        f"\\textit{{Notes:}} {notes} {SOURCE}",
        "\\end{minipage}", "\\end{figure}", ""])


def main():
    sh = shares()
    s = gpd.read_file(M.SECTORS)
    s["geometry"] = s.geometry.apply(make_valid)
    s["sid"] = s.sector_id.astype(int)
    s = s.to_crs(M.CRS)
    pk = gpd.read_file(M.PARKS)
    pk = pk[pk.designate.astype(str).str.contains("National Park", case=False, na=False)].to_crs(M.CRS)
    lk = gpd.clip(gpd.read_file(M.LAKES).to_crs(M.CRS), box(*s.total_bounds))
    matplotlib.rcParams["hatch.linewidth"] = .6
    P.MAPS.mkdir(parents=True, exist_ok=True)

    common = ("Each sector is shaded by the weighted share of its residents who live in villages NISR "
              "classifies as {kind}. NISR classifies each village (umudugudu), not each sector: a village is "
              "urban when it has a substantial built-up area and major infrastructure (schools, electricity "
              "and water, a market, financial institutions). The number of sectors in each class is in the "
              "legend; 416 sectors.")
    tex = []
    for y in (2012, 2022):
        m = s.merge(sh[sh.year == y], on="sid", how="left")
        assert m.urban.notna().all(), f"{y}: sectors without Census residents"
        f = f"census_urban_share_{y}.pdf"
        draw(m, pk, lk, "urban", f"Share of residents in urban areas, {y}", P.MAPS / f)
        kind = "urban" + (" (NISR's urban and semi-urban areas)" if y == 2012 else "")
        tex.append(caption(f"urban_share_{y}", f"Share of Residents Living in Urban Areas, by Sector, {y}",
                           common.format(kind=kind), f))
    m = s.merge(sh[sh.year == 2012], on="sid", how="left")
    for code, (key, name) in AREA_TYPES.items():
        f = f"census_area_{key}_share_2012.pdf"
        draw(m, pk, lk, f"area_{key}", f"Share of residents in {name.lower()} areas, 2012", P.MAPS / f)
        tex.append(caption(f"area_{key}_2012", f"Share of Residents Living in {name} Areas, by Sector, 2012",
                           common.format(kind=name.lower()) + " The four area types (urban, semi-urban, "
                           "peri-urban, rural) are released for 2012 only and add to 100 percent in each sector.",
                           f))
    (P.MAPS / "census_urban_maps_captions.tex").write_text("\n".join(tex))
    print(f"written {P.MAPS / 'census_urban_maps_captions.tex'}")


if __name__ == "__main__":
    main()
