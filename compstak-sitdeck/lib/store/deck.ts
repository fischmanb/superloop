import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface DeckFilters {
  market: string;
  submarket: string;
  propertyType: string;
  dateRange: string;
  buildingClass: string;
}

export interface WidgetLayout {
  i: string;
  x: number;
  y: number;
  w: number;
  h: number;
  widgetType: string;
  config: Record<string, unknown>;
}

export interface Deck {
  id: string;
  name: string;
  filters: DeckFilters;
  widgets: WidgetLayout[];
}

interface DeckStore {
  activeDeckId: string;
  decks: Record<string, Deck>;
  setActiveDeck: (deckId: string) => void;
  updateDeckFilters: (deckId: string, filters: Partial<DeckFilters>) => void;
  updateWidgetLayout: (deckId: string, widgets: WidgetLayout[]) => void;
}

const DEFAULT_DECK: Deck = {
  id: "command-center",
  name: "Command Center",
  filters: {
    market: "New York City",
    submarket: "",
    propertyType: "",
    dateRange: "12mo",
    buildingClass: "",
  },
  widgets: [
    {
      i: "cre-property-map-1",
      x: 0,
      y: 0,
      w: 12,
      h: 8,
      widgetType: "cre-property-map",
      config: {},
    },
  ],
};

export const useDeckStore = create<DeckStore>()(
  persist(
    (set) => ({
      activeDeckId: "command-center",
      decks: { "command-center": DEFAULT_DECK },

      setActiveDeck: (deckId) => set({ activeDeckId: deckId }),

      updateDeckFilters: (deckId, filters) =>
        set((state) => ({
          decks: {
            ...state.decks,
            [deckId]: {
              ...state.decks[deckId],
              filters: { ...state.decks[deckId].filters, ...filters },
            },
          },
        })),

      updateWidgetLayout: (deckId, widgets) =>
        set((state) => ({
          decks: {
            ...state.decks,
            [deckId]: { ...state.decks[deckId], widgets },
          },
        })),
    }),
    { name: "sitdeck-deck-store" }
  )
);
