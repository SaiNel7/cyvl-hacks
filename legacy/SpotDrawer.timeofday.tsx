"use client";

import useSWR from "swr";
import { X } from "lucide-react";
import { fetcher } from "@/lib/fetcher";
import { useAppStore } from "@/lib/store";
import { adjustedScore, formatImpressions, isRentable } from "@/lib/scoring";
import type { Spot, SpotDetail } from "@/lib/types";
import { ScoreBadge } from "./ScoreBadge";

const LAYER_LABELS: Record<keyof SpotDetail["layers"], string> = {
  physical: "Physical",
  safety: "Safety",
  crowd: "Crowd",
  functionality: "Function",
};

function layerBarClass(score: number): string {
  if (score >= 85) return "brut-bar-green";
  if (score >= 60) return "brut-bar-yellow";
  return "brut-bar-pink";
}

export function SpotDrawer({ spot }: { spot: Spot | null }) {
  const selectedSpotId = useAppStore((s) => s.selectedSpotId);
  const setSelectedSpotId = useAppStore((s) => s.setSelectedSpotId);
  const timeOfDay = useAppStore((s) => s.filters.timeOfDay);

  const { data: detail } = useSWR<SpotDetail>(
    selectedSpotId
      ? `/api/spots/${selectedSpotId}?time_of_day=${timeOfDay}`
      : null,
    fetcher
  );

  if (!selectedSpotId || !spot) return null;

  const displayScore = adjustedScore(spot, timeOfDay);
  const isBadExample = displayScore < 60;
  const rentable = isRentable(spot, timeOfDay);
  const impressions = detail?.est_impressions_per_event;

  return (
    <div className="pointer-events-none absolute inset-x-0 bottom-0 z-20 flex justify-center p-4 md:p-6">
      <div className="brut-drawer-enter pointer-events-auto w-full max-w-4xl brut-border brut-shadow bg-brut-white">
        {/* Header */}
        <div className="flex items-start justify-between gap-4 brut-border-b bg-brut-yellow px-5 py-5 md:px-6">
          <div className="min-w-0">
            {isBadExample && (
              <span className="mb-2 inline-block brut-border bg-brut-pink px-3 py-1 text-xs font-extrabold uppercase tracking-wide">
                Bad example — see why this fails
              </span>
            )}
            <h3 className="text-xl font-extrabold uppercase leading-tight tracking-tight md:text-2xl">
              {spot.name}
            </h3>
            <p className="mt-2 text-sm font-bold">
              ~{spot.capacity} people · {spot.height_m}m wall
              {rentable && impressions != null && (
                <>
                  {" "}
                  · Est. impressions: {formatImpressions(impressions)}/event
                </>
              )}
            </p>
          </div>
          <div className="flex shrink-0 items-start gap-3">
            <ScoreBadge score={displayScore} size="lg" />
            <button
              type="button"
              onClick={() => setSelectedSpotId(null)}
              className="brut-btn brut-btn-icon"
              aria-label="Close"
            >
              <X className="h-5 w-5" strokeWidth={3} />
            </button>
          </div>
        </div>

        {detail?.layers && (
          <div className="grid gap-4 p-5 sm:grid-cols-2 md:gap-5 md:p-6">
            {(Object.keys(detail.layers) as Array<keyof SpotDetail["layers"]>).map(
              (key) => {
                const layer = detail.layers[key];
                return (
                  <div key={key} className="brut-card-static p-4">
                    <div className="mb-3 flex items-center justify-between gap-2">
                      <span className="text-sm font-extrabold uppercase tracking-wide">
                        {LAYER_LABELS[key]}
                      </span>
                      <span className="brut-border bg-brut-black px-2 py-0.5 text-sm font-extrabold tabular-nums text-brut-white">
                        {layer.score}
                      </span>
                    </div>
                    <div className="brut-bar-track mb-4">
                      <div
                        className={`h-full ${layerBarClass(layer.score)}`}
                        style={{ width: `${layer.score}%` }}
                      />
                    </div>
                    <ul className="space-y-2">
                      {layer.reasons.map((reason) => (
                        <li
                          key={reason}
                          className="border-l-4 border-brut-black pl-3 text-sm font-medium leading-snug"
                        >
                          {reason}
                        </li>
                      ))}
                    </ul>
                  </div>
                );
              }
            )}
          </div>
        )}
      </div>
    </div>
  );
}
