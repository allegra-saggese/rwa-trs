"""
inventory.py — scan the NISR data folder and index every file and variable.

Reads metadata only (no data rows), so a full scan of several GB takes seconds
rather than minutes. Produces two outputs:

    docs/data_inventory.md          one row per file: rows, vars, encoding
    data/processed/variable_index.csv   one row per VARIABLE across every file

The variable index is the thing to grep. It answers "which files have an ISCO
variable", "what is s6bq3 called in EICV5", "does the census carry literacy"
without opening Stata.

Usage
-----
    python inventory.py                      # scan the default root
    python inventory.py --root /some/path    # scan elsewhere
    python inventory.py --find isco          # search the existing index
    python inventory.py --find "poverty|pov_" --regex

Why metadata only
-----------------
`pyreadstat` can read a .dta/.sav header without materialising rows. The Census
2022 file is 1.3M x 250; reading it in full to learn its column names would be
wasteful and, for the 3 GB Census folder, slow enough to discourage re-running.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent
PROC = REPO / "data" / "processed"
DOCS = REPO / "docs"

# Default location of the NISR holdings. Data lives outside the repo on purpose:
# NISR and DHS microdata are licensed to the individual researcher, and a git
# repo is the wrong place for 5 GB of restricted files.
DEFAULT_ROOT = Path(
    "/Users/allegrasaggese/Library/CloudStorage/Dropbox/Rwanda - TRS/"
    "data/Publicly Available NISR"
)

READABLE = {".dta", ".sav", ".csv"}

# NISR files mix encodings: EICV and Census .dta carry latin-1 accented value
# labels that fail a strict utf-8 read, while some .sav files are clean utf-8.
# Order matters - utf-8 first so correctly-encoded files are not mangled.
ENCODINGS = (None, "latin1", "cp1252")

INDEX_PATH = PROC / "variable_index.csv"


def _log(msg: str) -> None:
    print(f"[inventory] {msg}", flush=True)


# --------------------------------------------------------------------------
# Metadata reading
# --------------------------------------------------------------------------

def read_metadata(fp: Path):
    """Return (metadata, encoding_used) for a .dta/.sav, trying each encoding.

    Raises the last exception if every encoding fails, so an unreadable file is
    reported rather than silently skipped.
    """
    import pyreadstat

    reader = pyreadstat.read_dta if fp.suffix.lower() == ".dta" else pyreadstat.read_sav
    last: Exception | None = None
    for enc in ENCODINGS:
        try:
            kwargs = {"metadataonly": True}
            if enc:
                kwargs["encoding"] = enc
            _, meta = reader(fp, **kwargs)
            return meta, (enc or "utf-8")
        except Exception as exc:  # noqa: BLE001 - trying the next encoding is the point
            last = exc
    raise last  # type: ignore[misc]


def scan(root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Walk `root` and index every readable file and every variable in it."""
    files = sorted(p for p in root.rglob("*")
                   if p.suffix.lower() in READABLE and not p.name.startswith("."))
    _log(f"scanning {len(files)} file(s) under {root}")

    file_rows, var_rows = [], []

    for fp in files:
        rel = fp.relative_to(root)
        # Top-level folder is the dataset family (EICV, LFS, Census, ...).
        family = rel.parts[0] if len(rel.parts) > 1 else "(root)"
        # Second part distinguishes Raw / Cleaned / Merged Panel.
        stage = rel.parts[1] if len(rel.parts) > 2 else ""

        if fp.suffix.lower() == ".csv":
            try:
                head = pd.read_csv(fp, nrows=0)
                n_rows = sum(1 for _ in open(fp, encoding="utf-8", errors="replace")) - 1
                cols, labels, enc = list(head.columns), {}, "utf-8"
            except Exception as exc:  # noqa: BLE001
                _log(f"  ! {rel}: {type(exc).__name__}")
                continue
        else:
            try:
                meta, enc = read_metadata(fp)
            except Exception as exc:  # noqa: BLE001
                _log(f"  ! {rel}: {type(exc).__name__}: {str(exc)[:70]}")
                file_rows.append({"family": family, "stage": stage, "file": str(rel),
                                  "n_rows": None, "n_vars": None, "encoding": "FAILED",
                                  "size_mb": round(fp.stat().st_size / 1e6, 1)})
                continue
            cols = list(meta.column_names)
            labels = dict(meta.column_names_to_labels or {})
            n_rows = meta.number_rows

        file_rows.append({
            "family": family, "stage": stage, "file": str(rel),
            "n_rows": n_rows, "n_vars": len(cols), "encoding": enc,
            "size_mb": round(fp.stat().st_size / 1e6, 1),
        })
        for c in cols:
            var_rows.append({
                "family": family, "stage": stage, "file": str(rel),
                "variable": c, "label": (labels.get(c) or "").strip(),
            })

    return pd.DataFrame(file_rows), pd.DataFrame(var_rows)


