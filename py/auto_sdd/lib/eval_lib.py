# CONVERSION CHANGELOG (from lib/eval.sh)
# - run_mechanical_eval: returns MechanicalEvalResult dataclass instead of printing
#   JSON to stdout. Raises typed exceptions instead of returning exit code 1 with
#   error JSON. The caller handles serialization.
# - run_mechanical_eval: diff_stats is a dict with keys files_changed, lines_added,
#   lines_removed, files, new_type_exports, import_count, feature_name, commit —
#   matching the bash JSON output fields. MechanicalEvalResult wraps the structured
#   data rather than being a flat JSON blob.
# - run_mechanical_eval: merge commits return a MechanicalEvalResult with
#   passed=True and a diff_stats containing "skipped": True, "reason": "merge commit"
#   to match bash behavior of returning JSON with skipped flag.
# - generate_eval_prompt: returns the prompt string instead of printing to stdout.
#   Raises EvalError on missing arguments instead of printing to stderr and
#   returning exit code 1.
# - parse_eval_signal: returns empty string for missing signals (matches bash).
# - write_eval_result: uses atomic write (temp-then-rename) instead of direct cat.
#   Returns Path to output file instead of printing path to stdout.
# - Feature name sanitization in write_eval_result uses regex instead of sed/tr chain.
# - Inline exception classes (AutoSddError, EvalError) since errors.py doesn't
#   exist yet.

"""Eval function library for assessing completed feature builds.

Provides mechanical (deterministic) evaluation of git commits and prompt
generation for agent-based evaluation.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


# ── Inline exceptions (until errors.py exists) ──────────────────────────────

class AutoSddError(Exception):
    """Base for all auto-sdd errors."""


class EvalError(AutoSddError):
    """An eval operation failed."""


# ── Data types ───────────────────────────────────────────────────────────────

@dataclass
class MechanicalEvalResult:
    """Result of a deterministic, agent-free evaluation of a commit."""

    diff_stats: dict[str, int | str | bool | list[str]]
    type_exports_changed: list[str]
    redeclarations: list[str]
    test_files_touched: list[str]
    passed: bool


# ── Helpers ──────────────────────────────────────────────────────────────────

def _run_git(
    args: list[str],
    project_dir: Path,
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a git command in *project_dir*, returning the completed process."""
    cmd = ["git", "-C", str(project_dir), *args]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=check,
        timeout=60,
    )


def _get_parent_count(project_dir: Path, commit_hash: str) -> int:
    """Return the number of parents for *commit_hash*."""
    result = _run_git(
        ["rev-list", "--parents", "-n", "1", commit_hash],
        project_dir,
    )
    # Output: "<commit> [<parent1> <parent2> ...]"
    parts = result.stdout.strip().split()
    return len(parts) - 1


def _get_empty_tree_hash(project_dir: Path) -> str:
    """Return the well-known empty tree hash via git."""
    result = _run_git(
        ["hash-object", "-t", "tree", "/dev/null"],
        project_dir,
    )
    return result.stdout.strip()


def _parse_numstat(numstat_output: str) -> list[tuple[int, int, str]]:
    """Parse git diff --numstat output into (added, removed, filepath) tuples.

    Binary files show '-' for added/removed; those are treated as 0.
    """
    entries: list[tuple[int, int, str]] = []
    for line in numstat_output.strip().splitlines():
        if not line.strip():
            continue
        parts = line.split("\t", 2)
        if len(parts) < 3:
            continue
        added_str, removed_str, filepath = parts
        added = int(added_str) if added_str != "-" else 0
        removed = int(removed_str) if removed_str != "-" else 0
        entries.append((added, removed, filepath))
    return entries


def _is_test_file(filepath: str) -> bool:
    """Return True if *filepath* looks like a test file."""
    return "test" in filepath or "spec" in filepath or "__tests__" in filepath


def _extract_type_names(diff_content: str) -> list[str]:
    """Extract exported type/interface names from added lines in a diff."""
    names: list[str] = []
    pattern = re.compile(r"export\s+(?:type|interface)\s+(\w+)")
    for line in diff_content.splitlines():
        if not line.startswith("+"):
            continue
        match = pattern.search(line)
        if match:
            names.append(match.group(1))
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for name in names:
        if name not in seen:
            seen.add(name)
            unique.append(name)
    return unique


def _sanitize_feature_name(name: str) -> str:
    """Sanitize a feature name for use in filenames.

    Matches the bash: lowercase, replace non-alnum/dot/dash with -, collapse
    runs, strip leading/trailing dashes.
    """
    safe = name.lower()
    safe = re.sub(r"[^a-z0-9._-]", "-", safe)
    safe = re.sub(r"-{2,}", "-", safe)
    safe = safe.strip("-")
    return safe


# ── Public functions ─────────────────────────────────────────────────────────

