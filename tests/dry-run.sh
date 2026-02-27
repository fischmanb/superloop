#!/usr/bin/env bash
# tests/dry-run.sh — Integration test for build-loop-local.sh
#
# Creates a minimal toy project and runs build-loop-local.sh with MAX_FEATURES=1.
# This validates end-to-end: lock → circular dep check → agent call → signal parse
#   → drift check → state save → cleanup.
#
# Structural test: exercises shared library functions without an agent.
# Full test: runs the actual build loop, then validates:
#   - FEATURE_BUILT signal emitted
#   - Roadmap updated to reflect completion
#   - State file structure (completed_features, current_branch, valid JSON)
#   - Drift check signal (when DRIFT_CHECK enabled)
#
# Cleanup is idempotent: state files and roadmap changes are reverted on exit
# (pass or fail). Git branches are preserved and logged for debugging.
#
# Prerequisites:
#   - `agent` CLI must be installed (Cursor CLI)
#   - A model must be running or accessible
#
# Usage:
#   ./tests/dry-run.sh                 # Full dry run with agent
#   ./tests/dry-run.sh --verbose       # Full dry run, agent output to tests/dry-run-verbose.log
#   DRY_RUN_SKIP_AGENT=true ./tests/dry-run.sh  # Skip agent calls (structural test only)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
FIXTURES="$SCRIPT_DIR/fixtures/dry-run"
WORK_DIR=""
VERBOSE=false
VERBOSE_LOG="$SCRIPT_DIR/dry-run-verbose.log"

# ── Flag parsing ────────────────────────────────────────────────────────────

for arg in "$@"; do
    case "$arg" in
        --verbose)
            VERBOSE=true
            ;;
    esac
done

# Truncate verbose log at the start of each run so each run starts fresh
if [ "$VERBOSE" = true ]; then
    : > "$VERBOSE_LOG"
    echo "Verbose mode: agent output will be captured to $VERBOSE_LOG"
fi

# ── Setup ────────────────────────────────────────────────────────────────────

setup() {
    WORK_DIR=$(mktemp -d)
    echo "Dry-run work directory: $WORK_DIR"

    # Initialize a git repo in the work directory
    cd "$WORK_DIR"
    git init -b main
    git config user.email "test@test.com"
    git config user.name "Test"
    git config commit.gpgsign false

    # Copy fixtures
    cp -r "$FIXTURES/.specs" "$WORK_DIR/"

    # Create a minimal CLAUDE.md
    echo "# Test Project" > "$WORK_DIR/CLAUDE.md"

    # Create a minimal package.json (no test script)
    cat > "$WORK_DIR/package.json" << 'EOF'
{
  "name": "dry-run-test",
  "version": "1.0.0"
}
EOF

    # Initial commit
    git add -A
    git commit -m "initial: dry-run test project"

    # Copy scripts and lib
    mkdir -p "$WORK_DIR/scripts" "$WORK_DIR/lib"
    cp "$PROJECT_ROOT/scripts/build-loop-local.sh" "$WORK_DIR/scripts/"
    cp "$PROJECT_ROOT/lib/reliability.sh" "$WORK_DIR/lib/"

    echo "Setup complete."
}

# ── Idempotent cleanup ───────────────────────────────────────────────────────

cleanup() {
    local exit_code=$?

    if [ -z "$WORK_DIR" ] || [ ! -d "$WORK_DIR" ]; then
        return
    fi

    echo ""
    echo "=== Cleanup ==="

    # 1. Delete state file if it exists
    if [ -f "$WORK_DIR/.sdd-state/resume.json" ]; then
        rm -f "$WORK_DIR/.sdd-state/resume.json"
        echo "   Removed state file"
    fi
    if [ -d "$WORK_DIR/.sdd-state" ]; then
        rmdir "$WORK_DIR/.sdd-state" 2>/dev/null || true
    fi

    # 2. Revert any roadmap changes using git checkout
    cd "$WORK_DIR" 2>/dev/null && \
        git checkout -- .specs/roadmap.md 2>/dev/null && \
        echo "   Reverted roadmap changes" || true

    # 3. Log branch names instead of deleting them
    local branches
    branches=$(cd "$WORK_DIR" 2>/dev/null && git branch --list 'auto/*' 2>/dev/null || true)
    if [ -n "$branches" ]; then
        while IFS= read -r branch; do
            branch=$(echo "$branch" | sed 's/^[* ]*//')
            [ -z "$branch" ] && continue
            echo "   NOTE: branch $branch preserved for debugging — delete manually when no longer needed"
        done <<< "$branches"
    fi

    # 4. Delete temp worktree directory if it exists
    if [ -d "$WORK_DIR/.build-worktrees" ]; then
        rm -rf "$WORK_DIR/.build-worktrees"
        echo "   Removed .build-worktrees"
    fi

    # 5. Clean up lock file if it exists
    rm -f /tmp/sdd-build-loop-*.lock

    # 6. Remove the work directory
    rm -rf "$WORK_DIR"
    echo "   Cleaned up: $WORK_DIR"

    return $exit_code
}

