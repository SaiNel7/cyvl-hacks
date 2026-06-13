import type { AdFormat, InventoryStatus, TrafficZone, VendorCategory } from "./types";

export function formatUsd(amount: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(amount);
}

export function formatImpressions(count: number): string {
  return count.toLocaleString("en-US");
}

export const AD_FORMAT_LABELS: Record<AdFormat, string> = {
  projection: "Wall projection",
  banner: "Banner",
  plaza_wrap: "Plaza signage",
  digital_overlay: "Screen overlay",
};

export const STATUS_LABELS: Record<InventoryStatus, string> = {
  available: "Available",
  booked: "Booked",
  hold: "On hold",
};

export const TRAFFIC_ZONE_LABELS: Record<TrafficZone, string> = {
  premium: "Premium zone",
  standard: "Standard",
  economy: "Economy",
};

export const VENDOR_CATEGORY_LABELS: Record<VendorCategory, string> = {
  food: "Food",
  merch: "Merchandise",
  beverage: "Beverage",
  retail: "Retail",
};

export function statusColor(status: InventoryStatus): string {
  switch (status) {
    case "available":
      return "bg-brut-green";
    case "booked":
      return "bg-brut-pink";
    case "hold":
      return "bg-brut-yellow";
  }
}

export function trafficZoneColor(zone: TrafficZone): string {
  switch (zone) {
    case "premium":
      return "bg-brut-yellow";
    case "standard":
      return "bg-brut-blue text-white";
    case "economy":
      return "bg-brut-white";
  }
}
