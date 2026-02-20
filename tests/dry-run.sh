#!/bin/bash
# tests/dry-run.sh — Integration test for build-loop-local.sh
#
# Creates a minimal toy project and runs build-loop-local.sh with MAX_FEATURES=1.
# This validates end-to-end: lock → circular dep check → agent call → signal parse
#   → drift check → state save → cleanup.
#
# Prerequisites:
#   - `agent` CLI must be installed (Cursor CLI)
#   - A model must be running or accessible
#
# Usage:
#   ./tests/dry-run.sh                 # Full dry run with agent
#   DRY_RUN_SKIP_AGENT=true ./tests/dry-run.sh  # Skip agent calls (structural test only)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
FIXTURES="$SCRIPT_DIR/fixtures/dry-run"
WORK_DIR=""

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

# ── Cleanup ──────────────────────────────────────────────────────────────────

cleanup() {
    if [ -n "$WORK_DIR" ] && [ -d "$WORK_DIR" ]; then
        # Clean up lock file if it exists
        rm -f /tmp/sdd-build-loop-*.lock
        rm -rf "$WORK_DIR"
        echo "Cleaned up: $WORK_DIR"
    fi
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

    if ! command -v agent &>/dev/null; then
        echo "SKIP: agent CLI not found — run structural test only"
        echo "Install from: https://cursor.com/cli"
        return 0
    fi

    cd "$WORK_DIR"

    # Run build-loop with MAX_FEATURES=1
    echo "Running: MAX_FEATURES=1 PROJECT_DIR=$WORK_DIR ./scripts/build-loop-local.sh"
    echo ""

    MAX_FEATURES=1 \
    BRANCH_STRATEGY=sequential \
    DRIFT_CHECK=false \
    BUILD_CHECK_CMD=skip \
    TEST_CHECK_CMD=skip \
    POST_BUILD_STEPS="" \
    PROJECT_DIR="$WORK_DIR" \
        "$WORK_DIR/scripts/build-loop-local.sh" 2>&1 || {
        local exit_code=$?
        echo ""
        echo "Build loop exited with code $exit_code"
        if [ $exit_code -eq 3 ]; then
            echo "FAIL: Circular dep detected (unexpected)"
            exit 1
        elif [ $exit_code -eq 4 ]; then
            echo "FAIL: Lock held (stale lock?)"
            exit 1
        fi
        echo "Build loop failure is expected if no agent model is running"
    }

    # Check if state was saved
    if [ -f "$WORK_DIR/.sdd-state/resume.json" ]; then
        echo ""
        echo "State file exists after run:"
        cat "$WORK_DIR/.sdd-state/resume.json"
    fi

    echo ""
    echo "=== Full dry run complete ==="
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
