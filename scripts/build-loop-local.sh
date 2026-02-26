#!/bin/bash
# build-loop-local.sh
# Run /build-next in a loop locally. No git remote, no push, no PRs.
# Use when you want to build roadmap features without connecting to a remote.
#
# Usage:
#   ./scripts/build-loop-local.sh
#   MAX_FEATURES=5 ./scripts/build-loop-local.sh
#   BRANCH_STRATEGY=both ./scripts/build-loop-local.sh
#   ./scripts/build-loop-local.sh --resume    # Continue from last crash
#
# CONFIG: set MAX_FEATURES, MAX_RETRIES, BUILD_CHECK_CMD, BRANCH_STRATEGY in .env.local
# or pass in env. Command-line env vars override .env.local (e.g. MAX_FEATURES=3 ./script).
#
# BASE_BRANCH: Branch to create feature branches from (default: current)
#   - Unset or empty: Use current branch — checkout your branch, run script, done.
#   - develop, main: Use that branch instead.
#   Workflow: git checkout my-branch && ./scripts/build-loop-local.sh
#   Examples: BASE_BRANCH=develop  BASE_BRANCH=main
#
# BRANCH_STRATEGY: How to handle branches (default: chained)
#   - chained: Each feature branches from the previous feature's branch
#              (Feature #2 has Feature #1's code even if not merged)
#   - independent: Each feature builds in a separate git worktree from BASE_BRANCH
#                  (Features are isolated, no shared code until merged)
#   - both: Run chained first (full build), then rebuild each feature
#           independently from BASE_BRANCH (sequential, not parallel)
#   - sequential: All features on one branch (original behavior)
#
# BUILD_CHECK_CMD: command to verify the build after each feature.
#   Defaults to auto-detection (TypeScript → tsc, Python → pytest, etc.)
#   Set to "skip" to disable build checking.
#   Examples:
#     BUILD_CHECK_CMD="npx tsc --noEmit"
#     BUILD_CHECK_CMD="npm run build"
#     BUILD_CHECK_CMD="python -m py_compile main.py"
#     BUILD_CHECK_CMD="cargo check"
#     BUILD_CHECK_CMD="skip"
#
# DRIFT_CHECK: whether to run spec↔code drift detection after each feature.
#   Defaults to "true". Set to "false" to disable.
#   When enabled, a SEPARATE agent invocation reads the spec and source files
#   after the build agent commits, comparing them with fresh context.
#   This catches mismatches the build agent missed (fox-guarding-henhouse problem).
#
# MAX_DRIFT_RETRIES: how many times to retry fixing drift (default: 1).
#   If drift is found, the drift agent auto-fixes by updating specs.
#   If the fix breaks the build, it retries up to this many times.
#
# TEST_CHECK_CMD: command to run the test suite after each feature.
#   Defaults to auto-detection (npm test, pytest, cargo test, go test, etc.)
#   Set to "skip" to disable test checking.
#   Examples:
#     TEST_CHECK_CMD="npm test"
#     TEST_CHECK_CMD="npx vitest run"
#     TEST_CHECK_CMD="pytest"
#     TEST_CHECK_CMD="cargo test"
#     TEST_CHECK_CMD="skip"
#
# POST_BUILD_STEPS: comma-separated list of extra steps after build+drift.
#   Each agent-based step runs in a FRESH context window.
#   Available steps:
#     test          - Run test suite (shell cmd, uses TEST_CHECK_CMD)
#     code-review   - Agent reviews code quality (fresh context)
#   Note: drift check is controlled separately via DRIFT_CHECK.
#   Default: "test"
#   Examples:
#     POST_BUILD_STEPS="test"                  # Just tests (default)
#     POST_BUILD_STEPS="test,code-review"      # Tests + quality review
#     POST_BUILD_STEPS=""                       # Skip all post-build steps
#
# MODEL SELECTION: which AI model to use for each agent invocation.
#   Each step gets its own fresh context window — choose the model per step.
#   Leave empty to use the Cursor CLI default.
#   Run `agent --list-models` to see available models.
#
#   AGENT_MODEL       - Default model for ALL agent steps (fallback)
#   BUILD_MODEL       - Model for main build agent (/build-next → /spec-first --full)
#   RETRY_MODEL       - Model for retry attempts (fixing build/test failures)
#   DRIFT_MODEL       - Model for catch-drift agent
#   REVIEW_MODEL      - Model for code-review agent
#
#   Examples:
#     AGENT_MODEL="sonnet-4.5"                    # Use Sonnet for everything
#     BUILD_MODEL="opus-4.6-thinking"             # Opus for main build
#     DRIFT_MODEL="gemini-3-flash"                # Cheap model for drift checks
#     REVIEW_MODEL="sonnet-4.5-thinking"          # Thinking model for reviews

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${PROJECT_DIR:-$(dirname "$SCRIPT_DIR")}"

