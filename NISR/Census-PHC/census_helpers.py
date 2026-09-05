"""
census_helpers.py -- dataset-local helpers for the Census pipeline.

Every NISR dataset folder carries its own copy of this pattern (paths, logging,
Stata I/O, name/label hygiene) so each folder is independently replicable. Do not
import across dataset folders.
"""
from __future__ import annotations

import getpass, json, logging, os, re, sys, time
from pathlib import Path

import numpy as np
import pandas as pd
import pyreadstat

DATASET = "Census-PHC"
HERE = Path(__file__).resolve().parent
LOGS = HERE / "logs"

# --------------------------------------------------------------------------- paths
# The Dropbox project folder sits at a different path on each collaborator's Mac.
# NISR_DB_ROOT (environment) overrides everything; otherwise the login user decides.
ROOTS = {
    "matteo": "/Users/matteo/Library/CloudStorage/Dropbox/1-Ongoing Projects/Rwanda - TRS/data/Publicly-Available-NISR",
    "allegrasaggese": "/Users/allegrasaggese/Library/CloudStorage/Dropbox/Rwanda - TRS/data/Publicly-Available-NISR",
}

def db_root() -> Path:
    r = os.environ.get("NISR_DB_ROOT")
    if not r:
        u = getpass.getuser()
        if u not in ROOTS:
            sys.exit(f"Unknown user {u!r}: set NISR_DB_ROOT to the Publicly-Available-NISR folder, "
                     f"or add yourself to ROOTS in {Path(__file__).name}")
        r = ROOTS[u]
    p = Path(r)
    if not p.is_dir():
        sys.exit(f"Data root not found: {p}")
    return p

def paths() -> dict[str, Path]:
    d = db_root() / DATASET
    return {"root": d, "raw": d / "1_Raw", "inter": d / "2_Intermediate", "final": d / "3_Final",
            "doc": d / "z_Documentation", "rep": d / "zz_Reports"}

# ------------------------------------------------------------------------- logging
def get_logger(step: str) -> logging.Logger:
    """One log file per master run (NISR_RUN_ID); a step run on its own gets its own file."""
    LOGS.mkdir(exist_ok=True)
    run_id = os.environ.get("NISR_RUN_ID") or time.strftime("%Y%m%d-%H%M%S") + "_" + step
    log = logging.getLogger(step)
    log.setLevel(logging.INFO)
    if not log.handlers:
        fmt = logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s", "%H:%M:%S")
        fh = logging.FileHandler(LOGS / f"run_{run_id}.log", encoding="utf-8"); fh.setFormatter(fmt); log.addHandler(fh)
        sh = logging.StreamHandler(sys.stdout); sh.setFormatter(fmt); log.addHandler(sh)
    log.info("==== %s | run %s | python %s | pandas %s | pyreadstat %s", step, run_id,
             sys.version.split()[0], pd.__version__, pyreadstat.__version__)
    return log

class Checks:
    """Collects PASS/FAIL checks. A hard failure raises immediately; a soft one (hard=False) is
    logged as WARN and does not stop the run -- it is a documented data quirk, not a bug."""
    def __init__(self, log): self.log, self.fails, self.warns = log, [], []
    def __call__(self, cond: bool, msg: str, hard: bool = True):
        if cond: self.log.info("PASS  %s", msg)
        elif hard:
            self.log.error("FAIL  %s", msg); self.fails.append(msg); raise AssertionError(msg)
        else:
            self.log.warning("WARN  %s", msg); self.warns.append(msg)
    def done(self):
        if self.fails: raise AssertionError(f"{len(self.fails)} check(s) failed: {self.fails}")
        self.log.info("all hard checks passed (%d soft warnings)", len(self.warns))

# ------------------------------------------------------------------------ Stata I/O
def read_dta(path, **kw):
    """pyreadstat with a latin1 fallback (several NISR files carry non-UTF-8 labels).
    Returns df, var_labels, value_labels (value labels keyed by variable, {code: text})."""
    try:
        df, m = pyreadstat.read_dta(str(path), **kw)
    except UnicodeDecodeError:
        df, m = pyreadstat.read_dta(str(path), encoding="latin1", **kw)
    # pyreadstat hands back integer columns that contain missings as object dtype; make them float64
    for c in df.columns:
        if df[c].dtype == object:
            v = df[c].dropna()
            if len(v) and v.map(lambda x: isinstance(x, (int, float, np.integer, np.floating))).all():
                df[c] = pd.to_numeric(df[c], errors="coerce")
    return df, dict(m.column_names_to_labels), {k: dict(v) for k, v in m.variable_value_labels.items()}

