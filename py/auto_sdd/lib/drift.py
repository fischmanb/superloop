# CONVERSION CHANGELOG (from scripts/build-loop-local.sh lines 671–971)
# - read_latest_eval_feedback: accepts eval_output_dir (Path) instead of
#   reading EVAL_OUTPUT_DIR global. Uses json.loads() instead of awk field-walk.
#   Returns feedback string (empty if no evals).
# - update_repeated_mistakes / get_cumulative_mistakes: bash used a global
#   STATE_DIR and a file-backed accumulator. Python uses a MistakeTracker
#   dataclass that is passed in and returned — no module-level mutable state.
# - extract_drift_targets: returns DriftTargets dataclass instead of setting
#   DRIFT_SPEC_FILE / DRIFT_SOURCE_FILES globals. parse_signal moved inline
#   (same logic as eval_lib.parse_eval_signal).
# - check_drift: accepts explicit parameters instead of reading globals.
#   Invokes Claude via run_claude() from claude_wrapper.py. Returns a
#   DriftCheckResult instead of a shell exit code.
# - run_code_review: same invocation pattern as check_drift. Returns
#   CodeReviewResult.
# - parse_signal: private helper extracted for reuse by extract_drift_targets
#   and check_drift. Same logic as the bash parse_signal function.
"""Drift detection, eval feedback, and code review for the SDD build loop.

Provides functions to read eval feedback, track repeated mistakes, extract
drift targets from build output, run drift checks via Claude, and run
code reviews via Claude.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from auto_sdd.lib.claude_wrapper import ClaudeResult, run_claude
from auto_sdd.lib.learnings_writer import write_learning
from auto_sdd.lib.reliability import AutoSddError

logger = logging.getLogger(__name__)


# ── Data types ───────────────────────────────────────────────────────────────


@dataclass
class MistakeTracker:
    """In-memory tracker for repeated mistake patterns.

    In bash this was a file-backed global (``STATE_DIR/repeated-mistakes.txt``).
    In Python the caller owns the instance and persists if needed.
    """

    mistakes: list[str] = field(default_factory=list)


@dataclass
class DriftTargets:
    """Parsed drift check targets from build output."""

    spec_file: str
    source_files: str


@dataclass
class DriftCheckResult:
    """Result of a drift check."""

    passed: bool
    summary: str


@dataclass
class CodeReviewResult:
    """Result of a code review agent run."""

    passed: bool
    summary: str


# ── Signal parsing (private) ────────────────────────────────────────────────


def _parse_signal(signal_name: str, output: str) -> str:
    """Extract the last value of a named signal from multiline output.

    Args:
        signal_name: The signal prefix (e.g. ``"SPEC_FILE"``).
        output: Multiline text to search.

    Returns:
        The stripped value, or empty string if not found.
    """
    last_value = ""
    prefix = f"{signal_name}:"
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith(prefix):
            value = stripped[len(prefix):].strip()
            last_value = value
    return last_value


# ── Eval feedback ────────────────────────────────────────────────────────────


def read_latest_eval_feedback(eval_output_dir: Path) -> str:
    """Read the most recent eval JSON and extract advisory feedback.

    Looks for ``eval-*.json`` files (excluding campaign files) in
    *eval_output_dir*, reads the newest by mtime, and extracts non-passing
    fields as warnings for the next build agent.

    Args:
        eval_output_dir: Directory containing eval result JSON files.

    Returns:
        Multi-line feedback string, or empty string if nothing notable.
    """
    if not eval_output_dir.is_dir():
        return ""

    # Find eval JSON files, excluding campaign files
    eval_files = sorted(
        (
            f
            for f in eval_output_dir.glob("eval-*.json")
            if "eval-campaign-" not in f.name
        ),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )

    if not eval_files:
        return ""

    latest = eval_files[0]
    try:
        data = json.loads(latest.read_text())
    except (json.JSONDecodeError, OSError):
        return ""

    # Extract agent eval fields
    agent_eval = data.get("agent_eval", {})
    if not isinstance(agent_eval, dict):
        agent_eval = {}

    fw = agent_eval.get("framework_compliance", "")
    sc = agent_eval.get("scope_assessment", "")
    rm = agent_eval.get("repeated_mistakes", "")
    iq = agent_eval.get("integration_quality", "")
    en = agent_eval.get("eval_notes", "")

    parts: list[str] = []

    if fw in ("warn", "fail"):
        parts.append(
            f"\u26a0 FRAMEWORK COMPLIANCE ({fw}): Ensure roadmap status is "
            "updated, Agents.md entry is present, and spec frontmatter is complete."
        )

    if sc in ("moderate", "sprawling"):
        parts.append(
            f"\u26a0 SCOPE CREEP ({sc}): Only modify files required by the "
            "spec. Do not refactor or improve unrelated code."
        )

    if rm and rm != "none":
        parts.append(
            f"\U0001f6a8 REPEATED MISTAKE: This pattern has occurred before \u2014 {rm}"
        )

    if iq == "major_issues":
        parts.append(
            f"\u26a0 INTEGRATION QUALITY ({iq}): Check server/client component "
            "boundaries and ensure authorization filters are applied to all queries."
        )

    if en:
        parts.append(f"\U0001f4dd EVAL NOTE: {en}")

    return "\n".join(parts)


# ── Repeated mistake tracking ────────────────────────────────────────────────


def update_repeated_mistakes(
    new_mistake: str,
    tracker: MistakeTracker,
) -> MistakeTracker:
    """Add a mistake pattern to the tracker if not already present.

    No-op for empty strings or ``"none"``.

    Args:
        new_mistake: The mistake description.
        tracker: Current tracker state.

    Returns:
        Updated tracker (same instance, mutated in place).
    """
    if not new_mistake or new_mistake == "none":
        return tracker
    if new_mistake not in tracker.mistakes:
        tracker.mistakes.append(new_mistake)
    return tracker


def get_cumulative_mistakes(tracker: MistakeTracker) -> str:
    """Return accumulated mistakes as a formatted block.

    Args:
        tracker: Current mistake tracker.

    Returns:
        Formatted string, or empty string if no mistakes recorded.
    """
    if not tracker.mistakes:
        return ""

    lines = ["Known mistakes from previous builds in this campaign:"]
    for m in tracker.mistakes:
        lines.append(f"  - {m}")
    return "\n".join(lines)


# ── Drift target extraction ─────────────────────────────────────────────────


def extract_drift_targets(
    build_result: str,
    project_dir: Path | None = None,
) -> DriftTargets:
    """Parse SPEC_FILE and SOURCE_FILES signals from build output.

    Falls back to git diff if signals are missing and *project_dir* is
    provided.

    Args:
        build_result: Raw build agent output.
        project_dir: Optional project root for git fallback.

    Returns:
        DriftTargets with spec_file and source_files strings.
    """
    spec_file = _parse_signal("SPEC_FILE", build_result)
    source_files = _parse_signal("SOURCE_FILES", build_result)

    # Fallback: derive from git diff if agent didn't provide them
    if not spec_file and project_dir is not None:
        try:
            result = subprocess.run(
                ["git", "diff", "HEAD~1", "--name-only"],
                capture_output=True,
                text=True,
                cwd=str(project_dir),
                timeout=30,
            )
            for line in result.stdout.splitlines():
                line = line.strip()
                if re.search(r"\.specs/features/.*\.feature\.md$", line):
                    spec_file = line
                    break
        except (subprocess.TimeoutExpired, OSError):
            pass

    if not source_files and project_dir is not None:
        try:
            result = subprocess.run(
                ["git", "diff", "HEAD~1", "--name-only"],
                capture_output=True,
                text=True,
                cwd=str(project_dir),
                timeout=30,
            )
            files: list[str] = []
            for line in result.stdout.splitlines():
                line = line.strip()
                if re.search(r"\.(tsx?|jsx?|py|rs|go)$", line):
                    if ".test." not in line and ".spec." not in line:
                        files.append(line)
            source_files = ", ".join(files)
        except (subprocess.TimeoutExpired, OSError):
            pass

    return DriftTargets(spec_file=spec_file, source_files=source_files)


# Need subprocess for git fallback in extract_drift_targets
import subprocess  # noqa: E402


# ── Drift check ──────────────────────────────────────────────────────────────


def check_drift(
    spec_file: str,
    source_files: str,
    project_dir: Path,
    *,
    model: str | None = None,
    max_retries: int = 1,
    drift_enabled: bool = True,
    test_cmd: str = "",
    cost_log_path: Path | None = None,
    timeout: int = 600,
    project_name: str = "",
    feature_name: str = "",
    repo_dir: Path | None = None,
) -> DriftCheckResult:
    """Run a drift check via a fresh Claude agent.

    Args:
        spec_file: Path to the spec file.
        source_files: Comma-separated source file paths.
        project_dir: Project root.
        model: Claude model override.
        max_retries: Max retry attempts for fixing drift.
        drift_enabled: If False, skips the check.
        test_cmd: Test command for the drift agent to run.
        cost_log_path: Optional path for cost logging.
        timeout: Agent timeout in seconds.
        project_name: Project name for learnings attribution. Defaults to
            project_dir.name if not provided.
        feature_name: Feature name for learnings attribution.
        repo_dir: Superloop repo root for repo-level learnings. Defaults to
            auto-derived from module path.

    Returns:
        DriftCheckResult with passed flag and summary.
    """
    _pname = project_name or project_dir.name
    if not drift_enabled:
        logger.info("Drift check disabled (set DRIFT_CHECK=true to enable)")
        return DriftCheckResult(passed=True, summary="disabled")

    if not spec_file:
        logger.warning("No spec file found — skipping drift check")
        return DriftCheckResult(passed=True, summary="no spec file")

    logger.info("Running drift check (fresh agent)...")
    logger.info("  Spec: %s", spec_file)
    logger.info("  Source: %s", source_files or "<detected from spec>")

    test_context = ""
    if test_cmd:
        test_context = f"\nTest command: {test_cmd}"

    prompt = (
        "Run /catch-drift for this specific feature. This is an automated check "
        "— do NOT ask for user input. Auto-fix all drift by updating specs to "
        "match code (prefer documenting reality over reverting code).\n\n"
        f"Spec file: {spec_file}\n"
        f"Source files: {source_files}{test_context}\n\n"
        "Instructions:\n"
        "1. Read the spec file and all its Gherkin scenarios\n"
        "2. Read each source file listed above\n"
        "3. Compare: does the code implement what the spec describes?\n"
        "4. Check: are there behaviors in code not covered by the spec?\n"
        "5. Check: are there scenarios in the spec not implemented in code?\n"
        "6. If drift found: update specs, code, or tests as needed "
        "(prefer updating specs to match code)\n"
        f"7. Run the test suite (`{test_cmd}`) and fix any failures — "
        "iterate until tests pass\n"
        "8. Commit all fixes with message: 'fix: reconcile spec drift for {feature}'\n\n"
        "IMPORTANT: Your goal is spec+code alignment AND a passing test suite. "
        "Keep iterating until both are achieved.\n\n"
        "Output EXACTLY ONE of these signals at the end:\n"
        "NO_DRIFT\n"
        "DRIFT_FIXED: {brief summary of what was reconciled}\n"
        "DRIFT_UNRESOLVABLE: {what needs human attention and why}\n"
    )

    for attempt in range(max_retries + 1):
        if attempt > 0:
            logger.warning(
                "Drift fix retry %d/%d", attempt, max_retries
            )

        cmd_args = ["-p", "--dangerously-skip-permissions"]
        if model:
            cmd_args.extend(["--model", model])
        cmd_args.append(prompt)

        try:
            result = run_claude(
                cmd_args,
                cost_log_path=cost_log_path,
                timeout=timeout,
            )
            output = result.output
        except Exception:
            logger.exception("Drift agent failed")
            output = ""

        if "NO_DRIFT" in output:
            logger.info("✓ Drift check passed — spec and code are aligned")
            write_learning(
                summary=f"Drift check: no drift detected for {feature_name or spec_file}",
                detail=(
                    f"Spec and implementation are aligned.\n"
                    f"Spec: {spec_file}\nSource files: {source_files}"
                ),
                category="drift",
                project_name=_pname,
                feature_name=feature_name,
                project_dir=project_dir,
                repo_dir=repo_dir,
            )
            return DriftCheckResult(passed=True, summary="no drift")

        if "DRIFT_FIXED" in output:
            fix_summary = _parse_signal("DRIFT_FIXED", output)
            logger.info(
                "✓ Drift detected and auto-fixed: %s", fix_summary
            )
            write_learning(
                summary=f"Drift auto-fixed for {feature_name or spec_file}: {fix_summary}",
                detail=(
                    f"Spec/code misalignment was detected and auto-reconciled.\n"
                    f"Fix summary: {fix_summary}\n"
                    f"Spec: {spec_file}\nSource files: {source_files}"
                ),
                category="drift",
                project_name=_pname,
                feature_name=feature_name,
                project_dir=project_dir,
                repo_dir=repo_dir,
            )
            return DriftCheckResult(passed=True, summary=f"fixed: {fix_summary}")

        if "DRIFT_UNRESOLVABLE" in output:
            reason = _parse_signal("DRIFT_UNRESOLVABLE", output)
            logger.warning("Unresolvable drift: %s", reason)
            write_learning(
                summary=f"Drift UNRESOLVABLE for {feature_name or spec_file} — needs human review",
                detail=(
                    f"Drift agent could not reconcile spec and code.\n"
                    f"Reason: {reason}\n"
                    f"Spec: {spec_file}\nSource files: {source_files}"
                ),
                category="drift-unresolvable",
                project_name=_pname,
                feature_name=feature_name,
                project_dir=project_dir,
                repo_dir=repo_dir,
            )
            return DriftCheckResult(
                passed=False, summary=f"unresolvable: {reason}"
            )

        logger.warning("Drift check did not produce a clear signal")

    logger.error(
        "Drift check failed after %d attempt(s)", max_retries + 1
    )
    return DriftCheckResult(passed=False, summary="no clear signal after retries")


# ── Code review ──────────────────────────────────────────────────────────────


def run_code_review(
    project_dir: Path,
    *,
    model: str | None = None,
    test_cmd: str = "",
    cost_log_path: Path | None = None,
    timeout: int = 600,
) -> CodeReviewResult:
    """Run a code review via a fresh Claude agent.

    Args:
        project_dir: Project root.
        model: Claude model override.
        test_cmd: Test command for the review agent to run.
        cost_log_path: Optional path for cost logging.
        timeout: Agent timeout in seconds.

    Returns:
        CodeReviewResult with passed flag and summary.
    """
    logger.info(
        "Running code-review agent (fresh context, model: %s)...",
        model or "default",
    )

    test_context = ""
    if test_cmd:
        test_context = f"\nTest command: {test_cmd}"

    review_prompt = (
        "Review and improve the code quality of the most recently built feature.\n"
        f"{test_context}\n\n"
        "Steps:\n"
        "1. Check 'git log --oneline -10' to see recent commits\n"
        "2. Identify source files for the most recent feature\n"
        "3. Review against senior engineering standards\n"
        "4. Fix critical and high-severity issues ONLY\n"
        "5. Do NOT change feature behavior\n"
        "6. Do NOT refactor working code for style preferences\n"
        f"7. Run the test suite (`{test_cmd}`) after your changes\n"
        "8. Commit fixes if any\n\n"
        "After completion, output exactly one of:\n"
        "REVIEW_CLEAN\n"
        "REVIEW_FIXED: {summary}\n"
        "REVIEW_FAILED: {reason}\n"
    )

    cmd_args = ["-p", "--dangerously-skip-permissions"]
    if model:
        cmd_args.extend(["--model", model])
    cmd_args.append(review_prompt)

    try:
        result = run_claude(
            cmd_args,
            cost_log_path=cost_log_path,
            timeout=timeout,
        )
        output = result.output
    except Exception:
        logger.exception("Review agent failed")
        return CodeReviewResult(passed=False, summary="agent error")

    if "REVIEW_CLEAN" in output or "REVIEW_FIXED" in output:
        logger.info("✓ Code review complete")
        summary = _parse_signal("REVIEW_FIXED", output) or "clean"
        return CodeReviewResult(passed=True, summary=summary)

    logger.warning("Code review reported issues it couldn't fix")
    reason = _parse_signal("REVIEW_FAILED", output) or "unknown"
    return CodeReviewResult(passed=False, summary=reason)
