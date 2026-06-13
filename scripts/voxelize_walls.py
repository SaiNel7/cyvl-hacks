"""
voxelize_walls.py — Turn detected blank-wall candidates into colored 3D voxel
point clouds for deck.gl rendering on the Mapbox map.

Pipeline per wall candidate:
  1. nearest_frame(lon, lat) -> frame.points_in_view()  (lidar + pixel coords)
  2. colorize: this dataset's pts.colors is all-zero (no real RGB), so sample the
     true color from the frame photo at each in-view point's pixel; intensity ->
     color ramp is the fallback only when the frame has no image.
  3. voxelize: bin XYZ into VOXEL_M grid, mean color per voxel
  4. keep only voxels within PLANE_DIST_M of the fitted wall plane
  5. export {lon, lat, z, r, g, b} per voxel to data/wall_voxels/{id}.json

Run modes:
  python3 scripts/voxelize_walls.py --inspect   # STEP 1 only: show colors/intensity
  python3 scripts/voxelize_walls.py             # process the 4 test walls
"""

import argparse
import json
from pathlib import Path

import numpy as np

import cyvl
from cyvl.geometry import utm_to_lonlat

# ── config ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
CANDIDATES = ROOT / "data" / "wall_candidates.json"
OUT_DIR = ROOT / "data" / "wall_voxels"

LIDAR_RADIUS_M = 40.0    # match detect_walls.py so we see the same wall points
VOXEL_M = 0.2            # voxel size; bumped to 0.5 if a wall exceeds MAX_VOXELS
MAX_VOXELS = 50_000
PLANE_DIST_M = 2.0       # keep voxels within this of the fitted wall plane
CROP_RADIUS_M = 15.0     # horizontal crop around the wall before voxelizing

# 4 test walls: top-scoring projectable wall in each of the 4 zones
TEST_ZONES = ["davis_sq", "union_sq", "ball_sq", "teele_sq"]


def wall_id(w, idx):
    """Stable id matching backend/main.py load(): f'{zone}-{index}'."""
    return f"{w['zone']}-{idx}"


def load_candidates():
    with open(CANDIDATES) as f:
        walls = json.load(f)
    # mirror backend id assignment (enumerate order over the saved file)
    for i, w in enumerate(walls):
        w["id"] = f"{w['zone']}-{i}"
    return walls


def pick_test_walls(walls):
    """Top-scoring projectable wall per test zone (the 4 demo examples)."""
    picks = []
    for zone in TEST_ZONES:
        zone_walls = [w for w in walls if w["zone"] == zone and w.get("projectable")]
        if not zone_walls:
            zone_walls = [w for w in walls if w["zone"] == zone]
        if zone_walls:
            picks.append(max(zone_walls, key=lambda w: w.get("projection_score", 0)))
    return picks


# ── color ────────────────────────────────────────────────────────────────────

def intensity_to_rgb(intensity):
    """Map normalized lidar intensity -> viridis-like RGB uint8 (fallback when
    the cloud carries no real RGB). Percentile-stretched for contrast."""
    lo, hi = np.percentile(intensity, [2, 98])
    t = np.clip((intensity - lo) / max(hi - lo, 1e-6), 0, 1)
    # cheap 5-stop viridis ramp, no matplotlib dependency
    stops = np.array([
        [68, 1, 84], [59, 82, 139], [33, 145, 140],
        [94, 201, 98], [253, 231, 37],
    ], dtype=np.float64)
    pos = t * (len(stops) - 1)
    i0 = np.floor(pos).astype(int).clip(0, len(stops) - 2)
    frac = (pos - i0)[:, None]
    rgb = stops[i0] * (1 - frac) + stops[i0 + 1] * frac
    return rgb.astype(np.uint8)


def sample_image_colors(frame, pixels):
    """Sample true RGB from the frame photo at each (col,row) pixel. pixels are
    the projected in-view pixel coords (already inside image bounds). Returns
    (N,3) uint8."""
    img = frame.image()                       # (H, W, 3) uint8 RGB
    h, w = img.shape[:2]
    cols = np.clip(np.round(pixels[:, 0]).astype(int), 0, w - 1)
    rows = np.clip(np.round(pixels[:, 1]).astype(int), 0, h - 1)
    return img[rows, cols].astype(np.uint8)


