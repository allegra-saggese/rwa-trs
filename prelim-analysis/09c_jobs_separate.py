"""Table 5 (population control) estimated as two separate regressions:
(a) near-gate vs clean control only, (b) bordering-only vs clean control only."""
src = open(__file__.replace("09c_jobs_separate.py", "09_section_b.py")).read()
exec(src[:src.index("T10 = fmt(")])
JOBS_P = {k: v for k, v in JOBS.items() if k not in ("ln_pop", "ntl_chen_asinh")}
out = []
for grp, xs, sub in [("near gate", ["NG_2012", "NG_2022"], S[S.BO == 0]), ("bordering only", ["BO_2012", "BO_2022"], S[S.NG == 0])]:
    for y, lab in JOBS_P.items():
        r, n, G = fe_ols(sub, y, xs + ["ln_pop"], ["sid", "pw"], "district_id")
        for x in xs: out.append(dict(regression=grp, outcome=lab, term=x, coef=r.loc[x, "coef"], se=r.loc[x, "se"], p=r.loc[x, "p_wcb"], N=n))
R = pd.DataFrame(out); R.to_csv(OUT_T / "T10s_B_jobs_separate_long.csv", index=False)
J = pd.read_csv(OUT_T / "T10p_B_jobs_popctrl_long.csv")[["outcome", "term", "coef", "p_wcb"]].rename(columns={"coef": "joint", "p_wcb": "p_joint"})
M = R.merge(J, on=["outcome", "term"])
print(M[["term", "outcome", "joint", "coef", "p_joint", "p", "N"]].round(3).to_string(index=False))
