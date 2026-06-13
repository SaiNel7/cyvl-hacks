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
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
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
