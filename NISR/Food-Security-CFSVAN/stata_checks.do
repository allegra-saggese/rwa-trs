* stata_checks.do -- recompute CFSVA check statistics in Stata (written by 03_checks.py)
clear all
set more off
use wave wt dist using "/Users/matteo/Library/CloudStorage/Dropbox/1-Ongoing Projects/Rwanda - TRS/data/Publicly-Available-NISR/Food-Security-CFSVAN/3_Final/CFSVA_pooled_household.dta", clear
gen long one = 1
bysort wave dist: gen byte first_dist = _n == 1
collapse (sum) n=one sum_wt=wt n_dist=first_dist, by(wave)
export delimited using "/Users/matteo/Documents/GitHub/rwa-trs/NISR/Food-Security-CFSVAN/logs/stata_checks.csv", replace