def colorize(frame, pts, view):
    """Per-point RGB for the in-view points. Primary: real color sampled from the
    frame photo. Fallback: lidar intensity through a ramp when the frame has no
    image. Never mocked/constant. Returns (rgb uint8 (M,3), source_str)."""
    if frame.image_url is not None:
        return sample_image_colors(frame, np.asarray(pts.pixels)[view]), "photo"
    if pts.intensity is not None:
        it = np.asarray(pts.intensity, dtype=np.float64)[view]
        return intensity_to_rgb(it), "intensity"
    raise ValueError("frame has no image and cloud carries no intensity")


# ── STEP 1: inspect ───────────────────────────────────────────────────────────

def inspect(scene, walls):
    w = pick_test_walls(walls)[0]  # one Davis Square wall
    print(f"Inspecting Davis Square wall {w['id']}  "
          f"({w['lat']}, {w['lon']})  score={w['projection_score']}")
    frame = scene.nearest_frame(w["lon"], w["lat"])
    print(f"  nearest_frame: {frame.id}  @ ({frame.lat:.5f}, {frame.lon:.5f})")
    pts = frame.points_in_view(radius_m=LIDAR_RADIUS_M)
    n = len(pts)
    print(f"  points_in_view: {n:,} points  ({int(pts.in_view.sum()):,} in frustum)")
    print(f"  points_utm: shape={pts.points_utm.shape} dtype={pts.points_utm.dtype}")

    if pts.colors is not None:
        c = np.asarray(pts.colors)
        print(f"  pts.colors:   shape={c.shape} dtype={c.dtype}  "
              f"min={c.min(axis=0)} max={c.max(axis=0)} mean={c.mean(axis=0).round(1)}")
    else:
        print("  pts.colors:   None")

    if pts.intensity is not None:
        it = np.asarray(pts.intensity, dtype=np.float64)
        print(f"  pts.intensity: shape={it.shape} dtype={pts.intensity.dtype}  "
              f"min={it.min():.3f} max={it.max():.3f} mean={it.mean():.3f}")
    else:
        print("  pts.intensity: None")


# ── STEP 2: voxelize ───────────────────────────────────────────────────────────

def voxelize(xyz, rgb, voxel_m):
    """Bin points into voxel_m grid; mean XYZ + mean RGB per occupied voxel.
    Returns (centroids (M,3), colors (M,3) uint8)."""
    keys = np.floor(xyz / voxel_m).astype(np.int64)
    vid = (keys[:, 0] * 73856093) ^ (keys[:, 1] * 19349663) ^ (keys[:, 2] * 83492791)
    _, inv = np.unique(vid, return_inverse=True)
    m = inv.max() + 1
    sums = np.zeros((m, 3))
    csum = np.zeros((m, 3))
    counts = np.zeros(m)
    np.add.at(sums, inv, xyz)
    np.add.at(csum, inv, rgb.astype(np.float64))
    np.add.at(counts, inv, 1.0)
    centroids = sums / counts[:, None]
    colors = (csum / counts[:, None]).round().astype(np.uint8)
    return centroids, colors


def fit_plane_svd(pts):
    """Least-squares plane. Returns (unit normal, d) with normal·x + d = 0."""
    c = pts.mean(axis=0)
    _, _, vt = np.linalg.svd(pts - c, full_matrices=False)
    n = vt[-1]
    n /= np.linalg.norm(n)
    return n, -n.dot(c)


# ── STEP 3: process one wall end-to-end ────────────────────────────────────────

