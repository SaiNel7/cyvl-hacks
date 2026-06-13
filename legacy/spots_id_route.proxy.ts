import { NextRequest, NextResponse } from "next/server";
import { readFile } from "fs/promises";
import path from "path";
import { geoJsonToSpots } from "@/lib/scoring";
import type { SpotDetailMap, SpotsGeoJSON } from "@/lib/types";

async function loadData() {
  const spotsPath = path.join(process.cwd(), "public/data/spots.json");
  const detailPath = path.join(process.cwd(), "public/data/spots-detail.json");
  const [spotsRaw, detailRaw] = await Promise.all([
    readFile(spotsPath, "utf-8"),
    readFile(detailPath, "utf-8"),
  ]);
  return {
    geojson: JSON.parse(spotsRaw) as SpotsGeoJSON,
    details: JSON.parse(detailRaw) as SpotDetailMap,
  };
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  // Crime & functionality layers are time-of-day dependent; forward the hour.
  const timeOfDay = request.nextUrl.searchParams.get("time_of_day") ?? "18";

  // Prefer the live FastAPI backend when configured; on a reachable 404 surface it,
  // and on a network error fall back to the static dummy data below.
  const backend = process.env.BACKEND_URL;
  if (backend) {
    try {
      const res = await fetch(
        `${backend}/api/spots/${id}?time_of_day=${timeOfDay}`,
        { cache: "no-store" }
      );
      if (res.ok) return NextResponse.json(await res.json());
      if (res.status === 404) {
        return NextResponse.json({ error: "Spot not found" }, { status: 404 });
      }
    } catch {
      // network/backend error — fall through to static data
    }
  }

  const { geojson, details } = await loadData();
  const spots = geoJsonToSpots(geojson);
  const spot = spots.find((s) => s.id === id);
  const detail = details[id];

  if (!spot || !detail) {
    return NextResponse.json({ error: "Spot not found" }, { status: 404 });
  }

  return NextResponse.json({
    ...spot,
    layers: detail.layers,
    imagery_url: detail.imagery_url,
    est_impressions_per_event: detail.est_impressions_per_event,
  });
}
