"""
Layer 3 — Crowd-dynamics scoring for Third Space Finder.

One of several venue-scoring layers (capacity, crime, shade, weather, transit, ...).
This module scores only the *crowd-dynamics* layer, answering the PRD's question:
"Can this space handle the crowd without spilling into traffic?"

Five sub-signals, each independently visible (mirrors the crime layer's design):
  1. Traffic exposure  - how busy is the road the crowd would spill onto?
  2. Egress            - how many independent escape routes / how much width?
  3. Transit           - subway/rail station + bus stops for arrival & dispersal
  4. Overflow          - expected crowd vs venue capacity, penalized by traffic
  5. Liquor licenses   - active alcohol establishments to serve the crowd (mild +)

Data sources:
  - OpenStreetMap via the Overpass API (free, no key) for the road network. OSM's
    `highway` class + `lanes` is a *traffic-volume proxy* (AADT); MassDOT AADT
    counts are the production upgrade.
  - MBTA V3 API (the GTFS-backed feed, https://api-v3.mbta.com) for transit:
    authoritative stop locations with `route_type`, so subway/rail stations are
    distinguished from bus stops. OSM transit tags are kept only as a fallback.
  - Somerville open data "Applications for Permits and Licenses" (nneb-s3f7) for
    the liquor sub-signal: real active alcohol-license establishments (restaurants,
    package stores, private clubs, etc.) with coordinates. OSM bars are kept only
    as a fallback if that fetch fails.

All distances are computed in meters by projecting to EPSG:26986
(NAD83 / Massachusetts Mainland).
"""

from __future__ import annotations

import functools
import os
from dataclasses import dataclass

import httpx
import pyproj
from shapely.geometry import LineString, Point
from shapely.ops import transform as shp_transform

from backend.scoring.crime import LayerScore  # shared {score, reasons} contract

# ---------------------------------------------------------------------------
# Sub-signal weights (sum to 1.0). Overflow is dropped + the rest renormalized
# when no crowd/capacity is supplied.
# ---------------------------------------------------------------------------
WEIGHTS = {
    "traffic": 0.30,
    "egress": 0.25,
    "transit": 0.20,
    "overflow": 0.15,
    "liquor": 0.10,
}

# OSM highway class -> (AADT proxy vehicles/day, default lane count).
# Pedestrian/foot classes carry no cars (great for spillover + egress).
ROAD_PROFILE: dict[str, tuple[float, int]] = {
    "motorway": (60000, 3), "motorway_link": (20000, 1),
    "trunk": (40000, 2), "trunk_link": (15000, 1),
    "primary": (20000, 2), "primary_link": (8000, 1),
    "secondary": (12000, 2), "secondary_link": (5000, 1),
    "tertiary": (6000, 1), "tertiary_link": (3000, 1),
    "unclassified": (3000, 1),
    "residential": (1500, 1), "living_street": (600, 1),
    "busway": (500, 1), "service": (400, 1),
}
PEDESTRIAN_CLASSES = {"pedestrian", "footway", "path", "steps", "cycleway", "living_street"}
MOTOR_MIN_AADT = 300  # below this we treat a way as effectively non-vehicular

# Distance thresholds (meters)
ADJACENT_ROAD_M = 35       # road the crowd directly fronts / spills onto
EGRESS_RADIUS_M = 120      # escape-route catchment
TRANSIT_RADIUS_M = 450     # MBTA stop proximity (PRD: ~400m)
STATION_NEAR_M = 150       # station this close -> full transit marks
STATION_FAR_M = 600        # station beyond this contributes ~nothing
BAR_RADIUS_M = 200         # PRD: licensed alcohol establishment within 200m

AADT_HIGH = 25000          # adjacent AADT that zeroes the traffic sub-score

