"""Shared paths, ISIC groupings and park-distance bands for the preliminary analysis.

Outputs go to the single Dropbox output/ folder (see output/README.md):
  figures -> output/figures, maps -> output/maps,
  tables  -> output/tables/summary_statistics or output/tables/regressions,
  journal-style regression tables -> output/tables/regressions/journal_format.
Scripts keep their short internal ids (fig03_..., T10_B_jobs, tab3_B_jobs); OUT_F and OUT_T translate
each id to its descriptive file name and folder through the tables below, so every read and write
in the pipeline lands on the same file. An id missing from the tables raises KeyError.
Derived sector panels (OUT_D) are unchanged."""
import sys
from pathlib import Path
import pandas as pd
import matplotlib as mpl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import paths as P  # repo-root paths.py: Dropbox root per user, or RWA_ROOT

REPO = P.REPO
ROOT = P.DROPBOX
DATA = ROOT / "data"
ANA = DATA / "Publicly-Available-NISR" / "Analysis"
OUT = P.OUT
OUT_D = ANA / "prelim"  # derived sector-level panels
OUT_D.mkdir(parents=True, exist_ok=True)

# figure id -> (folder under output/, descriptive name)
FIGURE_NAMES = {
    'fig01_map_jobs_levels': ('maps', 'census_jobs_levels_and_change'),
    'fig02_map_land_glclu': ('maps', 'glclu_land_use_2000_2020'),
    'fig03_stacked_jobs_groups': ('figures', 'census_jobs_by_treatment_group'),
    'fig04_stacked_jobs_by_park': ('figures', 'census_jobs_by_park'),
    'fig05_stacked_land_groups': ('figures', 'glclu_land_by_treatment_group'),
    'fig06_sector_land_treated': ('figures', 'glclu_land_treated_sectors_2000_vs_2020'),
    'fig07_sector_land_all_2020': ('figures', 'glclu_land_all_sectors_2020'),
    'fig08_land_transitions': ('figures', 'glclu_land_transitions_2000_2020'),
    'fig09_ntl_by_park': ('figures', 'nightlights_and_visitors_by_park'),
    'fig10_district_facets_agriculture': ('figures', 'district_agriculture_share_eicv_lfs'),
    'fig11_district_facets_tourism': ('figures', 'district_tourism_share_eicv_lfs'),
    'fig12_violins': ('figures', 'model_objects_by_treatment_group_violins'),
    'fig13_tourism_definitions_lfs': ('figures', 'lfs_tourism_definitions_by_district'),
    'fig14_map_change_tourism_agriculture': ('maps', 'census_change_tourism_and_agriculture'),
    'fig15_map_ec2011_accommodation': ('maps', 'ec2011_accommodation_food'),
    'fig16_kabatwa_mudende_two_cells': ('maps', 'two_cells_kabatwa_mudende'),
    'fig16_musanze_two_cells': ('maps', 'two_cells_musanze'),
    'fig17_map_pop_density': ('maps', 'population_density'),
    'fig18_gate_gradient': ('figures', 'gate_distance_gradient_estimates'),
    'jobs_by_park_band': ('figures', 'census_jobs_by_distance_band'),
    'jobs_change_distance_binscatter': ('figures', 'census_jobs_change_by_distance_binscatter'),
    'jobs_national_trend': ('figures', 'census_jobs_national_trend'),
    'land_by_park_band': ('figures', 'glclu_land_by_distance_band'),
    'land_elasticity_and_c': ('figures', 'land_elasticity_estimates_by_distance_band'),
    'output_ag_value_per_ha_by_group': ('figures', 'sas_ag_value_per_ha_by_group'),
    'output_trends': ('figures', 'output_trends_sas_ec_nightlights'),
}

