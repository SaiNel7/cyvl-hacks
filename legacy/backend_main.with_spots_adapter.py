# backend/main.py
import json
from math import radians, cos, sin, asin, sqrt
from pathlib import Path
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware

DATA = Path(__file__).parent.parent / "data" / "wall_candidates.json"
SCORES = Path(__file__).parent.parent / "data" / "wall_scores.json"
VOXEL_DIR = Path(__file__).parent.parent / "data" / "wall_voxels"
PERSON_M2 = 0.28  # crowd-safety standard, per PRD
DEFAULT_SPOTS_LIMIT = 40  # only surface the best-fit surfaces, not all 239
DEFAULT_HOUR = 18         # FilterBar default; layers/blend are time-of-day dependent

app = FastAPI(title="Third Space Finder API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

def load():
    with open(DATA) as f:
        venues = json.load(f)
    for i, v in enumerate(venues):
        v.setdefault("id", f"{v['zone']}-{i}")
        v.setdefault("total_score", v.get("projection_score", 0))
        # rough capacity proxy until open-space frontage lands:
        # treat wall footprint as standing area placeholder
        v.setdefault("est_capacity", int(v.get("wall_area_sqm", 0) / PERSON_M2))
    return venues
VENUES = load()

def haversine_m(lat1, lon1, lat2, lon2):
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlon/2)**2
    return 6_371_000 * 2 * asin(sqrt(a))

@app.get("/venues")
def list_venues(
    lat: float | None = None,
    lon: float | None = None,
    radius_m: float = 1000,
    needs_projection: bool = False,
    min_capacity: int = 0,
    exclude_west: bool = False,
    limit: int = 50,
    ):
    out = VENUES
    if lat is not None and lon is not None:
        out = [v for v in out if haversine_m(lat, lon, v["lat"], v["lon"]) <= radius_m]
    if needs_projection:
        out = [v for v in out if v.get("projectable")]
    if exclude_west:
        out = [v for v in out if not v.get("west_facing")]
    if min_capacity:
        out = [v for v in out if v.get("est_capacity", 0) >= min_capacity]
    out = sorted(out, key=lambda v: -v.get("total_score",0))[:limit]

    return {"count": len(out), "venues": out}

@app.get("/venues/{venue_id}")
def get_venue(venue_id: str):
    for v in VENUES:
        if v["id"] == venue_id:
            return v
    raise HTTPException(404, "venue not found")

@app.get("/city/heatmap")
def heatmap():
    return {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [v["lon"], v["lat"]]},
            "properties": {k: v[k] for k in v if k != "image_url"},
        } for v in VENUES],
    }

# ── frontend adapter: venue → Spot / SpotDetail (see frontend/lib/types.ts) ─────
# The frontend renders extruded *polygons* with a name, badges, a 0–100 score and a
# 4-layer (physical/safety/crowd/functionality) story. The wall pipeline gives us a
# *point* + dimensions + bearing + context counts. We synthesize the rest here so the
# frontend's existing contract is met without changing its components/scoring.

_scores = [v["total_score"] for v in VENUES] or [0]
TOTAL_MIN, TOTAL_MAX = min(_scores), max(_scores)
M_PER_DEG_LAT = 111_320.0

ZONE_NAMES = {
    "davis_sq": "Davis Sq", "union_sq": "Union Sq", "ball_sq": "Ball Sq",
    "teele_sq": "Teele Sq", "powderhouse": "Powderhouse", "assembly": "Assembly",
}

def _clamp(x):
    return max(0, min(100, int(round(x))))

def rescale(total):
    """Linear rescale of total_score (observed ~30–118) onto the frontend's 0–100
    color scale (green ≥85 / yellow ≥60 / pink <60)."""
    if TOTAL_MAX == TOTAL_MIN:
        return 100
    return _clamp((total - TOTAL_MIN) / (TOTAL_MAX - TOTAL_MIN) * 100)

def pretty_zone(zone):
    return ZONE_NAMES.get(zone, zone.replace("_", " ").title())

def synth_polygon(lon, lat, bearing_deg, width_m, depth_m=2.0):
    """Thin, bearing-oriented wall footprint as a closed 5-point ring, for deck.gl
    extrusion. The geometry *is* the product — this turns a LiDAR point into a wall."""
    m_per_deg_lon = (M_PER_DEG_LAT * cos(radians(lat))) or 1e-9
    b = radians(bearing_deg)
    ax, ay = sin(b), cos(b)                      # along-wall axis (bearing from north)
    px, py = sin(b + radians(90)), cos(b + radians(90))  # perpendicular (depth) axis
    hw, hd = width_m / 2.0, depth_m / 2.0
    ring = []
    for sx, sy in ((1, 1), (1, -1), (-1, -1), (-1, 1)):
        dx = ax * hw * sx + px * hd * sy
        dy = ay * hw * sx + py * hd * sy
        ring.append([lon + dx / m_per_deg_lon, lat + dy / M_PER_DEG_LAT])
    ring.append(ring[0])
    return [ring]

