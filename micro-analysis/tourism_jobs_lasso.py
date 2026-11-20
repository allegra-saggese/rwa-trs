"""
tourism_jobs_lasso.py -- who holds tourism jobs? A lasso on the Census, 2012 and 2022.

Outcome   1 if a worker's industry is ISIC section I (accommodation and food) or R (arts,
          entertainment and recreation), 0 for any other stated industry. Sample: residents aged
          16+ with a stated industry, each Census wave on its own.

Candidates: person characteristics (age, sex, schooling, literacy, marital status, relationship
to the head, migration, nationality, religion, parents alive, registration, fertility, disability),
household characteristics (size and composition, the head's sex, age and schooling, settlement
type, urban), household wealth (grid electricity, phone, vehicle, land, and in 2022 every crop the
household grew), and all pairwise interactions of the demographic block (age band, sex, schooling,
marital status, urban). Wealth may partly be a result of a tourism job; it is kept as a predictor on
purpose (better-off households may find service jobs more easily).

Two models, each wave:
  individual   person and household characteristics only (no sector features)
  exposure     the same, plus the sector's park exposure -- borders a park (dummy) and the share of
               the sector's area inside a park -- and log population density (persons per km2 of
               non-park land, from that wave's Census). These three are always kept (not penalised);
               the lasso selects among the person and household characteristics around them.

Method
  1. L1-penalised logit, Census person weights, features standardised. The penalty is chosen by
     5-fold cross-validation with folds grouped by sector (no sector in both training and test fold),
     at the value with the highest out-of-fold log-likelihood.
  2. Out-of-fold fit at that penalty: area under the ROC curve and under the precision-recall curve
     (the base rate is the reference for the latter).
  3. Post-lasso: a linear probability model on the selected variables (plus the kept ones), weighted,
     with CR1 standard errors clustered by sector; wild cluster restricted bootstrap p-values
     (helpers/regression.py) for the three sector variables of the exposure model. The intervals ignore the selection step: these coefficients describe who
     holds tourism jobs, they are not causal effects.

Writes (Dropbox output/tables/regressions/):
  census_tourism_jobs_lasso_<year>_<model>.csv   every candidate: lasso coefficient (standardised,
                                                 logit scale), selected or not, post-lasso LPM
                                                 coefficient, SE, wild-bootstrap p
  census_tourism_jobs_lasso_fit.csv              one row per year x model: sample, base rate, penalty,
                                                 variables selected, out-of-fold AUC and PR-AUC

Usage
    python micro-analysis/tourism_jobs_lasso.py                       # both waves, both models
    python micro-analysis/tourism_jobs_lasso.py --years 2012 --models individual
    python micro-analysis/tourism_jobs_lasso.py --sample 0.2          # 20% of sectors, for a quick test
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "helpers"))
import paths as P  # noqa: E402
from regression import fe_ols  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pyreadstat  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import average_precision_score, roc_auc_score  # noqa: E402
from sklearn.model_selection import GroupKFold  # noqa: E402

CENSUS = P.NISR / "Census-PHC/3_Final/Census_pooled_person.dta"
SECTORS = P.HARMONIZED / "model_sector_cross.csv"
OUT = P.TABLES_REG
TOURISM = {9, 18}                       # ISIC sections I and R (same as the labour tables)
NOT_STATED = {2012: {22, 23}, 2022: {22}}   # "industry not stated", "not applicable"
FORCED = ["border", "park_share", "log_pop_density"]
C_GRID = np.logspace(-4, 0, 13)         # inverse penalty strength for the L1 logit
B = int(os.environ.get("WCB_REPS", 9999))


def _log(msg):
    print(f"[tourism-lasso] {msg}", flush=True)


# ---------------------------------------------------------------------------- sample and features
COLS = {
    2012: ["census_education_level_2012", "census_school_attendance_2012", "census_marital_status_2012",
           "census_relation_head_2002_2012", "census_birth_place_2012", "census_disability_any_2012",
           "census_isic_section_2012", "census_years_completed_2012", "census_highest_certificate_2012",
           "census_languages_literate_2012", "census_religion_2012", "census_nationality_group_2012",
           "census_mother_alive_2012", "census_father_alive_2012", "census_mother_in_household_2012",
           "census_father_in_household_2012", "census_residence_duration_2012",
           "census_previous_residence_2012", "census_age_first_marriage_2012", "census_births_boys_2012",
           "census_births_girls_2012", "census_children_alive_boys_2012", "census_children_alive_girls_2012",
           "census_birth_registered_2012", "census_area_residence_2012", "census_settlement_2002_2012",
           "census_lighting_source_2012", "census_cell_phones_2012", "census_vehicles_2012", "census_land_2012"],
    2022: ["census_education_level_2022", "census_school_attendance_2022", "census_marital_status_2022",
           "census_relation_head_2022", "census_birth_district_2022", "census_birth_country_2022",
           "census_literacy_languages_2022", "census_difficulty_seeing_2022", "census_difficulty_hearing_2022",
           "census_difficulty_walking_2022", "census_difficulty_communic_2022",
           "census_difficulty_remember_2022", "census_difficulty_self_care_2022", "census_isic_section_2022",
           "census_years_completed_2022", "census_highest_certificate_2022", "census_religion_2022",
           "census_nationality_country_2022", "census_mother_alive_2022", "census_father_alive_2022",
           "census_mother_in_household_2022", "census_father_in_household_2022",
           "census_residence_duration_2022", "census_previous_in_rwanda_2022", "census_previous_district_2022",
           "census_age_first_marriage_2022", "census_births_boys_2022", "census_births_girls_2022",
           "census_children_alive_boys_2022", "census_children_alive_girls_2022",
           "census_civil_registered_2022", "census_settlement_2022", "census_grid_electricity_2022",
           "census_mobile_phone_type_2022", "census_asset_vehicle_2022", "census_farming_place_2022",
           "census_grew_crops_2022", "census_fruit_trees_2022"],
}
BASE = ["census_year", "census_household_id", "census_sector", "census_district", "census_urban",
        "census_sex", "census_age", "census_weight"]


def load(year: int) -> tuple[pd.DataFrame, dict]:
    """One row per resident of that wave, with household counts and the head's characteristics attached."""
    meta = pyreadstat.read_dta(str(CENSUS), metadataonly=True)[1]
    crops = [c for c in meta.column_names if c.endswith("_grown")] if year == 2022 else []
    d, meta = pyreadstat.read_dta(str(CENSUS), usecols=BASE + COLS[year] + crops)
    d = d[d.census_year == year].copy()
    d.attrs["crops"] = crops
    hh = d.groupby("census_household_id")
    a = d.census_age
    d["hh_size"] = hh.census_age.transform("size")
    d["hh_children_u15"] = hh.census_age.transform(lambda x: (x < 15).sum())
    d["hh_elderly_65p"] = hh.census_age.transform(lambda x: (x >= 65).sum())
    d["_adult"] = (a >= 16).astype(int)
    d["_adult_woman"] = ((a >= 16) & (d.census_sex == 2)).astype(int)
    d["_working_age"] = ((a >= 15) & (a <= 64)).astype(int)
    d["hh_adults"] = hh._adult.transform("sum")
    d["hh_adult_women"] = hh._adult_woman.transform("sum")
    d["hh_dependency_ratio"] = (d.hh_children_u15 + d.hh_elderly_65p) / hh._working_age.transform("sum").clip(lower=1)
    rel = "census_relation_head_2002_2012" if year == 2012 else "census_relation_head_2022"
    edu = f"census_education_level_{year}"
    head = d[d[rel] == 1].drop_duplicates("census_household_id").set_index("census_household_id")
    for c, name in [("census_sex", "head_sex"), ("census_age", "head_age"), (edu, "head_education")]:
        d[name] = d.census_household_id.map(head[c])
    if year == 2022:                                   # phones are asked per person in 2022
        d["_phone"] = d.census_mobile_phone_type_2022.isin([1, 2, 3]).astype(int)
        d["hh_any_phone"] = hh._phone.transform("max")
    return d, meta.variable_value_labels


