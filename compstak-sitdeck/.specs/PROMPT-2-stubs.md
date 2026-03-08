# SitDeck — Prompt 2: Generate Feature Stubs

> Paste this entire prompt into the Claude for Mac Code tab.
> Run AFTER Prompt 1 is merged to main. Do not run /build-next until all 44 stub files pass verification.

---

## Scope Note

This prompt writes 44 files. If context runs low before all 44 are complete, stop at the end of the current phase, commit what exists, and report progress. Brian will run this prompt again referencing the next phase. Do NOT partially write a file.

---

## Hard Constraints

- These instructions override any conflicting guidance in CLAUDE.md or other repo-level files.
- Follow the numbered steps IN ORDER. Do not explore or investigate files speculatively.
- You may ONLY modify these files: Agents.md, py/auto_sdd/data/general-estimates.jsonl
- You may ONLY create these new files: compstak-sitdeck/.specs/features/F-001-*.md through F-044-*.md (44 stub files, exact names specified below)
- You may NOT run npm, yarn, pip, brew, or any package manager command
- You may NOT delete any files
- You may read any file necessary for this task. Before reading, state which file and why.
- If you encounter ANYTHING unexpected — roadmap.md missing, widget count wrong, paths missing — STOP IMMEDIATELY. Report exactly what you found. Take no further action.
- If ANY verification step fails, STOP IMMEDIATELY. Do not commit. Report the failure.
- Before committing, run `git diff --stat` and verify ONLY the allowed files appear. If ANY other file appears, STOP.

---

## Preconditions

```bash
cd ~/auto-sdd
git checkout main
git log --oneline -1
# Expected HEAD: aef6c99 merge: SitDeck roadmap.md generated
# If HEAD does not match, STOP IMMEDIATELY.

git fetch origin
git log --oneline origin/main..main
# Expected: empty. If any commits appear, STOP.

git checkout -b claude/sitdeck-stubs-$(openssl rand -hex 3)

ls compstak-sitdeck/.specs/roadmap.md
grep -c "^| [0-9]" compstak-sitdeck/.specs/roadmap.md
# Expected: file exists, count = 44. If missing or count != 44, STOP.

mkdir -p compstak-sitdeck/.specs/features/
ls compstak-sitdeck/.specs/features/ | wc -l
# Expected: 0 (no stubs yet). If files already exist, report and wait for instruction.
```

Report: branch name, HEAD confirmed.

---

## Data Sources (reference only — do not open these files)

**Leases**: `~/compstak-sitdeck/_shared-csv-data/snowflake-full-leases-2026-03-04.csv`
Key columns: Market, Submarket, Space Type, Space Subtype, Transaction Type, Lease Type,
Building Class, Property Type, Property Subtype, Starting Rent, Net Effective Rent, Current Rent,
Asking Rent, Transaction SQFT, Lease Term, Free Rent, TI Value / Work Value, Execution Date,
Commencement Date, Expiration Date, Tenant Name, Tenant Industry, Building Name,
Street Address, City, State, Geo Point, Landlord Brokerage Firms, Landlord Brokers,
Tenant Brokerage Firms, Tenant Brokers

**Sales**: `~/compstak-sitdeck/_shared-csv-data/snowflake-full-sales-2026-03-04.csv`
Key columns: Market, Submarket, Total Sale Price, Sale Price (PSF), Cap Rate, NOI,
Sale Date, Sale Quarter, Buyer, Seller, Building Class, Property Type, Property Subtype,
Transaction SQFT, Building Size, Street Address, City, State, Geo Point

**Properties**: `~/compstak-sitdeck/_shared-csv-data/snowflake-full-properties-2025-03-17.csv` (3.4M rows)
Key columns: ID, LINK, ADDRESS, CITY, STATE, ZIPCODE, COUNTY, MARKET, SUBMARKET,
LATITUDE, LONGITUDE, PROPERTY_NAME, LANDLORD, PROPERTY_SIZE, PARKING_RATIO,
YEAR_BUILT, YEAR_RENOVATED, LOT_SIZE, LOADING_DOCKS_COUNT, GROUND_LVL_DOORS_COUNT,
FLOOR_AREA_RATIO, FLOORS, CEILING_HEIGHT, BUILDING_CLASS, PROPERTY_TYPE, PROPERTY_SUBTYPE,
PROPERTY_MARKET_EFFECTIVE_RENT_ESTIMATE, PROPERTY_MARKET_STARTING_RENT_ESTIMATE, DATE_CREATED

