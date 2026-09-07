* stata_checks.do -- recompute the WBES check statistics in Stata (written by 03_checks.py)
clear all
set more off
use wbes_wave wbes_weight using "/Users/matteo/Library/CloudStorage/Dropbox/1-Ongoing Projects/Rwanda - TRS/data/WB-Enterprise-Surveys/3_Final/WBES_pooled_establishment.dta", clear
rename (wbes_wave wbes_weight) (wave wstrict)
gen long one = 1
collapse (sum) n=one sum_w=wstrict, by(wave)
export delimited using "/Users/matteo/Documents/GitHub/rwa-trs/WB-Enterprise-Surveys/logs/stata_checks.csv", replace
