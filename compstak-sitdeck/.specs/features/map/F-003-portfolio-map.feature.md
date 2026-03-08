---
feature: Portfolio Map
domain: map
source: components/widgets/portfolio-map/PortfolioMapWidget.tsx
tests:
  - tests/db/portfolio-map.test.ts
components:
  - PortfolioMapWidget
  - PortfolioMapLeaflet
status: implemented
created: 2026-03-08
updated: 2026-03-08
---

# Portfolio Map

**Source File**: components/widgets/portfolio-map/PortfolioMapWidget.tsx
**Design System**: .specs/design-system/tokens.md

## Feature: Portfolio Map

Dual-layer CRE map showing both lease comps (blue) and sale transactions (orange) for a
selected market. Users toggle which data layers are visible (Leases / Sales / Both) and
filter by property type. A submarket stats sidebar ranks submarkets by total activity
(lease + sale deal count) with per-submarket avg rent and avg sale price. Clicking a
submarket in the sidebar flies the map to that submarket's centroid and highlights it.

### Scenario: Default view loads with both layers visible
Given the Portfolio Map widget is rendered on the dashboard
When the component mounts
Then it fetches lease points and sale points for the default market (New York City)
And displays blue CircleMarkers for lease comps
And displays orange CircleMarkers for sale transactions
And renders the submarket stats sidebar ranked by total deal count

### Scenario: User toggles the Leases layer off
Given the Portfolio Map widget is showing both layers
When the user clicks the "Leases" toggle button to deactivate it
Then lease comp markers disappear from the map
And only sale transaction markers remain visible
And the stats sidebar still shows combined counts

### Scenario: User toggles the Sales layer off
Given the Portfolio Map widget is showing both layers
When the user clicks the "Sales" toggle button to deactivate it
Then sale transaction markers disappear from the map
And only lease comp markers remain visible

### Scenario: User changes market filter
Given the Portfolio Map widget is displaying data
When the user selects a different market from the dropdown
Then both lease and sale queries refetch with the new market
And the map updates markers for the new market
And the submarket stats sidebar refreshes

### Scenario: User filters by property type
Given the Portfolio Map widget is displaying data
When the user toggles a property type filter (Office, Industrial, Retail, Flex/R&D)
Then only lease comps matching the selected type are shown
And sale points are unaffected (sales have no space type)
And submarket stats update to reflect the filter

### Scenario: User clicks a submarket row
Given the submarket stats panel is visible
When the user clicks on a submarket row
Then the selected submarket is highlighted in the table
And non-matching lease/sale points fade to low opacity
And the map flies to the submarket centroid
And clicking again deselects and restores full opacity

### Scenario: No data for selected filters
Given the Portfolio Map widget has loaded
When the selected market has no comps
Then the map renders with no markers (default center, zoom-out view)
And the stats panel shows "No data for the selected filters"

### Scenario: DuckDB query error
Given the Portfolio Map widget has loaded
When a server-side DuckDB query fails
Then the widget renders an error state with the message
And a retry button is shown

## UI Mockup

```
┌────────────────────────────────────────────────────────────────────────────────┐
│ PORTFOLIO MAP  [Market ▼]  [Leases ●] [Sales ●]  [Office] [Industrial] [Retail]│
│                                                  850 leases · 142 sales         │
├─────────────────────────────────────────┬──────────────────────────────────────┤
│                                         │ SUBMARKET ACTIVITY                   │
│                                         │                                      │
│           [LEAFLET MAP]                 │  Submarket      Leases Sales Avg $   │
│                                         │  Midtown          823    52   $72    │
│  ● lease comp points (blue)             │  Downtown         601    38   $65    │
│  ● sale transaction points (orange)     │  Midtown South    487    29   $68    │
│                                         │  Chelsea          354    21   $61    │
│  Legend:                                │  FiDi             312    18   $58    │
│  ● Leases  ● Sales                      │  ...                                 │
│                                         │                                      │
└─────────────────────────────────────────┴──────────────────────────────────────┘
```

## Component References

- PortfolioMapWidget: Filter bar + map + submarket stats sidebar
- PortfolioMapLeaflet: Leaflet map with lease (blue) and sale (orange) CircleMarkers

## Data Notes

- Lease points: Geo Point column parsed as "lat lon" (space-separated); filter by Market + Space Type
- Sale points: Geo Point column parsed same way; filter by Market only (no space type in sales)
- Submarket stats: combined from leases + sales via UNION query, GROUP BY Submarket
- Stats sorted by (lease_count + sale_count) DESC, LIMIT 25; HAVING (lease_count + sale_count) >= 2
- "Avg $" column shows avgStartingRent if > 0, otherwise avgSalePrice (formatted as $NM/$NK)
- Lease points limited to 1500 most recent; sale points limited to 500
- Property type filter applies to lease layer only
- centerLat/centerLng from AVG of Geo Point coords per submarket for map flyTo
- Sales CSV columns: "Total Sale Price" (not "Sale Price"), "Sale Date" (not "Close Date"), "Transaction SQFT"

## Learnings

- Sales CSV has no "Space Type" column — property type filter only applies to leases
- Portfolio map differentiates layers via color: blue (#3b82f6) for leases, orange (#f97316) for sales
- UNION-based submarket stats query combines both CSVs in a single DuckDB call
