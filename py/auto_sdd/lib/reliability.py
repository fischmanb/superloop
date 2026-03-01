# CONVERSION CHANGELOG (from lib/reliability.sh)
# - completed_features_json() removed: bash-ism. write_state() now accepts
#   list[str] directly and serializes internally.
# - DriftPair fields: spec_file (Path) and source_files (str) instead of
#   bash's colon-delimited pair string. Typed for clarity.
# - Feature dataclass: has id (int), name (str), complexity (str) instead of
#   bash's pipe-delimited output string.
# - ResumeState: field names follow Python conventions (branch_strategy,
#   completed_features) instead of bash's RESUME_INDEX/RESUME_STRATEGY globals.
#   Includes timestamp field persisted in JSON.
# - count_files() removed: bash-specific nameref pattern. Not in interface
#   contract. Callers can use pathlib directly.
# - acquire_lock uses fcntl.flock() + PID-in-file stale detection instead of
#   bash's simple file-exists check. release_lock removes both lockfile and fd.
# - run_agent_with_backoff returns exit code instead of setting global
#   AGENT_EXIT. Uses subprocess.run() instead of bash pipe-to-tee.
# - Signal emission uses logging instead of echo, consistent with conventions.
"""Shared reliability utilities for SDD orchestration scripts.

Provides: locking, resume-state persistence, exponential backoff for agent
calls, context-budget truncation, dependency-graph cycle detection,
topological sort of pending features, and parallel drift checking.
"""
from __future__ import annotations

import fcntl
import json
import logging
import multiprocessing
import os
import re
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)


# ── Exception hierarchy ──────────────────────────────────────────────────────
# Defined here until errors.py is created in a later conversion phase.


class AutoSddError(Exception):
    """Base for all auto-sdd errors."""


class LockContentionError(AutoSddError):
    """Another instance holds the lock."""


class AgentTimeoutError(AutoSddError):
    """Claude agent exceeded timeout."""


class CircularDependencyError(AutoSddError):
    """Roadmap dependency graph has a cycle."""


# ── Data structures ──────────────────────────────────────────────────────────


@dataclass
class ResumeState:
    """Persisted build-loop resume state."""

    feature_index: int
    branch_strategy: str
    completed_features: list[str]
    current_branch: str
    timestamp: str


@dataclass
class Feature:
    """A pending feature from the roadmap, used in topological ordering."""

    id: int
    name: str
    complexity: str


@dataclass
class DriftPair:
    """A spec-file / source-files pair for drift checking."""

    spec_file: Path
    source_files: str


# ── Concurrency lock ─────────────────────────────────────────────────────────

# Module-level dict to track open lock file descriptors by path.
_lock_fds: dict[str, int] = {}


def acquire_lock(lock_file: Path) -> None:
    """Acquire a process-level file lock.

    If the lock file already exists and contains a PID of a live process,
    raises ``LockContentionError``. Stale locks (dead PID) are cleaned up
    automatically.

    The lock is held via ``fcntl.flock()`` AND a PID written to the file
    for stale-lock detection by other processes.

    Raises:
        LockContentionError: If the lock is held by a live process.
    """
    lock_file.parent.mkdir(parents=True, exist_ok=True)

    # Check for existing lock file with PID-based stale detection
    if lock_file.exists():
        try:
            existing_pid_str = lock_file.read_text().strip()
            if existing_pid_str:
                existing_pid = int(existing_pid_str)
                try:
                    os.kill(existing_pid, 0)
                    # Process is alive — lock is held
                    raise LockContentionError(
                        f"Another instance is already running (PID: {existing_pid}). "
                        f"Lock file: {lock_file}. "
                        f"If this is stale, remove {lock_file} manually."
                    )
                except OSError:
                    # Process is dead — stale lock
                    logger.warning(
                        "Removing stale lock file (PID %d no longer running)",
                        existing_pid,
                    )
                    lock_file.unlink(missing_ok=True)
        except (ValueError, FileNotFoundError):
            # Corrupt or vanished lock file — clean up
            lock_file.unlink(missing_ok=True)

    # Create lock file with our PID
    fd = os.open(str(lock_file), os.O_CREAT | os.O_WRONLY | os.O_TRUNC)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        raise LockContentionError(
            f"Could not acquire flock on {lock_file}."
        )
    os.write(fd, f"{os.getpid()}\n".encode())
    os.fsync(fd)
    _lock_fds[str(lock_file)] = fd


