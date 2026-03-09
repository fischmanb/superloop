"""Tests for auto_sdd.scripts.build_loop — BuildLoop orchestration class.

Since this is orchestration code that calls many sub-modules, heavy mocking
is acceptable here (unlike lib modules where we prefer real files).
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from auto_sdd.lib.build_gates import BuildCheckResult
from auto_sdd.lib.drift import (
    DriftCheckResult,
    DriftTargets,
    MistakeTracker,
)
from auto_sdd.lib.prompt_builder import BuildConfig
from auto_sdd.lib.reliability import DriftPair, Feature, ResumeState
from auto_sdd.scripts.build_loop import (
    BuildLoop,
    FeatureRecord,
    _check_contamination,
    _check_repo_contamination,
    _detect_dep_excludes,
    _EXPECTED_WRITE_PATTERNS,
    _format_duration,
    _parse_signal,
    _parse_token_usage,
    _PROTECT_DIRS,
    _protect_repo_tree,
    _REPO_ROOT,
    _restore_repo_tree,
    _validate_required_signals,
    derive_component_types,
)


# ── Helper fixtures ──────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove env vars that could interfere with BuildLoop construction."""
    for var in [
        "PROJECT_DIR", "MAIN_BRANCH", "BASE_BRANCH", "BRANCH_STRATEGY",
        "MAX_FEATURES", "MAX_RETRIES", "MIN_RETRY_DELAY", "BUILD_MODE",
        "DRIFT_CHECK", "POST_BUILD_STEPS", "PARALLEL_VALIDATION",
        "ENABLE_RESUME", "AGENT_MODEL", "BUILD_MODEL", "RETRY_MODEL",
        "DRIFT_MODEL", "REVIEW_MODEL", "LOGS_DIR", "EVAL_OUTPUT_DIR",
        "COST_LOG_FILE", "BUILD_CHECK_CMD", "TEST_CHECK_CMD",
        "EVAL_SIDECAR", "CLAUDECODE", "ANALYSIS_INTERVAL",
        "ENABLE_PATTERN_ANALYSIS",
    ]:
        monkeypatch.delenv(var, raising=False)


def _make_loop(tmp_path: Path) -> BuildLoop:
    """Create a BuildLoop with mocked lock and minimal config."""
    os.environ["PROJECT_DIR"] = str(tmp_path)
    os.environ["MAIN_BRANCH"] = "main"
    os.environ["BUILD_CHECK_CMD"] = "skip"
    os.environ["TEST_CHECK_CMD"] = "skip"
    os.environ["ENABLE_RESUME"] = "false"
    os.environ["EVAL_SIDECAR"] = "false"
    os.environ["LOGS_DIR"] = str(tmp_path / "logs")

    # Create minimal project structure
    (tmp_path / ".specs").mkdir(exist_ok=True)
    (tmp_path / ".specs" / "roadmap.md").touch()

    with patch("auto_sdd.scripts.build_loop.acquire_lock"):
        with patch("auto_sdd.scripts.build_loop.release_lock"):
            loop = BuildLoop()
    return loop


# ── Helper function tests ────────────────────────────────────────────────────


class TestParseSignal:
    """Tests for _parse_signal."""

    def test_extracts_last_value(self) -> None:
        output = (
            "FEATURE_BUILT: first\n"
            "some other line\n"
            "FEATURE_BUILT: second\n"
        )
        assert _parse_signal("FEATURE_BUILT", output) == "second"

    def test_returns_empty_when_not_found(self) -> None:
        assert _parse_signal("MISSING", "no signals here") == ""

    def test_handles_colons_in_value(self) -> None:
        output = "SPEC_FILE: path/to/file:with:colons.md\n"
        assert _parse_signal("SPEC_FILE", output) == "path/to/file:with:colons.md"


class TestFormatDuration:
    """Tests for _format_duration."""

    def test_seconds_only(self) -> None:
        assert _format_duration(45) == "45s"

    def test_minutes_and_seconds(self) -> None:
        assert _format_duration(125) == "2m 5s"

    def test_hours_minutes_seconds(self) -> None:
        assert _format_duration(3661) == "1h 1m 1s"


class TestParseTokenUsage:
    """Tests for _parse_token_usage."""

    def test_json_style_tokens(self) -> None:
        output = '"input_tokens": 1000\n"output_tokens": 500\n'
        assert _parse_token_usage(output) == 1500

    def test_total_tokens_pattern(self) -> None:
        output = "Total tokens: 2500\n"
        assert _parse_token_usage(output) == 2500

    def test_returns_none_when_not_found(self) -> None:
        assert _parse_token_usage("no tokens here") is None


class TestCreditExhaustionError:
    """CreditExhaustionError is raised by claude_wrapper, not build_loop."""

    def test_is_importable(self) -> None:
        from auto_sdd.lib.claude_wrapper import CreditExhaustionError
        assert issubclass(CreditExhaustionError, Exception)

    def test_billing_regex_does_not_match_feature_names(self) -> None:
        from auto_sdd.lib.claude_wrapper import _BILLING_RE
        assert not _BILLING_RE.search("Tenant Credit Indicators")
        assert not _BILLING_RE.search("FEATURE_BUILT: Tenant Credit Indicators")

    def test_billing_regex_matches_api_errors(self) -> None:
        from auto_sdd.lib.claude_wrapper import _BILLING_RE
        assert _BILLING_RE.search("credit_balance_too_low")
        assert _BILLING_RE.search("insufficient_quota")
        assert _BILLING_RE.search("402 Payment Required")
        assert _BILLING_RE.search("Your API credits are exhausted")


class TestValidateRequiredSignals:
    """Tests for _validate_required_signals."""

    def test_returns_false_without_feature_built(self) -> None:
        assert not _validate_required_signals("just some output")

    def test_returns_false_without_spec_file(self) -> None:
        assert not _validate_required_signals("FEATURE_BUILT: auth\n")

    def test_returns_false_when_spec_file_missing_on_disk(
        self, tmp_path: Path
    ) -> None:
        output = (
            "FEATURE_BUILT: auth\n"
            "SPEC_FILE: /nonexistent/path.feature.md\n"
        )
        assert not _validate_required_signals(output)

    def test_returns_true_when_all_present(
        self, tmp_path: Path
    ) -> None:
        spec = tmp_path / "feature.feature.md"
        spec.write_text("# Feature\n")
        output = (
            f"FEATURE_BUILT: auth\n"
            f"SPEC_FILE: {spec}\n"
        )
        assert _validate_required_signals(output)


