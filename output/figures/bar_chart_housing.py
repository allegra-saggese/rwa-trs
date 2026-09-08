"""
bar_chart_housing.py -- descriptive difference-in-differences on housing, census 2002 / 2012 / 2022.

    python bar_chart_housing.py

Builds the sector-by-wave panel, writes it to the Dropbox Analysis folder, and draws the bar chart.

    Analysis/census_sector_housing_panel.csv   sector x wave, every indicator
    output/figures/bar_chart_housing.pdf       the five components and the index, three treatments

The panel holds every indicator that was ever built; COMPONENTS picks the five the figures use.

Design (Matteo, 2026-09-07)
  Outcomes   five binary housing indicators at household level, plus an index. See COMPONENTS for
             what is in and what was dropped and why. The index is the average of the component
             shares, standardised on the 2002 CONTROL mean and standard deviation.
  Unit       weighted household means per sector and wave, so the sector is the observation.
  Treatment  Bordering (42 sectors), Gates (4), Gates+ (25).
  Control    one fixed pool for all three treatments (Matteo, 2026-09-07): every sector that is neither
             bordering a park nor in Gates+ (their union is 50 sectors), minus the City of Kigali and the
             four largest towns of 2002, leaving 322. The Gishwati-Mukura sectors stay in the pool.
             This is the strongest of the twelve control definitions the two maps allow; the others give
             the same sign and significance with effects 11-22% smaller. See
             Analysis/spec_curve_control_restrictions.csv.
  Display    change since 2002, at 2012 and at 2022, for treated and control, with bootstrapped
             intervals on the bars and on the difference in differences.

The 2022 census has no activity-status question, so employment is not an outcome here; housing is the
only economic block measured identically in all three waves. Code lists differ by wave and the
crosswalk below is the mapping; see the value labels in Census_pooled_household.dta.
"""
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyreadstat

DB = Path("/Users/matteo/Library/CloudStorage/Dropbox/1-Ongoing Projects/Rwanda - TRS")
NISR = DB / "data/Publicly-Available-NISR"
GEO = DB / "data/geo-data"
ANALYSIS = NISR / "Analysis"
FIG = DB / "output/figures"
RNG = np.random.default_rng(20260907)
B = 2000                                        # bootstrap replications

# ---------------------------------------------------------------- housing crosswalk
# codes counted as "yes" in each wave; everything else is no, missing stays missing
# Electric lighting is deliberately NOT included (Matteo, 2026-09-07): connection to the grid is a
# national infrastructure decision, not something a household can act on, so it measures where the
# rollout went rather than how a community fared. Its crosswalk is kept here for reference only.
UNUSED = {"electricity": {"var": "lighting_source", 2002: [1, 2], 2012: [1, 2], 2022: [1, 2, 4],
                          "na": {2002: [9]}}}    # 2022 code 4 is a private solar mini grid
CROSSWALK = {
    "durable_roof": {"var": "roof_material", 2002: [1, 2, 3, 4], 2012: [1, 2, 3, 4, 5], 2022: [1, 2, 3, 4, 5],
                     "na": {2002: [9], 2022: [9]}},
    "modern_roof": {"var": "roof_material", 2002: [1, 3, 4], 2012: [1, 3, 5], 2022: [1, 3, 5],
                    "na": {2002: [9], 2022: [9]}},
    "wall_nonmud": {"var": "wall_material", 2002: [3, 4, 5, 6, 7], 2012: [3, 5, 6, 7, 8],
                    2022: [3, 4, 6, 7, 8, 9, 10, 11, 12], "na": {2002: [99], 2012: [0], 2022: [99]}},
    "improved_floor": {"var": "floor_material", 2002: [2, 3, 4, 5], 2012: [2, 3, 4, 5], 2022: [3, 4, 5, 6, 7, 8],
                       "na": {2002: [9], 2022: [10]}},
    "improved_water": {"var": "water_source", 2002: [1, 2, 3, 4], 2012: [1, 2, 3, 4], 2022: [1, 2, 3, 4, 5, 6],
                       "na": {2002: [99]}},
    "water_piped": {"var": "water_source", 2002: [1, 2, 3], 2012: [1, 2, 3], 2022: [1, 2, 3, 4],
                    "na": {2002: [99]}},
    "improved_toilet": {"var": "toilet_facility", 2002: [1, 2], 2012: [1, 2], 2022: [1, 3, 5],
                        "na": {2002: [9]}},
}

