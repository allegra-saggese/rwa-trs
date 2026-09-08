"""
01_clean.py -- WBES: 1_Raw/* -> 2_Intermediate/WBES_<wave>_establishment_clean.dta (one file per round)

Four rounds from three shipped files (see z_Documentation and the folder README):
  2006, 2011   the World Bank's own panel file, which stacks 2006 / 2011 / 2019 with one row per
               firm-round. Items asked in a subset of rounds carry a wave prefix there
               (_2006_, _2011_, _2019_, _2006_2011_, _2011_2019_, _2006_2019_); the prefix is
               stripped so an item lands on its questionnaire code and lines up across rounds.
  2019         the stand-alone 2019 release (403 variables, including the sampling region and
               sector that the panel drops), with the panel's extra columns for those firms
               merged on the World Bank firm id -- the two agree on every shared column.
  2023         the stand-alone 2023 release (the redesigned "BEE" questionnaire).

Per round: lower-case names, the key block (survey year wave establishment_id country_firm_id
panel_id panel_rounds sampling_region region locality_size sector_* size_* stratum weight*),
columns that the round did not ask dropped, destring, downcast, back-check, then written under
the clean names of variable_names.csv (native names, labels and value labels stay in
logs/clean_<wave>_meta.json for 02_merge, 00_names and the codebook). Unit = establishment.
"""
import json, re, sys
import numpy as np, pandas as pd
from wbes_helpers import (paths, get_logger, Checks, read_dta, write_dta, lower_names, destring, downcast,
                          save_json, LOGS, HERE, NameTable, DATASET_TAG)

log = get_logger("01_clean"); P = paths()
NAMES = NameTable(HERE / "variable_names.csv", DATASET_TAG)      # clean names and labels per file (built by 00_names.py, committed)
WAVES = [w for w in (sys.argv[1:] or ["2006", "2011", "2019", "2023"])]
RAW = {"2019": P["raw"] / "2019" / "WBES_2019.dta", "2023": P["raw"] / "2023" / "WBES_2023.dta",
       "panel": P["raw"] / "panel" / "WBES_panel_2006_2011_2019.dta"}
PUBLISHED = {"2006": 212, "2011": 241, "2019": 360, "2023": 358}      # interviewed establishments, implementation reports
WEIGHTED = {"2019", "2023"}       # the panel file carries no weights for 2006 / 2011 (see the README: use those rounds unweighted)

KEY_ORDER = ["survey", "year", "wave", "idstd", "id", "panelid", "panel", "a2", "a3a", "a3", "a4a", "a4b",
             "a6a", "a6b", "strata", "stratificationregioncode", "wstrict", "wmedian", "wweak"]
KEY_LABELS = {"survey": "Source survey", "year": "Survey year", "wave": "Round (2006, 2011, 2019, 2023)",
              "idstd": "World Bank standard firm identifier, unique across countries and rounds",
              "id": "Firm identifier of the round as issued by the survey firm",
              "panelid": "Firm identifier shared across rounds by the World Bank panel (blank in 2023)",
              "panel": "Rounds in which the firm was interviewed (panel file)",
              "a2": "Sampling region", "a3a": "Region of the establishment", "a3": "Size of the locality",
              "a4a": "Industry sampling sector", "a4b": "Industry screener sector",
              "a6a": "Sampling size class", "a6b": "Screener size class",
              "strata": "Sampling stratum: industry by size by region", "stratificationregioncode": "Stratification region code",
              "wstrict": "Sampling weight under strict eligibility (the World Bank's default)",
              "wmedian": "Sampling weight under the median eligibility assumption",
              "wweak": "Sampling weight under the weak eligibility assumption"}
_PREFIX = re.compile(r"^_((?:19|20)\d\d(?:_(?:19|20)\d\d)*)_")
DECODE = ("a2", "a3a", "a4a", "stratificationregioncode")      # classifications the rounds redraw: written as text, see below
# a4b (the screener sector) keeps its codes: they are ISIC-based and mean the same thing in every round (55 = hotels).

def panel_round(wave, log):
    """the panel's rows for one round, with the wave prefixes stripped so items land on their
    questionnaire code; a prefixed column is kept only when the round is one of its years"""
    df, vl, vv = read_dta(RAW["panel"])
    df, vl, vv = lower_names(df, vl, vv, log)
    keep, ren, taken = [], {}, {c for c in df.columns if not _PREFIX.match(c)}
    for c in df.columns:
        m = _PREFIX.match(c)
        if m is None: keep.append(c); continue
        if wave not in m.group(1).split("_"): continue
        stem = c[m.end():]
        if stem in taken: stem = f"{stem}_{m.group(1)}"      # 2011 ships both `panel` and `_2011_Panel`: keep them apart
        keep.append(c); ren[c] = stem; taken.add(stem)
    df = df[keep].rename(columns=ren)
    vl = {ren.get(c, c): t for c, t in vl.items() if c in keep}
    vv = {ren.get(c, c): d for c, d in vv.items() if c in keep}
    out = df[pd.to_numeric(df["year"], errors="coerce") == int(wave)].reset_index(drop=True)
    log.info("%s: %s of %s panel rows, %d columns after stripping the wave prefixes", wave, f"{len(out):,}", f"{len(df):,}", out.shape[1])
    return out, vl, vv

def standalone(wave, log):
    df, vl, vv = read_dta(RAW[wave]); df, vl, vv = lower_names(df, vl, vv, log)
    return df, vl, vv

