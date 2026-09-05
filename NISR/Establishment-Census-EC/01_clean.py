"""
01_clean.py -- EC: 1_Raw/<year>/EC_<year>.(sav|dta) -> 2_Intermediate/EC_<year>_establishment_clean.dta

Per census: lower-case names, build the harmonised key block (survey year wave prov dist
sector urban estid wt), attach NISR's current province/district/sector names as value
labels, keep every other variable under its own name, destring, downcast, back-check, write.
Unit = establishment. See DECISIONS.md.
"""
import difflib, sys
import numpy as np, pandas as pd
from ec_helpers import (paths, db_root, get_logger, Checks, read_any, write_dta, lower_names, destring, downcast, save_json, LOGS)

log = get_logger("01_clean"); P = paths()
YEARS = [int(a) for a in sys.argv[1:]] or [2011, 2014, 2017, 2020, 2023]
FILES = {2011: "EC_2011.sav", 2014: "EC_2014.sav", 2017: "EC_2017.sav", 2020: "EC_2020.dta", 2023: "EC_2023.dta"}
PUBLISHED = {2011: 123_526, 2014: 154_236, 2017: 190_288, 2020: 232_283}   # establishments, NISR EC reports (2014 = weighted total)
KEY_ORDER = ["survey", "year", "wave", "prov", "dist", "sector", "urban", "estid", "wt"]
KEY_LABELS = {"survey": "Source survey", "year": "Census year", "wave": "Wave (census year)", "prov": "Province (1-5, NISR codes)",
              "dist": "District (11-57, NISR codes)", "sector": "Sector (1101-5715, NISR codes; 2011 and 2014 only)",
              "urban": "Area of residence (1 urban, 2 rural)", "estid": "Establishment id (NISR key where shipped, else year*1e6 + row number)",
              "wt": "Weight (1 for full enumerations; NISR final sampling weight in 2014)",
              "cell_seq_2011": "2011 cell sequence within sector (ID4, as shipped)", "village_seq_2011": "2011 village sequence within cell (ID5, as shipped)"}
URBAN_LABELS = {1: "Urban", 2: "Rural"}

geo = db_root() / "geodata-nisr" / "Village_Boundary_2022_924768113126413998.csv"
v = pd.read_csv(geo)
SECTORS = v.drop_duplicates("Sector ID")[["Province ID", "Province", "District ID", "District", "Sector ID", "Sector"]].sort_values("Sector ID")
PROV_LABELS = {int(k): s for k, s in SECTORS.drop_duplicates("Province ID")[["Province ID", "Province"]].values}
DIST_LABELS = {int(k): s for k, s in SECTORS.drop_duplicates("District ID")[["District ID", "District"]].values}
SECT_LABELS = {int(k): s for k, s in SECTORS[["Sector ID", "Sector"]].values}

def match_names(df, prov_col, dist_name_col, sect_name_col, log, ck):
    """2011: province code + district/sector NAMES (ID2/ID3 are within-parent sequence numbers) ->
    current NISR district and sector codes, matched by name within parent (fuzzy for spelling)."""
    tab = df[[prov_col, dist_name_col, sect_name_col]].drop_duplicates()
    dmap, smap, fuzzy = {}, {}, []
    for p, g in tab.groupby(prov_col):
        cand = SECTORS[SECTORS["Province ID"] == p]
        dnames = {n.strip().upper(): int(k) for k, n in cand.drop_duplicates("District ID")[["District ID", "District"]].values}
        for dn in g[dist_name_col].dropna().unique():
            key = str(dn).strip().upper()
            if key in dnames: dmap[(p, dn)] = dnames[key]
            else:
                m = difflib.get_close_matches(key, list(dnames), n=1, cutoff=0.6)
                if not m: raise ValueError(f"district {dn!r} in province {p} unmatched among {list(dnames)}")
                dmap[(p, dn)] = dnames[m[0]]; fuzzy.append((dn, m[0]))
            d = dmap[(p, dn)]
            snames = {n.strip().upper(): int(k) for k, n in cand[cand["District ID"] == d][["Sector ID", "Sector"]].values}
            for sn in g.loc[g[dist_name_col] == dn, sect_name_col].dropna().unique():
                key = str(sn).strip().upper()
                if key in snames: smap[(p, dn, sn)] = snames[key]
                else:
                    m = difflib.get_close_matches(key, list(snames), n=1, cutoff=0.6)
                    if not m: raise ValueError(f"sector {sn!r} in district {dn} unmatched among {list(snames)}")
                    smap[(p, dn, sn)] = snames[m[0]]; fuzzy.append((sn, m[0]))
    log.info("2011 names matched fuzzily (spelling variants): %s", fuzzy)
    dist = pd.Series([dmap.get((p, dn)) for p, dn in zip(df[prov_col], df[dist_name_col])], index=df.index, dtype="float64")
    sect = pd.Series([smap.get((p, dn, sn)) for p, dn, sn in zip(df[prov_col], df[dist_name_col], df[sect_name_col])], index=df.index, dtype="float64")
    return dist, sect

