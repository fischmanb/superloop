"""Tests for auto_sdd.scripts.nightly_review — nightly learnings extraction.

Since this is orchestration code that calls git and the Claude CLI,
heavy mocking is acceptable here (unlike lib modules where we prefer real files).
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest

from auto_sdd.scripts.nightly_review import (
    EXTRACTION_PROMPT_TEMPLATE,
    NightlyReviewConfig,
    NightlyReviewer,
    _source_env_file,
    main,
)


# ── Helper fixtures ──────────────────────────────────────────────────────────


def _make_config(tmp_path: Path, **overrides: Any) -> NightlyReviewConfig:
    """Create a NightlyReviewConfig with sensible test defaults."""
    defaults: dict[str, Any] = {
        "project_dir": tmp_path,
        "hours_back": 24,
    }
    defaults.update(overrides)
    return NightlyReviewConfig(**defaults)


def _make_reviewer(tmp_path: Path, **overrides: Any) -> NightlyReviewer:
    """Create a NightlyReviewer with test config."""
    config = _make_config(tmp_path, **overrides)
    return NightlyReviewer(config)


def _git_result(
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    """Create a mock CompletedProcess."""
    return subprocess.CompletedProcess(
        args=["git"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


# ── _source_env_file tests ───────────────────────────────────────────────────


class TestSourceEnvFile:
    """Tests for _source_env_file."""

    def test_loads_simple_key_value(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env.local"
        env_file.write_text("NIGHTLY_TEST_VAR=hello\n")
        _source_env_file(env_file)
        assert os.environ.get("NIGHTLY_TEST_VAR") == "hello"
        del os.environ["NIGHTLY_TEST_VAR"]

    def test_strips_quotes(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env.local"
        env_file.write_text('NIGHTLY_TEST_Q="quoted value"\n')
        _source_env_file(env_file)
        assert os.environ.get("NIGHTLY_TEST_Q") == "quoted value"
        del os.environ["NIGHTLY_TEST_Q"]

    def test_skips_comments(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env.local"
        env_file.write_text("# comment\nNIGHTLY_TEST_C=val\n")
        _source_env_file(env_file)
        assert os.environ.get("NIGHTLY_TEST_C") == "val"
        del os.environ["NIGHTLY_TEST_C"]

    def test_does_not_override_existing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("NIGHTLY_TEST_E", "existing")
        env_file = tmp_path / ".env.local"
        env_file.write_text("NIGHTLY_TEST_E=new\n")
        _source_env_file(env_file)
        assert os.environ["NIGHTLY_TEST_E"] == "existing"

    def test_nonexistent_file_is_noop(self, tmp_path: Path) -> None:
        env_file = tmp_path / "nonexistent"
        _source_env_file(env_file)  # Should not raise

    def test_skips_lines_without_equals(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env.local"
        env_file.write_text("NOEQUALS\nNIGHTLY_TEST_F=ok\n")
        _source_env_file(env_file)
        assert os.environ.get("NIGHTLY_TEST_F") == "ok"
        del os.environ["NIGHTLY_TEST_F"]


# ── NightlyReviewConfig tests ────────────────────────────────────────────────


class TestNightlyReviewConfig:
    """Tests for NightlyReviewConfig."""

    def test_default_hours_back(self, tmp_path: Path) -> None:
        config = NightlyReviewConfig(project_dir=tmp_path)
        assert config.hours_back == 24

    def test_custom_hours_back(self, tmp_path: Path) -> None:
        config = NightlyReviewConfig(project_dir=tmp_path, hours_back=48)
        assert config.hours_back == 48


# ── _sync_branch tests ───────────────────────────────────────────────────────


class TestSyncBranch:
    """Tests for NightlyReviewer._sync_branch."""

    @patch.object(NightlyReviewer, "_run_git")
    def test_syncs_main_branch(
        self, mock_git: MagicMock, tmp_path: Path
    ) -> None:
        reviewer = _make_reviewer(tmp_path)

        def git_side(args: list[str]) -> subprocess.CompletedProcess[str]:
            if args == ["checkout", "main"]:
                return _git_result(0)
            if args == ["branch", "--show-current"]:
                return _git_result(0, stdout="main\n")
            if args[:2] == ["pull", "origin"]:
                return _git_result(0)
            return _git_result(0)

        mock_git.side_effect = git_side
        reviewer._sync_branch()
        # Should have called checkout main
        assert any(
            c[0][0] == ["checkout", "main"]
            for c in mock_git.call_args_list
        )

    @patch.object(NightlyReviewer, "_run_git")
    def test_falls_back_to_master(
        self, mock_git: MagicMock, tmp_path: Path
    ) -> None:
        reviewer = _make_reviewer(tmp_path)

        def git_side(args: list[str]) -> subprocess.CompletedProcess[str]:
            if args == ["checkout", "main"]:
                return _git_result(1)
            if args == ["checkout", "master"]:
                return _git_result(0)
            if args == ["branch", "--show-current"]:
                return _git_result(0, stdout="master\n")
            return _git_result(0)

        mock_git.side_effect = git_side
        reviewer._sync_branch()

    @patch.object(NightlyReviewer, "_run_git")
    def test_both_checkout_fail_raises(
        self, mock_git: MagicMock, tmp_path: Path
    ) -> None:
        reviewer = _make_reviewer(tmp_path)
        mock_git.return_value = _git_result(1)

        with pytest.raises(RuntimeError, match="Could not checkout"):
            reviewer._sync_branch()

    @patch.object(NightlyReviewer, "_run_git")
    def test_pull_failure_continues(
        self, mock_git: MagicMock, tmp_path: Path
    ) -> None:
        reviewer = _make_reviewer(tmp_path)

        def git_side(args: list[str]) -> subprocess.CompletedProcess[str]:
            if args == ["checkout", "main"]:
                return _git_result(0)
            if args == ["branch", "--show-current"]:
                return _git_result(0, stdout="main\n")
            if args[:2] == ["pull", "origin"]:
                return _git_result(1, stderr="pull failed")
            return _git_result(0)

        mock_git.side_effect = git_side
        reviewer._sync_branch()  # Should not raise


# ── _gather_context tests ────────────────────────────────────────────────────


class TestGatherContext:
    """Tests for NightlyReviewer._gather_context."""

    @patch.object(NightlyReviewer, "_get_recent_prs", return_value="")
    @patch.object(NightlyReviewer, "_run_git")
    def test_returns_commits_and_files(
        self,
        mock_git: MagicMock,
        mock_prs: MagicMock,
        tmp_path: Path,
    ) -> None:
        reviewer = _make_reviewer(tmp_path)

        def git_side(args: list[str]) -> subprocess.CompletedProcess[str]:
            if "--pretty=format:%h %s" in args:
                return _git_result(0, stdout="abc123 feat: login\ndef456 fix: bug\n")
            if "--name-only" in args:
                return _git_result(0, stdout="src/login.ts\nsrc/bug.ts\n")
            return _git_result(0)

        mock_git.side_effect = git_side
        commits, files, prs = reviewer._gather_context()

        assert "abc123" in commits
        assert "def456" in commits
        assert "src/login.ts" in files
        assert prs == ""

    @patch.object(NightlyReviewer, "_get_recent_prs", return_value="")
    @patch.object(NightlyReviewer, "_run_git")
    def test_no_commits(
        self,
        mock_git: MagicMock,
        mock_prs: MagicMock,
        tmp_path: Path,
    ) -> None:
        reviewer = _make_reviewer(tmp_path)
        mock_git.return_value = _git_result(0, stdout="")
        commits, files, prs = reviewer._gather_context()
        assert commits == ""

    @patch.object(NightlyReviewer, "_run_git")
    def test_with_gh_prs(
        self,
        mock_git: MagicMock,
        tmp_path: Path,
    ) -> None:
        reviewer = _make_reviewer(tmp_path)
        mock_git.return_value = _git_result(0, stdout="abc feat\n")

        with patch("shutil.which", return_value="/usr/bin/gh"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = subprocess.CompletedProcess(
                    args=["gh"],
                    returncode=0,
                    stdout="PR: Auth feature\nPR: Bug fix\n",
                )
                commits, files, prs = reviewer._gather_context()

        assert "Auth feature" in prs

    @patch.object(NightlyReviewer, "_run_git")
    def test_without_gh_cli(
        self,
        mock_git: MagicMock,
        tmp_path: Path,
    ) -> None:
        reviewer = _make_reviewer(tmp_path)
        mock_git.return_value = _git_result(0, stdout="abc feat\n")

        with patch("shutil.which", return_value=None):
            commits, files, prs = reviewer._gather_context()

        assert prs == ""

    @patch.object(NightlyReviewer, "_get_recent_prs", return_value="")
    @patch.object(NightlyReviewer, "_run_git")
    def test_deduplicates_files(
        self,
        mock_git: MagicMock,
        mock_prs: MagicMock,
        tmp_path: Path,
    ) -> None:
        reviewer = _make_reviewer(tmp_path)

        def git_side(args: list[str]) -> subprocess.CompletedProcess[str]:
            if "--name-only" in args:
                return _git_result(
                    0, stdout="src/a.ts\nsrc/a.ts\nsrc/b.ts\nsrc/a.ts\n"
                )
            return _git_result(0, stdout="abc feat\n")

        mock_git.side_effect = git_side
        _, files, _ = reviewer._gather_context()
        file_list = [f for f in files.splitlines() if f.strip()]
        assert len(file_list) == 2


# ── _run_extraction tests ────────────────────────────────────────────────────


class TestRunExtraction:
    """Tests for NightlyReviewer._run_extraction."""

    @patch("auto_sdd.scripts.nightly_review.run_claude")
    def test_calls_claude_with_prompt(
        self, mock_claude: MagicMock, tmp_path: Path
    ) -> None:
        reviewer = _make_reviewer(tmp_path)
        mock_result = MagicMock()
        mock_result.exit_code = 0
        mock_claude.return_value = mock_result

        reviewer._run_extraction("commit1", "file1.ts", "PR: test")

        mock_claude.assert_called_once()
        args = mock_claude.call_args[0][0]
        assert "-p" in args
        assert "--dangerously-skip-permissions" in args
        # Prompt should contain commits, files, prs
        prompt = args[-1]
        assert "commit1" in prompt
        assert "file1.ts" in prompt
        assert "PR: test" in prompt

    @patch("auto_sdd.scripts.nightly_review.run_claude")
    def test_agent_failure_does_not_raise(
        self, mock_claude: MagicMock, tmp_path: Path
    ) -> None:
        reviewer = _make_reviewer(tmp_path)
        mock_claude.side_effect = RuntimeError("agent failed")
        # Should not raise
        reviewer._run_extraction("commits", "files", "prs")

    @patch("auto_sdd.scripts.nightly_review.run_claude")
    def test_prompt_includes_hours_back(
        self, mock_claude: MagicMock, tmp_path: Path
    ) -> None:
        reviewer = _make_reviewer(tmp_path, hours_back=48)
        mock_result = MagicMock()
        mock_result.exit_code = 0
        mock_claude.return_value = mock_result

        reviewer._run_extraction("commits", "files", "prs")

        prompt = mock_claude.call_args[0][0][-1]
        assert "48" in prompt


# ── _verify_and_report tests ─────────────────────────────────────────────────


class TestVerifyAndReport:
    """Tests for NightlyReviewer._verify_and_report."""

    @patch.object(NightlyReviewer, "_run_git")
    def test_commit_found(
        self, mock_git: MagicMock, tmp_path: Path
    ) -> None:
        reviewer = _make_reviewer(tmp_path)
        mock_git.return_value = _git_result(
            0, stdout="compound: nightly review 2026-03-02"
        )
        reviewer._verify_and_report(5, 10)  # Should not raise

    @patch.object(NightlyReviewer, "_run_git")
    def test_no_commit(
        self, mock_git: MagicMock, tmp_path: Path
    ) -> None:
        reviewer = _make_reviewer(tmp_path)
        mock_git.return_value = _git_result(
            0, stdout="feat: something else"
        )
        reviewer._verify_and_report(5, 10)  # Should not raise


# ── Full run() flow tests ────────────────────────────────────────────────────


class TestFullRun:
    """Tests for NightlyReviewer.run with full mocking."""

    @patch("auto_sdd.scripts.nightly_review.run_claude")
    @patch("shutil.which", return_value="/usr/bin/claude")
    @patch.object(NightlyReviewer, "_run_git")
    def test_full_run_with_commits(
        self,
        mock_git: MagicMock,
        mock_which: MagicMock,
        mock_claude: MagicMock,
        tmp_path: Path,
    ) -> None:
        reviewer = _make_reviewer(tmp_path)

        call_count = [0]

        def git_side(args: list[str]) -> subprocess.CompletedProcess[str]:
            call_count[0] += 1
            if args == ["checkout", "main"]:
                return _git_result(0)
            if args == ["branch", "--show-current"]:
                return _git_result(0, stdout="main\n")
            if "--pretty=format:%h %s" in args:
                return _git_result(0, stdout="abc feat: login\n")
            if "--name-only" in args:
                return _git_result(0, stdout="src/login.ts\n")
            if args[:2] == ["log", "-1"]:
                return _git_result(0, stdout="compound: nightly review 2026-03-02")
            return _git_result(0)

        mock_git.side_effect = git_side
        mock_result = MagicMock()
        mock_result.exit_code = 0
        mock_claude.return_value = mock_result

        reviewer.run()
        mock_claude.assert_called_once()

    @patch.object(NightlyReviewer, "_run_git")
    def test_early_exit_no_commits(
        self, mock_git: MagicMock, tmp_path: Path
    ) -> None:
        reviewer = _make_reviewer(tmp_path)

        def git_side(args: list[str]) -> subprocess.CompletedProcess[str]:
            if args == ["checkout", "main"]:
                return _git_result(0)
            if args == ["branch", "--show-current"]:
                return _git_result(0, stdout="main\n")
            return _git_result(0, stdout="")

        mock_git.side_effect = git_side
        # Should return early without raising
        reviewer.run()

    @patch("auto_sdd.scripts.nightly_review.run_claude")
    @patch("shutil.which", return_value=None)
    @patch.object(NightlyReviewer, "_run_git")
    def test_missing_claude_cli_raises(
        self,
        mock_git: MagicMock,
        mock_which: MagicMock,
        mock_claude: MagicMock,
        tmp_path: Path,
    ) -> None:
        reviewer = _make_reviewer(tmp_path)

        def git_side(args: list[str]) -> subprocess.CompletedProcess[str]:
            if args == ["checkout", "main"]:
                return _git_result(0)
            if args == ["branch", "--show-current"]:
                return _git_result(0, stdout="main\n")
            if "--pretty=format:%h %s" in args:
                return _git_result(0, stdout="abc feat\n")
            if "--name-only" in args:
                return _git_result(0, stdout="file.ts\n")
            return _git_result(0)

        mock_git.side_effect = git_side

        with pytest.raises(RuntimeError, match="not found"):
            reviewer.run()


# ── _get_recent_prs tests ────────────────────────────────────────────────────


class TestGetRecentPrs:
    """Tests for NightlyReviewer._get_recent_prs."""

    @patch("subprocess.run")
    def test_returns_pr_titles(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        reviewer = _make_reviewer(tmp_path)
        mock_run.return_value = subprocess.CompletedProcess(
            args=["gh"],
            returncode=0,
            stdout="PR: Auth\nPR: Dashboard\n",
        )
        result = reviewer._get_recent_prs()
        assert "Auth" in result
        assert "Dashboard" in result

    @patch("subprocess.run", side_effect=subprocess.TimeoutExpired("gh", 30))
    def test_timeout_returns_empty(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        reviewer = _make_reviewer(tmp_path)
        result = reviewer._get_recent_prs()
        assert result == ""

    @patch("subprocess.run")
    def test_gh_failure_returns_empty(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        reviewer = _make_reviewer(tmp_path)
        mock_run.return_value = subprocess.CompletedProcess(
            args=["gh"],
            returncode=1,
            stdout="",
        )
        result = reviewer._get_recent_prs()
        assert result == ""

    @patch("subprocess.run", side_effect=OSError("no gh"))
    def test_os_error_returns_empty(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        reviewer = _make_reviewer(tmp_path)
        result = reviewer._get_recent_prs()
        assert result == ""


# ── Prompt template tests ────────────────────────────────────────────────────


class TestPromptTemplate:
    """Tests for the EXTRACTION_PROMPT_TEMPLATE."""

    def test_template_has_all_placeholders(self) -> None:
        assert "{hours_back}" in EXTRACTION_PROMPT_TEMPLATE
        assert "{recent_commits}" in EXTRACTION_PROMPT_TEMPLATE
        assert "{changed_files}" in EXTRACTION_PROMPT_TEMPLATE
        assert "{recent_prs}" in EXTRACTION_PROMPT_TEMPLATE
        assert "{today_date}" in EXTRACTION_PROMPT_TEMPLATE

    def test_template_format_succeeds(self) -> None:
        result = EXTRACTION_PROMPT_TEMPLATE.format(
            hours_back=24,
            recent_commits="abc feat",
            changed_files="file.ts",
            recent_prs="PR: test",
            today_date="2026-03-02",
            main_branch="main",
        )
        assert "abc feat" in result
        assert "24" in result

    def test_template_preserves_instructions(self) -> None:
        assert "CATEGORIZE" in EXTRACTION_PROMPT_TEMPLATE
        assert "COMMIT all changes" in EXTRACTION_PROMPT_TEMPLATE
        assert "compound: nightly review" in EXTRACTION_PROMPT_TEMPLATE

    def test_template_uses_main_branch_placeholder(self) -> None:
        assert "{main_branch}" in EXTRACTION_PROMPT_TEMPLATE


# ── Configurable main_branch tests ────────────────────────────────────────


class TestConfigurableMainBranch:
    """Tests for configurable main_branch parameter (Finding #19)."""

    def test_default_main_branch(self, tmp_path: Path) -> None:
        config = NightlyReviewConfig(project_dir=tmp_path)
        assert config.main_branch == "main"

    def test_custom_main_branch(self, tmp_path: Path) -> None:
        config = NightlyReviewConfig(
            project_dir=tmp_path, main_branch="develop"
        )
        assert config.main_branch == "develop"

    @patch("auto_sdd.scripts.nightly_review.run_claude")
    def test_prompt_uses_configured_branch(
        self, mock_claude: MagicMock, tmp_path: Path
    ) -> None:
        reviewer = _make_reviewer(tmp_path, main_branch="develop")
        mock_result = MagicMock()
        mock_result.exit_code = 0
        mock_claude.return_value = mock_result

        reviewer._run_extraction("commits", "files", "prs")

        prompt = mock_claude.call_args[0][0][-1]
        assert "git push origin develop" in prompt
        assert "git push origin main" not in prompt
