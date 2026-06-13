import type { Badge } from "@/lib/types";
import { BADGE_LABELS } from "@/lib/scoring";
import {
  Sun,
  SunDim,
  TrainFront,
  Zap,
  Beer,
  CalendarCheck,
  Footprints,
} from "lucide-react";

const BADGE_ICONS: Record<Badge, React.ReactNode> = {
  good_sun: <Sun className="h-4 w-4" strokeWidth={2.5} />,
  bad_sun: <SunDim className="h-4 w-4" strokeWidth={2.5} />,
  transit: <TrainFront className="h-4 w-4" strokeWidth={2.5} />,
  power: <Zap className="h-4 w-4" strokeWidth={2.5} />,
  near_bar: <Beer className="h-4 w-4" strokeWidth={2.5} />,
  prior_events: <CalendarCheck className="h-4 w-4" strokeWidth={2.5} />,
  wide_sidewalk: <Footprints className="h-4 w-4" strokeWidth={2.5} />,
};

function scoreClasses(score: number): string {
  if (score >= 85) return "brut-score-green";
  if (score >= 60) return "brut-score-yellow";
  return "brut-score-pink";
}

export function ScoreBadge({
  score,
  size = "md",
}: {
  score: number;
  size?: "md" | "lg";
}) {
  const sizeClasses =
    size === "lg"
      ? "px-4 py-2 text-xl font-extrabold"
      : "px-3 py-1 text-base font-extrabold";

  return (
    <span
      className={`inline-flex items-center tabular-nums ${sizeClasses} ${scoreClasses(score)}`}
    >
      {Math.round(score)}
    </span>
  );
}

export function RentableBadge() {
  return (
    <span
      title="Rentable ad surface"
      className="inline-flex h-7 w-7 items-center justify-center brut-border bg-brut-green text-sm font-extrabold"
    >
      $
    </span>
  );
}

export function BadgeIcons({ badges }: { badges: Badge[] }) {
  return (
    <span className="inline-flex flex-wrap items-center justify-end gap-1">
      {badges.map((badge) => (
        <span
          key={badge}
          title={BADGE_LABELS[badge]}
          className="inline-flex items-center justify-center brut-border bg-brut-white p-1"
        >
          {BADGE_ICONS[badge]}
        </span>
      ))}
    </span>
  );
}
