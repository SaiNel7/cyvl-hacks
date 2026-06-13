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

export type InventoryStatus = "available" | "booked" | "hold";
export type AdFormat = "projection" | "banner" | "plaza_wrap" | "digital_overlay";

export interface AdSlot {
  id: string;
  spot_id: string;
  spot_name: string;
  neighborhood: string;
  format: AdFormat;
  wall_area_m2: number;
  price_usd: number;
  est_impressions: number;
  cpm_usd: number;
  event_window: string;
  status: InventoryStatus;
  buyer?: string;
}

export type VendorCategory = "food" | "merch" | "beverage" | "retail";
export type TrafficZone = "premium" | "standard" | "economy";

export interface VendorStall {
  id: string;
  spot_id: string;
  spot_name: string;
  neighborhood: string;
  position: string;
  traffic_zone: TrafficZone;
  category: VendorCategory;
  dimensions: string;
  price_usd: number;
  foot_traffic_score: number;
  event_window: string;
  status: InventoryStatus;
  vendor?: string;
}

export interface Activation {
  id: string;
  name: string;
  spot_id: string;
  spot_name: string;
  date: string;
  expected_crowd: number;
  ad_slots_sold: number;
  vendor_stalls_sold: number;
  city_approved: boolean;
  safety_score: number;
}

export interface PlatformStats {
  city: string;
  grant_pool_usd: number;
  grant_communities: number;
  total_surfaces: number;
  rentable_surfaces: number;
  ad_slots_total: number;
  ad_slots_available: number;
  vendor_stalls_total: number;
  vendor_stalls_available: number;
  upcoming_activations: number;
  est_weekend_revenue_usd: number;
  neighborhoods: Array<{
    name: string;
    surfaces: number;
    activation_ready: number;
  }>;
}
