# PRD: Third Space Finder
### Cyvl Hackathon — June 13, 2026 — Somerville, MA

> **"The best third spaces in your city already exist. Nobody mapped them yet."**

---

## 1. Problem

Third spaces — the parks, plazas, sidewalks, and blank walls where community actually forms — are disappearing not because they're gone but because no one can find them. This gap becomes visible at scale during spontaneous civic moments: Knicks watch parties spilling onto Manhattan sidewalks, World Cup crowds projecting onto random building walls. People want to gather. Cities want them to gather safely. Nobody has given either side a tool to make it happen.

The friction is real:
- Event organizers spend days scouting locations manually
- Cities have no data on where organic gathering already happens
- Crowds end up in wrong locations — bottlenecked on high-traffic arterials, on west-facing walls at sunset, in areas with poor egress or no power access
- Permit offices have no spatial intelligence to fast-track safe spots vs. flag risky ones

---

## 2. Solution

**Third Space Finder** turns Somerville's physical infrastructure into a ranked, filterable venue database for spontaneous and organized community events. It uses Cyvl's LiDAR geometry and 360° imagery — data no Google Maps project can touch — to identify, score, and surface every viable outdoor gathering space in the city.

Three user-facing products from one data pipeline:

| Facet | Who | What |
|---|---|---|
| **Spot Map** | General public | Browse and filter open spots by capacity, shade, projection suitability, transit proximity |
| **Organizer Dashboard** | Event hosts | Full venue scorecard, permit history, power access, noise ordinance, crowd flow |
| **City Intelligence View** | Government / permitting | Aggregate heatmap of third space potential, safety profiles, civic activation opportunities |

---

## 3. User Stories

**Consumer**
> "I want to watch the World Cup outside near Davis Square with ~50 people. Show me walls with good projection, shade, and safe egress."

- Lands on map view of Somerville
- Filters: event type (watch party), expected crowd (50), time of day (7pm), needs projector wall (yes), shade (yes)
- Sees ranked dots. Clicks one → photo from Cyvl 360° imagery, wall dimensions, crowd capacity, safety score, nearest transit, whether a bar is within 200m
- One-tap "Get Permit Info" → links to Somerville's event permit page with pre-filled location data

**Organizer**
> "I'm hosting a 200-person outdoor screening. I need a complete venue report to submit with my permit application."

- Enters address or clicks map
- Gets full venue scorecard PDF: wall suitability, crowd capacity, egress chokepoints flagged, noise ordinance zone, power access points, prior permit history, crime time-of-day profile
- Shareable link for city submission

**City / Permitting Office**
> "Where in Somerville are people most likely to gather, and which of those spots are actually safe to activate?"

- Dashboard view: all scored venues ranked by civic activation potential
- Filters by neighborhood, safety tier, infrastructure readiness
- Exportable GeoJSON for GIS integration

---

## 4. Scoring Model

Every venue gets a composite **Third Space Score (0–100)** from four independent layers. Each layer is independently visible so users and city officials can see exactly why a spot scored the way it did.

### Layer 1 — Physical Suitability (Cyvl)
*Can this space physically host an event?*

| Signal | Source | Weight |
|---|---|---|
| Wall area (m²) — minimum 15ft projectable surface | SAM3 + `cyvl.measure()` | 25% |
| Wall orientation — penalize west-facing after 4pm | `frame.camera_to_utm` pose | 15% |
| Sidewalk/plaza width → crowd capacity | `cyvl.measure()` + pavement layer | 20% |
| Shade coverage | Cyvl tree canopy + building shadow geometry | 15% |
| Surface obstructions (windows, signs, pipes) | SAM3 on 360° imagery | 25% |

Capacity formula:
```
usable_area_m2 = sidewalk_width_m × available_length_m
max_crowd = usable_area_m2 / 0.28  # 0.28 m² per standing person (crowd safety standard)
```

Good example: 18m × 9m blank gable end on a triple-decker, 12ft sidewalk, north-facing.
Bad example: West-facing brick wall with 4 windows, 4ft sidewalk on Holland St during rush hour.

### Layer 2 — Safety Profile (Boston PD Open Data)
*Is this space safe to activate at the time of the event?*

- Pull incident type, location, timestamp from Somerville/Boston PD public crime data
- Score by incident type × time-of-day pattern, NOT by neighborhood blanket label
- A plaza with car break-ins at 2am scores fine for a 6pm watch party
- Flag: assault/robbery incidents within 50m in the 4-hour window matching event time
- Display: "Last 12 months — 0 relevant incidents at this time of day" vs. specific flags