trap cleanup EXIT

# ── Structural dry run (no agent needed) ─────────────────────────────────────

structural_test() {
    echo ""
    echo "=== Structural dry run (no agent calls) ==="
    echo ""

    cd "$WORK_DIR"

    # 1. Verify circular dep check passes
    echo "1. Testing circular dependency check..."
    source "$WORK_DIR/lib/reliability.sh"
    PROJECT_DIR="$WORK_DIR"
    check_circular_deps
    echo "   PASS: No circular deps detected"

    # 2. Verify lock works
    echo "2. Testing lock..."
    LOCK_FILE="/tmp/sdd-build-loop-dry-run-test.lock"
    acquire_lock
    if [ -f "$LOCK_FILE" ]; then
        echo "   PASS: Lock acquired"
    else
        echo "   FAIL: Lock file not created"
        exit 1
    fi
    release_lock
    if [ ! -f "$LOCK_FILE" ]; then
        echo "   PASS: Lock released"
    else
        echo "   FAIL: Lock file still exists"
        exit 1
    fi

    # 3. Verify state persistence
    echo "3. Testing state persistence..."
    STATE_DIR="$WORK_DIR/.sdd-state"
    STATE_FILE="$STATE_DIR/resume.json"
    BUILT_FEATURE_NAMES=("Hello World")
    write_state 1 "chained" "$(completed_features_json)" "auto/test-branch"
    if [ -f "$STATE_FILE" ]; then
        echo "   PASS: State file written"
    else
        echo "   FAIL: State file not created"
        exit 1
    fi
    read_state
    if [ "$RESUME_INDEX" = "1" ]; then
        echo "   PASS: State round-trip successful"
    else
        echo "   FAIL: State round-trip failed (index=$RESUME_INDEX)"
        exit 1
    fi
    clean_state

    # 4. Verify truncate works
    echo "4. Testing context truncation..."
    local result
    result=$(truncate_for_context "$WORK_DIR/.specs/roadmap.md")
    if [ -n "$result" ]; then
        echo "   PASS: Truncation returns content"
    else
        echo "   FAIL: Truncation returned empty"
        exit 1
    fi

    echo ""
    echo "=== Structural dry run: ALL PASSED ==="
}

# ── Full dry run (requires agent CLI) ────────────────────────────────────────

