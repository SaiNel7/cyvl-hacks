"""
detect_walls.py — Geometric blank-wall detection from Cyvl LiDAR.

Third Space Finder: find blank building walls in Somerville suitable for
outdoor projector screenings. Pure-numpy geometry pipeline — no SAM3, no
fal.ai, no mocked data. Every point comes from frame.lidar().

Pipeline per zone frame:
  1. Load point cloud         frame.lidar(radius_m=40, same_pass=True)
  2. Ground removal           RANSAC horizontal-plane fit, drop inliers
  3. Wall-height band-pass    keep 2m..15m above ground (drop cars/canopy)
  4. Plane extraction         sequential RANSAC -> keep VERTICAL planes only
  5. Wall scoring             width, height, area, bearing, west-facing, score
  6. Output                   data/wall_candidates.json + top-5 print
"""

import json
import math
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")

import cyvl
from cyvl.geometry import utm_to_lonlat

# ── config ────────────────────────────────────────────────────────────────────

# zone centers — each is sampled at center + N/S/E/W offsets (spread sampling)
ZONES = {
    "davis_sq": {"lon": -71.1225, "lat": 42.3967},
    "union_sq": {"lon": -71.0950, "lat": 42.3780},
    "ball_sq":  {"lon": -71.1000, "lat": 42.3967},
    "teele_sq": {"lon": -71.1240, "lat": 42.4030},
}
OFFSET_M = 150.0            # N/S/E/W sample offset from each zone center

LIDAR_RADIUS_M   = 40.0     # horizontal radius around camera
VOXEL_M          = 0.15     # downsample resolution

GROUND_THRESH_M  = 0.20     # RANSAC inlier band for ground plane
GROUND_ITERS     = 300
GROUND_MIN_NZ    = 0.85     # ground normal must be near-vertical

WALL_MIN_H       = 2.0      # head height above ground
WALL_MAX_H       = 15.0     # roofline cap

PLANE_THRESH_M   = 0.15     # RANSAC inlier band for wall planes (tight: foliage<wall)
SLAB_REMOVE_M    = 0.40     # remove this thicker slab so one wall isn't re-detected
PLANE_ITERS      = 350
MAX_PLANES       = 25       # sequential RANSAC extraction budget
PLANE_MIN_PTS    = 250      # min inliers to accept a plane
VERTICAL_MAX_NZ  = 0.25     # |normal_z| below this => vertical (a wall)

SEG_GAP_M        = 1.5      # split a plane's points into segments on this gap
SEG_MIN_PTS      = 150

# wall quality gates — a projectable building face, not a fence/hedge/car
MIN_AREA_SQM     = 25.0     # substantial surface
MIN_HEIGHT_M     = 3.5      # building height, rejects fences/hedges/vehicles
MAX_PLANE_RMS_M  = 0.10     # flat & blank, rejects foliage / rough clutter

# non-max suppression — collapse duplicate detections of one physical wall
NMS_PERP_M       = 3.0      # coplanar: planes within this perpendicular offset …
NMS_CENTROID_M   = 10.0     # cross-frame: centroids within this distance …
NMS_BEARING_DEG  = 25.0     # … and facing within this are the same wall

WEST_LO, WEST_HI = 247.0, 293.0   # west-facing bearing band (bad for evening)

OUTPUT_PATH = Path(__file__).parent.parent / "data" / "wall_candidates.json"

# ── geometry helpers ──────────────────────────────────────────────────────────

def voxel_downsample(xyz, voxel):
    """Keep one point per occupied voxel (centroid). Pure numpy."""
    keys = np.floor(xyz / voxel).astype(np.int64)
    # unique voxel id
    _, idx, inv = np.unique(
        keys[:, 0] * 73856093 ^ keys[:, 1] * 19349663 ^ keys[:, 2] * 83492791,
        return_index=True, return_inverse=True,
    )
    # centroid per voxel
    sums = np.zeros((len(idx), 3))
    counts = np.zeros(len(idx))
    np.add.at(sums, inv, xyz)
    np.add.at(counts, inv, 1.0)
    return sums / counts[:, None]


