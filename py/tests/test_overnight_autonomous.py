"""Tests for auto_sdd.scripts.overnight_autonomous — OvernightRunner.

Since this is orchestration code that calls many sub-modules, heavy mocking
is acceptable here (unlike lib modules where we prefer real files).
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest

from auto_sdd.lib.build_gates import BuildCheckResult
from auto_sdd.lib.drift import DriftCheckResult, DriftTargets
from auto_sdd.lib.reliability import AgentTimeoutError, AutoSddError, Feature
from auto_sdd.lib.claude_wrapper import CreditExhaustionError
from auto_sdd.scripts.overnight_autonomous import (
    OvernightConfig,
    OvernightRunner,
    _format_duration,
    _load_config,
    _parse_signal,
    _source_env_file,
    _validate_required_signals,
)


# ── Helper fixtures ──────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove env vars that could interfere with OvernightRunner."""
    for var in [
        "PROJECT_DIR", "BASE_BRANCH", "BRANCH_STRATEGY",
        "MAX_FEATURES", "MAX_RETRIES", "MIN_RETRY_DELAY",
        "SLACK_FEATURE_CHANNEL", "SLACK_REPORT_CHANNEL",
        "JIRA_PROJECT_KEY", "ENABLE_RESUME",
        "AGENT_MODEL", "BUILD_MODEL", "RETRY_MODEL",
        "DRIFT_MODEL", "REVIEW_MODEL", "TRIAGE_MODEL",
        "POST_BUILD_STEPS", "EVAL_SIDECAR", "EVAL_AGENT",
        "EVAL_MODEL", "CLAUDECODE",
    ]:
        monkeypatch.delenv(var, raising=False)


def _make_config(tmp_path: Path, **overrides: Any) -> OvernightConfig:
    """Create an OvernightConfig with sensible test defaults."""
    defaults: dict[str, Any] = {
        "project_dir": tmp_path,
        "base_branch": "main",
        "branch_strategy": "chained",
        "max_features": 4,
        "max_retries": 1,
        "min_retry_delay": 0,
        "enable_resume": False,
        "eval_sidecar": False,
        "post_build_steps": "",
    }
    defaults.update(overrides)
    return OvernightConfig(**defaults)


def _make_runner(tmp_path: Path, **overrides: Any) -> OvernightRunner:
    """Create an OvernightRunner with mocked lock and minimal config."""
    config = _make_config(tmp_path, **overrides)
    # Create minimal project structure
    (tmp_path / ".specs").mkdir(exist_ok=True)
    (tmp_path / ".specs" / "roadmap.md").touch()
    runner = OvernightRunner(config)
    runner.script_start = 1000.0
    return runner


# ── Helper function tests ────────────────────────────────────────────────────


class TestFormatDuration:
    """Tests for _format_duration."""

    def test_seconds_only(self) -> None:
        assert _format_duration(45) == "45s"

    def test_minutes_and_seconds(self) -> None:
        assert _format_duration(125) == "2m 5s"

    def test_hours_minutes_seconds(self) -> None:
        assert _format_duration(3661) == "1h 1m 1s"

    def test_zero(self) -> None:
        assert _format_duration(0) == "0s"


class TestParseSignal:
    """Tests for _parse_signal."""

    def test_extracts_last_value(self) -> None:
        output = "FEATURE_BUILT: first\nsome other line\nFEATURE_BUILT: second\n"
        assert _parse_signal("FEATURE_BUILT", output) == "second"

    def test_returns_empty_when_not_found(self) -> None:
        assert _parse_signal("MISSING", "no signals here") == ""

    def test_handles_colons_in_value(self) -> None:
        output = "SPEC_FILE: path/to/file:with:colons.md\n"
        assert _parse_signal("SPEC_FILE", output) == "path/to/file:with:colons.md"

    def test_strips_whitespace(self) -> None:
        output = "  FEATURE_BUILT:   auth login  \n"
        assert _parse_signal("FEATURE_BUILT", output) == "auth login"


class TestValidateRequiredSignals:
    """Tests for _validate_required_signals."""

    def test_returns_false_without_feature_built(self) -> None:
        assert not _validate_required_signals("just some output")

    def test_returns_false_without_spec_file(self) -> None:
        assert not _validate_required_signals("FEATURE_BUILT: auth\n")

    def test_returns_false_when_spec_file_missing_on_disk(self) -> None:
        output = "FEATURE_BUILT: auth\nSPEC_FILE: /nonexistent/path.feature.md\n"
        assert not _validate_required_signals(output)

    def test_returns_true_when_all_present(self, tmp_path: Path) -> None:
        spec = tmp_path / "feature.feature.md"
        spec.write_text("# Feature\n")
        output = f"FEATURE_BUILT: auth\nSPEC_FILE: {spec}\n"
        assert _validate_required_signals(output)


class TestCreditExhaustionError:
    """CreditExhaustionError is raised by claude_wrapper on billing signals."""

    def test_is_exception(self) -> None:
        err = CreditExhaustionError("quota exceeded")
        assert isinstance(err, Exception)

    def test_message_preserved(self) -> None:
        err = CreditExhaustionError("Error: insufficient_quota reached")
        assert "insufficient_quota" in str(err)

    def test_is_not_raised_for_normal_text(self) -> None:
        # CreditExhaustionError is raised by claude_wrapper, not from output text
        err = CreditExhaustionError("FEATURE_BUILT: auth")
        assert "FEATURE_BUILT" in str(err)

    def test_billing_message_402(self) -> None:
        err = CreditExhaustionError("Error: 402 Payment Required")
        assert "402" in str(err)