# ── BuildLoop construction tests ─────────────────────────────────────────────


class TestBuildLoopInit:
    """Tests for BuildLoop.__init__."""

    def test_reads_config_from_env(self, tmp_path: Path) -> None:
        os.environ["BRANCH_STRATEGY"] = "independent"
        os.environ["MAX_FEATURES"] = "10"
        loop = _make_loop(tmp_path)
        assert loop.branch_strategy == "independent"
        assert loop.max_features == 10
        assert loop.project_dir == tmp_path

    def test_default_values(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)
        assert loop.max_retries == 1
        assert loop.loop_built == 0
        assert loop.loop_failed == 0
        assert loop.built_feature_names == []
        assert loop.feature_records == []
        assert loop.eval_sidecar_pid is None

    def test_acquires_lock(self, tmp_path: Path) -> None:
        os.environ["PROJECT_DIR"] = str(tmp_path)
        os.environ["MAIN_BRANCH"] = "main"
        os.environ["BUILD_CHECK_CMD"] = "skip"
        os.environ["TEST_CHECK_CMD"] = "skip"
        os.environ["ENABLE_RESUME"] = "false"
        os.environ["EVAL_SIDECAR"] = "false"
        os.environ["LOGS_DIR"] = str(tmp_path / "logs")
        (tmp_path / ".specs").mkdir(exist_ok=True)
        (tmp_path / ".specs" / "roadmap.md").touch()

        with patch(
            "auto_sdd.scripts.build_loop.acquire_lock"
        ) as mock_lock:
            with patch("auto_sdd.scripts.build_loop.release_lock"):
                _loop = BuildLoop()
            mock_lock.assert_called_once()


# ── _record_build_result tests ───────────────────────────────────────────────


class TestRecordBuildResult:
    """Tests for BuildLoop._record_build_result."""

    def test_success_updates_all_tracking(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)
        loop._record_build_result(
            "auth", "built", "opus", 120, "auto/chained-123",
            build_output='"input_tokens": 100\n"output_tokens": 50\n',
        )
        assert loop.loop_built == 1
        assert loop.loop_failed == 0
        assert "auth" in loop.built_feature_names
        assert len(loop.feature_records) == 1
        assert loop.feature_records[0].status == "built"
        assert loop.feature_records[0].token_usage == 150
        assert len(loop.loop_timings) == 1
        assert "✓ auth" in loop.loop_timings[0]

    def test_failure_updates_tracking(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)
        loop._record_build_result(
            "auth", "failed", "opus", 60, "auto/chained-123",
        )
        assert loop.loop_built == 0
        assert loop.loop_failed == 1
        assert "auth" in loop.loop_skipped
        assert len(loop.feature_records) == 1
        assert loop.feature_records[0].status == "failed"

    def test_multiple_builds_accumulate(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)
        loop._record_build_result(
            "auth", "built", "opus", 100, "branch-1",
        )
        loop._record_build_result(
            "dashboard", "built", "sonnet", 200, "branch-2",
        )
        loop._record_build_result(
            "settings", "failed", "opus", 300, "branch-3",
        )
        assert loop.loop_built == 2
        assert loop.loop_failed == 1
        assert len(loop.feature_records) == 3
        assert len(loop.built_feature_names) == 2


# ── write_build_summary tests ────────────────────────────────────────────────


class TestWriteBuildSummary:
    """Tests for BuildLoop.write_build_summary."""

    def test_produces_valid_json(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)
        loop._record_build_result(
            "auth", "built", "opus", 120, "branch-1",
            source_files="src/auth.ts, src/login.ts",
        )
        loop._record_build_result(
            "dashboard", "failed", "sonnet", 60, "branch-2",
        )

        path = loop.write_build_summary(180)
        assert path.exists()

        data = json.loads(path.read_text())
        assert data["features_built"] == 1
        assert data["features_failed"] == 1
        assert data["total_time_seconds"] == 180
        assert len(data["features"]) == 2

    def test_summary_structure(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)
        loop._record_build_result(
            "auth", "built", "opus", 90, "branch-1",
            source_files="src/auth.ts",
            test_count=15,
        )

        path = loop.write_build_summary(90)
        data = json.loads(path.read_text())

        assert "timestamp" in data
        assert "branch_strategy" in data
        assert "model" in data

        feat = data["features"][0]
        assert feat["name"] == "auth"
        assert feat["status"] == "built"
        assert feat["model"] == "opus"
        assert feat["time_seconds"] == 90
        assert feat["source_files"] == ["src/auth.ts"]
        assert feat["test_count"] == 15


# ── run() integration tests (with heavy mocking) ────────────────────────────


