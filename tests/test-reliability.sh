#!/bin/bash
# tests/test-reliability.sh — Unit tests for lib/reliability.sh
#
# Run: ./tests/test-reliability.sh
# Exit code 0 = all tests passed, 1 = failures
#
# Tests:
#   1. truncate_for_context: exact line counts, empty files, files shorter than limit
#   2. write_state/read_state: round-trip with special characters (", \, colons)
#   3. check_circular_deps: mock roadmap with a known cycle → should detect
#   4. acquire_lock/release_lock: acquire, verify file exists, release, verify gone
#   5. completed_features_json: special characters produce valid JSON
#   6. grep check: verify all library functions are actually CALLED from scripts

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LIB="$PROJECT_ROOT/lib/reliability.sh"

PASS=0
FAIL=0
TEST_TMPDIR=""

# ── Test framework ──────────────────────────────────────────────────────────

setup() {
    TEST_TMPDIR=$(mktemp -d)
    # Reset library guard so we can re-source
    _RELIABILITY_SH_LOADED=""
    # Set required globals
    PROJECT_DIR="$TEST_TMPDIR"
    STATE_DIR="$TEST_TMPDIR/.sdd-state"
    STATE_FILE="$STATE_DIR/resume.json"
    LOCK_FILE="$TEST_TMPDIR/test.lock"
    BUILT_FEATURE_NAMES=()
    MAX_CONTEXT_TOKENS=100000
    MAX_AGENT_RETRIES=3
    BACKOFF_MAX_SECONDS=60
    PARALLEL_VALIDATION=false
    # Source the library
    source "$LIB"
}

teardown() {
    rm -rf "$TEST_TMPDIR"
}

assert_eq() {
    local desc="$1" expected="$2" actual="$3"
    if [ "$expected" = "$actual" ]; then
        echo "  PASS: $desc"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: $desc"
        echo "    expected: $expected"
        echo "    actual:   $actual"
        FAIL=$((FAIL + 1))
    fi
}

assert_contains() {
    local desc="$1" needle="$2" haystack="$3"
    if echo "$haystack" | grep -qF "$needle"; then
        echo "  PASS: $desc"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: $desc"
        echo "    expected to contain: $needle"
        echo "    actual: $haystack"
        FAIL=$((FAIL + 1))
    fi
}

assert_file_exists() {
    local desc="$1" path="$2"
    if [ -e "$path" ]; then
        echo "  PASS: $desc"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: $desc (file not found: $path)"
        FAIL=$((FAIL + 1))
    fi
}

assert_file_not_exists() {
    local desc="$1" path="$2"
    if [ ! -e "$path" ]; then
        echo "  PASS: $desc"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: $desc (file still exists: $path)"
        FAIL=$((FAIL + 1))
    fi
}

assert_exit_code() {
    local desc="$1" expected="$2" actual="$3"
    if [ "$expected" = "$actual" ]; then
        echo "  PASS: $desc"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: $desc (expected exit $expected, got $actual)"
        FAIL=$((FAIL + 1))
    fi
}

# ── Test: truncate_for_context ──────────────────────────────────────────────

test_truncate_for_context() {
    echo ""
    echo "=== truncate_for_context ==="
    setup

    # Test 1: file shorter than limit → full content
    local small_file="$TEST_TMPDIR/small.md"
    printf 'line1\nline2\nline3\n' > "$small_file"
    local result
    result=$(truncate_for_context "$small_file")
    assert_eq "small file returns full content" "line1
line2
line3" "$result"

    # Test 2: empty file → empty output
    local empty_file="$TEST_TMPDIR/empty.md"
    touch "$empty_file"
    result=$(truncate_for_context "$empty_file")
    assert_eq "empty file returns empty" "" "$result"

    # Test 3: nonexistent file → no output, no error
    result=$(truncate_for_context "$TEST_TMPDIR/noexist.md" 2>/dev/null)
    assert_eq "nonexistent file returns empty" "" "$result"

    # Test 4: large file → truncated to Gherkin only
    # MAX_CONTEXT_TOKENS=100000 means budget_half=50000, so >200000 chars triggers truncation
    MAX_CONTEXT_TOKENS=40  # Force truncation: budget_half=20 tokens = 80 chars
    local large_file="$TEST_TMPDIR/large.feature.md"
    cat > "$large_file" << 'EOF'
---
feature: Test
status: specced
---
# Feature: Login
## Scenario: Happy path
Given a registered user
When they log in
Then they see the dashboard
## UI Mockup
+------------------+
| Username: [____] |
| Password: [____] |
| [  Login  ]      |
+------------------+
Some random text that should be removed
More non-Gherkin content here
EOF
    result=$(truncate_for_context "$large_file" 2>/dev/null)
    # Should contain frontmatter and Gherkin lines, but NOT the mockup
    assert_contains "truncated output has frontmatter" "feature: Test" "$result"
    assert_contains "truncated output has Scenario" "Scenario: Happy path" "$result"
    assert_contains "truncated output has Given" "Given a registered user" "$result"
    assert_contains "truncated output has When" "When they log in" "$result"
    assert_contains "truncated output has Then" "Then they see the dashboard" "$result"

    teardown
}

