"""
Layer 4 — Venue-functionality scoring for Third Space Finder.

One of several venue-scoring layers (capacity, crime, crowd, functionality, ...).
This module scores only the *functionality* layer, answering the PRD's question:
"Can an event actually run here?"

Three scored sub-signals (each independently visible, same {score, reasons}):
  1. Permit history  - prior public-event/block-party permits nearby -> precedent
  2. Noise / zoning   - residential quiet-hours, TIME-GATED to the event hour
  3. Cell coverage    - Ookla measured mobile download speed at the venue's tile
Plus a non-scored note: power access (see limitation below).

Data sources (all real, measured data):
  - "Applications for Permits and Licenses" (nneb-s3f7): event permits for history.
  - "Zoning & Overlay Districts" (crrw-ex2a): a zipped shapefile (EPSG:2249,
    MA State Plane feet) of 1,469 zoning polygons; ZONECODE/ZONEDESC classify
    residential vs commercial vs civic.
  - Ookla Open Data mobile speed tiles (zoom-16, ~600m): real measured cellular
    download speeds. We extract the Somerville-area tiles once (DuckDB over the
    S3 parquet, filtered by quadkey) and cache them; a venue is scored by the tile
    it falls in, smoothed over its 3x3 neighborhood and weighted by test count.

KNOWN LIMITATION — power access is NOT scored:
  Somerville publishes NO streetlight/utility/power dataset (verified: nothing on
  the open-data portal or ArcGIS; OSM streetlamps too sparse). Electrical permits
  track building/renovation work, not public power access, so they are NOT a valid
  proxy. Rather than fake a number, power is surfaced as an "unverified — confirm
  on site" flag and excluded from the score.
"""

from __future__ import annotations

import functools
import io
import json
import math
import pathlib
import zipfile

import httpx
import pyproj
import shapefile  # pyshp
from shapely.geometry import Point, shape
from shapely.strtree import STRtree

from backend.scoring.crime import LayerScore   # shared contract

# ---------------------------------------------------------------------------
# Weights (sum 1.0)
# ---------------------------------------------------------------------------
WEIGHTS = {
    "permit_history": 0.40,
    "noise": 0.40,
    "cell": 0.20,
}

PERMIT_RESOURCE = "https://data.somervillema.gov/resource/nneb-s3f7.json"
ZONING_BLOB = (
    "https://data.somervillema.gov/api/views/crrw-ex2a/files/"
    "9d8e0b4f-c007-49c0-90b6-050f0a48ebc3"
)
_HEADERS = {"User-Agent": "third-space-finder/0.1 (cyvl-hackathon)"}

# Permit types that signal a venue has hosted a public gathering before.
EVENT_PERMIT_TYPES = (
    "Public Event License",
    "Block Party",
    "Special Alcohol License",
    "Entertainment License",
    "Farmers Market",
    "Farmer Winery Event License",
)

# Distance thresholds (meters)
PERMIT_RADIUS_M = 200    # prior-event precedent catchment

# Ookla Open Data — measured mobile speed tiles (zoom 16, ~600m).
OOKLA_URL = (
    "https://ookla-open-data.s3.amazonaws.com/parquet/performance/type=mobile/"
    "year=2026/quarter=1/2026-01-01_performance_mobile_tiles.parquet"
)
OOKLA_QK_PREFIX = "03023321213"   # zoom-16 quadkey prefix covering the Somerville area
OOKLA_ZOOM = 16
OOKLA_CACHE = pathlib.Path(__file__).resolve().parents[1] / "data" / "cache" / "ookla_mobile_somerville.json"
GOOD_DATA_MBPS = 25.0    # download speed at/above which attendees have solid data -> full marks
MIN_TILE_TESTS = 3       # below this, treat coverage as low-confidence/neutral

# Zoning ZONECODE -> noise sensitivity class.
RESIDENTIAL_ZONES = {"NR", "UR"}                       # strict quiet hours
MIXED_USE_ZONES = {"MR3", "MR4", "MR5", "MR6", "HR"}   # residential above retail
CIVIC_ZONES = {"CIV", "TU", "PS"}                      # event-friendly institutional
# Everything else (CB, CC3/4/5, CI, FAB, ASMD) = commercial/industrial.

# Projections: meters for distances, MA State Plane feet for the zoning shapefile.
_TO_M = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:26986", always_xy=True).transform
_TO_SP = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:2249", always_xy=True).transform