**Anti-redlining safeguard:** scores are time-gated and incident-type-specific. No neighborhood-level penalty. Each venue scored independently on its own incident history.

### Layer 3 — Crowd Dynamics (MassDOT + OSM)
*Can this space handle the crowd without spilling into traffic?*

| Signal | Source |
|---|---|
| Vehicle traffic volume (AADT) on adjacent road | MassDOT open data |
| Sidewalk overflow risk: crowd footprint vs. capacity | Cyvl geometry |
| Egress chokepoints: narrow exits, one-way pinches | OSM road network + Cyvl |
| Liquor license within 200m (bar nearby to serve crowd) | Somerville open data |
| Transit proximity: MBTA stop within 400m | MBTA GTFS |

Overflow flag logic:
```
if crowd_footprint_m2 > sidewalk_capacity_m2:
    flag("crowd will spill into roadway")
    apply traffic_volume_penalty
```

### Layer 4 — Venue Functionality
*Can an event actually run here?*

| Signal | Source |
|---|---|
| Power access within 50m (utility box, commercial outlet) | Somerville open data / OSM |
| Noise ordinance zone (residential quiet hours) | Somerville zoning data |
| Prior permit history at this address | Somerville permit records |
| Network/cell coverage (proxy: commercial density) | OSM land use |

---

## 5. Tech Stack

### Frontend
- **Next.js 14** (App Router)
- **Mapbox GL JS** — custom layer compositing, 3D building extrusion from LiDAR data, per-layer toggle
- **Tailwind CSS**
- **Deck.gl** — for heatmap and scatter layers on top of Mapbox

### Backend
- **FastAPI** (Python) — single service, async
- **PostGIS** (PostgreSQL + spatial extension) — all spatial joins, crime data, traffic data
- **geopandas + shapely + pyproj** — geometry operations, coordinate transforms
- **osmnx** — OSM road network, transit proximity

### Cyvl SDK
```python
pip install "cyvl[viz,sam] @ git+https://github.com/roadgnar/cyvl-spatial-sdk"
```
- `cyvl.load_scene("somerville")` — parquet cache, primary data source
- `frame.points_in_view()` — LiDAR into specific frames
- `cyvl.measure()` — real metric measurements from imagery
- `locate(frame, "blank building facade")` — SAM3 text → 3D wall detection
- `frame.camera_to_utm` — pose for wall orientation calculation
- Cyvl MCP — Claude Code natural language queries over infrastructure data

### AI Layer
- **Claude API** (`claude-sonnet-4-6`) with Cyvl MCP — natural language venue queries
- **SAM3 via fal.ai** — text-prompt wall detection, pre-computed not live
- **$200 Anthropic credits** from hackathon

### External Data
| Dataset | Source | Use |
|---|---|---|
| Crime incidents | Boston PD Open Data / Somerville PD | Safety layer |
| AADT traffic counts | MassDOT open data | Crowd dynamics |
| Road network | OSM via osmnx | Egress analysis |
| Transit stops | MBTA GTFS | Proximity scoring |
| Liquor licenses | Somerville open data | Venue functionality |
| Noise ordinance zones | Somerville zoning GIS | Functionality layer |
| Permit history | Somerville open data | Functionality layer |
| Power/utility access | OSM + Somerville open data | Functionality layer |
| Sun angle / shadow | `suncalc` Python lib + Cyvl building heights | Shade scoring |

---

## 6. Data Strategy

**Do not download 500GB.** The full Somerville point cloud is 514 LiDAR tiles. Use the pre-processed 120MB parquet cache for city-wide filtering, then pull individual tiles only for finalist venues.

```
215k features (parquet) 
    → bbox filter to target squares (Davis, Union, Ball, Teele)
    → ~8-10k features
    → sidewalk width + open space filter
    → ~500 candidates
    → manual review + map spot-check
    → ~50 frames for SAM3 wall detection
    → 15-20 final scored venues
```

Target neighborhoods for Somerville (in priority order):
1. **Davis Square** — highest foot traffic, existing informal gathering culture
2. **Union Square** — large open plazas, post-development open space
3. **Ball Square** — dense residential, blank triple-decker gables
4. **Teele Square** — underutilized, good candidate for discovery

Pre-compute and cache all SAM3 results. Never run wall detection live in the demo.

---

## 7. API Endpoints

