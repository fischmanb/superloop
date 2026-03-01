"""Tests for auto_sdd.lib.eval_lib — equivalent coverage to tests/test-eval.sh (53 assertions)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from auto_sdd.lib.eval_lib import (
    EvalError,
    MechanicalEvalResult,
    generate_eval_prompt,
    parse_eval_signal,
    run_mechanical_eval,
    write_eval_result,
    _sanitize_feature_name,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _git(repo: Path, *args: str) -> str:
    """Run a git command in *repo* and return stdout."""
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    return result.stdout.strip()


def _init_repo(repo: Path) -> None:
    """Initialise a fresh git repo with config."""
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@test.com")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "commit.gpgsign", "false")


def create_fixture_repo(base: Path) -> Path:
    """Create a fixture git repo simulating a React/TS project.

    Mirrors the bash create_fixture_repo helper exactly: initial commit with
    types + component + CLAUDE.md + learnings, then a feature commit adding
    a Header component and test file.
    """
    repo = base / "repo"
    repo.mkdir()
    _init_repo(repo)

    # -- Initial commit --
    (repo / "src" / "components").mkdir(parents=True)
    (repo / "src" / "types").mkdir(parents=True)

    (repo / "src" / "types" / "index.ts").write_text(
        "export type User = {\n"
        "  id: string;\n"
        "  name: string;\n"
        "};\n"
        "\n"
        "export interface ApiResponse {\n"
        "  data: unknown;\n"
        "  status: number;\n"
        "}\n"
    )

    (repo / "src" / "components" / "Button.tsx").write_text(
        "import React from 'react';\n"
        "\n"
        "export interface ButtonProps {\n"
        "  label: string;\n"
        "  onClick: () => void;\n"
        "}\n"
        "\n"
        "export default function Button({ label, onClick }: ButtonProps) {\n"
        "  return <button onClick={onClick}>{label}</button>;\n"
        "}\n"
    )

    (repo / "CLAUDE.md").write_text(
        "# Test Project\n"
        "This project uses spec-driven development.\n"
    )

    (repo / ".specs" / "learnings").mkdir(parents=True)
    (repo / ".specs" / "learnings" / "index.md").write_text(
        "# Learnings Index\n"
        "- Always validate inputs at boundaries\n"
    )

    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "feat: initial project setup")

    # -- Feature commit --
    (repo / "src" / "components" / "Header.tsx").write_text(
        "import React from 'react';\n"
        "import Button from './Button';\n"
        "\n"
        "export type HeaderVariant = 'primary' | 'secondary';\n"
        "\n"
        "export default function Header() {\n"
        "  return (\n"
        "    <header>\n"
        "      <h1>My App</h1>\n"
        "      <Button label=\"Menu\" onClick={() => {}} />\n"
        "    </header>\n"
        "  );\n"
        "}\n"
    )

    (repo / "tests").mkdir(exist_ok=True)
    (repo / "tests" / "Header.test.tsx").write_text(
        "import { render } from '@testing-library/react';\n"
        "import Header from '../src/components/Header';\n"
        "\n"
        "test('renders header', () => {\n"
        "  const { getByText } = render(<Header />);\n"
        "  expect(getByText('My App')).toBeInTheDocument();\n"
        "});\n"
    )

    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "feat: add Header component with tests")

    return repo


# ── Test: mechanical eval — normal feature commit ────────────────────────────


class TestRunMechanicalEvalNormal:
    """Equivalent to test_mechanical_eval_normal in bash (14 assertions)."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path) -> None:
        self.repo = create_fixture_repo(tmp_path)
        self.commit_hash = _git(self.repo, "rev-parse", "HEAD")
        self.result = run_mechanical_eval(self.repo, self.commit_hash)

    def test_returns_result(self) -> None:
        assert isinstance(self.result, MechanicalEvalResult)

    def test_passed(self) -> None:
        assert self.result.passed is True

    def test_has_commit_field(self) -> None:
        assert "commit" in self.result.diff_stats

    def test_has_feature_name_field(self) -> None:
        assert "feature_name" in self.result.diff_stats

    def test_has_files_changed_field(self) -> None:
        assert "files_changed" in self.result.diff_stats

    def test_has_lines_added_field(self) -> None:
        assert "lines_added" in self.result.diff_stats

    def test_has_lines_removed_field(self) -> None:
        assert "lines_removed" in self.result.diff_stats

    def test_has_new_type_exports_field(self) -> None:
        assert "new_type_exports" in self.result.diff_stats

    def test_has_type_redeclarations_field(self) -> None:
        assert "type_redeclarations" in self.result.diff_stats

    def test_has_import_count_field(self) -> None:
        assert "import_count" in self.result.diff_stats

    def test_has_test_files_touched_field(self) -> None:
        assert "test_files_touched" in self.result.diff_stats

    def test_commit_hash_matches(self) -> None:
        assert self.result.diff_stats["commit"] == self.commit_hash

    def test_feature_name_extracted(self) -> None:
        assert self.result.diff_stats["feature_name"] == "add Header component with tests"

    def test_files_changed_is_2(self) -> None:
        assert self.result.diff_stats["files_changed"] == 2

    def test_test_files_touched_true(self) -> None:
        assert self.result.diff_stats["test_files_touched"] is True