class TestBuildLoopRun:
    """Tests for BuildLoop.run with mocked sub-modules."""

    def test_no_features_exits_cleanly(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)
        with patch(
            "auto_sdd.scripts.build_loop.emit_topo_order",
            return_value=[],
        ):
            with patch(
                "auto_sdd.scripts.build_loop.check_circular_deps"
            ):
                loop.run()
        assert loop.loop_built == 0

    @patch("auto_sdd.lib.prompt_builder.generate_codebase_summary", return_value="mock summary")
    @patch("auto_sdd.scripts.build_loop.run_claude")
    @patch("auto_sdd.scripts.build_loop.setup_branch_chained")
    @patch("auto_sdd.scripts.build_loop.cleanup_branch_chained")
    @patch("auto_sdd.scripts.build_loop.check_working_tree_clean", return_value=True)
    @patch("auto_sdd.scripts.build_loop.clean_working_tree")
    @patch("auto_sdd.scripts.build_loop.check_build")
    @patch("auto_sdd.scripts.build_loop.check_drift")
    @patch("auto_sdd.scripts.build_loop.extract_drift_targets")
    @patch("auto_sdd.scripts.build_loop._get_head", side_effect=["abc123", "def456"])
    def test_single_feature_success(
        self,
        mock_head: MagicMock,
        mock_extract: MagicMock,
        mock_drift: MagicMock,
        mock_build: MagicMock,
        mock_clean_wt: MagicMock,
        mock_wt_clean: MagicMock,
        mock_cleanup: MagicMock,
        mock_setup: MagicMock,
        mock_claude: MagicMock,
        mock_summary: MagicMock,
        tmp_path: Path,
    ) -> None:
        loop = _make_loop(tmp_path)

        mock_setup.return_value = MagicMock(
            branch_name="auto/chained-123", worktree_path=None
        )
        mock_cleanup.return_value = "auto/chained-123"

        mock_claude.return_value = MagicMock(
            output="FEATURE_BUILT: auth\nSPEC_FILE: spec.md\nSOURCE_FILES: src/auth.ts",
        )

        mock_build.return_value = BuildCheckResult(success=True, output="")
        mock_drift.return_value = DriftCheckResult(passed=True, summary="ok")
        mock_extract.return_value = DriftTargets(
            spec_file="spec.md", source_files="src/auth.ts"
        )

        features = [Feature(id=1, name="auth", complexity="M")]

        with patch(
            "auto_sdd.scripts.build_loop.emit_topo_order",
            return_value=features,
        ):
            with patch(
                "auto_sdd.scripts.build_loop.check_circular_deps"
            ):
                with patch(
                    "auto_sdd.scripts.build_loop.show_preflight_summary"
                ):
                    loop.run()

        assert loop.loop_built == 1
        assert "auth" in loop.built_feature_names
        mock_claude.assert_called_once()

    @patch("auto_sdd.scripts.build_loop.run_claude")
    @patch("auto_sdd.scripts.build_loop.setup_branch_chained")
    @patch("auto_sdd.scripts.build_loop.cleanup_branch_chained")
    @patch("auto_sdd.scripts.build_loop.check_working_tree_clean", return_value=True)
    @patch("auto_sdd.scripts.build_loop.clean_working_tree")
    @patch("auto_sdd.scripts.build_loop.check_build")
    @patch("auto_sdd.scripts.build_loop.check_drift")
    @patch("auto_sdd.scripts.build_loop.extract_drift_targets")
    @patch("auto_sdd.scripts.build_loop._get_head", side_effect=["abc123", "def456", "def456"])
    @patch("auto_sdd.scripts.build_loop.time")
    def test_retry_succeeds_on_second_attempt(
        self,
        mock_time: MagicMock,
        mock_head: MagicMock,
        mock_extract: MagicMock,
        mock_drift: MagicMock,
        mock_build: MagicMock,
        mock_clean_wt: MagicMock,
        mock_wt_clean: MagicMock,
        mock_cleanup: MagicMock,
        mock_setup: MagicMock,
        mock_claude: MagicMock,
        tmp_path: Path,
    ) -> None:
        loop = _make_loop(tmp_path)
        # Prevent real sleeps
        mock_time.time.return_value = 1000
        mock_time.sleep = MagicMock()

        mock_setup.return_value = MagicMock(
            branch_name="auto/chained-123", worktree_path=None
        )
        mock_cleanup.return_value = "auto/chained-123"

        # First attempt fails, second succeeds
        fail_result = MagicMock(output="BUILD_FAILED: compile error")
        success_result = MagicMock(
            output="FEATURE_BUILT: auth\nSPEC_FILE: spec.md\nSOURCE_FILES: src/auth.ts",
        )
        mock_claude.side_effect = [fail_result, success_result]

        mock_build.return_value = BuildCheckResult(success=True, output="")
        mock_drift.return_value = DriftCheckResult(passed=True, summary="ok")
        mock_extract.return_value = DriftTargets(
            spec_file="spec.md", source_files="src/auth.ts"
        )

        features = [Feature(id=1, name="auth", complexity="M")]

        with patch(
            "auto_sdd.scripts.build_loop.emit_topo_order",
            return_value=features,
        ):
            with patch(
                "auto_sdd.scripts.build_loop.check_circular_deps"
            ):
                with patch(
                    "auto_sdd.scripts.build_loop.show_preflight_summary"
                ):
                    with patch("subprocess.run"):
                        loop.run()

        assert loop.loop_built == 1
        assert mock_claude.call_count == 2


class TestResumeFromState:
    """Tests for resume functionality."""

    def test_skips_completed_features(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)
        # Pre-populate completed features (simulating resume)
        loop.built_feature_names = ["auth"]

        features = [
            Feature(id=1, name="auth", complexity="M"),
            Feature(id=2, name="dashboard", complexity="L"),
        ]

        with patch(
            "auto_sdd.lib.prompt_builder.generate_codebase_summary",
            return_value="mock summary",
        ):
            with patch(
                "auto_sdd.scripts.build_loop.run_claude"
            ) as mock_claude:
                mock_claude.return_value = MagicMock(
                    output="FEATURE_BUILT: dashboard\nSPEC_FILE: spec.md\nSOURCE_FILES: src/dash.ts",
                )
                with patch(
                    "auto_sdd.scripts.build_loop.setup_branch_chained"
                ) as mock_setup:
                    mock_setup.return_value = MagicMock(
                        branch_name="auto/chained-456",
                        worktree_path=None,
                    )
                    with patch(
                        "auto_sdd.scripts.build_loop.cleanup_branch_chained",
                        return_value="auto/chained-456",
                    ):
                        with patch(
                            "auto_sdd.scripts.build_loop.check_working_tree_clean",
                            return_value=True,
                        ):
                            with patch(
                                "auto_sdd.scripts.build_loop.clean_working_tree"
                            ):
                                with patch(
                                    "auto_sdd.scripts.build_loop.check_build",
                                    return_value=BuildCheckResult(
                                        success=True, output=""
                                    ),
                                ):
                                    with patch(
                                        "auto_sdd.scripts.build_loop.check_drift",
                                        return_value=DriftCheckResult(
                                            passed=True, summary="ok"
                                        ),
                                    ):
                                        with patch(
                                            "auto_sdd.scripts.build_loop.extract_drift_targets",
                                            return_value=DriftTargets(
                                                spec_file="spec.md",
                                                source_files="src/dash.ts",
                                            ),
                                        ):
                                            with patch(
                                                "auto_sdd.scripts.build_loop._get_head",
                                                side_effect=["abc123", "def456"],
                                            ):
                                                loop._run_build_loop(
                                                    "chained", features
                                            )

        # auth was skipped, only dashboard built
        assert loop.loop_built == 1
        assert "dashboard" in loop.built_feature_names
        mock_claude.assert_called_once()