def run_mechanical_eval(
    project_dir: Path,
    commit_hash: str,
) -> MechanicalEvalResult:
    """Run deterministic, agent-free checks against a commit.

    Args:
        project_dir: Path to a git repository.
        commit_hash: The commit to evaluate.

    Returns:
        MechanicalEvalResult with diff stats and analysis.

    Raises:
        EvalError: If project_dir is missing/invalid or commit not found.
    """
    if not commit_hash:
        raise EvalError("run_mechanical_eval: commit_hash is required")

    if not project_dir.is_dir():
        raise EvalError(
            f"run_mechanical_eval: directory does not exist: {project_dir}"
        )

    # Verify the commit exists
    cat_file = _run_git(
        ["cat-file", "-t", commit_hash], project_dir, check=False
    )
    if cat_file.returncode != 0:
        raise EvalError(
            f"run_mechanical_eval: commit not found: {commit_hash}"
        )

    # Check for merge commit
    parent_count = _get_parent_count(project_dir, commit_hash)
    if parent_count > 1:
        logger.info("Skipping merge commit %s", commit_hash)
        return MechanicalEvalResult(
            diff_stats={
                "commit": commit_hash,
                "skipped": True,
                "reason": "merge commit",
            },
            type_exports_changed=[],
            redeclarations=[],
            test_files_touched=[],
            passed=True,
        )

    # Extract feature name from commit message
    log_result = _run_git(
        ["log", "-1", "--format=%s", commit_hash], project_dir
    )
    commit_msg = log_result.stdout.strip()
    # Strip leading "prefix: " (e.g. "feat: ") from commit message
    feature_name = re.sub(r"^[^:]*:\s*", "", commit_msg)

    is_first_commit = parent_count == 0

    # Get diff numstat
    if is_first_commit:
        empty_tree = _get_empty_tree_hash(project_dir)
        numstat_result = _run_git(
            ["diff", "--numstat", empty_tree, commit_hash],
            project_dir,
            check=False,
        )
    else:
        numstat_result = _run_git(
            ["diff", "--numstat", f"{commit_hash}^", commit_hash],
            project_dir,
            check=False,
        )

    numstat_output = numstat_result.stdout or ""
    entries = _parse_numstat(numstat_output)

    files_changed = len(entries)
    lines_added = sum(a for a, _, _ in entries)
    lines_removed = sum(r for _, r, _ in entries)
    files_list = [fp for _, _, fp in entries]

    test_files = [fp for fp in files_list if _is_test_file(fp)]

    # Get diff content for type analysis
    if is_first_commit:
        empty_tree = _get_empty_tree_hash(project_dir)
        diff_result = _run_git(
            ["diff", empty_tree, commit_hash], project_dir, check=False
        )
    else:
        diff_result = _run_git(
            ["diff", f"{commit_hash}^", commit_hash],
            project_dir,
            check=False,
        )

    diff_content = diff_result.stdout or ""

    # Count new type/interface exports
    new_type_names = _extract_type_names(diff_content)
    new_type_exports = len(new_type_names)

    # Check for redeclarations
    redeclared: list[str] = []
    if new_type_exports > 0 and not is_first_commit:
        for type_name in new_type_names:
            grep_result = _run_git(
                [
                    "grep",
                    "-l",
                    f"export \\(type\\|interface\\) {type_name}",
                    f"{commit_hash}^",
                    "--",
                    "*.ts",
                    "*.tsx",
                ],
                project_dir,
                check=False,
            )
            existing_files = [
                f
                for f in grep_result.stdout.strip().splitlines()
                if f.strip()
            ]
            if len(existing_files) > 0:
                redeclared.append(type_name)

    # Count import statements added
    import_count = 0
    if diff_content:
        for line in diff_content.splitlines():
            if line.startswith("+") and "import " in line:
                # Exclude diff header lines like "+++ b/..."
                if not line.startswith("+++"):
                    import_count += 1

    diff_stats: dict[str, int | str | bool | list[str]] = {
        "commit": commit_hash,
        "feature_name": feature_name,
        "files_changed": files_changed,
        "files": files_list,
        "lines_added": lines_added,
        "lines_removed": lines_removed,
        "new_type_exports": new_type_exports,
        "type_redeclarations": len(redeclared),
        "redeclared_type_names": redeclared,
        "import_count": import_count,
        "test_files_touched": len(test_files) > 0,
    }

    return MechanicalEvalResult(
        diff_stats=diff_stats,
        type_exports_changed=new_type_names,
        redeclarations=redeclared,
        test_files_touched=test_files,
        passed=True,
    )


