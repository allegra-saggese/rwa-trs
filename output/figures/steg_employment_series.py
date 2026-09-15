"""
steg_employment_series.py -- structural transformation and tourism jobs, 2001-2025, for the STEG appendix.

    python steg_employment_series.py
    output/figures/steg_employment_sectors.pdf    share of workers in agriculture (subsistence included) and in services
    output/figures/steg_employment_tourism.pdf    people employed in tourism-related services: accommodation & food
                                                  and arts & recreation (ISIC sections I, R), every year

Each person is counted once, by main job, so agriculture + services + industry = 100%; industry is the
remainder (2% in 2001, 12% in 2025). The x axis is broken (//) between survey years that are not consecutive.

Two surveys, never spliced in levels.
    EICV   2001, 2006, 2011, 2014 -- NISR household living conditions survey, main job of everyone who
           worked, own farm included by construction
    LFS    2017-2025 annual -- NISR labour force survey. Its headline "employment" follows the 2013 ILO
           standard and EXCLUDES subsistence farmers; they are added back here from NISR's own
           subsistence-producer flag, because leaving them out would describe a country where two
           thirds of workers do not exist. The flag is missing in 2019; that year uses NISR's own
           in-or-out-of-agriculture variable instead, which gives 61.1% against the 61.2% in the 2019
           LFS report.

The sectors figure is in shares because the two surveys count different people: EICV takes ages 6+ over
twelve months, LFS ages 16+ (14+ from 2020) over seven days, so headcounts jump at the join for reasons
that have nothing to do with the economy. The overlap years show the size of that difference (EICV 2017
and 2024 are printed for comparison, not plotted). The tourism figure is in people: tourism counts line up
across the two surveys (EICV 2024 159k, LFS 2024 163k), so the level is informative. It counts direct
main jobs only, so it sits well below WTTC's "jobs supported by travel & tourism" (386k in 2024), which
adds transport, retail and indirect and induced jobs.

EICV 2011 and 2017 are rebuilt from the raw job files because the harmonised EICV file carries no
industry code for either round. 2011: main job = the job with the most annual hours; industry from the
job module, or for independent non-farmers from the enterprise module; NISR's own industry groups mapped
to agriculture (11-14), services (61-93), tourism (64 hotels & restaurants, 92 recreation & tourism).
EICV 2011 has only NISR's industry groups and EICV 2014 and 2017 only ISIC sections, so the green bars
are sections I and R (NISR groups 64 and 92 in 2011) in every year, gambling (92) included. Travel
agencies (79), air (51) and water (50) transport and rental (77) are separable only in the LFS and add
4-10k a year, so they are left out.
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd, pyreadstat, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import paths as P

EICV = P.NISR / "Household-Living-Conditions-EICV"
LFS = P.NISR / "Labour-Force-Survey-LFS" / "4_Harmonized" / "H_LFS_person.dta"
TOUR = [9, 18]                          # ISIC sections I and R
num = lambda s: pd.to_numeric(s, errors="coerce")


def summarise(wt, agri, serv, tour, total=None):
    t = wt.sum() if total is None else total
    return dict(workforce_M=t / 1e6, agri_pct=wt[agri].sum() / t * 100, serv_pct=wt[serv].sum() / t * 100,
                tourism_k=wt[tour].sum() / 1e3)


def eicv_harmonised():
    d, _ = pyreadstat.read_dta(str(EICV / "4_Harmonized" / "H_EICV_person.dta"),
                               usecols=["eicv_year", "eicv_weight", "eicv_employed", "eicv_industry_isic",
                                        "eicv_industry_isic_approx"])
    d = d[num(d.eicv_employed) == 1].copy()
    d["isic"] = num(d.eicv_industry_isic).fillna(num(d.eicv_industry_isic_approx))
    d["wt"] = num(d.eicv_weight).fillna(0)
    out = {}
    for y, g in d.groupby("eicv_year"):
        g = g[g.isic.notna()]
        if len(g):
            out[int(y)] = summarise(g.wt, g.isic == 1, g.isic >= 7, g.isic.isin(TOUR))
    return out


def eicv_2011():
    raw = EICV / "1_Raw" / "EICV3"
    j, _ = pyreadstat.read_dta(str(next(raw.rglob("EICV3_s06cdef_jobs.dta"))))
    e, _ = pyreadstat.read_dta(str(next(raw.rglob("EICV3_s07_enterprise.dta"))), usecols=["HHID", "PID", "EID", "S7AQ4"])
    hours = lambda a, b, c: num(j[a]).fillna(0) * num(j[b]).fillna(0) * num(j[c]).fillna(0)
    j["hours"] = hours("S6CQ5A", "S6CQ5B", "S6CQ5C") + hours("S6CQ5D", "S6CQ5E", "S6CQ5F")
    j = j.merge(e.drop_duplicates(["HHID", "PID", "EID"]), on=["HHID", "PID", "EID"], how="left")
    j["grp"] = num(j.S6DQ3).fillna(num(j.S6EQ3)).fillna(num(j.S6FQ3)).fillna(num(j.S7AQ4))
    main = j.sort_values("hours", ascending=False).drop_duplicates(["HHID", "PID"])
    farm_status = num(main.S6CQ7).isin([1, 4, 5])                  # wage farm, independent farmer, unpaid farm
    agri = farm_status | main.grp.between(11, 14)
    serv = ~agri & main.grp.between(61, 93)
    tour = ~agri & main.grp.isin([64, 92])
    wt = num(main.HH_WT).fillna(0)
    s = summarise(wt, agri, serv, tour)
    s["unclassified_nonfarm_pct"] = wt[~agri & main.grp.isna()].sum() / wt.sum() * 100
    return s


def eicv_2017():
    f = next((EICV / "1_Raw" / "EICV5_CS").rglob("EICV5_CS_cs_s6b_employement*.dta"))
    d, _ = pyreadstat.read_dta(str(f), usecols=["hhid", "pid", "weight", "s6bq4b", "s6bq6"])
    m = d[d.s6bq6 == 1].drop_duplicates(["hhid", "pid"])
    i = num(m.s6bq4b)
    return summarise(num(m.weight).fillna(0), i == 1, i >= 7, i.isin(TOUR))


def lfs():
    cols = ["lfs_year", "lfs_weight", "lfs_labour_force_status", "lfs_subsistence_producer", "lfs_industry_isic",
            "lfs_agricultural_work_2019"]
    d, _ = pyreadstat.read_dta(str(LFS), usecols=cols)
    d["wt"] = num(d.lfs_weight).fillna(0)
    out = {}
    for y, g in d.groupby("lfs_year"):
        emp = g.lfs_labour_force_status == 1
        i = num(g.lfs_industry_isic)
        tour = emp & i.isin(TOUR)
        if y == 2019:
            a = g.lfs_agricultural_work_2019
            total = g.wt[a.notna()].sum(); agri = a == 2
        else:
            sub = g.lfs_subsistence_producer == 1
            total = g.wt[emp | sub].sum(); agri = (emp & (i == 1)) | (sub & ~emp)
        out[int(y)] = summarise(g.wt, agri, emp & (i >= 7), tour, total=total)
    return out


def broken_axis(ax, years):
    """evenly spaced survey years; where two years are not consecutive, a short gap and a // on the axis"""
    x = [0.0]
    for a, b in zip(years, years[1:]):
        x.append(x[-1] + (1 if b - a == 1 else 1.6))
    xt = ax.get_xaxis_transform()
    for k in range(1, len(years)):
        if years[k] - years[k - 1] > 1:
            m = (x[k] + x[k - 1]) / 2
            ax.plot([m - .13, m + .13], [0, 0], color="white", lw=4, transform=xt, clip_on=False, zorder=5)
            for dx in (-.06, .06):
                ax.plot([m + dx - .05, m + dx + .05], [-.03, .03], color="black", lw=.9, transform=xt,
                        clip_on=False, zorder=6)
    ax.set_xticks(x); ax.set_xticklabels(years, fontsize=9)
    ax.set_xlim(x[0] - .7, x[-1] + .7)
    return np.array(x)


