"""Tests for auto_sdd.scripts.eval_sidecar — comprehensive coverage."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from auto_sdd.lib.eval_lib import (
    EvalError,
    MechanicalEvalResult,
)
from auto_sdd.scripts.eval_sidecar import (
    CampaignState,
    EvalSidecarConfig,
    _build_agent_cmd,
    _get_commit_message,
    _get_head,
    _get_new_commits,
    _is_credit_exhaustion,
    _evaluate_commit,
    generate_campaign_summary,
    run_polling_loop,
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


def _make_commit(repo: Path, filename: str, content: str, msg: str) -> str:
    """Create a file and commit it, returning the commit hash."""
    (repo / filename).write_text(content)
    _git(repo, "add", filename)
    _git(repo, "commit", "-m", msg)
    return _git(repo, "rev-parse", "HEAD")


def _create_test_repo(tmp_path: Path) -> Path:
    """Create a git repo with one initial commit."""
    repo = tmp_path / "project"
    repo.mkdir()
    _init_repo(repo)
    _make_commit(repo, "README.md", "# Test\n", "initial commit")
    return repo


def _make_eval_json(
    eval_dir: Path,
    name: str,
    *,
    type_redeclarations: int = 0,
    feature_name: str = "test-feature",
    agent_avail: bool = False,
    fw: str = "pass",
    scope: str = "focused",
    iq: str = "clean",
) -> Path:
    """Write a mock eval JSON file and return its path."""
    data: dict[str, Any] = {
        "eval_timestamp": "2026-01-01T00:00:00Z",
        "mechanical": {
            "feature_name": feature_name,
            "type_redeclarations": type_redeclarations,
            "files_changed": 2,
        },
        "agent_eval_available": agent_avail,
    }
    if agent_avail:
        data["agent_eval"] = {
            "framework_compliance": fw,
            "scope_assessment": scope,
            "integration_quality": iq,
        }
    path = eval_dir / f"eval-{name}.json"
    path.write_text(json.dumps(data, indent=2))
    return path


# ── Config validation ─────────────────────────────────────────────────────────


class TestEvalSidecarConfig:
    """Tests for EvalSidecarConfig validation."""

    def test_config_missing_project_dir(self, tmp_path: Path) -> None:
        """Config raises EvalError when project_dir doesn't exist."""
        nonexistent = tmp_path / "nonexistent"
        with pytest.raises(EvalError, match="does not exist"):
            EvalSidecarConfig(project_dir=nonexistent)

    def test_config_valid_project_dir(self, tmp_path: Path) -> None:
        """Config accepts a valid project directory."""
        config = EvalSidecarConfig(project_dir=tmp_path)
        assert config.project_dir == tmp_path
        assert config.eval_interval == 30
        assert config.eval_agent is True
        assert config.eval_model == ""
        assert config.eval_output_dir == tmp_path / "logs" / "evals"

    def test_config_custom_output_dir(self, tmp_path: Path) -> None:
        """Config uses custom eval_output_dir when provided."""
        custom = tmp_path / "custom-evals"
        custom.mkdir()
        config = EvalSidecarConfig(
            project_dir=tmp_path, eval_output_dir=custom
        )
        assert config.eval_output_dir == custom

    def test_config_custom_interval(self, tmp_path: Path) -> None:
        """Config accepts custom eval_interval."""
        config = EvalSidecarConfig(project_dir=tmp_path, eval_interval=60)
        assert config.eval_interval == 60

    def test_config_agent_disabled(self, tmp_path: Path) -> None:
        """Config accepts eval_agent=False."""
        config = EvalSidecarConfig(project_dir=tmp_path, eval_agent=False)
        assert config.eval_agent is False


# ── Campaign summary ──────────────────────────────────────────────────────────


