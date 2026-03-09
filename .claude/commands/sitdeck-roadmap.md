---
description: Create or update the SitDeck product roadmap (~/compstak-sitdeck/.specs/roadmap.md)
---

Manage the SitDeck roadmap: $ARGUMENTS

## Paths

- Specs: ~/compstak-sitdeck/.specs/
- Vision: ~/compstak-sitdeck/.specs/vision.md
- Roadmap: ~/compstak-sitdeck/.specs/roadmap.md

## Mode Detection

| Condition | Mode |
|-----------|------|
| No roadmap.md or empty | **Create** — build from vision.md |
| `create` subcommand | **Create** — force fresh |
| `add "feature"` subcommand | **Add** — append to existing roadmap |
| `reprioritize` subcommand | **Reprioritize** — restructure phases |
| `status` subcommand | **Status** — read-only progress report |
| No subcommand, roadmap exists | **Interactive** — ask what to do |

## Instructions

### Create Mode

1. Read `~/compstak-sitdeck/.specs/vision.md` — app overview, widget catalog, tech stack, design principles
2. Verify the widget catalog section exists (Widget Catalog, 50+ Planned) — all 44 named widgets must appear
3. Do NOT decompose or invent features. The widget list is the canonical feature set. Transcribe it exactly.
4. Write `~/compstak-sitdeck/.specs/roadmap.md` using the format below
5. Show draft, wait for approval before saving

### Add Mode

