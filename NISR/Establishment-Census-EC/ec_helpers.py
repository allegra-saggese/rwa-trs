"""
ec_helpers.py -- dataset-local helpers for the Establishment Census pipeline.

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

DATASET = "Establishment-Census-EC"
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
        if dd:
            total = sum(len(t) for t in dd.values())
            if total > 30_000:                       # pandas/Stata cap: all labels of one variable < 32,000 chars
                cut = max(8, 30_000 // max(1, len(dd)))
                dd = {k: t[:cut] for k, t in dd.items()}
                log.info("value labels on %s truncated to %d chars each (%d codes, %d chars shipped)", c, cut, len(dd), total)
                if sum(len(t) for t in dd.values()) > 30_000: log.warning("value labels on %s dropped (too many codes)", c); dd = {}
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

# ============================================================ clean variable names and labels (identical in every <ds>_helpers.py)

import re, unicodedata

STOP = {"the", "a", "an", "of", "in", "for", "to", "is", "are", "was", "were", "be", "been", "being", "do", "does", "did", "you", "your",
        "this", "that", "these", "those", "by", "on", "at", "with", "from", "and", "or", "as", "any", "per", "during", "it", "its", "into",
        "has", "have", "had", "there", "which", "what", "who", "whom", "whose", "how", "many", "much", "if", "then", "when", "where",
        "also", "only", "all", "some", "more", "most", "very", "each", "every", "same", "such", "so", "please", "specify", "specified",
        "i", "e", "g", "etc", "vs", "currently", "usually", "household's", "establishment's", "s", "de", "la", "le", "les", "du", "des",
        "et", "en", "following", "one", "ones", "name", "code", "he", "she", "his", "her", "him", "they", "them", "their", "we", "our", "me", "my",
        "person", "persons", "someone", "anyone", "anybody", "somebody", "even", "could", "would", "should", "can", "will", "shall", "might",   # "may" is kept: it is a month
        "than", "ever", "still", "yet", "just", "about", "over", "under", "up", "down", "out", "within", "without", "among", "between", "whether",
        "while", "because", "since", "until", "after", "before", "ago", "done", "get", "got", "take", "took", "taken", "give", "gave", "given", "make",
        "made", "spend", "spent", "actually", "really", "generally", "mainly", "did", "were", "kindly", "respondent's", "member", "members", "ask",
        "asked", "question", "answer", "say", "said", "state", "stated", "yes", "no", "indicate", "record", "write", "enter", "select", "choose"}
_ORDINAL = {"1": "first", "2": "second", "3": "third", "4": "fourth", "5": "fifth", "6": "sixth", "7": "seventh", "8": "eighth", "9": "ninth", "10": "tenth"}
_ORD = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)\b", re.I)
_COUNTED = re.compile(r"\b(visit|item|article|product|season|line|member|child|spouse|plot|parcel|field|crop|animal|job|round|payment|trip|source|method|methode|reason|problem|option|choice|rank|part|section|wave|phase|stage|episode|type|loan|seed|measure|activity|service|institution|code|name|person|month|year|day|week|quarter|group|category|level|grade|class|unit|tree|bird|cow|goat|pig|sheep|hive|kind|other)\s*[-_ ]?\s*(\d{1,3})\b", re.I)
GENERIC = {"total", "last", "main", "current", "own", "other", "type", "kind", "level", "number", "status", "general", "actual", "usual", "first", "second"}
_TIMEFRAME = re.compile(r"\b(in|during|over|for|within)?\s*(the)?\s*(last|past|previous|next|preceding|reference)\s+(\d+|one|two|three|four|five|six|seven|twelve|thirty)?\s*(days?|weeks?|months?|years?|hours?|hrs?|seasons?)\b", re.I)
KEEP_SHORT = {"n", "hh", "id", "kg", "ha", "m2", "km", "rwf", "usd", "vup", "isic", "isco", "gdp", "vat", "tin", "rra", "rdb", "rca", "psf", "rgb", "rssb", "ngo", "hiv", "tv"}
ABBREV = [("household", "hh"), ("agricultural", "agri"), ("agriculture", "agri"), ("expenditure", "expend"), ("production", "prod"), ("quantity", "qty"),
          ("number", "num"), ("establishment", "estab"), ("employment", "employ"), ("education", "educ"), ("information", "info"), ("organisation", "org"),
          ("organization", "org"), ("government", "govt"), ("community", "comm"), ("activities", "activ"), ("activity", "activ"), ("consumption", "consum"),
          ("transport", "transp"), ("received", "recvd"), ("months", "mo"), ("month", "mo"), ("questionnaire", "quest"), ("population", "pop"),
          ("average", "avg"), ("percentage", "pct"), ("percent", "pct"), ("secondary", "second"), ("primary", "prim"), ("international", "intl"),
          ("environment", "environ"), ("development", "devt"), ("cooperative", "coop"), ("insurance", "insur"), ("purchased", "bought"),
          ("relationship", "relation"), ("characteristics", "charact"), ("vegetables", "veg"), ("fertilizer", "fert"), ("fertiliser", "fert"),
          ("pesticide", "pest"), ("irrigation", "irrig"), ("livestock", "lvstk"), ("equipment", "equip"), ("maintenance", "maint"),
          ("registration", "regist"), ("respondent", "resp"), ("reference", "ref"), ("previous", "prev"), ("business", "biz"), ("services", "svc"),
          ("service", "svc"), ("workers", "wkrs"), ("worker", "wkr"), ("employees", "emps"), ("employee", "emp"), ("foreigner", "foreign")]
# French / Kinyarwanda -> English for label text (whole words, case-insensitive); extend per dataset in TRANSLATE_EXTRA
TRANSLATE = {"secteur": "sector", "menage": "household", "ménage": "household", "taille du ménage": "household size", "taille du menage": "household size",
             "identifiant du menage": "household id", "identifiant du ménage": "household id", "relation avec le cm": "relationship to the household head",
             "niveau de pauvreté": "poverty level", "niveau de pauvrete": "poverty level", "niveau d'instruction": "level of education",
             "montant des dépenses": "amount spent", "montant des depenses": "amount spent", "au cours des": "in the last", "dern.": "last",
             "semaines": "weeks", "semaine": "week", "mois": "months", "année": "year", "annee": "year", "ans": "years", "oui": "yes", "non": "no",
             "autres": "other", "autre": "other", "pays": "country", "enfants": "children", "enfant": "child", "femme": "woman", "homme": "man",
             "âge": "age", "activité principale": "main activity", "activité": "activity", "travail": "work", "emploi": "employment", "dernier": "last",
             "dépenses": "expenditure", "depenses": "expenditure", "nombre": "number", "chef de ménage": "household head", "cm": "household head",
             "y-a-t-il eu": "were there", "wh pays": "who pays", "province": "province", "district": "district", "afrique": "africa", "europe": "europe",
             "asie": "asia", "amérique": "america", "amerique": "america", "océanie": "oceania", "autres pays": "other countries",
             "des": "of the", "du": "of the", "de": "of", "la": "the", "le": "the", "les": "the", "une": "a", "un": "a", "dans": "in", "avec": "with", "pour": "for",
             "sur": "on", "et": "and", "ou": "or", "vous": "you", "votre": "your", "combien": "how many", "quel": "which", "quelle": "which",
             "est-ce que": "", "dern": "last", "ménages": "households", "menages": "households", "personnes": "persons", "personne": "person"}

_FRENCH = re.compile(r"(?<![a-z])(le|la|les|des|du|une|dans|avec|pour|sur|aux|vous|votre|quel|quelle|combien|est-ce|y-a-t-il|nombre de|au cours|dern\.|ménage|menage|chef de|autres?|niveau|pays|afrique|europe|asie|amérique|amerique|océanie|oceanie|d'instruction|d'[a-z]|l'[a-z]|dépenses|depenses|activité|secteur|taille)(?![a-z])", re.I)
KINYARWANDA = {"yego": "yes", "oya": "no", "urajwe": "fallow", "marakuja": "passion fruit", "ingano y'ibyahinduwe": "quantity transformed",
               "izindi mboga zerera igihembwe zitamara umwaka mu murima zivuge": "other seasonal vegetable", "ubwoko bw'ifumbire y'imborera": "type of organic fertiliser",
               "umurenge": "sector", "akarere": "district", "intara": "province", "akagari": "cell", "umudugudu": "village", "urugo": "household"}
def _translate(s, extra=None):
    """French -> English only when the text reads as French (function words or accents); Kinyarwanda words always.
    A whole label listed in the dataset's own dictionary (extra) is replaced first, exactly."""
    if extra:
        fold = lambda x: re.sub(r"\s+", " ", _QNUM.sub("", _ascii(str(x).replace("\u2019", "'")))).strip().lower()
        key = fold(s)
        hit = next((v for k, v in extra.items() if not k.startswith("re:") and fold(k) == key), None)
        if hit is not None: return hit
        for k, v in extra.items():                                   # "re:<pattern>" rows: regular expressions applied to the whole label
            if k.startswith("re:"):
                s2, n = re.subn(k[3:], v, s)
                if n: return s2
    words = {k: v for k, v in (extra or {}).items() if not k.startswith("re:")}       # whole-label rows only match whole labels
    for k, v in sorted({**KINYARWANDA, **{k: v for k, v in words.items() if k in KINYARWANDA}}.items(), key=lambda kv: -len(kv[0])):
        s = re.sub(r"(?<![A-Za-z'])" + re.escape(k) + r"(?![A-Za-z])", lambda m, v=v: v, s, flags=re.I)
    if _FRENCH.search(s) or re.search(r"[àâçéèêëîïôûùüÿœ]", s, re.I):
        for k, v in sorted({**TRANSLATE, **words}.items(), key=lambda kv: -len(kv[0])):
            s = re.sub(r"(?<![A-Za-z'])" + re.escape(k) + r"(?![A-Za-z])", lambda m, v=v: v, s, flags=re.I)
    return s

