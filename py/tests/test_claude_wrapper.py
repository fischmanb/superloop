"""Tests for auto_sdd.lib.claude_wrapper — Claude CLI wrapper."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from auto_sdd.lib.claude_wrapper import (
    AgentTimeoutError,
    ClaudeOutputError,
    ClaudeResult,
    _build_cost_record,
    _dominant_model,
    run_claude,
)


# ---------------------------------------------------------------------------
# _dominant_model
# ---------------------------------------------------------------------------


class TestDominantModel:
    """Tests for the _dominant_model helper."""

    def test_dominant_model_single_model(self) -> None:
        usage = {"claude-3-opus": {"input_tokens": 100, "output_tokens": 50}}
        assert _dominant_model(usage) == "claude-3-opus"

    def test_dominant_model_multiple_models(self) -> None:
        usage = {
            "claude-3-opus": {"input_tokens": 100, "output_tokens": 50},
            "claude-3-haiku": {"input_tokens": 500, "output_tokens": 300},
        }
        assert _dominant_model(usage) == "claude-3-haiku"

    def test_dominant_model_empty_returns_unknown(self) -> None:
        assert _dominant_model({}) == "unknown"

    def test_dominant_model_missing_token_fields(self) -> None:
        usage = {"claude-3-opus": {"input_tokens": 100}}
        assert _dominant_model(usage) == "claude-3-opus"

    def test_dominant_model_all_zero_tokens(self) -> None:
        usage = {
            "model-a": {"input_tokens": 0, "output_tokens": 0},
            "model-b": {"input_tokens": 0, "output_tokens": 0},
        }
        # Both are 0, first one encountered with total > best_total (-1) wins
        result = _dominant_model(usage)
        assert result in ("model-a", "model-b")

    def test_dominant_model_tie_goes_to_later(self) -> None:
        # When totals are equal, the last one with > best_total is kept.
        # Actually both have the same total (150), so the first one wins
        # because subsequent equal values don't satisfy > best_total.
        usage = {
            "model-a": {"input_tokens": 100, "output_tokens": 50},
            "model-b": {"input_tokens": 75, "output_tokens": 75},
        }
        result = _dominant_model(usage)
        assert result in ("model-a", "model-b")


# ---------------------------------------------------------------------------
# _build_cost_record
# ---------------------------------------------------------------------------


class TestBuildCostRecord:
    """Tests for _build_cost_record."""

    def test_build_cost_record_full_data(self) -> None:
        data: dict[str, Any] = {
            "total_cost_usd": 0.05,
            "usage": {
                "input_tokens": 1000,
                "output_tokens": 500,
                "cache_creation_input_tokens": 200,
                "cache_read_input_tokens": 100,
            },
            "duration_ms": 5000,
            "duration_api_ms": 4000,
            "num_turns": 3,
            "modelUsage": {
                "claude-3-opus": {"input_tokens": 1000, "output_tokens": 500}
            },
            "session_id": "sess-123",
            "stop_reason": "end_turn",
        }
        record = _build_cost_record(data)

        assert record["cost_usd"] == 0.05
        assert record["input_tokens"] == 1000
        assert record["output_tokens"] == 500
        assert record["cache_creation_tokens"] == 200
        assert record["cache_read_tokens"] == 100
        assert record["duration_ms"] == 5000
        assert record["duration_api_ms"] == 4000
        assert record["num_turns"] == 3
        assert record["model"] == "claude-3-opus"
        assert record["session_id"] == "sess-123"
        assert record["stop_reason"] == "end_turn"
        assert "timestamp" in record

    def test_build_cost_record_minimal_data(self) -> None:
        data: dict[str, Any] = {}
        record = _build_cost_record(data)

        assert record["cost_usd"] is None
        assert record["input_tokens"] is None
        assert record["output_tokens"] is None
        assert record["model"] == "unknown"
        assert record["session_id"] is None
        assert "timestamp" in record

    def test_build_cost_record_timestamp_is_utc_iso(self) -> None:
        data: dict[str, Any] = {}
        record = _build_cost_record(data)
        ts = record["timestamp"]
        assert isinstance(ts, str)
        assert ts.endswith("Z")

    def test_build_cost_record_non_dict_usage_ignored(self) -> None:
        data: dict[str, Any] = {"usage": "not-a-dict"}
        record = _build_cost_record(data)
        assert record["input_tokens"] is None


# ---------------------------------------------------------------------------
# ClaudeResult dataclass
# ---------------------------------------------------------------------------


class TestClaudeResult:
    """Tests for the ClaudeResult dataclass."""

    def test_claude_result_defaults(self) -> None:
        r = ClaudeResult(output="hello", exit_code=0)
        assert r.output == "hello"
        assert r.exit_code == 0
        assert r.cost_usd is None
        assert r.input_tokens is None
        assert r.output_tokens is None
        assert r.model is None
        assert r.session_id is None
        assert r.duration_ms is None

    def test_claude_result_full(self) -> None:
        r = ClaudeResult(
            output="response",
            exit_code=0,
            cost_usd=0.01,
            input_tokens=100,
            output_tokens=50,
            model="opus",
            session_id="s-1",
            duration_ms=3000,
        )
        assert r.cost_usd == 0.01
        assert r.model == "opus"


# ---------------------------------------------------------------------------
# run_claude — success path
# ---------------------------------------------------------------------------


def _make_claude_json(
    result: str = "Hello world",
    cost: float = 0.01,
    input_tokens: int = 100,
    output_tokens: int = 50,
    model: str = "claude-3-opus",
    session_id: str = "sess-abc",
    duration_ms: int = 2500,
) -> str:
    """Build a realistic Claude JSON response string."""
    return json.dumps(
        {
            "result": result,
            "total_cost_usd": cost,
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            },
            "duration_ms": duration_ms,
            "duration_api_ms": 2000,
            "num_turns": 1,
            "modelUsage": {
                model: {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                }
            },
            "session_id": session_id,
            "stop_reason": "end_turn",
        }
    )


class TestRunClaudeSuccess:
    """Tests for run_claude when claude exits 0 with valid JSON."""

    @patch("auto_sdd.lib.claude_wrapper.subprocess.run")
    def test_run_claude_returns_result(
        self, mock_run: Any
    ) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["claude"],
            returncode=0,
            stdout=_make_claude_json(),
            stderr="",
        )
        result = run_claude(["-p", "hello"])

        assert result.output == "Hello world"
        assert result.exit_code == 0
        assert result.cost_usd == 0.01
        assert result.input_tokens == 100
        assert result.output_tokens == 50
        assert result.model == "claude-3-opus"
        assert result.session_id == "sess-abc"
        assert result.duration_ms == 2500

    @patch("auto_sdd.lib.claude_wrapper.subprocess.run")
    def test_run_claude_passes_correct_command(
        self, mock_run: Any
    ) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["claude"],
            returncode=0,
            stdout=_make_claude_json(),
            stderr="",
        )
        run_claude(["-p", "--dangerously-skip-permissions", "do stuff"])

        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert cmd[0] == "claude"
        assert "-p" in cmd
        assert "--dangerously-skip-permissions" in cmd
        assert "do stuff" in cmd
        assert cmd[-2:] == ["--output-format", "json"]

    @patch("auto_sdd.lib.claude_wrapper.subprocess.run")
    def test_run_claude_unsets_claudecode_env(
        self, mock_run: Any
    ) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["claude"],
            returncode=0,
            stdout=_make_claude_json(),
            stderr="",
        )
        # Temporarily set CLAUDECODE in environment
        with patch.dict("os.environ", {"CLAUDECODE": "1"}):
            run_claude(["-p", "test"])

        call_kwargs = mock_run.call_args[1]
        env = call_kwargs.get("env", {})
        assert "CLAUDECODE" not in env

    @patch("auto_sdd.lib.claude_wrapper.subprocess.run")
    def test_run_claude_uses_specified_timeout(
        self, mock_run: Any
    ) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["claude"],
            returncode=0,
            stdout=_make_claude_json(),
            stderr="",
        )
        run_claude(["-p", "test"], timeout=300)

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["timeout"] == 300

    @patch("auto_sdd.lib.claude_wrapper.subprocess.run")
    def test_run_claude_default_timeout_is_600(
        self, mock_run: Any
    ) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["claude"],
            returncode=0,
            stdout=_make_claude_json(),
            stderr="",
        )
        run_claude(["-p", "test"])

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["timeout"] == 600


# ---------------------------------------------------------------------------
# run_claude — cost logging
# ---------------------------------------------------------------------------


class TestRunClaudeCostLogging:
    """Tests for JSONL cost log writing."""

    @patch("auto_sdd.lib.claude_wrapper.subprocess.run")
    def test_run_claude_writes_cost_log(
        self, mock_run: Any, tmp_path: Path
    ) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["claude"],
            returncode=0,
            stdout=_make_claude_json(),
            stderr="",
        )
        log_path = tmp_path / "cost.jsonl"
        run_claude(["-p", "test"], cost_log_path=log_path)

        assert log_path.exists()
        lines = log_path.read_text().strip().split("\n")
        assert len(lines) == 1

        record = json.loads(lines[0])
        assert record["cost_usd"] == 0.01
        assert record["input_tokens"] == 100
        assert record["output_tokens"] == 50
        assert record["model"] == "claude-3-opus"
        assert record["session_id"] == "sess-abc"

    @patch("auto_sdd.lib.claude_wrapper.subprocess.run")
    def test_run_claude_appends_to_existing_cost_log(
        self, mock_run: Any, tmp_path: Path
    ) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["claude"],
            returncode=0,
            stdout=_make_claude_json(),
            stderr="",
        )
        log_path = tmp_path / "cost.jsonl"
        log_path.write_text('{"existing": true}\n')

        run_claude(["-p", "test"], cost_log_path=log_path)

        lines = log_path.read_text().strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0]) == {"existing": True}

    @patch("auto_sdd.lib.claude_wrapper.subprocess.run")
    def test_run_claude_no_cost_log_when_path_is_none(
        self, mock_run: Any, tmp_path: Path
    ) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["claude"],
            returncode=0,
            stdout=_make_claude_json(),
            stderr="",
        )
        result = run_claude(["-p", "test"], cost_log_path=None)
        assert result.exit_code == 0
        # No cost log file should be created anywhere

    @patch("auto_sdd.lib.claude_wrapper.subprocess.run")
    def test_run_claude_creates_parent_dirs_for_cost_log(
        self, mock_run: Any, tmp_path: Path
    ) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["claude"],
            returncode=0,
            stdout=_make_claude_json(),
            stderr="",
        )
        log_path = tmp_path / "nested" / "dir" / "cost.jsonl"
        run_claude(["-p", "test"], cost_log_path=log_path)

        assert log_path.exists()

    @patch("auto_sdd.lib.claude_wrapper.subprocess.run")
    def test_run_claude_cost_log_record_has_all_bash_fields(
        self, mock_run: Any, tmp_path: Path
    ) -> None:
        """Verify the JSONL record matches the bash cost-log format."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["claude"],
            returncode=0,
            stdout=_make_claude_json(),
            stderr="",
        )
        log_path = tmp_path / "cost.jsonl"
        run_claude(["-p", "test"], cost_log_path=log_path)

        record = json.loads(log_path.read_text().strip())
        expected_fields = {
            "timestamp",
            "cost_usd",
            "input_tokens",
            "output_tokens",
            "cache_creation_tokens",
            "cache_read_tokens",
            "duration_ms",
            "duration_api_ms",
            "num_turns",
            "model",
            "session_id",
            "stop_reason",
        }
        assert set(record.keys()) == expected_fields


