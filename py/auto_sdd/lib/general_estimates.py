# CONVERSION CHANGELOG (from lib/general-estimates.sh)
# - get_session_actual_tokens: bash shells out to `python3 -c` inline; Python
#   extracts that logic directly into a proper function. No subprocess needed.
# - append_general_estimate: bash uses `jq -c` for validation/compacting;
#   Python uses json.loads/json.dumps directly.
# - query_estimate_actuals: bash shells out to `python3 -c`; Python implements
#   the same stats logic natively.
# - estimate_general_tokens: bash shells out to `python3 -c` for the blend
#   calculation; Python does it natively.
# - GENERAL_ESTIMATES_FILE env var: bash defaults from env; Python accepts
#   explicit Path parameter with fallback to "general-estimates.jsonl".
# - Error return: bash returns JSON with "error" key on failure; Python raises
#   exceptions (FileNotFoundError, ValueError) — callers handle them.
# - find command for most recent JSONL: bash uses `find -printf '%T+ %p'`;
#   Python uses pathlib + stat().st_mtime for portable sorting.
"""Token estimation and actual usage tracking.

Provides functions to:
- Read Claude Code session JSONL files and extract token usage.
- Append calibration records to ``general-estimates.jsonl``.
- Query per-activity-type statistics from the JSONL log.
- Compute calibrated token estimates via graduated blending.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Default estimates file (relative to repo root)
_DEFAULT_ESTIMATES_FILE = Path("general-estimates.jsonl")


# ── Public API ────────────────────────────────────────────────────────────────


def get_session_actual_tokens(
    jsonl_path: Path | None = None,
) -> dict[str, object]:
    """Read Claude Code session JSONL and return actual token counts.

    Parses assistant entries from the JSONL file and sums their
    ``message.usage`` fields.

    Args:
        jsonl_path: Explicit path to a session JSONL file. If ``None``,
            finds the most recent JSONL under ``~/.claude/projects/``.

    Returns:
        Dict with keys: ``input_tokens``, ``output_tokens``,
        ``cache_creation_tokens``, ``cache_read_tokens``, ``active_tokens``,
        ``cumulative_tokens``, ``total_tokens``, ``api_calls``, ``source``.

    Raises:
        FileNotFoundError: If no JSONL file is found or the specified path
            does not exist.
    """
    if jsonl_path is None:
        jsonl_path = _find_most_recent_session_jsonl()

    if not jsonl_path.exists():
        raise FileNotFoundError(f"JSONL file not found: {jsonl_path}")

    input_total = 0
    output_total = 0
    cache_creation_total = 0
    cache_read_total = 0
    api_calls = 0

    for line in jsonl_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if data.get("type") != "assistant":
            continue
        usage = data.get("message", {})
        if isinstance(usage, dict):
            usage = usage.get("usage", {})
        else:
            continue
        if not isinstance(usage, dict) or not usage:
            continue
        api_calls += 1
        input_total += _int_from(usage.get("input_tokens"))
        output_total += _int_from(usage.get("output_tokens"))
        cache_creation_total += _int_from(
            usage.get("cache_creation_input_tokens")
        )
        cache_read_total += _int_from(usage.get("cache_read_input_tokens"))

    active = input_total + output_total
    cumulative = active + cache_creation_total + cache_read_total

    return {
        "input_tokens": input_total,
        "output_tokens": output_total,
        "cache_creation_tokens": cache_creation_total,
        "cache_read_tokens": cache_read_total,
        "active_tokens": active,
        "cumulative_tokens": cumulative,
        "total_tokens": cumulative,
        "api_calls": api_calls,
        "source": "jsonl_direct",
    }


def append_general_estimate(
    record: dict[str, object],
    estimates_file: Path | None = None,
) -> None:
    """Validate and append a JSON record to the estimates JSONL file.

    Args:
        record: The record to append. Must be JSON-serializable.
        estimates_file: Path to the JSONL file. Defaults to
            ``general-estimates.jsonl`` in the current directory.

    Raises:
        ValueError: If *record* is not a dict or cannot be serialized.
    """
    if not isinstance(record, dict):
        raise ValueError(
            f"record must be a dict, got {type(record).__name__}"
        )

    path = estimates_file or _DEFAULT_ESTIMATES_FILE

    # Validate round-trip serialization
    try:
        compact = json.dumps(record, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"record is not JSON-serializable: {exc}") from exc

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(compact + "\n")

    logger.info("Appended estimate record to %s", path)


def query_estimate_actuals(
    activity_type: str | None = None,
    estimates_file: Path | None = None,
) -> dict[str, object]:
    """Return per-activity-type statistics from the estimates JSONL.

    Args:
        activity_type: Filter to a specific activity type. ``None`` returns
            aggregate stats across all types.
        estimates_file: Path to the JSONL file. Defaults to
            ``general-estimates.jsonl``.

    Returns:
        Dict with keys: ``activity_type``, ``sample_count``,
        ``avg_active_tokens``, ``min_active``, ``max_active``,
        ``avg_estimation_error_pct``, ``calibration_ready``.
    """
    path = estimates_file or _DEFAULT_ESTIMATES_FILE
    label = activity_type or "all"

    if not path.exists():
        return {
            "activity_type": label,
            "sample_count": 0,
            "calibration_ready": False,
        }

    entries: list[dict[str, int]] = []

    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue
        if activity_type and entry.get("activity_type") != activity_type:
            continue

        # Prefer active_tokens, fall back to approx_actual_tokens
        tokens = _int_from(
            entry.get("active_tokens", entry.get("approx_actual_tokens"))
        )
        if tokens > 0:
            entries.append(
                {
                    "tokens": tokens,
                    "estimated": _int_from(
                        entry.get("estimated_tokens_pre")
                    ),
                }
            )

    if not entries:
        return {
            "activity_type": label,
            "sample_count": 0,
            "calibration_ready": False,
        }

    tokens_list = [e["tokens"] for e in entries]
    errors: list[float] = []
    for e in entries:
        if e["estimated"] > 0 and e["tokens"] > 0:
            errors.append(
                ((e["estimated"] - e["tokens"]) / e["tokens"]) * 100
            )

    return {
        "activity_type": label,
        "sample_count": len(entries),
        "avg_active_tokens": int(sum(tokens_list) / len(tokens_list)),
        "min_active": min(tokens_list),
        "max_active": max(tokens_list),
        "avg_estimation_error_pct": (
            round(sum(errors) / len(errors), 1) if errors else None
        ),
        "calibration_ready": len(entries) >= 5,
    }


def estimate_general_tokens(
    activity_type: str,
    fallback_estimate: int,
    estimates_file: Path | None = None,
) -> int:
    """Return a calibrated token estimate for an activity type.

    Uses a graduated blend that shifts 20% per historical sample from
    the heuristic *fallback_estimate* toward actual measured averages,
    reaching 100% actuals at 5+ samples.

    Args:
        activity_type: The activity type key in the estimates JSONL.
        fallback_estimate: Heuristic estimate when no data exists.
        estimates_file: Path to the JSONL file.

    Returns:
        Integer token estimate.
    """
    stats = query_estimate_actuals(activity_type, estimates_file)
    sample_count = _int_from(stats.get("sample_count"))

    if sample_count == 0:
        return fallback_estimate

    avg = _int_from(stats.get("avg_active_tokens"))
    actuals_weight = min(sample_count * 0.2, 1.0)
    blended = int(avg * actuals_weight + fallback_estimate * (1.0 - actuals_weight))
    return blended


# ── Private helpers ───────────────────────────────────────────────────────────


def _int_from(val: object) -> int:
    """Coerce a value to int, defaulting to 0."""
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        return int(val)
    if isinstance(val, str):
        try:
            return int(val)
        except ValueError:
            return 0
    return 0


def _find_most_recent_session_jsonl() -> Path:
    """Find the most recent Claude session JSONL file.

    Searches ``~/.claude/projects/`` for ``*.jsonl`` files and returns the
    one with the most recent modification time.

    Raises:
        FileNotFoundError: If the projects directory does not exist or
            contains no JSONL files.
    """
    claude_projects_dir = Path.home() / ".claude" / "projects"

    if not claude_projects_dir.is_dir():
        raise FileNotFoundError(
            "Claude projects directory not found: "
            f"{claude_projects_dir}"
        )

    jsonl_files = list(claude_projects_dir.rglob("*.jsonl"))
    if not jsonl_files:
        raise FileNotFoundError(
            f"No JSONL session files found in {claude_projects_dir}"
        )

    # Sort by modification time, most recent first
    jsonl_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return jsonl_files[0]
