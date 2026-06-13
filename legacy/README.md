# legacy/ — superseded backend-wiring approach

This folder preserves an earlier integration that wired the frontend to a **live
FastAPI backend** for the spot/venue data. The team later standardized on a
**static-precompute** approach (`scripts/precompute_venues.py` →
`frontend/public/data/spots.json` + `spots-detail.json`), so the code here is no
longer used. Kept for reference, not deleted.

| File | Was | Superseded by |
|---|---|---|
| `backend_main.with_spots_adapter.py` | `backend/main.py` with a `/api/spots` + `/api/spots/{id}` adapter that synthesized polygons, blended the 4 layers, and served `wall_scores.json` | `scripts/precompute_venues.py` (bakes the same layers into static JSON) |
| `score_layers.py` | `scripts/score_layers.py` — precomputed crime/crowd/functionality per hour into `data/wall_scores.json` | `scripts/precompute_venues.py` |
| `wall_scores.json` | sidecar consumed by the old `/api/spots` | `frontend/public/data/spots-detail.json` (`hourly`) |
| `spots_route.proxy.ts` | `frontend/app/api/spots/route.ts` that proxied `BACKEND_URL` with a static fallback | upstream route reads static JSON directly |
| `spots_id_route.proxy.ts` | `frontend/app/api/spots/[id]/route.ts` proxy | upstream route reads static JSON directly |
| `SpotDrawer.timeofday.tsx` | my `SpotDrawer.tsx` edit adding `time_of_day` to the detail fetch | upstream `SpotDrawer.tsx` (already time-aware) |

Note: the **voxel** feature still uses the live FastAPI backend
(`backend/main.py` `GET /api/walls/{id}/voxels` + the `BACKEND_URL` proxy in
`frontend/app/api/walls/[id]/voxels/route.ts`), so the FastAPI server is still
needed for 3D point clouds — just not for spots.
