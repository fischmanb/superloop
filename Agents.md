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

### Round 2: Review + Fix (branch: claude/review-agent-updates-uvKGj)

**What was asked**: Review round 1's claims. Fix what's missing.

**What actually happened**: Verified round 1 was false, then actually implemented all 6 features inline in both scripts. Found and fixed a latent bug (`fail` called instead of `error` in overnight-autonomous.sh). But made the same class of error — defined `run_parallel_drift_checks` without wiring it in. Also duplicated ~100 lines between both scripts.

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
| Resume doesn't skip already-built features | `read_state` sets `RESUME_INDEX` to skip the loop counter, but if the roadmap wasn't updated to `✅` before the crash, the feature gets rebuilt. | After `read_state`, check `BUILT_FEATURE_NAMES` array against the current feature name before calling the agent. |
| No live integration test | `dry-run.sh` full mode requires `agent` CLI + running model. All current validation is structural (bash -n, unit tests, dry-run). | Run `./tests/dry-run.sh` with a real agent endpoint. |
| `write_state` JSON escaping is sed-based | Works for typical feature names like `Auth: Signup`. Breaks on names with `"`, `\`, or newlines. | Use `jq` if available, fall back to current sed approach. The `completed_features_json()` function already handles `"` and `\` properly — it's the `branch_strategy` and `current_branch` fields in `write_state` that use raw interpolation. |
| `eval` used for BUILD_CMD/TEST_CMD | Intentional — these can contain pipes. Values come from `.env.local` (user-controlled, not agent-controlled). | Not a fix needed — just document the trust boundary. |
| `lib/common.sh` and `lib/models.sh` are orphaned | These 160 lines are from the stages/ infrastructure. Neither main script sources them. | Either delete them or wire them into the stages/ scripts if those are still used. |

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
│   ├── overnight-autonomous.sh # Overnight automation with Slack/Jira (790 lines)
│   └── generate-mapping.sh     # Auto-generate .specs/mapping.md from frontmatter
├── lib/                        # Shared libraries
│   ├── reliability.sh          # Lock, backoff, state, truncation, cycle detection (385 lines)
│   ├── common.sh               # curl, parsing, validation (UNUSED by main scripts)
│   └── models.sh               # Model endpoint management (UNUSED by main scripts)
├── stages/                     # Multi-invocation pipeline (local LLM infrastructure)
│   ├── 01-plan.sh              # Spec → plan.json
│   ├── 02-build.sh             # plan.json → files
│   ├── 03-review.sh            # files → review.json
│   └── 04-fix.sh               # review.json → fixed files
├── framework/                  # User-facing tools
│   └── ai-dev                  # Main CLI entry for stages/
├── tests/                      # Test suite
│   ├── test-reliability.sh     # Unit tests for lib/reliability.sh (41 assertions)
│   ├── dry-run.sh              # Integration test for build-loop-local.sh
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

2. **Local LLM pipeline** (`stages/`, `framework/`, `lib/common.sh`, `lib/models.sh`)
   - Uses locally-hosted models on Mac Studio (Qwen, DeepSeek)
   - Fresh context per stage (plan → build → review → fix)
   - This was the initial prototype; unclear if still actively used

`lib/reliability.sh` serves system 1 only. `lib/common.sh` and `lib/models.sh` serve system 2 only.

## How to Modify

### Adding a Stage (system 2)

1. Create `stages/05-newstage.sh`
2. Follow the pattern:
   - Read input from previous stage's JSON
   - Call model with fresh context
   - Write output to JSON
   - Return 0 on success, 1 on failure
3. Update `framework/ai-dev` to call new stage

### Modifying a Stage (system 2)

1. Keep context budget under the limit (see table above)
2. Maintain JSON I/O format for chaining
3. Test in isolation: `./stages/02-build.sh < test-input.json`

### Modifying Orchestration Scripts (system 1)

1. Shared functions go in `lib/reliability.sh`
2. Script-specific logic stays in the script
3. Source `lib/reliability.sh` after defining `log`, `warn`, `success`, `error`
4. Run `bash -n` on both scripts after changes
5. Run `./tests/test-reliability.sh` to verify shared functions
6. Run `DRY_RUN_SKIP_AGENT=true ./tests/dry-run.sh` for integration

### Changing Models (system 2)

Edit `lib/models.sh`:
```bash
BUILDER_URL="http://127.0.0.1:8080"
REVIEWER_URL="http://127.0.0.1:8081"
DRIFT_URL="http://127.0.0.1:8082"
```