class TestBothMode:
    """Tests for 'both' mode (chained then independent)."""

    def test_dispatches_both_passes(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)
        loop.branch_strategy = "both"

        with patch.object(
            loop, "_run_build_loop"
        ) as mock_chained:
            with patch.object(
                loop, "_run_independent_pass"
            ) as mock_indep:
                with patch.object(
                    loop, "write_build_summary",
                    return_value=tmp_path / "summary.json",
                ):
                    with patch.object(loop, "stop_eval_sidecar"):
                        with patch(
                            "auto_sdd.scripts.build_loop.cleanup_all_worktrees"
                        ):
                            with patch(
                                "auto_sdd.scripts.build_loop.cleanup_merged_branches"
                            ):
                                # Simulate chained pass building 1 feature
                                def set_built(
                                    strategy: str,
                                    features: list[Feature],
                                ) -> None:
                                    loop.loop_built = 1
                                    loop.built_feature_names = ["auth"]

                                mock_chained.side_effect = set_built

                                features = [
                                    Feature(
                                        id=1, name="auth", complexity="M"
                                    )
                                ]
                                loop._run_both_mode(features)

        mock_chained.assert_called_once()
        mock_indep.assert_called_once_with(["auth"])


# ── Post-build gates tests ───────────────────────────────────────────────────


class TestPostBuildGates:
    """Tests for _run_post_build_gates."""

    def test_skip_steps_not_in_config(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)
        loop.post_build_steps = ""  # No steps

        with patch(
            "auto_sdd.scripts.build_loop.check_working_tree_clean",
            return_value=True,
        ):
            with patch(
                "auto_sdd.scripts.build_loop.check_build",
                return_value=BuildCheckResult(success=True, output=""),
            ):
                result = loop._run_post_build_gates(
                    "FEATURE_BUILT: auth\n", "auth"
                )

        assert result is True

    def test_fails_on_dirty_tree(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)

        with patch(
            "auto_sdd.scripts.build_loop.check_working_tree_clean",
            return_value=False,
        ):
            result = loop._run_post_build_gates(
                "FEATURE_BUILT: auth\n", "auth"
            )

        assert result is False

    def test_fails_on_build_failure(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)

        with patch(
            "auto_sdd.scripts.build_loop.check_working_tree_clean",
            return_value=True,
        ):
            with patch(
                "auto_sdd.scripts.build_loop.check_build",
                return_value=BuildCheckResult(
                    success=False, output="error"
                ),
            ):
                result = loop._run_post_build_gates(
                    "FEATURE_BUILT: auth\n", "auth"
                )

        assert result is False

    def test_runs_configured_steps(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)
        loop.post_build_steps = "test,dead-code,lint"
        loop.drift_check = False

        with patch(
            "auto_sdd.scripts.build_loop.check_working_tree_clean",
            return_value=True,
        ):
            with patch(
                "auto_sdd.scripts.build_loop.check_build",
                return_value=BuildCheckResult(success=True, output=""),
            ):
                with patch(
                    "auto_sdd.scripts.build_loop.check_tests",
                    return_value=BuildCheckResult(
                        success=True, output="", test_count=10
                    ),
                ) as mock_tests:
                    with patch(
                        "auto_sdd.scripts.build_loop.check_dead_exports"
                    ) as mock_dead:
                        with patch(
                            "auto_sdd.scripts.build_loop.check_lint"
                        ) as mock_lint:
                            result = loop._run_post_build_gates(
                                "FEATURE_BUILT: auth\n", "auth"
                            )

        assert result is True
        mock_tests.assert_called_once()
        mock_dead.assert_called_once()
        mock_lint.assert_called_once()

    def test_fails_when_head_has_not_advanced(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)

        with patch(
            "auto_sdd.scripts.build_loop._get_head",
            return_value="same_commit_hash",
        ):
            result = loop._run_post_build_gates(
                "FEATURE_BUILT: auth\n",
                "auth",
                branch_start_commit="same_commit_hash",
            )

        assert result is False

    def test_passes_when_head_has_advanced(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)
        loop.post_build_steps = ""

        with patch(
            "auto_sdd.scripts.build_loop._get_head",
            return_value="new_commit_hash",
        ):
            with patch(
                "auto_sdd.scripts.build_loop.check_working_tree_clean",
                return_value=True,
            ):
                with patch(
                    "auto_sdd.scripts.build_loop.check_build",
                    return_value=BuildCheckResult(success=True, output=""),
                ):
                    result = loop._run_post_build_gates(
                        "FEATURE_BUILT: auth\n",
                        "auth",
                        branch_start_commit="old_commit_hash",
                    )

        assert result is True

    def test_skips_head_check_when_no_start_commit(self, tmp_path: Path) -> None:
        """When branch_start_commit is empty, HEAD check is skipped."""
        loop = _make_loop(tmp_path)
        loop.post_build_steps = ""

        with patch(
            "auto_sdd.scripts.build_loop.check_working_tree_clean",
            return_value=True,
        ):
            with patch(
                "auto_sdd.scripts.build_loop.check_build",
                return_value=BuildCheckResult(success=True, output=""),
            ):
                result = loop._run_post_build_gates(
                    "FEATURE_BUILT: auth\n", "auth"
                )

        assert result is True


# ── Sidecar lifecycle tests ──────────────────────────────────────────────────