NOTE: Properties CSV uses LATITUDE + LONGITUDE as separate columns — not "Geo Point".
The LINK column is a URL to the CompStak exchange listing per property.

---

## Canonical Enumerations — Use Verbatim in Every Stub

Do not invent values. Use exactly these in mock data and MOCK_* constants.

**Building Class**: A, B, C

**Space Type** (leases only): Office, Industrial, Retail, Flex/R&D, Land, Other

**Property Type** (leases + sales): Hotel, Industrial, Land, Mixed-Use, Multi-Family, Office, Other, Retail

**Transaction Type** (leases, 13 values):
New Lease, Renewal, Expansion, Extension, Extension/Expansion, Early Renewal, Pre-lease,
Relet, Assignment, Restructure, Renewal/Expansion, Renewal/Contraction, Long leasehold

**Lease Type** (leases, 8 values):
Full Service, Gross, Industrial Gross, Modified Gross, Net, NN, NNN, Net of Electric

**MOCK_MARKETS** (use exactly this list):
New York City, Los Angeles - Orange - Inland, Chicago Metro, Dallas - Ft. Worth, Boston,
Bay Area, Washington DC, Houston, Atlanta, Miami - Ft. Lauderdale, Seattle, Denver,
Philadelphia - Central PA - DE - So. NJ, Phoenix, Austin, Nashville, Charlotte, Tampa Bay,
San Francisco, San Diego, New Jersey - North and Central, Long Island, Westchester and CT,
Baltimore, Minneapolis - St. Paul, Detroit - Ann Arbor - Lansing, St. Louis Metro,
Kansas City Metro, Portland Metro, Sacramento - Central Valley, Las Vegas, Salt Lake City,
Indianapolis, Columbus, Pittsburgh, Richmond, Raleigh - Durham, Orlando, Jacksonville, San Antonio

**Submarket**: NOT enumerable — 900+ values. Every stub with a submarket filter must say:
"Submarket dropdown populates from data filtered by currently selected Market — never a static list."

**Sale Type, Buyer Type, Seller Type**: Free-text, not enumerable. Always text search input, never a dropdown. State this explicitly in AC for any widget using these fields.

**Property Subtype** (use for mocks): Apartments, Business Park, Community Shopping Center,
Flex/R&D, Heavy Industrial, Hospital/Healthcare Facility, Life Science/Lab, Light Industrial,
Manufacturing, Medical/Healthcare, Mixed-Use, Neighborhood Shopping Center, Professional Building,
Restaurant/Bar, Self-Storage, Shallow Bay, Warehouse/Distribution

---

## Implementation

Write one file per widget. Use this exact file path pattern:
`compstak-sitdeck/.specs/features/F-{NNN}-{kebab-name}.md`

Use this exact stub structure for every file:

```markdown
# F-{NNN}: {Widget Name}

**Category**: {category}
**Phase**: {1|2|3}
**Data Source**: {Leases | Sales | Leases + Sales | Properties CSV | External | AI | Internal}
**Status**: Planned

## Description
[2–3 sentences: what this widget does and why it matters to a CRE professional]

## Acceptance Criteria

- [ ] Widget renders in a deck grid cell at minimum 2×2 grid units
- [ ] [filter and data loading criteria specific to this widget — reference MOCK_* constants by name]
- [ ] Submarket dropdown populates from data filtered by currently selected Market — never a static list [omit line if widget has no submarket filter]
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

// 5+ records using exact CSV column names, realistic values
const MOCK_RECORDS = [ ... ];
```

## API Readiness Notes