# ── Test: mechanical eval — first commit ─────────────────────────────────────


class TestRunMechanicalEvalFirstCommit:
    """Equivalent to test_mechanical_eval_first_commit in bash (4 assertions)."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path) -> None:
        self.repo = tmp_path / "first_repo"
        self.repo.mkdir()
        _init_repo(self.repo)
        (self.repo / "README.md").write_text("# Hello\nInitial file.\n")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-q", "-m", "feat: initial commit")
        self.commit_hash = _git(self.repo, "rev-parse", "HEAD")
        self.result = run_mechanical_eval(self.repo, self.commit_hash)

    def test_exits_success(self) -> None:
        assert self.result.passed is True

    def test_files_changed_is_1(self) -> None:
        assert self.result.diff_stats["files_changed"] == 1

    def test_has_commit_field(self) -> None:
        assert "commit" in self.result.diff_stats

    def test_not_skipped(self) -> None:
        assert "skipped" not in self.result.diff_stats


# ── Test: mechanical eval — merge commit ─────────────────────────────────────


class TestRunMechanicalEvalMergeCommit:
    """Equivalent to test_mechanical_eval_merge_commit in bash (3 assertions)."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path) -> None:
        self.repo = tmp_path / "merge_repo"
        self.repo.mkdir()
        _init_repo(self.repo)

        (self.repo / "file.txt").write_text("base\n")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-q", "-m", "initial")

        _git(self.repo, "checkout", "-q", "-b", "feature")
        (self.repo / "feature.txt").write_text("feature\n")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-q", "-m", "add feature")

        # Checkout main branch (could be main or master)
        try:
            _git(self.repo, "checkout", "-q", "master")
        except subprocess.CalledProcessError:
            _git(self.repo, "checkout", "-q", "main")

        (self.repo / "main.txt").write_text("main change\n")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-q", "-m", "main change")

        _git(self.repo, "merge", "-q", "--no-ff", "feature", "-m", "Merge feature")

        self.merge_hash = _git(self.repo, "rev-parse", "HEAD")
        self.result = run_mechanical_eval(self.repo, self.merge_hash)

    def test_exits_success(self) -> None:
        assert self.result.passed is True

    def test_skipped_true(self) -> None:
        assert self.result.diff_stats.get("skipped") is True

    def test_reason_merge_commit(self) -> None:
        assert self.result.diff_stats.get("reason") == "merge commit"


# ── Test: mechanical eval — error cases ──────────────────────────────────────


