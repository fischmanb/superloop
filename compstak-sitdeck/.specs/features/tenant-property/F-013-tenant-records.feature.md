---
feature: Tenant Records
domain: tenant-property
source: components/widgets/TenantRecords.tsx
tests:
  - tests/db/tenant-records.test.ts
  - tests/widgets/TenantRecords.test.ts
components:
  - TenantRecords
status: implemented
created: 2026-03-07
updated: 2026-03-07
---

# Feature: Tenant Records

**Source File**: components/widgets/TenantRecords.tsx
**DB Layer**: lib/db/tenant-records.ts
**tRPC Router**: lib/trpc/router.ts (tenantRecords namespace)
**Design System**: .specs/design-system/tokens.md

## Overview

The Tenant Records widget surfaces all known tenants from CompStak lease data, with
address, space type, lease status (active vs. expired), and key lease details. Users
can search by tenant name, filter by market, submarket, property type, building class,
and space type. Results are paginated and sortable.

This is the foundational Tenant & Property widget — features #14 (Active Tenants) and
#16 (Terminated Lease Monitor) depend on it.

---

## Feature: Tenant Records Widget

### Scenario: Display tenant records with defaults
Given the TenantRecords widget is mounted
When no filters are applied
Then a paginated table of tenant records is displayed
And each row shows: tenant name, address, space type, lease type, transaction SQFT, starting rent, execution date, expiration date, building class, property type
And results are limited to 50 rows by default
And a total count is shown above the table

### Scenario: Search by tenant name
Given the TenantRecords widget is mounted
When the user types a tenant name in the search input
Then only records matching the tenant name (case-insensitive, substring match) are shown
And the result count updates

### Scenario: Filter by market
Given the TenantRecords widget is mounted
When the user selects a market from the market dropdown
Then only records in that market are shown
And the submarket dropdown repopulates with submarkets for that market

### Scenario: Filter by submarket
Given a market is selected
When the user selects one or more submarkets
Then only records in those submarkets are shown

### Scenario: Filter by property type
Given the TenantRecords widget is mounted
When the user selects one or more property types (Office, Retail, Industrial, Flex/R&D)
Then only records matching those property types are shown

### Scenario: Filter by building class
Given the TenantRecords widget is mounted
When the user selects a building class (A, B, C)
Then only records for that building class are shown

### Scenario: Filter by lease status
Given the TenantRecords widget is mounted
When the user selects "Active" lease status
Then only records where expiration date is in the future (or null) are shown
When the user selects "Expired"
Then only records where expiration date is in the past are shown
When "All" is selected (default)
Then records of all statuses are shown

### Scenario: Deck-level filter inheritance
Given the deck store has a market filter set to "New York City"
When the TenantRecords widget mounts without a local market override
Then it automatically applies the deck-level market filter

### Scenario: Paginate results
Given more than 50 tenant records match the current filters
When the user clicks "Next page"
Then the next 50 records are shown

### Scenario: Sort by column
Given the tenant records table is displayed
When the user clicks a column header (e.g., "Execution Date")
Then the results re-sort by that column
And clicking again reverses the sort order

### Scenario: Empty state
Given filters are applied that match no records
Then a "No records found" message is shown
And the user is invited to clear filters

---

## UI Mockup

```
┌─────────────────────────────────────────────────────────────────────┐
│  TENANT RECORDS                                          1,284 results│
├───────────────────────────────────────────────────────────────────── ┤
│  [🔍 Search tenant name...  ] [Market ▼] [Submarket ▼] [Type ▼]    │
│  [Class ▼] [Status: All ▼]                                          │
├──────────────────┬──────────────────┬───────────┬──────┬────────────┤
│ Tenant Name ▲▼  │ Address          │ Space Type│ Class│ Exec Date  │
├──────────────────┼──────────────────┼───────────┼──────┼────────────┤
│ Amazon.com Inc  │ 410 10th Ave, NY │ Office    │ A    │ 2023-06-15 │
│ Spotify AB      │ 4 World Trade... │ Office    │ A    │ 2022-03-10 │
│ JPMorgan Chase  │ 383 Madison Ave  │ Office    │ A    │ 2021-09-22 │
│ Whole Foods Mkt │ 250 7th Ave, NY  │ Retail    │ B    │ 2020-11-01 │
│ FedEx Ground    │ 500 Commerce Dr  │ Industrial│ B    │ 2023-01-14 │
│ ...             │ ...              │ ...       │ ...  │ ...        │
├──────────────────┴──────────────────┴───────────┴──────┴────────────┤
│  ← Prev   Page 1 of 26   Next →                                     │
└─────────────────────────────────────────────────────────────────────┘
```

Columns visible in full view:
- Tenant Name (sortable, searchable)
- Address (Street Address + City)
- Space Type (badge)
- Property Type
- Building Class (badge: A/B/C)
- Transaction SQFT (formatted with commas)
- Starting Rent ($/SF)
- Execution Date (YYYY-MM-DD)
- Expiration Date (YYYY-MM-DD, color-coded: red=expired, yellow=<12mo, green=active)
- Lease Status badge (Active / Expired)

---

## Constants

```typescript
export const TENANT_SPACE_TYPES = [
  'Flex/R&D', 'Industrial', 'Land', 'Office', 'Other', 'Retail'
] as const

export const TENANT_BUILDING_CLASSES = ['A', 'B', 'C'] as const

export const TENANT_PROPERTY_TYPES = [
  'Office', 'Retail', 'Industrial', 'Mixed-Use', 'Multi-Family', 'Hotel', 'Land', 'Other'
] as const

export const TENANT_LEASE_STATUSES = ['all', 'active', 'expired'] as const

export const TENANT_PAGE_SIZE = 50
```

---

## DB Query Notes

- Source: leases CSV (`snowflake-full-leases-2026-03-04.csv`) via DuckDB view
- Filter on `"Tenant Name"` column (ILIKE for case-insensitive search)
- Market: exact match on `"Market"` column
- Submarket: `"Submarket"` IN list
- Property type: `"Property Type"` IN list
- Building class: `"Building Class"` = value
- Active status: `"Expiration Date" >= CURRENT_DATE OR "Expiration Date" IS NULL`
- Expired status: `"Expiration Date" < CURRENT_DATE`
- Sort default: `"Execution Date"` DESC
- Pagination via OFFSET / LIMIT

---

## Component References

- Design tokens: .specs/design-system/tokens.md
- Related widgets: Active Tenants (#14), Terminated Lease Monitor (#16)

---

## Learnings

- Tenant Name search uses ILIKE '%term%' — adequate for millions of rows with DuckDB's columnar engine
- Expiration Date can be NULL (short-term/rolling leases) — treat NULL as "active" for status filter
- Space Type (from leases) ≠ Property Type — Space Type is the occupied space category; Property Type is the building category
