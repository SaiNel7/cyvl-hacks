# backend/main.py
import json
from math import radians, cos, sin, asin, sqrt
from pathlib import Path
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware

DATA = Path(__file__).parent.parent / "data" / "wall_candidates.json"
VOXEL_DIR = Path(__file__).parent.parent / "data" / "wall_voxels"
PERSON_M2 = 0.28  # crowd-safety standard, per PRD

# Spot/venue data is served to the frontend via the static-precompute pipeline
# (scripts/precompute_venues.py → frontend/public/data/*.json); see legacy/ for the
# earlier live-API adapter. This FastAPI app now backs the 3D voxel point clouds.

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
