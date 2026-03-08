# SitDeck Roadmap & Feature Stubs — Agent Prompt

## Your Task

Write a complete product roadmap and feature stub files for the CompStak SitDeck project.

You will:
1. Write `~/auto-sdd/compstak-sitdeck/.specs/roadmap.md` — a fully populated roadmap covering all 44 named widgets from vision.md
2. Create one feature stub file per widget in `~/auto-sdd/compstak-sitdeck/.specs/features/`

**Do NOT write a script to generate these files. Write them directly.**

---

## Preconditions

Run these before starting:

```bash
ls ~/auto-sdd/compstak-sitdeck/.specs/
mkdir -p ~/auto-sdd/compstak-sitdeck/.specs/features/
wc -l ~/auto-sdd/compstak-sitdeck/.specs/vision.md
```

If any path is missing, stop and report — do not proceed.

---

## Context

**Repo**: ~/auto-sdd/compstak-sitdeck/ (inside auto-sdd monorepo)
**Spec files**: ~/auto-sdd/compstak-sitdeck/.specs/
**Tech stack**: Next.js 15, DuckDB, SQLite, Mapbox, NextAuth, Zustand, react-grid-layout

### Data Sources

**Leases**: ~/compstak-sitdeck/_shared-csv-data/snowflake-full-leases-2026-03-04.csv
Key columns: Market, Submarket, Space Type, Space Subtype, Transaction Type, Lease Type,
Building Class, Property Type, Property Subtype, Starting Rent, Net Effective Rent, Current Rent,
Asking Rent, Transaction SQFT, Lease Term, Free Rent, TI Value / Work Value, Execution Date,
Commencement Date, Expiration Date, Tenant Name, Tenant Industry, Building Name,
Street Address, City, State, Geo Point, Landlord Brokerage Firms, Landlord Brokers,
Tenant Brokerage Firms, Tenant Brokers

**Sales**: ~/compstak-sitdeck/_shared-csv-data/snowflake-full-sales-2026-03-04.csv
Key columns: Market, Submarket, Total Sale Price, Sale Price (PSF), Cap Rate, NOI,
Sale Date, Sale Quarter, Buyer, Seller, Building Class, Property Type, Property Subtype,
Transaction SQFT, Building Size, Street Address, City, State, Geo Point

**No property records CSV exists.** Property-level queries derive from lease/sales data.

---

## Canonical Enumerations — Use Verbatim

Do not invent values. These come directly from the data.

**Building Class**: A, B, C

**Space Type** (leases only): Office, Industrial, Retail, Flex/R&D, Land, Other

**Property Type** (leases + sales): Hotel, Industrial, Land, Mixed-Use, Multi-Family, Office, Other, Retail

**Transaction Type** (leases, 13 values):
New Lease, Renewal, Expansion, Extension, Extension/Expansion, Early Renewal, Pre-lease,
Relet, Assignment, Restructure, Renewal/Expansion, Renewal/Contraction, Long leasehold

**Lease Type** (leases, 8 values):
Full Service, Gross, Industrial Gross, Modified Gross, Net, NN, NNN, Net of Electric

**Markets** (105 total — use this set for mocks):
New York City, Los Angeles - Orange - Inland, Chicago Metro, Dallas - Ft. Worth, Boston,
Bay Area, Washington DC, Houston, Atlanta, Miami - Ft. Lauderdale, Seattle, Denver,
Philadelphia - Central PA - DE - So. NJ, Phoenix, Austin, Nashville, Charlotte, Tampa Bay,
San Francisco, San Diego, New Jersey - North and Central, Long Island, Westchester and CT,
Baltimore, Minneapolis - St. Paul, Detroit - Ann Arbor - Lansing, St. Louis Metro,
Kansas City Metro, Portland Metro, Sacramento - Central Valley, Las Vegas, Salt Lake City,
Indianapolis, Columbus, Pittsburgh, Richmond, Raleigh - Durham, Orlando, Jacksonville, San Antonio

**Submarket**: NOT a static enum. 900+ values. Acceptance criteria must say:
"Submarket dropdown populates from data, filtered by currently selected Market."

**Sales-side type fields** (Sale Type, Buyer Type, Seller Type): Free-text — not enumerable.
Any filter on these fields must be a text search input, not a dropdown.

