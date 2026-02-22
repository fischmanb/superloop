# Build Roadmap

> Ordered list of features to implement. Each feature should be completable within a single agent context window.
> Updated by `/roadmap`, `/clone-app`, `/roadmap-triage`, and `/build-next`.

## Implementation Rules

This is a **front-end prototype phase** — features use static mock data passed via props. Real API/database integration comes later.

- Components receive data through props — no hardcoded data inside components
- Mock data is co-located in `__mocks__/` directories next to the components that use it
- Tests use React Testing Library and Vitest
- All components are TypeScript with proper type definitions

---

## Progress

| Status | Count |
|--------|-------|
| ✅ Completed | 1 |
| 🔄 In Progress | 0 |
| ⬜ Pending | 3 |
| ⏸️ Blocked | 0 |

**Last updated**: 2026-02-22

---

## Phase 1: Foundation

> Week view — the core screen of the app.

| # | Feature | Source | Jira | Complexity | Deps | Status |
|---|---------|--------|------|------------|------|--------|
| 1 | Calendar: Week View | vision | - | M | - | ✅ |

---

## Phase 2: Core Features

> Interaction features that build on the week view.

| # | Feature | Source | Jira | Complexity | Deps | Status |
|---|---------|--------|------|------------|------|--------|
| 2 | Coach Client Switcher | vision | - | S | 1 | ⬜ |
| 3 | Block: Add and Edit | vision | - | M | 1 | ⬜ |
| 4 | Block: Detail View | vision | - | S | 1 | ⬜ |

---

## Phase 3: Enhancement

> Polish and secondary features.

| # | Feature | Source | Jira | Complexity | Deps | Status |
|---|---------|--------|------|------------|------|--------|

---

## Ad-hoc Requests

| # | Feature | Source | Jira | Complexity | Deps | Status |
|---|---------|--------|------|------------|------|--------|

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

_This file is the single source of truth for `/build-next`. Features are picked in order, respecting dependencies._
