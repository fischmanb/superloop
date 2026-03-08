"""Write learning entries to both project-local and repo-level learnings files.

This module is project-agnostic: it writes structured findings from runtime
events (drift, retries, build failures) to two locations:

  1. <project_dir>/.specs/learnings/general.md  — project-local, read by
     build agents for that project via generate_eval_prompt learnings injection.

  2. <repo_dir>/learnings/pending.md  — repo-level, queued for human review
     and promotion to the appropriate repo learnings file (failure-patterns.md,
     domain-knowledge.md, etc.).

Entries are append-only. IDs are NOT auto-assigned (those are human-managed).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Repo root derivation ─────────────────────────────────────────────────────

def _default_repo_dir() -> Path:
    """Derive the superloop repo root from this file's install location.

    Layout: <repo>/py/auto_sdd/lib/learnings_writer.py
    So repo root is 3 parents up from this file's parent.
    """
    return Path(__file__).resolve().parents[3]


# ── Public API ───────────────────────────────────────────────────────────────

def write_learning(
    *,
    summary: str,
    detail: str,
    category: str,
    project_name: str,
    feature_name: str = "",
    project_dir: Path | None = None,
    repo_dir: Path | None = None,
) -> None:
    """Append a learning entry to project-local and repo-level learnings.

    Args:
        summary: One-line description (used as heading).
        detail: Full description of the finding.
        category: Type tag, e.g. "drift", "retry", "build-failure".
        project_name: Name of the target project (e.g. "compstak-sitdeck").
        feature_name: Optional feature name for context.
        project_dir: If provided, write to <project_dir>/.specs/learnings/general.md.
        repo_dir: Superloop repo root. Defaults to auto-derived from module path.
            Writes to <repo_dir>/learnings/pending.md.
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if repo_dir is None:
        repo_dir = _default_repo_dir()

    feature_ctx = f" / {feature_name}" if feature_name else ""

    # ── Project-local entry ──────────────────────────────────────────────────
    if project_dir is not None:
        local_learnings_dir = project_dir / ".specs" / "learnings"
        try:
            local_learnings_dir.mkdir(parents=True, exist_ok=True)
            local_file = local_learnings_dir / "general.md"
            entry = (
                f"\n### {date_str} — {summary}\n"
                f"Category: {category}\n"
                f"Feature: {feature_name or '(campaign-wide)'}\n\n"
                f"{detail.strip()}\n"
            )
            with local_file.open("a") as f:
                f.write(entry)
            logger.debug(
                "Wrote project-local learning to %s", local_file
            )
        except OSError:
            logger.debug(
                "Failed to write project-local learning", exc_info=True
            )

    # ── Repo-level pending entry ─────────────────────────────────────────────
    repo_learnings_dir = repo_dir / "learnings"
    try:
        repo_learnings_dir.mkdir(parents=True, exist_ok=True)
        pending_file = repo_learnings_dir / "pending.md"
        entry = (
            f"\n---\n\n"
            f"## [pending] {category.upper()} — {project_name}{feature_ctx} — {date_str}\n"
            f"Timestamp: {ts}\n"
            f"Category: {category}\n"
            f"Project: {project_name}\n"
            f"Feature: {feature_name or '(campaign-wide)'}\n\n"
            f"**{summary}**\n\n"
            f"{detail.strip()}\n"
        )
        with pending_file.open("a") as f:
            f.write(entry)
        logger.debug(
            "Wrote repo-level pending learning to %s", pending_file
        )
    except OSError:
        logger.debug(
            "Failed to write repo-level pending learning", exc_info=True
        )