# "Any durable": owns at least one of these, in every wave. Counts in 2002 and 2012, yes-no in 2022.
# Radio and television are deliberately excluded (Matteo, 2026-09-07). Ownership of a radio or a
# television goes 43% - 65% - 43%: between 2012 and 2022 phones displaced radios and the 2022 item
# added the word "functional". That break is correlated with electrification, which we already know
# runs against the treated sectors, so including it would import the electricity gap into the outcome.
DURABLE_ITEMS = {
    "computer": ("computer_internet_2002", "computers_2012", "asset_computer_2022"),
    "bicycle": ("bicycles_2002", "bicycles_2012", "asset_bicycle_2022"),
    "vehicle": ("vehicles_2002", "vehicles_2012", "asset_vehicle_2022"),
    "motorcycle": ("motorcycles_2002", "motorcycles_2012", "asset_motorcycle_2022"),
}
INDICATORS = list(CROSSWALK) + ["any_durable"]

# The settled component set (Matteo, 2026-09-07). The panel carries every indicator above so the
# alternatives stay one edit away, but the figures use these five and only these five.
#   durable roof   out: 83.5% to 99.9%, both groups close 99% of their headroom, so a difference in
#                  differences on it is mechanical.
#   piped water    out: null everywhere and it only diluted the index.
#   any durable    out: radio and television ownership falls 65% to 43% between 2012 and 2022 as
#                  phones displace radios, a measurement break correlated with electrification.
COMPONENTS = ["modern_roof", "wall_nonmud", "improved_floor", "improved_water", "improved_toilet"]
NICE = {"durable_roof": "Durable roof", "modern_roof": "Modern roof", "wall_nonmud": "Non-mud wall",
        "improved_floor": "Improved floor", "improved_water": "Improved water",
        "water_piped": "Piped water", "improved_toilet": "Private toilet",
        "any_durable": "Any durable good", "index": "Housing index"}

GATES = [4307, 3701, 2509, 5407]
KIG_OUTER = ["Gikomero", "Rutunga", "Rusororo", "Masaka", "Mageregere", "Nduba", "Jali",
             "Kanyinya", "Bumbogo", "Ndera", "Jabana"]          # >= 10 km from the Convention Centre
CITY9 = [2708, 2712, 2409, 2414, 4308, 4302, 3304, 3311, 3312]  # the four largest towns of 2002


def geography():
    """treated sets and the four exclusion sets, re-derived from the geometry"""
    g = gpd.read_file(GEO / "protected-areas/sectors_park_exposure_wdpa.gpkg").to_crs(32736)
    g["sid"] = g.sector_id.astype(int)
    pk = gpd.read_file(GEO / "protected-areas/rwanda_protected_areas_geodata_rw.gpkg")
    pk = pk[pk.designate.astype(str).str.contains("National Park", case=False, na=False)].to_crs(32736)
    def block(pat):
        return pk[pk.areaname.astype(str).str.contains(pat, case=False, na=False)].union_all()
    long_standing = block("Volcanoes").union(block("Nyungwe")).union(block("Akagera"))
    bordering = set(g.sid[g.geometry.distance(long_standing) == 0])
    buf = g.geometry.buffer(10)
    gates_plus = set()
    for sid in GATES:
        gates_plus |= set(g.sid[buf.intersects(buf[g.sid == sid].iloc[0])])
    kig = g[g.province.str.contains("Kigali", na=False)]
    kig_all, kig_inner = set(kig.sid), set(kig.sid[~kig.sector.isin(KIG_OUTER)])
    T = {"Bordering": bordering, "Gates": set(GATES), "Gates+": gates_plus}
    X = {"Inner Kigali": kig_inner, "Kigali all": kig_all,
         "Inner Kigali + cities": kig_inner | set(CITY9), "Kigali all + cities": kig_all | set(CITY9)}
    never = bordering | gates_plus                    # never in the control pool, whatever the treatment
    return g, T, X, never


def any_durable(df):
    """1 if the household owns a computer, a bicycle, a vehicle or a motorcycle; see DURABLE_ITEMS"""
    w = df.wave
    cols = []
    for name, (c02, c12, c22) in DURABLE_ITEMS.items():
        o = pd.Series(np.nan, index=df.index)
        v = pd.to_numeric(df[f"census_{c02}"], errors="coerce")
        if name == "computer":                              # 1 computer, 2 computer and internet, 9 not stated
            o[w == 2002] = v[w == 2002].isin([1, 2]).astype(float)
            o[(w == 2002) & v.eq(9)] = np.nan
        else:                                               # a count of the item
            o[w == 2002] = (v[w == 2002] > 0).astype(float)
        v12 = pd.to_numeric(df[f"census_{c12}"], errors="coerce")
        o[w == 2012] = (v12[w == 2012] > 0).astype(float)
        v22 = pd.to_numeric(df[f"census_{c22}"], errors="coerce")
        o[w == 2022] = (v22[w == 2022] == 1).astype(float)   # 1 yes, 2 no
        cols.append(o)
    y = pd.concat(cols, axis=1)
    out = (y.fillna(0).sum(axis=1) > 0).astype(float)
    out[y.isna().all(axis=1)] = np.nan                      # no item answered: the household is missing
    return out


