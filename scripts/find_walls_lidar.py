"""
find_walls_lidar.py — Geometric wall detection from LiDAR point clouds.

No SAM3 / fal.ai required. Detects vertical planar surfaces directly from
frame.points_in_view() by binning into a 2D XY grid and finding cells with
high Z-span (tall vertical structures = building walls).

Outputs data/wall_candidates.json in the same schema as precompute_walls.py.
"""

import json
import math
import sys
from collections import defaultdict, deque
from pathlib import Path

import numpy as np

import cyvl

# ── tunables ─────────────────────────────────────────────────────────────────

ZONES = {
    "davis_sq": {"lat": 42.3967, "lon": -71.1225},
    "union_sq": {"lat": 42.3780, "lon": -71.0950},
    "ball_sq":  {"lat": 42.3967, "lon": -71.1000},
    "teele_sq": {"lat": 42.4030, "lon": -71.1240},
}

FRAMES_PER_ZONE   = 3     # take 3 nearest frames per zone centre
CELL_SIZE_M       = 0.5   # XY grid cell size for vertical plane detection
MIN_CELL_POINTS   = 15    # min lidar points per cell to be a wall candidate
MIN_Z_SPAN_M      = 2.5   # min vertical extent to qualify as a wall (not just curb/steps)
MIN_CLUSTER_CELLS = 6     # minimum grid cells per wall segment (~1.5m × 1.5m footprint)
MIN_WALL_AREA_SQM = 20.0  # final area threshold for projectable flag
MAX_DEPTH_M       = 25.0  # ignore distant background points

OUTPUT_PATH = Path(__file__).parent.parent / "data" / "wall_candidates.json"

# ── helpers ──────────────────────────────────────────────────────────────────

def haversine_m(lat1, lon1, lat2, lon2):
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def is_west_facing(bearing_deg):
    return 247 <= bearing_deg <= 293


def wall_bearing(cam_xyz, wall_centroid_xy):
    """
    Compass bearing of the wall's outward-facing normal.
    We use the vector from wall centroid toward camera — the direction the
    wall 'looks out' into (where a projector would sit).
    UTM: X=Easting, Y=Northing → bearing = atan2(dX, dY).
    """
    dx = cam_xyz[0] - wall_centroid_xy[0]
    dy = cam_xyz[1] - wall_centroid_xy[1]
    return math.degrees(math.atan2(dx, dy)) % 360


def safe_measure(frame, p1, p2):
    try:
        return float(cyvl.measure(frame, p1, p2).meters)
    except Exception as exc:
        print(f"        measure() {p1}→{p2} failed: {exc}")
        return None


def frames_near(imagery_df, lon, lat, n):
    """Return up to n (distance, row) pairs nearest to (lon, lat)."""
    rows = []
    for _, row in imagery_df.iterrows():
        d = haversine_m(lat, lon, row["lat"], row["lon"])
        rows.append((d, row))
        # early-exit: once we have plenty, stop scanning
        if len(rows) >= n * 20:
            break
    rows.sort(key=lambda x: x[0])
    return rows[:n]


# ── LiDAR wall detector ───────────────────────────────────────────────────────