# ---------------------------------------------------------------------------
# Data loaders (cached)
# ---------------------------------------------------------------------------
def _load_permit_points(where: str) -> tuple[tuple[float, float], ...]:
    resp = httpx.get(
        PERMIT_RESOURCE,
        params={
            "$select": "application_latitude,application_longitude",
            "$where": where,
            "$limit": 50000,
        },
        headers=_HEADERS,
        timeout=90.0,
    )
    resp.raise_for_status()
    pts = []
    for row in resp.json():
        lat, lng = row.get("application_latitude"), row.get("application_longitude")
        if lat and lng:
            pts.append(_TO_M(float(lng), float(lat)))
    return tuple(pts)


@functools.lru_cache(maxsize=1)
def load_event_permits() -> tuple[tuple[float, float], ...]:
    inlist = ",".join("'" + t.replace("'", "''") + "'" for t in EVENT_PERMIT_TYPES)
    return _load_permit_points(
        f"application_type in({inlist}) AND application_latitude IS NOT NULL"
    )


@functools.lru_cache(maxsize=1)
def load_zoning() -> tuple[STRtree, list[str], list[str]]:
    """Zoning polygons (in EPSG:2249), an STRtree over them, and parallel
    ZONECODE / ZONEDESC lists indexed the same as the tree's geometries."""
    resp = httpx.get(ZONING_BLOB, headers=_HEADERS, timeout=120.0, follow_redirects=True)
    resp.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(resp.content))
    sf = shapefile.Reader(
        shp=io.BytesIO(z.read("Zoning.shp")),
        dbf=io.BytesIO(z.read("Zoning.dbf")),
        shx=io.BytesIO(z.read("Zoning.shx")),
    )
    fields = [f[0] for f in sf.fields[1:]]
    ci_code, ci_desc = fields.index("ZONECODE"), fields.index("ZONEDESC")

    geoms, codes, descs = [], [], []
    for sr in sf.shapeRecords():
        geoms.append(shape(sr.shape.__geo_interface__))
        codes.append(sr.record[ci_code])
        descs.append(sr.record[ci_desc])
    return STRtree(geoms), codes, descs


def _count_within(points: tuple[tuple[float, float], ...], lat: float, lng: float, radius_m: float) -> int:
    vx, vy = _TO_M(lng, lat)
    r2 = radius_m * radius_m
    return sum(1 for (x, y) in points if (x - vx) ** 2 + (y - vy) ** 2 <= r2)


def zone_at(lat: float, lng: float) -> tuple[str | None, str | None]:
    """Return (ZONECODE, ZONEDESC) of the polygon containing the point, else (None, None)."""
    tree, codes, descs = load_zoning()
    px, py = _TO_SP(lng, lat)
    pt = Point(px, py)
    for i in tree.query(pt):           # candidates by bbox
        if tree.geometries[i].contains(pt):
            return codes[i], descs[i]
    return None, None


# ---------------------------------------------------------------------------
# Sub-scorers
# ---------------------------------------------------------------------------
def score_permit_history(lat: float, lng: float) -> tuple[float, str]:
    n = _count_within(load_event_permits(), lat, lng, PERMIT_RADIUS_M)
    score = float(min(100, 60 + 8 * n))   # 0 -> 60 neutral; precedent is a bonus
    if n == 0:
        reason = f"No prior public-event permit precedent within {PERMIT_RADIUS_M}m."
    else:
        reason = (
            f"{n} prior public-event/block-party permit(s) within {PERMIT_RADIUS_M}m "
            "— permit precedent exists (fast-track signal)."
        )
    return round(score, 1), reason


def score_noise(lat: float, lng: float, event_hour: int) -> tuple[float, str, bool]:
    code, desc = zone_at(lat, lng)
    late = event_hour >= 22 or event_hour < 8
    evening = 20 <= event_hour < 22
    flag = False

    if code is None or code == "Not Applicable":
        return 75.0, "Zoning unresolved (right-of-way / unzoned) — neutral noise assumption.", False
    label = f"{desc} ({code})"

    if code in RESIDENTIAL_ZONES:
        if late:
            score, note, flag = 20.0, "residential quiet hours in effect", True
        elif evening:
            score, note = 45.0, "approaching residential quiet hours"
        else:
            score, note = 70.0, "residential — daytime events tolerated"
    elif code in MIXED_USE_ZONES:
        score, note = (55.0, "mixed-use — late noise sensitivity") if late else (85.0, "mixed-use, residential above retail")
        flag = late
    elif code in CIVIC_ZONES:
        score, note = 90.0, "civic/institutional — event-friendly"
    else:  # commercial / industrial
        score, note = 95.0, "commercial/industrial — minimal quiet-hours constraint"

    return round(score, 1), f"Zone: {label} — {note} (event {event_hour:02d}:00).", flag