**Property Subtype** (representative subset for mocks — 58 values total):
Apartments, Business Park, Community Shopping Center, Convenience/Strip Center, Flex/R&D,
Heavy Industrial, Hospital/Healthcare Facility, Life Science/Lab, Light Industrial, Manufacturing,
Medical/Healthcare, Mixed-Use, Neighborhood Shopping Center, Professional Building,
Restaurant/Bar, Self-Storage, Shallow Bay, Warehouse/Distribution

---

## Step 1: Write roadmap.md

Path: ~/auto-sdd/compstak-sitdeck/.specs/roadmap.md

Use exactly this section structure:

```
# SitDeck Product Roadmap

## Overview
[1-2 sentences]

## Phase Structure
- Phase 1 — Core data widgets (lease comps, maps, market intelligence, deal/tenant data)
- Phase 2 — AI, portfolio analysis, broker network, advanced analytics
- Phase 3 — External data feeds (financial markets, economic indicators, demographics)

---

## Widget Roadmap

### Map Widgets

#### F-001: CRE Property Map
- **Phase**: 1
- **Category**: Map
- **Data**: Leases + Sales
- **Priority**: P1
- **Status**: Planned
- **Description**: [one sentence]
- **Key Columns**: Geo Point, Market, Submarket, Space Type, Building Class, Starting Rent, Transaction SQFT
- **Stub**: features/F-001-cre-property-map.md

[continue for all 44 widgets using sequential F-IDs]
```

Phase assignments (assign these exactly):

Phase 1: CRE Property Map, Market Map, Portfolio Map, Rent Optimizer, Underlying Comps,
Adjustable Comps & Weights, Vacant Space Pricer, Rent Trends, Market Overview,
Construction Pipeline, Recent Transactions, Deal Activity Heatmap, Tenant Records,
Active Tenants, Property Details, Terminated Lease Monitor, Portfolio Overview,
Lease Expiration Calendar, Rent Potential, Cap Rate Trends, Income Projection,
League Tables, Broker Rankings, Broker Activity Feed, Network Directory, Data Feed Status

Phase 2: Breaking CRE News, AI Market Summary, Deal Pipeline, News Alerts,
Template Outreach, Tenant Credit Indicators, AI Agent (Chat), Custom Alerts,
Market Briefing, Situation Reports, Client Data Overlay, Document Upload, API Explorer

Phase 3: Demographics, Interest Rate Monitor, REIT Index Tracker,
CRE Capital Markets, Economic Indicators

Key Columns in each entry must be real column names from the data sources above.
---

## Step 2: Write Feature Stubs

Write one file per widget at: ~/auto-sdd/compstak-sitdeck/.specs/features/F-XXX-kebab-widget-name.md

Use this exact structure:

