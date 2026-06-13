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

function parseFilters(searchParams: URLSearchParams): Filters {
  return {
    timeOfDay: Number(searchParams.get("time_of_day") ?? 18),
    minCapacity: Number(searchParams.get("min_capacity") ?? 0),
    expectedCrowd: Number(searchParams.get("expected_crowd") ?? 0),
    needsPower: searchParams.get("needs_power") === "true",
    nearBar: searchParams.get("near_bar") === "true",
    needsTransit: searchParams.get("needs_transit") === "true",
    lowTrafficOnly: searchParams.get("low_traffic") === "true",
    priorPermits: searchParams.get("prior_permits") === "true",
    avoidQuietHours: searchParams.get("avoid_quiet_hours") === "true",
    goodEgress: searchParams.get("good_egress") === "true",
    sort: (searchParams.get("sort") as Filters["sort"]) ?? "score",
  };
}

export async function GET(request: NextRequest) {
  const filters = parseFilters(request.nextUrl.searchParams);

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
        metrics: spot.metrics,
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