# --- Ookla speed-tile quadkey helpers ---
def _deg2tile(lat: float, lng: float, z: int) -> tuple[int, int]:
    n = 2 ** z
    x = int((lng + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n)
    return x, y


def _to_quadkey(x: int, y: int, z: int) -> str:
    qk = []
    for i in range(z, 0, -1):
        d, mask = 0, 1 << (i - 1)
        if x & mask:
            d += 1
        if y & mask:
            d += 2
        qk.append(str(d))
    return "".join(qk)


def _quadkey_at(lat: float, lng: float, z: int = OOKLA_ZOOM) -> str:
    return _to_quadkey(*_deg2tile(lat, lng, z), z)


def _neighbor_quadkeys(lat: float, lng: float, z: int = OOKLA_ZOOM) -> list[str]:
    x, y = _deg2tile(lat, lng, z)
    return [_to_quadkey(x + dx, y + dy, z) for dx in (-1, 0, 1) for dy in (-1, 0, 1)]


@functools.lru_cache(maxsize=1)
def load_ookla() -> dict[str, tuple[float, int]]:
    """quadkey -> (avg download kbps, tests). Reads the local cache, else extracts
    the Somerville-area tiles from Ookla's S3 parquet via DuckDB and writes the cache."""
    if OOKLA_CACHE.exists():
        return {k: tuple(v) for k, v in json.loads(OOKLA_CACHE.read_text()).items()}

    import duckdb  # lazy: only needed when building the cache
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    rows = con.execute(
        f"SELECT quadkey, avg_d_kbps, tests FROM read_parquet('{OOKLA_URL}') "
        f"WHERE quadkey LIKE '{OOKLA_QK_PREFIX}%'"
    ).fetchall()
    data = {qk: (float(d), int(t)) for qk, d, t in rows}
    OOKLA_CACHE.parent.mkdir(parents=True, exist_ok=True)
    OOKLA_CACHE.write_text(json.dumps(data))
    return data


def score_cell(lat: float, lng: float) -> tuple[float, str]:
    data = load_ookla()
    # Tests-weighted mean download over the venue's tile + 8 neighbors (smooths noise).
    tot_tests, weighted_kbps = 0, 0.0
    for qk in _neighbor_quadkeys(lat, lng):
        if qk in data:
            d_kbps, tests = data[qk]
            weighted_kbps += d_kbps * tests
            tot_tests += tests

    if tot_tests < MIN_TILE_TESTS:
        return 70.0, "Sparse Ookla coverage data at this tile — neutral assumption."

    mbps = (weighted_kbps / tot_tests) / 1000.0
    score = round(min(100.0, 100.0 * mbps / GOOD_DATA_MBPS), 1)
    return score, (
        f"Measured mobile download ~{mbps:.0f} Mbps (Ookla, {tot_tests} tests over "
        "this + neighboring tiles)."
    )


# ---------------------------------------------------------------------------
# Composite
# ---------------------------------------------------------------------------
def score_functionality(lat: float, lng: float, event_hour: int = 19) -> LayerScore:
    """Venue-functionality layer score for a venue at (lat, lng), event at event_hour."""
    parts: dict[str, float] = {}
    reasons: list[str] = []
    flags: list[str] = []

    parts["permit_history"], r = score_permit_history(lat, lng); reasons.append(r)
    parts["noise"], r, quiet = score_noise(lat, lng, event_hour); reasons.append(r)
    if quiet:
        flags.append("Residential quiet-hours risk at this event time — amplified sound may be restricted.")
    parts["cell"], r = score_cell(lat, lng); reasons.append(r)
    # Power access has no Somerville open dataset — surfaced, never scored.
    flags.append("Power access unverified — no Somerville utility data; confirm on-site outlets/generator.")

    score = round(sum(parts[k] * WEIGHTS[k] for k in parts), 1)
    return LayerScore(score=score, reasons=reasons + flags)


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("Warming caches (event permits, zoning, Ookla tiles)...")
    load_event_permits(); load_zoning(); load_ookla()

    venues = [
        ("Davis Square", 42.3967, -71.1226, 19),
        ("Union Square", 42.3793, -71.0951, 19),
        ("Assembly Row", 42.3925, -71.0772, 19),
        ("Residential (UR) @ 2pm", 42.3880, -71.1010, 14),
        ("Residential (UR) @ 11pm", 42.3880, -71.1010, 23),
    ]
    for name, lat, lng, hr in venues:
        res = score_functionality(lat, lng, hr)
        print(f"\n{name}  [{hr:02d}:00]  ->  FUNCTIONALITY {res.score}")
        for r in res.reasons:
            print(f"   - {r}")
