"""Plot the corrected 5-km matched-DiD forest estimates.

The estimates are from the pooled Volcanoes, Nyungwe, and Akagera analysis.
Gishwati-Mukura park cells and the city-sector sample are excluded. Each
treated 1-km forest cell is matched to a control cell in the same district.
"""

from pathlib import Path
import textwrap

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


OUTPUT = Path(
    "/Users/matteo/Library/CloudStorage/Dropbox/1-Ongoing Projects/"
    "Rwanda - TRS/output/figures/coefplot_forest_5km.pdf"
)
CI_Z = 1.645

COMPARISONS = [
    "Park vs all non-park",
    "Park + 5 km vs beyond 5 km",
    "0-5 km ring vs beyond 5 km",
    "Park vs beyond 5 km",
]

RESULTS = pd.DataFrame(
    [
        ("Park vs all non-park", "Hansen", -0.211641, 0.123421, 0.086385, 1705, 21),
        ("Park vs all non-park", "JRC", 0.012647, 0.071673, 0.859933, 1424, 20),
        ("Park + 5 km vs beyond 5 km", "Hansen", 0.001910, 0.050976, 0.970118, 2914, 28),
        ("Park + 5 km vs beyond 5 km", "JRC", -0.556478, 0.176889, 0.001656, 1797, 24),
        ("0-5 km ring vs beyond 5 km", "Hansen", -0.029198, 0.038722, 0.450823, 1209, 24),
        ("0-5 km ring vs beyond 5 km", "JRC", -0.188177, 0.150965, 0.212583, 373, 20),
        ("Park vs beyond 5 km", "Hansen", -0.072178, 0.092849, 0.436942, 1705, 21),
        ("Park vs beyond 5 km", "JRC", -0.670540, 0.188357, 0.000371, 1424, 20),
    ],
    columns=["comparison", "dataset", "coefficient", "standard_error", "p_value", "pairs", "blocks"],
)


def note():
    return textwrap.fill(
        "Each point is the pooled post-2005 coefficient from a matched-pair difference-in-differences "
        "regression. The unit is a fixed 1-km grid cell; the outcome is hectares of annual forest loss. "
        "Each treated cell is matched with replacement to the closest eligible control cell in the same "
        "district using 2004 forest stock, elevation, slope, distance to primary or trunk roads, 2001 "
        "gridded population density, baseline precipitation, and the pre-treatment level and trend of forest loss. "
        "Regressions include pair fixed effects, annual rainfall, temperature and PDSI differences, and "
        "baseline-covariate-specific linear trends. Bars are 90% confidence intervals with two-way "
        "clustered standard errors based on the treated and matched-control 20-by-20-km spatial blocks. "
        "All comparisons pool Volcanoes, Nyungwe and Akagera; Gishwati-Mukura park cells and city sectors "
        "are excluded. Each product uses cells containing at least 10 hectares of its forest measure in 2004. "
        "Negative coefficients mean less forest loss in the first area. Both products cover 2001-2024. Sources: "
        "Hansen Global Forest Change 2024 v1.12 and JRC Tropical Moist Forest 2025.",
        width=184,
    )


def main():
    results = RESULTS.copy()
    results["lo90"] = results.coefficient - CI_Z * results.standard_error
    results["hi90"] = results.coefficient + CI_Z * results.standard_error

    fig, ax = plt.subplots(figsize=(10.4, 6.2))
    y = np.arange(len(COMPARISONS))[::-1]
    styles = {
        "Hansen": {"color": "#8C8C8C", "marker": "o", "offset": 0.12},
        "JRC": {"color": "#2E75A8", "marker": "D", "offset": -0.12},
    }

    for dataset, style in styles.items():
        subset = results[results.dataset == dataset].set_index("comparison").loc[COMPARISONS]
        ax.errorbar(
            subset.coefficient,
            y + style["offset"],
            xerr=[subset.coefficient - subset.lo90, subset.hi90 - subset.coefficient],
            fmt=style["marker"],
            ms=6,
            color=style["color"],
            ecolor=style["color"],
            elinewidth=1.5,
            capsize=3,
            label=dataset,
        )

    ax.axvline(0, color="#333333", lw=0.8)
    ax.set_yticks(y)
    ax.set_yticklabels(COMPARISONS, fontsize=9.5)
    ax.set_xlabel("effect on annual forest loss (hectares per 1-km cell)", fontsize=9.5)
    ax.set_title("Forest loss around national parks: 5-km comparisons", fontsize=11, pad=10)
    ax.grid(axis="x", lw=0.3, color="#DDDDDD")
    ax.set_axisbelow(True)
    ax.tick_params(axis="x", labelsize=9)
    ax.tick_params(axis="y", length=0)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.legend(frameon=False, fontsize=9, loc="lower right")

    fig.text(
        0.012,
        0.012,
        note(),
        fontsize=6.7,
        va="bottom",
        ha="left",
        color="#333333",
        linespacing=1.45,
    )
    fig.tight_layout(rect=[0.01, 0.22, 0.995, 0.99])
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT, bbox_inches="tight")
    plt.close(fig)
    print(f"Written: {OUTPUT}")


if __name__ == "__main__":
    main()
