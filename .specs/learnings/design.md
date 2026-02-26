# Design System Learnings

Patterns for UI and design system in this codebase.

---

## Token Usage

<!-- When to use which tokens, overrides -->

_No learnings yet._

---

## Component Patterns

<!-- Common component structures, composition -->

### 2026-02-25 (stakd campaign)
- **Pattern**: Auth gate teaser UX — show a blurred/decorative placeholder with a lock icon + login CTA; more engaging than a hard redirect; let guests see the concept before signing up.
- **Pattern**: Tab navigation synced to URL — `useSearchParams().get('tab')` drives active tab; clicking fires `router.push('?tab=X')` — SSR-safe, shareable URLs, no `useState` needed for tab selection.
- **Pattern**: Leaderboard/rank display — top 3 use medal emojis (🥇🥈🥉) for visual hierarchy; positions 4+ use `#N` in muted gray.
- **Pattern**: Volume formatting for display: check thresholds `>= 1_000_000_000` (B), `>= 1_000_000` (M), `>= 1_000` (K); `.replace(/\.0$/, '')` strips trailing zero.
- **Pattern**: Initials avatar fallback — `name.split(' ').map(p => p[0]).join('').toUpperCase().slice(0, 2)` gives a two-letter abbreviation; rendered as a `rounded-full` div with brand color, no image dependency.
- **Pattern**: Conditional contact row — renders only if at least one of phone/website/linkedinUrl is truthy; avoids empty icon rows.
- **Pattern**: Component reuse via optional props — adding a default-valued `basePath` prop enables reuse across pages without changing existing call sites.
- **Pattern**: Collapsible advanced filter panels — use `useState(() => hasAdvancedParams(searchParams))` initializer to auto-expand when relevant URL params are present on load.

---

## Responsive Design

<!-- Breakpoints, mobile-first patterns -->

### 2026-02-25 (stakd campaign)
- **Pattern**: Tailwind mobile-first — base styles are mobile, then add breakpoint prefixes for larger screens. Hero headlines: `text-4xl sm:text-5xl lg:text-6xl`.
- **Pattern**: Grid layouts with responsive columns: `grid-cols-1 md:grid-cols-2 lg:grid-cols-3` for card grids. Filter grids: `grid-cols-2 sm:grid-cols-3 lg:grid-cols-N` where N = number of filter dropdowns.
- **Pattern**: Stack → side-by-side: `flex flex-col sm:flex-row` for form layouts, `flex flex-col lg:flex-row gap-8` for detail page two-column layouts. Sidebar: `lg:w-80 shrink-0`.
- **Pattern**: Profile header layout — `flex flex-col sm:flex-row items-start gap-6` stacks avatar above info on mobile, aligns side-by-side on sm+.
- **Pattern**: Dual-price display — use a boolean to drive which price to render; guard for null before rendering either.

---

## Accessibility

<!-- ARIA, keyboard nav, screen readers -->

_No learnings yet._

---

## Animation

<!-- Motion patterns, transitions -->

_No learnings yet._
