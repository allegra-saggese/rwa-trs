* stata_checks.do -- recompute LFS check statistics in Stata (written by 03_checks.py)
clear all
set more off
use lfs_year lfs_weight lfs_working_age_16_plus lfs_sex using "/Users/matteo/Library/CloudStorage/Dropbox/1-Ongoing Projects/Rwanda - TRS/data/Publicly-Available-NISR/Labour-Force-Survey-LFS/3_Final/LFS_pooled_person.dta", clear
rename (lfs_year lfs_weight lfs_working_age_16_plus lfs_sex) (year wt wap16 sex)
gen double wwap = wap16 * wt
gen byte male = sex == 1
gen byte female = sex == 2
gen long one = 1
collapse (sum) n=one sum_wt=wt wpop_wap16=wwap male female, by(year)
export delimited using "/Users/matteo/Documents/GitHub/rwa-trs/NISR/Labour-Force-Survey-LFS/logs/stata_checks.csv", replace
use lfs_year lfs_household_id lfs_household_size using "/Users/matteo/Library/CloudStorage/Dropbox/1-Ongoing Projects/Rwanda - TRS/data/Publicly-Available-NISR/Labour-Force-Survey-LFS/3_Final/LFS_pooled_household.dta", clear
rename (lfs_year lfs_household_id lfs_household_size) (year hhid hhsize)
collapse (count) n_hh=hhid (sum) hhsize_sum=hhsize, by(year)
export delimited using "/Users/matteo/Documents/GitHub/rwa-trs/NISR/Labour-Force-Survey-LFS/logs/stata_checks_hh.csv", replace
