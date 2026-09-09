"""
03_merge.py -- one pooled panel per unit, every product and layer side by side, as Stata files.

    python 03_merge.py

    3_Final/Nightlights_pooled_sector.dta   416 sectors x year
    3_Final/Nightlights_pooled_cell.dta     2,148 cells x year

The panel is built on the RAW sensor backbone (Matteo, 2026-09-08). DMSP-OLS v4 and VIIRS VNL v2 are
the measurements; Li and Chen ride alongside as a bridge across the 2012 sensor break. Products are
never averaged with each other -- they are on different scales and two of the four bridge halves are
model output -- so each keeps its own columns.

DMSP two-satellite years. Twelve years have two satellites flying. The series is the MEAN of the
satellites available that year (Matteo, 2026-09-08), which is defensible because the intercalibrated
layer is built precisely so that satellites are comparable; ntl_dmsp_n_sat records how many went in.

Columns are ntl_<product>_<layer>_<statistic> for the raw products and ntl_<product>_<statistic> for
the bridge products, which have one layer each. Four statistics come from 02_zonal.py -- mean, sum,
max and lit_share -- and four more are derived here for the headline series:

    asinh   inverse hyperbolic sine of the total. Behaves like a log where there is light and is
            defined at zero, which matters when most sector-years are dark.
    pc      total per 1,000 residents. SECTORS ONLY: the census has no cell identifier, and splitting
            a sector's population across its cells by area would invent the variation.
    first   first year the unit was lit, repeated down the panel.

Population is interpolated log-linearly between the 2002, 2012 and 2022 censuses and extrapolated
forward at the 2012-2022 rate. It is MISSING BEFORE 2002 and so, therefore, is every per-capita
column: interpolating a Rwandan sector's population back through 1994 is not defensible, and inventing
it would put a fabricated denominator under a real numerator. WorldPop is not used at any point --
it is itself modelled partly from nightlights, so a per-capita measure built on it would be circular.
"""
import numpy as np
import pandas as pd
import pyreadstat

import ntl_helpers as H

CENSUS = (H.DATA / "Publicly-Available-NISR/Census-PHC/3_Final/Census_pooled_person.dta")
CENSUS_YEARS = [2002, 2012, 2022]

KEYS = {
    "sector": [("unit_id", "ntl_sector_id", "Sector, NISR code 1101-5715"),
               ("sector", "ntl_sector", "Sector name"),
               ("district", "ntl_district", "District name"),
               ("province", "ntl_province", "Province name")],
    "cell": [("unit_id", "ntl_cell_id", "Cell identifier, nested in the sector code"),
             ("cell", "ntl_cell", "Cell name"),
             ("sector_id", "ntl_sector_id", "Sector, NISR code 1101-5715"),
             ("sector", "ntl_sector", "Sector name"),
             ("district", "ntl_district", "District name"),
             ("province", "ntl_province", "Province name")],
}
SHORT_LAYER = {"stable": "stable lights", "intercal": "intercalibrated", "avgvis": "uncensored",
               "cfcvg": "cloud-free nights", "avg": "mean radiance", "med": "median radiance",
               "lit": "lit mask", "main": ""}
SHORT_PROD = {"dmsp": "DMSP", "viirs": "VIIRS", "viirs_m": "VIIRS monthly",
              "li": "Li harmonised", "chen": "Chen VIIRS-like"}
STAT_DESC = {"mean": "area-weighted mean", "sum": "area-weighted total",
             "max": "brightest pixel", "lit_share": "lit share of area",
             "top": "share of total in brightest pixel"}
DERIV_DESC = {"asinh": "asinh of total", "pc": "total per 1,000 people",
              "first": "first year lit"}


