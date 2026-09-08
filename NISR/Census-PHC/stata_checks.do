* stata_checks.do -- recompute Census check statistics in Stata (written by 03_checks.py)
clear all
set more off
use census_year census_weight census_sex census_sector census_household_id using "/Users/matteo/Library/CloudStorage/Dropbox/1-Ongoing Projects/Rwanda - TRS/data/Publicly-Available-NISR/Census-PHC/3_Final/Census_pooled_person.dta", clear
rename (census_year census_weight census_sex census_sector census_household_id) (year wt sex sector hhid)
gen byte male = sex == 1
gen byte female = sex == 2
gen long one = 1
bysort year sector: gen byte first_sector = _n == 1
collapse (sum) n=one sum_wt=wt male female n_sector=first_sector, by(year)
export delimited using "/Users/matteo/Documents/GitHub/rwa-trs/NISR/Census-PHC/logs/stata_checks.csv", replace
use census_year census_weight census_household_size census_household_id using "/Users/matteo/Library/CloudStorage/Dropbox/1-Ongoing Projects/Rwanda - TRS/data/Publicly-Available-NISR/Census-PHC/3_Final/Census_pooled_household.dta", clear
rename (census_year census_weight census_household_size census_household_id) (year wt hhsize hhid)
collapse (count) n_hh=hhid (sum) hhsize_sum=hhsize sum_wt_hh=wt, by(year)
export delimited using "/Users/matteo/Documents/GitHub/rwa-trs/NISR/Census-PHC/logs/stata_checks_hh.csv", replace
