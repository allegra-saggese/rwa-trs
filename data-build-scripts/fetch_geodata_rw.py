"""
fetch_geodata_rw.py — pull layers from Rwanda's national geodata portal.

geodata.rw runs ArcGIS FeatureServers. They cap each response at 2,000 records,
so anything larger has to be paged with resultOffset. This handles that and
writes GeoJSON + GeoPackage in EPSG:4326.

    python fetch_geodata_rw.py --list
    python fetch_geodata_rw.py District_boundary
    python fetch_geodata_rw.py Road_network Land_Cover --out ../path/to/geo-data

The portal's native CRS is ITRF_2005 / Rwanda TM; outSR=4326 is requested so
everything lands in the same frame as the rest of the project.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import paths as P

BASE = "https://geodata.rw/server/rest/services/basemap"
DEFAULT_OUT = P.GEO
PAGE = 1000   # under the server's 2000 cap, and keeps each response small


def _log(msg: str) -> None:
    print(f"[geodata.rw] {msg}", flush=True)


def _get(url: str, timeout: int = 240) -> dict | None:
    """curl rather than urllib: the portal rejects the default python UA."""
    p = subprocess.run(["curl", "-s", "--max-time", str(timeout), url],
                       capture_output=True, text=True)
    try:
        return json.loads(p.stdout)
    except Exception:
        return None


def list_layers() -> int:
    d = _get(f"{BASE}?f=json")
    if not d:
        _log("could not read the service list")
        return 1
    names = sorted({s["name"].split("/")[-1] for s in d.get("services", [])
                    if s.get("type") == "FeatureServer"})
    _log(f"{len(names)} FeatureServer layers:")
    for n in names:
        print(f"    {n}")
    return 0


def fetch(layer: str, out_dir: Path) -> int:
    meta = _get(f"{BASE}/{layer}/FeatureServer/0?f=json")
    if not meta or "fields" not in meta:
        _log(f"{layer}: no layer 0, or not a FeatureServer")
        return 0

    cnt = _get(f"{BASE}/{layer}/FeatureServer/0/query"
               f"?where=1%3D1&returnCountOnly=true&f=json") or {}
    total = cnt.get("count", 0)
    _log(f"{layer}: {total:,} features ({meta.get('geometryType','?')})")
    if not total:
        return 0

    feats, off = [], 0
    while off < total:
        url = (f"{BASE}/{layer}/FeatureServer/0/query?where=1%3D1&outFields=*"
               f"&outSR=4326&returnGeometry=true&f=geojson"
               f"&resultOffset={off}&resultRecordCount={PAGE}")
        d = _get(url)
        got = (d or {}).get("features") or []
        if not got:
            _log(f"  stopped at offset {off:,} (no features returned)")
            break
        feats.extend(got)
        off += len(got)
        if total > PAGE:
            _log(f"  {off:,}/{total:,}")
        if len(got) < PAGE:
            break
        time.sleep(0.2)

    if not feats:
        return 0

    out_dir.mkdir(parents=True, exist_ok=True)
    gj = out_dir / f"geodatarw_{layer.lower()}.geojson"
    gj.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))

    try:
        import geopandas as gpd
        g = gpd.read_file(gj)
        g.set_crs(4326, allow_override=True).to_file(
            out_dir / f"geodatarw_{layer.lower()}.gpkg",
            layer=layer.lower(), driver="GPKG")
        _log(f"  -> geodatarw_{layer.lower()}.{{geojson,gpkg}}  {len(g):,} features")
    except Exception as exc:  # noqa: BLE001 - GeoJSON is still written
        _log(f"  -> geojson only ({type(exc).__name__})")
    return len(feats)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("layers", nargs="*", help="layer names, e.g. District_boundary")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--list", action="store_true")
    a = p.parse_args(argv)

    if a.list or not a.layers:
        return list_layers()
    for layer in a.layers:
        fetch(layer, a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