class TestCampaignSummary:
    """Tests for generate_campaign_summary."""

    def test_empty_results(self, tmp_path: Path) -> None:
        """Campaign summary returns None with no eval files."""
        eval_dir = tmp_path / "evals"
        eval_dir.mkdir()
        result = generate_campaign_summary(eval_dir)
        assert result is None

    def test_nonexistent_dir(self, tmp_path: Path) -> None:
        """Campaign summary returns None for nonexistent directory."""
        result = generate_campaign_summary(tmp_path / "no-such-dir")
        assert result is None

    def test_single_mechanical_only(self, tmp_path: Path) -> None:
        """Campaign summary with one mechanical-only eval (no issues)."""
        eval_dir = tmp_path / "evals"
        eval_dir.mkdir()
        _make_eval_json(eval_dir, "feat-one", feature_name="feat-one")

        result = generate_campaign_summary(eval_dir)
        assert result is not None
        assert result.name.startswith("eval-campaign-")

        data = json.loads(result.read_text())
        assert data["total_features_evaluated"] == 1
        assert data["type_redeclarations_total"] == 0
        assert data["features_with_issues_count"] == 0
        assert data["features_with_issues"] == []

    def test_mixed_results_with_issues(self, tmp_path: Path) -> None:
        """Campaign summary aggregates signals from multiple eval files."""
        eval_dir = tmp_path / "evals"
        eval_dir.mkdir()

        # Clean feature
        _make_eval_json(
            eval_dir, "clean",
            feature_name="clean-feat",
            agent_avail=True,
            fw="pass", scope="focused", iq="clean",
        )
        # Feature with type redeclaration
        _make_eval_json(
            eval_dir, "redecl",
            feature_name="redecl-feat",
            type_redeclarations=2,
        )
        # Feature with framework warning
        _make_eval_json(
            eval_dir, "fw-warn",
            feature_name="fw-warn-feat",
            agent_avail=True,
            fw="warn", scope="moderate", iq="minor_issues",
        )
        # Feature with sprawling scope and major issues
        _make_eval_json(
            eval_dir, "sprawl",
            feature_name="sprawl-feat",
            agent_avail=True,
            fw="fail", scope="sprawling", iq="major_issues",
        )

        result = generate_campaign_summary(eval_dir)
        assert result is not None

        data = json.loads(result.read_text())
        assert data["total_features_evaluated"] == 4
        assert data["type_redeclarations_total"] == 2

        assert data["framework_compliance"]["pass"] == 1
        assert data["framework_compliance"]["warn"] == 1
        assert data["framework_compliance"]["fail"] == 1

        assert data["scope_assessment"]["focused"] == 1
        assert data["scope_assessment"]["moderate"] == 1
        assert data["scope_assessment"]["sprawling"] == 1

        assert data["integration_quality"]["clean"] == 1
        assert data["integration_quality"]["minor_issues"] == 1
        assert data["integration_quality"]["major_issues"] == 1

        assert data["features_with_issues_count"] == 3
        assert "redecl-feat" in data["features_with_issues"]
        assert "fw-warn-feat" in data["features_with_issues"]
        assert "sprawl-feat" in data["features_with_issues"]
        assert "clean-feat" not in data["features_with_issues"]

    def test_campaign_ignores_campaign_files(self, tmp_path: Path) -> None:
        """Campaign summary ignores existing campaign files."""
        eval_dir = tmp_path / "evals"
        eval_dir.mkdir()
        _make_eval_json(eval_dir, "feat-x", feature_name="feat-x")
        # Pre-existing campaign file should be ignored
        (eval_dir / "eval-campaign-20260101-000000.json").write_text("{}")

        result = generate_campaign_summary(eval_dir)
        assert result is not None
        data = json.loads(result.read_text())
        assert data["total_features_evaluated"] == 1


# ── Commit discovery ──────────────────────────────────────────────────────────


