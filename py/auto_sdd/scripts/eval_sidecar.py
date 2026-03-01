# CONVERSION CHANGELOG (from scripts/eval-sidecar.sh)
# - Config: env-var-based config replaced with EvalSidecarConfig dataclass. main()
#   reads env vars and constructs the config for CLI compatibility.
# - Logging: echo-based log/warn/error/success replaced with stdlib logging.
# - Signal handling: bash trap replaced with signal module handlers for
#   SIGINT/SIGTERM.
# - Campaign summary: heredoc JSON replaced with json.dumps() via atomic_write_json
#   pattern (temp-then-rename).
# - Subprocess: git commands use subprocess.run() (same pattern as eval_lib._run_git).
# - Agent command: agent_cmd() bash function replaced by _build_agent_cmd() returning
#   list[str].
# - Drain sentinel: same file-based sentinel protocol, cleaned up on startup and
#   after drain.
# - Credit exhaustion: same keyword-based detection, disables agent evals for
#   remainder of run (mechanical continues).
# - generate_campaign_summary returns the Path to the campaign file (or None if no
#   results) instead of only logging.
# - run_polling_loop extracted as a testable function that accepts config + callbacks.
"""Eval sidecar: watches a git repo for new commits and evaluates them.

Runs alongside the build loop. Purely observational — never modifies the
project, never blocks the build, fails gracefully on individual eval errors.

Usage:
    PROJECT_DIR=/path/to/project python -m auto_sdd.scripts.eval_sidecar
    EVAL_AGENT=true EVAL_INTERVAL=60 python -m auto_sdd.scripts.eval_sidecar
"""
from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── Exceptions ────────────────────────────────────────────────────────────────
# Import from the modules that define them.

from auto_sdd.lib.eval_lib import (
    AutoSddError,
    EvalError,
    MechanicalEvalResult,
    generate_eval_prompt,
    parse_eval_signal,
    run_mechanical_eval,
    write_eval_result,
)
from auto_sdd.lib.reliability import (
    AgentTimeoutError,
    run_agent_with_backoff,
)
from auto_sdd.lib.claude_wrapper import (
    ClaudeOutputError,
    run_claude,
)


# ── Configuration ─────────────────────────────────────────────────────────────

@dataclass
class EvalSidecarConfig:
    """Configuration for the eval sidecar polling loop."""

    project_dir: Path
    eval_interval: int = 30
    eval_agent: bool = True
    eval_model: str = ""
    eval_output_dir: Path | None = None

    def __post_init__(self) -> None:
        if not self.project_dir.is_dir():
            raise EvalError(
                f"PROJECT_DIR does not exist: {self.project_dir}"
            )
        if self.eval_output_dir is None:
            self.eval_output_dir = self.project_dir / "logs" / "evals"


# ── Campaign state ────────────────────────────────────────────────────────────

@dataclass
class CampaignState:
    """Mutable state for the sidecar's polling loop."""

    last_evaluated_commit: str = ""
    agent_evals_disabled: bool = False
    eval_count: int = 0
    eval_errors: int = 0
    draining: bool = False
    shutdown_requested: bool = False


# ── Credit exhaustion keywords ────────────────────────────────────────────────

_CREDIT_KEYWORDS: list[str] = [
    "credit",
    "billing",
    "insufficient_quota",
    "quota exceeded",
    "402 payment",
    "429 too many",
    "payment required",
]


def _is_credit_exhaustion(output: str) -> bool:
    """Return True if *output* contains credit/billing exhaustion keywords."""
    lower = output.lower()
    return any(kw in lower for kw in _CREDIT_KEYWORDS)


# ── Git helpers ───────────────────────────────────────────────────────────────

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


def _get_head(project_dir: Path) -> str:
    """Return the HEAD commit hash, or empty string on failure."""
    try:
        result = _run_git(["rev-parse", "HEAD"], project_dir, check=False)
        if result.returncode != 0:
            return ""
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        return ""


def _get_new_commits(
    project_dir: Path,
    since_commit: str,
    until_commit: str,
) -> list[str]:
    """Return commit hashes between *since_commit* and *until_commit*.

    Oldest first, skip merges. Returns empty list on error.
    """
    try:
        result = _run_git(
            [
                "log",
                "--reverse",
                "--no-merges",
                "--format=%H",
                f"{since_commit}..{until_commit}",
            ],
            project_dir,
            check=False,
        )
        if result.returncode != 0:
            return []
        lines = result.stdout.strip().splitlines()
        return [h for h in lines if h.strip()]
    except (subprocess.TimeoutExpired, OSError):
        return []