def dummies(s: pd.Series, labels: dict, prefix: str, drop=None, skip=()) -> pd.DataFrame:
    """One 0/1 column per category, named by its label; `drop` is the omitted category."""
    keep = [k for k in sorted(s.dropna().unique()) if k not in skip and k != drop]
    out = {}
    for k in keep:
        name = f"{prefix}: {str(labels.get(k, k)).strip()}"
        out[name] = (s == k).astype(float)
    return pd.DataFrame(out, index=s.index)


DEMOGRAPHIC = ("age ", "female", "education: ", "never attended school", "marital: ", "urban")


def _num(s: pd.Series, missing=()) -> pd.Series:
    """Numeric value with the not-stated codes set to 0 (their own dummy carries the information)."""
    return s.where(~s.isin(missing)).fillna(0).astype(float)


def features(d: pd.DataFrame, vl: dict, year: int) -> pd.DataFrame:
    """Every candidate predictor; missing or not-stated categories get their own dummy or a zero."""
    X = pd.DataFrame(index=d.index)
    lab = lambda c: vl.get(c, {})
    # ---- demographic block (these are also interacted with each other)
    X["female"] = (d.census_sex == 2).astype(float)
    bands = pd.cut(d.census_age, [15, 19, 24, 29, 34, 39, 44, 49, 54, 59, 64, 200],
                   labels=["16-19", "20-24", "25-29", "30-34", "35-39", "40-44", "45-49", "50-54",
                           "55-59", "60-64", "65+"])
    X = X.join(pd.get_dummies(bands, prefix="age", prefix_sep=" ", dtype=float).drop(columns="age 30-34"))
    X["urban"] = (d.census_urban == 1).astype(float)
    if year == 2012:
        X["never attended school"] = (d.census_school_attendance_2012 == 1).astype(float)
        X = X.join(dummies(d.census_education_level_2012, lab("census_education_level_2012"), "education",
                           drop=1, skip=(99,)))
        X = X.join(dummies(d.census_marital_status_2012, lab("census_marital_status_2012"), "marital", drop=2))
    else:
        X["never attended school"] = (d.census_school_attendance_2022 == 3).astype(float)
        X = X.join(dummies(d.census_education_level_2022, lab("census_education_level_2022"), "education",
                           drop=3))
        X["education: not stated"] = d.census_education_level_2022.isna().astype(float)
        X = X.join(dummies(d.census_marital_status_2022, lab("census_marital_status_2022"), "marital", drop=1))
    demog = [c for c in X.columns if c.startswith(DEMOGRAPHIC)]

    # ---- other person characteristics
    y = str(year)
    rel = "census_relation_head_2002_2012" if year == 2012 else "census_relation_head_2022"
    X = X.join(dummies(d[rel], lab(rel), "relation to head", drop=1))
    X["years completed at highest level"] = _num(d[f"census_years_completed_{y}"], (9, 99))
    X = X.join(dummies(d[f"census_highest_certificate_{y}"], lab(f"census_highest_certificate_{y}"),
                       "certificate", drop=None, skip=(0, 9, 99)))
    X = X.join(dummies(d[f"census_religion_{y}"], lab(f"census_religion_{y}"), "religion", drop=1))
    for p in ("mother", "father"):
        X[f"{p} not alive"] = (d[f"census_{p}_alive_{y}"] == 2).astype(float)
        X[f"{p} lives in the household"] = (d[f"census_{p}_in_household_{y}"] == 1).astype(float)
    dur = d[f"census_residence_duration_{y}"]
    never = dur.isin([999] if year == 2012 else [888])
    X["never moved"] = never.astype(float)
    X["years in current place"] = np.where(never, d.census_age, _num(dur, (888, 999)))
    X["age at first marriage"] = _num(d[f"census_age_first_marriage_{y}"], (98, 99, 999))
    born = _num(d[f"census_births_boys_{y}"], (98, 99)) + _num(d[f"census_births_girls_{y}"], (98, 99))
    alive = _num(d[f"census_children_alive_boys_{y}"], (98, 99)) + _num(d[f"census_children_alive_girls_{y}"], (98, 99))
    X["children ever born"] = born
    X["children who died"] = (born - alive).clip(lower=0)
    if year == 2012:
        bp = d.census_birth_place_2012
        X["born abroad"] = (bp > 57).astype(float)
        X["born in another district"] = ((bp <= 57) & (bp != d.census_district)).astype(float)
        pr = d.census_previous_residence_2012
        X["previously lived abroad"] = (pr > 57).astype(float)
        X["previously lived in another district"] = ((pr <= 57) & (pr != d.census_district)).astype(float)
        X["foreign national"] = (~d.census_nationality_group_2012.isin([1, 2, 99]) &
                                 d.census_nationality_group_2012.notna()).astype(float)
        X["dual citizen"] = (d.census_nationality_group_2012 == 2).astype(float)
        lit = d.census_languages_literate_2012.map(lab("census_languages_literate_2012")).fillna("")
        X["reads and writes English"] = lit.str.contains("English").astype(float)
        X["reads and writes French"] = lit.str.contains("French").astype(float)
        X["cannot read or write"] = (d.census_languages_literate_2012 == 0).astype(float)
        X["birth registered"] = (d.census_birth_registered_2012 == 1).astype(float)
        X["disability"] = (d.census_disability_any_2012 == 1).astype(float)
    else:
        X["born abroad"] = d.census_birth_country_2022.notna().astype(float)
        X["born in another district"] = (d.census_birth_district_2022.notna()
                                         & (d.census_birth_district_2022 != d.census_district)).astype(float)
        X["previously lived abroad"] = (d.census_previous_in_rwanda_2022 == 2).astype(float)
        X["previously lived in another district"] = (d.census_previous_district_2022.notna()
                                                     & (d.census_previous_district_2022 != d.census_district)).astype(float)
        nat = d.census_nationality_country_2022.map(lab("census_nationality_country_2022")).fillna("")
        X["foreign national"] = (d.census_nationality_country_2022.notna()
                                 & ~nat.str.contains("Rwanda", case=False)).astype(float)
        lit = d.census_literacy_languages_2022.map(lab("census_literacy_languages_2022")).fillna("")
        X["reads and writes English"] = lit.str.contains("Engl|Engish", case=False).astype(float)
        X["reads and writes French"] = lit.str.contains("French", case=False).astype(float)
        X["reads and writes Swahili"] = lit.str.contains("Swahili|Swahii", case=False).astype(float)
        X["cannot read or write"] = (d.census_literacy_languages_2022 == 0).astype(float)
        X["civil registration"] = (d.census_civil_registered_2022 == 1).astype(float)
        diff = d[[c for c in d.columns if c.startswith("census_difficulty_")]]
        X["disability"] = (diff >= 2).any(axis=1).astype(float)

    # ---- household characteristics
    X["household size"] = d.hh_size
    X["children under 15 in household"] = d.hh_children_u15
    X["people 65+ in household"] = d.hh_elderly_65p
    X["adults in household"] = d.hh_adults
    X["adult women in household"] = d.hh_adult_women
    X["dependency ratio"] = d.hh_dependency_ratio
    X["head is female"] = (d.head_sex == 2).astype(float)
    X["head's age"] = d.head_age.fillna(d.head_age.median())
    X = X.join(dummies(d.head_education, lab(f"census_education_level_{y}"), "head's education",
                       drop=1 if year == 2012 else 3, skip=(99,)))
    sett = "census_settlement_2002_2012" if year == 2012 else "census_settlement_2022"
    X = X.join(dummies(d[sett], lab(sett), "settlement", drop=1, skip=(9,)))
    if year == 2012:
        X = X.join(dummies(d.census_area_residence_2012, lab("census_area_residence_2012"), "area", drop=2))

    # ---- household wealth
    if year == 2012:
        X["grid electricity"] = (d.census_lighting_source_2012 == 1).astype(float)
        X["household has a phone"] = (d.census_cell_phones_2012.fillna(0) > 0).astype(float)
        X["household has a vehicle"] = (d.census_vehicles_2012.fillna(0) > 0).astype(float)
        land = d.census_land_2012.map(lab("census_land_2012")).fillna("")
        X["farms own land"] = land.str.contains("own land", case=False).astype(float)
        X["farms rented land"] = land.str.contains("in land he rented|Land rented|and rent", case=False).astype(float)
    else:
        X["grid electricity"] = (d.census_grid_electricity_2022 == 1).astype(float)
        X["household has a phone"] = d.hh_any_phone.astype(float)
        X["owns a smartphone"] = (d.census_mobile_phone_type_2022 == 1).astype(float)
        X["household has a vehicle"] = (d.census_asset_vehicle_2022 == 1).astype(float)
        X["farms own land"] = d.census_farming_place_2022.isin([1, 3]).astype(float)
        X["farms rented land"] = d.census_farming_place_2022.isin([2, 3]).astype(float)
        X["household grew crops"] = (d.census_grew_crops_2022 == 1).astype(float)
        X["grows fruit trees"] = (d.census_fruit_trees_2022 == 1).astype(float)
        for c in d.attrs.get("crops", []):
            X["grows " + c.replace("census_", "").replace("_grown", "").replace("_", " ")] = (d[c] == 1).astype(float)

    X = X.loc[:, X.std() > 0]
    # ---- pairwise interactions of the demographic block (pairs within one categorical are all zero)
    demog = [c for c in demog if c in X.columns]
    group = lambda c: c.split(":")[0] if ":" in c else c.split(" ")[0]
    inter = {}
    for i, a in enumerate(demog):
        for b in demog[i + 1:]:
            if group(a) == group(b):
                continue
            v = X[a] * X[b]
            if v.std() > 0:
                inter[f"{a} x {b}"] = v
    return pd.concat([X, pd.DataFrame(inter, index=X.index)], axis=1).astype("float32")