def facing_from(bearing_deg, west_facing):
    """Surface-normal bearing (270 ≈ west) from wall bearing + the west_facing flag,
    so the frontend's time-of-day sun penalty lands on the right band."""
    n = (bearing_deg + 90) % 360
    in_west = 225 <= n <= 315
    if west_facing and not in_west:
        n = (bearing_deg - 90) % 360
    elif (not west_facing) and in_west:
        n = (bearing_deg - 90) % 360
    return round(n, 1)

def badges_for(v, overall):
    """Real signals where we have them; plausible proxies for the rest."""
    b = ["bad_sun" if v.get("west_facing") else "good_sun"]
    if v.get("crosswalks_80m", 0) >= 20:
        b.append("transit")          # crossing density ≈ transit/intersection hub
    if v.get("sidewalks_80m", 0) >= 8:
        b.append("wide_sidewalk")
    if v.get("luminaries_75m", 0) > 0:
        b.append("power")            # street lighting ≈ municipal power present
    if v.get("pedestrian_context_score", 0) >= 18:
        b.append("near_bar")         # synthesized: dense pedestrian context
    if overall >= 80:
        b.append("prior_events")     # synthesized: top-tier, demo-worthy surface
    return b

def physical_layer(v):
    """Physical layer — computed from the LiDAR wall geometry (no external module)."""
    proj = v.get("projection_score", 0)
    rms = v.get("plane_rms_m", 0.0)
    w, h = v.get("wall_width_m", 0), v.get("wall_height_m", 0)
    area = v.get("wall_area_sqm", 0)
    west = v.get("west_facing")
    return {
        "score": _clamp(proj),
        "reasons": [
            f"Flat facade — plane RMS {rms:.2f} m over {w:.0f}×{h:.0f} m ({area:.0f} m²)",
            "West-facing — evening glare risk until sundown" if west
            else "Not west-facing — low evening glare",
            f"LiDAR projection score {proj:.0f}/100",
        ],
    }

def synth_layers(v):
    """Fallback 4-layer story (used only when the precomputed sidecar is absent),
    so the app never breaks without data/wall_scores.json."""
    cap = int(v.get("est_capacity", 0))
    sw, cw = v.get("sidewalks_80m", 0), v.get("crosswalks_80m", 0)
    lum = v.get("luminaries_75m", 0)
    ctx = v.get("pedestrian_context_score", 0)
    sparse = v.get("context_data_sparse", False)
    return {
        "physical": physical_layer(v),
        "safety": {
            "score": _clamp(40 + min(lum, 6) / 6 * 40 + min(ctx, 30) / 30 * 20),
            "reasons": (
                [f"{lum} street luminaries within 75 m — lit for evening events"] if lum
                else ["No street lighting mapped nearby — bring temporary lighting"]
            ) + (
                ["Survey-coverage gap here: low context = missing data, not missing infrastructure"]
                if sparse else
                [f"Pedestrian-context score {ctx:.0f}/30 — active, surveilled block"]
            ),
        },
        "crowd": {
            "score": _clamp(min(cap, 1000) / 1000 * 60 + min(cw, 25) / 25 * 40),
            "reasons": [
                f"~{cap} standing capacity (wall-frontage proxy)",
                f"{sw} sidewalks + {cw} crosswalks within 80 m — egress & dispersal",
            ],
        },
        "functionality": {
            "score": _clamp(min(lum, 6) / 6 * 50 + min(ctx, 30) / 30 * 50),
            "reasons": [
                f"{lum} luminaries nearby — municipal power infrastructure present" if lum
                else "No mapped power infrastructure — generator likely needed",
                f"Pedestrian-context score {ctx:.0f}/30",
            ],
        },
    }

# ── precomputed layers (data/wall_scores.json from scripts/score_layers.py) ─────
# crime→safety, crowd, functionality are real, externally-sourced, and (for crime &
# functionality) time-of-day dependent. When the sidecar is present we blend all four
# layers into the headline score and rank by it; when absent we fall back to the
# surface score (rescaled total_score) + synthesized layers so nothing breaks.
try:
    _sc = json.loads(SCORES.read_text())
    WALL_SCORES = _sc.get("scores", {})
    SCORE_HOURS = _sc.get("meta", {}).get("hours") or [12, 15, 18, 21]
except (OSError, ValueError):
    WALL_SCORES, SCORE_HOURS = {}, [12, 15, 18, 21]
HAS_SCORES = bool(WALL_SCORES)

BLEND_WEIGHTS = {"physical": 0.30, "safety": 0.25, "crowd": 0.25, "functionality": 0.20}

