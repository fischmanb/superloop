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

### Round 8: Fix agent permissions (branch: claude/fix-agent-permissions)

**What was asked**: Fix permissions so spawned Claude Code agents can write files autonomously.

**What was changed**:
- scripts/build-loop-local.sh: added --dangerously-skip-permissions to agent_cmd()
- scripts/overnight-autonomous.sh: same change
- .claude/settings.local.json: set permissions.allow to ["*"]

**What was NOT changed**: No other files. No packages installed. No dependencies added.

**Verification**: bash -n passes on both scripts, grep confirms flag present, git diff --stat shows exactly 4 files

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
│   ├── test-reliability.sh     # Unit tests for lib/reliability.sh (57 assertions)
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
# Unit tests for lib/reliability.sh (57 assertions, all passing)
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

1. **Agent self-assessments are unreliable.** Round 1 agent described bugs in code it never wrote. Always verify with grep/tests.
2. **"Defined but never called" is the most common agent failure mode.** All 3 rounds had at least one instance. After adding any function, grep for call sites.
3. **`bash -n` is necessary but insufficient.** It catches syntax errors but not unreachable code or wrong function names. The grep check in `test-reliability.sh` catches the most common failure.
4. **Independent verification catches what self-assessment misses.** This is the same principle as the codebase's own drift detection (Layer 1 self-check vs Layer 2 cross-check).
5. **Agents are better at verification than comprehensive implementation.** The skill gradient: verification > implementation > self-assessment.

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

## Questions?

See [ARCHITECTURE.md](./ARCHITECTURE.md) for deeper design rationale.
See [Brians-Notes/HANDOFF-PROMPT.md](./Brians-Notes/HANDOFF-PROMPT.md) for successor agent prompts.