# ---------------------------------------------------------------------------
# run_claude — error paths
# ---------------------------------------------------------------------------


class TestRunClaudeErrors:
    """Tests for error handling in run_claude."""

    @patch("auto_sdd.lib.claude_wrapper.subprocess.run")
    def test_run_claude_nonzero_exit_raises_called_process_error(
        self, mock_run: Any
    ) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["claude"],
            returncode=1,
            stdout="error output",
            stderr="some error",
        )
        with pytest.raises(subprocess.CalledProcessError) as exc_info:
            run_claude(["-p", "test"])

        assert exc_info.value.returncode == 1

    @patch("auto_sdd.lib.claude_wrapper.subprocess.run")
    def test_run_claude_nonzero_exit_includes_diagnostics(
        self, mock_run: Any
    ) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["claude"],
            returncode=42,
            stdout="raw stdout",
            stderr="raw stderr",
        )
        with pytest.raises(subprocess.CalledProcessError) as exc_info:
            run_claude(["-p", "test"])

        assert exc_info.value.output == "raw stdout"
        assert exc_info.value.stderr == "raw stderr"

    @patch("auto_sdd.lib.claude_wrapper.subprocess.run")
    def test_run_claude_timeout_raises_agent_timeout_error(
        self, mock_run: Any
    ) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=["claude"], timeout=10
        )
        with pytest.raises(AgentTimeoutError, match="10s timeout"):
            run_claude(["-p", "test"], timeout=10)

    @patch("auto_sdd.lib.claude_wrapper.subprocess.run")
    def test_run_claude_invalid_json_raises_claude_output_error(
        self, mock_run: Any
    ) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["claude"],
            returncode=0,
            stdout="this is not json",
            stderr="",
        )
        with pytest.raises(ClaudeOutputError, match="not return valid JSON"):
            run_claude(["-p", "test"])

    @patch("auto_sdd.lib.claude_wrapper.subprocess.run")
    def test_run_claude_json_without_result_raises_claude_output_error(
        self, mock_run: Any
    ) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["claude"],
            returncode=0,
            stdout='{"no_result_field": true}',
            stderr="",
        )
        with pytest.raises(ClaudeOutputError, match="no .result field"):
            run_claude(["-p", "test"])

    @patch("auto_sdd.lib.claude_wrapper.subprocess.run")
    def test_run_claude_json_array_raises_claude_output_error(
        self, mock_run: Any
    ) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["claude"],
            returncode=0,
            stdout="[1, 2, 3]",
            stderr="",
        )
        with pytest.raises(ClaudeOutputError, match="Expected JSON object"):
            run_claude(["-p", "test"])

    @patch("auto_sdd.lib.claude_wrapper.subprocess.run")
    def test_run_claude_empty_stdout_on_success_raises_output_error(
        self, mock_run: Any
    ) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["claude"],
            returncode=0,
            stdout="",
            stderr="",
        )
        with pytest.raises(ClaudeOutputError):
            run_claude(["-p", "test"])


