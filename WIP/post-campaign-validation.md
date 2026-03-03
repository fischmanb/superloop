# Post-Campaign Validation Pipeline

**Status:** WIP — spec draft v0.3
**Location:** `auto-sdd/WIP/post-campaign-validation.md`
**Scope:** Autonomous post-campaign validation for any auto-sdd target project. Boots the app, validates runtime, generates acceptance criteria from specs, tests them via Playwright, catalogs failures, performs root cause analysis, and fixes them through the existing build-loop gates.

## Changelog

| Version | Date       | Changes |
|---------|------------|---------|
| v0.1    | 2026-02-28 | Initial spec draft |
| v0.2    | 2026-02-28 | Phase 2a discrepancy classification (MISSING/PARTIAL/DRIFTED/UNEXPECTED). Phase 4 split into 4a (Catalog) and 4b (RCA). Documentation versioning system with flush toggle. |
| v0.3    | 2026-02-28 | QA test account as build-phase deliverable. Phase 0 auth bootstrap. Cleanup teardown. |

---

## Problem

The build loop validates features individually (tsc, unit tests, optional drift check). It never boots the full app. Campaigns that build 20+ features routinely produce applications that:

- Don't start (`npm run dev` crashes)
- Start but fail production build (`npm run build` — server/client boundary violations, missing modules)
- Render but have broken styles (tailwind config drift, missing CSS classes)
- Load but throw runtime errors on interaction (cascading failures across features)
- Have features that pass all unit tests but are unreachable from the UI

These are caught manually after the campaign ends, costing hours of triage. The fix is a multi-agent pipeline that catches them automatically.

---

## Architecture

Seven phases (Phase 4 split into Catalog + RCA), each executed by isolated agents with fresh context. No agent sees the full campaign. Each phase's output is structured, versioned, and feeds the next phase as input.

```
┌─────────────┐   ┌─────────────┐   ┌──────────────┐
│  PHASE 0    │──▶│  PHASE 1    │──▶│  PHASE 2     │
│  Runtime    │   │  Discovery  │   │  AC          │
│  Bootstrap  │   │  Agent      │   │  Generation  │
└─────────────┘   └─────────────┘   └──────────────┘
                                           │
                                           ▼
                  ┌─────────────┐   ┌──────────────┐
                  │  PHASE 4a   │◀──│  PHASE 3     │
                  │  Failure    │   │  Playwright  │
                  │  Catalog    │   │  Validation  │
                  └──────┬──────┘   └──────────────┘
                         │                 │
                         ▼                 ▼
                  ┌─────────────┐   ┌──────────────┐
                  │  PHASE 4b   │   │  PHASE 3b    │
                  │  Root Cause │   │  Gap Tests   │
                  │  Analysis   │   └──────────────┘
                  └──────┬──────┘
                         │
                         ▼
                  ┌─────────────┐
                  │  PHASE 5    │
                  │  Fix Agents │
                  │  (per-fix)  │
                  └─────────────┘
```

---

## Documentation Versioning & Flush System

All pipeline artifacts are versioned documents. Each phase produces structured output that is written to disk through a controlled flush mechanism.

### Document Registry

Every artifact produced by the pipeline is registered in `.sdd-state/validation-docs.json`:

```json
{
  "run_id": "val-20260228-143022",
  "flush_mode": "auto",
  "documents": [
    {
      "id": "discovery-inventory",
      "phase": "1",
      "version": 1,
      "path": "logs/validation/{run_id}/phase-1/discovery-inventory.v1.json",
      "checksum": "sha256:abc123...",
      "flushed_at": "2026-02-28T14:32:15Z",
      "status": "final"
    },
    {
      "id": "acceptance-criteria",
      "phase": "2a",
      "version": 2,
      "path": "logs/validation/{run_id}/phase-2/acceptance-criteria.v2.json",
      "checksum": "sha256:def456...",
      "flushed_at": "2026-02-28T14:35:22Z",
      "status": "final",
      "supersedes": "acceptance-criteria.v1.json"
    }
  ]
}
```

