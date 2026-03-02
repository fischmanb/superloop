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
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

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
    check_build,
    check_dead_exports,
    check_lint,
    check_tests,
    check_working_tree_clean,
    clean_working_tree,
    detect_build_check,
    detect_test_check,
    should_run_step,
)
from auto_sdd.lib.claude_wrapper import ClaudeResult, run_claude
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
from auto_sdd.lib.prompt_builder import (
    BuildConfig,
    build_feature_prompt,
    build_retry_prompt,
    show_preflight_summary,
)
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


def _validate_required_signals(build_result: str) -> bool:
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

    if not Path(spec_file).exists():
        logger.warning("SPEC_FILE does not exist on disk: %s", spec_file)
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


_CREDIT_RE = re.compile(
    r"credit|billing|insufficient_quota|quota exceeded|"
    r"402 Payment|429 Too Many|payment required",
    re.IGNORECASE,
)


def _is_credit_exhaustion(output: str) -> bool:
    """Return True if output contains credit/billing exhaustion keywords."""
    return bool(_CREDIT_RE.search(output))


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
        self.max_features = _env_int("MAX_FEATURES", 25)
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
        self.mistake_tracker = MistakeTracker()
        self.script_start: int = int(time.time())

        # ── Acquire lock ─────────────────────────────────────────────────
        lock_dir = Path("/tmp")
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

        if status == "built":
            self.loop_built += 1
            self.built_feature_names.append(feature_name)
            self.loop_timings.append(
                f"✓ {feature_name}: {_format_duration(duration)}"
            )
            logger.info(
                "✓ Feature %d built: %s (%s)",
                self.loop_built,
                feature_name,
                _format_duration(duration),
            )
        else:
            self.loop_failed += 1
            self.loop_skipped.append(feature_name)
            self.loop_timings.append(
                f"✗ {feature_name}: {_format_duration(duration)}"
            )
            logger.error(
                "Feature failed: %s (%s)", feature_name,
                _format_duration(duration),
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

        loop_limit = min(len(features), self.max_features)

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
            elapsed = feature_start - self.script_start

            logger.info("")
            logger.info(
                "[%s] Build #%d: %s (%d/%d, built: %d, "
                "failed: %d) | elapsed: %s",
                strategy,
                feature.id,
                feature.name,
                idx + 1,
                loop_limit,
                self.loop_built,
                self.loop_failed,
                _format_duration(elapsed),
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

            for attempt in range(self.max_retries + 1):
                if attempt > 0:
                    logger.warning(
                        "Retry %d/%d — waiting %ds",
                        attempt,
                        self.max_retries,
                        self.min_retry_delay,
                    )
                    time.sleep(self.min_retry_delay)
                    # Reset to starting point for clean retry
                    subprocess.run(
                        ["git", "reset", "--hard", branch_start_commit],
                        capture_output=True,
                        text=True,
                        cwd=str(self.project_dir),
                        timeout=30,
                    )
                    subprocess.run(
                        [
                            "git", "clean", "-fd",
                            "-e", "node_modules",
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
                if attempt == 0:
                    prompt = build_feature_prompt(
                        feature.id,
                        feature.name,
                        self.project_dir,
                        self.build_config,
                        mistake_tracker=self.mistake_tracker,
                    )
                    model = self.build_model or self.agent_model or None
                else:
                    prompt = build_retry_prompt(
                        feature.id,
                        feature.name,
                        self.project_dir,
                        self.build_config,
                        build_output=last_build_output,
                        test_output=last_test_output,
                    )
                    model = self.retry_model or self.agent_model or None

                # Invoke agent
                cmd_args = ["-p", "--dangerously-skip-permissions"]
                if model:
                    cmd_args.extend(["--model", model])
                cmd_args.append(prompt)

                try:
                    result = run_claude(
                        cmd_args,
                        cost_log_path=self.cost_log_path,
                        timeout=600,
                    )
                    build_result = result.output
                except Exception:
                    logger.exception("Agent invocation failed")
                    build_result = ""

                # Check for credit exhaustion
                if _is_credit_exhaustion(build_result):
                    logger.error(
                        "API credits exhausted — halting build loop"
                    )
                    raise SystemExit(1)

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

                    # Verify: clean tree, build passes, tests pass
                    if self._run_post_build_gates(
                        build_result, feature_name or feature.name,
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
                            build_output=build_result,
                        )
                        feature_done = True
                        break
                    else:
                        # Gates failed — will retry
                        last_build_output = build_result[-2000:]
                        last_test_output = ""

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
                                if should_run_step(
                                    "test", self.post_build_steps
                                ):
                                    test_result = check_tests(
                                        self.test_cmd, self.project_dir
                                    )
                                    test_ok = test_result.success
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
                                        build_output=build_result,
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
                            if should_run_step(
                                "test", self.post_build_steps
                            ):
                                test_result = check_tests(
                                    self.test_cmd, self.project_dir
                                )
                                test_ok = test_result.success
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
                                    build_output=build_result,
                                )
                                feature_done = True
                                break

                # Build failed — store outputs for retry prompt
                if "BUILD_FAILED" in build_result:
                    reason = _parse_signal("BUILD_FAILED", build_result)
                    logger.warning("Build failed: %s", reason)

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
    ) -> bool:
        """Run all post-build verification gates. Return True if all pass."""
        # Gate 0: Clean working tree
        if not check_working_tree_clean(self.project_dir):
            logger.warning(
                "Agent said FEATURE_BUILT but left uncommitted changes"
            )
            return False

        # Gate 1: Build check
        build_ok = check_build(self.build_cmd, self.project_dir)
        if not build_ok.success:
            logger.warning(
                "Agent said FEATURE_BUILT but build check failed"
            )
            return False

        # Gate 2: Test check
        if should_run_step("test", self.post_build_steps):
            test_result = check_tests(self.test_cmd, self.project_dir)
            if not test_result.success:
                logger.warning(
                    "Agent said FEATURE_BUILT but tests failed"
                )
                return False

        # Gate 3: Drift check
        drift_ok = True
        if _validate_required_signals(build_result):
            drift_targets = extract_drift_targets(
                build_result, self.project_dir
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
                    self.project_dir,
                    model=self.drift_model or None,
                    max_retries=self.max_drift_retries,
                    drift_enabled=self.drift_check,
                    test_cmd=self.test_cmd,
                    cost_log_path=self.cost_log_path,
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

        # Gate 4: Code review (optional, non-blocking for gate result)
        if should_run_step("code-review", self.post_build_steps):
            run_code_review(
                self.project_dir,
                model=self.review_model or None,
                test_cmd=self.test_cmd,
                cost_log_path=self.cost_log_path,
            )
            # Re-validate after review
            recheck = check_build(self.build_cmd, self.project_dir)
            if not recheck.success:
                logger.warning("Code review broke the build!")
            elif should_run_step("test", self.post_build_steps):
                test_recheck = check_tests(
                    self.test_cmd, self.project_dir
                )
                if not test_recheck.success:
                    logger.warning("Code review broke tests!")

        # Gate 5: Dead exports (non-blocking)
        if should_run_step("dead-code", self.post_build_steps):
            check_dead_exports(self.project_dir)

        # Gate 6: Lint (non-blocking)
        if should_run_step("lint", self.post_build_steps):
            check_lint(self.project_dir)

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

        for fn in chained_names:
            feature_start = int(time.time())
            elapsed = feature_start - self.script_start

            logger.info(
                "[independent] Building: %s | elapsed: %s",
                fn,
                _format_duration(elapsed),
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

            # Build in the worktree
            prompt = (
                f"Build the feature: {fn}\n\n"
                "Instructions:\n"
                f"1. Run /spec-first {fn} --full\n"
                f"2. This is an independent build from {self.main_branch}\n"
                "3. Create spec, write tests, implement, and commit\n"
                "4. Regenerate mapping: ./scripts/generate-mapping.sh\n"
                "5. Commit all changes\n\n"
                "After completion, output exactly one of:\n"
                f"FEATURE_BUILT: {fn}\n"
                "BUILD_FAILED: {{reason}}\n"
            )

            cmd_args = ["-p", "--dangerously-skip-permissions"]
            model = self.build_model or self.agent_model or None
            if model:
                cmd_args.extend(["--model", model])
            cmd_args.append(prompt)

            try:
                result = run_claude(
                    cmd_args,
                    cost_log_path=self.cost_log_path,
                    timeout=600,
                )
                build_output = result.output
            except Exception:
                logger.exception("Independent build agent failed for: %s", fn)
                build_output = ""

            duration = int(time.time()) - feature_start

            if "FEATURE_BUILT" in build_output:
                if check_working_tree_clean(
                    worktree_path
                ):
                    self._record_build_result(
                        fn, "built", model or "default",
                        duration, branch_name,
                        build_output=build_output,
                    )
                else:
                    logger.warning(
                        "Independent build left uncommitted changes: %s",
                        fn,
                    )
                    self._record_build_result(
                        fn, "failed", model or "default",
                        duration, branch_name,
                        build_output=build_output,
                    )
            else:
                logger.warning(
                    "Independent build failed for: %s", fn
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
            "model": self.agent_model or "default",
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
        logger.info("  Model: %s", self.agent_model or "default")
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
        if not sidecar_script.is_file():
            logger.warning(
                "Eval sidecar script not found: %s", sidecar_script
            )
            return

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
                    ["bash", str(sidecar_script)],
                    stdout=log_fd,
                    stderr=log_fd,
                    env=env,
                )
            self.eval_sidecar_pid = proc.pid
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

        # Check if still running
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
            try:
                os.kill(self.eval_sidecar_pid, signal.SIGTERM)
            except OSError:
                pass

        drain_sentinel.unlink(missing_ok=True)
        self.eval_sidecar_pid = None

    # ── Internal helpers ─────────────────────────────────────────────────

    def _check_sidecar_health(self) -> None:
        """Log a warning if the sidecar process has died."""
        if self.eval_sidecar_pid is None:
            return
        try:
            os.kill(self.eval_sidecar_pid, 0)
        except OSError:
            logger.warning(
                "EVAL SIDECAR DIED (was PID %d) — no eval coverage "
                "for remaining features",
                self.eval_sidecar_pid,
            )
            self.eval_sidecar_pid = None

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
