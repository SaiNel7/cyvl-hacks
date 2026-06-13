# Frontend MVP — "City as Venue" Watch Party Finder

> Consumer-facing app that surfaces the best public spots in Somerville, MA to host a World Cup / NBA watch party. Built on LiDAR-derived projectable surfaces — **not** a Google Maps pin dump. The geometry *is* the product.

**Scope of this doc:** the frontend only. The Python/FastAPI scoring pipeline is a separate workstream; this app consumes its output via a fixed contract (see [API Contract](#api-contract)). You can build the entire app against the dummy data in this doc before the real pipeline is ready.

---

## Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Framework | **Next.js (App Router) + TypeScript** | Highest vibe-coding velocity; routing + API routes + frontend in one repo |
| Styling | **Tailwind CSS** | Fast, consistent, AI tools generate it well |
| 3D / Map | **deck.gl + MapLibre GL** | LiDAR-native WebGL rendering of extruded surfaces over a free base map. This is the "use LiDAR, don't be Google Maps" answer |
| State | **Zustand** (or React Context) | Lightweight global store for selected spot + filters. Skip Redux |
| Data fetching | **SWR** | Tiny, cache-friendly, perfect for read-only GeoJSON |
| Icons | **lucide-react** | Clean consumer-grade iconography |
| Deploy | **Vercel** (local for demo is fine too) | One-click for Next |

### Key dependencies

```bash
npm install deck.gl @deck.gl/react @deck.gl/layers @deck.gl/aggregation-layers \
            maplibre-gl react-map-gl \
            zustand swr lucide-react
# tailwind via create-next-app --tailwind
```

> **MapLibre token note:** MapLibre needs no token. Use a free style URL (e.g. a CARTO or MapTiler free style). If you use MapTiler put the key in `.env.local` as `NEXT_PUBLIC_MAPTILER_KEY`.

---

## Repo Structure

```
watchparty-frontend/
├── app/
│   ├── layout.tsx            # root layout, Tailwind globals
│   ├── page.tsx              # main screen (map + list + drawer)
│   └── api/
│       └── spots/
│           ├── route.ts      # GET /api/spots  (serves static GeoJSON in MVP)
│           └── [id]/route.ts # GET /api/spots/:id
├── components/
│   ├── MapView.tsx           # deck.gl + MapLibre, extruded surfaces
│   ├── SpotList.tsx          # right-hand scrollable list / "leaderboard"
│   ├── SpotCard.tsx          # one row: score, badges
│   ├── SpotDrawer.tsx        # detail panel, 4-layer breakdown
│   ├── FilterBar.tsx         # top bar: time-of-day, capacity, power, near-bar
│   └── ScoreBadge.tsx        # colored score pill + badge icons
├── lib/
│   ├── store.ts              # zustand: selectedSpotId, filters
│   ├── types.ts              # Spot, SpotDetail, Filters types
│   ├── scoring.ts            # client-side filter/sort helpers
│   └── fetcher.ts            # SWR fetcher
├── public/
│   └── data/
│       ├── spots.json        # dummy GeoJSON (see below)
│       └── spots-detail.json # dummy per-spot detail
├── .env.local
└── package.json
```

---

## Screen Layout (single screen, consumer-first)

```
┌────────────────────────────────────────────────────────────┐
│  [FilterBar]  time:6pm ▼   capacity:200+ ▼  ⚡power  🍺near-bar │
├──────────────────────────────────────────┬─────────────────┤
│                                            │  Sort: Score ▼  │
│                                            │ ┌─────────────┐ │
│            MapView (deck.gl 3D)            │ │ SpotCard    │ │
│      extruded projectable surfaces         │ │ 92 ☀️🚇⚡     │ │
│      tilted camera, color = score          │ ├─────────────┤ │
│                                            │ │ SpotCard 87 │ │
│                                            │ └─────────────┘ │
├────────────────────────────────────────────┴─────────────────┤
│  [SpotDrawer] slides up when a spot is selected               │
│   Physical 90 · Safety 85 · Crowd 78 · Function 95            │
└────────────────────────────────────────────────────────────┘
```

- **Map ~70%**, list docked right (~30%), collapses on mobile to a bottom sheet.
- **No standalone leaderboard** — it's the list with `sort=score`.
- Clicking a card flies the camera to that surface; clicking a surface opens the drawer.
- **Time-of-day filter recolors the map** (safety + sun are time-dependent). Best live-demo moment.

---

## Core Interactions / User Flow (Consumer)

1. Land on map → city lit up with color-coded projectable surfaces.
2. Adjust **FilterBar** (e.g. "I need a spot for ~300 people at 9pm with power").
3. Map + list re-rank live. Bad-at-9pm spots dim/red.
4. Tap a glowing wall or a list card → **SpotDrawer** opens with the 4-layer story and human-readable reasoning ("West-facing — glare until ~7:30pm" / "Hosted 3 prior permitted events").
5. Drawer shows a "good vs bad example" framing so judges instantly get the value.

---

## API Contract

> This is the boundary you own. Lock these field names with the pipeline teammate early. In the MVP, `/api/spots` just reads `public/data/spots.json`; swap to the live FastAPI URL later via an env var.

### `GET /api/spots`
Returns a GeoJSON `FeatureCollection`. Query params (all optional): `time_of_day` (0–23), `min_capacity`, `needs_power` (bool), `near_bar` (bool), `sort` (`score`|`capacity`|`transit`).

### `GET /api/spots/:id`
Returns one `SpotDetail` with the full 4-layer breakdown + reasoning strings.

### TypeScript types (`lib/types.ts`)

```ts
export interface Spot {
  id: string;
  name: string;
  geometry: GeoJSON.Polygon;   // surface footprint (lat/lng ring)
  height_m: number;            // extrusion height for deck.gl
  facing_deg: number;          // surface normal bearing; 270 = west-facing
  overall_score: number;       // 0–100
  capacity: number;            // approx standing crowd
  badges: Badge[];             // quick-glance chips
}

export type Badge =
  | 'good_sun' | 'bad_sun' | 'transit' | 'power'
  | 'near_bar' | 'prior_events' | 'wide_sidewalk';

export interface LayerScore {
  score: number;               // 0–100
  reasons: string[];           // human-readable "why"
}

export interface SpotDetail extends Spot {
  layers: {
    physical: LayerScore;      // flat wall, sun, sidewalk width, transit
    safety: LayerScore;        // crime by incident-type + time-of-day
    crowd: LayerScore;         // capacity, chokepoints, bottleneck risk
    functionality: LayerScore; // power, network, noise zone, permit history
  };
  imagery_url?: string;        // 360°/streetview ref, optional
}
```

---

## Dummy Data

Drop this into `public/data/spots.json`. Coordinates are real-ish Somerville points (Davis Sq, Union Sq, Assembly, Powderhouse) so the map looks right.

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": {
        "id": "davis-statue-wall",
        "name": "Davis Square — CVS Blank Facade",
        "height_m": 12,
        "facing_deg": 90,
        "overall_score": 92,
        "capacity": 350,
        "badges": ["good_sun", "transit", "wide_sidewalk", "near_bar"]
      },
      "geometry": {
        "type": "Polygon",
        "coordinates": [[
          [-71.1226, 42.3967],[-71.1224, 42.3967],
          [-71.1224, 42.3969],[-71.1226, 42.3969],[-71.1226, 42.3967]
        ]]
      }
    },
    {
      "type": "Feature",
      "properties": {
        "id": "union-sq-plaza-wall",
        "name": "Union Square Plaza — East Retaining Wall",
        "height_m": 8,
        "facing_deg": 270,
        "overall_score": 74,
        "capacity": 500,
        "badges": ["bad_sun", "near_bar", "prior_events", "power"]
      },
      "geometry": {
        "type": "Polygon",
        "coordinates": [[
          [-71.0951, 42.3793],[-71.0949, 42.3793],
          [-71.0949, 42.3795],[-71.0951, 42.3795],[-71.0951, 42.3793]
        ]]
      }
    },
    {
      "type": "Feature",
      "properties": {
        "id": "assembly-row-garage",
        "name": "Assembly Row — Parking Garage South Wall",
        "height_m": 18,
        "facing_deg": 180,
        "overall_score": 88,
        "capacity": 800,
        "badges": ["good_sun", "transit", "power", "wide_sidewalk"]
      },
      "geometry": {
        "type": "Polygon",
        "coordinates": [[
          [-71.0772, 42.3925],[-71.0769, 42.3925],
          [-71.0769, 42.3928],[-71.0772, 42.3928],[-71.0772, 42.3925]
        ]]
      }
    },
    {
      "type": "Feature",
      "properties": {
        "id": "powderhouse-underpass",
        "name": "Powderhouse — Rail Underpass Wall",
        "height_m": 6,
        "facing_deg": 200,
        "overall_score": 41,
        "capacity": 120,
        "badges": ["bad_sun"]
      },
      "geometry": {
        "type": "Polygon",
        "coordinates": [[
          [-71.1085, 42.4015],[-71.1083, 42.4015],
          [-71.1083, 42.4017],[-71.1085, 42.4017],[-71.1085, 42.4015]
        ]]
      }
    }
  ]
}
```

Dummy detail for one spot (`public/data/spots-detail.json`, keyed by id):

```json
{
  "davis-statue-wall": {
    "id": "davis-statue-wall",
    "name": "Davis Square — CVS Blank Facade",
    "overall_score": 92,
    "capacity": 350,
    "layers": {
      "physical": { "score": 95, "reasons": [
        "Flat unobstructed brick facade, ~12m tall — no windows or signage",
        "East-facing — fully shaded after 4pm, ideal for evening projection",
        "4.5m sidewalk + adjacent plaza approximates 350 standing"
      ]},
      "safety": { "score": 90, "reasons": [
        "Incidents cluster 1–4am (bar closing); negligible 5–10pm",
        "High foot traffic = natural surveillance during event hours"
      ]},
      "crowd": { "score": 88, "reasons": [
        "Plaza absorbs crowd off the roadway — low bottleneck risk",
        "Two transit egress points (Red Line + bus) spread dispersal"
      ]},
      "functionality": { "score": 95, "reasons": [
        "City power pedestal 15m away",
        "Strong carrier coverage for live stream",
        "Hosted Honk! Festival staging — permit precedent exists"
      ]}
    }
  }
}
```

---

## deck.gl Rendering Notes

- Use a single **`SolidPolygonLayer`** (or `PolygonLayer`) with `extruded: true`, `getElevation: d => d.height_m`.
- `getFillColor` mapped from `overall_score`: green ≥85, yellow 60–84, red <60. Recompute on filter change.
- Initial `viewState` tilted: `{ pitch: 50, bearing: -20, zoom: 14, longitude: -71.10, latitude: 42.39 }` over Somerville.
- `onClick` → set `selectedSpotId` in the store → drawer opens, camera flies in.
- Optional flex: a `PointCloudLayer` sample of raw LiDAR points near a selected wall for the "whoa" factor. Cut if time-tight.

---

## Build Order (vibe-coding checklist)

1. `create-next-app` with TS + Tailwind. Add deps.
2. Static `/api/spots` + `/api/spots/[id]` reading the dummy JSON.
3. `MapView` with deck.gl extruded polygons over MapLibre. Get the 3D tilt looking good.
4. `SpotList` + `SpotCard` from the same data. Wire click → camera fly.
5. `SpotDrawer` with the 4-layer breakdown.
6. `FilterBar` → recolor/re-rank live (time-of-day is the showpiece).
7. Polish: badge icons, score colors, mobile bottom-sheet, one "bad example" spot to contrast.
8. Swap `NEXT_PUBLIC_API_URL` to the real FastAPI endpoint when the pipeline lands.

---

## Cut List (if running out of time)

- ❌ PointCloudLayer (nice-to-have only)
- ❌ Mobile bottom-sheet (desktop demo is fine)
- ❌ `near_bar` / `power` filters (keep time-of-day + capacity)
- ✅ Never cut: 3D extruded surfaces, score colors, the detail drawer story. That's the whole pitch.