### Flush Modes

**Auto (default):** Each phase flushes its output to disk immediately upon completion. The orchestrator writes the document, registers it, and proceeds to the next phase. No human gate.

**Manual:** Phase output is held in memory (passed via structured JSON between phases) and NOT written to disk until an explicit flush command. Useful for:
- Dry runs where you want to inspect output before committing to disk
- Debugging where you want to re-run a phase without accumulating stale artifacts
- Selective persistence — flush only the phases you care about

**Toggle:**
```bash
# Auto mode (default)
./scripts/post-campaign-validation.sh --flush=auto

# Manual mode — hold everything in memory
./scripts/post-campaign-validation.sh --flush=manual

# Manual flush during a paused run
./scripts/post-campaign-validation.sh --resume --flush-now

# Flush specific phase output
./scripts/post-campaign-validation.sh --resume --flush-phase=2a
```

### Versioning Rules

1. Each document is versioned independently (v1, v2, v3...)
2. A phase re-run increments the version of its output document
3. Previous versions are retained (not overwritten) — `discovery-inventory.v1.json` stays when `v2` is written
4. The registry always points to the latest version per document
5. `--resume` reads the latest version of each upstream dependency
6. Retention policy: keep last 3 versions per document per run. Older versions are pruned on next flush.

### Phase-to-Document Mapping

| Phase | Document ID | Format |
|-------|------------|--------|
| 0     | `runtime-report` | JSON |
| 0     | `qa-credentials` | JSON (ephemeral, never versioned, wiped on cleanup) |
| 1     | `discovery-inventory` | JSON |
| 2a    | `acceptance-criteria` | JSON |
| 2b    | `gap-criteria` | JSON |
| 3     | `validation-results` | JSON |
| 3b    | `gap-validation-results` | JSON |
| 4a    | `failure-catalog` | JSON |
| 4b    | `root-cause-analysis` | JSON |
| 5     | `fix-reports` (one per fix) | JSON |

---

## QA Test Account (Build-Phase Deliverable)

**Problem:** The discovery agent can't browse authenticated routes without credentials. Auth bypass middleware is invasive and a security risk. The build agent already knows the app's auth stack because it just built it.

**Solution:** The build agent produces a `scripts/qa-seed.ts` (or `.sh`, `.js` — whatever matches the project) as a standard build deliverable for any project with authentication. This script:

1. **Creates** a test user account through the app's actual user creation path (ORM insert, API call, auth provider SDK — whatever the app uses)
2. **Outputs** credentials to stdout as JSON: `{"email": "qa-{uuid}@test.local", "password": "{random}", "role": "admin"}`
3. **Accepts** a `--teardown` flag that deletes the test account and any associated data

**Requirements:**
- Credentials are randomly generated per run (UUID email prefix, random password). No hardcoded values.
- The test user should have the highest permission level available (admin/superuser) so the discovery agent can reach all routes.
- The script must be idempotent — running it twice doesn't create duplicate accounts.
- The script must work with the app's actual auth system, not a backdoor. If login is broken, the test account won't help, and that's a real failure to catch.

**Spec integration:** Feature specs for auth-gated features should note auth requirements (e.g., "requires authenticated user," "requires admin role"). The build agent uses this to ensure the seed script creates an account with appropriate access. If no spec mentions auth, the build agent should still produce a seed script if it detects an auth system in the codebase (NextAuth, Clerk, Supabase, etc.) — defensive by default.

**Lifecycle:**
```
Build phase:  build agent produces scripts/qa-seed.ts alongside features
Phase 0:      orchestrator runs `scripts/qa-seed.ts` → credentials written to .sdd-state/qa-credentials.json
Phase 0 (auth verify): Playwright opens login page, submits credentials, confirms auth succeeds
Phase 1+:     all Playwright sessions start by logging in with stored credentials
Cleanup:      orchestrator runs `scripts/qa-seed.ts --teardown` → account deleted
              .sdd-state/qa-credentials.json wiped
              git status verified clean (no QA artifacts committed)
```

