#!/usr/bin/env bash
# tests/test-eval.sh — Unit tests for lib/eval.sh
#
# Run: ./tests/test-eval.sh
# Exit code 0 = all tests passed, 1 = failures
#
# Tests:
#   1. Mechanical eval: expected JSON fields, correct counts
#   2. Mechanical eval: merge commit skipping
#   3. Mechanical eval: first commit handling
#   4. Mechanical eval: error cases (missing args)
#   5. Eval prompt: contains commit hash and safety instructions
#   6. Signal parsing: present and missing signals
#   7. Write eval result: full agent + mechanical merge
#   8. Write eval result: agent-less (no agent output)
#   9. Write eval result: malformed agent output

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LIB="$PROJECT_ROOT/lib/eval.sh"

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
    _EVAL_SH_LOADED=""
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

# ── Helper: create a fixture git repo simulating a React/TS project ──────

create_fixture_repo() {
    local repo_dir="$1"
    mkdir -p "$repo_dir"
    git -C "$repo_dir" init -q

    git -C "$repo_dir" config user.email "test@test.com"
    git -C "$repo_dir" config user.name "Test User"
    git -C "$repo_dir" config commit.gpgsign false

    # Initial commit: base project structure
    mkdir -p "$repo_dir/src/components"
    mkdir -p "$repo_dir/src/types"

    cat > "$repo_dir/src/types/index.ts" << 'EOF'
export type User = {
  id: string;
  name: string;
};

export interface ApiResponse {
  data: unknown;
  status: number;
}
EOF

    cat > "$repo_dir/src/components/Button.tsx" << 'EOF'
import React from 'react';

export interface ButtonProps {
  label: string;
  onClick: () => void;
}

export default function Button({ label, onClick }: ButtonProps) {
  return <button onClick={onClick}>{label}</button>;
}
EOF

    # CLAUDE.md for prompt generation tests
    cat > "$repo_dir/CLAUDE.md" << 'EOF'
# Test Project
This project uses spec-driven development.
EOF

    mkdir -p "$repo_dir/.specs/learnings"
    cat > "$repo_dir/.specs/learnings/index.md" << 'EOF'
# Learnings Index
- Always validate inputs at boundaries
EOF

    git -C "$repo_dir" add -A
    git -C "$repo_dir" commit -q -m "feat: initial project setup"

    # Feature commit: add Header component + test file
    cat > "$repo_dir/src/components/Header.tsx" << 'EOF'
import React from 'react';
import Button from './Button';

export type HeaderVariant = 'primary' | 'secondary';

export default function Header() {
  return (
    <header>
      <h1>My App</h1>
      <Button label="Menu" onClick={() => {}} />
    </header>
  );
}
EOF

    mkdir -p "$repo_dir/tests"
    cat > "$repo_dir/tests/Header.test.tsx" << 'EOF'
import { render } from '@testing-library/react';
import Header from '../src/components/Header';

test('renders header', () => {
  const { getByText } = render(<Header />);
  expect(getByText('My App')).toBeInTheDocument();
});
EOF

    git -C "$repo_dir" add -A
    git -C "$repo_dir" commit -q -m "feat: add Header component with tests"
}

# ── Test: mechanical eval — normal feature commit ──────────────────────────