# Somerville liquor licenses (Applications for Permits and Licenses, nneb-s3f7).
# Fixed establishments that can serve a crowd — NOT the temporary "Special
# Alcohol License" / "Public Event" permits (those are prior-permit history,
# Layer 4). Only currently-active rows are counted.
# MBTA V3 API — GTFS-backed stop feed. route_type: 0 light rail, 1 heavy rail
# (subway), 2 commuter rail, 3 bus, 4 ferry. An API key (env MBTA_API_KEY) lifts
# the rate limit but is optional.
MBTA_STOPS_URL = "https://api-v3.mbta.com/stops"
MBTA_API_KEY = os.environ.get("MBTA_API_KEY")

LIQUOR_RESOURCE = "https://data.somervillema.gov/resource/nneb-s3f7.json"
ALCOHOL_ESTABLISHMENT_TYPES = (
    "Restaurant (with alcohol)",
    "Package Store (with alcohol)",
    "Private Club (with alcohol)",
    "Inn (with alcohol)",
    "Farmer Pourer (with alcohol)",
    "Educational Institution (with alcohol)",
)

# Public Overpass instances hiccup (429/504) under load — try mirrors in order.
OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
_HEADERS = {"User-Agent": "third-space-finder/0.1 (cyvl-hackathon)"}

_TO_M = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:26986", always_xy=True).transform


# ---------------------------------------------------------------------------
# OSM fetch + parse
# ---------------------------------------------------------------------------
@dataclass
class Road:
    name: str
    cls: str
    aadt: float
    lanes: int
    oneway: bool
    dist_m: float          # min distance from venue to this way
    is_motor: bool


@dataclass
class OSMContext:
    roads: list[Road]
    station_dist_m: float | None   # nearest rail/subway station
    bus_count: int                 # bus stops within TRANSIT_RADIUS_M
    bar_count: int                 # bars/pubs within BAR_RADIUS_M


def _query(lat: float, lng: float) -> str:
    return f"""
[out:json][timeout:25];
(
  way(around:{EGRESS_RADIUS_M},{lat},{lng})[highway];
  node(around:{TRANSIT_RADIUS_M},{lat},{lng})[railway=station];
  node(around:{TRANSIT_RADIUS_M},{lat},{lng})[station=subway];
  node(around:{TRANSIT_RADIUS_M},{lat},{lng})[railway=subway_entrance];
  node(around:{TRANSIT_RADIUS_M},{lat},{lng})[highway=bus_stop];
  node(around:{BAR_RADIUS_M},{lat},{lng})[amenity~"^(bar|pub|nightclub|biergarten)$"];
);
out tags geom;
"""


def _overpass(query: str) -> list[dict]:
    """POST to Overpass, falling back across mirrors on 429/504/network errors."""
    last_err: Exception | None = None
    for url in OVERPASS_MIRRORS:
        for attempt in range(2):
            try:
                resp = httpx.post(url, data={"data": query}, headers=_HEADERS, timeout=60.0)
                if resp.status_code in (429, 502, 503, 504):
                    last_err = httpx.HTTPStatusError(
                        f"{resp.status_code}", request=resp.request, response=resp
                    )
                    continue
                resp.raise_for_status()
                return resp.json()["elements"]
            except (httpx.HTTPError, ValueError) as e:
                last_err = e
                continue
    raise RuntimeError(f"All Overpass mirrors failed: {last_err}")


