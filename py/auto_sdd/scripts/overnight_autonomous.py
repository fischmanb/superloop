# CONVERSION CHANGELOG (from scripts/overnight-autonomous.sh, 1310 lines)
#
# - OvernightConfig replaces env-var globals. Config is loaded once in main()
#   and passed to OvernightRunner.
# - OvernightRunner does NOT subclass BuildLoop. Behavioral differences are
#   too substantial (non-blocking failures, PR creation, no signal fallback,
#   post-agent commit). Shares library modules via direct import.
# - Branch validation: "both" and "sequential" strategies are rejected at
#   config time. Overnight only supports "chained" and "independent".
# - Non-blocking failures: drift/test failures log warnings but still push
#   the branch and create a PR. BuildLoop blocks on these.
# - No signal fallback inference: only FEATURE_BUILT is checked. No
#   NO_DRIFT/DRIFT_FIXED fallback path or retry-inferred path.
# - Post-agent commit: if agent leaves uncommitted changes, overnight
#   commits them (git add -A && git commit). BuildLoop expects agent to commit.
# - PR creation: draft PRs via `gh pr create --draft` with feature name,
#   spec content, and review checklist.
# - Stale branch detection: if BASE_BRANCH=current resolves to auto/*,
#   reset to "main".
# - Eval sidecar lifecycle: start_eval_sidecar / stop_eval_sidecar extracted
#   from bash inline code. Uses subprocess.Popen for background process.
# - Step timings: tracked as list[str] (matching bash STEP_TIMINGS array).
# - Feature timings: tracked as list[str] (matching bash FEATURE_TIMINGS array).
# - Prompt templates: build_feature_prompt_overnight and
#   build_retry_prompt_overnight replicate bash content faithfully using f-strings.
# - format_duration: reuses _format_duration from build_loop, but since we
#   cannot import private names cross-module cleanly, reimplemented as a
#   module-level helper (same logic).
# - CLAUDECODE guard: check + raise, not exit 1.
# - Circular dependency check: delegates to check_circular_deps from reliability.
# - Resume state: delegates to read_state / write_state / clean_state from
#   reliability.
"""Overnight autonomous feature implementation runner.

Orchestrates the full overnight flow: sync → rebase → triage → build → report.
Does NOT subclass BuildLoop — behavioral differences are too substantial.

Usage:
    python -m auto_sdd.scripts.overnight_autonomous
    python -m auto_sdd.scripts.overnight_autonomous --resume
"""
from __future__ import annotations

import argparse
import atexit
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from auto_sdd.lib.build_gates import (
    BuildCheckResult,
    agent_cmd,
    check_build,
    check_dead_exports,
    check_lint,
    check_tests,
    detect_build_check,
    detect_test_check,
    should_run_step,
)
from auto_sdd.lib.codebase_summary import generate_codebase_summary
from auto_sdd.lib.drift import (
    DriftCheckResult,
    check_drift,
    extract_drift_targets,
    run_code_review,
)
from auto_sdd.lib.reliability import (
    AgentTimeoutError,
    AutoSddError,
    Feature,
    acquire_lock,
    check_circular_deps,
    clean_state,
    emit_topo_order,
    read_state,
    release_lock,
    run_agent_with_backoff,
    write_state,
)
from auto_sdd.lib.vector_store import VectorStore, generate_campaign_id
from auto_sdd.scripts.build_loop import derive_component_types

logger = logging.getLogger(__name__)


# ── Duration formatting ──────────────────────────────────────────────────────


def _format_duration(total_seconds: int) -> str:
    """Format seconds into human-readable duration string."""
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    if hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    if minutes > 0:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


# ── Signal parsing ───────────────────────────────────────────────────────────


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
    """Check that FEATURE_BUILT and SPEC_FILE signals are present and valid."""
    feature_name = _parse_signal("FEATURE_BUILT", build_result)
    spec_file = _parse_signal("SPEC_FILE", build_result)

    if not feature_name:
        logger.warning("Missing required signal: FEATURE_BUILT")
        return False
    if not spec_file:
        logger.warning("Missing required signal: SPEC_FILE (needed for drift check)")
        return False
    if not Path(spec_file).exists():
        logger.warning("SPEC_FILE does not exist on disk: %s", spec_file)
        return False
    return True


# ── Credit exhaustion detection ──────────────────────────────────────────────

_CREDIT_RE = re.compile(
    r"credit|billing|insufficient_quota|quota exceeded|402 payment|429 too many|payment required",
    re.IGNORECASE,
)


def _is_credit_exhaustion(output: str) -> bool:
    """Return True if output contains credit/billing exhaustion keywords."""
    return bool(_CREDIT_RE.search(output))


# ── Git helpers ──────────────────────────────────────────────────────────────


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


# ── Configuration ────────────────────────────────────────────────────────────


