"""
04_checks.py -- everything that should be true of the pooled panels, tested and written to a log.

    python 04_checks.py            ->  logs/checks_report.txt

Sections:
  A  shape and keys          one row per unit-year, no duplicates, no missing keys, complete grid
  B  geography               unit counts match the boundary layers, cells nest inside sectors
  D2 product coverage        which years each product AND LAYER covers, and no year without a raw sensor
  C  coverage and areas      every unit has raster area, and the zonal areas reproduce the
                             boundary layer's own area to within 2%
  D  ranges                  each product and layer inside its own scale, shares in 0-1, DMSP\n                             satellites averaged 1 or 2 a year
  E  the sensor break        the two products should agree on the RANKING of units even where they
                             disagree on levels; a collapse in that correlation around 2012-2014 is
                             what a bad harmonisation looks like
  F  external sanity         Kigali is the brightest sector in every year, and the national total
                             rises over the period
"""
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

import ntl_helpers as H

OUT = []


def say(s=""):
    print(s)
    OUT.append(s)


def check(name, ok, detail=""):
    say(f"  [{'PASS' if ok else 'FAIL'}] {name}{('  ' + detail) if detail else ''}")
    return bool(ok)


def main():
    import geopandas as gpd
    fails = 0
    panels = {u: pd.read_stata(H.FINAL / f"Nightlights_pooled_{u}.dta") for u in H.UNITS}

    say("=" * 100)
    say("NIGHTTIME LIGHTS -- CHECKS")
    say("=" * 100)

    say("\nA. SHAPE AND KEYS")
    for unit, df in panels.items():
        idc = f"ntl_{unit}_id"
        years = sorted(df.ntl_year.unique())
        fails += not check(f"{unit}: no duplicate unit-year", not df.duplicated([idc, "ntl_year"]).any())
        fails += not check(f"{unit}: keys never missing", df[[idc, "ntl_year"]].notna().all().all())
        fails += not check(f"{unit}: complete grid",
                           len(df) == df[idc].nunique() * len(years),
                           f"{df[idc].nunique():,} units x {len(years)} years = {len(df):,} rows")
        say(f"         years {years[0]}-{years[-1]}")

    say("\nB. GEOGRAPHY")
    for unit, df in panels.items():
        path, idcol = H.UNITS[unit]
        g = gpd.read_file(path)
        idc = f"ntl_{unit}_id"
        fails += not check(f"{unit}: unit count matches the boundary layer",
                           df[idc].nunique() == len(g), f"{df[idc].nunique():,} vs {len(g):,}")
    cell = panels["cell"]
    sec = set(panels["sector"].ntl_sector_id.unique())
    fails += not check("cells nest inside the sectors", set(cell.ntl_sector_id.unique()) <= sec)

    # Names are not unique on their own: 379 distinct names across 416 sectors, four of them Remera.
    # They are unique once the district is added, which is the name-based key anyone merging on text
    # must use. Codes remain the safe key; this only guards the fallback.
    one = panels["sector"][panels["sector"].ntl_year == panels["sector"].ntl_year.min()]
    fails += not check("sector names alone do not identify a sector",
                       one.ntl_sector.nunique() < len(one),
                       f"{one.ntl_sector.nunique()} names for {len(one)} sectors")
    fails += not check("district + sector does identify a sector",
                       one.groupby(["ntl_district", "ntl_sector"]).ngroups == len(one))
    onec = cell[cell.ntl_year == cell.ntl_year.min()]
    fails += not check("district + sector + cell identifies a cell",
                       onec.groupby(["ntl_district", "ntl_sector", "ntl_cell"]).ngroups == len(onec),
                       f"{onec.ntl_cell.nunique():,} cell names for {len(onec):,} cells")

    say("\nC. COVERAGE AND AREAS")
    say("     The boundary layers cover land only, about 24,350 km2; Rwanda's 26,338 km2 includes"
        " its share of the lakes.")
    for unit, df in panels.items():
        path, _ = H.UNITS[unit]
        layer_km2 = float(gpd.read_file(path).to_crs(32736).area.sum() / 1e6)
        fails += not check(f"{unit}: every unit has raster area", (df.ntl_area_km2 > 0).all())
        one = df[df.ntl_year == df.ntl_year.min()]
        total = one.ntl_area_km2.sum()
        fails += not check(f"{unit}: zonal area within 2% of the boundary layer's own area",
                           abs(total / layer_km2 - 1) < 0.02,
                           f"{total:,.0f} vs {layer_km2:,.0f} km2")

    say("\nD. RANGES")
    for unit, df in panels.items():
        for p_, l_, lo, hi, why in [
                ("dmsp", "stable", 0, 63, "digital numbers"),
                ("dmsp", "avgvis", 0, 63, "digital numbers"),
                ("dmsp", "intercal", 0, 120, "intercalibration rescales above 63"),
                ("dmsp", "cfcvg", 0, 400, "cloud-free nights in a year"),
                ("viirs", "cfcvg", 0, 400, "cloud-free nights in a year"),
                ("viirs", "lit", 0, 1, "a mask"),
                ("li", "", 0, 63, "DMSP scale"),
                ("chen", "", 0, None, "radiance, non-negative")]:
            tag = f"ntl_{p_}" + (f"_{l_}" if l_ else "")
            col = f"{tag}_mean"
            if col not in df.columns or df[col].isna().all():
                continue
            v = df[col].dropna()
            ok = (v.min() >= lo) and (hi is None or df[f"{tag}_max"].dropna().max() <= hi)
            fails += not check(f"{unit}: {tag} within range ({why})", ok,
                               f"mean {v.min():.3g}-{v.max():.3g}, max {df[f'{tag}_max'].max():.3g}")
        # VIIRS mean and median radiance are background-subtracted and may legitimately go negative.
        for tag in ("ntl_viirs_avg", "ntl_viirs_med"):
            if f"{tag}_mean" in df.columns and df[f"{tag}_mean"].notna().any():
                say(f"         {unit}: {tag}_mean ranges "
                    f"{df[f'{tag}_mean'].min():.3g} to {df[f'{tag}_mean'].max():.3g}"
                    " (negative values are background subtraction, not an error)")
        shares = [c for c in df.columns if c.endswith("_lit_share") or c.endswith("_top")]
        ok = all((df[c].between(0, 1) | df[c].isna()).all() for c in shares)
        fails += not check(f"{unit}: every share and top-pixel ratio lies in 0-1", ok,
                           f"{len(shares)} columns")
        if "ntl_dmsp_n_sat" in df.columns:
            v = df.ntl_dmsp_n_sat.dropna()
            fails += not check(f"{unit}: DMSP satellites averaged per year is 1 or 2",
                               v.isin([1, 2]).all(), f"two-satellite unit-years: {int((v == 2).sum()):,}")

    say("\nD2. PRODUCT AND LAYER COVERAGE")
    df = panels["sector"]
    for p_ in H.PRODUCTS:
        for l_ in sorted(H.PRODUCTS[p_]["layers"]):
            tag = f"ntl_{p_}" + (f"_{l_}" if l_ != "main" else "")
            col = f"{tag}_mean"
            if col not in df.columns:
                say(f"     {tag}: NOT IN PANEL")
                continue
            yy = sorted(df.loc[df[col].notna(), "ntl_year"].unique())
            gaps = [y for y in range(min(yy), max(yy) + 1) if y not in yy] if yy else []
            say(f"     {tag}: {min(yy)}-{max(yy)}, {len(yy)} years" +
                (f", GAPS {gaps}" if gaps else ", no gaps"))
    raw = [c for c in ("ntl_dmsp_intercal_mean", "ntl_viirs_avg_mean") if c in df.columns]
    cov = df[raw].notna().any(axis=1).groupby(df.ntl_year).any()
    fails += not check("a RAW sensor covers every year from 1992 to 2025",
                       cov.loc[1992:2025].all(),
                       f"uncovered: {sorted(cov.index[~cov])}")

    say("\nE. AGREEMENT BETWEEN PRODUCTS")
    say("     Spearman correlation across sectors, raw against the harmonised product built on it.")
    for a, b, lab in [("ntl_dmsp_intercal_mean", "ntl_li_mean", "DMSP vs Li"),
                      ("ntl_viirs_avg_mean", "ntl_chen_mean", "VIIRS vs Chen"),
                      ("ntl_dmsp_intercal_mean", "ntl_viirs_avg_mean", "DMSP vs VIIRS (overlap)")]:
        if a not in df.columns or b not in df.columns:
            continue
        rows = []
        for y in sorted(df.ntl_year.unique()):
            d = df[df.ntl_year == y].dropna(subset=[a, b])
            if len(d) < 50 or d[a].nunique() < 5 or d[b].nunique() < 5:
                continue
            rows.append((y, spearmanr(d[a], d[b]).statistic))
        if not rows:
            continue
        lo_ = min(r for _, r in rows)
        say(f"     {lab}: {len(rows)} overlapping years, "
            f"{rows[0][0]}-{rows[-1][0]}, lowest {lo_:.3f}")
        fails += not check(f"{lab}: rankings agree in every overlapping year", lo_ > 0.5,
                           f"lowest {lo_:.3f} in {min(rows, key=lambda r: r[1])[0]}")

    say("\nF. DERIVED MEASURES")
    for unit, df in panels.items():
        for p_, l_ in H.HEADLINE:
            tag = f"ntl_{p_}" + (f"_{l_}" if l_ != "main" else "")
            if f"{tag}_asinh" not in df.columns:
                continue
            d = df.dropna(subset=[f"{tag}_asinh", f"{tag}_sum"])
            ok = np.allclose(d[f"{tag}_asinh"], np.arcsinh(d[f"{tag}_sum"].clip(lower=0)), atol=1e-8)
            fails += not check(f"{unit}: {tag}_asinh is asinh of the total", ok)
        pc = [c for c in df.columns if c.endswith("_pc")]
        if unit == "sector" and pc:
            pre = df[df.ntl_year < 2002][pc]
            fails += not check("sector: per-capita columns are missing before 2002",
                               pre.isna().all().all(),
                               "population is not extrapolated back through 1994")
        elif unit == "cell":
            fails += not check("cell: no per-capita columns", not pc,
                               "the census has no cell identifier")
        for p_, l_ in H.HEADLINE:
            tag = f"ntl_{p_}" + (f"_{l_}" if l_ != "main" else "")
            fc, ls = f"{tag}_first", f"{tag}_lit_share"
            if fc not in df.columns:
                continue
            d = df.dropna(subset=[fc])
            first_obs = d[d[ls].fillna(0) > 0].groupby(f"ntl_{unit}_id").ntl_year.min()
            claimed = d.groupby(f"ntl_{unit}_id")[fc].first()
            ok = claimed.reindex(first_obs.index).equals(first_obs.astype(claimed.dtype))
            fails += not check(f"{unit}: {tag}_first matches the first lit year", ok)

    say("\nG. THE CENSORING TEST")
    say("     stable_lights zeroes dim and ephemeral light by design; avg_vis does not. If the")
    say("     park-adjacent sectors read zero in stable_lights but not in avg_vis, the harmonised")
    say("     products built on stable_lights are discarding the signal we are looking for.")
    df = panels["sector"]
    d = df.dropna(subset=["ntl_dmsp_stable_mean", "ntl_dmsp_avgvis_mean"])
    try:
        import sys
        sys.path.insert(0, str(H.LOGS.parent.parent / "output/figures"))
        import bar_chart_housing as BCH
        _, T_, X_, never_ = BCH.geography()
        treated = T_["Bordering or Gates+"]
    except Exception as e:
        treated = set()
        say(f"     (treated split unavailable: {e})")
    say("     period      n      dark in stable   mean avg_vis where stable reads zero   ratio of means")
    for lo_, hi_ in [(1992, 2001), (2002, 2009), (2010, 2013)]:
        for lab, q in [("all", d[d.ntl_year.between(lo_, hi_)]),
                       ("treated", d[d.ntl_year.between(lo_, hi_) & d.ntl_sector_id.isin(treated)])]:
            if q.empty:
                continue
            dark = q.ntl_dmsp_stable_lit_share.fillna(0) == 0
            hidden = q.loc[dark, "ntl_dmsp_avgvis_mean"].mean() if dark.any() else float("nan")
            say(f"     {lo_}-{hi_} {lab:8s} {len(q):5,}   {100 * dark.mean():5.1f}%"
                f"          {hidden:6.3f} DN"
                f"                    {q.ntl_dmsp_avgvis_mean.mean() / max(q.ntl_dmsp_stable_mean.mean(), 1e-9):5.2f}x")
    say("     Read the middle column as the light stable_lights throws away: sector-years it calls")
    say("     completely dark still carry that much mean brightness in the uncensored composite.")

    say("\nH. EXTERNAL SANITY")
    df = panels["sector"]
    for col, lab in [("ntl_dmsp_intercal_mean", "DMSP"), ("ntl_viirs_avg_mean", "VIIRS")]:
        if col not in df.columns:
            continue
        d = df.dropna(subset=[col])
        top = d.loc[d.groupby("ntl_year")[col].idxmax(), ["ntl_year", "ntl_sector", "ntl_district"]]
        kig = top.ntl_district.str.contains("Nyarugenge|Gasabo|Kicukiro", case=False, na=False)
        fails += not check(f"the brightest sector is in Kigali in every year ({lab})", kig.all(),
                           f"{int(kig.sum())} of {len(top)} years")
    for col, lab in [("ntl_dmsp_intercal_sum", "DMSP 1992-2013"), ("ntl_viirs_avg_sum", "VIIRS 2012-2025")]:
        if col not in df.columns:
            continue
        tot = df.dropna(subset=[col]).groupby("ntl_year")[col].sum()
        fails += not check(f"the national total rises over the period ({lab})",
                           tot.iloc[-1] > tot.iloc[0],
                           f"{tot.iloc[0]:,.0f} in {tot.index[0]} to {tot.iloc[-1]:,.0f} in {tot.index[-1]}")

    say("\n" + "=" * 100)
    say(f"{'ALL CHECKS PASS' if fails == 0 else str(fails) + ' CHECK(S) FAILED'}")
    say("=" * 100)
    H.log("checks_report.txt", "\n".join(OUT) + "\n")
    return fails


if __name__ == "__main__":
    raise SystemExit(1 if main() else 0)