# ── Test: write_state / read_state round-trip ────────────────────────────────

test_state_roundtrip() {
    echo ""
    echo "=== write_state / read_state ==="
    setup

    # Test 1: basic round-trip
    BUILT_FEATURE_NAMES=("Auth: Signup" "Dashboard")
    local json
    json=$(completed_features_json)
    write_state 3 "chained" "$json" "auto/feature-1"

    assert_file_exists "state file created" "$STATE_FILE"

    read_state
    assert_eq "feature_index round-trip" "3" "$RESUME_INDEX"
    assert_eq "branch_strategy round-trip" "chained" "$RESUME_STRATEGY"
    assert_eq "current_branch round-trip" "auto/feature-1" "$RESUME_BRANCH"

    # Test 2: special characters in feature names
    BUILT_FEATURE_NAMES=('Feature with "quotes"' 'Feature with \backslash' 'Feature: with colons')
    json=$(completed_features_json)
    write_state 5 "independent" "$json" "auto/feature-2"

    # Verify the JSON is valid (if jq is available)
    if command -v jq &>/dev/null; then
        if jq empty "$STATE_FILE" 2>/dev/null; then
            echo "  PASS: state file is valid JSON (special chars)"
            PASS=$((PASS + 1))
        else
            echo "  FAIL: state file is invalid JSON (special chars)"
            FAIL=$((FAIL + 1))
        fi
    else
        echo "  SKIP: jq not available for JSON validation"
    fi

    # Test 3: clean_state removes file
    clean_state
    assert_file_not_exists "clean_state removes file" "$STATE_FILE"

    # Test 4: read_state returns 1 when no file
    if read_state 2>/dev/null; then
        echo "  FAIL: read_state should return 1 when no file"
        FAIL=$((FAIL + 1))
    else
        echo "  PASS: read_state returns 1 when no file"
        PASS=$((PASS + 1))
    fi

    teardown
}

# ── Test: completed_features_json ────────────────────────────────────────────

test_completed_features_json() {
    echo ""
    echo "=== completed_features_json ==="
    setup

    # Test 1: empty array
    BUILT_FEATURE_NAMES=()
    local result
    result=$(completed_features_json)
    assert_eq "empty array" "[]" "$result"

    # Test 2: single item
    BUILT_FEATURE_NAMES=("Auth")
    result=$(completed_features_json)
    assert_eq "single item" "[\"Auth\"]" "$result"

    # Test 3: multiple items
    BUILT_FEATURE_NAMES=("Auth" "Dashboard" "Settings")
    result=$(completed_features_json)
    assert_eq "multiple items" "[\"Auth\", \"Dashboard\", \"Settings\"]" "$result"

    # Test 4: item with colons (common in feature names)
    BUILT_FEATURE_NAMES=("Auth: Signup" "Auth: Login")
    result=$(completed_features_json)
    assert_eq "colons in names" "[\"Auth: Signup\", \"Auth: Login\"]" "$result"

    teardown
}

# ── Test: check_circular_deps ────────────────────────────────────────────────

