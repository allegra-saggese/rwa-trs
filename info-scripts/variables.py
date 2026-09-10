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

ROOT = Path(__file__).resolve().parents[1]
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

    # extract.py lives in data-build-scripts/, a sibling folder, so it is not on
    # sys.path when this script runs. Add it rather than duplicating the table.
    try:
        sys.path.insert(0, str(ROOT / "data-build-scripts"))
        from extract import EICV7_FILES
    except ImportError as exc:
        print(f"! could not import EICV7_FILES from data-build-scripts/extract.py: {exc}")
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


# --------------------------------------------------------------------------
# Definitions pulled from the .dta metadata
#
# The dictionary CSV gives a one-line label and nothing else. The .dta files
# carry the response categories, which is what you actually need to write a
# recode or read a coefficient. This resolves every code in WORKSTREAMS to its
# harmonised column and reads both.
# --------------------------------------------------------------------------

# Raw EICV7 module files, used only for the variables the harmonised person and
# household files do not carry (the VUP modules are separate units and are not
# merged into either).
RAW_MODULES = {
    "poverty": "EICV7_CS_cs_eicv7_poverty_file.dta",
    "person": "EICV7_CS_cs_s0_s1_s2_s3_s4_s6a_s6b_s6c_person.dta",
    "household": "EICV7_CS_cs_s01_s5_s7_household.dta",
    "services": "EICV7_CS_cs_s5f_access_to_services.dta",
    "vup_direct_support": "EICV7_CS_cs_s9d1_direct_support.dta",
    "vup_classic_public_work": "EICV7_CS_cs_s9d2_classic_public_work.dta",
    "vup_expanded_public_work": "EICV7_CS_cs_s9d3_expanded_public_work.dta",
    "vup_nsds": "EICV7_CS_cs_s9d4_nsds.dta",
    "vup_financial_services": "EICV7_CS_cs_s9d5_financial_services.dta",
}

NAME_MAP = ("NISR/Household-Living-Conditions-EICV/variable_names.csv")


def _paths():
    sys.path.insert(0, str(ROOT))
    import paths as P
    return P


# NISR .dta files mix encodings: EICV and Census carry latin-1 accented value
# labels that fail a strict utf-8 read. Same fallback chain as inventory.py.
ENCODINGS = (None, "latin1", "cp1252")


def _read_meta(fp):
    """Metadata for a .dta, trying each encoding. Returns None if all fail."""
    import pyreadstat
    for enc in ENCODINGS:
        try:
            kwargs = {"metadataonly": True}
            if enc:
                kwargs["encoding"] = enc
            _d, m = pyreadstat.read_dta(str(fp), **kwargs)
            return m
        except Exception:  # noqa: BLE001 - trying the next encoding is the point
            continue
    print(f"! could not read {Path(fp).name} in any of {ENCODINGS}")
    return None


def _harmonised_meta(P):
    """Variable and value labels from the harmonised EICV files.

    4_Harmonized is the dataset of record, so it is read first and the raw
    modules are only consulted for what it does not carry.
    """
    labels, values = {}, {}
    for unit in ("person", "household"):
        fp = P.NISR / f"Household-Living-Conditions-EICV/4_Harmonized/H_EICV_{unit}.dta"
        if not fp.exists():
            continue
        m = _read_meta(fp)
        if m is None:
            continue
        labels.update(dict(zip(m.column_names, m.column_labels)))
        values.update(m.variable_value_labels)
    return labels, values


def _raw_meta(P, unit: str):
    """Variable and value labels from one raw EICV7 module, keyed by native code."""
    fname = RAW_MODULES.get(unit)
    if not fname:
        return {}, {}
    hits = list((P.NISR / "Household-Living-Conditions-EICV/1_Raw").rglob(fname))
    if not hits:
        return {}, {}
    m = _read_meta(hits[0])
    if m is None:
        return {}, {}
    low = {c.lower(): c for c in m.column_names}
    labels = {k: lab for k, lab in
              zip([c.lower() for c in m.column_names], m.column_labels)}
    values = {c.lower(): m.variable_value_labels[orig]
              for c, orig in low.items() if orig in m.variable_value_labels}
    return labels, values