@functools.lru_cache(maxsize=2048)
def fetch_osm_context(lat: float, lng: float) -> OSMContext:
    elements = _overpass(_query(lat, lng))

    vx, vy = _TO_M(lng, lat)
    venue = Point(vx, vy)

    roads: list[Road] = []
    station_dist: float | None = None
    bus_count = 0
    bar_count = 0

    for el in elements:
        tags = el.get("tags", {})
        if el["type"] == "way" and "geometry" in el:
            cls = tags.get("highway", "")
            line = LineString([_TO_M(p["lon"], p["lat"]) for p in el["geometry"]])
            dist = venue.distance(line)
            if dist > EGRESS_RADIUS_M:
                continue
            aadt, default_lanes = ROAD_PROFILE.get(cls, (0.0, 1))
            roads.append(Road(
                name=tags.get("name", cls),
                cls=cls,
                aadt=aadt,
                lanes=_int(tags.get("lanes"), default_lanes),
                oneway=tags.get("oneway") in ("yes", "true", "1", "-1"),
                dist_m=dist,
                is_motor=aadt >= MOTOR_MIN_AADT and cls not in PEDESTRIAN_CLASSES,
            ))
        elif el["type"] == "node":
            nx, ny = _TO_M(el["lon"], el["lat"])
            d = venue.distance(Point(nx, ny))
            if tags.get("railway") in ("station", "subway_entrance") or tags.get("station") == "subway":
                station_dist = d if station_dist is None else min(station_dist, d)
            elif tags.get("highway") == "bus_stop" and d <= TRANSIT_RADIUS_M:
                bus_count += 1
            elif tags.get("amenity") in ("bar", "pub", "nightclub", "biergarten") and d <= BAR_RADIUS_M:
                bar_count += 1

    return OSMContext(roads=roads, station_dist_m=station_dist, bus_count=bus_count, bar_count=bar_count)


def _int(val, default: int) -> int:
    try:
        return int(str(val).split(";")[0])
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Sub-scorers — each returns (score 0-100, reason str, extra)
# ---------------------------------------------------------------------------
def _nearest_motor_road(ctx: OSMContext) -> Road | None:
    motor = [r for r in ctx.roads if r.is_motor and r.dist_m <= ADJACENT_ROAD_M]
    return min(motor, key=lambda r: r.dist_m) if motor else None


def score_traffic(ctx: OSMContext) -> tuple[float, str]:
    road = _nearest_motor_road(ctx)
    if road is None:
        return 95.0, "No motor road directly abuts the venue — crowd spillover stays off vehicle traffic."
    score = 100.0 * (1.0 - min(1.0, road.aadt / AADT_HIGH))
    return round(score, 1), (
        f"Fronts {road.name} (~{int(road.aadt):,} est. vehicles/day, {road.cls}) "
        f"{road.dist_m:.0f}m away."
    )


def score_egress(ctx: OSMContext) -> tuple[float, str, bool]:
    motor = {r.name: r for r in ctx.roads if r.is_motor and r.dist_m <= EGRESS_RADIUS_M}
    n_routes = len(motor)
    total_lanes = sum(r.lanes for r in motor.values())
    has_ped = any(r.cls in PEDESTRIAN_CLASSES and r.dist_m <= EGRESS_RADIUS_M for r in ctx.roads)

    base = {0: 20, 1: 35, 2: 60, 3: 78}.get(n_routes, 90)
    if total_lanes >= 6:
        base += 5
    if has_ped:
        base += 8
    score = float(min(100, base))

    chokepoint = n_routes <= 1 or (n_routes == 2 and all(r.oneway for r in motor.values()))
    reason = (
        f"{n_routes} independent road egress route(s) within {EGRESS_RADIUS_M}m "
        f"({total_lanes} lanes total)"
        + (", plus pedestrian paths for foot dispersal" if has_ped else "")
        + ("."if not chokepoint else " — narrow/limited egress, chokepoint risk.")
    )
    return round(score, 1), reason, chokepoint


