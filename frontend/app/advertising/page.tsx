"use client";

import { useMemo, useState } from "react";
import useSWR from "swr";
import Link from "next/link";
import { fetcher } from "@/lib/fetcher";
import { PageHeader } from "@/components/layout/PageHeader";
import { StatCard } from "@/components/layout/StatCard";
import {
  AD_FORMAT_LABELS,
  STATUS_LABELS,
  formatImpressions,
  formatUsd,
  statusColor,
} from "@/lib/marketplace";
import type { AdSlot, InventoryStatus } from "@/lib/types";

export default function AdvertisingPage() {
  const { data, isLoading } = useSWR<{ slots: AdSlot[]; meta: { total: number; available: number } }>(
    "/api/ad-slots",
    fetcher
  );
  const [statusFilter] = useState<InventoryStatus | "all">("available");

  const slots = data?.slots ?? [];
  const filtered = useMemo(
    () =>
      slots.filter((s) => statusFilter === "all" || s.status === statusFilter),
    [slots, statusFilter]
  );
  const totalValue = filtered
    .filter((s) => s.status === "available")
    .reduce((sum, s) => sum + s.price_usd, 0);

  return (
    <div className="flex-1">
      <PageHeader
        title="Sponsors"
        subtitle="Brands buy projection and banner packages at specific watch parties."
      />
      <section className="grid gap-4 p-4 sm:grid-cols-2 md:p-8">
        <StatCard
          label="Sponsor slots"
          value={isLoading ? "…" : String(data?.meta.total ?? 0)}
          detail={`${data?.meta.available ?? 0} available`}
          accent="yellow"
        />
        <StatCard
          label="Open packages"
          value={formatUsd(totalValue)}
          detail="Filtered"
          accent="pink"
        />
      </section>
      <section className="p-4 md:p-8">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[700px] border-collapse text-left text-sm">
            <thead>
              <tr className="brut-border-b bg-brut-blue text-white">
                <th className="p-3 font-extrabold uppercase">Venue</th>
                <th className="p-3 font-extrabold uppercase">Format</th>
                <th className="p-3 font-extrabold uppercase">Audience</th>
                <th className="p-3 font-extrabold uppercase">Price</th>
                <th className="p-3 font-extrabold uppercase">Status</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((slot) => (
                <tr key={slot.id} className="brut-border-b">
                  <td className="p-3 font-bold">{slot.spot_name}</td>
                  <td className="p-3">{AD_FORMAT_LABELS[slot.format]}</td>
                  <td className="p-3 tabular-nums">~{formatImpressions(slot.est_impressions)}</td>
                  <td className="p-3 font-extrabold">{formatUsd(slot.price_usd)}</td>
                  <td className="p-3">
                    <span className={`brut-border px-2 py-0.5 text-xs font-extrabold uppercase ${statusColor(slot.status)}`}>
                      {STATUS_LABELS[slot.status]}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Link href="/map" className="brut-btn mt-6">
          View venues on map
        </Link>
      </section>
    </div>
  );
}
