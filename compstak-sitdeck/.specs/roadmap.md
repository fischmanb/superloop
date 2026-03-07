# SitDeck Product Roadmap

> A widget-based CRE intelligence dashboard built on CompStak lease, sales, and property data.

## Implementation Rules

- No mock APIs in Phase 1–2 — use DuckDB queries against real CSVs
- All filter enumerations sourced from canonical constants defined in each feature stub
- Submarket filters always load dynamically filtered by selected Market — never a static list
- Sales-side type filters (Sale Type, Buyer Type, Seller Type) are text search inputs, never dropdowns
- Properties CSV uses LATITUDE + LONGITUDE columns (not Geo Point like leases/sales)
- Widget-level filters override deck-level filters when set

## Progress

| Status | Count |
|--------|-------|
| ✅ Completed | 0 |
| 🔄 In Progress | 0 |
| ⬜ Pending | 44 |
| ⏸️ Blocked | 0 |

**Last updated**: 2026-03-07

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
| S | 1–3 files, single component |
| M | 3–7 files, multiple components |
| L | 7–15 files, full feature |

## Notes

- Phase 1: DuckDB queries against snowflake-full-leases and snowflake-full-sales CSVs
- Phase 2: AI widgets call OpenAI gpt-4.1-nano via tRPC routes
- Phase 3: External feed integrations — implement stubs with placeholder data first
