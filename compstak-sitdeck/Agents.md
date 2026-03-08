# Agents.md

Round log of agent sessions for this project.

---

## Round 2 — Feature #1: CRE Property Map

**Date**: 2026-03-07
**Branch**: auto/chained-20260307-165927

### What was asked
Build Feature #1 (CRE Property Map) from roadmap.md — interactive Mapbox GL map widget showing lease and sales comp markers from DuckDB, with layer toggles and deck-level filter integration.

### What was changed

**New files created:**
- `.specs/features/map/F-001-cre-property-map.feature.md` — feature spec with Gherkin scenarios, UI mockup, acceptance criteria
- `lib/trpc/routers/map.ts` — tRPC router for `map.getMarkers` procedure; queries leases, sales, and properties views in DuckDB; supports market, propertyType, buildingClass, dateFrom, dateTo, bbox, and layers filters; uses TRY_CAST for safe Geo Point parsing
- `app/providers.tsx` — TRPCProvider + QueryClientProvider wrapper for React client components
- `components/widgets/CREPropertyMap.tsx` — client-only Mapbox GL map widget; uses dynamic import of mapbox-gl; initializes map in useEffect; adds GeoJSON circle layers per data type; responds to deck store filters with widget-level overrides; shows layer toggles, record counts, empty state, and missing-token message

**Modified files:**
- `lib/trpc/router.ts` — added `map: mapRouter` to appRouter
- `app/layout.tsx` — wrapped children with `<Providers>` for tRPC React hooks
- `components/WidgetGrid.tsx` — reads widget list from Zustand store; dispatches to WidgetRenderer by widgetType; uses `dynamic(..., { ssr: false })` for CREPropertyMap
- `components/DeckFilterBar.tsx` — connected to Zustand deck store (was local state); writes market/propertyType/dateRange back to store so CREPropertyMap responds reactively
- `lib/store/deck.ts` — DEFAULT_DECK now includes cre-property-map-1 widget in widget list
- `.specs/roadmap.md` — marked #1 as ✅ completed, updated counts (2 ✅, 0 🔄, 43 ⬜)
- `.specs/mapping.md` — regenerated with F-001 entry

### What was NOT changed
- vision.md, other spec stub files
- lib/db/duckdb.ts, lib/db/sqlite.ts — unchanged
- pages/_document.tsx, pages/_error.tsx — unchanged
- CSV data files (external to repo)

### Verification results
- `NODE_ENV=production npm run build` — passes, 4 routes clean
- `./scripts/generate-mapping.sh` — passes, 2 features registered
- TypeScript: 0 errors (build confirms)

### Notes
- `keepPreviousData` was removed in @tanstack/react-query v5; replaced with `placeholderData: keepPreviousData` from the package
- Mapbox GL initialized with dynamic `import("mapbox-gl")` inside useEffect — avoids SSR/build issues with browser-only APIs
- `TRY_CAST` essential for DuckDB Geo Point parsing — some rows in real CSVs have malformed coordinates
- DeckFilterBar was previously using local useState (not persisted); now uses Zustand store so deck filters propagate to map widget
- `NEXT_PUBLIC_MAPBOX_TOKEN` must be set in `.env.local` for map to render; widget shows helpful setup message if missing

---

## Round 1 — Feature #0: Project Setup

**Date**: 2026-03-07
**Branch**: auto/chained-20260307-155445

### What was asked
Build Feature #0 (Project Setup) from roadmap.md — scaffold the Next.js 15 app with all dependencies, database connections, tRPC, and basic app shell.

### What was changed

**New files created:**
- `package.json` — dependencies: Next.js 15, React 19, DuckDB, better-sqlite3, tRPC v11, Zustand, react-grid-layout, Mapbox GL, Recharts, next-auth v5, Zod, Tailwind CSS 4
- `tsconfig.json` — TypeScript config for Next.js App Router
- `next.config.ts` — serverExternalPackages for native modules (better-sqlite3, duckdb)
- `postcss.config.mjs` — Tailwind CSS 4 PostCSS config
- `app/globals.css` — Tailwind CSS 4 design token system (colors, spacing, typography)
- `app/layout.tsx` — root layout with dark theme
- `app/page.tsx` — redirects root to /dashboard
- `app/not-found.tsx` — 404 page with force-dynamic (required for build env)
- `app/dashboard/page.tsx` — dashboard shell with NavBar + DeckFilterBar + WidgetGrid
- `app/api/trpc/[trpc]/route.ts` — tRPC HTTP handler
- `components/NavBar.tsx` — top navigation bar
- `components/DeckFilterBar.tsx` — deck-level filters (market, property type, date range)
- `components/WidgetGrid.tsx` — widget grid placeholder
- `lib/db/duckdb.ts` — DuckDB connection module with CSV view registration
- `lib/db/sqlite.ts` — SQLite connection with schema migrations
- `lib/trpc/server.ts` — tRPC server init with context
- `lib/trpc/router.ts` — root tRPC router (health endpoint)
- `lib/trpc/client.ts` — tRPC React client
- `lib/store/deck.ts` — Zustand store for deck state and widget layout
- `scripts/generate-mapping.sh` — copied from parent repo
- `lib/validation.sh` — copied from parent repo (generate-mapping dependency)
- `.gitignore` — node_modules, .next, data/*.db, .env
- `data/.gitkeep` — placeholder for data directory
- `pages/_document.tsx` — pages router document (required for error page rendering)
- `pages/_error.tsx` — custom error page
- `.specs/features/infrastructure/F-000-project-setup.feature.md` — feature spec

**Modified files:**
- `.specs/roadmap.md` — marked #0 as ✅ completed, updated counts
- `.specs/mapping.md` — regenerated with F-000 entry

### What was NOT changed
- `vision.md`, other spec files
- Any widget feature files (all still ⬜ pending)
- CSV data files (external to repo)

### Verification results
- `npx tsc --noEmit` — passes (0 errors)
- `NODE_ENV=production npm run build` — passes, 4 routes: /, /_not-found (dynamic), /api/trpc/[trpc] (dynamic), /dashboard (static)
- `./scripts/generate-mapping.sh` — passes, 1 feature registered

### Notes
- Build requires `NODE_ENV=production` — the Claude Code environment sets NODE_ENV=development by default, which causes a Next.js 15.5.12 prerender worker module loading issue. Fixed by adding `NODE_ENV=production` to the build script.
- `python-setuptools` brew package was installed to fix `distutils` issue with Node 24 + node-gyp for native module compilation.
- `@duckdb/node-api` package doesn't have stable semver versions (only `1.4.4-r.3` style); using `duckdb` package instead.
- next-auth upgraded to v5 beta to avoid Pages Router conflicts with Next.js 15 App Router.