def release_lock(lock_file: Path) -> None:
    """Release a previously acquired lock and remove the lock file."""
    key = str(lock_file)
    fd = _lock_fds.pop(key, None)
    if fd is not None:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            os.close(fd)
        except OSError:
            pass
    lock_file.unlink(missing_ok=True)


# ── Resume state persistence ─────────────────────────────────────────────────


def write_state(
    state_file: Path,
    feature_index: int,
    strategy: str,
    completed_features: list[str],
    current_branch: str,
) -> None:
    """Write build-loop resume state atomically (temp file then rename).

    The JSON format is compatible with the bash ``read_state`` parser so
    that bash and Python scripts can coexist during the migration period.
    """
    state_file.parent.mkdir(parents=True, exist_ok=True)

    state = {
        "feature_index": feature_index,
        "branch_strategy": strategy,
        "completed_features": completed_features,
        "current_branch": current_branch,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    data = json.dumps(state, indent=2) + "\n"

    fd, tmp_path = tempfile.mkstemp(
        dir=str(state_file.parent), prefix=state_file.stem
    )
    try:
        with os.fdopen(fd, "w") as f:
            f.write(data)
        os.rename(tmp_path, str(state_file))
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def read_state(state_file: Path) -> ResumeState | None:
    """Read persisted resume state. Returns ``None`` if the file is missing."""
    if not state_file.exists():
        return None

    raw = json.loads(state_file.read_text())

    return ResumeState(
        feature_index=int(raw["feature_index"]),
        branch_strategy=str(raw["branch_strategy"]),
        completed_features=[str(n) for n in raw.get("completed_features", [])],
        current_branch=str(raw["current_branch"]),
        timestamp=str(raw.get("timestamp", "")),
    )


def clean_state(state_file: Path) -> None:
    """Remove the resume state file if it exists."""
    state_file.unlink(missing_ok=True)


# ── Exponential backoff for agent calls ──────────────────────────────────────

_RATE_LIMIT_RE = re.compile(
    r"rate.?limit|429|too many requests|overloaded|capacity", re.IGNORECASE
)


def run_agent_with_backoff(
    output_file: Path,
    cmd: list[str],
    *,
    max_retries: int = 5,
    backoff_max: int = 60,
) -> int:
    """Run *cmd* with exponential backoff on rate-limit failures.

    The command's combined stdout+stderr is written to *output_file* on each
    attempt. If the command fails with a rate-limit indicator in its output,
    it is retried up to *max_retries* times with exponential backoff capped
    at *backoff_max* seconds.

    Returns:
        The exit code of the last invocation (0 on success).

    Raises:
        AgentTimeoutError: After exhausting all retries due to rate limiting.
    """
    exit_code = 0

    for attempt in range(max_retries + 1):
        if attempt > 0:
            backoff = min(2**attempt, backoff_max)
            logger.warning(
                "Rate limit detected, retrying in %ds (attempt %d/%d)...",
                backoff,
                attempt,
                max_retries,
            )
            time.sleep(backoff)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
        )
        combined = result.stdout + result.stderr
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(combined)
        exit_code = result.returncode

        if exit_code != 0 and _RATE_LIMIT_RE.search(combined):
            continue

        # Not a rate-limit error — return immediately
        return exit_code

    raise AgentTimeoutError(
        f"Agent failed after {max_retries} retries due to rate limiting"
    )


# ── Context budget management ────────────────────────────────────────────────

# Lines matching these patterns are kept during truncation.
_GHERKIN_RE = re.compile(
    r"^(\s*(Feature|Scenario|Given|When|Then|And|But|Background|Rule)[:\s])"
    r"|^(---$)"
    r"|^(#+\s)"
    r"|^(\*\*)",
)