def save(fig, ax, fname):
    ax.grid(axis="y", lw=.35, color="#DDD"); ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    fig.savefig(P.FIGS / fname, bbox_inches="tight"); plt.close(fig)
    print(f"written {P.FIGS / fname}")


def main():
    eh = eicv_harmonised()
    e11, e17 = eicv_2011(), eicv_2017()
    lf = lfs()
    eicv = {**{y: eh[y] for y in (2001, 2006, 2014) if y in eh}, 2011: e11}
    print("EICV (plotted):"); print(pd.DataFrame(eicv).T.sort_index().round(2).to_string())
    print("EICV overlap years (not plotted):", {2017: {k: round(v, 2) for k, v in e17.items()},
                                                 2024: {k: round(v, 2) for k, v in eh.get(2024, {}).items()}})
    print("LFS (plotted):"); print(pd.DataFrame(lf).T.round(2).to_string())

    years = sorted(eicv) + sorted(lf)
    rows = {**eicv, **lf}
    for y in years:
        assert rows[y]["agri_pct"] + rows[y]["serv_pct"] < 100, y

    fig, ax = plt.subplots(figsize=(9.5, 4.2))
    x = broken_axis(ax, years)
    w = .38
    ax.bar(x - w / 2, [rows[y]["agri_pct"] for y in years], w, color="#e9c46a", label="Agriculture, subsistence included")
    ax.bar(x + w / 2, [rows[y]["serv_pct"] for y in years], w, color="#1b4965", label="Services")
    ax.set_ylabel("% of workers"); ax.set_ylim(0, 100)
    ax.legend(loc="upper right", frameon=False, fontsize=9)
    save(fig, ax, "steg_employment_sectors.pdf")

    fig, ax = plt.subplots(figsize=(9.5, 4.2))
    x = broken_axis(ax, years)
    ax.bar(x, [rows[y]["tourism_k"] for y in years], .7, color="#2a9d8f")
    ax.set_ylabel("People employed, thousands")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))
    save(fig, ax, "steg_employment_tourism.pdf")


if __name__ == "__main__":
    main()