meta_all = {}
for wave in WAVES:
    log.info("================ %s ================", wave)
    ck = Checks(log); srcmap = {}
    if wave in ("2006", "2011"):
        df, vl, vv = panel_round(wave, log)
        srcmap = {c: f"panel file (wave prefix stripped where present)" for c in df.columns}
    else:
        df, vl, vv = standalone(wave, log)
        srcmap = {c: f"{RAW[wave].name}" for c in df.columns}
        if wave == "2019":                                   # add what only the panel carries for these firms
            pdf, pvl, pvv = panel_round("2019", log)
            extra = [c for c in pdf.columns if c not in df.columns]
            common = [c for c in pdf.columns if c in df.columns and c != "idstd"]
            disagree = []
            for c in common:                                  # the two releases must agree where they overlap
                a = pdf.set_index("idstd")[c].sort_index(); b = df.set_index("idstd")[c].sort_index()
                na, nb = pd.to_numeric(a, errors="coerce"), pd.to_numeric(b, errors="coerce")
                if na.notna().any() or nb.notna().any():
                    ok = ((na.isna() & nb.isna()) | np.isclose(na.fillna(-9e18), nb.fillna(-9e18))).all()
                else: ok = (a.astype(str).values == b.astype(str).values).all()
                if not ok: disagree.append(c)
            ck(not disagree, f"2019: the panel and the stand-alone release agree on all {len(common)} shared columns" + (f" -- differ on {disagree[:5]}" if disagree else ""))
            df = df.merge(pdf[["idstd"] + extra], on="idstd", how="left")
            for c in extra: vl[c] = pvl.get(c, ""); vv[c] = pvv.get(c, {}); srcmap[c] = "panel file (merged on idstd)"
            log.info("2019: %d columns merged from the panel (panel link, and items the stand-alone file does not carry)", len(extra))
    n_raw = len(df)
    # The region and the sector partitions are redrawn between rounds: code 2 is Butare in 2006/2011, Western Province
    # in 2019 and "Western and Northern" in 2023; sector code 2 is Services in 2011 and Retail from 2019. Pooling those
    # codes would make one number mean several things, so these columns are written as the round's own text.
    for c in DECODE:
        if c not in df.columns: continue
        lab = {float(k): str(v) for k, v in (vv.get(c) or {}).items() if str(k).lstrip("-").replace(".", "", 1).isdigit()}
        if not lab: continue
        num = pd.to_numeric(df[c], errors="coerce")
        unlabelled = sorted(set(num.dropna().unique()) - set(lab))
        if unlabelled: log.warning("%s: %s has codes without a label, kept as the code itself: %s", wave, c, unlabelled[:8])
        df[c] = [None if pd.isna(x) else lab.get(x, f"{x:g}") for x in num]
        vv.pop(c, None); log.info("%s: %s written as text (%s)", wave, c, ", ".join(sorted(set(lab.values()))[:6]))
    df["survey"] = "WBES"; df["year"] = np.int16(int(wave)); df["wave"] = wave
    for c, t in KEY_LABELS.items():
        if c in df.columns: vl[c] = t
    # a round carries only the items it asked: an all-missing column belongs to another round
    empty = [c for c in df.columns if c not in KEY_ORDER and df[c].isna().all()]
    if empty: df = df.drop(columns=empty); log.info("%s: %d columns dropped, not asked in this round", wave, len(empty))
    df = destring(df, log, skip=("survey", "wave", "panel", *DECODE))
    df = downcast(df, keep_double=("idstd", "id", "panelid", "wstrict", "wmedian", "wweak"))
    df = df[[c for c in KEY_ORDER if c in df.columns] + [c for c in df.columns if c not in KEY_ORDER]]

    ck(len(df) == n_raw, f"row count unchanged ({n_raw:,})")
    ck(len(df) == PUBLISHED[wave], f"{len(df):,} establishments == the implementation report's {PUBLISHED[wave]:,}")
    ck(df["idstd"].is_unique, "World Bank firm id unique")
    # The World Bank's panel file ships no sampling weights for 2006 and 2011 (only 2019); the stand-alone
    # releases of those two rounds carry them but are not part of this folder. Recorded, not worked around.
    w = pd.to_numeric(df["wstrict"], errors="coerce")
    if wave in WEIGHTED: ck(w.notna().all() and (w > 0).all(), f"{wave}: the strict-eligibility weight is present and > 0 on every row")
    else: ck(w.isna().all(), f"{wave}: no sampling weight in the World Bank panel file (declared limitation, see the README)", hard=False)
    log.info("%s: %s establishments x %s variables | weighted universe (strict) = %s", wave, f"{len(df):,}", df.shape[1],
             f"{w.sum():,.0f}" if wave in WEIGHTED else "not shipped for this round")
    ck.done()

    out_df, vl_out, vv_out, clean_names = NAMES.apply(df, vl, vv, f"wave:{wave}", log)      # written under the clean names; native kept in the meta
    write_dta(out_df, P["inter"] / f"WBES_{wave}_establishment_clean.dta", vl_out, vv_out, f"World Bank Enterprise Survey Rwanda {wave} (cleaned)", log)
    meta_all[wave] = {"n": len(df), "vars": list(df.columns), "var_labels": vl,
                      "value_labels": {k: v for k, v in vv.items() if k in df.columns}, "source": srcmap,
                      "dtypes": {c: str(df[c].dtype) for c in df.columns}, "clean_names": clean_names}
    save_json(meta_all[wave], LOGS / f"clean_{wave}_meta.json")
log.info("01_clean done for %s", WAVES)
