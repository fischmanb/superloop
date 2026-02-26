# General Learnings

Patterns that don't fit other categories.

---

## Code Style

<!-- Conventions, naming, organization -->

### 2026-02-25 (stakd campaign)
- **Pattern**: Next.js 15 App Router — `'use client'` is ONLY for components that use React hooks (useState, useEffect, useRouter), browser APIs, or event handlers. Pages that import `cookies()`, `headers()`, or export `metadata`/`generateMetadata` MUST remain server components. If a page needs both, split: server page renders a client leaf component.
- **Pattern**: Dynamic route `[slug]` receives `params` as a `Promise<{ slug: string }>` in Next.js 15 — must `await params` before using slug. Same for `generateMetadata`.
- **Pattern**: No dotAll regex `/s` flag in test files — use `[\s\S]` instead for ES2018 compatibility.
- **Pattern**: Server page + client form split — page is an `async` server component that reads cookies + redirects unauthenticated users, then renders the client form as a leaf; client form owns all state without any props from the page.
- **Pattern**: `generateMetadata` export in App Router page files enables per-page SEO without a separate layout; reads DB to build dynamic title and description.
- **Pattern**: `notFound()` from `next/navigation` returns a proper 404 in server components — call it immediately after null-checking the query result.

---

## Git Workflow

<!-- Branching, commits, PRs -->

_No learnings yet._

---

## Tooling

<!-- Build tools, linting, formatting -->

_No learnings yet._

---

## Debugging

<!-- Common issues, debugging techniques -->

_No learnings yet._

---

## Other

<!-- Miscellaneous patterns -->

### 2026-02-25 (stakd campaign)
- **Pattern**: New Drizzle table schemas must be added to the schema index via `export * from './tableName'` — the `db` instance uses `* schema` so any table not re-exported is invisible to `db.query.*` and `db.select().from(...)`.
- **Pattern**: Leaflet CSS injection — `if (!document.querySelector('link[href*="leaflet"]')) { append link }` inside `useEffect` injects the CSS exactly once per page, even if the component mounts multiple times.
- **Pattern**: Leaflet default icon fix in Webpack — delete `(L.Icon.Default.prototype as any)._getIconUrl` then call `L.Icon.Default.mergeOptions({ iconUrl, iconRetinaUrl, shadowUrl })` with CDN URLs; without this, markers render as broken images in Next.js.
- **Pattern**: Form submission handling: support both button clicks and Enter key with `onSubmit` and `onKeyDown`.
- **Pattern**: Loading states with skeleton UI using `animate-pulse` provides good UX during data fetching.
- **Pattern**: Error states should show user-friendly message with retry option.
- **Pattern**: Dynamic form arrays — `useState<Item[]>([emptyItem()])` initialized with a factory function; add via spread, remove via `filter`, update via `map` with index match.
- **Pattern**: Success state in forms — use a boolean `success` flag to swap the form for a confirmation view in the same component; include a CTA and a "Submit Another" reset button.