class TestRunMechanicalEvalErrors:
    """Equivalent to test_mechanical_eval_errors in bash (4 assertions)."""

    def test_missing_commit_hash_raises(self, tmp_path: Path) -> None:
        with pytest.raises(EvalError, match="commit_hash is required"):
            run_mechanical_eval(tmp_path, "")

    def test_nonexistent_dir_raises(self, tmp_path: Path) -> None:
        bad_dir = tmp_path / "nonexistent"
        with pytest.raises(EvalError, match="directory does not exist"):
            run_mechanical_eval(bad_dir, "abc123")

    def test_invalid_commit_raises(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        (repo / "f.txt").write_text("x\n")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "init")
        with pytest.raises(EvalError, match="commit not found"):
            run_mechanical_eval(repo, "deadbeefdeadbeef")

    def test_error_message_is_descriptive(self, tmp_path: Path) -> None:
        with pytest.raises(EvalError) as exc_info:
            run_mechanical_eval(tmp_path, "")
        assert "commit_hash" in str(exc_info.value)


# ── Test: generate_eval_prompt ───────────────────────────────────────────────


class TestGenerateEvalPrompt:
    """Equivalent to test_generate_eval_prompt in bash (9 assertions)."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path) -> None:
        self.repo = create_fixture_repo(tmp_path)
        self.commit_hash = _git(self.repo, "rev-parse", "HEAD")
        self.prompt = generate_eval_prompt(self.repo, self.commit_hash)

    def test_returns_string(self) -> None:
        assert isinstance(self.prompt, str)

    def test_contains_commit_hash(self) -> None:
        assert self.commit_hash in self.prompt

    def test_contains_no_modify(self) -> None:
        assert "do NOT modify any files" in self.prompt

    def test_contains_no_commit(self) -> None:
        assert "do NOT commit" in self.prompt

    def test_contains_no_input(self) -> None:
        assert "do NOT ask for user input" in self.prompt

    def test_contains_claude_md_content(self) -> None:
        assert "spec-driven development" in self.prompt

    def test_contains_learnings(self) -> None:
        assert "validate inputs at boundaries" in self.prompt

    def test_contains_eval_complete_signal(self) -> None:
        assert "EVAL_COMPLETE" in self.prompt

    def test_contains_eval_framework_compliance_signal(self) -> None:
        assert "EVAL_FRAMEWORK_COMPLIANCE" in self.prompt


# ── Test: generate_eval_prompt — error cases ──────────────────────────────────


class TestGenerateEvalPromptErrors:
    """Additional error cases for generate_eval_prompt."""

    def test_empty_commit_hash_raises(self, tmp_path: Path) -> None:
        with pytest.raises(EvalError):
            generate_eval_prompt(tmp_path, "")

    def test_nonexistent_dir_raises(self, tmp_path: Path) -> None:
        with pytest.raises(EvalError):
            generate_eval_prompt(tmp_path / "nope", "abc123")


# ── Test: parse_eval_signal ──────────────────────────────────────────────────


SAMPLE_AGENT_OUTPUT = """\
Some preamble text here.
EVAL_COMPLETE: true
EVAL_FRAMEWORK_COMPLIANCE: pass
EVAL_SCOPE_ASSESSMENT: focused
EVAL_INTEGRATION_QUALITY: clean
EVAL_REPEATED_MISTAKES: none
EVAL_NOTES: Clean commit following project conventions"""


class TestParseEvalSignal:
    """Equivalent to test_parse_eval_signal in bash (5 assertions)."""

    def test_parses_eval_complete(self) -> None:
        assert parse_eval_signal("EVAL_COMPLETE", SAMPLE_AGENT_OUTPUT) == "true"

    def test_parses_framework_compliance(self) -> None:
        assert parse_eval_signal("EVAL_FRAMEWORK_COMPLIANCE", SAMPLE_AGENT_OUTPUT) == "pass"

    def test_parses_scope_assessment(self) -> None:
        assert parse_eval_signal("EVAL_SCOPE_ASSESSMENT", SAMPLE_AGENT_OUTPUT) == "focused"

    def test_parses_eval_notes(self) -> None:
        assert parse_eval_signal("EVAL_NOTES", SAMPLE_AGENT_OUTPUT) == "Clean commit following project conventions"

    def test_missing_signal_returns_empty(self) -> None:
        assert parse_eval_signal("EVAL_NONEXISTENT", SAMPLE_AGENT_OUTPUT) == ""


class TestParseEvalSignalEdgeCases:
    """Additional edge cases for parse_eval_signal."""

    def test_empty_output(self) -> None:
        assert parse_eval_signal("EVAL_COMPLETE", "") == ""

    def test_last_value_wins(self) -> None:
        output = "EVAL_COMPLETE: false\nEVAL_COMPLETE: true\n"
        assert parse_eval_signal("EVAL_COMPLETE", output) == "true"

    def test_partial_match_not_returned(self) -> None:
        output = "NOT_EVAL_COMPLETE: true\n"
        assert parse_eval_signal("EVAL_COMPLETE", output) == ""

    def test_value_with_spaces(self) -> None:
        output = "EVAL_NOTES:   spaces around   \n"
        assert parse_eval_signal("EVAL_NOTES", output) == "spaces around"


# ── Test: write_eval_result — full (agent + mechanical) ──────────────────────


class TestWriteEvalResultFull:
    """Equivalent to test_write_eval_result_full in bash (5 assertions)."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path) -> None:
        self.out_dir = tmp_path / "eval_output"
        mech = MechanicalEvalResult(
            diff_stats={
                "commit": "abc123",
                "files_changed": 3,
                "lines_added": 50,
                "lines_removed": 10,
            },
            type_exports_changed=[],
            redeclarations=[],
            test_files_touched=[],
            passed=True,
        )
        agent_output = (
            "EVAL_COMPLETE: true\n"
            "EVAL_FRAMEWORK_COMPLIANCE: pass\n"
            "EVAL_SCOPE_ASSESSMENT: focused\n"
            "EVAL_INTEGRATION_QUALITY: clean\n"
            "EVAL_REPEATED_MISTAKES: none\n"
            "EVAL_NOTES: Solid implementation\n"
        )
        self.result_file = write_eval_result(
            self.out_dir, "header-component", mech, agent_output
        )
        self.content = json.loads(self.result_file.read_text())

    def test_file_created(self) -> None:
        assert self.result_file.is_file()

    def test_agent_eval_available_true(self) -> None:
        assert self.content["agent_eval_available"] is True

    def test_framework_compliance_pass(self) -> None:
        assert self.content["agent_eval"]["framework_compliance"] == "pass"

    def test_has_mechanical_data(self) -> None:
        assert "mechanical" in self.content

    def test_has_eval_timestamp(self) -> None:
        assert "eval_timestamp" in self.content


