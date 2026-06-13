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

export function MapFilterBar() {
  const filters = useAppStore((s) => s.filters);
  const setFilters = useAppStore((s) => s.setFilters);

  return (
    <div className="flex flex-wrap items-center gap-2 brut-border-b bg-brut-white px-4 py-3 md:gap-3 md:px-6">
      <p className="mr-auto w-full text-sm font-extrabold uppercase tracking-tight sm:w-auto">
        Score spots for your watch party
      </p>

      <label className="brut-input">
        <Clock className="h-4 w-4 shrink-0" strokeWidth={2.5} />
        <select
          value={filters.timeOfDay}
          onChange={(e) => setFilters({ timeOfDay: Number(e.target.value) })}
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
          value={filters.minCapacity}
          onChange={(e) =>
            setFilters({ minCapacity: Number(e.target.value) })
          }
          aria-label="Minimum capacity"
        >
          {CAPACITY_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </label>

      <label className="brut-input" title="Filters overflow / spill risk">
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
        title="MBTA subway/rail or bus stops nearby"
      >
        <TrainFront className="h-4 w-4" strokeWidth={2.5} />
        Transit
      </button>

      <button
        type="button"
        onClick={() => setFilters({ goodEgress: !filters.goodEgress })}
        className={`brut-btn ${filters.goodEgress ? "brut-btn-active" : ""}`}
        aria-pressed={filters.goodEgress}
        title="No egress chokepoints"
      >
        <Route className="h-4 w-4" strokeWidth={2.5} />
        Egress
      </button>

      <button
        type="button"
        onClick={() => setFilters({ lowTrafficOnly: !filters.lowTrafficOnly })}
        className={`brut-btn ${filters.lowTrafficOnly ? "brut-btn-active" : ""}`}
        aria-pressed={filters.lowTrafficOnly}
        title="Low adjacent road traffic (AADT)"
      >
        <Car className="h-4 w-4" strokeWidth={2.5} />
        Low traffic
      </button>

      <button
        type="button"
        onClick={() => setFilters({ nearBar: !filters.nearBar })}
        className={`brut-btn ${filters.nearBar ? "brut-btn-active" : ""}`}
        aria-pressed={filters.nearBar}
        title="Licensed alcohol within 200m"
      >
        <Beer className="h-4 w-4" strokeWidth={2.5} />
        Near bar
      </button>

      <button
        type="button"
        onClick={() => setFilters({ priorPermits: !filters.priorPermits })}
        className={`brut-btn ${filters.priorPermits ? "brut-btn-active" : ""}`}
        aria-pressed={filters.priorPermits}
        title="Prior public-event permits nearby"
      >
        <CalendarCheck className="h-4 w-4" strokeWidth={2.5} />
        Permits
      </button>

      <button
        type="button"
        onClick={() => setFilters({ avoidQuietHours: !filters.avoidQuietHours })}
        className={`brut-btn ${filters.avoidQuietHours ? "brut-btn-active" : ""}`}
        aria-pressed={filters.avoidQuietHours}
        title="Exclude residential quiet-hour zones at event time"
      >
        <VolumeX className="h-4 w-4" strokeWidth={2.5} />
        No quiet hrs
      </button>

      <button
        type="button"
        onClick={() => setFilters({ needsPower: !filters.needsPower })}
        className={`brut-btn ${filters.needsPower ? "brut-btn-active" : ""}`}
        aria-pressed={filters.needsPower}
        title="Power likely on-site (Somerville data unverified)"
      >
        <Zap className="h-4 w-4" strokeWidth={2.5} />
        Power
      </button>
    </div>
  );
}
