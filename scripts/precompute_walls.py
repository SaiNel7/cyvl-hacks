"""
precompute_walls.py — SAM3 wall detection pipeline for Third Space Finder.

Bypasses fal-cdn-v3 upload (which needs special CDN permissions) by passing
the frame's existing public CloudFront URL directly to fal_client.subscribe().
No file upload required.
"""

import json
import math
import os
import sys
from pathlib import Path

import numpy as np

import cyvl

# ── constants ────────────────────────────────────────────────────────────────

ZONES = {
    "davis_sq":  {"lat": 42.3967, "lon": -71.1225, "radius_m": 300, "max_frames": 15},
    "union_sq":  {"lat": 42.3780, "lon": -71.0950, "radius_m": 300, "max_frames": 15},
    "ball_sq":   {"lat": 42.3967, "lon": -71.1000, "radius_m": 200, "max_frames": 15},
    "teele_sq":  {"lat": 42.4030, "lon": -71.1240, "radius_m": 200, "max_frames": 15},
}

SAM3_PROMPT     = "large flat blank building wall no windows no signage"
SAM3_ENDPOINT   = "fal-ai/sam-3/image-rle"
MIN_WALL_AREA_SQM = 20.0
MIN_SAM3_SCORE  = 0.5   # discard low-confidence masks

# Pixel coords for measure() calls.
# Horizontal span across the middle of the frame for width.
# Vertical span for height. 360° frames are typically 4096×2048.
FRAME_W, FRAME_H = 4096, 2048
WALL_LEFT   = (int(FRAME_W * 0.30), int(FRAME_H * 0.40))
WALL_RIGHT  = (int(FRAME_W * 0.70), int(FRAME_H * 0.40))
WALL_TOP    = (int(FRAME_W * 0.50), int(FRAME_H * 0.25))
WALL_BOTTOM = (int(FRAME_W * 0.50), int(FRAME_H * 0.65))

OUTPUT_PATH = Path(__file__).parent.parent / "data" / "wall_candidates.json"

# ── SAM3 via direct URL (no fal CDN upload) ──────────────────────────────────

def sam3_detect_wall(image_url: str, fal_key: str) -> list[float]:
    """
    Call SAM3 on a public image URL, returning confidence scores for any
    wall masks found.  Raises on API error; returns [] when nothing found.

    Uses fal_client.subscribe() directly instead of fal_client.upload_file()
    to avoid the fal-cdn-v3 403 that hits accounts without CDN write scope.
    """
    import fal_client  # cyvl[sam] extra

    os.environ["FAL_KEY"] = fal_key  # fal_client reads this

    result = fal_client.subscribe(
        SAM3_ENDPOINT,
        arguments={
            "image_url": image_url,
            "prompt": SAM3_PROMPT,
            "return_multiple_masks": True,
            "max_masks": 3,
            "include_scores": True,
            "include_boxes": True,
        },
    )
    scores = list(result.get("scores", []))
    return [s for s in scores if s >= MIN_SAM3_SCORE]


# ── helpers ──────────────────────────────────────────────────────────────────

def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def bearing_from_pose(pose: np.ndarray) -> float:
    """Compass bearing of camera forward vector from 4×4 pose matrix."""
    forward = pose[:3, 2]
    return math.degrees(math.atan2(forward[0], forward[1])) % 360


def is_west_facing(bearing_deg: float) -> bool:
    return 247 <= bearing_deg <= 293


def safe_measure(frame, p1: tuple, p2: tuple) -> float | None:
    try:
        return float(cyvl.measure(frame, p1, p2).meters)
    except Exception as exc:
        print(f"      measure() failed {p1}→{p2}: {exc}")
        return None


def frames_in_zone(imagery_df, zone_lat: float, zone_lon: float, radius_m: float, max_frames: int):
    rows = []
    for _, row in imagery_df.iterrows():
        d = haversine_m(zone_lat, zone_lon, row["lat"], row["lon"])
        if d <= radius_m:
            rows.append((d, row))
        if len(rows) >= max_frames * 5:
            break
    rows.sort(key=lambda x: x[0])
    return rows[:max_frames]


# ── main pipeline ─────────────────────────────────────────────────────────────

