"""
harmonize_helpers.py -- helpers for the cross-dataset harmonisation step (NISR/Harmonize).

Own copy of the path / logging / Stata I/O pattern used by every dataset folder (no imports across
folders). This step READS the seven datasets' 3_Final/ and 2_Intermediate/appended/ files and their
logs/merge_alignment.json, and WRITES Publicly-Available-NISR/Harmonized/.
"""
from __future__ import annotations
import getpass, json, logging, os, re, sys, time
from pathlib import Path
import numpy as np, pandas as pd, pyreadstat

HERE = Path(__file__).resolve().parent
LOGS = HERE / "logs"
REPO_NISR = HERE.parent                      # rwa-trs/NISR/<dataset>/ folders (for merge_alignment.json)
ROOTS = {
    "matteo": "/Users/matteo/Library/CloudStorage/Dropbox/1-Ongoing Projects/Rwanda - TRS/data/Publicly-Available-NISR",
    "allegrasaggese": "/Users/allegrasaggese/Library/CloudStorage/Dropbox/Rwanda - TRS/data/Publicly-Available-NISR",
}
DATASETS = {   # short tag -> Dropbox / repo folder name
    "LFS": "Labour-Force-Survey-LFS", "Census": "Census-PHC", "EICV": "Household-Living-Conditions-EICV",
    "EC": "Establishment-Census-EC", "AHS": "Agriculture-Survey-AHS", "SAS": "Season-Agriculture-Survey-SAS",
    "CFSVA": "Food-Security-CFSVAN",
}

def db_root() -> Path:
    r = os.environ.get("NISR_DB_ROOT")
    if not r:
        u = getpass.getuser()
        if u not in ROOTS: sys.exit(f"Unknown user {u!r}: set NISR_DB_ROOT or add yourself to ROOTS in {Path(__file__).name}")
        r = ROOTS[u]
    p = Path(r)
    if not p.is_dir(): sys.exit(f"Data root not found: {p}")
    return p

def out_dir() -> Path:
    d = db_root() / "Harmonized"; d.mkdir(exist_ok=True); return d

def ds_paths(tag: str) -> dict[str, Path]:
    d = db_root() / DATASETS[tag]
    return {"root": d, "final": d / "3_Final", "appended": d / "2_Intermediate" / "appended", "repo": REPO_NISR / DATASETS[tag]}

def alignment(tag: str) -> dict:
    return json.load(open(ds_paths(tag)["repo"] / "logs" / "merge_alignment.json"))

def decisions_for(tag: str, fname: str, align: dict) -> dict:
    """{base_name: {'versions': {column: [waves]}}} for a pooled file, whatever the dataset's JSON layout."""
    if "files" in align and fname in align["files"]: return align["files"][fname].get("decisions", {})
    return align.get("decisions", {})

def col_for(decisions: dict, base: str, wave, columns) -> str | None:
    """The pooled column that carries native variable `base` for `wave` (version rule), or None."""
    d = decisions.get(base)
    if d:
        for col, waves in d.get("versions", {}).items():
            if str(wave) in {str(w) for w in waves} and col in columns: return col
        return None
    return base if base in columns else None

# ------------------------------------------------------------------------- logging / checks
def get_logger(step: str) -> logging.Logger:
    LOGS.mkdir(exist_ok=True)
    run_id = os.environ.get("NISR_RUN_ID") or time.strftime("%Y%m%d-%H%M%S") + "_" + step
    log = logging.getLogger(step); log.setLevel(logging.INFO)
    if not log.handlers:
        fmt = logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s", "%H:%M:%S")
        fh = logging.FileHandler(LOGS / f"run_{run_id}.log", encoding="utf-8"); fh.setFormatter(fmt); log.addHandler(fh)
        sh = logging.StreamHandler(sys.stdout); sh.setFormatter(fmt); log.addHandler(sh)
    log.info("==== %s | run %s | python %s | pandas %s | pyreadstat %s", step, run_id, sys.version.split()[0], pd.__version__, pyreadstat.__version__)
    return log

class Checks:
    def __init__(self, log): self.log, self.fails, self.warns = log, [], []
    def __call__(self, cond, msg, hard=True):
        if cond: self.log.info("PASS  %s", msg)
        elif hard: self.log.error("FAIL  %s", msg); self.fails.append(msg); raise AssertionError(msg)
        else: self.log.warning("WARN  %s", msg); self.warns.append(msg)
    def done(self):
        if self.fails: raise AssertionError(f"{len(self.fails)} check(s) failed: {self.fails}")
        self.log.info("all hard checks passed (%d soft warnings)", len(self.warns))

# ------------------------------------------------------------------------- Stata I/O
def read_dta(path, **kw):
    try: df, m = pyreadstat.read_dta(str(path), **kw)
    except UnicodeDecodeError: df, m = pyreadstat.read_dta(str(path), encoding="latin1", **kw)
    for c in df.columns:
        if df[c].dtype == object:
            v = df[c].dropna()
            if len(v) and v.map(lambda x: isinstance(x, (int, float, np.integer, np.floating))).all(): df[c] = pd.to_numeric(df[c], errors="coerce")
    return df, dict(m.column_names_to_labels), {k: dict(v) for k, v in m.variable_value_labels.items()}

