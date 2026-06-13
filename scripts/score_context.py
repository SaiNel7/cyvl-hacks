"""
score_context.py — pedestrian-context scoring for wall candidates.

Post-processes data/wall_candidates.json (produced by detect_walls.py) using
already-downloaded City of Somerville open data. Walls near sidewalks,
crosswalks, trees and street lighting score higher — this demotes isolated
residential house walls and promotes square-adjacent / commercial venues.

Cheap to run: no LiDAR, no SDK. Re-run freely after tuning weights.
"""

import json
import math
from pathlib import Path

import numpy as np
import geopandas as gpd

# ── paths ─────────────────────────────────────────────────────────────────────

DOWNLOADS   = Path.home() / "Downloads"
ASSETS_PATH = DOWNLOADS / "CityofSomervilleMAMarketingDemo-aboveGroundAssets.geojson"
SAM_PATH    = DOWNLOADS / "CityofSomervilleMAMarketingDemo-sam.geojson"
WALLS_PATH  = Path(__file__).parent.parent / "data" / "wall_candidates.json"

# ── scoring config ──────────────────────────────────────────────────────────--

SIDEWALK_RADIUS_M  = 80.0
CROSSWALK_RADIUS_M = 80.0
TREE_RADIUS_M      = 60.0
LUMINARY_RADIUS_M  = 75.0

# coverage transparency: the asset/marking survey did not densely cover every
# block (e.g. Ball Sq has ~0 features nearby). Flag walls in a survey gap so a
# zero context score is read as "no data" not "no infrastructure".
COVERAGE_RADIUS_M    = 150.0
COVERAGE_MIN_FEATURES = 20

# pedestrian_context_score components (0-30 total), capped per component.
# Thresholds tuned for real separation: a busy square (Davis) has ~40-60
# crosswalk/marking features within 80 m, deep residential has ~0-10. Crosswalks
# are the strongest square-vs-residential signal, so weight them most and give
# them headroom before saturating. Trees are shade-only and small (leafy
# residential streets shouldn't out-score a plaza on tree count alone).
SIDEWALK_FULL  = 15    # this many within radius => full points
CROSSWALK_FULL = 25
TREE_FULL      = 12
LUMINARY_FULL  = 6
SIDEWALK_PTS   = 10.0
CROSSWALK_PTS  = 12.0
TREE_PTS       = 4.0
LUMINARY_PTS   = 4.0

# ── geometry helpers ──────────────────────────────────────────────────────────

def representative_lonlat(gdf):
    """Return (lon, lat) Nx2 array of representative points: centroid for
    LineStrings/Polygons, the point itself for Points."""
    geom = gdf.geometry
    pts = geom.representative_point()   # always inside the geometry, fast
    return np.column_stack([pts.x.to_numpy(), pts.y.to_numpy()])


def count_within(wall_lon, wall_lat, asset_lonlat, radius_m):
    """Count assets within radius_m of a wall using an equirectangular
    approximation (accurate to <0.1% at city scale, fully vectorized)."""
    if len(asset_lonlat) == 0:
        return 0
    lat0 = math.radians(wall_lat)
    m_per_deg_lat = 111320.0
    m_per_deg_lon = 111320.0 * math.cos(lat0)
    dx = (asset_lonlat[:, 0] - wall_lon) * m_per_deg_lon
    dy = (asset_lonlat[:, 1] - wall_lat) * m_per_deg_lat
    return int(np.count_nonzero(dx * dx + dy * dy <= radius_m * radius_m))