# table id -> (folder under output/tables/, descriptive name)
TABLE_NAMES = {
    'T10_B_jobs': ('regressions', 'park_proximity_jobs'),
    'T10_B_jobs_long': ('regressions', 'park_proximity_jobs_long'),
    'T10p_B_jobs_popctrl_long': ('regressions', 'park_proximity_jobs_popcontrol_long'),
    'T10p_B_jobs_popctrl_popcoef': ('regressions', 'park_proximity_jobs_popcontrol_popcoef'),
    'T10s_B_jobs_separate_long': ('regressions', 'park_proximity_jobs_by_group_long'),
    'T11_B_land': ('regressions', 'park_proximity_land'),
    'T11_B_land_lights': ('regressions', 'park_proximity_nightlights'),
    'T11_B_land_lights_long': ('regressions', 'park_proximity_nightlights_long'),
    'T11_B_land_long': ('regressions', 'park_proximity_land_long'),
    'T11b_B_land_robustness_long': ('regressions', 'park_proximity_land_robustness_long'),
    'T12_B_robustness': ('regressions', 'park_proximity_robustness'),
    'T12_B_robustness_long': ('regressions', 'park_proximity_robustness_long'),
    'T13_B_by_park': ('regressions', 'park_proximity_by_park'),
    'T13_B_by_park_long': ('regressions', 'park_proximity_by_park_long'),
    'T14_B_wage_gaps': ('regressions', 'within_district_wage_gaps'),
    'T15_land_rent_by_group': ('summary_statistics', 'land_rent_by_group'),
    'T16_new_outcomes_long': ('regressions', 'land_forest_builtup_rent_outcomes_long'),
    'T17_shift_share_long': ('regressions', 'visitor_shift_share_long'),
    'T18_gate_gradient_long': ('regressions', 'gate_distance_gradient_long'),
    'T19_income_land_long': ('regressions', 'income_on_land_long'),
    'T1_national_employment': ('summary_statistics', 'national_employment_census'),
    'T2_model_objects': ('summary_statistics', 'model_objects_by_group_and_wave'),
    'T2_model_objects_full': ('summary_statistics', 'model_objects_by_group_and_wave_full'),
    'T3_balance_treated_control': ('summary_statistics', 'balance_treated_vs_control'),
    'T4a_parks_jobs': ('summary_statistics', 'park_jobs'),
    'T4b_parks_land': ('summary_statistics', 'park_land'),
    'T4c_park_visitors': ('summary_statistics', 'park_visitors'),
    'T5_land_transitions': ('summary_statistics', 'glclu_land_transitions'),
    'T6a_output_agriculture': ('summary_statistics', 'output_agriculture_sas'),
    'T6b_output_services': ('summary_statistics', 'output_services_ec'),
    'T6c_output_nightlights': ('summary_statistics', 'output_nightlights'),
    'T7_earnings_long': ('summary_statistics', 'earnings_by_sector_long'),
    'T7_earnings_ratios': ('summary_statistics', 'earnings_ratios_by_sector'),
    'T8_land_regressions': ('regressions', 'land_on_services_share'),
    'T8_land_regressions_long': ('regressions', 'land_on_services_share_long'),
    'T8b_land_timing_fe_long': ('regressions', 'land_on_services_share_timing_fe_long'),
    'T9a_tourism_definitions_census2012': ('summary_statistics', 'tourism_definitions_census2012'),
    'T9b_tourism_lfs_district_groups': ('summary_statistics', 'tourism_definitions_lfs_by_district'),
    'candidate_cell_pairs': ('summary_statistics', 'candidate_cell_pairs'),
    'district_shares_eicv_lfs': ('summary_statistics', 'district_shares_eicv_lfs'),
    'jobs_by_park_band': ('summary_statistics', 'jobs_by_distance_band'),
    'jobs_changes_by_band': ('summary_statistics', 'jobs_change_by_distance_band'),
    'jobs_isic_sections_census': ('summary_statistics', 'jobs_isic_sections_census'),
    'jobs_lfs_national_shares': ('summary_statistics', 'jobs_lfs_national_shares'),
    'jobs_national_census': ('summary_statistics', 'jobs_national_census'),
    'kabatwa_mudende_two_cells': ('summary_statistics', 'two_cells_kabatwa_mudende'),
    'land_by_park_band': ('summary_statistics', 'land_by_distance_band'),
    'land_elasticity': ('regressions', 'land_elasticity_by_distance_band'),
    'land_moments_glclu': ('summary_statistics', 'land_moments_glclu'),
    'land_moments_worldcover': ('summary_statistics', 'land_moments_worldcover'),
    'musanze_two_cells': ('summary_statistics', 'two_cells_musanze'),
    'output_ag_national': ('summary_statistics', 'output_agriculture_national_sas'),
    'output_ag_top_crops_kt': ('summary_statistics', 'output_agriculture_top_crops_sas'),
    'output_ag_value_per_ha_by_group': ('summary_statistics', 'output_agriculture_value_per_ha_by_group'),
    'output_ec_national': ('summary_statistics', 'output_ec_national'),
    'output_ec_turnover_per_worker': ('summary_statistics', 'output_ec_turnover_per_worker'),
    'output_nightlights_by_band': ('summary_statistics', 'output_nightlights_by_distance_band'),
    'output_tourism_national': ('summary_statistics', 'output_tourism_national'),
}