def _ascii(s):
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()

# a leading question / item code: optional 1-4 letters (with optional dot), digits, then segments that carry a digit or a single
# letter suffix, then separators -- "Q22A Sector", "2.7 Sowing", "4_14A. At which", "S4_09_2/Heat", "GS13_15 Yesterday", "2.15.v.6 Which",
# "A.2x City", "s1q3. Age", "0.16.1 Agricultural". Applied to the ORIGINAL text (underscores intact), only when real text remains.
_QNUM = re.compile(r"^\s*(?:q(?:uestion)?\.?\s*)?(?:[a-z]{1,4}\.?)?\d+(?:[._\-]?(?:[a-z]{1,2}\d{1,3}|\d{1,3}|[a-z]\b))*(?=[\s.:/)\-_,]|$)[\s.:/)\-_,]*", re.I)

def clean_label(text, tag, extra=None):
    """Plain English sentence for a variable label: question numbers, brackets, codes and version tags removed,
    French / Kinyarwanda translated, '[NAME]' -> 'the person', tidy spacing and case; returns text WITHOUT the tag prefix."""
    s = "" if text is None else str(text)
    if not s.strip(): return ""
    s2 = _QNUM.sub("", s)
    if re.search(r"[a-z]{2}", s2, re.I) and not re.match(r"^\s*\d+\s+[a-z]", s, re.I): s = s2      # strip the item code only when text remains; "2 weeks" is text
    s3 = re.sub(r"^\s*[A-Za-z]{1,3}\d+(?:_\d+)*(?:_[a-z]{1,3}\d*)*\s*[/:\-]?\s*(?=[A-Za-z])", "", s)        # "AS10_05_4/May of 2023", "Q1_13Age1", "S8_09_1 If yes"
    if s3 != s and re.search(r"[a-z]{3}", s3, re.I): s = s3
    s = re.sub(r"\s*[\[(]\s*(NAME|CHILD_?NAME|MEMBER|ITEM\s*NAME|you\s*/\s*name|name\s*/\s*you)\s*[\])]\s*", " the person ", s, flags=re.I)
    s = re.sub(r"\bhe\s*/\s*she\b", "the person", s, flags=re.I); s = re.sub(r"\bhis\s*/\s*her\b", "their", s, flags=re.I)
    s = re.sub(r"\bhim\s*/\s*her\b", "them", s, flags=re.I); s = re.sub(r"\bis\s*/\s*was\b", "is", s, flags=re.I)
    s = re.sub(r"\?(?=[A-Za-z])", "? ", s)
    s = re.sub(r"\[[^\]]*version[^\]]*\]", " ", s, flags=re.I)                        # "[2024-2025 version]"
    s = re.sub(r"\[from [^\]]*\]|\[not shipped[^\]]*\]|\[not in [^\]]*\]", " ", s, flags=re.I)
    s = re.sub(r"[\[\]{}|]", " ", s)
    s = s.replace("--", ";").replace("_", " ")
    s = re.sub(r"\s*\?\s*s\b", "'s", s); s = re.sub(r"\s+'s\b", "'s", s)          # "person ? s" / "person 's" -> "person's"
    s = _translate(s, extra)
    if sum(ch.isupper() for ch in s) > 0.6 * max(1, sum(ch.isalpha() for ch in s)): s = s.lower()      # ALL-CAPS source label -> sentence case
    s = re.sub(r"\bhh\.?\b", "household", s); s = re.sub(r"\bnisr\b", "NISR", s); s = re.sub(r"\bisic\b", "ISIC", s); s = re.sub(r"\bisco\b", "ISCO", s)
    s = _ORD.sub(lambda m: _ORDINAL.get(m.group(1), m.group(0)), s)                   # "1st shock" -> "first shock"
    s = re.sub(r"\s+", " ", s).strip(" .;:,-/")
    s = _ascii(s)
    s = _acronyms(s)
    if s: s = s[0].upper() + s[1:]
    return s

