* stata_checks.do -- recompute SAS check statistics in Stata (written by 03_checks.py)
clear all
set more off
use sas_wave sas_weight sas_production_kg sas_plot_area_ha using "/Users/matteo/Library/CloudStorage/Dropbox/1-Ongoing Projects/Rwanda - TRS/data/Publicly-Available-NISR/Season-Agriculture-Survey-SAS/3_Final/SAS_pooled_plotcrop.dta", clear
rename (sas_wave sas_weight sas_production_kg sas_plot_area_ha) (wave wt production_kg plot_area_ha)
gen long one = 1
gen byte haswt = wt < .
collapse (sum) n=one n_wt=haswt sum_wt=wt prod=production_kg (median) med_plot=plot_area_ha, by(wave)
export delimited using "/Users/matteo/Documents/GitHub/rwa-trs/NISR/Season-Agriculture-Survey-SAS/logs/stata_checks.csv", replace
