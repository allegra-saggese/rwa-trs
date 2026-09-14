"""
steg_tourism_series.py -- Rwanda's tourism boom from Rwanda Development Board figures, for the STEG appendix.

    python steg_tourism_series.py
    output/figures/steg_tourism_parks.pdf       national parks: visits (left), direct revenue collection (entry tickets) in constant 2024 US$ (right)
    output/figures/steg_tourism_national.pdf    all tourism: international arrivals (left), revenue in constant 2024 US$ (right)

Revenue and park figures are Rwanda Development Board data, from its annual reports and, for park visits
to 2023, NISR's Statistical Yearbook 2024 (source: RDB). International arrivals are NISR's "tourist
arrivals" for 2013-2017 (Statistical Yearbook 2019, source RDB and Immigration) and RDB's published totals
for 2019, 2020 and 2023-2025. World Bank tourism series are not used.

Both revenue series are put in constant 2024 US dollars with the US GDP deflator, since RDB quotes them
in current dollars. Both are shown in levels, with visits and arrivals as levels on the left axis.

No arrivals total is published for 2018, 2021 or 2022; a dashed segment joins the published years on
either side, so the missing years are visibly not data. Immigration's broader "visitor arrivals" (2.6 million in 2018-2019) are
not used: they add cross-border transit, mostly from the DRC, and would put a false jump into the line.
"""
import sys
from pathlib import Path
import pandas as pd, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import paths as P

SRC = P.DATA / "Tourism Data"
BASE_PRICE = 2024
C_LEFT, C_RIGHT = "#2a9d8f", "#1b4965"


def to_real(nominal):
    """current US$ million -> constant BASE_PRICE US$ million, with the US GDP deflator"""
    w = pd.read_csv(SRC / "world_bank_wdi.csv")
    defl = w[(w.country == "USA") & (w.indicator_code == "NY.GDP.DEFL.ZS")].set_index("year").value
    return nominal * defl[BASE_PRICE] / defl.reindex(nominal.index)


def line(ax, s, color, marker, label):
    """solid through consecutive years; a dashed segment bridges any year with no published figure"""
    s = s.dropna().sort_index()
    full = s.reindex(range(int(s.index.min()), int(s.index.max()) + 1))
    ax.plot(full.index, full.values, "-" + marker, color=color, lw=2, ms=4, label=label)
    yrs = list(s.index)
    for a, b in zip(yrs, yrs[1:]):
        if b - a > 1:
            ax.plot([a, b], [s[a], s[b]], "--", color=color, lw=1.4)


def draw(left, left_label, left_fmt, right, right_label, fname):
    fig, ax = plt.subplots(figsize=(9.5, 4.8))
    ax2 = ax.twinx()
    line(ax, left, C_LEFT, "o", left_label)
    line(ax2, right, C_RIGHT, "s", f"{right_label}, million constant {BASE_PRICE} US$ (right)")
    ax.set_ylabel(left_label.replace(" (left)", ""))
    ax.yaxis.set_major_formatter(FuncFormatter(left_fmt))
    ax.set_ylim(0, left.max() * 1.15)
    ax2.set_ylabel(f"{right_label},\nmillion constant {BASE_PRICE} US$")
    ax2.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax2.set_ylim(0, right.max() * 1.15)
    first = int(min(left.index.min(), right.index.min()))
    ax.set_xticks(range(first, 2026, 2 if 2025 - first > 12 else 1))
    ax.set_xlim(first - 0.6, 2025.6)
    ax.grid(axis="y", lw=.35, color="#DDD"); ax.set_axisbelow(True)
    for a in (ax, ax2): a.spines["top"].set_visible(False)
    h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper left", frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(P.FIGS / fname, bbox_inches="tight"); plt.close(fig)
    print(f"written {P.FIGS / fname}")


def main():
    pr = pd.read_csv(SRC / "park_revenue_usd_million.csv").set_index("year").park_revenue_usd_million_nominal
    pv = pd.read_csv(SRC / "park_visitors_by_park.csv").set_index("year").total
    tr = pd.read_csv(SRC / "rdb_tourism_revenue_usd_million.csv").set_index("year").tourism_revenue_usd_million_nominal
    nisr = pd.read_csv(SRC / "arrivals_by_purpose_nisr.csv")
    nisr = nisr[nisr.series == "tourist arrivals"].set_index("year").total
    rdb = pd.read_csv(SRC / "rdb_visitor_arrivals.csv").set_index("year").arrivals
    ta = pd.concat([nisr, rdb[rdb.index > nisr.index.max()]]).sort_index()
    preal = to_real(pr)
    treal = to_real(tr)
    draw(pv / 1e3, "National park visits, thousands (left)", lambda v, _: f"{v:,.0f}", preal,
         "National park direct revenue collection", "steg_tourism_parks.pdf")
    draw(ta / 1e6, "International arrivals, million (left)", lambda v, _: f"{v:.2f}", treal,
         "Spending by international visitors", "steg_tourism_national.pdf")
    f = lambda s, y: float(s.get(y, float("nan")))
    print(f"parks: visits 2005 {f(pv,2005):,.0f} 2019 {f(pv,2019):,.0f} 2020 {f(pv,2020):,.0f} 2025 {f(pv,2025):,.0f} | "
          f"real revenue US$M: 2008 {f(preal,2008):.1f} 2019 {f(preal,2019):.1f} 2020 {f(preal,2020):.1f} 2025 {f(preal,2025):.1f}")
    print(f"national: arrivals 2019 {f(ta,2019):,.0f} 2020 {f(ta,2020):,.0f} 2025 {f(ta,2025):,.0f} | "
          f"real revenue US$M: 2008 {f(treal,2008):.0f} 2019 {f(treal,2019):.0f} 2020 {f(treal,2020):.0f} 2025 {f(treal,2025):.0f} | "
          f"arrivals 2013 {f(ta,2013):,.0f} 2017 {f(ta,2017):,.0f}")


if __name__ == "__main__":
    main()
