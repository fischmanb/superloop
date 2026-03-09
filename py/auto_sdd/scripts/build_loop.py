# CONVERSION CHANGELOG (from scripts/build-loop-local.sh lines 1237–2299,
#   plus main body lines 1885–2296 and sidecar lifecycle lines 1948–1995)
#
# - 3+1 success-recording deduplication: bash duplicated the success block
#   4 times (FEATURE_BUILT path ~1430-1480, drift-signal fallback ~1500-1530,
#   retry-signal fallback ~1560-1590, "both" mode independent pass ~2120-2160).
#   All four collapsed into _record_build_result().
# - write_build_summary: bash was 172 lines of manual JSON string construction
#   with sed escaping and heredoc templates. Replaced with ~30 lines using
#   json.dumps() via atomic_write_json pattern.
# - "both" mode independent pass extracted to _run_independent_pass() (bash
#   had it inline in the main body, making the control flow hard to follow).
# - Global mutable arrays (BUILT_FEATURE_NAMES, FEATURE_TIMINGS,
#   FEATURE_STATUSES, FEATURE_MODELS, LOOP_BUILT, LOOP_FAILED, etc.)
#   replaced with BuildLoop instance attributes.
# - env-var config: __init__ reads env vars once and stores typed fields.
#   bash re-read globals on every reference.
# - bash trap (cleanup_build_loop) replaced with atexit handler.
# - parse_signal / validate_required_signals: reuse drift._parse_signal.
# - format_duration / parse_token_usage / format_tokens: ported inline.
# - check_working_tree_clean / clean_working_tree: imported from build_gates.
# - CLAUDECODE env-var guard: now just a check + raise, not exit 1.
"""Core build-loop orchestration for the SDD build loop.

Encapsulates the main body + ``run_build_loop()`` from
``scripts/build-loop-local.sh`` in a single ``BuildLoop`` class.

Usage:
    python -m auto_sdd.scripts.build_loop

Configuration is read from environment variables (same names as bash) and
an optional ``.env.local`` file in the project directory.
"""
from __future__ import annotations

import atexit
import json
import logging
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from auto_sdd.lib.project_config import load_project_config
from auto_sdd.lib.branch_manager import (
    BranchSetupResult,
    cleanup_all_worktrees,
    cleanup_branch_chained,
    cleanup_branch_independent,
    cleanup_branch_sequential,
    cleanup_merged_branches,
    setup_branch_chained,
    setup_branch_independent,
    setup_branch_sequential,
)
from auto_sdd.lib.build_gates import (
    BuildCheckResult,
    DeadExportResult,
    _detect_package_manager,
    check_build,
    check_dead_exports,
    check_deps,
    check_lint,
    check_tests,
    check_working_tree_clean,
    clean_working_tree,
    detect_build_check,
    detect_test_check,
    run_cmd_safe,
    should_run_step,
)
from auto_sdd.lib.claude_wrapper import ClaudeResult, CreditExhaustionError, run_claude
from auto_sdd.lib.drift import (
    CodeReviewResult,
    DriftCheckResult,
    DriftTargets,
    MistakeTracker,
    check_drift,
    extract_drift_targets,
    read_latest_eval_feedback,
    run_code_review,
    update_repeated_mistakes,
)
from auto_sdd.lib.learnings_writer import write_learning
from auto_sdd.lib.prompt_builder import (
    BuildConfig,
    build_feature_prompt,
    build_fix_prompt,
    build_retry_prompt,
    show_preflight_summary,
)
from auto_sdd.lib.pattern_analysis import (
    generate_risk_context,
    run_analysis,
)
from auto_sdd.lib.vector_store import VectorStore, generate_campaign_id
from auto_sdd.lib.reliability import (
    AutoSddError,
    DriftPair,
    Feature,
    LockContentionError,
    ResumeState,
    acquire_lock,
    check_circular_deps,
    clean_state,
    emit_topo_order,
    read_state,
    release_lock,
    run_parallel_drift_checks,
    write_state,
)

logger = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _parse_signal(signal_name: str, output: str) -> str:
    """Extract the last value of a named signal from multiline output."""
    last_value = ""
    prefix = f"{signal_name}:"
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith(prefix):
            value = stripped[len(prefix):].strip()
            last_value = value
    return last_value


def _validate_required_signals(
    build_result: str,
    project_dir: Path | None = None,
) -> bool:
    """Return True if FEATURE_BUILT and SPEC_FILE signals are present."""
    feature_name = _parse_signal("FEATURE_BUILT", build_result)
    spec_file = _parse_signal("SPEC_FILE", build_result)

    if not feature_name:
        logger.warning("Missing required signal: FEATURE_BUILT")
        return False

    if not spec_file:
        logger.warning(
            "Missing required signal: SPEC_FILE (needed for drift check)"
        )
        return False

    # Resolve relative paths against project_dir so they don't resolve
    # against the loop's cwd (py/) which is different from the project root.
    resolved = Path(spec_file)
    if not resolved.is_absolute() and project_dir is not None:
        resolved = project_dir / resolved

    if not resolved.exists():
        logger.warning("SPEC_FILE does not exist on disk: %s", resolved)
        return False

    return True


def _format_duration(total_seconds: int) -> str:
    """Format seconds as human-readable duration."""
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    if hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    if minutes > 0:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def _parse_token_usage(output: str) -> int | None:
    """Parse total token count from agent output (best-effort).

    Looks for ``"input_tokens": N`` + ``"output_tokens": N`` JSON-style
    patterns, or ``Total tokens: N``.  Returns ``None`` if not found.
    """
    input_match = re.findall(r'"input_tokens"\s*:\s*(\d+)', output)
    output_match = re.findall(r'"output_tokens"\s*:\s*(\d+)', output)
    if input_match and output_match:
        return int(input_match[-1]) + int(output_match[-1])

    total_match = re.findall(r'(?i)total tokens\s*:\s*(\d+)', output)
    if total_match:
        return int(total_match[-1])

    return None


def _check_contamination(
    project_dir: Path,
    branch_start_commit: str,
) -> list[str]:
    """Check whether the agent modified files outside the project directory.

    Compares ``branch_start_commit..HEAD`` and returns a list of file paths
    whose resolved location falls outside *project_dir*.  An empty list
    means no contamination was detected.
    """
    if not branch_start_commit:
        return []

    resolved_root = project_dir.resolve()

    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", branch_start_commit, "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(project_dir),
            timeout=30,
        )
        if result.returncode != 0:
            logger.warning(
                "Contamination check: git diff failed (rc=%d)",
                result.returncode,
            )
            return []
    except (subprocess.TimeoutExpired, OSError):
        logger.warning("Contamination check: git diff timed out or errored")
        return []

    contaminated: list[str] = []
    for line in result.stdout.strip().splitlines():
        path = line.strip()
        if not path:
            continue
        full = (project_dir / path).resolve()
        try:
            full.relative_to(resolved_root)
        except ValueError:
            contaminated.append(path)

    if contaminated:
        logger.warning(
            "CONTAMINATION DETECTED: %d file(s) outside project root: %s",
            len(contaminated),
            ", ".join(contaminated),
        )

    return contaminated


# ── Auto-sdd repo contamination helpers ──────────────────────────────────────

_REPO_ROOT: Path = Path(__file__).resolve().parents[3]

_EXPECTED_WRITE_PATTERNS: frozenset[str] = frozenset({
    "logs/",
    "learnings/pending.md",
    "general-estimates.jsonl",
    ".onboarding-state",
    ".prompt-stash.json",
})

_PROTECT_DIRS: tuple[str, ...] = (
    "py/", "scripts/", "lib/", "tests/", ".claude/", "learnings/", "WIP/",
)

# Root-level files to protect. Matched by glob against repo root.
# These are outside _PROTECT_DIRS but agents could still write to them.
_PROTECT_ROOT_GLOBS: tuple[str, ...] = (
    "*.md",
    ".gitignore",
    ".env.local.example",
    "VERSION",
)


