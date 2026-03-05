# Auto-QA Validation Against CRE — Implementation Plan

> Status: Implementation phase. Investigation complete.
> Author: Brian Fischman + Claude, 2026-03-04
> Depends on: auto-QA pipeline (COMPLETE), CRE lease tracker (3 features built)
> Investigation reports: two agent investigations on branch `claude/apply-hard-constraints-mJKTY`

---

## 1. Problem Statement

The auto-QA pipeline (`py/auto_sdd/scripts/post_campaign_validation.py`) has 96 passing tests but zero production runs. Before building the campaign intelligence system on top of it, we must validate it works against a real project. CRE lease tracker is the benchmark: 3 features (auth + dashboard, lease comp search, comp detail/export), Vite + TypeScript client, TypeScript server, split client/server directory structure.

---

## 2. Investigation Findings

### Blockers

| # | Issue | Severity | Detail |
|---|-------|----------|--------|
| B1 | Phase 0 doesn't handle monorepo/split projects | Critical | `detect_package_manager()`, `detect_dev_command()`, `run_phase_0()` all root-only. CRE has no root `package.json`. Phase 0 fails at build step and dev command detection. |
| B2 | No `--phase` CLI flag | Medium | Cannot run Phase 0 alone. Pipeline runs all phases sequentially. `--resume` skips completed phases but can't select individual phases. |
| B4 | Playwright browser binaries unknown | Low | Global CLI at `/opt/node22/bin/playwright`. Browser binaries may need `npx playwright install chromium`. |

### Playwright Validation Gaps (rated DEGRADED — partial but useful)

The Playwright approach is agent-mediated functional checks with natural-language instructions. No specific Playwright API guidance, no visual regression, no explicit waits, no console monitoring during tests. Screenshots only on failure. 3x retry for transient failures (missing from Phase 5 re-validation).

**Adequately covered for CRE**: Route existence, basic navigation, form happy paths, data display, auth flow (~60-70% of failure modes).

**Not adequately covered**: Search/filter multi-step interactions, sort/pagination verification, export functionality, loading states, visual correctness, error states (~30-40%).

### Cheap Playwright Improvements (include in Round 1)

1. Phase 5 retry policy parity — missing from re-validation prompt, present in Phase 3
2. `page.waitForLoadState('networkidle')` instruction — one line, critical for API-backed tables
3. Explicit multi-step interaction patterns — paragraph about dropdowns, filters, async data

### Heavier Improvements (defer to Round 4 if gaps materialize)

- Visual regression via `toHaveScreenshot()` baseline comparison
- Console error monitoring via `page.on('console')` during test execution
- Screenshot-on-every-assertion (audit trail for passing tests)
- `expect(locator).toBeVisible()` / `toHaveText()` standardization
- `page.waitForResponse()` for API-dependent assertions

---

## 3. Implementation Rounds

### Round 1: Pipeline fixes + Playwright prompt improvements

**Scope**: Fix the blockers that prevent running auto-QA against CRE. Include cheap Playwright improvements that don't change architecture.

- **`--phase` CLI flag**: Add `--phase` argument to `_parse_args()`. When provided, `pipeline.run()` executes only that phase. Supports single phase (e.g., `--phase 0`) or range. Small change to argparse + conditional in run().
- **Monorepo/split-project support in Phase 0**:
  - `detect_package_manager()`: search subdirectories if no root lockfile found
  - `detect_dev_command()`: search subdirectories if no root `package.json`
  - `run_phase_0()`: support building and starting multiple sub-projects (client + server). Detect which subdirs have `package.json`, build each, start dev servers, health check against the correct ports.
- **Phase 5 retry policy**: Add the 3x retry instruction from Phase 3's `build_playwright_prompt()` to `build_revalidation_prompt()`.
- **Playwright prompt: networkidle**: Add instruction to use `page.waitForLoadState('networkidle')` before asserting on data-dependent UI.
- **Playwright prompt: multi-step interactions**: Add paragraph instructing agent on dropdown, filter, pagination, and async data patterns.
- Tests for all changes.
- **Touches**: `post_campaign_validation.py`, `tests/test_post_campaign_validation.py`
- **Estimated tokens**: ~20-25k active (large file, many functions to modify). May need sub-round split.

### Round 2: Run Phase 0 against CRE in isolation

- Set `PROJECT_DIR=~/cre-lease-tracker`
- Run `python -m auto_sdd.scripts.post_campaign_validation --phase 0`
- Verify: package manager detection, client build, server build, dev server start, health check
- Document findings — what works, what breaks, what needs env setup (database, .env files, Playwright browsers)
- **This is a manual run, not an agent prompt.** Brian executes and reports.

### Round 3: Full pipeline run + results collection