def match_sectors_2011(df, log):
    """2011 sector NAMES (S003) -> current NISR sector codes within the (already coded) district;
    exact match first, then closest spelling; names that match nothing are logged and left missing."""
    tab = df[["dist", "s003"]].drop_duplicates(); smap, fuzzy, unmatched = {}, [], {}
    for d, g in tab.groupby("dist"):
        snames = {n.strip().upper(): int(k) for k, n in SECTORS[SECTORS["District ID"] == d][["Sector ID", "Sector"]].values}
        for sn in g["s003"].dropna().unique():
            key = str(sn).strip().upper()
            if key in snames: smap[(d, sn)] = snames[key]; continue
            m = difflib.get_close_matches(key, list(snames), n=1, cutoff=0.6)
            if m: smap[(d, sn)] = snames[m[0]]; fuzzy.append((int(d), sn, m[0]))
            else: unmatched[(int(d), sn)] = int((df["dist"].eq(d) & df["s003"].eq(sn)).sum())
    log.info("2011 sector names matched by closest spelling: %s", fuzzy)
    if unmatched: log.warning("2011 sector names with no match (rows): %s", unmatched)
    return pd.Series([smap.get((d, sn)) for d, sn in zip(df["dist"], df["s003"])], index=df.index, dtype="float64")

def ren(df, vl, vv, src, dst, srcmap):
    if src in df.columns and dst not in df.columns:
        df.rename(columns={src: dst}, inplace=True)
        if src in vl: vl[dst] = vl.pop(src)
        if src in vv: vv[dst] = vv.pop(src)
        srcmap[dst] = src; return True
    return False