def population():
    """weighted sector population at each census, log-linear in between, forward to 2026"""
    d, _ = pyreadstat.read_dta(CENSUS, usecols=["census_year", "census_sector", "census_weight"])
    p = (d.groupby(["census_year", "census_sector"]).census_weight.sum()
         .rename("pop").reset_index())
    p = p.pivot(index="census_sector", columns="census_year", values="pop")
    out = []
    for sid, r in p.iterrows():
        lg = {y: np.log(r[y]) for y in CENSUS_YEARS if y in r and r[y] > 0}
        if len(lg) < 2:
            continue
        for y in H.YEARS:
            if y < min(lg):
                continue                                    # never extrapolated backwards
            lo = max([c for c in lg if c <= y], default=None)
            hi = min([c for c in lg if c >= y], default=None)
            if lo is not None and hi is not None and lo != hi:
                v = lg[lo] + (lg[hi] - lg[lo]) * (y - lo) / (hi - lo)
            elif lo == hi:
                v = lg[y]
            else:                                           # past the last census: last decade's rate
                a, b = sorted(lg)[-2:]
                v = lg[b] + (lg[b] - lg[a]) / (b - a) * (y - b)
            out.append({"unit_id": int(sid), "period": y, "pop": float(np.exp(v))})
    return pd.DataFrame(out)


def collapse(df, product):
    """average over satellites within unit, layer and period; count how many there were"""
    stats = list(H.STATS)
    g = df.groupby(["unit_id", "layer", "period"], as_index=False)
    out = g[stats].mean()
    out["n_sat"] = g.size()["size"].values if product == "dmsp" else 1
    return out


def wide(df, product):
    """long in layer -> one column per layer and statistic"""
    frames = []
    for layer, sub in df.groupby("layer"):
        tag = f"ntl_{product}" if layer == "main" else f"ntl_{product}_{layer}"
        r = sub.set_index(["unit_id", "period"])[list(H.STATS)]
        r.columns = [f"{tag}_{s}" for s in r.columns]
        frames.append(r)
    w = pd.concat(frames, axis=1).reset_index()
    if product == "dmsp":
        w = w.merge(df.groupby(["unit_id", "period"], as_index=False).n_sat.max()
                    .rename(columns={"n_sat": "ntl_dmsp_n_sat"}), on=["unit_id", "period"])
    return w


def derive(w, product, layer, pop, labels):
    """asinh, top-pixel share, per capita and first year lit, for one headline series"""
    tag = f"ntl_{product}" if layer == "main" else f"ntl_{product}_{layer}"
    s, ls = f"{tag}_sum", f"{tag}_lit_share"
    if s not in w.columns:
        return w
    w[f"{tag}_asinh"] = np.arcsinh(w[s].clip(lower=0))
    if pop is not None:
        w = w.merge(pop, on=["unit_id", "period"], how="left")
        w[f"{tag}_pc"] = np.where(w["pop"].notna() & (w["pop"] > 0),
                                  w[s] / w["pop"] * 1000.0, np.nan)
        w = w.drop(columns="pop")
    lit = w[w[ls].fillna(0) > 0].groupby("unit_id").period.min()
    w[f"{tag}_first"] = w.unit_id.map(lit)
    for k, desc in DERIV_DESC.items():
        col = f"{tag}_{k}"
        if col in w.columns:
            labels[col] = f"NIGHTLIGHTS: {SHORT_PROD[product]}"
            if SHORT_LAYER.get(layer):
                labels[col] += f" {SHORT_LAYER[layer]}"
            labels[col] += f", {desc}"
    return w


