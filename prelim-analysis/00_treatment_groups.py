"""Treatment groups, taken from rwa-trs/output/maps/maps-treat-sectors.py::classify() so they match
map1-map3 exactly (Bordering 42, Gates 4, Gates+ 21 after the settled-land rule, control 322,
Kigali 35 + four 2002 towns (9 sectors) excluded, Gishwati-Mukura neighbours flagged).
Writes data/Publicly-Available-NISR/Analysis/prelim/treatment_groups.csv with one row per sector:
  group: Gates | Gates+ (near_gates not gates) | Bordering (border only) | Kigali | Towns | Control
Precedence for the single label: Kigali > Towns > Gates > Gates+ > Bordering > Control.
Gishwati-Mukura neighbours stay in Control, as in map3 (flag `gish`).
Flags for every set are kept so any definition from map3 can be rebuilt."""
import importlib.util, os, sys, types
from pathlib import Path
import pandas as pd
from _common import DATA, OUT_D, REPO
sys.modules.setdefault("adjustText", types.SimpleNamespace(adjust_text=lambda *a, **k: None))
spec = importlib.util.spec_from_file_location("mts", REPO / "output/maps/maps-treat-sectors.py")
mts = importlib.util.module_from_spec(spec); spec.loader.exec_module(mts)
mts.GEO = DATA / "geo-data"                      # the module hard-codes Matteo's Dropbox path
sec, dist, pk, parks = mts.load()
L = mts.classify(sec, parks, pk)

df = sec[["sid", "sector", "district"]].copy()
for k in ["border", "gates", "near_gates", "gish", "kig_all", "kig_core", "towns"]:
    df[k] = df.sid.isin(L[k]).astype(int)
def grp(r):
    if r.kig_all: return "Kigali"
    if r.towns: return "Towns"
    if r.gates: return "Gates"
    if r.near_gates: return "Gates+"
    if r.border: return "Bordering"
    return "Control"
df["group"] = df.apply(grp, axis=1)
df["treated_any"] = ((df.border | df.near_gates) & ~df.kig_all.astype(bool) & ~df.towns.astype(bool)).astype(int)
df["control"] = (~(df.border | df.near_gates).astype(bool) & ~df.kig_all.astype(bool) & ~df.towns.astype(bool)).astype(int)
# spillover ring: non-treated, non-urban sectors whose polygon touches a treated sector (10 m tolerance)
tr_union = sec[sec.sid.isin(L["border"] | L["near_gates"])].union_all().buffer(10)
df["ring1"] = (sec.geometry.intersects(tr_union).values & (df.treated_any == 0) & (df.control == 1)).astype(int)
# clean control (main): control, not a Gishwati-Mukura neighbour, not in the spillover ring
df["control_clean"] = ((df.control == 1) & (df.gish == 0) & (df.ring1 == 0)).astype(int)
# park-border dummies for park x wave terms (sector touches that park; Gishwati-Mukura included)
for name in ["Volcanoes", "Nyungwe", "Akagera", "Gishwati-Mukura"]:
    df["border_" + name.split("-")[0].lower()] = (sec.geometry.distance(parks[name]) == 0).astype(int).values
# nearest long-standing park for park-specific panels
park_of = {}
for name in ["Volcanoes", "Nyungwe", "Akagera"]:
    d = sec.geometry.distance(parks[name]); park_of[name] = d
dd = pd.DataFrame(park_of); df["park"] = dd.idxmin(axis=1).values
df.to_csv(OUT_D / "treatment_groups.csv", index=False)
print({k: len(v) for k, v in L.items()})
print(df.group.value_counts().to_dict()); print("treated_any", df.treated_any.sum(), "control", df.control.sum(), "ring1", df.ring1.sum(), "control_clean", df.control_clean.sum())
print(df[[c for c in df if c.startswith("border_")]].sum().to_dict())
print(df[df.group.isin(["Gates", "Gates+"])].groupby(["park", "group"]).sector.apply(list).to_string())