@functools.lru_cache(maxsize=2048)
def fetch_mbta_transit(lat: float, lng: float) -> tuple[float | None, int]:
    """Authoritative transit context from the MBTA V3 API.

    Returns (nearest subway/rail station distance in m or None, # of distinct bus
    stops within TRANSIT_RADIUS_M). Raises on network/HTTP failure so the caller
    can fall back to OSM tags.
    """
    def _query(route_types: str, radius_deg: float) -> list[dict]:
        params = {
            "filter[latitude]": lat,
            "filter[longitude]": lng,
            "filter[radius]": radius_deg,
            "filter[route_type]": route_types,
            "fields[stop]": "latitude,longitude",
        }
        if MBTA_API_KEY:
            params["api_key"] = MBTA_API_KEY
        resp = httpx.get(MBTA_STOPS_URL, params=params, headers=_HEADERS, timeout=30.0)
        resp.raise_for_status()
        return resp.json()["data"]

    vx, vy = _TO_M(lng, lat)

    # Nearest subway / light rail / commuter rail station.
    station_dist: float | None = None
    for s in _query("0,1,2", 0.012):
        a = s["attributes"]
        sx, sy = _TO_M(a["longitude"], a["latitude"])
        d = ((sx - vx) ** 2 + (sy - vy) ** 2) ** 0.5
        station_dist = d if station_dist is None else min(station_dist, d)

    # Bus stops within range, deduped to ~11m so opposite-corner stops still count.
    seen: set = set()
    bus_count = 0
    r2 = TRANSIT_RADIUS_M * TRANSIT_RADIUS_M
    for s in _query("3", 0.008):
        a = s["attributes"]
        key = (round(a["latitude"], 4), round(a["longitude"], 4))
        if key in seen:
            continue
        seen.add(key)
        sx, sy = _TO_M(a["longitude"], a["latitude"])
        if (sx - vx) ** 2 + (sy - vy) ** 2 <= r2:
            bus_count += 1

    return station_dist, bus_count


def score_transit(station_dist_m: float | None, bus_count: int, source: str = "MBTA") -> tuple[float, str]:
    if station_dist_m is not None and station_dist_m <= STATION_FAR_M:
        station_score = min(100.0, 100.0 * max(
            0.0, (STATION_FAR_M - station_dist_m) / (STATION_FAR_M - STATION_NEAR_M)
        ))
        st = f"Subway/rail station {station_dist_m:.0f}m away"
    else:
        station_score = 0.0
        st = "No subway/rail station within range"
    bus_score = min(40.0, bus_count * 8.0)
    score = min(100.0, station_score + 0.5 * bus_score)
    note = "" if source == "MBTA" else f" [{source} fallback]"
    return round(score, 1), f"{st}; {bus_count} bus stop(s) within {TRANSIT_RADIUS_M}m ({source}){note}."


@functools.lru_cache(maxsize=1)
def load_liquor_establishments() -> tuple[tuple[float, float], ...]:
    """Active Somerville alcohol-license establishments, projected to meters.

    Deduplicated by parcel (falling back to rounded coordinates). Cached for the
    process; raises on fetch failure so callers can fall back to OSM bars.
    """
    inlist = ",".join("'" + t.replace("'", "''") + "'" for t in ALCOHOL_ESTABLISHMENT_TYPES)
    where = (
        f"application_type in({inlist}) AND currently_active='1' "
        "AND application_latitude IS NOT NULL"
    )
    resp = httpx.get(
        LIQUOR_RESOURCE,
        params={
            "$select": "application_latitude,application_longitude,parcel_number",
            "$where": where,
            "$limit": 5000,
        },
        headers=_HEADERS,
        timeout=60.0,
    )
    resp.raise_for_status()

    seen: set = set()
    pts: list[tuple[float, float]] = []
    for row in resp.json():
        lat, lng = row.get("application_latitude"), row.get("application_longitude")
        if not lat or not lng:
            continue
        key = row.get("parcel_number") or (round(float(lat), 6), round(float(lng), 6))
        if key in seen:
            continue
        seen.add(key)
        pts.append(_TO_M(float(lng), float(lat)))
    return tuple(pts)


def score_liquor(lat: float, lng: float, osm_bar_fallback: int) -> tuple[float, str]:
    """Liquor sub-signal: count active alcohol licenses within BAR_RADIUS_M."""
    try:
        pts = load_liquor_establishments()
        vx, vy = _TO_M(lng, lat)
        r2 = BAR_RADIUS_M * BAR_RADIUS_M
        n = sum(1 for (x, y) in pts if (x - vx) ** 2 + (y - vy) ** 2 <= r2)
        src = "active Somerville alcohol licenses"
    except Exception:
        n = osm_bar_fallback
        src = "OSM bars — license data unavailable"
    score = float(min(100, 50 + 15 * n))
    return round(score, 1), f"{n} licensed alcohol establishment(s) within {BAR_RADIUS_M}m ({src})."