# Load .env.local but don't overwrite vars already set (command-line wins over .env.local)
if [ -f "$PROJECT_DIR/.env.local" ]; then
    while IFS= read -r line || [ -n "$line" ]; do
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        [[ "$line" =~ ^[[:space:]]*$ ]] && continue
        if [[ "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
            key="${BASH_REMATCH[1]}"
            [[ -n "${!key+x}" ]] && continue
            value="${BASH_REMATCH[2]}"
            value="${value%\"}"; value="${value#\"}"
            value="${value%\'}"; value="${value#\'}"
            export "$key=$value"
        fi
    done < "$PROJECT_DIR/.env.local"
fi

# ── Logging ───────────────────────────────────────────────────────────────
log() { echo "[$(date '+%H:%M:%S')] $1"; }
success() { echo "[$(date '+%H:%M:%S')] ✓ $1"; }
warn() { echo "[$(date '+%H:%M:%S')] ⚠ $1"; }
error() { echo "[$(date '+%H:%M:%S')] ✗ $1"; }

# ── Source shared reliability library ─────────────────────────────────────
source "$SCRIPT_DIR/../lib/reliability.sh"

# ── File locking (concurrency protection) ──────────────────────────────────
LOCK_DIR="/tmp"
LOCK_FILE="${LOCK_DIR}/sdd-build-loop-$(echo "$PROJECT_DIR" | tr '/' '_' | tr ' ' '_').lock"

acquire_lock

# ── Resume capability ──────────────────────────────────────────────────────
STATE_DIR="$PROJECT_DIR/.sdd-state"
STATE_FILE="$STATE_DIR/resume.json"
ENABLE_RESUME="${ENABLE_RESUME:-true}"
RESUME_MODE=false

# Parse --resume flag
for arg in "$@"; do
    if [ "$arg" = "--resume" ]; then
        RESUME_MODE=true
    fi
done

# write_state, read_state, completed_features_json, clean_state
# are provided by lib/reliability.sh

# Handle --resume
RESUME_START_INDEX=0
if [ "$RESUME_MODE" = true ]; then
    if read_state; then
        if [ "$RESUME_STRATEGY" != "${BRANCH_STRATEGY}" ]; then
            warn "Branch strategy changed (was: $RESUME_STRATEGY, now: $BRANCH_STRATEGY) — resetting resume state"
            clean_state
        else
            RESUME_START_INDEX=$RESUME_INDEX
            log "Resuming from feature index $RESUME_START_INDEX (branch: ${RESUME_BRANCH:-unknown})"
            if [ -n "$RESUME_BRANCH" ]; then
                LAST_FEATURE_BRANCH="$RESUME_BRANCH"
            fi
        fi
    else
        warn "No resume state found at $STATE_FILE — starting from beginning"
    fi
fi

MAX_FEATURES="${MAX_FEATURES:-${MAX_FEATURES_PER_RUN:-25}}"
MAX_RETRIES="${MAX_RETRIES:-1}"
MIN_RETRY_DELAY="${MIN_RETRY_DELAY:-30}"
BRANCH_STRATEGY="${BRANCH_STRATEGY:-chained}"
DRIFT_CHECK="${DRIFT_CHECK:-true}"
MAX_DRIFT_RETRIES="${MAX_DRIFT_RETRIES:-1}"
POST_BUILD_STEPS="${POST_BUILD_STEPS:-test}"
PARALLEL_VALIDATION="${PARALLEL_VALIDATION:-false}"

# Model selection (per-step overrides with AGENT_MODEL fallback)
AGENT_MODEL="${AGENT_MODEL:-}"
BUILD_MODEL="${BUILD_MODEL:-}"
RETRY_MODEL="${RETRY_MODEL:-}"
DRIFT_MODEL="${DRIFT_MODEL:-}"
REVIEW_MODEL="${REVIEW_MODEL:-}"

# ── Robust signal parsing ─────────────────────────────────────────────────
# Extracts the LAST occurrence of a signal from agent output.
# Handles values containing colons, preserves internal whitespace,
# trims leading/trailing whitespace only.
# Usage: parse_signal "SIGNAL_NAME" "$output"
parse_signal() {
    local signal_name="$1"
    local output="$2"
    echo "$output" | awk -v sig="^${signal_name}:" '$0 ~ sig {
        val = $0
        sub(/^[^:]*:/, "", val)       # Remove everything up to and including first colon
        sub(/^[[:space:]]+/, "", val)  # Trim leading whitespace
        sub(/[[:space:]]+$/, "", val)  # Trim trailing whitespace
        last = val
    } END { print last }'
}

# ── Required signal validation ──────────────────────────────────────────────
# Validates that agent output contains all required signals after a build.
# Returns 0 if all required signals are present, 1 otherwise.
# Usage: validate_required_signals "$build_result"
validate_required_signals() {
    local build_result="$1"
    local feature_name spec_file

    feature_name=$(parse_signal "FEATURE_BUILT" "$build_result")
    spec_file=$(parse_signal "SPEC_FILE" "$build_result")

    if [ -z "$feature_name" ]; then
        warn "Missing required signal: FEATURE_BUILT"
        return 1
    fi

    if [ -z "$spec_file" ]; then
        warn "Missing required signal: SPEC_FILE (needed for drift check)"
        return 1
    fi

    if [ ! -f "$spec_file" ]; then
        warn "SPEC_FILE does not exist on disk: $spec_file"
        return 1
    fi

    return 0
}

format_duration() {
    local total_seconds=$1
    local hours=$((total_seconds / 3600))
    local minutes=$(((total_seconds % 3600) / 60))
    local seconds=$((total_seconds % 60))
    if [ "$hours" -gt 0 ]; then
        printf "%dh %dm %ds" "$hours" "$minutes" "$seconds"
    elif [ "$minutes" -gt 0 ]; then
        printf "%dm %ds" "$minutes" "$seconds"
    else
        printf "%ds" "$seconds"
    fi
}

# ── Parse token usage from agent output (best-effort) ────────────────────
# Looks for patterns like "input_tokens": 1234 or "Total tokens: 5678"
# Returns total tokens or empty string if not found.
parse_token_usage() {
    local output="$1"
    local input_tokens output_tokens total
    # Try JSON-style token fields from claude wrapper
    input_tokens=$(echo "$output" | grep -oE '"input_tokens"[[:space:]]*:[[:space:]]*[0-9]+' | grep -oE '[0-9]+' | tail -1 || echo "")
    output_tokens=$(echo "$output" | grep -oE '"output_tokens"[[:space:]]*:[[:space:]]*[0-9]+' | grep -oE '[0-9]+' | tail -1 || echo "")
    if [ -n "$input_tokens" ] && [ -n "$output_tokens" ]; then
        echo $(( input_tokens + output_tokens ))
        return
    fi
    # Try "Total tokens:" pattern
    total=$(echo "$output" | grep -oiE 'total tokens[[:space:]]*:[[:space:]]*[0-9]+' | grep -oE '[0-9]+' | tail -1 || echo "")
    if [ -n "$total" ]; then
        echo "$total"
        return
    fi
    echo ""
}

# ── Format token count for display ───────────────────────────────────────
format_tokens() {
    local tokens="$1"
    if [ -z "$tokens" ] || [ "$tokens" = "null" ]; then
        echo "N/A"
        return
    fi
    if [ "$tokens" -ge 1000 ]; then
        # Show as X.Yk
        local whole=$((tokens / 1000))
        local frac=$(( (tokens % 1000) / 100 ))
        echo "${whole}.${frac}k"
    else
        echo "$tokens"
    fi
}

SCRIPT_START=$(date +%s)

cd "$PROJECT_DIR"

# Validate BRANCH_STRATEGY
if [[ ! "$BRANCH_STRATEGY" =~ ^(chained|independent|both|sequential)$ ]]; then
    error "Invalid BRANCH_STRATEGY: $BRANCH_STRATEGY (must be: chained, independent, both, or sequential)"
    exit 1
fi

# Get base branch (sync target and branch-from target)
# BASE_BRANCH: explicit (e.g. develop, main); unset = current branch
if [ -n "$BASE_BRANCH" ]; then
    if git rev-parse --verify "$BASE_BRANCH" >/dev/null 2>&1; then
        MAIN_BRANCH="$BASE_BRANCH"
    else
        echo "Error: BASE_BRANCH=$BASE_BRANCH does not exist"
        exit 1
    fi
else
    MAIN_BRANCH=$(git branch --show-current 2>/dev/null || echo "main")
    if [ -z "$MAIN_BRANCH" ]; then
        MAIN_BRANCH="main"
    fi
fi

if ! command -v claude &> /dev/null; then
    echo "Claude Code CLI (claude) not found. Install via: npm install -g @anthropic-ai/claude-code"
    exit 1
fi

# ── Auto-detect build check command ──────────────────────────────────────

detect_build_check() {
    if [ -n "$BUILD_CHECK_CMD" ]; then
        if [ "$BUILD_CHECK_CMD" = "skip" ]; then
            echo ""
        else
            echo "$BUILD_CHECK_CMD"
        fi
        return
    fi

    # TypeScript (check for tsconfig.build.json first, then tsconfig.json)
    if [ -f "tsconfig.build.json" ]; then
        echo "npx tsc --noEmit --project tsconfig.build.json"
    elif [ -f "tsconfig.json" ]; then
        echo "npx tsc --noEmit"
    # Python
    elif [ -f "pyproject.toml" ] || [ -f "setup.py" ]; then
        echo "python -m py_compile $(find . -name '*.py' -not -path '*/venv/*' -not -path '*/.venv/*' | head -1 2>/dev/null || echo 'main.py')"
    # Rust
    elif [ -f "Cargo.toml" ]; then
        echo "cargo check"
    # Go
    elif [ -f "go.mod" ]; then
        echo "go build ./..."
    # Node.js with build script
    elif [ -f "package.json" ] && grep -q '"build"' package.json 2>/dev/null; then
        echo "npm run build"
    else
        echo ""
    fi
}

BUILD_CMD=$(detect_build_check)

# ── Auto-detect test check command ────────────────────────────────────────

detect_test_check() {
    if [ -n "$TEST_CHECK_CMD" ]; then
        if [ "$TEST_CHECK_CMD" = "skip" ]; then echo ""; else echo "$TEST_CHECK_CMD"; fi
        return
    fi
    if [ -f "package.json" ] && grep -q '"test"' package.json 2>/dev/null; then
        if ! grep -q "no test specified" package.json 2>/dev/null; then echo "npm test"; return; fi
    fi
    if [ -f "pytest.ini" ] || [ -f "conftest.py" ]; then echo "pytest"; return; fi
    if [ -f "pyproject.toml" ] && grep -q "pytest" "pyproject.toml" 2>/dev/null; then echo "pytest"; return; fi
    if [ -f "Cargo.toml" ]; then echo "cargo test"; return; fi
    if [ -f "go.mod" ]; then echo "go test ./..."; return; fi
    echo ""
}

TEST_CMD=$(detect_test_check)

# ── Agent command builder (model selection) ───────────────────────────────

agent_cmd() {
    local step_model="$1"
    local model="${step_model:-$AGENT_MODEL}"
    local cmd="bash lib/claude-wrapper.sh -p --dangerously-skip-permissions"
    if [ -n "$model" ]; then
        cmd="$cmd --model $model"
    fi
    echo "$cmd"
}

# ── Helpers ──────────────────────────────────────────────────────────────

check_working_tree_clean() {
    local dirty
    dirty=$(git status --porcelain 2>/dev/null | grep -v '^\?\?' | head -1)
    [ -z "$dirty" ]
}

clean_working_tree() {
    if ! check_working_tree_clean; then
        warn "Cleaning dirty working tree before next feature..."
        git stash push -m "build-loop: stashing failed feature attempt $(date '+%Y%m%d-%H%M%S')" 2>/dev/null || true
        success "Stashed uncommitted changes"
    fi
}

LAST_BUILD_OUTPUT=""
LAST_TEST_OUTPUT=""

# run_agent_with_backoff is provided by lib/reliability.sh
# Config: MAX_AGENT_RETRIES, BACKOFF_MAX_SECONDS (defaults in library)

# ── Safe command execution ──────────────────────────────────────────────────
# Executes a command safely without eval. For custom commands from .env.local,
# uses bash -c with proper error handling.
run_cmd_safe() {
    local cmd="$1"
    local is_custom="${2:-false}"
    if [ "$is_custom" = "true" ]; then
        warn "Executing custom command from .env.local: $cmd"
        bash -c "$cmd"
    else
        bash -c "$cmd"
    fi
}

check_build() {
    if [ -z "$BUILD_CMD" ]; then
        log "No build check configured (set BUILD_CHECK_CMD to enable)"
        return 0
    fi
    log "Running build check: $BUILD_CMD"
    local tmpfile
    tmpfile=$(mktemp)
    local is_custom="false"
    [ -n "$BUILD_CHECK_CMD" ] && [ "$BUILD_CHECK_CMD" != "skip" ] && is_custom="true"
    run_cmd_safe "$BUILD_CMD" "$is_custom" 2>&1 | tee "$tmpfile"
    local exit_code=${PIPESTATUS[0]}
    if [ $exit_code -eq 0 ]; then
        success "Build check passed"
        LAST_BUILD_OUTPUT=""
    else
        LAST_BUILD_OUTPUT=$(tail -50 "$tmpfile")
        error "Build check failed"
    fi
    rm -f "$tmpfile"
    return $exit_code
}

check_tests() {
    if [ -z "$TEST_CMD" ]; then
        log "No test suite configured (set TEST_CHECK_CMD to enable)"
        return 0
    fi
    log "Running test suite: $TEST_CMD"
    local tmpfile
    tmpfile=$(mktemp)
    local is_custom="false"
    [ -n "$TEST_CHECK_CMD" ] && [ "$TEST_CHECK_CMD" != "skip" ] && is_custom="true"
    run_cmd_safe "$TEST_CMD" "$is_custom" 2>&1 | tee "$tmpfile"
    local exit_code=${PIPESTATUS[0]}
    # Parse test count from runner output (vitest/jest/pytest patterns)
    LAST_TEST_COUNT=$(grep -oE '(Tests\s+)?[0-9]+ (passed|tests? passed)' "$tmpfile" | grep -oE '[0-9]+' | tail -1 || echo "")
    if [ -z "$LAST_TEST_COUNT" ]; then
        # Try pytest pattern: "N passed"
        LAST_TEST_COUNT=$(grep -oE '[0-9]+ passed' "$tmpfile" | grep -oE '[0-9]+' | tail -1 || echo "")
    fi
    if [ $exit_code -eq 0 ]; then
        success "Tests passed"
        LAST_TEST_OUTPUT=""
    else
        LAST_TEST_OUTPUT=$(tail -80 "$tmpfile")
        error "Tests failed"
    fi
    rm -f "$tmpfile"
    return $exit_code
}

should_run_step() {
    echo ",$POST_BUILD_STEPS," | grep -q ",$1,"
}

# truncate_for_context is provided by lib/reliability.sh
# Config: MAX_CONTEXT_TOKENS (default in library)

# ── Drift check helpers ──────────────────────────────────────────────────

# Extract spec file and source files from build output or git diff.
# Sets: DRIFT_SPEC_FILE, DRIFT_SOURCE_FILES
extract_drift_targets() {
    local build_result="$1"

    # Try to extract from agent's structured output first
    DRIFT_SPEC_FILE=$(parse_signal "SPEC_FILE" "$build_result")
    DRIFT_SOURCE_FILES=$(parse_signal "SOURCE_FILES" "$build_result")

    # Fallback: derive from git diff if agent didn't provide them
    if [ -z "$DRIFT_SPEC_FILE" ]; then
        DRIFT_SPEC_FILE=$(git diff HEAD~1 --name-only 2>/dev/null | grep '\.specs/features/.*\.feature\.md$' | head -1 || echo "")
    fi
    if [ -z "$DRIFT_SOURCE_FILES" ]; then
        DRIFT_SOURCE_FILES=$(git diff HEAD~1 --name-only 2>/dev/null | grep -E '\.(tsx?|jsx?|py|rs|go)$' | grep -v '\.test\.' | grep -v '\.spec\.' | tr '\n' ', ' | sed 's/,$//' || echo "")
    fi
}

# Run catch-drift via a fresh agent invocation.
# Args: $1 = spec file path, $2 = comma-separated source files
# Returns 0 if no drift (or drift was fixed), 1 if unresolvable drift.
check_drift() {
    if [ "$DRIFT_CHECK" != "true" ]; then
        log "Drift check disabled (set DRIFT_CHECK=true to enable)"
        return 0
    fi

    local spec_file="$1"
    local source_files="$2"

    if [ -z "$spec_file" ]; then
        warn "No spec file found — skipping drift check"
        return 0
    fi

    log "Running drift check (fresh agent)..."
    log "  Spec: $spec_file"
    log "  Source: ${source_files:-<detected from spec>}"

    local drift_attempt=0
    while [ "$drift_attempt" -le "$MAX_DRIFT_RETRIES" ]; do
        if [ "$drift_attempt" -gt 0 ]; then
            warn "Drift fix retry $drift_attempt/$MAX_DRIFT_RETRIES"
        fi

        DRIFT_OUTPUT=$(mktemp)

        local test_context=""
        if [ -n "$TEST_CMD" ]; then
            test_context="
Test command: $TEST_CMD"
        fi
        if [ -n "$LAST_TEST_OUTPUT" ]; then
            test_context="$test_context

PREVIOUS TEST FAILURE OUTPUT (last 80 lines):
$LAST_TEST_OUTPUT"
        fi

        # Inline (possibly truncated) spec content for drift agent context
        local spec_content=""
        spec_content=$(truncate_for_context "$spec_file" 2>/dev/null || true)

        local drift_prompt="
Run /catch-drift for this specific feature. This is an automated check — do NOT ask for user input. Auto-fix all drift by updating specs to match code (prefer documenting reality over reverting code).

Spec file: $spec_file
Source files: $source_files$test_context

Spec content (inline, may be truncated — read from disk if you need the full file):
$spec_content

Instructions:
1. Read the spec file and all its Gherkin scenarios
2. Read each source file listed above
3. Compare: does the code implement what the spec describes?
4. Check: are there behaviors in code not covered by the spec?
5. Check: are there scenarios in the spec not implemented in code?
6. If drift found: update specs, code, or tests as needed (prefer updating specs to match code)
7. Run the test suite (\`$TEST_CMD\`) and fix any failures — iterate until tests pass
8. Commit all fixes with message: 'fix: reconcile spec drift for {feature}'

IMPORTANT: Your goal is spec+code alignment AND a passing test suite. Keep iterating until both are achieved.

Output EXACTLY ONE of these signals at the end:
NO_DRIFT
DRIFT_FIXED: {brief summary of what was reconciled}
DRIFT_UNRESOLVABLE: {what needs human attention and why}
"
        local AGENT_EXIT=0
        set +e
        $(agent_cmd "$DRIFT_MODEL") "$drift_prompt" 2>&1 | tee "$DRIFT_OUTPUT"
        AGENT_EXIT=${PIPESTATUS[0]}
        set -e

        if [ "$AGENT_EXIT" -ne 0 ]; then
            warn "Drift agent exited with code $AGENT_EXIT (will check signals for actual status)"
        fi

        DRIFT_RESULT=$(cat "$DRIFT_OUTPUT")
        rm -f "$DRIFT_OUTPUT"

        if echo "$DRIFT_RESULT" | grep -q "NO_DRIFT"; then
            success "Drift check passed — spec and code are aligned"
            return 0
        fi

        if echo "$DRIFT_RESULT" | grep -q "DRIFT_FIXED"; then
            local fix_summary
            fix_summary=$(parse_signal "DRIFT_FIXED" "$DRIFT_RESULT")
            success "Drift detected and auto-fixed: $fix_summary"
            # Verify the fix didn't break build or tests
            if ! check_build; then
                warn "Drift fix broke the build — retrying"
            elif should_run_step "test" && [ -n "$TEST_CMD" ] && ! check_tests; then
                warn "Drift fix broke tests — retrying"
            else
                return 0
            fi
        fi

        if echo "$DRIFT_RESULT" | grep -q "DRIFT_UNRESOLVABLE"; then
            local unresolvable_reason
            unresolvable_reason=$(parse_signal "DRIFT_UNRESOLVABLE" "$DRIFT_RESULT")
            warn "Unresolvable drift: $unresolvable_reason"
            return 1
        fi

        # No clear signal — treat as drift found but not fixed
        warn "Drift check did not produce a clear signal"
        drift_attempt=$((drift_attempt + 1))
    done

    error "Drift check failed after $((MAX_DRIFT_RETRIES + 1)) attempt(s)"
    return 1
}

# ── Code review (fresh agent) ────────────────────────────────────────────

run_code_review() {
    log "Running code-review agent (fresh context, model: ${REVIEW_MODEL:-${AGENT_MODEL:-default}})..."
    local REVIEW_OUTPUT
    REVIEW_OUTPUT=$(mktemp)

    local test_context=""
    if [ -n "$TEST_CMD" ]; then
        test_context="
Test command: $TEST_CMD"
    fi

    local AGENT_EXIT=0
    set +e
    $(agent_cmd "$REVIEW_MODEL") "
Review and improve the code quality of the most recently built feature.
$test_context

Steps:
1. Check 'git log --oneline -10' to see recent commits
2. Identify source files for the most recent feature (look at git diff of recent commits)
3. Review against senior engineering standards:
   - TypeScript: No 'any' types, proper utility types, explicit return types
   - Async: Proper error handling, no await-in-forEach, correct Promise patterns
   - React: Complete useEffect deps, proper cleanup, no state mutation
   - Architecture: Proper abstraction, no library leaking, DRY
   - Security: Input validation, XSS prevention
4. Fix critical and high-severity issues ONLY
5. Do NOT change feature behavior
6. Do NOT refactor working code for style preferences
7. Run the test suite (\`$TEST_CMD\`) after your changes — iterate until tests pass
8. Commit fixes if any: git add -A && git commit -m 'refactor: code quality improvements (auto-review)'

IMPORTANT: Do not introduce test regressions. Run tests after every change and fix anything you break.

After completion, output exactly one of:
REVIEW_CLEAN
REVIEW_FIXED: {summary}
REVIEW_FAILED: {reason}
" 2>&1 | tee "$REVIEW_OUTPUT"
    AGENT_EXIT=${PIPESTATUS[0]}
    set -e

    if [ "$AGENT_EXIT" -ne 0 ]; then
        warn "Review agent exited with code $AGENT_EXIT (will check signals for actual status)"
    fi

    local REVIEW_RESULT
    REVIEW_RESULT=$(cat "$REVIEW_OUTPUT")
    rm -f "$REVIEW_OUTPUT"

    if echo "$REVIEW_RESULT" | grep -q "REVIEW_CLEAN\|REVIEW_FIXED"; then
        success "Code review complete"
        if ! check_working_tree_clean; then
            git add -A && git commit -m "refactor: code quality improvements (auto-review)" 2>/dev/null || true
        fi
        return 0
    else
        warn "Code review reported issues it couldn't fix"
        if ! check_working_tree_clean; then
            git add -A && git commit -m "refactor: partial code quality fixes (auto-review)" 2>/dev/null || true
        fi
        return 1
    fi
}

# ── Branch strategy helpers ────────────────────────────────────────────────

setup_branch_chained() {
    # WHY: Failed features can leave dirty worktree, causing all subsequent checkouts to fail (cascade failure)
    git add -A && git stash push -m "auto-stash before branch switch" 2>/dev/null || true

    local base_branch="${LAST_FEATURE_BRANCH:-$MAIN_BRANCH}"

    if [ "$base_branch" != "$MAIN_BRANCH" ]; then
        log "Branching from previous feature: $base_branch"
        git checkout "$base_branch" 2>/dev/null || {
            warn "Previous branch $base_branch not found, using $MAIN_BRANCH"
            base_branch="$MAIN_BRANCH"
            git checkout "$base_branch"
        }
    else
        log "Branching from $MAIN_BRANCH (first feature)"
        git checkout "$MAIN_BRANCH"
    fi

    CURRENT_FEATURE_BRANCH="auto/chained-$(date +%Y%m%d-%H%M%S)"
    git checkout -b "$CURRENT_FEATURE_BRANCH" 2>/dev/null || {
        error "Failed to create branch $CURRENT_FEATURE_BRANCH"
        return 1
    }
    success "Created branch: $CURRENT_FEATURE_BRANCH (from $base_branch)"
}

# ── Disk space monitoring ───────────────────────────────────────────────────
WORKTREE_SPACE_MB="${WORKTREE_SPACE_MB:-5120}"

check_disk_space() {
    if [ "$BRANCH_STRATEGY" = "sequential" ]; then
        return 0  # No worktrees created in sequential mode
    fi

    # Get available space in MB
    local available_mb
    available_mb=$(df -m . 2>/dev/null | awk 'NR==2 {print $4}')
    if [ -z "$available_mb" ]; then
        warn "Could not determine available disk space"
        return 0
    fi

    if [ "$available_mb" -lt "$WORKTREE_SPACE_MB" ]; then
        error "Insufficient disk space: ${available_mb}MB available, ${WORKTREE_SPACE_MB}MB required per worktree"
        error "Suggestion: use BRANCH_STRATEGY=sequential to avoid worktrees"
        error "Or set WORKTREE_SPACE_MB to a lower value in .env.local"
        exit 5
    fi

    log "Disk space OK: ${available_mb}MB available (${WORKTREE_SPACE_MB}MB required per worktree)"
}

setup_branch_independent() {
    check_disk_space
    local worktree_name="auto-independent-$(date +%Y%m%d-%H%M%S)"
    local worktree_path="$PROJECT_DIR/.build-worktrees/$worktree_name"

    mkdir -p "$(dirname "$worktree_path")"

    log "Creating worktree: $worktree_name (from $MAIN_BRANCH)"
    git worktree add -b "auto/$worktree_name" "$worktree_path" "$MAIN_BRANCH" 2>/dev/null || {
        error "Failed to create worktree $worktree_name"
        return 1
    }

    CURRENT_FEATURE_BRANCH="auto/$worktree_name"
    CURRENT_WORKTREE_PATH="$worktree_path"
    cd "$worktree_path"
    success "Created worktree: $worktree_name at $worktree_path"
}

setup_branch_sequential() {
    CURRENT_FEATURE_BRANCH=$(git branch --show-current)
    log "Building on current branch: $CURRENT_FEATURE_BRANCH"
}

cleanup_branch_chained() {
    LAST_FEATURE_BRANCH="$CURRENT_FEATURE_BRANCH"
    log "Next feature will branch from: $LAST_FEATURE_BRANCH"
}

cleanup_branch_independent() {
    if [ -n "$CURRENT_WORKTREE_PATH" ] && [ -d "$CURRENT_WORKTREE_PATH" ]; then
        log "Removing worktree: $CURRENT_WORKTREE_PATH"
        cd "$PROJECT_DIR"
        git worktree remove "$CURRENT_WORKTREE_PATH" 2>/dev/null || {
            warn "Failed to remove worktree, may need manual cleanup"
        }
        success "Cleaned up worktree (kept branch: $CURRENT_FEATURE_BRANCH)"
    fi
    cd "$PROJECT_DIR"
}

cleanup_branch_sequential() {
    :
}

# ── Prompts ──────────────────────────────────────────────────────────────

# show_preflight_summary <topo_lines>
# Prints the sorted feature list with t-shirt sizes and total count.
# If AUTO_APPROVE is not "true", prompts user for confirmation.
show_preflight_summary() {
    local topo_lines="$1"
    local count=0
    local line

    echo ""
    echo "╔═══════════════════════════════════════════════════════════╗"
    echo "║  Pre-Flight Build Plan                                   ║"
    echo "╚═══════════════════════════════════════════════════════════╝"
    echo ""
    printf "  %-4s %-40s %s\n" "#" "Feature" "Size"
    echo "  ──── ──────────────────────────────────────── ────"

    while IFS= read -r line; do
        [ -z "$line" ] && continue
        local fid fname fcmplx
        fid="${line%%|*}"
        local rest="${line#*|}"
        fname="${rest%%|*}"
        fcmplx="${rest##*|}"
        printf "  %-4s %-40s %s\n" "$fid" "$fname" "$fcmplx"
        count=$((count + 1))
    done <<< "$topo_lines"

    echo ""
    echo "  Total features: $count (capped at MAX_FEATURES=$MAX_FEATURES)"
    echo ""

    if [ "${AUTO_APPROVE:-false}" != "true" ]; then
        printf "  Proceed with build? [Y/n] "
        read -r answer </dev/tty
        if [ -n "$answer" ] && [[ ! "$answer" =~ ^[Yy] ]]; then
            log "Build cancelled by user"
            exit 0
        fi
    else
        log "AUTO_APPROVE=true — skipping confirmation"
    fi
}

# build_feature_prompt <feature_id> <feature_name>
# Generates the build prompt for a specific feature. Replaces the old
# static BUILD_PROMPT variable.
build_feature_prompt() {
    local feature_id="$1"
    local feature_name="$2"

    cat <<PROMPT_EOF
Build feature #${feature_id}: ${feature_name}

Instructions:
1. Read .specs/roadmap.md and locate feature #${feature_id} ("${feature_name}")
2. Update roadmap to mark it 🔄 in progress
3. Run /spec-first ${feature_name} --full to build it (includes /compound)
4. Update roadmap to mark it ✅ completed
5. Regenerate mapping: run ./scripts/generate-mapping.sh
6. Commit all changes with a descriptive message
7. If build fails, output: BUILD_FAILED: {reason}

CRITICAL IMPLEMENTATION RULES:
- Seed data is fine; stub functions are not. Use seed data, fixtures, or realistic sample data to make features work.
- NO stub functions that return hardcoded values or TODO placeholders. Every function must contain real logic.
- NO placeholder UI. Components must be wired to real data sources.
- Features must work end-to-end or they are not done.
- Real validation, real error handling, real flows.

After completion, output EXACTLY these signals (each on its own line):
FEATURE_BUILT: ${feature_name}
SPEC_FILE: {path to the .feature.md file you created/updated}
SOURCE_FILES: {comma-separated paths to source files created/modified}

Or if build fails:
BUILD_FAILED: {reason}

The SPEC_FILE and SOURCE_FILES lines are REQUIRED when FEATURE_BUILT is reported.
They are used by the automated drift-check that runs after your build.
PROMPT_EOF
}

build_retry_prompt() {
    local prompt='The previous build attempt FAILED. There are uncommitted changes or build errors from the last attempt.

Your job:
1. Run "git status" to understand the current state
2. Look at .specs/roadmap.md to find the feature marked 🔄 in progress
3. Fix whatever is broken — type errors, missing imports, incomplete implementation, failing tests
4. Make sure the feature works end-to-end. Seed data is fine; stub functions are not.
5. Run the test suite to verify everything passes: '"$TEST_CMD"'
6. Commit all changes with a descriptive message
7. Update roadmap to mark the feature ✅ completed

CRITICAL: Seed data is fine; stub functions are not. All features must use real function implementations, not placeholder stubs.
'

    # Append failure context if available
    if [ -n "$LAST_BUILD_OUTPUT" ]; then
        prompt="$prompt
BUILD CHECK FAILURE OUTPUT (last 50 lines):
$LAST_BUILD_OUTPUT
"
    fi

    if [ -n "$LAST_TEST_OUTPUT" ]; then
        prompt="$prompt
TEST SUITE FAILURE OUTPUT (last 80 lines):
$LAST_TEST_OUTPUT
"
    fi

    prompt="$prompt
After completion, output EXACTLY these signals (each on its own line):
FEATURE_BUILT: {feature name}
SPEC_FILE: {path to the .feature.md file}
SOURCE_FILES: {comma-separated paths to source files created/modified}

Or if build fails:
BUILD_FAILED: {reason}
"
    echo "$prompt"
}

# ── Build loop function ──────────────────────────────────────────────────
#
# run_build_loop <strategy> <topo_lines>
#
# Runs the build loop with the given strategy over topo-sorted features.
# topo_lines: newline-separated "ID|NAME|COMPLEXITY" from emit_topo_order().
# Iteration is capped at MAX_FEATURES.
# Sets these globals:
#   LOOP_BUILT, LOOP_FAILED, LOOP_SKIPPED, BUILT_FEATURE_NAMES[]
#
run_build_loop() {
    local strategy="$1"
    local topo_lines="$2"
    LOOP_BUILT=0
    LOOP_FAILED=0
    LOOP_SKIPPED=""
    LOOP_TIMINGS=()
    LAST_FEATURE_BRANCH=""
    CURRENT_FEATURE_BRANCH=""
    CURRENT_WORKTREE_PATH=""
    # Reset drift pairs to prevent cross-run contamination
    DRIFT_PAIRS=()

    # Parse topo_lines into arrays for iteration
    local -a TOPO_IDS=()
    local -a TOPO_NAMES=()
    local -a TOPO_CMPLX=()
    local _line
    while IFS= read -r _line; do
        [ -z "$_line" ] && continue
        TOPO_IDS+=("${_line%%|*}")
        local _rest="${_line#*|}"
        TOPO_NAMES+=("${_rest%%|*}")
        TOPO_CMPLX+=("${_rest##*|}")
    done <<< "$topo_lines"

    local topo_count=${#TOPO_IDS[@]}
    local loop_limit=$topo_count
    if [ "$loop_limit" -gt "$MAX_FEATURES" ]; then
        loop_limit=$MAX_FEATURES
    fi

    local idx=0
    while [ "$idx" -lt "$loop_limit" ]; do
        local i="${TOPO_IDS[$idx]}"
        local feature_label="${TOPO_NAMES[$idx]}"

        # ── Resume: skip already-completed features (by name) ──
        local already_built=false
        for _built_name in "${BUILT_FEATURE_NAMES[@]}"; do
            if [ "$_built_name" = "$feature_label" ]; then
                already_built=true
                break
            fi
        done
        if [ "$already_built" = true ]; then
            log "[$strategy] Skipping already-built feature: $feature_label"
            idx=$((idx + 1))
            continue
        fi

        FEATURE_START=$(date +%s)
        local elapsed_so_far=$(( FEATURE_START - SCRIPT_START ))

        echo ""
        echo "═══════════════════════════════════════════════════════════"
        log "[$strategy] Build #$i: $feature_label ($((idx + 1))/$loop_limit, built: $LOOP_BUILT, failed: $LOOP_FAILED) | elapsed: $(format_duration $elapsed_so_far)"
        echo "═══════════════════════════════════════════════════════════"
        echo ""

        # ── Setup branch based on strategy ──
        case "$strategy" in
            chained)
                setup_branch_chained || { error "Failed to setup chained branch"; idx=$((idx + 1)); continue; }
                ;;
            independent)
                setup_branch_independent || { error "Failed to setup independent worktree"; idx=$((idx + 1)); continue; }
                ;;
            sequential)
                setup_branch_sequential
                ;;
        esac

        # ── Pre-flight: ensure working tree is clean ──
        clean_working_tree

        # Save branch starting point for clean retries (findings #2, #18, #35)
        local BRANCH_START_COMMIT
        BRANCH_START_COMMIT=$(git rev-parse HEAD)

        # ── Build attempt ──
        local attempt=0
        local feature_done=false

        while [ "$attempt" -le "$MAX_RETRIES" ]; do
            if [ "$attempt" -gt 0 ]; then
                echo ""
                warn "Retry $attempt/$MAX_RETRIES — waiting ${MIN_RETRY_DELAY}s before retry (findings #2, #18, #35)"
                sleep "$MIN_RETRY_DELAY"
                # Reset branch to starting point for clean retry (reuse branch, don't create new one)
                git reset --hard "$BRANCH_START_COMMIT" 2>/dev/null || true
                git clean -fd 2>/dev/null || true
                echo ""
            fi

            BUILD_OUTPUT=$(mktemp)

            local AGENT_EXIT=0
            if [ "$attempt" -eq 0 ]; then
                run_agent_with_backoff "$BUILD_OUTPUT" $(agent_cmd "$BUILD_MODEL") "$(build_feature_prompt "$i" "$feature_label")"
            else
                run_agent_with_backoff "$BUILD_OUTPUT" $(agent_cmd "$RETRY_MODEL") "$(build_retry_prompt)"
            fi

            if [ "$AGENT_EXIT" -ne 0 ]; then
                warn "Agent exited with code $AGENT_EXIT (will check signals for actual status)"
            fi

            BUILD_RESULT=$(cat "$BUILD_OUTPUT")
            rm -f "$BUILD_OUTPUT"

            # ── Check for API credit exhaustion ──
            # WHY: Credit exhaustion means all subsequent features will also fail — halt immediately instead of wasting time
            if echo "$BUILD_RESULT" | grep -qiE '(credit|billing|insufficient_quota|quota exceeded|402 Payment|429 Too Many|payment required)'; then
                error "✗ API credits exhausted — halting build loop"
                exit 1
            fi

            # ── Check for "no features ready" ──
            if echo "$BUILD_RESULT" | grep -q "NO_FEATURES_READY"; then
                log "No more features ready to build"
                feature_done=true

                # Clean up the branch/worktree we just created (nothing to build)
                case "$strategy" in
                    chained)
                        # WHY: Failed features can leave dirty worktree, causing all subsequent checkouts to fail (cascade failure)
                        git add -A && git stash push -m "auto-stash before branch switch" 2>/dev/null || true
                        git checkout "${LAST_FEATURE_BRANCH:-$MAIN_BRANCH}" 2>/dev/null || git checkout "$MAIN_BRANCH" 2>/dev/null || true
                        git branch -D "$CURRENT_FEATURE_BRANCH" 2>/dev/null || true
                        ;;
                    independent)
                        cleanup_branch_independent
                        ;;
                esac

                return 0  # Exit the function (all done)
            fi

            # ── Check if the agent reported success ──
            if echo "$BUILD_RESULT" | grep -q "FEATURE_BUILT"; then
                local feature_name
                feature_name=$(parse_signal "FEATURE_BUILT" "$BUILD_RESULT")

                # ── Skip if this feature was already built (resume case) ──
                local already_built=false
                for _built_name in "${BUILT_FEATURE_NAMES[@]}"; do
                    if [ "$_built_name" = "$feature_name" ]; then
                        already_built=true
                        break
                    fi
                done
                if [ "$already_built" = true ]; then
                    log "[$strategy] Skipping already-built feature: $feature_name"
                    feature_done=true
                    break
                fi

                # Verify: did it actually commit?
                if check_working_tree_clean; then
                    # Verify: does it actually build?
                    if check_build; then
                        # Verify: do tests pass?
                        if ! should_run_step "test" || check_tests; then
                            # Validate required signals and run drift check
                            local drift_ok=true
                            if validate_required_signals "$BUILD_RESULT"; then
                                extract_drift_targets "$BUILD_RESULT"
                                if [ "$PARALLEL_VALIDATION" = "true" ]; then
                                    # Accumulate spec:source pairs for batch parallel drift check after loop.
                                    # source_files is comma-separated (from parse_signal "SOURCE_FILES"),
                                    # which run_parallel_drift_checks passes through to check_drift as-is.
                                    DRIFT_PAIRS+=("$DRIFT_SPEC_FILE:$DRIFT_SOURCE_FILES")
                                    log "Deferred drift check for parallel batch (pair #${#DRIFT_PAIRS[@]})"
                                else
                                    if ! check_drift "$DRIFT_SPEC_FILE" "$DRIFT_SOURCE_FILES"; then
                                        drift_ok=false
                                    fi
                                fi
                            else
                                warn "Required signals missing/invalid — skipping drift check"
                            fi
                            if [ "$drift_ok" = true ]; then
                                # Optional: code review (fresh agent)
                                if should_run_step "code-review"; then
                                    run_code_review || warn "Code review had issues (non-blocking)"
                                    # Re-validate after review changes
                                    if ! check_build; then
                                        warn "Code review broke the build!"
                                    elif should_run_step "test" && [ -n "$TEST_CMD" ] && ! check_tests; then
                                        warn "Code review broke tests!"
                                    fi
                                fi

                                LOOP_BUILT=$((LOOP_BUILT + 1))
                                local feature_end=$(date +%s)
                                local feature_duration=$((feature_end - FEATURE_START))
                                success "Feature $LOOP_BUILT built: $feature_name ($(format_duration $feature_duration))"
                                LOOP_TIMINGS+=("✓ $feature_name: $(format_duration $feature_duration)")
                                feature_done=true

                                # Track feature name for 'both' mode
                                BUILT_FEATURE_NAMES+=("$feature_name")

                                # Track build summary data
                                FEATURE_TIMINGS+=("$feature_duration")
                                FEATURE_SOURCE_FILES+=("${DRIFT_SOURCE_FILES:-}")
                                FEATURE_TEST_COUNTS+=("${LAST_TEST_COUNT:-}")
                                FEATURE_TOKEN_USAGE+=("$(parse_token_usage "$BUILD_RESULT")")
                                FEATURE_STATUSES+=("built")

                                # Save resume state
                                if [ "$ENABLE_RESUME" = "true" ]; then
                                    write_state "$i" "$strategy" "$(completed_features_json)" "${CURRENT_FEATURE_BRANCH:-}"
                                fi

                                break
                            else
                                warn "Agent said FEATURE_BUILT but drift check failed"
                            fi
                        else
                            warn "Agent said FEATURE_BUILT but tests failed"
                        fi
                    else
                        warn "Agent said FEATURE_BUILT but build check failed"
                    fi
                else
                    warn "Agent said FEATURE_BUILT but left uncommitted changes"
                fi
            fi

            # ── If we get here, the attempt failed ──
            if echo "$BUILD_RESULT" | grep -q "BUILD_FAILED"; then
                local reason
                reason=$(parse_signal "BUILD_FAILED" "$BUILD_RESULT")
                warn "Build failed: $reason"
            else
                warn "Build did not produce a clear success signal"
            fi

            attempt=$((attempt + 1))
        done

        # ── Post-build: cleanup branch ──
        if [ "$feature_done" = true ]; then
            case "$strategy" in
                chained)    cleanup_branch_chained ;;
                independent) cleanup_branch_independent ;;
                sequential)  cleanup_branch_sequential ;;
            esac
        else
            # Feature failed
            LOOP_FAILED=$((LOOP_FAILED + 1))
            local feature_end=$(date +%s)
            local feature_duration=$((feature_end - FEATURE_START))
            LOOP_SKIPPED="${LOOP_SKIPPED}\n  - #$i $feature_label ($(format_duration $feature_duration))"
            LOOP_TIMINGS+=("✗ #$i $feature_label: $(format_duration $feature_duration)")

            # Track failed feature in build summary
            BUILT_FEATURE_NAMES+=("#$i $feature_label")
            FEATURE_TIMINGS+=("$feature_duration")
            FEATURE_SOURCE_FILES+=("")
            FEATURE_TEST_COUNTS+=("")
            FEATURE_TOKEN_USAGE+=("$(parse_token_usage "${BUILD_RESULT:-}")")
            FEATURE_STATUSES+=("failed")

            error "Feature failed after $((MAX_RETRIES + 1)) attempt(s). Skipping. ($(format_duration $feature_duration))"
            clean_working_tree

            case "$strategy" in
                chained)
                    # Keep LAST_FEATURE_BRANCH so next feature branches from last successful, not base
                    warn "Feature failed, next feature will branch from last successful: ${LAST_FEATURE_BRANCH:-$MAIN_BRANCH}"
                    # WHY: Failed features can leave dirty worktree, causing all subsequent checkouts to fail (cascade failure)
                    git add -A && git stash push -m "auto-stash before branch switch" 2>/dev/null || true
                    git checkout "${LAST_FEATURE_BRANCH:-$MAIN_BRANCH}" 2>/dev/null || git checkout "$MAIN_BRANCH" 2>/dev/null || true
                    git branch -D "$CURRENT_FEATURE_BRANCH" 2>/dev/null || true
                    ;;
                independent)
                    cleanup_branch_independent
                    ;;
                sequential)
                    cleanup_branch_sequential
                    ;;
            esac
        fi
        idx=$((idx + 1))
    done

    # After the build loop, run any accumulated parallel drift checks
    if [ "$PARALLEL_VALIDATION" = "true" ] && [ "${#DRIFT_PAIRS[@]}" -gt 0 ]; then
        log "Running ${#DRIFT_PAIRS[@]} deferred drift checks in parallel..."
        if ! run_parallel_drift_checks "${DRIFT_PAIRS[@]}"; then
            warn "One or more parallel drift checks failed"
        fi
    fi
}

# get_cpu_count and run_parallel_drift_checks are provided by lib/reliability.sh
# Config: PARALLEL_VALIDATION (default in library)

# ── Clean up worktrees helper ────────────────────────────────────────────

cleanup_all_worktrees() {
    if [ -d "$PROJECT_DIR/.build-worktrees" ]; then
        log "Cleaning up remaining worktrees..."
        for wt in "$PROJECT_DIR/.build-worktrees"/*; do
            if [ -d "$wt" ]; then
                git worktree remove "$wt" 2>/dev/null || true
            fi
        done
        rmdir "$PROJECT_DIR/.build-worktrees" 2>/dev/null || true
    fi
}

# ── Build summary report ─────────────────────────────────────────────────
#
# write_build_summary <total_elapsed> <built_count> <failed_count>
#
# Writes a JSON summary to logs/build-summary-{timestamp}.json and prints
# a human-readable summary table to stdout. Uses the accumulator arrays
# (BUILT_FEATURE_NAMES, FEATURE_TIMINGS, FEATURE_SOURCE_FILES,
# FEATURE_TEST_COUNTS, FEATURE_TOKEN_USAGE, FEATURE_STATUSES).
#
write_build_summary() {
    local total_elapsed="$1"
    local built_count="$2"
    local failed_count="$3"

    local timestamp
    timestamp=$(date -u '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || date '+%Y-%m-%dT%H:%M:%S')
    local file_timestamp
    file_timestamp=$(date '+%Y%m%d-%H%M%S')

    # Compute total test count (last non-empty test count from any feature)
    local total_tests=0
    local idx=0
    while [ "$idx" -lt "${#FEATURE_TEST_COUNTS[@]}" ]; do
        if [ -n "${FEATURE_TEST_COUNTS[$idx]}" ]; then
            total_tests="${FEATURE_TEST_COUNTS[$idx]}"
        fi
        idx=$((idx + 1))
    done

    # ── Write JSON summary ──
    mkdir -p "$PROJECT_DIR/logs"
    local summary_file="$PROJECT_DIR/logs/build-summary-${file_timestamp}.json"

    # Build features JSON array using indexed arrays (no associative arrays for bash 3.x)
    local features_json=""
    idx=0
    while [ "$idx" -lt "${#BUILT_FEATURE_NAMES[@]}" ]; do
        local fname="${BUILT_FEATURE_NAMES[$idx]}"
        local ftime="${FEATURE_TIMINGS[$idx]:-0}"
        local fsrc="${FEATURE_SOURCE_FILES[$idx]:-}"
        local ftests="${FEATURE_TEST_COUNTS[$idx]:-}"
        local ftokens="${FEATURE_TOKEN_USAGE[$idx]:-}"
        local fstatus="${FEATURE_STATUSES[$idx]:-built}"

        # Escape feature name for JSON
        fname=$(echo "$fname" | sed 's/\\/\\\\/g; s/"/\\"/g')

        # Build source_files JSON array from comma-separated string
        local src_json="[]"
        if [ -n "$fsrc" ]; then
            src_json="["
            local first_src=true
            local IFS_SAVE="$IFS"
            IFS=','
            for src_item in $fsrc; do
                # Trim whitespace
                src_item=$(echo "$src_item" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
                if [ -n "$src_item" ]; then
                    src_item=$(echo "$src_item" | sed 's/\\/\\\\/g; s/"/\\"/g')
                    if [ "$first_src" = true ]; then
                        src_json="${src_json}\"${src_item}\""
                        first_src=false
                    else
                        src_json="${src_json}, \"${src_item}\""
                    fi
                fi
            done
            IFS="$IFS_SAVE"
            src_json="${src_json}]"
        fi

        # Format test count and tokens as JSON values
        local tests_json="null"
        if [ -n "$ftests" ]; then
            tests_json="$ftests"
        fi
        local tokens_json="null"
        if [ -n "$ftokens" ]; then
            tokens_json="$ftokens"
        fi

        local feature_entry
        feature_entry=$(cat <<FEATURE_EOF
    {
      "name": "$fname",
      "status": "$fstatus",
      "time_seconds": $ftime,
      "source_files": $src_json,
      "test_count": $tests_json,
      "tokens": $tokens_json
    }
FEATURE_EOF
)
        if [ "$idx" -eq 0 ]; then
            features_json="$feature_entry"
        else
            features_json="${features_json},
${feature_entry}"
        fi
        idx=$((idx + 1))
    done

    # Escape model and strategy for JSON safety
    local model_json="${AGENT_MODEL:-default}"
    model_json=$(echo "$model_json" | sed 's/\\/\\\\/g; s/"/\\"/g')
    local strategy_json="${BRANCH_STRATEGY:-chained}"
    strategy_json=$(echo "$strategy_json" | sed 's/\\/\\\\/g; s/"/\\"/g')

    cat > "$summary_file" <<SUMMARY_EOF
{
  "timestamp": "$timestamp",
  "total_time_seconds": $total_elapsed,
  "model": "$model_json",
  "branch_strategy": "$strategy_json",
  "features_built": $built_count,
  "features_failed": $failed_count,
  "total_tests": $total_tests,
  "features": [
$features_json
  ]
}
SUMMARY_EOF

    # ── Print human-readable summary ──
    echo ""
    echo "═══ Build Summary ═══"
    echo "  Model: ${AGENT_MODEL:-default}"
    echo "  Strategy: $BRANCH_STRATEGY"
    echo "  Total time: $(format_duration $total_elapsed)"
    echo "  Features: $built_count built, $failed_count failed"
    echo "  Total tests: $total_tests"

    if [ "${#BUILT_FEATURE_NAMES[@]}" -gt 0 ]; then
        printf "  %-36s %-10s %-8s %-9s %s\n" "Feature" "Time" "Tests" "Tokens" "Status"
        echo "  ─────────────────────────────────────────────────────────────────"
        idx=0
        while [ "$idx" -lt "${#BUILT_FEATURE_NAMES[@]}" ]; do
            local fname="${BUILT_FEATURE_NAMES[$idx]}"
            local ftime="${FEATURE_TIMINGS[$idx]:-0}"
            local ftests="${FEATURE_TEST_COUNTS[$idx]:-}"
            local ftokens="${FEATURE_TOKEN_USAGE[$idx]:-}"
            local fstatus="${FEATURE_STATUSES[$idx]:-built}"

            # Truncate long feature names
            if [ ${#fname} -gt 34 ]; then
                fname="${fname:0:31}..."
            fi

            local time_str
            time_str=$(format_duration "$ftime")
            local tests_str="${ftests:-N/A}"
            local tokens_str
            tokens_str=$(format_tokens "$ftokens")
            local status_str="✓"
            if [ "$fstatus" = "failed" ]; then
                status_str="✗"
            fi

            printf "  %-36s %-10s %-8s %-9s %s\n" "$fname" "$time_str" "$tests_str" "$tokens_str" "$status_str"
            idx=$((idx + 1))
        done
    fi
    echo ""
    echo "  Summary written to: logs/build-summary-${file_timestamp}.json"
    echo ""
}

# ── Main ──────────────────────────────────────────────────────────────────

# check_circular_deps is provided by lib/reliability.sh
check_circular_deps

echo ""
echo "Build loop (local only, no remote/push/PR)"
echo "Base branch: $MAIN_BRANCH"
echo "Branch strategy: $BRANCH_STRATEGY"
echo "Max features: $MAX_FEATURES | Max retries per feature: $MAX_RETRIES | Min retry delay: ${MIN_RETRY_DELAY}s"
if [ -n "$BUILD_CMD" ]; then
    echo "Build check: $BUILD_CMD"
else
    echo "Build check: disabled (set BUILD_CHECK_CMD to enable)"
fi
if [ -n "$TEST_CMD" ]; then
    echo "Test suite: $TEST_CMD"
else
    echo "Test suite: disabled (set TEST_CHECK_CMD to enable)"
fi
if [ "$DRIFT_CHECK" = "true" ]; then
    echo "Drift check: enabled (max retries: $MAX_DRIFT_RETRIES)"
else
    echo "Drift check: disabled (set DRIFT_CHECK=true to enable)"
fi
echo "Post-build steps: ${POST_BUILD_STEPS:-none}"
if [ "$PARALLEL_VALIDATION" = "true" ]; then
    echo "Parallel validation: enabled ($(get_cpu_count) cores)"
fi
if [ -n "$AGENT_MODEL" ] || [ -n "$BUILD_MODEL" ] || [ -n "$DRIFT_MODEL" ] || [ -n "$REVIEW_MODEL" ]; then
    echo "Models: default=${AGENT_MODEL:-CLI default} build=${BUILD_MODEL:-↑} drift=${DRIFT_MODEL:-↑} review=${REVIEW_MODEL:-↑}"
fi
echo ""

# Track feature names across passes (used by 'both' mode)
BUILT_FEATURE_NAMES=()

# Build summary accumulators (indexed arrays for macOS bash 3.x compatibility)
FEATURE_TIMINGS=()
FEATURE_SOURCE_FILES=()
FEATURE_TEST_COUNTS=()
FEATURE_TOKEN_USAGE=()
FEATURE_STATUSES=()
LAST_TEST_COUNT=""

# ── Topological sort + pre-flight summary (shown once, even in "both" mode) ──
# emit_topo_order is provided by lib/reliability.sh
TOPO_LINES=$(emit_topo_order)

if [ -z "$TOPO_LINES" ]; then
    log "No pending (⬜) features found in roadmap — nothing to build"
    release_lock
    exit 0
fi

show_preflight_summary "$TOPO_LINES"

if [ "$BRANCH_STRATEGY" = "both" ]; then
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # BOTH MODE: Run chained first, then independent
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    echo ""
    echo "╔═══════════════════════════════════════════════════════════╗"
    echo "║  PASS 1 of 2: CHAINED                                   ║"
    echo "║  Building all features sequentially (each has deps)      ║"
    echo "╚═══════════════════════════════════════════════════════════╝"
    echo ""

    run_build_loop "chained" "$TOPO_LINES"
    CHAINED_BUILT=$LOOP_BUILT
    CHAINED_FAILED=$LOOP_FAILED
    CHAINED_SKIPPED="$LOOP_SKIPPED"
    CHAINED_TIMINGS=("${LOOP_TIMINGS[@]}")
    CHAINED_LAST_BRANCH="$LAST_FEATURE_BRANCH"
    CHAINED_FEATURE_NAMES=("${BUILT_FEATURE_NAMES[@]}")

    success "Chained pass complete: $CHAINED_BUILT built, $CHAINED_FAILED failed"

    if [ "$CHAINED_BUILT" -eq 0 ]; then
        warn "No features were built in chained pass. Skipping independent pass."
    else
        # Go back to main for independent pass
        cd "$PROJECT_DIR"
        # WHY: Failed features can leave dirty worktree, causing all subsequent checkouts to fail (cascade failure)
        git add -A && git stash push -m "auto-stash before branch switch" 2>/dev/null || true
        git checkout "$MAIN_BRANCH" 2>/dev/null || true

        echo ""
        echo "╔═══════════════════════════════════════════════════════════╗"
        echo "║  PASS 2 of 2: INDEPENDENT                               ║"
        echo "║  Rebuilding each feature from $MAIN_BRANCH (isolated)    ║"
        echo "╚═══════════════════════════════════════════════════════════╝"
        echo ""
        log "Features to rebuild independently: ${#CHAINED_FEATURE_NAMES[@]}"
        for fn in "${CHAINED_FEATURE_NAMES[@]}"; do
            log "  - $fn"
        done
        echo ""

        INDEPENDENT_BUILT=0
        INDEPENDENT_FAILED=0
        INDEPENDENT_TIMINGS=()
        # Reset drift pairs for the independent pass to prevent cross-run contamination
        DRIFT_PAIRS=()

        for fn in "${CHAINED_FEATURE_NAMES[@]}"; do
            INDEP_FEATURE_START=$(date +%s)
            elapsed_so_far=$(( INDEP_FEATURE_START - SCRIPT_START ))

            echo ""
            echo "═══════════════════════════════════════════════════════════"
            log "[independent] Building: $fn | elapsed: $(format_duration $elapsed_so_far)"
            echo "═══════════════════════════════════════════════════════════"
            echo ""

            # Check disk space before creating worktree
            check_disk_space

            # Create a worktree from main for this feature
            worktree_name="independent-$(echo "$fn" | tr ' :/' '-' | tr '[:upper:]' '[:lower:]')-$(date +%H%M%S)"
            worktree_path="$PROJECT_DIR/.build-worktrees/$worktree_name"
            branch_name="auto/independent-$(echo "$fn" | tr ' :/' '-' | tr '[:upper:]' '[:lower:]')"

            mkdir -p "$(dirname "$worktree_path")"

            # Remove branch if it already exists (from a previous run)
            git branch -D "$branch_name" 2>/dev/null || true

            git worktree add -b "$branch_name" "$worktree_path" "$MAIN_BRANCH" 2>/dev/null || {
                error "Failed to create worktree for: $fn"
                INDEPENDENT_FAILED=$((INDEPENDENT_FAILED + 1))
                continue
            }

            success "Created worktree: $worktree_path (branch: $branch_name)"

            cd "$worktree_path"

            INDEP_PROMPT="
Build the feature: $fn

Instructions:
1. Run /spec-first $fn --full to build this feature from scratch
2. This is an independent build from $MAIN_BRANCH — do not assume other features exist
3. Create the spec, write tests, implement, and commit
4. Regenerate mapping: run ./scripts/generate-mapping.sh
5. Commit all changes with a descriptive message

CRITICAL IMPLEMENTATION RULES:
- Seed data is fine; stub functions are not. Use seed data, fixtures, or realistic sample data to make features work.
- NO stub functions that return hardcoded values or TODO placeholders. Every function must contain real logic.
- NO placeholder UI. Components must be wired to real data sources.
- Features must work end-to-end or they are not done.
- Real validation, real error handling, real flows.

After completion, output exactly one of:
FEATURE_BUILT: $fn
BUILD_FAILED: {reason}
"

            BUILD_OUTPUT=$(mktemp)
            AGENT_EXIT=0
            set +e
            $(agent_cmd "$BUILD_MODEL") "$INDEP_PROMPT" 2>&1 | tee "$BUILD_OUTPUT"
            AGENT_EXIT=${PIPESTATUS[0]}
            set -e

            if [ "$AGENT_EXIT" -ne 0 ]; then
                warn "Agent exited with code $AGENT_EXIT (will check signals for actual status)"
            fi

            BUILD_RESULT=$(cat "$BUILD_OUTPUT")
            rm -f "$BUILD_OUTPUT"

            indep_feature_end=$(date +%s)
            indep_feature_duration=$((indep_feature_end - INDEP_FEATURE_START))

            if echo "$BUILD_RESULT" | grep -q "FEATURE_BUILT"; then
                if check_working_tree_clean; then
                    # Accumulate or run drift check for independent build
                    indep_drift_ok=true
                    if validate_required_signals "$BUILD_RESULT"; then
                        extract_drift_targets "$BUILD_RESULT"
                        if [ "$PARALLEL_VALIDATION" = "true" ]; then
                            # Accumulate spec:source pairs for batch parallel drift check after loop.
                            # source_files is comma-separated (from parse_signal "SOURCE_FILES"),
                            # which run_parallel_drift_checks passes through to check_drift as-is.
                            DRIFT_PAIRS+=("$DRIFT_SPEC_FILE:$DRIFT_SOURCE_FILES")
                            log "Deferred drift check for parallel batch (pair #${#DRIFT_PAIRS[@]})"
                        else
                            if ! check_drift "$DRIFT_SPEC_FILE" "$DRIFT_SOURCE_FILES"; then
                                indep_drift_ok=false
                            fi
                        fi
                    else
                        warn "Required signals missing/invalid — skipping drift check"
                    fi

                    if [ "$indep_drift_ok" = true ]; then
                        INDEPENDENT_BUILT=$((INDEPENDENT_BUILT + 1))
                        success "Independently built: $fn (branch: $branch_name) ($(format_duration $indep_feature_duration))"
                        INDEPENDENT_TIMINGS+=("✓ $fn: $(format_duration $indep_feature_duration)")
                    else
                        warn "Independent build drift check failed for: $fn ($(format_duration $indep_feature_duration))"
                        INDEPENDENT_FAILED=$((INDEPENDENT_FAILED + 1))
                        INDEPENDENT_TIMINGS+=("✗ $fn: $(format_duration $indep_feature_duration)")
                    fi
                else
                    warn "Agent said FEATURE_BUILT but left uncommitted changes ($(format_duration $indep_feature_duration))"
                    INDEPENDENT_FAILED=$((INDEPENDENT_FAILED + 1))
                    INDEPENDENT_TIMINGS+=("✗ $fn: $(format_duration $indep_feature_duration)")
                fi
            else
                warn "Independent build failed for: $fn ($(format_duration $indep_feature_duration))"
                INDEPENDENT_FAILED=$((INDEPENDENT_FAILED + 1))
                INDEPENDENT_TIMINGS+=("✗ $fn: $(format_duration $indep_feature_duration)")
            fi

            # Clean up worktree but keep the branch
            cd "$PROJECT_DIR"
            git worktree remove "$worktree_path" 2>/dev/null || {
                warn "Failed to remove worktree: $worktree_path"
            }
        done

        # After the independent pass, run any accumulated parallel drift checks
        if [ "$PARALLEL_VALIDATION" = "true" ] && [ "${#DRIFT_PAIRS[@]}" -gt 0 ]; then
            log "Running ${#DRIFT_PAIRS[@]} deferred drift checks in parallel..."
            if ! run_parallel_drift_checks "${DRIFT_PAIRS[@]}"; then
                warn "One or more parallel drift checks failed"
            fi
        fi

        cleanup_all_worktrees
    fi

    # ── Final summary for both mode ──
    cd "$PROJECT_DIR"
    # WHY: Failed features can leave dirty worktree, causing all subsequent checkouts to fail (cascade failure)
    git add -A && git stash push -m "auto-stash before branch switch" 2>/dev/null || true
    git checkout "$MAIN_BRANCH" 2>/dev/null || true

    total_elapsed=$(( $(date +%s) - SCRIPT_START ))

    echo ""
    echo "═══════════════════════════════════════════════════════════"
    echo ""
    success "BOTH PASSES COMPLETE (total: $(format_duration $total_elapsed))"
    echo ""
    echo "  Chained pass:      $CHAINED_BUILT built, $CHAINED_FAILED failed"
    echo "  Independent pass:  ${INDEPENDENT_BUILT:-0} built, ${INDEPENDENT_FAILED:-0} failed"
    echo ""
    if [ ${#CHAINED_TIMINGS[@]} -gt 0 ]; then
        echo "  Chained timings:"
        for t in "${CHAINED_TIMINGS[@]}"; do
            echo "    $t"
        done
        echo ""
    fi
    if [ ${#INDEPENDENT_TIMINGS[@]} -gt 0 ]; then
        echo "  Independent timings:"
        for t in "${INDEPENDENT_TIMINGS[@]}"; do
            echo "    $t"
        done
        echo ""
    fi
    if [ -n "$CHAINED_LAST_BRANCH" ]; then
        echo "  Chained branches (full app with deps):"
        echo "    Last branch: $CHAINED_LAST_BRANCH"
    fi
    if [ "${INDEPENDENT_BUILT:-0}" -gt 0 ] 2>/dev/null; then
        echo ""
        echo "  Independent branches (isolated per feature):"
        for fn in "${CHAINED_FEATURE_NAMES[@]}"; do
            branch_name="auto/independent-$(echo "$fn" | tr ' :/' '-' | tr '[:upper:]' '[:lower:]')"
            if git rev-parse --verify "$branch_name" >/dev/null 2>&1; then
                echo "    $branch_name"
            fi
        done
    fi
    if [ -n "$CHAINED_SKIPPED" ]; then
        echo ""
        warn "Skipped in chained pass:"
        echo -e "$CHAINED_SKIPPED"
    fi
    echo ""
    echo "  Total time: $(format_duration $total_elapsed)"
    echo ""
    echo "═══════════════════════════════════════════════════════════"
    echo ""

    # Write build summary report (JSON + human-readable)
    write_build_summary "$total_elapsed" "$CHAINED_BUILT" "$CHAINED_FAILED"

    # Clean resume state on successful completion
    if [ "$ENABLE_RESUME" = "true" ]; then
        clean_state
    fi

else
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # SINGLE MODE: chained, independent, or sequential
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    run_build_loop "$BRANCH_STRATEGY" "$TOPO_LINES"

    # ── Final cleanup ──
    cd "$PROJECT_DIR"

    if [ "$BRANCH_STRATEGY" = "independent" ]; then
        cleanup_all_worktrees
    fi

    total_elapsed=$(( $(date +%s) - SCRIPT_START ))

    echo ""
    echo "═══════════════════════════════════════════════════════════"
    success "Done. Built: $LOOP_BUILT, Failed: $LOOP_FAILED (total: $(format_duration $total_elapsed))"
    echo ""
    if [ ${#LOOP_TIMINGS[@]} -gt 0 ]; then
        echo "  Per-feature timings:"
        for t in "${LOOP_TIMINGS[@]}"; do
            echo "    $t"
        done
        echo ""
    fi
    if [ -n "$LOOP_SKIPPED" ]; then
        warn "Skipped features (check git stash list for their partial work):"
        echo -e "$LOOP_SKIPPED"
        echo ""
    fi
    if [ "$BRANCH_STRATEGY" = "chained" ] && [ -n "$LAST_FEATURE_BRANCH" ]; then
        log "Last feature branch: $LAST_FEATURE_BRANCH"
        log "You can review/merge branches or reset to $MAIN_BRANCH"
        echo ""
    fi
    echo "  Total time: $(format_duration $total_elapsed)"
    echo "═══════════════════════════════════════════════════════════"
    echo ""

    # Write build summary report (JSON + human-readable)
    write_build_summary "$total_elapsed" "$LOOP_BUILT" "$LOOP_FAILED"

    # Clean resume state on successful completion of all features
    if [ "$ENABLE_RESUME" = "true" ] && [ "$LOOP_FAILED" -eq 0 ]; then
        clean_state
    fi
fi