def _get_commit_message(project_dir: Path, commit_hash: str) -> str:
    """Return the first-line commit message, or '<unknown>' on failure."""
    try:
        result = _run_git(
            ["log", "-1", "--format=%s", commit_hash],
            project_dir,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        pass
    return "<unknown>"


# ── Agent command builder ─────────────────────────────────────────────────────

def _build_agent_cmd(eval_model: str) -> list[str]:
    """Build the base claude CLI command for agent evals."""
    cmd = ["-p", "--dangerously-skip-permissions"]
    if eval_model:
        cmd.extend(["--model", eval_model])
    return cmd


# ── Campaign summary ──────────────────────────────────────────────────────────

def generate_campaign_summary(eval_output_dir: Path) -> Path | None:
    """Aggregate all eval JSON files into a campaign-level summary.

    Returns:
        Path to the campaign file, or None if no eval results exist.
    """
    logger.info("Generating campaign summary...")

    # Collect eval JSON files (not campaign files)
    eval_files: list[Path] = sorted(
        f
        for f in eval_output_dir.iterdir()
        if f.name.startswith("eval-")
        and f.name.endswith(".json")
        and not f.name.startswith("eval-campaign-")
    ) if eval_output_dir.is_dir() else []

    total = len(eval_files)
    if total == 0:
        logger.info("No eval results to summarize")
        return None

    # Signal accumulators
    fw_pass = 0
    fw_warn = 0
    fw_fail = 0
    scope_focused = 0
    scope_moderate = 0
    scope_sprawling = 0
    int_clean = 0
    int_minor = 0
    int_major = 0
    total_type_redeclarations = 0
    features_with_issues: list[str] = []

    for eval_file in eval_files:
        try:
            data = json.loads(eval_file.read_text())
        except (json.JSONDecodeError, OSError):
            logger.warning("Could not parse eval file: %s", eval_file)
            continue

        mechanical: dict[str, Any] = data.get("mechanical", {})
        has_issue = False

        # Type redeclarations
        redecl = int(mechanical.get("type_redeclarations", 0))
        total_type_redeclarations += redecl
        if redecl > 0:
            has_issue = True

        feature_name: str = str(mechanical.get("feature_name", "unknown"))

        # Agent eval signals
        agent_avail = data.get("agent_eval_available", False)
        if agent_avail:
            agent_eval: dict[str, str] = data.get("agent_eval", {})

            fw = agent_eval.get("framework_compliance", "")
            if fw == "pass":
                fw_pass += 1
            elif fw == "warn":
                fw_warn += 1
                has_issue = True
            elif fw == "fail":
                fw_fail += 1
                has_issue = True

            sc = agent_eval.get("scope_assessment", "")
            if sc == "focused":
                scope_focused += 1
            elif sc == "moderate":
                scope_moderate += 1
            elif sc == "sprawling":
                scope_sprawling += 1
                has_issue = True

            iq = agent_eval.get("integration_quality", "")
            if iq == "clean":
                int_clean += 1
            elif iq == "minor_issues":
                int_minor += 1
            elif iq == "major_issues":
                int_major += 1
                has_issue = True

        if has_issue:
            features_with_issues.append(feature_name)

    # Build campaign JSON
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    file_timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    campaign: dict[str, Any] = {
        "campaign_timestamp": timestamp,
        "total_features_evaluated": total,
        "type_redeclarations_total": total_type_redeclarations,
        "framework_compliance": {
            "pass": fw_pass,
            "warn": fw_warn,
            "fail": fw_fail,
        },
        "scope_assessment": {
            "focused": scope_focused,
            "moderate": scope_moderate,
            "sprawling": scope_sprawling,
        },
        "integration_quality": {
            "clean": int_clean,
            "minor_issues": int_minor,
            "major_issues": int_major,
        },
        "features_with_issues_count": len(features_with_issues),
        "features_with_issues": features_with_issues,
    }

    campaign_file = eval_output_dir / f"eval-campaign-{file_timestamp}.json"
    eval_output_dir.mkdir(parents=True, exist_ok=True)

    # Atomic write: temp file then rename
    fd, tmp_path = tempfile.mkstemp(
        dir=str(eval_output_dir), prefix="eval-campaign-"
    )
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(campaign, indent=2) + "\n")
        os.rename(tmp_path, str(campaign_file))
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    # Human-readable summary
    logger.info("=" * 48)
    logger.info("         EVAL CAMPAIGN SUMMARY")
    logger.info("=" * 48)
    logger.info("Total features evaluated: %d", total)
    logger.info("Type redeclarations:      %d", total_type_redeclarations)
    logger.info("-" * 48)
    logger.info(
        "Framework Compliance: pass=%d  warn=%d  fail=%d",
        fw_pass, fw_warn, fw_fail,
    )
    logger.info(
        "Scope Assessment: focused=%d  moderate=%d  sprawling=%d",
        scope_focused, scope_moderate, scope_sprawling,
    )
    logger.info(
        "Integration Quality: clean=%d  minor=%d  major=%d",
        int_clean, int_minor, int_major,
    )
    logger.info("-" * 48)
    logger.info("Features with issues: %d", len(features_with_issues))
    for name in features_with_issues:
        logger.info("  - %s", name)
    logger.info("=" * 48)
    logger.info("Campaign file: %s", campaign_file)

    return campaign_file