test_mechanical_eval_normal() {
    echo ""
    echo "=== Mechanical eval: normal feature commit ==="
    setup

    local repo_dir="$TEST_TMPDIR/repo"
    create_fixture_repo "$repo_dir"

    local commit_hash
    commit_hash=$(git -C "$repo_dir" rev-parse HEAD)

    local output
    local exit_code=0
    output=$(run_mechanical_eval "$repo_dir" "$commit_hash") || exit_code=$?

    assert_exit_code "mechanical eval exits 0" "0" "$exit_code"

    # JSON fields present
    assert_contains "has commit field" "\"commit\":" "$output"
    assert_contains "has feature_name field" "\"feature_name\":" "$output"
    assert_contains "has files_changed field" "\"files_changed\":" "$output"
    assert_contains "has lines_added field" "\"lines_added\":" "$output"
    assert_contains "has lines_removed field" "\"lines_removed\":" "$output"
    assert_contains "has new_type_exports field" "\"new_type_exports\":" "$output"
    assert_contains "has type_redeclarations field" "\"type_redeclarations\":" "$output"
    assert_contains "has import_count field" "\"import_count\":" "$output"
    assert_contains "has test_files_touched field" "\"test_files_touched\":" "$output"

    # Verify correct values
    assert_contains "commit hash in output" "$commit_hash" "$output"
    assert_contains "feature name extracted" "add Header component with tests" "$output"
    assert_contains "files_changed is 2" "\"files_changed\": 2" "$output"
    assert_contains "test files were touched" "\"test_files_touched\": true" "$output"

    teardown
}

# ── Test: mechanical eval — first commit ────────────────────────────────────

test_mechanical_eval_first_commit() {
    echo ""
    echo "=== Mechanical eval: first commit ==="
    setup

    local repo_dir="$TEST_TMPDIR/first_repo"
    mkdir -p "$repo_dir"
    git -C "$repo_dir" init -q
    git -C "$repo_dir" config user.email "test@test.com"
    git -C "$repo_dir" config user.name "Test User"
    git -C "$repo_dir" config commit.gpgsign false

    cat > "$repo_dir/README.md" << 'EOF'
# Hello
Initial file.
EOF

    git -C "$repo_dir" add -A
    git -C "$repo_dir" commit -q -m "feat: initial commit"

    local commit_hash
    commit_hash=$(git -C "$repo_dir" rev-parse HEAD)

    local output
    local exit_code=0
    output=$(run_mechanical_eval "$repo_dir" "$commit_hash") || exit_code=$?

    assert_exit_code "first commit eval exits 0" "0" "$exit_code"
    assert_contains "files_changed is 1" "\"files_changed\": 1" "$output"
    assert_contains "has commit field" "\"commit\":" "$output"
    assert_not_contains "not skipped" "\"skipped\":" "$output"

    teardown
}

# ── Test: mechanical eval — merge commit ────────────────────────────────────

test_mechanical_eval_merge_commit() {
    echo ""
    echo "=== Mechanical eval: merge commit ==="
    setup

    local repo_dir="$TEST_TMPDIR/merge_repo"
    mkdir -p "$repo_dir"
    git -C "$repo_dir" init -q
    git -C "$repo_dir" config user.email "test@test.com"
    git -C "$repo_dir" config user.name "Test User"
    git -C "$repo_dir" config commit.gpgsign false

    echo "base" > "$repo_dir/file.txt"
    git -C "$repo_dir" add -A
    git -C "$repo_dir" commit -q -m "initial"

    git -C "$repo_dir" checkout -q -b feature
    echo "feature" > "$repo_dir/feature.txt"
    git -C "$repo_dir" add -A
    git -C "$repo_dir" commit -q -m "add feature"

    git -C "$repo_dir" checkout -q master 2>/dev/null || git -C "$repo_dir" checkout -q main
    echo "main change" > "$repo_dir/main.txt"
    git -C "$repo_dir" add -A
    git -C "$repo_dir" commit -q -m "main change"

    git -C "$repo_dir" merge -q --no-ff feature -m "Merge feature"

    local merge_hash
    merge_hash=$(git -C "$repo_dir" rev-parse HEAD)

    local output
    local exit_code=0
    output=$(run_mechanical_eval "$repo_dir" "$merge_hash") || exit_code=$?

    assert_exit_code "merge commit eval exits 0" "0" "$exit_code"
    assert_contains "merge commit is skipped" "\"skipped\": true" "$output"
    assert_contains "reason is merge commit" "\"reason\": \"merge commit\"" "$output"

    teardown
}

# ── Test: mechanical eval — error cases ──────────────────────────────────────

