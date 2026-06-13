import { NextRequest, NextResponse } from "next/server";
import { readFile } from "fs/promises";
import path from "path";
import {
  filterSpots,
  geoJsonToSpots,
  sortSpots,
} from "@/lib/scoring";
import type { Filters, SpotsGeoJSON } from "@/lib/types";

async function loadSpots(): Promise<SpotsGeoJSON> {
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

  const geojson = await loadSpots();
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
