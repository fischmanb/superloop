"""Tests for auto_sdd.lib.general_estimates — token estimation and tracking."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from auto_sdd.lib.general_estimates import (
    _find_most_recent_session_jsonl,
    _int_from,
    append_general_estimate,
    estimate_general_tokens,
    get_session_actual_tokens,
    query_estimate_actuals,
)


# ── Helper to create a session JSONL ──────────────────────────────────────────


def _write_session_jsonl(path: Path, entries: list[dict[str, object]]) -> None:
    """Write a list of JSON objects as JSONL."""
    with open(path, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


def _assistant_entry(
    input_tokens: int = 100,
    output_tokens: int = 50,
    cache_creation: int = 10,
    cache_read: int = 5,
) -> dict[str, object]:
    """Build a mock assistant JSONL entry."""
    return {
        "type": "assistant",
        "message": {
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_creation_input_tokens": cache_creation,
                "cache_read_input_tokens": cache_read,
            }
        },
    }


# ── _int_from tests ───────────────────────────────────────────────────────────


class TestIntFrom:
    """Tests for the _int_from helper."""

    def test_int_passthrough(self) -> None:
        assert _int_from(42) == 42

    def test_float_truncated(self) -> None:
        assert _int_from(3.7) == 3

    def test_string_parsed(self) -> None:
        assert _int_from("99") == 99

    def test_invalid_string_returns_zero(self) -> None:
        assert _int_from("abc") == 0

    def test_none_returns_zero(self) -> None:
        assert _int_from(None) == 0

    def test_list_returns_zero(self) -> None:
        assert _int_from([1, 2]) == 0


# ── get_session_actual_tokens tests ───────────────────────────────────────────


class TestGetSessionActualTokens:
    """Tests for get_session_actual_tokens."""

    def test_valid_session_jsonl(self, tmp_path: Path) -> None:
        jsonl = tmp_path / "session.jsonl"
        _write_session_jsonl(
            jsonl,
            [
                _assistant_entry(100, 50, 10, 5),
                _assistant_entry(200, 80, 20, 15),
            ],
        )
        result = get_session_actual_tokens(jsonl)

        assert result["input_tokens"] == 300
        assert result["output_tokens"] == 130
        assert result["cache_creation_tokens"] == 30
        assert result["cache_read_tokens"] == 20
        assert result["active_tokens"] == 430
        assert result["cumulative_tokens"] == 480
        assert result["api_calls"] == 2
        assert result["source"] == "jsonl_direct"

    def test_empty_jsonl(self, tmp_path: Path) -> None:
        jsonl = tmp_path / "empty.jsonl"
        jsonl.write_text("")
        result = get_session_actual_tokens(jsonl)
        assert result["api_calls"] == 0
        assert result["active_tokens"] == 0

    def test_malformed_lines_skipped(self, tmp_path: Path) -> None:
        jsonl = tmp_path / "bad.jsonl"
        jsonl.write_text(
            "not json\n"
            + json.dumps(_assistant_entry(100, 50, 0, 0))
            + "\n"
            + "{invalid json\n"
        )
        result = get_session_actual_tokens(jsonl)
        assert result["api_calls"] == 1
        assert result["input_tokens"] == 100

    def test_non_assistant_entries_skipped(self, tmp_path: Path) -> None:
        jsonl = tmp_path / "mixed.jsonl"
        _write_session_jsonl(
            jsonl,
            [
                {"type": "human", "message": {"content": "hello"}},
                _assistant_entry(100, 50, 0, 0),
                {"type": "system", "content": "info"},
            ],
        )
        result = get_session_actual_tokens(jsonl)
        assert result["api_calls"] == 1

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        jsonl = tmp_path / "nonexistent.jsonl"
        with pytest.raises(FileNotFoundError):
            get_session_actual_tokens(jsonl)

    def test_auto_find_most_recent(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test that passing None triggers auto-detection (which will fail
        in test environment since ~/.claude/projects/ won't exist)."""
        monkeypatch.setenv("HOME", str(tmp_path))
        with pytest.raises(FileNotFoundError):
            get_session_actual_tokens(None)

    def test_entry_with_no_usage(self, tmp_path: Path) -> None:
        jsonl = tmp_path / "no_usage.jsonl"
        _write_session_jsonl(
            jsonl,
            [{"type": "assistant", "message": {}}],
        )
        result = get_session_actual_tokens(jsonl)
        assert result["api_calls"] == 0

    def test_blank_lines_skipped(self, tmp_path: Path) -> None:
        jsonl = tmp_path / "blanks.jsonl"
        content = (
            "\n\n"
            + json.dumps(_assistant_entry(50, 25, 0, 0))
            + "\n\n"
        )
        jsonl.write_text(content)
        result = get_session_actual_tokens(jsonl)
        assert result["api_calls"] == 1
        assert result["active_tokens"] == 75


