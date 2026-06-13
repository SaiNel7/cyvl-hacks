"use client";

import dynamic from "next/dynamic";
import useSWR from "swr";
import { MapFilterBar } from "@/components/MapFilterBar";
import { SpotList } from "@/components/SpotList";
import { SpotDrawer } from "@/components/SpotDrawer";
import { useAppStore } from "@/lib/store";
import { fetcher } from "@/lib/fetcher";
import { geoJsonToSpots } from "@/lib/scoring";
import { buildSpotsUrl } from "@/lib/spots-url";
import type { SpotsGeoJSON } from "@/lib/types";

const MapView = dynamic(
  () => import("@/components/MapView").then((m) => m.MapView),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-full flex-col items-center justify-center gap-4 bg-brut-yellow">
        <div className="brut-border brut-shadow bg-white px-8 py-6 text-center">
          <p className="text-2xl font-extrabold uppercase tracking-tight">
            Loading map
          </p>
          <p className="mt-2 text-sm font-semibold">Venues incoming…</p>
        </div>
      </div>
    ),
  }
);

export default function MapPage() {
  const filters = useAppStore((s) => s.filters);
  const selectedSpotId = useAppStore((s) => s.selectedSpotId);

  const { data } = useSWR<SpotsGeoJSON>(buildSpotsUrl(filters), fetcher);
  const spots = data ? geoJsonToSpots(data) : [];
  const selectedSpot = spots.find((s) => s.id === selectedSpotId) ?? null;

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <MapFilterBar />
      <div className="relative flex min-h-0 flex-1">
        <div className="relative min-w-0 flex-[7] brut-border-r">
          <MapView />
          {/* Drawer overlays the map only — the right sidebar stays visible. */}
          <SpotDrawer spot={selectedSpot} />
        </div>
        <div className="hidden min-w-0 flex-[3] md:block">
          <SpotList />
        </div>
      </div>
      <div className="brut-border-t bg-brut-white md:hidden">
        <div className="max-h-52 overflow-y-auto p-2">
          <SpotList compact />
        </div>
      </div>
    </div>
  );
}
