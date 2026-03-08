---
feature: Recent Transactions
domain: deal-intelligence
source: components/widgets/RecentTransactions.tsx
tests:
  - tests/widgets/recent-transactions.test.ts
components:
  - RecentTransactions
  - TransactionRow
status: implemented
created: 2026-03-07
updated: 2026-03-07
---

# Feature: Recent Transactions

**Source File**: `components/widgets/RecentTransactions.tsx`
**Data**: Leases CSV + Sales CSV via DuckDB
**Design System**: `.specs/design-system/tokens.md`

A tabular widget showing the most recent lease and sale transactions filtered by market,
property type, and date range. Supports deck-level filter inheritance with widget-level
overrides.

---

## Feature: Recent Transactions

### Scenario: Default view loads recent transactions
Given the user opens the SitDeck dashboard
When the Recent Transactions widget mounts
Then it fetches the 50 most recent transactions from DuckDB
And displays them in a table sorted by date descending
And each row shows: Date, Type (Lease/Sale), Address, Market, Tenant/Buyer, SQFT, Rent/Price PSF

### Scenario: Filter by transaction type
Given the Recent Transactions widget is showing combined lease and sale results
When the user selects "Leases Only" from the type filter
Then only lease transactions are shown
When the user selects "Sales Only"
Then only sale transactions are shown
When the user selects "Both"
Then both leases and sales are shown, merged and sorted by date

### Scenario: Filter by market
Given the Recent Transactions widget is visible
When the user selects a market from the market dropdown
Then the table reloads showing only transactions for that market
And the submarket dropdown populates with submarkets from that market

### Scenario: Filter by submarket
Given the user has selected a market
When the user selects one or more submarkets
Then the table reloads showing only transactions for those submarkets

### Scenario: Filter by date range
Given the Recent Transactions widget is visible
When the user sets a date range (from / to)
Then only transactions with execution/sale date within that range are shown

### Scenario: Deck-level filter inheritance
Given the deck-level market filter is set to "Manhattan"
When the Recent Transactions widget mounts
Then it inherits the market filter and shows only Manhattan transactions
When the user sets a widget-level market filter to "Chicago"
Then the widget shows Chicago transactions (widget overrides deck)

### Scenario: Empty state
Given filters are set such that no transactions match
When the query returns zero rows
Then the widget displays "No transactions found for the selected filters"

### Scenario: Loading state
Given the user changes a filter
When the DuckDB query is in flight
Then the widget shows a loading skeleton in place of the table rows

---

## UI Mockup

```
┌─────────────────────────────────────────────────────────────────────────┐
│ RECENT TRANSACTIONS                                          [↻ Refresh] │
├──────────────┬──────────────────────┬──────────────────────┬────────────┤
│ Market: [▾]  │ Type: [Both     ▾]   │ From: [________]     │ To:[______]│
├──────────────┴──────────────────────┴──────────────────────┴────────────┤
│ DATE       │ TYPE  │ ADDRESS               │ MARKET   │ TENANT/BUYER    │
│ SQFT       │ PSF   │ SPACE TYPE            │ LEASE TYPE│               │
├────────────┼───────┼───────────────────────┼──────────┼─────────────────┤
│ 2026-02-14 │ LEASE │ 123 Park Ave          │ Manhattan│ Goldman Sachs   │
│ 25,000     │ $85   │ Office                │ Full Svc │                 │
├────────────┼───────┼───────────────────────┼──────────┼─────────────────┤
│ 2026-02-12 │ SALE  │ 455 Market St         │ SF       │ Blackstone      │
│ 180,000    │ $650  │                       │          │                 │
├────────────┼───────┼───────────────────────┼──────────┼─────────────────┤
│                           [ Load more ]                                  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Component References

- Design tokens: `.specs/design-system/tokens.md`
- DuckDB queries: `lib/db/recent-transactions.ts`
- tRPC router: `lib/trpc/router.ts`
- Deck store: `lib/store/deck.ts`

---

## Canonical Constants

```typescript
export const TRANSACTION_TYPES = ['both', 'lease', 'sale'] as const
export const PROPERTY_TYPES = ['Office', 'Retail', 'Industrial', 'Multifamily', 'Mixed Use'] as const
export const DATE_PRESETS = [
  { label: 'Last 30 days', days: 30 },
  { label: 'Last 90 days', days: 90 },
  { label: 'Last 12 months', days: 365 },
  { label: 'Last 3 years', days: 1095 },
] as const
```