for y in YEARS:
    log.info("---------------- %s ----------------", y)
    df, vl, vv = read_any(P["raw"] / str(y) / FILES[y]); n_raw = len(df)
    log.info("read %s: %s rows x %s vars", FILES[y], f"{n_raw:,}", df.shape[1])
    df, vl, vv = lower_names(df, vl, vv, log)
    srcmap, ck = {}, Checks(log)
    df["survey"] = "EC"; df["year"] = np.int16(y); df["wave"] = str(y)
    if y == 2011:
        ren(df, vl, vv, "id1", "prov", srcmap)
        x = pd.to_numeric(df["districts_names"], errors="coerce"); df["dist"] = np.where(x >= 100, (x // 100) * 10 + x % 100, x)
        srcmap["dist"] = "districts_names (NISR 101-507 codes -> 11-57)"
        df["sector"] = match_sectors_2011(df, log); srcmap["sector"] = "s003 (sector name) matched to NISR codes within district; unmatched names -> missing"
        seq = (df["prov"] * 1000 + df["id2"] * 100 + df["id3"])
        log.info("2011: shipped sequence codes (ID1*1000+ID2*100+ID3) equal the name-matched sector code in %.4f of rows", (seq == df["sector"]).mean())
        df = df.rename(columns={"id4": "cell_seq_2011", "id5": "village_seq_2011"})
        df["urban"] = df["u_r"].map({1: 2, 2: 1}); srcmap["urban"] = "u_r recoded (2011 codes 1 rural, 2 urban -> key block 1 urban, 2 rural; u_r kept)"
        df["estid"] = df["key"]; srcmap["estid"] = "key"
        df["wt"] = 1.0; srcmap["wt"] = "1 (full enumeration)"
    elif y == 2014:
        ren(df, vl, vv, "id1", "prov", srcmap); ren(df, vl, vv, "id2", "dist", srcmap); ren(df, vl, vv, "id3", "sector", srcmap)
        df["urban"] = df["u_r"].map({1: 2, 2: 1}); srcmap["urban"] = "u_r recoded (2014 codes 1 rural, 2 urban -> key block 1 urban, 2 rural; u_r kept)"
        df["estid"] = df["key"]; srcmap["estid"] = "key"
        ren(df, vl, vv, "sampleweight_final_", "wt", srcmap)
    else:
        ren(df, vl, vv, "q1_1", "prov", srcmap); ren(df, vl, vv, "q1_2", "dist", srcmap)
        x = pd.to_numeric(df["dist"], errors="coerce"); df["dist"] = np.where(x >= 100, (x // 100) * 10 + x % 100, x)
        ren(df, vl, vv, "q1_5_1", "urban", srcmap)      # 1 urban, 2 rural already
        df["estid"] = y * 1_000_000 + np.arange(1, len(df) + 1); srcmap["estid"] = "year*1e6 + row number (no establishment id shipped)"
        df["wt"] = 1.0; srcmap["wt"] = "1 (full enumeration)"
    vv["prov"], vv["dist"], vv["urban"] = PROV_LABELS, DIST_LABELS, URBAN_LABELS
    if "sector" in df.columns: vv["sector"] = SECT_LABELS
    for c, t in KEY_LABELS.items():
        if c in df.columns: vl[c] = t
    df = destring(df, log, skip=("survey", "wave", "s001", "s002", "s003", "q22_other"))
    df = downcast(df, keep_double=("wt", "estid", "key"))
    df = df[[c for c in KEY_ORDER if c in df.columns] + [c for c in df.columns if c not in KEY_ORDER]]

    ck(len(df) == n_raw, f"row count unchanged ({n_raw:,})")
    ck(df["estid"].is_unique, "estid unique")
    ck(df["prov"].nunique() == 5 and set(df["prov"].dropna().unique()) <= set(PROV_LABELS), "5 provinces on NISR codes")
    ck(df["dist"].nunique() == 30 and set(df["dist"].dropna().unique()) == set(DIST_LABELS), "30 districts on the 11-57 scheme")
    ck((df["dist"] // 10 == df["prov"]).all(), "district nests in province")
    if "sector" in df.columns:
        ck(set(df["sector"].dropna().unique()) <= set(SECT_LABELS), f"sector codes within the NISR 416-sector list ({df['sector'].nunique()} sectors present)")
        ck((df.loc[df['sector'].notna(), "sector"] // 100 == df.loc[df['sector'].notna(), "dist"]).all(), "sector nests in district")
        ck(df["sector"].notna().mean() > 0.98, f"sector assigned for {df['sector'].notna().mean():.2%} of establishments", hard=False)
    ck(set(df["urban"].dropna().unique()) <= {1, 2}, "urban in {1,2}")
    ck(df["wt"].notna().all() and (df["wt"] > 0).all(), "wt present and > 0")
    if y in PUBLISHED:
        working = df["wt"].sum() if y != 2011 else float((df["s04"] == 1).sum())
        ck(abs(working / PUBLISHED[y] - 1) < 0.01, f"{'working' if y == 2011 else 'weighted'} establishments {working:,.0f} within 1% of published {PUBLISHED[y]:,}")
    log.info("urban share: %.3f | total workers: %s", (df["urban"] == 1).mean(),
             f"{df['total_workers'].sum():,.0f}" if "total_workers" in df else (f"{df['q20'].where(df['q20'] < 88888).sum():,.0f} (q20)" if "q20" in df else "n/a"))
    ck.done()
    write_dta(df, P["inter"] / f"EC_{y}_establishment_clean.dta", vl, vv, f"Rwanda Establishment Census {y} (cleaned)", log)
    save_json({"n": len(df), "vars": list(df.columns), "var_labels": vl, "value_labels": {k: v for k, v in vv.items() if k in df.columns},
               "source": srcmap, "dtypes": {c: str(df[c].dtype) for c in df.columns}}, LOGS / f"clean_{y}_meta.json")
log.info("01_clean done for %s", YEARS)