def truncate_for_context(
    file_path: Path, max_tokens: int = 100_000
) -> str:
    """Return the contents of *file_path*, truncating if over context budget.

    Token estimation: 4 characters ≈ 1 token. If the file exceeds 50% of
    *max_tokens*, only YAML frontmatter, headings, bold lines, and Gherkin
    scenario lines are returned.

    Returns an empty string for missing or empty files.
    """
    if not file_path.exists():
        return ""

    content = file_path.read_text()
    if not content:
        return ""

    estimated_tokens = len(content) // 4
    budget_half = max_tokens // 2

    if estimated_tokens <= budget_half:
        return content

    logger.warning(
        "Spec file exceeds 50%% of context budget (~%d tokens, budget: %d)",
        estimated_tokens,
        max_tokens,
    )
    logger.warning(
        "Truncating to Gherkin scenarios only (removing mockups and "
        "non-essential content)"
    )

    # Extract frontmatter + Gherkin lines (mirrors the bash awk filter)
    kept: list[str] = []
    in_frontmatter = False
    frontmatter_count = 0

    for line in content.splitlines():
        if line.rstrip() == "---":
            frontmatter_count += 1
            if frontmatter_count <= 2:
                kept.append(line)
                if frontmatter_count == 1:
                    in_frontmatter = True
                else:
                    in_frontmatter = False
                continue

        if in_frontmatter:
            kept.append(line)
            continue

        # Headings
        if re.match(r"^#+\s", line):
            kept.append(line)
            continue

        # Gherkin keywords
        if re.match(
            r"^\s*(Feature|Scenario|Given|When|Then|And|But|Background|Rule)[:\s]",
            line,
        ):
            kept.append(line)
            continue

        # Bold lines
        if line.startswith("**"):
            kept.append(line)
            continue

    return "\n".join(kept)


# ── Circular dependency detection ────────────────────────────────────────────

# Regex for roadmap table rows: | <id> | Feature | Source | Jira | Complexity | Deps | Status |
_ROADMAP_ROW_RE = re.compile(r"^\|\s*(\d+)\s*\|")


def _parse_roadmap_rows(
    roadmap: Path,
) -> list[tuple[str, str, str, str, str]]:
    """Parse roadmap table rows into (id, name, complexity, deps, status) tuples."""
    rows: list[tuple[str, str, str, str, str]] = []
    if not roadmap.exists():
        return rows

    for line in roadmap.read_text().splitlines():
        if not _ROADMAP_ROW_RE.match(line):
            continue
        cols = [c.strip() for c in line.split("|")]
        # Split by | gives ['', id, name, source, jira, complexity, deps, status, '']
        if len(cols) < 9:
            continue
        fid = cols[1]
        if not fid.isdigit():
            continue
        fname = cols[2]
        fcmplx = cols[5]
        fdeps = cols[6]
        fstatus = cols[7]
        rows.append((fid, fname, fcmplx, fdeps, fstatus))
    return rows


def check_circular_deps(project_dir: Path) -> None:
    """Detect cycles in the roadmap dependency graph.

    Reads ``{project_dir}/.specs/roadmap.md`` and performs DFS cycle detection.

    Raises:
        CircularDependencyError: If a cycle is found.
    """
    roadmap = project_dir / ".specs" / "roadmap.md"
    if not roadmap.exists():
        return

    rows = _parse_roadmap_rows(roadmap)
    if not rows:
        return

    # Build adjacency list from deps column
    adj: dict[str, list[str]] = {}
    nodes: set[str] = set()

    for fid, _name, _cmplx, fdeps, _status in rows:
        if fdeps == "-" or not fdeps:
            continue
        dep_ids: list[str] = []
        for part in fdeps.split(","):
            dep = re.sub(r"[^0-9]", "", part.strip())
            if dep:
                dep_ids.append(dep)
                nodes.add(dep)
        if dep_ids:
            adj[fid] = dep_ids
            nodes.add(fid)

    if not nodes:
        return

    # DFS cycle detection
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {n: WHITE for n in nodes}

    def dfs(node: str, path: str) -> None:
        if color.get(node, WHITE) == GRAY:
            raise CircularDependencyError(
                f"Circular dependency detected in roadmap! "
                f"CYCLE: {path} -> {node}. "
                f"Fix the dependency cycle in .specs/roadmap.md before building."
            )
        if color.get(node, WHITE) == BLACK:
            return
        color[node] = GRAY
        for neighbor in adj.get(node, []):
            dfs(neighbor, f"{path} -> {neighbor}")
        color[node] = BLACK

    for node in nodes:
        if color.get(node, WHITE) == WHITE:
            dfs(node, node)


