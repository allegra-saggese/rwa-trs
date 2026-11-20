"""
tourism_jobs_lasso.py -- who holds tourism jobs? A lasso on the Census, 2012 and 2022.

Outcome   1 if a worker's industry is ISIC section I (accommodation and food) or R (arts,
          entertainment and recreation), 0 for any other stated industry. Sample: residents aged
          16+ with a stated industry, each Census wave on its own.

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
     with CR1 standard errors and wild cluster restricted bootstrap p-values by sector
     (helpers/regression.py). The intervals ignore the selection step: these coefficients describe who
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
           "census_isic_section_2012"],
    2022: ["census_education_level_2022", "census_school_attendance_2022", "census_marital_status_2022",
           "census_relation_head_2022", "census_birth_district_2022", "census_birth_country_2022",
           "census_literacy_languages_2022", "census_difficulty_seeing_2022", "census_difficulty_hearing_2022",
           "census_difficulty_walking_2022", "census_difficulty_communic_2022",
           "census_difficulty_remember_2022", "census_difficulty_self_care_2022", "census_isic_section_2022"],
}
BASE = ["census_year", "census_household_id", "census_sector", "census_district", "census_urban",
        "census_sex", "census_age", "census_weight"]


def load(year: int) -> tuple[pd.DataFrame, dict]:
    """One row per resident of that wave, with the household counts attached."""
    d, meta = pyreadstat.read_dta(str(CENSUS), usecols=BASE + COLS[year])
    d = d[d.census_year == year].copy()
    hh = d.groupby("census_household_id")
    d["hh_size"] = hh.census_age.transform("size")
    d["hh_children_u15"] = hh.census_age.transform(lambda a: (a < 15).sum())
    d["hh_elderly_65p"] = hh.census_age.transform(lambda a: (a >= 65).sum())
    return d, meta.variable_value_labels


def dummies(s: pd.Series, labels: dict, prefix: str, drop=None, skip=()) -> pd.DataFrame:
    """One 0/1 column per category, named by its label; `drop` is the omitted category."""
    keep = [k for k in sorted(s.dropna().unique()) if k not in skip and k != drop]
    out = {}
    for k in keep:
        name = f"{prefix}: {str(labels.get(k, k)).strip()}"
        out[name] = (s == k).astype(float)
    return pd.DataFrame(out, index=s.index)


def features(d: pd.DataFrame, vl: dict, year: int) -> pd.DataFrame:
    """Person and household characteristics. Missing or not-stated categories get their own dummy."""
    X = pd.DataFrame(index=d.index)
    X["female"] = (d.census_sex == 2).astype(float)
    bands = pd.cut(d.census_age, [15, 19, 24, 29, 34, 39, 44, 49, 54, 59, 64, 200],
                   labels=["16-19", "20-24", "25-29", "30-34", "35-39", "40-44", "45-49", "50-54",
                           "55-59", "60-64", "65+"])
    X = X.join(pd.get_dummies(bands, prefix="age", prefix_sep=" ", dtype=float).drop(columns="age 30-34"))
    X["urban"] = (d.census_urban == 1).astype(float)
    X["household size"] = d.hh_size
    X["children under 15 in household"] = d.hh_children_u15
    X["people 65+ in household"] = d.hh_elderly_65p
    if year == 2012:
        X["never attended school"] = (d.census_school_attendance_2012 == 1).astype(float)
        X = X.join(dummies(d.census_education_level_2012, vl["census_education_level_2012"], "education",
                           drop=1, skip=(99,)))
        X = X.join(dummies(d.census_marital_status_2012, vl["census_marital_status_2012"], "marital",
                           drop=2))
        X = X.join(dummies(d.census_relation_head_2002_2012, vl["census_relation_head_2002_2012"],
                           "relation to head", drop=1))
        bp = d.census_birth_place_2012
        X["born abroad"] = (bp > 57).astype(float)
        X["born in another district"] = ((bp <= 57) & (bp != d.census_district)).astype(float)
        X["disability"] = (d.census_disability_any_2012 == 1).astype(float)
    else:
        X["never attended school"] = (d.census_school_attendance_2022 == 3).astype(float)
        X = X.join(dummies(d.census_education_level_2022, vl["census_education_level_2022"], "education",
                           drop=3))
        X["education: not stated"] = d.census_education_level_2022.isna().astype(float)
        X = X.join(dummies(d.census_marital_status_2022, vl["census_marital_status_2022"], "marital",
                           drop=1))
        X = X.join(dummies(d.census_relation_head_2022, vl["census_relation_head_2022"],
                           "relation to head", drop=1))
        X["born abroad"] = d.census_birth_country_2022.notna().astype(float)
        X["born in another district"] = (d.census_birth_district_2022.notna()
                                         & (d.census_birth_district_2022 != d.census_district)).astype(float)
        lit = d.census_literacy_languages_2022.map(vl["census_literacy_languages_2022"]).fillna("")
        X["reads and writes English"] = lit.str.contains("Engl|Engish", case=False).astype(float)
        X["reads and writes French"] = lit.str.contains("French", case=False).astype(float)
        X["reads and writes Swahili"] = lit.str.contains("Swahili|Swahii", case=False).astype(float)
        X["cannot read or write"] = (d.census_literacy_languages_2022 == 0).astype(float)
        diff = d[[c for c in d.columns if c.startswith("census_difficulty_")]]
        X["disability"] = (diff >= 2).any(axis=1).astype(float)
    return X.loc[:, X.std() > 0]


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
    Zs, _, sd = _standardise(Z.to_numpy(float), wt)
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
    est, n, G = fe_ols(df, "y", xs, [], "sector", B=B)
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
         f"post-lasso LPM with {B} bootstrap draws")
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
