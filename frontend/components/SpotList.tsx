"use client";

import useSWR from "swr";
import { fetcher } from "@/lib/fetcher";
import { useAppStore } from "@/lib/store";
import { geoJsonToSpots } from "@/lib/scoring";
import { buildSpotsUrl } from "@/lib/spots-url";
import type { SpotsGeoJSON } from "@/lib/types";
import { SpotCard } from "./SpotCard";

interface SpotListProps {
  compact?: boolean;
}

export function SpotList({ compact = false }: SpotListProps) {
  const filters = useAppStore((s) => s.filters);
  const setFilters = useAppStore((s) => s.setFilters);
  const selectedSpotId = useAppStore((s) => s.selectedSpotId);

  const { data, isLoading } = useSWR<SpotsGeoJSON & { meta?: { count: number } }>(
    buildSpotsUrl(filters),
    fetcher,
    { keepPreviousData: true }
  );

  const spots = data ? geoJsonToSpots(data) : [];

  return (
    <aside className={`flex h-full flex-col bg-brut-white ${compact ? "" : "brut-border-l"}`}>
      <div
        className={`flex items-center justify-between gap-3 px-4 py-4 ${compact ? "bg-brut-blue text-white" : "brut-border-b bg-brut-black text-brut-white"}`}
      >
        <div>
          <h2 className="text-lg font-extrabold uppercase tracking-tight">
            Top spots
          </h2>
          <p className="mt-0.5 text-sm font-semibold opacity-90">
            {isLoading ? "Loading…" : `${spots.length} surfaces`}
          </p>
        </div>
        <label className="brut-input shrink-0 !min-h-0 !bg-white !py-2 !text-black">
          <span className="text-xs font-bold uppercase">Sort</span>
          <select
            value={filters.sort}
            onChange={(e) =>
              setFilters({ sort: e.target.value as typeof filters.sort })
            }
            aria-label="Sort spots"
          >
            <option value="score">Score</option>
            <option value="capacity">Capacity</option>
            <option value="transit">Transit</option>
            <option value="safety">Safety</option>
            <option value="traffic">Low traffic</option>
          </select>
        </label>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto bg-brut-white p-4">
        {spots.map((spot) => (
          <SpotCard
            key={spot.id}
            spot={spot}
            isSelected={selectedSpotId === spot.id}
          />
        ))}
        {!isLoading && spots.length === 0 && (
          <div className="brut-card px-4 py-8 text-center">
            <p className="text-base font-bold">No spots match</p>
            <p className="mt-2 text-sm font-semibold">
              Try loosening crowd size or toggles.
            </p>
          </div>
        )}
      </div>
    </aside>
  );
}