# ── Topological sort of pending features ─────────────────────────────────────


def emit_topo_order(project_dir: Path) -> list[Feature]:
    """Return pending (⬜) features from the roadmap in topological order.

    Uses Kahn's algorithm (BFS). Dependencies pointing to completed (✅)
    features are considered satisfied and ignored. Features with other
    statuses (🔄, ⏸️, ❌) are skipped.
    """
    roadmap = project_dir / ".specs" / "roadmap.md"
    if not roadmap.exists():
        return []

    rows = _parse_roadmap_rows(roadmap)
    if not rows:
        return []

    completed: set[str] = set()
    pending_name: dict[str, str] = {}
    pending_cmplx: dict[str, str] = {}
    pending_ids: list[str] = []

    for fid, fname, fcmplx, _fdeps, fstatus in rows:
        if "\u2705" in fstatus:  # ✅
            completed.add(fid)
        elif "\u2b1c" in fstatus:  # ⬜
            pending_name[fid] = fname
            pending_cmplx[fid] = fcmplx
            pending_ids.append(fid)

    if not pending_ids:
        return []

    # Build in-degree map: only count deps on other pending features
    in_degree: dict[str, int] = {fid: 0 for fid in pending_ids}
    pending_deps: dict[str, list[str]] = {fid: [] for fid in pending_ids}

    for fid, _fname, _fcmplx, fdeps, _fstatus in rows:
        if fid not in pending_name:
            continue
        if fdeps == "-" or not fdeps:
            continue
        for part in fdeps.split(","):
            dep = re.sub(r"[^0-9]", "", part.strip())
            if not dep:
                continue
            if dep in completed:
                continue
            if dep in pending_name:
                pending_deps[fid].append(dep)
                in_degree[fid] += 1

    # Kahn's algorithm
    queue: list[str] = [fid for fid in pending_ids if in_degree[fid] == 0]
    sorted_ids: list[str] = []
    qi = 0

    while qi < len(queue):
        current = queue[qi]
        qi += 1
        sorted_ids.append(current)

        for fid in pending_ids:
            if current in pending_deps[fid]:
                in_degree[fid] -= 1
                if in_degree[fid] == 0:
                    queue.append(fid)

    return [
        Feature(id=int(fid), name=pending_name[fid], complexity=pending_cmplx[fid])
        for fid in sorted_ids
    ]


# ── Parallel validation ──────────────────────────────────────────────────────


def get_cpu_count() -> int:
    """Return the number of available CPUs, defaulting to 4 if unknown."""
    try:
        return multiprocessing.cpu_count() or 4
    except NotImplementedError:
        return 4


def run_parallel_drift_checks(
    pairs: list[DriftPair],
    check_fn: Callable[[Path, str], bool],
) -> bool:
    """Run drift checks in parallel using a thread pool.

    Calls ``check_fn(pair.spec_file, pair.source_files)`` for each pair.

    Returns:
        ``True`` if all checks passed, ``False`` if any failed.
    """
    if not pairs:
        return True

    max_workers = min(get_cpu_count(), len(pairs))
    logger.info(
        "Running parallel drift checks (%d pairs, max %d workers)...",
        len(pairs),
        max_workers,
    )

    any_failed = False

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(check_fn, pair.spec_file, pair.source_files): pair
            for pair in pairs
        }
        for future in as_completed(futures):
            pair = futures[future]
            try:
                passed = future.result()
            except Exception:
                logger.exception(
                    "Drift check raised an exception for %s", pair.spec_file
                )
                passed = False
            if not passed:
                logger.warning(
                    "Parallel drift check failed for: %s", pair.spec_file.name
                )
                any_failed = True

    return not any_failed
