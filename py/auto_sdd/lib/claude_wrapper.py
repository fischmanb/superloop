# CONVERSION CHANGELOG (from lib/claude-wrapper.sh)
# - Bash script is a standalone executable wrapper; Python version is a library
#   function `run_claude()` meant to be imported and called.
# - Bash writes raw `.result` text to stdout; Python returns it in
#   ClaudeResult.output. Callers decide what to do with it.
# - Bash unconditionally appends cost data when `.result` exists; Python only
#   appends when `cost_log_path` is not None.
# - Bash falls through with the original exit code on non-JSON output;
#   Python raises ClaudeOutputError so callers can catch it explicitly.
# - Bash derives model from modelUsage (highest total tokens); Python
#   preserves this logic exactly.
# - Bash logs cache_creation_tokens, cache_read_tokens, duration_api_ms,
#   num_turns, and stop_reason in the JSONL cost log. Python preserves all
#   of these fields for format compatibility with existing bash consumers.
# - AgentTimeoutError and other exceptions defined inline because shared
#   errors.py does not exist yet (Phase 1).
"""Wrapper around the Claude CLI.

Invokes the ``claude`` command-line tool with ``--output-format json``,
parses the structured response, extracts the human-readable result, and
optionally appends cost/usage metadata to a JSONL log file.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Billing-specific signals from the Anthropic API / Claude CLI stderr.
# Intentionally narrow: must not match on feature names or build output.
_BILLING_RE = re.compile(
    r"credit_balance_too_low"
    r"|insufficient_quota"
    r"|quota.{0,10}exceeded"
    r"|402 Payment Required"
    r"|payment required"
    r"|your (api )?credits? (are |is )?(exhausted|too low|insufficient|depleted)"
    r"|billing.{0,20}error",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Inline exception hierarchy (will move to errors.py in a later phase)
# ---------------------------------------------------------------------------


class AutoSddError(Exception):
    """Base for all auto-sdd errors."""


class AgentTimeoutError(AutoSddError):
    """Claude agent exceeded timeout."""


class ClaudeOutputError(AutoSddError):
    """Claude returned output that is not valid JSON or lacks a .result field."""


class CreditExhaustionError(AutoSddError):
    """Claude CLI exited with a billing/credit error.

    Raised by ``run_claude()`` when the process exits non-zero and the
    combined stderr+stdout contains billing-specific signals from the
    Anthropic API (e.g. credit_balance_too_low, 402, payment required).
    Callers should catch this explicitly and halt rather than retrying.
    """


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class ClaudeResult:
    """Structured result from a Claude CLI invocation."""

    output: str
    exit_code: int
    cost_usd: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    model: str | None = None
    session_id: str | None = None
    duration_ms: int | None = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _dominant_model(model_usage: dict[str, dict[str, int]]) -> str:
    """Return the model name with the highest total token count.

    Mirrors the bash jq logic:
    ``[.modelUsage | to_entries[] | {key, total: (.value.input_tokens +
    .value.output_tokens)}] | max_by(.total) | .key``

    Returns ``"unknown"`` when *model_usage* is empty.
    """
    if not model_usage:
        return "unknown"

    best_model = "unknown"
    best_total = -1
    for model_name, counts in model_usage.items():
        total = counts.get("input_tokens", 0) + counts.get("output_tokens", 0)
        if total > best_total:
            best_total = total
            best_model = model_name
    return best_model


def _build_cost_record(data: dict[str, object]) -> dict[str, object]:
    """Build a JSONL cost-log record from raw Claude JSON output.

    The record format matches the bash original exactly so that downstream
    consumers (bash scripts, dashboards) can parse either source.
    """
    usage: dict[str, object] = {}
    raw_usage = data.get("usage")
    if isinstance(raw_usage, dict):
        usage = raw_usage

    raw_model_usage = data.get("modelUsage")
    model_usage: dict[str, dict[str, int]] = {}
    if isinstance(raw_model_usage, dict):
        for k, v in raw_model_usage.items():
            if isinstance(k, str) and isinstance(v, dict):
                model_usage[k] = {
                    sk: sv for sk, sv in v.items()
                    if isinstance(sk, str) and isinstance(sv, int)
                }

    def _int_or_none(val: object) -> int | None:
        return int(val) if isinstance(val, (int, float)) else None

    return {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cost_usd": data.get("total_cost_usd"),
        "input_tokens": _int_or_none(usage.get("input_tokens")),
        "output_tokens": _int_or_none(usage.get("output_tokens")),
        "cache_creation_tokens": _int_or_none(usage.get("cache_creation_input_tokens")),
        "cache_read_tokens": _int_or_none(usage.get("cache_read_input_tokens")),
        "duration_ms": data.get("duration_ms"),
        "duration_api_ms": data.get("duration_api_ms"),
        "num_turns": data.get("num_turns"),
        "model": _dominant_model(model_usage),
        "session_id": data.get("session_id"),
        "stop_reason": data.get("stop_reason"),
    }


def _append_cost_log(path: Path, record: dict[str, object]) -> None:
    """Append a single JSON record to the JSONL cost log.

    Creates parent directories if they don't exist.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(record) + "\n")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _log_token_usage(
    result: ClaudeResult, activity_type: str = "agent_call"
) -> None:
    """Append token usage from a ClaudeResult to general-estimates.jsonl."""
    from auto_sdd.lib.general_estimates import (
        _DEFAULT_ESTIMATES_FILE,
        append_general_estimate,
    )

    record: dict[str, object] = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "activity_type": activity_type,
        "source": "claude_wrapper",
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "active_tokens": (result.input_tokens or 0) + (result.output_tokens or 0),
        "cost_usd": result.cost_usd,
        "model": result.model,
        "exit_code": result.exit_code,
        "duration_ms": result.duration_ms,
    }
    append_general_estimate(record, estimates_file=_DEFAULT_ESTIMATES_FILE)


