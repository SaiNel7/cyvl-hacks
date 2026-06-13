"use client";

import { useAppStore } from "@/lib/store";
import { formatHour } from "@/lib/scoring";
import {
  Clock,
  Users,
  Zap,
  Beer,
  TrainFront,
  Route,
  CalendarCheck,
  VolumeX,
  Car,
} from "lucide-react";

const CAPACITY_OPTIONS = [
  { label: "Any size", value: 0 },
  { label: "100+", value: 100 },
  { label: "200+", value: 200 },
  { label: "500+", value: 500 },
];

const CROWD_OPTIONS = [
  { label: "Any crowd", value: 0 },
  { label: "~100", value: 100 },
  { label: "~200", value: 200 },
  { label: "~350", value: 350 },
  { label: "~500", value: 500 },
];

const HOUR_OPTIONS = [12, 15, 18, 21];

export function FilterBar() {
  const filters = useAppStore((s) => s.filters);
  const setFilters = useAppStore((s) => s.setFilters);

  return (
    <header className="flex flex-wrap items-center gap-3 brut-border-b bg-brut-yellow px-4 py-4 md:px-6">
      <div className="mr-auto min-w-0">
        <h1 className="text-xl font-extrabold uppercase leading-none tracking-tight md:text-2xl">
          BlockParty
        </h1>
        <p className="mt-1 text-sm font-semibold">
          Surface intelligence for cities &amp; brands
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2 md:gap-3">
        <label className="brut-input">
          <Clock className="h-4 w-4 shrink-0" strokeWidth={2.5} />
          <select
            value={filters.timeOfDay}
            onChange={(e) =>
              setFilters({ timeOfDay: Number(e.target.value) })
            }
            aria-label="Time of day"
          >
            {HOUR_OPTIONS.map((h) => (
              <option key={h} value={h}>
                {formatHour(h)}
              </option>
            ))}
          </select>
        </label>

        <label className="brut-input">
          <Users className="h-4 w-4 shrink-0" strokeWidth={2.5} />
          <select
            value={filters.expectedCrowd}
            onChange={(e) =>
              setFilters({ expectedCrowd: Number(e.target.value) })
            }
            aria-label="Expected crowd"
          >
            {CROWD_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>

        <button
          type="button"
          onClick={() => setFilters({ needsTransit: !filters.needsTransit })}
          className={`brut-btn ${filters.needsTransit ? "brut-btn-active" : ""}`}
          aria-pressed={filters.needsTransit}
        >
          <TrainFront className="h-4 w-4" strokeWidth={2.5} />
          Transit
        </button>

        <button
          type="button"
          onClick={() => setFilters({ goodEgress: !filters.goodEgress })}
          className={`brut-btn ${filters.goodEgress ? "brut-btn-active" : ""}`}
          aria-pressed={filters.goodEgress}
        >
          <Route className="h-4 w-4" strokeWidth={2.5} />
          Egress
        </button>

        <button
          type="button"
          onClick={() => setFilters({ avoidQuietHours: !filters.avoidQuietHours })}
          className={`brut-btn ${filters.avoidQuietHours ? "brut-btn-active" : ""}`}
          aria-pressed={filters.avoidQuietHours}
        >
          <VolumeX className="h-4 w-4" strokeWidth={2.5} />
          No quiet hrs
        </button>

        <button
          type="button"
          onClick={() => setFilters({ nearBar: !filters.nearBar })}
          className={`brut-btn ${filters.nearBar ? "brut-btn-active" : ""}`}
          aria-pressed={filters.nearBar}
        >
          <Beer className="h-4 w-4" strokeWidth={2.5} />
          Near bar
        </button>
      </div>
    </header>
  );
}