@dataclass
class OvernightConfig:
    """Overnight run configuration from env/.env.local."""

    project_dir: Path
    base_branch: str = "main"
    branch_strategy: str = "chained"
    max_features: int = 4
    max_retries: int = 1
    min_retry_delay: int = 30
    slack_feature_channel: str = "#feature-requests"
    slack_report_channel: str = ""
    jira_project_key: str = ""
    enable_resume: bool = True
    # Model selection
    agent_model: str = ""
    build_model: str = ""
    retry_model: str = ""
    drift_model: str = ""
    review_model: str = ""
    triage_model: str = ""
    # Post-build steps
    post_build_steps: str = "test,dead-code,lint"
    # Eval sidecar
    eval_sidecar: bool = True
    eval_agent: bool = True
    eval_model: str = ""

    def __post_init__(self) -> None:
        """Validate configuration."""
        if self.branch_strategy not in ("chained", "independent"):
            logger.warning(
                "Invalid BRANCH_STRATEGY: %s (must be: chained or independent). "
                "Using default: chained",
                self.branch_strategy,
            )
            self.branch_strategy = "chained"


def _load_config(resume_mode: bool = False) -> OvernightConfig:
    """Load configuration from environment variables (same names as bash).

    Loads .env.local if it exists, then reads env vars.
    """
    project_dir_str = os.environ.get("PROJECT_DIR", "")
    if not project_dir_str:
        project_dir_str = str(Path.cwd())
    project_dir = Path(project_dir_str).resolve()

    # Load .env.local if present
    env_file = project_dir / ".env.local"
    if env_file.is_file():
        _source_env_file(env_file)

    def _bool_env(key: str, default: bool) -> bool:
        val = os.environ.get(key, "").lower()
        if val in ("true", "1", "yes"):
            return True
        if val in ("false", "0", "no"):
            return False
        return default

    return OvernightConfig(
        project_dir=project_dir,
        base_branch=os.environ.get("BASE_BRANCH", "main"),
        branch_strategy=os.environ.get("BRANCH_STRATEGY", "chained"),
        max_features=int(os.environ.get("MAX_FEATURES", "4")),
        max_retries=int(os.environ.get("MAX_RETRIES", "1")),
        min_retry_delay=int(os.environ.get("MIN_RETRY_DELAY", "30")),
        slack_feature_channel=os.environ.get(
            "SLACK_FEATURE_CHANNEL", "#feature-requests"
        ),
        slack_report_channel=os.environ.get("SLACK_REPORT_CHANNEL", ""),
        jira_project_key=os.environ.get("JIRA_PROJECT_KEY", ""),
        enable_resume=_bool_env("ENABLE_RESUME", True),
        agent_model=os.environ.get("AGENT_MODEL", ""),
        build_model=os.environ.get("BUILD_MODEL", ""),
        retry_model=os.environ.get("RETRY_MODEL", ""),
        drift_model=os.environ.get("DRIFT_MODEL", ""),
        review_model=os.environ.get("REVIEW_MODEL", ""),
        triage_model=os.environ.get("TRIAGE_MODEL", ""),
        post_build_steps=os.environ.get(
            "POST_BUILD_STEPS", "test,dead-code,lint"
        ),
        eval_sidecar=_bool_env("EVAL_SIDECAR", True),
        eval_agent=_bool_env("EVAL_AGENT", True),
        eval_model=os.environ.get("EVAL_MODEL", ""),
    )


def _source_env_file(env_file: Path) -> None:
    """Load KEY=VALUE lines from an env file into os.environ.

    Only simple KEY=VALUE and KEY="VALUE" lines are handled. Shell expansion
    and complex bash syntax are not supported.
    """
    try:
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            # Strip surrounding quotes
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            # Only set if not already in environment (env takes precedence)
            if key not in os.environ:
                os.environ[key] = value
    except OSError:
        logger.warning("Could not read env file: %s", env_file)


# ── OvernightRunner ──────────────────────────────────────────────────────────


