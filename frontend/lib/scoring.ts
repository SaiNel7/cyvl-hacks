import type { Badge, Filters, Spot, SpotsGeoJSON } from "./types";

export function geoJsonToSpots(geojson: SpotsGeoJSON): Spot[] {
  return geojson.features.map((feature) => ({
    id: feature.properties.id,
    name: feature.properties.name,
    geometry: feature.geometry,
    height_m: feature.properties.height_m,
    facing_deg: feature.properties.facing_deg,
    overall_score: feature.properties.overall_score,
    capacity: feature.properties.capacity,
    badges: feature.properties.badges,
    metrics: feature.properties.metrics,
  }));
}

/** Police shift windows used by the crime layer (backend). */
export function eventShift(hour: number): "Day" | "Evening" | "Night" {
  if (hour >= 8 && hour <= 15) return "Day";
  if (hour >= 16 && hour <= 23) return "Evening";
  return "Night";
}

export function safetyScoreAtHour(spot: Spot, hour: number): number | null {
  const m = spot.metrics?.safety_by_hour;
  if (!m) return null;
  return m[String(hour)] ?? m["18"] ?? null;
}

export function noiseOkAtHour(spot: Spot, hour: number): boolean {
  const m = spot.metrics?.noise_ok_by_hour;
  if (!m) return true;
  return m[String(hour)] ?? true;
}

/** Time-of-day sun penalty: west-facing walls glare in evening; east-facing in morning. */
export function sunPenalty(facingDeg: number, hour: number): number {
  const isEvening = hour >= 17 && hour <= 21;
  const isMorning = hour >= 7 && hour <= 11;

  if (isEvening) {
    if (facingDeg >= 225 && facingDeg <= 315) return 25;
    if (facingDeg >= 45 && facingDeg <= 135) return -5;
  }
  if (isMorning) {
    if (facingDeg >= 45 && facingDeg <= 135) return 20;
    if (facingDeg >= 225 && facingDeg <= 315) return -5;
  }
  return 0;
}

export function adjustedScore(spot: Spot, hour: number): number {
  const penalty = sunPenalty(spot.facing_deg, hour);
  const hasBadSun = spot.badges.includes("bad_sun");
  const hasGoodSun = spot.badges.includes("good_sun");
  let bonus = 0;
  if (hasBadSun && penalty > 15) bonus = -10;
  if (hasGoodSun && penalty < 0) bonus = 5;

  let score = spot.overall_score - penalty + bonus;

  const safety = safetyScoreAtHour(spot, hour);
  if (safety != null) {
    score += (safety - 75) * 0.12;
  }
  if (!noiseOkAtHour(spot, hour)) {
    score -= 10;
  }

  return Math.max(0, Math.min(100, Math.round(score)));
}

export function hasLiquorNearby(spot: Spot): boolean {
  return (
    spot.badges.includes("near_bar") ||
    (spot.metrics?.liquor_count ?? 0) > 0
  );
}

export function hasTransitAccess(spot: Spot): boolean {
  return (
    spot.badges.includes("transit") ||
    (spot.metrics?.transit_score ?? 0) >= 60
  );
}

export function hasPriorPermits(spot: Spot): boolean {
  return (
    spot.badges.includes("prior_events") ||
    (spot.metrics?.prior_permits ?? 0) > 0
  );
}

export function hasLowTraffic(spot: Spot): boolean {
  const m = spot.metrics;
  if (!m) return false;
  return m.traffic_score >= 70 || m.adjacent_aadt < 12000;
}

export function hasGoodEgress(spot: Spot): boolean {
  const m = spot.metrics;
  if (!m) return spot.badges.includes("wide_sidewalk");
  return !m.chokepoint && m.egress_score >= 60;
}

export function crowdFits(spot: Spot, expectedCrowd: number): boolean {
  if (expectedCrowd <= 0) return true;
  return spot.capacity >= expectedCrowd;
}

