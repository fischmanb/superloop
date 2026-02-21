#!/bin/bash
# tests/test-validation.sh — Unit tests for lib/validation.sh
#
# Run: ./tests/test-validation.sh
# Exit code 0 = all tests passed, 1 = failures
#
# Tests:
#   1. validate_frontmatter: valid frontmatter passes
#   2. validate_frontmatter: missing required field fails
#   3. validate_frontmatter: malformed YAML (missing markers) fails
#   4. validate_frontmatter: empty file fails
#   5. validate_frontmatter: missing closing --- marker fails

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LIB="$PROJECT_ROOT/lib/validation.sh"

PASS=0
FAIL=0
TEST_TMPDIR=""

# ── Test framework ──────────────────────────────────────────────────────────

setup() {
    TEST_TMPDIR=$(mktemp -d)
    # Reset library guard so we can re-source
    _VALIDATION_SH_LOADED=""
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

# ── Test: validate_frontmatter ────────────────────────────────────────────────

test_validate_frontmatter() {
    echo ""
    echo "=== validate_frontmatter ==="
    setup

    # Test 1: valid frontmatter passes
    local valid_file="$TEST_TMPDIR/valid.feature.md"
    cat > "$valid_file" << 'EOF'
---
feature: User Login
domain: auth
source: src/auth/login.tsx
status: specced
created: 2026-01-15
---
# Feature: User Login

## Scenario: Happy path
Given a registered user
When they submit valid credentials
Then they are redirected to the dashboard
EOF
    local exit_code=0
    validate_frontmatter "$valid_file" 2>/dev/null || exit_code=$?
    assert_exit_code "valid frontmatter passes" "0" "$exit_code"

    # Test 2: missing required field 'feature' fails
    local no_feature="$TEST_TMPDIR/no-feature.feature.md"
    cat > "$no_feature" << 'EOF'
---
domain: auth
status: specced
---
# Some content
EOF
    exit_code=0
    validate_frontmatter "$no_feature" 2>/dev/null || exit_code=$?
    assert_exit_code "missing 'feature' field fails" "1" "$exit_code"

    # Test 3: missing required field 'domain' fails
    local no_domain="$TEST_TMPDIR/no-domain.feature.md"
    cat > "$no_domain" << 'EOF'
---
feature: User Login
status: specced
---
# Some content
EOF
    exit_code=0
    validate_frontmatter "$no_domain" 2>/dev/null || exit_code=$?
    assert_exit_code "missing 'domain' field fails" "1" "$exit_code"

    # Test 4: malformed YAML — missing opening --- marker
    local no_open="$TEST_TMPDIR/no-open.feature.md"
    cat > "$no_open" << 'EOF'
feature: User Login
domain: auth
---
# Some content
EOF
    exit_code=0
    validate_frontmatter "$no_open" 2>/dev/null || exit_code=$?
    assert_exit_code "missing opening --- marker fails" "1" "$exit_code"

    # Test 5: malformed YAML — missing closing --- marker
    local no_close="$TEST_TMPDIR/no-close.feature.md"
    cat > "$no_close" << 'EOF'
---
feature: User Login
domain: auth
status: specced
# Some content without closing marker
EOF
    exit_code=0
    validate_frontmatter "$no_close" 2>/dev/null || exit_code=$?
    assert_exit_code "missing closing --- marker fails" "1" "$exit_code"

    # Test 6: empty file fails
    local empty_file="$TEST_TMPDIR/empty.feature.md"
    touch "$empty_file"
    exit_code=0
    validate_frontmatter "$empty_file" 2>/dev/null || exit_code=$?
    assert_exit_code "empty file fails" "1" "$exit_code"

    teardown
}

# ── Test: syntax check ───────────────────────────────────────────────────────

test_syntax() {
    echo ""
    echo "=== Syntax checks (bash -n) ==="

    if bash -n "$LIB" 2>/dev/null; then
        echo "  PASS: validation.sh passes bash -n"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: validation.sh has syntax errors"
        FAIL=$((FAIL + 1))
    fi

    if bash -n "$PROJECT_ROOT/scripts/generate-mapping.sh" 2>/dev/null; then
        echo "  PASS: generate-mapping.sh passes bash -n"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: generate-mapping.sh has syntax errors"
        FAIL=$((FAIL + 1))
    fi
}

# ── Test: generate-mapping.sh sources lib/validation.sh ───────────────────────

test_sourcing() {
    echo ""
    echo "=== Sourcing checks ==="

    if grep -q 'source.*lib/validation.sh' "$PROJECT_ROOT/scripts/generate-mapping.sh" 2>/dev/null; then
        echo "  PASS: generate-mapping.sh sources lib/validation.sh"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: generate-mapping.sh does NOT source lib/validation.sh"
        FAIL=$((FAIL + 1))
    fi

    # validate_frontmatter should NOT be defined locally in generate-mapping.sh
    if grep -q '^validate_frontmatter()' "$PROJECT_ROOT/scripts/generate-mapping.sh" 2>/dev/null; then
        echo "  FAIL: generate-mapping.sh still has local validate_frontmatter definition"
        FAIL=$((FAIL + 1))
    else
        echo "  PASS: validate_frontmatter is not locally defined in generate-mapping.sh"
        PASS=$((PASS + 1))
    fi
}

# ── Run all tests ────────────────────────────────────────────────────────────

echo "Running lib/validation.sh test suite..."

test_validate_frontmatter
test_syntax
test_sourcing

echo ""
echo "═══════════════════════════════════════════════"
echo "Results: $PASS passed, $FAIL failed"
echo "═══════════════════════════════════════════════"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
exit 0