def build(unit, cadence="annual"):
    """cadence "annual" builds the year panel; "monthly" builds the VIIRS monthly panel.

    They cannot share a frame: the monthly period is a year-month like 201408, so putting it in the
    same column as a year would silently corrupt the grid."""
    pop = population() if (unit == "sector" and cadence == "annual") else None
    frames, labels = {}, {}
    for product in [p for p in H.PRODUCTS if H.PRODUCTS[p]["cadence"] == cadence]:
        f = H.INTERMEDIATE / f"ntl_{product}_{unit}_long.csv"
        if not f.exists():
            print(f"  {product}: no {f.name}, skipped")
            continue
        d = pd.read_csv(f)
        w = wide(collapse(d, product), product)
        for layer in sorted(d.layer.unique()):
            if (product, layer) in H.HEADLINE:
                w = derive(w, product, layer, pop, labels)
            tag = f"ntl_{product}" if layer == "main" else f"ntl_{product}_{layer}"
            for s, desc in STAT_DESC.items():
                col = f"{tag}_{s}"
                if col in w.columns:
                    lab = f"NIGHTLIGHTS: {SHORT_PROD[product]}"
                    if SHORT_LAYER.get(layer):
                        lab += f" {SHORT_LAYER[layer]}"
                    labels[col] = f"{lab}, {desc}"
        frames[product] = w

    if not frames:
        raise SystemExit("nothing in 2_Intermediate; run 02_zonal.py first")
    geo_src = pd.read_csv(H.INTERMEDIATE / f"ntl_{list(frames)[-1]}_{unit}_long.csv")
    geo_cols = [c for c, _, _ in KEYS[unit] if c != "unit_id"]
    geo = (geo_src.sort_values("period").groupby("unit_id", as_index=False).first()
           [["unit_id"] + [c for c in geo_cols if c in geo_src.columns] + ["area_km2"]])
    years = sorted({y for f in frames.values() for y in f.period.unique()})
    out = (pd.MultiIndex.from_product([sorted(geo.unit_id), years], names=["unit_id", "period"])
           .to_frame(index=False).merge(geo, on="unit_id", how="left"))
    for f in frames.values():
        out = out.merge(f, on=["unit_id", "period"], how="left")
    if pop is not None:
        out = out.merge(pop, on=["unit_id", "period"], how="left").rename(columns={"pop": "ntl_pop"})
        labels["ntl_pop"] = "NIGHTLIGHTS: Population, interpolated between censuses"

    order = []
    for old, new, lab in KEYS[unit]:
        if old in out.columns:
            out = out.rename(columns={old: new}); labels[new] = f"NIGHTLIGHTS: {lab}"
            order.append(new)
    out = out.rename(columns={"period": "ntl_year", "area_km2": "ntl_area_km2"})
    labels["ntl_year"] = ("NIGHTLIGHTS: Calendar year of the annual composite" if cadence == "annual"
                          else "NIGHTLIGHTS: Year and month of the composite, YYYYMM")
    labels["ntl_area_km2"] = "NIGHTLIGHTS: Area of the unit on the finest raster grid, square km"
    order += ["ntl_year", "ntl_area_km2"] + (["ntl_pop"] if pop is not None else [])
    order += [c for c in out.columns if c.startswith("ntl_") and c not in order]
    out = out[order].sort_values([order[0], "ntl_year"]).reset_index(drop=True)

    bad = {k: len(v) for k, v in labels.items() if len(v) > 80}
    if bad:
        raise SystemExit(f"labels over Stata's 80 characters: {bad}")
    bad = [c for c in out.columns if len(c) > 32]
    if bad:
        raise SystemExit(f"names over Stata's 32 characters: {bad}")
    for c in out.columns:
        if out[c].dtype == object:
            out[c] = out[c].fillna("").astype(str)
    return out, {k: v for k, v in labels.items() if k in out.columns}


if __name__ == "__main__":
    H.FINAL.mkdir(parents=True, exist_ok=True)
    for cadence in ("annual", "monthly"):
        for unit in H.UNITS:
            try:
                df, labels = build(unit, cadence)
            except SystemExit as e:
                print(f"{cadence} {unit}: {e}")
                continue
            name = "pooled" if cadence == "annual" else "monthly"
            out = H.FINAL / f"Nightlights_{name}_{unit}.dta"
            df.to_stata(out, write_index=False, variable_labels=labels, version=118)
            df.to_csv(out.with_suffix(".csv"), index=False)
            idc = [c for c in df.columns if c.endswith("_id")][0]
            print(f"{cadence} {unit}: {df.shape[0]:,} rows x {df.shape[1]} cols, "
                  f"{df[idc].nunique():,} units x {df.ntl_year.nunique()} periods -> {out.name}")
