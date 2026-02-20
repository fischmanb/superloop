# Agents.md

> **For AI agents working on this codebase**
> Last updated: 2026-02-20
> Architecture: Multi-invocation, context-safe

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
optimized-256gb/
├── stages/           # One script per stage
│   ├── 01-plan.sh   # Spec → plan.json
│   ├── 02-build.sh  # plan.json → files
│   ├── 03-review.sh # files → review.json
│   └── 04-fix.sh    # review.json → fixed files
├── lib/             # Shared libraries
│   ├── common.sh    # curl, parsing, validation
│   ├── models.sh    # Model endpoint management
│   └── reliability.sh # Lock, backoff, state, truncation, cycle detection
└── framework/       # User-facing tools
    └── ai-dev       # Main CLI entry
```

## How to Modify

### Adding a Stage

1. Create `stages/05-newstage.sh`
2. Follow the pattern:
   - Read input from previous stage's JSON
   - Call model with fresh context
   - Write output to JSON
   - Return 0 on success, 1 on failure
3. Update `framework/ai-dev` to call new stage

### Modifying a Stage

1. Keep context budget under the limit (see table above)
2. Maintain JSON I/O format for chaining
3. Test in isolation: `./stages/02-build.sh < test-input.json`

### Changing Models

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

## State Management

State passes between stages via JSON files:

```
01-plan.sh    → plan.json
02-build.sh   ← plan.json → writes files
03-review.sh  ← files + spec → review.json
04-fix.sh     ← review.json → fixes files
```

Each stage is idempotent. Can restart from any point.

## Testing Changes

Run a single stage in isolation:

```bash
# Test plan stage
cat test-spec.md | ./stages/01-plan.sh
cat plan.json

# Test build stage (requires plan.json)
./stages/02-build.sh
ls -la src/

# Test review stage (requires built files)
./stages/03-review.sh
cat review.json
```

## Model Endpoints

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

## Shared Library: lib/reliability.sh

Both `scripts/build-loop-local.sh` and `scripts/overnight-autonomous.sh` source
`lib/reliability.sh` for shared reliability functions:

| Function | Purpose |
|----------|---------|
| `acquire_lock` / `release_lock` | PID-file lock with stale detection |
| `run_agent_with_backoff` | Exponential backoff retry for rate limits |
| `truncate_for_context` | Truncate large specs to Gherkin-only for context budget |
| `check_circular_deps` | DFS cycle detection on roadmap dependency graph |
| `write_state` / `read_state` / `clean_state` | JSON resume state persistence |
| `completed_features_json` | Build JSON array from bash array (with escaping) |
| `get_cpu_count` / `run_parallel_drift_checks` | Parallel drift checks (M3 Ultra) |

**Caller contract**: define `log`, `warn`, `success`, `error` before sourcing.
Set globals (`LOCK_FILE`, `PROJECT_DIR`, `STATE_DIR`, `STATE_FILE`) before calling.

## Testing

```bash
# Unit tests for lib/reliability.sh
./tests/test-reliability.sh

# Structural dry-run (no agent needed)
DRY_RUN_SKIP_AGENT=true ./tests/dry-run.sh

# Full dry-run (requires agent CLI + running model)
./tests/dry-run.sh
```

## Known Gaps

- `run_parallel_drift_checks` is defined but not yet wired into the independent build pass
- Resume doesn't skip already-built features (relies on roadmap ✅ status)
- No live integration testing yet — all validation is `bash -n` + unit tests

## Questions?

See [ARCHITECTURE.md](./ARCHITECTURE.md) for deeper design rationale.
