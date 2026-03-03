"""Generate a concise codebase summary for build agent prompts.

Uses a lightweight Claude agent to analyze the project's file tree and
produce a structural summary.  Falls back to an empty string on any
failure so the build loop is never blocked.

Public API:
    generate_codebase_summary(project_dir) -> str
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


_EXCLUDED_DIRS: frozenset[str] = frozenset({
    "node_modules", ".git", "dist", "build", ".next",
    "__pycache__", "target", ".build-worktrees", "venv", ".venv",
})

_FILE_TREE_CAP: int = 500

_AGENT_PROMPT_TEMPLATE: str = """\
You are a codebase analyst.  Below is the file tree of a software project.
Produce a structured summary covering:

1. **Key modules / entry points** — the main files that drive the application
2. **Public types and interfaces** — important data structures, API contracts
3. **Import / dependency relationships** — how modules connect to each other
4. **Architectural patterns** — framework usage, layering, notable conventions

Constraints:
- Output no more than 100 lines.
- Use compact markdown (##, bullets, short descriptions).
- Work from the file tree below.  Read only the files you need to understand
  the structure — do not read every file.
- Do NOT include language-specific instructions.  Identify the language(s)
  from the file extensions and adapt accordingly.

## File Tree

```
{file_tree}
```
"""


def _generate_file_tree(project_dir: Path) -> str:
    """Walk *project_dir* and return a newline-separated listing of relative paths.

    Respects ``_EXCLUDED_DIRS`` and caps output at ``_FILE_TREE_CAP`` files.
    """
    paths: list[str] = []
    stack: list[Path] = [project_dir]
    while stack:
        current = stack.pop()
        try:
            entries = sorted(current.iterdir(), key=lambda p: p.name)
        except OSError:
            continue
        for entry in entries:
            if entry.is_dir():
                if entry.name not in _EXCLUDED_DIRS:
                    stack.append(entry)
            elif entry.is_file():
                if len(paths) >= _FILE_TREE_CAP:
                    paths.append(f"... (truncated at {_FILE_TREE_CAP} files)")
                    return "\n".join(paths)
                paths.append(str(entry.relative_to(project_dir)))
    paths.sort()
    return "\n".join(paths)


def _get_tree_hash(project_dir: Path) -> str | None:
    """Return the git tree hash for *project_dir*, or ``None`` if not a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD^{tree}"],
            capture_output=True,
            text=True,
            cwd=project_dir,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def _cache_dir(project_dir: Path) -> Path:
    return project_dir / ".auto-sdd-cache"


def _cache_path(project_dir: Path, tree_hash: str) -> Path:
    return _cache_dir(project_dir) / f"codebase-summary-{tree_hash}.md"


def _read_cache(project_dir: Path, tree_hash: str) -> str | None:
    """Return cached summary if it exists, otherwise ``None``."""
    path = _cache_path(project_dir, tree_hash)
    if path.is_file():
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            pass
    return None


def _write_cache(project_dir: Path, tree_hash: str, content: str) -> None:
    """Write *content* to the cache and ensure a ``.gitignore`` exists."""
    cache = _cache_dir(project_dir)
    cache.mkdir(parents=True, exist_ok=True)
    gitignore = cache / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("*\n")
    _cache_path(project_dir, tree_hash).write_text(content, encoding="utf-8")


def _call_agent(project_dir: Path, file_tree: str) -> str:
    """Invoke a lightweight Claude agent to produce a codebase summary.

    Raises on any failure — caller is responsible for fallback.
    """
    from auto_sdd.lib.claude_wrapper import run_claude

    prompt = _AGENT_PROMPT_TEMPLATE.format(file_tree=file_tree)
    result = run_claude(
        ["-p", "--dangerously-skip-permissions", prompt],
        timeout=120,
    )
    return result.output


def _read_recent_learnings(project_dir: Path) -> str:
    """Read recent learnings from ``.specs/learnings/`` and return as text.

    Returns an empty string when the directory is missing or contains no
    non-empty markdown files.
    """
    learnings_dir = project_dir / ".specs" / "learnings"
    if not learnings_dir.is_dir():
        return ""

    md_files = sorted(learnings_dir.glob("*.md"))
    lines: list[str] = []
    learnings_cap = 40

    for md_file in md_files:
        if not md_file.is_file():
            continue
        if md_file.stat().st_size == 0:
            continue
        try:
            content = md_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines.append(f"### {md_file.name}")
        lines.extend(content.split("\n"))

    if not lines:
        return ""

    capped = lines[:learnings_cap]
    if len(lines) > learnings_cap:
        capped.append(f"... (learnings truncated at {learnings_cap} lines)")

    return "\n".join(["## Recent Learnings", "", *capped, ""])


def generate_codebase_summary(project_dir: Path) -> str:
    """Generate a structured codebase summary using a Claude agent.

    The summary is cached by git tree hash so repeated calls for the
    same tree state are free.  If the agent call fails for any reason
    the function returns an empty string — the build loop must never
    crash because of summary generation.

    Args:
        project_dir: Absolute path to the project being scanned.

    Returns:
        Structured plain-text summary, or empty string on failure.

    Raises:
        ValueError: If *project_dir* does not exist or is not a directory.
    """
    if not project_dir.exists():
        raise ValueError(
            f"generate_codebase_summary: directory does not exist: {project_dir}"
        )
    if not project_dir.is_dir():
        raise ValueError(
            f"generate_codebase_summary: not a directory: {project_dir}"
        )

    logger.info("Generating codebase summary for %s", project_dir)

    # 1. Generate file tree
    file_tree = _generate_file_tree(project_dir)

    # 2. Check cache
    tree_hash = _get_tree_hash(project_dir)
    if tree_hash is not None:
        cached = _read_cache(project_dir, tree_hash)
        if cached is not None:
            logger.info("Cache hit for tree hash %s", tree_hash)
            learnings = _read_recent_learnings(project_dir)
            return cached + "\n" + learnings if learnings else cached

    # 3. Call agent
    agent_summary = ""
    try:
        agent_summary = _call_agent(project_dir, file_tree)
    except Exception:
        logger.warning(
            "Agent call failed; returning empty summary", exc_info=True
        )

    # 4. Cache result (only if we got a tree hash and non-empty output)
    if tree_hash is not None and agent_summary:
        try:
            _write_cache(project_dir, tree_hash, agent_summary)
            logger.info("Cached summary for tree hash %s", tree_hash)
        except OSError:
            logger.warning("Failed to write cache", exc_info=True)

    # 5. Append learnings
    learnings = _read_recent_learnings(project_dir)
    if learnings and agent_summary:
        return agent_summary + "\n" + learnings
    if learnings:
        return learnings
    return agent_summary