full_test() {
    echo ""
    echo "=== Full dry run (with agent calls) ==="
    echo ""

    if ! command -v claude &>/dev/null; then
        echo "SKIP: claude CLI not found — run structural test only"
        echo "Install via: npm install -g @anthropic-ai/claude-code"
        return 0
    fi

    cd "$WORK_DIR"

    # Capture build output for post-run validation
    local build_output_file
    build_output_file=$(mktemp)

    # Run build-loop with MAX_FEATURES=1
    echo "Running: MAX_FEATURES=1 PROJECT_DIR=$WORK_DIR ./scripts/build-loop-local.sh"
    echo ""

    local build_exit=0
    if [ "$VERBOSE" = true ]; then
        MAX_FEATURES=1 \
        BRANCH_STRATEGY=sequential \
        DRIFT_CHECK="${DRIFT_CHECK:-false}" \
        BUILD_CHECK_CMD=skip \
        TEST_CHECK_CMD=skip \
        POST_BUILD_STEPS="" \
        PROJECT_DIR="$WORK_DIR" \
            "$WORK_DIR/scripts/build-loop-local.sh" 2>&1 | tee "$build_output_file" >> "$VERBOSE_LOG" || build_exit=$?
    else
        MAX_FEATURES=1 \
        BRANCH_STRATEGY=sequential \
        DRIFT_CHECK="${DRIFT_CHECK:-false}" \
        BUILD_CHECK_CMD=skip \
        TEST_CHECK_CMD=skip \
        POST_BUILD_STEPS="" \
        PROJECT_DIR="$WORK_DIR" \
            "$WORK_DIR/scripts/build-loop-local.sh" > "$build_output_file" 2>&1 || build_exit=$?
    fi

    local build_output
    build_output=$(cat "$build_output_file")
    rm -f "$build_output_file"

    if [ $build_exit -ne 0 ]; then
        echo ""
        echo "Build loop exited with code $build_exit"
        if [ $build_exit -eq 3 ]; then
            echo "FAIL: Circular dep detected (unexpected)"
            exit 1
        elif [ $build_exit -eq 4 ]; then
            echo "FAIL: Lock held (stale lock?)"
            exit 1
        fi
        echo "Build loop failure is expected if no agent model is running"
    fi

    # ── Post-run validation checks ──

    echo ""
    echo "--- Post-run validation ---"
    echo ""

    # a. FEATURE_BUILT signal check
    echo "a. Checking FEATURE_BUILT signal..."
    if echo "$build_output" | grep -q "FEATURE_BUILT"; then
        echo "   PASS: FEATURE_BUILT signal found"
    else
        echo "   FAIL: FEATURE_BUILT signal not found in build output"
        echo "   Hint: The build agent must output 'FEATURE_BUILT: {name}' on success"
        exit 1
    fi

    # b. Roadmap update check
    echo "b. Checking roadmap status update..."
    if grep -qE '(✅|🔄)' "$WORK_DIR/.specs/roadmap.md" 2>/dev/null; then
        echo "   PASS: Roadmap shows completion status"
    else
        echo "   FAIL: Roadmap was not updated — expected ✅ or 🔄 status"
        echo "   Current roadmap:"
        cat "$WORK_DIR/.specs/roadmap.md"
        exit 1
    fi

    # c. State file structure check
    echo "c. Checking state file structure..."
    local state_file="$WORK_DIR/.sdd-state/resume.json"
    if [ -f "$state_file" ]; then
        echo "   PASS: State file exists"
    else
        echo "   FAIL: State file not found at $state_file"
        exit 1
    fi

    if grep -q '"completed_features"' "$state_file" 2>/dev/null; then
        echo "   PASS: State file contains completed_features key"
    else
        echo "   FAIL: State file missing completed_features key"
        cat "$state_file"
        exit 1
    fi

    if grep -q '"current_branch"' "$state_file" 2>/dev/null; then
        echo "   PASS: State file contains current_branch key"
    else
        echo "   FAIL: State file missing current_branch key"
        cat "$state_file"
        exit 1
    fi

    if command -v jq &>/dev/null; then
        if jq . "$state_file" >/dev/null 2>&1; then
            echo "   PASS: State file is valid JSON"
        else
            echo "   FAIL: State file is not valid JSON"
            cat "$state_file"
            exit 1
        fi
    else
        echo "   SKIP: jq not available — JSON validation skipped"
    fi

    # d. Drift check signal (conditional)
    if [ "${DRIFT_CHECK:-false}" = "true" ]; then
        echo "d. Checking drift check signal..."
        if echo "$build_output" | grep -qE '(NO_DRIFT|DRIFT_FIXED)'; then
            echo "   PASS: Drift check signal found"
        else
            echo "   FAIL: Neither NO_DRIFT nor DRIFT_FIXED signal found in build output"
            echo "   Hint: When DRIFT_CHECK=true, the drift agent must output NO_DRIFT or DRIFT_FIXED"
            exit 1
        fi
    else
        echo "d. SKIP: Drift check disabled (DRIFT_CHECK=${DRIFT_CHECK:-false})"
    fi

    # Check if state was saved (informational)
    if [ -f "$state_file" ]; then
        echo ""
        echo "State file contents:"
        cat "$state_file"
    fi

    echo ""
    echo "=== Full dry run: ALL PASSED ==="
}

# ── Main ──────────────────────────────────────────────────────────────────────

echo "Dry-run integration test for build-loop-local.sh"
echo ""

setup

structural_test

if [ "${DRY_RUN_SKIP_AGENT:-false}" != "true" ]; then
    full_test
else
    echo ""
    echo "Skipping full test (DRY_RUN_SKIP_AGENT=true)"
fi

echo ""
echo "All dry-run tests passed."