def fit_plane_svd(pts):
    """Least-squares plane through pts. Returns (normal unit, d, rms_residual)."""
    centroid = pts.mean(axis=0)
    u, s, vt = np.linalg.svd(pts - centroid, full_matrices=False)
    normal = vt[-1]
    normal /= np.linalg.norm(normal)
    d = -normal.dot(centroid)
    resid = np.abs((pts - centroid) @ normal)
    return normal, d, float(np.sqrt((resid ** 2).mean()))


def ransac_ground(pts, thresh, iters, min_nz, rng):
    """Best near-horizontal plane (the ground). Returns (normal, d, inlier_mask)."""
    N = len(pts)
    best_count, best = 0, None
    for _ in range(iters):
        tri = pts[rng.choice(N, 3, replace=False)]
        n = np.cross(tri[1] - tri[0], tri[2] - tri[0])
        norm = np.linalg.norm(n)
        if norm < 1e-9:
            continue
        n = n / norm
        if abs(n[2]) < min_nz:          # ground must be near-horizontal
            continue
        d = -n.dot(tri[0])
        dist = np.abs(pts @ n + d)
        count = int((dist < thresh).sum())
        if count > best_count:
            best_count, best = count, (n, d)
    if best is None:
        return None, None, np.zeros(N, dtype=bool)
    n, d = best
    if n[2] < 0:                        # orient normal up
        n, d = -n, -d
    inliers = np.abs(pts @ n + d) < thresh
    return n, d, inliers


def ransac_plane(pts, thresh, iters, rng, vertical_max_nz=None):
    """Best plane on pts. Returns (normal, d, inlier_mask, saw_nonvertical).

    When vertical_max_nz is given, only planes whose normal is near-horizontal
    (|n_z| <= vertical_max_nz, i.e. vertical surfaces / walls) are eligible —
    so tree canopy and road clutter never win an extraction round. We still
    track whether the unconstrained best candidate was non-vertical, for the
    zero-walls diagnostic.
    """
    N = len(pts)
    best_count, best = 0, None
    best_any_count, best_any_nz = 0, None
    for _ in range(iters):
        tri = pts[rng.choice(N, 3, replace=False)]
        n = np.cross(tri[1] - tri[0], tri[2] - tri[0])
        norm = np.linalg.norm(n)
        if norm < 1e-9:
            continue
        n = n / norm
        d = -n.dot(tri[0])
        count = int((np.abs(pts @ n + d) < thresh).sum())
        if count > best_any_count:
            best_any_count, best_any_nz = count, abs(n[2])
        if vertical_max_nz is not None and abs(n[2]) > vertical_max_nz:
            continue                       # not a vertical surface — ineligible
        if count > best_count:
            best_count, best = count, (n, d)
    saw_nonvertical = best_any_nz is not None and best_any_nz > VERTICAL_MAX_NZ
    if best is None:
        return None, None, np.zeros(N, dtype=bool), saw_nonvertical
    n, d = best
    inliers = np.abs(pts @ n + d) < thresh
    return n, d, inliers, saw_nonvertical


def compass_bearing(vec_xy):
    """Compass degrees of a horizontal vector (x=easting, y=northing)."""
    return math.degrees(math.atan2(vec_xy[0], vec_xy[1])) % 360.0


def haversine_m(lat1, lon1, lat2, lon2):
    R = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def zone_sample_points(lon, lat, offset_m):
    """5 spread points: center + N/S/E/W at offset_m, so candidates come from
    many buildings across a square rather than one intersection."""
    dlat = offset_m / 111320.0
    dlon = offset_m / (111320.0 * math.cos(math.radians(lat)))
    return [
        (lon, lat),            # center
        (lon, lat + dlat),     # N
        (lon, lat - dlat),     # S
        (lon + dlon, lat),     # E
        (lon - dlon, lat),     # W
    ]