_TYPE = {"int8": "Int8", "int16": "Int16", "int32": "Int32", "float": "float32", "double": "float64"}

def read_dta_typed(path, log, chunk=250_000):
    """Read a .dta in row chunks and keep Stata's own storage types (byte/int/long -> nullable Int8/16/32,
    float/double -> float32/64, strings -> object) so a multi-million-row file needs a fraction of the
    memory pyreadstat's default float64 frame would take. Returns df, var_labels, value_labels."""
    m = read_meta(path); types = m.readstat_variable_types; parts = []
    for off in range(0, m.number_rows, chunk):
        part, _, _ = read_dta(path, row_offset=off, row_limit=chunk)
        for c in part.columns:
            t = _TYPE.get(types.get(c, ""))
            if t and pd.api.types.is_numeric_dtype(part[c]):
                try: part[c] = part[c].astype("float64").astype(t) if t.startswith("Int") else part[c].astype(t)
                except (TypeError, ValueError): pass
        parts.append(part)
    df = pd.concat(parts, ignore_index=True) if len(parts) > 1 else (parts[0] if parts else pd.DataFrame(columns=m.column_names))
    del parts
    log.info("read %s: %s rows x %s vars (typed, %.1f GB in memory)", Path(path).name, f"{len(df):,}", len(df.columns), df.memory_usage(deep=False).sum() / 1e9)
    return df, dict(m.column_names_to_labels), {k: dict(v) for k, v in m.variable_value_labels.items()}

def read_meta(path):
    try: _, m = pyreadstat.read_dta(str(path), metadataonly=True)
    except UnicodeDecodeError: _, m = pyreadstat.read_dta(str(path), metadataonly=True, encoding="latin1")
    return m

def downcast_new(df: pd.DataFrame, cols) -> pd.DataFrame:
    """Smallest exact nullable integer type for the (small-coded) harmonised columns."""
    for c in cols:
        if c not in df.columns or not pd.api.types.is_numeric_dtype(df[c]): continue
        v = df[c].dropna().astype("float64")
        if len(v) and np.all(np.mod(v, 1) == 0):
            lo, hi = v.min(), v.max()
            t = "Int8" if -127 <= lo and hi <= 100 else "Int16" if -32767 <= lo and hi <= 32740 else "Int32"
            df[c] = df[c].astype("float64").round().astype(t)
        elif len(v) == 0: df[c] = df[c].astype("Int8")
    return df

def write_dta(df: pd.DataFrame, path, var_labels: dict, value_labels: dict, data_label: str, log):
    df = df.copy()
    vl = {c: (var_labels.get(c) or "")[:80] for c in df.columns}
    vv = {}
    for c, d in value_labels.items():
        if c not in df.columns or not pd.api.types.is_numeric_dtype(df[c]): continue
        dd = {}
        for k, t in d.items():
            try: kk = int(k)
            except (TypeError, ValueError): continue
            if -2147483647 <= kk <= 2147483620: dd[kk] = str(t)[:32000]
        if dd and sum(len(t) for t in dd.values()) > 30_000:
            cut = max(8, 30_000 // max(1, len(dd))); dd = {k: t[:cut] for k, t in dd.items()}
            if sum(len(t) for t in dd.values()) > 30_000: dd = {}
        if dd: vv[c] = dd
    for c in df.columns:
        if df[c].dtype == object or pd.api.types.is_string_dtype(df[c]):
            nonnull = df[c].dropna()
            if len(nonnull) and nonnull.map(lambda x: isinstance(x, (int, float, np.integer, np.floating))).all():
                df[c] = pd.to_numeric(df[c], errors="coerce"); continue
            df[c] = df[c].astype(object).where(df[c].notna(), "").astype(str)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    df.to_stata(str(path), version=118, write_index=False, data_label=data_label[:80], variable_labels=vl, value_labels=vv)
    log.info("wrote %s  (%s rows x %s vars, %.1f MB)", Path(path).name, f"{len(df):,}", len(df.columns), os.path.getsize(path) / 1e6)

def save_json(obj, path): Path(path).write_text(json.dumps(obj, indent=1, default=str))

def recode(s: pd.Series, mapping: dict) -> pd.Series:
    """Integer recode: mapping {source_code: target_code}; unmapped codes -> missing."""
    m = {int(k): int(v) for k, v in mapping.items()}
    out = pd.to_numeric(s, errors="coerce").map(m)
    return out.astype("float64")

def flat(spec: dict) -> dict:
    """{target: [sources]} -> {source: target}."""
    return {int(s): int(t) for t, ss in spec.items() for s in ss}

def rule_text(spec: dict) -> str:
    return "; ".join(f"{','.join(str(s) for s in ss)}->{t}" for t, ss in spec.items())