class OvernightRunner:
    """Orchestrates overnight autonomous feature implementation."""

    def __init__(self, config: OvernightConfig) -> None:
        self.config = config
        self.project_dir = config.project_dir

        # Lock
        lock_name = str(self.project_dir).replace("/", "_").replace(" ", "_")
        self.lock_file = Path(tempfile.gettempdir()) / f"sdd-overnight-{lock_name}.lock"

        # State
        self.state_dir = self.project_dir / ".sdd-state"
        self.state_file = self.state_dir / "resume.json"

        # Tracking
        self.built_feature_names: list[str] = []
        self.step_timings: list[str] = []
        self.feature_timings: list[str] = []
        self.built: int = 0
        self.failed: int = 0

        # Branch tracking
        self.main_branch: str = ""
        self.last_feature_branch: str = ""

        # Build/test commands (auto-detected)
        self.build_cmd: str = ""
        self.test_cmd: str = ""

        # Eval sidecar
        self.eval_sidecar_pid: int | None = None

        # Test state
        self.last_build_output: str = ""
        self.last_test_output: str = ""
        self.prev_test_count: int = 0

        # Script start time
        self.script_start: float = 0.0

        # Resume mode
        self.resume_mode: bool = False

        # ── Campaign Intelligence System ────────────────────────────────
        self.campaign_id = generate_campaign_id(
            strategy=config.branch_strategy,
            model=config.build_model or config.agent_model or "unknown",
        )
        self.vector_store = VectorStore(
            self.project_dir / ".sdd-state" / "feature-vectors.jsonl"
        )

    def run(self) -> None:
        """Execute the full overnight flow: sync → rebase → triage → build → report."""
        self.script_start = time.time()

        # CLAUDECODE guard
        if os.environ.get("CLAUDECODE"):
            raise AutoSddError(
                "Detected active Claude Code session (CLAUDECODE env var set). "
                "The overnight runner spawns child 'claude -p' processes that "
                "will hang inside a nested session. Run from a regular terminal."
            )

        # Check prerequisites
        if shutil.which("claude") is None:
            raise AutoSddError(
                "Claude Code CLI (claude) not found. "
                "Install via: npm install -g @anthropic-ai/claude-code"
            )

        has_gh = shutil.which("gh") is not None
        if not has_gh:
            logger.warning("GitHub CLI (gh) not found - PRs won't be created")

        # Acquire lock
        acquire_lock(self.lock_file)
        atexit.register(self._cleanup)

        # Log configuration
        logger.info("═" * 59)
        logger.info("  OVERNIGHT AUTONOMOUS RUN")
        logger.info("═" * 59)
        logger.info("Project: %s", self.project_dir)
        logger.info("Base branch: %s", self.config.base_branch)
        logger.info("Branch strategy: %s", self.config.branch_strategy)
        logger.info(
            "Max features: %d | Max retries: %d | Min retry delay: %ds",
            self.config.max_features,
            self.config.max_retries,
            self.config.min_retry_delay,
        )
        logger.info("Slack channel: %s", self.config.slack_feature_channel)
        logger.info(
            "Jira project: %s",
            self.config.jira_project_key or "not configured",
        )

        # Auto-detect build/test commands
        self.build_cmd = detect_build_check(self.project_dir)
        self.test_cmd = detect_test_check(self.project_dir)
        logger.info("Test suite: %s", self.test_cmd or "disabled")
        logger.info(
            "Post-build steps: %s",
            self.config.post_build_steps or "none",
        )

        # Handle resume mode
        if self.resume_mode and self.config.enable_resume:
            state = read_state(self.state_file)
            if state is not None:
                self.built_feature_names = list(state.completed_features)
                logger.info(
                    "Resuming — %d features already completed",
                    len(self.built_feature_names),
                )
                if state.current_branch:
                    self.last_feature_branch = state.current_branch
            else:
                logger.warning(
                    "No resume state found at %s — starting from beginning",
                    self.state_file,
                )

        # Execute steps
        self._sync_branch()
        self._rebase_prs()
        self._run_triage()
        built, failed = self._build_features()
        self.built = built
        self.failed = failed
        self._report_summary()

    # ── Step 0: Git Sync ──────────────────────────────────────────────────

    def _sync_branch(self) -> None:
        """Checkout and pull base branch. Reject stale auto/* branches."""
        sync_branch = self.config.base_branch
        if sync_branch == "current":
            result = _run_git(
                ["branch", "--show-current"], self.project_dir
            )
            sync_branch = result.stdout.strip() or "main"
            # Reject stale campaign branches
            if sync_branch.startswith("auto/"):
                logger.warning(
                    "SYNC_BRANCH detected as '%s' (stale campaign branch). "
                    "Resetting to 'main'.",
                    sync_branch,
                )
                sync_branch = "main"

        logger.info("═" * 59)
        logger.info("  STEP 0: Sync with %s", sync_branch)
        logger.info("═" * 59)
        step_start = time.time()

        # Verify branch exists
        verify = _run_git(
            ["rev-parse", "--verify", sync_branch], self.project_dir
        )
        if verify.returncode != 0:
            raise AutoSddError(
                f"BASE_BRANCH={self.config.base_branch} "
                f"(resolved: {sync_branch}) does not exist"
            )

        _run_git(["checkout", sync_branch], self.project_dir, check=True)
        self.main_branch = sync_branch
        _run_git(
            ["pull", "origin", self.main_branch],
            self.project_dir,
            check=True,
            timeout=120,
        )

        duration = int(time.time() - step_start)
        logger.info(
            "✓ Synced with %s (%s)",
            self.main_branch,
            _format_duration(duration),
        )
        self.step_timings.append(
            f"Step 0 - Sync: {_format_duration(duration)}"
        )

    # ── Step 1: PR Rebase ─────────────────────────────────────────────────

    def _rebase_prs(self) -> int:
        """Rebase existing auto/* PRs onto base branch. Returns count rebased."""
        logger.info("═" * 59)
        logger.info("  STEP 1: Rebase existing auto PRs")
        logger.info("═" * 59)
        step_start = time.time()

        rebased = 0
        if shutil.which("gh") is None:
            logger.info("Skipping rebase (gh CLI not available)")
        else:
            try:
                result = subprocess.run(
                    [
                        "gh", "pr", "list",
                        "--search", "head:auto/",
                        "--json", "headRefName",
                        "--jq", ".[].headRefName",
                    ],
                    capture_output=True,
                    text=True,
                    cwd=str(self.project_dir),
                    timeout=60,
                )
                branches = [
                    b.strip()
                    for b in result.stdout.splitlines()
                    if b.strip()
                ]
            except (subprocess.TimeoutExpired, OSError):
                branches = []

            for pr_branch in branches:
                fetch = _run_git(
                    ["fetch", "origin", pr_branch], self.project_dir
                )
                if fetch.returncode != 0:
                    continue
                checkout = _run_git(
                    ["checkout", pr_branch], self.project_dir
                )
                if checkout.returncode != 0:
                    continue
                rebase = _run_git(
                    ["rebase", f"origin/{self.main_branch}"],
                    self.project_dir,
                )
                if rebase.returncode == 0:
                    push = _run_git(
                        ["push", "--force-with-lease", "origin", pr_branch],
                        self.project_dir,
                    )
                    if push.returncode == 0:
                        logger.info("✓ Rebased %s", pr_branch)
                        rebased += 1
                else:
                    _run_git(["rebase", "--abort"], self.project_dir)
                    logger.warning(
                        "Could not rebase %s - may need manual intervention",
                        pr_branch,
                    )

            _run_git(["checkout", self.main_branch], self.project_dir)

            if rebased > 0:
                logger.info("✓ Rebased %d existing PRs", rebased)
            else:
                logger.info("No existing auto PRs to rebase")

        duration = int(time.time() - step_start)
        self.step_timings.append(
            f"Step 1 - Rebase PRs: {_format_duration(duration)}"
        )
        return rebased

    # ── Step 2: Triage ────────────────────────────────────────────────────

    def _run_triage(self) -> None:
        """Invoke triage agent to scan Slack/Jira → roadmap."""
        logger.info("═" * 59)
        logger.info("  STEP 2: Triage new requests")
        logger.info("═" * 59)
        step_start = time.time()

        logger.info("Running /roadmap-triage to scan Slack/Jira...")

        triage_prompt = (
            "Run the /roadmap-triage command to:\n"
            f"1. Scan Slack channel {self.config.slack_feature_channel} "
            "for feature requests\n"
            f"2. Scan Jira project {self.config.jira_project_key} "
            "for tickets with label 'auto-ok'\n"
            "3. Add new items to .specs/roadmap.md in the Ad-hoc Requests section\n"
            "4. Create Jira tickets for Slack items (if configured)\n"
            "5. Mark sources as triaged (reply to Slack, comment on Jira)\n"
            "6. Commit the roadmap changes\n\n"
            "If no new requests found, that's fine - continue.\n"
        )

        cmd = agent_cmd(self.config.triage_model or None)
        cmd.append(triage_prompt)
        output_file = self.project_dir / "logs" / "triage-output.txt"
        output_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            exit_code = run_agent_with_backoff(output_file, cmd)
            if exit_code != 0:
                logger.warning(
                    "Triage agent exited with code %d (non-blocking, continuing)",
                    exit_code,
                )
        except AgentTimeoutError:
            logger.warning("Triage agent timed out (non-blocking, continuing)")
        finally:
            output_file.unlink(missing_ok=True)

        duration = int(time.time() - step_start)
        logger.info("✓ Triage complete (%s)", _format_duration(duration))
        self.step_timings.append(
            f"Step 2 - Triage: {_format_duration(duration)}"
        )

    # ── Step 3: Build Features ────────────────────────────────────────────

    def _build_features(self) -> tuple[int, int]:
        """Build features from topo order. Returns (built, failed) counts."""
        logger.info("═" * 59)
        logger.info("  STEP 3: Build features from roadmap")
        logger.info("═" * 59)
        step_start = time.time()

        # Circular dependency check
        check_circular_deps(self.project_dir)

        # Get topological order of pending features
        features = emit_topo_order(self.project_dir)

        if not features:
            logger.info(
                "No pending (⬜) features found in roadmap — nothing to build"
            )
            release_lock(self.lock_file)
            duration = int(time.time() - step_start)
            self.step_timings.append(
                f"Step 3 - Build features: {_format_duration(duration)}"
            )
            return 0, 0

        # Pre-flight summary
        logger.info("Pre-flight build plan:")
        for feat in features:
            logger.info("  #%d  %s  [%s]", feat.id, feat.name, feat.complexity)
        logger.info(
            "Total features: %d (capped at MAX_FEATURES=%d)",
            len(features),
            self.config.max_features,
        )

        # Start eval sidecar
        self._start_eval_sidecar()

        built = 0
        failed = 0
        loop_limit = min(len(features), self.config.max_features)

        for idx in range(loop_limit):
            feat = features[idx]

            # Skip already-completed features (resume mode)
            if feat.name in self.built_feature_names:
                logger.info("Skipping already-built feature: %s", feat.name)
                continue

            success = self._build_single_feature(
                str(feat.id), feat.name, idx, loop_limit
            )
            if success:
                built += 1
            else:
                failed += 1

        # Clean resume state on successful completion
        if self.config.enable_resume and failed == 0:
            clean_state(self.state_file)

        # Stop eval sidecar
        self._stop_eval_sidecar()

        duration = int(time.time() - step_start)
        self.step_timings.append(
            f"Step 3 - Build features: {_format_duration(duration)}"
        )
        return built, failed

    def _build_single_feature(
        self,
        feature_id: str,
        feature_name: str,
        idx: int,
        total: int,
    ) -> bool:
        """Build one feature with retry loop. Returns True if built."""
        feature_start = time.time()
        elapsed_so_far = int(feature_start - self.script_start)
        logger.info(
            "Build #%s: %s (%d/%d) | elapsed: %s",
            feature_id,
            feature_name,
            idx + 1,
            total,
            _format_duration(elapsed_so_far),
        )

        # ── CIS: create feature vector ──────────────────────────────────
        current_vector_id = ""
        try:
            current_vector_id = self.vector_store.create_vector({
                "feature_id": int(feature_id),
                "feature_name": feature_name,
                "campaign_id": self.campaign_id,
                "build_order_position": idx,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            self.vector_store.update_section(
                current_vector_id,
                "pre_build_v1",
                {
                    "complexity_tier": "unknown",
                    "dependency_count": 0,
                    "branch_strategy": self.config.branch_strategy,
                },
            )
        except Exception:
            logger.debug(
                "Vector store error at feature start", exc_info=True
            )

        # Create branch
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        branch_name = f"auto/feature-{timestamp}"

        if self.config.branch_strategy == "chained":
            base = self.last_feature_branch or self.main_branch
            if base != self.main_branch:
                logger.info("Branching from previous feature: %s", base)
                result = _run_git(["checkout", base], self.project_dir)
                if result.returncode != 0:
                    logger.warning(
                        "Previous branch %s not found, using %s",
                        base,
                        self.main_branch,
                    )
                    _run_git(
                        ["checkout", self.main_branch],
                        self.project_dir,
                        check=True,
                    )
            else:
                logger.info("Branching from %s (first feature)", self.main_branch)
                _run_git(
                    ["checkout", self.main_branch],
                    self.project_dir,
                    check=True,
                )
        else:
            # Independent: always branch from main
            _run_git(
                ["checkout", self.main_branch],
                self.project_dir,
                check=True,
            )

        _run_git(
            ["checkout", "-b", branch_name],
            self.project_dir,
            check=True,
        )

        # Record starting commit for retry resets
        head_result = _run_git(["rev-parse", "HEAD"], self.project_dir)
        branch_start_commit = head_result.stdout.strip()

        # Retry loop
        feature_done = False
        build_result = ""

        for attempt in range(self.config.max_retries + 1):
            if attempt > 0:
                logger.warning(
                    "Retry %d/%d — waiting %ds before retry",
                    attempt,
                    self.config.max_retries,
                    self.config.min_retry_delay,
                )
                time.sleep(self.config.min_retry_delay)
                _run_git(
                    ["reset", "--hard", branch_start_commit],
                    self.project_dir,
                )
                _run_git(["clean", "-fd"], self.project_dir)

            output_file = self.project_dir / "logs" / "build-output.txt"
            output_file.parent.mkdir(parents=True, exist_ok=True)

            if attempt == 0:
                prompt = self._build_feature_prompt(feature_id, feature_name)
                model = self.config.build_model
            else:
                prompt = self._build_retry_prompt()
                model = self.config.retry_model or self.config.build_model

            cmd = agent_cmd(model or None)
            cmd.append(prompt)

            try:
                exit_code = run_agent_with_backoff(output_file, cmd)
            except AgentTimeoutError:
                logger.warning("Agent timed out for %s", feature_name)
                exit_code = 1

            if output_file.is_file():
                build_result = output_file.read_text()
                output_file.unlink(missing_ok=True)
            else:
                build_result = ""

            if exit_code != 0:
                logger.warning(
                    "Agent exited with code %d (will check signals for actual status)",
                    exit_code,
                )

            # Check for credit exhaustion
            if _is_credit_exhaustion(build_result):
                raise AutoSddError(
                    "API credits exhausted — halting overnight run"
                )

            # Check for NO_FEATURES_READY
            if "NO_FEATURES_READY" in build_result:
                logger.info("No more features ready to build")
                _run_git(["checkout", self.main_branch], self.project_dir)
                _run_git(
                    ["branch", "-D", branch_name], self.project_dir
                )
                feature_done = True
                break

            # Check for success
            if "FEATURE_BUILT" in build_result:
                feature_done = True
                break

            # Build failed — log reason
            if "BUILD_FAILED" in build_result:
                reason = _parse_signal("BUILD_FAILED", build_result)
                logger.warning("Build failed: %s", reason)
            else:
                logger.warning("Build did not produce a clear success signal")

        # All attempts failed
        if not feature_done:
            feature_duration = int(time.time() - feature_start)
            logger.warning(
                "Feature failed after %d attempt(s) (%s)",
                self.config.max_retries + 1,
                _format_duration(feature_duration),
            )
            self.feature_timings.append(
                f"✗ {feature_name}: {_format_duration(feature_duration)}"
            )
            # ── CIS: record failure ─────────────────────────────────
            if current_vector_id:
                try:
                    comp_types = derive_component_types(self.project_dir)
                    self.vector_store.update_section(
                        current_vector_id,
                        "build_signals_v1",
                        {
                            "build_success": False,
                            "retry_count": self.config.max_retries,
                            "agent_model": (
                                self.config.build_model
                                or self.config.agent_model
                                or "default"
                            ),
                            "build_duration_seconds": feature_duration,
                            "drift_check_passed": False,
                            "test_check_passed": False,
                            "injections_received": [],
                            "component_types": comp_types,
                            "touches_shared_modules": "database" in comp_types,
                        },
                    )
                except Exception:
                    logger.debug(
                        "Vector store error at build end", exc_info=True
                    )
            _run_git(["checkout", self.main_branch], self.project_dir)
            _run_git(["branch", "-D", branch_name], self.project_dir)
            return False

        # NO_FEATURES_READY exits early
        if "NO_FEATURES_READY" in build_result:
            return False

        # Feature built — handle post-build
        return self._post_build(
            branch_name,
            feature_name,
            feature_id,
            build_result,
            feature_start,
            vector_id=current_vector_id,
        )

    def _post_build(
        self,
        branch_name: str,
        feature_name: str,
        feature_id: str,
        build_result: str,
        feature_start: float,
        *,
        vector_id: str = "",
    ) -> bool:
        """Handle post-build: commit, gates, push, PR. Returns True if successful."""
        # Post-agent commit: if uncommitted changes exist, commit them
        status = _run_git(["status", "--porcelain"], self.project_dir)
        if status.stdout.strip():
            _run_git(["add", "-A"], self.project_dir)
            extracted_name = _parse_signal("FEATURE_BUILT", build_result)
            commit_name = extracted_name or feature_name
            _run_git(
                ["commit", "-m", f"feat(auto): {commit_name}"],
                self.project_dir,
            )
        else:
            # No changes to commit
            logger.info("No changes to commit")
            _run_git(["checkout", self.main_branch], self.project_dir)
            _run_git(["branch", "-D", branch_name], self.project_dir)
            return False

        # Non-blocking test check
        if should_run_step("test", self.config.post_build_steps) and self.test_cmd:
            test_result = check_tests(self.test_cmd, self.project_dir)
            if not test_result.success:
                feature_duration = int(time.time() - feature_start)
                logger.warning(
                    "Tests failed for %s (%s)",
                    feature_name,
                    _format_duration(feature_duration),
                )
                self.feature_timings.append(
                    f"⚠ {feature_name} (tests): {_format_duration(feature_duration)}"
                )
                self.last_test_output = test_result.output
                # Continue to push — tests are documented in PR

        # Drift check (non-blocking)
        if _validate_required_signals(build_result):
            targets = extract_drift_targets(
                build_result, self.project_dir
            )
            drift_result = check_drift(
                targets.spec_file,
                targets.source_files,
                self.project_dir,
                model=self.config.drift_model or None,
                drift_enabled=True,
                test_cmd=self.test_cmd,
            )
            if not drift_result.passed:
                feature_duration = int(time.time() - feature_start)
                logger.warning(
                    "Feature built but drift check failed (%s)",
                    _format_duration(feature_duration),
                )
                self.feature_timings.append(
                    f"⚠ {feature_name} (drift): {_format_duration(feature_duration)}"
                )
                # Continue to push — drift is documented in PR
        else:
            logger.warning(
                "Required signals missing/invalid — skipping drift check"
            )

        # Code review (non-blocking)
        if should_run_step("code-review", self.config.post_build_steps):
            review = run_code_review(
                self.project_dir,
                model=self.config.review_model or None,
                test_cmd=self.test_cmd,
            )
            if not review.passed:
                logger.warning("Code review had issues (non-blocking)")
            # Re-validate after review
            if self.build_cmd:
                build_check = check_build(self.build_cmd, self.project_dir)
                if not build_check.success:
                    logger.warning("Code review broke the build!")
            if (
                should_run_step("test", self.config.post_build_steps)
                and self.test_cmd
            ):
                test_check = check_tests(self.test_cmd, self.project_dir)
                if not test_check.success:
                    logger.warning("Code review broke tests!")

        # Dead export detection
        if should_run_step("dead-code", self.config.post_build_steps):
            check_dead_exports(self.project_dir)

        # Lint check
        if should_run_step("lint", self.config.post_build_steps):
            check_lint(self.project_dir)

        # Push and create PR
        push_result = _run_git(
            ["push", "-u", "origin", branch_name],
            self.project_dir,
            timeout=120,
        )
        if push_result.returncode == 0:
            logger.info("✓ Pushed branch %s", branch_name)

            # Get spec content for PR body
            spec_content = ""
            spec_file = _parse_signal("SPEC_FILE", build_result)
            if spec_file and Path(spec_file).is_file():
                try:
                    spec_content = Path(spec_file).read_text()
                except OSError:
                    pass

            pr_url = self._create_pr(branch_name, feature_name, spec_content)

            feature_duration = int(time.time() - feature_start)
            if pr_url:
                logger.info(
                    "✓ Created PR: %s (%s)",
                    pr_url,
                    _format_duration(feature_duration),
                )
            else:
                logger.info(
                    "✓ Branch pushed (%s)",
                    _format_duration(feature_duration),
                )

            self.feature_timings.append(
                f"✓ {feature_name}: {_format_duration(feature_duration)}"
            )
            self.built_feature_names.append(feature_name)

            # ── CIS: record success ─────────────────────────────────
            if vector_id:
                try:
                    comp_types = derive_component_types(self.project_dir)
                    self.vector_store.update_section(
                        vector_id,
                        "build_signals_v1",
                        {
                            "build_success": True,
                            "retry_count": 0,
                            "agent_model": (
                                self.config.build_model
                                or self.config.agent_model
                                or "default"
                            ),
                            "build_duration_seconds": feature_duration,
                            "drift_check_passed": True,
                            "test_check_passed": True,
                            "injections_received": [],
                            "component_types": comp_types,
                            "touches_shared_modules": "database" in comp_types,
                        },
                    )
                except Exception:
                    logger.debug(
                        "Vector store error at build end", exc_info=True
                    )

            # Track branch for chained mode
            if self.config.branch_strategy == "chained":
                self.last_feature_branch = branch_name

            # Save resume state
            if self.config.enable_resume:
                write_state(
                    self.state_file,
                    int(feature_id),
                    self.config.branch_strategy,
                    self.built_feature_names,
                    branch_name,
                )

            # Return to main for next iteration (unless chained mode)
            if self.config.branch_strategy != "chained":
                _run_git(["checkout", self.main_branch], self.project_dir)

            return True
        else:
            logger.error("Failed to push branch %s", branch_name)
            return False

    def _create_pr(
        self,
        branch_name: str,
        feature_name: str,
        spec_content: str,
    ) -> str | None:
        """Create draft PR via `gh` CLI. Returns PR URL or None."""
        if shutil.which("gh") is None:
            return None

        body = (
            f"## Feature\n\n{feature_name}\n\n"
            "## Generated Spec\n\n"
            "<details>\n<summary>Click to expand</summary>\n\n"
            f"```markdown\n{spec_content}\n```\n\n"
            "</details>\n\n"
            "## Review Checklist\n\n"
            "- [ ] Spec makes sense\n"
            "- [ ] Implementation matches spec\n"
            "- [ ] Tests are adequate\n"
            "- [ ] No security issues\n"
            "- [ ] Code follows project patterns\n\n"
            "---\n\n"
            "_Generated by overnight-autonomous.py_\n"
        )

        try:
            result = subprocess.run(
                [
                    "gh", "pr", "create", "--draft",
                    "--title", f"Auto: {feature_name}",
                    "--body", body,
                ],
                capture_output=True,
                text=True,
                cwd=str(self.project_dir),
                timeout=60,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, OSError):
            logger.warning("Failed to create PR for %s", branch_name)

        return None

    # ── Step 4: Report ────────────────────────────────────────────────────

    def _report_summary(self) -> None:
        """Print summary with step timings, feature timings, roadmap status."""
        total_elapsed = int(time.time() - self.script_start)

        logger.info("═" * 59)
        logger.info(
            "  SUMMARY (total: %s)", _format_duration(total_elapsed)
        )
        logger.info("═" * 59)

        logger.info("Features built: %d", self.built)
        logger.info("Features failed: %d", self.failed)

        # Roadmap status
        roadmap = self.project_dir / ".specs" / "roadmap.md"
        if roadmap.is_file():
            try:
                content = roadmap.read_text()
                completed = content.count("| ✅ |")
                pending = content.count("| ⬜ |")
                in_progress = content.count("| 🔄 |")
                logger.info("")
                logger.info("Roadmap status:")
                logger.info("  ✅ Completed: %d", completed)
                logger.info("  🔄 In Progress: %d", in_progress)
                logger.info("  ⬜ Pending: %d", pending)
            except OSError:
                pass

        logger.info("")
        logger.info("Step timings:")
        for t in self.step_timings:
            logger.info("  %s", t)

        if self.feature_timings:
            logger.info("")
            logger.info("Per-feature timings:")
            for t in self.feature_timings:
                logger.info("  %s", t)

        logger.info("")
        logger.info("Total time: %s", _format_duration(total_elapsed))

        # Slack notification
        if self.built > 0 and self.config.slack_report_channel:
            self._notify_slack(self.built, self.failed)

        logger.info("✓ Overnight run complete!")

    def _notify_slack(self, built: int, failed: int) -> None:
        """Send summary to Slack via agent if configured."""
        # Read roadmap status for the message
        roadmap = self.project_dir / ".specs" / "roadmap.md"
        completed = 0
        pending = 0
        if roadmap.is_file():
            try:
                content = roadmap.read_text()
                completed = content.count("| ✅ |")
                pending = content.count("| ⬜ |")
            except OSError:
                pass

        slack_prompt = (
            f"Post a message to Slack channel {self.config.slack_report_channel}:\n\n"
            "🌙 **Overnight Run Complete**\n\n"
            f"Features built: {built}\n"
            f"Features failed: {failed}\n\n"
            f"Roadmap: {completed} completed, {pending} pending\n\n"
            "Check GitHub for draft PRs to review.\n"
        )

        cmd = agent_cmd(self.config.triage_model or None)
        cmd.append(slack_prompt)
        output_file = self.project_dir / "logs" / "slack-output.txt"
        output_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            run_agent_with_backoff(output_file, cmd)
        except AgentTimeoutError:
            logger.warning("Slack notification timed out")
        finally:
            output_file.unlink(missing_ok=True)

    # ── Eval sidecar ──────────────────────────────────────────────────────

    def _start_eval_sidecar(self) -> None:
        """Start the eval sidecar background process."""
        if not self.config.eval_sidecar:
            logger.info("Eval sidecar disabled (EVAL_SIDECAR=false)")
            return

        sidecar_script = self.project_dir / "scripts" / "eval-sidecar.sh"

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
        log_path = self.project_dir / "logs" / "eval-sidecar.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        env = {
            **os.environ,
            "PROJECT_DIR": str(self.project_dir),
        }

        try:
            with open(log_path, "a") as log_f:
                proc = subprocess.Popen(
                    sidecar_cmd,
                    stdout=log_f,
                    stderr=log_f,
                    env=env,
                )
            self.eval_sidecar_pid = proc.pid
            logger.info(
                "Eval sidecar started (PID: %d)", self.eval_sidecar_pid
            )
        except OSError:
            logger.warning("Eval sidecar failed to start — continuing without it")

    def _stop_eval_sidecar(self) -> None:
        """Stop the eval sidecar (cooperative drain → timeout → SIGTERM)."""
        if self.eval_sidecar_pid is None:
            return

        # Check if still running
        try:
            os.kill(self.eval_sidecar_pid, 0)
        except OSError:
            logger.info("Eval sidecar already exited")
            self.eval_sidecar_pid = None
            return

        # Signal drain
        drain_sentinel = self.project_dir / ".sdd-eval-drain"
        logger.info("Signaling eval sidecar to drain...")
        drain_sentinel.touch()

        # Wait for exit (up to 120s)
        timeout = 120
        waited = 0
        while waited < timeout:
            try:
                os.kill(self.eval_sidecar_pid, 0)
            except OSError:
                break
            time.sleep(2)
            waited += 2

        # Force kill if still running
        try:
            os.kill(self.eval_sidecar_pid, 0)
            logger.warning(
                "Eval sidecar did not exit within %ds — sending SIGTERM",
                timeout,
            )
            import signal
            os.kill(self.eval_sidecar_pid, signal.SIGTERM)
        except OSError:
            logger.info("Eval sidecar exited cleanly")

        drain_sentinel.unlink(missing_ok=True)
        self.eval_sidecar_pid = None

    # ── Prompts ───────────────────────────────────────────────────────────

    def _build_feature_prompt(
        self, feature_id: str, feature_name: str
    ) -> str:
        """Generate overnight build prompt (includes Jira sync, mapping regen)."""
        codebase_summary = ""
        try:
            codebase_summary = generate_codebase_summary(self.project_dir)
        except Exception:
            logger.warning(
                "Failed to generate codebase summary", exc_info=True
            )

        codebase_section = ""
        if codebase_summary:
            codebase_section = (
                f"\n## Codebase Summary (auto-generated)\n{codebase_summary}\n"
            )

        return (
            f"Build feature #{feature_id}: {feature_name}\n\n"
            "Instructions:\n"
            f'1. Read .specs/roadmap.md and locate feature #{feature_id} ("{feature_name}")\n'
            "2. Update roadmap to mark it 🔄 in progress\n"
            f"3. Run /spec-first {feature_name} --full to build it (includes /compound)\n"
            "4. Update roadmap to mark it ✅ completed\n"
            "5. Sync Jira status if configured\n"
            "6. Regenerate mapping: run python -m auto_sdd.scripts.generate_mapping\n"
            "7. Commit all changes with a descriptive message\n"
            "8. If build fails, output: BUILD_FAILED: {reason}\n"
            f"{codebase_section}"
            "After completion, output EXACTLY these signals (each on its own line):\n"
            f"FEATURE_BUILT: {feature_name}\n"
            "SPEC_FILE: {path to the .feature.md file you created/updated}\n"
            "SOURCE_FILES: {comma-separated paths to source files created/modified}\n\n"
            "Or if build fails:\n"
            "BUILD_FAILED: {reason}\n\n"
            "The SPEC_FILE and SOURCE_FILES lines are REQUIRED when FEATURE_BUILT is reported.\n"
            "They are used by the automated drift-check that runs after your build.\n"
        )

    def _build_retry_prompt(self) -> str:
        """Generate overnight retry prompt."""
        parts: list[str] = [
            "The previous build attempt FAILED. There are uncommitted changes "
            "or build errors from the last attempt.\n\n"
            "Your job:\n"
            '1. Run "git status" to understand the current state\n'
            "2. Look at .specs/roadmap.md to find the feature marked 🔄 in progress\n"
            "3. Fix whatever is broken — type errors, missing imports, "
            "incomplete implementation, failing tests\n"
            "4. Make sure the feature works end-to-end. Seed data is fine; "
            "stub functions are not.\n"
            f"5. Run the test suite to verify everything passes: {self.test_cmd}\n"
            "6. Commit all changes with a descriptive message\n"
            "7. Update roadmap to mark the feature ✅ completed\n",
        ]

        if self.last_build_output:
            parts.append(
                f"\nBUILD CHECK FAILURE OUTPUT (last 50 lines):\n"
                f"{self.last_build_output}\n"
            )

        if self.last_test_output:
            parts.append(
                f"\nTEST SUITE FAILURE OUTPUT (last 80 lines):\n"
                f"{self.last_test_output}\n"
            )

        parts.append(
            "\nAfter completion, output EXACTLY these signals (each on its own line):\n"
            "FEATURE_BUILT: {feature name}\n"
            "SPEC_FILE: {path to the .feature.md file}\n"
            "SOURCE_FILES: {comma-separated paths to source files created/modified}\n\n"
            "Or if build fails:\n"
            "BUILD_FAILED: {reason}\n"
        )

        return "".join(parts)

    # ── Cleanup ───────────────────────────────────────────────────────────

    def _cleanup(self) -> None:
        """Release lock and stop sidecar."""
        self._stop_eval_sidecar()
        release_lock(self.lock_file)


# ── CLI entry point ──────────────────────────────────────────────────────────


def main() -> None:
    """CLI entry point: parse args (--resume), load config, run."""
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(
        description="Overnight autonomous feature implementation"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Continue from last crash",
    )
    args = parser.parse_args()

    config = _load_config(resume_mode=args.resume)
    runner = OvernightRunner(config)
    runner.resume_mode = args.resume

    try:
        runner.run()
    except AutoSddError as exc:
        logger.error("Fatal: %s", exc)
        raise SystemExit(1) from exc
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
