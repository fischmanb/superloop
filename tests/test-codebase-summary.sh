#!/bin/bash
# tests/test-codebase-summary.sh — Unit tests for lib/codebase-summary.sh
#
# Run: ./tests/test-codebase-summary.sh
# Exit code 0 = all tests passed, 1 = failures
#
# Tests:
#   1. Normal project: section headers, component entries, type exports, import graph, learnings
#   2. Edge case: empty project dir (no src/, no .specs/)
#   3. Edge case: MAX_LINES truncation

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LIB="$PROJECT_ROOT/lib/codebase-summary.sh"

PASS=0
FAIL=0
TEST_TMPDIR=""

# ── Cleanup trap ──────────────────────────────────────────────────────────

cleanup() {
    if [ -n "$TEST_TMPDIR" ] && [ -d "$TEST_TMPDIR" ]; then
        rm -rf "$TEST_TMPDIR"
    fi
}
trap cleanup EXIT INT TERM

# ── Test framework ──────────────────────────────────────────────────────────

setup() {
    TEST_TMPDIR=$(mktemp -d)
    # Reset library guard so we can re-source
    _CODEBASE_SUMMARY_SH_LOADED=""
    source "$LIB"
}

teardown() {
    rm -rf "$TEST_TMPDIR"
    TEST_TMPDIR=""
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
        echo "    actual output (first 20 lines): $(echo "$haystack" | head -20)"
        FAIL=$((FAIL + 1))
    fi
}

assert_not_contains() {
    local desc="$1" needle="$2" haystack="$3"
    if echo "$haystack" | grep -qF "$needle"; then
        echo "  FAIL: $desc"
        echo "    expected NOT to contain: $needle"
        FAIL=$((FAIL + 1))
    else
        echo "  PASS: $desc"
        PASS=$((PASS + 1))
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

# ── Helper: create fixture project ────────────────────────────────────────

create_fixture_project() {
    local base="$1"

    # src/components/Button.tsx — has export default
    mkdir -p "$base/src/components"
    cat > "$base/src/components/Button.tsx" << 'TSXEOF'
import React from 'react';

interface ButtonProps {
  label: string;
  onClick: () => void;
}

export default function Button({ label, onClick }: ButtonProps) {
  return <button onClick={onClick}>{label}</button>;
}
TSXEOF

    # src/components/Header.tsx — has export default + local import of ./Button
    cat > "$base/src/components/Header.tsx" << 'TSXEOF'
import React from 'react';
import Button from './Button';

export default function Header() {
  return (
    <header>
      <h1>My App</h1>
      <Button label="Menu" onClick={() => {}} />
    </header>
  );
}
TSXEOF

    # src/types/index.ts — type and interface exports
    mkdir -p "$base/src/types"
    cat > "$base/src/types/index.ts" << 'TSEOF'
export type User = {
  id: string;
  name: string;
  email: string;
};

export interface ApiResponse {
  data: unknown;
  status: number;
  message: string;
}
TSEOF

    # src/utils/helpers.ts — a regular function export (not type)
    mkdir -p "$base/src/utils"
    cat > "$base/src/utils/helpers.ts" << 'TSEOF'
export function formatDate(date: Date): string {
  return date.toISOString().split('T')[0];
}
TSEOF

    # .specs/learnings/general.md — some learnings content
    mkdir -p "$base/.specs/learnings"
    cat > "$base/.specs/learnings/general.md" << 'MDEOF'
# General Learnings

- **Pattern**: Use semantic tokens for colors instead of hardcoded hex values.
- **Pattern**: Always validate user input at the boundary.
MDEOF
}

# ── Test: normal project scan ─────────────────────────────────────────────

test_normal_project() {
    echo ""
    echo "=== Normal project scan ==="
    setup

    local fixture_dir="$TEST_TMPDIR/project"
    mkdir -p "$fixture_dir"
    create_fixture_project "$fixture_dir"

    local output
    output=$(generate_codebase_summary "$fixture_dir")
    local exit_code=$?

    assert_exit_code "normal project exits 0" "0" "$exit_code"

    # Section headers present
    assert_contains "has Component Registry header" "## Component Registry" "$output"
    assert_contains "has Type Exports header" "## Type Exports" "$output"
    assert_contains "has Import Graph header" "## Import Graph" "$output"
    assert_contains "has Recent Learnings header" "## Recent Learnings" "$output"

    # Component Registry contents
    assert_contains "Button.tsx in component registry" "Button.tsx" "$output"
    assert_contains "Header.tsx in component registry" "Header.tsx" "$output"
    assert_contains "Button has export default" "Button.tsx  (export default: yes)" "$output"

    # Type Exports contents
    assert_contains "User type in type exports" "User" "$output"
    assert_contains "ApiResponse interface in type exports" "ApiResponse" "$output"

    # Import Graph contents
    assert_contains "Header imports Button" "Header.tsx" "$output"
    assert_contains "import path ./Button present" "./Button" "$output"

    # Recent Learnings contents
    assert_contains "learnings content appears" "semantic tokens" "$output"

    teardown
}

# ── Test: empty project ───────────────────────────────────────────────────

test_empty_project() {
    echo ""
    echo "=== Empty project (no src/, no .specs/) ==="
    setup

    local empty_dir="$TEST_TMPDIR/empty_project"
    mkdir -p "$empty_dir"

    local output
    local exit_code=0
    output=$(generate_codebase_summary "$empty_dir") || exit_code=$?

    assert_exit_code "empty project exits 0" "0" "$exit_code"

    # All section headers still present
    assert_contains "has Component Registry header" "## Component Registry" "$output"
    assert_contains "has Type Exports header" "## Type Exports" "$output"
    assert_contains "has Import Graph header" "## Import Graph" "$output"
    assert_contains "has Recent Learnings header" "## Recent Learnings" "$output"

    # Empty/not-found messages
    assert_contains "no components message" "No .tsx/.jsx files found" "$output"
    assert_contains "no learnings message" "No learnings directory found." "$output"

    teardown
}

# ── Test: MAX_LINES truncation ────────────────────────────────────────────

test_max_lines_truncation() {
    echo ""
    echo "=== MAX_LINES truncation ==="
    setup

    local fixture_dir="$TEST_TMPDIR/project_trunc"
    mkdir -p "$fixture_dir"
    create_fixture_project "$fixture_dir"

    local output
    output=$(generate_codebase_summary "$fixture_dir" 20)
    local exit_code=$?

    assert_exit_code "truncated run exits 0" "0" "$exit_code"

    # Output should contain truncation notice
    assert_contains "truncation notice present" "[Summary truncated at 20 lines]" "$output"

    # Line count should not exceed MAX_LINES + 1 (the truncation notice itself)
    local line_count
    line_count=$(echo "$output" | wc -l | tr -d ' ')
    if [ "$line_count" -le 21 ]; then
        echo "  PASS: line count ($line_count) within limit"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: line count ($line_count) exceeds MAX_LINES + 1 (21)"
        FAIL=$((FAIL + 1))
    fi

    teardown
}

# ── Run all tests ────────────────────────────────────────────────────────

echo "Running lib/codebase-summary.sh test suite..."

test_normal_project
test_empty_project
test_max_lines_truncation

echo ""
echo "═══════════════════════════════════════════════"
echo "Results: $PASS passed, $FAIL failed"
echo "═══════════════════════════════════════════════"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
exit 0