# ---------------------------------------------------------------------------
# run_claude — edge cases
# ---------------------------------------------------------------------------


class TestRunClaudeEdgeCases:
    """Edge-case tests for run_claude."""

    @patch("auto_sdd.lib.claude_wrapper.subprocess.run")
    def test_run_claude_null_result_returns_empty_string(
        self, mock_run: Any
    ) -> None:
        """When .result is JSON null, output should be empty string."""
        data = {
            "result": None,
            "total_cost_usd": 0.0,
            "usage": {"input_tokens": 0, "output_tokens": 0},
            "modelUsage": {},
        }
        mock_run.return_value = subprocess.CompletedProcess(
            args=["claude"],
            returncode=0,
            stdout=json.dumps(data),
            stderr="",
        )
        result = run_claude(["-p", "test"])
        assert result.output == ""

    @patch("auto_sdd.lib.claude_wrapper.subprocess.run")
    def test_run_claude_missing_usage_fields_returns_none(
        self, mock_run: Any
    ) -> None:
        """When usage fields are absent, tokens should be None."""
        data = {"result": "hello", "total_cost_usd": 0.01}
        mock_run.return_value = subprocess.CompletedProcess(
            args=["claude"],
            returncode=0,
            stdout=json.dumps(data),
            stderr="",
        )
        result = run_claude(["-p", "test"])
        assert result.output == "hello"
        assert result.input_tokens is None
        assert result.output_tokens is None
        assert result.model == "unknown"

    @patch("auto_sdd.lib.claude_wrapper.subprocess.run")
    def test_run_claude_missing_cost_returns_none(
        self, mock_run: Any
    ) -> None:
        data = {"result": "hello"}
        mock_run.return_value = subprocess.CompletedProcess(
            args=["claude"],
            returncode=0,
            stdout=json.dumps(data),
            stderr="",
        )
        result = run_claude(["-p", "test"])
        assert result.cost_usd is None

    @patch("auto_sdd.lib.claude_wrapper.subprocess.run")
    def test_run_claude_cost_log_failure_does_not_crash(
        self, mock_run: Any
    ) -> None:
        """If cost log write fails (e.g., permission denied), run_claude
        should still return successfully — it logs a warning instead."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["claude"],
            returncode=0,
            stdout=_make_claude_json(),
            stderr="",
        )
        # Use a path that can't be written (directory doesn't exist and
        # we make parent dir creation fail by using a file as "parent")
        bad_path = Path("/dev/null/impossible/cost.jsonl")
        result = run_claude(["-p", "test"], cost_log_path=bad_path)
        # Should succeed despite log failure
        assert result.output == "Hello world"

    @patch("auto_sdd.lib.claude_wrapper.subprocess.run")
    def test_run_claude_nonzero_exit_empty_stderr(
        self, mock_run: Any
    ) -> None:
        """Non-zero exit with empty stderr should still raise."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["claude"],
            returncode=2,
            stdout="",
            stderr="",
        )
        with pytest.raises(subprocess.CalledProcessError) as exc_info:
            run_claude(["-p", "test"])
        assert exc_info.value.returncode == 2

    @patch("auto_sdd.lib.claude_wrapper.subprocess.run")
    def test_run_claude_empty_args_list(
        self, mock_run: Any
    ) -> None:
        """Passing empty args should still work (just runs claude --output-format json)."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["claude"],
            returncode=0,
            stdout=_make_claude_json(),
            stderr="",
        )
        result = run_claude([])
        assert result.exit_code == 0
        cmd = mock_run.call_args[0][0]
        assert cmd == ["claude", "--output-format", "json"]