ACRONYMS = ["isic", "isco", "nisr", "vup", "tpr", "paye", "rra", "rdb", "rca", "psf", "rgb", "rssb", "ngo", "vat", "tin", "gdp", "hiv", "aids", "eicv", "lfs",
            "cfsva", "ahs", "sas", "phc", "gps", "psu", "ppp", "usd", "rwf", "wfp", "fao", "ilo", "ict", "tvet", "sme", "ebm", "nid", "sacco", "bnr", "mfi",
            "vsla", "fcs", "cari", "rcsi", "hdds", "wdds", "muac", "iycf", "bmi", "ddi", "eicv1", "eicv2", "eicv3", "eicv4", "eicv5", "eicv7", "pca", "rdhs", "dhs"]
_ACR = re.compile(r"\b(" + "|".join(ACRONYMS) + r")\b", re.I)
def _acronyms(s):
    return _ACR.sub(lambda m: m.group(1).upper(), s)

def make_slug(label, tag, native="", maxlen=32):
    """Name from a clean label: content words joined by underscores, prefixed with the dataset tag, <= maxlen and never
    cut inside a word. Time-frame phrases ('in the last 7 days'), stopwords and standalone numbers are dropped; if the
    name still does not fit, generic words (total, main, type ...) are dropped, then the abbreviation table is applied
    word by word (longest words first), then trailing words are dropped."""
    text = _TIMEFRAME.sub(" ", _ascii(label).lower())
    text = _COUNTED.sub(lambda m: f"{m.group(1)}{m.group(2)}", text)                       # "visit 2" -> visit2, "item 3" -> item3
    words = [w for w in re.sub(r"[^a-z0-9]+", " ", text).split() if w and w not in STOP and not w.isdigit()]
    if not words: words = [w for w in re.sub(r"[^a-z0-9]+", " ", _ascii(label).lower()).split() if w and w not in STOP]
    if not words and not str(label).strip(): return _fix(f"{tag}_unlabelled_" + re.sub(r"[^a-z0-9]+", "_", str(native).lower()))[:maxlen]
    if not words: words = [w for w in re.sub(r"[^a-z0-9]+", " ", str(native).lower()).split()] or ["var"]
    def join(ws): return _fix(f"{tag}_" + "_".join(ws))
    if len(join(words)) <= maxlen: return join(words)
    words2 = [w for w in words if w not in GENERIC] or words
    if len(join(words2)) <= maxlen: return join(words2)
    ws = list(words2)
    for full, ab in sorted(ABBREV, key=lambda p: -len(p[0])):
        if len(join(ws)) <= maxlen: break
        ws = [ab if w == full else w for w in ws]
    keep_last = ws[-1] if len(ws) > 1 and re.search(r"\d", ws[-1]) else None      # "visit2", "item3", "2nd": the counted token is what distinguishes the item
    body = ws[:-1] if keep_last else ws
    out = []
    for w in body:                                           # keep whole words while they fit
        if len(join(out + [w] + ([keep_last] if keep_last else []))) <= maxlen: out.append(w)
        else: break
    if keep_last: out.append(keep_last)
    if not out: out = [ws[0][:maxlen - len(tag) - 1]]          # a single word longer than the budget: cut it (rare)
    return join(out)