def sector_features(d: pd.DataFrame) -> pd.DataFrame:
    """Park exposure of the resident's sector, and log persons per km2 of non-park land (this wave)."""
    s = pd.read_csv(SECTORS)[["sid", "border", "park_share", "Lbar_km2"]]
    pop = d.groupby("census_sector").census_weight.sum().rename("pop").reset_index()
    s = s.merge(pop, left_on="sid", right_on="census_sector", how="left")
    s["log_pop_density"] = np.log(s["pop"] / s.Lbar_km2)
    m = d[["census_sector"]].merge(s[["sid"] + FORCED], left_on="census_sector", right_on="sid", how="left")
    m.index = d.index
    return m[FORCED].astype(float)


def sample(year: int, frac: float | None) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, np.ndarray, np.ndarray]:
    d, vl = load(year)
    S = sector_features(d)
    isic = d[f"census_isic_section_{year}"]
    w = (d.census_age >= 16) & isic.notna() & ~isic.isin(NOT_STATED[year])
    if frac:
        rng = np.random.default_rng(0)
        secs = d.census_sector.unique()
        w &= d.census_sector.isin(rng.choice(secs, int(len(secs) * frac), replace=False))
    X = features(d[w], vl, year)
    y = isic[w].isin(TOURISM).astype(int)
    return X, S[w], y, d.census_weight[w].to_numpy(float), d.census_sector[w].to_numpy(int)