def context_score(n_sidewalk, n_crosswalk, n_tree, n_luminary):
    s  = min(n_sidewalk  / SIDEWALK_FULL,  1.0) * SIDEWALK_PTS
    c  = min(n_crosswalk / CROSSWALK_FULL, 1.0) * CROSSWALK_PTS
    t  = min(n_tree      / TREE_FULL,      1.0) * TREE_PTS
    l  = min(n_luminary  / LUMINARY_FULL,  1.0) * LUMINARY_PTS
    return round(min(s + c + t + l, 30.0), 1)


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    walls = json.load(open(WALLS_PATH))
    print(f"Loaded {len(walls)} wall candidates from {WALLS_PATH.name}")

    # above-ground assets: sidewalks, trees, luminaries
    assets = gpd.read_file(ASSETS_PATH).to_crs(epsg=4326)
    sidewalks  = representative_lonlat(assets[assets["asset_type"] == "SIDEWALK"])
    trees      = representative_lonlat(assets[assets["asset_type"] == "TREE"])
    luminaries = representative_lonlat(assets[assets["asset_type"] == "LUMINARIES"])
    print(f"  assets: {len(sidewalks)} sidewalks, {len(trees)} trees, "
          f"{len(luminaries)} luminaries")

    # crosswalks / markings from SAM layer
    sam = gpd.read_file(SAM_PATH).to_crs(epsg=4326)
    is_crosswalk = (
        sam["type"].str.contains("CROSSWALK", case=False, na=False)
        | (sam["category"] == "markings")
    )
    crosswalks = representative_lonlat(sam[is_crosswalk])
    print(f"  sam: {len(crosswalks)} crosswalk/marking features\n")

    # all surveyed features, for coverage / data-gap detection
    all_features = np.vstack([representative_lonlat(assets),
                              representative_lonlat(sam)])

    for w in walls:
        lon, lat = w["lon"], w["lat"]
        n_sw = count_within(lon, lat, sidewalks,  SIDEWALK_RADIUS_M)
        n_cw = count_within(lon, lat, crosswalks, CROSSWALK_RADIUS_M)
        n_tr = count_within(lon, lat, trees,      TREE_RADIUS_M)
        n_lm = count_within(lon, lat, luminaries, LUMINARY_RADIUS_M)
        ctx  = context_score(n_sw, n_cw, n_tr, n_lm)

        coverage = count_within(lon, lat, all_features, COVERAGE_RADIUS_M)
        sparse   = coverage < COVERAGE_MIN_FEATURES

        w["sidewalks_80m"]            = n_sw
        w["crosswalks_80m"]           = n_cw
        w["trees_60m"]                = n_tr
        w["luminaries_75m"]           = n_lm
        w["pedestrian_context_score"] = ctx
        w["total_score"]              = round(w["projection_score"] + ctx, 1)
        # transparency: zero context here means the survey didn't cover the
        # block, not that the venue lacks pedestrian infrastructure
        w["context_coverage_features"] = coverage
        w["context_data_sparse"]       = bool(sparse)

    walls.sort(key=lambda x: -x["total_score"])
    with open(WALLS_PATH, "w") as f:
        json.dump(walls, f, indent=2)
    print(f"Updated {WALLS_PATH} with pedestrian-context + total scores\n")

    # report
    ctx_vals = [w["pedestrian_context_score"] for w in walls]
    print("━━━ CONTEXT SCORE DISTRIBUTION ━━━")
    print(f"  min/median/max: {min(ctx_vals):.1f} / "
          f"{float(np.median(ctx_vals)):.1f} / {max(ctx_vals):.1f}")
    by_zone = {}
    for w in walls:
        by_zone.setdefault(w["zone"], []).append(w["pedestrian_context_score"])
    for z, vals in sorted(by_zone.items()):
        print(f"  {z:12s}  mean context={np.mean(vals):.1f}  (n={len(vals)})")

    sparse = [w for w in walls if w["context_data_sparse"]]
    if sparse:
        sparse_zones = {}
        for w in sparse:
            sparse_zones[w["zone"]] = sparse_zones.get(w["zone"], 0) + 1
        print(f"\n⚠ {len(sparse)} walls in a survey-coverage gap "
              f"(<{COVERAGE_MIN_FEATURES} features within {COVERAGE_RADIUS_M:.0f} m) "
              f"— their low context score reflects missing data, not missing "
              f"infrastructure: {sparse_zones}")

    print("\n━━━ TOP 5 WALLS BY TOTAL SCORE ━━━")
    for i, w in enumerate(walls[:5], 1):
        print(f"  {i}. [{w['zone']}] total={w['total_score']}  "
              f"(projection={w['projection_score']} + context={w['pedestrian_context_score']})")
        print(f"     {w['wall_width_m']}×{w['wall_height_m']}m ({w['wall_area_sqm']} m²)  "
              f"bearing={w['bearing_deg']}° {'WEST ' if w['west_facing'] else ''}")
        print(f"     sidewalks={w['sidewalks_80m']} crosswalks={w['crosswalks_80m']} "
              f"trees={w['trees_60m']} luminaries={w['luminaries_75m']}")
        print(f"     ({w['lat']}, {w['lon']})")


if __name__ == "__main__":
    main()