def nms_walls(walls, perp_dist_m, centroid_dist_m, bearing_deg):
    """Greedy non-max suppression. Two detections are the same physical wall
    when they face the same way (bearing within bearing_deg) AND either:
      - lie on nearly the same line (perpendicular plane offset small) — merges
        fragments of one long wall whose centroids are far apart along its
        length, which centroid distance alone cannot do; or
      - their centroids are within centroid_dist_m — merges the same wall seen
        from adjacent frames in spread sampling.
    """
    kept = []
    for w in sorted(walls, key=lambda x: -x["projection_score"]):
        dup = False
        for k in kept:
            bd = abs(w["bearing_deg"] - k["bearing_deg"]) % 360.0
            bd = min(bd, 360.0 - bd)
            if bd >= bearing_deg:
                continue
            dx, dy = w["_cx"] - k["_cx"], w["_cy"] - k["_cy"]
            perp = abs(dx * k["_nx"] + dy * k["_ny"])          # coplanar offset
            dist = math.hypot(dx, dy)                          # centroid distance
            if perp < perp_dist_m or dist < centroid_dist_m:
                dup = True
                break
        if not dup:
            kept.append(w)
    return kept


def projection_score(area, width, height, rms, west):
    """0-100 suitability for a projector screening."""
    area_score  = min(area / 100.0, 1.0) * 40.0          # 100 m^2 saturates
    flat_score  = (1.0 - min(rms / PLANE_THRESH_M, 1.0)) * 30.0  # blank/flat
    width_score = min(width / 8.0, 1.0) * 15.0           # >=8 m wide ideal
    height_score = min(height / 4.0, 1.0) * 15.0         # >=4 m tall ideal
    score = area_score + flat_score + width_score + height_score
    if west:
        score *= 0.6                                     # sun glare penalty
    return round(min(score, 100.0), 1)


# ── per-frame wall detection ────────────────────────────────────────────────--

