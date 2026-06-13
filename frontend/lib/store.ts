import { create } from "zustand";
import type { Filters } from "./types";

interface AppState {
  selectedSpotId: string | null;
  filters: Filters;
  setSelectedSpotId: (id: string | null) => void;
  setFilters: (partial: Partial<Filters>) => void;
}

export const useAppStore = create<AppState>((set) => ({
  selectedSpotId: null,
  filters: {
    timeOfDay: 18,
    minCapacity: 0,
    expectedCrowd: 0,
    needsPower: false,
    nearBar: false,
    needsTransit: false,
    lowTrafficOnly: false,
    priorPermits: false,
    avoidQuietHours: false,
    goodEgress: false,
    sort: "score",
  },
  setSelectedSpotId: (id) => set({ selectedSpotId: id }),
  setFilters: (partial) =>
    set((state) => ({ filters: { ...state.filters, ...partial } })),
}));