class TestSidecarLifecycle:
    """Tests for eval sidecar start/stop."""

    def test_start_stores_pid(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)

        sidecar_script = tmp_path / "scripts" / "eval-sidecar.sh"
        sidecar_script.parent.mkdir(parents=True, exist_ok=True)
        sidecar_script.write_text("#!/bin/bash\nsleep 60\n")

        # Enable sidecar
        os.environ["EVAL_SIDECAR"] = "true"

        with patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.pid = 12345
            mock_popen.return_value = mock_proc
            loop.start_eval_sidecar()

        assert loop.eval_sidecar_pid == 12345

    def test_stop_sends_sigterm_after_timeout(
        self, tmp_path: Path
    ) -> None:
        loop = _make_loop(tmp_path)
        loop.eval_sidecar_pid = 99999

        with patch("os.kill") as mock_kill:
            # First kill(0) succeeds (still running), then always succeeds
            mock_kill.side_effect = None
            with patch(
                "auto_sdd.scripts.build_loop.time"
            ) as mock_time:
                mock_time.sleep = MagicMock()
                # Simulate sidecar never exiting — kill(0) always works
                # We need os.kill to succeed for signal 0 checks
                # but eventually hit timeout
                call_count = [0]

                def kill_side_effect(pid: int, sig: int) -> None:
                    call_count[0] += 1

                mock_kill.side_effect = kill_side_effect

                # Patch time.time to prevent infinite wait
                loop.stop_eval_sidecar()

        # Should have tried to kill the sidecar
        assert mock_kill.called
        assert loop.eval_sidecar_pid is None

    def test_python_module_fallback_when_no_bash_script(
        self, tmp_path: Path
    ) -> None:
        loop = _make_loop(tmp_path)

        # Do NOT create scripts/eval-sidecar.sh — trigger fallback
        os.environ["EVAL_SIDECAR"] = "true"

        with patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.pid = 54321
            mock_popen.return_value = mock_proc
            loop.start_eval_sidecar()

        assert loop.eval_sidecar_pid == 54321
        # Verify the fallback command uses Python module, not bash
        call_args = mock_popen.call_args[0][0]
        assert "-m" in call_args
        assert "auto_sdd.scripts.eval_sidecar" in call_args

    def test_stop_noop_when_no_pid(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)
        loop.eval_sidecar_pid = None
        loop.stop_eval_sidecar()  # Should not raise


# ── Cleanup tests ────────────────────────────────────────────────────────────


class TestCleanup:
    """Tests for lock and cleanup behavior."""

    def test_cleanup_releases_lock(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)

        with patch(
            "auto_sdd.scripts.build_loop.release_lock"
        ) as mock_release:
            loop._cleanup()

        mock_release.assert_called_once_with(loop.lock_file)

    def test_cleanup_stops_sidecar(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)

        with patch.object(
            loop, "stop_eval_sidecar"
        ) as mock_stop:
            with patch("auto_sdd.scripts.build_loop.release_lock"):
                loop._cleanup()

        mock_stop.assert_called_once()


# ── FeatureRecord dataclass tests ────────────────────────────────────────────


class TestFeatureRecord:
    """Tests for FeatureRecord dataclass."""

    def test_creation(self) -> None:
        record = FeatureRecord(
            name="auth",
            status="built",
            model="opus",
            duration_seconds=120,
            source_files="src/auth.ts",
            test_count=10,
            token_usage=1500,
        )
        assert record.name == "auth"
        assert record.status == "built"
        assert record.model == "opus"
        assert record.duration_seconds == 120

    def test_defaults(self) -> None:
        record = FeatureRecord(
            name="auth",
            status="built",
            model="opus",
            duration_seconds=60,
        )
        assert record.source_files == ""
        assert record.test_count is None
        assert record.token_usage is None


# ── _detect_dep_excludes tests ────────────────────────────────────────────


class TestDetectDepExcludes:
    """Tests for _detect_dep_excludes."""

    def test_detect_dep_excludes_empty_dir(self, tmp_path: Path) -> None:
        result = _detect_dep_excludes(tmp_path)
        assert result == []

    def test_detect_dep_excludes_node_modules(self, tmp_path: Path) -> None:
        (tmp_path / "node_modules").mkdir()
        result = _detect_dep_excludes(tmp_path)
        assert result == ["-e", "node_modules"]

    def test_detect_dep_excludes_multiple(self, tmp_path: Path) -> None:
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "venv").mkdir()
        (tmp_path / "target").mkdir()
        result = _detect_dep_excludes(tmp_path)
        assert ["-e", "node_modules"] == result[0:2]
        assert ["-e", "venv"] == result[2:4]
        assert ["-e", "target"] == result[4:6]

    def test_detect_dep_excludes_python_venvs(self, tmp_path: Path) -> None:
        (tmp_path / ".venv").mkdir()
        result = _detect_dep_excludes(tmp_path)
        assert result == ["-e", ".venv"]

    def test_detect_dep_excludes_vendor(self, tmp_path: Path) -> None:
        (tmp_path / "vendor").mkdir()
        result = _detect_dep_excludes(tmp_path)
        assert result == ["-e", "vendor"]

    def test_detect_dep_excludes_ignores_files(self, tmp_path: Path) -> None:
        """Files named like dep dirs should be ignored (only dirs count)."""
        (tmp_path / "node_modules").write_text("not a dir")
        result = _detect_dep_excludes(tmp_path)
        assert result == []


# ── Independent pass prompt builder tests ─────────────────────────────────


