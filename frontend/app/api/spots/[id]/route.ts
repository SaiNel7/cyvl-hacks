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
  const hour = Number(request.nextUrl.searchParams.get("time_of_day") ?? 18);
  const expectedCrowd = Number(request.nextUrl.searchParams.get("expected_crowd") ?? 0);
  const hourKey = String(hour);

  const { geojson, details } = await loadData();
  const spots = geoJsonToSpots(geojson);
  const spot = spots.find((s) => s.id === id);
  const detail = details[id];

  if (!spot || !detail) {
    return NextResponse.json({ error: "Spot not found" }, { status: 404 });
  }

  const hourly = detail.hourly?.[hourKey] ?? detail.hourly?.["18"];
  let layers = {
    ...detail.layers,
    safety: hourly?.safety ?? detail.layers.safety,
    functionality: hourly?.functionality ?? detail.layers.functionality,
  };

  if (expectedCrowd > spot.capacity && layers.crowd.parts) {
    const over = expectedCrowd / spot.capacity - 1;
    const overflowScore = Math.max(0, 100 - over * 100);
    const spillFlag =
      "Crowd will spill into the roadway — apply traffic penalty / consider closure.";
    const flags = layers.crowd.flags ?? [];
    layers = {
      ...layers,
      crowd: {
        ...layers.crowd,
        score: Math.round(layers.crowd.score * 0.6 + overflowScore * 0.4),
        parts: { ...layers.crowd.parts, overflow: Math.round(overflowScore) },
        flags: flags.includes(spillFlag) ? flags : [...flags, spillFlag],
      },
    };
  }

  return NextResponse.json({
    ...spot,
    layers,
    imagery_url: detail.imagery_url,
    est_impressions_per_event: detail.est_impressions_per_event,
  });
}
