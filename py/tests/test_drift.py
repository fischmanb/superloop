"""Tests for auto_sdd.lib.drift."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from auto_sdd.lib.drift import (
    CodeReviewResult,
    DriftCheckResult,
    DriftTargets,
    MistakeTracker,
    _parse_signal,
    check_drift,
    extract_drift_targets,
    get_cumulative_mistakes,
    read_latest_eval_feedback,
    run_code_review,
    update_repeated_mistakes,
)


# ── _parse_signal ────────────────────────────────────────────────────────────


class TestParseSignal:
    def test_extracts_signal(self) -> None:
        output = "some text\nSPEC_FILE: path/to/spec.md\nmore text"
        assert _parse_signal("SPEC_FILE", output) == "path/to/spec.md"

    def test_returns_last_match(self) -> None:
        output = "FEATURE_BUILT: foo\nFEATURE_BUILT: bar"
        assert _parse_signal("FEATURE_BUILT", output) == "bar"

    def test_returns_empty_for_missing(self) -> None:
        assert _parse_signal("MISSING", "no signals here") == ""

    def test_strips_whitespace(self) -> None:
        output = "SPEC_FILE:   path/to/spec.md   "
        assert _parse_signal("SPEC_FILE", output) == "path/to/spec.md"


# ── read_latest_eval_feedback ────────────────────────────────────────────────


class TestReadLatestEvalFeedback:
    def test_returns_empty_for_missing_dir(self, tmp_path: Path) -> None:
        assert read_latest_eval_feedback(tmp_path / "nonexistent") == ""

    def test_returns_empty_for_no_eval_files(self, tmp_path: Path) -> None:
        assert read_latest_eval_feedback(tmp_path) == ""

    def test_returns_empty_for_passing_eval(self, tmp_path: Path) -> None:
        eval_data = {
            "agent_eval": {
                "framework_compliance": "pass",
                "scope_assessment": "focused",
                "integration_quality": "clean",
                "repeated_mistakes": "none",
                "eval_notes": "",
            }
        }
        (tmp_path / "eval-feature.json").write_text(json.dumps(eval_data))
        assert read_latest_eval_feedback(tmp_path) == ""

    def test_returns_feedback_for_warn(self, tmp_path: Path) -> None:
        eval_data = {
            "agent_eval": {
                "framework_compliance": "warn",
                "scope_assessment": "focused",
                "integration_quality": "clean",
                "repeated_mistakes": "none",
                "eval_notes": "",
            }
        }
        (tmp_path / "eval-feature.json").write_text(json.dumps(eval_data))
        result = read_latest_eval_feedback(tmp_path)
        assert "FRAMEWORK COMPLIANCE" in result

    def test_returns_feedback_for_scope_creep(self, tmp_path: Path) -> None:
        eval_data = {
            "agent_eval": {
                "framework_compliance": "pass",
                "scope_assessment": "sprawling",
                "integration_quality": "clean",
                "repeated_mistakes": "none",
                "eval_notes": "",
            }
        }
        (tmp_path / "eval-feature.json").write_text(json.dumps(eval_data))
        result = read_latest_eval_feedback(tmp_path)
        assert "SCOPE CREEP" in result

    def test_returns_feedback_for_repeated_mistake(
        self, tmp_path: Path
    ) -> None:
        eval_data = {
            "agent_eval": {
                "framework_compliance": "pass",
                "scope_assessment": "focused",
                "integration_quality": "clean",
                "repeated_mistakes": "missing error handling",
                "eval_notes": "",
            }
        }
        (tmp_path / "eval-feature.json").write_text(json.dumps(eval_data))
        result = read_latest_eval_feedback(tmp_path)
        assert "REPEATED MISTAKE" in result

    def test_excludes_campaign_files(self, tmp_path: Path) -> None:
        # Campaign files should be excluded
        campaign_data = {
            "agent_eval": {
                "framework_compliance": "fail",
                "scope_assessment": "sprawling",
                "integration_quality": "major_issues",
                "repeated_mistakes": "everything",
                "eval_notes": "bad",
            }
        }
        (tmp_path / "eval-campaign-summary.json").write_text(
            json.dumps(campaign_data)
        )
        assert read_latest_eval_feedback(tmp_path) == ""

    def test_handles_invalid_json(self, tmp_path: Path) -> None:
        (tmp_path / "eval-broken.json").write_text("not json")
        assert read_latest_eval_feedback(tmp_path) == ""


# ── update_repeated_mistakes ────────────────────────────────────────────────


class TestUpdateRepeatedMistakes:
    def test_adds_new_mistake(self) -> None:
        tracker = MistakeTracker()
        update_repeated_mistakes("missing imports", tracker)
        assert "missing imports" in tracker.mistakes

    def test_skips_empty_string(self) -> None:
        tracker = MistakeTracker()
        update_repeated_mistakes("", tracker)
        assert len(tracker.mistakes) == 0

    def test_skips_none_string(self) -> None:
        tracker = MistakeTracker()
        update_repeated_mistakes("none", tracker)
        assert len(tracker.mistakes) == 0

    def test_deduplicates(self) -> None:
        tracker = MistakeTracker()
        update_repeated_mistakes("same error", tracker)
        update_repeated_mistakes("same error", tracker)
        assert len(tracker.mistakes) == 1


# ── get_cumulative_mistakes ──────────────────────────────────────────────────


class TestGetCumulativeMistakes:
    def test_empty_tracker(self) -> None:
        assert get_cumulative_mistakes(MistakeTracker()) == ""

    def test_formats_mistakes(self) -> None:
        tracker = MistakeTracker(mistakes=["error A", "error B"])
        result = get_cumulative_mistakes(tracker)
        assert "Known mistakes" in result
        assert "  - error A" in result
        assert "  - error B" in result


# ── extract_drift_targets ────────────────────────────────────────────────────


class TestExtractDriftTargets:
    def test_extracts_from_signals(self) -> None:
        output = (
            "FEATURE_BUILT: auth\n"
            "SPEC_FILE: .specs/features/auth/login.feature.md\n"
            "SOURCE_FILES: src/auth.ts, src/login.ts\n"
        )
        targets = extract_drift_targets(output)
        assert targets.spec_file == ".specs/features/auth/login.feature.md"
        assert "src/auth.ts" in targets.source_files

    def test_empty_output(self) -> None:
        targets = extract_drift_targets("")
        assert targets.spec_file == ""
        assert targets.source_files == ""


# ── check_drift ──────────────────────────────────────────────────────────────


class TestCheckDrift:
    def test_disabled_returns_passed(self, tmp_path: Path) -> None:
        result = check_drift(
            "spec.md", "src.ts", tmp_path, drift_enabled=False
        )
        assert result.passed is True
        assert result.summary == "disabled"

    def test_no_spec_returns_passed(self, tmp_path: Path) -> None:
        result = check_drift("", "src.ts", tmp_path)
        assert result.passed is True
        assert result.summary == "no spec file"

    @patch("auto_sdd.lib.drift.run_claude")
    def test_no_drift_detected(
        self, mock_claude: MagicMock, tmp_path: Path
    ) -> None:
        mock_claude.return_value = MagicMock(output="NO_DRIFT")
        result = check_drift("spec.md", "src.ts", tmp_path)
        assert result.passed is True

    @patch("auto_sdd.lib.drift.run_claude")
    def test_unresolvable_drift(
        self, mock_claude: MagicMock, tmp_path: Path
    ) -> None:
        mock_claude.return_value = MagicMock(
            output="DRIFT_UNRESOLVABLE: missing schema"
        )
        result = check_drift("spec.md", "src.ts", tmp_path)
        assert result.passed is False
        assert "missing schema" in result.summary


# ── run_code_review ──────────────────────────────────────────────────────────


class TestRunCodeReview:
    @patch("auto_sdd.lib.drift.run_claude")
    def test_review_clean(
        self, mock_claude: MagicMock, tmp_path: Path
    ) -> None:
        mock_claude.return_value = MagicMock(output="REVIEW_CLEAN")
        result = run_code_review(tmp_path)
        assert result.passed is True

    @patch("auto_sdd.lib.drift.run_claude")
    def test_review_failed(
        self, mock_claude: MagicMock, tmp_path: Path
    ) -> None:
        mock_claude.return_value = MagicMock(
            output="REVIEW_FAILED: couldn't fix"
        )
        result = run_code_review(tmp_path)
        assert result.passed is False

    @patch("auto_sdd.lib.drift.run_claude")
    def test_review_agent_error(
        self, mock_claude: MagicMock, tmp_path: Path
    ) -> None:
        mock_claude.side_effect = RuntimeError("boom")
        result = run_code_review(tmp_path)
        assert result.passed is False
        assert result.summary == "agent error"