# ── Test: write_eval_result — no agent output ────────────────────────────────


class TestWriteEvalResultNoAgent:
    """Equivalent to test_write_eval_result_no_agent in bash (3 assertions)."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path) -> None:
        self.out_dir = tmp_path / "eval_output2"
        mech = MechanicalEvalResult(
            diff_stats={"commit": "def456", "files_changed": 1},
            type_exports_changed=[],
            redeclarations=[],
            test_files_touched=[],
            passed=True,
        )
        self.result_file = write_eval_result(
            self.out_dir, "simple-fix", mech, ""
        )
        self.content = json.loads(self.result_file.read_text())

    def test_agent_eval_available_false(self) -> None:
        assert self.content["agent_eval_available"] is False

    def test_has_mechanical_data(self) -> None:
        assert "mechanical" in self.content

    def test_no_agent_eval_section(self) -> None:
        assert "agent_eval" not in self.content


# ── Test: write_eval_result — malformed agent output ─────────────────────────


class TestWriteEvalResultMalformed:
    """Equivalent to test_write_eval_result_malformed_agent in bash (2 assertions)."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path) -> None:
        self.out_dir = tmp_path / "eval_output3"
        mech = MechanicalEvalResult(
            diff_stats={"commit": "ghi789", "files_changed": 2},
            type_exports_changed=[],
            redeclarations=[],
            test_files_touched=[],
            passed=True,
        )
        self.result_file = write_eval_result(
            self.out_dir, "broken-eval", mech, "Some random text without any signals"
        )
        self.content = json.loads(self.result_file.read_text())

    def test_agent_eval_available_false(self) -> None:
        assert self.content["agent_eval_available"] is False

    def test_mechanical_data_present(self) -> None:
        assert "mechanical" in self.content