def main():
    fal_key = os.environ.get("FAL_KEY", "")
    if not fal_key:
        print("ERROR: FAL_KEY not set. Export it before running.")
        sys.exit(1)

    print("Loading Cyvl scene …")
    scene = cyvl.load_scene("somerville")
    imagery = scene.imagery
    print(f"  imagery rows: {len(imagery):,}  columns: {imagery.columns.tolist()}\n")

    all_candidates = []

    for zone_name, cfg in ZONES.items():
        print(f"━━━ {zone_name.upper()} (radius={cfg['radius_m']}m, max={cfg['max_frames']} frames) ━━━")

        zone_rows = frames_in_zone(
            imagery, cfg["lat"], cfg["lon"], cfg["radius_m"], cfg["max_frames"]
        )
        print(f"  Frames in zone: {len(zone_rows)}")

        if not zone_rows:
            print(f"  ⚠ WARNING: no frames found in {zone_name}\n")
            continue

        zone_candidates = []

        for dist_m, row in zone_rows:
            frame_id  = row["id"]
            lon, lat  = row["lon"], row["lat"]
            image_url = row.get("image_url", "")
            print(f"  frame {frame_id}  ({lat:.5f}, {lon:.5f})  d={dist_m:.0f}m")

            if not image_url:
                print("    no image_url, skipping")
                continue

            # SAM3 wall detection — no CDN upload, direct public URL
            try:
                scores = sam3_detect_wall(image_url, fal_key)
            except Exception as exc:
                print(f"    SAM3 failed: {exc}")
                continue

            if not scores:
                print(f"    no wall masks above threshold")
                continue

            best_score = max(scores)
            print(f"    {len(scores)} wall mask(s), best score={best_score:.3f}")

            # Load frame for pose + measure
            try:
                frame = scene.nearest_frame(lon, lat)
            except Exception as exc:
                print(f"    nearest_frame() failed: {exc}")
                bearing_deg = None
                frame = None
            else:
                try:
                    bearing_deg = bearing_from_pose(frame.pose)
                except Exception as exc:
                    print(f"    pose bearing failed: {exc}")
                    bearing_deg = None

            west = is_west_facing(bearing_deg) if bearing_deg is not None else False

            # Measure wall dimensions
            if frame is not None:
                wall_width_m  = safe_measure(frame, WALL_LEFT, WALL_RIGHT)
                wall_height_m = safe_measure(frame, WALL_TOP, WALL_BOTTOM)
            else:
                wall_width_m = wall_height_m = None

            if wall_width_m is not None and wall_height_m is not None:
                wall_area_sqm = wall_width_m * wall_height_m
            elif wall_width_m is not None:
                wall_area_sqm = wall_width_m * wall_width_m
            else:
                wall_area_sqm = None

            projectable = (
                wall_area_sqm is not None
                and wall_area_sqm >= MIN_WALL_AREA_SQM
                and not west
            )

            candidate = {
                "zone":          zone_name,
                "frame_id":      str(frame_id),
                "lon":           lon,
                "lat":           lat,
                "distance_m":    round(dist_m, 1),
                "sam3_score":    round(best_score, 3),
                "wall_width_m":  round(wall_width_m, 2) if wall_width_m is not None else None,
                "wall_height_m": round(wall_height_m, 2) if wall_height_m is not None else None,
                "wall_area_sqm": round(wall_area_sqm, 2) if wall_area_sqm is not None else None,
                "bearing_deg":   round(bearing_deg, 1) if bearing_deg is not None else None,
                "west_facing":   west,
                "image_url":     image_url,
                "projectable":   projectable,
            }
            zone_candidates.append(candidate)

            area_str = f"{wall_area_sqm:.1f}sqm" if wall_area_sqm is not None else "N/A sqm"
            bear_str = f"{bearing_deg:.0f}°" if bearing_deg is not None else "N/A°"
            flag = "✓ PROJECTABLE" if projectable else "✗ skip"
            print(f"      {flag}  area={area_str}  bearing={bear_str}  west={west}")

        if not zone_candidates:
            print(f"  ⚠ WARNING: 0 wall candidates found in {zone_name}")
        else:
            n_proj = sum(1 for c in zone_candidates if c["projectable"])
            print(f"  → {len(zone_candidates)} candidates, {n_proj} projectable")

        all_candidates.extend(zone_candidates)
        print()

    # Write output
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(all_candidates, f, indent=2)

    # Summary
    n_total = len(all_candidates)
    n_proj  = sum(1 for c in all_candidates if c["projectable"])
    by_zone: dict[str, dict] = {}
    for c in all_candidates:
        z = c["zone"]
        by_zone.setdefault(z, {"total": 0, "projectable": 0})
        by_zone[z]["total"] += 1
        if c["projectable"]:
            by_zone[z]["projectable"] += 1

    print("━━━ SUMMARY ━━━")
    for z, counts in by_zone.items():
        print(f"  {z:12s}  {counts['projectable']}/{counts['total']} projectable")
    print(f"\n  Total candidates : {n_total}")
    print(f"  Projectable      : {n_proj}")
    print(f"  Output           : {OUTPUT_PATH}")

    if n_proj == 0:
        print("\n  ⚠ WARNING: no projectable venues found")
        sys.exit(1)


if __name__ == "__main__":
    main()
