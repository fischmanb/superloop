# CONVERSION CHANGELOG (from scripts/nightly-review.sh)
# - Color codes (RED, GREEN, YELLOW, BLUE, NC): replaced by structured logging.
# - .env.local loading: bash sources the file; Python parses KEY=VALUE lines
#   manually (same pattern as overnight_autonomous._source_env_file).
# - git commands: bash uses bare git; Python uses subprocess.run with
#   capture_output=True and timeout.
# - Claude invocation: bash calls `bash lib/claude-wrapper.sh`; Python calls
#   `claude_wrapper.run_claude()` from the already-converted lib module.
# - Agent prompt: preserved faithfully as EXTRACTION_PROMPT_TEMPLATE constant.
# - gh CLI for PRs: bash uses `gh pr list --state merged`; Python attempts
#   the same subprocess call and silently skips if gh is unavailable.
# - HOURS_BACK: bash reads from env with default 24; Python reads from
#   NightlyReviewConfig with the same default.
# - Exit behavior: bash `exit 0` on no commits; Python returns early from
#   run() without raising.
"""Nightly review: extract learnings from recent commits.

Orchestrates nightly learnings extraction from the day's work.
Designed to run before ``overnight-autonomous.sh`` so learnings are
available for implementation.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from auto_sdd.lib.claude_wrapper import run_claude

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────


@dataclass
class NightlyReviewConfig:
    """Nightly review configuration."""

    project_dir: Path
    hours_back: int = 24
    main_branch: str = "main"


# ── Agent prompt template ─────────────────────────────────────────────────────

EXTRACTION_PROMPT_TEMPLATE = """\
NIGHTLY REVIEW: Extract learnings from today's work.

## Recent Commits (last {hours_back} hours)

{recent_commits}

## Changed Files

{changed_files}

## Recent Merged PRs

{recent_prs}

---

INSTRUCTIONS:

1. ANALYZE the commits and changes to understand what was worked on today.

2. For each significant piece of work, identify:
   - **Patterns**: What approaches worked well?
   - **Gotchas**: What edge cases or pitfalls were discovered?
   - **Decisions**: What architectural or design choices were made?
   - **Bug Fixes**: What bugs were fixed and why did they occur?

3. CATEGORIZE each learning:

   a) **Feature-specific learnings**:
      - Find the relevant spec in .specs/features/
      - Add to that spec's '## Learnings' section
      - Format: '### {today_date}' followed by bullet points

   b) **Cross-cutting learnings**:
      - Add to .specs/learnings/{{category}}.md based on type:
        - testing.md: Mocking, assertions, test patterns
        - performance.md: Optimization, lazy loading, caching
        - security.md: Auth, cookies, validation
        - api.md: Endpoints, data handling, errors
        - design.md: Tokens, components, accessibility
        - general.md: Other patterns
      - Also add brief entry to .specs/learnings/index.md under "Recent Learnings"

4. UPDATE frontmatter:
   - Set 'updated: {today_date}' in any modified specs

5. RUN drift detection:
   - Check if any specs don't match their implementations
   - Note any drift found in the commit message

6. COMMIT all changes:
   git add .specs/ CLAUDE.md
   git commit -m 'compound: nightly review {today_date}'
   git push origin {main_branch}

7. REPORT what was captured:
   - Number of learnings extracted
   - Which files were updated
   - Any drift detected
   - Any learnings promoted to CLAUDE.md