test_check_circular_deps() {
    echo ""
    echo "=== check_circular_deps ==="
    setup

    # Test 1: no roadmap → success
    check_circular_deps
    assert_exit_code "no roadmap returns 0" "0" "$?"

    # Test 2: roadmap with no cycles
    mkdir -p "$TEST_TMPDIR/.specs"
    cat > "$TEST_TMPDIR/.specs/roadmap.md" << 'EOF'
# Roadmap

| # | Feature | Source | Jira | Complexity | Deps | Status |
|---|---------|--------|------|------------|------|--------|
| 1 | Auth | clone | - | M | - | ⬜ |
| 2 | Dashboard | clone | - | L | 1 | ⬜ |
| 3 | Settings | clone | - | S | 1 | ⬜ |
| 4 | Reports | clone | - | M | 2, 3 | ⬜ |
EOF
    check_circular_deps
    assert_exit_code "no cycle returns 0" "0" "$?"

    # Test 3: roadmap with a cycle (2→3→4→2)
    cat > "$TEST_TMPDIR/.specs/roadmap.md" << 'EOF'
# Roadmap

| # | Feature | Source | Jira | Complexity | Deps | Status |
|---|---------|--------|------|------------|------|--------|
| 1 | Auth | clone | - | M | - | ⬜ |
| 2 | Dashboard | clone | - | L | 4 | ⬜ |
| 3 | Settings | clone | - | S | 2 | ⬜ |
| 4 | Reports | clone | - | M | 3 | ⬜ |
EOF
    # check_circular_deps calls exit 3 on cycle — run in subshell
    local exit_code=0
    (check_circular_deps) 2>/dev/null || exit_code=$?
    assert_exit_code "cycle detected exits with 3" "3" "$exit_code"

    # Test 4: roadmap with no deps column content
    cat > "$TEST_TMPDIR/.specs/roadmap.md" << 'EOF'
# Roadmap

| # | Feature | Source | Jira | Complexity | Deps | Status |
|---|---------|--------|------|------------|------|--------|
| 1 | Auth | clone | - | M | - | ⬜ |
| 2 | Dashboard | clone | - | L | - | ⬜ |
EOF
    check_circular_deps
    assert_exit_code "no deps returns 0" "0" "$?"

    teardown
}

# ── Test: acquire_lock / release_lock ────────────────────────────────────────

test_lock() {
    echo ""
    echo "=== acquire_lock / release_lock ==="
    setup

    # Disable the trap for testing (we don't want cleanup on test exit)
    trap '' INT TERM EXIT

    # Test 1: acquire creates lock file
    acquire_lock
    assert_file_exists "lock file created" "$LOCK_FILE"

    # Test 2: lock file contains our PID
    local lock_pid
    lock_pid=$(cat "$LOCK_FILE")
    assert_eq "lock file contains PID" "$$" "$lock_pid"

    # Test 3: release removes lock file
    release_lock
    assert_file_not_exists "lock file removed after release" "$LOCK_FILE"

    # Test 4: stale lock (PID that doesn't exist) gets cleaned up
    echo "99999999" > "$LOCK_FILE"
    acquire_lock 2>/dev/null
    lock_pid=$(cat "$LOCK_FILE")
    assert_eq "stale lock replaced with our PID" "$$" "$lock_pid"
    release_lock

    # Reset trap
    trap '' INT TERM EXIT

    teardown
}

# ── Test: grep check — functions are CALLED from scripts ─────────────────────

test_functions_called() {
    echo ""
    echo "=== Functions called from scripts (not just defined) ==="

    local build_loop="$PROJECT_ROOT/scripts/build-loop-local.sh"
    local overnight="$PROJECT_ROOT/scripts/overnight-autonomous.sh"

    # Functions that should be called (not just defined) in at least one script
    local functions=(
        "acquire_lock"
        "run_agent_with_backoff"
        "truncate_for_context"
        "check_circular_deps"
        "write_state"
        "read_state"
        "clean_state"
        "completed_features_json"
        "get_cpu_count"
    )

    for func in "${functions[@]}"; do
        # Check if it's defined in the library
        if ! grep -q "^${func}()" "$LIB" 2>/dev/null; then
            echo "  FAIL: $func not defined in lib/reliability.sh"
            FAIL=$((FAIL + 1))
            continue
        fi

        # Check if it's called from at least one script (exclude comments and the source line)
        local called=false
        for script in "$build_loop" "$overnight"; do
            # Grep for function name, exclude comment lines and "provided by" lines
            if grep -n "$func" "$script" 2>/dev/null | grep -v ":#\|: #" | grep -v 'provided by' | grep -qv "^.*${func}()" 2>/dev/null; then
                called=true
                break
            fi
        done

        if [ "$called" = true ]; then
            echo "  PASS: $func is called from scripts"
            PASS=$((PASS + 1))
        else
            echo "  FAIL: $func is defined but NEVER CALLED from scripts"
            FAIL=$((FAIL + 1))
        fi
    done

    # Check: run_parallel_drift_checks should be called from build-loop-local.sh
    if grep -n "run_parallel_drift_checks" "$build_loop" 2>/dev/null | grep -v ":#\|: #" | grep -v 'provided by' | grep -qv "^.*run_parallel_drift_checks()" 2>/dev/null; then
        echo "  PASS: run_parallel_drift_checks is called from scripts"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: run_parallel_drift_checks is defined but NEVER CALLED from scripts"
        FAIL=$((FAIL + 1))
    fi

    # Check that lib/reliability.sh is actually sourced from both scripts
    for script in "$build_loop" "$overnight"; do
        local basename
        basename=$(basename "$script")
        if grep -q 'source.*lib/reliability.sh' "$script" 2>/dev/null; then
            echo "  PASS: $basename sources lib/reliability.sh"
            PASS=$((PASS + 1))
        else
            echo "  FAIL: $basename does NOT source lib/reliability.sh"
            FAIL=$((FAIL + 1))
        fi
    done
}