# ── Config tests ─────────────────────────────────────────────────────────────


class TestOvernightConfig:
    """Tests for OvernightConfig."""

    def test_rejects_both_strategy(self) -> None:
        config = OvernightConfig(
            project_dir=Path("/tmp"),
            branch_strategy="both",
        )
        assert config.branch_strategy == "chained"

    def test_rejects_sequential_strategy(self) -> None:
        config = OvernightConfig(
            project_dir=Path("/tmp"),
            branch_strategy="sequential",
        )
        assert config.branch_strategy == "chained"

    def test_accepts_chained(self) -> None:
        config = OvernightConfig(
            project_dir=Path("/tmp"),
            branch_strategy="chained",
        )
        assert config.branch_strategy == "chained"

    def test_accepts_independent(self) -> None:
        config = OvernightConfig(
            project_dir=Path("/tmp"),
            branch_strategy="independent",
        )
        assert config.branch_strategy == "independent"

    def test_default_values(self) -> None:
        config = OvernightConfig(project_dir=Path("/tmp"))
        assert config.max_features == 4
        assert config.max_retries == 1
        assert config.min_retry_delay == 30
        assert config.enable_resume is True
        assert config.eval_sidecar is True


class TestSourceEnvFile:
    """Tests for _source_env_file."""

    def test_loads_simple_key_value(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env.local"
        env_file.write_text("TEST_VAR_XYZ=hello\n")
        _source_env_file(env_file)
        assert os.environ.get("TEST_VAR_XYZ") == "hello"
        # Clean up
        del os.environ["TEST_VAR_XYZ"]

    def test_strips_quotes(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env.local"
        env_file.write_text('TEST_VAR_ABC="quoted value"\n')
        _source_env_file(env_file)
        assert os.environ.get("TEST_VAR_ABC") == "quoted value"
        del os.environ["TEST_VAR_ABC"]

    def test_skips_comments(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env.local"
        env_file.write_text("# comment\nTEST_VAR_DEF=val\n")
        _source_env_file(env_file)
        assert os.environ.get("TEST_VAR_DEF") == "val"
        del os.environ["TEST_VAR_DEF"]

    def test_does_not_override_existing_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TEST_VAR_GHI", "existing")
        env_file = tmp_path / ".env.local"
        env_file.write_text("TEST_VAR_GHI=new\n")
        _source_env_file(env_file)
        assert os.environ["TEST_VAR_GHI"] == "existing"


class TestLoadConfig:
    """Tests for _load_config."""

    def test_reads_from_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PROJECT_DIR", str(tmp_path))
        monkeypatch.setenv("MAX_FEATURES", "10")
        monkeypatch.setenv("BRANCH_STRATEGY", "independent")
        config = _load_config()
        assert config.max_features == 10
        assert config.branch_strategy == "independent"

    def test_defaults_without_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PROJECT_DIR", str(tmp_path))
        config = _load_config()
        assert config.base_branch == "main"
        assert config.max_retries == 1


# ── OvernightRunner construction tests ───────────────────────────────────────


class TestOvernightRunnerInit:
    """Tests for OvernightRunner.__init__."""

    def test_default_tracking_state(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)
        assert runner.built_feature_names == []
        assert runner.step_timings == []
        assert runner.feature_timings == []
        assert runner.built == 0
        assert runner.failed == 0
        assert runner.eval_sidecar_pid is None

    def test_lock_file_path(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)
        assert "sdd-overnight" in str(runner.lock_file)


# ── _sync_branch tests ──────────────────────────────────────────────────────


class TestSyncBranch:
    """Tests for OvernightRunner._sync_branch."""

    @patch("auto_sdd.scripts.overnight_autonomous._run_git")
    def test_syncs_main_branch(
        self, mock_git: MagicMock, tmp_path: Path
    ) -> None:
        runner = _make_runner(tmp_path, base_branch="main")
        mock_git.return_value = MagicMock(
            returncode=0, stdout="abc123\n"
        )
        runner._sync_branch()
        assert runner.main_branch == "main"
        assert len(runner.step_timings) == 1

    @patch("auto_sdd.scripts.overnight_autonomous._run_git")
    def test_stale_branch_reset(
        self, mock_git: MagicMock, tmp_path: Path
    ) -> None:
        runner = _make_runner(tmp_path, base_branch="current")
        # First call: branch --show-current returns stale auto/ branch
        # Second call: rev-parse --verify returns success
        # Third call: checkout
        # Fourth call: pull
        call_count = [0]

        def side_effect(args: list[str], *a: Any, **kw: Any) -> MagicMock:
            call_count[0] += 1
            result = MagicMock(returncode=0)
            if args == ["branch", "--show-current"]:
                result.stdout = "auto/stale-branch\n"
            else:
                result.stdout = "abc123\n"
            return result

        mock_git.side_effect = side_effect
        runner._sync_branch()
        assert runner.main_branch == "main"

    @patch("auto_sdd.scripts.overnight_autonomous._run_git")
    def test_nonexistent_branch_raises(
        self, mock_git: MagicMock, tmp_path: Path
    ) -> None:
        runner = _make_runner(tmp_path, base_branch="nonexistent")
        mock_git.return_value = MagicMock(
            returncode=1, stdout=""
        )
        with pytest.raises(AutoSddError, match="does not exist"):
            runner._sync_branch()


# ── _rebase_prs tests ────────────────────────────────────────────────────────


class TestRebasePrs:
    """Tests for OvernightRunner._rebase_prs."""

    @patch("shutil.which", return_value=None)
    def test_skips_when_no_gh(
        self, mock_which: MagicMock, tmp_path: Path
    ) -> None:
        runner = _make_runner(tmp_path)
        runner.main_branch = "main"
        rebased = runner._rebase_prs()
        assert rebased == 0

    @patch("auto_sdd.scripts.overnight_autonomous._run_git")
    @patch("shutil.which", return_value="/usr/bin/gh")
    @patch("subprocess.run")
    def test_rebases_auto_branches(
        self,
        mock_subprocess: MagicMock,
        mock_which: MagicMock,
        mock_git: MagicMock,
        tmp_path: Path,
    ) -> None:
        runner = _make_runner(tmp_path)
        runner.main_branch = "main"
        # gh pr list returns one branch
        mock_subprocess.return_value = MagicMock(
            returncode=0,
            stdout="auto/feature-123\n",
        )
        mock_git.return_value = MagicMock(returncode=0, stdout="")
        rebased = runner._rebase_prs()
        assert rebased == 1


# ── _run_triage tests ────────────────────────────────────────────────────────


class TestRunTriage:
    """Tests for OvernightRunner._run_triage."""

    @patch("auto_sdd.scripts.overnight_autonomous.run_agent_with_backoff")
    def test_triage_completes(
        self, mock_agent: MagicMock, tmp_path: Path
    ) -> None:
        runner = _make_runner(tmp_path)
        mock_agent.return_value = 0
        runner._run_triage()
        assert len(runner.step_timings) == 1
        mock_agent.assert_called_once()

    @patch("auto_sdd.scripts.overnight_autonomous.run_agent_with_backoff")
    def test_triage_failure_nonblocking(
        self, mock_agent: MagicMock, tmp_path: Path
    ) -> None:
        runner = _make_runner(tmp_path)
        mock_agent.return_value = 1
        runner._run_triage()  # Should not raise
        assert len(runner.step_timings) == 1

    @patch(
        "auto_sdd.scripts.overnight_autonomous.run_agent_with_backoff",
        side_effect=AgentTimeoutError("timeout"),
    )
    def test_triage_timeout_nonblocking(
        self, mock_agent: MagicMock, tmp_path: Path
    ) -> None:
        runner = _make_runner(tmp_path)
        runner._run_triage()  # Should not raise


# ── _build_features tests ────────────────────────────────────────────────────


class TestBuildFeatures:
    """Tests for OvernightRunner._build_features."""

    @patch("auto_sdd.scripts.overnight_autonomous.emit_topo_order", return_value=[])
    @patch("auto_sdd.scripts.overnight_autonomous.check_circular_deps")
    @patch("auto_sdd.scripts.overnight_autonomous.release_lock")
    def test_no_features_exits_cleanly(
        self,
        mock_release: MagicMock,
        mock_circ: MagicMock,
        mock_topo: MagicMock,
        tmp_path: Path,
    ) -> None:
        runner = _make_runner(tmp_path)
        runner.main_branch = "main"
        built, failed = runner._build_features()
        assert built == 0
        assert failed == 0

    @patch("auto_sdd.scripts.overnight_autonomous.generate_codebase_summary", return_value="mock summary")
    @patch("auto_sdd.scripts.overnight_autonomous.check_drift")
    @patch("auto_sdd.scripts.overnight_autonomous.extract_drift_targets")
    @patch("auto_sdd.scripts.overnight_autonomous._run_git")
    @patch("auto_sdd.scripts.overnight_autonomous.run_agent_with_backoff")
    @patch("auto_sdd.scripts.overnight_autonomous.emit_topo_order")
    @patch("auto_sdd.scripts.overnight_autonomous.check_circular_deps")
    def test_single_feature_success(
        self,
        mock_circ: MagicMock,
        mock_topo: MagicMock,
        mock_agent: MagicMock,
        mock_git: MagicMock,
        mock_drift_targets: MagicMock,
        mock_drift: MagicMock,
        mock_summary: MagicMock,
        tmp_path: Path,
    ) -> None:
        runner = _make_runner(tmp_path)
        runner.main_branch = "main"

        mock_drift.return_value = MagicMock(passed=True)

        mock_topo.return_value = [Feature(id=1, name="auth", complexity="M")]

        # Agent succeeds with FEATURE_BUILT
        output_file_written = [False]

        def agent_side_effect(
            output_file: Path, cmd: list[str], **kw: Any
        ) -> int:
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(
                "FEATURE_BUILT: auth\n"
                "SPEC_FILE: spec.md\n"
                "SOURCE_FILES: src/auth.ts\n"
            )
            return 0

        mock_agent.side_effect = agent_side_effect

        # Git calls succeed with appropriate outputs
        def git_side_effect(
            args: list[str], project_dir: Path, **kw: Any
        ) -> MagicMock:
            result = MagicMock(returncode=0)
            if args == ["rev-parse", "HEAD"]:
                result.stdout = "abc123\n"
            elif args == ["status", "--porcelain"]:
                result.stdout = "M src/auth.ts\n"
            else:
                result.stdout = ""
            return result

        mock_git.side_effect = git_side_effect

        built, failed = runner._build_features()
        assert built == 1
        assert failed == 0

    @patch("auto_sdd.scripts.overnight_autonomous.generate_codebase_summary", return_value="mock summary")
    @patch("auto_sdd.scripts.overnight_autonomous._run_git")
    @patch("auto_sdd.scripts.overnight_autonomous.run_agent_with_backoff")
    @patch("auto_sdd.scripts.overnight_autonomous.emit_topo_order")
    @patch("auto_sdd.scripts.overnight_autonomous.check_circular_deps")
    def test_feature_failure_all_retries(
        self,
        mock_circ: MagicMock,
        mock_topo: MagicMock,
        mock_agent: MagicMock,
        mock_git: MagicMock,
        mock_summary: MagicMock,
        tmp_path: Path,
    ) -> None:
        runner = _make_runner(tmp_path, max_retries=1, min_retry_delay=0)
        runner.main_branch = "main"

        mock_topo.return_value = [Feature(id=1, name="auth", complexity="M")]

        def agent_side_effect(
            output_file: Path, cmd: list[str], **kw: Any
        ) -> int:
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text("BUILD_FAILED: compile error\n")
            return 1

        mock_agent.side_effect = agent_side_effect
        mock_git.return_value = MagicMock(returncode=0, stdout="abc123\n")

        built, failed = runner._build_features()
        assert built == 0
        assert failed == 1
        assert len(runner.feature_timings) == 1
        assert "✗ auth" in runner.feature_timings[0]


# ── _build_single_feature tests ──────────────────────────────────────────────


class TestBuildSingleFeature:
    """Tests for OvernightRunner._build_single_feature."""

    @patch("auto_sdd.scripts.overnight_autonomous.generate_codebase_summary", return_value="mock summary")
    @patch("auto_sdd.scripts.overnight_autonomous._run_git")
    @patch("auto_sdd.scripts.overnight_autonomous.run_agent_with_backoff")
    def test_credit_exhaustion_raises(
        self,
        mock_agent: MagicMock,
        mock_git: MagicMock,
        mock_summary: MagicMock,
        tmp_path: Path,
    ) -> None:
        runner = _make_runner(tmp_path)
        runner.main_branch = "main"

        def agent_side_effect(
            output_file: Path, cmd: list[str], **kw: Any
        ) -> int:
            raise CreditExhaustionError("insufficient_quota")

        mock_agent.side_effect = agent_side_effect
        mock_git.return_value = MagicMock(returncode=0, stdout="abc123\n")

        with pytest.raises(AutoSddError, match="credits exhausted"):
            runner._build_single_feature("1", "auth", 0, 1)

    @patch("auto_sdd.scripts.overnight_autonomous.generate_codebase_summary", return_value="mock summary")
    @patch("auto_sdd.scripts.overnight_autonomous._run_git")
    @patch("auto_sdd.scripts.overnight_autonomous.run_agent_with_backoff")
    def test_no_features_ready_returns_false(
        self,
        mock_agent: MagicMock,
        mock_git: MagicMock,
        mock_summary: MagicMock,
        tmp_path: Path,
    ) -> None:
        runner = _make_runner(tmp_path)
        runner.main_branch = "main"

        def agent_side_effect(
            output_file: Path, cmd: list[str], **kw: Any
        ) -> int:
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text("NO_FEATURES_READY\n")
            return 0

        mock_agent.side_effect = agent_side_effect
        mock_git.return_value = MagicMock(returncode=0, stdout="abc123\n")

        result = runner._build_single_feature("1", "auth", 0, 1)
        assert result is False


# ── _post_build tests (non-blocking failures) ────────────────────────────────


class TestPostBuild:
    """Tests for non-blocking failure behavior."""

    @patch("auto_sdd.scripts.overnight_autonomous._run_git")
    @patch("auto_sdd.scripts.overnight_autonomous.check_drift")
    @patch("auto_sdd.scripts.overnight_autonomous.extract_drift_targets")
    def test_drift_failure_still_pushes(
        self,
        mock_extract: MagicMock,
        mock_drift: MagicMock,
        mock_git: MagicMock,
        tmp_path: Path,
    ) -> None:
        runner = _make_runner(tmp_path)
        runner.main_branch = "main"

        mock_extract.return_value = DriftTargets(
            spec_file="spec.md", source_files="src/auth.ts"
        )
        mock_drift.return_value = DriftCheckResult(
            passed=False, summary="drift found"
        )

        # Create spec file for signal validation
        spec = tmp_path / "spec.md"
        spec.write_text("# Spec\n")

        def git_side_effect(
            args: list[str], project_dir: Path, **kw: Any
        ) -> MagicMock:
            result = MagicMock(returncode=0)
            if args == ["status", "--porcelain"]:
                result.stdout = "M file.ts\n"
            else:
                result.stdout = ""
            return result

        mock_git.side_effect = git_side_effect

        build_result = f"FEATURE_BUILT: auth\nSPEC_FILE: {spec}\nSOURCE_FILES: src/auth.ts\n"
        success = runner._post_build(
            "auto/feature-123", "auth", "1", build_result, 1000.0
        )
        assert success is True
        assert "auth" in runner.built_feature_names

    @patch("auto_sdd.scripts.overnight_autonomous._run_git")
    @patch("auto_sdd.scripts.overnight_autonomous.check_tests")
    def test_test_failure_still_pushes(
        self,
        mock_tests: MagicMock,
        mock_git: MagicMock,
        tmp_path: Path,
    ) -> None:
        runner = _make_runner(tmp_path, post_build_steps="test")
        runner.main_branch = "main"
        runner.test_cmd = "npm test"

        mock_tests.return_value = BuildCheckResult(
            success=False, output="1 test failed"
        )

        def git_side_effect(
            args: list[str], project_dir: Path, **kw: Any
        ) -> MagicMock:
            result = MagicMock(returncode=0)
            if args == ["status", "--porcelain"]:
                result.stdout = "M file.ts\n"
            else:
                result.stdout = ""
            return result

        mock_git.side_effect = git_side_effect

        build_result = "FEATURE_BUILT: auth\nSPEC_FILE: missing.md\n"
        success = runner._post_build(
            "auto/feature-123", "auth", "1", build_result, 1000.0
        )
        assert success is True
        assert any("⚠" in t for t in runner.feature_timings)


# ── _create_pr tests ─────────────────────────────────────────────────────────


class TestCreatePr:
    """Tests for OvernightRunner._create_pr."""

    @patch("shutil.which", return_value=None)
    def test_returns_none_without_gh(
        self, mock_which: MagicMock, tmp_path: Path
    ) -> None:
        runner = _make_runner(tmp_path)
        result = runner._create_pr("auto/branch", "auth", "spec content")
        assert result is None

    @patch("shutil.which", return_value="/usr/bin/gh")
    @patch("subprocess.run")
    def test_creates_draft_pr(
        self,
        mock_run: MagicMock,
        mock_which: MagicMock,
        tmp_path: Path,
    ) -> None:
        runner = _make_runner(tmp_path)
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="https://github.com/test/repo/pull/42\n",
        )
        result = runner._create_pr("auto/branch", "auth", "spec content")
        assert result == "https://github.com/test/repo/pull/42"
        # Verify --draft flag used
        call_args = mock_run.call_args[0][0]
        assert "--draft" in call_args

    @patch("shutil.which", return_value="/usr/bin/gh")
    @patch("subprocess.run", side_effect=subprocess.TimeoutExpired("gh", 60))
    def test_returns_none_on_timeout(
        self,
        mock_run: MagicMock,
        mock_which: MagicMock,
        tmp_path: Path,
    ) -> None:
        runner = _make_runner(tmp_path)
        result = runner._create_pr("auto/branch", "auth", "spec content")
        assert result is None


# ── Resume mode tests ────────────────────────────────────────────────────────


class TestResumeMode:
    """Tests for resume functionality."""

    @patch("auto_sdd.scripts.overnight_autonomous.generate_codebase_summary", return_value="mock summary")
    @patch("auto_sdd.scripts.overnight_autonomous.check_drift")
    @patch("auto_sdd.scripts.overnight_autonomous.extract_drift_targets")
    @patch("auto_sdd.scripts.overnight_autonomous._run_git")
    @patch("auto_sdd.scripts.overnight_autonomous.run_agent_with_backoff")
    @patch("auto_sdd.scripts.overnight_autonomous.emit_topo_order")
    @patch("auto_sdd.scripts.overnight_autonomous.check_circular_deps")
    def test_skips_completed_features(
        self,
        mock_circ: MagicMock,
        mock_topo: MagicMock,
        mock_agent: MagicMock,
        mock_git: MagicMock,
        mock_drift_targets: MagicMock,
        mock_drift: MagicMock,
        mock_summary: MagicMock,
        tmp_path: Path,
    ) -> None:
        runner = _make_runner(tmp_path)
        runner.main_branch = "main"
        runner.built_feature_names = ["auth"]

        mock_drift.return_value = MagicMock(passed=True)

        mock_topo.return_value = [
            Feature(id=1, name="auth", complexity="M"),
            Feature(id=2, name="dashboard", complexity="L"),
        ]

        def agent_side_effect(
            output_file: Path, cmd: list[str], **kw: Any
        ) -> int:
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(
                "FEATURE_BUILT: dashboard\n"
                "SPEC_FILE: spec.md\n"
                "SOURCE_FILES: src/dash.ts\n"
            )
            return 0

        mock_agent.side_effect = agent_side_effect

        def git_side_effect(
            args: list[str], project_dir: Path, **kw: Any
        ) -> MagicMock:
            result = MagicMock(returncode=0)
            if args == ["rev-parse", "HEAD"]:
                result.stdout = "abc123\n"
            elif args == ["status", "--porcelain"]:
                result.stdout = "M src/dash.ts\n"
            else:
                result.stdout = ""
            return result

        mock_git.side_effect = git_side_effect

        built, failed = runner._build_features()
        # auth was skipped, only dashboard built
        assert built == 1
        assert "dashboard" in runner.built_feature_names


# ── Prompts tests ────────────────────────────────────────────────────────────


class TestPrompts:
    """Tests for prompt generation."""

    @patch(
        "auto_sdd.scripts.overnight_autonomous.generate_codebase_summary",
        return_value="mock summary",
    )
    def test_build_feature_prompt_includes_jira_sync(
        self, mock_summary: MagicMock, tmp_path: Path
    ) -> None:
        runner = _make_runner(tmp_path)
        prompt = runner._build_feature_prompt("1", "auth")
        assert "Sync Jira status" in prompt
        assert "auth" in prompt
        assert "FEATURE_BUILT" in prompt
        assert "Codebase Summary" in prompt

    @patch(
        "auto_sdd.scripts.overnight_autonomous.generate_codebase_summary",
        side_effect=Exception("fail"),
    )
    def test_build_feature_prompt_handles_summary_failure(
        self, mock_summary: MagicMock, tmp_path: Path
    ) -> None:
        runner = _make_runner(tmp_path)
        prompt = runner._build_feature_prompt("1", "auth")
        assert "auth" in prompt
        assert "Codebase Summary" not in prompt

    def test_retry_prompt_includes_last_output(
        self, tmp_path: Path
    ) -> None:
        runner = _make_runner(tmp_path)
        runner.test_cmd = "npm test"
        runner.last_build_output = "error: type mismatch"
        runner.last_test_output = "1 test failed"
        prompt = runner._build_retry_prompt()
        assert "type mismatch" in prompt
        assert "1 test failed" in prompt
        assert "FEATURE_BUILT" in prompt

    def test_retry_prompt_without_failure_output(
        self, tmp_path: Path
    ) -> None:
        runner = _make_runner(tmp_path)
        runner.test_cmd = ""
        prompt = runner._build_retry_prompt()
        assert "BUILD CHECK FAILURE" not in prompt
        assert "TEST SUITE FAILURE" not in prompt


# ── Eval sidecar tests ──────────────────────────────────────────────────────


class TestEvalSidecar:
    """Tests for eval sidecar lifecycle."""

    def test_start_disabled(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path, eval_sidecar=False)
        runner._start_eval_sidecar()
        assert runner.eval_sidecar_pid is None

    @patch("subprocess.Popen")
    def test_start_missing_script_falls_back_to_python(
        self, mock_popen: MagicMock, tmp_path: Path
    ) -> None:
        runner = _make_runner(tmp_path, eval_sidecar=True)
        mock_proc = MagicMock()
        mock_proc.pid = 99999
        mock_popen.return_value = mock_proc

        runner._start_eval_sidecar()
        # With fallback, sidecar should still start via Python module
        assert runner.eval_sidecar_pid == 99999
        call_args = mock_popen.call_args[0][0]
        assert "-m" in call_args

    @patch("subprocess.Popen")
    def test_start_stores_pid(
        self, mock_popen: MagicMock, tmp_path: Path
    ) -> None:
        runner = _make_runner(tmp_path, eval_sidecar=True)
        # Create sidecar script
        sidecar = tmp_path / "scripts" / "eval-sidecar.sh"
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        sidecar.write_text("#!/bin/bash\nsleep 60\n")

        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_popen.return_value = mock_proc

        runner._start_eval_sidecar()
        assert runner.eval_sidecar_pid == 12345

    @patch("subprocess.Popen")
    def test_python_module_fallback_when_no_bash_script(
        self, mock_popen: MagicMock, tmp_path: Path
    ) -> None:
        runner = _make_runner(tmp_path, eval_sidecar=True)
        # Do NOT create scripts/eval-sidecar.sh — trigger fallback

        mock_proc = MagicMock()
        mock_proc.pid = 54321
        mock_popen.return_value = mock_proc

        runner._start_eval_sidecar()
        assert runner.eval_sidecar_pid == 54321
        # Verify the fallback command uses Python module, not bash
        call_args = mock_popen.call_args[0][0]
        assert "-m" in call_args
        assert "auto_sdd.scripts.eval_sidecar" in call_args

    def test_stop_noop_when_no_pid(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)
        runner.eval_sidecar_pid = None
        runner._stop_eval_sidecar()  # Should not raise

    @patch("os.kill")
    def test_stop_sends_signals(
        self, mock_kill: MagicMock, tmp_path: Path
    ) -> None:
        runner = _make_runner(tmp_path)
        runner.eval_sidecar_pid = 99999

        # First call to kill(0) succeeds (still running), second raises OSError (exited)
        call_count = [0]

        def kill_side_effect(pid: int, sig: int) -> None:
            call_count[0] += 1
            if call_count[0] > 2:
                raise OSError("No such process")

        mock_kill.side_effect = kill_side_effect

        with patch("time.sleep"):
            runner._stop_eval_sidecar()

        assert runner.eval_sidecar_pid is None


# ── Report summary tests ────────────────────────────────────────────────────


class TestReportSummary:
    """Tests for OvernightRunner._report_summary."""

    def test_prints_summary_without_error(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)
        runner.script_start = 1000.0
        runner.built = 2
        runner.failed = 1
        runner.step_timings = ["Step 0 - Sync: 5s"]
        runner.feature_timings = ["✓ auth: 120s"]
        with patch("time.time", return_value=1300.0):
            runner._report_summary()  # Should not raise

    def test_reads_roadmap_status(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)
        runner.script_start = 1000.0
        runner.built = 0
        runner.failed = 0
        roadmap = tmp_path / ".specs" / "roadmap.md"
        roadmap.write_text("| ✅ | done |\n| ⬜ | pending |\n| 🔄 | wip |\n")
        with patch("time.time", return_value=1100.0):
            runner._report_summary()  # Should not raise


# ── Slack notification tests ─────────────────────────────────────────────────


class TestNotifySlack:
    """Tests for OvernightRunner._notify_slack."""

    @patch("auto_sdd.scripts.overnight_autonomous.run_agent_with_backoff")
    def test_sends_slack_message(
        self, mock_agent: MagicMock, tmp_path: Path
    ) -> None:
        runner = _make_runner(tmp_path, slack_report_channel="#reports")
        mock_agent.return_value = 0
        runner._notify_slack(2, 1)
        mock_agent.assert_called_once()

    @patch(
        "auto_sdd.scripts.overnight_autonomous.run_agent_with_backoff",
        side_effect=AgentTimeoutError("timeout"),
    )
    def test_slack_timeout_nonblocking(
        self, mock_agent: MagicMock, tmp_path: Path
    ) -> None:
        runner = _make_runner(tmp_path, slack_report_channel="#reports")
        runner._notify_slack(1, 0)  # Should not raise


# ── Full run() integration test ──────────────────────────────────────────────


class TestFullRun:
    """Integration test for OvernightRunner.run with full mocking."""

    @patch("auto_sdd.scripts.overnight_autonomous.release_lock")
    @patch("auto_sdd.scripts.overnight_autonomous.acquire_lock")
    @patch("auto_sdd.scripts.overnight_autonomous._run_git")
    @patch("auto_sdd.scripts.overnight_autonomous.run_agent_with_backoff")
    @patch("auto_sdd.scripts.overnight_autonomous.emit_topo_order", return_value=[])
    @patch("auto_sdd.scripts.overnight_autonomous.check_circular_deps")
    @patch("shutil.which", return_value="/usr/bin/claude")
    def test_run_no_features(
        self,
        mock_which: MagicMock,
        mock_circ: MagicMock,
        mock_topo: MagicMock,
        mock_agent: MagicMock,
        mock_git: MagicMock,
        mock_lock: MagicMock,
        mock_release: MagicMock,
        tmp_path: Path,
    ) -> None:
        runner = _make_runner(tmp_path)
        # Agent for triage
        mock_agent.return_value = 0
        mock_git.return_value = MagicMock(returncode=0, stdout="abc123\n")

        runner.run()
        assert runner.built == 0
        assert runner.failed == 0

    @patch("auto_sdd.scripts.overnight_autonomous.release_lock")
    @patch("auto_sdd.scripts.overnight_autonomous.acquire_lock")
    @patch("shutil.which", return_value="/usr/bin/claude")
    def test_run_claudecode_guard(
        self,
        mock_which: MagicMock,
        mock_lock: MagicMock,
        mock_release: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("CLAUDECODE", "1")
        runner = _make_runner(tmp_path)
        with pytest.raises(AutoSddError, match="CLAUDECODE"):
            runner.run()

    @patch("auto_sdd.scripts.overnight_autonomous.release_lock")
    @patch("auto_sdd.scripts.overnight_autonomous.acquire_lock")
    @patch("shutil.which", return_value=None)
    def test_run_missing_claude_cli(
        self,
        mock_which: MagicMock,
        mock_lock: MagicMock,
        mock_release: MagicMock,
        tmp_path: Path,
    ) -> None:
        runner = _make_runner(tmp_path)
        with pytest.raises(AutoSddError, match="not found"):
            runner.run()


# ── Branch strategy tests ────────────────────────────────────────────────────


class TestBranchStrategy:
    """Tests for branch creation with different strategies."""

    @patch("auto_sdd.scripts.overnight_autonomous.generate_codebase_summary", return_value="mock summary")
    @patch("auto_sdd.scripts.overnight_autonomous._run_git")
    @patch("auto_sdd.scripts.overnight_autonomous.run_agent_with_backoff")
    def test_independent_branches_from_main(
        self,
        mock_agent: MagicMock,
        mock_git: MagicMock,
        mock_summary: MagicMock,
        tmp_path: Path,
    ) -> None:
        runner = _make_runner(tmp_path, branch_strategy="independent")
        runner.main_branch = "main"

        def agent_side_effect(
            output_file: Path, cmd: list[str], **kw: Any
        ) -> int:
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text("BUILD_FAILED: fail\n")
            return 1

        mock_agent.side_effect = agent_side_effect
        mock_git.return_value = MagicMock(returncode=0, stdout="abc123\n")

        result = runner._build_single_feature("1", "auth", 0, 1)
        assert result is False

        # Verify checkout main was called (independent always branches from main)
        checkout_main_calls = [
            c for c in mock_git.call_args_list
            if c[0][0] == ["checkout", "main"]
        ]
        assert len(checkout_main_calls) >= 1


# ── Cleanup tests ────────────────────────────────────────────────────────────


class TestCleanup:
    """Tests for OvernightRunner._cleanup."""

    @patch("auto_sdd.scripts.overnight_autonomous.release_lock")
    def test_cleanup_releases_lock(
        self, mock_release: MagicMock, tmp_path: Path
    ) -> None:
        runner = _make_runner(tmp_path)
        runner._cleanup()
        mock_release.assert_called_once_with(runner.lock_file)

    @patch("auto_sdd.scripts.overnight_autonomous.release_lock")
    def test_cleanup_stops_sidecar(
        self, mock_release: MagicMock, tmp_path: Path
    ) -> None:
        runner = _make_runner(tmp_path)
        with patch.object(runner, "_stop_eval_sidecar") as mock_stop:
            runner._cleanup()
        mock_stop.assert_called_once()


# ── Post-agent commit tests ──────────────────────────────────────────────────


class TestPostAgentCommit:
    """Tests for post-agent commit behavior."""

    @patch("auto_sdd.scripts.overnight_autonomous._run_git")
    def test_commits_uncommitted_changes(
        self, mock_git: MagicMock, tmp_path: Path
    ) -> None:
        runner = _make_runner(tmp_path)
        runner.main_branch = "main"

        call_log: list[list[str]] = []

        def git_side_effect(
            args: list[str], project_dir: Path, **kw: Any
        ) -> MagicMock:
            call_log.append(args)
            result = MagicMock(returncode=0)
            if args == ["status", "--porcelain"]:
                result.stdout = "M file.ts\n"
            else:
                result.stdout = ""
            return result

        mock_git.side_effect = git_side_effect

        build_result = "FEATURE_BUILT: auth\n"
        runner._post_build(
            "auto/feature-123", "auth", "1", build_result, 1000.0
        )

        # Should have called git add -A and git commit
        add_calls = [c for c in call_log if c == ["add", "-A"]]
        commit_calls = [c for c in call_log if c[0] == "commit"]
        assert len(add_calls) == 1
        assert len(commit_calls) == 1

    @patch("auto_sdd.scripts.overnight_autonomous._run_git")
    def test_no_changes_returns_false(
        self, mock_git: MagicMock, tmp_path: Path
    ) -> None:
        runner = _make_runner(tmp_path)
        runner.main_branch = "main"

        def git_side_effect(
            args: list[str], project_dir: Path, **kw: Any
        ) -> MagicMock:
            result = MagicMock(returncode=0)
            if args == ["status", "--porcelain"]:
                result.stdout = ""
            else:
                result.stdout = ""
            return result

        mock_git.side_effect = git_side_effect

        result = runner._post_build(
            "auto/feature-123", "auth", "1", "FEATURE_BUILT: auth\n", 1000.0
        )
        assert result is False


# ── Resume state persistence tests ───────────────────────────────────────────


class TestResumePersistence:
    """Tests for write_state being called during builds."""

    @patch("auto_sdd.scripts.overnight_autonomous._run_git")
    @patch("auto_sdd.scripts.overnight_autonomous.write_state")
    def test_write_state_called_on_success(
        self,
        mock_write: MagicMock,
        mock_git: MagicMock,
        tmp_path: Path,
    ) -> None:
        runner = _make_runner(tmp_path, enable_resume=True)
        runner.main_branch = "main"

        def git_side_effect(
            args: list[str], project_dir: Path, **kw: Any
        ) -> MagicMock:
            result = MagicMock(returncode=0)
            if args == ["status", "--porcelain"]:
                result.stdout = "M file.ts\n"
            else:
                result.stdout = ""
            return result

        mock_git.side_effect = git_side_effect

        runner._post_build(
            "auto/feature-123", "auth", "1",
            "FEATURE_BUILT: auth\n", 1000.0,
        )
        mock_write.assert_called_once()


# ── VectorStore wiring tests ─────────────────────────────────────────────


class TestVectorStoreWiring:
    """Tests for CIS VectorStore integration in OvernightRunner."""

    def test_init_creates_campaign_id(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)
        assert runner.campaign_id.startswith("campaign-")

    def test_init_creates_vector_store(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path)
        assert runner.vector_store is not None

    @patch("auto_sdd.scripts.overnight_autonomous.generate_codebase_summary", return_value="mock summary")
    @patch("auto_sdd.scripts.overnight_autonomous._run_git")
    @patch("auto_sdd.scripts.overnight_autonomous.run_agent_with_backoff")
    def test_vector_created_at_feature_start(
        self,
        mock_agent: MagicMock,
        mock_git: MagicMock,
        mock_summary: MagicMock,
        tmp_path: Path,
    ) -> None:
        runner = _make_runner(tmp_path)
        runner.main_branch = "main"

        def agent_side_effect(
            output_file: Path, cmd: list[str], **kw: Any
        ) -> int:
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text("BUILD_FAILED: test\n")
            return 1

        mock_agent.side_effect = agent_side_effect
        mock_git.return_value = MagicMock(returncode=0, stdout="abc123\n")

        with patch.object(runner.vector_store, "create_vector") as mock_create:
            mock_create.return_value = "test-vector-id"
            with patch.object(runner.vector_store, "update_section"):
                runner._build_single_feature("1", "auth", 0, 1)

        mock_create.assert_called_once()
        call_args = mock_create.call_args[0][0]
        assert call_args["feature_name"] == "auth"
        assert call_args["campaign_id"] == runner.campaign_id