If no significant learnings are found, that's okay - just report \
'No new learnings identified.'
"""


# ── Nightly Reviewer ──────────────────────────────────────────────────────────


class NightlyReviewer:
    """Orchestrates nightly learnings extraction from recent commits."""

    def __init__(self, config: NightlyReviewConfig) -> None:
        self.config = config
        self.project_dir = config.project_dir
        self.hours_back = config.hours_back
        self.main_branch = config.main_branch

    def run(self) -> None:
        """Execute: sync -> gather -> extract -> verify -> report."""
        logger.info("Starting nightly review")
        logger.info("Project: %s", self.project_dir)
        logger.info(
            "Reviewing commits from last %d hours", self.hours_back
        )

        self._sync_branch()

        commits, files, prs = self._gather_context()
        commit_count = len(
            [line for line in commits.splitlines() if line.strip()]
        )
        file_count = len(
            [line for line in files.splitlines() if line.strip()]
        )

        if commit_count == 0:
            logger.info(
                "No commits in the last %d hours. Nothing to review.",
                self.hours_back,
            )
            return

        logger.info("Found %d commits to review", commit_count)

        # Check for claude CLI
        if not shutil.which("claude"):
            logger.error(
                "Claude Code CLI (claude) not found. "
                "Install via: npm install -g @anthropic-ai/claude-code"
            )
            raise RuntimeError(
                "Claude Code CLI (claude) not found"
            )

        self._run_extraction(commits, files, prs)
        self._verify_and_report(commit_count, file_count)

    def _sync_branch(self) -> None:
        """Checkout main/master and pull."""
        logger.info("Syncing with main branch...")

        # Try main first, fall back to master
        result = self._run_git(["checkout", "main"])
        if result.returncode != 0:
            result = self._run_git(["checkout", "master"])
            if result.returncode != 0:
                logger.error("Could not checkout main or master branch")
                raise RuntimeError(
                    "Could not checkout main or master branch"
                )

        # Get current branch name
        branch_result = self._run_git(["branch", "--show-current"])
        current_branch = branch_result.stdout.strip()

        pull_result = self._run_git(["pull", "origin", current_branch])
        if pull_result.returncode != 0:
            logger.warning(
                "Pull failed (exit %d), continuing with local state",
                pull_result.returncode,
            )

        logger.info("Synced with remote")

    def _gather_context(self) -> tuple[str, str, str]:
        """Returns (recent_commits, changed_files, recent_prs)."""
        logger.info("Gathering recent commits...")

        since = f"{self.hours_back} hours ago"

        # Get recent commits
        commit_result = self._run_git(
            [
                "log",
                f"--since={since}",
                "--pretty=format:%h %s",
                "--no-merges",
            ]
        )
        recent_commits = commit_result.stdout.strip()
        # Limit to 50 lines
        lines = recent_commits.splitlines()[:50]
        recent_commits = "\n".join(lines)

        # Get changed files
        files_result = self._run_git(
            [
                "log",
                f"--since={since}",
                "--name-only",
                "--pretty=format:",
                "--no-merges",
            ]
        )
        changed_lines = files_result.stdout.strip().splitlines()
        # Deduplicate and filter blanks, limit to 100
        seen: set[str] = set()
        unique_files: list[str] = []
        for line in changed_lines:
            stripped = line.strip()
            if stripped and stripped not in seen:
                seen.add(stripped)
                unique_files.append(stripped)
                if len(unique_files) >= 100:
                    break
        changed_files = "\n".join(unique_files)

        # Get recent PRs (if gh available)
        recent_prs = ""
        if shutil.which("gh"):
            recent_prs = self._get_recent_prs()

        return recent_commits, changed_files, recent_prs

    def _get_recent_prs(self) -> str:
        """Fetch recent merged PR titles via gh CLI. Returns empty on failure."""
        try:
            result = subprocess.run(
                [
                    "gh", "pr", "list",
                    "--state", "merged",
                    "--json", "title",
                    "--jq", ".[].title",
                ],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(self.project_dir),
            )
            if result.returncode == 0:
                lines = result.stdout.strip().splitlines()[:10]
                return "\n".join(lines)
        except (subprocess.TimeoutExpired, OSError):
            logger.debug("gh CLI unavailable or timed out")
        return ""

    def _run_extraction(
        self, commits: str, files: str, prs: str
    ) -> None:
        """Invoke Claude agent with learning extraction prompt.

        Uses :func:`~auto_sdd.lib.claude_wrapper.run_claude`.
        """
        logger.info("Extracting learnings from recent work...")

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        prompt = EXTRACTION_PROMPT_TEMPLATE.format(
            hours_back=self.hours_back,
            recent_commits=commits,
            changed_files=files,
            recent_prs=prs or "(none)",
            today_date=today,
            main_branch=self.main_branch,
        )

        try:
            result = run_claude(
                ["-p", "--dangerously-skip-permissions", prompt],
                timeout=600,
            )
            logger.info(
                "Extraction agent completed (exit=%d)", result.exit_code
            )
        except Exception:
            logger.exception("Extraction agent failed")

    def _verify_and_report(
        self, commit_count: int, file_count: int
    ) -> None:
        """Check if extraction committed, print summary."""
        # Check if anything was committed
        result = self._run_git(["log", "-1", "--pretty=format:%s"])
        last_commit = result.stdout.strip()

        if "compound: nightly review" in last_commit:
            logger.info(
                "Nightly review complete - learnings committed"
            )
        else:
            logger.info(
                "Nightly review complete - no new learnings to commit"
            )

        logger.info(
            "Commits reviewed: %d | Files changed: %d",
            commit_count,
            file_count,
        )

    def _run_git(
        self, args: list[str]
    ) -> subprocess.CompletedProcess[str]:
        """Run a git command in the project directory."""
        return subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(self.project_dir),
        )


# ── Environment loading ──────────────────────────────────────────────────────


def _source_env_file(env_file: Path) -> None:
    """Parse a ``.env.local`` file and set env vars (without overriding)."""
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


# ── CLI entry point ───────────────────────────────────────────────────────────


def main() -> None:
    """CLI entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Determine project directory
    script_dir = Path(__file__).resolve().parent
    default_project_dir = script_dir.parent.parent.parent

    # Load .env.local
    project_dir_str = os.environ.get("PROJECT_DIR", "")
    if project_dir_str:
        project_dir = Path(project_dir_str)
    else:
        project_dir = default_project_dir

    env_file = project_dir / ".env.local"
    _source_env_file(env_file)

    # Re-read after env loading
    project_dir_str = os.environ.get("PROJECT_DIR", "")
    if project_dir_str:
        project_dir = Path(project_dir_str)

    hours_back = int(os.environ.get("HOURS_BACK", "24"))

    main_branch = os.environ.get("MAIN_BRANCH", "main")

    config = NightlyReviewConfig(
        project_dir=project_dir,
        hours_back=hours_back,
        main_branch=main_branch,
    )

    reviewer = NightlyReviewer(config)
    reviewer.run()


if __name__ == "__main__":
    main()