# --------------------------------------------------------------------------
# Outputs
# --------------------------------------------------------------------------

def write_outputs(files: pd.DataFrame, variables: pd.DataFrame, root: Path) -> None:
    PROC.mkdir(parents=True, exist_ok=True)
    DOCS.mkdir(parents=True, exist_ok=True)

    variables.to_csv(INDEX_PATH, index=False)
    _log(f"-> {INDEX_PATH.relative_to(REPO)} ({len(variables):,} variable records)")

    lines = [
        "# NISR data inventory", "",
        "Generated by `python inventory.py`. Do not hand-edit.", "",
        f"**Root:** `{root}`  ",
        f"**Files indexed:** {len(files)}  ",
        f"**Variable records:** {len(variables):,}  ",
        f"**Distinct variable names:** {variables['variable'].nunique():,}", "",
        "Search the index with `python inventory.py --find <pattern>`.", "",
    ]

    for family, g in files.groupby("family"):
        total = g["n_rows"].sum(skipna=True)
        lines += ["", f"## {family}", "",
                  f"{len(g)} file(s), {g['size_mb'].sum():,.0f} MB, "
                  f"{total:,.0f} total rows", "",
                  "| File | Rows | Vars | Enc |", "|---|---:|---:|---|"]
        for r in g.sort_values("file").itertuples():
            rows = f"{r.n_rows:,}" if pd.notna(r.n_rows) else "—"
            nv = f"{r.n_vars:,.0f}" if pd.notna(r.n_vars) else "—"
            lines.append(f"| `{Path(r.file).name}` | {rows} | {nv} | {r.encoding} |")

    (DOCS / "data_inventory.md").write_text("\n".join(lines) + "\n")
    _log(f"-> docs/data_inventory.md")


def find(pattern: str, regex: bool = False, limit: int = 60) -> int:
    """Search the variable index by name or label."""
    if not INDEX_PATH.exists():
        _log("no index yet - run `python inventory.py` first")
        return 1

    idx = pd.read_csv(INDEX_PATH).fillna("")
    pat = pattern if regex else re.escape(pattern)
    hit = idx[idx["variable"].str.contains(pat, case=False, regex=True, na=False)
              | idx["label"].str.contains(pat, case=False, regex=True, na=False)]

    if hit.empty:
        print(f"no match for {pattern!r}")
        return 0

    print(f"{len(hit)} match(es) for {pattern!r}"
          f"{'' if len(hit) <= limit else f' — showing {limit}'}\n")
    for r in hit.head(limit).itertuples():
        print(f"  {r.variable:22s} {Path(r.file).name[:38]:40s} {str(r.label)[:48]}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    p.add_argument("--find", metavar="PATTERN", help="search the existing index")
    p.add_argument("--regex", action="store_true", help="treat --find as a regex")
    args = p.parse_args(argv)

    if args.find:
        return find(args.find, args.regex)

    if not args.root.exists():
        _log(f"root not found: {args.root}")
        return 1

    files, variables = scan(args.root)
    write_outputs(files, variables, args.root)
    _log(f"done: {len(files)} files, {len(variables):,} variable records")
    return 0


if __name__ == "__main__":
    sys.exit(main())