test_mechanical_eval_errors() {
    echo ""
    echo "=== Mechanical eval: error cases ==="
    setup

    # Missing project_dir
    local output
    local exit_code=0
    output=$(run_mechanical_eval "" "abc123") || exit_code=$?
    assert_exit_code "missing project_dir returns 1" "1" "$exit_code"
    assert_contains "error mentions project_dir" "project_dir is required" "$output"

    # Missing commit_hash
    exit_code=0
    output=$(run_mechanical_eval "/tmp" "") || exit_code=$?
    assert_exit_code "missing commit_hash returns 1" "1" "$exit_code"
    assert_contains "error mentions commit_hash" "commit_hash is required" "$output"

    teardown
}

# ── Test: generate_eval_prompt ──────────────────────────────────────────────

test_generate_eval_prompt() {
    echo ""
    echo "=== Generate eval prompt ==="
    setup

    local repo_dir="$TEST_TMPDIR/prompt_repo"
    create_fixture_repo "$repo_dir"

    local commit_hash
    commit_hash=$(git -C "$repo_dir" rev-parse HEAD)

    local output
    local exit_code=0
    output=$(generate_eval_prompt "$repo_dir" "$commit_hash") || exit_code=$?

    assert_exit_code "prompt generation exits 0" "0" "$exit_code"
    assert_contains "prompt contains commit hash" "$commit_hash" "$output"
    assert_contains "prompt contains safety: no modify" "do NOT modify any files" "$output"
    assert_contains "prompt contains safety: no commit" "do NOT commit" "$output"
    assert_contains "prompt contains safety: no input" "do NOT ask for user input" "$output"
    assert_contains "prompt contains CLAUDE.md content" "spec-driven development" "$output"
    assert_contains "prompt contains learnings" "validate inputs at boundaries" "$output"
    assert_contains "prompt contains EVAL_COMPLETE signal" "EVAL_COMPLETE" "$output"
    assert_contains "prompt contains EVAL_FRAMEWORK_COMPLIANCE signal" "EVAL_FRAMEWORK_COMPLIANCE" "$output"
    assert_contains "prompt contains EVAL_SCOPE_ASSESSMENT signal" "EVAL_SCOPE_ASSESSMENT" "$output"

    teardown
}

# ── Test: parse_eval_signal ────────────────────────────────────────────────

test_parse_eval_signal() {
    echo ""
    echo "=== Parse eval signal ==="
    setup

    local sample_output
    sample_output=$(cat <<'EOF'
Some preamble text here.
EVAL_COMPLETE: true
EVAL_FRAMEWORK_COMPLIANCE: pass
EVAL_SCOPE_ASSESSMENT: focused
EVAL_INTEGRATION_QUALITY: clean
EVAL_REPEATED_MISTAKES: none
EVAL_NOTES: Clean commit following project conventions
EOF
)

    local result

    result=$(parse_eval_signal "EVAL_COMPLETE" "$sample_output")
    assert_eq "parses EVAL_COMPLETE" "true" "$result"

    result=$(parse_eval_signal "EVAL_FRAMEWORK_COMPLIANCE" "$sample_output")
    assert_eq "parses EVAL_FRAMEWORK_COMPLIANCE" "pass" "$result"

    result=$(parse_eval_signal "EVAL_SCOPE_ASSESSMENT" "$sample_output")
    assert_eq "parses EVAL_SCOPE_ASSESSMENT" "focused" "$result"

    result=$(parse_eval_signal "EVAL_NOTES" "$sample_output")
    assert_eq "parses EVAL_NOTES" "Clean commit following project conventions" "$result"

    # Missing signal returns empty string
    result=$(parse_eval_signal "EVAL_NONEXISTENT" "$sample_output")
    assert_eq "missing signal returns empty" "" "$result"

    teardown
}

# ── Test: write_eval_result — full (agent + mechanical) ────────────────────