# ---------------------------------------------------------------------------- lasso
def _standardise(Z: np.ndarray, wt: np.ndarray):
    mu = np.average(Z, axis=0, weights=wt)
    sd = np.sqrt(np.average((Z - mu) ** 2, axis=0, weights=wt))
    return (Z - mu) / np.where(sd > 0, sd, 1), mu, sd


def _fit(Z, y, wt, C):
    m = LogisticRegression(penalty="l1", solver="liblinear", C=C, intercept_scaling=100, max_iter=500)
    return m.fit(Z, y, sample_weight=wt)


def lasso(X: pd.DataFrame, forced: pd.DataFrame | None, y, wt, groups):
    """L1 logit with the `forced` columns left (effectively) unpenalised. Returns coefficients,
    chosen C and out-of-fold predictions at that C."""
    Z = X if forced is None else pd.concat([X, forced], axis=1)
    names = list(Z.columns)
    Zs, _, sd = _standardise(Z.to_numpy(np.float32), wt.astype(np.float32))
    Zs = Zs.astype(np.float64)   # liblinear works in double precision
    nf = 0 if forced is None else forced.shape[1]
    if nf:
        Zs[:, -nf:] *= 1e3                 # an L1 penalty on a coefficient 1000x smaller: effectively none
    wt = wt / wt.mean()
    folds = list(GroupKFold(n_splits=5).split(Zs, y, groups))
    ll = np.zeros(len(C_GRID)); oof = {}
    for i, C in enumerate(C_GRID):
        p = np.empty(len(y))
        for tr, te in folds:
            p[te] = _fit(Zs[tr], y[tr], wt[tr], C).predict_proba(Zs[te])[:, 1]
        pc = np.clip(p, 1e-9, 1 - 1e-9)
        ll[i] = np.average(y * np.log(pc) + (1 - y) * np.log(1 - pc), weights=wt)
        oof[C] = p
        _log(f"    C={C:.2e}  out-of-fold log-likelihood {ll[i]:.5f}")
    best = C_GRID[int(np.argmax(ll))]
    m = _fit(Zs, y, wt, best)
    coef = m.coef_[0].copy()
    if nf:
        coef[-nf:] *= 1e3                  # back to per-standard-deviation units
    return pd.Series(coef, index=names), best, oof[best]


