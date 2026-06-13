"use client";

import { useMemo, useState } from "react";
import useSWR from "swr";
import Link from "next/link";
import { fetcher } from "@/lib/fetcher";
import { PageHeader } from "@/components/layout/PageHeader";
import { StatCard } from "@/components/layout/StatCard";
import {
  STATUS_LABELS,
  TRAFFIC_ZONE_LABELS,
  VENDOR_CATEGORY_LABELS,
  formatUsd,
  statusColor,
  trafficZoneColor,
} from "@/lib/marketplace";
import type { InventoryStatus, VendorStall } from "@/lib/types";

export default function VendorsPage() {
  const { data, isLoading } = useSWR<{ stalls: VendorStall[]; meta: { total: number; available: number } }>(
    "/api/vendor-stalls",
    fetcher
  );
  const [statusFilter] = useState<InventoryStatus | "all">("available");

  const stalls = data?.stalls ?? [];
  const filtered = useMemo(
    () =>
      stalls.filter((s) => statusFilter === "all" || s.status === statusFilter),
    [stalls, statusFilter]
  );

  const bySpot = useMemo(() => {
    const map = new Map<string, VendorStall[]>();
    for (const stall of filtered) {
      const list = map.get(stall.spot_id) ?? [];
      list.push(stall);
      map.set(stall.spot_id, list);
    }
    return map;
  }, [filtered]);

  return (
    <div className="flex-1">
      <PageHeader
        title="Vendors"
        subtitle="Food and merch stalls at watch party sites — ranked by foot traffic."
      />
      <section className="grid gap-4 p-4 sm:grid-cols-2 md:p-8">
        <StatCard
          label="Stall positions"
          value={isLoading ? "…" : String(data?.meta.total ?? 0)}
          detail={`${data?.meta.available ?? 0} available`}
          accent="lime"
        />
        <StatCard
          label="Event sites"
          value={String(bySpot.size)}
          detail="Somerville"
          accent="cyan"
        />
      </section>
      <section className="space-y-8 p-4 md:p-8">
        {Array.from(bySpot.entries()).map(([spotId, spotStalls]) => (
          <div key={spotId}>
            <h2 className="text-lg font-extrabold uppercase">{spotStalls[0].spot_name}</h2>
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              {spotStalls.map((stall) => (
                <div key={stall.id} className="brut-card-static bg-brut-yellow p-4">
                  <div className="flex justify-between gap-2">
                    <span className={`brut-border px-2 py-0.5 text-xs font-extrabold uppercase ${trafficZoneColor(stall.traffic_zone)}`}>
                      {TRAFFIC_ZONE_LABELS[stall.traffic_zone]}
                    </span>
                    <span className={`brut-border px-2 py-0.5 text-xs font-extrabold uppercase ${statusColor(stall.status)}`}>
                      {STATUS_LABELS[stall.status]}
                    </span>
                  </div>
                  <p className="mt-3 font-extrabold uppercase">{stall.position}</p>
                  <p className="mt-1 text-sm font-semibold">
                    {VENDOR_CATEGORY_LABELS[stall.category]} · {formatUsd(stall.price_usd)}
                  </p>
                </div>
              ))}
            </div>
          </div>
        ))}
      </section>
      <div className="px-4 pb-8 md:px-8">
        <Link href="/map" className="brut-btn">View venues on map</Link>
      </div>
    </div>
  );
}