# ── append_general_estimate tests ─────────────────────────────────────────────


class TestAppendGeneralEstimate:
    """Tests for append_general_estimate."""

    def test_appends_valid_record(self, tmp_path: Path) -> None:
        path = tmp_path / "estimates.jsonl"
        record = {"activity_type": "test", "estimated_tokens_pre": 1000}
        append_general_estimate(record, path)

        lines = path.read_text().strip().splitlines()
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["activity_type"] == "test"

    def test_appends_multiple_records(self, tmp_path: Path) -> None:
        path = tmp_path / "estimates.jsonl"
        for i in range(3):
            append_general_estimate({"n": i}, path)
        lines = path.read_text().strip().splitlines()
        assert len(lines) == 3

    def test_non_dict_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "estimates.jsonl"
        with pytest.raises(ValueError, match="must be a dict"):
            append_general_estimate("not a dict", path)  # type: ignore[arg-type]

    def test_unserializable_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "estimates.jsonl"
        with pytest.raises(ValueError, match="not JSON-serializable"):
            append_general_estimate({"bad": object()}, path)

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        path = tmp_path / "subdir" / "deep" / "estimates.jsonl"
        append_general_estimate({"test": True}, path)
        assert path.exists()

    def test_default_path_used(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """When no explicit path given, uses _DEFAULT_ESTIMATES_FILE."""
        default_path = tmp_path / "general-estimates.jsonl"
        monkeypatch.setattr(
            "auto_sdd.lib.general_estimates._DEFAULT_ESTIMATES_FILE",
            default_path,
        )
        append_general_estimate({"test": True})
        assert default_path.exists()


# ── query_estimate_actuals tests ──────────────────────────────────────────────


class TestQueryEstimateActuals:
    """Tests for query_estimate_actuals."""

    def test_no_file_returns_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "nope.jsonl"
        result = query_estimate_actuals(estimates_file=path)
        assert result["sample_count"] == 0
        assert result["calibration_ready"] is False

    def test_single_sample(self, tmp_path: Path) -> None:
        path = tmp_path / "est.jsonl"
        record = {
            "activity_type": "build",
            "estimated_tokens_pre": 10000,
            "active_tokens": 8000,
        }
        path.write_text(json.dumps(record) + "\n")

        result = query_estimate_actuals("build", path)
        assert result["sample_count"] == 1
        assert result["avg_active_tokens"] == 8000
        assert result["calibration_ready"] is False

    def test_multiple_samples(self, tmp_path: Path) -> None:
        path = tmp_path / "est.jsonl"
        records = [
            {"activity_type": "build", "active_tokens": 8000, "estimated_tokens_pre": 10000},
            {"activity_type": "build", "active_tokens": 12000, "estimated_tokens_pre": 10000},
        ]
        path.write_text(
            "\n".join(json.dumps(r) for r in records) + "\n"
        )

        result = query_estimate_actuals("build", path)
        assert result["sample_count"] == 2
        assert result["avg_active_tokens"] == 10000
        assert result["min_active"] == 8000
        assert result["max_active"] == 12000

    def test_activity_type_filter(self, tmp_path: Path) -> None:
        path = tmp_path / "est.jsonl"
        records = [
            {"activity_type": "build", "active_tokens": 8000},
            {"activity_type": "review", "active_tokens": 3000},
            {"activity_type": "build", "active_tokens": 12000},
        ]
        path.write_text(
            "\n".join(json.dumps(r) for r in records) + "\n"
        )

        result = query_estimate_actuals("build", path)
        assert result["sample_count"] == 2

        result = query_estimate_actuals("review", path)
        assert result["sample_count"] == 1

    def test_no_filter_returns_all(self, tmp_path: Path) -> None:
        path = tmp_path / "est.jsonl"
        records = [
            {"activity_type": "build", "active_tokens": 8000},
            {"activity_type": "review", "active_tokens": 3000},
        ]
        path.write_text(
            "\n".join(json.dumps(r) for r in records) + "\n"
        )

        result = query_estimate_actuals(None, path)
        assert result["sample_count"] == 2
        assert result["activity_type"] == "all"

    def test_calibration_ready_at_five(self, tmp_path: Path) -> None:
        path = tmp_path / "est.jsonl"
        records = [
            {"activity_type": "build", "active_tokens": 1000 * (i + 1)}
            for i in range(5)
        ]
        path.write_text(
            "\n".join(json.dumps(r) for r in records) + "\n"
        )

        result = query_estimate_actuals("build", path)
        assert result["calibration_ready"] is True
        assert result["sample_count"] == 5

    def test_estimation_error_pct(self, tmp_path: Path) -> None:
        path = tmp_path / "est.jsonl"
        records = [
            {"activity_type": "build", "active_tokens": 10000, "estimated_tokens_pre": 12000},
        ]
        path.write_text(json.dumps(records[0]) + "\n")

        result = query_estimate_actuals("build", path)
        # Error = (12000 - 10000) / 10000 * 100 = 20.0%
        assert result["avg_estimation_error_pct"] == 20.0

    def test_fallback_to_approx_actual_tokens(self, tmp_path: Path) -> None:
        path = tmp_path / "est.jsonl"
        record = {
            "activity_type": "build",
            "approx_actual_tokens": 5000,
        }
        path.write_text(json.dumps(record) + "\n")

        result = query_estimate_actuals("build", path)
        assert result["sample_count"] == 1
        assert result["avg_active_tokens"] == 5000

    def test_zero_tokens_skipped(self, tmp_path: Path) -> None:
        path = tmp_path / "est.jsonl"
        records = [
            {"activity_type": "build", "active_tokens": 0},
            {"activity_type": "build", "active_tokens": 5000},
        ]
        path.write_text(
            "\n".join(json.dumps(r) for r in records) + "\n"
        )

        result = query_estimate_actuals("build", path)
        assert result["sample_count"] == 1

    def test_malformed_lines_skipped(self, tmp_path: Path) -> None:
        path = tmp_path / "est.jsonl"
        path.write_text(
            "not json\n"
            + json.dumps({"activity_type": "x", "active_tokens": 1000})
            + "\n"
        )
        result = query_estimate_actuals("x", path)
        assert result["sample_count"] == 1

    def test_no_estimation_error_when_no_estimates(self, tmp_path: Path) -> None:
        path = tmp_path / "est.jsonl"
        record = {"activity_type": "build", "active_tokens": 5000}
        path.write_text(json.dumps(record) + "\n")

        result = query_estimate_actuals("build", path)
        assert result["avg_estimation_error_pct"] is None


# ── estimate_general_tokens tests ─────────────────────────────────────────────


class TestEstimateGeneralTokens:
    """Tests for estimate_general_tokens graduated blend."""

    def test_no_data_returns_fallback(self, tmp_path: Path) -> None:
        path = tmp_path / "est.jsonl"
        result = estimate_general_tokens("build", 15000, path)
        assert result == 15000

    def test_one_sample_20pct_blend(self, tmp_path: Path) -> None:
        path = tmp_path / "est.jsonl"
        path.write_text(
            json.dumps({"activity_type": "build", "active_tokens": 10000})
            + "\n"
        )
        # 1 sample: 20% actuals (10000), 80% fallback (20000)
        # = 0.2 * 10000 + 0.8 * 20000 = 2000 + 16000 = 18000
        result = estimate_general_tokens("build", 20000, path)
        assert result == 18000

    def test_two_samples_40pct_blend(self, tmp_path: Path) -> None:
        path = tmp_path / "est.jsonl"
        records = [
            {"activity_type": "build", "active_tokens": 10000},
            {"activity_type": "build", "active_tokens": 10000},
        ]
        path.write_text(
            "\n".join(json.dumps(r) for r in records) + "\n"
        )
        # 2 samples: 40% * 10000 + 60% * 20000 = 4000 + 12000 = 16000
        result = estimate_general_tokens("build", 20000, path)
        assert result == 16000

    def test_three_samples_60pct_blend(self, tmp_path: Path) -> None:
        path = tmp_path / "est.jsonl"
        records = [
            {"activity_type": "build", "active_tokens": 10000},
            {"activity_type": "build", "active_tokens": 10000},
            {"activity_type": "build", "active_tokens": 10000},
        ]
        path.write_text(
            "\n".join(json.dumps(r) for r in records) + "\n"
        )
        # 3 samples: 60% * 10000 + 40% * 20000 = 6000 + 8000 = 14000
        result = estimate_general_tokens("build", 20000, path)
        assert result == 14000

    def test_four_samples_80pct_blend(self, tmp_path: Path) -> None:
        path = tmp_path / "est.jsonl"
        records = [
            {"activity_type": "build", "active_tokens": 10000}
            for _ in range(4)
        ]
        path.write_text(
            "\n".join(json.dumps(r) for r in records) + "\n"
        )
        # 4 samples: 80% * 10000 + 20% * 20000 = 8000 + 4000 = 12000
        result = estimate_general_tokens("build", 20000, path)
        assert result == 12000

    def test_five_plus_samples_100pct_actuals(self, tmp_path: Path) -> None:
        path = tmp_path / "est.jsonl"
        records = [
            {"activity_type": "build", "active_tokens": 10000}
            for _ in range(5)
        ]
        path.write_text(
            "\n".join(json.dumps(r) for r in records) + "\n"
        )
        # 5+ samples: 100% actuals = 10000
        result = estimate_general_tokens("build", 20000, path)
        assert result == 10000

    def test_seven_samples_still_100pct(self, tmp_path: Path) -> None:
        path = tmp_path / "est.jsonl"
        records = [
            {"activity_type": "build", "active_tokens": 8000}
            for _ in range(7)
        ]
        path.write_text(
            "\n".join(json.dumps(r) for r in records) + "\n"
        )
        result = estimate_general_tokens("build", 20000, path)
        assert result == 8000

    def test_nonexistent_file_returns_fallback(self, tmp_path: Path) -> None:
        path = tmp_path / "nope.jsonl"
        result = estimate_general_tokens("build", 15000, path)
        assert result == 15000


# ── _find_most_recent_session_jsonl tests ─────────────────────────────────────


class TestFindMostRecentSessionJsonl:
    """Tests for _find_most_recent_session_jsonl."""

    def test_no_claude_dir_raises(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        with pytest.raises(FileNotFoundError, match="not found"):
            _find_most_recent_session_jsonl()

    def test_empty_projects_dir_raises(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        (tmp_path / ".claude" / "projects").mkdir(parents=True)
        with pytest.raises(FileNotFoundError, match="No JSONL"):
            _find_most_recent_session_jsonl()

    def test_finds_most_recent(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        projects_dir = tmp_path / ".claude" / "projects" / "test"
        projects_dir.mkdir(parents=True)

        import time

        old_file = projects_dir / "old.jsonl"
        old_file.write_text("{}\n")
        time.sleep(0.05)
        new_file = projects_dir / "new.jsonl"
        new_file.write_text("{}\n")

        result = _find_most_recent_session_jsonl()
        assert result == new_file
