import { ACCENT_BG, type BrutAccent } from "@/lib/brut-colors";

interface StatCardProps {
  label: string;
  value: string;
  detail?: string;
  accent: BrutAccent;
}

export function StatCard({ label, value, detail, accent }: StatCardProps) {
  return (
    <div className={`brut-card-static p-4 md:p-5 ${ACCENT_BG[accent]}`}>
      <p className="text-xs font-bold uppercase tracking-wide">{label}</p>
      <p className="mt-2 text-3xl font-extrabold tabular-nums md:text-5xl">
        {value}
      </p>
      {detail && (
        <p className="mt-1 text-xs font-semibold">{detail}</p>
      )}
    </div>
  );
}
