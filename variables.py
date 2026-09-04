"""
variables.py — EICV7 variable codebook, organised by research workstream.

A single declarative place where analysis names map to EICV7 variable codes, so
cleaning code never carries bare `s6bq3` literals and a reviewer can audit the
selection without opening a .dta file.

Every code here is verified to exist in EICV7_2023-24_variable_dictionary.csv.
Re-verify after any edit:

    python variables.py --check           # confirm every code exists
    python variables.py --list labour     # print one workstream
    python variables.py --list all        # print everything
    python variables.py --export          # write docs/variable_lists.md

Structure
---------
Each entry maps an analysis name to (file_unit, eicv7_code). `file_unit` uses
the short names from `extract.EICV7_FILES`, so `("person", "s6bq3")` means
variable s6bq3 in F2.

Cross-round warning
-------------------
These codes are EICV7-specific. Section letters shifted between rounds — access
to services moved s5e -> s5f, person employment/time-use moved s6e/s6f -> s6b/s6c.
Matching earlier rounds on code will silently mismatch; match on question
content instead. See docs/cleaning_decisions.md.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DICTIONARY = ROOT / "EICV7_2023-24_variable_dictionary.csv"


# --------------------------------------------------------------------------
# Identifiers and weights — needed by every workstream
# --------------------------------------------------------------------------

IDENTIFIERS = {
    "hhid": "Household identification",
    "clust": "Cluster (PSU)",
    "strata_id": "Stratum",
    "province": "Province",
    "district": "District",
    "ur": "Urban/rural",
}

# pid appears in the person file and in every VUP component file.
PERSON_ID = {"pid": "Household member id"}

WEIGHTS = {
    "weight": "Household weight — use for household-level statistics",
    "pop_wt": "Population weight — use for person-level statistics (F1, F3 only)",
}


# --------------------------------------------------------------------------
# Workstreams
# --------------------------------------------------------------------------

WORKSTREAMS: dict[str, dict] = {

    # ---------------------------------------------------------------- labour
    "labour": {
        "title": "Tourism jobs and labour",
        "unit": "person",
        "note": (
            "Household-side match to the RDB administrative labour data. EICV7 "
            "records a MAIN JOB ONLY — secondary jobs were dropped this round, so "
            "multiple-job structure is not recoverable. For a consistent labour "
            "series over time the Labour Force Survey (2017-) is the better "
            "instrument than the EICV employment module."
        ),
        "variables": {
            # Activity status, last 7 days (s6aq2-s6aq12)
            "worked_own_farm_unpaid":      ("person", "s6aq2"),
            "farm_products_obtained":      ("person", "s6aq3"),
            "any_agricultural_activity":   ("person", "s6aq4"),
            "worked_wage_nonfarm":         ("person", "s6aq5"),
            "ran_nonfarm_business":        ("person", "s6aq6"),
            "worked_in_nonfarm_business":  ("person", "s6aq7"),
            "worked_unpaid_trainee":       ("person", "s6aq8"),
            "temporarily_absent_activity": ("person", "s6aq9"),
            "reason_not_working":          ("person", "s6aq10"),
            "income_during_absence":       ("person", "s6aq11"),
            "absence_under_3_months":      ("person", "s6aq12"),

            # Main job characteristics (s6bq*)
            "hours_usual_per_week":        ("person", "s6bq1"),
            "hours_actual_last_7d":        ("person", "s6bq2"),
            "occupation_isco1":            ("person", "s6bq3"),
            "industry_isic1":              ("person", "s6bq4"),
            "institutional_sector":        ("person", "s6bq5"),
            "works_overnight":             ("person", "s6bq6"),
            "employment_status":           ("person", "s6bq7"),
            "contract_type":               ("person", "s6bq8"),
            "earnings_main_job_amount":    ("person", "s6bq9a"),
            "earnings_main_job_unit":      ("person", "s6bq9b"),

            # Demographics needed for any labour analysis
            "sex":                         ("person", "s1q1"),
            "age_years":                   ("person", "s1q3y"),
        },
    },

    # ------------------------------------------------------------ livelihood
    "livelihood": {
        "title": "Livelihood-program measurement",
        "unit": "household (VUP blocks are household x member)",
        "note": (
            "Welfare aggregates are on EICV7's REVISED methodology and a January "
            "2024 price base. NISR explicitly cautions against comparing EICV7 "
            "poverty to earlier rounds. F13-F17 already carry quintile, poverty, "
            "pov_jan and epov_jan, so no F1 merge is needed for those four."
        ),
        "variables": {
            # Constructed welfare (F1)
            "consumption_total":           ("poverty", "cons1"),
            "consumption_per_ae":          ("poverty", "cons1ae"),
            "consumption_per_ae_jan2024":  ("poverty", "sol_jan"),
            "consumption_quintile":        ("poverty", "quintile"),
            "welfare_category":            ("poverty", "poverty"),
            "poor":                        ("poverty", "pov_jan"),
            "extreme_poor":                ("poverty", "epov_jan"),
            "poverty_line_jan2024":        ("poverty", "Poverty_line"),
            "food_poverty_line_jan2024":   ("poverty", "Extreme_line"),
            "hh_size":                     ("poverty", "member"),
            "hh_size_adult_equiv":         ("poverty", "ae"),
            "food_expenditure_total":      ("poverty", "food"),

            # Livestock buffer stock (F3)
            "owns_livestock":              ("household", "s7aq4"),
            "n_cattle":                    ("household", "s7aq4a"),
            "n_goats":                     ("household", "s7aq4b"),
            "n_sheep":                     ("household", "s7aq4c"),
            "n_pigs":                      ("household", "s7aq4d"),
            "n_poultry":                   ("household", "s7aq4e"),
            "n_other_livestock":           ("household", "s7aq4f"),

            # Girinka one-cow-per-poor-family (F3)
            "girinka_received_cow":        ("household", "s7a2q1"),
            "girinka_year_received":       ("household", "s7a2q2"),
            "girinka_still_keeps":         ("household", "s7a2q3"),
            "ngo_animal_received":         ("household", "s7a2q4"),
            "ngo_animal_kind_1":           ("household", "s7a2q5a"),
            "girinka_n_animals_changed":   ("household", "s7a2q6a"),
            "uses_maintained_pasture":     ("household", "s7a2q7"),

            # Shocks and coping (F3)
            "any_shock_12m":               ("household", "s5eq1"),
            "shock_1":                     ("household", "s5eq2a"),
            "shock_1_month":               ("household", "s5eq2aa_m"),
            "shock_1_year":                ("household", "s5eq2aa_y"),
            "shock_2":                     ("household", "s5eq2b"),
            "shock_3":                     ("household", "s5eq2c"),
            "coping_1":                    ("household", "s5eq3a"),
            "coping_2":                    ("household", "s5eq3b"),
            "coping_3":                    ("household", "s5eq3c"),
            "months_to_recover_1":         ("household", "s5eq4a"),
            "months_to_recover_2":         ("household", "s5eq4b"),
            "months_to_recover_3":         ("household", "s5eq4c"),

            # VUP participation — s9d1q1 is the universal flag, present in ALL
            # five component files.
            "vup_any_component":           ("vup_direct_support", "s9d1q1"),

            "vup_ds_beneficiary":          ("vup_direct_support", "s9d1q2"),
            "vup_ds_join_year":            ("vup_direct_support", "s9d1q2y"),
            "vup_ds_amount_12m":           ("vup_direct_support", "s9d1q4"),
            "vup_ds_payment_mode":         ("vup_direct_support", "s9d1q5"),
            "vup_ds_full_entitlement":     ("vup_direct_support", "s9d1q7"),

            "vup_cpw_beneficiary":         ("vup_classic_public_work", "s9d2q1"),
            "vup_cpw_join_year":           ("vup_classic_public_work", "s9d2q2y"),
            "vup_cpw_months_12m":          ("vup_classic_public_work", "s9d2q3"),
            "vup_cpw_daily_wage":          ("vup_classic_public_work", "s9d2q4"),
            "vup_cpw_total_12m":           ("vup_classic_public_work", "s9d2q11"),

            "vup_epw_beneficiary":         ("vup_expanded_public_work", "s9d3q1"),
            "vup_epw_component":           ("vup_expanded_public_work", "s9d3q2"),
            "vup_epw_join_year":           ("vup_expanded_public_work", "s9d3q2y"),
            "vup_epw_months_12m":          ("vup_expanded_public_work", "s9d3q3"),
            "vup_epw_total_12m":           ("vup_expanded_public_work", "s9d3q10"),
            "vup_epw_monthly_wage":        ("vup_expanded_public_work", "s9d3q11"),

            "vup_nsds_beneficiary":        ("vup_nsds", "s9d4q1"),
            "vup_nsds_join_year":          ("vup_nsds", "s9d4q1aa_y"),
            "vup_nsds_status":             ("vup_nsds", "s9d4q2"),
            "vup_nsds_quarters_received":  ("vup_nsds", "s9d4q7"),

            "vup_fs_applied":              ("vup_financial_services", "s9d5q1"),
            "vup_fs_approved":             ("vup_financial_services", "s9d5q2"),
            "vup_fs_join_year":            ("vup_financial_services", "s9d5q2y"),
            "vup_fs_loan_amount":          ("vup_financial_services", "s9d5q4"),
            "vup_fs_loan_type":            ("vup_financial_services", "s9d5q5"),
        },
    },

    # ---------------------------------------------------------- conservation
    "conservation": {
        "title": "Conservation and forest-pressure proxies",
        "unit": "household, plus person-level foraging",
        "note": (
            "s6cq3/s6cq4 are direct elicitation of firewood foraging at the "
            "person level — a cleaner measure than most surveys carry, and the "
            "closest household-side proxy for forest pressure. Note these are "
            "person-level, so aggregating to household requires summing hours "
            "across members before applying the household weight."
        ),
        "variables": {
            # Cooking energy (F3) — the main forest-pressure driver
            "cook_stove_type":             ("household", "s5cq21"),
            "cook_fuel_primary":           ("household", "s5cq22a"),
            "cook_fuel_second":            ("household", "s5cq22b"),
            "cook_fuel_third":             ("household", "s5cq22c"),
            "cook_location":               ("household", "s5cq23"),

            # Firewood foraging (F2, person level)
            "foraged_firewood_7d":         ("person", "s6cq3"),
            "hours_foraging_wood_7d":      ("person", "s6cq4"),

            # Other time-use competing for the same labour
            "hours_fetching_water_7d":     ("person", "s6cq2"),
            "hours_fodder_7d":             ("person", "s6cq6"),
            "hours_to_market_7d":          ("person", "s6cq8"),
            "hours_cooking_7d":            ("person", "s6cq10"),

            # Environmental exposure and information (F3)
            "env_destruction_problems":    ("household", "s5cq31"),
            "main_dwelling_disaster":      ("household", "s5cq32"),
            "received_env_information":    ("household", "s5cq33"),
            "env_information_source":      ("household", "s5cq34"),

            # Electricity access — the substitution margin away from biomass
            "grid_connected":              ("household", "s5cq14"),
            "reason_not_grid":             ("household", "s5cq15"),
            "lighting_energy_source":      ("household", "s5cq16"),

            # Waste and sanitation, secondary environmental pressure
            "rubbish_disposal":            ("household", "s5cq24"),
            "toilet_type":                 ("household", "s5cq25"),
        },
    },
}


# --------------------------------------------------------------------------
# Access helpers
# --------------------------------------------------------------------------

def codes_for(workstream: str, unit: str | None = None) -> list[str]:
    """EICV7 codes for a workstream, optionally filtered to one file unit."""
    if workstream not in WORKSTREAMS:
        raise KeyError(f"unknown workstream {workstream!r}; have {list(WORKSTREAMS)}")
    items = WORKSTREAMS[workstream]["variables"].items()
    return [code for _, (u, code) in items if unit is None or u == unit]


def rename_map(workstream: str, unit: str | None = None) -> dict[str, str]:
    """{eicv7_code: analysis_name} for use with DataFrame.rename(columns=...)."""
    items = WORKSTREAMS[workstream]["variables"].items()
    return {code: name for name, (u, code) in items if unit is None or u == unit}


def units_used(workstream: str) -> list[str]:
    """Which EICV7 file units a workstream draws on."""
    return sorted({u for u, _ in WORKSTREAMS[workstream]["variables"].values()})


# --------------------------------------------------------------------------
# Verification
# --------------------------------------------------------------------------

def check() -> int:
    """Confirm every code exists in the dictionary, in the file it claims.

    Returns the number of problems found; 0 means the codebook is clean.
    """
    import pandas as pd

    if not DICTIONARY.exists():
        print(f"! dictionary not found at {DICTIONARY}")
        return 1

    try:
        from extract import EICV7_FILES
    except ImportError:
        print("! could not import EICV7_FILES from extract.py")
        return 1

    d = pd.read_csv(DICTIONARY)
    d["fnum"] = d["data_file"].str.split().str[0]
    unit_by_fnum = {f: u for f, u in EICV7_FILES.items()}
    d["unit"] = d["fnum"].map(unit_by_fnum)

    # Case-insensitive lookup: the dictionary mixes cases (Poverty_line).
    by_code: dict[str, set[str]] = {}
    for r in d.itertuples():
        by_code.setdefault(str(r.variable).lower(), set()).add(r.unit)

    problems = 0
    for ws, spec in WORKSTREAMS.items():
        bad = []
        for name, (unit, code) in spec["variables"].items():
            units = by_code.get(code.lower())
            if units is None:
                bad.append(f"    MISSING   {name:30s} {code:14s} (not in dictionary)")
            elif unit not in units:
                bad.append(f"    WRONG FILE{name:30s} {code:14s} "
                           f"declared {unit!r}, dictionary says {sorted(units)}")
        n = len(spec["variables"])
        if bad:
            problems += len(bad)
            print(f"  {ws}: {n - len(bad)}/{n} OK")
            print("\n".join(bad))
        else:
            print(f"  {ws}: {n}/{n} OK")

    # Identifiers and weights
    for label, group in [("identifiers", IDENTIFIERS), ("person id", PERSON_ID),
                         ("weights", WEIGHTS)]:
        missing = [c for c in group if c.lower() not in by_code]
        if missing:
            problems += len(missing)
            print(f"  {label}: MISSING {missing}")
        else:
            print(f"  {label}: {len(group)}/{len(group)} OK")

    print(f"\n{'no problems' if problems == 0 else f'{problems} problem(s)'}")
    return problems


# --------------------------------------------------------------------------
# Printing and export
# --------------------------------------------------------------------------

def _labels() -> dict[str, str]:
    import pandas as pd
    if not DICTIONARY.exists():
        return {}
    d = pd.read_csv(DICTIONARY)
    return {str(r.variable).lower(): str(r.label) for r in d.itertuples()}


def show(which: str = "all") -> None:
    labels = _labels()
    names = list(WORKSTREAMS) if which == "all" else [which]
    for ws in names:
        spec = WORKSTREAMS[ws]
        print(f"\n{'=' * 78}\n{spec['title']}  [{ws}]")
        print(f"unit: {spec['unit']}\nfiles: {', '.join(units_used(ws))}")
        print(f"\n{spec['note']}\n")
        for name, (unit, code) in spec["variables"].items():
            lab = labels.get(code.lower(), "")[:44]
            print(f"  {name:30s} {code:14s} {unit:26s} {lab}")
        print(f"\n  ({len(spec['variables'])} variables)")


def export_markdown(dest: Path | None = None) -> Path:
    """Write the codebook to docs/variable_lists.md."""
    labels = _labels()
    dest = dest or (ROOT / "docs" / "variable_lists.md")
    dest.parent.mkdir(parents=True, exist_ok=True)

    out = ["# EICV7 variable lists by workstream", "",
           "Generated by `python variables.py --export`. Edit `variables.py`, not this file.",
           "",
           "All codes verified against `EICV7_2023-24_variable_dictionary.csv`",
           "(`python variables.py --check`).", "",
           "## Identifiers, present in every file", "",
           "| Variable | Meaning |", "|---|---|"]
    out += [f"| `{k}` | {v} |" for k, v in {**IDENTIFIERS, **PERSON_ID, **WEIGHTS}.items()]

    for ws, spec in WORKSTREAMS.items():
        out += ["", f"## {spec['title']}", "",
                f"**Unit:** {spec['unit']}  ",
                f"**Files:** {', '.join(units_used(ws))}  ",
                f"**Variables:** {len(spec['variables'])}", "",
                f"> {spec['note']}", "",
                "| Analysis name | EICV7 code | File | Dictionary label |",
                "|---|---|---|---|"]
        for name, (unit, code) in spec["variables"].items():
            out.append(f"| `{name}` | `{code}` | {unit} | {labels.get(code.lower(), '')} |")

    dest.write_text("\n".join(out) + "\n")
    return dest


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--check", action="store_true", help="verify codes against the dictionary")
    p.add_argument("--list", dest="which", nargs="?", const="all",
                   choices=["all", *WORKSTREAMS], help="print a workstream")
    p.add_argument("--export", action="store_true", help="write docs/variable_lists.md")
    args = p.parse_args(argv)

    if not (args.check or args.which or args.export):
        p.print_help()
        return 1
    if args.check:
        return 1 if check() else 0
    if args.which:
        show(args.which)
    if args.export:
        print(f"-> {export_markdown()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
