export type BrutAccent = "yellow" | "pink" | "cyan" | "lime";

export const ACCENT_BG: Record<BrutAccent, string> = {
  yellow: "bg-brut-yellow",
  pink: "bg-brut-pink",
  cyan: "bg-brut-blue",
  lime: "bg-brut-green",
};

export const ACCENT_CYCLE: BrutAccent[] = ["yellow", "pink", "cyan", "lime"];

export function accentAt(index: number): BrutAccent {
  return ACCENT_CYCLE[index % ACCENT_CYCLE.length];
}
