"""Table 5 variant: drop night lights, control for ln total population (time-varying, sector FE and province x wave FE).
Reuses the data set-up of 09_section_b.py (everything before the T10 line)."""
src = open(__file__.replace("09b_jobs_popctrl.py", "09_section_b.py")).read()
exec(src[:src.index("T10 = fmt(")])
JOBS_P = {k: v for k, v in JOBS.items() if k not in ("ln_pop", "ntl_chen_asinh")}
R = table(JOBS_P, ["sid", "pw"], extra=["ln_pop"])
# population coefficient for each outcome
rows = []
for y, lab in JOBS_P.items():
    r, n, G = fe_ols(S, y, TX + ["ln_pop"], ["sid", "pw"], "district_id")
    rows.append(dict(outcome=lab, coef=r.loc["ln_pop", "coef"], se=r.loc["ln_pop", "se"], p_wcb=r.loc["ln_pop", "p_wcb"]))
P = pd.DataFrame(rows)
R.to_csv(OUT_T / "T10p_B_jobs_popctrl_long.csv", index=False); P.to_csv(OUT_T / "T10p_B_jobs_popctrl_popcoef.csv", index=False)
print(R.pivot(index="term", columns="outcome", values="coef").round(3).to_string())
print(R.pivot(index="term", columns="outcome", values="p_wcb").round(3).to_string())
print(P.round(3).to_string(index=False))