test_write_eval_result_full() {
    echo ""
    echo "=== Write eval result: full ==="
    setup

    local out_dir="$TEST_TMPDIR/eval_output"

    local mech_json='{"commit":"abc123","files_changed":3,"lines_added":50,"lines_removed":10}'

    local agent_output
    agent_output=$(cat <<'EOF'
EVAL_COMPLETE: true
EVAL_FRAMEWORK_COMPLIANCE: pass
EVAL_SCOPE_ASSESSMENT: focused
EVAL_INTEGRATION_QUALITY: clean
EVAL_REPEATED_MISTAKES: none
EVAL_NOTES: Solid implementation
EOF
)

    local result_file
    local exit_code=0
    result_file=$(write_eval_result "$out_dir" "header-component" "$mech_json" "$agent_output") || exit_code=$?

    assert_exit_code "write_eval_result exits 0" "0" "$exit_code"

    # Check file was created
    if [ -f "$result_file" ]; then
        echo "  PASS: result file created"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: result file not created at $result_file"
        FAIL=$((FAIL + 1))
    fi

    local file_content
    file_content=$(cat "$result_file")

    assert_contains "result has agent_eval_available true" "\"agent_eval_available\": true" "$file_content"
    assert_contains "result has framework_compliance" "\"framework_compliance\": \"pass\"" "$file_content"
    assert_contains "result has mechanical data" "\"mechanical\":" "$file_content"
    assert_contains "result has eval_timestamp" "\"eval_timestamp\":" "$file_content"

    teardown
}

# ── Test: write_eval_result — no agent output ──────────────────────────────

test_write_eval_result_no_agent() {
    echo ""
    echo "=== Write eval result: no agent output ==="
    setup

    local out_dir="$TEST_TMPDIR/eval_output2"
    local mech_json='{"commit":"def456","files_changed":1}'

    local result_file
    local exit_code=0
    result_file=$(write_eval_result "$out_dir" "simple-fix" "$mech_json" "") || exit_code=$?

    assert_exit_code "write_eval_result (no agent) exits 0" "0" "$exit_code"

    local file_content
    file_content=$(cat "$result_file")

    assert_contains "result has agent_eval_available false" "\"agent_eval_available\": false" "$file_content"
    assert_contains "result has mechanical data" "\"mechanical\":" "$file_content"
    assert_not_contains "no agent_eval section" "\"agent_eval\":" "$file_content"

    teardown
}

# ── Test: write_eval_result — malformed agent output ────────────────────────

test_write_eval_result_malformed_agent() {
    echo ""
    echo "=== Write eval result: malformed agent output ==="
    setup

    local out_dir="$TEST_TMPDIR/eval_output3"
    local mech_json='{"commit":"ghi789","files_changed":2}'

    # Agent output without EVAL_COMPLETE signal
    local bad_output="Some random text without any signals"

    local result_file
    local exit_code=0
    result_file=$(write_eval_result "$out_dir" "broken-eval" "$mech_json" "$bad_output") || exit_code=$?

    assert_exit_code "write_eval_result (malformed) exits 0" "0" "$exit_code"

    local file_content
    file_content=$(cat "$result_file")

    assert_contains "malformed results in agent_eval_available false" "\"agent_eval_available\": false" "$file_content"
    assert_contains "mechanical data still present" "\"mechanical\":" "$file_content"

    teardown
}

# ── Run all tests ────────────────────────────────────────────────────────

echo "Running lib/eval.sh test suite..."

test_mechanical_eval_normal
test_mechanical_eval_first_commit
test_mechanical_eval_merge_commit
test_mechanical_eval_errors
test_generate_eval_prompt
test_parse_eval_signal
test_write_eval_result_full
test_write_eval_result_no_agent
test_write_eval_result_malformed_agent

echo ""
echo "═══════════════════════════════════════════════"
echo "Results: $PASS passed, $FAIL failed"
echo "═══════════════════════════════════════════════"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
exit 0
