# CompStak SitDeck — The Bloomberg Terminal for Commercial Real Estate

> A real-time CRE intelligence dashboard that transforms CompStak's 10+ years of lease comp data, tenant records, and market intelligence into a drag-and-drop, widget-based workspace — powered by AI analysis and live data feeds.

---

## Overview

CompStak SitDeck adapts the [SitDeck OSINT dashboard](https://sitdeck.com/product) model to commercial real estate: instead of 187 government intelligence feeds, SitDeck surfaces CompStak's proprietary lease comps, rent predictions, tenant records, market analytics, and CRE news through a modular, customizable dashboard. Users drag and drop widgets from 10+ categories, toggle map layers (office, retail, industrial, multifamily), run AI-powered analysis, and save unlimited dashboard layouts ("Decks").

The platform serves both sides of CompStak's business model:

- **Exchange users** (free) — brokers, researchers, appraisers who submit data in exchange for deal intelligence, league tables, and platform access
- **Enterprise users** (paid) — owners, investors, lenders, underwriters, acquisitions teams, and asset managers who pay for premium data, AI-powered insights, and predictive analytics

**Target users**: CRE brokers (Exchange), underwriters & acquisitions teams (Enterprise), asset managers (Enterprise), market researchers (both)

**Core value proposition**: Every comp, every tenant, every market signal — one screen. Maintained data sources. Drag-and-drop widgets. AI-powered rent predictions. Always live, always working.

---

## Key Screens / Areas

| Screen | Purpose | Priority |
|--------|---------|----------|
| Dashboard (Widget Grid) | Customizable workspace with drag-and-drop CRE widgets | Core |
| Interactive CRE Map | Property visualization with togglable layers (comps, tenants, rent heatmaps, vacancies) | Core |
| Widget Library | Browse and add widgets from 10+ CRE categories | Core |
| Deck Filter Bar | Shared market/property type/date filters that apply to all widgets on a deck | Core |
| Deck Selector | Switch between saved dashboard layouts (templates + custom) | Core |
| AI Agent (Chat) | Tool-using AI agent that answers CRE questions by calling the same primitives that power widgets and the API | Core |
| Rent Optimizer | Estimated starting rent with underlying comps, adjustable weights, vacant space pricing | Core |
| Deal Manager | Pipeline management for Exchange brokers (leads, outreach, contacts) | Core |
| Market Summaries | AI-generated market reports by geography and asset class | Core |
| Collections Panel | Browse, manage, and visualize saved cross-dataset query results | Core |
| All Records View | Unified view of comps, rent roll partials, and tenant records | Secondary |
| Portfolio Manager | Aggregate portfolio-level views with rent insights and alerts | Secondary |
| Data Integration | Connect client data with CompStak data (warehouse or upload) | Secondary |
| Settings & Profile | Account management, notification preferences, API keys | Secondary |

---

## Ready-Made Decks (Pre-configured Dashboard Templates)

Deploy in one click with curated widgets for specific workflows:

| Deck | Target User | Widgets | Status |
|------|-------------|---------|--------|
| **Command Center** | Everyone | CRE Map, Breaking News, Market Overview, AI Chat, Recent Transactions, Data Feed Status | 5/6 working (AI Chat stub) |
| **Deal Flow** | Brokers (Exchange) | Deal Pipeline, Deal Intelligence, League Tables, News Alerts, Contact Manager, Broker Rankings | 0/6 (all stubs — Phase 3) |
| **Underwriting** | Acquisitions Teams | Rent Optimizer, Property Details, AI Market Summary, Rent Trends, Market Overview | 3/5 working (Rent Optimizer, AI Market Summary stubs — Phase 4) |
| **Portfolio Manager** | Asset Managers | Portfolio Overview, Lease Expiration Calendar, Rent Trends, Economic Indicators, Market Overview | 3/5 working (Portfolio Overview, Lease Expiration Calendar stubs — Phase 6) |
| **Market Research** | Analysts | Market Overview, Rent Trends, Economic Indicators, Recent Transactions, Breaking News | 5/5 working |
| **Retail Intelligence** | Retail Specialists | CRE Map, Market Overview, Rent Trends, Recent Transactions, Economic Indicators | 5/5 working |

> **Note**: Unimplemented widgets render as "Coming Soon" placeholders. Decks become fully functional as their widgets are built in later phases.

---

## Deck-Level Filters (Cross-Widget Filtering)

Every deck has an optional **filter bar** that applies shared context to all widgets on that deck. When a user selects a market, property type, or date range at the deck level, every widget on that deck responds — no need to set the same filter in each widget individually.

### How It Works

1. **Filter bar** sits at the top of the deck, below the nav bar
2. **Shared filters** propagate to all widgets that support them
3. **Widget-specific filters** still exist for widget-local refinements (e.g., a specific address in Property Details)
4. **Filters persist per deck** — switching decks restores that deck's filters
5. **Ready-made deck templates** ship with sensible filter presets (e.g., Command Center defaults to user's home market)

### Available Deck-Level Filters

| Filter | Type | Applies To |
|--------|------|------------|
| **Market** | Single-select dropdown | All widgets with market-scoped data |
| **Submarket** | Multi-select (filtered by market) | Widgets with submarket granularity |
| **Property Type** | Multi-select (Office, Retail, Industrial, Multifamily) | All comp/property widgets |
| **Date Range** | Preset ranges + custom (Last 12mo, Last 3yr, etc.) | Transaction-based widgets |
| **Asset Class** | Single-select (Class A, B, C) | Comp and property widgets |

### Filter Hierarchy

```
Deck-Level Filters (shared across all widgets)
 └── Widget-Level Filters (local overrides / additions)
      └── e.g., Property Details still has its own address search
      └── e.g., CRE Map still has its own layer toggles
```

Widgets that don't support a given filter simply ignore it (e.g., Breaking News ignores Property Type).

---

## AI Agent Architecture & Tool Layer

The AI Chat widget is not a standalone chatbot — it's a **tool-using agent** that operates on the same atomic primitives that power widgets, the REST API, and MCP servers. This means every capability in the platform is accessible three ways: through the UI (widgets), through conversation (AI agent), and through code (API/MCP).

### Design Principles

| # | Principle | Definition | Test |
|---|-----------|------------|------|
| 1 | **Parity** | Whatever the user can do through the UI, the agent should be able to achieve through tools. | Pick any UI action. Can the agent accomplish it? |
| 2 | **Granularity** | Tools are atomic primitives. Features are outcomes achieved by an agent operating in a loop. | To change behavior, do you edit prompts or refactor code? |
| 3 | **Composability** | With atomic tools and parity, new features are just new prompts — no code required. | Can you ship a new capability without shipping code? |
| 4 | **Emergent capability** | The agent can accomplish things you didn't explicitly design for. | Can it handle open-ended requests in your domain? |

### How It Works

```
User asks: "What's the average Class A office rent in Midtown vs Downtown?"

AI Agent loop:
  1. tool_call: query_comps({ market: "Manhattan", submarket: "Midtown", property_type: "Office", building_class: "A" })
  2. tool_call: query_comps({ market: "Manhattan", submarket: "Downtown", property_type: "Office", building_class: "A" })
  3. tool_call: compute_stats({ metric: "avg_starting_rent", group_by: "submarket" })
  4. Synthesize response with sourced data
```

The agent doesn't have a special "compare markets" feature — it composes atomic tools in a loop to achieve the outcome.

### The Shared Tool Layer

```
┌─────────────────────────────────────────────────────────┐
│                    USER INTERFACES                       │
│                                                         │
│  ┌──────────┐   ┌──────────┐   ┌──────────────────┐    │
│  │ Widgets  │   │ AI Agent │   │ API / MCP Server │    │
│  │ (UI)     │   │ (Chat)   │   │ (Programmatic)   │    │
│  └────┬─────┘   └────┬─────┘   └────────┬─────────┘    │
│       │              │                   │              │
│       └──────────────┼───────────────────┘              │
│                      ▼                                  │
│         ┌────────────────────────┐                      │
│         │   Atomic Tool Layer    │                      │
│         │                        │                      │
│         │  query_comps()         │                      │
│         │  query_sales()         │                      │
│         │  query_properties()    │                      │
│         │  cross_query()         │  ← joins across      │
│         │  get_market_stats()    │    datasets           │
│         │  estimate_rent()       │                      │
│         │  search_tenants()      │                      │
│         │  save_collection()     │  ← persist results   │
│         │  add_collection_layer()│    as reusable object │
│         │  set_deck_filters()    │                      │
│         │  add_widget()          │                      │
│         │  get_news()            │                      │
│         │  resolve_entity()      │                      │
│         │  ...                   │                      │
│         └────────────┬───────────┘                      │
│                      ▼                                  │
│         ┌────────────────────────┐                      │
│         │   DuckDB + SQLite      │                      │
│         │   (10.5M rows CRE)     │                      │
│         └────────────────────────┘                      │
└─────────────────────────────────────────────────────────┘
```

### What This Enables

**Single-dataset queries:**
- **"Show me lease comps near 200 Park Ave"** → `query_comps()` with bounding box, then `add_widget("cre-map")` with results highlighted
- **"Set my dashboard to the Chicago office market"** → `set_deck_filters({ market: "Chicago", property_type: "Office" })`
- **"Compare rent trends for Midtown vs FiDi over the last 3 years"** → `query_comps()` twice, `compute_stats()`, explains the comparison

**Cross-dataset queries (joins across leases, sales, properties):**
- **"Show me sales where there was a Walgreens at the time of sale"** → `cross_query()` joining sales + tenants, `save_collection()`, `add_collection_layer()` on map
- **"Properties that sold in the past 3 years with 50% of leases expiring that year"** → `cross_query()` with aggregation, saved as collection, displayed as map layer + list
- **"Which landlords have the most expiring leases in Manhattan next 12 months?"** → `cross_query()` grouping by landlord, sorted by count

**Open-ended / emergent:**
- **"Help me underwrite 450 Lexington"** → agent discovers what tools are needed (comps, sales history, tenant mix, rent estimate, market context) and loops until the outcome is reached
- **"Generate a market summary for Dallas industrial"** → `get_market_stats()`, `query_comps()`, `get_news()`, synthesizes a report

### Relationship to API & MCP (Phase 7)

The tool layer is built once (Phase 4) and exposed three ways:

| Interface | When | How |
|-----------|------|-----|
| **Widgets** | Phase 1-2 (done) | React components call tRPC routes that use the primitives |
| **AI Agent** | Phase 4 | gpt-5-nano with tool definitions pointing to the same primitives |
| **REST API** | Phase 7 | HTTP endpoints wrapping the same primitives |
| **MCP Servers** | Phase 7 | MCP tool definitions wrapping the same primitives for external LLM integration |

Building the tool layer for the AI agent in Phase 4 directly accelerates Phase 7 — the API/MCP layer is just a different transport for the same tools.

---

## Cross-Dataset Queries & Collections

### The Problem

Today's widgets each show one dataset — Recent Transactions shows leases, the map shows comps as points, Market Overview shows aggregates. But real CRE analysis requires **joining across datasets**:

- *"Show me sales where there was a Walgreens at the time of sale"* → JOIN sales + tenant records, filter by tenant name and date overlap
- *"Properties that sold in the past 3 years with 50% of leases set to expire that year"* → JOIN sales + leases + properties, aggregate lease expirations relative to sale date
- *"Office buildings in Midtown where rents dropped 10%+ since 2023"* → JOIN lease comps + properties, compute rent change over time
- *"Landlords with the most expiring leases in the next 12 months"* → GROUP BY landlord across leases, filter by expiration date

DuckDB can run these cross-dataset joins in milliseconds across 10.5M rows. The platform needs to expose this power through both AI and UI.

### Collections: Saved Query Results as First-Class Objects

A **Collection** is a saved query result that becomes a reusable object in the platform. Think of it as a "smart list" — it's defined by a query, so it stays live as data updates.

| Property | Description |
|----------|-------------|
| **Name** | User-defined label ("Walgreens sales", "Expiring lease properties") |
| **Query** | The underlying DuckDB query (cross-dataset joins, filters, aggregations) |
| **Result type** | Properties, comps, sales, tenants, or mixed |
| **Live vs snapshot** | Live by default (re-runs query); snapshot option for point-in-time analysis |
| **Created by** | AI agent, "Save this result" action, or query builder UI |
| **Stored in** | SQLite (query definition + metadata); results materialized on demand from DuckDB |

### How Collections Appear in Widgets

Collections are not locked to one view — they flow across widgets:

```
┌─────────────────────────────────────────────────────────────────┐
│  Collection: "Walgreens sale properties"                        │
│  Query: sales JOIN tenants WHERE tenant ILIKE '%walgreens%'     │
│  Result: 847 properties                                         │
│                                                                 │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────────┐  │
│  │  Map Layer  │  │  List/Table  │  │  Stats / Aggregates   │  │
│  │  (points on │  │  (sortable,  │  │  (avg price, avg cap  │  │
│  │   the map)  │  │  drill-down  │  │   rate, total volume) │  │
│  │             │  │  to details) │  │                       │  │
│  └─────────────┘  └──────────────┘  └───────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

- **Map widget**: Collection appears as a toggleable layer — same as lease comps or sales comps layers, but user-defined
- **List widget**: Sortable, filterable table of the collection's rows with drill-down to Property Details
- **Stats widget**: Aggregate metrics (avg rent, total volume, count) computed from the collection
- **Deck-level**: A collection can be pinned to a deck so all widgets on that deck can reference it

### Creating Collections

**Via AI Agent (primary)**: Natural language → agent composes the DuckDB query → saves as collection → displays across widgets.

```
User: "Show me all properties that sold in Manhattan in the last 2 years 
       where more than half the leases were expiring within a year of the sale"

Agent:
  1. tool_call: cross_query({ 
       description: "Sales with high lease expiration ratio",
       joins: ["sales", "leases", "properties"],
       ... 
     })
  2. tool_call: save_collection({ name: "High-expiry Manhattan sales", result_id: "..." })
  3. tool_call: add_collection_layer({ collection_id: "...", widget: "cre-map" })
  4. "Found 234 properties. I've saved this as a collection and added it as a 
      map layer. The average sale price was $X/psf with a Y% cap rate..."
```

**Via UI (secondary)**: "Save as Collection" button on any widget's filtered results, or a query builder for constructing cross-dataset queries visually (later phase).

**Via API/MCP**: Programmatic collection creation through the same tool primitives.

### Collections Panel

A sidebar panel (similar to Widget Library) for managing saved collections:
- Browse all saved collections with name, result count, created date
- Toggle collection visibility on map
- Open collection in list widget
- Edit, rename, duplicate, delete
- Share collections across decks

---

## Widget Catalog (50+ Planned)

### Map Widgets (3)
- **CRE Property Map** — Interactive map with 15+ togglable layers (comps, tenants, vacancies, rent heatmaps, construction, sales)
- **Market Map** — Submarket-level visualization of rent trends, absorption, vacancy by geography
- **Portfolio Map** — Overlay portfolio properties with market context

### Rent & Pricing (5)
- **Rent Optimizer** — Estimated starting rent with confidence scores (office, retail, industrial)
- **Underlying Comps** — Display the comps driving rent predictions with distances and weights
- **Adjustable Comps & Weights** — User-adjustable compsets with back-testing vs. CompStak recommendation
- **Vacant Space Pricer** — Price any space by address, even without a lease record
- **Rent Trends** — Time-series rent data by market, submarket, asset class

### Market Intelligence (5)
- **Breaking CRE News** — Aggregated feeds from CRE news sources (tenant moves, expansions, contractions)
- **Market Overview** — Vacancy rates, absorption, asking rents, transaction volume by market
- **AI Market Summary** — AI-generated market reports by geography and asset class
- **Construction Pipeline** — New development and deliveries by market
- **Demographics** — Population growth, employment data, migration patterns affecting rents

### Deal Intelligence (5)
- **Deal Pipeline** — Active deals with stage tracking (Exchange/Deal Manager)
- **Recent Transactions** — Latest lease comps and sales by market
- **News Alerts** — Automated notifications for relevant tenant/market news
- **Deal Activity Heatmap** — Visualization of transaction density by geography
- **Template Outreach** — AI-generated outreach messages for leads

### Tenant & Property (5)
- **Tenant Records** — All known tenants with address, space type, and lease status
- **Active Tenants** — Currently occupied spaces with lease details
- **Property Details** — Property-level view with all associated records
- **Tenant Credit Indicators** — Credit risk signals at tenant and portfolio level
- **Terminated Lease Monitor** — Recently vacated spaces and closure detection

### Portfolio & Underwriting (5)
- **Portfolio Overview** — Aggregate metrics across properties (NOI, occupancy, WALT)
- **Lease Expiration Calendar** — Visual timeline of upcoming expirations
- **Rent Potential** — Gap analysis between in-place rents and market rents
- **Cap Rate Trends** — Historical and current cap rates by market and asset class
- **Income Projection** — Estimated rental income potential across properties

### Broker & Network (4)
- **League Tables** — Broker rankings by market, asset class, transaction volume
- **Broker Rankings** — Competitive dynamics to incentivize data submission
- **Broker Activity Feed** — Recent deal activity from network connections
- **Network Directory** — Anonymous Q&A and connection mechanisms between Exchange and Enterprise

### AI & Analytics (5)
- **AI Agent (Chat)** — Tool-using AI agent that answers CRE questions by calling atomic tool primitives (query comps, get market stats, run rent estimates, set deck filters, add widgets). Same tools exposed via API/MCP. See [AI Agent Architecture](#ai-agent-architecture--tool-layer) below.
- **Custom Alerts** — Monitor any feed for keywords, thresholds, or new items (email/webhook)
- **Market Briefing** — Auto-generated daily/weekly intelligence briefing
- **Situation Reports** — AI-generated multi-pass CRE analysis on custom topics
- **Data Feed Status** — Live health overview of all data sources

### Financial & Economic (4)
- **Interest Rate Monitor** — Fed funds rate, treasury yields, SOFR, CME FedWatch
- **REIT Index Tracker** — FTSE NAREIT, sector-level REIT performance
- **CRE Capital Markets** — CMBS spreads, origination volume, lending conditions
- **Economic Indicators** — GDP, employment, CPI, and other macro factors affecting CRE

### Data Integration (3)
- **Client Data Overlay** — Visualize client proprietary data alongside CompStak data
- **Document Upload** — Bulk upload rent rolls and leases for automatic parsing
- **API Explorer** — Interactive API access to Rent Optimizer, entity resolution, and data feeds

---

## Map Layers (15+)

| Layer | Data Source | Description |
|-------|------------|-------------|
| Lease Comps | CompStak | All lease transactions with rent, term, TI, free rent |
| Sales Comps | CompStak | Property sales with price, cap rate, buyer/seller |
| Active Tenants | CompStak + POI | Currently occupied spaces with tenant details |
| Vacant Spaces | CompStak + POI | Identified vacancies and recently terminated leases |
| Rent Heatmap | Rent Optimizer | Color-coded estimated rents by submarket |
| Construction | CompStak + Public | New developments, under construction, planned |
| Rent Roll Partials | CompStak | Partial lease data (tenant, rent, expiration) |
| Property Boundaries | Public Data | Parcel outlines and property boundaries |
| Submarkets | CompStak | Submarket boundary definitions |
| Zoning | Public Data | Zoning districts and use restrictions |
| Transit | Public Data | Public transit routes and stations |
| Demographics | Census/BLS | Population density, income, employment |
| Portfolio Properties | Client Data | User's own portfolio overlay |
| Comparables Radius | Rent Optimizer | Visual radius of comps used in rent prediction |
| Deal Activity | CompStak | Transaction density over time |

---

## Data Sources

### CompStak Proprietary
- **Lease comps** — 10+ years of verified lease transactions (office, retail, industrial)
- **Sales comps** — Property transaction data
- **Tenant records** — Tenant occupancy data from POI providers and rent rolls
- **Rent roll partials** — Partial lease data (tenant, rent, expiration, sq ft, space type)

### AI/ML Models
- **Rent Optimizer** — ML-based estimated starting rent by space
- **Terminated lease detection** — Automated Google search + AI analysis for closed businesses
- **Entity resolution** — Address, tenant, landlord, and broker name matching

### External Data (Phase 3+)
- **CRE news feeds** — Industry news aggregation (tenant moves, market reports)
- **Demographics** — Census, BLS employment, population data
- **Interest rates** — Federal Reserve, Treasury, SOFR
- **REIT indices** — FTSE NAREIT sector performance
- **Construction pipeline** — Permits, starts, deliveries by market
- **POI data** — Points of interest for tenant record validation

---

## Business Model Alignment

### Exchange (Free) — Data Collection Engine

| Feature | Purpose | Incentive |
|---------|---------|-----------|
| Deal Manager | Accelerate broker deal cycles | Free CRM-like tool |
| Deal Intelligence | Surface leads from past deals and searches | Access tied to data submission |
| News Alerts | Conversation starters with tenants | Free value |
| League Tables | Competitive broker rankings | Submit data to climb rankings |
| Broker Visibility | Showcase to Enterprise users | Network access |
| Dashboard | Customizable CRE workspace | Free with core widgets |

### Enterprise (Paid) — Monetization Engine

| Feature | Tier | Revenue Path |
|---------|------|-------------|
| Rent Optimizer | Platform | Subscription |
| AI Chat & Market Summaries | Platform | Subscription |
| Underlying Comps & Adjustable Weights | Platform | Subscription |
| Vacant Space Pricing | Platform | Premium subscription |
| Portfolio Views | Platform | Subscription |
| API / Data Feeds | API | Premium upsell |
| Data Integration (client data + CompStak) | Enterprise | Key upsell revenue driver |
| MCP Servers for LLM Integration | API | Premium upsell |
| Entity Resolution APIs | API | Premium upsell |
| Collaboration (Exchange ↔ Enterprise) | Platform | Network effects |

---

## Tech Stack

| Layer | Technology | Notes |
|-------|------------|-------|
| Frontend | Next.js 15 (App Router) | React 19, Server Components |
| Styling | Tailwind CSS 4 | Design token system |
| State Management | Zustand | Widget state, layout persistence |
| Maps | Mapbox GL JS | Interactive CRE maps with custom layers |
| Charts | Recharts / D3 | Market trends, rent analytics |
| Grid Layout | react-grid-layout | Drag-and-drop widget positioning |
| Backend | Next.js API Routes + tRPC | Type-safe API layer |
| Analytical DB | DuckDB | 10.5M rows of lease/sales/property data — columnar engine for fast aggregations, map queries, widget data |
| Transactional DB | SQLite (better-sqlite3) | User accounts, saved decks, alert configs, preferences |
| AI | OpenAI (gpt-5-nano) | Tool-using agent with atomic CRE primitives; same tools power API/MCP |
| Auth | NextAuth.js | Exchange (free) + Enterprise (paid) tiers |
| Real-time | Server-Sent Events | Live data updates to widgets |
| Hosting | Vercel | Edge deployment |

## Data Sources (Real CompStak Data)

The platform is built on **real CompStak data exports** (not mock data), stored in `_shared-csv-data/`:

| Dataset | File | Rows | Size | Key Columns |
|---------|------|------|------|-------------|
| Lease Comps | `LeaseSearch_2025-2-24_1336.csv` | 4.1M | 902 MB | starting_rent, effective_rent, TI, free_rent, lease_term, space_type, tenant, landlord, market, submarket, lat/lon, execution_date |
| Property Records | `PropertySearch_2025-3-17_1924.csv` | 3.4M | 734 MB | property_size, year_built, building_class, property_type, rent_estimates, market, submarket, lat/lon |
| Sales Comps | `SalesSearch_2025-3-17_1903.csv` | 2.9M | 1.1 GB | price, price_psf, cap_rate, NOI, buyers, sellers, sale_date, market, submarket |

### Why DuckDB (Analytical) + SQLite (Transactional)

**DuckDB** handles the heavy CRE data (10.5M rows):
- Columnar storage — aggregation queries only read needed columns (e.g., avg rent query skips 70+ irrelevant columns)
- Embedded — runs in-process with Next.js, zero network latency
- Millisecond analytical queries on millions of rows (GROUP BY market, bounding box for map viewports)
- One-time CSV import into a persistent `.duckdb` file

**SQLite** handles user/app data:
- User accounts, sessions, preferences
- Saved deck layouts, widget configurations
- Custom alert definitions, notification settings
- Small data with CRUD operations

This dual-database approach gives dashboard-grade speed for widgets (DuckDB) without needing cloud infrastructure, while keeping user data simple and reliable (SQLite).

---

## Design Principles

1. **Data density over whitespace** — CRE professionals need information-dense views; every pixel should earn its space (Professional personality, tight spacing)
2. **Dark-first tactical interface** — Inspired by SitDeck's intelligence aesthetic; reduces eye strain for all-day use; signals "serious tool"
3. **Zero-config to value** — Ready-made Decks get users to insights in 30 seconds; customization is optional, not required
4. **Modular and composable** — Every widget is independent; any combination works; new widgets can be added without changing existing ones
5. **AI-augmented, not AI-dependent** — AI enhances analysis but data is always visible and explorable; predictions are always explainable with supporting comps. The AI agent uses the same tools as the UI (Parity), composed from atomic primitives (Granularity), enabling new capabilities via prompts alone (Composability)
6. **Exchange ↔ Enterprise bridge** — Platform architecture supports both free (data collection) and paid (monetization) workflows through the same widget system

---

## Out of Scope (for now)

- Mobile native apps (responsive web only for v1)
- Real-time collaboration / multiplayer editing
- CompStak Terminal Marketplace (third-party vendor data)
- Property valuation models (Phase 5 in data roadmap, needs proven rent prediction first)
- CMBS/CLO analytics (future data source)
- International markets (US-focused for v1)

---

## Reference

**Source app**: [SitDeck](https://sitdeck.com/product) — Open-Source Intelligence Dashboard
**CompStak product doc**: 2026 CompStak Product Roadmap: Vision, Strategy & Roadmap
**Analysis date**: 2026-03-03

---

_This file is created by `/clone-app` and serves as the north star for `/build-next` decisions._
_Update with `/vision --update` to reflect what's been built and learned._