class TestIndependentPassUsesPromptBuilder:
    """Fix 1: _run_independent_pass should use build_feature_prompt."""

    @patch("auto_sdd.scripts.build_loop.run_claude")
    @patch("auto_sdd.scripts.build_loop.build_feature_prompt")
    @patch("subprocess.run")
    def test_independent_pass_calls_build_feature_prompt(
        self,
        mock_subprocess: MagicMock,
        mock_prompt: MagicMock,
        mock_claude: MagicMock,
        tmp_path: Path,
    ) -> None:
        loop = _make_loop(tmp_path)
        mock_prompt.return_value = ("generated prompt", [])

        # Mock subprocess.run for worktree creation/cleanup
        mock_subprocess.return_value = MagicMock(returncode=0, stdout="", stderr="")

        mock_claude.return_value = MagicMock(output="BUILD_FAILED: test")

        with patch.object(loop, "_run_post_build_gates", return_value=False):
            loop._run_independent_pass(["auth"])

        mock_prompt.assert_called_once()
        call_kwargs = mock_prompt.call_args
        assert call_kwargs[0][0] == 0  # feature_id
        assert call_kwargs[0][1] == "auth"  # feature_name


# ── Independent pass post-build gates tests ───────────────────────────────


class TestIndependentPassRunsPostBuildGates:
    """Fix 4: _run_independent_pass should run _run_post_build_gates."""

    @patch("auto_sdd.scripts.build_loop.run_claude")
    @patch("auto_sdd.scripts.build_loop.build_feature_prompt", return_value=("prompt", []))
    @patch("subprocess.run")
    def test_independent_pass_calls_post_build_gates_on_success(
        self,
        mock_subprocess: MagicMock,
        mock_prompt: MagicMock,
        mock_claude: MagicMock,
        tmp_path: Path,
    ) -> None:
        loop = _make_loop(tmp_path)
        mock_subprocess.return_value = MagicMock(returncode=0, stdout="", stderr="")

        mock_claude.return_value = MagicMock(
            output="FEATURE_BUILT: auth\nSPEC_FILE: spec.md\n"
        )

        with patch.object(
            loop, "_run_post_build_gates", return_value=True
        ) as mock_gates:
            loop._run_independent_pass(["auth"])

        mock_gates.assert_called_once()
        # Verify project_dir kwarg is the worktree path (not self.project_dir)
        call_kwargs = mock_gates.call_args
        assert call_kwargs[1].get("project_dir") is not None
        assert ".build-worktrees" in str(call_kwargs[1]["project_dir"])

    @patch("auto_sdd.scripts.build_loop.run_claude")
    @patch("auto_sdd.scripts.build_loop.build_feature_prompt", return_value=("prompt", []))
    @patch("subprocess.run")
    def test_independent_pass_fails_when_gates_fail(
        self,
        mock_subprocess: MagicMock,
        mock_prompt: MagicMock,
        mock_claude: MagicMock,
        tmp_path: Path,
    ) -> None:
        loop = _make_loop(tmp_path)
        mock_subprocess.return_value = MagicMock(returncode=0, stdout="", stderr="")

        mock_claude.return_value = MagicMock(
            output="FEATURE_BUILT: auth\nSPEC_FILE: spec.md\n"
        )

        with patch.object(loop, "_run_post_build_gates", return_value=False):
            loop._run_independent_pass(["auth"])

        assert loop.loop_failed == 1
        assert loop.loop_built == 0


# ── Post-build gates project_dir override tests ──────────────────────────


class TestPostBuildGatesProjectDirOverride:
    """Tests for _run_post_build_gates with project_dir kwarg."""

    def test_uses_override_project_dir(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)
        loop.post_build_steps = ""
        override_dir = tmp_path / "worktree"
        override_dir.mkdir()

        with patch(
            "auto_sdd.scripts.build_loop._get_head",
            return_value="new_hash",
        ):
            with patch(
                "auto_sdd.scripts.build_loop.check_working_tree_clean",
                return_value=True,
            ) as mock_wt:
                with patch(
                    "auto_sdd.scripts.build_loop.check_build",
                    return_value=BuildCheckResult(success=True, output=""),
                ) as mock_build:
                    result = loop._run_post_build_gates(
                        "FEATURE_BUILT: auth\n",
                        "auth",
                        branch_start_commit="old_hash",
                        project_dir=override_dir,
                    )

        assert result is True
        # Verify the override dir was passed to the gate functions
        mock_wt.assert_called_once_with(override_dir)
        mock_build.assert_called_once_with(loop.build_cmd, override_dir)

    def test_defaults_to_self_project_dir(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)
        loop.post_build_steps = ""

        with patch(
            "auto_sdd.scripts.build_loop.check_working_tree_clean",
            return_value=True,
        ) as mock_wt:
            with patch(
                "auto_sdd.scripts.build_loop.check_build",
                return_value=BuildCheckResult(success=True, output=""),
            ):
                loop._run_post_build_gates(
                    "FEATURE_BUILT: auth\n", "auth"
                )

        mock_wt.assert_called_once_with(tmp_path)


# ── VectorStore wiring tests ─────────────────────────────────────────────


class TestVectorStoreWiring:
    """Tests for CIS VectorStore integration in BuildLoop."""

    def test_init_creates_campaign_id(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)
        assert loop.campaign_id.startswith("campaign-")
        assert loop.vector_store is not None

    def test_init_creates_vector_store(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)
        assert loop.vector_store is not None

    def test_record_build_result_updates_vector(
        self, tmp_path: Path
    ) -> None:
        loop = _make_loop(tmp_path)
        # Create a vector first
        vid = loop.vector_store.create_vector({
            "feature_id": 1,
            "feature_name": "auth",
            "campaign_id": loop.campaign_id,
            "build_order_position": 0,
            "timestamp": "2026-03-06T00:00:00Z",
        })
        with patch(
            "auto_sdd.scripts.build_loop.derive_component_types",
            return_value=(["client", "test"], ["src/components/App.tsx", "src/auth.test.ts"]),
        ):
            loop._record_build_result(
                "auth", "built", "opus", 120, "auto/chained-123",
                vector_id=vid,
                injections_received=["codebase_summary"],
                retry_count=0,
            )
        vec = loop.vector_store.get_vector(vid)
        assert vec is not None
        signals = vec.sections.get("build_signals_v1", {})
        assert signals["build_success"] is True
        assert signals["agent_model"] == "opus"
        assert signals["injections_received"] == ["codebase_summary"]
        assert signals["component_types"] == ["client", "test"]

    def test_record_build_result_no_vector_id_skips(
        self, tmp_path: Path
    ) -> None:
        """When vector_id is empty, no vector store update happens."""
        loop = _make_loop(tmp_path)
        # Should not raise even with empty vector_id
        loop._record_build_result(
            "auth", "built", "opus", 120, "auto/chained-123",
            vector_id="",
        )

    def test_vector_store_error_does_not_abort(
        self, tmp_path: Path
    ) -> None:
        loop = _make_loop(tmp_path)
        with patch.object(
            loop.vector_store, "update_section",
            side_effect=RuntimeError("store failure"),
        ):
            # Should not raise
            loop._record_build_result(
                "auth", "built", "opus", 120, "auto/chained-123",
                vector_id="nonexistent-id",
            )
        # Build still recorded
        assert loop.loop_built == 1


