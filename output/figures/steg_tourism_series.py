"""
steg_tourism_series.py -- Rwanda's tourism boom in three national series, for the STEG grant appendix.

    python steg_tourism_series.py
    output/figures/steg_tourism_series.pdf

    international arrivals ....... World Bank WDI ST.INT.ARVL, 2006-2019
    tourism receipts ............. World Bank WDI ST.INT.RCPT.CD, 1995-2020
    national park revenue ........ Rwanda Development Board annual reports, 2008-2024

Both money series are converted to constant 2024 US dollars with the US GDP deflator (WDI
NY.GDP.DEFL.ZS). The sources report current dollars and neither is deflated upstream. The US deflator
is the right one because both series are quoted in US dollars; Rwanda's CPI would deflate a local
currency amount.

Receipts run about twenty times park revenue, so on a linear axis park revenue would sit flat along
the bottom. The money axis is therefore logarithmic: equal vertical distances are equal growth rates,
and both series stay readable. Arrivals sit on their own linear axis on the right.

Receipts and park revenue are not the same concept, and neither is a subset of the other. Receipts
are balance-of-payments spending by all international visitors, business and regional travellers
included. Park revenue is RDB's income from national park permits and fees. The gaps are left as
gaps: WDI has no receipts for 2002-2004 and nothing after 2020, and arrivals stop in 2019.
"""
import sys
from pathlib import Path
import pandas as pd, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, FixedLocator
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import paths as P

SRC = P.DATA / "Tourism Data"
BASE = 2024


def load():
    w = pd.read_csv(SRC / "world_bank_wdi.csv")
    series = lambda c, code: w[(w.country == c) & (w.indicator_code == code)].set_index("year").value
    defl = series("USA", "NY.GDP.DEFL.ZS")
    real = lambda s: s * defl[BASE] / defl.reindex(s.index)
    park = pd.read_csv(SRC / "park_revenue_usd_million.csv").set_index("year").park_revenue_usd_million_nominal
    return (series("RWA", "ST.INT.ARVL") / 1e6,
            real(series("RWA", "ST.INT.RCPT.CD")) / 1e6,
            real(park * 1e6) / 1e6)


def main():
    arrivals, receipts, parks = load()
    full = lambda s: s.reindex(range(int(s.index.min()), int(s.index.max()) + 1))   # gaps stay gaps
    fig, ax = plt.subplots(figsize=(9.5, 5.0))
    ax2 = ax.twinx()
    C_REC, C_PARK, C_ARR = "#1b4965", "#2a9d8f", "#c1121f"
    ax.plot(full(receipts).index, full(receipts).values, "-o", color=C_REC, lw=2.0, ms=4,
            label="International tourism receipts (left)")
    ax.plot(full(parks).index, full(parks).values, "-s", color=C_PARK, lw=2.0, ms=4,
            label="National park revenue (left)")
    ax2.plot(full(arrivals).index, full(arrivals).values, "--^", color=C_ARR, lw=1.8, ms=4,
             label="International arrivals (right)")
    ax.set_yscale("log")
    ticks = [5, 10, 20, 50, 100, 200, 500, 1000]
    ax.yaxis.set_major_locator(FixedLocator(ticks)); ax.yaxis.set_minor_locator(FixedLocator([]))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.set_ylim(4, 1100)
    ax.set_ylabel(f"US$ million, constant {BASE} prices (log scale)")
    ax2.set_ylabel("International arrivals, million")
    ax2.set_ylim(0, 2.0)
    ax.set_xlim(1994, 2025); ax.set_xticks(range(1995, 2026, 5))
    ax.grid(axis="y", lw=.35, color="#DDD"); ax.set_axisbelow(True)
    for a in (ax, ax2):
        a.spines["top"].set_visible(False)
    h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper left", frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(P.FIGS / "steg_tourism_series.pdf", bbox_inches="tight")
    plt.close(fig)
    print(f"written {P.FIGS / 'steg_tourism_series.pdf'}")
    # numbers the caption and note quote
    r = lambda s, y: float(s.get(y, float("nan")))
    print(f"receipts, constant {BASE} US$ M: 1995 {r(receipts,1995):.0f}  2005 {r(receipts,2005):.0f}  "
          f"2019 {r(receipts,2019):.0f}  2020 {r(receipts,2020):.0f}")
    print(f"park revenue, constant {BASE} US$ M: 2008 {r(parks,2008):.1f}  2019 {r(parks,2019):.1f}  "
          f"2020 {r(parks,2020):.1f}  2024 {r(parks,2024):.1f}")
    print(f"arrivals M: 2006 {r(arrivals,2006):.2f}  2019 {r(arrivals,2019):.2f}")
    print(f"park revenue / receipts, 2019: {r(parks,2019)/r(receipts,2019)*100:.1f}%")


if __name__ == "__main__":
    main()