```
GET  /venues
     ?lat=&lon=&radius_m=
     &min_capacity=
     &event_time=          # ISO datetime → affects safety + shade scoring
     &needs_projection=    # bool
     &needs_shade=         # bool
     &max_traffic_aadt=
     → ranked list of venues with scores

GET  /venues/{venue_id}
     → full scorecard: all 4 layers, 360° frame URL, wall dimensions,
       crowd capacity, egress flags, permit info, power access

GET  /venues/{venue_id}/frame
     → Cyvl 360° imagery frame for this venue with LiDAR overlay

POST /venues/query
     body: { "natural_language": "wall for 200 people near Davis Sq tonight" }
     → Claude + Cyvl MCP → ranked venues with explanation

GET  /city/heatmap
     → GeoJSON of all scored venues for city dashboard view
```

---

## 8. Repo Structure

```
third-space-finder/
├── README.md
├── PRD.md
├── docker-compose.yml          # PostGIS + FastAPI
│
├── backend/
│   ├── main.py                 # FastAPI app, all routes
│   ├── scoring/
│   │   ├── physical.py         # Layer 1: Cyvl geometry scoring
│   │   ├── crime.py            # Layer 2: crime data scoring
│   │   ├── crowd.py            # Layer 3: traffic + egress scoring
│   │   └── functionality.py    # Layer 4: power, noise, permits
│   ├── data/
│   │   ├── ingest_crime.py     # Boston PD CSV → PostGIS
│   │   ├── ingest_traffic.py   # MassDOT AADT → PostGIS
│   │   ├── ingest_transit.py   # MBTA GTFS → PostGIS
│   │   └── ingest_permits.py   # Somerville permits → PostGIS
│   ├── cyvl/
│   │   ├── scene.py            # Scene loading + caching
│   │   ├── walls.py            # SAM3 wall detection + measurement
│   │   └── precompute.py       # Pre-run SAM3 on all candidates
│   └── llm/
│       └── query.py            # Claude + Cyvl MCP natural language layer
│
├── frontend/
│   ├── app/
│   │   ├── page.tsx            # Map view (consumer)
│   │   ├── organizer/
│   │   │   └── page.tsx        # Organizer dashboard
│   │   └── city/
│   │       └── page.tsx        # City intelligence view
│   ├── components/
│   │   ├── Map.tsx             # Mapbox GL + layer toggles
│   │   ├── VenueCard.tsx       # Scorecard with 4-layer breakdown
│   │   ├── FrameViewer.tsx     # Embedded Cyvl 360° imagery
│   │   ├── FilterPanel.tsx     # Consumer filters
│   │   └── ScoreBreakdown.tsx  # Visual score explainer
│   └── lib/
│       └── api.ts              # API client
│
├── data/                       # Pre-downloaded public datasets
│   ├── crime/                  # Boston PD CSVs
│   ├── traffic/                # MassDOT AADT shapefiles
│   ├── transit/                # MBTA GTFS
│   └── somerville/             # Somerville open data
│
├── scripts/
│   ├── precompute_walls.py     # Run SAM3 on all candidates, cache results
│   ├── bootstrap_db.py         # Ingest all external data into PostGIS
│   └── validate_venues.py      # Sanity check scored venues against imagery
│
└── notebooks/
    ├── 01_explore_scene.ipynb  # Cyvl quickstart
    ├── 02_wall_candidates.ipynb # Narrowing from 215k → 50 candidates
    └── 03_scoring_dev.ipynb    # Scoring model development
```

---

## 9. Dependencies

```toml
# backend/pyproject.toml

[dependencies]
fastapi = ">=0.111"
uvicorn = ">=0.29"
geopandas = ">=0.14"
shapely = ">=2.0"
pyproj = ">=3.6"
osmnx = ">=1.9"
psycopg2-binary = ">=2.9"
sqlalchemy = ">=2.0"
geoalchemy2 = ">=0.14"
pandas = ">=2.0"
anthropic = ">=0.25"
suncalc = ">=0.1"
httpx = ">=0.27"
cyvl = {git = "https://github.com/roadgnar/cyvl-spatial-sdk", extras = ["viz", "sam"]}
```

```json
// frontend/package.json dependencies
{
  "next": "14",
  "mapbox-gl": "^3",
  "deck.gl": "^9",
  "@anthropic-ai/sdk": "latest",
  "tailwindcss": "^3",
  "swr": "^2"
}
```
---

## 10. Judging Criteria Mapping

| Criterion | How we address it |
|---|---|
| **Technical execution** | Cyvl SDK + SAM3 wall detection + PostGIS spatial joins — real data pipeline, no mocks |
| **Physical-AI fit** | LiDAR geometry → crowd capacity, wall suitability, shadow modeling. Cannot be done with any other data source |
| **Civic viability** | Direct output for city permitting office, anti-redlining safety model, permit fast-track pathway |
| **Demo clarity** | Consumer map → venue scorecard → contrast moment → NL query → city view. 5 clean beats |

---