class TestCommitDiscovery:
    """Tests for git helpers used in commit discovery."""

    def test_get_head_valid_repo(self, tmp_path: Path) -> None:
        """_get_head returns the HEAD hash for a valid repo."""
        repo = _create_test_repo(tmp_path)
        head = _get_head(repo)
        assert len(head) == 40
        assert head == _git(repo, "rev-parse", "HEAD")

    def test_get_head_nonexistent_dir(self, tmp_path: Path) -> None:
        """_get_head returns empty string for nonexistent directory."""
        result = _get_head(tmp_path / "no-repo")
        assert result == ""

    def test_no_new_commits(self, tmp_path: Path) -> None:
        """_get_new_commits returns empty list when no new commits exist."""
        repo = _create_test_repo(tmp_path)
        head = _git(repo, "rev-parse", "HEAD")
        commits = _get_new_commits(repo, head, head)
        assert commits == []

    def test_single_new_commit(self, tmp_path: Path) -> None:
        """_get_new_commits returns one commit hash."""
        repo = _create_test_repo(tmp_path)
        base = _git(repo, "rev-parse", "HEAD")
        new_hash = _make_commit(repo, "file.txt", "content", "feat: new file")
        commits = _get_new_commits(repo, base, new_hash)
        assert len(commits) == 1
        assert commits[0] == new_hash

    def test_multiple_new_commits(self, tmp_path: Path) -> None:
        """_get_new_commits returns multiple commits oldest first."""
        repo = _create_test_repo(tmp_path)
        base = _git(repo, "rev-parse", "HEAD")
        h1 = _make_commit(repo, "a.txt", "a", "feat: add a")
        h2 = _make_commit(repo, "b.txt", "b", "feat: add b")
        h3 = _make_commit(repo, "c.txt", "c", "feat: add c")
        commits = _get_new_commits(repo, base, h3)
        assert commits == [h1, h2, h3]

    def test_merge_commit_skipped(self, tmp_path: Path) -> None:
        """_get_new_commits excludes merge commits (--no-merges)."""
        repo = _create_test_repo(tmp_path)
        base = _git(repo, "rev-parse", "HEAD")

        # Create a branch, make a commit, merge
        _git(repo, "checkout", "-b", "feature")
        h_feat = _make_commit(
            repo, "feature.txt", "feat", "feat: on branch"
        )
        _git(repo, "checkout", "master")
        _make_commit(repo, "main.txt", "main", "feat: on main")
        _git(repo, "merge", "feature", "--no-ff", "-m", "Merge feature")
        merge_head = _git(repo, "rev-parse", "HEAD")

        commits = _get_new_commits(repo, base, merge_head)
        # Should have the feature commit and main commit but NOT the merge
        hashes = set(commits)
        assert h_feat in hashes
        # The merge commit itself should be excluded
        assert merge_head not in hashes

    def test_get_commit_message(self, tmp_path: Path) -> None:
        """_get_commit_message returns the first line of the commit message."""
        repo = _create_test_repo(tmp_path)
        _make_commit(repo, "x.txt", "x", "feat: my feature")
        head = _git(repo, "rev-parse", "HEAD")
        msg = _get_commit_message(repo, head)
        assert msg == "feat: my feature"

    def test_get_commit_message_bad_hash(self, tmp_path: Path) -> None:
        """_get_commit_message returns '<unknown>' for invalid hash."""
        repo = _create_test_repo(tmp_path)
        msg = _get_commit_message(repo, "0" * 40)
        assert msg == "<unknown>"


# ── Drain sentinel ────────────────────────────────────────────────────────────


class TestDrainSentinel:
    """Tests for drain sentinel detection in the polling loop."""

    @patch("auto_sdd.scripts.eval_sidecar._get_head")
    def test_drain_sentinel_triggers_drain(self, mock_head: MagicMock, tmp_path: Path) -> None:
        """Drain sentinel file causes loop to enter drain mode and exit."""
        repo = _create_test_repo(tmp_path)
        eval_dir = tmp_path / "evals"
        eval_dir.mkdir()
        head = _git(repo, "rev-parse", "HEAD")

        config = EvalSidecarConfig(
            project_dir=repo,
            eval_interval=0,
            eval_agent=False,
            eval_output_dir=eval_dir,
        )

        # HEAD never changes — drain sentinel triggers exit
        mock_head.return_value = head

        # Write drain sentinel before loop starts
        # (loop removes stale sentinel on startup, so write in a callback)
        call_count = 0

        original_return = head

        def side_effect(project_dir: Path) -> str:
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                # Write sentinel after first poll
                (repo / ".sdd-eval-drain").write_text("drain")
            return original_return

        mock_head.side_effect = side_effect

        state = run_polling_loop(config)
        assert state.draining is True

    @patch("auto_sdd.scripts.eval_sidecar._get_head")
    def test_drain_processes_remaining_commits(
        self, mock_head: MagicMock, tmp_path: Path
    ) -> None:
        """Drain processes remaining commits before exiting."""
        repo = _create_test_repo(tmp_path)
        eval_dir = tmp_path / "evals"
        eval_dir.mkdir()
        base = _git(repo, "rev-parse", "HEAD")
        new_hash = _make_commit(repo, "f.txt", "f", "feat: new")

        config = EvalSidecarConfig(
            project_dir=repo,
            eval_interval=0,
            eval_agent=False,
            eval_output_dir=eval_dir,
        )

        call_count = 0

        def side_effect(project_dir: Path) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call: return base (initialization)
                return base
            # Write sentinel and report new HEAD
            (repo / ".sdd-eval-drain").write_text("drain")
            return new_hash

        mock_head.side_effect = side_effect

        state = run_polling_loop(config)
        assert state.draining is True
        assert state.eval_count >= 1