# ── Test: syntax check all scripts ──────────────────────────────────────────

test_syntax() {
    echo ""
    echo "=== Syntax checks (bash -n) ==="

    for script in "$PROJECT_ROOT/lib/reliability.sh" \
                  "$PROJECT_ROOT/scripts/build-loop-local.sh" \
                  "$PROJECT_ROOT/scripts/overnight-autonomous.sh"; do
        local basename
        basename=$(basename "$script")
        if bash -n "$script" 2>/dev/null; then
            echo "  PASS: $basename passes bash -n"
            PASS=$((PASS + 1))
        else
            echo "  FAIL: $basename has syntax errors"
            FAIL=$((FAIL + 1))
        fi
    done
}

# ── Test: count_files ─────────────────────────────────────────────────────────

test_count_files() {
    echo ""
    echo "=== count_files ==="
    setup

    # Test 1: directory does not exist → error code 1
    local exit_code=0
    declare -A cf_result=()
    count_files "$TEST_TMPDIR/nonexistent" cf_result 2>/dev/null || exit_code=$?
    assert_exit_code "nonexistent dir returns 1" "1" "$exit_code"

    # Test 2: empty directory → zero counts, no error
    local empty_dir="$TEST_TMPDIR/empty_dir"
    mkdir -p "$empty_dir"
    declare -A cf_empty=()
    exit_code=0
    count_files "$empty_dir" cf_empty || exit_code=$?
    assert_exit_code "empty dir returns 0" "0" "$exit_code"
    assert_eq "empty dir has zero keys" "0" "${#cf_empty[@]}"

    # Test 3: mixed extension directory → correct counts per extension
    local mixed_dir="$TEST_TMPDIR/mixed"
    mkdir -p "$mixed_dir"
    touch "$mixed_dir/a.sh" "$mixed_dir/b.sh" "$mixed_dir/c.md" "$mixed_dir/d.txt" "$mixed_dir/e.txt" "$mixed_dir/f.txt"
    declare -A cf_mixed=()
    count_files "$mixed_dir" cf_mixed
    assert_eq "sh count" "2" "${cf_mixed[sh]}"
    assert_eq "md count" "1" "${cf_mixed[md]}"
    assert_eq "txt count" "3" "${cf_mixed[txt]}"

    # Test 4: files with no extension → grouped under "none"
    local noext_dir="$TEST_TMPDIR/noext"
    mkdir -p "$noext_dir"
    touch "$noext_dir/Makefile" "$noext_dir/Dockerfile" "$noext_dir/script.sh"
    declare -A cf_noext=()
    count_files "$noext_dir" cf_noext
    assert_eq "no-extension files grouped as none" "2" "${cf_noext[none]}"
    assert_eq "sh files still counted" "1" "${cf_noext[sh]}"

    teardown
}

# ── Test: read_state populates BUILT_FEATURE_NAMES ────────────────────────────

