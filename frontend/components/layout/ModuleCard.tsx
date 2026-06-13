import Link from "next/link";
import { ACCENT_BG, type BrutAccent } from "@/lib/brut-colors";

interface ModuleCardProps {
  title: string;
  description: string;
  href: string;
  stat: string;
  statLabel: string;
  accent: BrutAccent;
}

export function ModuleCard({
  title,
  description,
  href,
  stat,
  statLabel,
  accent,
}: ModuleCardProps) {
  return (
    <Link href={href} className={`brut-card block p-6 ${ACCENT_BG[accent]}`}>
      <p className="text-xs font-bold uppercase tracking-wide">{statLabel}</p>
      <p className="mt-1 text-3xl font-extrabold tabular-nums">{stat}</p>
      <h2 className="mt-4 text-xl font-extrabold uppercase tracking-tight">
        {title}
      </h2>
      <p className="mt-2 text-sm font-semibold leading-snug">{description}</p>
      <span className="mt-4 inline-block text-sm font-extrabold uppercase underline">
        Open →
      </span>
    </Link>
  );
}