def read_sav(path, **kw):
    """SPSS reader with the same latin1 fallback and return shape as read_dta."""
    try:
        df, m = pyreadstat.read_sav(str(path), **kw)
    except UnicodeDecodeError:
        df, m = pyreadstat.read_sav(str(path), encoding="latin1", **kw)
    for c in df.columns:
        if df[c].dtype == object:
            v = df[c].dropna()
            if len(v) and v.map(lambda x: isinstance(x, (int, float, np.integer, np.floating))).all():
                df[c] = pd.to_numeric(df[c], errors="coerce")
    return df, dict(m.column_names_to_labels), {k: dict(v) for k, v in m.variable_value_labels.items()}

def read_any(path, **kw):
    return read_sav(path, **kw) if str(path).lower().endswith(".sav") else read_dta(path, **kw)

def read_meta(path):
    rd = pyreadstat.read_sav if str(path).lower().endswith(".sav") else pyreadstat.read_dta
    try:
        _, m = rd(str(path), metadataonly=True)
    except UnicodeDecodeError:
        _, m = rd(str(path), metadataonly=True, encoding="latin1")
    return m

_STATA_NAME = re.compile(r"[^A-Za-z0-9_]")

def stata_name(name: str) -> str:
    n = _STATA_NAME.sub("_", str(name))
    if not n or n[0].isdigit(): n = "v_" + n
    return n[:32]

def lower_names(df: pd.DataFrame, var_labels: dict, value_labels: dict, log) -> tuple[pd.DataFrame, dict, dict]:
    """Lower-case every variable name. On a collision, drop the copy that is entirely
    missing (NISR ships e.g. `district`/`District` in LFS 2020); otherwise suffix _2. Logged."""
    new, seen = {}, {}
    for c in df.columns:
        n = stata_name(c.lower())
        if n in seen:
            other = seen[n]
            if df[c].isna().all():
                log.info("name collision %r vs %r -> dropping %r (all missing)", c, other, c); df = df.drop(columns=[c]); continue
            if df[other].isna().all():
                log.info("name collision %r vs %r -> dropping %r (all missing)", c, other, other)
                df = df.drop(columns=[other]); del new[other]
            else:
                n2 = stata_name(n + "_2"); log.info("name collision %r vs %r -> renaming %r to %r", c, other, c, n2); n = n2
        seen[n] = c; new[c] = n
    df = df.rename(columns=new)
    vl = {new[k]: v for k, v in var_labels.items() if k in new}
    vv = {new[k]: v for k, v in value_labels.items() if k in new}
    return df, vl, vv

def destring(df: pd.DataFrame, log, skip=()) -> pd.DataFrame:
    """Convert string columns whose non-empty values are all numeric (Stata `destring`)."""
    for c in df.columns:
        if c in skip or df[c].dtype != object: continue
        s = df[c].astype("string").str.strip()
        nonempty = s[(s.notna()) & (s != "")]
        if len(nonempty) == 0: continue
        num = pd.to_numeric(nonempty, errors="coerce")
        if num.notna().all():
            out = pd.to_numeric(s.replace("", pd.NA), errors="coerce").astype("float64")
            df[c] = out; log.info("destring %s (%d values)", c, len(nonempty))
    return df

def downcast(df: pd.DataFrame, keep_double=()) -> pd.DataFrame:
    """Smallest exact Stata storage type, like Stata's `compress`: integer-valued columns
    become byte/int/long (pandas Int8/Int16/Int32, nullable, so missings survive); everything
    else stays double. Weights/ids listed in keep_double stay double."""
    for c in df.columns:
        s = df[c]
        if c in keep_double or not pd.api.types.is_numeric_dtype(s) or pd.api.types.is_bool_dtype(s): continue
        v = s.dropna().astype("float64")
        if len(v) == 0: df[c] = s.astype("Int8"); continue
        if not np.all(np.mod(v, 1) == 0): continue
        lo, hi = v.min(), v.max()
        if -127 <= lo and hi <= 100: t = "Int8"
        elif -32767 <= lo and hi <= 32740: t = "Int16"
        elif -2147483647 <= lo and hi <= 2147483620: t = "Int32"
        else: continue
        df[c] = s.astype("float64").round().astype(t)
    return df