def cut(name, maxlen):
    """cut a name at a word boundary so that it fits maxlen"""
    if len(name) <= maxlen: return name
    c = name[:maxlen]
    return c[:c.rfind("_")] if "_" in c[1:] and c.rfind("_") > len(name.split("_")[0]) else c

def _fix(name):
    name = re.sub(r"_+", "_", name).strip("_")
    if name[len(name.split("_")[0]) + 1:][:1].isdigit(): name = name.split("_")[0] + "_n" + name[len(name.split("_")[0]) + 1:]   # tag_2017 -> tag_n2017
    return name

_TF = re.compile(r"\b(?:in|during|over|within|for)?\s*(?:the\s+)?(last|past|previous|preceding|next)\s+(\d+|one|two|three|four|five|six|seven|twelve|thirty)?\s*(days?|weeks?|months?|years?|hours?|seasons?)\b\s*,?\s*", re.I)
_SCAFFOLD = [r"^(what|which|who|whom|when|where|why|how many|how much|how long|how often|how soon)\s+(is|are|was|were|does|do|did|has|have|had|would|could|will|can)?\s*(the person|you|your|their|the|this|that)?\s*",
             r"^(did|does|do|is|are|was|were|has|have|had|will|would|could|can)\s+(the person|you|your household|the household|this household|anyone|someone|he|she|it)\s+",
             r"\((?:do|does|have|has|is|are|was|were)\s*/\s*(?:do|does|have|has|is|are|was|were)\)\s*", r"\b(please|kindly)\s+(specify|indicate|state|record)\b", r"\bin your opinion,?\s*",
             r"\s*\([^)]*\)"]
