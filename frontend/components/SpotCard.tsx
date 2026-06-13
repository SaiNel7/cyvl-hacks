"use client";

import type { Spot } from "@/lib/types";
import { adjustedScore, isRentable } from "@/lib/scoring";
import { useAppStore } from "@/lib/store";
import { ScoreBadge, BadgeIcons, RentableBadge } from "./ScoreBadge";
import { Users } from "lucide-react";

interface SpotCardProps {
  spot: Spot;
  isSelected: boolean;
}

export function SpotCard({ spot, isSelected }: SpotCardProps) {
  const timeOfDay = useAppStore((s) => s.filters.timeOfDay);
  const setSelectedSpotId = useAppStore((s) => s.setSelectedSpotId);
  const score = adjustedScore(spot, timeOfDay);
  const rentable = isRentable(spot, timeOfDay);

  return (
    <button
      type="button"
      onClick={() => setSelectedSpotId(spot.id)}
      className={`brut-card w-full p-4 text-left ${
        isSelected ? "brut-card-selected" : ""
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="truncate text-base font-bold leading-tight">
            {spot.name}
          </p>
          <p className="mt-2 flex items-center gap-1.5 text-sm font-semibold">
            <Users className="h-4 w-4" strokeWidth={2.5} />
            ~{spot.capacity} capacity
          </p>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-2">
          <div className="flex items-center gap-1.5">
            {rentable && <RentableBadge />}
            <ScoreBadge score={score} />
          </div>
          <BadgeIcons badges={spot.badges} />
        </div>
      </div>
    </button>
  );
}