def panel():
    """household file -> sector x wave means of every indicator, whatever spec is drawn later"""
    need = ["census_wave", "census_sector", "census_household_weight"]
    need += [f"census_{c['var']}_{y}" for c in CROSSWALK.values() for y in (2002, 2012, 2022)]
    need += [f"census_{c}" for t in DURABLE_ITEMS.values() for c in t]
    df, _ = pyreadstat.read_dta(NISR / "Census-PHC/3_Final/Census_pooled_household.dta",
                                usecols=sorted(set(need)))
    df["wave"] = df.census_wave.astype(str).astype(int)
    for name, spec in CROSSWALK.items():
        out = pd.Series(np.nan, index=df.index)
        for y in (2002, 2012, 2022):
            col = f"census_{spec['var']}_{y}"
            v = pd.to_numeric(df[col], errors="coerce")
            m = (df.wave == y) & v.notna() & ~v.isin(spec.get("na", {}).get(y, []))
            out.loc[m] = v[m].isin(spec[y]).astype(float)   # "not stated" stays missing, never a no
        df[name] = out
    df["any_durable"] = any_durable(df)
    w = df.census_household_weight.fillna(1.0)
    rows = []
    for (sid, y), gr in df.groupby(["census_sector", "wave"]):
        r = {"sid": int(sid), "wave": int(y), "households": len(gr), "weight": w[gr.index].sum()}
        for c in INDICATORS:
            v, ww = gr[c], w[gr.index]
            ok = v.notna()
            r[c] = float((v[ok] * ww[ok]).sum() / ww[ok].sum()) if ok.any() and ww[ok].sum() > 0 else np.nan
        rows.append(r)
    return pd.DataFrame(rows)


def standardise(p, control_sids, comps=None):
    """The index is the average of the component shares, standardised on the 2002 control mean and sd.

    Averaging the shares first, rather than standardising each component and averaging the z-scores,
    keeps one component from dominating: a component with a near-zero baseline standard deviation would
    otherwise swamp the rest. The index is an amenity score between 0 and 1, standardised once."""
    comps = comps or COMPONENTS
    p["amenities"] = p[comps].mean(axis=1)
    base = p[(p.wave == 2002) & p.sid.isin(control_sids)]
    mu, sd = base["amenities"].mean(), base["amenities"].std(ddof=1)
    p["index"] = (p["amenities"] - mu) / sd
    for c in comps:
        p[c + "_pp"] = p[c] * 100                      # components stay in percentage points
    return p


def changes(p, sids, outcome):
    """per sector, the change since 2002 at 2012, at 2022, and the two pooled.

    Pooled is the sector's average of its two post-period changes, so every sector still contributes
    one observation and the bootstrap over sectors needs no correction for the two years being the
    same place twice."""
    w = p[p.sid.isin(sids)].pivot(index="sid", columns="wave", values=outcome).dropna()
    d12, d22 = (w[2012] - w[2002]).values, (w[2022] - w[2002]).values
    return d12, d22, (d12 + d22) / 2


def boot(t, c):
    """mean change for treated and control with 90% intervals, and the difference with its p-value"""
    out = {}
    for lab, x in (("T", t), ("C", c)):
        d = RNG.choice(x, size=(B, len(x)), replace=True).mean(axis=1)
        out[lab] = (x.mean(), np.percentile(d, 5), np.percentile(d, 95))
    dt = RNG.choice(t, size=(B, len(t)), replace=True).mean(axis=1)
    dc = RNG.choice(c, size=(B, len(c)), replace=True).mean(axis=1)
    d = dt - dc
    pv = 2 * min((d <= 0).mean(), (d >= 0).mean())            # two-sided bootstrap p
    out["D"] = (t.mean() - c.mean(), np.percentile(d, 5), np.percentile(d, 95), max(pv, 1 / B))
    return out


