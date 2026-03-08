---
feature: Project Setup
domain: infrastructure
source: app/layout.tsx
tests:
  - scripts/generate-mapping.sh
components:
  - AppShell
  - DeckFilterBar
status: implemented
created: 2026-03-07
updated: 2026-03-07
---

# F-000: Project Setup

**Category**: Infrastructure
**Phase**: 1
**Data Source**: Internal
**Status**: Implemented

## Feature: Project Setup

### Scenario: Next.js app initializes without errors
Given the project is cloned
When `npm run dev` is executed
Then the app starts on port 3000
And the root route renders the dashboard shell
And no TypeScript or build errors occur

### Scenario: DuckDB connects to CSV data sources
Given the CSV files exist at `~/compstak-sitdeck/_shared-csv-data/`
When the DuckDB connection module is imported
Then a connection is established to the persistent `.duckdb` file
And the leases, sales, and properties tables are queryable

### Scenario: SQLite initializes for user/app data
Given the app starts for the first time
When SQLite is initialized
Then the `sitdeck.db` file is created at `data/sitdeck.db`
And the schema migrations run successfully

### Scenario: tRPC router is reachable
Given the app is running
When a request hits `GET /api/trpc`
Then the tRPC handler responds
And type-safe routes are accessible from the client

### Scenario: Tailwind design tokens are available
Given the app loads
When any component uses a design token class
Then the class resolves to the correct CSS value defined in the token system

## UI Mockup

```
┌─────────────────────────────────────────────────────────────────┐
│  COMPSTAK SITDECK                     [User] [Settings]  [+]    │
├─────────────────────────────────────────────────────────────────┤
│  Deck: Command Center ▾   Market: New York City ▾  [Filters]   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │                                                         │   │
│   │         Widget grid area (react-grid-layout)            │   │
│   │                                                         │   │
│   │   Drag and drop widgets here                            │   │
│   │                                                         │   │
│   └─────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Acceptance Criteria

- [ ] `npm run dev` starts without errors
- [ ] `npm run build` completes without TypeScript errors
- [ ] DuckDB module connects to CSV files and runs a test query returning > 0 rows
- [ ] SQLite `sitdeck.db` initializes with schema on first run
- [ ] tRPC handler responds at `/api/trpc`
- [ ] Tailwind CSS 4 loads with dark theme by default
- [ ] App shell renders: top nav bar, deck filter bar, widget grid area
- [ ] Zustand store initializes for widget layout state
- [ ] `scripts/generate-mapping.sh` runs from project root

## Component References

- AppShell: Top-level layout with nav bar + deck filter bar + grid area
- DeckFilterBar: Market, Submarket, Property Type, Date Range, Asset Class filters

## Implementation Notes

- DuckDB persistent file: `data/sitdeck.duckdb` — created on first connection
- CSV paths: resolved from `SITDECK_DATA_DIR` env var. Falls back to `$HOME/compstak-sitdeck/_shared-csv-data` if not set. Throws at startup if neither is available.
- Add `SITDECK_DATA_DIR=/absolute/path/to/_shared-csv-data` to `.env.local` for non-default setups.
- SQLite path: `data/sitdeck.db` — initialized with schema on startup
- tRPC router mounted at `app/api/trpc/[trpc]/route.ts`
- Tailwind CSS 4 uses `@theme` directive for design tokens
- react-grid-layout breakpoints: lg=1200, md=996, sm=768
