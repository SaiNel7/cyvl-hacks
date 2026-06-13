"use client";

import { useAppStore } from "@/lib/store";
import { formatHour } from "@/lib/scoring";
import { Clock, Users, Zap, Beer } from "lucide-react";

const CAPACITY_OPTIONS = [
  { label: "Any size", value: 0 },
  { label: "100+", value: 100 },
  { label: "200+", value: 200 },
  { label: "500+", value: 500 },
];

const HOUR_OPTIONS = [12, 15, 18, 21];

export function MapFilterBar() {
  const filters = useAppStore((s) => s.filters);
  const setFilters = useAppStore((s) => s.setFilters);

  return (
    <div className="flex flex-wrap items-center gap-3 brut-border-b bg-brut-white px-4 py-3 md:px-6">
      <p className="mr-auto text-sm font-extrabold uppercase tracking-tight">
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
      <button
        type="button"
        onClick={() => setFilters({ needsPower: !filters.needsPower })}
        className={`brut-btn ${filters.needsPower ? "brut-btn-active" : ""}`}
        aria-pressed={filters.needsPower}
      >
        <Zap className="h-4 w-4" strokeWidth={2.5} />
        Power
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
  );
}
