---
feature: CRE Property Map
domain: map
source: components/widgets/CREPropertyMap.tsx
tests: []
components:
  - CREPropertyMap
status: implemented
created: 2026-03-07
updated: 2026-03-07
---

# F-001: CRE Property Map

**Category**: Map
**Phase**: 1
**Data Source**: Leases + Sales
**Status**: Implemented

## Description

An interactive Mapbox GL map displaying CRE lease and sales comp markers across US markets. Users toggle data layers (lease comps, sales comps, property records), filter by market/property type/building class, and see a live count of visible records. The widget responds to deck-level filters and supports widget-level overrides for independent exploration.

## Feature: CRE Property Map

### Scenario: Default load shows lease and sales comps for active deck market
Given the user is on the Command Center deck
And the deck market filter is set to "New York City"
When the CRE Property Map widget loads
Then the map centers on New York City coordinates
And lease comp markers (green) are visible for the NYC market
And sales comp markers (blue) are visible for the NYC market
And properties layer is toggled off by default
And a record count shows "N leases, N sales" in the status bar

### Scenario: Widget-level market filter overrides deck-level filter
Given the deck market filter is "New York City"
When the user selects "Chicago Metro" in the widget's market filter
Then the map re-queries with market = "Chicago Metro"
And markers update to show Chicago comps
And the deck market filter remains unchanged at "New York City"

### Scenario: Layer toggles show and hide data
Given the map is loaded with NYC data
When the user clicks "Sales" toggle to turn it off
Then sales markers disappear from the map immediately
When the user clicks "Properties" toggle to turn it on
Then property markers (orange) appear on the map
And a new DuckDB query is triggered for property records

### Scenario: Map pan triggers viewport-bounded query
Given the map is showing NYC lease comps
When the user pans to a different area within the same market
Then a new query fires with the updated bounding box
And markers update to reflect the new viewport
And the loading indicator is shown during the query

### Scenario: Empty state when no data matches filters
Given the user has selected "Industrial" property type
And has set Building Class to "C"
When the query returns no records for the active viewport
Then an empty state overlay shows "No records match current filters"

### Scenario: Missing Mapbox token shows setup instructions
Given NEXT_PUBLIC_MAPBOX_TOKEN is not set
When the CRE Property Map widget renders
Then a clear message is displayed: "Mapbox token required — set NEXT_PUBLIC_MAPBOX_TOKEN in .env.local"

## UI Mockup

```
┌────────────────────────────────────────────────────────────────┐
│ [● Leases] [● Sales] [○ Properties]  Market: [NYC ▼]  Class: [▼]│
├────────────────────────────────────────────────────────────────┤
│                                                                  │
│   ╔══════════════════════════════════════════════════════════╗  │
│   ║                                                          ║  │
│   ║   [dark Mapbox map with colored circle markers]          ║  │
│   ║                                                          ║  │
│   ║   ● ● ●  ●  ●●●   ●                                    ║  │
│   ║     ●●   ● ●  ●●  ●●●  (green = leases)                ║  │
│   ║       ■  ■  ■  ■   ■   (blue = sales)                   ║  │
│   ║          ▲  ▲         (orange = properties, if on)       ║  │
│   ║                                                          ║  │
│   ╚══════════════════════════════════════════════════════════╝  │
│                                                                  │
│ 342 leases · 87 sales  ·  [Loading...] or [Last updated 2s ago] │
└────────────────────────────────────────────────────────────────┘
```

## Acceptance Criteria