- Fix whatever Round 2 surfaces
- Ensure Playwright browsers installed (`npx playwright install chromium`)
- Ensure CRE server env configured (database, .env)
- Run full pipeline: `PROJECT_DIR=~/cre-lease-tracker python -m auto_sdd.scripts.post_campaign_validation`
- Collect: Phase 1 discovery inventory, Phase 2 acceptance criteria, Phase 3 validation results, Phase 4 failure catalog + RCA, Phase 5 fix attempts
- **This produces the first real auto-QA dataset.** Results inform CIS design refinements.

### Round 4: Playwright hardening (if gaps materialize from Round 3)

- Only if Round 3 results show missed failures that the heavier improvements would catch
- Visual regression via `toHaveScreenshot()`
- Console error monitoring during test execution
- Screenshot-on-every-assertion
- Explicit Playwright API assertions (`toBeVisible`, `toHaveText`, `toHaveCount`)
- `page.waitForResponse()` for API-dependent assertions
- Scope determined by actual Round 3 failure patterns

---

## 4. Dependencies

```
Round 1 (pipeline fixes)
  └──▶ Round 2 (Phase 0 against CRE — manual)
         └──▶ Round 3 (full pipeline — manual)
                └──▶ Round 4 (Playwright hardening — only if needed)
                       └──▶ CIS implementation (campaign intelligence system)
```

---

## 6. First Full Run Results (2026-03-05)

**Run ID**: `val-20260305-223636`  
**Total**: ~31 minutes, ~$5.61 API cost  
**Artifacts**: `logs/validation/val-20260305-223636/`

### Phase Results

| Phase | Duration | Result |
|-------|----------|--------|
| 0: Bootstrap | 18s | RUNTIME_READY (both ports, health discovery, auth seeded) |
| 1: Discovery | 3.5 min | 8 routes found, $0.72 |
| 2a: AC Writer | 1.5 min | 5 features, 25 criteria, $0.22 |
| 2b: Gap Detection | instant | 25 criteria |
| 3: Playwright | 22 min | 14 pass, 3 fail, 8 blocked, $4.46 (5 agent calls) |
| 4a: Failure Catalog | instant | 25 total |
| 4b: RCA | 20s | 4 root causes, $0.07 |
| 5: Fix Agents | 4 min | 0 fixed, 4 failed, $1.15 (4 agent calls) |

### Root Causes Identified

- **RC-001** (8 BLOCKED): Phase 3 parse error — agent returned prose instead of JSON for "Lease Comp Search and Filtering". Screenshot shows `login-failure.png`. **This is an infrastructure failure, not an app bug.** Phase 5 tried to fix it by modifying `qa-test-phase3.js` (a temp agent file). Pipeline should not dispatch fix agents for infra failures.
- **RC-002** (1 FAIL): Missing 404 catch-all route — unknown routes redirect to /dashboard. Fix agent correctly created NotFound.tsx + modified App.tsx.
- **RC-003** (1 FAIL): Dashboard Recent Activity shows static empty placeholder. Fix agent correctly modified 4 files (server route + client API + types + page).
- **RC-004** (1 FAIL): Register page missing "Manager" role option. Fix agent correctly modified Register.tsx.

### Why All Fix Agents Failed

**Root cause: Phase 5 build gates use root-only `npm run build`** (line 3304-3312). Same pattern that broke Phase 0 before the monorepo fix. CRE has no root build script. Every fix agent did the correct work (modified the right files) but the build gate ran `npm run build` at root, got "Missing script: build", reverted all changes with `git checkout -- .`, and reported "Build gates failed after fix."

The monorepo fix only landed in Phase 0 (`run_phase_0` / `_run_phase_0_monorepo`), not in Phase 5's build gate.

### Fixes Needed

1. **Phase 5 build gates need monorepo support** — same pattern as Phase 0. Build each sub-project, not root.
2. **Distinguish infra vs app failures** — Phase 4b/5 should tag RC entries as `type: infra` vs `type: app` and skip fix agents for infra issues (parse errors, auth failures, agent timeouts).

### Notes on Criteria Count

25 criteria for 3 features (~8 per feature). Phase 2a invented 2 additional "features" (404 handling, dashboard recent activity) from the roadmap's "real error handling" requirement. For a 28-feature project, expect 200+ criteria. The count is reasonable for this project's scope.

---

## 7. Open Questions

1. **CRE server database**: Does the server need a running database? SQLite file? Postgres? Need to check `server/` for DB config before Round 2.
2. **CRE auth bootstrap**: Phase 0 looks for a seed script for auth. Does CRE have one, or does it need manual account creation?
3. **Monorepo strategy**: Should Phase 0 auto-detect sub-projects, or require explicit config (e.g., `PROJECT_DIRS=client,server` env var)? Auto-detect is more generalizable but harder to get right.
4. **Round 1 sizing**: `post_campaign_validation.py` is ~3200 lines. Modifying Phase 0 + argparse + two prompt functions + tests may exceed single-prompt context budget. May need sub-round split.