# ── Single-commit evaluation ──────────────────────────────────────────────────

def _evaluate_commit(
    config: EvalSidecarConfig,
    state: CampaignState,
    commit_hash: str,
) -> None:
    """Evaluate a single commit: mechanical + optional agent eval.

    Updates *state* counters in place. Never raises — logs and records errors.
    """
    commit_short = commit_hash[:8]
    commit_msg = _get_commit_message(config.project_dir, commit_hash)
    logger.info("Evaluating %s: %s", commit_short, commit_msg)

    assert config.eval_output_dir is not None

    # ── Mechanical eval ───────────────────────────────────────────────────
    try:
        mechanical = run_mechanical_eval(config.project_dir, commit_hash)
    except (EvalError, AutoSddError) as exc:
        logger.warning(
            "Mechanical eval failed for %s — skipping: %s", commit_short, exc
        )
        state.eval_errors += 1
        return

    # Feature name from diff_stats
    feature_name = str(mechanical.diff_stats.get("feature_name", commit_short))
    if not feature_name:
        feature_name = commit_short

    # Skip if merge commit (shouldn't happen since --no-merges, but be safe)
    if mechanical.diff_stats.get("skipped") is True:
        logger.info("Skipped merge commit %s", commit_short)
        return

    # ── Agent eval (if enabled) ───────────────────────────────────────────
    agent_output = ""

    if config.eval_agent and not state.agent_evals_disabled:
        logger.info("Running agent eval for %s...", commit_short)

        try:
            eval_prompt = generate_eval_prompt(
                config.project_dir, commit_hash
            )
        except (EvalError, AutoSddError) as exc:
            logger.warning(
                "Failed to generate eval prompt for %s — mechanical only: %s",
                commit_short, exc,
            )
            state.eval_errors += 1
            eval_prompt = ""

        if eval_prompt:
            agent_output_file = Path(
                tempfile.mktemp(prefix="eval-agent-", suffix=".txt")
            )
            try:
                agent_cmd = _build_agent_cmd(config.eval_model)
                full_cmd = agent_cmd + [eval_prompt]

                agent_exit = run_agent_with_backoff(
                    agent_output_file, full_cmd
                )

                if agent_output_file.is_file():
                    agent_output = agent_output_file.read_text()

                if agent_exit != 0:
                    if _is_credit_exhaustion(agent_output):
                        logger.warning(
                            "API credits exhausted — disabling agent evals "
                            "for remainder of run"
                        )
                        state.agent_evals_disabled = True
                        agent_output = ""
                    else:
                        logger.warning(
                            "Agent eval failed for %s (exit %d) — "
                            "mechanical only",
                            commit_short, agent_exit,
                        )
                        state.eval_errors += 1
                        agent_output = ""
            except AgentTimeoutError:
                logger.warning(
                    "Agent eval timed out for %s — mechanical only",
                    commit_short,
                )
                state.eval_errors += 1
                agent_output = ""
            finally:
                if agent_output_file.is_file():
                    try:
                        agent_output_file.unlink()
                    except OSError:
                        pass

    # ── Write result ──────────────────────────────────────────────────────
    try:
        result_file = write_eval_result(
            config.eval_output_dir, feature_name, mechanical, agent_output
        )
        state.eval_count += 1
        logger.info("Eval complete for %s -> %s", commit_short, result_file)
    except (EvalError, AutoSddError, OSError) as exc:
        logger.warning(
            "Failed to write eval result for %s: %s", commit_short, exc
        )
        state.eval_errors += 1