**Failure modes:**
- Seed script doesn't exist → skip auth, discovery runs unauthenticated (will miss protected routes, but catalog captures this)
- Seed script fails → `AUTH_SETUP_FAILED` in Phase 0 output. Pipeline continues unauthenticated with a warning.
- Login fails with valid credentials → real bug. Catalog it.
- Teardown fails → warning in final report. Credentials file still wiped. Orphaned test account is low-risk (random email, test DB).

**Security constraints:**
- `scripts/qa-seed.ts` is committed to the project repo (it's a legitimate test utility, not a backdoor)
- `.sdd-state/qa-credentials.json` is gitignored and ephemeral — never committed
- Credentials exist only for the duration of the validation run
- The test account uses a `@test.local` domain that won't collide with real users

---

## Phase 0: Runtime Bootstrap

**Goal:** Get the app running on localhost. No agent — pure shell.

**Steps:**
1. `npm install` (or detected package manager)
2. `npm run build` — production build. If this fails, stop. The campaign left broken code. Output the error and exit with a structured failure report. No point browsing an app that won't build.
3. `npm run dev` (or detected dev command) — start dev server in background.
4. Health check: poll localhost (port auto-detected from project config or default 3000/5173) until it responds with HTTP 200 or timeout after 60s.
5. If health check fails, capture console output and exit with failure report.
6. **Auth bootstrap** (if `scripts/qa-seed.ts` exists):
   - Run the seed script. Parse JSON credentials from stdout.
   - Write credentials to `.sdd-state/qa-credentials.json`.
   - Launch Playwright, navigate to the app's login page, submit credentials, verify authentication succeeds (look for redirect to authenticated route or absence of login form).
   - If login fails, report `AUTH_SETUP_FAILED` but continue — pipeline runs unauthenticated.

**Output:**
```
RUNTIME_READY: http://localhost:{port}
AUTH_READY: qa-{uuid}@test.local (admin)
```
or
```
RUNTIME_READY: http://localhost:{port}
AUTH_SETUP_FAILED: {reason} — continuing unauthenticated
```
or
```
RUNTIME_FAILED: {phase} — {error summary}
```

**Gate:** Hard. If the app doesn't start, nothing else runs. The failure report becomes the fix input (skip to Phase 4a catalog with the build/runtime error as the sole failure).

**Project-agnostic considerations:**
- Package manager detection: check for `pnpm-lock.yaml`, `yarn.lock`, `package-lock.json` in that order
- Dev command detection: check `package.json` scripts for `dev`, `start`, `serve`
- Port detection: parse dev command output or check common ports (3000, 3001, 5173, 8080)
- Framework detection: Next.js, Vite, CRA each have different dev server behaviors and build commands

---

## Phase 1: Discovery Agent

**Goal:** Browse the running app with no prior knowledge. Produce a structured inventory of what exists.

**Agent inputs:**
- App URL (from Phase 0)
- Playwright browser tools
- QA credentials (from `.sdd-state/qa-credentials.json`, if auth bootstrap succeeded)
- Instruction: "Log in using the provided credentials (if any), then browse this web application systematically. Visit every discoverable page. On each page, inventory all interactive elements, visible text sections, and navigation links. Take a screenshot of each distinct page/state. Report any console errors, missing images, or broken layouts you observe."

**Agent does NOT get:**
- Roadmap, specs, feature list, or any knowledge of what should exist
- Component names, file paths, or implementation details

**Output schema:**
```json
{
  "routes_found": [
    {
      "url": "/dashboard",
      "screenshot_path": "discovery/dashboard.png",
      "interactive_elements": ["nav-link:Settings", "button:Create New", "filter:Category"],
      "console_errors": [],
      "visual_issues": ["Sidebar text overlaps on narrow viewport"]
    }
  ],
  "navigation_graph": {"/" : ["/dashboard", "/settings"], "/dashboard": ["/item/1"]},
  "global_issues": ["Tailwind classes not loading on /settings page"],
  "unreachable_dead_ends": ["/settings — back button missing"]
}
```

**Scope limit:** Max 20 routes. Max 5 minutes. If the app has more than 20 distinct routes, the agent reports "discovered 20+ routes, stopped at limit" and moves on.

---

## Phase 2: Acceptance Criteria Generation

**Goal:** Produce testable acceptance criteria per feature by comparing what should exist (specs) against what does exist (discovery). Explicitly classify the match quality for each feature.

### Discrepancy Classification

Every feature from the roadmap receives one of four statuses after comparing specs against the discovery inventory:

| Status | Definition | AC Strategy |
|--------|-----------|-------------|
| **FOUND** | Feature's route and primary UI elements exist in discovery and match spec expectations | Write criteria per spec. Standard testing path. |
| **MISSING** | Feature is in the roadmap/specs but has no corresponding route, page section, or UI elements in discovery | Write criteria anyway — they become the test for "is this really missing or just hidden?" All criteria expected to FAIL or BLOCKED. |
| **PARTIAL** | Route exists but only some spec'd behaviors/elements are present (e.g., page renders but half the controls are missing) | Write criteria for all spec'd behaviors. Mark which criteria target present vs absent elements. Expect mixed PASS/FAIL. |
| **DRIFTED** | Feature exists in discovery but doesn't match spec (different route, different UI pattern, renamed elements, divergent behavior) | Write criteria per the spec's *intent*, not per discovery. If tests fail, that's signal of implementation divergence. Include a `drift_notes` field describing the observed vs expected difference. |
| **UNEXPECTED** | Something exists in discovery that matches no spec at all | Detected by 2a agent (included in single-pass prompt). Phase 2b mechanically verifies coverage gaps. |

### Phase 2a: Spec-Based AC Writer

**Inputs:**
- Roadmap (`.specs/roadmap.md`)
- Feature specs (`.specs/features/*.feature.md`)
- Discovery inventory from Phase 1

**Instruction:** "For each feature in the roadmap that is marked as built, compare its spec against the discovery inventory. Classify the match as FOUND, MISSING, PARTIAL, or DRIFTED. Then write concrete Playwright-testable acceptance criteria. Each criterion must be verifiable through browser interaction alone — no file system access, no code inspection. For FOUND and PARTIAL features, ground criteria in actual discovered routes/elements. For MISSING features, write criteria based on spec alone — these will likely fail, confirming the absence. For DRIFTED features, write criteria per the spec's intent, not the discovered implementation."

**Output per feature:**
```json
{
  "feature": "News Category Filter",
  "status": "PARTIAL",
  "route": "/news",
  "match_notes": "Route exists, filter dropdown present, but sort control from spec not found",
  "criteria": [
    {
      "id": "AC-001",
      "description": "User can filter news articles by category",
      "targets_present_element": true,
      "steps": [
        "Navigate to /news",
        "Locate category filter control",
        "Select 'Technology' category",
        "Verify displayed articles change to show only Technology articles"
      ],
      "expected_outcome": "Only articles with Technology category visible"
    },
    {
      "id": "AC-002",
      "description": "User can sort filtered results by date",
      "targets_present_element": false,
      "steps": [
        "Navigate to /news",
        "Locate sort control",
        "Select 'Date (newest first)'",
        "Verify article order changes"
      ],
      "expected_outcome": "Articles displayed in descending date order"
    }
  ],
  "drift_notes": null
}
```

**Example DRIFTED output:**
```json
{
  "feature": "User Settings Page",
  "status": "DRIFTED",
  "route": "/account/preferences",
  "match_notes": "Spec defines /settings route with tabbed layout. Discovery found /account/preferences with accordion layout instead.",
  "drift_notes": "Route changed from /settings to /account/preferences. UI pattern changed from tabs to accordion. Core settings fields appear present but organized differently.",
  "criteria": [ "..." ]
}
```

### Phase 2b: Mechanical Gap Detection (no agent call)

**Implementation note (2026-03-03):** Originally spec'd as a second agent pass. Refactored to pure Python set operations (`detect_coverage_gaps()`). The 2b agent received the same discovery inventory that 2a already had, and gap detection is a structural comparison, not a reasoning task. UNEXPECTED element detection merged into the 2a prompt.

**Inputs:**
- Phase 2a output (feature list with criteria)
- Discovery inventory

**Mechanical checks (pure Python):**
1. Compare discovery routes against routes referenced in criteria → uncovered routes
2. Flag criteria where `targets_present_element` is False → likely broken

**Output:** Gap report with `uncovered_routes` and `likely_broken` lists.

**Scope limit:** Total AC count should not exceed 10 per feature.

---

## Phase 3: Playwright Validation

**Goal:** Execute acceptance criteria as automated Playwright tests against the running app.

**Structure:** One agent invocation per feature (parallelizable in future, sequential for v1). Each agent gets:

- App URL
- The acceptance criteria for ONE feature (from Phase 2)
- Playwright tools (navigate, click, type, screenshot, assert)
- Instruction: "Write and execute a Playwright test for each acceptance criterion. For each criterion, report PASS or FAIL with a screenshot. If a criterion cannot be tested because the UI element doesn't exist or the route is unreachable, report BLOCKED with explanation."

**Output per criterion:**
```
VALIDATION_PASS: AC-001 — User can filter news by category
VALIDATION_FAIL: AC-002 — Sort control exists but clicking it throws runtime error [screenshot: fail-ac002.png]
VALIDATION_BLOCKED: AC-003 — Settings page returns 404
```

**Scope limits per agent:**
- Max 10 criteria (enforced by Phase 2 cap)
- Max 3 retries per criterion (click didn't land, page still loading, etc.)
- 5 minute timeout per feature's test suite
- If Playwright itself crashes, report `INFRA_FAILURE` and move to next feature

### Phase 3b: AC Gap Playwright Pass

**Inputs:**
- Gap criteria from Phase 2b
- App URL

**Same mechanics as Phase 3.** Tests the supplemental criteria that cover elements discovered but not spec'd. These results are tagged as `GAP_TEST` to distinguish from spec-derived tests.

---

## Phase 4a: Failure Catalog

**Goal:** Collect all validation failures into a clean, objective catalog. No analysis, no guessing at root cause, no file references. Just what failed.

**Inputs:**
- All Phase 3/3b results (pass, fail, blocked)
- Discovery inventory screenshots (for reference)

**Instruction:** "Create a structured catalog of every validation failure and blocked criterion. For each entry: what was tested, what was expected, what actually happened, and the screenshot reference. Do not speculate about root causes. Do not reference source files. Do not group failures. Just describe each one plainly and accurately."

**Output:**
```json
{
  "run_id": "val-20260228-143022",
  "catalog": [
    {
      "id": "FAIL-001",
      "criterion_id": "AC-002",
      "feature": "News Category Filter",
      "feature_status": "PARTIAL",
      "result": "FAIL",
      "description": "Sort control not found on /news page",
      "expected": "Dropdown or button labeled 'Sort' present on page",
      "actual": "No sort control found. Page contains filter dropdown and article list only.",
      "screenshot": "phase-3/news-filter/fail-ac002.png",
      "console_errors": ["TypeError: Cannot read properties of undefined (reading 'sort')"],
      "timestamp": "2026-02-28T14:45:12Z"
    },
    {
      "id": "FAIL-002",
      "criterion_id": "AC-007",
      "feature": "Calendar View",
      "feature_status": "FOUND",
      "result": "FAIL",
      "description": "Calendar renders but all event tiles show 'undefined' instead of event titles",
      "expected": "Event tiles display event title text",
      "actual": "All 6 visible event tiles display the text 'undefined'",
      "screenshot": "phase-3/calendar/fail-ac007.png",
      "console_errors": [],
      "timestamp": "2026-02-28T14:47:33Z"
    },
    {
      "id": "BLOCK-001",
      "criterion_id": "AC-015",
      "feature": "User Settings",
      "feature_status": "DRIFTED",
      "result": "BLOCKED",
      "description": "Settings page returns 404 at spec'd route /settings",
      "expected": "Page loads at /settings",
      "actual": "HTTP 404. Discovery found settings-like content at /account/preferences instead.",
      "screenshot": "phase-3/settings/block-ac015.png",
      "console_errors": [],
      "timestamp": "2026-02-28T14:50:01Z"
    }
  ],
  "stats": {
    "total_criteria": 45,
    "passed": 31,
    "failed": 10,
    "blocked": 4,
    "gap_tested": 8,
    "gap_passed": 6,
    "gap_failed": 2
  }
}
```

**Why this is separate from RCA:** The catalog is objective and verifiable. A human can look at it and say "yes, these are real failures" without needing to evaluate whether the root cause analysis is correct. It's the ground truth layer. If RCA gets it wrong, you can re-run 4b against the same catalog without re-running Playwright.

---

## Phase 4b: Root Cause Analysis

**Goal:** Take the failure catalog and group failures by probable root cause. Identify likely files involved. Prioritize for fix agents.

**Inputs:**
- Failure catalog from Phase 4a
- Discovery inventory (for context on app structure)
- Project file tree (to help identify which source files are relevant)
- Phase 2a discrepancy classifications (MISSING/PARTIAL/DRIFTED status informs RCA)

**Agent does NOT get:**
- Full source code
- Build logs from the original campaign
- Feature implementation history

**Instruction:** "Analyze this failure catalog. Group failures that likely share a common root cause — multiple features may fail because of one shared issue (e.g., a broken layout component, a missing API route, a tailwind config problem). For each root cause group, identify the likely files involved using the project file tree. Prioritize by impact. Use the discrepancy classifications from Phase 2a to inform your analysis — DRIFTED features may have different root causes than MISSING ones."

**Priority ranking:**
1. Issues that block multiple features
2. Runtime errors (console errors present)
3. MISSING features (entire feature absent)
4. PARTIAL features (elements missing from otherwise working pages)
5. DRIFTED features (implementation diverged from spec)
6. Visual/layout problems
7. Gap test failures (UNEXPECTED behavior in unspec'd elements)

**Output:**
```json
{
  "root_causes": [
    {
      "id": "RC-001",
      "priority": 1,
      "root_cause": "Tailwind config missing custom color tokens used by 4 features",
      "confidence": "high",
      "affected_failures": ["FAIL-001", "FAIL-004", "FAIL-008", "FAIL-009"],
      "affected_features": ["Calendar View", "Dashboard", "Settings", "Profile"],
      "likely_files": ["tailwind.config.ts", "src/styles/globals.css"],
      "fix_description": "Add missing color token definitions to tailwind config",
      "estimated_complexity": "small"
    },
    {
      "id": "RC-002",
      "priority": 3,
      "root_cause": "Settings feature built at /account/preferences instead of spec'd /settings",
      "confidence": "high",
      "affected_failures": ["BLOCK-001", "BLOCK-002"],
      "affected_features": ["User Settings"],
      "likely_files": ["src/app/account/preferences/page.tsx", "src/lib/navigation.ts"],
      "fix_description": "Add redirect from /settings to /account/preferences, or move page to spec'd route",
      "estimated_complexity": "small"
    }
  ],
  "ungrouped_failures": [],
  "stats": {
    "total_failures": 14,
    "grouped_into_root_causes": 14,
    "ungrouped": 0,
    "root_cause_count": 6
  }
}
```

**Scope limit:** Max 15 root cause groups. If RCA produces more than 15, the agent must consolidate — if there are truly 15+ independent root causes, the campaign has systemic problems and a human needs to intervene.

**Confidence levels:** `high` (strong evidence from multiple correlated failures), `medium` (plausible but only 1-2 failures), `low` (speculative, may be wrong). Fix agents should tackle `high` confidence items first.

---

## Phase 5: Fix Agents

**Goal:** Fix each root cause, one agent per fix, through the existing build-loop gates.

**Structure:** Sequential, ordered by RCA priority. High-confidence root causes first. Each fix agent gets:

- The root cause item from Phase 4b (root cause, affected files, fix description)
- Access to the relevant source files (and only those files — not the whole codebase)
- The specific failure catalog entries for this root cause (from Phase 4a)
- Instruction: "Fix this specific issue. After fixing, run the project's build and test commands to verify your fix doesn't break anything. If the fix requires changes to more than 4 files, stop and report — the scope may be wrong."

**After each fix agent completes:**
1. Run existing gates: `tsc --noEmit`, `npm test`, `npm run build`
2. If gates pass, commit with message: `fix(post-validation): {fix description}`
3. Reboot dev server
4. Re-run ONLY the affected Playwright criteria (not the full suite) to verify the fix actually resolved the reported failures
5. If re-validation fails, revert the commit and report `FIX_FAILED` with details

**Scope limits:**
- Max 4 files modified per fix agent
- 10 minute timeout per fix
- If a fix agent needs more context than provided, it reports `NEEDS_ESCALATION` rather than reading the whole codebase
- Max 2 retry attempts per fix item before marking it `MANUAL_INTERVENTION_REQUIRED`
- Skip `low` confidence root causes entirely — report them for human review

---

## Orchestration

**Script:** `scripts/post-campaign-validation.sh`
**Sources:** `lib/reliability.sh` (locking, backoff, state, truncation)

**Invocation:**
```bash
cd ~/auto-sdd && PROJECT_DIR=./stakd-v2 ./scripts/post-campaign-validation.sh

# With manual flush
cd ~/auto-sdd && PROJECT_DIR=./stakd-v2 ./scripts/post-campaign-validation.sh --flush=manual

# Resume after crash
cd ~/auto-sdd && PROJECT_DIR=./stakd-v2 ./scripts/post-campaign-validation.sh --resume

# Flush specific phase from a manual run
cd ~/auto-sdd && PROJECT_DIR=./stakd-v2 ./scripts/post-campaign-validation.sh --resume --flush-phase=4a
```

**State persistence:** `.sdd-state/validation-state.json` — tracks which phase completed, which features validated, which fixes applied. Supports `--resume` for crash recovery (same pattern as build loop).

**Document persistence:** `.sdd-state/validation-docs.json` — tracks all versioned documents, their flush status, and lineage. See Documentation Versioning section.

**Logging:** All agent outputs, screenshots, and Playwright results go to `logs/validation/{timestamp}/` with per-phase subdirectories.

**Cleanup (always runs, even on crash):**
1. Kill dev server process
2. Run `scripts/qa-seed.ts --teardown` (if seed script exists) — deletes test account
3. Wipe `.sdd-state/qa-credentials.json`
4. Verify `git status` shows no QA artifacts staged or committed
5. Optionally: `npm run build` one final time to confirm the app builds clean post-fixes

**Exit codes:**
- 0: All criteria pass (or pass after fixes)
- 1: Fixes applied, some criteria still failing (report generated)
- 2: Runtime bootstrap failed (app doesn't start)
- 3: Infrastructure failure (Playwright crash, agent timeout)

---

## Roadmap (Prioritized Build Order)

### Milestone 1: Runtime Bootstrap (Phase 0)
**Priority:** Highest — everything else depends on this.
**Scope:** Shell script, no agents. Package manager detection, build, dev server start, health check.
**Validation:** Run against stakd-v2 post-campaign. Does it boot? Does production build pass?
**Estimated complexity:** Small. One function in the orchestration script.

### Milestone 2: Discovery Agent (Phase 1)
**Priority:** High — generates the ground truth all other phases need.
**Scope:** One agent prompt, Playwright browser tools, structured JSON output.
**Dependency:** Milestone 1 (app must be running).
**Validation:** Run against stakd-v2. Does the inventory match what you see when you manually browse?
**Estimated complexity:** Medium. Agent prompt design + output parsing. Playwright integration is the new infrastructure.

### Milestone 3: AC Generation (Phase 2a + 2b)
**Priority:** High — without criteria, there's nothing to test.
**Scope:** One agent prompt (2a: spec reader + discovery matcher + UNEXPECTED detection) + mechanical Python gap detection (2b). Discrepancy classification (FOUND/MISSING/PARTIAL/DRIFTED/UNEXPECTED).
**Dependency:** Milestones 1 + 2.
**Validation:** Human review of generated criteria. Do they make sense? Are they testable? Are discrepancy classifications accurate?
**Estimated complexity:** Medium-Hard. The quality of generated AC and the accuracy of discrepancy classification determines the quality of everything downstream.

### Milestone 4: Playwright Validation (Phase 3 + 3b)
**Priority:** High — this is the core value.
**Scope:** Per-feature agent invocations. Playwright test writing + execution.
**Dependency:** Milestones 1 + 2 + 3.
**Validation:** Run against stakd-v2. Do pass/fail results match manual testing?
**Estimated complexity:** Hard. Playwright test generation by agents is unreliable. Will need iteration on prompt design and retry logic.

### Milestone 5: Failure Catalog + Documentation Versioning (Phase 4a + flush system)
**Priority:** Medium-High — the catalog is the objective truth layer; versioning is the persistence backbone.
**Scope:** One agent prompt for catalog. Flush toggle implementation in orchestrator. Document registry.
**Dependency:** Milestone 4.
**Validation:** Is the catalog accurate? Can you resume from a flushed state? Do version numbers increment correctly on re-runs?
**Estimated complexity:** Medium. Catalog agent is simple (no analysis). Flush system is plumbing but critical for reliability.

### Milestone 6: Root Cause Analysis (Phase 4b)
**Priority:** Medium — interpretive layer, useful but separable.
**Scope:** One agent prompt. Failure grouping + file identification + priority ranking.
**Dependency:** Milestone 5.
**Validation:** Do the groupings make sense? Would a human triage differently? Are confidence levels appropriate?
**Estimated complexity:** Medium. Pattern matching across failures. Needs codebase file tree awareness.

### Milestone 7: Fix Agents (Phase 5)
**Priority:** Medium — the payoff, but only as good as RCA.
**Scope:** Per-fix agent invocations through existing gates.
**Dependency:** All previous milestones.
**Validation:** Do fixes stick? Does re-validation confirm resolution?
**Estimated complexity:** Hard. Fix agents face the same reliability challenges as build agents. The existing sidecar feedback loop should help.

---

## Open Questions

1. **Playwright installation.** Does the target project need Playwright as a devDependency, or does the validation script install it in a temp location? Keeping it out of the project's `package.json` avoids polluting the target project.

2. **Dev server management.** Phase 0 starts the dev server. When does it stop? After Phase 3? After Phase 5? If fix agents modify code, the dev server may need a restart (HMR handles most changes, but not all).

3. **Screenshot storage.** Could generate hundreds of screenshots across a full run. Where do they go? `logs/validation/` seems right. Should they be committed to the repo or gitignored?

4. **Token budget tracking.** Log `--output-format json` usage from every agent invocation. Build a profile over time. Set alerts when an agent exceeds 2x its historical average — likely means it's spiraling.

5. **Parallel validation.** Phase 3 is per-feature and embarrassingly parallel. v1 runs sequential. When do we parallelize? Probably after v1 proves the concept on stakd-v2.

6. **Catalog-to-RCA handoff in manual flush mode.** If Phase 4a output isn't flushed, Phase 4b reads from memory. If the run crashes between 4a and 4b, the catalog is lost. Should manual mode force-flush between phases that have downstream consumers? Or is that the user's problem?

7. **DRIFTED features — fix to spec or accept drift?** When a feature is DRIFTED, should the fix agent correct it to match the spec, or should it update the spec to match the implementation? v1 probably fixes to spec. Future versions could ask.

8. **Version retention across runs.** Current policy: keep 3 versions per document per run. But across runs? If you run validation 5 times, that's potentially 15 versions of discovery-inventory. Retention policy for cross-run cleanup TBD.