# ── Credit exhaustion ─────────────────────────────────────────────────────────


class TestCreditExhaustion:
    """Tests for credit exhaustion detection."""

    def test_credit_keyword_detection(self) -> None:
        """_is_credit_exhaustion detects credit-related keywords."""
        assert _is_credit_exhaustion("Error: insufficient_quota reached")
        assert _is_credit_exhaustion("402 Payment Required")
        assert _is_credit_exhaustion("429 Too Many requests")
        assert _is_credit_exhaustion("billing issue detected")
        assert _is_credit_exhaustion("credit limit exceeded")

    def test_no_credit_keywords(self) -> None:
        """_is_credit_exhaustion returns False for normal errors."""
        assert not _is_credit_exhaustion("Connection timeout")
        assert not _is_credit_exhaustion("Internal server error")
        assert not _is_credit_exhaustion("")

    @patch("auto_sdd.scripts.eval_sidecar.run_agent_with_backoff")
    @patch("auto_sdd.scripts.eval_sidecar.run_mechanical_eval")
    def test_credit_exhaustion_disables_agent_evals(
        self,
        mock_mech: MagicMock,
        mock_backoff: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Agent eval credit failure disables agent evals for remainder."""
        repo = _create_test_repo(tmp_path)
        eval_dir = tmp_path / "evals"
        eval_dir.mkdir()

        config = EvalSidecarConfig(
            project_dir=repo,
            eval_interval=0,
            eval_agent=True,
            eval_output_dir=eval_dir,
        )
        state = CampaignState()
        commit = _git(repo, "rev-parse", "HEAD")

        mock_mech.return_value = MechanicalEvalResult(
            diff_stats={"feature_name": "test", "files_changed": 1},
            type_exports_changed=[],
            redeclarations=[],
            test_files_touched=[],
            passed=True,
        )

        # Agent fails with credit error
        def backoff_side_effect(output_file: Path, cmd: list[str], **kwargs: Any) -> int:
            output_file.write_text("Error: 402 Payment Required")
            return 1

        mock_backoff.side_effect = backoff_side_effect

        _evaluate_commit(config, state, commit)
        assert state.agent_evals_disabled is True


# ── Individual eval error handling ────────────────────────────────────────────


class TestEvalErrorHandling:
    """Tests for error handling during individual commit evaluation."""

    @patch("auto_sdd.scripts.eval_sidecar.run_mechanical_eval")
    def test_mechanical_fail_skips_commit(
        self, mock_mech: MagicMock, tmp_path: Path
    ) -> None:
        """Mechanical eval failure skips the commit and increments errors."""
        repo = _create_test_repo(tmp_path)
        eval_dir = tmp_path / "evals"
        eval_dir.mkdir()

        config = EvalSidecarConfig(
            project_dir=repo,
            eval_interval=0,
            eval_agent=False,
            eval_output_dir=eval_dir,
        )
        state = CampaignState()
        commit = _git(repo, "rev-parse", "HEAD")

        mock_mech.side_effect = EvalError("boom")

        _evaluate_commit(config, state, commit)
        assert state.eval_errors == 1
        assert state.eval_count == 0

    @patch("auto_sdd.scripts.eval_sidecar.run_agent_with_backoff")
    @patch("auto_sdd.scripts.eval_sidecar.run_mechanical_eval")
    def test_agent_fail_falls_back_to_mechanical_only(
        self,
        mock_mech: MagicMock,
        mock_backoff: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Agent eval failure still writes mechanical-only result."""
        repo = _create_test_repo(tmp_path)
        eval_dir = tmp_path / "evals"
        eval_dir.mkdir()

        config = EvalSidecarConfig(
            project_dir=repo,
            eval_interval=0,
            eval_agent=True,
            eval_output_dir=eval_dir,
        )
        state = CampaignState()
        commit = _git(repo, "rev-parse", "HEAD")

        mock_mech.return_value = MechanicalEvalResult(
            diff_stats={"feature_name": "fallback-test", "files_changed": 1},
            type_exports_changed=[],
            redeclarations=[],
            test_files_touched=[],
            passed=True,
        )

        # Agent fails with non-credit error
        def backoff_side_effect(output_file: Path, cmd: list[str], **kwargs: Any) -> int:
            output_file.write_text("some error")
            return 1

        mock_backoff.side_effect = backoff_side_effect

        _evaluate_commit(config, state, commit)
        # Should still write the eval result (mechanical only)
        assert state.eval_count == 1
        assert state.eval_errors == 1
        assert state.agent_evals_disabled is False


# ── Agent command builder ─────────────────────────────────────────────────────


class TestAgentCmd:
    """Tests for _build_agent_cmd."""

    def test_default_cmd(self) -> None:
        """Default agent command has no model flag."""
        cmd = _build_agent_cmd("")
        assert cmd == ["-p", "--dangerously-skip-permissions"]

    def test_cmd_with_model(self) -> None:
        """Agent command includes --model when model is specified."""
        cmd = _build_agent_cmd("claude-sonnet-4-20250514")
        assert "--model" in cmd
        assert "claude-sonnet-4-20250514" in cmd


# ── CampaignState ────────────────────────────────────────────────────────────


class TestCampaignState:
    """Tests for CampaignState defaults."""

    def test_defaults(self) -> None:
        """CampaignState initializes with correct defaults."""
        state = CampaignState()
        assert state.last_evaluated_commit == ""
        assert state.agent_evals_disabled is False
        assert state.eval_count == 0
        assert state.eval_errors == 0
        assert state.draining is False
        assert state.shutdown_requested is False


# ── Polling loop ──────────────────────────────────────────────────────────────


class TestPollingLoop:
    """Tests for run_polling_loop."""

    def test_loop_fails_on_no_head(self, tmp_path: Path) -> None:
        """Polling loop raises EvalError when HEAD can't be determined."""
        # Use a non-git directory
        project = tmp_path / "not-a-repo"
        project.mkdir()
        eval_dir = tmp_path / "evals"
        eval_dir.mkdir()

        config = EvalSidecarConfig(
            project_dir=project,
            eval_interval=0,
            eval_agent=False,
            eval_output_dir=eval_dir,
        )
        with pytest.raises(EvalError, match="Could not determine HEAD"):
            run_polling_loop(config)

    @patch("auto_sdd.scripts.eval_sidecar._get_head")
    def test_shutdown_requested_exits_loop(
        self, mock_head: MagicMock, tmp_path: Path
    ) -> None:
        """Setting shutdown_requested causes the loop to exit."""
        repo = _create_test_repo(tmp_path)
        eval_dir = tmp_path / "evals"
        eval_dir.mkdir()
        head = _git(repo, "rev-parse", "HEAD")

        config = EvalSidecarConfig(
            project_dir=repo,
            eval_interval=0,
            eval_agent=False,
            eval_output_dir=eval_dir,
        )

        call_count = 0

        def side_effect(project_dir: Path) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return head
            # On second call (inside loop), write sentinel to drain
            (repo / ".sdd-eval-drain").write_text("drain")
            return head

        mock_head.side_effect = side_effect

        state = run_polling_loop(config)
        assert state.shutdown_requested is False
        assert state.draining is True

    def test_stale_sentinel_cleaned_on_startup(self, tmp_path: Path) -> None:
        """Stale drain sentinel from a prior crash is removed on startup."""
        repo = _create_test_repo(tmp_path)
        eval_dir = tmp_path / "evals"
        eval_dir.mkdir()

        # Create stale sentinel
        sentinel = repo / ".sdd-eval-drain"
        sentinel.write_text("stale")
        assert sentinel.exists(), "Sentinel should exist before loop starts"

        config = EvalSidecarConfig(
            project_dir=repo,
            eval_interval=0,
            eval_agent=False,
            eval_output_dir=eval_dir,
        )

        head = _git(repo, "rev-parse", "HEAD")
        call_count = 0

        def head_side_effect(project_dir: Path) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # This is initialization — stale sentinel should already
                # have been cleaned by this point
                return head
            # Write a fresh sentinel to trigger drain exit
            sentinel.write_text("drain")
            return head

        with patch(
            "auto_sdd.scripts.eval_sidecar._get_head",
            side_effect=head_side_effect,
        ):
            state = run_polling_loop(config)
            assert state.draining is True
            # The stale sentinel was cleaned; the drain sentinel was also
            # cleaned after drain completed
            assert not sentinel.exists(), "Sentinel should be cleaned after drain"
