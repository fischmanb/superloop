"""Tests for auto_sdd.scripts.build_loop — BuildLoop orchestration class.

Since this is orchestration code that calls many sub-modules, heavy mocking
is acceptable here (unlike lib modules where we prefer real files).
"""
from __future__ import annotations

import json
import os
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
    _format_duration,
    _is_credit_exhaustion,
    _parse_signal,
    _parse_token_usage,
    _validate_required_signals,
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
        "EVAL_SIDECAR", "CLAUDECODE",
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


class TestIsCreditExhaustion:
    """Tests for _is_credit_exhaustion."""

    def test_detects_credit_keyword(self) -> None:
        assert _is_credit_exhaustion("Error: insufficient_quota reached")

    def test_case_insensitive(self) -> None:
        assert _is_credit_exhaustion("CREDIT exhausted")

    def test_returns_false_for_normal_output(self) -> None:
        assert not _is_credit_exhaustion("FEATURE_BUILT: auth")


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
    @patch("auto_sdd.scripts.build_loop._get_head", side_effect=["abc123", "def456"])
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