def draw_all(p, T, X, never, path, comps=None):
    """one figure: the fixed control group, three treatments, the five components and the index"""
    comps = comps or COMPONENTS
    xset = X["Kigali all + cities"]                      # the working specification (Matteo, 2026-09-07)
    ctrl = set(p.sid.unique()) - never - xset
    ps = standardise(p.copy(), ctrl, comps)
    outs = comps + ["index"]
    fig, axes = plt.subplots(len(T), len(outs), figsize=(3.6 * len(outs), 9.5), sharey="col")
    for i, (tn, tset) in enumerate(T.items()):
        for j, o in enumerate(outs):
            ax = axes[i, j]
            col = o if o == "index" else o + "_pp"
            T3 = changes(ps, tset, col)
            C3 = changes(ps, ctrl, col)
            R = [boot(a, b) for a, b in zip(T3, C3)]
            xs = np.array([0, 1, 2])
            for k, (lab, cc, key) in enumerate([("Treated", "#E0A33E", "T"), ("Control", "#8C8C8C", "C")]):
                r = [x[key] for x in R]
                m = [v[0] for v in r]
                lo = [v[0] - v[1] for v in r]
                hi = [v[2] - v[0] for v in r]
                ax.bar(xs + (k - 0.5) * 0.36, m, 0.34, color=cc, yerr=[lo, hi], capsize=2,
                       label=lab if (i == 0 and j == 0) else None, error_kw=dict(lw=0.7, ecolor="#333333"))
            for xx, r in zip(xs, R):
                ax.annotate(f"{r['D'][0]:+.2f}", (xx, 0.012), xycoords=ax.get_xaxis_transform(),
                            ha="center", va="bottom", fontsize=6.8, color="#555555")
            ax.set_xticks(xs); ax.set_xticklabels(["2012", "2022", "pooled"], fontsize=7)
            ax.axhline(0, color="#555555", lw=0.6); ax.tick_params(labelsize=7)
            if i == 0: ax.set_title(NICE[o] + ("  (SD)" if o == "index" else "  (pp)"), fontsize=9)
            if j == 0: ax.set_ylabel(f"{tn} ({len(tset)})\nchange since 2002", fontsize=8)
    for j in range(len(outs)):                       # one scale per variable, headroom for the labels
        lo_, hi_ = axes[0, j].get_ylim()
        axes[0, j].set_ylim(min(lo_, 0) - 0.22 * (hi_ - lo_), hi_)
    fig.legend(loc="upper right", fontsize=9, frameon=False, ncol=2, bbox_to_anchor=(0.99, 0.985))
    fig.suptitle("Housing: each component and the index, control excludes Kigali and the four largest towns of 2002",
                 fontsize=13, fontweight="bold", x=0.008, ha="left", y=0.995)
    fig.text(0.008, 0.012, note(comps), fontsize=6.6, va="bottom", ha="left", color="#333333",
             linespacing=1.6)
    fig.tight_layout(rect=[0, 0.075, 1, 0.965])
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


import textwrap
def note(comps):
    names = ", ".join(NICE[c].lower() for c in comps)
    return textwrap.fill(
    "Bars show the change since 2002 for the treated sectors and for the control sectors, at 2012, at 2022, and the two pooled "
    f"(each sector's average of its two changes). Each of the {len(comps)} components ({names}) is a share of households shown in "
    "percentage points; the index averages those shares and is standardised on the 2002 control mean and standard deviation. "
    "The unit is the sector: household values are averaged within sector and wave using "
    "census household weights, so each sector counts once. Intervals are 90% percentile bootstrap over sectors, 2,000 replications, "
    "drawn separately for treated and control. The grey number under each pair is the difference in differences. Controls are the 322 sectors that neither border a park nor sit next to a "
    "park entrance, less the City of Kigali and the four largest towns of 2002; the Gishwati-Mukura sectors stay in. "
    "Source: Rwanda Population and Housing Census 2002, 2012 and 2022, 10% public-use samples.", width=352)


if __name__ == "__main__":
    ANALYSIS.mkdir(exist_ok=True); FIG.mkdir(parents=True, exist_ok=True)
    g, T, X, never = geography()
    print({k: len(v) for k, v in T.items()}, "| never in control:", len(never))
    p = panel()
    p = p.merge(g[["sid", "sector", "district", "province"]], on="sid", how="left")
    p.to_csv(ANALYSIS / "census_sector_housing_panel.csv", index=False)
    print("panel:", p.shape, "->", ANALYSIS / "census_sector_housing_panel.csv")
    out = FIG / "bar_chart_housing.pdf"
    draw_all(p, T, X, never, out)
    print("written:", out)