def bucket_hour(hour):
    """Snap an arbitrary event hour to the nearest precomputed bucket."""
    return min(SCORE_HOURS, key=lambda h: abs(h - hour)) if SCORE_HOURS else DEFAULT_HOUR

def blend(layers):
    """Weighted blend of the 4 layer scores → 0–100 headline score."""
    return _clamp(sum(layers[k]["score"] * w for k, w in BLEND_WEIGHTS.items()))

def layers_at(entry, hour):
    """The 4-layer story for a wall at a given hour: physical from geometry, the
    rest from the precomputed sidecar (crowd is hour-independent), else synthesized."""
    v = entry["v"]
    sc = WALL_SCORES.get(v["id"])
    if not sc:
        return synth_layers(v)
    by_hour = sc.get("by_hour", {})
    bh = by_hour.get(str(bucket_hour(hour))) or (next(iter(by_hour.values())) if by_hour else {})
    return {
        "physical": entry["physical"],
        "safety": bh.get("safety") or synth_layers(v)["safety"],
        "crowd": sc.get("crowd") or synth_layers(v)["crowd"],
        "functionality": bh.get("functionality") or synth_layers(v)["functionality"],
    }

def overall_at(entry, hour):
    """Headline score: blended 4-layer score when precomputed, else surface score."""
    if HAS_SCORES and entry["v"]["id"] in WALL_SCORES:
        return blend(layers_at(entry, hour))
    return rescale(entry["v"]["total_score"])

def _build_spots():
    """Precompute the per-wall static parts (geometry, badges, base props). The
    hour-dependent overall score + layers are assembled per request."""
    spots = {}
    zone_idx = {}
    for v in VENUES:
        zone = v["zone"]
        zone_idx[zone] = zone_idx.get(zone, 0) + 1
        cap = int(v.get("est_capacity", 0))
        base = {
            "id": v["id"],
            "name": f"{pretty_zone(zone)} — Wall {zone_idx[zone]} "
                    f"({v.get('wall_width_m', 0):.0f}×{v.get('wall_height_m', 0):.0f}m)",
            "height_m": round(v.get("wall_height_m", 0), 1),
            "facing_deg": facing_from(v.get("bearing_deg", 0), v.get("west_facing")),
            "capacity": cap,
            # badges use the hour-independent surface score for the prior_events chip
            "badges": badges_for(v, rescale(v["total_score"])),
        }
        spots[v["id"]] = {
            "v": v,
            "base": base,
            "physical": physical_layer(v),
            "geom": {
                "type": "Polygon",
                "coordinates": synth_polygon(
                    v["lon"], v["lat"], v.get("bearing_deg", 0), v.get("wall_width_m", 0)
                ),
            },
            "imagery_url": v.get("image_url"),
            "est_impressions_per_event": int(cap * 35),
        }
    return spots

SPOTS = _build_spots()

def _feature(entry, hour):
    props = {**entry["base"], "overall_score": overall_at(entry, hour)}
    return {"type": "Feature", "properties": props, "geometry": entry["geom"]}

@app.get("/api/spots")
def api_spots(
    time_of_day: int = DEFAULT_HOUR,
    limit: int = DEFAULT_SPOTS_LIMIT,
    projectable_only: bool = True,
):
    """Best-fit surfaces as a frontend-shaped GeoJSON FeatureCollection, ranked by
    the blended 4-layer score for `time_of_day`. When the sidecar is present the pool
    is the precomputed best-fits; otherwise it's projectable walls by surface score."""
    if HAS_SCORES:
        entries = [SPOTS[i] for i in WALL_SCORES if i in SPOTS]
    else:
        entries = [e for e in SPOTS.values()
                   if e["v"].get("projectable") or not projectable_only]
    feats = [_feature(e, time_of_day) for e in entries]
    feats.sort(key=lambda f: -f["properties"]["overall_score"])
    return {"type": "FeatureCollection", "features": feats[:limit]}

@app.get("/api/spots/{spot_id}")
def api_spot_detail(spot_id: str, time_of_day: int = DEFAULT_HOUR):
    entry = SPOTS.get(spot_id)
    if not entry:
        raise HTTPException(404, "spot not found")
    return {
        **entry["base"],
        "overall_score": overall_at(entry, time_of_day),
        "geometry": entry["geom"],
        "layers": layers_at(entry, time_of_day),
        "imagery_url": entry["imagery_url"],
        "est_impressions_per_event": entry["est_impressions_per_event"],
    }

@app.get("/api/walls/{wall_id}/voxels")
def wall_voxels(wall_id: str):
    """Colored 3D voxel point cloud for one wall (built by
    scripts/voxelize_walls.py). List of {lon, lat, z, r, g, b}. 404 when this
    wall hasn't been voxelized yet."""
    f = VOXEL_DIR / f"{wall_id}.json"
    if not f.exists():
        raise HTTPException(404, "voxels not found for this wall")
    with open(f) as fh:
        return json.load(fh)