# ---------------------------------------------------------------------------- post-lasso LPM
def post_lasso(X: pd.DataFrame, y, wt, groups, keep: list[str]) -> pd.DataFrame:
    """Weighted LPM of y on the kept variables: WLS by scaling every column (and the constant) by sqrt(w)."""
    r = np.sqrt(wt / wt.mean())
    df = pd.DataFrame({c: X[c].to_numpy(float) * r for c in keep})
    df["constant"] = r
    df["y"] = y * r
    df["sector"] = groups
    xs = keep + ["constant"]
    test = [c for c in FORCED if c in keep]
    est, n, G = fe_ols(df, "y", xs, [], "sector", B=B, test=test)
    return est


def run(year: int, model: str, frac: float | None) -> dict:
    t0 = time.time()
    _log(f"{year} / {model}: building the sample")
    X, S, y, wt, groups = sample(year, frac)
    forced = S if model == "exposure" else None
    _log(f"  {len(y):,} workers in {len(np.unique(groups))} sectors; tourism share "
         f"{np.average(y, weights=wt):.2%} weighted, {y.sum():,} tourism workers")
    coef, C, oof = lasso(X, forced, y.to_numpy(), wt, groups)
    sel = [c for c in X.columns if coef[c] != 0]
    keep = sel + (FORCED if forced is not None else [])
    Xall = X if forced is None else pd.concat([X, forced], axis=1)
    _log(f"  penalty C={C:.2e}: {len(sel)} of {X.shape[1]} person / household variables selected; "
         f"post-lasso LPM" + (f" with {B} bootstrap draws for the sector variables" if forced is not None else ""))
    est = post_lasso(Xall, y.to_numpy(), wt, groups, keep)
    tab = pd.DataFrame({"variable": Xall.columns, "lasso_coef_std_logit": coef.reindex(Xall.columns).values})
    tab["selected"] = tab.lasso_coef_std_logit.ne(0) | tab.variable.isin(FORCED if forced is not None else [])
    tab["kept_unpenalised"] = tab.variable.isin(FORCED) if forced is not None else False
    tab = tab.merge(est.rename_axis("variable").reset_index()[["variable", "coef", "se", "p_wcb"]]
                    .rename(columns={"coef": "lpm_coef", "se": "lpm_se", "p_wcb": "lpm_p_wild_bootstrap"}),
                    on="variable", how="outer")
    tab = tab.sort_values(["selected", "lasso_coef_std_logit"], key=lambda s: s.abs() if s.name != "selected" else s,
                          ascending=[False, False])
    tag = f"{year}_{model}" + ("_sample" if frac else "")
    OUT.mkdir(parents=True, exist_ok=True)
    tab.to_csv(OUT / f"census_tourism_jobs_lasso_{tag}.csv", index=False)
    yv = y.to_numpy()
    fit = {"year": year, "model": model, "sample_share_of_sectors": frac or 1.0, "workers": len(yv),
           "sectors": len(np.unique(groups)), "tourism_workers": int(yv.sum()),
           "tourism_share_weighted": np.average(yv, weights=wt), "penalty_C": C,
           "candidates": X.shape[1], "selected": len(sel),
           "oof_auc": roc_auc_score(yv, oof, sample_weight=wt),
           "oof_pr_auc": average_precision_score(yv, oof, sample_weight=wt)}
    _log(f"  out-of-fold AUC {fit['oof_auc']:.3f}, PR-AUC {fit['oof_pr_auc']:.3f} "
         f"(base rate {fit['tourism_share_weighted']:.3f}); {time.time() - t0:.0f}s")
    return fit


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--years", nargs="+", type=int, default=[2012, 2022], choices=[2012, 2022])
    p.add_argument("--models", nargs="+", default=["individual", "exposure"], choices=["individual", "exposure"])
    p.add_argument("--sample", type=float, default=None, help="share of sectors to keep, for a quick test")
    a = p.parse_args(argv)
    fits = [run(y, m, a.sample) for y in a.years for m in a.models]
    f = OUT / ("census_tourism_jobs_lasso_fit" + ("_sample" if a.sample else "") + ".csv")
    new = pd.DataFrame(fits)
    if f.exists():
        old = pd.read_csv(f)
        new = pd.concat([old[~old.set_index(["year", "model"]).index.isin(new.set_index(["year", "model"]).index)], new])
    new.sort_values(["year", "model"]).to_csv(f, index=False)
    _log(f"-> {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
