---
description: Generate all 44 SitDeck feature stub files from the populated roadmap (compstak-sitdeck/.specs/features/)
---

Generate SitDeck feature stubs: $ARGUMENTS

## Preconditions

Run these checks first. If any fail, stop and report — do not proceed:

```bash
ls /Users/brianfischman/auto-sdd/compstak-sitdeck/.specs/roadmap.md
wc -l /Users/brianfischman/auto-sdd/compstak-sitdeck/.specs/roadmap.md
mkdir -p /Users/brianfischman/auto-sdd/compstak-sitdeck/.specs/features/
```

`roadmap.md` must exist and have content. If it's blank or missing, run `/sitdeck-roadmap create` first.

---

## What This Command Does

Reads the populated `compstak-sitdeck/.specs/roadmap.md` and writes one `.md` stub file per widget into `compstak-sitdeck/.specs/features/`.

**Do NOT write a script to generate these files. Write each file directly.**

---

## Context

**Repo**: compstak-sitdeck/ (inside auto-sdd monorepo — agent is already at repo root)
**Specs dir**: compstak-sitdeck/.specs/
**Features dir**: compstak-sitdeck/.specs/features/
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

**Properties**: ~/compstak-sitdeck/_shared-csv-data/snowflake-full-properties-2025-03-17.csv (3.4M rows)
Key columns: ID, LINK, ADDRESS, CITY, STATE, ZIPCODE, COUNTY, MARKET, SUBMARKET,
LATITUDE, LONGITUDE, PROPERTY_NAME, LANDLORD, PROPERTY_SIZE, PARKING_RATIO,
YEAR_BUILT, YEAR_RENOVATED, LOT_SIZE, LOADING_DOCKS_COUNT, GROUND_LVL_DOORS_COUNT,
FLOOR_AREA_RATIO, FLOORS, CEILING_HEIGHT, BUILDING_CLASS, PROPERTY_TYPE, PROPERTY_SUBTYPE,
PROPERTY_MARKET_EFFECTIVE_RENT_ESTIMATE, PROPERTY_MARKET_STARTING_RENT_ESTIMATE, DATE_CREATED

NOTE: Properties CSV uses LATITUDE + LONGITUDE as separate columns (not "Geo Point").
The LINK column contains a URL to the CompStak exchange listing per property.

---

## Canonical Enumerations — Use Verbatim

Do not invent values. Use exactly these.

**Building Class**: A, B, C

**Space Type** (leases only): Office, Industrial, Retail, Flex/R&D, Land, Other

**Property Type** (leases + sales): Hotel, Industrial, Land, Mixed-Use, Multi-Family, Office, Other, Retail

**Transaction Type** (leases, 13 values):
New Lease, Renewal, Expansion, Extension, Extension/Expansion, Early Renewal, Pre-lease,
Relet, Assignment, Restructure, Renewal/Expansion, Renewal/Contraction, Long leasehold

**Lease Type** (leases, 8 values):
Full Service, Gross, Industrial Gross, Modified Gross, Net, NN, NNN, Net of Electric

**Markets** (use this exact set for MOCK_MARKETS):
New York City, Los Angeles - Orange - Inland, Chicago Metro, Dallas - Ft. Worth, Boston,
Bay Area, Washington DC, Houston, Atlanta, Miami - Ft. Lauderdale, Seattle, Denver,
Philadelphia - Central PA - DE - So. NJ, Phoenix, Austin, Nashville, Charlotte, Tampa Bay,
San Francisco, San Diego, New Jersey - North and Central, Long Island, Westchester and CT,
Baltimore, Minneapolis - St. Paul, Detroit - Ann Arbor - Lansing, St. Louis Metro,
Kansas City Metro, Portland Metro, Sacramento - Central Valley, Las Vegas, Salt Lake City,
Indianapolis, Columbus, Pittsburgh, Richmond, Raleigh - Durham, Orlando, Jacksonville, San Antonio

**Submarket**: NOT a static enum. 900+ values. All stubs must specify:
"Submarket dropdown populates from data, filtered by currently selected Market."

**Sales-side type fields** (Sale Type, Buyer Type, Seller Type): Free-text — not enumerable.
Any filter on these must be a text search input, never a dropdown.

**Property Subtype** (representative subset for mocks):
Apartments, Business Park, Community Shopping Center, Flex/R&D, Heavy Industrial,
Hospital/Healthcare Facility, Life Science/Lab, Light Industrial, Manufacturing,
Medical/Healthcare, Mixed-Use, Neighborhood Shopping Center, Professional Building,
Restaurant/Bar, Self-Storage, Shallow Bay, Warehouse/Distribution

