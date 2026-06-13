#!/usr/bin/env python3
"""
Precompute venue layer scores from backend/scoring and write frontend JSON.

Runs your friend's real scorers (crime, crowd, functionality) for each spot
in frontend/public/data/spots.json and updates:
  - frontend/public/data/spots-detail.json  (layer scores + reasons)
  - frontend/public/data/spots.json           (metrics, badges, overall_score)

Usage (from repo root):
  python -m backend.data.ingest_crime   # cache crime data first (optional)
  python scripts/precompute_venues.py
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.scoring.crime import (
    build_crime_index,
    latlng_to_block,
    load_crime_incidents,
    score_crime,
)
from backend.scoring.crowd import (
    WEIGHTS as CROWD_WEIGHTS,
    _nearest_motor_road,
    fetch_mbta_transit,
    fetch_osm_context,
    score_crowd,
    score_egress,
    score_liquor,
    score_overflow,
    score_traffic,
    score_transit,
)
from backend.scoring.functionality import (
    WEIGHTS as FUNC_WEIGHTS,
    _count_within,
    load_event_permits,
    score_cell,
    score_functionality,
    score_noise,
    score_permit_history,
)

SPOTS_PATH = ROOT / "frontend/public/data/spots.json"
DETAIL_PATH = ROOT / "frontend/public/data/spots-detail.json"
CRIME_CACHE = ROOT / "backend/data/cache/crime.parquet"
CRIME_CACHE_CSV = ROOT / "backend/data/cache/crime.csv"
HOURS = (12, 15, 18, 21)

# Physical scores stay LiDAR/mock until Layer 1 exists in backend.
PHYSICAL = {
    "davis-statue-wall": {
        "score": 95,
        "reasons": [
            "Flat unobstructed brick facade, ~12m tall — no windows or signage",
            "East-facing — fully shaded after 4pm, ideal for evening projection",
            "4.5m sidewalk + adjacent plaza approximates 350 standing",
        ],
    },
    "union-sq-plaza-wall": {
        "score": 70,
        "reasons": [
            "West-facing retaining wall — direct glare until ~7:30pm in summer",
            "8m tall with clean projection surface but limited shade options",
            "Plaza offers 500+ standing capacity with room to spread",
        ],
    },
    "assembly-row-garage": {
        "score": 92,
        "reasons": [
            "18m south-facing garage wall — shaded by 5pm, massive canvas",
            "Wide pedestrian promenade with no overhead obstructions",
            "LiDAR confirms flat surface variance < 3cm across projection zone",
        ],
    },
    "powderhouse-underpass": {
        "score": 35,
        "reasons": [
            "Only 6m tall — projection image too small for 100+ viewers",
            "Southwest-facing with partial shade but uneven brick texture",
            "Narrow 2.1m sidewalk — major crowd constraint",
        ],
    },
}

IMPRESSIONS = {
    "davis-statue-wall": 12400,
    "union-sq-plaza-wall": 17800,
    "assembly-row-garage": 28400,
}


def centroid(coords: list) -> tuple[float, float]:
    lng = sum(c[0] for c in coords) / len(coords)
    lat = sum(c[1] for c in coords) / len(coords)
    return lat, lng


def load_crime_index():
    cache = CRIME_CACHE if CRIME_CACHE.exists() else CRIME_CACHE_CSV if CRIME_CACHE_CSV.exists() else None
    if cache:
        print(f"Loading crime cache: {cache}")
        incidents = load_crime_incidents(str(cache))
    else:
        print("No crime cache — fetching live from Somerville open data...")
        incidents = load_crime_incidents()
    index = build_crime_index(incidents)
    print(f"  {len(incidents):,} incidents, {len(index.risk):,} block×shift cells")
    return index


def score_crowd_detailed(lat: float, lng: float, capacity: int) -> dict:
    ctx = fetch_osm_context(round(lat, 5), round(lng, 5))
    parts: dict[str, float] = {}
    reasons: list[str] = []
    flags: list[str] = []

    parts["traffic"], r = score_traffic(ctx)
    reasons.append(r)
    parts["egress"], r, choke = score_egress(ctx)
    reasons.append(r)
    if choke:
        flags.append("Limited egress — chokepoint risk for crowd dispersal.")

    try:
        station_dist, bus_count = fetch_mbta_transit(round(lat, 5), round(lng, 5))
        transit_src = "MBTA"
    except Exception:
        station_dist, bus_count, transit_src = ctx.station_dist_m, ctx.bus_count, "OSM"

    parts["transit"], r = score_transit(station_dist, bus_count, transit_src)
    reasons.append(r)
    parts["liquor"], liquor_reason = score_liquor(lat, lng, ctx.bar_count)
    reasons.append(liquor_reason)
    liquor_n = int(liquor_reason.split()[0]) if liquor_reason.split()[0].isdigit() else 0

    parts["overflow"], overflow_reason, spill = score_overflow(ctx, capacity, capacity)
    reasons.append(overflow_reason)
    if spill:
        flags.append("Crowd will spill into the roadway — apply traffic penalty / consider closure.")

    score = round(sum(parts[k] * CROWD_WEIGHTS[k] for k in parts), 1)
    road = _nearest_motor_road(ctx)
    adjacent_aadt = int(road.aadt) if road else 0

    return {
        "score": score,
        "parts": {k: round(v, 1) for k, v in parts.items()},
        "reasons": reasons,
        "flags": flags,
        "chokepoint": choke,
        "adjacent_aadt": adjacent_aadt,
        "liquor_count": liquor_n,
        "traffic_score": round(parts["traffic"], 1),
        "egress_score": round(parts["egress"], 1),
        "transit_score": round(parts["transit"], 1),
    }


def score_functionality_detailed(lat: float, lng: float, hour: int) -> dict:
    parts: dict[str, float] = {}
    reasons: list[str] = []
    flags: list[str] = []

    parts["permit_history"], r = score_permit_history(lat, lng)
    reasons.append(r)
    parts["noise"], r, quiet = score_noise(lat, lng, hour)
    reasons.append(r)
    if quiet:
        flags.append(
            "Residential quiet-hours risk at this event time — amplified sound may be restricted."
        )
    parts["cell"], r = score_cell(lat, lng)
    reasons.append(r)
    flags.append(
        "Power access unverified — no Somerville utility data; confirm on-site outlets/generator."
    )

    score = round(sum(parts[k] * FUNC_WEIGHTS[k] for k in parts), 1)
    prior = _count_within(load_event_permits(), lat, lng, 200)

    cell_mbps = None
    if "Mbps" in r:
        try:
            cell_mbps = int(r.split("~")[1].split(" Mbps")[0].strip())
        except (IndexError, ValueError):
            pass

    return {
        "score": score,
        "parts": {k: round(v, 1) for k, v in parts.items()},
        "reasons": reasons,
        "flags": flags,
        "prior_permits": prior,
        "noise_ok": not quiet,
        "cell_mbps": cell_mbps,
    }


def sun_badges(facing_deg: float) -> list[str]:
    badges = []
    if 45 <= facing_deg <= 135:
        badges.append("good_sun")
    if 225 <= facing_deg <= 315:
        badges.append("bad_sun")
    return badges


def derive_badges(
    facing_deg: float,
    capacity: int,
    crowd: dict,
    func: dict,
) -> list[str]:
    badges = sun_badges(facing_deg)
    if crowd["transit_score"] >= 60:
        badges.append("transit")
    if crowd["liquor_count"] > 0:
        badges.append("near_bar")
    if func["prior_permits"] > 0:
        badges.append("prior_events")
    if not crowd["chokepoint"] and crowd["egress_score"] >= 60:
        badges.append("good_egress")
    if crowd["traffic_score"] >= 70:
        badges.append("low_traffic")
    if func["cell_mbps"] is not None and func["cell_mbps"] >= 25:
        badges.append("good_cell")
    if capacity >= 300:
        badges.append("wide_sidewalk")
    return badges


def main() -> None:
    print("=== Precomputing venue scores from backend/scoring ===\n")

    spots_geo = json.loads(SPOTS_PATH.read_text())
    crime_index = load_crime_index()

    details: dict = {}
    for feature in spots_geo["features"]:
        props = feature["properties"]
        spot_id = props["id"]
        ring = feature["geometry"]["coordinates"][0]
        lat, lng = centroid(ring)
        capacity = props["capacity"]
        facing = props["facing_deg"]

        print(f"\n{props['name']} ({lat:.4f}, {lng:.4f})")

        block = latlng_to_block(lat, lng)
        print(f"  census block: {block}")

        safety_by_hour = {}
        noise_ok_by_hour = {}
        hourly: dict = {}
        for hour in HOURS:
            safety_h = score_crime(crime_index, block, hour)
            func_h = score_functionality_detailed(lat, lng, hour)
            safety_by_hour[hour] = safety_h.score
            noise_ok_by_hour[hour] = func_h["noise_ok"]
            hourly[str(hour)] = {
                "safety": {"score": safety_h.score, "reasons": safety_h.reasons},
                "functionality": {
                    "score": func_h["score"],
                    "parts": func_h["parts"],
                    "reasons": func_h["reasons"],
                    "flags": func_h["flags"],
                },
            }

        crowd = score_crowd_detailed(lat, lng, capacity)
        func = score_functionality_detailed(lat, lng, 18)
        physical = PHYSICAL[spot_id]
        safety_18 = hourly["18"]["safety"]

        overall = round(
            0.25 * physical["score"]
            + 0.25 * safety_18["score"]
            + 0.25 * crowd["score"]
            + 0.25 * func["score"]
        )

        badges = derive_badges(facing, capacity, crowd, func)

        props["overall_score"] = overall
        props["badges"] = badges
        props["metrics"] = {
            "traffic_score": crowd["traffic_score"],
            "egress_score": crowd["egress_score"],
            "transit_score": crowd["transit_score"],
            "liquor_count": crowd["liquor_count"],
            "prior_permits": func["prior_permits"],
            "cell_mbps": func["cell_mbps"],
            "power_verified": False,
            "chokepoint": crowd["chokepoint"],
            "adjacent_aadt": crowd["adjacent_aadt"],
            "safety_by_hour": {str(h): safety_by_hour[h] for h in HOURS},
            "noise_ok_by_hour": {str(h): noise_ok_by_hour[h] for h in HOURS},
        }

        detail_entry: dict = {
            "id": spot_id,
            "name": props["name"],
            "overall_score": overall,
            "capacity": capacity,
            "layers": {
                "physical": physical,
                "safety": hourly["18"]["safety"],
                "crowd": {
                    "score": crowd["score"],
                    "parts": crowd["parts"],
                    "reasons": crowd["reasons"],
                    "flags": crowd["flags"],
                },
                "functionality": {
                    "score": func["score"],
                    "parts": func["parts"],
                    "reasons": func["reasons"],
                    "flags": func["flags"],
                },
            },
            "hourly": hourly,
        }
        if spot_id in IMPRESSIONS:
            detail_entry["est_impressions_per_event"] = IMPRESSIONS[spot_id]

        details[spot_id] = detail_entry

        print(f"  overall={overall}  safety={safety_18['score']}  crowd={crowd['score']}  func={func['score']}")

    SPOTS_PATH.write_text(json.dumps(spots_geo, indent=2) + "\n")
    DETAIL_PATH.write_text(json.dumps(details, indent=2) + "\n")
    print(f"\nWrote {SPOTS_PATH}")
    print(f"Wrote {DETAIL_PATH}")


if __name__ == "__main__":
    main()
