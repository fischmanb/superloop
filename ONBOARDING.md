# ONBOARDING.md

> **Read this file first.** It gives a fresh Claude instance everything needed to pick up work on `auto-sdd` with Brian.
>
> Last updated: 2026-03-01

> **⚠️ Per-response protocol**: Read and update `.onboarding-state` on every project-related response. See "Keeping This File Current" for full rules.

---

## What This Project Is

**auto-sdd** is a spec-driven development system that orchestrates autonomous Claude Code agents to build features from Gherkin specs. You write a roadmap of features. The loop picks the next one, hands it to a fresh Claude Code agent, validates the output (compile, test, drift check), commits, and moves on.

Forked from [AdrianRogowski/auto-sdd](https://github.com/AdrianRogowski/auto-sdd). Brian rewrote the runtime — adding reliability, crash recovery, test suites, cost tracking, and Claude Code CLI support. The original was a concept; this is the hardened version.

**Repo**: `https://github.com/fischmanb/auto-sdd`
**Local path**: `~/auto-sdd`
**Version**: 2.0.0
**License**: MIT

---

## Chat Session Permissions

Chat sessions (claude.ai with Desktop Commander or any equivalent tool or capability that provides filesystem or system access) must ask Brian for explicit permission before making any file changes, git commits, or GitHub operations. The only exceptions are `.onboarding-state` reads/writes and `ONBOARDING.md` reads/writes required by the onboarding state protocol. This applies to documentation edits, prompt files, script changes, and any other filesystem modification. Do not batch multiple changes into a single approval request in a way that obscures what's being changed — describe each change clearly.

**Merge/push rule**: Claude must never run `git merge` or `git push` in the same response where it presents verification results or proposes the action. The response must end with the request. The merge or push can only happen in a subsequent response after Brian's explicit approval in the intervening message. This creates a forced wait state that prevents inferred permission from context.

**Documentation-as-code discipline**: Documentation and protocol changes (ONBOARDING.md reconciliation excluded) carry the same ask-first requirement as code changes. Edits to the prompt engineering guide, Agents.md, README.md, CLAUDE.md, or any other documentation file require explicit permission before execution.

---

## Current State (as of 2026-02-28)

### What works

- **Build loop runs end-to-end.** Validated Feb 22, 2026: 2 features built autonomously against a React+TS+Vite app. 19 tests passing, TypeScript clean, drift auto-reconciled.
- **Reliability layer**: locking, exponential backoff, context truncation, cycle detection, crash recovery with `--resume`.
- **Resume state persistence**: resume.json committed to git after each successful feature build — survives crashes across runs (Round 21).
- **Nested session guard**: detects `CLAUDECODE` env var at startup, exits with clear instructions instead of hanging silently (Round 21).
- **Retry hardening**: 30-second minimum delay between retries regardless of failure type. Branch reuse on retry instead of creating orphan branches per attempt. Overnight script now has retry mechanism + credit exhaustion detection (Round 22).
- **Build log auto-rotation**: all output tee'd to `logs/build-{timestamp}.log` (Round 23).
- **Model logging per feature**: actual model used recorded in build summary JSON and human-readable table (Round 23).
- **Post-run branch cleanup**: merged `auto/chained-*` and `auto/independent-*` branches auto-deleted after build summary (Round 23).
- **NODE_ENV guard**: explicitly sets `NODE_ENV=development` before agent calls (Round 23).
- **Test suite**: 68 unit assertions (`test-reliability.sh`), 10 validation assertions (`test-validation.sh`), 23 codebase-summary assertions (`test-codebase-summary.sh`), 53 eval assertions (`test-eval.sh`), structural dry-run. **154 total assertions passing.**
- **Cost tracking**: `lib/claude-wrapper.sh` logs token/cost data as JSONL.
- **Build summary reports**: per-feature timing, test counts, token usage, model used, written to `logs/build-summary-{timestamp}.json`.
- **Git stash hardening**: dirty worktree can't cascade failures across features.
- **Credit exhaustion detection**: both scripts halt immediately when API credits run out instead of retrying doomed calls.
- **Topological sort + pre-flight**: shell-side Kahn's algorithm orders features by dependency, pre-flight summary with user confirmation before build starts.
- **Codebase summary injection**: each build agent receives a summary of existing components, type exports, import graph, and recent learnings from prior features. Prevents type redeclaration and repeated mistakes across features (Rounds 25-26, findings #11, #21, #23).

### What's next

1. **Rerun stakd 28-feature campaign** — First real validation with sidecar feedback loop active. Use existing `stakd/.specs/vision.md` and `stakd/.specs/roadmap.md`. Run on **Sonnet 4.6** (`BUILD_MODEL=claude-sonnet-4-6`). Run build loop with eval sidecar in parallel. Data from this run informs all future decisions.
2. **Post-campaign validation pipeline** — Multi-agent pipeline that boots the built app, browses it blind (Playwright), generates acceptance criteria from specs vs discovery, tests them, catalogs failures objectively, performs root cause analysis, and applies fixes through existing build gates. Auth-gated routes handled via QA test account (build-phase deliverable). Spec: `WIP/post-campaign-validation.md` (v0.3). Addresses the #1 gap: build loop validates features individually but never boots the full app.
3. **Local model integration** — replace cloud API with local LM Studio on Mac Studio
4. **Adaptive routing / parallelism** — only if data from 1-3 shows remaining sequential bottleneck justifies the complexity

### Remediation status

All remediation rounds (21-37) complete. **154 assertions passing.** See Agents.md for per-round details and git history for individual commits. This section is frozen — new work items go into Active Considerations while active and get pruned when done.

### Known gaps

- ~~No live integration testing~~ — **Addressed by post-campaign validation pipeline** (`WIP/post-campaign-validation.md`). Spec complete, implementation not started. Pipeline boots the app, browses via Playwright, validates features against specs, catalogs failures, and applies fixes.
- `run_parallel_drift_checks` defined but not wired into independent build pass
- Backend spec layer missing — no Gherkin equivalent for DB schemas, API contracts, migrations
- Agent self-assessment is unreliable (documented extensively in Agents.md)

---

## Active Considerations

> **⚠️ Per-response protocol**: Read and update `.onboarding-state` on every project-related response. No exceptions.

> What's next and what's in-flight. Priority stack is the execution plan; everything below it is context a fresh chat should pick up.

### Priority stack (updated 2026-02-28)

Ordered by efficiency gain per complexity added:

1. **stakd 28-feature campaign — v2 COMPLETE, v3 STALLED.**
   - **stakd-v2 (Sonnet 4.6)**: ✅ 28/28 features built. Post-campaign `npm run build` fails — client component (NewsCategoryFilter.tsx) transitively imports postgres via news.ts → db/index.ts. Same root cause as stakd-v1. Fix prompt drafted, pending execution.
   - **stakd-v3 (Haiku 4.5)**: ⏸️ Stalled at 11/28 features. Hung `claude` process (PID 94635) killed 2026-02-28. Build loop needs restart.
   - **Throughput finding**: Token speed does NOT translate to build speed. Haiku 2x faster tokens but only marginally faster builds (~16-18 min/feature both models) because npm install, TypeScript compile, tests, drift checks are fixed-cost CPU/disk-bound steps that dominate wall time. Model speed only affects agent thinking fraction. Parallelism across features matters more than per-feature model speed.
   - **Build logs**: Located at `stakd-v2/logs/build-*.log` and `stakd-v3/logs/build-*.log`. tee processes write them live. If `ls` or `cat` fail, the files still exist — search harder (check exact paths, use `find`, verify tee PID is alive).
   - **Agent push discipline**: Agents ignore "do NOT push" instructions 100% of the time across Rounds 32-34. Documented as expected behavior, not a bug to fix.
   - Round 35 merged to main and pushed to origin.
   - **Data snapshot**: `~/auto-sdd/campaign-results/` — central location for all campaign data and analysis. Structure:
     ```
     campaign-results/
       raw/
         v2-sonnet/       # git-log.txt, roadmap-snapshot.md, build logs, cost logs, evals
         v3-haiku/        # same structure
       reports/
         v2-sonnet/       # generated analysis (throughput, quality, cost breakdowns)
         v3-haiku/        # same structure
     ```
     After campaigns complete: copy final build logs, cost logs (`logs/cost-log.jsonl`), build summaries (`logs/build-summary-*.json`), and eval results into `raw/`. Generate reports from raw data into `reports/`. This folder is the single source of truth for campaign comparison.
2. **Post-campaign validation pipeline** — Multi-agent pipeline that boots the built app, browses it blind via Playwright, generates acceptance criteria from specs vs discovery, tests them, catalogs failures, performs root cause analysis, and fixes through existing build gates. Seven phases (0-5, with Phase 4 split into 4a Catalog + 4b RCA). Spec: `WIP/post-campaign-validation.md` (v0.3). Phase 0 includes auth bootstrap via QA test account (build-phase deliverable). Phase 2a classifies spec-vs-discovery discrepancies as FOUND/MISSING/PARTIAL/DRIFTED/UNEXPECTED. Milestones prioritized: Runtime Bootstrap → Discovery → AC Generation → Playwright Validation → Failure Catalog → RCA → Fix Agents. *Spec complete, implementation not started.*
3. **Local model integration** — Replace cloud API calls with local LM Studio endpoints on Mac Studio. The archived `archive/local-llm-pipeline/` system is reference material. *Not started.*
4. **Adaptive routing / parallelism** — Only if data from 1–3 shows remaining sequential bottleneck justifies the complexity. *Deprioritized.*

### Historical build estimator (designed, not yet built)

After at least one full campaign, a function will correlate t-shirt sizes from roadmap with actual metrics from `logs/build-summary-*.json` and write aggregate stats to `logs/estimation-model.json` (avg seconds, avg tokens, sample count, success rate per t-shirt size). Pre-flight then uses this to project total run cost/time. Self-correcting — updates running averages after each `write_build_summary()`. `MAX_FEATURES` becomes an optional backstop once estimator provides informed consent via real projections. Build after stakd campaign provides real data.

### Other active items

- **Learnings system design — Option C (2026-03-01)**: Constitutional "core learnings" file (curated, commonly read on fresh onboard, mix of types) + separate typed catalog files (comprehensive). Core entries duplicated in their proper type files — core is a self-contained read, not a pointer file. Standing design principles: (1) grepability — every entry greppable by ID, type, tag, date without parsing logic; (2) graph-readiness — format should make graph store transition a format conversion, not knowledge extraction. Relationship type schema must be defined before first entry — small set (~4-5 general types to keep graph sparse). All pruned knowledge from ONBOARDING.md active items must be preserved in the learnings system, not just git history. *Schema design phase — no implementation started.*
- **ONBOARDING.md maintenance rules (2026-03-01)**: Added in `a8d0674` but needs revision — first-response fresh onboard must stay read-only (no staleness sweep writes). Pruning logic: check before new writes, not during onboard. Archive destination for pruned items TBD (pending learnings system design).
- **Knowledge graph for workflow continuity (2026-02-28)**: Proposed as solution to cross-session context loss exposed by transcript isolation. Scope: personal workflow tool first (track entities/relationships across sessions), productize later. Real constraint is scope discipline. *Design phase — no implementation started.*

---

## Key Files — What to Read and When

| File | What it contains | When to read |
|------|-----------------|--------------|
| **ONBOARDING.md** (this file) | Full project context for a fresh chat | Always read first |
| **Agents.md** | Agent work log (Rounds 1-30), architecture reference, signal protocol, verification checklist, known gaps, process lessons | Before making ANY changes — this is the source of truth for what happened and what works |
| **README.md** | Public-facing docs: quick start, config, file structure, what works and what breaks | For understanding the user-facing narrative |
| **CLAUDE.md** | Instructions that Claude Code agents read automatically when invoked by the build loop | When modifying agent behavior or build prompts |
| **ARCHITECTURE.md** | Design decisions for the local LLM pipeline (system 2, archived) and context management philosophy | When working on the local model integration |
| **Brians-Notes/PROMPT-ENGINEERING-GUIDE.md** | Methodology for writing hardened agent prompts. Failure catalog and process lessons are in `.specs/learnings/agent-operations.md` | Before writing any new agent prompts |
| **WIP/post-campaign-validation.md** | Post-campaign validation pipeline spec (v0.3). Seven-phase multi-agent system for runtime validation, auth bootstrap, Playwright testing, failure cataloging, RCA, and automated fixes | When implementing or extending post-campaign validation |
| **lib/reliability.sh** | Shared runtime: lock, backoff, state, truncation, cycle detection (~594 lines) | When debugging build failures or modifying shared behavior |
| **lib/codebase-summary.sh** | Generates cross-feature context summary (component registry, type exports, import graph, learnings) | When modifying the summary format or debugging agent context issues |
| **lib/eval.sh** | Eval functions: mechanical checks, prompt generation, signal parsing, result writing | When modifying eval behavior or adding new eval signals |
| **lib/claude-wrapper.sh** | Wraps `claude` CLI, extracts text to stdout, logs cost data to JSONL | When debugging cost tracking or agent invocation |
| **scripts/build-loop-local.sh** | Main orchestration script (~2299 lines) | When modifying the build loop |
| **scripts/overnight-autonomous.sh** | Overnight automation variant (~1041 lines) | When modifying overnight runs |
| **scripts/eval-sidecar.sh** | Eval sidecar — runs alongside build loop, polls for commits, evaluates features (~354 lines) | When modifying eval behavior or running evals |
| **.env.local.example** | Full config reference (167 lines) | When setting up or changing config |

---

## Architecture in 60 Seconds

Two systems live in this repo:

**System 1 — Orchestration (active)**: `scripts/build-loop-local.sh` and `overnight-autonomous.sh` call Claude Code agents with a fresh context per feature. Each feature goes through: BUILD → COMPILE CHECK → TESTS → DRIFT CHECK → COMMIT. The shell validates between every agent step — no trust in self-assessment.

**System 2 — Local LLM pipeline (archived)**: Multi-stage pipeline (plan → build → review → fix) for locally-hosted models. Archived to `archive/local-llm-pipeline/`. Preserved for future LM Studio integration.

`lib/reliability.sh` serves System 1 only.

### Signal protocol

Agents communicate via grep-parseable signals — no JSON parsing, no eval on agent output:

```
FEATURE_BUILT: {name}          # Build agent success
SPEC_FILE: {path}              # Where the spec lives
SOURCE_FILES: {paths}          # What was produced
BUILD_FAILED: {reason}         # Build agent failure
NO_DRIFT / DRIFT_FIXED / DRIFT_UNRESOLVABLE   # Drift agent
REVIEW_CLEAN / REVIEW_FIXED / REVIEW_FAILED    # Review agent
```

### Branch strategies

- **chained**: each feature branches from previous (default for local)
- **independent**: all branch from base (for parallel comparison)
- **both**: runs chained then independent
- **sequential**: no branching, commit to current branch

---

## How to Verify Everything Works

```bash
cd ~/auto-sdd

# Requires bash 5+ (brew install bash). Scripts use #!/usr/bin/env bash
# so ./script works directly as long as Homebrew bash is in PATH (default after install).

# Syntax check all scripts
bash -n scripts/build-loop-local.sh
bash -n scripts/overnight-autonomous.sh
bash -n lib/reliability.sh
bash -n lib/validation.sh

# Unit tests
./tests/test-reliability.sh        # 68 assertions
./tests/test-validation.sh         # 10 assertions
./tests/test-codebase-summary.sh   # 23 assertions
./tests/test-eval.sh               # 53 assertions

# Structural dry-run (no agent/API needed)
DRY_RUN_SKIP_AGENT=true ./tests/dry-run.sh

# Full dry-run (requires claude CLI + ANTHROPIC_API_KEY)
./tests/dry-run.sh
```

---

## Agent Work Log Summary (Rounds 1-15)

Full details in `Agents.md`. Here's the arc:

| Round | What | Outcome |
|-------|------|---------|
| 1 | Initial reliability features | **Failed** — agent claimed implementation, wrote nothing |
| 2 | Review + fix Round 1 | Implemented features but left functions unwired |
| 3 | Extract lib + tests + hardening | **Major milestone** — `lib/reliability.sh`, 57-assertion test suite, dry-run |
| 4 | Cursor → Claude Code CLI swap | Clean swap, 57/57 tests pass |
| 5 | Fix broken grep comment-filter | Targeted fix, 57/57 tests pass |
| 6 | Fix `local` outside functions + MAX_FEATURES env key | 7 bare locals fixed, env fallback chain added |
| 7 | **End-to-end smoke test** | **Success** — 2 features built autonomously, 19 tests, drift reconciled |
| 8 | Fix agent permissions | `--dangerously-skip-permissions` + settings.local.json |
| 9 | Add cost/token tracking wrapper | `lib/claude-wrapper.sh`, JSONL logging |
| 10 | Allow seed data in build prompts | Replaced anti-mock rules with permissive seed data language |
| 11 | Diagnose 78% build failure rate | Root cause: credit exhaustion, not context loss |
| 12 | Add decision comments to build prompts | Agents now leave WHY comments |
| 13 | Git stash hardening + credit exhaustion detection | 5 stash guards, early halt on billing errors |
| 14 | Investigate adaptive routing | Investigation only — results lost to compaction, re-analyzed in Round 16 |
| 15 | Build summary report | Per-feature metrics, JSON + human-readable output |
| 16 | ONBOARDING.md + maintenance protocol + adaptive routing analysis | Created onboarding file, mechanical state-tracking protocol, full edge case analysis of adaptive routing → deprioritized in favor of codebase summary + topo sort |
| 17 | Topological sort + pre-flight summary | `emit_topo_order()` in reliability.sh, `build_feature_prompt()` + `show_preflight_summary()` in build-loop-local.sh, 10 new tests (68 total) |
| 18 | Overnight script parity for topo sort | `build_feature_prompt_overnight()` + topo iteration in overnight-autonomous.sh |
| 19 | stakd map page fix + build campaign triage | Root cause: "use client" on server component. DealMapLoader wrapper (42d7a3a). 28 features built. |
| 20 | Build loop failure investigation | 37 findings across 4 batches. Prioritized remediation plan. |
| 21 | Resume state persistence + nested session guard | `git add -f resume.json` after each feature. CLAUDECODE env var guard. |
| 22 | Retry hardening | 30s min delay, branch reuse on retry. Overnight retry mechanism + credit exhaustion ported. |
| 23 | Operational hygiene | Build log rotation, model logging per feature, post-run branch cleanup, NODE_ENV guard. |
| 24 | stakd CLAUDE.md + learnings | Next.js 15 rules in CLAUDE.md. Primary learnings catalog populated. Learnings consolidated. |
| 25 | Codebase summary generation | `lib/codebase-summary.sh` + 23-assertion test suite. Scans project dir, emits component/type/import/learnings summary. |
| 26 | Codebase summary wiring | Injected summary into `build_feature_prompt()` and `build_feature_prompt_overnight()` in both scripts. |
| 27 | Eval function library | `lib/eval.sh` — mechanical eval, prompt generation, signal parsing, result writing. 53-assertion test suite. |
| 28 | Eval sidecar script + build loop integration | `scripts/eval-sidecar.sh` — standalone sidecar polling for commits, running evals, aggregating campaign summary. 28b: auto-launch from both build scripts, `EVAL_AGENT=true` default. |
| 29 | Eval sidecar cooperative drain shutdown | Sentinel file triggers graceful queue drain. Both build scripts manage sidecar lifecycle. |
| 30 | Mechanical validation gates | Three non-blocking gates: test count regression detection, dead export detection, static analysis/lint. Default `POST_BUILD_STEPS=test,dead-code,lint`. |
| 31 | Retry resilience | Three bugs from failed stakd-v2 campaign: git clean exclusions, signal fallback detection, cascade failure fix. 68/68 tests passing. |
| 31.1 | Retry prompt signal hardening | Parameterized retry prompt with actual feature name, emphatic CRITICAL signal block as final prompt content. |
| 32 | Shell portability | All 17 scripts converted from `#!/bin/bash` to `#!/usr/bin/env bash`. |
| 33 | PROJECT_DIR resolution | `PROJECT_DIR` resolved to absolute path via `realpath`/fallback. |
| 34 | claude-wrapper.sh rewrite | Removed `set -e`, stderr to file, unset CLAUDECODE, MAIN_BRANCH rejects `auto/*`, SCRIPT_DIR path fix. |
| 35 | Sidecar + model log fixes | Sidecar source/dedup/health fixes, model log jq cosmetic fix. 154 assertions. Merged `dbf2997`. |
| 37 | Sidecar feedback loop | Three functions: read eval feedback, track repeated mistakes, inject into build prompt. All 4 success paths tracked. Advisory only. 154 assertions. Merged `cecf7bb`. |

**Key lesson that repeats**: Agent self-assessments are unreliable. Always verify with grep, `bash -n`, and tests. Never trust the agent's narrative summary.

---

## Process Lessons (Hard-Won)

See `.specs/learnings/agent-operations.md` for the full consolidated catalog. All process lessons, failure modes, and session discipline rules are maintained there as the single source of truth.

---

## Working with Brian

- Direct, no-bullshit communicator. Skip preamble and qualifiers.
- 12+ years product management experience in AI/ML, e-commerce, fintech (Walmart, AmEx, startups).
- Deep technical understanding — he reads the code and verifies claims.
- The `stakd/` directory inside the repo is a separate project (Traded.co clone). It has its own `.git`, `.specs/`, and `CLAUDE.md`. Don't conflate them.
- Brian pushes to GitHub manually. Agents should commit locally but not push.

---

## Quick Reference: Common Tasks

**Run the build loop against a project:**
```bash
cd ~/auto-sdd
PROJECT_DIR=/path/to/project MAX_FEATURES=4 ./scripts/build-loop-local.sh
```

**Resume after a crash:**
```bash
./scripts/build-loop-local.sh --resume
```

**Check what's on GitHub vs local:**
```bash
git fetch origin && git log --oneline main..origin/main  # remote ahead
git log --oneline origin/main..main                       # local ahead
git diff origin/main --stat                                # file differences
```

**Clean up orphan remote branches:**
```bash
git branch -r | grep claude/ | while read b; do git push origin --delete "${b#origin/}"; done
```

---

## File Tree (annotated)

```
auto-sdd/
├── scripts/
│   ├── build-loop-local.sh        # Main build loop (2299 lines)
│   ├── overnight-autonomous.sh    # Overnight variant (1041 lines)
│   ├── eval-sidecar.sh            # Eval sidecar (354 lines)
│   ├── nightly-review.sh          # Extract learnings from commits
│   ├── generate-mapping.sh        # Auto-generate .specs/mapping.md
│   ├── setup-overnight.sh         # Install macOS launchd jobs
│   └── uninstall-overnight.sh     # Remove launchd jobs
├── lib/
│   ├── reliability.sh             # Shared runtime (594 lines)
│   ├── codebase-summary.sh        # Cross-feature context summary generation
│   ├── eval.sh                    # Eval functions (mechanical + agent)
│   ├── claude-wrapper.sh          # Claude CLI wrapper + cost logging
│   └── validation.sh              # YAML frontmatter validation
├── tests/
│   ├── test-reliability.sh        # 68 unit assertions
│   ├── test-validation.sh         # 10 unit assertions
│   ├── test-codebase-summary.sh   # 23 unit assertions
│   ├── test-eval.sh              # 53 unit assertions
│   ├── dry-run.sh                 # Structural integration test
│   └── fixtures/dry-run/          # Test fixtures
├── .specs/                        # Spec-driven development specs (templates)
├── .claude/commands/              # Claude Code slash commands
├── archive/local-llm-pipeline/    # Archived local LLM system
├── Brians-Notes/
│   └── PROMPT-ENGINEERING-GUIDE.md  # Prompt methodology + failure catalog
├── WIP/                             # Work-in-progress specs and designs
│   └── post-campaign-validation.md  # Post-campaign validation pipeline spec (v0.3)
├── ONBOARDING.md                  # ← YOU ARE HERE
├── CLAUDE.md                      # Agent instructions (read by Claude Code automatically)
├── Agents.md                      # Agent work log + architecture + verification checklist
├── README.md                      # Public-facing documentation
├── ARCHITECTURE.md                # Design decisions (local LLM pipeline)
├── VERSION                        # 2.0.0
├── .onboarding-state              # State tracking for update protocol (local only, gitignored)
└── .env.local.example             # Full config reference
```

---

## Keeping This File Current

This file is useless if it's stale. Context loss — compaction, crashes, new chats — happens without warning. The update protocol is designed around that reality and enforced mechanically.

### Reconciliation after agent rounds

When a Claude Code agent completes a round and updates Agents.md, the chat session that triggered or reviewed that round is responsible for reconciling ONBOARDING.md before the session ends. This is a process rule, not a mechanical check — the chat is already reading Agents.md to verify the agent's work, so the marginal cost is near zero. Without this, Agents.md can drift from ONBOARDING.md silently: the hash stays clean, the interval check passes, and the next fresh chat onboards with stale context.

### Enforcement mechanism: `.onboarding-state`

A JSON state file at `~/auto-sdd/.onboarding-state` tracks update status:

```json
{
  "last_check_ts": "<ISO timestamp of last reconciliation>",
  "last_check_hash": "<md5 of ONBOARDING.md at last full read>",
  "prompt_count": 0,
  "pending_captures": ["item 1", "item 2"]
}
```

**Every project-related response** (silent, no meta-commentary):
1. Read `.onboarding-state`, increment `prompt_count`
2. If the current exchange has something that might need capturing, append a one-liner to `pending_captures`, flag inline with 📌, and **write the state file immediately in the same response** (not deferred to next response — protects against context compaction)
3. Write state file back

**At interval (prompt_count >= 4)**:
1. Hash ONBOARDING.md, compare to `last_check_hash`
2. If hash matches AND `pending_captures` is empty → reset counter, done
3. If hash differs → another agent or Brian edited the file. Read only the **Active Considerations** section (grep for section boundaries, ~15 lines). Note what changed.
4. If `pending_captures` is non-empty → read only **Active Considerations**, reconcile the buffer into it, flush `pending_captures`, update hash
5. Reset counter

**Privacy check on every read**: When reading any portion of ONBOARDING.md (interval or fresh onboard), if anything private, non-project-related, or sensitive (personal details, credentials, API keys, account info) is detected, immediately report all findings to Brian concisely. Do not silently correct — surface it.

**Fresh onboard (state file missing or `last_check_ts` > 24h stale)**:
- Full read of ONBOARDING.md. This is the only case where the whole file gets read.
- Read `.specs/learnings/agent-operations.md` — the consolidated failure catalog and process lessons. These hard-won failure modes repeat if not internalized at session start.
- **Flush stale captures**: If `pending_captures` is non-empty, reconcile them into the **Active Considerations** section immediately.
- **Staleness sweep**: Check each item in Active Considerations and Other active items. If an item is clearly done (has ✅, "merged", "complete", "done", or describes work that's already in the priority stack), remove it. This catches items that were marked done but never pruned by the session that completed them.
- Report status. No other file writes, no commits, no edits beyond protocol housekeeping (flushes, pruning).

**Continuing session (state file < 24h, recognizably the same work context)**:
- Read/write `.onboarding-state` per the per-response protocol. That's it.
- Do NOT re-read the full ONBOARDING.md. The session already has context.
- If the interval check fires and `pending_captures` is non-empty, read only the **Active Considerations** section header boundaries (~15 lines) to reconcile. Don't read the whole file.

**Cost profile**: 95% of responses = read/write a 5-line file (negligible). Every ~4th response = one md5 + maybe 15 lines (minimal). New chat after a break = full read (appropriate).

### Two triggers

**1. Significance trigger (immediate):** If there is even a question of whether the current exchange could matter to the next chat, append to `pending_captures` and flag with 📌. Don't deliberate. The cost of a false positive is near zero.

This includes:
- Decisions and actions (new files, resolved gaps, changed priorities)
- **Topics under active consideration** — directions being weighed, open questions, things Brian raised that haven't resolved yet
- New process lessons or failure modes observed
- Anything Brian says that reframes the project or its priorities

**2. Interval trigger (every 3-5 prompts):** The mechanical check described above. Catches slow drift where no single message feels significant but several in a row shift the picture.

### What to capture

Not just outcomes. The **Active Considerations** section exists specifically for in-progress thinking. A fresh chat that knows what was being discussed is 10x more useful than one that only knows what was decided.

### Maintenance rules (preventing staleness)

These are as important as the capture rules. Capturing without pruning is how the file got bloated in the first place.

**1. Completion pruning (same-session):** When a session marks something ✅ done, it removes the full item from Active Considerations in that same session. Replace it with a one-liner summary that stays for exactly one cycle (so the next fresh chat sees what just finished), then the next fresh onboard's staleness sweep removes the one-liner.

**2. No duplication across sections:** If something is in the priority stack, it does not also get a bullet in "Other active items." One canonical location per item. The priority stack is for sequenced execution items. "Other active items" is for things that don't have a clear sequence position (ongoing processes, design explorations, unresolved questions).

**3. Remediation section is frozen:** The remediation checklist is historical and compressed. New work goes into Active Considerations while active, gets pruned per rule 1 when done. Nothing gets appended to the remediation section.

**4. Fresh onboard staleness sweep:** Every fresh onboard (full read) includes checking Active Considerations for completed items. Anything with ✅, "merged," "complete," "done," or that describes work already captured in the priority stack gets removed. This is the safety net for items that slipped through same-session pruning.

**5. Priority stack hygiene:** When a priority stack item is fully complete (not just "in progress"), move it out of the numbered list. Add a one-line "Recently completed" entry below the stack if the next session needs to know. The stack should only contain actionable next steps.

### How to update

1. Edit this file
2. `git add ONBOARDING.md && git commit -m "docs: update ONBOARDING.md — <what changed>"`
3. Ask Brian before pushing

### How to verify it's working

```bash
# Check update frequency — should show commits every few sessions
git log --oneline ONBOARDING.md

# Check state file — prompt_count should increment, pending_captures should flush periodically
cat ~/auto-sdd/.onboarding-state

# Spot check — ask a fresh chat "what are the active considerations for auto-sdd?"
# If the answer is stale, the protocol failed.
```

### Scope

This protocol is maintained **exclusively through chat sessions** (claude.ai with Desktop Commander). Claude Code build-loop agents must not read, write, or update `.onboarding-state` or ONBOARDING.md. See CLAUDE.md for the agent-facing rule.

### What NOT to put here

- Implementation details that belong in `Agents.md` (per-round specifics, line-level changes)
- Prompt methodology that belongs in `Brians-Notes/PROMPT-ENGINEERING-GUIDE.md`
- Agent instructions that belong in `CLAUDE.md`

This file is the **orientation layer**. It tells you what exists and where to find it, what's active, and what's being considered. The other files contain the depth.

---

_To pick up work: read this file, then read `Agents.md` for current state and verification checklist. Everything else is reachable from those two files._