# ── derive_component_types tests ─────────────────────────────────────────


class TestDeriveComponentTypes:
    """Tests for derive_component_types."""

    @patch("subprocess.run")
    def test_categorizes_client_files(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="src/components/Button.tsx\nclient/App.tsx\n",
        )
        comp_types, files = derive_component_types(tmp_path)
        assert "client" in comp_types

    @patch("subprocess.run")
    def test_categorizes_server_files(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="server/api.ts\nsrc/api/handler.ts\nsrc/routes/index.ts\n",
        )
        comp_types, _files = derive_component_types(tmp_path)
        assert "server" in comp_types

    @patch("subprocess.run")
    def test_categorizes_database_files(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="src/db/schema.ts\nlib/models/user.ts\n",
        )
        comp_types, _files = derive_component_types(tmp_path)
        assert "database" in comp_types

    @patch("subprocess.run")
    def test_categorizes_test_files(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="src/auth.test.ts\ntests/login.spec.ts\n",
        )
        comp_types, _files = derive_component_types(tmp_path)
        assert "test" in comp_types

    @patch("subprocess.run")
    def test_categorizes_style_files(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="src/styles/main.css\ntheme.scss\n",
        )
        comp_types, _files = derive_component_types(tmp_path)
        assert "style" in comp_types

    @patch("subprocess.run")
    def test_categorizes_other_files(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="README.md\npackage.json\n",
        )
        comp_types, _files = derive_component_types(tmp_path)
        assert "other" in comp_types

    @patch("subprocess.run")
    def test_deduplicates(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="client/a.tsx\nclient/b.tsx\n",
        )
        comp_types, _files = derive_component_types(tmp_path)
        assert comp_types.count("client") == 1

    @patch("subprocess.run")
    def test_returns_empty_on_failure(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        result = derive_component_types(tmp_path)
        assert result == ([], [])

    @patch("subprocess.run")
    def test_mixed_types(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=(
                "client/App.tsx\n"
                "server/api.ts\n"
                "src/db/schema.ts\n"
                "src/auth.test.ts\n"
                "styles.css\n"
                "README.md\n"
            ),
        )
        result = derive_component_types(tmp_path)
        comp_types, files = result
        assert sorted(comp_types) == ["client", "database", "other", "server", "style", "test"]
        assert "client/App.tsx" in files
        assert "server/api.ts" in files

    @patch("subprocess.run")
    def test_returns_tuple(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        """derive_component_types returns (component_types, files_touched) tuple."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="src/components/Button.tsx\nserver/api.ts\n",
        )
        result = derive_component_types(tmp_path)
        assert isinstance(result, tuple)
        assert len(result) == 2
        comp_types, files = result
        assert isinstance(comp_types, list)
        assert isinstance(files, list)
        assert "client" in comp_types
        assert "server" in comp_types
        assert files == ["src/components/Button.tsx", "server/api.ts"]

    @patch("subprocess.run")
    def test_returns_empty_tuple_on_failure(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        result = derive_component_types(tmp_path)
        assert result == ([], [])

    @patch("subprocess.run")
    def test_files_touched_in_build_signals(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        """files_touched is stored in build_signals_v1."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="src/components/Button.tsx\n",
        )
        comp_types, files = derive_component_types(tmp_path)
        assert files == ["src/components/Button.tsx"]


# ── CIS Round 2: Pattern analysis wiring ────────────────────────────────────


class TestPatternAnalysisWiring:
    """Test that BuildLoop runs pattern analysis at the configured interval."""

    def test_analysis_runs_after_n_features(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)
        loop.analysis_interval = 2
        loop._current_strategy = "chained"
        loop._loop_limit = 10

        # Record 2 results to trigger analysis at interval 2
        with patch("auto_sdd.scripts.build_loop.run_analysis", return_value=[]) as mock_analysis, \
             patch("auto_sdd.scripts.build_loop.derive_component_types", return_value=([], [])), \
             patch("auto_sdd.scripts.build_loop.read_latest_eval_feedback", return_value=""), \
             patch("auto_sdd.scripts.build_loop.update_repeated_mistakes"):
            loop._record_build_result(
                "feat-1", "built", "model-x", 60, "branch-1",
            )
            # After 1 feature (built=1, failed=0), total=1, not multiple of 2
            mock_analysis.assert_not_called()

            loop._record_build_result(
                "feat-2", "built", "model-x", 90, "branch-1",
            )
            # After 2 features, total=2, triggers analysis
            mock_analysis.assert_called_once()

    def test_risk_context_written(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)
        loop.analysis_interval = 1
        loop._current_strategy = "chained"
        loop._loop_limit = 10

        fake_finding_list = [MagicMock()]
        with patch("auto_sdd.scripts.build_loop.run_analysis", return_value=fake_finding_list), \
             patch("auto_sdd.scripts.build_loop.generate_risk_context", return_value="## Risk Context\nTest") as mock_ctx, \
             patch("auto_sdd.scripts.build_loop.derive_component_types", return_value=([], [])), \
             patch("auto_sdd.scripts.build_loop.read_latest_eval_feedback", return_value=""), \
             patch("auto_sdd.scripts.build_loop.update_repeated_mistakes"):
            loop._record_build_result(
                "feat-1", "built", "model-x", 60, "branch-1",
            )

        risk_path = loop.eval_output_dir / "risk-context.md"
        assert risk_path.exists()
        content = risk_path.read_text()
        assert "Risk Context" in content

    def test_analysis_failure_does_not_abort(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)
        loop.analysis_interval = 1
        loop._current_strategy = "chained"
        loop._loop_limit = 10

        with patch("auto_sdd.scripts.build_loop.run_analysis", side_effect=RuntimeError("boom")), \
             patch("auto_sdd.scripts.build_loop.derive_component_types", return_value=([], [])), \
             patch("auto_sdd.scripts.build_loop.read_latest_eval_feedback", return_value=""), \
             patch("auto_sdd.scripts.build_loop.update_repeated_mistakes"):
            # Should not raise
            loop._record_build_result(
                "feat-1", "built", "model-x", 60, "branch-1",
            )
        # Loop state should be intact
        assert loop.loop_built == 1


# ── _check_contamination ────────────────────────────────────────────────────


class TestCheckContamination:
    """Tests for the post-agent contamination audit."""

    def test_empty_start_commit_returns_empty(self, tmp_path: Path) -> None:
        assert _check_contamination(tmp_path, "") == []

    @patch("auto_sdd.scripts.build_loop.subprocess.run")
    def test_no_contamination_for_in_project_files(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.return_value = MagicMock(
            returncode=0, stdout="src/app.ts\npackage.json\n"
        )
        result = _check_contamination(tmp_path, "abc123")
        assert result == []

    @patch("auto_sdd.scripts.build_loop.subprocess.run")
    def test_detects_path_traversal(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.return_value = MagicMock(
            returncode=0, stdout="src/app.ts\n../../etc/passwd\n"
        )
        result = _check_contamination(tmp_path, "abc123")
        assert len(result) == 1
        assert "../../etc/passwd" in result

    @patch("auto_sdd.scripts.build_loop.subprocess.run")
    def test_returns_empty_on_git_failure(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.return_value = MagicMock(returncode=128, stdout="")
        result = _check_contamination(tmp_path, "abc123")
        assert result == []

    @patch("auto_sdd.scripts.build_loop.subprocess.run")
    def test_returns_empty_on_timeout(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=30)
        result = _check_contamination(tmp_path, "abc123")
        assert result == []

    @patch("auto_sdd.scripts.build_loop.subprocess.run")
    def test_empty_diff_output(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        result = _check_contamination(tmp_path, "abc123")
        assert result == []


# ── _check_repo_contamination tests ──────────────────────────────────────────


class TestCheckRepoContamination:
    """Tests for _check_repo_contamination (auto-sdd working tree audit)."""

    @patch("auto_sdd.scripts.build_loop.subprocess.run")
    def test_clean_status_returns_empty(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        result = _check_repo_contamination(Path("/fake/repo"), _EXPECTED_WRITE_PATTERNS)
        assert result == []

    @patch("auto_sdd.scripts.build_loop.subprocess.run")
    def test_allowlisted_paths_return_empty(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=" M logs/foo/bar.json\n M learnings/pending.md\n M general-estimates.jsonl\n",
        )
        result = _check_repo_contamination(Path("/fake/repo"), _EXPECTED_WRITE_PATTERNS)
        assert result == []

    @patch("auto_sdd.scripts.build_loop.subprocess.run")
    def test_unexpected_path_detected(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=" M py/auto_sdd/lib/foo.py\n",
        )
        result = _check_repo_contamination(Path("/fake/repo"), _EXPECTED_WRITE_PATTERNS)
        assert result == ["py/auto_sdd/lib/foo.py"]

    @patch("auto_sdd.scripts.build_loop.subprocess.run")
    def test_untracked_files_ignored(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="?? some-new-file.txt\n?? another/untracked.py\n",
        )
        result = _check_repo_contamination(Path("/fake/repo"), _EXPECTED_WRITE_PATTERNS)
        assert result == []

    @patch("auto_sdd.scripts.build_loop.subprocess.run")
    def test_mixed_allowlisted_and_contaminated(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=" M logs/build.json\n M py/auto_sdd/scripts/build_loop.py\n M learnings/pending.md\n",
        )
        result = _check_repo_contamination(Path("/fake/repo"), _EXPECTED_WRITE_PATTERNS)
        assert result == ["py/auto_sdd/scripts/build_loop.py"]


# ── _protect_repo_tree / _restore_repo_tree tests ────────────────────────────


class TestProtectRestoreRepoTree:
    """Tests for chmod-based write protection functions."""

    @patch("auto_sdd.scripts.build_loop.subprocess.run")
    def test_protect_calls_chmod_remove_write(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        # Create the directories that _protect_repo_tree checks for
        for d in _PROTECT_DIRS:
            (tmp_path / d).mkdir(parents=True, exist_ok=True)

        result = _protect_repo_tree(tmp_path)
        assert result is True

        # Verify chmod -R a-w was called for each directory
        calls = mock_run.call_args_list
        assert len(calls) == len(_PROTECT_DIRS)
        for call, d in zip(calls, _PROTECT_DIRS):
            args = call[0][0]
            assert args[0] == "chmod"
            assert args[1] == "-R"
            assert args[2] == "a-w"
            assert args[3] == str(tmp_path / d)

    @patch("auto_sdd.scripts.build_loop.subprocess.run")
    def test_restore_calls_chmod_add_write(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        for d in _PROTECT_DIRS:
            (tmp_path / d).mkdir(parents=True, exist_ok=True)

        _restore_repo_tree(tmp_path)

        calls = mock_run.call_args_list
        assert len(calls) == len(_PROTECT_DIRS)
        for call, d in zip(calls, _PROTECT_DIRS):
            args = call[0][0]
            assert args[0] == "chmod"
            assert args[1] == "-R"
            assert args[2] == "u+w"
            assert args[3] == str(tmp_path / d)

    @patch("auto_sdd.scripts.build_loop.subprocess.run")
    def test_protect_returns_false_on_exception(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        (tmp_path / "py").mkdir()
        mock_run.side_effect = OSError("permission denied")
        result = _protect_repo_tree(tmp_path)
        assert result is False
