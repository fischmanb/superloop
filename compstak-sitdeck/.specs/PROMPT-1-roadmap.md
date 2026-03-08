# SitDeck — Prompt 1: Generate Roadmap

> Paste this entire prompt into the Claude for Mac Code tab.
> Run this first. Do not run Prompt 2 until roadmap.md has content and this prompt's commit exists.

---

## Hard Constraints

- These instructions override any conflicting guidance in CLAUDE.md or other repo-level files.
- Follow the numbered steps IN ORDER. Do not explore or investigate files speculatively.
- You may ONLY modify these files: compstak-sitdeck/.specs/roadmap.md, Agents.md, py/auto_sdd/data/general-estimates.jsonl
- You may ONLY create these new files: none
- You may NOT run npm, yarn, pip, brew, or any package manager command
- You may NOT delete any files
- You may read any file necessary for this task. Before reading, state which file and why.
- If you encounter ANYTHING unexpected — files not matching descriptions, missing paths, structure differences — STOP IMMEDIATELY. Report exactly what you found. Take no further action.
- If ANY verification step fails, STOP IMMEDIATELY. Do not commit. Report the failure.
- Before committing, run `git diff --stat` and verify ONLY the allowed files appear. If ANY other file appears, STOP.

---

## Preconditions

```bash
cd ~/auto-sdd
git checkout main
git log --oneline -1
# Expected HEAD: f74fcda add: compstak-sitdeck project scaffold
# If HEAD does not match, STOP IMMEDIATELY.

git fetch origin
git log --oneline origin/main..main
# Expected: empty. If any commits appear, STOP. Brian must push before proceeding.

git checkout -b claude/sitdeck-roadmap-$(openssl rand -hex 3)

ls compstak-sitdeck/.specs/vision.md
wc -l compstak-sitdeck/.specs/vision.md
# Expected: file exists, ~497 lines. If missing or empty, STOP.

ls compstak-sitdeck/.specs/roadmap.md
wc -l compstak-sitdeck/.specs/roadmap.md
# Expected: file exists. Contents may be blank — that is correct. Do not STOP for a blank file.
```

Report: branch forked from, HEAD hash confirmed.

---

## Implementation

1. Read `compstak-sitdeck/.specs/vision.md` in full.
2. Locate the Widget Catalog section. Confirm all 44 named widgets are present. If fewer than 44 are found, STOP and report.
3. Do NOT invent, decompose, or rename widgets. Transcribe the widget list exactly as written in vision.md.
4. Write `compstak-sitdeck/.specs/roadmap.md` using exactly this structure:

---

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

**Last updated**: [today's date]

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

---

5. Add a round entry to `Agents.md`:
   - What was asked: generated SitDeck roadmap.md from vision.md
   - What was changed: compstak-sitdeck/.specs/roadmap.md
   - What was NOT changed: vision.md, features/, all scripts, all lib/, all tests/
   - Verification: counts below

---

## Verification

```bash
grep -c "^| [0-9]" compstak-sitdeck/.specs/roadmap.md
# Expected: 44

grep "Phase 1\|Phase 2\|Phase 3" compstak-sitdeck/.specs/roadmap.md
# Expected: all 3 phase headers present

git diff --stat
# Expected: compstak-sitdeck/.specs/roadmap.md and Agents.md only
# If ANY other file appears, STOP. Do not commit.
```

---

## Token Usage Report

```bash
cd py && .venv/bin/python -c "
from auto_sdd.lib.general_estimates import get_session_actual_tokens, append_general_estimate
from datetime import datetime, timezone
t = get_session_actual_tokens()
est = 12000
active = t['active_tokens']
cumulative = t['cumulative_tokens']
err = round((est - active) / active * 100, 1) if active else 0
print('=== TOKEN USAGE REPORT ===')
print(f'activity_type: sitdeck-roadmap-gen')
print(f'estimated_tokens_pre: {est}')
print(f'actual_tokens_data: {t}')
print(f'active_tokens (input+output): {active}')
print(f'cumulative_tokens (incl cache): {cumulative}')
print(f'estimation_error_pct: {err}')
print(f'source: {t[\"source\"]}')
append_general_estimate({
    'timestamp': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    'activity_type': 'sitdeck-roadmap-gen',
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
git add compstak-sitdeck/.specs/roadmap.md Agents.md py/auto_sdd/data/general-estimates.jsonl
# Do NOT use git add -A or git add .
git commit -m "feat: generate SitDeck roadmap.md — 44 widgets across 3 phases"
# Do NOT merge to main. Do NOT push.
```

Report: branch name and commit hash.

---

Report your findings immediately upon completion. Do not wait for a follow-up question.