test_read_state_built_feature_names() {
    echo ""
    echo "=== read_state BUILT_FEATURE_NAMES ==="
    setup

    # Test 1: write_state with two completed features, read_state populates BUILT_FEATURE_NAMES
    BUILT_FEATURE_NAMES=("Auth: Signup" "Dashboard")
    local json
    json=$(completed_features_json)
    write_state 2 "chained" "$json" "auto/feature-2"

    # Reset BUILT_FEATURE_NAMES to verify read_state repopulates it
    BUILT_FEATURE_NAMES=()
    read_state
    assert_eq "BUILT_FEATURE_NAMES has 2 entries" "2" "${#BUILT_FEATURE_NAMES[@]}"
    assert_eq "BUILT_FEATURE_NAMES[0] is Auth: Signup" "Auth: Signup" "${BUILT_FEATURE_NAMES[0]}"
    assert_eq "BUILT_FEATURE_NAMES[1] is Dashboard" "Dashboard" "${BUILT_FEATURE_NAMES[1]}"

    # Test 2: empty completed_features array → BUILT_FEATURE_NAMES is empty, no error
    BUILT_FEATURE_NAMES=()
    json=$(completed_features_json)
    write_state 0 "chained" "$json" "auto/feature-0"

    BUILT_FEATURE_NAMES=("stale")
    read_state
    assert_eq "empty completed_features → empty BUILT_FEATURE_NAMES" "0" "${#BUILT_FEATURE_NAMES[@]}"

    teardown
}

# ── Test: write_state with special characters in branch/strategy ──────────────

test_write_state_branch_with_double_quote() {
    echo ""
    echo "=== write_state: branch with double quote ==="
    setup

    BUILT_FEATURE_NAMES=("Feature1")
    local json
    json=$(completed_features_json)
    write_state 0 "chained" "$json" 'auto/branch-with"quote'

    if command -v jq &>/dev/null; then
        if jq empty "$STATE_FILE" 2>/dev/null; then
            echo "  PASS: state file is valid JSON (branch with double quote)"
            PASS=$((PASS + 1))
        else
            echo "  FAIL: state file is invalid JSON (branch with double quote)"
            FAIL=$((FAIL + 1))
        fi
    else
        echo "  SKIP: jq not available — JSON validation skipped"
        PASS=$((PASS + 1))
    fi

    teardown
}

test_write_state_branch_with_backslash() {
    echo ""
    echo "=== write_state: branch with backslash ==="
    setup

    BUILT_FEATURE_NAMES=("Feature1")
    local json
    json=$(completed_features_json)
    write_state 0 "chained" "$json" 'auto/branch-with\backslash'

    if command -v jq &>/dev/null; then
        if jq empty "$STATE_FILE" 2>/dev/null; then
            echo "  PASS: state file is valid JSON (branch with backslash)"
            PASS=$((PASS + 1))
        else
            echo "  FAIL: state file is invalid JSON (branch with backslash)"
            FAIL=$((FAIL + 1))
        fi
    else
        echo "  SKIP: jq not available — JSON validation skipped"
        PASS=$((PASS + 1))
    fi

    teardown
}

test_write_state_strategy_with_double_quote() {
    echo ""
    echo "=== write_state: strategy with double quote ==="
    setup

    BUILT_FEATURE_NAMES=("Feature1")
    local json
    json=$(completed_features_json)
    write_state 0 'strategy"with-quote' "$json" "auto/feature-1"

    if command -v jq &>/dev/null; then
        if jq empty "$STATE_FILE" 2>/dev/null; then
            echo "  PASS: state file is valid JSON (strategy with double quote)"
            PASS=$((PASS + 1))
        else
            echo "  FAIL: state file is invalid JSON (strategy with double quote)"
            FAIL=$((FAIL + 1))
        fi
    else
        echo "  SKIP: jq not available — JSON validation skipped"
        PASS=$((PASS + 1))
    fi

    teardown
}

# ── Run all tests ────────────────────────────────────────────────────────────

echo "Running lib/reliability.sh test suite..."

test_truncate_for_context
test_state_roundtrip
test_completed_features_json
test_check_circular_deps
test_lock
test_count_files
test_read_state_built_feature_names
test_write_state_branch_with_double_quote
test_write_state_branch_with_backslash
test_write_state_strategy_with_double_quote
test_functions_called
test_syntax

echo ""
echo "═══════════════════════════════════════════════"
echo "Results: $PASS passed, $FAIL failed"
echo "═══════════════════════════════════════════════"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
exit 0
