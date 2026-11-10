"""Assemble output/writeup/prelim_results_writeup.tex from writeup/template.tex and the journal-format
tables in output/tables/regressions/journal_format/ (run 10_paper_tables.py first). Tables are placed inline ([H])."""
import re
from pathlib import Path
from _common import OUT, OUT_T
T = OUT_T / "paper"; W = OUT / "writeup"; W.mkdir(parents=True, exist_ok=True)
s = (Path(__file__).resolve().parent / "writeup" / "template.tex").read_text()
def put(m):
    tab = (T / f"{m.group(1)}.tex").read_text().replace(r"\begin{table}[!htbp]", r"\begin{table}[H]")
    if m.group(1) in ("tab4b_B_land_robustness", "tab5_B_robustness"):      # longest tables: smaller type to fit inline
        tab = tab.replace(r"\centering\footnotesize", r"\centering\scriptsize").replace(r"\centering\small", r"\centering\scriptsize\renewcommand{\arraystretch}{0.95}")
    return tab
s = re.sub(r"%%TABLE:(\w+)%%", put, s)
(W / "prelim_results_writeup.tex").write_text(s); print("written", len(s))
