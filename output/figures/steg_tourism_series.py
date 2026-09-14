"""
steg_tourism_series.py -- Rwanda's tourism boom from Rwanda Development Board figures, for the STEG appendix.

    python steg_tourism_series.py
    output/figures/steg_tourism_parks.pdf       national parks: visits (left), revenue change since 2008 (right)
    output/figures/steg_tourism_national.pdf    all tourism: visitor arrivals (left), revenue change since 2008 (right)

Every series is Rwanda Development Board data, as published in its annual reports and, for park visits
to 2023, in NISR's Statistical Yearbook 2024 (source: RDB). World Bank tourism series are not used.

Revenue is shown as the cumulative change since 2008, the first year both revenue series exist, in
constant 2024 US dollars (US GDP deflator; both series are quoted in current US dollars). Arrivals are
levels on the left axis.

National arrivals are drawn as points only. RDB publishes a total for 2017, 2019, 2020 and 2023-2025,
on definitions that drift (non-resident arrivals in 2017, visitors plus holiday-makers in 2019, visitors
including MICE delegates from 2023), and nothing for 2008-2016, 2018, 2021 or 2022. A line through
those points would invent the missing years.
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


def draw(left, left_label, left_fmt, right, fname, points_only):
    fig, ax = plt.subplots(figsize=(9.5, 4.8))
    ax2 = ax.twinx()
    if points_only:
        ax.plot(left.index, left.values, "o", color=C_LEFT, ms=7, label=left_label)
    else:
        ax.plot(left.index, left.values, "-o", color=C_LEFT, lw=2, ms=4, label=left_label)
    ax2.plot(right.index, right.values, "-s", color=C_RIGHT, lw=2, ms=4,
             label=f"Revenue, cumulative change since {BASE_YEAR} (right)")
    ax.set_ylabel(left_label.replace(" (left)", ""))
    ax.yaxis.set_major_formatter(FuncFormatter(left_fmt))
    ax.set_ylim(0, left.max() * 1.15)
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
    ta = pd.read_csv(SRC / "rdb_visitor_arrivals.csv").set_index("year").arrivals
    pchg, preal = cumulative_real(pr)
    tchg, treal = cumulative_real(tr)
    draw(pv / 1e3, "National park visits, thousands (left)", lambda v, _: f"{v:,.0f}", pchg,
         "steg_tourism_parks.pdf", points_only=False)
    draw(ta / 1e6, "International visitor arrivals, million (left)", lambda v, _: f"{v:.1f}", tchg,
         "steg_tourism_national.pdf", points_only=True)
    f = lambda s, y: float(s.get(y, float("nan")))
    print(f"parks: visits 2005 {f(pv,2005):,.0f} 2019 {f(pv,2019):,.0f} 2020 {f(pv,2020):,.0f} 2025 {f(pv,2025):,.0f} | "
          f"real revenue change since 2008: 2019 {f(pchg,2019):+.0f}% 2020 {f(pchg,2020):+.0f}% 2025 {f(pchg,2025):+.0f}%")
    print(f"national: arrivals 2019 {f(ta,2019):,.0f} 2020 {f(ta,2020):,.0f} 2025 {f(ta,2025):,.0f} | "
          f"real revenue change since 2008: 2019 {f(tchg,2019):+.0f}% 2020 {f(tchg,2020):+.0f}% 2025 {f(tchg,2025):+.0f}% | "
          f"real revenue 2008 {f(treal,2008):.0f} 2025 {f(treal,2025):.0f}")


if __name__ == "__main__":
    main()
