# CONVERSION CHANGELOG (from scripts/build-loop-local.sh lines 972–1073,
#   1672–1692, 1865–1947)
# - setup_branch_chained: accepts explicit parameters instead of reading
#   LAST_FEATURE_BRANCH / MAIN_BRANCH globals. Returns a BranchSetupResult
#   dataclass with the new branch name instead of setting globals.
# - setup_branch_independent: returns BranchSetupResult with branch name AND
#   worktree path. Does not cd — the caller uses the returned path.
# - setup_branch_sequential: returns BranchSetupResult with current branch.
# - cleanup_branch_chained: returns the new last_branch name instead of
#   setting LAST_FEATURE_BRANCH global.
# - cleanup_branch_independent: accepts worktree_path and project_dir
#   explicitly. Does not cd.
# - check_disk_space: accepts project_dir and min_mb explicitly instead of
#   reading globals. Raises InsufficientDiskSpaceError instead of exit 5.
# - cleanup_all_worktrees: pure function, no globals.
# - cleanup_merged_branches: accepts project_dir and main_branch explicitly.
# - Branch names use datetime.now() instead of shell $(date +%Y%m%d-%H%M%S).
"""Branch management for the SDD build loop.

Provides setup and cleanup functions for chained, independent (worktree),
and sequential branch strategies.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from auto_sdd.lib.reliability import AutoSddError

logger = logging.getLogger(__name__)


# ── Exceptions ───────────────────────────────────────────────────────────────


class InsufficientDiskSpaceError(AutoSddError):
    """Not enough disk space for worktree creation."""


class BranchSetupError(AutoSddError):
    """Failed to create or switch to a branch."""


# ── Data types ───────────────────────────────────────────────────────────────


@dataclass
class BranchSetupResult:
    """Result of a branch setup operation."""

    branch_name: str
    worktree_path: Path | None = None


# ── Helpers ──────────────────────────────────────────────────────────────────


def _run_git(
    args: list[str],
    project_dir: Path,
    *,
    timeout: int = 60,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run a git command in *project_dir*."""
    return subprocess.run(
        ["git", "-C", str(project_dir), *args],
        capture_output=True,
        text=True,
        check=check,
        timeout=timeout,
    )


def _timestamp_suffix() -> str:
    """Return a timestamp string for branch naming."""
    return datetime.now().strftime("%Y%m%d-%H%M%S")


# ── Branch setup ─────────────────────────────────────────────────────────────


def setup_branch_chained(
    project_dir: Path,
    feature_name: str,
    last_branch: str | None,
    main_branch: str,
) -> BranchSetupResult:
    """Create a chained branch from the previous feature branch or main.

    Stashes any dirty state before switching branches.

    Args:
        project_dir: Git repo root.
        feature_name: Feature name (for logging only; branch name uses timestamp).
        last_branch: Previous feature branch, or None for first feature.
        main_branch: Base branch name (e.g. ``"main"``).

    Returns:
        BranchSetupResult with the new branch name.

    Raises:
        BranchSetupError: If branch creation fails.
    """
    # Stash to prevent cascade failures from dirty worktrees
    _run_git(["add", "-A"], project_dir)
    _run_git(
        ["stash", "push", "-m", "auto-stash before branch switch"],
        project_dir,
    )

    base_branch = last_branch or main_branch

    if base_branch != main_branch:
        logger.info("Branching from previous feature: %s", base_branch)
        result = _run_git(["checkout", base_branch], project_dir)
        if result.returncode != 0:
            logger.warning(
                "Previous branch %s not found, using %s",
                base_branch,
                main_branch,
            )
            base_branch = main_branch
            _run_git(["checkout", base_branch], project_dir, check=True)
    else:
        logger.info("Branching from %s (first feature)", main_branch)
        _run_git(["checkout", main_branch], project_dir, check=True)

    new_branch = f"auto/chained-{_timestamp_suffix()}"
    create_result = _run_git(["checkout", "-b", new_branch], project_dir)
    if create_result.returncode != 0:
        raise BranchSetupError(f"Failed to create branch {new_branch}")

    logger.info(
        "✓ Created branch: %s (from %s)", new_branch, base_branch
    )
    return BranchSetupResult(branch_name=new_branch)


def setup_branch_independent(
    project_dir: Path,
    feature_name: str,
    main_branch: str,
    min_disk_mb: int = 5120,
) -> BranchSetupResult:
    """Create a worktree + branch for independent building.

    Args:
        project_dir: Git repo root.
        feature_name: Feature name (for logging).
        main_branch: Base branch name.
        min_disk_mb: Minimum disk space in MB.

    Returns:
        BranchSetupResult with branch name and worktree path.

    Raises:
        InsufficientDiskSpaceError: If disk space is below minimum.
        BranchSetupError: If worktree creation fails.
    """
    check_disk_space(project_dir, min_disk_mb)

    worktree_name = f"auto-independent-{_timestamp_suffix()}"
    worktree_path = project_dir / ".build-worktrees" / worktree_name

    worktree_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Creating worktree: %s (from %s)", worktree_name, main_branch)
    branch_name = f"auto/{worktree_name}"
    result = _run_git(
        [
            "worktree", "add", "-b", branch_name,
            str(worktree_path), main_branch,
        ],
        project_dir,
    )
    if result.returncode != 0:
        raise BranchSetupError(
            f"Failed to create worktree {worktree_name}: {result.stderr}"
        )

    logger.info(
        "✓ Created worktree: %s at %s", worktree_name, worktree_path
    )
    return BranchSetupResult(
        branch_name=branch_name, worktree_path=worktree_path
    )


