import type { Polygon } from "geojson";

export interface Spot {
  id: string;
  name: string;
  geometry: Polygon;
  height_m: number;
  facing_deg: number;
  overall_score: number;
  capacity: number;
  badges: Badge[];
}

export type Badge =
  | "good_sun"
  | "bad_sun"
  | "transit"
  | "power"
  | "near_bar"
  | "prior_events"
  | "wide_sidewalk";

export interface LayerScore {
  score: number;
  reasons: string[];
}

export interface SpotDetail extends Spot {
  layers: {
    physical: LayerScore;
    safety: LayerScore;
    crowd: LayerScore;
    functionality: LayerScore;
  };
  imagery_url?: string;
  /** LiDAR-derived audience × dwell estimate for ad inventory */
  est_impressions_per_event?: number;
}

export interface Filters {
  timeOfDay: number;
  minCapacity: number;
  needsPower: boolean;
  nearBar: boolean;
  sort: "score" | "capacity" | "transit";
}

export interface SpotFeatureProperties {
  id: string;
  name: string;
  height_m: number;
  facing_deg: number;
  overall_score: number;
  capacity: number;
  badges: Badge[];
}

export interface SpotsGeoJSON {
  type: "FeatureCollection";
  features: Array<{
    type: "Feature";
    properties: SpotFeatureProperties;
    geometry: Polygon;
  }>;
}

export type SpotDetailMap = Record<
  string,
  {
    layers: SpotDetail["layers"];
    imagery_url?: string;
    est_impressions_per_event?: number;
  }
>;