def process_wall(scene, w, verbose=True):
    frame = scene.nearest_frame(w["lon"], w["lat"])
    pts = frame.points_in_view(radius_m=LIDAR_RADIUS_M)

    # only points actually visible in the photo carry trustworthy color and
    # belong to the surface the camera saw — drops occluded / behind-camera pts
    view = pts.in_view
    xyz = np.asarray(pts.points_utm)[view]
    rgb, src = colorize(frame, pts, view)
    if len(xyz) < 200:
        if verbose:
            print(f"  {w['id']}: only {len(xyz)} in-view points — skip")
        return None

    # crop to a horizontal disc around the wall location so we voxelize the wall
    # building, not the whole 40 m street scene. Radius scales with wall width.
    cx, cy = frame.project(lonlat=np.array([[w["lon"], w["lat"]]]), alt=0.0).points_utm[0, :2]
    crop_r = max(CROP_RADIUS_M, w.get("wall_width_m", 0) / 2 + 5.0)
    disc = np.hypot(xyz[:, 0] - cx, xyz[:, 1] - cy) < crop_r
    xyz, rgb = xyz[disc], rgb[disc]
    if len(xyz) < 200:
        if verbose:
            print(f"  {w['id']}: only {len(xyz)} points near wall — skip")
        return None
    raw_n = len(xyz)

    def voxelize_and_clip(voxel_m):
        """Voxelize the cropped cloud, then keep only voxels within PLANE_DIST_M
        of the wall plane (fitted on the voxels nearest the candidate point, so
        we lock onto the wall, not a roadside tree)."""
        centroids, colors = voxelize(xyz, rgb, voxel_m)
        near = np.hypot(centroids[:, 0] - cx, centroids[:, 1] - cy) < 12.0
        seed = centroids[near] if near.sum() > 50 else centroids
        n, d = fit_plane_svd(seed)
        keep = np.abs(centroids @ n + d) < PLANE_DIST_M
        return centroids[keep], colors[keep]

    # 0.2 m by default; only coarsen if the WALL itself (post-clip) is too dense
    voxel_m = VOXEL_M
    centroids, colors = voxelize_and_clip(voxel_m)
    if len(centroids) > MAX_VOXELS:
        voxel_m = 0.5
        centroids, colors = voxelize_and_clip(voxel_m)

    if len(centroids) == 0:
        if verbose:
            print(f"  {w['id']}: no voxels near wall plane — skip")
        return None

    # UTM -> WGS84; Z relative to ground (min Z of the kept cluster)
    lonlat = utm_to_lonlat(centroids, frame.utm_epsg)
    z = centroids[:, 2] - centroids[:, 2].min()
    voxels = [
        {"lon": round(float(lon), 7), "lat": round(float(lat), 7),
         "z": round(float(zz), 2),
         "r": int(r), "g": int(g), "b": int(b)}
        for (lon, lat, _), zz, (r, g, b) in zip(lonlat, z, colors)
    ]

    if verbose:
        print(f"  {w['id']:14s} src={src:9s} voxel={voxel_m}m  "
              f"{raw_n:>7,} pts -> {len(centroids):>6,} voxels "
              f"({raw_n / max(len(centroids),1):.1f}x)  z=0..{z.max():.1f}m")
    return voxels


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inspect", action="store_true", help="STEP 1 only")
    ap.add_argument("--all", action="store_true", help="process all walls, not just the 4 tests")
    args = ap.parse_args()

    print("Loading Cyvl scene 'somerville' …")
    scene = cyvl.load_scene("somerville")
    walls = load_candidates()

    if args.inspect:
        inspect(scene, walls)
        return

    targets = walls if args.all else pick_test_walls(walls)
    print(f"Processing {len(targets)} wall(s) -> {OUT_DIR}\n")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    ok = 0
    for w in targets:
        try:
            voxels = process_wall(scene, w)
        except Exception as exc:
            print(f"  {w['id']}: ERROR {exc}")
            continue
        if voxels:
            out = OUT_DIR / f"{w['id']}.json"
            with open(out, "w") as f:
                json.dump(voxels, f)
            ok += 1
    print(f"\nWrote {ok}/{len(targets)} voxel files to {OUT_DIR}")


if __name__ == "__main__":
    main()