def compress_label(text, room):
    """A long question shortened to a descriptive phrase that fits `room`: the time frame ('last 7 days') is moved to
    the end, question scaffolding ('During the past 7 days, did the person ...', 'How many ... does the person') and
    parenthetical asides are removed step by step, and only then is the text cut at a clause or word boundary."""
    s = re.sub(r"\s+", " ", str(text)).strip()
    if len(s) <= room: return s
    m = _TF.search(s); tf = ""
    if m:
        tf = f"{m.group(1).lower()} {m.group(2) + ' ' if m.group(2) else ''}{m.group(3).lower()}"; s = _TF.sub(" ", s, count=1)
    s = re.sub(r"\s+", " ", s).strip(" ,;:-")
    for pat in _SCAFFOLD:
        if len(s) + (len(tf) + 2 if tf else 0) <= room: break
        s = re.sub(pat, "", s, flags=re.I); s = re.sub(r"\s+", " ", s).strip(" ,;:-?")
    s = s.rstrip("?").strip(" ,;:-")
    if tf and len(s) + len(tf) + 2 <= room: s = f"{s}, {tf}"
    if len(s) > room:
        c = s[:room]; k = max(c.rfind(";"), c.rfind(","))
        s = (c[:k] if k > room // 2 else c.rsplit(" ", 1)[0]).rstrip(" ,;:-")
    return s[:1].upper() + s[1:]

def label_with_tag(tag_upper, clean, years=None, maxlen=80):
    """'EICV 2011-2017: text' or 'EICV: text'; a text that does not fit is compressed (compress_label), never cut mid-word."""
    head = f"{tag_upper}{' ' + years if years else ''}: "
    body = compress_label(clean, maxlen - len(head))
    return head + (body[:1].upper() + body[1:])

def _words(label):
    text = _COUNTED.sub(lambda m: f"{m.group(1)}{m.group(2)}", _TIMEFRAME.sub(" ", _ascii(label).lower()))
    return [w for w in re.sub(r"[^a-z0-9]+", " ", text).split() if w and w not in STOP and not w.isdigit()]

def assign_names(tag, items, maxlen=32):
    """items: list of (native, clean_label). Returns the list of unique clean names for one file: the slug of the label;
    where labels give the same slug, the distinguishing words of each label are added, then the numeric suffix of the
    native name (item 1, 2, ...), then the native code itself."""
    slugs = [make_slug(l, tag, n, maxlen) for n, l in items]
    groups = {}
    for i, s in enumerate(slugs): groups.setdefault(s, []).append(i)
    out = list(slugs)
    for s, idx in groups.items():
        if len(idx) == 1: continue
        common = set.intersection(*[set(_words(items[i][1])) for i in idx])
        for i in idx:
            ws = _words(items[i][1]); distinct = [w for w in ws if w not in common][:3]
            head = [w for w in ws if w in common][:2]
            cand = make_slug(" ".join(head + distinct), tag, items[i][0], maxlen) if distinct else s
            m = re.search(r"(\d+[a-z]?)$", str(items[i][0]))
            if cand == s and m: cand = cut(s, maxlen - len(m.group(1)) - 1) + "_" + m.group(1)
            out[i] = cand
        seen = {}
        for i in idx:                                         # still identical -> the native code
            if out[i] in seen or out[i] in [out[j] for j in range(len(out)) if j not in idx]:
                suf = "_" + re.sub(r"[^a-z0-9]+", "", str(items[i][0]).lower())[:10]
                out[i] = cut(out[i], maxlen - len(suf)) + suf
            seen[out[i]] = 1
    return unique_names(out, [n for n, _ in items], maxlen)

def unique_names(names, natives, maxlen=32):
    """Resolve collisions inside one file: the second occurrence gets the native code as suffix."""
    seen, out = {}, []
    for n, nat in zip(names, natives):
        if n not in seen: seen[n] = 1; out.append(n); continue
        suf = "_" + re.sub(r"[^a-z0-9]+", "", str(nat).lower())[:8]
        cand = cut(n, maxlen - len(suf)) + suf
        k = 2
        while cand in seen: cand = cut(n, maxlen - len(suf) - 2) + suf + str(k); k += 1
        seen[cand] = 1; out.append(cand)
    return out

_VL_CODE = re.compile(r"^\s*(?:\d+|[a-z])\s*[.:)\-=]\s+(?=\S)", re.I)     # "1. Yes", "01 - Rural", "a) Cattle"
def clean_value_label(text, extra=None):
    """Plain English category text: leading code removed, translated, tidy spacing and sentence case."""
    s = "" if text is None else str(text)
    s = _VL_CODE.sub("", s)
    s = re.sub(r"[\[\]{}|]", " ", s).replace("_", " ")
    s = _translate(s, extra)
    if sum(ch.isupper() for ch in s) > 0.6 * max(1, sum(ch.isalpha() for ch in s)): s = s.lower()
    s = re.sub(r"\s+", " ", s).strip(" .;:,-/")
    s = _acronyms(_ascii(s))
    if s: s = s[0].upper() + s[1:]
    return s

def version_suffix(waves, wave_year):
    """'_2017_2020' or '_2023' from the waves of one version (wave_year maps wave ids to survey years)."""
    ys = sorted({int(wave_year(w)) for w in waves})
    return f"_{ys[0]}" if len(ys) == 1 or ys[0] == ys[-1] else f"_{ys[0]}_{ys[-1]}"

def versioned(name, suffix, maxlen=32):
    return cut(name, maxlen - len(suffix)) + suffix

# ------------------------------------------------------------ the name table (variable_names.csv next to the code)
import csv as _csv
from pathlib import Path as _Path

# Stems reserved for the harmonised concepts written by NISR/Harmonize (<ds>_<stem>, the same stem in every
# dataset). A native variable must never take one of them: the harmonised variable would collide with it.
# Two exceptions are deliberate and checked there: sex and head_sex / head_age are already in the common
# coding, so the dataset's own columns ARE the harmonised ones and are harmonised in place.
HARMONISED_STEMS = {"marital_status", "relationship_to_head", "school_attendance", "education_level", "literacy",
                    "labour_status", "employed", "labour_definition", "employment_status", "industry_isic",
                    "industry_isic_approx", "occupation_isco", "occupation_isco_approx", "head_marital_status",
                    "head_education_level", "head_literacy", "household_key", "person_key"}

KEY_STEMS = {   # native key-block / derived names -> clean stem (the dataset tag is prefixed) and label text
    "survey": ("survey", "Source survey"), "year": ("year", "Survey year"), "wave": ("wave", "Wave identifier"),
    "sample": ("sample", "Sample component"), "unit": ("unit", "Unit of observation of the file"),
    "prov": ("province", "Province, NISR code 1-5"), "dist": ("district", "District, NISR code 11-57"),
    "sector": ("sector", "Sector, NISR code 1101-5715"), "urban": ("urban", "Area of residence: 1 urban, 2 rural"),
    "cluster": ("cluster", "Sampling cluster or village identifier"), "psu": ("psu", "Primary sampling unit"), "stratum": ("stratum", "Sampling stratum"),
    "hhid": ("household_id", "Household identifier"), "pid": ("person_id", "Person number within the household"),
    "estid": ("establishment_id", "Establishment identifier"), "sex": ("sex", "Sex: 1 male, 2 female"), "age": ("age", "Age in completed years"),
    "wt": ("weight", "Sampling weight"), "wt_hh": ("household_weight", "Household weight"), "wt_round": ("round_weight", "Round weight"),
    "hhsize": ("household_size", "Household size (persons in the roster)"), "head_sex": ("head_sex", "Sex of the household head"),
    "head_age": ("head_age", "Age of the household head"), "interview": ("interview", "Interview number of the household in the year"),
    "round": ("round", "Data collection round"), "quarter": ("quarter", "Quarter of the round"), "season": ("season", "Agricultural season"),
    "farm_type": ("farm_type", "Farm type: 1 small-scale, 2 large-scale"), "segment": ("segment", "Segment or list-frame identifier"),
    "holder": ("holder", "Holder or questionnaire identifier"), "plot": ("plot", "Plot number"), "crop": ("crop", "Crop code of the wave's own list"),
    "crop_name": ("crop_name", "Crop name"), "crop_list": ("crop_code_list", "Crop code list generation"), "record_type": ("record_type", "Record type of the shipped file"),
    "source_module": ("source_file", "Shipped file the row comes from"), "wt_source": ("weight_source", "Where the plot weight came from"),
}

class NameTable:
    """native <-> clean names per scope ('wave:<id>' for a per-wave file, 'pooled:<file>' for a pooled file)."""
    def __init__(self, path, tag):
        self.path, self.tag, self.rows = _Path(path), tag, []
        if self.path.exists():
            with open(self.path, newline="", encoding="utf-8") as fh: self.rows = list(_csv.DictReader(fh))
        self.by_scope = {}
        for r in self.rows: self.by_scope.setdefault(r["scope"], {})[r["native"]] = r
    def save(self):
        with open(self.path, "w", newline="", encoding="utf-8") as fh:
            wr = _csv.DictWriter(fh, fieldnames=["scope", "wave", "native", "clean_name", "clean_label", "native_label"]); wr.writeheader(); wr.writerows(self.rows)
    def clean(self, scope):   return {n: r["clean_name"] for n, r in self.by_scope.get(scope, {}).items()}
    def labels(self, scope):  return {r["clean_name"]: r["clean_label"] for r in self.by_scope.get(scope, {}).values()}
    def native(self, scope):  return {r["clean_name"]: n for n, r in self.by_scope.get(scope, {}).items()}
    def apply(self, df, vl, vv, scope, log=None, extra=None):
        """rename a native-named frame to clean names and labels (value labels cleaned); unlisted columns get engine names"""
        if extra is None: extra = globals().get("TRANSLATE_EXTRA") or {}                  # the dataset's own dictionary (value_label_translations.csv)
        m = dict(self.clean(scope)); labs = self.labels(scope); used = set(m.values()); tagU = self.tag.upper()
        missing = [c for c in df.columns if c not in m]
        if missing:
            names = assign_names(self.tag, [(c, clean_label(vl.get(c, "") or c, self.tag, extra)) for c in missing])
            for c, n in zip(missing, names):
                k = 2
                while n in used: n = cut(n, 30) + f"_{k}"; k += 1
                m[c] = n; used.add(n); labs[n] = label_with_tag(tagU, clean_label(vl.get(c, "") or c, self.tag, extra))
                if log: log.warning("%s: variable %r not in variable_names.csv -> named %r", scope, c, n)
        df = df.rename(columns=m)
        vl2 = {m.get(c, c): labs.get(m.get(c, c), label_with_tag(tagU, clean_label(vl.get(c, ""), self.tag, extra))) for c in m}
        vv2 = {m.get(c, c): {k: clean_value_label(t, extra) for k, t in d.items()} for c, d in vv.items() if c in m}
        return df, vl2, vv2, m
    def invert(self, df, vl, vv, scope):
        """clean-named frame back to native names (labels as stored in the file)"""
        inv = self.native(scope)
        df = df.rename(columns=inv); vl = {inv.get(c, c): t for c, t in vl.items()}; vv = {inv.get(c, c): d for c, d in vv.items()}
        return df, vl, vv


# ------------------------------------------------------------ dataset-specific naming constants
DATASET_TAG = "ec"
WAVE_YEAR = lambda w: int(str(w)[:4])                     # wave id -> survey year
TRANSLATE_EXTRA = {}
KEY_EXTRA = {"key": ("nisr_establishment_key", "NISR establishment key as shipped (2011 and 2014)"),
             "year_nisr": ("nisr_year_variable", "NISR variable named year as shipped, a year-of-start group"),
             "geo_conflict_2011": ("district_name_conflict_2011", "District code disagreed with the district name; the names were used"),
             "prov_derived": ("province_derived", "Province derived from the district code where missing"),
             "cell_seq_2011": ("cell_sequence_2011", "Cell sequence within the sector as shipped"),
             "village_seq_2011": ("village_sequence_2011", "Village sequence within the cell as shipped")}

