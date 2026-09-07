* stata_checks.do -- recompute EICV check statistics in Stata (written by 03_checks.py)
clear all
set more off
use eicv_wave eicv_weight eicv_sex eicv_district eicv_household_id using "/Users/matteo/Library/CloudStorage/Dropbox/1-Ongoing Projects/Rwanda - TRS/data/Publicly-Available-NISR/Household-Living-Conditions-EICV/3_Final/EICV_pooled_person.dta", clear
rename (eicv_wave eicv_weight eicv_sex eicv_district eicv_household_id) (wave wt sex dist hhid)
gen byte male = sex == 1
gen byte female = sex == 2
gen long one = 1
bysort wave hhid: gen byte first_hh = _n == 1
collapse (sum) n=one sum_wt=wt male female n_hh=first_hh, by(wave)
export delimited using "/Users/matteo/Documents/GitHub/rwa-trs/NISR/Household-Living-Conditions-EICV/logs/stata_checks.csv", replace
use eicv_wave eicv_weight eicv_household_size eicv_household_id using "/Users/matteo/Library/CloudStorage/Dropbox/1-Ongoing Projects/Rwanda - TRS/data/Publicly-Available-NISR/Household-Living-Conditions-EICV/3_Final/EICV_pooled_household.dta", clear
rename (eicv_wave eicv_weight eicv_household_size eicv_household_id) (wave wt hhsize hhid)
collapse (count) n_hh=hhid (sum) hhsize_sum=hhsize sum_wt_hh=wt, by(wave)
export delimited using "/Users/matteo/Documents/GitHub/rwa-trs/NISR/Household-Living-Conditions-EICV/logs/stata_checks_hh.csv", replace
