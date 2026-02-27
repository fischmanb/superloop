# Build Roadmap: Stakd

> Ordered list of features to implement. Each feature should be completable within a single agent context window.
> Updated by `/roadmap`, `/clone-app`, `/roadmap-triage`, and `/build-next`.

## Implementation Rules

**Every feature in this roadmap must be implemented with real data, real API calls, and real database operations.** No exceptions.

- **No mock data** — never use hardcoded arrays, fake JSON, or placeholder content to simulate functionality. If a feature needs data, it reads from the database or calls a real API.
- **No fake API endpoints** — every endpoint must do real work. No routes that return static JSON.
- **No placeholder UI** — components must be wired to real data sources. If the data isn't available yet, show a proper empty state, not fake data.
- **No "demo mode"** — features either work end-to-end or they aren't done. A feature is only ✅ when a real user can use it with their real data.
- **Real validation** — forms validate against real constraints, not just "is this field filled in?"
- **Real error handling** — API failures, empty results, rate limits, and edge cases must be handled, not ignored.
- **Test against real flows** — when verifying a feature, use the app as a user would. Trigger real API calls, see real results.

---

## Progress

| Status | Count |
|--------|-------|
| ✅ Completed | 11 |
| 🔄 In Progress | 0 |
| ⬜ Pending | 17 |
| ⏸️ Blocked | 0 |

**Last updated**: 2026-02-27 (completed feature #5: Auth: Session & protected routes)

---

## Phase 1: Foundation

> Core infrastructure, auth, and layout. Must be built first.

| # | Feature | Source | Jira | Complexity | Deps | Status |
|---|---------|--------|------|------------|------|--------|
| 1 | Project setup (Next.js, Tailwind, DB, env) | clone-app | - | S | - | ✅ |
| 2 | Core layout (header, nav, footer) | clone-app | - | M | 1 | ✅ |
| 3 | Auth: Sign up | clone-app | - | M | 1 | ✅ |
| 4 | Auth: Log in | clone-app | - | M | 1 | ✅ |
| 5 | Auth: Session & protected routes | clone-app | - | M | 3,4 | ✅ |
| 6 | Deal model & database schema | clone-app | - | M | 1 | ✅ |
| 7 | Agent/User profile model & schema | clone-app | - | M | 1 | ✅ |

---

## Phase 2: Core Features

> Primary user-facing functionality.

| # | Feature | Source | Jira | Complexity | Deps | Status |
|---|---------|--------|------|------------|------|--------|
| 8 | Landing page (hero, search bar, market filters) | clone-app | - | M | 2 | ✅ |
| 9 | Deals list page (feed, filters, pagination) | clone-app | - | L | 6,8 | ⬜ |
| 10 | Deal detail page | clone-app | - | M | 6,9 | ⬜ |
| 11 | Deal card component (status, image, amount, participants) | clone-app | - | M | 6 | ⬜ |
| 12 | Market/submarket filters (state, city, neighborhood) | clone-app | - | M | 9 | ⬜ |
| 13 | Search (address, advanced filters) | clone-app | - | M | 9 | ⬜ |
| 14 | Submit deal form & flow | clone-app | - | L | 5,6,7 | ⬜ |
| 15 | Agent profile page | clone-app | - | M | 7,11 | ⬜ |
| 16 | Rankings page (top brokers, investors, lenders) | clone-app | - | L | 7,9 | ⬜ |
| 17 | Listings page (active for-sale/for-lease) | clone-app | - | M | 6,9 | ⬜ |
| 18 | Map view (deal locations, gated for logged-in) | clone-app | - | M | 5,9 | ⬜ |

---

## Phase 3: Enhancement

> Secondary features, polish, and integrations.

| # | Feature | Source | Jira | Complexity | Deps | Status |
|---|---------|--------|------|------------|------|--------|
| 19 | News section / industry news feed | clone-app | - | M | 2,6 | ⬜ |
| 20 | Awards categories (Whales, Lease Beasts, etc.) | clone-app | - | M | 16 | ⬜ |
| 21 | Trending deals (homepage) | clone-app | - | S | 9,11 | ⬜ |
| 22 | Top brokers sidebar (deals page) | clone-app | - | S | 16 | ⬜ |
| 23 | CompStak API integration (comps link on deal) | clone-app | - | M | 10 | ⬜ |
| 24 | Dark mode toggle | clone-app | - | S | 2 | ✅ |
| 25 | User settings & profile edit | clone-app | - | M | 5,7 | ⬜ |
| 26 | Social links (footer, share) | clone-app | - | S | 2 | ✅ |
| 27 | Email newsletter signup (footer) | clone-app | - | S | 2 | ✅ |
| 28 | Data / analytics page (CompStak insights) | clone-app | - | L | 23 | ⬜ |

---

## Ad-hoc Requests

> Features added from Slack/Jira that don't fit a phase. Processed after current phase.

| # | Feature | Source | Jira | Complexity | Deps | Status |
|---|---------|--------|------|------------|------|--------|
| 100 | _Reserved for ad-hoc_ | - | - | - | - | - |

---

## Status Legend

| Symbol | Meaning |
|--------|---------|
| ⬜ | Pending - not started |
| 🔄 | In Progress - currently being built |
| ✅ | Completed - PR merged |
| ⏸️ | Blocked - waiting on dependency or decision |
| ❌ | Cancelled - no longer needed |

## Complexity Legend

| Symbol | Meaning | Typical Scope |
|--------|---------|---------------|
| S | Small | Single component, few files |
| M | Medium | Multiple components, moderate logic |
| L | Large | Full feature, many files, complex logic |

---

## Notes

- **CompStak API**: Phase 3 feature #23 assumes CompStak API access. If unavailable, show "View comps on CompStak" link instead.
- **Deal submission**: Can start with manual admin approval; automate later.
- **Map**: Mapbox or similar; requires API key.

---

_This file is the single source of truth for `/build-next`. Features are picked in order, respecting dependencies._
