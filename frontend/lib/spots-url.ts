import type { Filters } from "./types";

export function buildSpotsUrl(filters: Filters): string {
  const params = new URLSearchParams({
    time_of_day: String(filters.timeOfDay),
    min_capacity: String(filters.minCapacity),
    expected_crowd: String(filters.expectedCrowd),
    needs_power: String(filters.needsPower),
    near_bar: String(filters.nearBar),
    needs_transit: String(filters.needsTransit),
    low_traffic: String(filters.lowTrafficOnly),
    prior_permits: String(filters.priorPermits),
    avoid_quiet_hours: String(filters.avoidQuietHours),
    good_egress: String(filters.goodEgress),
    sort: filters.sort,
  });
  return `/api/spots?${params}`;
}
