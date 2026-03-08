"use client";

import { useDeckStore } from "@/lib/store/deck";

const MARKETS = [
  "New York City",
  "Chicago Metro",
  "Los Angeles - Orange - Inland",
  "Dallas - Ft. Worth",
  "Boston",
  "Bay Area",
  "Washington DC",
  "Houston",
  "Atlanta",
  "Miami - Ft. Lauderdale",
  "Seattle",
  "Denver",
  "Phoenix",
  "Austin",
  "Nashville",
  "Charlotte",
  "Tampa Bay",
  "Philadelphia - Central PA - DE - So. NJ",
  "San Francisco",
  "San Diego",
  "New Jersey - North and Central",
  "Long Island",
  "Westchester and CT",
  "Baltimore",
  "Minneapolis - St. Paul",
  "Portland Metro",
  "Las Vegas",
  "Salt Lake City",
  "Raleigh - Durham",
  "Orlando",
  "San Antonio",
];

const PROPERTY_TYPES = [
  "Office",
  "Industrial",
  "Retail",
  "Multi-Family",
  "Mixed-Use",
  "Hotel",
  "Land",
  "Other",
];

const DATE_RANGES = [
  { label: "Last 12 months", value: "12mo" },
  { label: "Last 3 years", value: "3yr" },
  { label: "Last 5 years", value: "5yr" },
  { label: "All Time", value: "all" },
];

const selectStyle: React.CSSProperties = {
  backgroundColor: "var(--color-surface)",
  color: "var(--color-text)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-sm)",
  padding: "2px 6px",
  fontSize: "12px",
};

export default function DeckFilterBar() {
  const { activeDeckId, decks, updateDeckFilters } = useDeckStore();
  const filters = decks[activeDeckId]?.filters;

  if (!filters) return null;

  const update = (partial: Partial<typeof filters>) =>
    updateDeckFilters(activeDeckId, partial);

  return (
    <div
      style={{
        height: "40px",
        backgroundColor: "var(--color-surface-elevated)",
        borderBottom: "1px solid var(--color-border)",
        display: "flex",
        alignItems: "center",
        padding: "0 16px",
        gap: "8px",
        flexShrink: 0,
        fontSize: "12px",
      }}
    >
      <span style={{ color: "var(--color-text-muted)", marginRight: "4px" }}>
        Deck Filters:
      </span>

      <select
        value={filters.market}
        onChange={(e) => update({ market: e.target.value })}
        style={selectStyle}
      >
        {MARKETS.map((m) => (
          <option key={m} value={m}>
            {m}
          </option>
        ))}
      </select>

      <select
        value={filters.propertyType}
        onChange={(e) => update({ propertyType: e.target.value })}
        style={selectStyle}
      >
        <option value="">All Property Types</option>
        {PROPERTY_TYPES.map((t) => (
          <option key={t} value={t}>
            {t}
          </option>
        ))}
      </select>

      <select
        value={filters.dateRange}
        onChange={(e) => update({ dateRange: e.target.value })}
        style={selectStyle}
      >
        {DATE_RANGES.map((r) => (
          <option key={r.value} value={r.value}>
            {r.label}
          </option>
        ))}
      </select>
    </div>
  );
}