def _check_repo_contamination(
    repo_root: Path, allowlist: frozenset[str]
) -> list[str]:
    """Check auto-sdd's own working tree for unexpected modifications.

    Runs ``git status --porcelain`` on *repo_root* and returns paths that
    are modified/added/deleted but do NOT match any prefix in *allowlist*.
    Untracked files (``??``) are skipped — they may be pre-existing.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.warning(
                "Repo contamination check: git status failed (rc=%d)",
                result.returncode,
            )
            return []
    except (subprocess.TimeoutExpired, OSError):
        logger.warning("Repo contamination check: git status timed out or errored")
        return []

    contaminated: list[str] = []
    for line in result.stdout.splitlines():
        if not line or len(line) < 4:
            continue
        status = line[:2].strip()
        if status == "??":
            continue
        path = line[3:]
        if any(path.startswith(pat) for pat in allowlist):
            continue
        contaminated.append(path)

    return contaminated


def _protect_repo_tree(repo_root: Path) -> bool:
    """Make auto-sdd source directories read-only to prevent agent writes.

    Returns True if protection was applied, False on failure.
    """
    try:
        for d in _PROTECT_DIRS:
            target = repo_root / d
            if target.is_dir():
                subprocess.run(
                    ["chmod", "-R", "a-w", str(target)],
                    timeout=10,
                    capture_output=True,
                )
        # Protect root-level files (not inside any protected directory)
        for pattern in _PROTECT_ROOT_GLOBS:
            for f in repo_root.glob(pattern):
                if f.is_file():
                    f.chmod(f.stat().st_mode & ~0o222)  # remove write for all
        return True
    except Exception:
        logger.warning("Failed to apply write protection to repo tree")
        return False


def _restore_repo_tree(repo_root: Path) -> None:
    """Restore write permissions on auto-sdd source directories."""
    try:
        for d in _PROTECT_DIRS:
            target = repo_root / d
            if target.is_dir():
                subprocess.run(
                    ["chmod", "-R", "u+w", str(target)],
                    timeout=10,
                    capture_output=True,
                )
        # Restore root-level files
        for pattern in _PROTECT_ROOT_GLOBS:
            for f in repo_root.glob(pattern):
                if f.is_file():
                    f.chmod(f.stat().st_mode | 0o200)  # restore owner write
    except Exception:
        logger.warning("Failed to restore write permissions on repo tree")


# Dependency directories to auto-detect for git clean exclusions.
_DEP_DIRS = ("node_modules", "venv", ".venv", "target", "vendor")


def _detect_dep_excludes(project_dir: Path) -> list[str]:
    """Return ``-e <dir>`` args for each dependency directory that exists.

    Auto-detects common dependency directories (node_modules, venv, .venv,
    target, vendor) so ``git clean -fd`` doesn't delete them.
    """
    excludes: list[str] = []
    for d in _DEP_DIRS:
        if (project_dir / d).is_dir():
            excludes.extend(["-e", d])
    return excludes


def derive_component_types(
    project_dir: Path,
) -> tuple[list[str], list[str]]:
    """Categorize files changed in the last commit into component types.

    Runs ``git diff --name-only HEAD~1`` and classifies each path.

    Returns:
        Tuple of (component_types, files_touched).
        component_types: Deduplicated list of component type strings.
        files_touched: Raw list of file paths from the diff.
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1"],
            capture_output=True,
            text=True,
            cwd=str(project_dir),
            timeout=30,
        )
        if result.returncode != 0:
            return [], []
    except (subprocess.TimeoutExpired, OSError):
        return [], []

    types: set[str] = set()
    files_touched: list[str] = []
    for line in result.stdout.strip().splitlines():
        path = line.strip()
        if not path:
            continue
        files_touched.append(path)
        if path.endswith(".css") or path.endswith(".scss"):
            types.add("style")
        elif "/test" in path or ".test." in path or ".spec." in path:
            types.add("test")
        elif "/db/" in path or "/models/" in path or "/migrations/" in path:
            types.add("database")
        elif (
            path.startswith("client/")
            or path.startswith("src/components/")
        ):
            types.add("client")
        elif (
            path.startswith("server/")
            or path.startswith("src/api/")
            or path.startswith("src/routes/")
        ):
            types.add("server")
        else:
            types.add("other")
    return sorted(types), files_touched


def _load_env_local(project_dir: Path) -> None:
    """Load ``.env.local`` into os.environ without overwriting existing vars.

    Matches the bash behavior: command-line env vars win over .env.local.
    """
    env_file = project_dir / ".env.local"
    if not env_file.is_file():
        return

    for line in env_file.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)", stripped)
        if not match:
            continue
        key = match.group(1)
        if key in os.environ:
            continue  # Don't overwrite
        value = match.group(2)
        # Strip surrounding quotes
        for q in ('"', "'"):
            if value.startswith(q) and value.endswith(q):
                value = value[1:-1]
                break
        os.environ[key] = value


def _env_str(name: str, default: str = "") -> str:
    """Read an env var as string with a default."""
    return os.environ.get(name, default)


def _env_int(name: str, default: int) -> int:
    """Read an env var as int with a default."""
    raw = os.environ.get(name, "")
    if raw:
        try:
            return int(raw)
        except ValueError:
            pass
    return default


def _env_bool(name: str, default: bool) -> bool:
    """Read an env var as bool with a default."""
    raw = os.environ.get(name, "")
    if not raw:
        return default
    return raw.lower() in ("true", "1", "yes")


