"""
score_layers.py — precompute the crime / crowd / functionality layers for the
best-fit wall candidates and write them to data/wall_scores.json.

The three scoring layers (backend/scoring/{crime,crowd,functionality}.py) each hit
external open-data APIs (Somerville Socrata crime, US Census geocoder, Overpass/OSM,
MBTA V3, Somerville permits/zoning, Ookla tiles). Computing them live per request is
slow and flaky, so we precompute once into a sidecar that backend/main.py reads and
blends into the 4-layer story + headline score.

Time-of-day matters: crime is shift-gated and functionality is quiet-hours-gated, so
those two are computed for each of the frontend FilterBar hours (HOURS). Crowd is
time-independent and computed once per wall.

Run from the repo root with the backend venv:

    backend/.venv/bin/python scripts/score_layers.py [--limit N] [--all]

Re-run any time to refresh. Network hiccups on a single wall/layer fall back to a
neutral score (with a transparent reason) so one failure never tanks the whole run.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Make `backend` importable when run as a plain script from the repo root.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.scoring import crime, crowd, functionality  # noqa: E402

DATA = REPO_ROOT / "data" / "wall_candidates.json"
OUT = REPO_ROOT / "data" / "wall_scores.json"
CRIME_CACHE = REPO_ROOT / "backend" / "data" / "cache" / "crime.parquet"

# Frontend FilterBar hours; the time-dependent layers are precomputed for each.
HOURS = [12, 15, 18, 21]
DEFAULT_LIMIT = 40  # match the number of surfaces the frontend renders


def _ls(obj) -> dict:
    """LayerScore dataclass -> plain dict."""
    return {"score": round(float(obj.score), 1), "reasons": list(obj.reasons)}


def _neutral(layer: str) -> dict:
    return {"score": 70.0, "reasons": [f"{layer} data unavailable — neutral default."]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                    help="number of top projectable walls (by total_score) to score")
    ap.add_argument("--all", action="store_true", help="score every projectable wall")
    args = ap.parse_args()

    walls = json.loads(DATA.read_text())
    # Assign ids exactly as backend/main.py load() does (file-order index), so the
    # sidecar keys line up with what /api/spots serves.
    for i, w in enumerate(walls):
        w.setdefault("id", f"{w['zone']}-{i}")
    pool = [w for w in walls if w.get("projectable")]
    pool.sort(key=lambda w: -w.get("total_score", 0))
    if not args.all:
        pool = pool[: args.limit]
    print(f"Scoring {len(pool)} walls × {len(HOURS)} hours {HOURS}\n")

    # ── build crime index once (cache if present, else live) ──────────────────
    print("Loading Somerville crime data + building risk index...")
    cache = str(CRIME_CACHE) if CRIME_CACHE.exists() else None
    incidents = crime.load_crime_incidents(cache_path=cache)
    crime_index = crime.build_crime_index(incidents)
    print(f"  {len(incidents):,} incidents | baseline={crime_index.baseline:.3f} "
          f"p75={crime_index.risk_scale:.3f}")

    # ── warm functionality caches once (permits, zoning, Ookla tiles) ─────────
    print("Warming functionality caches (permits, zoning, Ookla)...")
    for name, fn in (("permits", functionality.load_event_permits),
                     ("zoning", functionality.load_zoning),
                     ("ookla", functionality.load_ookla)):
        try:
            fn()
            print(f"  {name} ok")
        except Exception as e:  # noqa: BLE001
            print(f"  {name} FAILED ({e}) — functionality will fall back per wall")

    out: dict[str, dict] = {}
    t0 = time.time()
    for i, w in enumerate(pool, 1):
        wid, lat, lon = w["id"], w["lat"], w["lon"]
        print(f"[{i}/{len(pool)}] {wid} ({lat:.5f},{lon:.5f})")

        # crowd — time-independent, the slow one (Overpass)
        try:
            crowd_ls = _ls(crowd.score_crowd(lat, lon))
        except Exception as e:  # noqa: BLE001
            print(f"    crowd failed: {e}")
            crowd_ls = _neutral("Crowd-dynamics")

        # crime block resolution — once per wall
        try:
            block = crime.latlng_to_block(lat, lon)
        except Exception as e:  # noqa: BLE001
            print(f"    geocode failed: {e}")
            block = None

        by_hour: dict[str, dict] = {}
        for hour in HOURS:
            try:
                safety = _ls(crime.score_crime(crime_index, block, hour))
            except Exception as e:  # noqa: BLE001
                print(f"    crime@{hour} failed: {e}")
                safety = _neutral("Crime")
            try:
                func = _ls(functionality.score_functionality(lat, lon, hour))
            except Exception as e:  # noqa: BLE001
                print(f"    functionality@{hour} failed: {e}")
                func = _neutral("Functionality")
            by_hour[str(hour)] = {"safety": safety, "functionality": func}

        out[wid] = {"crowd": crowd_ls, "block": block, "by_hour": by_hour}

    meta = {"hours": HOURS, "n_walls": len(out),
            "generated_s": round(time.time() - t0, 1)}
    OUT.write_text(json.dumps({"meta": meta, "scores": out}, indent=2))
    print(f"\nWrote {OUT} ({len(out)} walls, {meta['generated_s']}s)")


if __name__ == "__main__":
    main()