def generate_eval_prompt(
    project_dir: Path,
    commit_hash: str,
) -> str:
    """Generate a prompt string for a fresh eval agent.

    Args:
        project_dir: Path to the git repository.
        commit_hash: The commit to evaluate.

    Returns:
        The prompt text for an eval agent.

    Raises:
        EvalError: If project_dir or commit_hash is missing.
    """
    if not commit_hash:
        raise EvalError(
            "generate_eval_prompt: project_dir and commit_hash are required"
        )

    if not project_dir.is_dir():
        raise EvalError(
            "generate_eval_prompt: project_dir and commit_hash are required"
        )

    # Get parent count to decide how to diff
    parent_count = _get_parent_count(project_dir, commit_hash)

    if parent_count == 0:
        empty_tree = _get_empty_tree_hash(project_dir)
        diff_result = _run_git(
            ["diff", empty_tree, commit_hash], project_dir, check=False
        )
    else:
        diff_result = _run_git(
            ["diff", f"{commit_hash}^", commit_hash],
            project_dir,
            check=False,
        )

    diff_content = diff_result.stdout or ""

    # Read CLAUDE.md if it exists
    claude_md_path = project_dir / "CLAUDE.md"
    claude_md_content = ""
    if claude_md_path.is_file():
        claude_md_content = claude_md_path.read_text()

    # Read learnings index if it exists
    learnings_path = project_dir / ".specs" / "learnings" / "index.md"
    learnings_content = ""
    if learnings_path.is_file():
        learnings_content = learnings_path.read_text()

    prompt = f"""You are an eval agent reviewing commit {commit_hash}.

IMPORTANT: do NOT modify any files, do NOT commit, do NOT ask for user input. You are read-only.

## Your Task

Review the following diff and assess the quality of this commit against the project's standards.

## Project Standards (CLAUDE.md)

{claude_md_content}

## Recent Learnings

{learnings_content}

## Diff to Review

{diff_content}

## Assessment Criteria

1. **Framework Compliance**: Does the code follow the project's spec-driven development workflow? Are specs, tests, and implementation consistent?
2. **Scope Discipline**: Is the commit focused on a single feature/fix, or does it sprawl across unrelated concerns?
3. **Integration Quality**: Are imports clean? Are types properly used? Does the code integrate well with existing patterns?
4. **Repeated Mistakes**: Does this commit repeat any mistakes documented in learnings?

## Required Output Signals

You MUST output these exact signals (one per line) in your response:

EVAL_COMPLETE: true
EVAL_FRAMEWORK_COMPLIANCE: <pass|warn|fail>
EVAL_SCOPE_ASSESSMENT: <focused|moderate|sprawling>
EVAL_INTEGRATION_QUALITY: <clean|minor_issues|major_issues>
EVAL_REPEATED_MISTAKES: <none|comma-separated list of repeated mistakes>
EVAL_NOTES: <one-line summary of your assessment>"""

    return prompt


def parse_eval_signal(signal_name: str, output: str) -> str:
    """Extract the last value of a named signal from multiline output.

    Args:
        signal_name: The signal name (e.g. "EVAL_COMPLETE").
        output: The multiline text to search.

    Returns:
        The signal value (stripped), or empty string if not found.
    """
    last_value = ""
    prefix = f"{signal_name}:"
    for line in output.splitlines():
        if line.startswith(prefix):
            # Everything after "SIGNAL_NAME:" stripped
            value = line[len(prefix):].strip()
            last_value = value
    return last_value


def write_eval_result(
    output_dir: Path,
    feature_name: str,
    mechanical: MechanicalEvalResult,
    agent_output: str,
) -> Path:
    """Merge mechanical eval with parsed agent signals into a result file.

    If agent output is empty or unparseable, writes mechanical-only results.
    Uses atomic write (temp-then-rename).

    Args:
        output_dir: Directory for output files.
        feature_name: Human-readable feature name.
        mechanical: Result from run_mechanical_eval.
        agent_output: Raw text output from the eval agent (may be empty).

    Returns:
        Path to the written result file.

    Raises:
        EvalError: If output_dir or feature_name is empty.
    """
    if not feature_name:
        raise EvalError(
            "write_eval_result: output_dir and feature_name are required"
        )

    safe_name = _sanitize_feature_name(feature_name)
    output_file = output_dir / f"eval-{safe_name}.json"

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # Build mechanical JSON from the diff_stats dict
    mechanical_data = mechanical.diff_stats

    # Try to parse agent signals
    agent_eval_available = False
    agent_eval: dict[str, str] = {}

    if agent_output:
        eval_complete = parse_eval_signal("EVAL_COMPLETE", agent_output)
        if eval_complete == "true":
            agent_eval_available = True
            agent_eval = {
                "framework_compliance": parse_eval_signal(
                    "EVAL_FRAMEWORK_COMPLIANCE", agent_output
                ),
                "scope_assessment": parse_eval_signal(
                    "EVAL_SCOPE_ASSESSMENT", agent_output
                ),
                "integration_quality": parse_eval_signal(
                    "EVAL_INTEGRATION_QUALITY", agent_output
                ),
                "repeated_mistakes": parse_eval_signal(
                    "EVAL_REPEATED_MISTAKES", agent_output
                ),
                "eval_notes": parse_eval_signal(
                    "EVAL_NOTES", agent_output
                ),
            }

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    result: dict[str, object] = {
        "eval_timestamp": timestamp,
        "mechanical": mechanical_data,
        "agent_eval_available": agent_eval_available,
    }

    if agent_eval_available:
        result["agent_eval"] = agent_eval

    data = json.dumps(result, indent=2) + "\n"

    # Atomic write: temp file then rename
    fd, tmp_path = tempfile.mkstemp(
        dir=str(output_dir), prefix=output_file.stem
    )
    try:
        with os.fdopen(fd, "w") as f:
            f.write(data)
        os.rename(tmp_path, str(output_file))
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    logger.info("Wrote eval result to %s", output_file)
    return output_file
