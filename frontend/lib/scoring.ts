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
  }));
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
  return Math.max(0, Math.min(100, spot.overall_score - penalty + bonus));
}

export function filterSpots(spots: Spot[], filters: Filters): Spot[] {
  return spots.filter((spot) => {
    if (filters.minCapacity > 0 && spot.capacity < filters.minCapacity) {
      return false;
    }
    if (filters.needsPower && !spot.badges.includes("power")) {
      return false;
    }
    if (filters.nearBar && !spot.badges.includes("near_bar")) {
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
        const aTransit = a.badges.includes("transit") ? 1 : 0;
        const bTransit = b.badges.includes("transit") ? 1 : 0;
        return bTransit - aTransit || b.overall_score - a.overall_score;
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
};