---

## Stub File Structure

Write each file at: `compstak-sitdeck/.specs/features/F-{NNN}-{kebab-widget-name}.md`

```markdown
# F-{NNN}: {Widget Name}

**Category**: {category}
**Phase**: {1|2|3}
**Data Source**: {Leases | Sales | Leases + Sales | External | AI | Internal}
**Status**: Planned

## Description
[2-3 sentences: what the widget does and why it matters to a CRE professional]

## Acceptance Criteria

- [ ] Widget renders in a deck grid cell at minimum 2x2 grid units
- [ ] [filters and data loading specific to this widget — reference MOCK_* constants by name]
- [ ] Submarket dropdown populates from data filtered by currently selected Market (not a static list)
  [omit if widget has no submarket filter]
- [ ] Widget-level filters override deck-level filters when set
- [ ] Loading state shown while DuckDB query executes
- [ ] Empty state shown when no data matches filters
- [ ] [3+ widget-specific behavioral criteria]

## Mock Data Spec

```typescript
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

// 5+ sample records using exact CSV column names, realistic values
const MOCK_RECORDS = [ ... ];
```

## API Readiness Notes

- MOCK_* constants replace with `GET /api/enums/{type}` when live
- DuckDB column names match CSV headers verbatim — no mapping needed at integration
- Submarket filter wired to parent Market selection — no API change needed at integration
- [any widget-specific notes on Sales columns, AI endpoints, or external feed contracts]
```

---

## Rules

1. Acceptance criteria must be widget-specific — no boilerplate that applies to all 44
2. Every filter dropdown must reference a named MOCK_* constant (not an inline array)
3. Mock data must have 5+ records with realistic values using exact column names
4. Widgets using Sales data: include Total Sale Price, Sale Price (PSF), Cap Rate in records
5. Widgets with Buyer/Seller/Sale Type filters: text search input only — state this in AC
6. Phase 3 widgets: AC describes the data contract and output format; mock uses hardcoded placeholder values with a TODO comment for feed integration
7. AI widgets (Phase 2): AC describes input prompt format and expected output format only
8. Stub format must be identical across all 44 — no improvised variations

---

## Widget List

Write stubs for all 44 widgets in roadmap order. F-IDs assigned sequentially:

**Phase 1** (F-001 – F-026):
CRE Property Map, Market Map, Portfolio Map, Rent Optimizer, Underlying Comps,
Adjustable Comps & Weights, Vacant Space Pricer, Rent Trends, Market Overview,
Construction Pipeline, Recent Transactions, Deal Activity Heatmap, Tenant Records,
Active Tenants, Property Details, Terminated Lease Monitor, Portfolio Overview,
Lease Expiration Calendar, Rent Potential, Cap Rate Trends, Income Projection,
League Tables, Broker Rankings, Broker Activity Feed, Network Directory, Data Feed Status

**Phase 2** (F-027 – F-039):
Breaking CRE News, AI Market Summary, Deal Pipeline, News Alerts, Template Outreach,
Tenant Credit Indicators, AI Agent (Chat), Custom Alerts, Market Briefing,
Situation Reports, Client Data Overlay, Document Upload, API Explorer

**Phase 3** (F-040 – F-044):
Demographics, Interest Rate Monitor, REIT Index Tracker, CRE Capital Markets, Economic Indicators

---

## Verification

Run after all 44 files are written:

```bash
echo "=== Stub files created ==="
ls /Users/brianfischman/auto-sdd/compstak-sitdeck/.specs/features/ | wc -l

echo "=== Named widget spot check ==="
grep -rl "CRE Property Map\|Recent Transactions\|Market Overview\|League Tables\|Rent Optimizer\|AI Agent" \
  /Users/brianfischman/auto-sdd/compstak-sitdeck/.specs/features/ | wc -l

echo "=== Enum check ==="
grep -rl "MOCK_MARKETS\|MOCK_BUILDING_CLASSES" \
  /Users/brianfischman/auto-sdd/compstak-sitdeck/.specs/features/ | wc -l
```

Expected: 44, 6, 44. Fix any mismatch before reporting done.

---

## After Completing

```
✅ SitDeck feature stubs written: 44 files in compstak-sitdeck/.specs/features/

Phase breakdown:
- Phase 1: F-001 – F-026 (26 core data widgets)
- Phase 2: F-027 – F-039 (13 AI/advanced widgets)
- Phase 3: F-040 – F-044 (5 external feed widgets)

Next step: Run /build-next to start building
```