```
# F-001: CRE Property Map

**Category**: Map
**Phase**: 1
**Data Source**: Leases + Sales
**Status**: Planned

## Description
[2-3 sentences on what the widget does and why it matters]

## Acceptance Criteria

- [ ] Widget renders in a deck grid cell at minimum 2x2 grid units
- [ ] Map initializes centered on the selected Market from the deck-level filter
- [ ] Comp markers load from DuckDB query on the Geo Point column, filtered by:
  - Market: single-select dropdown, values from MOCK_MARKETS constant
  - Property Type: multi-select, values from MOCK_PROPERTY_TYPES constant
  - Building Class: multi-select, values from MOCK_BUILDING_CLASSES constant
  - Date Range: preset picker (Last 12mo, Last 3yr, All Time)
- [ ] Submarket dropdown populates from data filtered by currently selected Market (not a static list)
- [ ] [at least 3 widget-specific criteria]
- [ ] Widget-level filters override deck-level filters when set
- [ ] Loading state shown while DuckDB query executes
- [ ] Empty state shown when no data matches filters

## Mock Data Spec

const MOCK_MARKETS = [
  "New York City", "Chicago Metro", "Los Angeles - Orange - Inland",
  "Dallas - Ft. Worth", "Boston", "Bay Area", "Washington DC",
  "Houston", "Atlanta", "Miami - Ft. Lauderdale", "Seattle", "Denver",
  "Phoenix", "Austin", "Nashville", "Charlotte", "Tampa Bay",
  "Philadelphia - Central PA - DE - So. NJ", "San Francisco", "San Diego",
  "New Jersey - North and Central", "Long Island", "Westchester and CT",
  "Baltimore", "Minneapolis - St. Paul", "Portland Metro", "Las Vegas",
  "Salt Lake City", "Raleigh - Durham", "Orlando", "San Antonio"
];
const MOCK_BUILDING_CLASSES = ["A", "B", "C"];
const MOCK_PROPERTY_TYPES = ["Hotel", "Industrial", "Land", "Mixed-Use", "Multi-Family", "Office", "Other", "Retail"];
const MOCK_SPACE_TYPES = ["Office", "Industrial", "Retail", "Flex/R&D", "Land", "Other"];
const MOCK_TRANSACTION_TYPES = [
  "New Lease", "Renewal", "Expansion", "Extension", "Extension/Expansion",
  "Early Renewal", "Pre-lease", "Relet", "Assignment", "Restructure",
  "Renewal/Expansion", "Renewal/Contraction", "Long leasehold"
];
const MOCK_LEASE_TYPES = [
  "Full Service", "Gross", "Industrial Gross", "Modified Gross",
  "Net", "NN", "NNN", "Net of Electric"
];

// 5+ sample records — real column names, realistic values
const MOCK_RECORDS = [
  {
    "Street Address": "200 Park Ave", "City": "New York", "State": "NY",
    "Market": "New York City", "Submarket": "Midtown",
    "Space Type": "Office", "Building Class": "A", "Property Type": "Office",
    "Starting Rent": 85.00, "Net Effective Rent": 72.50,
    "Transaction SQFT": 12500, "Lease Term": 60,
    "Transaction Type": "New Lease", "Lease Type": "Full Service",
    "Execution Date": "2024-03-15", "Geo Point": "40.7527,-73.9772"
  },
  ... (4 more records across different markets and property types)
];

## API Readiness Notes

- MOCK_* constants replace with GET /api/enums/{type} when live
- DuckDB column names in queries match CSV headers verbatim — no mapping needed at integration
- Submarket filter wired to parent Market selection — no API change needed at integration
- [any widget-specific note on Sales data, AI endpoints, or external feeds]
```
---

## Rules for Stubs

1. Acceptance criteria must be widget-specific — not generic boilerplate
2. Every filter dropdown must reference a named MOCK_* constant
3. Mock data must have 5+ records with realistic values using exact column names from the data
4. Widgets using Sales data: include Total Sale Price, Sale Price (PSF), Cap Rate in mock records
5. Widgets with Buyer/Seller/Sale Type filters: text search input only — note this in acceptance criteria
6. Phase 3 widgets: acceptance criteria describe the data contract and output format.
   Mock uses hardcoded placeholder values with a TODO comment for feed integration.
7. AI widgets: acceptance criteria describe input prompt format and expected output format only.

---

## Verification

Run after completing all files:

```bash
echo "=== Feature count in roadmap ==="
grep -c "^#### F-0" ~/auto-sdd/compstak-sitdeck/.specs/roadmap.md

echo "=== Stub files created ==="
ls ~/auto-sdd/compstak-sitdeck/.specs/features/ | wc -l

echo "=== Named widget spot check ==="
grep -rl "CRE Property Map\|Recent Transactions\|Market Overview\|League Tables\|Rent Optimizer\|AI Agent" \
  ~/auto-sdd/compstak-sitdeck/.specs/features/ | wc -l

echo "=== Enum check ==="
grep -rl "MOCK_MARKETS\|MOCK_BUILDING_CLASSES" \
  ~/auto-sdd/compstak-sitdeck/.specs/features/ | wc -l
```

Expected output: 44, 44, 6, 44

Fix any mismatch before reporting done.

---

## Definition of Done

- [ ] roadmap.md: all 44 entries, each with ID / phase / priority / data source / key columns / stub path
- [ ] 44 stub files in features/ directory
- [ ] Every stub: real column names, real enum values, no invented market names or building classes
- [ ] Sales-side type filters: text search pattern (not dropdown)
- [ ] Submarket: dynamic load pattern, not static list
- [ ] All 4 verification counts pass (44, 44, 6, 44)
