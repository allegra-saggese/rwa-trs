"""
make_tex_figures.py -- regenerate every figure without its embedded caption or note, for STEG-Results.

    python make_tex_figures.py [module ...]
    output/figures/tex/*.pdf

The LaTeX document carries the caption above each figure and the note below it, so the image itself
must contain neither. Rather than edit ten figure scripts, this driver imports each one and runs it
with three methods temporarily replaced:

    Figure.text      -> no-op   removes the note block drawn at the foot of the figure
    Figure.suptitle  -> no-op   removes the overall title, which becomes the LaTeX caption
    Axes.set_title   -> cleared at save time, but only on single-panel figures, where the axes
                       title is acting as the caption; column headers on multi-panel figures stay
    Figure.savefig   -> writes into output/figures/tex/ instead of output/figures/

Axis titles, axis labels, legends and in-panel statistics boxes are left alone: those are part of the
figure, not a caption. Nothing in the original scripts is modified and the originals they normally
write are not touched.
"""
import sys, time, importlib, traceback
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
from matplotlib.figure import Figure
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bar_chart_housing as B          # never alias to C: shadows patsy C()

TEXFIG = Path(str(B.FIG)) / "tex"
TEXFIG.mkdir(parents=True, exist_ok=True)

MODULES = ["bar_chart_housing", "coefplot_housing", "coefplot_housing_lasso",
           "coefplot_jobs", "cohort_education", "cohort_marriage",
           "coefplot_forest_5km", "coefplot_jrc_forest",
           "forest_event_study_5km", "event_ntl_groups"]

_text, _suptitle, _savefig = Figure.text, Figure.suptitle, Figure.savefig


def _noop(self, *a, **k):
    return self.text(0, 0, "") if False else None


def _redirect(self, fname, *a, **k):
    # On a single-panel figure the axes title IS the caption, so drop it. On a multi-panel figure
    # the axes titles are column headers and are part of the figure, so leave them alone.
    if len(self.axes) == 1:
        self.axes[0].set_title("")
    try:
        name = Path(str(fname)).name
    except Exception:
        return _savefig(self, fname, *a, **k)
    if not name.lower().endswith((".pdf", ".png")):
        return _savefig(self, fname, *a, **k)
    k.pop("bbox_inches", None)
    return _savefig(self, TEXFIG / name, *a, bbox_inches="tight", **k)


def run(name):
    """Call main() if the module has one, otherwise execute its __main__ block.

    sys.argv is blanked first: some figure scripts parse arguments of their own, and would
    otherwise choke on the module names passed to this driver.
    """
    saved_argv = sys.argv[:]
    sys.argv = [f"{name}.py"]
    try:
        return _run_module(name)
    finally:
        sys.argv = saved_argv


def _run_module(name):
    mod = importlib.import_module(name)
    if hasattr(mod, "main"):
        mod.main()
        return "main()"
    import runpy
    runpy.run_path(str(Path(__file__).resolve().parent / f"{name}.py"), run_name="__main__")
    return "__main__ block"


def main(names):
    Figure.text, Figure.suptitle, Figure.savefig = _noop, _noop, _redirect
    ok, bad = [], []
    try:
        for name in names:
            try:
                # compare modification times, not the set of names: a rerun overwrites files
                # that are already there, and a set difference would call that "wrote nothing"
                started = time.time()
                how = run(name)
                made = sorted(f.name for f in TEXFIG.glob("*.pdf") if f.stat().st_mtime >= started - 1)
                if not made:
                    bad.append((name, "produced no figure"))
                    print(f"  EMPTY {name}: ran via {how} but wrote nothing")
                else:
                    ok.append(name)
                    print(f"  ok    {name}  ({how}) -> {', '.join(made)}")
            except Exception as exc:
                bad.append((name, exc))
                print(f"  FAIL  {name}: {type(exc).__name__}: {exc}")
                traceback.print_exc(limit=2)
    finally:
        Figure.text, Figure.suptitle, Figure.savefig = _text, _suptitle, _savefig
    print(f"\n{len(ok)} ok, {len(bad)} failed -> {TEXFIG}")
    for f in sorted(TEXFIG.glob("*.pdf")):
        print("   ", f.name)


if __name__ == "__main__":
    main(sys.argv[1:] or MODULES)
