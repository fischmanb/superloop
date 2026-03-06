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

# Default estimates file — resolve relative to repo root, not CWD.
# The repo root is 2 levels up from this file (lib/ -> auto_sdd/ -> py/ -> repo)
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_DEFAULT_ESTIMATES_FILE = _REPO_ROOT / "general-estimates.jsonl"


# ── Public API ────────────────────────────────────────────────────────────────


def get_session_actual_tokens(
    jsonl_path: Path | None = None,
    project_dir: Path | None = None,
    after: str | None = None,
) -> dict[str, object]:
    """Read Claude Code session JSONL and return actual token counts.

    Parses assistant entries from the JSONL file and sums their
    ``message.usage`` fields.

    When *jsonl_path* is ``None``, searches for session files scoped to
    *project_dir* (or the most recent globally if *project_dir* is also
    ``None``).  If *after* is given (ISO timestamp), only session files
    modified after that time are included.  Multiple session files are
    summed to handle compaction splits.

    Args:
        jsonl_path: Explicit path to a session JSONL file.
        project_dir: Scope session file search to this project directory.
        after: ISO timestamp — only include session files modified after
            this time.

    Returns:
        Dict with keys: ``input_tokens``, ``output_tokens``,
        ``cache_creation_tokens``, ``cache_read_tokens``, ``active_tokens``,
        ``cumulative_tokens``, ``total_tokens``, ``api_calls``, ``source``,
        ``files_summed``.

    Raises:
        FileNotFoundError: If no JSONL file is found or the specified path
            does not exist.
    """
    if jsonl_path is not None:
        if not jsonl_path.exists():
            raise FileNotFoundError(f"JSONL file not found: {jsonl_path}")
        paths = [jsonl_path]
    else:
        paths = _find_session_jsonls(project_dir=project_dir, after=after)

    input_total = 0
    output_total = 0
    cache_creation_total = 0
    cache_read_total = 0
    api_calls = 0

    for p in paths:
        if not p.exists():
            continue
        for line in p.read_text().splitlines():
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
            cache_read_total += _int_from(
                usage.get("cache_read_input_tokens")
            )

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
        "files_summed": len(paths),
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
    cost_values: list[float] = []
    duration_values: list[int] = []
    source_counts: dict[str, int] = {}

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

        # Track source breakdown
        src = str(entry.get("source", "unknown"))
        source_counts[src] = source_counts.get(src, 0) + 1

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

        # Collect cost and duration from wrapper records
        raw_cost = entry.get("cost_usd")
        if isinstance(raw_cost, (int, float)) and raw_cost > 0:
            cost_values.append(float(raw_cost))
        raw_dur = entry.get("duration_ms")
        if isinstance(raw_dur, (int, float)) and raw_dur > 0:
            duration_values.append(int(raw_dur))

    if not entries:
        result_dict: dict[str, object] = {
            "activity_type": label,
            "sample_count": 0,
            "calibration_ready": False,
        }
        if source_counts:
            result_dict["source_breakdown"] = source_counts
        return result_dict

    tokens_list = [e["tokens"] for e in entries]
    errors: list[float] = []
    for e in entries:
        if e["estimated"] > 0 and e["tokens"] > 0:
            errors.append(
                ((e["estimated"] - e["tokens"]) / e["tokens"]) * 100
            )

    result_dict = {
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

    if cost_values:
        result_dict["avg_cost_usd"] = round(
            sum(cost_values) / len(cost_values), 6
        )
    if duration_values:
        result_dict["avg_duration_ms"] = int(
            sum(duration_values) / len(duration_values)
        )
    if source_counts:
        result_dict["source_breakdown"] = source_counts

    return result_dict


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


def estimate_from_history(
    activity_type: str,
    fallback: int = 30000,
    estimates_file: Path | None = None,
) -> dict[str, object]:
    """Return a calibrated estimate with reasoning for a prompt.

    Queries historical data for the activity type and returns a dict
    suitable for inclusion in an agent prompt's token budget section.

    Returns:
        Dict with: ``estimated_tokens``, ``basis`` (str explaining the
        estimate), ``sample_count``, ``avg_actual``, ``avg_cost_usd``.
    """
    stats = query_estimate_actuals(activity_type, estimates_file)
    sample_count = _int_from(stats.get("sample_count"))
    avg_actual = _int_from(stats.get("avg_active_tokens"))
    avg_cost: float | None = None
    raw_cost = stats.get("avg_cost_usd")
    if isinstance(raw_cost, (int, float)):
        avg_cost = float(raw_cost)

    if sample_count >= 3:
        return {
            "estimated_tokens": avg_actual,
            "basis": f"historical average from {sample_count} samples",
            "sample_count": sample_count,
            "avg_actual": avg_actual,
            "avg_cost_usd": avg_cost,
        }

    if sample_count >= 1:
        # Blend: weight actuals by 20% per sample, rest is fallback
        actuals_weight = sample_count * 0.2
        blended = int(
            avg_actual * actuals_weight + fallback * (1.0 - actuals_weight)
        )
        return {
            "estimated_tokens": blended,
            "basis": f"blended ({sample_count} samples + fallback)",
            "sample_count": sample_count,
            "avg_actual": avg_actual,
            "avg_cost_usd": avg_cost,
        }

    # 0 samples — try prefix match for similar activity types
    path = estimates_file or _DEFAULT_ESTIMATES_FILE
    if path.exists():
        prefix = activity_type.split("_")[0] + "_"
        similar_stats = query_estimate_actuals(None, estimates_file)
        # Re-scan for prefix matches
        similar_count = 0
        similar_total = 0
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
            entry_type = entry.get("activity_type", "")
            if isinstance(entry_type, str) and entry_type.startswith(prefix):
                tokens = _int_from(
                    entry.get(
                        "active_tokens", entry.get("approx_actual_tokens")
                    )
                )
                if tokens > 0:
                    similar_count += 1
                    similar_total += tokens

        if similar_count > 0:
            similar_avg = similar_total // similar_count
            return {
                "estimated_tokens": similar_avg,
                "basis": (
                    f"similar activity prefix '{prefix}*' "
                    f"from {similar_count} samples"
                ),
                "sample_count": 0,
                "avg_actual": 0,
                "avg_cost_usd": None,
            }

    return {
        "estimated_tokens": fallback,
        "basis": "no historical data, using fallback",
        "sample_count": 0,
        "avg_actual": 0,
        "avg_cost_usd": None,
    }


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


def _encode_project_dir(project_dir: Path) -> str:
    """Encode a project directory path to Claude's session dir name.

    Claude Code stores session files under
    ``~/.claude/projects/{encoded_cwd}/`` where the CWD is encoded
    by replacing ``/`` with ``-``.
    """
    return str(project_dir.resolve()).replace("/", "-")


def _find_session_jsonls(
    project_dir: Path | None = None,
    after: str | None = None,
) -> list[Path]:
    """Find Claude session JSONL files, optionally scoped by project.

    Args:
        project_dir: If given, only search in the session dir for this
            project CWD. If ``None``, searches all project dirs and
            returns the single most recent file (legacy behavior).
        after: ISO timestamp string. If given, only return files whose
            mtime is after this timestamp. Handles compaction splits by
            returning ALL matching files so they can be summed.

    Returns:
        List of Path objects to session JSONL files, newest first.

    Raises:
        FileNotFoundError: If no matching session files are found.
    """
    claude_projects_dir = Path.home() / ".claude" / "projects"

    if not claude_projects_dir.is_dir():
        raise FileNotFoundError(
            "Claude projects directory not found: "
            f"{claude_projects_dir}"
        )

    if project_dir is not None:
        encoded = _encode_project_dir(project_dir)
        search_dir = claude_projects_dir / encoded
        if not search_dir.is_dir():
            raise FileNotFoundError(
                f"No session dir for project {project_dir}: "
                f"expected {search_dir}"
            )
        jsonl_files = list(search_dir.glob("*.jsonl"))
    else:
        jsonl_files = list(claude_projects_dir.rglob("*.jsonl"))

    if not jsonl_files:
        raise FileNotFoundError(
            f"No JSONL session files found in {claude_projects_dir}"
        )

    # Filter by time if requested
    if after is not None:
        from datetime import datetime, timezone

        try:
            cutoff = datetime.fromisoformat(after)
            if cutoff.tzinfo is None:
                cutoff = cutoff.replace(tzinfo=timezone.utc)
            cutoff_ts = cutoff.timestamp()
        except ValueError:
            logger.warning("Invalid 'after' timestamp: %s, ignoring", after)
            cutoff_ts = 0.0

        jsonl_files = [
            f for f in jsonl_files if f.stat().st_mtime > cutoff_ts
        ]

        if not jsonl_files:
            raise FileNotFoundError(
                f"No session files modified after {after}"
            )

    # Sort by mtime, newest first
    jsonl_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    # If project_dir was given, return ALL matching files (sum for compaction)
    # If no project_dir, return just the most recent (legacy fallback)
    if project_dir is not None:
        return jsonl_files
    return jsonl_files[:1]


def _find_most_recent_session_jsonl() -> Path:
    """Find the most recent Claude session JSONL file.

    .. deprecated::
        Use ``_find_session_jsonls(project_dir=...)`` instead for
        project-scoped, compaction-safe session discovery.
    """
    results = _find_session_jsonls()
    return results[0]