def to_plain_float(df: pd.DataFrame) -> pd.DataFrame:
    """Nullable-integer columns (Int8/16/32) -> float64 before pd.concat: concat of frames that
    do not all carry a column turns extension dtypes into object. downcast() restores them."""
    for c in df.columns:
        if isinstance(df[c].dtype, pd.api.extensions.ExtensionDtype) and pd.api.types.is_numeric_dtype(df[c]):
            df[c] = df[c].astype("float64")
    return df

def resolve_object_columns(df: pd.DataFrame, log, keep_str=()) -> pd.DataFrame:
    """After pd.concat: an object column holding Python numbers is a reindex artefact -> float64.
    A column that is numeric in some waves and text in others is a type conflict: it becomes
    numeric if every text value parses as a number, otherwise it stays text and is logged."""
    for c in df.columns:
        if c in keep_str or df[c].dtype != object: continue
        v = df[c].dropna()
        if len(v) == 0: df[c] = df[c].astype("float64"); continue
        isnum = v.map(lambda x: isinstance(x, (int, float, np.integer, np.floating)))
        if isnum.all(): df[c] = pd.to_numeric(df[c], errors="coerce"); continue
        if isnum.any():
            txt = v[~isnum].astype(str).str.strip()
            if pd.to_numeric(txt.mask(txt == ""), errors="coerce").notna().all() or (txt == "").all():
                obj = df[c].astype(object); df[c] = pd.to_numeric(obj.mask(obj == ""), errors="coerce")
                log.info("type conflict %s: numeric in some waves, numeric-looking text in others -> numeric", c)
            else:
                log.warning("type conflict %s: numeric in some waves, free text in others -> kept as text", c)
                df[c] = df[c].astype(object).where(df[c].notna(), "").astype(str)
    return df

def write_dta(df: pd.DataFrame, path, var_labels: dict, value_labels: dict, data_label: str, log):
    """pandas.to_stata (v118): keeps small storage types, writes variable + value labels."""
    df = df.copy()
    vl = {c: (var_labels.get(c) or "")[:80] for c in df.columns}
    vv = {}
    for c, d in value_labels.items():
        if c not in df.columns or not pd.api.types.is_numeric_dtype(df[c]): continue
        dd = {}
        for k, t in d.items():
            try: kk = int(k)
            except (TypeError, ValueError): continue
            if -2147483647 <= kk <= 2147483620: dd[kk] = str(t)[:32000]     # Stata value labels are int32
            else: log.info("value label %s=%r on %s dropped (key outside int32)", k, str(t)[:30], c)
        if dd: vv[c] = dd
    for c in df.columns:
        if df[c].dtype == object or pd.api.types.is_string_dtype(df[c]):
            nonnull = df[c].dropna()
            if len(nonnull) and nonnull.map(lambda x: isinstance(x, (int, float, np.integer, np.floating))).all():
                # an object column of numbers = a concat/reindex artefact; never write it as a string
                log.warning("column %s is numeric but object-typed -> cast to float64 before writing", c)
                df[c] = pd.to_numeric(df[c], errors="coerce"); continue
            df[c] = df[c].astype(object).where(df[c].notna(), "").astype(str)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    df.to_stata(str(path), version=118, write_index=False, data_label=data_label[:80],
                variable_labels=vl, value_labels=vv)
    log.info("wrote %s  (%s rows x %s vars, %.1f MB)", Path(path).name, f"{len(df):,}", len(df.columns),
             os.path.getsize(path) / 1e6)

# ------------------------------------------------------------ label reconciliation
_STOP = {"the", "a", "an", "of", "in", "to", "for", "is", "are", "was", "were", "do", "does", "did",
         "name", "names", "you", "your", "he", "she", "his", "her", "and", "or", "at", "on", "by", "with"}

def label_tokens(s: str) -> set:
    return {t for t in re.sub(r"[^a-z0-9 ]", " ", str(s).lower()).split() if t not in _STOP and len(t) > 1}

def label_similarity(a: str, b: str) -> float:
    ta, tb = label_tokens(a), label_tokens(b)
    if not ta and not tb: return 1.0
    if not ta or not tb: return 0.0
    return len(ta & tb) / len(ta | tb)

def save_json(obj, path):
    Path(path).write_text(json.dumps(obj, indent=1, default=str))