1. Read existing roadmap to understand current phases, numbering, dependencies
2. Add new feature(s) to appropriate phase or as ad-hoc (#100+)
3. Show diff and confirm before applying

### Reprioritize Mode

1. Read roadmap, vision, learnings
2. Present analysis: done, in progress, pending, dependency bottlenecks
3. Ask about changes, then restructure
4. Show diff and confirm

### Status Mode (read-only)

Show progress table by phase, overall %, next feature, blocked items. No file changes.

## Roadmap Format

```markdown
# SitDeck Product Roadmap

> A widget-based CRE intelligence dashboard built on 10.5M rows of CompStak lease and sales data.

## Implementation Rules

- No mock APIs in Phase 1-2 — use DuckDB queries against real CSVs
- All filter enumerations sourced from canonical constants (see scaffold-stubs)
- Submarket filters always load dynamically from data, filtered by selected Market
- Sales-side type filters (Sale Type, Buyer Type, Seller Type) use text search — never dropdowns
- Widget-level filters override deck-level filters when set
- Properties CSV uses LATITUDE + LONGITUDE columns (not Geo Point like leases/sales)

## Progress

| Status | Count |
|--------|-------|
| ✅ Completed | 0 |
| 🔄 In Progress | 0 |
| ⬜ Pending | 44 |
| ⏸️ Blocked | 0 |

**Last updated**: [date]

---

## Phase 1 — Core Data Widgets

| # | Widget | Category | Data | Complexity | Deps | Status |
|---|--------|----------|------|------------|------|--------|
| 1 | CRE Property Map | Map | Leases + Sales | L | - | ⬜ |
| 2 | Market Map | Map | Leases | M | 1 | ⬜ |
| 3 | Portfolio Map | Map | Leases + Sales | M | 1 | ⬜ |
| 4 | Rent Optimizer | Rent & Pricing | Leases | L | - | ⬜ |
| 5 | Underlying Comps | Rent & Pricing | Leases | M | 4 | ⬜ |
| 6 | Adjustable Comps & Weights | Rent & Pricing | Leases | M | 4,5 | ⬜ |
| 7 | Vacant Space Pricer | Rent & Pricing | Leases | M | 4 | ⬜ |
| 8 | Rent Trends | Rent & Pricing | Leases | M | - | ⬜ |
| 9 | Market Overview | Market Intelligence | Leases + Sales | M | - | ⬜ |
| 10 | Construction Pipeline | Market Intelligence | Leases | M | 9 | ⬜ |
| 11 | Recent Transactions | Deal Intelligence | Leases + Sales | S | - | ⬜ |
| 12 | Deal Activity Heatmap | Deal Intelligence | Leases + Sales | M | 1 | ⬜ |
| 13 | Tenant Records | Tenant & Property | Leases | M | - | ⬜ |
| 14 | Active Tenants | Tenant & Property | Leases | S | 13 | ⬜ |
| 15 | Property Details | Tenant & Property | Properties CSV | M | - | ⬜ |
| 16 | Terminated Lease Monitor | Tenant & Property | Leases | M | 13 | ⬜ |
| 17 | Portfolio Overview | Portfolio & Underwriting | Leases + Sales | M | - | ⬜ |
| 18 | Lease Expiration Calendar | Portfolio & Underwriting | Leases | M | 17 | ⬜ |
| 19 | Rent Potential | Portfolio & Underwriting | Leases | M | 4,17 | ⬜ |
| 20 | Cap Rate Trends | Portfolio & Underwriting | Sales | M | - | ⬜ |
| 21 | Income Projection | Portfolio & Underwriting | Leases | M | 17 | ⬜ |
| 22 | League Tables | Broker & Network | Leases + Sales | M | - | ⬜ |
| 23 | Broker Rankings | Broker & Network | Leases + Sales | M | 22 | ⬜ |
| 24 | Broker Activity Feed | Broker & Network | Leases + Sales | S | 22 | ⬜ |
| 25 | Network Directory | Broker & Network | Leases | S | - | ⬜ |
| 26 | Data Feed Status | AI & Analytics | Internal | S | - | ⬜ |

## Phase 2 — AI, Portfolio & Advanced Analytics

| # | Widget | Category | Data | Complexity | Deps | Status |
|---|--------|----------|------|------------|------|--------|
| 27 | Breaking CRE News | Market Intelligence | External | M | - | ⬜ |
| 28 | AI Market Summary | Market Intelligence | Leases + AI | L | 9 | ⬜ |
| 29 | Deal Pipeline | Deal Intelligence | SQLite | M | 11 | ⬜ |
| 30 | News Alerts | Deal Intelligence | External | M | 27 | ⬜ |
| 31 | Template Outreach | Deal Intelligence | AI | M | 13 | ⬜ |
| 32 | Tenant Credit Indicators | Tenant & Property | Leases + AI | L | 13 | ⬜ |
| 33 | AI Agent (Chat) | AI & Analytics | All + AI | L | 9,11,13 | ⬜ |
| 34 | Custom Alerts | AI & Analytics | All | M | 33 | ⬜ |
| 35 | Market Briefing | AI & Analytics | Leases + AI | M | 9,28 | ⬜ |
| 36 | Situation Reports | AI & Analytics | All + AI | L | 33 | ⬜ |
| 37 | Client Data Overlay | Data Integration | Client | L | 1 | ⬜ |
| 38 | Document Upload | Data Integration | Client | L | - | ⬜ |
| 39 | API Explorer | Data Integration | API | M | - | ⬜ |

## Phase 3 — External Feeds

| # | Widget | Category | Data | Complexity | Deps | Status |
|---|--------|----------|------|------------|------|--------|
| 40 | Demographics | Market Intelligence | External | M | 9 | ⬜ |
| 41 | Interest Rate Monitor | Financial & Economic | External | S | - | ⬜ |
| 42 | REIT Index Tracker | Financial & Economic | External | S | - | ⬜ |
| 43 | CRE Capital Markets | Financial & Economic | External | M | - | ⬜ |
| 44 | Economic Indicators | Financial & Economic | External | S | - | ⬜ |

---

## Status Legend
| Symbol | Meaning |
|--------|---------|
| ✅ | Completed |
| 🔄 | In Progress |
| ⬜ | Pending |
| ⏸️ | Blocked |

## Complexity Legend
| Size | Scope |
|------|-------|
| S | 1-3 files, single component |
| M | 3-7 files, multiple components |
| L | 7-15 files, full feature |

## Notes

- Phase 1 widgets use DuckDB queries against snowflake-full-leases and snowflake-full-sales CSVs
- Phase 2 AI widgets call OpenAI gpt-4.1-nano via tRPC routes; same tool primitives exposed to AI Agent
- Phase 3 requires external feed integrations — implement stubs with placeholder data first
- Run /sitdeck-scaffold-stubs after creating this roadmap to generate all 44 feature stub files
```

## After Saving

Report:
```
✅ SitDeck roadmap saved to ~/compstak-sitdeck/.specs/roadmap.md

44 widgets across 3 phases:
- Phase 1: 26 core data widgets
- Phase 2: 13 AI/advanced widgets  
- Phase 3: 5 external feed widgets

Next step: Run /sitdeck-scaffold-stubs to generate feature stub files
Then: Run /build-next to start building
```
