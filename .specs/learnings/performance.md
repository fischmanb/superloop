# Performance Learnings

Optimization patterns for this codebase.

---

## Lazy Loading

<!-- Code splitting, dynamic imports, route-based splitting -->

### 2026-02-25 (stakd campaign)
- **Pattern**: Browser-API-dependent libraries (Leaflet, chart libs) must use `dynamic(() => import(...), { ssr: false })` in Next.js App Router — they access `window`/`document` at import time, which crashes SSR.
- **⚠️ Critical**: The `dynamic(ssr: false)` call must live in a **dedicated client wrapper component** (with `"use client"`), NOT in the server page itself. Never add `"use client"` to a page that uses `cookies()`, `headers()`, or exports `metadata` — this breaks the server component. Create a separate wrapper that handles the dynamic import, and import that wrapper into the server page.
- **Pattern**: Dynamic import inside `useEffect` as alternative: `import('leaflet').then(L => { ... })` — safe, no extra wrapper component needed, and the entire bundle is code-split from the initial page load.
- **Pattern**: Store map/chart instances in `useRef` (not `useState`) to prevent re-initialization on re-renders without triggering a re-render itself; check ref before init and call cleanup in the `useEffect` return.

---

## Caching

<!-- Cache strategies, invalidation patterns -->

_No learnings yet._

---

## Rendering

<!-- React performance, memoization, virtualization -->

_No learnings yet._

---

## Data Fetching

<!-- Query optimization, pagination, prefetching -->

_No learnings yet._

---

## Bundle Size

<!-- Tree shaking, dependency analysis -->

_No learnings yet._
