# CONVERSION CHANGELOG (from scripts/build-loop-local.sh lines 1074–1236)
# - show_preflight_summary: accepts typed Feature list and config params
#   instead of parsing pipe-delimited topo_lines string. Logs via logger
#   instead of printf to stdout. Does NOT prompt for user input — the caller
#   handles AUTO_APPROVE logic.
# - build_feature_prompt: accepts feature_id, feature_name, project_dir, and
#   a BuildConfig dataclass instead of reading globals. Calls
#   generate_codebase_summary() and read_latest_eval_feedback() with explicit
#   arguments.
# - build_retry_prompt: accepts feature_id, feature_name, and failure context
#   (build_output, test_output, test_cmd) explicitly instead of reading
#   LAST_BUILD_OUTPUT / LAST_TEST_OUTPUT globals.
# - BuildConfig dataclass replaces the collection of env vars / globals that
#   bash functions read.
"""Prompt construction for the SDD build loop.

Provides functions to build the prompt strings sent to Claude agents
during feature builds, retries, and pre-flight summaries.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from auto_sdd.lib.codebase_summary import generate_codebase_summary
from auto_sdd.lib.drift import (
    MistakeTracker,
    get_cumulative_mistakes,
    read_latest_eval_feedback,
)
from auto_sdd.lib.reliability import Feature

logger = logging.getLogger(__name__)

# ── Prompt size limits (L-00178) ─────────────────────────────────────────────
# If a single injected section exceeds this, the solution is probably in the
# wrong layer. See L-00178: "Does a build tool, linter, test, or existing gate
# already enforce this constraint? If yes, ensure it runs."
MAX_INJECTED_SECTION_LINES = 150
MAX_TOTAL_PROMPT_LINES = 400


def _normalize_name(name: str) -> str:
    """Normalize a feature name for comparison: lowercase, spaces→hyphens."""
    return name.lower().replace(" ", "-").replace("_", "-")


def _resolve_spec_file(project_dir: Path, feature_name: str) -> str | None:
    """Find a spec file in .specs/features/ matching *feature_name*.

    Matching is case-insensitive with spaces/underscores normalised to hyphens.
    Returns the relative path (e.g. ``.specs/features/foo.feature.md``) when
    exactly one match is found, or ``None`` on zero / multiple matches.
    """
    features_dir = project_dir / ".specs" / "features"
    if not features_dir.is_dir():
        return None

    normalized = _normalize_name(feature_name)

    matches: list[Path] = []
    for path in features_dir.rglob("*"):
        if not path.is_file():
            continue
        stem = path.stem  # e.g. "auth-and-dashboard-shell.feature" → stem with .feature
        # Also strip compound suffixes like .feature before comparing
        bare = stem.split(".")[0]
        if _normalize_name(bare) == normalized:
            matches.append(path)

    if len(matches) == 1:
        try:
            return str(matches[0].relative_to(project_dir))
        except ValueError:
            return str(matches[0])
    return None


# ── Config dataclass ─────────────────────────────────────────────────────────


@dataclass
class BuildConfig:
    """Configuration for the build loop, replacing bash env vars / globals."""

    project_dir: Path
    main_branch: str = "main"
    drift_check: bool = True
    build_model: str | None = None
    retry_model: str | None = None
    drift_model: str | None = None
    review_model: str | None = None
    post_build_steps: str = ""
    max_features: int = 999
    max_retries: int = 3
    auto_approve: bool = False
    eval_output_dir: Path | None = None
    test_cmd: str = ""
    build_cmd: str = ""


# ── Pre-flight summary ──────────────────────────────────────────────────────


def show_preflight_summary(
    features: list[Feature],
    strategy: str,
    max_features: int,
    config: BuildConfig,
) -> None:
    """Log the pre-build summary of features to be built.

    This is a logging-only function. The caller handles user confirmation
    (AUTO_APPROVE logic) separately.

    Args:
        features: Topologically sorted list of pending features.
        strategy: Branch strategy name.
        max_features: Cap on features to build.
        config: Build configuration.
    """
    logger.info("")
    logger.info(
        "╔═══════════════════════════════════════════════════════════╗"
    )
    logger.info(
        "║  Pre-Flight Build Plan                                   ║"
    )
    logger.info(
        "╚═══════════════════════════════════════════════════════════╝"
    )
    logger.info("")
    logger.info("  %-4s %-40s %s", "#", "Feature", "Size")
    logger.info("  ──── ──────────────────────────────────────── ────")

    for feat in features:
        logger.info("  %-4d %-40s %s", feat.id, feat.name, feat.complexity)

    logger.info("")
    logger.info(
        "  Total features: %d (capped at MAX_FEATURES=%d)",
        len(features),
        max_features,
    )
    logger.info("")


# ── Build prompt ─────────────────────────────────────────────────────────────


def build_feature_prompt(
    feature_id: int,
    feature_name: str,
    project_dir: Path,
    config: BuildConfig,
    *,
    mistake_tracker: MistakeTracker | None = None,
) -> str:
    """Construct the build agent prompt for a specific feature.

    Calls ``generate_codebase_summary()`` and ``read_latest_eval_feedback()``
    to enrich the prompt with project context.

    Args:
        feature_id: Numeric feature ID from the roadmap.
        feature_name: Human-readable feature name.
        project_dir: Project root.
        config: Build configuration.
        mistake_tracker: Optional tracker for repeated mistakes.

    Returns:
        The complete prompt string for the build agent.
    """
    # Generate codebase summary
    codebase_summary = ""
    try:
        codebase_summary = generate_codebase_summary(project_dir)
    except Exception:
        logger.warning("Failed to generate codebase summary", exc_info=True)

    # Read eval feedback
    eval_feedback = ""
    if config.eval_output_dir is not None:
        eval_feedback = read_latest_eval_feedback(config.eval_output_dir)

    # Get cumulative mistakes
    cumulative_mistakes = ""
    if mistake_tracker is not None:
        cumulative_mistakes = get_cumulative_mistakes(mistake_tracker)

    # Resolve spec file path so the agent knows where to read
    resolved_spec = _resolve_spec_file(project_dir, feature_name)

    parts: list[str] = [
        f"Build feature #{feature_id}: {feature_name}\n",
        "Instructions:",
        f'1. Read .specs/roadmap.md and locate feature #{feature_id} ("{feature_name}")',
        "2. Update roadmap to mark it \U0001f504 in progress",
    ]

    # Step 3: direct implementation instructions (spec-aware)
    if resolved_spec is not None:
        parts.append(
            f"3. Read the feature spec at {resolved_spec} and implement "
            "the feature end-to-end based on its Gherkin scenarios"
        )
    else:
        parts.append(
            "3. Read the feature spec in .specs/features/ (if it exists) and "
            "implement the feature end-to-end"
        )
    parts.append("   - Read CLAUDE.md for project-specific constraints")
    parts.append("   - Run any build or test commands if they exist")

    parts.extend([
        "4. Update roadmap to mark it \u2705 completed",
        "5. Commit all changes with a descriptive message",
        "6. If build fails, output: BUILD_FAILED: {reason}\n",
        "CRITICAL IMPLEMENTATION RULES:",
        "- Seed data is fine; stub functions are not. Use seed data, fixtures, or "
        "realistic sample data to make features work.",
        "- NO stub functions that return hardcoded values or TODO placeholders. "
        "Every function must contain real logic.",
        "- NO placeholder UI. Components must be wired to real data sources.",
        "- Features must work end-to-end or they are not done.",
        "- Real validation, real error handling, real flows.\n",
    ])

    if codebase_summary:
        parts.append("## Codebase Summary (auto-generated)")
        parts.append(codebase_summary)

    if eval_feedback:
        parts.append("## Sidecar Eval Feedback (from previous build)")
        parts.append(eval_feedback)

    if cumulative_mistakes:
        parts.append("## Known Mistakes (accumulated across this campaign)")
        parts.append(cumulative_mistakes)

    # Build spec signal for output signals section
    if resolved_spec is not None:
        spec_signal = f"SPEC_FILE: {resolved_spec}"
    else:
        spec_signal = (
            "SPEC_FILE: {path to the .feature.md file you created/updated}"
        )

    parts.extend([
        "After completion, output EXACTLY these signals (each on its own line):",
        f"FEATURE_BUILT: {feature_name}",
        spec_signal,
        "SOURCE_FILES: {comma-separated paths to source files created/modified}\n",
        "Before outputting the SPEC_FILE signal, verify the path exists with `ls`."
        " If it doesn't match, report the actual path you find.\n",
        "Or if build fails:",
        "BUILD_FAILED: {reason}\n",
        "The SPEC_FILE and SOURCE_FILES lines are REQUIRED when FEATURE_BUILT is reported.",
        "They are used by the automated drift-check that runs after your build.",
    ])

    return "\n".join(parts)


# ── Retry prompt ─────────────────────────────────────────────────────────────


def build_retry_prompt(
    feature_id: int,
    feature_name: str,
    project_dir: Path,
    config: BuildConfig,
    *,
    build_output: str = "",
    test_output: str = "",
) -> str:
    """Construct the retry prompt for a failed feature build.

    Args:
        feature_id: Numeric feature ID.
        feature_name: Human-readable feature name.
        project_dir: Project root.
        config: Build configuration.
        build_output: Last build failure output (last 50 lines).
        test_output: Last test failure output (last 80 lines).

    Returns:
        The complete retry prompt string.
    """
    # Resolve spec file path so the agent reports the real path
    resolved_spec = _resolve_spec_file(project_dir, feature_name)
    if resolved_spec is not None:
        spec_signal = f"SPEC_FILE: {resolved_spec}"
    else:
        spec_signal = "SPEC_FILE: {path to the .feature.md file}"

    parts: list[str] = [
        "The previous build attempt FAILED. There are uncommitted changes or "
        "build errors from the last attempt.\n",
        "Your job:",
        '1. Run "git status" to understand the current state',
        "2. Look at .specs/roadmap.md to find the feature marked \U0001f504 in progress",
        "3. Fix whatever is broken — type errors, missing imports, incomplete "
        "implementation, failing tests",
        "4. Make sure the feature works end-to-end. Seed data is fine; stub "
        "functions are not.",
        f"5. Run the test suite to verify everything passes: {config.test_cmd}",
        "6. Commit all changes with a descriptive message",
        "7. Update roadmap to mark the feature \u2705 completed\n",
        "CRITICAL: Seed data is fine; stub functions are not. All features "
        "must use real function implementations, not placeholder stubs.\n",
        "After completion, output EXACTLY these signals (each on its own line):",
        f"FEATURE_BUILT: {feature_name}",
        spec_signal,
        "SOURCE_FILES: {comma-separated paths to source files created/modified}\n",
        "Before outputting the SPEC_FILE signal, verify the path exists with `ls`."
        " If it doesn't match, report the actual path you find.\n",
        "Or if build fails:",
        "BUILD_FAILED: {reason}",
    ]

    if build_output:
        parts.append(
            f"\nBUILD CHECK FAILURE OUTPUT (last 50 lines):\n{build_output}"
        )

    if test_output:
        parts.append(
            f"\nTEST SUITE FAILURE OUTPUT (last 80 lines):\n{test_output}"
        )

    parts.extend([
        "\n═══════════════════════════════════════════════════════════",
        "CRITICAL — REQUIRED OUTPUT SIGNAL:",
        "Your FINAL output lines MUST include exactly:",
        f"FEATURE_BUILT: {feature_name}",
        spec_signal,
        "SOURCE_FILES: {comma-separated paths to source files}\n",
        "The build loop uses the FEATURE_BUILT signal to detect success.",
        "If you omit it, your successful build will be marked as FAILED.",
        "If the build truly failed, output: BUILD_FAILED: {reason}",
        "═══════════════════════════════════════════════════════════",
    ])

    return "\n".join(parts)