def setup_branch_sequential(project_dir: Path) -> BranchSetupResult:
    """No-op setup for sequential strategy — uses current branch.

    Args:
        project_dir: Git repo root.

    Returns:
        BranchSetupResult with the current branch name.
    """
    result = _run_git(["branch", "--show-current"], project_dir)
    branch = result.stdout.strip() or "main"
    logger.info("Building on current branch: %s", branch)
    return BranchSetupResult(branch_name=branch)


# ── Branch cleanup ───────────────────────────────────────────────────────────


def cleanup_branch_chained(current_branch: str) -> str:
    """Record the current branch as the base for the next chained feature.

    Args:
        current_branch: The branch that was just built on.

    Returns:
        The branch name to use as ``last_branch`` for the next feature.
    """
    logger.info("Next feature will branch from: %s", current_branch)
    return current_branch


def cleanup_branch_independent(
    worktree_path: Path | None,
    project_dir: Path,
    branch_name: str = "",
) -> None:
    """Remove a worktree after an independent build.

    Args:
        worktree_path: Path to the worktree directory.
        project_dir: Git repo root.
        branch_name: Branch name (for logging only).
    """
    if worktree_path is None or not worktree_path.is_dir():
        return

    logger.info("Removing worktree: %s", worktree_path)
    result = _run_git(
        ["worktree", "remove", str(worktree_path)], project_dir
    )
    if result.returncode != 0:
        logger.warning(
            "Failed to remove worktree, may need manual cleanup: %s",
            result.stderr,
        )
    else:
        logger.info(
            "✓ Cleaned up worktree (kept branch: %s)", branch_name
        )


def cleanup_branch_sequential() -> None:
    """No-op cleanup for sequential strategy."""


# ── Disk space ───────────────────────────────────────────────────────────────


def check_disk_space(project_dir: Path, min_mb: int = 5120) -> None:
    """Check that available disk space exceeds the minimum.

    Args:
        project_dir: Path to check disk space for.
        min_mb: Minimum megabytes required.

    Raises:
        InsufficientDiskSpaceError: If available space is below minimum.
    """
    try:
        usage = shutil.disk_usage(str(project_dir))
        available_mb = usage.free // (1024 * 1024)
    except OSError:
        logger.warning("Could not determine available disk space")
        return

    if available_mb < min_mb:
        raise InsufficientDiskSpaceError(
            f"Insufficient disk space: {available_mb}MB available, "
            f"{min_mb}MB required per worktree. "
            f"Use BRANCH_STRATEGY=sequential to avoid worktrees."
        )

    logger.info(
        "Disk space OK: %dMB available (%dMB required per worktree)",
        available_mb,
        min_mb,
    )


# ── Bulk cleanup ─────────────────────────────────────────────────────────────


def cleanup_all_worktrees(project_dir: Path) -> None:
    """Remove all worktrees under ``.build-worktrees``.

    Args:
        project_dir: Git repo root.
    """
    worktrees_dir = project_dir / ".build-worktrees"
    if not worktrees_dir.is_dir():
        return

    logger.info("Cleaning up remaining worktrees...")
    for wt in worktrees_dir.iterdir():
        if wt.is_dir():
            _run_git(["worktree", "remove", str(wt)], project_dir)

    # Remove the parent directory if empty
    try:
        worktrees_dir.rmdir()
    except OSError:
        pass


def cleanup_merged_branches(
    project_dir: Path,
    main_branch: str,
) -> int:
    """Delete merged ``auto/*`` branches.

    Args:
        project_dir: Git repo root.
        main_branch: The base branch to check merges against.

    Returns:
        Number of branches deleted.
    """
    result = _run_git(["branch", "--merged"], project_dir)

    if result.returncode != 0:
        return 0

    merged: list[str] = []
    for line in result.stdout.splitlines():
        branch = line.strip().lstrip("* ")
        if branch.startswith("auto/chained-") or branch.startswith(
            "auto/independent-"
        ):
            merged.append(branch)

    if not merged:
        logger.info("No merged auto-sdd branches to clean up")
        return 0

    logger.info("Cleaning up merged auto-sdd branches:")
    count = 0
    for branch in merged:
        logger.info("  Deleting: %s", branch)
        del_result = _run_git(["branch", "-d", branch], project_dir)
        if del_result.returncode != 0:
            logger.warning("  Failed to delete: %s", branch)
        else:
            count += 1

    logger.info("✓ Cleaned up %d merged branch(es)", count)
    return count
