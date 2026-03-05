"""Tests for auto_sdd.lib.prompt_builder."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from auto_sdd.lib.drift import MistakeTracker
from auto_sdd.lib.prompt_builder import (
    BuildConfig,
    MAX_INJECTED_SECTION_LINES,
    MAX_TOTAL_PROMPT_LINES,
    _resolve_spec_file,
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

    @patch("auto_sdd.lib.prompt_builder.generate_codebase_summary")
    @patch("auto_sdd.lib.prompt_builder.read_latest_eval_feedback")
    def test_no_spec_first_or_generate_mapping(
        self,
        mock_feedback: MagicMock,
        mock_summary: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_summary.return_value = ""
        mock_feedback.return_value = ""
        config = BuildConfig(project_dir=tmp_path)
        prompt = build_feature_prompt(1, "Auth", tmp_path, config)

        assert "/spec-first" not in prompt
        assert "generate-mapping.sh" not in prompt

    @patch("auto_sdd.lib.prompt_builder.generate_codebase_summary")
    @patch("auto_sdd.lib.prompt_builder.read_latest_eval_feedback")
    def test_direct_implementation_instructions_with_spec(
        self,
        mock_feedback: MagicMock,
        mock_summary: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_summary.return_value = ""
        mock_feedback.return_value = ""
        features_dir = tmp_path / ".specs" / "features"
        features_dir.mkdir(parents=True)
        (features_dir / "auth.feature.md").write_text("Feature: Auth")
        config = BuildConfig(project_dir=tmp_path)
        prompt = build_feature_prompt(1, "Auth", tmp_path, config)

        assert ".specs/features/auth.feature.md" in prompt
        assert "Read the feature spec at" in prompt
        assert "CLAUDE.md" in prompt

    @patch("auto_sdd.lib.prompt_builder.generate_codebase_summary")
    @patch("auto_sdd.lib.prompt_builder.read_latest_eval_feedback")
    def test_direct_implementation_instructions_without_spec(
        self,
        mock_feedback: MagicMock,
        mock_summary: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_summary.return_value = ""
        mock_feedback.return_value = ""
        config = BuildConfig(project_dir=tmp_path)
        prompt = build_feature_prompt(1, "Auth", tmp_path, config)

        assert "Read the feature spec in .specs/features/" in prompt
        assert "CLAUDE.md" in prompt


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

    def test_uses_resolved_spec_file(self, tmp_path: Path) -> None:
        features_dir = tmp_path / ".specs" / "features"
        features_dir.mkdir(parents=True)
        spec = features_dir / "auth.feature.md"
        spec.write_text("Feature: Auth")
        config = BuildConfig(project_dir=tmp_path)
        prompt = build_retry_prompt(1, "Auth", tmp_path, config)
        assert "SPEC_FILE: .specs/features/auth.feature.md" in prompt
        assert "{path to the .feature.md file}" not in prompt

    def test_falls_back_to_placeholder_when_no_match(self, tmp_path: Path) -> None:
        features_dir = tmp_path / ".specs" / "features"
        features_dir.mkdir(parents=True)
        config = BuildConfig(project_dir=tmp_path)
        prompt = build_retry_prompt(1, "Auth", tmp_path, config)
        assert "SPEC_FILE: {path to the .feature.md file}" in prompt


# ── _resolve_spec_file ──────────────────────────────────────────────────────


class TestResolveSpecFile:
    def test_exact_match(self, tmp_path: Path) -> None:
        features_dir = tmp_path / ".specs" / "features"
        features_dir.mkdir(parents=True)
        spec = features_dir / "auth-login.feature.md"
        spec.write_text("Feature: Auth Login")
        result = _resolve_spec_file(tmp_path, "auth-login")
        assert result == ".specs/features/auth-login.feature.md"

    def test_case_insensitive_match(self, tmp_path: Path) -> None:
        features_dir = tmp_path / ".specs" / "features"
        features_dir.mkdir(parents=True)
        spec = features_dir / "auth-login.feature.md"
        spec.write_text("Feature: Auth Login")
        result = _resolve_spec_file(tmp_path, "Auth-Login")
        assert result == ".specs/features/auth-login.feature.md"

    def test_spaces_to_hyphens(self, tmp_path: Path) -> None:
        features_dir = tmp_path / ".specs" / "features"
        features_dir.mkdir(parents=True)
        spec = features_dir / "auth-login.feature.md"
        spec.write_text("Feature: Auth Login")
        result = _resolve_spec_file(tmp_path, "Auth Login")
        assert result == ".specs/features/auth-login.feature.md"

    def test_no_match_returns_none(self, tmp_path: Path) -> None:
        features_dir = tmp_path / ".specs" / "features"
        features_dir.mkdir(parents=True)
        (features_dir / "dashboard.feature.md").write_text("Feature: Dashboard")
        result = _resolve_spec_file(tmp_path, "Auth Login")
        assert result is None

    def test_multiple_matches_returns_none(self, tmp_path: Path) -> None:
        features_dir = tmp_path / ".specs" / "features"
        features_dir.mkdir(parents=True)
        (features_dir / "auth.feature.md").write_text("Feature: Auth")
        sub = features_dir / "subdir"
        sub.mkdir()
        (sub / "auth.feature.md").write_text("Feature: Auth v2")
        result = _resolve_spec_file(tmp_path, "auth")
        assert result is None

    def test_no_features_dir_returns_none(self, tmp_path: Path) -> None:
        result = _resolve_spec_file(tmp_path, "Auth")
        assert result is None

    def test_match_in_subdirectory(self, tmp_path: Path) -> None:
        features_dir = tmp_path / ".specs" / "features" / "auth"
        features_dir.mkdir(parents=True)
        spec = features_dir / "login.feature.md"
        spec.write_text("Feature: Login")
        result = _resolve_spec_file(tmp_path, "login")
        assert result == ".specs/features/auth/login.feature.md"

    def test_feature_prompt_uses_resolved_path(self, tmp_path: Path) -> None:
        features_dir = tmp_path / ".specs" / "features"
        features_dir.mkdir(parents=True)
        spec = features_dir / "auth-and-dashboard-shell.feature"
        spec.write_text("Feature: Auth and Dashboard Shell")
        config = BuildConfig(project_dir=tmp_path)
        with patch("auto_sdd.lib.prompt_builder.generate_codebase_summary", return_value=""), \
             patch("auto_sdd.lib.prompt_builder.read_latest_eval_feedback", return_value=""):
            prompt = build_feature_prompt(
                1, "auth-and-dashboard-shell", tmp_path, config,
            )
        assert "SPEC_FILE: .specs/features/auth-and-dashboard-shell.feature" in prompt
        assert "{path to the .feature.md file" not in prompt

    def test_feature_prompt_falls_back_to_placeholder(self, tmp_path: Path) -> None:
        features_dir = tmp_path / ".specs" / "features"
        features_dir.mkdir(parents=True)
        config = BuildConfig(project_dir=tmp_path)
        with patch("auto_sdd.lib.prompt_builder.generate_codebase_summary", return_value=""), \
             patch("auto_sdd.lib.prompt_builder.read_latest_eval_feedback", return_value=""):
            prompt = build_feature_prompt(1, "nonexistent", tmp_path, config)
        assert "SPEC_FILE: {path to the .feature.md file you created/updated}" in prompt


# ── Prompt size limits (L-00178) ─────────────────────────────────────────────


class TestPromptSizeLimits:
    """L-00178: if a single injected section or the total prompt exceeds
    size limits, the solution is probably in the wrong layer."""

    def _make_prompt(self, tmp_path: Path, **overrides: str) -> str:
        config = BuildConfig(project_dir=tmp_path)
        codebase = overrides.get("codebase_summary", "")
        eval_fb = overrides.get("eval_feedback", "")
        with patch(
            "auto_sdd.lib.prompt_builder.generate_codebase_summary",
            return_value=codebase,
        ), patch(
            "auto_sdd.lib.prompt_builder.read_latest_eval_feedback",
            return_value=eval_fb,
        ):
            return build_feature_prompt(1, "test-feature", tmp_path, config)

    def test_base_prompt_under_total_limit(self, tmp_path: Path) -> None:
        prompt = self._make_prompt(tmp_path)
        lines = prompt.split("\n")
        assert len(lines) <= MAX_TOTAL_PROMPT_LINES, (
            f"L-00178: base prompt is {len(lines)} lines "
            f"(limit {MAX_TOTAL_PROMPT_LINES})"
        )

    def test_bloated_section_caught(self, tmp_path: Path) -> None:
        """A 200-line injected section should exceed the per-section limit."""
        bloat = "\n".join(f"pattern {i}: don't do this" for i in range(200))
        prompt = self._make_prompt(tmp_path, codebase_summary=bloat)
        # Find the codebase summary section
        lines = prompt.split("\n")
        in_section = False
        section_lines = 0
        for line in lines:
            if line.startswith("## Codebase Summary"):
                in_section = True
                section_lines = 0
                continue
            if in_section and line.startswith("## "):
                break
            if in_section:
                section_lines += 1
        assert section_lines > MAX_INJECTED_SECTION_LINES, (
            "Test setup error: bloated section should exceed limit"
        )

    def test_warning_emitted_for_bloated_section(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """_warn_prompt_size fires a log warning for oversized sections."""
        import logging

        bloat = "\n".join(f"pattern {i}" for i in range(200))
        with caplog.at_level(logging.WARNING, logger="auto_sdd.lib.prompt_builder"):
            self._make_prompt(tmp_path, codebase_summary=bloat)
        assert "L-00178" in caplog.text

    def test_normal_sections_under_limit(self, tmp_path: Path) -> None:
        """With typical injections, no section exceeds the limit."""
        codebase = "\n".join(f"component {i}" for i in range(30))
        eval_fb = "\n".join(f"feedback {i}" for i in range(10))
        prompt = self._make_prompt(
            tmp_path, codebase_summary=codebase, eval_feedback=eval_fb
        )
        lines = prompt.split("\n")
        current_header: str | None = None
        section_start = 0
        for i, line in enumerate(lines):
            if line.startswith("## "):
                if current_header is not None:
                    section_len = i - section_start
                    assert section_len <= MAX_INJECTED_SECTION_LINES, (
                        f"L-00178: '{current_header}' is {section_len} lines"
                    )
                current_header = line
                section_start = i
        if current_header is not None:
            section_len = len(lines) - section_start
            assert section_len <= MAX_INJECTED_SECTION_LINES, (
                f"L-00178: '{current_header}' is {section_len} lines"
            )


# ── QA seed prompt injection ──────────────────────────────────────────────


class TestQaSeedPromptInjection:
    @patch("auto_sdd.lib.prompt_builder.generate_codebase_summary")
    @patch("auto_sdd.lib.prompt_builder.read_latest_eval_feedback")
    def test_first_feature_includes_qa_seed_instruction(
        self,
        mock_feedback: MagicMock,
        mock_summary: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_summary.return_value = ""
        mock_feedback.return_value = ""
        config = BuildConfig(project_dir=tmp_path)
        prompt = build_feature_prompt(1, "Auth", tmp_path, config)
        assert "qa-seed" in prompt
        assert "qa-test@test.local" in prompt
        assert "--teardown" in prompt

    @patch("auto_sdd.lib.prompt_builder.generate_codebase_summary")
    @patch("auto_sdd.lib.prompt_builder.read_latest_eval_feedback")
    def test_non_first_feature_excludes_qa_seed(
        self,
        mock_feedback: MagicMock,
        mock_summary: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_summary.return_value = ""
        mock_feedback.return_value = ""
        config = BuildConfig(project_dir=tmp_path)
        prompt = build_feature_prompt(2, "Dashboard", tmp_path, config)
        assert "qa-seed" not in prompt
        assert "qa-test@test.local" not in prompt

    @patch("auto_sdd.lib.prompt_builder.generate_codebase_summary")
    @patch("auto_sdd.lib.prompt_builder.read_latest_eval_feedback")
    def test_qa_seed_mentions_auth_detection(
        self,
        mock_feedback: MagicMock,
        mock_summary: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_summary.return_value = ""
        mock_feedback.return_value = ""
        config = BuildConfig(project_dir=tmp_path)
        prompt = build_feature_prompt(1, "Auth", tmp_path, config)
        assert "authentication" in prompt.lower() or "auth" in prompt.lower()