- [x] Widget renders in a deck grid cell at minimum 4×4 grid units
- [x] Lease layer: green circle markers from leases view, filtered by Market, Property Type, Building Class, Date Range
- [x] Sales layer: blue circle markers from sales view, same filter set
- [x] Properties layer: orange circle markers from properties view (off by default)
- [x] Submarket dropdown not applicable to this widget (uses market-level granularity)
- [x] Widget-level market/property-type/building-class filters override deck-level filters when set
- [x] Loading state shown while DuckDB query executes
- [x] Empty state shown when no data matches filters
- [x] Layer toggles immediately show/hide markers without re-querying
- [x] Map pans trigger re-query with bounding box for viewport-bounded loading
- [x] Record count shows per-layer totals in status bar
- [x] Map uses Mapbox dark-v11 style, consistent with app dark theme
- [x] Missing Mapbox token shows a helpful setup message (no crash)
- [x] Geo Point parsing: split "lat,lon" string on comma; skip rows where parse fails

## Mock Data Spec

```typescript
const MOCK_MARKETS = [
  "New York City", "Chicago Metro", "Los Angeles - Orange - Inland",
  "Dallas - Ft. Worth", "Boston", "Bay Area", "Washington DC",
  "Houston", "Atlanta", "Miami - Ft. Lauderdale", "Seattle", "Denver",
  "Phoenix", "Austin", "Nashville", "Charlotte", "Tampa Bay",
  "Philadelphia - Central PA - DE - So. NJ", "San Francisco", "San Diego",
  "New Jersey - North and Central", "Long Island", "Westchester and CT",
  "Baltimore", "Minneapolis - St. Paul", "Portland Metro", "Las Vegas",
  "Salt Lake City", "Raleigh - Durham", "Orlando", "San Antonio"
];
const MOCK_BUILDING_CLASSES = ["A", "B", "C"];
const MOCK_PROPERTY_TYPES = ["Hotel", "Industrial", "Land", "Mixed-Use", "Multi-Family", "Office", "Other", "Retail"];

// Sample lease records (exact CSV column names)
const MOCK_LEASES = [
  {
    "Id": "L-100001",
    "Street Address": "350 Fifth Avenue",
    "Market": "New York City",
    "Property Type": "Office",
    "Building Class": "A",
    "Starting Rent": 75.50,
    "Transaction SQFT": 12500,
    "Tenant Name": "Acme Corp",
    "Execution Date": "2025-06-15",
    "Geo Point": "40.7484,-73.9967"
  },
  {
    "Id": "L-100002",
    "Street Address": "1 Chicago Plaza",
    "Market": "Chicago Metro",
    "Property Type": "Office",
    "Building Class": "B",
    "Starting Rent": 42.00,
    "Transaction SQFT": 8200,
    "Tenant Name": "Beta LLC",
    "Execution Date": "2025-03-20",
    "Geo Point": "41.8858,-87.6181"
  }
];

// Sample sales records
const MOCK_SALES = [
  {
    "ID": "S-200001",
    "Street Address": "1251 Avenue of the Americas",
    "Market": "New York City",
    "Property Type": "Office",
    "Building Class": "A",
    "Total Sale Price": 850000000,
    "Sale Price (PSF)": 1100.00,
    "Cap Rate": 4.2,
    "Sale Date": "2025-08-01",
    "Geo Point": "40.7590,-73.9845"
  }
];
```

## API Readiness Notes

- MOCK_MARKETS replaces with `GET /api/enums/markets` when live
- DuckDB column names match CSV headers verbatim — no mapping at integration
- `"Geo Point"` in leases/sales is a `"lat,lon"` single string — split on `,` at query time
- Properties CSV uses `LATITUDE` and `LONGITUDE` as separate numeric columns (different from leases/sales)
- Bbox filter uses DuckDB `split_part` and `TRY_CAST` for safe coordinate extraction
- Date range "12mo"/"3yr"/"5yr"/"all" converted to ISO date strings server-side before query

## Learnings

- Mapbox GL JS must be initialized in `useEffect` (never on first render) due to SSR/browser API requirements
- Use GeoJSON source + circle paint layer instead of individual `Marker` instances for >100 points (performance)
- `TRY_CAST` in DuckDB is essential for Geo Point parsing — some rows have malformed coordinates
- `initDuckDBViews()` must be called before any DuckDB query; it's idempotent (safe to call every request)
