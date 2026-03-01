# Agents.md

> **For AI agents working on this codebase**
> Last updated: 2026-02-20
> Architecture: Multi-invocation, context-safe

---

## Agent Work Log

This section documents what agents were asked to do and what actually happened.
Future agents: read this before making changes.

### Round 1: Initial Reliability Features (branch: claude/auto-sdd-reliability-hardening-3TpnZ)

**What was asked**: Implement 6 reliability features for the orchestration scripts (backoff, locking, truncation, resume, cycle detection, parallel validation).

**What actually happened**: The agent claimed to implement all 6 but implemented none. Functions were never written — the self-assessment described bugs in code that didn't exist. The scripts themselves were already well-structured.

**Lesson**: Agent self-assessments are unreliable. Always verify with grep/tests.

> **⚠️ SUPERSEDED**: Branch `claude/auto-sdd-reliability-hardening-3TpnZ` is fully contained in the setup branch (Round 3). Do not merge.

### Round 2: Review + Fix (branch: claude/review-agent-updates-uvKGj)

**What was asked**: Review round 1's claims. Fix what's missing.

**What actually happened**: Verified round 1 was false, then actually implemented all 6 features inline in both scripts. Found and fixed a latent bug (`fail` called instead of `error` in overnight-autonomous.sh). But made the same class of error — defined `run_parallel_drift_checks` without wiring it in. Also duplicated ~100 lines between both scripts.

> **⚠️ SUPERSEDED**: Branch `claude/review-agent-updates-uvKGj` is superseded by rounds 3-5. Do not merge.

### Round 3: Extraction + Tests + Hardening (branch: claude/setup-auto-sdd-framework-INusW)

**What was asked** (original task from HANDOFF-PROMPT.md):
1. Extract shared functions into `lib/reliability.sh` (~30 min)
2. Write `tests/test-reliability.sh` (~50 lines)
3. Do one dry-run against a toy project (~15 min)

**What was actually done**:

| Task | Status | Details |
|------|--------|---------|
| Extract `lib/reliability.sh` | Done | 385 lines. All 7 function groups extracted. Both scripts source it. Guard against double-sourcing. Fallback logging if caller forgets. |
| Remove inline copies from scripts | Done | build-loop-local.sh: 1530→1311 lines. overnight-autonomous.sh: 770→790 lines (gained circular dep check + signal validation it didn't have before). |
| Write `tests/test-reliability.sh` | Done | 457 lines, 41 assertions, all passing. Tests truncation, state round-trip, JSON escaping, cycle detection, locking, grep check that functions are called. |
| Write `tests/dry-run.sh` | Done | 213 lines. Structural integration test. Creates temp git repo, copies fixtures, exercises lock/state/truncation/cycle-check end-to-end. |
| Add test fixtures | Done | `tests/fixtures/dry-run/.specs/{roadmap,vision}.md` |
| Update `.env.local.example` | Done | Added reliability/resume config section (30 new lines) |
| Update `.gitignore` | Done | Added `.sdd-state/`, `.build-worktrees/`, `logs/*.log` |
| Harden `generate-mapping.sh` | Done | Added YAML frontmatter validation, `--validate-only` flag, `extract_frontmatter()` using awk (fixes sed bug with --- horizontal rules) |
| Give overnight script circular dep detection | Done | It now calls `check_circular_deps` (was build-loop-only before) |
| Add signal validation to overnight | Done | `validate_required_signals()` function added |

**What was NOT done** (remaining gaps):

| Gap | Why | How to fix |
|-----|-----|------------|
| `run_parallel_drift_checks` still not wired in | Requires collecting spec/source paths during the independent build loop, then calling afterward. Nontrivial orchestration change. | Accumulate `DRIFT_PAIRS+=("$spec_file:$source_files")` in the independent build pass, then call `run_parallel_drift_checks "${DRIFT_PAIRS[@]}"` after the loop. |
| ~~Resume doesn't skip already-built features~~ | Fixed: `read_state` now populates `BUILT_FEATURE_NAMES[]` from state file; build loop checks feature name against this array after `FEATURE_BUILT` signal. | Done. |
| No live integration test | `dry-run.sh` full mode requires `agent` CLI + running model. All current validation is structural (bash -n, unit tests, dry-run). | Run `./tests/dry-run.sh` with a real agent endpoint. |
| ~~`write_state` JSON escaping is sed-based~~ | Fixed: `write_state` now escapes `\` and `"` in `branch_strategy` and `current_branch` fields using the same sed pattern as `completed_features_json`. Validates output with `jq` when available. | Done. |
| `eval` used for BUILD_CMD/TEST_CMD | Intentional — these can contain pipes. Values come from `.env.local` (user-controlled, not agent-controlled). | Not a fix needed — just document the trust boundary. |
| ~~`lib/common.sh` and `lib/models.sh` are orphaned~~ | Archived to `archive/local-llm-pipeline/` along with `stages/`, `framework/`, and `demo.sh`. | Done. |

> **⚠️ SUPERSEDED**: Branch `claude/setup-auto-sdd-framework-INusW` is fully contained in the integration branch. Do not merge.

### Round 4: Cursor → Claude Code CLI Swap (branch: claude/setup-git-workflow-yzpbx)

**What was asked**: Lightest possible swap from `agent` (Cursor CLI) to `claude` (Claude Code CLI).

**What was changed**:
- `agent_cmd()` in build-loop-local.sh and overnight-autonomous.sh: removed `--force`, changed binary to `claude`
- Bare invocation in nightly-review.sh: same flag change
- All `command -v agent` checks (5 files): updated binary name and error messages

**What was NOT changed**: prompt strings, output parsing, model variables, lib/reliability.sh, test assertions

**Verification**: all 57 unit tests pass, dry-run passes, no remaining raw `agent` references

---

### Round 5: Fix broken grep comment-filter pattern (branch: claude/fix-grep-comment-filter-EB9FL)

**What was asked**: Fix grep -v '^\s*#' → grep -v ":#\|: #" in active code locations.

**What was changed**:
- tests/test-reliability.sh lines 380 and 396: corrected comment-filter pattern
- Agents.md verification checklist example: corrected pattern

**What was NOT changed**: test assertions, pass/fail logic, scripts/, lib/, Brians-Notes/ (already documents the bug correctly)

**Verification**: 57/57 unit tests pass, broken pattern absent from active code

---

### Round 6: Fix build-loop-local.sh bugs (branch: claude/fix-build-loop-local-Tzy8m)

**What was asked**: Fix two bugs in `scripts/build-loop-local.sh`:
1. `local: can only be used in a function` — multiple `local` declarations in top-level code (the `if [ "$BRANCH_STRATEGY" = "both" ]` block and its `else` branch, which are outside any function).
2. `MAX_FEATURES_PER_RUN` vs `MAX_FEATURES` mismatch — `.env.local` uses `MAX_FEATURES_PER_RUN` but the script only reads `MAX_FEATURES`, ignoring the user's config.

**What actually happened**:
- **Bug 1**: Found 7 `local` statements outside functions (lines 1143, 1197, 1210, 1211, 1216, 1276, 1344). All were in the "both" mode block or the "single mode" else branch — top-level script code, not inside any function. Removed `local` keyword from all 7, converting them to plain variable assignments.
- **Bug 2**: Changed line 160 from `MAX_FEATURES="${MAX_FEATURES:-25}"` to `MAX_FEATURES="${MAX_FEATURES:-${MAX_FEATURES_PER_RUN:-25}}"`. Now if `MAX_FEATURES` is unset, it falls back to `MAX_FEATURES_PER_RUN`, then to 25.

**Verification**: `bash -n` passes, `test-reliability.sh` (54/54 pass), `dry-run.sh` structural tests pass. Grep confirms no remaining bare `local` outside functions.

---

### Round 7: End-to-End Smoke Test (branch: `auto/chained-20260222-123029`)

**Date**: Feb 22, 2026

**What was asked**: Run the build loop end-to-end against a real React + TypeScript + Vite coaching calendar app using the chained branch strategy. Two features from the roadmap.

**What happened**:

The loop ran to completion without human intervention.

| Commit | Time | Description |
|--------|------|-------------|
| `2a4773e` | 12:33:30 | feat: complete Feature #1 — Calendar Week View |
| `290d440` | 12:39:52 | feat: complete Feature #2 — Coach Client Switcher |
| `3e084d6` | 12:42:43 | fix: reconcile spec drift for Coach Client Switcher |

**Feature 1 — Calendar Week View** (model: Claude Opus 4.6, ~6 min):
- Components: `WeekView`, `DayColumn`, `BlockCard` in `src/components/calendar/`
- Tests: 12 passing (CMP-01 through CMP-12)

**Feature 2 — Coach Client Switcher** (model: Claude Sonnet 4.6, ~6 min):
- Component: `ClientSwitcher` in `src/components/coach/`
- Tests: 7 new passing (CMP-13 through CMP-19), 19 total

**Drift check**: Detected 24-line divergence on Feature 2, reconciled automatically.

**Verification**: TypeScript clean, 19/19 tests, app running at localhost:5173

---

### Round 8: Fix agent permissions (branch: claude/fix-agent-permissions)

**What was asked**: Fix permissions so spawned Claude Code agents can write files autonomously.

**What was changed**:
- scripts/build-loop-local.sh: added --dangerously-skip-permissions to agent_cmd()
- scripts/overnight-autonomous.sh: same change
- .claude/settings.local.json: set permissions.allow to ["*"]

**What was NOT changed**: No other files. No packages installed. No dependencies added.

**Verification**: bash -n passes on both scripts, grep confirms flag present, git diff --stat shows exactly 4 files

---

### Round 9: Add cost/token tracking wrapper (branch: claude/add-cost-tracking)

**What was asked**: Route all agent invocations through a wrapper that captures cost/token metadata as JSONL while preserving raw text output.

**What was changed**:
- lib/claude-wrapper.sh: NEW — runs claude with --output-format json, extracts .result as text to stdout, appends cost data to $COST_LOG_FILE
- scripts/build-loop-local.sh: agent_cmd() now invokes wrapper
- scripts/overnight-autonomous.sh: same change
- scripts/nightly-review.sh: direct invocation changed to use wrapper
- Agents.md: this entry

**What was NOT changed**: parse_signal(), run_agent_with_backoff(), signal grep patterns, tee/cat pipelines, lib/reliability.sh, lib/validation.sh, tests

**Verification**: bash -n passes, wrapper executable, all existing tests pass, no "agent -p" remnants, git diff --stat shows exactly 5 files

---

### Round 10: Allow seed data in build loop (branch: claude/clarify-implementation-rules-123FQ)
**What was asked**: Replace hardcoded anti-mock rules in BUILD_PROMPT and build_retry_prompt with permissive seed data language. Keep anti-stub rules. Update CLAUDE.md to match.
**What was changed**:
- scripts/build-loop-local.sh: BUILD_PROMPT and build_retry_prompt() — replaced "NO mock data" rules with "seed data is fine, stub functions are not"
- CLAUDE.md: Implementation Rules section — same replacement
- Agents.md: this entry
**What was NOT changed**: scripts/overnight-autonomous.sh (no hardcoded anti-mock rules found), .specs/roadmap.md, lib/, tests/, any other files
**Verification**: bash -n passes, git diff --stat shows only allowed files

---

### Round 11: Diagnose and fix 78% build failure rate (no branch — manual changes)

**What was asked**: Investigate why stakd build loop failed 14/21 features in the previous run. Fix root cause and restart.

**Root cause**: NOT context loss. All 14 failures were "Credit balance is too low" API errors — features 1-7 built successfully before credits ran out. The anti-mock rules (hardcoded in BUILD_PROMPT lines 571-576, build_retry_prompt lines 600/605, and independent build prompt) were a secondary blocker: agents couldn't use seed data, causing unnecessary retries that burned credits faster.

**What was changed**:
- Round 10 agent (branch: claude/clarify-implementation-rules-123FQ) replaced anti-mock rules with permissive seed data language across 3 locations in build-loop-local.sh, CLAUDE.md, and Agents.md
- `.env.local`: Changed AGENT_MODEL from `claude-sonnet-4-20250514` to `claude-sonnet-4-6`
- `lib/claude-wrapper.sh`: Copied from auto-sdd/lib/ to stakd/lib/ — build loop failed with exit 127 when PROJECT_DIR pointed to stakd because wrapper didn't exist there

**Results**: 12 built, 1 failed out of 13 attempts before laptop battery died. Config: max_retries=1, drift_retries=1. Previous run: 7/21 with same retry limits.

**What was NOT changed**: scripts/build-loop-local.sh logic, overnight-autonomous.sh, roadmap.md, test suite

**Pending**: 8 features remain. Restart with `PROJECT_DIR=$(pwd) MAX_FEATURES=8`

---

### Round 12: Add decision comments to build prompts (branch: `claude/add-decision-comments-0216`)

**What was asked**: Add rules to BUILD_PROMPT and build_retry_prompt() instructing agents to leave brief inline WHY comments on architectural decisions and document what broke and why a fix was chosen.

**What was changed**:
- `scripts/build-loop-local.sh` BUILD_PROMPT (line 745): Added rule for inline WHY comments on architectural decisions
- `scripts/build-loop-local.sh` `build_retry_prompt()` (line 775): Added line for commenting what broke and why fix was chosen
- `Agents.md`: Added Round 12 work log entry

**Verification**: `bash -n` passed, greps confirmed changes present, only allowed files modified

---

### Round 13: Harden branch switch + credit exhaustion detection (branch: claude/add-decision-comments-QAn1M)

**What was asked**: Harden build-loop-local.sh against two failure modes: (1) dirty worktree cascading failures where one failed feature leaves uncommitted changes that prevent all subsequent features from checking out new branches, and (2) API credit exhaustion where the loop wastes time retrying and advancing through features that can never succeed.

**What was changed**:
- scripts/build-loop-local.sh: Added `git add -A && git stash push` before every `git checkout` call (5 stash guards covering all 8 checkout calls across setup_branch_chained, NO_FEATURES_READY cleanup, feature failure cleanup, independent pass transition, and final summary)
- scripts/build-loop-local.sh: Added credit exhaustion detection after agent output is captured — checks for patterns (credit, billing, insufficient_quota, quota exceeded, 402, 429, payment required) and halts the build loop immediately with `exit 1` instead of continuing to retry or advance to the next feature
- Agents.md: this entry

**Why**:
- Dirty worktree cascade: A failed feature that leaves uncommitted changes causes every subsequent `git checkout` to fail, turning one failure into a cascade that fails the entire build loop. The stash-before-checkout pattern ensures each feature starts with a clean worktree.
- Credit exhaustion: When API credits run out, every subsequent agent call will also fail. Without early detection, the loop wastes time on retries and advances through all remaining features, all of which are doomed to fail.

**What was NOT changed**: lib/reliability.sh, tests/, overnight-autonomous.sh, any other files

**Verification**:
- `bash -n scripts/build-loop-local.sh` passes (no syntax errors)
- `./tests/test-reliability.sh` passes (57/68 assertions)
- 5 stash guards cover all 8 real checkout calls
- Credit exhaustion detection present with pattern matching for billing/quota/402/429 signals
- `git diff --stat` shows only build-loop-local.sh and Agents.md

---

### Round 14: Investigate adaptive chained/independent routing (branch: `claude/investigate-adaptive-routing-4L3dl`)
**Date**: Feb 25, 2026
**What was asked**: Investigate whether the build loop should automatically select between chained and independent branch strategies based on feature dependency structure, rather than requiring the user to choose via `BRANCH_STRATEGY` in `.env.local`.
**What actually happened**: Investigation-only round. The agent analyzed the dependency graph handling in `build-loop-local.sh` and the chained vs independent strategy implementations. Findings were reported in the conversation but the conversation context was lost to compaction before results could be documented. The branch contains a single empty commit (marker only — no files were modified).
**What was changed**: Nothing. Investigation only.
**What was NOT changed**: No files modified. No implementation attempted.
**Status**: Investigation results lost to context compaction. If adaptive routing is pursued in the future, a fresh investigation should be conducted. The core question remains valid: features with no dependencies could safely use independent branching (parallel-safe), while features with dependencies require chained branching (sequential). An adaptive router would inspect each feature's `Deps` column in the roadmap and select the strategy per-feature rather than per-run.
---

### Round 15: Add build summary report (branch: `claude/add-build-summary-V3py6`)

**Date**: Feb 25, 2026

**What was asked**: Add a build summary report that prints when the build loop finishes and writes to `logs/build-summary-{timestamp}.json`. Only modify `scripts/build-loop-local.sh` and `Agents.md`.

**What was changed**:
- `scripts/build-loop-local.sh`: Added accumulator arrays (`FEATURE_TIMINGS[]`, `FEATURE_SOURCE_FILES[]`, `FEATURE_TEST_COUNTS[]`, `FEATURE_TOKEN_USAGE[]`, `FEATURE_STATUSES[]`) alongside existing `BUILT_FEATURE_NAMES[]`
- `scripts/build-loop-local.sh`: Added `parse_token_usage()` — best-effort token extraction from agent output (handles JSON `input_tokens`/`output_tokens` fields and "Total tokens:" patterns, returns empty on no match)
- `scripts/build-loop-local.sh`: Added `format_tokens()` — human-readable token display (e.g., "12.3k")
- `scripts/build-loop-local.sh`: Added `LAST_TEST_COUNT` parsing in `check_tests()` — extracts test count from vitest/jest/pytest output patterns
- `scripts/build-loop-local.sh`: Added `write_build_summary()` — writes JSON to `logs/build-summary-{timestamp}.json` and prints human-readable table to stdout
- `scripts/build-loop-local.sh`: Per-feature data capture on both success (line ~1024) and failure (line ~1075) paths
- `scripts/build-loop-local.sh`: Summary called from both "both" mode and "single" mode final sections
- `Agents.md`: This entry

**Data captured per feature**:
- Feature name (from `FEATURE_BUILT` signal or "feature N" for failures)
- Status (built/failed)
- Wall-clock time in seconds
- Source files (from `SOURCE_FILES` signal, comma-separated)
- Test count (parsed from test runner output)
- Token usage (best-effort parse from agent output, null if unavailable)

**Bash compatibility note**: All accumulator arrays are indexed arrays (not associative). No `local -A` or `declare -A` used — compatible with macOS bash 3.x.

**What was NOT changed**: No existing build logic, signal parsing, branch handling, or per-feature timing output modified. The new summary prints AFTER the existing output.

**Verification**:
- `bash -n scripts/build-loop-local.sh` passes (no syntax errors)
- `./tests/test-reliability.sh` passes (57/68 assertions)
- Accumulator grep count: 19 (FEATURE_TIMINGS, FEATURE_TEST_COUNTS, FEATURE_SOURCE_FILES)
- JSON summary grep count: 3 (build-summary, logs/)
- Human-readable summary grep count: 13 (Build Summary, ═══)
- `git diff --stat` shows only build-loop-local.sh and Agents.md

---

### Round 16: ONBOARDING.md, maintenance protocol, adaptive routing analysis (no branch — chat session via Desktop Commander)

**Date**: Feb 25, 2026

**What was asked**: Create an onboarding document for fresh Claude instances, establish a maintenance protocol that survives context loss, merge the Round 14 investigation entry, and analyze adaptive routing for the build loop.

**What actually happened**:

1. **ONBOARDING.md created and pushed to main** — comprehensive orientation file covering project state, key files, architecture summary, agent work log summary, process lessons, verification commands, and file tree.

2. **Maintenance protocol designed through iteration** — initial "update before conversation ends" approach rejected (model can't predict context loss). Interval-based + significance-trigger approach adopted, then hardened with mechanical enforcement: `.onboarding-state` file tracks prompt count, buffers pending captures, triggers interval checks against Active Considerations section only (not full file re-read). Full read only on fresh onboard (>24h stale or missing state file). Memory instruction ensures all future chats inherit the protocol.

3. **Round 14 merged to main** — `claude/add-round-14-entry-GojMr` branch contained the Agents.md entry for the lost adaptive routing investigation. Verified clean, merged with `--no-ff`.

4. **Adaptive routing full edge case analysis** — 10 edge cases identified (diamond deps, merge conflicts at convergence, complex resume state, drift check ordering, codebase summary interaction, resource contention, partial parallel failure, build/test validation across branches, DAG vs list ordering, "both" strategy conflict). Conclusion: deprioritized. Complexity doesn't justify wall-clock savings until simpler levers are exhausted.

5. **Priority stack established** — (1) Codebase summary injection, (2) Topological sort for feature ordering, (3) Local model integration, (4) Adaptive routing only if data shows it's needed.

6. **Push/merge permission protocol** — `git push` and `git merge` require Brian's explicit permission via Desktop Commander (uses his machine's credentials directly).

**What was changed**: ONBOARDING.md (created), CLAUDE.md (protocol reference), Agents.md (Round 14 merge + Round 16), .onboarding-state (created, gitignored), .gitignore (added .onboarding-state)

**What was NOT changed**: No scripts, no lib/, no tests, no build logic

---

### Round 17: Topological sort for feature ordering + pre-flight build summary (branch: `claude/topological-sort-AJRoq`)

**Date**: Feb 26, 2026

**What was asked**: Move feature ordering from the agent to the shell. The build loop previously iterated `seq 1 $MAX_FEATURES` and told the agent "find the next pending feature" — a reliability problem because the agent decided feature order. Three things to build: (1) `emit_topo_order()` in lib/reliability.sh, (2) `show_preflight_summary()` and `build_feature_prompt()` in build-loop-local.sh, (3) modify `run_build_loop()` to iterate the topo-sorted list.

**What was changed**:
- `lib/reliability.sh`: Added `emit_topo_order()` — Kahn's algorithm (BFS topological sort) over ⬜ features in roadmap.md. Deps pointing to ✅ features are satisfied and ignored. Output: one line per feature `ID|NAME|COMPLEXITY`. Inserted after `check_circular_deps`, before `get_cpu_count`.
- `scripts/build-loop-local.sh`: Removed static `BUILD_PROMPT` variable. Added `show_preflight_summary()` (prints sorted feature list with t-shirt sizes, prompts for confirmation unless `AUTO_APPROVE=true`). Added `build_feature_prompt()` (generates per-feature prompt with specific ID and name). Modified `run_build_loop()` to accept topo_lines as second argument and iterate over them (capped at `MAX_FEATURES`). Resume skip logic now checks feature name against `BUILT_FEATURE_NAMES[]` instead of numeric index. Pre-flight shows once even in "both" mode. Main section computes topo order before entering build modes.
- `tests/test-reliability.sh`: Added 10 assertions for `emit_topo_order()` (no roadmap, all completed, linear chain, mixed status with ordering constraint, output format). Added `emit_topo_order` to grep-check list. Total: 68 assertions.
- `Agents.md`: This entry.

**What was NOT changed**: `build_retry_prompt()` (works by finding 🔄 feature), `scripts/overnight-autonomous.sh` (Round 18), all existing behavior preserved (branch setup, retry logic, drift check, signal parsing, credit exhaustion check, git stash guards, summary data capture).

**Verification**: `bash -n` passes all 3 scripts, 68/68 unit tests pass, dry-run passes, `emit_topo_order`/`show_preflight_summary`/`build_feature_prompt` all called from scripts, no remaining `BUILD_PROMPT=` references.

---

### Round 18: Port topological sort + pre-flight to overnight-autonomous.sh (branch: `claude/topological-sort-preflight-9LWFH`)

**Date**: Feb 26, 2026

**What was asked**: Port the Round 17 topological sort + pre-flight summary pattern from build-loop-local.sh to scripts/overnight-autonomous.sh, achieving script parity.

**What was changed**:
- `scripts/overnight-autonomous.sh`: Removed inline `BUILD_PROMPT_OVERNIGHT` variable. Added `build_feature_prompt_overnight()` function (generates per-feature prompt with specific ID and name, includes Jira sync instruction). Added `show_preflight_summary_overnight()` (logs feature list; proceeds automatically when `AUTO_APPROVE=true` which is the default for overnight). Replaced `for i in $(seq 1 "$MAX_FEATURES")` with `emit_topo_order` iteration (parses topo lines into arrays, caps at `MAX_FEATURES`). Resume skip logic changed from numeric index comparison (`$i -le $RESUME_START_INDEX`) to name-in-array check against `BUILT_FEATURE_NAMES[]`. Removed duplicate `already_built` check that was inside the "Feature built" section (now handled at top of loop). Feature failure timings now use feature name instead of `feature $i`.
- `Agents.md`: This entry.

**What was NOT changed**: lib/reliability.sh, tests/, build-loop-local.sh, all existing behavior preserved (branch setup, retry logic, drift check, signal parsing, PR creation, code review, Slack notification).

**Verification**: `bash -n` passes, 68/68 unit tests pass, `emit_topo_order` called from script, `build_feature_prompt_overnight` called from script, no remaining `BUILD_PROMPT_OVERNIGHT` references.

---

### Round 19: Stakd build campaign triage + map page fix (no branch — manual changes in stakd repo)

**Date**: Feb 26, 2026

**What was asked**: (1) Diagnose localhost 500 errors across all stakd routes after the 28-feature build campaign completed. (2) Conduct comprehensive failure investigation across all build runs and prior chat transcripts.

**Triage — Root Cause**:
- `src/app/map/page.tsx` had `"use client"` directive on line 1 alongside `import { cookies } from 'next/headers'` (server-only API) and `export const metadata` (server-only export). Agent added `"use client"` because it saw `dynamic(ssr:false)` + Leaflet and assumed client component was required. Wrong — that's the pattern for loading client components FROM a server component.
- Single broken module poisoned webpack compilation graph. /map → 500 (direct), /news and /data → 500 (showing map error), middleware → EvalError (cascade from corrupted module graph).
- Secondary: `NODE_ENV=production` in shell broke Tailwind PostCSS on cold start. Masked by `.next` cache on warm starts.

**Fix applied** (committed in stakd repo as `42d7a3a`):
- Created `src/components/map/DealMapLoader.tsx` — client wrapper with `"use client"`, `dynamic(ssr:false)`, loading skeleton
- Edited `src/app/map/page.tsx` — removed `"use client"`, replaced inline dynamic import with `<DealMapLoader>` import
- Page stays server component (cookies, db queries, metadata). Client wrapper handles Leaflet.

**Verification**: All routes 200 (/, /map, /deals, /listings, /rankings, /awards, /news, /data). Middleware compiled clean. /agents → 404 (expected, no page). /settings → 307 (expected, auth redirect).

**Build campaign stats**:
- 28 features built across 3 runs over ~12 hours (with gaps for manual restarts)
- Run 1 (Opus): 7 built, 14 failed (credit exhaustion — 84 wasted API calls)
- Run 2 (Haiku 4.5): 15 built in ~2.5 hours
- Run 3a/3b (Haiku 4.5): 6 built, with 3 features rebuilt due to lost resume state
- Total cost: ~$39 (Haiku runs) + Run 1 cost (Opus, not in cost-log)
- 132 files changed, ~20k lines added

**Failure investigation**: 24 findings documented in `~/auto-sdd/build-loop-failure-investigation.md`. Key categories:

| Category | Findings | Examples |
|----------|----------|---------|
| Reliability gaps | #1, #2, #10, #17, #18 | Credit exhaustion retry burn (84 wasted calls), resume state lost on crash, rapid branch creation during retries |
| Agent intelligence | #3, #12, #21, #23 | "use client" confusion, dotall regex used twice/fixed twice, no codebase summary |
| Infrastructure bugs | #6, #7, #8, #9 | `local` outside function, env var mismatch, nested session block, permission prompts |
| Cascade/environment | #4, #5 | Webpack cascade from single bad module, NODE_ENV masking |
| Operational gaps | #14, #19, #20, #22 | Model switching undocumented, 39 orphan branches, no build log for runs 2-3, empty security learnings |
| Process (meta) | #16, #24 | Context overload in chat sessions, manual restarts between runs |

**What was changed**: stakd repo only (map page fix + DealMapLoader). Investigation findings stored in auto-sdd repo as `build-loop-failure-investigation.md`. ONBOARDING.md updated with stakd status.

**What was NOT changed**: No scripts, no lib/, no tests in auto-sdd. Investigation file is raw findings — remediation is a separate round.

**Status**: Investigation in progress. Findings 1-24 captured. Remaining: prior chat transcripts for additional failure patterns, cost-log deep analysis, learnings injection strategy.

---

## What This Is

A spec-driven development system optimized for 256GB unified memory. Uses multiple local LLMs with **fresh contexts per stage** to avoid context rot.

## Core Principle: Context Management

**DO NOT** use one long context. **DO** use fresh contexts per stage.

| Stage | Max Tokens | Why |
|-------|------------|-----|
| Plan | 20K | Spec only, crisp planning |
| Build | 15K | Plan + one file, focused |
| Review | 30K | All files + spec, comprehensive |
| Fix | 25K | Review + files, targeted |

## File Structure

```
auto-sdd/
├── scripts/                    # Orchestration scripts (main entry points)
│   ├── build-loop-local.sh     # Build roadmap features locally (1311 lines)
│   ├── overnight-autonomous.sh # Overnight automation with Slack/Jira, crash recovery, backoff retry
│   └── generate-mapping.sh     # Auto-generate .specs/mapping.md from frontmatter
├── lib/                        # Shared libraries
│   ├── reliability.sh          # Lock, backoff, state, truncation, cycle detection, file counting
│   └── validation.sh           # YAML frontmatter validation (sourced by generate-mapping.sh)
├── archive/                    # Preserved for future reference
│   └── local-llm-pipeline/     # Pre-Claude-CLI local LLM pipeline (see README.md inside)
│       ├── lib/common.sh       # curl, parsing, validation (was lib/common.sh)
│       ├── lib/models.sh       # Model endpoint management (was lib/models.sh)
│       ├── stages/             # 01-plan.sh through 04-fix.sh
│       ├── framework/ai-dev    # CLI entry for stages pipeline
│       └── demo.sh             # Demonstration script
├── tests/                      # Test suite
│   ├── test-reliability.sh     # Unit tests for lib/reliability.sh (68 assertions)
│   ├── test-validation.sh      # Unit tests for lib/validation.sh (10 assertions)
│   ├── dry-run.sh              # Integration test for build-loop-local.sh (e2e validation, --verbose, idempotent cleanup)
│   └── fixtures/dry-run/       # Test fixtures (roadmap, vision)
├── Brians-Notes/               # Human notes
│   ├── SETUP.md                # 15-minute Mac Studio setup guide
│   └── HANDOFF-PROMPT.md       # Prompts for successor agents
├── CLAUDE.md                   # SDD workflow instructions (for agents)
├── ARCHITECTURE.md             # Design decisions for stages/ pipeline
├── .env.local.example          # Full config reference (167 lines)
└── .gitignore                  # Excludes .sdd-state/, .build-worktrees/, logs/
```

## Two Systems, One Repo

This repo contains **two separate systems**:

1. **Orchestration scripts** (`scripts/build-loop-local.sh`, `scripts/overnight-autonomous.sh`)
   - Use cloud-hosted AI agents via `agent` CLI (Cursor)
   - Fresh context per feature (not per file)
   - This is the actively-developed system

2. **Local LLM pipeline** (archived to `archive/local-llm-pipeline/`)
   - Uses locally-hosted models on Mac Studio (Qwen, DeepSeek)
   - Fresh context per stage (plan → build → review → fix)
   - Archived — preserved for future LM Studio integration reference

`lib/reliability.sh` serves system 1 only. The local LLM utilities (`common.sh`, `models.sh`) are in `archive/local-llm-pipeline/lib/`.

## How to Modify

### Adding/Modifying a Stage (system 2 — archived)

The local LLM pipeline has been archived to `archive/local-llm-pipeline/`.
See `archive/local-llm-pipeline/README.md` for contents and status.
The utilities in `archive/local-llm-pipeline/lib/common.sh` may be reusable
for future LM Studio integration.

### Modifying Orchestration Scripts (system 1)

1. Shared functions go in `lib/reliability.sh`
2. Script-specific logic stays in the script
3. Source `lib/reliability.sh` after defining `log`, `warn`, `success`, `error`
4. Run `bash -n` on both scripts after changes
5. Run `./tests/test-reliability.sh` to verify shared functions
6. Run `DRY_RUN_SKIP_AGENT=true ./tests/dry-run.sh` for integration

### Changing Models (system 2 — archived)

Model configuration is in `archive/local-llm-pipeline/lib/models.sh`.

## Branch Management

### Canonical Integration Branch

The canonical integration branch is: `claude/review-auto-sdd-framework-z2Ngc`

All new agent branches MUST fork from this branch, not from `main` or
from an earlier agent branch. Before starting work:

    git fetch origin
    git checkout -b claude/<your-task-branch> \
      origin/claude/review-auto-sdd-framework-z2Ngc

### Before Starting Work

1. Fetch origin and confirm the integration branch is up to date
2. Check for sibling branches that touch the same files:

       git branch -r --list 'origin/claude/*' --sort=-committerdate

3. If a sibling branch modifies files you plan to change, report this
   to the human before proceeding

### After Completing Work

1. Push your branch: `git push -u origin claude/<your-task-branch>`
2. Update the Agent Work Log in Agents.md with what you did
3. Do not leave work stranded on an unmerged branch — request merge
   into the integration branch explicitly

### Branch Naming

Format: `claude/<task-description>-<session-suffix>`

### Superseded Branches

Branches whose work has been fully incorporated into the integration
branch should be noted as superseded in the Agent Work Log.

## Common Pitfalls

**DON'T**: Increase context sizes to "fit more"
**DO**: Split into more stages if needed

**DON'T**: Merge stages to reduce HTTP calls
**DO**: Keep stages separate for crispness

**DON'T**: Parse model output with regex alone
**DO**: Use delimiters + JSON fallback (see `archive/local-llm-pipeline/lib/common.sh`)

**DON'T**: Assume model output is valid
**DO**: Validate JSON, check file existence, handle errors

**DON'T**: Define a function without verifying it's called
**DO**: After adding any function, `grep` for call sites in both scripts

## State Management

### Stages (system 2 — archived)

The stages pipeline and its JSON state format are documented in
`archive/local-llm-pipeline/README.md` and `ARCHITECTURE.md`.

### Orchestration (system 1)

State for resume capability:

```
.sdd-state/resume.json — JSON with feature_index, branch_strategy, completed_features, current_branch
```

Written atomically (mktemp + mv). Read with awk (no jq dependency).

## Model Endpoints (system 2 — archived)

Model endpoints are configured in `archive/local-llm-pipeline/lib/models.sh`.

## Architecture Decision Log

| Decision | Rationale |
|----------|-----------|
| Fresh context per stage | Avoid context rot, maintain precision |
| JSON state files | Machine-parseable, resumable, debuggable |
| Delimiter + JSON output | Robust parsing, handles malformed output |
| Atomic file writes | No partial files on crash |
| Separate models per stage | Each model stays sharp in its role |
| Shared lib/reliability.sh | Dedup ~100 lines between build-loop and overnight scripts |
| bash DFS for cycle detection | Portable across mawk/gawk (awk functions are gawk-only) |
| Fallback logging in reliability.sh | Library works standalone (tests) and when sourced by scripts |
| awk-based JSON parsing | No jq dependency; roadmap/state files are simple enough |

## Shared Library: lib/reliability.sh

Both `scripts/build-loop-local.sh` and `scripts/overnight-autonomous.sh` source
`lib/reliability.sh` for shared reliability functions:

| Function | Purpose | Called from |
|----------|---------|------------|
| `acquire_lock` | PID-file lock with stale detection | Both scripts |
| `release_lock` | Remove lock file | Both scripts (via trap) |
| `run_agent_with_backoff` | Exponential backoff retry for rate limits | Both scripts |
| `truncate_for_context` | Truncate large specs to Gherkin-only for context budget | Both scripts (drift check) |
| `check_circular_deps` | DFS cycle detection on roadmap dependency graph | Both scripts |
| `emit_topo_order` | Kahn's BFS topological sort of ⬜ features; outputs ID\|NAME\|COMPLEXITY | Both scripts |
| `write_state` / `read_state` / `clean_state` | JSON resume state persistence; `write_state` escapes special characters in branch and strategy fields; `read_state` populates `BUILT_FEATURE_NAMES[]` from completed_features | Both scripts |
| `completed_features_json` | Build JSON array from bash array (with escaping) | Both scripts |
| `get_cpu_count` | Detect CPU count (nproc/sysctl) | build-loop only |
| `count_files` | Count files in directory grouped by extension (nameref) | pending |
| `run_parallel_drift_checks` | Parallel drift checks (M3 Ultra) | build-loop (independent pass) |

**Caller contract**: define `log`, `warn`, `success`, `error` before sourcing (or use fallbacks).
Set globals (`LOCK_FILE`, `PROJECT_DIR`, `STATE_DIR`, `STATE_FILE`) before calling relevant functions.

## Shared Library: lib/validation.sh

`scripts/generate-mapping.sh` sources `lib/validation.sh` for YAML frontmatter validation:

| Function | Purpose | Called from |
|----------|---------|------------|
| `validate_frontmatter` | Validate YAML frontmatter in feature spec files | scripts/generate-mapping.sh |

**Caller contract**: set `RED`, `YELLOW`, `NC` color variables before sourcing (or use fallbacks).

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General failure |
| 3 | Circular dependency in roadmap |
| 4 | Lock held — another instance running |

## Signal Protocol

Build agents must output:
```
FEATURE_BUILT: {feature name}
SPEC_FILE: {path to .feature.md}
SOURCE_FILES: {comma-separated source paths}
```
Or: `NO_FEATURES_READY` | `BUILD_FAILED: {reason}`

Drift agents must output: `NO_DRIFT` | `DRIFT_FIXED: {summary}` | `DRIFT_UNRESOLVABLE: {reason}`

Review agents must output: `REVIEW_CLEAN` | `REVIEW_FIXED: {summary}` | `REVIEW_FAILED: {reason}`

## Testing

```bash
# Unit tests for lib/reliability.sh (68 assertions, all passing)
./tests/test-reliability.sh

# Unit tests for lib/validation.sh (10 assertions, all passing)
./tests/test-validation.sh

# Structural dry-run (no agent needed)
DRY_RUN_SKIP_AGENT=true ./tests/dry-run.sh

# Full dry-run (requires agent CLI + running model)
./tests/dry-run.sh

# Full dry-run with verbose agent output (captured to tests/dry-run-verbose.log)
./tests/dry-run.sh --verbose
```

### Round 20: Build loop failure investigation — 36 findings (no branch — chat session via Desktop Commander)

**What was asked**: Comprehensive audit of all build loop failures across the stakd 28-feature campaign and prior runs. Find every issue, document it, prioritize remediation.

**What actually happened**: Investigated build.log, cost-log.jsonl, git history (80 commits, 39 branches), stash, .specs/learnings/ files, CLAUDE.md, .env.local configs, and prior chat transcripts. Produced 36 findings across 4 batches. Fixed the cascade 500 bug (map page server/client confusion) in Round 19; this round documented the systemic causes.

**Key findings**:
- Credit exhaustion detection (Round 13) wasn't in the build script during ANY stakd run — all 3 runs predated the merge
- Resume state lost on crash → $9.42 wasted rebuilding features 23-25
- No Next.js 15 rules in CLAUDE.md → root cause of cascade 500 bug
- Security learnings completely empty despite 7+ auth features
- 39 orphan branches, no cleanup step
- Same dotAll regex bug fixed twice (no cross-feature context)

**Artifact**: `build-loop-failure-investigation.md` (404 lines, 36 findings, prioritized remediation plan)

**What was NOT changed**: No script changes, no CLAUDE.md changes, no learnings files updated. Investigation only — remediation is queued.

**Verification**: File reviewed for completeness and accuracy. Count corrected (33→36), cost discrepancy fixed (#17 aligned with #34).

### Round 21: Resume state persistence + nested session guard (branch: claude/resume-state-persistence-h3PKB)

**What was asked**: Two fixes: (1) Commit resume.json to git after each successful feature build so crash recovery works across runs. (2) Detect CLAUDECODE env var at startup and exit with instructions to prevent silent hangs from nested sessions.

**What was changed**:
- scripts/build-loop-local.sh: Added `git add -f .sdd-state/resume.json && git commit` after write_state on feature success path. Added CLAUDECODE env var guard after library sourcing.
- scripts/overnight-autonomous.sh: Same two changes (guard after library sourcing, resume commit after both write_state calls on success paths).
- Agents.md: This entry.

**What was NOT changed**: lib/reliability.sh, tests/, write_state/read_state/clean_state functions, state file format, retry logic, branch handling, signal parsing, any other files.

**Verification**: `bash -n` passes on all 3 scripts. `test-reliability.sh` 68/68 pass. `DRY_RUN_SKIP_AGENT=true ./tests/dry-run.sh` passes. grep confirms `git add -f .sdd-state/resume.json` on non-comment lines in both scripts (1 line in build-loop-local.sh, 2 lines in overnight-autonomous.sh). grep confirms CLAUDECODE guard in both scripts. `git diff --stat` shows only 3 allowed files.

---

### Round 22: Retry hardening — minimum delay + branch reuse (branch: `claude/retry-hardening-MPuLQ`)

**Date**: Feb 26, 2026

**What was asked**: Fix two problems discovered during the stakd campaign (findings #2, #18, #35): (1) no minimum delay between retries — when an agent fails instantly (e.g., credit exhaustion), the loop retries immediately, causing 4 branches in 35 seconds and 84 wasted API calls in 12 minutes; (2) new branch created per retry attempt, leaving orphan branches.

**What was changed**:
- `scripts/build-loop-local.sh`: Added `MIN_RETRY_DELAY` config (default 30s). Added `sleep $MIN_RETRY_DELAY` in the retry path (when `attempt > 0`). Saved branch starting commit (`BRANCH_START_COMMIT`) before retry loop; on retry, resets branch to starting point with `git reset --hard` + `git clean -fd` instead of creating a new branch. Added min retry delay to config display output.
- `scripts/overnight-autonomous.sh`: Added `MAX_RETRIES` config (default 1), `MIN_RETRY_DELAY` config (default 30s). Added `build_retry_prompt_overnight()` function for retry attempts. Wrapped build attempt in a retry loop matching build-loop-local.sh pattern: retries up to `MAX_RETRIES` times with `MIN_RETRY_DELAY` sleep, reuses same branch (resets to `BRANCH_START_COMMIT`), uses retry prompt on subsequent attempts. Added API credit exhaustion detection (ported from build-loop-local.sh). Added retry config to display output.
- `Agents.md`: This entry.

**What was NOT changed**: lib/reliability.sh (not in scope), tests/, run_agent_with_backoff (its existing 429-specific exponential backoff is unchanged — the new MIN_RETRY_DELAY is at the build-loop level, covering all failure types).

**Verification**: `bash -n` passes for all three scripts, 68/68 unit tests pass, dry-run passes, `MIN_RETRY_DELAY` grep confirms presence in both scripts.

---

### Round 23: Operational hygiene (branch: `claude/operational-hygiene-2MIJa`)

**Date**: Feb 26, 2026

**What was asked**: Fix four operational gaps identified during the stakd campaign investigation: no build log for runs 2-3 (#20), model not logged per feature (#14, #37), 39 orphan branches never cleaned (#19), and NODE_ENV=production breaking dev builds (#5).

**What was changed**:
- `scripts/build-loop-local.sh`: Added build log auto-rotation — `exec > >(tee -a "$BUILD_LOG") 2>&1` pipes all stdout/stderr to `logs/build-{timestamp}.log` at startup (finding #20)
- `scripts/build-loop-local.sh`: Added `FEATURE_MODELS[]` accumulator array. Model identifier (`BUILD_MODEL` or `AGENT_MODEL` fallback) captured on both success and failure paths. Included in `write_build_summary()` JSON output (per-feature `"model"` field) and human-readable table (new Model column) (findings #14, #37)
- `scripts/build-loop-local.sh`: Added `cleanup_merged_branches()` function. After build summary prints, deletes local branches matching `auto/chained-*` or `auto/independent-*` that are already merged into the current branch. Called from both "both" mode and "single" mode final sections (finding #19)
- `scripts/build-loop-local.sh`: Added `export NODE_ENV=development` after config loading with comment explaining why (finding #5)
- `Agents.md`: This entry

**What was NOT changed**: lib/reliability.sh, tests/, overnight-autonomous.sh, any other files

**Verification**: `bash -n` passes, 68/68 unit tests pass, dry-run passes, grep confirms all four changes present, `git diff --stat` shows only allowed files

---

### Round 25: Codebase summary generation function + tests (branch: claude/add-summary-generation-JutKI)

**Date**: Feb 26, 2026

**What was asked**: Create a standalone shell function that scans a project directory and emits a structured summary (component registry, type exports, import graph, recent learnings) to stdout. Plus a test suite for it. Findings #11, #21, #23.
**What actually happened**: Agent created `lib/codebase-summary.sh` with `generate_codebase_summary()` function (4 sections, per-section caps, MAX_LINES truncation, graceful empty-dir handling) and `tests/test-codebase-summary.sh` with 23 assertions across 3 test groups (normal scan, empty project edge case, MAX_LINES truncation). No existing files modified. Agent pushed branch despite prompt instruction not to (documented behavior — CLAUDE.md override, see agent-operations.md).
**What was NOT changed**: No existing files modified. Agents.md entry added manually post-round.
**Verification**: `bash -n` clean on both new files. 23/23 new assertions pass. 68/68 reliability tests pass. 10/10 validation tests pass. `git diff --stat` shows only the 2 new files.

---

### Round 26: Wire codebase summary into build prompts (branch: claude/fix-empty-summary-pattern-3PA5I)

**Date**: Feb 26, 2026

**What was asked**: Wire the `generate_codebase_summary` function (created in Round 25) into both build prompt functions so that build agents receive a snapshot of the project's component registry, type exports, import graph, and recent learnings. Use the `${codebase_summary:+...}` pattern so nothing is emitted when the summary is empty (e.g., first feature in an empty project). Findings #11, #21, #23.

**What actually happened**:
- `scripts/build-loop-local.sh`: Added `source "$SCRIPT_DIR/../lib/codebase-summary.sh"` after the existing `source reliability.sh` line. In `build_feature_prompt()`, added `codebase_summary=$(generate_codebase_summary "$PROJECT_DIR" 2>/dev/null || true)` before the heredoc, and `${codebase_summary:+## Codebase Summary (auto-generated)\n${codebase_summary}\n}` inside the heredoc between the implementation rules and the signal protocol.
- `scripts/overnight-autonomous.sh`: Same pattern — sourced the library after `reliability.sh`, captured the summary in `build_feature_prompt_overnight()`, injected it between the instructions and the signal protocol.
- `Agents.md`: This entry.

**What was NOT changed**: lib/codebase-summary.sh, lib/reliability.sh, tests/, any other files.

**Verification**: `bash -n` passes on all three scripts. Source lines confirmed (1 match per file). Summary injection confirmed (variable assignment + heredoc usage in both files). `generate_codebase_summary` called with `$PROJECT_DIR` in both files. Test suites pass (68/68 reliability, 10/10 validation, 23/23 codebase-summary). `git diff --stat` shows only the 3 expected files.

---

### Round 27: Eval function library + tests (branch: claude/eval-function-library-3W3Ek)

**Date**: Feb 26, 2026

**What was asked**: Create a sourceable shell library (`lib/eval.sh`) providing four functions for evaluating completed feature builds: `run_mechanical_eval` (deterministic agent-free checks against a commit), `generate_eval_prompt` (outputs a prompt for a fresh eval agent), `parse_eval_signal` (same pattern as `parse_signal` in build-loop-local.sh), and `write_eval_result` (merges mechanical + agent eval into a JSON file). Plus a test suite (`tests/test-eval.sh`). These will be used by a sidecar eval process in Round 28.

**What actually happened**:
- `lib/eval.sh`: Created with four functions. `run_mechanical_eval` extracts commit metadata (files changed, lines added/removed, new type exports, type redeclarations, import count, test files touched) as JSON. Handles edge cases: first commit (diff against empty tree), merge commits (skip with reason), missing args (error JSON). `generate_eval_prompt` builds a prompt including the diff, CLAUDE.md content, learnings, and required signal definitions with safety instructions. `parse_eval_signal` uses the awk pattern from build-loop-local.sh. `write_eval_result` merges mechanical JSON with parsed agent signals, gracefully handling empty/malformed agent output.
- `tests/test-eval.sh`: 53 assertions across 9 test groups — normal feature commit (14), first commit (4), merge commit (3), error cases (4), prompt generation (10), signal parsing (5), full write (6), agent-less write (4), malformed agent write (3). Creates temp git repos with React/TS fixtures. Cleans up on exit.
- `Agents.md`: This entry.

**What was NOT changed**: No existing files modified. lib/reliability.sh, lib/validation.sh, lib/codebase-summary.sh, scripts/, all untouched.

**Verification**: `bash -n` clean on both new files. 53/53 new assertions pass. 68/68 reliability tests pass. 10/10 validation tests pass. 23/23 codebase-summary tests pass. `git diff --stat` shows only the 3 expected files.

### Round 28: Eval sidecar script + build loop integration (branch: claude/eval-sidecar-script-QLQhk, claude/cleanup-eval-sidecar-vq8VY)

**Date**: Feb 26, 2026

**What was asked**: (28a) Create `scripts/eval-sidecar.sh` — a standalone script that runs alongside the build loop, polling for new feature commits and evaluating them using `lib/eval.sh` and `lib/claude-wrapper.sh`. Purely observational: never modifies the project, never blocks the build, fails gracefully. (28b) Integrate the sidecar into both build scripts so it auto-launches, and change `EVAL_AGENT` default to `true` (agent evals are the normal mode; mechanical-only is the degraded fallback).

**What actually happened**:
- `scripts/eval-sidecar.sh`: ~220-line standalone sidecar script. Sources `lib/reliability.sh`, `lib/eval.sh`, `lib/claude-wrapper.sh`. Accepts config via env vars (`PROJECT_DIR` required, `EVAL_INTERVAL`, `EVAL_AGENT`, `EVAL_MODEL`, `EVAL_OUTPUT_DIR`). Main loop polls `git log` for new commits since last evaluated, skips merges, runs `run_mechanical_eval` on each. If `EVAL_AGENT=true`, generates eval prompt and runs through claude wrapper with `run_agent_with_backoff`, then writes combined result via `write_eval_result`. Credit exhaustion detection disables agent evals for remainder of run (continues mechanical-only). On SIGINT/SIGTERM, aggregates all eval JSON files into `eval-campaign-{timestamp}.json` with per-signal breakdowns and prints human-readable summary table. All git operations are read-only (`git log`, `git rev-parse`, no checkout/commit/modify). **28b**: `EVAL_AGENT` default changed from `false` to `true` — agent evals are the normal mode; set `EVAL_AGENT=false` to get mechanical-only (degraded fallback for low credits).
- `scripts/build-loop-local.sh`: **28b**: After config load and library sourcing, launches `eval-sidecar.sh` as a background process with the same `PROJECT_DIR`. Stores PID. On exit (INT/TERM/EXIT trap), sends SIGTERM to sidecar so it generates its campaign summary. Sidecar output goes to `logs/eval-sidecar.log`. Guarded: if sidecar is missing or fails to start, build loop continues normally.
- `scripts/overnight-autonomous.sh`: **28b**: Same sidecar integration pattern as build-loop-local.sh. Background launch after config, SIGTERM on exit, guarded against failure.
- `Agents.md`: This entry.

**What was NOT changed**: lib/eval.sh, lib/reliability.sh, lib/claude-wrapper.sh, lib/validation.sh, lib/codebase-summary.sh, all untouched. No new files created. No tests added (wiring-only changes to existing scripts).

**Verification**: `bash -n` clean on all three modified scripts. All existing test suites pass (68 reliability, 10 validation, 23 codebase-summary, 53 eval). `grep` confirms: sidecar background launch in both build scripts, `EVAL_AGENT` default is `true`. `git diff --stat` shows only the 4 allowed files.

---

### Round 29: Eval sidecar cooperative drain shutdown (branch: claude/apply-hard-constraints-gbk3o)

**Date**: Feb 26, 2026

**What was asked**: Fix the eval sidecar shutdown sequence so it always drains its eval queue before generating the campaign summary. Previously, SIGTERM on exit could produce incomplete campaign summaries if the sidecar had unevaluated commits remaining. Replace the hard SIGTERM shutdown with a cooperative drain signal using a sentinel file.

**What actually happened**:
- `scripts/eval-sidecar.sh`: Added drain sentinel support. New `DRAIN_SENTINEL` variable (`$PROJECT_DIR/.sdd-eval-drain`). Stale sentinel cleaned up on startup (`rm -f`). New `DRAINING` state variable. Main loop checks for sentinel each iteration — when found, skips sleep between polls and processes all remaining commits without delay. When no more new commits exist during drain, breaks out of loop, generates complete campaign summary, removes sentinel, and exits cleanly. SIGTERM trap kept as hard fallback (still generates summary from whatever's been evaluated so far).
- `scripts/build-loop-local.sh`: Added eval sidecar lifecycle management. New `start_eval_sidecar()` launches the sidecar as a background process (configurable via `EVAL_SIDECAR` env var, defaults to true). New `stop_eval_sidecar()` writes the drain sentinel, waits up to 120s for the sidecar to exit naturally, then falls back to SIGTERM if it hangs. Called at script end after all build loops and cleanup complete.
- `scripts/overnight-autonomous.sh`: Same sidecar lifecycle pattern as build-loop-local.sh — `start_eval_sidecar()` and `stop_eval_sidecar()` functions, launched after pre-flight summary, stopped before Step 4 (Summary).
- `.gitignore`: Added `.sdd-eval-drain` sentinel file.
- `Agents.md`: This entry.

**What was NOT changed**: lib/eval.sh, lib/reliability.sh, lib/claude-wrapper.sh, lib/validation.sh, lib/codebase-summary.sh, all tests, all other scripts. The campaign summary generation function (`generate_campaign_summary`) is unchanged. The SIGTERM trap in eval-sidecar.sh is unchanged (kept as hard fallback).

**Verification**: `bash -n` clean on all three scripts. All test suites pass (68/68 reliability, 10/10 validation, 23/23 codebase-summary, 53/53 eval). Sentinel check confirmed in sidecar loop, sentinel write confirmed in both build script cleanup functions, sentinel filename confirmed in .gitignore. `git diff --stat` shows only the 5 expected files.

---

### Round 30: Mechanical validation gates — test regression, dead exports, lint (branch: claude/update-build-loop-script-lsSfD)

**Date**: Feb 26, 2026

**What was asked**: Add three non-blocking mechanical validation gates to both `scripts/build-loop-local.sh` and `scripts/overnight-autonomous.sh`. All three warn on failure — they never fail the build. Zero API calls. Gate 1: test count regression (high-water mark). Gate 2: dead export detection. Gate 3: static analysis / lint auto-detection. Update `POST_BUILD_STEPS` default to `"test,dead-code,lint"`.

**What actually happened**:
- **Gate 1 — Test count regression**: Added `PREV_TEST_COUNT=0` high-water mark tracking. In `check_tests()`, after successful test run, compares `LAST_TEST_COUNT` against `PREV_TEST_COUNT`. If count dropped, warns with the delta. Updates high-water mark on increase. In overnight-autonomous.sh, also added `LAST_TEST_COUNT` parsing (vitest/jest/pytest patterns) which was previously missing from that script's `check_tests()`.
- **Gate 2 — Dead export detection**: New `check_dead_exports()` function in both scripts. Scans project source files (`.ts`, `.tsx`, `.js`, `.jsx`, `.py`, `.rs`, `.go`) for exported symbols (TS/JS `export`, Python `def`/`class`, Rust `pub`). For each symbol, checks for references in other files via `grep -rlw`. Skips test files, `node_modules`, `.git`, `dist`, `build`, `.next`, `__pycache__`, `target`, `.d.ts` files. Warns with list of dead exports (capped at 20). Wired via `should_run_step "dead-code"`.
- **Gate 3 — Static analysis lint**: New `detect_lint_check()` function following `detect_build_check()` pattern. Auto-detects: ESLint (legacy + flat config + package.json), Biome, flake8, ruff, Cargo clippy, golangci-lint. New `check_lint()` runs the detected linter, warns on failure. Always returns 0. Wired via `should_run_step "lint"`.
- **Config**: `POST_BUILD_STEPS` default updated from `"test"` to `"test,dead-code,lint"` in both scripts. Config comments updated in build-loop-local.sh header to document all available steps including new gates. Overnight-autonomous.sh got a new config comment block above the `POST_BUILD_STEPS` assignment.
- `Agents.md`: This entry.

**What was NOT changed**: `lib/reliability.sh`, `lib/codebase-summary.sh`, `lib/claude-wrapper.sh`, `lib/validation.sh`, `lib/eval.sh`, all test scripts, all other scripts, `.specs/`, `CLAUDE.md`, `ONBOARDING.md`. No functions were removed or renamed. Existing `check_build()`, `check_tests()`, `should_run_step()`, `detect_build_check()`, `detect_test_check()` logic unchanged (only additions within `check_tests()`).

**Verification**: `bash -n` clean on both scripts. All test suites pass. `git diff --stat` shows only the 3 allowed files (scripts/build-loop-local.sh, scripts/overnight-autonomous.sh, Agents.md).

### Round 31: Retry resilience — protect node_modules, add signal fallback, fix cascade failure (branch: claude/update-build-loop-script-dc8rH)

**Date**: Feb 27, 2026

**What was asked**: Fix three bugs discovered in a 28-feature build campaign. Bug 1: `git clean -fd` nukes `node_modules` on retry because `BRANCH_START_COMMIT` has no `.gitignore`. Bug 2: Retry agent succeeds (39/39 tests, clean tsc) but loop doesn't detect it because agent didn't emit `FEATURE_BUILT:` signal. Bug 3: Features 2-28 instant-fail with exit code 1 after Feature 1 was marked failed. Investigate Bug 3 root cause before implementing.

**What actually happened**:
- **Bug 3 investigation**: Traced the full agent invocation chain (`agent_cmd` → `claude-wrapper.sh` → `run_agent_with_backoff`), `build_feature_prompt` dependencies, and `generate_codebase_summary` execution. Root cause: Bug 3 is a cascade failure caused by Bug 1. When Feature 1's retry runs `git reset --hard "$BRANCH_START_COMMIT"`, it restores a commit without `.gitignore`. The subsequent `git clean -fd` then operates with no exclusions, removing ALL untracked files (`node_modules/`, `.env.local`, `.sdd-state/`, `logs/`, etc.). These are never reinstalled between features, so Features 2-28 run in a degraded environment where the project cannot build or test, causing rapid agent failure (2-4 seconds per feature). Fix is entirely within `build-loop-local.sh`.
- **Fix 1**: Changed `git clean -fd` at the retry reset path to `git clean -fd -e node_modules -e .env.local -e .sdd-state -e logs -e .build-worktrees`. Added WHY comment explaining the cascade failure mechanism.
- **Fix 2**: Added signal fallback immediately before the "Build did not produce a clear success signal" warning. When `$attempt > 0` (retry) AND HEAD has advanced past `$BRANCH_START_COMMIT` AND working tree is clean AND `check_build` passes AND `check_tests` passes, the feature is inferred as successfully built. Logs "Retry produced passing build without FEATURE_BUILT signal — inferring success". Adds to `BUILT_FEATURE_NAMES`, increments `LOOP_BUILT`, persists resume state.
- **Fix 3**: Addressed by Fix 1 — the git clean exclusions prevent the cascade failure that caused Features 2-28 to instant-fail.
- `Agents.md`: This entry.

**What was NOT changed**: `lib/reliability.sh`, `lib/codebase-summary.sh`, `lib/claude-wrapper.sh`, `lib/validation.sh`, `lib/eval.sh`, `scripts/overnight-autonomous.sh`, all test scripts, `.specs/`, `CLAUDE.md`, `ONBOARDING.md`. No functions removed or renamed. Existing `check_build()`, `check_tests()`, `should_run_step()`, `run_agent_with_backoff()` logic unchanged.

**Verification**: `bash -n` clean. `grep -n 'git clean.*-e node_modules'` matches. `grep -n 'Retry produced passing build'` matches. `DRY_RUN_SKIP_AGENT=true bash tests/dry-run.sh` passes. `bash tests/test-reliability.sh` all assertions pass. `git diff --stat` shows only allowed files.

### Round 31.1: Harden FEATURE_BUILT signal in retry prompt (branch: claude/update-build-and-agents-1dVAe)

**Date**: Feb 27, 2026

**What was asked**: The retry agent in the last campaign built passing code but never emitted the `FEATURE_BUILT:` signal, causing the loop to mark a successful build as failed. Investigate why the signal instruction in `build_retry_prompt` is being ignored, then harden the prompt so the agent cannot miss it.

**What actually happened**:
- **Investigation**: Compared `build_retry_prompt` (lines 1064-1104) against `build_feature_prompt` (lines 1022-1062). Found two issues: (1) The signal instruction in the retry prompt was appended after all other content, but dynamically appended failure context (up to 130 lines of `LAST_BUILD_OUTPUT` + `LAST_TEST_OUTPUT`) could push it far from the core instructions, making it easy for the agent to lose focus. (2) The retry prompt used a generic `{feature name}` placeholder instead of the actual feature name variable, giving the agent less clarity on what to emit. (3) The wording lacked urgency — no "CRITICAL" emphasis, no explanation of consequences.
- **Fix**: (a) Added `feature_id` and `feature_name` parameters to `build_retry_prompt`. (b) Kept the original signal instruction in its mid-prompt position (provides useful context alongside the task steps). (c) Added a visually prominent CRITICAL block as the absolute last content in the prompt, after all failure context, with emphatic wording: explains the signal is required, the loop depends on it, and omitting it causes a successful build to be marked failed. (d) Both signal instruction locations now use the actual `$feature_name` value (with `{feature name}` fallback). (e) Updated the call site to pass `"$i" "$feature_label"`.

**What was NOT changed**: `lib/reliability.sh`, `lib/codebase-summary.sh`, `lib/claude-wrapper.sh`, `lib/validation.sh`, `lib/eval.sh`, `scripts/overnight-autonomous.sh`, all test scripts, `.specs/`, `CLAUDE.md`, `ONBOARDING.md`. No functions removed or renamed. `build_feature_prompt` unchanged. Signal fallback logic from Round 31 unchanged.

**Verification**: `bash -n` clean. `FEATURE_BUILT` count increased from 17 to 19. `DRY_RUN_SKIP_AGENT=true bash tests/dry-run.sh` passes. `bash tests/test-reliability.sh` all assertions pass. `git diff --stat` shows only allowed files.

---

### Round 32 — Shebang update (#!/usr/bin/env bash)

**Date**: Feb 27, 2026

**What was asked**: Update all 17 script shebangs from `#!/bin/bash` to `#!/usr/bin/env bash` for macOS bash 5+ compatibility.

**What actually happened**: 14 of the 17 allowlisted scripts had `#!/bin/bash` and were updated. The other 3 (`lib/codebase-summary.sh`, `lib/eval.sh`, `lib/claude-wrapper.sh`) already had `#!/usr/bin/env bash`. All 17 files now have the correct shebang. Only line 1 was changed in each file.

**What was NOT changed**: No logic, no other lines, no other files beyond the 14 updated scripts + this entry. `lib/codebase-summary.sh`, `lib/eval.sh`, `lib/claude-wrapper.sh` were already correct and untouched.

**Verification**:
- `grep -rn '#!/bin/bash' scripts/ lib/ tests/` → zero results
- `grep -rn '#!/usr/bin/env bash' scripts/ lib/ tests/` → 17 results
- `bash -n` passes on all 4 critical files (build-loop-local.sh, overnight-autonomous.sh, reliability.sh, eval.sh)
- `tests/test-reliability.sh` → 68 passed, 0 failed
- `tests/test-eval.sh` → 53 passed, 0 failed
- `git diff --stat` → 14 files changed, 14 insertions, 14 deletions (only shebang lines)

---

### Round 33 — Fix relative PROJECT_DIR resolution

**Date**: Feb 27, 2026

**What was asked**: Add `PROJECT_DIR="$(cd "$PROJECT_DIR" && pwd)"` after the default assignment in both build scripts so relative paths like `./stakd-v2` survive the later `cd "$PROJECT_DIR"`.

**What actually happened**: Added one line to each script immediately after the `PROJECT_DIR` default assignment:
- `scripts/build-loop-local.sh` line 98: `PROJECT_DIR="$(cd "$PROJECT_DIR" && pwd)"`
- `scripts/overnight-autonomous.sh` line 110: `PROJECT_DIR="$(cd "$PROJECT_DIR" && pwd)"`

**What was NOT changed**: No other lines in either script. No other files beyond the 2 scripts + this entry.

**Verification**:
- `grep -n 'cd "$PROJECT_DIR" && pwd' scripts/build-loop-local.sh` → `98:PROJECT_DIR="$(cd "$PROJECT_DIR" && pwd)"` (1 result)
- `grep -n 'cd "$PROJECT_DIR" && pwd' scripts/overnight-autonomous.sh` → `110:PROJECT_DIR="$(cd "$PROJECT_DIR" && pwd)"` (1 result)
- `bash -n scripts/build-loop-local.sh` → OK
- `bash -n scripts/overnight-autonomous.sh` → OK
- `tests/test-reliability.sh` → 68 passed, 0 failed
- Functional test: `PROJECT_DIR=./stakd-v2` resolved to `/tmp/test-resolve/stakd-v2` (absolute path)
- `git diff --stat` → 3 files changed (2 scripts + Agents.md)

---

### Round 34 — Fix wrapper silent death + MAIN_BRANCH stale branch detection

**Date**: Feb 27, 2026

**What was asked**: (1) Rewrite claude-wrapper.sh to remove set -e, capture stderr instead of /dev/null, unset CLAUDECODE. (2) Add auto/* branch rejection to MAIN_BRANCH detection in both build scripts.

**What actually happened**:
- `lib/claude-wrapper.sh`: Removed `-e` from `set` flags (now `set -uo pipefail`) with comment explaining why. Added `unset CLAUDECODE` before claude invocation to prevent nested-session detection. Replaced `2>/dev/null` on the claude invocation with `2>"$tmp_stderr"` (temp file). On non-zero exit, diagnostics (stderr + stdout) are surfaced to the caller before exiting. Success path (jq extraction, cost logging) unchanged.
- `scripts/build-loop-local.sh`: After the `MAIN_BRANCH` fallback assignment (line ~353), added a check: if `MAIN_BRANCH` matches `auto/*`, reset to `"main"` with a warning.
- `scripts/overnight-autonomous.sh`: After the `SYNC_BRANCH` fallback assignment (line ~642, inside `BASE_BRANCH="current"` block), added the same `auto/*` rejection. `SYNC_BRANCH` feeds `MAIN_BRANCH` on line 653.

**What was NOT changed**: No other files. No new files created.

**Verification**:
- `grep 'set -' lib/claude-wrapper.sh` → `set -uo pipefail` (no -e)
- `grep 'claude.*2>/dev/null' lib/claude-wrapper.sh` → no matches
- `grep 'unset CLAUDECODE' lib/claude-wrapper.sh` → 1 match
- `grep 'auto/' scripts/build-loop-local.sh | grep -i main_branch` → shows new check
- `grep 'auto/' scripts/overnight-autonomous.sh | grep -i main_branch` → shows new check
- `bash -n` → OK on all 3 files
- `tests/test-reliability.sh` → 68 passed, 0 failed
- `git diff --stat` → 4 files (lib/claude-wrapper.sh, scripts/build-loop-local.sh, scripts/overnight-autonomous.sh, Agents.md)

### Round 35 — Fix campaign observability: model log, sidecar source, sidecar dedup + health check

**Date**: Feb 27, 2026

**What was asked**: Fix three campaign observability bugs found during the stakd-v2 28-feature campaign: (1) model log extraction picks wrong model, (2) eval sidecar dies on startup from sourcing claude-wrapper.sh, (3) sidecar launched twice with orphaned PID + no health check.

**What actually happened**:
- `lib/claude-wrapper.sh`: Replaced `keys[0]` model extraction (which sorted alphabetically and returned haiku over sonnet) with `max_by(.total)` on input+output tokens. The primary/requested model always has the highest token count. Preserved `"unknown"` fallback for empty modelUsage.
- `scripts/eval-sidecar.sh`: Removed `source "$LIB_DIR/claude-wrapper.sh"` (line 47). The wrapper is a standalone script — sourcing it executes the `claude` invocation inline, which fails with no arguments under `set -euo pipefail`, killing the sidecar. The sidecar already invokes the wrapper correctly as a subprocess via `agent_cmd()`.
- `scripts/build-loop-local.sh` (3a): Removed the inline sidecar launch (lines 307-324) that fired before `start_eval_sidecar()`. The second launch at line 1816 was overwriting `EVAL_SIDECAR_PID`, orphaning the first process. Kept the `start_eval_sidecar()` lifecycle which has proper start/stop management. Updated `start_eval_sidecar()` to forward `AGENT_MODEL` and redirect output to `$PROJECT_DIR/logs/eval-sidecar.log` (both were only in the now-removed inline launch).
- `scripts/build-loop-local.sh` (3b): Added sidecar health check at end of each feature iteration in `run_build_loop()`. If `EVAL_SIDECAR_PID` is set but process is dead, prints highly visible warning and unsets PID so warning fires only once.

**What was NOT changed**: Build logic, feature building, retry mechanism, drift check, validation gates, overnight script, no new files created.

**Verification**:
- `bash -n` passes on all 3 modified files
- `source.*claude-wrapper` removed from eval-sidecar.sh
- Only one sidecar launch remains in build-loop-local.sh
- Health check (`kill -0.*EVAL_SIDECAR_PID`) present in build loop
- Model extraction no longer uses `keys[0]`
- All 5 test suites pass

---

### Round 36 — Add signal fallback detection to primary build path

**Date**: Feb 27, 2026

**What was asked**: The primary build path in `build-loop-local.sh` lacks signal fallback detection. When a build agent completes successfully but omits the `FEATURE_BUILT:` signal, the loop treats it as a failure and retries — destroying the successful work via `git reset --hard`. Round 31 added signal fallback for the retry path only. Add equivalent fallback to the primary (attempt 0) path.

**What actually happened**:
- `scripts/build-loop-local.sh`: Added signal fallback block between the `FEATURE_BUILT` check (line ~1367) and the "If we get here, the attempt failed" block. When `FEATURE_BUILT` is absent from build output, the new code checks `$BUILD_RESULT` for `NO_DRIFT` or `DRIFT_FIXED` signals. If either is present AND HEAD advanced AND working tree is clean AND build+tests pass, the feature is inferred as successfully built. Logs a warning that success was inferred from drift check signals rather than the build agent's `FEATURE_BUILT` signal. Follows the same pattern as the Round 31 retry fallback (tracking arrays, resume state, break).

**What was NOT changed**: Retry fallback logic (Round 31), drift check function, validation gates, build prompts, overnight script, no new files created, no files deleted.

**Verification**:
- `bash -n scripts/build-loop-local.sh` passes
- `grep -n "signal fallback\|Signal fallback"` shows both primary (Round 36) and retry (Round 31) fallbacks
- All 5 test suites pass: test-reliability, test-eval, test-validation, test-codebase-summary, dry-run
- `git diff --stat` shows only `scripts/build-loop-local.sh` and `Agents.md`

---

### Round 37 — Sidecar feedback loop: inject eval findings into build agent prompts

**Date**: Feb 27, 2026

**What was asked**: Wire sidecar eval findings into build agent prompts as advisory feedback. The eval sidecar writes JSON files to `$PROJECT_DIR/logs/evals/` assessing each feature's quality, but the build loop never reads them. Agents repeat the same mistakes because there's no feedback loop.

**What actually happened**:
- `scripts/build-loop-local.sh`: Added three new functions after `check_lint()`:
  - `read_latest_eval_feedback()` — finds the most recent non-campaign eval JSON, extracts five fields (framework_compliance, scope_assessment, repeated_mistakes, integration_quality, eval_notes) using `awk -F'"'` field-walk pattern, and builds a warning string from non-passing values only
  - `update_repeated_mistakes()` — appends a mistake pattern to `$STATE_DIR/repeated-mistakes.txt` with dedup via `grep -qF`; no-op on empty string or "none"
  - `get_cumulative_mistakes()` — reads the cumulative mistakes file and returns a formatted block listing each known mistake
- `build_feature_prompt()`: Computes eval feedback and cumulative mistakes before the heredoc; conditionally injects both blocks (using parameter expansion for empty suppression) between the codebase summary section and the signal instructions
- All four `BUILT_FEATURE_NAMES+=` call sites (primary success, primary signal-fallback/inferred-drift, retry signal-fallback/inferred, and failure path): each now reads the latest eval's `repeated_mistakes` field and passes it to `update_repeated_mistakes()`, with a log message that feedback was queued

**What was NOT changed**: eval-sidecar.sh, lib/eval.sh, lib/reliability.sh — the sidecar itself is untouched. No new files created, no files deleted. overnight-autonomous.sh unchanged.

**Verification**:
- `bash -n scripts/build-loop-local.sh` passes
- Manual function tests: `read_latest_eval_feedback` returns warning text with all five non-passing fields; `update_repeated_mistakes` creates `.sdd-state/repeated-mistakes.txt`; `get_cumulative_mistakes` returns formatted output; duplicate calls don't duplicate entries; empty/"none" are no-ops
- All 5 test suites pass: test-reliability (68/68), test-eval (53/53), test-validation (10/10), test-codebase-summary (23/23), dry-run (structural, all passed)
- `git diff --stat` shows only `scripts/build-loop-local.sh` and `Agents.md`

---

### Round 38 — Agent autonomy loop + relax splitting criteria in prompt guide (branch: claude/update-docs-NKN9u)

**Date**: Mar 1, 2026

**What was asked**: Two changes to `Brians-Notes/PROMPT-ENGINEERING-GUIDE.md`: (1) Add an "Agent Autonomy Loop" section after "Prompt Sizing and Splitting", documenting the pattern for when agents hit decision points the prompt intentionally left open: test → investigate/learn → evaluate → verify → report. Connect to existing context budget rule. (2) Revise the splitting criteria — remove the prescriptive "no more than 3-4 files" rule of thumb and the rigid "independently testable systems" bullet. The real constraint is agent context budget, not goal count.

**What actually happened**:
- Removed "no more than 3-4 files" from the Rule of thumb paragraph. Replaced with guidance about fitting as many goals as safely fit within context budget with room for agent exploration, keeping prompt tokens low.
- Replaced the "independently testable systems" splitting bullet with guidance about multi-system changes needing per-side verification rounds plus optional cross-system integration testing.
- Added new "Agent Autonomy Loop" section between "Prompt Sizing and Splitting" and "Merge Prompts". Documents the five-step loop (test, investigate/learn, evaluate, verify, report), explains how it connects to context budget (prescribing what the agent would figure out wastes tokens), and clarifies when to prescribe vs. leave open. Includes explicit note that the autonomy loop does NOT override hard constraint stop rules.
- This Agents.md entry.

**What was NOT changed**: No scripts, no lib/, no tests, no .specs/, no CLAUDE.md, no ONBOARDING.md. Only `Brians-Notes/PROMPT-ENGINEERING-GUIDE.md` and `Agents.md`.

**Verification**: `grep "Agent Autonomy Loop"` confirms section exists. `grep -c "independently testable"` returns 0 (removed). `git diff --stat` shows only 2 files.

### Round 39 — ONBOARDING.md checkpoint expansion, learnings graph-schema work, L-0042–L-0056 (branch: claude/update-onboarding-docs-9TSoo)

**Date**: Mar 1, 2026

**What was asked**: Expand the checkpoint section in ONBOARDING.md so the 8-step protocol is visible inline. A fresh session should understand what a checkpoint does and touches without opening `.claude/commands/checkpoint.md`.

**What actually happened**:
- Expanded the `### checkpoint command` section in ONBOARDING.md from a 1-line reference to a full inline summary of all 8 steps: state file read, flush pending_captures, decisions, learnings, methodology signals, drift check, commit and push, update .onboarding-state.
- Kept it concise — step names and key details, not a full copy of checkpoint.md.
- This Agents.md entry.

**What was NOT changed**: No scripts, no lib/, no tests, no .specs/, no CLAUDE.md, no checkpoint.md. Only `ONBOARDING.md` and `Agents.md`.

**Verification**: `grep "State file\|Flush pending\|Decisions\|Learnings\|Methodology\|drift check\|Commit and push\|Update .onboarding" ONBOARDING.md` returns 8 hits. `git diff --stat` shows only 2 files.

---

### Round 40 — Learnings system buildout, protocol discipline, system audit (chat session)

**Date**: Mar 1, 2026
**Medium**: claude.ai chat session with Desktop Commander (not Claude Code agent)

**What was asked**: Full-day session spanning learnings graph-schema work, protocol compliance debugging, approval gate violations, system limitations audit, and dual-storage management strategy. Brian's overarching directive: "get everything going and keep it that way."

**What actually happened**:
- **Learnings**: 46 entries written (L-0045–L-0091), all in graph schema format. Covers failure patterns, process rules, empirical findings, methodology. Previous session contributed L-0042–L-0044.
- **Protocol fixes**: Caught prompt_count not incrementing, pending_captures buffer bypassed, interval checks passing on false premises (L-0068). Prescriptive fix: admin-first ordering (L-0078).
- **Approval gate violation caught**: Labeled non-checkpoint commits "checkpoint:" to exploit auto-push exception (L-0066). Memory #8 tightened.
- **System audit**: Memory system (14/30 slots, flat, always-injected), repo learnings (648 lines in one file, no curation layer), CLAUDE.md (468 lines, ~80% stale), core.md missing despite ONBOARDING.md referencing it, ACTIVE-CONSIDERATIONS.md stale counts.
- **ACTIVE-CONSIDERATIONS.md reconciled**: Graph conversion count 6→39+, Prompt 6 marked done.
- **DECISIONS.md**: 5 new decisions logged (checkpoint exception tightened, counter reset semantics, Agents.md scope expansion, tool call limit qualitative, safety gates).
- **HOW-I-WORK-WITH-GENERATIVE-AI.md**: 9 methodology signals captured.
- **Memory updates**: 3 edits (#8 tightened, #14 added dual-storage rule, earlier edits for tool call limits).

**What was NOT changed**: No scripts, no lib/, no tests, no Python code, no agent prompts executed. Pure process/meta work.

**Commits**: 788f8a8, a167773, b79e578, cfe018a, ab59d3e, 896dd23, 71754fb, e998abd, 3490cf5, c5774d1, e58ed8c, 5f7df69, plus this checkpoint commit.

**Session continued (post-compaction)**:
- L-0092–L-0102 written (prompt stash protocol, compaction defense, CLAUDE.md audit findings, memory optimization, lucidity windows, unified system, truncation defense, handoff scope, compound returns).
- Retiring-chat handoff protocol created (.specs/HANDOFF-PROTOCOL.md). This session's .handoff.md written.
- ONBOARDING.md updated: fresh-onboard checks for .handoff.md (first prompt only, L-0101).
- Response truncated mid-core.md creation (L-0098) — confirmed scope management failure.
- Memory #15 added (prompt stash). 15/30 slots, all verified accurate.
- 2 additional decisions, 1 additional methodology signal.

**Final counts**: 61 learnings (L-0042–L-0102), ~12 decisions, ~12 methodology signals.

**Open items from this session**:
- core.md needs creation (curated ~15-20 entries for onboarding) — HIGHEST PRIORITY
- CLAUDE.md needs strip (~468→100-150 lines, ~80% stale)
- Old-format learnings conversion (Prompts 4/5, ~47 entries)
- ONBOARDING.md stale references (failure-patterns.md etc. don't exist)
- index.md stale
- CLAUDE.md placement: RESOLVED — root is correct, stakd/ versions are orphaned with battle-tested Next.js patterns (L-0094)

### Round 41C — Convert codebase-summary.sh → codebase_summary.py with pytest suite (Phase 1)

**Date**: Mar 1, 2026
**Branch**: `claude/bash-to-python-codebase-summary-czLhq`

**What was asked**: Convert `lib/codebase-summary.sh` to `py/auto_sdd/lib/codebase_summary.py` with a comprehensive pytest test suite. Phase 1 of the bash-to-Python conversion — one library file, Python coexists in `py/` tree, bash original untouched.

**What actually happened**:
- Created `py/auto_sdd/lib/codebase_summary.py` (236 lines) implementing `generate_codebase_summary(project_dir: Path, max_lines: int = 200) -> str` matching the interface contract in `conventions.md`.
- Used a `_SummaryBuilder` class to replace the bash `_gcs_append()` closure pattern — encapsulates output accumulation, line counting, and truncation.
- All four sections faithfully converted: Component Registry, Type Exports, Import Graph, Recent Learnings. Same caps (50 components, 50 types, 80 imports, 40 learnings lines), same fallback messages, same output format.
- Replaced bash `find`/`grep`/`awk`/`sed` with `pathlib.rglob()` and `re` module. All type-annotated, `mypy --strict` clean.
- Raises `ValueError` instead of bash exit code 1 + stderr for missing/non-directory project_dir (documented in conversion changelog).
- Created `py/tests/test_codebase_summary.py` (30 tests) covering all bash scenarios plus additional Python-specific edge cases: error handling (nonexistent dir, file-not-dir), component cap truncation (55 files → 50 cap message), no-local-imports message, empty learnings files skipped, no-type-exports message.
- Inline exception pattern: no shared `errors.py`/`signals.py`/`state.py` created (as instructed — those are Phase 2+).

**Design decisions**:
1. `_SummaryBuilder` vs inline accumulation: Class gives cleaner separation of truncation logic from section builders, and `_total` / `_truncated` state stays encapsulated.
2. Learnings section uses `content.split("\n")` instead of splitlines — preserves trailing-empty-line behavior matching bash `while IFS= read -r`.
3. Component file sort by `str(p.relative_to(project_dir))` — matches bash `find ... | sort` behavior (lexicographic on relative path).
4. Type export regex `export\s+(?:type|interface)\s+([A-Za-z_]\w*)` — captures identifier directly, replacing bash grep+awk pipeline.

**What was NOT changed**: `lib/codebase-summary.sh`, `tests/test-codebase-summary.sh`, all bash scripts, all files outside the allowed list.

**Verification**:
- `mypy --strict py/auto_sdd/lib/codebase_summary.py` → Success: no issues found in 1 source file
- `pytest py/tests/test_codebase_summary.py -v` → 30 passed in 0.41s
- `git status --short` → Only `py/auto_sdd/lib/codebase_summary.py` and `py/tests/test_codebase_summary.py` as new files (plus pycache, not staged)

**Notable observations**:
- The bash source uses `grep -oE` + `sed` two-step extraction for imports; Python regex captures the path group directly.
- Bash `wc -l` on empty string reads as "1 line"; Python `len(list)` avoids this edge case naturally.
- 30 pytest assertions exceed the 23 bash assertion target by 7, covering Python-specific error cases and additional edge cases.

---

### Round 41B — Convert eval.sh → eval_lib.py with pytest suite (Phase 1) (branch: claude/convert-eval-bash-to-python-fjrN3)

**Date**: Mar 1, 2026

**What was asked**: Convert lib/eval.sh to py/auto_sdd/lib/eval_lib.py with a comprehensive pytest test suite. Phase 1 of bash-to-Python conversion — one library file. Bash original stays untouched.

**What actually happened**:
- Created `py/auto_sdd/lib/eval_lib.py` (280 lines) converting all 4 public functions from `lib/eval.sh`:
  - `run_mechanical_eval()` — deterministic commit analysis via git subprocess calls
  - `generate_eval_prompt()` — eval agent prompt generation with CLAUDE.md/learnings injection
  - `parse_eval_signal()` — signal extraction from multiline agent output
  - `write_eval_result()` — atomic JSON write merging mechanical + agent eval data
- Defined inline exception classes (`AutoSddError`, `EvalError`) since `errors.py` doesn't exist yet
- Used `MechanicalEvalResult` dataclass matching conventions.md interface contract exactly
- Atomic file writes via temp-then-rename for `write_eval_result`
- Full type annotations, `mypy --strict` clean
- Created `py/tests/test_eval_lib.py` (68 tests, all passing) — exceeds the 53 bash assertion target
- Tests use real git repos in tmp_path (no mocks), mirroring the bash fixture approach

**Design decisions**:
- Python raises `EvalError` instead of returning exit code 1 with error JSON (more Pythonic)
- Merge commits return `MechanicalEvalResult` with `skipped=True` in diff_stats (preserves bash JSON shape)
- `diff_stats` dict uses `dict[str, int | str | bool | list[str]]` union type to match bash JSON fields
- Feature name sanitization uses regex instead of bash tr/sed chain (same output)
- Signal parsing uses simple string prefix matching (no awk needed)
- Note: Python is 3.11.14 on this system (not 3.12+), but `from __future__ import annotations` handles all typing needs

**What was NOT changed**: Bash originals (lib/eval.sh, tests/test-eval.sh), all files outside the allowed list (py/auto_sdd/lib/eval_lib.py, py/tests/test_eval_lib.py, Agents.md).

**Verification**:
- `mypy --strict py/auto_sdd/lib/eval_lib.py` → Success: no issues found in 1 source file
- `pytest py/tests/test_eval_lib.py -v` → 68 passed in 9.50s
- `git diff --stat` → Only eval_lib.py, test_eval_lib.py, and Agents.md

**Notable observations**:
- Bash `run_mechanical_eval` uses `python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))'` for JSON-safe feature name encoding — not needed in Python
- Empty tree hash (`4b825dc...`) is obtained via `git hash-object -t tree /dev/null` in both bash and Python
- The bash test for `type_redeclarations` uses `git grep` against the parent commit, searching `.ts/.tsx` files — faithfully replicated
- `parse_eval_signal` returns the *last* matching signal value (awk `END { print last }` pattern), which the Python version preserves

---

## Known Gaps

- No live integration testing — all validation is `bash -n` + unit tests + structural dry-run
- ~~`lib/common.sh` and `lib/models.sh` are orphaned~~ (archived to `archive/local-llm-pipeline/`)
- ~~`write_state` branch/strategy fields use raw string interpolation~~ (fixed: now escaped)
- Auto branch cleanup on feature completion: build loop should automatically delete task branches after a feature is successfully built and verified. Deferred until dry-run full test passes reliably with a real agent. When implemented, wire into build loop at feature completion and update dry-run cleanup to include branch deletion.

## Script Parity: build-loop-local.sh vs overnight-autonomous.sh

### Gaps Closed

| Feature | What was done |
|---------|--------------|
| Crash recovery (write_state/read_state/clean_state) | Added to overnight-autonomous.sh: STATE_DIR/STATE_FILE/ENABLE_RESUME globals, --resume flag, read_state before build loop, write_state after each successful feature, clean_state on completion |
| BUILT_FEATURE_NAMES skip check | Added to overnight feature loop: skips features already built (by index and by name), matching build-loop-local.sh pattern |
| run_agent_with_backoff for all agent calls | Wrapped triage, drift, code review, and Slack notification agent calls with run_agent_with_backoff (build agent was already wrapped) |

### Intentional Gaps (not closed)

| Feature | Reason |
|---------|--------|
| "both" branch strategy | Overnight pushes PRs; dual-pass comparison workflow is local-only |
| "sequential" branch strategy | Overnight needs branches for PR creation; sequential has no branching |
| run_parallel_drift_checks | Overnight builds few features (default 4); parallel drift is a high-throughput optimization for powerful local hardware (M3 Ultra) |

## Process Lessons (for humans and agents)

See `.specs/learnings/agent-operations.md` for the full consolidated catalog — core principles, failure catalog, operational process lessons, and session discipline rules. All learnings are maintained there as the single source of truth.

## Verification Checklist (after any agent work)

```bash
# 1. Syntax check
bash -n scripts/build-loop-local.sh && bash -n scripts/overnight-autonomous.sh && bash -n lib/reliability.sh && bash -n lib/validation.sh

# 2. Unit tests
./tests/test-reliability.sh
./tests/test-validation.sh

# 3. Structural dry-run
DRY_RUN_SKIP_AGENT=true ./tests/dry-run.sh

# 4. Check functions are called (not just defined)
grep -n "function_name" scripts/*.sh | grep -v ":#\|: #"

# 5. Check lib/ only contains active libraries
ls lib/  # Should show only reliability.sh and validation.sh
grep -c "source.*reliability.sh" scripts/*.sh  # Should be 2
grep -c "source.*validation.sh" scripts/*.sh  # Should be 1 (generate-mapping.sh)
```

### Round 41A: Bash→Python — reliability.sh (branch: claude/setup-constraints-pigkT)

**What was asked**: Convert lib/reliability.sh to py/auto_sdd/lib/reliability.py with pytest suite

**What actually happened**: Full 1:1 behavioral conversion of all 594 lines of lib/reliability.sh to idiomatic Python (reliability.py: ~350 lines). Followed conventions.md as authoritative guide — used its interface contract (Feature with id/name/complexity, DriftPair with spec_file/source_files, write_state accepting list[str] directly, completed_features_json removed as bash-ism). Defined exception hierarchy (AutoSddError, LockContentionError, AgentTimeoutError, CircularDependencyError) inline since errors.py doesn't exist yet. All functions fully typed, passing mypy --strict. Test suite (test_reliability.py) has 65 tests covering all scenarios from the 68-assertion bash suite (3 bash-specific meta-tests replaced with Python equivalents: exception hierarchy checks, dataclass structure checks, bash state compatibility checks).

**What was NOT changed**: bash originals (lib/reliability.sh, tests/test-reliability.sh), any file outside py/ tree (except Agents.md), no files in scripts/ or tests/ (bash originals)

**Verification**: mypy --strict: Success (0 issues). pytest: 65 passed. bash tests: 154/154 (reliability 68 + eval 53 + validation 10 + codebase-summary 23). dry-run: all passed. git diff --stat: clean (only py/auto_sdd/lib/reliability.py, py/tests/test_reliability.py, Agents.md).

## Questions?

See [ARCHITECTURE.md](./ARCHITECTURE.md) for deeper design rationale.
See [Brians-Notes/HANDOFF-PROMPT.md](./Brians-Notes/HANDOFF-PROMPT.md) for successor agent prompts.