# ── Polling loop ──────────────────────────────────────────────────────────────

def run_polling_loop(config: EvalSidecarConfig) -> CampaignState:
    """Run the eval sidecar polling loop.

    Returns when draining completes or shutdown is requested (SIGINT/SIGTERM).
    """
    assert config.eval_output_dir is not None
    config.eval_output_dir.mkdir(parents=True, exist_ok=True)

    drain_sentinel = config.project_dir / ".sdd-eval-drain"

    # Clean up stale sentinel from prior crash
    if drain_sentinel.is_file():
        drain_sentinel.unlink()

    state = CampaignState()

    # Initialize: start from current HEAD
    head = _get_head(config.project_dir)
    if not head:
        raise EvalError(
            f"Could not determine HEAD commit in {config.project_dir}"
        )
    state.last_evaluated_commit = head
    logger.info("Starting from commit: %s", head[:8])

    # Signal handler for cooperative shutdown
    def _handle_signal(signum: int, frame: Any) -> None:
        logger.info("Received signal %d, requesting shutdown...", signum)
        state.shutdown_requested = True

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    while not state.shutdown_requested:
        # Check for drain sentinel
        if drain_sentinel.is_file() and not state.draining:
            logger.info(
                "Drain sentinel detected — processing remaining evals..."
            )
            state.draining = True

        # Sleep between polls (skip during drain for faster processing)
        if not state.draining:
            time.sleep(config.eval_interval)

        # Check shutdown again after sleep
        if state.shutdown_requested:
            break

        # Get current HEAD
        current_head = _get_head(config.project_dir)
        if not current_head:
            if state.draining:
                logger.warning(
                    "Could not read HEAD during drain — finishing"
                )
                break
            logger.warning("Could not read HEAD — will retry next cycle")
            continue

        # If HEAD hasn't changed
        if current_head == state.last_evaluated_commit:
            if state.draining:
                break
            continue

        # Get new commits since last evaluated
        new_commits = _get_new_commits(
            config.project_dir,
            state.last_evaluated_commit,
            current_head,
        )

        if not new_commits:
            # Only merge commits or range error — advance pointer
            state.last_evaluated_commit = current_head
            if state.draining:
                break
            continue

        # Evaluate each new commit
        for commit_hash in new_commits:
            if state.shutdown_requested:
                break
            _evaluate_commit(config, state, commit_hash)

        # Advance pointer
        state.last_evaluated_commit = current_head

    # ── Shutdown / drain cleanup ──────────────────────────────────────────
    logger.info(
        "Shutting down (evaluated %d commits, %d errors)",
        state.eval_count, state.eval_errors,
    )
    generate_campaign_summary(config.eval_output_dir)

    if state.draining:
        logger.info("Drain complete — all commits evaluated")
        if drain_sentinel.is_file():
            drain_sentinel.unlink()

    return state


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    """CLI entry point — reads config from environment variables."""
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    project_dir_str = os.environ.get("PROJECT_DIR", "")
    if not project_dir_str:
        logger.error("PROJECT_DIR is required")
        raise SystemExit(1)

    project_dir = Path(project_dir_str)

    eval_interval = int(os.environ.get("EVAL_INTERVAL", "30"))
    eval_agent_str = os.environ.get("EVAL_AGENT", "true").lower()
    eval_agent = eval_agent_str in ("true", "1", "yes")
    eval_model = os.environ.get(
        "EVAL_MODEL", os.environ.get("AGENT_MODEL", "")
    )
    eval_output_dir_str = os.environ.get("EVAL_OUTPUT_DIR", "")
    eval_output_dir: Path | None = (
        Path(eval_output_dir_str) if eval_output_dir_str else None
    )

    config = EvalSidecarConfig(
        project_dir=project_dir,
        eval_interval=eval_interval,
        eval_agent=eval_agent,
        eval_model=eval_model,
        eval_output_dir=eval_output_dir,
    )

    logger.info("=== Eval Sidecar Starting ===")
    logger.info("PROJECT_DIR:    %s", config.project_dir)
    logger.info("EVAL_INTERVAL:  %ds", config.eval_interval)
    logger.info("EVAL_AGENT:     %s", config.eval_agent)
    logger.info("EVAL_MODEL:     %s", config.eval_model or "<default>")
    logger.info("EVAL_OUTPUT_DIR: %s", config.eval_output_dir)
    logger.info("=" * 30)

    run_polling_loop(config)
    logger.info("Exiting cleanly")


if __name__ == "__main__":
    main()
