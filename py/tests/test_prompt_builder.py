"""Tests for auto_sdd.lib.prompt_builder."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from auto_sdd.lib.drift import MistakeTracker
from auto_sdd.lib.prompt_builder import (
    BuildConfig,
    build_feature_prompt,
    build_retry_prompt,
    show_preflight_summary,
)
from auto_sdd.lib.reliability import Feature


# ── show_preflight_summary ───────────────────────────────────────────────────


class TestShowPreflightSummary:
    def test_logs_features(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        features = [
            Feature(id=1, name="Auth", complexity="M"),
            Feature(id=2, name="Dashboard", complexity="L"),
        ]
        config = BuildConfig(project_dir=tmp_path)
        with caplog.at_level(logging.INFO):
            show_preflight_summary(features, "chained", 10, config)

        log_text = caplog.text
        assert "Auth" in log_text
        assert "Dashboard" in log_text
        assert "Total features: 2" in log_text

    def test_empty_features(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        config = BuildConfig(project_dir=tmp_path)
        with caplog.at_level(logging.INFO):
            show_preflight_summary([], "sequential", 5, config)

        assert "Total features: 0" in caplog.text


# ── build_feature_prompt ─────────────────────────────────────────────────────


class TestBuildFeaturePrompt:
    @patch("auto_sdd.lib.prompt_builder.generate_codebase_summary")
    @patch("auto_sdd.lib.prompt_builder.read_latest_eval_feedback")
    def test_contains_feature_info(
        self,
        mock_feedback: MagicMock,
        mock_summary: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_summary.return_value = ""
        mock_feedback.return_value = ""
        config = BuildConfig(project_dir=tmp_path)
        prompt = build_feature_prompt(1, "Auth Login", tmp_path, config)

        assert "Build feature #1: Auth Login" in prompt
        assert "FEATURE_BUILT: Auth Login" in prompt
        assert "SPEC_FILE:" in prompt
        assert "SOURCE_FILES:" in prompt
        assert "BUILD_FAILED:" in prompt

    @patch("auto_sdd.lib.prompt_builder.generate_codebase_summary")
    @patch("auto_sdd.lib.prompt_builder.read_latest_eval_feedback")
    def test_includes_codebase_summary(
        self,
        mock_feedback: MagicMock,
        mock_summary: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_summary.return_value = "## Component Registry\nApp.tsx"
        mock_feedback.return_value = ""
        config = BuildConfig(project_dir=tmp_path)
        prompt = build_feature_prompt(1, "Auth", tmp_path, config)

        assert "Codebase Summary" in prompt
        assert "Component Registry" in prompt

    @patch("auto_sdd.lib.prompt_builder.generate_codebase_summary")
    @patch("auto_sdd.lib.prompt_builder.read_latest_eval_feedback")
    def test_includes_eval_feedback(
        self,
        mock_feedback: MagicMock,
        mock_summary: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_summary.return_value = ""
        mock_feedback.return_value = "FRAMEWORK COMPLIANCE warning"
        config = BuildConfig(
            project_dir=tmp_path,
            eval_output_dir=tmp_path / "evals",
        )
        prompt = build_feature_prompt(1, "Auth", tmp_path, config)

        assert "Sidecar Eval Feedback" in prompt
        assert "FRAMEWORK COMPLIANCE" in prompt

    @patch("auto_sdd.lib.prompt_builder.generate_codebase_summary")
    @patch("auto_sdd.lib.prompt_builder.read_latest_eval_feedback")
    def test_includes_cumulative_mistakes(
        self,
        mock_feedback: MagicMock,
        mock_summary: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_summary.return_value = ""
        mock_feedback.return_value = ""
        tracker = MistakeTracker(mistakes=["missing error handling"])
        config = BuildConfig(project_dir=tmp_path)
        prompt = build_feature_prompt(
            1, "Auth", tmp_path, config, mistake_tracker=tracker
        )

        assert "Known Mistakes" in prompt
        assert "missing error handling" in prompt

    @patch("auto_sdd.lib.prompt_builder.generate_codebase_summary")
    @patch("auto_sdd.lib.prompt_builder.read_latest_eval_feedback")
    def test_no_optional_sections_when_empty(
        self,
        mock_feedback: MagicMock,
        mock_summary: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_summary.return_value = ""
        mock_feedback.return_value = ""
        config = BuildConfig(project_dir=tmp_path)
        prompt = build_feature_prompt(1, "Auth", tmp_path, config)

        assert "Codebase Summary" not in prompt
        assert "Sidecar Eval Feedback" not in prompt
        assert "Known Mistakes" not in prompt

    @patch("auto_sdd.lib.prompt_builder.generate_codebase_summary")
    def test_handles_summary_exception(
        self,
        mock_summary: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_summary.side_effect = ValueError("bad dir")
        config = BuildConfig(project_dir=tmp_path)
        # Should not raise
        prompt = build_feature_prompt(1, "Auth", tmp_path, config)
        assert "Build feature #1: Auth" in prompt

    @patch("auto_sdd.lib.prompt_builder.generate_codebase_summary")
    @patch("auto_sdd.lib.prompt_builder.read_latest_eval_feedback")
    def test_contains_implementation_rules(
        self,
        mock_feedback: MagicMock,
        mock_summary: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_summary.return_value = ""
        mock_feedback.return_value = ""
        config = BuildConfig(project_dir=tmp_path)
        prompt = build_feature_prompt(1, "Auth", tmp_path, config)

        assert "NO stub functions" in prompt
        assert "NO placeholder UI" in prompt
        assert "end-to-end" in prompt


# ── build_retry_prompt ───────────────────────────────────────────────────────


class TestBuildRetryPrompt:
    def test_contains_retry_info(self, tmp_path: Path) -> None:
        config = BuildConfig(project_dir=tmp_path, test_cmd="npm test")
        prompt = build_retry_prompt(1, "Auth", tmp_path, config)

        assert "previous build attempt FAILED" in prompt.lower() or "FAILED" in prompt
        assert "FEATURE_BUILT: Auth" in prompt
        assert "npm test" in prompt

    def test_includes_build_output(self, tmp_path: Path) -> None:
        config = BuildConfig(project_dir=tmp_path)
        prompt = build_retry_prompt(
            1, "Auth", tmp_path, config,
            build_output="error: TS2345 type mismatch",
        )

        assert "BUILD CHECK FAILURE OUTPUT" in prompt
        assert "TS2345" in prompt

    def test_includes_test_output(self, tmp_path: Path) -> None:
        config = BuildConfig(project_dir=tmp_path)
        prompt = build_retry_prompt(
            1, "Auth", tmp_path, config,
            test_output="FAILED test_login_flow",
        )

        assert "TEST SUITE FAILURE OUTPUT" in prompt
        assert "test_login_flow" in prompt

    def test_no_failure_context_when_empty(self, tmp_path: Path) -> None:
        config = BuildConfig(project_dir=tmp_path)
        prompt = build_retry_prompt(1, "Auth", tmp_path, config)

        assert "BUILD CHECK FAILURE OUTPUT" not in prompt
        assert "TEST SUITE FAILURE OUTPUT" not in prompt

    def test_contains_required_signal_reminder(
        self, tmp_path: Path
    ) -> None:
        config = BuildConfig(project_dir=tmp_path)
        prompt = build_retry_prompt(1, "Auth", tmp_path, config)

        assert "REQUIRED OUTPUT SIGNAL" in prompt
        assert "FEATURE_BUILT" in prompt

    def test_contains_seed_data_reminder(self, tmp_path: Path) -> None:
        config = BuildConfig(project_dir=tmp_path)
        prompt = build_retry_prompt(1, "Auth", tmp_path, config)
        assert "Seed data is fine" in prompt