def _get_head(project_dir: Path) -> str:
    """Return the current HEAD commit hash."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(project_dir),
            timeout=30,
        )
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        return ""


# ── Feature timing / status dataclass ──────────────────────────────────────


@dataclass
class FeatureRecord:
    """Tracking data for a single feature build attempt."""

    name: str
    status: str  # "built" or "failed"
    model: str
    duration_seconds: int
    source_files: str = ""
    test_count: int | None = None
    token_usage: int | None = None


# ── BuildLoop class ──────────────────────────────────────────────────────────


class BuildLoop:
    """Encapsulates all build-loop state and orchestration.

    Replaces the 333-line main body + 435-line ``run_build_loop()`` function
    from the bash script.
    """

    def __init__(self) -> None:
        # ── Load .env.local ──────────────────────────────────────────────
        project_dir_str = os.environ.get("PROJECT_DIR", "")
        if project_dir_str:
            self.project_dir = Path(project_dir_str).resolve()
        else:
            self.project_dir = Path.cwd().resolve()

        _load_env_local(self.project_dir)

        # Load .sdd-config/project.yaml — sets env var defaults before any
        # _env_str() reads. Env vars already set in environment take precedence.
        load_project_config(self.project_dir)

        # ── Configuration ────────────────────────────────────────────────
        self.main_branch = _env_str("MAIN_BRANCH", "")
        if not self.main_branch:
            base = _env_str("BASE_BRANCH", "")
            if base:
                self.main_branch = base
            else:
                try:
                    result = subprocess.run(
                        ["git", "branch", "--show-current"],
                        capture_output=True,
                        text=True,
                        cwd=str(self.project_dir),
                        timeout=10,
                    )
                    self.main_branch = result.stdout.strip() or "main"
                except (subprocess.TimeoutExpired, OSError):
                    self.main_branch = "main"
                # Reject stale campaign branches
                if self.main_branch.startswith("auto/"):
                    logger.warning(
                        "MAIN_BRANCH detected as '%s' (stale campaign "
                        "branch). Resetting to 'main'.",
                        self.main_branch,
                    )
                    self.main_branch = "main"

        self.branch_strategy = _env_str("BRANCH_STRATEGY", "chained")
        self.max_features: int | None = (
            int(os.environ["MAX_FEATURES"]) if "MAX_FEATURES" in os.environ else None
        )
        self.max_retries = _env_int("MAX_RETRIES", 1)
        self.min_retry_delay = _env_int("MIN_RETRY_DELAY", 30)
        self.build_mode = _env_str("BUILD_MODE", "single")
        self.drift_check = _env_bool("DRIFT_CHECK", True)
        self.max_drift_retries = _env_int("MAX_DRIFT_RETRIES", 1)
        self.post_build_steps = _env_str(
            "POST_BUILD_STEPS", "test,dead-code,lint"
        )
        self.parallel_validation = _env_bool("PARALLEL_VALIDATION", False)
        self.enable_resume = _env_bool("ENABLE_RESUME", True)

        # Model selection
        self.agent_model = _env_str("AGENT_MODEL", "")
        self.build_model = _env_str("BUILD_MODEL", "")
        self.retry_model = _env_str("RETRY_MODEL", "")
        self.drift_model = _env_str("DRIFT_MODEL", "")
        self.review_model = _env_str("REVIEW_MODEL", "")

        # Agent timeout (seconds)
        self.agent_timeout = _env_int("AGENT_TIMEOUT", 1800)

        # Gate failure tracking — populated by _run_post_build_gates
        # so the retry loop can pass failure details to fix/retry prompts.
        self._last_gate_name: str = ""
        self._last_gate_build_output: str = ""
        self._last_gate_test_output: str = ""
        self._last_gate_test_count: int | None = None


        # Paths
        logs_dir_str = _env_str("LOGS_DIR", "")
        if logs_dir_str:
            self.logs_dir = Path(logs_dir_str)
        else:
            self.logs_dir = (
                self.project_dir.parent
                / "logs"
                / self.project_dir.name
            )
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        self.resume_file = (
            self.project_dir / ".sdd-state" / "resume.json"
        )
        self.eval_output_dir = Path(
            _env_str(
                "EVAL_OUTPUT_DIR",
                str(self.logs_dir / "evals"),
            )
        )
        self.cost_log_path = Path(
            _env_str(
                "COST_LOG_FILE",
                str(self.logs_dir / "cost-log.jsonl"),
            )
        )

        # Auto-detect build/test commands
        build_override = _env_str("BUILD_CHECK_CMD", "") or None
        test_override = _env_str("TEST_CHECK_CMD", "") or None
        self.build_cmd = detect_build_check(
            self.project_dir, build_override
        )
        self.test_cmd = detect_test_check(
            self.project_dir, test_override
        )

        # ── BuildConfig for prompt_builder ───────────────────────────────
        self.build_config = BuildConfig(
            project_dir=self.project_dir,
            main_branch=self.main_branch,
            drift_check=self.drift_check,
            build_model=self.build_model or None,
            retry_model=self.retry_model or None,
            drift_model=self.drift_model or None,
            review_model=self.review_model or None,
            post_build_steps=self.post_build_steps,
            max_features=self.max_features,
            max_retries=self.max_retries,
            eval_output_dir=self.eval_output_dir,
            test_cmd=self.test_cmd,
            build_cmd=self.build_cmd,
        )

        # ── Mutable tracking state ──────────────────────────────────────
        self.built_feature_names: list[str] = []
        self.feature_records: list[FeatureRecord] = []
        self.loop_timings: list[str] = []
        self.loop_built: int = 0
        self.loop_failed: int = 0
        self.loop_skipped: list[str] = []
        self.drift_pairs: list[DriftPair] = []
        self.last_feature_branch: str = ""
        self.eval_sidecar_pid: int | None = None
        self.eval_sidecar_proc: subprocess.Popen[bytes] | None = None
        self.mistake_tracker = MistakeTracker()
        self.script_start: int = int(time.time())
        self._loop_limit: int = 0
        self._current_strategy: str = ""

        # ── Campaign Intelligence System ────────────────────────────────
        self.campaign_id = generate_campaign_id(
            strategy=self.branch_strategy,
            model=self.build_model or self.agent_model or "unknown",
        )
        self.vector_store = VectorStore(
            self.project_dir / ".sdd-state" / "feature-vectors.jsonl"
        )
        self.analysis_interval = int(
            _env_str("ANALYSIS_INTERVAL", "3")
        )

        # ── Acquire lock ─────────────────────────────────────────────────
        lock_dir = Path(tempfile.gettempdir())
        safe_name = str(self.project_dir).replace("/", "_").replace(
            " ", "_"
        )
        self.lock_file = lock_dir / f"sdd-build-loop-{safe_name}.lock"
        acquire_lock(self.lock_file)

        # ── Register cleanup ─────────────────────────────────────────────
        atexit.register(self._cleanup)

    # ── Cleanup ──────────────────────────────────────────────────────────

    def _cleanup(self) -> None:
        """Release lock and stop sidecar on exit."""
        self.stop_eval_sidecar()
        try:
            release_lock(self.lock_file)
        except Exception:
            logger.debug("Lock release failed during cleanup", exc_info=True)

    # ── Core entry point ─────────────────────────────────────────────────

    def run(self) -> None:
        """Execute the full build loop."""
        check_circular_deps(self.project_dir)

        features = emit_topo_order(self.project_dir)
        if not features:
            logger.info(
                "No pending features found in roadmap — nothing to build"
            )
            return

        # Resume state
        if self.enable_resume:
            state = read_state(self.resume_file)
            if state is not None:
                if state.branch_strategy != self.branch_strategy:
                    logger.warning(
                        "Branch strategy changed (was: %s, now: %s) "
                        "— resetting resume state",
                        state.branch_strategy,
                        self.branch_strategy,
                    )
                    clean_state(self.resume_file)
                else:
                    self.built_feature_names = list(
                        state.completed_features
                    )
                    if state.current_branch:
                        self.last_feature_branch = state.current_branch
                    logger.info(
                        "Resuming: %d features already completed",
                        len(self.built_feature_names),
                    )

        show_preflight_summary(
            features,
            self.branch_strategy,
            self.max_features,
            self.build_config,
        )

        # Human pre-flight gate — separate from AUTO_APPROVE.
        # SKIP_PREFLIGHT=true bypasses this (for unattended/CI runs).
        # AUTO_APPROVE controls agent-level confirmations only.
        # Also skipped if stdin is not a TTY (e.g. subprocess, CI, tests).
        if os.environ.get("SKIP_PREFLIGHT", "").lower() != "true":
            import sys as _sys
            if _sys.stdin.isatty():
                answer = input("  Proceed with build? [Y/n] ").strip()
                if answer and not answer.lower().startswith("y"):
                    logger.info("Build cancelled by user.")
                    return
            else:
                logger.info("Non-interactive stdin — skipping pre-flight prompt")

        self.start_eval_sidecar()

        if self.branch_strategy == "both":
            self._run_both_mode(features)
        else:
            self._run_single_mode(features)

    # ── Single mode (chained / independent / sequential) ─────────────────

    def _run_single_mode(self, features: list[Feature]) -> None:
        """Run a single-strategy build loop and final cleanup."""
        self._run_build_loop(self.branch_strategy, features)

        if self.branch_strategy == "independent":
            cleanup_all_worktrees(self.project_dir)

        total_elapsed = int(time.time()) - self.script_start

        logger.info("")
        logger.info(
            "Done. Built: %d, Failed: %d (total: %s)",
            self.loop_built,
            self.loop_failed,
            _format_duration(total_elapsed),
        )

        self._print_timings()

        summary_path = self.write_build_summary(total_elapsed)
        logger.info("Summary written to: %s", summary_path)

        # Post-campaign clean-room verification
        if not self._post_campaign_verify():
            logger.error(
                "POST-CAMPAIGN VERIFICATION FAILED — the combined project "
                "has dependency or build issues that were not caught per-feature"
            )

        cleanup_merged_branches(self.project_dir, self.main_branch)

        if self.enable_resume and self.loop_failed == 0:
            clean_state(self.resume_file)

        self.stop_eval_sidecar()

    # ── Both mode (chained then independent) ─────────────────────────────

    def _run_both_mode(self, features: list[Feature]) -> None:
        """Run chained pass, then independent pass."""
        logger.info("PASS 1 of 2: CHAINED")
        self._run_build_loop("chained", features)
        chained_built = self.loop_built
        chained_failed = self.loop_failed
        chained_names = list(self.built_feature_names)

        logger.info(
            "✓ Chained pass complete: %d built, %d failed",
            chained_built,
            chained_failed,
        )

        if chained_built > 0:
            logger.info("PASS 2 of 2: INDEPENDENT")
            self._run_independent_pass(chained_names)

        cleanup_all_worktrees(self.project_dir)

        total_elapsed = int(time.time()) - self.script_start
        summary_path = self.write_build_summary(total_elapsed)
        logger.info("Summary written to: %s", summary_path)

        # Post-campaign clean-room verification
        if not self._post_campaign_verify():
            logger.error(
                "POST-CAMPAIGN VERIFICATION FAILED — the combined project "
                "has dependency or build issues that were not caught per-feature"
            )

        cleanup_merged_branches(self.project_dir, self.main_branch)

        if self.enable_resume:
            clean_state(self.resume_file)

        self.stop_eval_sidecar()

    # ── CRITICAL DEDUPLICATION: _record_build_result ─────────────────────

    def _record_build_result(
        self,
        feature_name: str,
        status: str,
        model: str,
        duration: int,
        branch: str,
        *,
        source_files: str = "",
        test_count: int | None = None,
        build_output: str = "",
        vector_id: str = "",
        injections_received: list[str] | None = None,
        retry_count: int = 0,
        drift_check_passed: bool = True,
        test_check_passed: bool = True,
    ) -> None:
        """Record the result of a feature build attempt.

        Consolidates the 3+1 duplicated success-recording blocks from bash.
        """
        record = FeatureRecord(
            name=feature_name,
            status=status,
            model=model,
            duration_seconds=duration,
            source_files=source_files,
            test_count=test_count,
            token_usage=_parse_token_usage(build_output),
        )
        self.feature_records.append(record)

        # ── CIS: update build_signals_v1 ────────────────────────────────
        if vector_id:
            try:
                comp_types, files_touched = derive_component_types(
                    self.project_dir
                )
                self.vector_store.update_section(
                    vector_id,
                    "build_signals_v1",
                    {
                        "build_success": status == "built",
                        "retry_count": retry_count,
                        "agent_model": model,
                        "build_duration_seconds": duration,
                        "drift_check_passed": drift_check_passed,
                        "test_check_passed": test_check_passed,
                        "injections_received": injections_received or [],
                        "component_types": comp_types,
                        "touches_shared_modules": "database" in comp_types,
                        "files_touched": files_touched,
                    },
                )
            except Exception:
                logger.debug(
                    "Vector store error at build end", exc_info=True
                )

        if status == "built":
            self.loop_built += 1
            self.built_feature_names.append(feature_name)
            self.loop_timings.append(
                f"✓ {feature_name}: {_format_duration(duration)}"
            )
            self._print_progress(
                self._loop_limit,
                feature_name=feature_name,
                phase=f"✓ BUILT in {_format_duration(duration)}",
                strategy=self._current_strategy,
                model=model,
                branch=branch,
            )
        else:
            self.loop_failed += 1
            self.loop_skipped.append(feature_name)
            self.loop_timings.append(
                f"✗ {feature_name}: {_format_duration(duration)}"
            )
            self._print_progress(
                self._loop_limit,
                feature_name=feature_name,
                phase=f"✗ FAILED after {_format_duration(duration)}",
                strategy=self._current_strategy,
                model=model,
                branch=branch,
            )
            # Write build failure learning
            tail = build_output[-2000:] if len(build_output) > 2000 else build_output
            write_learning(
                summary=f"Build failure: {feature_name} (status={status}, retries={retry_count})",
                detail=(
                    f"Model: {model}  Duration: {_format_duration(duration)}\n"
                    f"Drift check passed: {drift_check_passed}  "
                    f"Test check passed: {test_check_passed}\n"
                    f"Build output tail:\n{tail}"
                ),
                category="build-failure",
                project_name=self.project_dir.name,
                feature_name=feature_name,
                project_dir=self.project_dir,
                repo_dir=Path(__file__).resolve().parents[3],
            )

        # Queue sidecar feedback
        eval_feedback = read_latest_eval_feedback(self.eval_output_dir)
        if eval_feedback:
            update_repeated_mistakes(
                eval_feedback, self.mistake_tracker
            )

        # Save resume state
        if self.enable_resume and status == "built":
            write_state(
                self.resume_file,
                0,  # feature_index not used for lookup — we use names
                self.branch_strategy,
                list(self.built_feature_names),
                branch,
            )

        # ── CIS: periodic pattern analysis ──────────────────────────────
        completed = self.loop_built + self.loop_failed
        if (
            self.analysis_interval > 0
            and completed > 0
            and completed % self.analysis_interval == 0
        ):
            self._run_pattern_analysis()

    def _run_pattern_analysis(self) -> None:
        """Run pattern analysis on current campaign vectors and write risk context."""
        try:
            vectors = self.vector_store.query_vectors(
                {"campaign_id": self.campaign_id}
            )
            findings = run_analysis(vectors)
            risk_text = generate_risk_context(findings, len(vectors))
            if risk_text:
                risk_path = (
                    self.eval_output_dir / "risk-context.md"
                )
                risk_path.parent.mkdir(parents=True, exist_ok=True)
                risk_path.write_text(risk_text)
                logger.info(
                    "CIS: wrote risk context (%d findings) to %s",
                    len(findings),
                    risk_path,
                )
        except Exception:
            logger.debug(
                "CIS: pattern analysis failed (non-fatal)", exc_info=True
            )

    # ── Core build loop ──────────────────────────────────────────────────

    def _run_build_loop(
        self,
        strategy: str,
        features: list[Feature],
    ) -> None:
        """Build features using the given strategy.

        Converts ``run_build_loop()`` from bash lines 1237–1665.
        """
        self.loop_built = 0
        self.loop_failed = 0
        self.loop_skipped = []
        self.loop_timings = []
        self.drift_pairs = []
        current_feature_branch = ""
        current_worktree_path: Path | None = None

        loop_limit = len(features) if self.max_features is None else min(len(features), self.max_features)
        self._loop_limit = loop_limit
        self._current_strategy = strategy

        for idx in range(loop_limit):
            feature = features[idx]

            # Skip already-completed features (resume case)
            if feature.name in self.built_feature_names:
                logger.info(
                    "[%s] Skipping already-built feature: %s",
                    strategy,
                    feature.name,
                )
                continue

            feature_start = int(time.time())

            # ── CIS: create feature vector ──────────────────────────────
            current_vector_id = ""
            try:
                current_vector_id = self.vector_store.create_vector({
                    "feature_id": feature.id,
                    "feature_name": feature.name,
                    "campaign_id": self.campaign_id,
                    "build_order_position": idx,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                self.vector_store.update_section(
                    current_vector_id,
                    "pre_build_v1",
                    {
                        "complexity_tier": feature.complexity or "unknown",
                        "dependency_count": 0,
                        "branch_strategy": self.branch_strategy,
                    },
                )
            except Exception:
                logger.debug(
                    "Vector store error at feature start", exc_info=True
                )

            self._print_progress(
                loop_limit,
                feature_name=feature.name,
                phase="starting build",
                attempt=1,
                max_attempts=self.max_retries + 1,
                model=self.build_model or self.agent_model or "default",
                branch=current_feature_branch or "(pending setup)",
                strategy=strategy,
            )

            # ── Branch setup ─────────────────────────────────────────────
            try:
                if strategy == "chained":
                    branch_result = setup_branch_chained(
                        self.project_dir,
                        feature.name,
                        self.last_feature_branch or None,
                        self.main_branch,
                    )
                elif strategy == "independent":
                    branch_result = setup_branch_independent(
                        self.project_dir,
                        feature.name,
                        self.main_branch,
                    )
                else:  # sequential
                    branch_result = setup_branch_sequential(
                        self.project_dir
                    )
                current_feature_branch = branch_result.branch_name
                current_worktree_path = branch_result.worktree_path
            except AutoSddError as exc:
                logger.error("Failed to setup branch: %s", exc)
                continue

            clean_working_tree(self.project_dir)

            # Save starting commit for clean retries
            branch_start_commit = _get_head(self.project_dir)

            # ── Build attempts ───────────────────────────────────────────
            feature_done = False
            last_build_output = ""
            last_test_output = ""
            failed_attempt_outputs: list[str] = []  # full output from each failed attempt
            prior_attempt_summaries: list[dict[str, str]] = []  # for informed retry prompt

            for attempt in range(self.max_retries + 1):
                if attempt > 0:
                    logger.warning(
                        "Retry %d/%d — waiting %ds",
                        attempt,
                        self.max_retries,
                        self.min_retry_delay,
                    )
                    time.sleep(self.min_retry_delay)

                # ── Stage 1 (attempt 1): fix-in-place — code still on disk ──
                # ── Stage 2 (attempt 2+): informed fresh retry — git reset ──
                if attempt >= 2:
                    subprocess.run(
                        ["git", "reset", "--hard", branch_start_commit],
                        capture_output=True,
                        text=True,
                        cwd=str(self.project_dir),
                        timeout=30,
                    )
                    dep_excludes = _detect_dep_excludes(self.project_dir)
                    subprocess.run(
                        [
                            "git", "clean", "-fd",
                            *dep_excludes,
                            "-e", ".env.local",
                            "-e", ".sdd-state",
                            "-e", "logs",
                            "-e", ".build-worktrees",
                        ],
                        capture_output=True,
                        text=True,
                        cwd=str(self.project_dir),
                        timeout=30,
                    )

                # Build the prompt
                injections_received: list[str] = []
                if attempt == 0:
                    # ── Initial build ────────────────────────────────────
                    prompt, injections_received = build_feature_prompt(
                        feature.id,
                        feature.name,
                        self.project_dir,
                        self.build_config,
                        mistake_tracker=self.mistake_tracker,
                    )
                    model = self.build_model or self.agent_model or None
                elif attempt == 1:
                    # ── Fix attempt — code on disk, diagnose & fix ───────
                    prompt = build_fix_prompt(
                        feature.id,
                        feature.name,
                        self.project_dir,
                        self.build_config,
                        gate_name=self._last_gate_name,
                        build_output=self._last_gate_build_output,
                        test_output=self._last_gate_test_output or last_test_output,
                    )
                    model = self.retry_model or self.build_model or self.agent_model or None
                else:
                    # ── Informed fresh retry — reset done, new approach ──
                    prompt = build_retry_prompt(
                        feature.id,
                        feature.name,
                        self.project_dir,
                        self.build_config,
                        build_output=last_build_output,
                        test_output=last_test_output,
                        prior_attempts=prior_attempt_summaries,
                    )
                    model = self.retry_model or self.build_model or self.agent_model or None

                # Invoke agent
                self._print_progress(
                    loop_limit,
                    feature_name=feature.name,
                    phase="invoking agent" if attempt == 0 else (f"fix attempt — invoking agent" if attempt == 1 else f"retry #{attempt} — invoking agent"),
                    attempt=attempt + 1,
                    max_attempts=self.max_retries + 1,
                    model=model or "default",
                    branch=current_feature_branch,
                    strategy=strategy,
                )
                cmd_args = ["-p", "--dangerously-skip-permissions"]
                if model:
                    cmd_args.extend(["--model", model])
                cmd_args.append(prompt)

                protected = _protect_repo_tree(_REPO_ROOT)
                try:
                    result = run_claude(
                        cmd_args,
                        cost_log_path=self.cost_log_path,
                        timeout=self.agent_timeout,
                        cwd=self.project_dir,
                    )
                    build_result = result.output
                except CreditExhaustionError:
                    logger.error("API credits exhausted — halting build loop")
                    raise SystemExit(1)
                except Exception:
                    logger.exception("Agent invocation failed")
                    build_result = ""
                finally:
                    if protected:
                        _restore_repo_tree(_REPO_ROOT)
                        # TIMING DEPENDENCY: learnings/pending.md is written by
                        # write_learning() calls later in this method (via
                        # _record_build_result). learnings/ is in _PROTECT_DIRS,
                        # so writes MUST happen after restore. Do not move
                        # write_learning() calls above this point.

                    # ── Repo contamination audit (runs on ALL outcomes) ──
                    repo_contaminated = _check_repo_contamination(
                        _REPO_ROOT, _EXPECTED_WRITE_PATTERNS
                    )
                    if repo_contaminated:
                        for cpath in repo_contaminated:
                            logger.error(
                                "REPO_CONTAMINATION: %s", cpath
                            )

                # Re-detect build/test commands AFTER agent runs — project
                # structure may have changed (e.g., F-0 creates next.config.ts
                # so detection before the agent returns empty string).
                self.build_cmd = detect_build_check(self.project_dir, _env_str("BUILD_CHECK_CMD", "") or None)
                self.test_cmd = detect_test_check(self.project_dir, _env_str("TEST_CHECK_CMD", "") or None)
                self.build_config.build_cmd = self.build_cmd
                self.build_config.test_cmd = self.test_cmd

                # Check for "no features ready"
                if "NO_FEATURES_READY" in build_result:
                    logger.info("No more features ready to build")
                    feature_done = True
                    self._cleanup_branch_on_no_features(
                        strategy,
                        current_feature_branch,
                        current_worktree_path,
                    )
                    return

                # ── Check FEATURE_BUILT signal ───────────────────────────
                if "FEATURE_BUILT" in build_result:
                    feature_name = _parse_signal(
                        "FEATURE_BUILT", build_result
                    )

                    # Skip if already built (resume edge case)
                    if feature_name in self.built_feature_names:
                        logger.info(
                            "[%s] Skipping already-built: %s",
                            strategy,
                            feature_name,
                        )
                        feature_done = True
                        break

                    # Verify: HEAD moved, clean tree, build passes, tests pass
                    self._print_progress(
                        loop_limit,
                        feature_name=feature_name or feature.name,
                        phase="post-build gates",
                        attempt=attempt + 1,
                        max_attempts=self.max_retries + 1,
                        model=model or "default",
                        branch=current_feature_branch,
                        strategy=strategy,
                    )
                    if self._run_post_build_gates(
                        build_result, feature_name or feature.name,
                        branch_start_commit=branch_start_commit,
                    ):
                        duration = int(time.time()) - feature_start
                        drift_targets = extract_drift_targets(
                            build_result, self.project_dir
                        )
                        self._record_build_result(
                            feature_name or feature.name,
                            "built",
                            model or "default",
                            duration,
                            current_feature_branch,
                            source_files=drift_targets.source_files,
                            test_count=self._last_gate_test_count,
                            build_output=build_result,
                            vector_id=current_vector_id,
                            injections_received=injections_received,
                            retry_count=attempt,
                        )
                        # Write retry context for eval sidecar if this needed retries
                        if attempt > 0:
                            commit_hash = _get_head(self.project_dir) or "unknown"
                            retry_context = {
                                "commit_hash": commit_hash,
                                "feature_name": feature_name or feature.name,
                                "attempt_number": attempt + 1,
                                "total_attempts": attempt + 1,
                                "failed_attempts": [
                                    {"attempt": i + 1, "build_output": out}
                                    for i, out in enumerate(failed_attempt_outputs)
                                ],
                            }
                            retry_dir = self.eval_output_dir / "retry-context"
                            retry_dir.mkdir(parents=True, exist_ok=True)
                            retry_file = retry_dir / f"{commit_hash[:8]}.retry.json"
                            try:
                                retry_file.write_text(
                                    json.dumps(retry_context, indent=2)
                                )
                                logger.debug(
                                    "Wrote retry context for %s → %s",
                                    feature_name,
                                    retry_file,
                                )
                            except OSError:
                                logger.debug(
                                    "Failed to write retry context", exc_info=True
                                )
                            # Also write retry learning to both locations
                            failed_list: list[dict[str, str]] = retry_context["failed_attempts"]  # type: ignore[assignment]
                            failure_summaries = "\n".join(
                                f"Attempt {fa['attempt']}: "
                                + fa["build_output"].strip()[-300:]
                                for fa in failed_list
                            )
                            write_learning(
                                summary=(
                                    f"{feature_name or feature.name} required "
                                    f"{attempt + 1} attempts before passing gates"
                                ),
                                detail=(
                                    f"Feature passed on attempt {attempt + 1}. "
                                    f"Earlier attempt(s) failed:\n\n{failure_summaries}"
                                ),
                                category="retry",
                                project_name=self.project_dir.name,
                                feature_name=feature_name or feature.name,
                                project_dir=self.project_dir,
                                repo_dir=Path(__file__).resolve().parents[3],
                            )
                        feature_done = True
                        break
                    else:
                        # Gates failed — will retry
                        failed_attempt_outputs.append(build_result)
                        last_build_output = build_result[-2000:]
                        last_test_output = self._last_gate_test_output or ""
                        # Build structured summary for informed retry
                        prior_attempt_summaries.append({
                            "attempt": str(attempt + 1),
                            "failure_mode": self._last_gate_name or "unknown",
                            "summary": (
                                self._last_gate_test_output[:500]
                                or self._last_gate_build_output[:500]
                                or build_result[-500:]
                            ),
                        })

                # ── Signal fallback: drift-clean output ──────────────────
                if not feature_done and "FEATURE_BUILT" not in build_result:
                    if re.search(r"NO_DRIFT|DRIFT_FIXED", build_result):
                        head_now = _get_head(self.project_dir)
                        if (
                            head_now
                            and head_now != branch_start_commit
                            and check_working_tree_clean(self.project_dir)
                        ):
                            build_ok = check_build(
                                self.build_cmd, self.project_dir
                            )
                            if build_ok.success:
                                test_ok = True
                                gate_test_count: int | None = None
                                if should_run_step(
                                    "test", self.post_build_steps
                                ):
                                    test_result = check_tests(
                                        self.test_cmd, self.project_dir
                                    )
                                    test_ok = test_result.success
                                    gate_test_count = test_result.test_count
                                if test_ok:
                                    logger.warning(
                                        "Inferred success from drift "
                                        "signal (no FEATURE_BUILT)"
                                    )
                                    duration = (
                                        int(time.time()) - feature_start
                                    )
                                    self._record_build_result(
                                        feature.name,
                                        "built",
                                        model or "default",
                                        duration,
                                        current_feature_branch,
                                        test_count=gate_test_count,
                                        build_output=build_result,
                                        vector_id=current_vector_id,
                                        injections_received=injections_received,
                                        retry_count=attempt,
                                    )
                                    feature_done = True
                                    break

                # ── Signal fallback: retry inferred success ──────────────
                if not feature_done and "BUILD_FAILED" not in build_result:
                    head_now = _get_head(self.project_dir)
                    if (
                        attempt > 0
                        and head_now
                        and head_now != branch_start_commit
                        and check_working_tree_clean(self.project_dir)
                    ):
                        build_ok = check_build(
                            self.build_cmd, self.project_dir
                        )
                        if build_ok.success:
                            test_ok = True
                            retry_test_count: int | None = None
                            if should_run_step(
                                "test", self.post_build_steps
                            ):
                                test_result = check_tests(
                                    self.test_cmd, self.project_dir
                                )
                                test_ok = test_result.success
                                retry_test_count = test_result.test_count
                            if test_ok:
                                logger.warning(
                                    "Retry produced passing build "
                                    "without FEATURE_BUILT signal "
                                    "— inferring success"
                                )
                                duration = (
                                    int(time.time()) - feature_start
                                )
                                self._record_build_result(
                                    feature.name,
                                    "built",
                                    model or "default",
                                    duration,
                                    current_feature_branch,
                                    test_count=retry_test_count,
                                    build_output=build_result,
                                    vector_id=current_vector_id,
                                    injections_received=injections_received,
                                    retry_count=attempt,
                                )
                                feature_done = True
                                break

                # Build failed — store outputs for retry prompt
                if "BUILD_FAILED" in build_result:
                    reason = _parse_signal("BUILD_FAILED", build_result)
                    logger.warning("Build failed: %s", reason)
                    if not feature_done:
                        failed_attempt_outputs.append(build_result)
                        prior_attempt_summaries.append({
                            "attempt": str(attempt + 1),
                            "failure_mode": "BUILD_FAILED",
                            "summary": reason or build_result[-500:],
                        })

                last_build_output = build_result[-2000:]

            # ── Post-loop: branch cleanup ────────────────────────────────
            if feature_done:
                if strategy == "chained":
                    self.last_feature_branch = cleanup_branch_chained(
                        current_feature_branch
                    )
                elif strategy == "independent":
                    cleanup_branch_independent(
                        current_worktree_path,
                        self.project_dir,
                        current_feature_branch,
                    )
                elif strategy == "sequential":
                    cleanup_branch_sequential()
            else:
                # Feature failed after all retries
                duration = int(time.time()) - feature_start
                self._record_build_result(
                    feature.name,
                    "failed",
                    model or "default",
                    duration,
                    current_feature_branch,
                    build_output=build_result if build_result else "",
                    vector_id=current_vector_id,
                    injections_received=injections_received,
                    retry_count=self.max_retries,
                )
                # Best-effort drift check on failure path: if the agent
                # emitted SPEC_FILE/SOURCE_FILES signals, run drift regardless
                # of gate outcome so misalignment is captured in learnings.
                if build_result and self.drift_check:
                    _fail_targets = extract_drift_targets(
                        build_result, self.project_dir
                    )
                    if _fail_targets.spec_file:
                        logger.info(
                            "Running best-effort drift check on failed feature: %s",
                            feature.name,
                        )
                        try:
                            check_drift(
                                _fail_targets.spec_file,
                                _fail_targets.source_files,
                                self.project_dir,
                                model=self.drift_model or None,
                                max_retries=0,  # no retries on failure path
                                drift_enabled=True,
                                test_cmd=self.test_cmd,
                                cost_log_path=self.cost_log_path,
                                project_name=self.project_dir.name,
                                feature_name=feature.name,
                                repo_dir=Path(__file__).resolve().parents[3],
                            )
                        except Exception:
                            logger.debug(
                                "Best-effort drift check failed", exc_info=True
                            )
                clean_working_tree(self.project_dir)
                self._cleanup_failed_branch(
                    strategy,
                    current_feature_branch,
                    current_worktree_path,
                )

            # ── Sidecar health check ─────────────────────────────────────
            self._check_sidecar_health()

        # After loop: parallel drift checks
        if self.parallel_validation and self.drift_pairs:
            logger.info(
                "Running %d deferred drift checks in parallel...",
                len(self.drift_pairs),
            )

            def _drift_check_fn(
                spec_file: Path, source_files: str
            ) -> bool:
                result = check_drift(
                    str(spec_file),
                    source_files,
                    self.project_dir,
                    model=self.drift_model or None,
                    max_retries=self.max_drift_retries,
                    drift_enabled=self.drift_check,
                    test_cmd=self.test_cmd,
                    cost_log_path=self.cost_log_path,
                    project_name=self.project_dir.name,
                    repo_dir=Path(__file__).resolve().parents[3],
                )
                return result.passed

            if not run_parallel_drift_checks(
                self.drift_pairs, _drift_check_fn
            ):
                logger.warning(
                    "One or more parallel drift checks failed"
                )

    # ── Post-build gates ─────────────────────────────────────────────────

    def _run_post_build_gates(
        self,
        build_result: str,
        feature_name: str,
        branch_start_commit: str = "",
        *,
        project_dir: Path | None = None,
    ) -> bool:
        """Run all post-build verification gates. Return True if all pass.

        Args:
            build_result: Raw agent output containing signals.
            feature_name: Name of the feature being checked.
            branch_start_commit: If set, verify HEAD has advanced past this.
            project_dir: Override project directory (e.g. worktree path).
                         Defaults to ``self.project_dir``.
        """
        gate_dir = project_dir or self.project_dir

        # Reset gate failure tracking
        self._last_gate_name = ""
        self._last_gate_build_output = ""
        self._last_gate_test_output = ""
        self._last_gate_test_count = None

        # Gate 0: HEAD must have advanced (agent must have committed)
        if branch_start_commit:
            head_now = _get_head(gate_dir)
            if head_now == branch_start_commit:
                logger.warning(
                    "Agent said FEATURE_BUILT but HEAD has not advanced "
                    "(no commits made)"
                )
                return False

        # Gate 1: Clean working tree
        if not check_working_tree_clean(gate_dir):
            logger.warning(
                "Agent said FEATURE_BUILT but left uncommitted changes"
            )
            return False

        # Gate 1.5: Contamination check — files outside project root
        contaminated = _check_contamination(gate_dir, branch_start_commit)
        if contaminated:
            logger.warning(
                "Agent said FEATURE_BUILT but modified files outside "
                "project root: %s",
                ", ".join(contaminated),
            )
            return False

        # Gate 1.75: Dependency health — all declared packages resolved
        dep_result = check_deps(gate_dir)
        if not dep_result.success:
            logger.warning(
                "Agent said FEATURE_BUILT but dependency check failed"
            )
            self._last_gate_name = "deps"
            self._last_gate_build_output = dep_result.output[-3000:]
            return False

        # Gate 2: Build check
        build_ok = check_build(self.build_cmd, gate_dir)
        if not build_ok.success:
            logger.warning(
                "Agent said FEATURE_BUILT but build check failed"
            )
            self._last_gate_name = "build"
            self._last_gate_build_output = build_ok.output[-3000:]
            return False

        # Gate 3: Test check
        if should_run_step("test", self.post_build_steps):
            test_result = check_tests(self.test_cmd, gate_dir)
            self._last_gate_test_count = test_result.test_count
            if not test_result.success:
                logger.warning(
                    "Agent said FEATURE_BUILT but tests failed"
                )
                self._last_gate_name = "test"
                self._last_gate_test_output = test_result.output[-6000:]
                return False

        # Gate 4: Drift check
        drift_ok = True
        if _validate_required_signals(build_result, gate_dir):
            drift_targets = extract_drift_targets(
                build_result, gate_dir
            )
            if self.parallel_validation:
                self.drift_pairs.append(
                    DriftPair(
                        spec_file=Path(drift_targets.spec_file),
                        source_files=drift_targets.source_files,
                    )
                )
                logger.info(
                    "Deferred drift check for parallel batch "
                    "(pair #%d)",
                    len(self.drift_pairs),
                )
            else:
                drift_result = check_drift(
                    drift_targets.spec_file,
                    drift_targets.source_files,
                    gate_dir,
                    model=self.drift_model or None,
                    max_retries=self.max_drift_retries,
                    drift_enabled=self.drift_check,
                    test_cmd=self.test_cmd,
                    cost_log_path=self.cost_log_path,
                    project_name=self.project_dir.name,
                    feature_name=feature_name,
                    repo_dir=Path(__file__).resolve().parents[3],
                )
                if not drift_result.passed:
                    logger.warning(
                        "Agent said FEATURE_BUILT but drift check failed"
                    )
                    drift_ok = False
        else:
            logger.warning(
                "Required signals missing/invalid — skipping drift check"
            )

        if not drift_ok:
            return False

        # Gate 5: Code review (optional, non-blocking for gate result)
        if should_run_step("code-review", self.post_build_steps):
            review_result = run_code_review(
                gate_dir,
                model=self.review_model or None,
                test_cmd=self.test_cmd,
                cost_log_path=self.cost_log_path,
            )
            if review_result.summary and review_result.summary not in ("clean", "agent error"):
                write_learning(
                    summary=f"Code review finding for {feature_name}: {review_result.summary}",
                    detail=(
                        f"Code review {'fixed issues' if review_result.passed else 'found unfixed issues'}.\n"
                        f"Summary: {review_result.summary}"
                    ),
                    category="code-review",
                    project_name=self.project_dir.name,
                    feature_name=feature_name,
                    project_dir=self.project_dir,
                    repo_dir=Path(__file__).resolve().parents[3],
                )
            # Re-validate after review
            recheck = check_build(self.build_cmd, gate_dir)
            if not recheck.success:
                logger.warning("Code review broke the build!")
            elif should_run_step("test", self.post_build_steps):
                test_recheck = check_tests(
                    self.test_cmd, gate_dir
                )
                if not test_recheck.success:
                    logger.warning("Code review broke tests!")

        # Gate 6: Dead exports (non-blocking)
        if should_run_step("dead-code", self.post_build_steps):
            check_dead_exports(gate_dir)

        # Gate 7: Lint (non-blocking)
        if should_run_step("lint", self.post_build_steps):
            check_lint(gate_dir)

        return True

    # ── Post-campaign clean-room verification ────────────────────────────

    def _post_campaign_verify(self) -> bool:
        """Clean-room verification after all features are built.

        Removes node_modules, reinstalls dependencies from scratch
        with NODE_ENV=development forced, then runs build and test
        commands. Catches cases where individual features pass gates
        but the combined project has stale or broken dependencies.

        Returns True if verification passes.
        """
        logger.info("═══ Post-campaign clean-room verification ═══")

        pm = _detect_package_manager(self.project_dir)
        if pm is None:
            logger.info("No JS package manager — skipping clean-room verify")
            return True

        # Step 1: Remove node_modules
        nm_dir = self.project_dir / "node_modules"
        if nm_dir.exists():
            logger.info("Removing node_modules for clean reinstall...")
            import shutil
            shutil.rmtree(nm_dir, ignore_errors=True)

        # Step 2: Reinstall dependencies
        install_cmds = {"npm": "npm install", "yarn": "yarn install", "pnpm": "pnpm install"}
        install_cmd = install_cmds.get(pm, "npm install")
        logger.info("Reinstalling: %s", install_cmd)
        install_result = run_cmd_safe(install_cmd, self.project_dir, timeout=300)
        if install_result.returncode != 0:
            logger.error("Clean-room install failed:\n%s", (install_result.stdout or "")[-2000:])
            return False

        # Step 3: Verify deps
        dep_check = check_deps(self.project_dir)
        if not dep_check.success:
            logger.error("Clean-room dependency check failed:\n%s", dep_check.output[-2000:])
            return False

        # Step 4: Build check
        if self.build_cmd:
            build_check = check_build(self.build_cmd, self.project_dir)
            if not build_check.success:
                logger.error("Clean-room build failed:\n%s", build_check.output[-2000:])
                return False

        # Step 5: Test check
        if self.test_cmd:
            test_check = check_tests(self.test_cmd, self.project_dir)
            if not test_check.success:
                logger.error("Clean-room tests failed:\n%s", test_check.output[-2000:])
                return False

        logger.info("✓ Clean-room verification passed")
        return True

    # ── Independent pass (both mode) ─────────────────────────────────────

    def _run_independent_pass(
        self,
        chained_names: list[str],
    ) -> None:
        """Rebuild each chained feature independently from main.

        Converts bash lines ~1980-2180.
        """
        self.drift_pairs = []
        self._loop_limit = len(chained_names)
        self._current_strategy = "independent"

        for fn in chained_names:
            feature_start = int(time.time())

            self._print_progress(
                len(chained_names),
                feature_name=fn,
                phase="starting independent build",
                model=self.build_model or self.agent_model or "default",
                strategy="independent",
            )

            # Create worktree
            safe_name = re.sub(
                r"[ :/]", "-", fn
            ).lower()
            timestamp = datetime.now().strftime("%H%M%S")
            worktree_name = f"independent-{safe_name}-{timestamp}"
            worktree_path = (
                self.project_dir / ".build-worktrees" / worktree_name
            )
            branch_name = f"auto/independent-{safe_name}"

            worktree_path.parent.mkdir(parents=True, exist_ok=True)

            # Remove branch if exists from previous run
            subprocess.run(
                ["git", "branch", "-D", branch_name],
                capture_output=True,
                text=True,
                cwd=str(self.project_dir),
                timeout=30,
            )

            wt_result = subprocess.run(
                [
                    "git", "worktree", "add", "-b", branch_name,
                    str(worktree_path), self.main_branch,
                ],
                capture_output=True,
                text=True,
                cwd=str(self.project_dir),
                timeout=60,
            )
            if wt_result.returncode != 0:
                logger.error(
                    "Failed to create worktree for: %s", fn
                )
                duration = int(time.time()) - feature_start
                self._record_build_result(
                    fn, "failed", self.build_model or "default",
                    duration, branch_name,
                )
                continue

            # Build in the worktree — reuse the same prompt builder
            # as the main loop (feature_id=0 since we only have names)
            prompt, indep_injections = build_feature_prompt(
                0,
                fn,
                worktree_path,
                self.build_config,
                mistake_tracker=self.mistake_tracker,
            )

            cmd_args = ["-p", "--dangerously-skip-permissions"]
            model = self.build_model or self.agent_model or None
            if model:
                cmd_args.extend(["--model", model])
            cmd_args.append(prompt)

            self._print_progress(
                len(chained_names),
                feature_name=fn,
                phase="invoking agent",
                model=model or "default",
                branch=branch_name,
                strategy="independent",
            )

            try:
                result = run_claude(
                    cmd_args,
                    cost_log_path=self.cost_log_path,
                    timeout=self.agent_timeout,
                    cwd=worktree_path,
                )
                build_output = result.output
            except Exception:
                logger.exception("Independent build agent failed for: %s", fn)
                build_output = ""

            duration = int(time.time()) - feature_start

            if "FEATURE_BUILT" in build_output and self._run_post_build_gates(
                build_output,
                fn,
                project_dir=worktree_path,
            ):
                self._record_build_result(
                    fn, "built", model or "default",
                    duration, branch_name,
                    test_count=self._last_gate_test_count,
                    build_output=build_output,
                )
            else:
                if "FEATURE_BUILT" not in build_output:
                    logger.warning(
                        "Independent build failed for: %s", fn
                    )
                else:
                    logger.warning(
                        "Independent build gates failed for: %s", fn
                    )
                self._record_build_result(
                    fn, "failed", model or "default",
                    duration, branch_name,
                    build_output=build_output,
                )

            # Clean up worktree
            subprocess.run(
                ["git", "worktree", "remove", str(worktree_path)],
                capture_output=True,
                text=True,
                cwd=str(self.project_dir),
                timeout=60,
            )

        # Parallel drift checks for independent pass
        if self.parallel_validation and self.drift_pairs:
            logger.info(
                "Running %d deferred drift checks in parallel...",
                len(self.drift_pairs),
            )

            def _drift_fn(spec_file: Path, source_files: str) -> bool:
                r = check_drift(
                    str(spec_file),
                    source_files,
                    self.project_dir,
                    model=self.drift_model or None,
                    max_retries=self.max_drift_retries,
                    drift_enabled=self.drift_check,
                    test_cmd=self.test_cmd,
                    cost_log_path=self.cost_log_path,
                    project_name=self.project_dir.name,
                    repo_dir=Path(__file__).resolve().parents[3],
                )
                return r.passed

            if not run_parallel_drift_checks(
                self.drift_pairs, _drift_fn
            ):
                logger.warning(
                    "One or more parallel drift checks failed"
                )

    # ── Build summary ────────────────────────────────────────────────────

    def write_build_summary(self, total_elapsed: int) -> Path:
        """Write a JSON build summary. Returns the file path.

        Replaces 172-line ``write_build_summary()`` from bash with
        ~30 lines using json.dumps().
        """
        timestamp = datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        file_timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

        # Compute total test count (last non-None from any feature)
        total_tests = 0
        for record in self.feature_records:
            if record.test_count is not None:
                total_tests = record.test_count

        features_json = []
        for record in self.feature_records:
            features_json.append({
                "name": record.name,
                "status": record.status,
                "model": record.model,
                "time_seconds": record.duration_seconds,
                "source_files": (
                    [s.strip() for s in record.source_files.split(",")
                     if s.strip()]
                    if record.source_files
                    else []
                ),
                "test_count": record.test_count,
                "tokens": record.token_usage,
            })

        summary = {
            "timestamp": timestamp,
            "total_time_seconds": total_elapsed,
            "model": self.build_model or self.agent_model or "default",
            "branch_strategy": self.branch_strategy,
            "features_built": self.loop_built,
            "features_failed": self.loop_failed,
            "total_tests": total_tests,
            "features": features_json,
        }

        self.logs_dir.mkdir(parents=True, exist_ok=True)
        summary_path = (
            self.logs_dir / f"build-summary-{file_timestamp}.json"
        )
        summary_path.write_text(
            json.dumps(summary, indent=2) + "\n"
        )

        # Print human-readable summary
        logger.info("")
        logger.info("═══ Build Summary ═══")
        logger.info("  Model: %s", self.build_model or self.agent_model or "default")
        logger.info("  Strategy: %s", self.branch_strategy)
        logger.info(
            "  Total time: %s", _format_duration(total_elapsed)
        )
        logger.info(
            "  Features: %d built, %d failed",
            self.loop_built,
            self.loop_failed,
        )
        logger.info("  Total tests: %d", total_tests)

        return summary_path

    # ── Sidecar lifecycle ────────────────────────────────────────────────

    def start_eval_sidecar(self) -> None:
        """Start the eval sidecar as a background subprocess."""
        if not _env_bool("EVAL_SIDECAR", True):
            logger.info(
                "Eval sidecar disabled (EVAL_SIDECAR=false)"
            )
            return

        sidecar_script = (
            self.project_dir / "scripts" / "eval-sidecar.sh"
        )

        # Determine launch command: prefer bash script, fall back to Python module
        if sidecar_script.is_file():
            sidecar_cmd = ["bash", str(sidecar_script)]
        else:
            logger.info(
                "Bash sidecar not found (%s), trying Python module fallback",
                sidecar_script,
            )
            sidecar_cmd = [
                sys.executable, "-m", "auto_sdd.scripts.eval_sidecar",
            ]

        logger.info("Starting eval sidecar...")
        sidecar_log = self.logs_dir / "eval-sidecar.log"
        sidecar_log.parent.mkdir(parents=True, exist_ok=True)

        env = {
            **os.environ,
            "PROJECT_DIR": str(self.project_dir),
            "AGENT_MODEL": self.agent_model,
            "EVAL_OUTPUT_DIR": str(self.eval_output_dir),
        }

        try:
            with open(sidecar_log, "a") as log_fd:
                proc = subprocess.Popen(
                    sidecar_cmd,
                    stdout=log_fd,
                    stderr=log_fd,
                    env=env,
                )
            self.eval_sidecar_pid = proc.pid
            self.eval_sidecar_proc = proc
            logger.info(
                "Eval sidecar started (PID: %d)",
                self.eval_sidecar_pid,
            )
        except OSError:
            logger.warning(
                "Failed to start eval sidecar", exc_info=True
            )

    def stop_eval_sidecar(self) -> None:
        """Stop the eval sidecar subprocess."""
        if self.eval_sidecar_pid is None:
            return

        proc = self.eval_sidecar_proc

        # Check if still running — use proc.poll() to reap zombies
        if proc is not None and proc.poll() is not None:
            logger.info("Eval sidecar already exited")
            self.eval_sidecar_pid = None
            self.eval_sidecar_proc = None
            return

        # Fallback: os.kill check if we only have PID (shouldn't happen)
        if proc is None:
            try:
                os.kill(self.eval_sidecar_pid, 0)
            except OSError:
                logger.info("Eval sidecar already exited")
                self.eval_sidecar_pid = None
                return

        # Write drain sentinel
        drain_sentinel = self.project_dir / ".sdd-eval-drain"
        logger.info("Signaling eval sidecar to drain...")
        drain_sentinel.touch()

        # Wait for graceful exit (up to 120s)
        waited = 0
        timeout = 120
        while waited < timeout:
            if proc is not None:
                if proc.poll() is not None:
                    logger.info("Eval sidecar exited cleanly")
                    break
            else:
                try:
                    os.kill(self.eval_sidecar_pid, 0)
                except OSError:
                    logger.info("Eval sidecar exited cleanly")
                    break
            time.sleep(2)
            waited += 2
        else:
            logger.warning(
                "Eval sidecar did not exit within %ds — sending SIGTERM",
                timeout,
            )
            if proc is not None:
                proc.terminate()
            else:
                try:
                    os.kill(self.eval_sidecar_pid, signal.SIGTERM)
                except OSError:
                    pass

        drain_sentinel.unlink(missing_ok=True)
        self.eval_sidecar_pid = None
        self.eval_sidecar_proc = None

    # ── Internal helpers ─────────────────────────────────────────────────

    def _check_sidecar_health(self) -> None:
        """Log a warning if the sidecar process has died."""
        if self.eval_sidecar_pid is None:
            return
        exited = False
        if self.eval_sidecar_proc is not None:
            exited = self.eval_sidecar_proc.poll() is not None
        else:
            try:
                os.kill(self.eval_sidecar_pid, 0)
            except OSError:
                exited = True
        if exited:
            logger.warning(
                "EVAL SIDECAR DIED (was PID %d) — no eval coverage "
                "for remaining features",
                self.eval_sidecar_pid,
            )
            self.eval_sidecar_pid = None
            self.eval_sidecar_proc = None

    def _cleanup_branch_on_no_features(
        self,
        strategy: str,
        branch: str,
        worktree_path: Path | None,
    ) -> None:
        """Clean up the branch when no features are ready to build."""
        if strategy == "chained":
            subprocess.run(
                ["git", "checkout",
                 self.last_feature_branch or self.main_branch],
                capture_output=True,
                text=True,
                cwd=str(self.project_dir),
                timeout=30,
            )
            subprocess.run(
                ["git", "branch", "-D", branch],
                capture_output=True,
                text=True,
                cwd=str(self.project_dir),
                timeout=30,
            )
        elif strategy == "independent":
            cleanup_branch_independent(
                worktree_path, self.project_dir, branch
            )

    def _cleanup_failed_branch(
        self,
        strategy: str,
        branch: str,
        worktree_path: Path | None,
    ) -> None:
        """Clean up after a failed feature."""
        if strategy == "chained":
            logger.warning(
                "Feature failed, next will branch from: %s",
                self.last_feature_branch or self.main_branch,
            )
            # Stash to prevent cascade failure
            subprocess.run(
                ["git", "add", "-A"],
                capture_output=True, text=True,
                cwd=str(self.project_dir), timeout=30,
            )
            subprocess.run(
                ["git", "stash", "push", "-m",
                 "auto-stash before branch switch"],
                capture_output=True, text=True,
                cwd=str(self.project_dir), timeout=30,
            )
            subprocess.run(
                ["git", "checkout",
                 self.last_feature_branch or self.main_branch],
                capture_output=True, text=True,
                cwd=str(self.project_dir), timeout=30,
            )
            subprocess.run(
                ["git", "branch", "-D", branch],
                capture_output=True, text=True,
                cwd=str(self.project_dir), timeout=30,
            )
        elif strategy == "independent":
            cleanup_branch_independent(
                worktree_path, self.project_dir, branch
            )
        elif strategy == "sequential":
            cleanup_branch_sequential()

    def _print_progress(
        self,
        total_features: int,
        *,
        feature_name: str = "",
        phase: str = "",
        attempt: int = 0,
        max_attempts: int = 0,
        model: str = "",
        branch: str = "",
        strategy: str = "",
    ) -> None:
        """Print a delineated progress block visible in verbose output."""
        elapsed = _format_duration(int(time.time()) - self.script_start)
        bar = "=" * 70

        lines = [
            "",
            bar,
            f"  BUILD PROGRESS | {self.loop_built}/{total_features} built"
            f" | {self.loop_failed} failed | elapsed: {elapsed}",
        ]
        if feature_name:
            attempt_str = ""
            if max_attempts > 1:
                attempt_str = f" (attempt {attempt}/{max_attempts})"
            lines.append(f"  Feature: {feature_name}{attempt_str}")
        if phase:
            lines.append(f"  Phase: {phase}")
        if model:
            lines.append(f"  Model: {model}")
        if strategy:
            lines.append(f"  Strategy: {strategy}")
        if branch:
            lines.append(f"  Branch: {branch}")
        lines.append(bar)
        lines.append("")

        for line in lines:
            logger.info(line)

    def _print_timings(self) -> None:
        """Print per-feature timing report."""
        if self.loop_timings:
            logger.info("  Per-feature timings:")
            for t in self.loop_timings:
                logger.info("    %s", t)


# ── Entry point ──────────────────────────────────────────────────────────────


def main() -> None:
    """CLI entry point for the build loop."""
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Guard: detect nested Claude Code session
    if os.environ.get("CLAUDECODE"):
        logger.error(
            "Detected active Claude Code session (CLAUDECODE env var set). "
            "Run this script from a regular terminal."
        )
        raise SystemExit(1)

    loop = BuildLoop()
    loop.run()


if __name__ == "__main__":
    main()