def run_claude(
    args: list[str],
    *,
    cost_log_path: Path | None = None,
    timeout: int = 600,
    cwd: Path | str | None = None,
    activity_type: str = "agent_call",
) -> ClaudeResult:
    """Invoke the ``claude`` CLI, extract the result, and optionally log cost.

    Runs ``claude <args> --output-format json``, parses the JSON response,
    and returns a :class:`ClaudeResult`.

    Args:
        args: CLI arguments (e.g., ``["-p", "--dangerously-skip-permissions", prompt]``).
        cost_log_path: Path to JSONL cost log.  ``None`` disables logging.
        timeout: Seconds before the subprocess is killed.  Default 10 minutes.
        cwd: Working directory for the subprocess.  ``None`` inherits the
            current process's working directory.
        activity_type: Label for this call in the estimates log (e.g.,
            ``"build_feature"``, ``"eval_sidecar"``).  Defaults to
            ``"agent_call"``.

    Returns:
        :class:`ClaudeResult` with parsed output and cost metadata.

    Raises:
        AgentTimeoutError: If ``claude`` exceeds *timeout*.
        subprocess.CalledProcessError: If ``claude`` exits non-zero.
        ClaudeOutputError: If ``claude`` succeeds (exit 0) but returns
            invalid JSON or JSON without a ``.result`` field.
    """
    cmd = ["claude", *args, "--output-format", "json"]

    # Strip CLAUDECODE from the child environment to prevent nested-session
    # detection — mirrors ``unset CLAUDECODE`` in the bash wrapper.
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    logger.info("Running: %s (timeout=%ds)", " ".join(cmd), timeout)

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            cwd=cwd,
        )
    except subprocess.TimeoutExpired as exc:
        logger.error("Claude timed out after %ds", timeout)
        raise AgentTimeoutError(
            f"Claude agent exceeded {timeout}s timeout"
        ) from exc

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""

    # --- Non-zero exit: surface diagnostics and raise -----------------------
    if proc.returncode != 0:
        diag_parts: list[str] = [
            f"claude exited with code {proc.returncode}"
        ]
        if stderr:
            diag_parts.append(f"=== claude stderr ===\n{stderr}")
        if stdout:
            diag_parts.append(f"=== claude stdout ===\n{stdout}")
        diag = "\n".join(diag_parts)
        logger.error("WRAPPER_ERROR: %s", diag)
        # Raise a dedicated error for billing failures so callers can halt
        # without retrying, rather than scanning output text downstream.
        combined = stderr + stdout
        if _BILLING_RE.search(combined):
            raise CreditExhaustionError(
                f"API credit/billing error (exit {proc.returncode}): {combined[:300]}"
            )
        raise subprocess.CalledProcessError(
            proc.returncode, cmd, output=stdout, stderr=stderr
        )

    # --- Success path: parse JSON -------------------------------------------
    try:
        data: dict[str, object] = json.loads(stdout)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.error("Claude returned non-JSON output: %s", stdout[:200])
        raise ClaudeOutputError(
            "claude did not return valid JSON. "
            f"Raw output (first 200 chars): {stdout[:200]}"
        ) from exc

    if not isinstance(data, dict):
        raise ClaudeOutputError(
            f"Expected JSON object, got {type(data).__name__}"
        )

    if "result" not in data:
        logger.error("Claude JSON missing .result field: %s", stdout[:200])
        raise ClaudeOutputError(
            "claude JSON response has no .result field. "
            f"Raw output (first 200 chars): {stdout[:200]}"
        )

    result_text = data.get("result")
    output = str(result_text) if result_text is not None else ""

    # Extract metadata for ClaudeResult
    usage: dict[str, object] = {}
    raw_usage = data.get("usage")
    if isinstance(raw_usage, dict):
        usage = raw_usage

    raw_model_usage = data.get("modelUsage")
    model_usage: dict[str, dict[str, int]] = {}
    if isinstance(raw_model_usage, dict):
        for k, v in raw_model_usage.items():
            if isinstance(k, str) and isinstance(v, dict):
                model_usage[k] = {
                    sk: sv for sk, sv in v.items()
                    if isinstance(sk, str) and isinstance(sv, int)
                }

    def _float_or_none(val: object) -> float | None:
        return float(val) if isinstance(val, (int, float)) else None

    def _int_or_none(val: object) -> int | None:
        return int(val) if isinstance(val, (int, float)) else None

    def _str_or_none(val: object) -> str | None:
        return str(val) if val is not None else None

    cost_usd = _float_or_none(data.get("total_cost_usd"))
    input_tokens = _int_or_none(usage.get("input_tokens"))
    output_tokens = _int_or_none(usage.get("output_tokens"))
    model = _dominant_model(model_usage)
    session_id = _str_or_none(data.get("session_id"))
    duration_ms = _int_or_none(data.get("duration_ms"))

    # Log cost data if a log path was provided
    if cost_log_path is not None:
        try:
            record = _build_cost_record(data)
            _append_cost_log(cost_log_path, record)
            logger.info("Cost logged to %s", cost_log_path)
        except OSError:
            logger.warning("Failed to write cost log to %s", cost_log_path, exc_info=True)

    claude_result = ClaudeResult(
        output=output,
        exit_code=proc.returncode,
        cost_usd=cost_usd,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model=model,
        session_id=session_id,
        duration_ms=duration_ms,
    )

    # Log token usage to general estimates (best-effort, never fails the call)
    try:
        _log_token_usage(claude_result, activity_type=activity_type)
    except Exception:
        logger.debug("Failed to log token usage", exc_info=True)

    logger.info(
        "Claude completed: exit=%d, cost=$%s, tokens_in=%s, tokens_out=%s",
        claude_result.exit_code,
        claude_result.cost_usd,
        claude_result.input_tokens,
        claude_result.output_tokens,
    )

    return claude_result