def detect_walls(frame):
    """
    Return a list of wall dicts from a single frame's LiDAR point cloud.

    Algorithm:
    1. Keep only in-view points within MAX_DEPTH_M.
    2. Bin by (X, Y) in CELL_SIZE_M grid.
    3. Wall cell = ≥MIN_CELL_POINTS points with Z span ≥ MIN_Z_SPAN_M.
    4. BFS-cluster adjacent wall cells.
    5. Per cluster: compute UTM extent (width, height) and pixel bounds.
    """
    pts   = frame.points_in_view()
    iv    = pts.in_view.astype(bool)
    depth = pts.depth

    # Filter to in-view and nearby
    mask  = iv & (depth < MAX_DEPTH_M)
    if mask.sum() < MIN_CELL_POINTS:
        return []

    xyz = pts.points_utm[mask]
    pix = pts.pixels[mask].astype(np.int32)

    x, y, z = xyz[:, 0], xyz[:, 1], xyz[:, 2]
    u, v     = pix[:, 0], pix[:, 1]

    # ── grid binning ────────────────────────────────────────────────────────
    x_min, y_min = float(x.min()), float(y.min())
    ix = ((x - x_min) / CELL_SIZE_M).astype(np.int32)
    iy = ((y - y_min) / CELL_SIZE_M).astype(np.int32)

    nx = int(ix.max()) + 1
    ny = int(iy.max()) + 1

    # Flatten to 1D cell key for fast sorting
    cell_key = ix.astype(np.int64) * ny + iy.astype(np.int64)
    order        = np.argsort(cell_key, kind="stable")
    sorted_key   = cell_key[order]
    sorted_z     = z[order]

    # Find per-cell stats in one pass (sorted → contiguous blocks)
    bounds = np.concatenate(([0], np.flatnonzero(np.diff(sorted_key)) + 1, [len(sorted_key)]))

    wall_cell_set = set()
    for i in range(len(bounds) - 1):
        s, e = bounds[i], bounds[i + 1]
        if (e - s) < MIN_CELL_POINTS:
            continue
        z_block = sorted_z[s:e]
        if float(z_block.max()) - float(z_block.min()) >= MIN_Z_SPAN_M:
            key  = int(sorted_key[s])
            c_ix = key // ny
            c_iy = key % ny
            wall_cell_set.add((c_ix, c_iy))

    if not wall_cell_set:
        return []

    # ── BFS clustering ───────────────────────────────────────────────────────
    # Build a boolean grid for O(1) neighbour lookup
    wall_grid = np.zeros((nx, ny), dtype=bool)
    for c_ix, c_iy in wall_cell_set:
        wall_grid[c_ix, c_iy] = True

    visited  = np.zeros((nx, ny), dtype=bool)
    clusters = []  # list of lists of (c_ix, c_iy)

    for start in wall_cell_set:
        if visited[start]:
            continue
        cluster = []
        q = deque([start])
        visited[start] = True
        while q:
            cx, cy = q.popleft()
            cluster.append((cx, cy))
            for dx, dy in ((-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)):
                nx2, ny2 = cx + dx, cy + dy
                if 0 <= nx2 < nx and 0 <= ny2 < ny and wall_grid[nx2, ny2] and not visited[nx2, ny2]:
                    visited[nx2, ny2] = True
                    q.append((nx2, ny2))
        if len(cluster) >= MIN_CLUSTER_CELLS:
            clusters.append(cluster)

    if not clusters:
        return []

    # ── per-cluster properties ────────────────────────────────────────────────
    # Build reverse map: which local (filtered) point indices belong to each cell
    # Use the boolean grid for fast lookup
    in_wall_cell = wall_grid[ix, iy]        # bool (N_filtered,)
    cell_key_local = ix.astype(np.int64) * ny + iy.astype(np.int64)

    # Map cluster cells → flat cell key set for membership test
    cam_pos = frame.pose[:3, 3]
    cam_xy  = cam_pos[:2]
    cam_height = cam_pos[2]

    walls = []
    for cluster in clusters:
        cluster_key_set = set(int(c_ix) * ny + int(c_iy) for c_ix, c_iy in cluster)

        # Get point indices belonging to this cluster
        in_cluster = np.array([ck in cluster_key_set for ck in cell_key_local], dtype=bool)
        if not in_cluster.any():
            continue

        cxyz = xyz[in_cluster]
        cpix = pix[in_cluster]

        # Wall geometry from UTM coordinates
        wall_z_min = float(cxyz[:, 2].min())
        wall_z_max = float(cxyz[:, 2].max())
        height_utm = wall_z_max - wall_z_min

        # Width along wall's principal horizontal axis (PCA in XY)
        cxy = cxyz[:, :2]
        centroid_xy = cxy.mean(axis=0)
        xy_c = cxy - centroid_xy
        cov  = (xy_c.T @ xy_c) / max(len(xy_c) - 1, 1)
        _, eigvecs = np.linalg.eigh(cov)
        principal   = eigvecs[:, -1]
        proj        = xy_c @ principal
        width_utm   = float(proj.max() - proj.min())

        area_utm = width_utm * height_utm

        # Bearing: wall facing direction = from wall centroid toward camera
        bearing = wall_bearing(cam_xy, centroid_xy)
        west    = is_west_facing(bearing)

        # Pixel spans for cyvl.measure()
        cu, cv_arr = cpix[:, 0], cpix[:, 1]
        v_mid = int((cv_arr.min() + cv_arr.max()) / 2)
        u_mid = int((cu.min() + cu.max()) / 2)

        # Horizontal span at mid-height
        v_band = np.abs(cv_arr - v_mid) < max(int((cv_arr.max() - cv_arr.min()) * 0.15), 5)
        if v_band.sum() >= 2:
            u_left  = int(cu[v_band].min())
            u_right = int(cu[v_band].max())
        else:
            u_left, u_right = int(cu.min()), int(cu.max())

        # Vertical span at mid-width
        u_band = np.abs(cu - u_mid) < max(int((cu.max() - cu.min()) * 0.15), 5)
        if u_band.sum() >= 2:
            v_top    = int(cv_arr[u_band].min())
            v_bottom = int(cv_arr[u_band].max())
        else:
            v_top, v_bottom = int(cv_arr.min()), int(cv_arr.max())

        walls.append({
            "centroid_xy":   centroid_xy.tolist(),
            "height_utm":    round(height_utm, 2),
            "width_utm":     round(width_utm, 2),
            "area_utm":      round(area_utm, 2),
            "bearing_deg":   round(bearing, 1),
            "west":          west,
            "n_points":      int(in_cluster.sum()),
            "px_left":       (u_left,  v_mid),
            "px_right":      (u_right, v_mid),
            "px_top":        (u_mid,   v_top),
            "px_bottom":     (u_mid,   v_bottom),
        })

    return walls


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    print("Loading Cyvl scene …")
    scene   = cyvl.load_scene("somerville")
    imagery = scene.imagery
    print(f"  imagery rows: {len(imagery):,}\n")

    all_candidates = []

    for zone_name, cfg in ZONES.items():
        print(f"━━━ {zone_name.upper()} ━━━")
        zone_lon, zone_lat = cfg["lon"], cfg["lat"]

        nearest = frames_near(imagery, zone_lon, zone_lat, FRAMES_PER_ZONE)
        print(f"  Nearest {len(nearest)} frames:")

        zone_candidates = []

        for dist_m, row in nearest:
            fid       = row["id"]
            flon, flat = row["lon"], row["lat"]
            image_url = row.get("image_url", "")
            print(f"  ▸ {fid}  ({flat:.5f}, {flon:.5f})  d={dist_m:.0f}m")

            try:
                frame = scene.nearest_frame(flon, flat)
            except Exception as exc:
                print(f"    nearest_frame() failed: {exc}")
                continue

            # Print point cloud stats on first frame in first zone
            if zone_name == "davis_sq" and dist_m == nearest[0][0]:
                pts_tmp = frame.points_in_view()
                iv_tmp  = pts_tmp.in_view.astype(bool)
                xyz_tmp = pts_tmp.points_utm
                d_tmp   = pts_tmp.depth
                print(f"    [point cloud stats — first frame]")
                print(f"      total points  : {len(xyz_tmp):,}")
                print(f"      in-view       : {iv_tmp.sum():,}")
                xyz_v = xyz_tmp[iv_tmp & (d_tmp < MAX_DEPTH_M)]
                print(f"      depth<{MAX_DEPTH_M:.0f}m in-view: {len(xyz_v):,}")
                print(f"      X: {xyz_v[:,0].min():.1f}–{xyz_v[:,0].max():.1f}  span={xyz_v[:,0].max()-xyz_v[:,0].min():.1f}m")
                print(f"      Y: {xyz_v[:,1].min():.1f}–{xyz_v[:,1].max():.1f}  span={xyz_v[:,1].max()-xyz_v[:,1].min():.1f}m")
                print(f"      Z: {xyz_v[:,2].min():.1f}–{xyz_v[:,2].max():.1f}  span={xyz_v[:,2].max()-xyz_v[:,2].min():.1f}m")

            # Detect walls
            try:
                walls = detect_walls(frame)
            except Exception as exc:
                print(f"    detect_walls() failed: {exc}")
                continue

            print(f"    vertical plane clusters found: {len(walls)}")

            for wall in walls:
                # Refine dimensions with cyvl.measure() — overwrites UTM estimate
                width_m  = safe_measure(frame, wall["px_left"],  wall["px_right"])
                height_m = safe_measure(frame, wall["px_top"],   wall["px_bottom"])

                # Fall back to UTM-computed dimensions if measure() fails
                if width_m  is None: width_m  = wall["width_utm"]
                if height_m is None: height_m = wall["height_utm"]

                area_sqm   = width_m * height_m
                projectable = area_sqm >= MIN_WALL_AREA_SQM and not wall["west"]

                candidate = {
                    "zone":          zone_name,
                    "frame_id":      str(fid),
                    "lon":           flon,
                    "lat":           flat,
                    "distance_m":    round(dist_m, 1),
                    "wall_width_m":  round(width_m,  2),
                    "wall_height_m": round(height_m, 2),
                    "wall_area_sqm": round(area_sqm, 2),
                    "bearing_deg":   wall["bearing_deg"],
                    "west_facing":   wall["west"],
                    "image_url":     image_url,
                    "projectable":   projectable,
                    # debug fields
                    "_n_lidar_pts":  wall["n_points"],
                    "_width_utm":    wall["width_utm"],
                    "_height_utm":   wall["height_utm"],
                }
                zone_candidates.append(candidate)

                flag = "✓ PROJECTABLE" if projectable else "✗ skip"
                print(
                    f"      {flag}  area={area_sqm:.1f}sqm  "
                    f"bearing={wall['bearing_deg']:.0f}°  "
                    f"pts={wall['n_points']}"
                )

        if not zone_candidates:
            print(f"  ⚠ WARNING: 0 wall candidates in {zone_name}")
        else:
            n_proj = sum(1 for c in zone_candidates if c["projectable"])
            print(f"  → {len(zone_candidates)} candidates, {n_proj} projectable\n")

        all_candidates.extend(zone_candidates)

    # Write output
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(all_candidates, f, indent=2)

    # Summary
    n_total = len(all_candidates)
    n_proj  = sum(1 for c in all_candidates if c["projectable"])
    by_zone: dict = {}
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
        print("\n  ⚠ no projectable walls found — try lowering MIN_WALL_AREA_SQM or MIN_Z_SPAN_M")


if __name__ == "__main__":
    main()