# journal-format table id -> descriptive name, in output/tables/regressions/journal_format/
JOURNAL_NAMES = {
    'regression_tables': 'all_regression_tables',
    'regression_tables_standalone': 'all_regression_tables_standalone',
    'tab10_land_rent': 'land_rent_park_districts',
    'tab11_shift_share_jobs': 'visitor_shift_share_jobs',
    'tab12_shift_share_land': 'visitor_shift_share_land',
    'tab1_land_services': 'land_on_services_share',
    'tab1b_land_fe': 'land_on_services_share_alt_fe',
    'tab2_contract_curve': 'land_labor_contract_curve',
    'tab3_B_jobs': 'park_proximity_jobs',
    'tab4_B_land': 'park_proximity_land',
    'tab4b_B_land_robustness': 'park_proximity_land_robustness',
    'tab4c_B_land_parks': 'park_proximity_land_by_park',
    'tab5_B_robustness': 'park_proximity_robustness',
    'tab6_B_parks': 'park_proximity_by_park',
    'tab7_B_wages': 'within_district_wage_gaps',
    'tab8_land_other_outcomes': 'land_other_outcomes',
    'tab9_B_other_land': 'park_proximity_forest_and_builtup',
}


class _Out:
    """Output directory that maps a script's internal file id to its descriptive path."""

    def __init__(self, names, base, fixed_dir=None):
        self.names, self.base, self.fixed_dir = names, base, fixed_dir

    def _resolve(self, name):
        p = Path(name)
        stem, suf = (p.stem, p.suffix) if p.suffix else (p.name, "")
        if self.fixed_dir is not None:
            return self.fixed_dir / (self.names[stem] + suf)
        folder, new = self.names[stem]
        return self.base / folder / (new + suf)

    def __truediv__(self, name):
        if self.names is TABLE_NAMES and name == "paper":
            return _Out(JOURNAL_NAMES, None, OUT / "tables" / "regressions" / "journal_format")
        out = self._resolve(name)
        out.parent.mkdir(parents=True, exist_ok=True)
        return out

    def mkdir(self, *a, **k):
        if self.fixed_dir is not None:
            self.fixed_dir.mkdir(parents=True, exist_ok=True)


OUT_F = _Out(FIGURE_NAMES, OUT)
OUT_T = _Out(TABLE_NAMES, OUT / "tables")

# ISIC Rev.4 sections, numbered 1..21 as in the harmonized NISR files (A=1 ... U=21)
SEC = dict(zip(range(1, 22), list("ABCDEFGHIJKLMNOPQRSTU")))

# Model services s are sold to non-local (foreign) buyers. Classification by ISIC section:
#   S_tour : tourism-facing exports  I (accommodation, food), R (arts, recreation).
#            N is excluded: in the 2012 Census 4-digit codes, N79 (tour operators) is 0.7k of 24k N workers;
#            N80 security (14.4k) and N81 cleaning (8.0k) dominate, which are local non-tradables.
#   S_bus  : other services tradable across regions  J, K, M  (Jensen-Kletzer 2005 logic)
#   S_loc  : local non-tradables  G (trade), H (transport, mostly moto/freight), L, N, O (government),
#            P, Q, S, T (domestic workers), U
#   S_broad: all tertiary excluding G and O  (fallback definition requested)
GROUP = {**{s: "AG" for s in "A"}, **{s: "IND" for s in "BCDEF"},
         **{s: "S_tour" for s in "IR"}, **{s: "S_bus" for s in "JKM"},
         **{s: "S_loc" for s in "GHLNOPQSTU"}}
BROAD_EXCL = set("GO")

def band(cross: pd.DataFrame) -> pd.Series:
    """Park-distance band for each NISR sector."""
    b = pd.cut(cross.dist_to_park_km, [-1, 10, 30, 1e9], labels=["0-10 km", "10-30 km", ">30 km"]).astype(str)
    b = b.where(cross.border == 0, "Park border")
    b = b.where(cross.province_id != 1, "Kigali")
    return pd.Categorical(b, ["Park border", "0-10 km", "10-30 km", ">30 km", "Kigali"], ordered=True)

# validated categorical palette (dataviz reference, light mode)
PAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]
mpl.rcParams.update({"figure.dpi": 150, "savefig.dpi": 200, "axes.spines.top": False,
                     "axes.spines.right": False, "axes.grid": True, "grid.color": "#e5e5e5",
                     "grid.linewidth": 0.6, "axes.edgecolor": "#888", "font.size": 9,
                     "lines.linewidth": 2, "axes.prop_cycle": mpl.cycler(color=PAL)})

def to_tex(df: pd.DataFrame, path, caption, label, fmt="{:,.3f}"):
    df.to_csv(path.with_suffix(".csv"))
    tex = df.to_latex(float_format=lambda x: fmt.format(x), escape=True, na_rep="--",
                      caption=caption, label=label, position="htbp")
    path.with_suffix(".tex").write_text(tex)
