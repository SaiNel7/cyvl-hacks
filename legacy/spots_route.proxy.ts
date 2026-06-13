import { NextRequest, NextResponse } from "next/server";
import { readFile } from "fs/promises";
import path from "path";
import {
  filterSpots,
  geoJsonToSpots,
  sortSpots,
} from "@/lib/scoring";
import type { Filters, SpotsGeoJSON } from "@/lib/types";

async function loadSpots(timeOfDay: number): Promise<SpotsGeoJSON> {
  // Prefer the live FastAPI backend when configured; fall back to the static
  // dummy GeoJSON so the demo keeps working if the backend is down. The backend
  // ranks by the blended 4-layer score for the given hour, so forward it.
  const backend = process.env.BACKEND_URL;
  if (backend) {
    try {
      const res = await fetch(
        `${backend}/api/spots?time_of_day=${timeOfDay}`,
        { cache: "no-store" }
      );
      if (res.ok) return (await res.json()) as SpotsGeoJSON;
    } catch {
      // network/backend error — fall through to static data
    }
  }
  const filePath = path.join(process.cwd(), "public/data/spots.json");
  const raw = await readFile(filePath, "utf-8");
  return JSON.parse(raw) as SpotsGeoJSON;
}

export async function GET(request: NextRequest) {
  const { searchParams } = request.nextUrl;

  const filters: Filters = {
    timeOfDay: Number(searchParams.get("time_of_day") ?? 18),
    minCapacity: Number(searchParams.get("min_capacity") ?? 0),
    needsPower: searchParams.get("needs_power") === "true",
    nearBar: searchParams.get("near_bar") === "true",
    sort: (searchParams.get("sort") as Filters["sort"]) ?? "score",
  };

  const geojson = await loadSpots(filters.timeOfDay);
  let spots = geoJsonToSpots(geojson);
  spots = filterSpots(spots, filters);
  spots = sortSpots(spots, filters);

  const features = spots.map((spot) => {
    const original = geojson.features.find((f) => f.properties.id === spot.id)!;
    return {
      type: "Feature" as const,
      properties: {
        id: spot.id,
        name: spot.name,
        height_m: spot.height_m,
        facing_deg: spot.facing_deg,
        overall_score: spot.overall_score,
        capacity: spot.capacity,
        badges: spot.badges,
      },
      geometry: original.geometry,
    };
  });

  return NextResponse.json({
    type: "FeatureCollection",
    features,
    meta: { filters, count: features.length },
  });
}
