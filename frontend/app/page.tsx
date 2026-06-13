"use client";

import useSWR from "swr";
import Link from "next/link";
import { fetcher } from "@/lib/fetcher";
import { ModuleCard } from "@/components/layout/ModuleCard";
import { StatCard } from "@/components/layout/StatCard";
import type { Activation, PlatformStats } from "@/lib/types";

interface PlatformResponse {
  stats: PlatformStats;
  activations: Activation[];
}

export default function OverviewPage() {
  const { data } = useSWR<PlatformResponse>("/api/platform", fetcher);
  const stats = data?.stats;
  const activations = data?.activations ?? [];

  return (
    <div className="flex-1">
      <section className="brut-border-b bg-brut-pink px-4 py-12 md:px-8 md:py-16">
        <div className="flex flex-col gap-10 lg:flex-row lg:items-center lg:justify-between lg:gap-12">
          <div className="min-w-0">
            <span className="brut-border bg-brut-yellow px-3 py-1 text-xs font-extrabold uppercase">
              2026 World Cup
            </span>
            <h1 className="mt-6 max-w-3xl text-4xl font-extrabold uppercase leading-tight tracking-tight md:text-6xl lg:text-7xl">
              Find the best spot for your watch party
            </h1>
            <p className="mt-6 max-w-xl text-base font-semibold md:text-lg">
              CYVL LiDAR scores every plaza and projection wall in Somerville —
              shade, crowd, safety, power.
            </p>
            <Link href="/map" className="brut-btn brut-btn-primary mt-8">
              Find spots on the map →
            </Link>
          </div>
          <img
            src="/landingpage.png"
            alt="Watch party crew — a lineup of cartoon fans ready for the game"
            className="brut-border brut-shadow w-full bg-white lg:flex-1 lg:max-w-2xl xl:max-w-4xl"
          />
        </div>
      </section>

      {stats && (
        <>
          <section className="grid gap-4 p-4 sm:grid-cols-2 lg:grid-cols-4 md:p-8">
            <StatCard
              label="Scored venues"
              value={String(stats.total_surfaces)}
              detail={`${stats.rentable_surfaces} event-ready`}
              accent="yellow"
            />
            <StatCard
              label="Sponsor slots"
              value={`${stats.ad_slots_available}/${stats.ad_slots_total}`}
              detail="Open now"
              accent="pink"
            />
            <StatCard
              label="Vendor stalls"
              value={`${stats.vendor_stalls_available}/${stats.vendor_stalls_total}`}
              detail="At watch parties"
              accent="cyan"
            />
            <StatCard
              label="Watch parties"
              value={String(stats.upcoming_activations)}
              detail="Scheduled"
              accent="lime"
            />
          </section>

          <section className="grid gap-4 px-4 pb-8 sm:grid-cols-2 lg:grid-cols-4 md:px-8">
            <ModuleCard
              title="Find Spots"
              description="3D map with live scoring by time and crowd size."
              href="/map"
              stat={String(stats.rentable_surfaces)}
              statLabel="Ready"
              accent="yellow"
            />
            <ModuleCard
              title="Sponsors"
              description="Brand packages tied to each watch party."
              href="/advertising"
              stat={`${stats.ad_slots_available}`}
              statLabel="Open"
              accent="pink"
            />
            <ModuleCard
              title="Vendors"
              description="Food & merch stalls by foot traffic."
              href="/vendors"
              stat={`${stats.vendor_stalls_available}`}
              statLabel="Open"
              accent="cyan"
            />
            <ModuleCard
              title="Cities"
              description="Permits and safety scorecards."
              href="/city"
              stat={String(stats.upcoming_activations)}
              statLabel="Events"
              accent="lime"
            />
          </section>
        </>
      )}

      <section className="brut-border-t px-4 py-8 md:px-8">
        <h2 className="text-xl font-extrabold uppercase">Upcoming watch parties</h2>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[600px] border-collapse text-left text-sm">
            <thead>
              <tr className="brut-border-b bg-brut-yellow">
                <th className="p-3 font-extrabold uppercase">Event</th>
                <th className="p-3 font-extrabold uppercase">Venue</th>
                <th className="p-3 font-extrabold uppercase">Crowd</th>
                <th className="p-3 font-extrabold uppercase">Permit</th>
              </tr>
            </thead>
            <tbody>
              {activations.map((act) => (
                <tr key={act.id} className="brut-border-b">
                  <td className="p-3 font-bold">{act.name}</td>
                  <td className="p-3 font-semibold">{act.spot_name}</td>
                  <td className="p-3 tabular-nums">~{act.expected_crowd}</td>
                  <td className="p-3">
                    <span
                      className={`brut-border px-2 py-0.5 text-xs font-extrabold uppercase ${
                        act.city_approved ? "bg-brut-green" : "bg-brut-pink"
                      }`}
                    >
                      {act.city_approved ? "Approved" : "Pending"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