export function filterSpots(spots: Spot[], filters: Filters): Spot[] {
  return spots.filter((spot) => {
    if (filters.minCapacity > 0 && spot.capacity < filters.minCapacity) {
      return false;
    }
    if (!crowdFits(spot, filters.expectedCrowd)) {
      return false;
    }
    if (filters.needsPower) {
      const ok =
        spot.badges.includes("power") || spot.metrics?.power_verified === true;
      if (!ok) return false;
    }
    if (filters.nearBar && !hasLiquorNearby(spot)) {
      return false;
    }
    if (filters.needsTransit && !hasTransitAccess(spot)) {
      return false;
    }
    if (filters.lowTrafficOnly && !hasLowTraffic(spot)) {
      return false;
    }
    if (filters.priorPermits && !hasPriorPermits(spot)) {
      return false;
    }
    if (filters.avoidQuietHours && !noiseOkAtHour(spot, filters.timeOfDay)) {
      return false;
    }
    if (filters.goodEgress && !hasGoodEgress(spot)) {
      return false;
    }
    return true;
  });
}

export function sortSpots(spots: Spot[], filters: Filters): Spot[] {
  const sorted = [...spots];
  switch (filters.sort) {
    case "capacity":
      return sorted.sort((a, b) => b.capacity - a.capacity);
    case "transit":
      return sorted.sort((a, b) => {
        const aT = a.metrics?.transit_score ?? (a.badges.includes("transit") ? 80 : 0);
        const bT = b.metrics?.transit_score ?? (b.badges.includes("transit") ? 80 : 0);
        return bT - aT || adjustedScore(b, filters.timeOfDay) - adjustedScore(a, filters.timeOfDay);
      });
    case "safety":
      return sorted.sort((a, b) => {
        const aS = safetyScoreAtHour(a, filters.timeOfDay) ?? a.overall_score;
        const bS = safetyScoreAtHour(b, filters.timeOfDay) ?? b.overall_score;
        return bS - aS;
      });
    case "traffic":
      return sorted.sort((a, b) => {
        const aT = a.metrics?.traffic_score ?? 0;
        const bT = b.metrics?.traffic_score ?? 0;
        return bT - aT;
      });
    case "score":
    default:
      return sorted.sort(
        (a, b) =>
          adjustedScore(b, filters.timeOfDay) -
          adjustedScore(a, filters.timeOfDay)
      );
  }
}

export function scoreToColor(score: number, alpha = 200): [number, number, number, number] {
  if (score >= 85) return [0, 210, 106, alpha]; // #00D26A
  if (score >= 60) return [255, 214, 0, alpha]; // #FFD600
  return [255, 92, 138, alpha]; // #FF5C8A
}

export function formatHour(hour: number): string {
  const h = hour % 12 || 12;
  const ampm = hour < 12 ? "am" : "pm";
  return `${h}${ampm}`;
}

/** Rentable ad inventory: scored surface with enough capacity for sponsors */
export function isRentable(spot: Spot, hour: number): boolean {
  return adjustedScore(spot, hour) >= 60 && spot.capacity >= 200;
}

export function formatImpressions(count: number): string {
  return count.toLocaleString("en-US");
}

export const BADGE_LABELS: Record<Badge, string> = {
  good_sun: "Good sun",
  bad_sun: "Glare risk",
  transit: "Transit",
  power: "Power",
  near_bar: "Near bar",
  prior_events: "Prior events",
  wide_sidewalk: "Wide sidewalk",
  good_egress: "Good egress",
  low_traffic: "Low traffic",
  good_cell: "Good cell",
};

/** Sub-signal labels matching backend crowd + functionality layers */
export const PART_LABELS: Record<string, string> = {
  traffic: "Traffic",
  egress: "Egress",
  transit: "Transit",
  overflow: "Overflow",
  liquor: "Liquor nearby",
  permit_history: "Permit history",
  noise: "Noise / zoning",
  cell: "Cell coverage",
};

export function isLayerFlag(reason: string): boolean {
  return (
    reason.includes("chokepoint") ||
    reason.includes("spill into") ||
    reason.includes("quiet-hours") ||
    reason.includes("unverified")
  );
}