def definitions() -> "pd.DataFrame":  # noqa: F821
    """One row per variable in WORKSTREAMS, with its label and response categories.

    Resolution order for each EICV7 code:

    1. the EICV pipeline's `variable_names.csv` maps the native code to the
       clean name used in 4_Harmonized;
    2. the harmonised .dta supplies the label and value labels;
    3. anything the harmonised files do not carry (the VUP modules are separate
       units) falls back to the raw EICV7 module, marked `source=raw`.
    """
    import pandas as pd
    import pyreadstat  # noqa: F401  - fail early with a clear error if missing

    P = _paths()
    nm = pd.read_csv(ROOT / NAME_MAP)
    e7 = nm[nm.wave.astype(str).str.contains("EICV7", na=False)].copy()
    e7["nat"] = e7.native.astype(str).str.lower()
    lut = e7.drop_duplicates("nat").set_index("nat")

    h_lab, h_val = _harmonised_meta(P)
    raw_cache: dict[str, tuple] = {}
    dict_lab = {}
    if DICTIONARY.exists():
        d = pd.read_csv(DICTIONARY)
        dict_lab = dict(zip(d.variable.astype(str).str.lower(), d.label))

    rows = []
    for ws, spec in WORKSTREAMS.items():
        for name, (unit, code) in spec["variables"].items():
            key = str(code).lower()
            clean = lut.loc[key, "clean_name"] if key in lut.index else None
            label = values = None
            source = "unresolved"

            if clean and clean in h_lab:
                label, values, source = h_lab.get(clean), h_val.get(clean), "harmonised"
            else:
                if unit not in raw_cache:
                    raw_cache[unit] = _raw_meta(P, unit)
                r_lab, r_val = raw_cache[unit]
                if key in r_lab:
                    label, values, source = r_lab.get(key), r_val.get(key), "raw"

            if not label:
                label, source = dict_lab.get(key), (
                    "dictionary" if dict_lab.get(key) else "unresolved")

            rows.append(dict(
                workstream=ws, name=name, unit=unit, eicv7_code=code,
                harmonised_name=clean, label=label, source=source,
                n_categories=len(values) if values else 0,
                categories="; ".join(f"{k}={v}" for k, v in list(values.items())[:40])
                if values else ""))
    return pd.DataFrame(rows)


def export_definitions(dest: Path | None = None) -> Path:
    """Write docs/variable_definitions.md and the matching CSV."""
    import pandas as pd  # noqa: F401
    d = definitions()
    dest = dest or (ROOT / "docs" / "variable_definitions.md")
    dest.parent.mkdir(parents=True, exist_ok=True)
    d.to_csv(dest.with_suffix(".csv"), index=False)

    src = d.source.value_counts().to_dict()
    out = [
        "# EICV7 variable definitions",
        "",
        "Generated by `python info-scripts/variables.py --definitions`. "
        "Do not hand-edit.",
        "",
        "Labels and response categories are read from the .dta metadata, not "
        "from the dictionary CSV, which carries a label and nothing else. "
        "`4_Harmonized` is read first; the VUP modules are separate units that "
        "the harmonised person and household files do not carry, so those fall "
        "back to the raw EICV7 module and are marked `raw`.",
        "",
        f"**{len(d)} variables** — "
        + ", ".join(f"{k}: {v}" for k, v in sorted(src.items())),
        "",
    ]
    for ws in d.workstream.unique():
        sub = d[d.workstream == ws]
        out += [f"## {ws} ({len(sub)})", ""]
        for r in sub.itertuples():
            out.append(f"### `{r.name}` — {r.eicv7_code}")
            out.append("")
            out.append(f"- **Label:** {r.label or '_not found_'}")
            out.append(f"- **Unit:** {r.unit}   **Source:** {r.source}"
                       + (f"   **Harmonised as:** `{r.harmonised_name}`"
                          if r.harmonised_name else ""))
            if r.categories:
                out.append(f"- **Categories ({r.n_categories}):** {r.categories}")
            out.append("")
    dest.write_text("\n".join(out))
    print(f"-> {dest}")
    print(f"-> {dest.with_suffix('.csv')}")
    return dest


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--check", action="store_true", help="verify codes against the dictionary")
    p.add_argument("--list", dest="which", nargs="?", const="all",
                   choices=["all", *WORKSTREAMS], help="print a workstream")
    p.add_argument("--export", action="store_true", help="write docs/variable_lists.md")
    p.add_argument("--definitions", action="store_true",
                   help="write docs/variable_definitions.md from the .dta metadata")
    args = p.parse_args(argv)

    if not (args.check or args.which or args.export or args.definitions):
        p.print_help()
        return 1
    if args.check:
        return 1 if check() else 0
    if args.which:
        show(args.which)
    if args.export:
        print(f"-> {export_markdown()}")
    if args.definitions:
        export_definitions()
    return 0


if __name__ == "__main__":
    sys.exit(main())