# ── Test: _sanitize_feature_name ─────────────────────────────────────────────


class TestSanitizeFeatureName:
    """Test the filename sanitizer matches bash tr/sed behaviour."""

    def test_lowercase(self) -> None:
        assert _sanitize_feature_name("MyFeature") == "myfeature"

    def test_spaces_become_dashes(self) -> None:
        assert _sanitize_feature_name("my feature name") == "my-feature-name"

    def test_special_chars_replaced(self) -> None:
        assert _sanitize_feature_name("feat: add (thing)") == "feat-add-thing"

    def test_dots_preserved(self) -> None:
        assert _sanitize_feature_name("v1.2.3") == "v1.2.3"

    def test_collapse_multiple_dashes(self) -> None:
        assert _sanitize_feature_name("a---b") == "a-b"

    def test_strip_leading_trailing_dashes(self) -> None:
        assert _sanitize_feature_name("-foo-") == "foo"


# ── Test: write_eval_result — filename sanitization ──────────────────────────


class TestWriteEvalResultFilename:
    """Verify the output filename uses sanitized feature name."""

    def test_filename_is_sanitized(self, tmp_path: Path) -> None:
        mech = MechanicalEvalResult(
            diff_stats={"commit": "xyz"},
            type_exports_changed=[],
            redeclarations=[],
            test_files_touched=[],
            passed=True,
        )
        result = write_eval_result(
            tmp_path / "out", "My Feature: Cool Stuff!", mech, ""
        )
        assert result.name == "eval-my-feature-cool-stuff.json"

    def test_output_is_valid_json(self, tmp_path: Path) -> None:
        mech = MechanicalEvalResult(
            diff_stats={"commit": "xyz"},
            type_exports_changed=[],
            redeclarations=[],
            test_files_touched=[],
            passed=True,
        )
        result = write_eval_result(tmp_path / "out2", "test", mech, "")
        data = json.loads(result.read_text())
        assert isinstance(data, dict)


# ── Test: write_eval_result — error cases ────────────────────────────────────


class TestWriteEvalResultErrors:
    """Error handling for write_eval_result."""

    def test_empty_feature_name_raises(self, tmp_path: Path) -> None:
        mech = MechanicalEvalResult(
            diff_stats={},
            type_exports_changed=[],
            redeclarations=[],
            test_files_touched=[],
            passed=True,
        )
        with pytest.raises(EvalError, match="feature_name"):
            write_eval_result(tmp_path, "", mech, "")


# ── Test: mechanical eval — type analysis ────────────────────────────────────


class TestMechanicalEvalTypeAnalysis:
    """Test type export detection in commits."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path) -> None:
        self.repo = create_fixture_repo(tmp_path)
        self.commit_hash = _git(self.repo, "rev-parse", "HEAD")
        self.result = run_mechanical_eval(self.repo, self.commit_hash)

    def test_new_type_exports_counted(self) -> None:
        # Header.tsx adds "export type HeaderVariant"
        assert self.result.diff_stats["new_type_exports"] >= 1

    def test_type_exports_changed_populated(self) -> None:
        assert "HeaderVariant" in self.result.type_exports_changed


# ── Test: generate_eval_prompt — no CLAUDE.md or learnings ───────────────────


class TestGenerateEvalPromptNoOptionalFiles:
    """Prompt generation when optional files don't exist."""

    def test_works_without_claude_md(self, tmp_path: Path) -> None:
        repo = tmp_path / "bare_repo"
        repo.mkdir()
        _init_repo(repo)
        (repo / "file.txt").write_text("hello\n")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "init")
        commit = _git(repo, "rev-parse", "HEAD")
        prompt = generate_eval_prompt(repo, commit)
        assert "EVAL_COMPLETE" in prompt
        assert commit in prompt