## Common Pitfalls

**DON'T**: Increase context sizes to "fit more"
**DO**: Split into more stages if needed

**DON'T**: Merge stages to reduce HTTP calls
**DO**: Keep stages separate for crispness

**DON'T**: Parse model output with regex alone
**DO**: Use delimiters + JSON fallback (see `lib/common.sh`)

**DON'T**: Assume model output is valid
**DO**: Validate JSON, check file existence, handle errors

**DON'T**: Define a function without verifying it's called
**DO**: After adding any function, `grep` for call sites in both scripts

## State Management

### Stages (system 2)

State passes between stages via JSON files:

```
01-plan.sh    → plan.json
02-build.sh   ← plan.json → writes files
03-review.sh  ← files + spec → review.json
04-fix.sh     ← review.json → fixes files
```

Each stage is idempotent. Can restart from any point.

### Orchestration (system 1)

State for resume capability:

```
.sdd-state/resume.json — JSON with feature_index, branch_strategy, completed_features, current_branch
```

Written atomically (mktemp + mv). Read with awk (no jq dependency).

## Model Endpoints (system 2)

| Endpoint | Purpose | Health Check |
|----------|---------|--------------|
| `:8080/v1/chat/completions` | Builder | `curl :8080/health` |
| `:8081/v1/chat/completions` | Reviewer | `curl :8081/health` |
| `:8082/v1/chat/completions` | Drift/Fix | `curl :8082/health` |

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
| `write_state` / `read_state` / `clean_state` | JSON resume state persistence | build-loop only |
| `completed_features_json` | Build JSON array from bash array (with escaping) | build-loop only |
| `get_cpu_count` | Detect CPU count (nproc/sysctl) | build-loop only |
| `run_parallel_drift_checks` | Parallel drift checks (M3 Ultra) | build-loop (independent pass) |

**Caller contract**: define `log`, `warn`, `success`, `error` before sourcing (or use fallbacks).
Set globals (`LOCK_FILE`, `PROJECT_DIR`, `STATE_DIR`, `STATE_FILE`) before calling relevant functions.

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
# Unit tests for lib/reliability.sh (41 assertions, all passing)
./tests/test-reliability.sh

# Structural dry-run (no agent needed)
DRY_RUN_SKIP_AGENT=true ./tests/dry-run.sh

# Full dry-run (requires agent CLI + running model)
./tests/dry-run.sh
```

## Known Gaps

- Resume doesn't skip already-built features (relies on roadmap status being updated before crash)
- No live integration testing — all validation is `bash -n` + unit tests + structural dry-run
- `lib/common.sh` and `lib/models.sh` are orphaned (not sourced by main scripts)
- `write_state` branch/strategy fields use raw string interpolation (fine for typical values)

## Process Lessons (for humans and agents)

1. **Agent self-assessments are unreliable.** Round 1 agent described bugs in code it never wrote. Always verify with grep/tests.
2. **"Defined but never called" is the most common agent failure mode.** All 3 rounds had at least one instance. After adding any function, grep for call sites.
3. **`bash -n` is necessary but insufficient.** It catches syntax errors but not unreachable code or wrong function names. The grep check in `test-reliability.sh` catches the most common failure.
4. **Independent verification catches what self-assessment misses.** This is the same principle as the codebase's own drift detection (Layer 1 self-check vs Layer 2 cross-check).
5. **Agents are better at verification than comprehensive implementation.** The skill gradient: verification > implementation > self-assessment.

## Verification Checklist (after any agent work)

```bash
# 1. Syntax check
bash -n scripts/build-loop-local.sh && bash -n scripts/overnight-autonomous.sh && bash -n lib/reliability.sh

# 2. Unit tests
./tests/test-reliability.sh

# 3. Structural dry-run
DRY_RUN_SKIP_AGENT=true ./tests/dry-run.sh

# 4. Check functions are called (not just defined)
grep -n "function_name" scripts/*.sh | grep -v '^\s*#'

# 5. Check for orphaned code
grep -c "source.*common.sh" scripts/*.sh  # Should be 0 (orphaned)
grep -c "source.*reliability.sh" scripts/*.sh  # Should be 2
```

## Questions?

See [ARCHITECTURE.md](./ARCHITECTURE.md) for deeper design rationale.
See [Brians-Notes/HANDOFF-PROMPT.md](./Brians-Notes/HANDOFF-PROMPT.md) for successor agent prompts.
