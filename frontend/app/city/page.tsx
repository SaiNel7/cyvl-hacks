"use client";

import useSWR from "swr";
import Link from "next/link";
import { fetcher } from "@/lib/fetcher";
import { PageHeader } from "@/components/layout/PageHeader";
import { StatCard } from "@/components/layout/StatCard";
import { formatUsd } from "@/lib/marketplace";
import type { Activation, PlatformStats } from "@/lib/types";

export default function CityPage() {
  const { data } = useSWR<{ stats: PlatformStats; activations: Activation[] }>(
    "/api/platform",
    fetcher
  );
  const stats = data?.stats;
  const activations = data?.activations ?? [];
  const approved = activations.filter((a) => a.city_approved).length;

  return (
    <div className="flex-1">
      <PageHeader
        title="Cities"
        subtitle="Review watch party venues with safety scorecards before issuing permits."
        action={
          <button type="button" className="brut-btn brut-btn-primary">
            Export GeoJSON
          </button>
        }
      />
      {stats && (
        <section className="grid gap-4 p-4 sm:grid-cols-3 md:p-8">
          <StatCard
            label="World Cup fund"
            value={formatUsd(stats.grant_pool_usd)}
            detail={`${stats.grant_communities} communities`}
            accent="yellow"
          />
          <StatCard
            label="Event-ready"
            value={`${stats.rentable_surfaces}/${stats.total_surfaces}`}
            detail="LiDAR scored"
            accent="pink"
          />
          <StatCard
            label="Permits OK"
            value={`${approved}/${activations.length}`}
            detail="Watch parties"
            accent="cyan"
          />
        </section>
      )}
      <section className="space-y-4 p-4 md:p-8">
        {activations.map((act) => (
          <div key={act.id} className="brut-card-static bg-brut-green p-4">
            <div className="flex flex-wrap justify-between gap-2">
              <div>
                <p className="font-extrabold uppercase">{act.name}</p>
                <p className="text-sm font-semibold">{act.spot_name}</p>
              </div>
              <span
                className={`brut-border px-2 py-0.5 text-xs font-extrabold uppercase ${
                  act.city_approved ? "bg-brut-yellow" : "bg-brut-pink"
                }`}
              >
                {act.city_approved ? "Approved" : "Pending"}
              </span>
            </div>
            <p className="mt-2 text-sm font-bold">
              ~{act.expected_crowd} people · Safety {act.safety_score}
            </p>
          </div>
        ))}
      </section>
      <div className="px-4 pb-8 md:px-8">
        <Link href="/map" className="brut-btn brut-btn-primary">
          Review venues on map
        </Link>
      </div>
    </div>
  );
}