- MOCK_* constants replace with `GET /api/enums/{type}` when live
- DuckDB column names match CSV headers verbatim — no mapping needed at integration
- Submarket filter wired to parent Market selection — no change at integration
- [widget-specific note on Sales columns, AI endpoints, or external feed contracts]
```

---

## Rules

1. Acceptance criteria must be widget-specific — not boilerplate repeated across all 44
2. Every filter dropdown references a named MOCK_* constant — not an inline array
3. Mock data has 5+ records with realistic values using exact CSV column names
4. Sales widgets: include Total Sale Price, Sale Price (PSF), Cap Rate in mock records
5. Buyer/Seller/Sale Type filters: text search input only — state this explicitly in AC
6. Phase 3 widgets: AC describes data contract and output format; mock uses placeholder values with a TODO comment for feed integration
7. AI widgets (Phase 2): AC describes input prompt format and expected output format only
8. Stub format is identical across all 44 — no improvised variations

---

## File List (write in this order)

**Phase 1** (F-001–F-026):
- F-001-cre-property-map.md
- F-002-market-map.md
- F-003-portfolio-map.md
- F-004-rent-optimizer.md
- F-005-underlying-comps.md
- F-006-adjustable-comps-and-weights.md
- F-007-vacant-space-pricer.md
- F-008-rent-trends.md
- F-009-market-overview.md
- F-010-construction-pipeline.md
- F-011-recent-transactions.md
- F-012-deal-activity-heatmap.md
- F-013-tenant-records.md
- F-014-active-tenants.md
- F-015-property-details.md
- F-016-terminated-lease-monitor.md
- F-017-portfolio-overview.md
- F-018-lease-expiration-calendar.md
- F-019-rent-potential.md
- F-020-cap-rate-trends.md
- F-021-income-projection.md
- F-022-league-tables.md
- F-023-broker-rankings.md
- F-024-broker-activity-feed.md
- F-025-network-directory.md
- F-026-data-feed-status.md

**Phase 2** (F-027–F-039):
- F-027-breaking-cre-news.md
- F-028-ai-market-summary.md
- F-029-deal-pipeline.md
- F-030-news-alerts.md
- F-031-template-outreach.md
- F-032-tenant-credit-indicators.md
- F-033-ai-agent-chat.md
- F-034-custom-alerts.md
- F-035-market-briefing.md
- F-036-situation-reports.md
- F-037-client-data-overlay.md
- F-038-document-upload.md
- F-039-api-explorer.md

**Phase 3** (F-040–F-044):
- F-040-demographics.md
- F-041-interest-rate-monitor.md
- F-042-reit-index-tracker.md
- F-043-cre-capital-markets.md
- F-044-economic-indicators.md

---

## Verification

```bash
echo "=== Stub count ===" && \
ls /Users/brianfischman/auto-sdd/compstak-sitdeck/.specs/features/ | wc -l

echo "=== Widget spot check ===" && \
grep -rl "CRE Property Map\|Recent Transactions\|Market Overview\|League Tables\|Rent Optimizer\|AI Agent" \
  /Users/brianfischman/auto-sdd/compstak-sitdeck/.specs/features/ | wc -l

echo "=== Enum check ===" && \
grep -rl "MOCK_MARKETS\|MOCK_BUILDING_CLASSES" \
  /Users/brianfischman/auto-sdd/compstak-sitdeck/.specs/features/ | wc -l

git diff --stat
# Expected: 44 stub files + Agents.md + general-estimates.jsonl only
# If ANY other file appears, STOP. Do not commit.
```

Expected counts: 44 / 6 / 44. Fix any mismatch before committing.

---

## Agents.md Entry

Add a round entry:
- What was asked: generated 44 SitDeck feature stub files from roadmap.md
- What was changed: 44 files in compstak-sitdeck/.specs/features/
- What was NOT changed: roadmap.md, vision.md, all scripts, all lib/, all tests/
- Verification: counts above

---

## Token Usage Report

```bash
cd py && .venv/bin/python -c "
from auto_sdd.lib.general_estimates import get_session_actual_tokens, append_general_estimate
from datetime import datetime, timezone
t = get_session_actual_tokens()
est = 25000
active = t['active_tokens']
cumulative = t['cumulative_tokens']
err = round((est - active) / active * 100, 1) if active else 0
print('=== TOKEN USAGE REPORT ===')
print(f'activity_type: sitdeck-stubs-gen')
print(f'estimated_tokens_pre: {est}')
print(f'actual_tokens_data: {t}')
print(f'active_tokens (input+output): {active}')
print(f'cumulative_tokens (incl cache): {cumulative}')
print(f'estimation_error_pct: {err}')
print(f'source: {t[\"source\"]}')
append_general_estimate({
    'timestamp': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    'activity_type': 'sitdeck-stubs-gen',
    'estimated_tokens_pre': est,
    'active_tokens': active,
    'cumulative_tokens': cumulative,
})
print('=== END REPORT ===')
" && cd ..
```

---

## Commit

```bash
git add compstak-sitdeck/.specs/features/ Agents.md py/auto_sdd/data/general-estimates.jsonl
# Do NOT use git add -A or git add .
# Do NOT merge to main. Do NOT push.
git commit -m "feat: generate SitDeck feature stubs — 44 widgets (F-001–F-044)"
```

Report: branch name, commit hash, and final stub count from verification.

---

Report your findings immediately upon completion. Do not wait for a follow-up question.