def score_overflow(ctx: OSMContext, expected_crowd: int, venue_capacity: int) -> tuple[float, str, bool]:
    if expected_crowd <= venue_capacity:
        return 100.0, (
            f"Expected crowd (~{expected_crowd}) fits the venue capacity (~{venue_capacity})."
        ), False
    over = expected_crowd / venue_capacity - 1.0  # fraction over capacity
    road = _nearest_motor_road(ctx)
    # Spilling onto a quiet street is far less dangerous than onto an arterial.
    danger = 0.3 if road is None else 0.3 + 0.7 * min(1.0, road.aadt / AADT_HIGH)
    score = max(0.0, 100.0 - min(100.0, over * 100.0 * danger))
    where = f"toward {road.name} (~{int(road.aadt):,} veh/day)" if road else "into surrounding space"
    return round(score, 1), (
        f"Expected crowd (~{expected_crowd}) exceeds capacity (~{venue_capacity}) by "
        f"{over*100:.0f}% — will spill {where}."
    ), True


# ---------------------------------------------------------------------------
# Composite crowd-dynamics score
# ---------------------------------------------------------------------------
def score_crowd(
    lat: float,
    lng: float,
    expected_crowd: int | None = None,
    venue_capacity: int | None = None,
) -> LayerScore:
    """Crowd-dynamics layer score for a venue at (lat, lng)."""
    ctx = fetch_osm_context(round(lat, 5), round(lng, 5))

    parts: dict[str, float] = {}
    reasons: list[str] = []
    flags: list[str] = []

    parts["traffic"], r = score_traffic(ctx); reasons.append(r)
    parts["egress"], r, choke = score_egress(ctx); reasons.append(r)
    if choke:
        flags.append("Limited egress — chokepoint risk for crowd dispersal.")
    try:
        station_dist, bus_count = fetch_mbta_transit(round(lat, 5), round(lng, 5))
        transit_src = "MBTA"
    except Exception:
        station_dist, bus_count, transit_src = ctx.station_dist_m, ctx.bus_count, "OSM"
    parts["transit"], r = score_transit(station_dist, bus_count, transit_src); reasons.append(r)
    parts["liquor"], r = score_liquor(lat, lng, ctx.bar_count); reasons.append(r)

    if expected_crowd is not None and venue_capacity:
        parts["overflow"], r, spill = score_overflow(ctx, expected_crowd, venue_capacity)
        reasons.append(r)
        if spill:
            flags.append("Crowd will spill into the roadway — apply traffic penalty / consider closure.")
        weights = WEIGHTS
    else:
        # No crowd/capacity supplied: drop overflow and renormalize.
        weights = {k: v for k, v in WEIGHTS.items() if k != "overflow"}
        total = sum(weights.values())
        weights = {k: v / total for k, v in weights.items()}

    score = round(sum(parts[k] * weights[k] for k in parts), 1)
    return LayerScore(score=score, reasons=reasons + flags)


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    venues = [
        ("Davis Square (CVS wall)", 42.3967, -71.1226, 350, 350),
        ("Union Square plaza", 42.3793, -71.0951, 500, 500),
        ("Assembly Row garage", 42.3925, -71.0772, 800, 800),
        ("Davis Sq — 600-person overflow", 42.3967, -71.1226, 600, 300),
    ]
    for name, lat, lng, crowd, cap in venues:
        res = score_crowd(lat, lng, expected_crowd=crowd, venue_capacity=cap)
        print(f"\n{name}  ->  CROWD SCORE {res.score}")
        for r in res.reasons:
            print(f"   - {r}")