def detect_walls_in_frame(scene, frame, zone, log):
    walls = []
    rng = np.random.default_rng(42)

    # STEP 1 — load point cloud
    pc = frame.lidar(radius_m=LIDAR_RADIUS_M, same_pass=True)
    xyz_raw = pc.xyz
    log(f"    [1] raw points: {len(xyz_raw):,}")

    xyz = voxel_downsample(xyz_raw, VOXEL_M)
    log(f"        voxel-downsampled ({VOXEL_M} m): {len(xyz):,}")
    if len(xyz) < 1000:
        log("        too few points — skipping frame")
        return walls

    # STEP 2 — ground removal
    n_g, d_g, ground_mask = ransac_ground(xyz, GROUND_THRESH_M, GROUND_ITERS,
                                          GROUND_MIN_NZ, rng)
    if n_g is None:
        log("    [2] no ground plane found — skipping frame")
        return walls
    above = xyz[~ground_mask]
    log(f"    [2] ground removed: {int(ground_mask.sum()):,} ground pts -> "
        f"{len(above):,} above-ground  (ground normal_z={n_g[2]:.2f})")

    # height above ground plane (signed distance, normal points up)
    height_above = above @ n_g + d_g

    # STEP 3 — wall-height band-pass
    band = (height_above > WALL_MIN_H) & (height_above < WALL_MAX_H)
    wall_pts = above[band]
    log(f"    [3] wall-height band {WALL_MIN_H}-{WALL_MAX_H} m: {len(wall_pts):,} pts")
    if len(wall_pts) < PLANE_MIN_PTS:
        log("        too few wall-height points — no walls here")
        return walls

    # STEP 4 — sequential RANSAC plane extraction, keep vertical planes
    cam_xy = frame.position[:2]
    remaining = wall_pts.copy()
    planes_vertical = 0
    rounds_nonvertical = 0       # rounds where best overall plane was non-vertical

    for _ in range(MAX_PLANES):
        if len(remaining) < PLANE_MIN_PTS:
            break
        n_p, d_p, inl, saw_nonvert = ransac_plane(
            remaining, PLANE_THRESH_M, PLANE_ITERS, rng,
            vertical_max_nz=VERTICAL_MAX_NZ,
        )
        if saw_nonvert:
            rounds_nonvertical += 1
        if n_p is None or inl.sum() < PLANE_MIN_PTS:
            break                        # no vertical plane left with enough support
        planes_vertical += 1
        plane_pts = remaining[inl]
        # remove a thicker slab around the plane so the same physical wall
        # surface is not re-extracted as a parallel sliver next round
        slab = np.abs(remaining @ n_p + d_p) < SLAB_REMOVE_M
        remaining = remaining[~slab]

        # refine with SVD on inliers for a clean normal + residual
        n_ref, d_ref, rms = fit_plane_svd(plane_pts)
        if n_ref[2] < 0:
            n_ref = -n_ref
        # horizontal in-plane axis = normal x up, normalized
        horiz = np.cross(n_ref, np.array([0.0, 0.0, 1.0]))
        hn = np.linalg.norm(horiz)
        if hn < 1e-6:
            continue
        horiz /= hn

        # STEP 4b — split coplanar inliers into spatially separate segments
        u = plane_pts @ horiz
        order = np.argsort(u)
        u_sorted = u[order]
        pts_sorted = plane_pts[order]
        gaps = np.flatnonzero(np.diff(u_sorted) > SEG_GAP_M)
        seg_bounds = np.concatenate(([0], gaps + 1, [len(u_sorted)]))

        for i in range(len(seg_bounds) - 1):
            s, e = seg_bounds[i], seg_bounds[i + 1]
            if (e - s) < SEG_MIN_PTS:
                continue
            seg = pts_sorted[s:e]
            u_seg  = seg @ horiz
            width  = float(u_seg.max() - u_seg.min())
            height = float(seg[:, 2].max() - seg[:, 2].min())
            area   = width * height
            # quality gates: substantial, building-tall, flat/blank
            if area < MIN_AREA_SQM or height < MIN_HEIGHT_M or rms > MAX_PLANE_RMS_M:
                continue

            centroid = seg.mean(axis=0)
            # facing direction: horizontal normal pointing toward the camera
            normal_h = n_ref[:2].copy()
            normal_h /= np.linalg.norm(normal_h)
            if normal_h.dot(cam_xy - centroid[:2]) < 0:
                normal_h = -normal_h
            bearing = compass_bearing(normal_h)
            west = WEST_LO <= bearing <= WEST_HI

            lon, lat, _ = utm_to_lonlat(centroid[None, :], frame.utm_epsg)[0]
            # best image for this wall location
            try:
                img_frame = scene.nearest_frame(float(lon), float(lat))
                image_url = img_frame.image_url
            except Exception:
                image_url = frame.image_url

            score = projection_score(area, width, height, rms, west)

            walls.append({
                "zone":             zone,
                "frame_id":         str(frame.id),
                "lon":              round(float(lon), 6),
                "lat":              round(float(lat), 6),
                "wall_width_m":     round(width, 2),
                "wall_height_m":    round(height, 2),
                "wall_area_sqm":    round(area, 2),
                "bearing_deg":      round(bearing, 1),
                "west_facing":      bool(west),
                "plane_rms_m":      round(rms, 3),
                "n_points":         int(e - s),
                "projection_score": score,
                "image_url":        image_url,
                "projectable":      bool(area >= MIN_AREA_SQM and not west),
                # internal (stripped before save) — for plane-coincidence NMS
                "_cx": float(centroid[0]), "_cy": float(centroid[1]),
                "_nx": float(normal_h[0]), "_ny": float(normal_h[1]),
            })

    log(f"    [4] vertical planes extracted: {planes_vertical}  "
        f"(rounds whose densest plane was non-vertical clutter: {rounds_nonvertical})")
    if planes_vertical == 0:
        log(f"        → no vertical planar surface >= {PLANE_MIN_PTS} pts within "
            f"{LIDAR_RADIUS_M:.0f} m: building faces occluded by trees / set back "
            f"behind yards, camera facing open intersection")
    log(f"    [5] walls >= {MIN_AREA_SQM} m^2: {len(walls)}")
    return walls


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print("Loading Cyvl scene …")
    scene = cyvl.load_scene("somerville")
    print(f"  UTM zone EPSG:{scene.utm_epsg}\n")

    all_walls = []

    def log(msg):
        print(msg)

    for zone, c in ZONES.items():
        print(f"━━━ {zone.upper()}  center (lon={c['lon']}, lat={c['lat']}) ━━━")

        # spread sampling: resolve nearest frame for center + N/S/E/W, dedup by id
        frames = {}
        for s_lon, s_lat in zone_sample_points(c["lon"], c["lat"], OFFSET_M):
            try:
                f = scene.nearest_frame(s_lon, s_lat)
            except Exception as exc:
                print(f"    nearest_frame({s_lon:.5f},{s_lat:.5f}) failed: {exc}")
                continue
            frames[f.id] = f
        print(f"    {len(frames)} unique frame(s) across 5 sample points")

        zone_walls = []
        for frame in frames.values():
            print(f"  ▸ frame {frame.id}  @ ({frame.lat:.5f}, {frame.lon:.5f})")
            try:
                zone_walls.extend(detect_walls_in_frame(scene, frame, zone, log))
            except Exception as exc:
                import traceback
                print(f"    ERROR: {exc}")
                traceback.print_exc()

        if not zone_walls:
            print(f"    ⚠ {zone}: 0 walls — see cluster/rejection counts above\n")
        else:
            proj = sum(w["projectable"] for w in zone_walls)
            print(f"    → {zone}: {len(zone_walls)} raw walls ({proj} projectable / non-west)\n")
        all_walls.extend(zone_walls)

    # STEP 6 — dedupe (NMS) + save + report
    raw_count = len(all_walls)
    all_walls = nms_walls(all_walls, NMS_PERP_M, NMS_CENTROID_M, NMS_BEARING_DEG)
    print(f"Non-max suppression: {raw_count} raw detections -> {len(all_walls)} distinct walls\n")
    all_walls.sort(key=lambda w: -w["projection_score"])
    # strip internal NMS fields before writing the public schema
    for w in all_walls:
        for k in ("_cx", "_cy", "_nx", "_ny"):
            w.pop(k, None)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(all_walls, f, indent=2)

    print("━━━ SUMMARY ━━━")
    by_zone = {}
    for w in all_walls:
        by_zone.setdefault(w["zone"], 0)
        by_zone[w["zone"]] += 1
    for z in ZONES:
        print(f"  {z:12s}  {by_zone.get(z, 0)} walls")
    print(f"\n  Total walls       : {len(all_walls)}")
    print(f"  Projectable       : {sum(w['projectable'] for w in all_walls)}")
    print(f"  Output            : {OUTPUT_PATH}")

    print("\n━━━ TOP 5 WALLS BY PROJECTION SCORE ━━━")
    for i, w in enumerate(all_walls[:5], 1):
        print(f"  {i}. [{w['zone']}] score={w['projection_score']}  "
              f"{w['wall_width_m']}×{w['wall_height_m']}m ({w['wall_area_sqm']} m²)  "
              f"bearing={w['bearing_deg']}° "
              f"{'WEST-FACING ' if w['west_facing'] else ''}"
              f"rms={w['plane_rms_m']}m")
        print(f"     ({w['lat']}, {w['lon']})  {w['image_url'][:70]}…")


if __name__ == "__main__":
    main()
