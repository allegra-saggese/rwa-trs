* stata_checks.do -- recompute EC check statistics in Stata (written by 03_checks.py)
clear all
set more off
use year wt dist urban estid total_workers using "/Users/matteo/Library/CloudStorage/Dropbox/1-Ongoing Projects/Rwanda - TRS/data/Publicly-Available-NISR/Establishment-Census-EC/3_Final/EC_pooled_establishment.dta", clear
gen long one = 1
gen byte urb = urban == 1
bysort year dist: gen byte first_dist = _n == 1
collapse (sum) n=one sum_wt=wt urban=urb n_dist=first_dist workers=total_workers, by(year)
export delimited using "/Users/matteo/Documents/GitHub/rwa-trs/NISR/Establishment-Census-EC/logs/stata_checks.csv", replace
