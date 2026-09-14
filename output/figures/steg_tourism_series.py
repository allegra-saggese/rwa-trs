"""
steg_tourism_series.py -- Rwanda's tourism boom from Rwanda Development Board figures, for the STEG appendix.

    python steg_tourism_series.py
    output/figures/steg_tourism_parks.pdf       national parks: visits (left), revenue in constant 2024 US$ (right)
    output/figures/steg_tourism_national.pdf    all tourism: international arrivals (left), revenue in constant 2024 US$ (right)

Revenue and park figures are Rwanda Development Board data, from its annual reports and, for park visits
to 2023, NISR's Statistical Yearbook 2024 (source: RDB). International arrivals are NISR's "tourist
arrivals" for 2013-2017 (Statistical Yearbook 2019, source RDB and Immigration) and RDB's published totals
for 2019, 2020 and 2023-2025. World Bank tourism series are not used.

Both revenue series are put in constant 2024 US dollars with the US GDP deflator, since RDB quotes them
in current dollars. Both are shown in levels, with visits and arrivals as levels on the left axis.

No arrivals total is published for 2018, 2021 or 2022, so the arrivals line is broken there rather than
drawn through the missing years. Immigration's broader "visitor arrivals" (2.6 million in 2018-2019) are
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
BASE_PRICE, BASE_YEAR = 2024, 2008
C_LEFT, C_RIGHT = "#2a9d8f", "#1b4965"


def cumulative_real(nominal):
    w = pd.read_csv(SRC / "world_bank_wdi.csv")
    defl = w[(w.country == "USA") & (w.indicator_code == "NY.GDP.DEFL.ZS")].set_index("year").value
    real = nominal * defl[BASE_PRICE] / defl.reindex(nominal.index)
    return (real / real[BASE_YEAR] - 1) * 100, real


def draw(left, left_label, left_fmt, right, fname, points_only, right_mode="change"):
    fig, ax = plt.subplots(figsize=(9.5, 4.8))
    ax2 = ax.twinx()
    left = left.reindex(range(int(left.index.min()), int(left.index.max()) + 1))   # gaps stay gaps
    ax.plot(left.index, left.values, "-o", color=C_LEFT, lw=2, ms=4, label=left_label)
    right_legend = (f"Revenue, US$ million, constant {BASE_PRICE} prices (right)" if right_mode == "level"
                    else f"Revenue, cumulative change since {BASE_YEAR} (right)")
    ax2.plot(right.index, right.values, "-s", color=C_RIGHT, lw=2, ms=4, label=right_legend)
    ax.set_ylabel(left_label.replace(" (left)", ""))
    ax.yaxis.set_major_formatter(FuncFormatter(left_fmt))
    ax.set_ylim(0, left.max() * 1.15)
    if right_mode == "level":
        ax2.set_ylabel(f"US$ million, constant {BASE_PRICE} prices")
        ax2.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))
        ax2.set_ylim(0, right.max() * 1.15)
    else:
        ax2.set_ylabel(f"% change since {BASE_YEAR}, constant {BASE_PRICE} US$")
        ax2.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:+,.0f}%"))
        lo = min(right.min(), 0); ax2.set_ylim(lo - 20, right.max() * 1.15)
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
    pchg, preal = cumulative_real(pr)
    tchg, treal = cumulative_real(tr)
    draw(pv / 1e6, "National park visits, million (left)", lambda v, _: f"{v:.2f}", preal / 1e0,
         "steg_tourism_parks.pdf", points_only=False, right_mode="level")
    draw(ta / 1e6, "International arrivals, million (left)", lambda v, _: f"{v:.2f}", treal,
         "steg_tourism_national.pdf", points_only=False, right_mode="level")
    f = lambda s, y: float(s.get(y, float("nan")))
    print(f"parks: visits 2005 {f(pv,2005):,.0f} 2019 {f(pv,2019):,.0f} 2020 {f(pv,2020):,.0f} 2025 {f(pv,2025):,.0f} | "
          f"real revenue US$M: 2008 {f(preal,2008):.1f} 2019 {f(preal,2019):.1f} 2020 {f(preal,2020):.1f} 2025 {f(preal,2025):.1f}")
    print(f"national: arrivals 2019 {f(ta,2019):,.0f} 2020 {f(ta,2020):,.0f} 2025 {f(ta,2025):,.0f} | "
          f"real revenue US$M: 2008 {f(treal,2008):.0f} 2019 {f(treal,2019):.0f} 2020 {f(treal,2020):.0f} 2025 {f(treal,2025):.0f} | "
          f"arrivals 2013 {f(ta,2013):,.0f} 2017 {f(ta,2017):,.0f}")


if __name__ == "__main__":
    main()
