"""Treatment-definition maps: treatment_definitions.pdf, exclusion_definitions.pdf, estimation_samples.pdf
in Dropbox output/maps/. The definitions themselves are in helpers/treatment_groups.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
from treatment_groups import *  # noqa: F401,F403

sec, dist, pk, parks = load()
L = classify(sec, parks, pk[pk.geometry.area > 1e5])
print({k: len(v) for k, v in sorted(L.items())})
map1(sec, dist, pk, parks, L)
map2(sec, dist, pk, parks, L)
map3(sec, dist, pk, parks, L)
print("written to", OUT)
