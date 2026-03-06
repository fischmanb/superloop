"""Integration (dry-run) tests for the Python build loop.

Unlike the unit tests in test_build_loop.py which mock every subprocess,
these tests exercise real git operations, real file I/O, real roadmap
parsing, real branch setup, and real state persistence.  Only the
``run_claude`` call is mocked — it returns canned signals while also
committing real files into the repo so that post-build gates (HEAD
advancement, clean tree) pass for real.

Usage:
    py/.venv/bin/python -m pytest py/tests/test_dry_run.py -v
    py/.venv/bin/python -m pytest py/tests/test_dry_run.py -v -k structural
    py/.venv/bin/python -m pytest py/tests/test_dry_run.py -v -k full
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Generator
from unittest.mock import patch

import pytest

from auto_sdd.lib.claude_wrapper import ClaudeResult
from auto_sdd.lib.reliability import Feature, emit_topo_order
from auto_sdd.scripts.build_loop import BuildLoop

# Patch target for codebase summary — called inside prompt_builder
_CODEBASE_SUMMARY_PATCH = (
    "auto_sdd.lib.prompt_builder.generate_codebase_summary"
)

logger = logging.getLogger(__name__)

# ── Roadmap fixture text ─────────────────────────────────────────────────────

ROADMAP_TEXT = """\
# Dry-Run Test Roadmap

Minimal roadmap for integration testing.

| # | Feature | Source | Jira | Complexity | Deps | Status |
|---|---------|--------|------|------------|------|--------|
| 1 | Hello World | manual | - | S | - | ⬜ |
| 2 | Greeting Config | manual | - | S | 1 | ⬜ |
"""

VISION_TEXT = """\
# Test Project Vision
A minimal test project for dry-run integration testing.
"""


# ── Git helpers ──────────────────────────────────────────────────────────────


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        cwd=str(cwd),
        timeout=30,
    )


def _git_init(project: Path) -> None:
    """Initialize a git repo with initial commit."""
    _git(["init", "-b", "main"], project)
    _git(["config", "user.email", "test@dryrun.com"], project)
    _git(["config", "user.name", "DryRun"], project)
    _git(["config", "commit.gpgsign", "false"], project)
    _git(["add", "-A"], project)
    _git(["commit", "-m", "initial: dry-run test project"], project)


def _head_sha(cwd: Path) -> str:
    result = _git(["rev-parse", "HEAD"], cwd)
    return result.stdout.strip()


def _is_clean(cwd: Path) -> bool:
    result = _git(["status", "--porcelain"], cwd)
    return result.stdout.strip() == ""


def _branch_list(cwd: Path) -> list[str]:
    result = _git(["branch", "--list"], cwd)
    return [b.strip().lstrip("* ") for b in result.stdout.splitlines() if b.strip()]



# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def dry_run_project(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a minimal git-initialized project for integration tests."""
    project = tmp_path / "test-project"
    project.mkdir()

    # Spec files
    specs = project / ".specs"
    specs.mkdir()
    (specs / "roadmap.md").write_text(ROADMAP_TEXT)
    (specs / "vision.md").write_text(VISION_TEXT)

    # Minimal project files
    (project / "CLAUDE.md").write_text("# Test Project\n")
    (project / "package.json").write_text(
        '{"name": "dry-run-test", "version": "1.0.0"}\n'
    )

    _git_init(project)
    yield project


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove env vars that interfere with BuildLoop."""
    for var in [
        "PROJECT_DIR", "MAIN_BRANCH", "BASE_BRANCH",
        "BRANCH_STRATEGY", "MAX_FEATURES", "MAX_RETRIES",
        "MIN_RETRY_DELAY", "BUILD_MODE", "DRIFT_CHECK",
        "POST_BUILD_STEPS", "PARALLEL_VALIDATION",
        "ENABLE_RESUME", "AGENT_MODEL", "BUILD_MODEL",
        "RETRY_MODEL", "DRIFT_MODEL", "REVIEW_MODEL",
        "LOGS_DIR", "EVAL_OUTPUT_DIR", "COST_LOG_FILE",
        "BUILD_CHECK_CMD", "TEST_CHECK_CMD",
        "EVAL_SIDECAR", "CLAUDECODE", "AGENT_TIMEOUT",
    ]:
        monkeypatch.delenv(var, raising=False)


def _fake_agent(project: Path, feature_name: str) -> ClaudeResult:
    """Simulate what an agent does: create a file, commit, emit signals.

    This runs real git commands so post-build gates (HEAD advancement,
    clean working tree) pass without mocking.
    """
    safe = feature_name.lower().replace(" ", "-")
    src_file = project / f"{safe}.ts"
    src_file.write_text(f'export const {safe} = "{feature_name}";\n')
    spec_file = project / ".specs" / f"{safe}.md"
    spec_file.write_text(f"---\nfeature: {feature_name}\n---\n")

    _git(["add", "-A"], project)
    _git(["commit", "-m", f"feat: {feature_name}"], project)

    return ClaudeResult(
        output=(
            f"FEATURE_BUILT: {feature_name}\n"
            f"SPEC_FILE: {spec_file}\n"
            f"SOURCE_FILES: {src_file}\n"
        ),
        exit_code=0,
        cost_usd=0.01,
        input_tokens=500,
        output_tokens=200,
    )


def _make_dry_run_loop(project: Path) -> BuildLoop:
    """Create a BuildLoop pointed at a real git project.

    Only sets env vars that aren't already set, so tests can override
    specific values before calling this.
    """
    defaults = {
        "PROJECT_DIR": str(project),
        "MAIN_BRANCH": "main",
        "BRANCH_STRATEGY": "sequential",
        "MAX_FEATURES": "2",
        "MAX_RETRIES": "0",
        "MIN_RETRY_DELAY": "0",
        "BUILD_CHECK_CMD": "skip",
        "TEST_CHECK_CMD": "skip",
        "POST_BUILD_STEPS": "",
        "DRIFT_CHECK": "false",
        "ENABLE_RESUME": "true",
        "EVAL_SIDECAR": "false",
        "LOGS_DIR": str(project / "logs"),
        "AGENT_TIMEOUT": "60",
    }
    for key, val in defaults.items():
        if key not in os.environ:
            os.environ[key] = val

    loop = BuildLoop()
    return loop


@contextmanager
def _mock_agent_env(
    mock_fn: Callable[..., ClaudeResult],
) -> Generator[None, None, None]:
    """Patch both run_claude and codebase summary for integration tests."""
    with patch(
        "auto_sdd.scripts.build_loop.run_claude",
        side_effect=mock_fn,
    ), patch(
        _CODEBASE_SUMMARY_PATCH,
        return_value="(codebase summary stubbed for dry-run)",
    ):
        yield



# ═══════════════════════════════════════════════════════════════════════════
# STRUCTURAL TESTS — no agent calls, validate infrastructure
# ═══════════════════════════════════════════════════════════════════════════


class TestStructuralDryRun:
    """Exercises real git, real roadmap parsing, real state — no agent."""

    def test_roadmap_parses_correctly(
        self, dry_run_project: Path
    ) -> None:
        features = emit_topo_order(dry_run_project)
        assert len(features) == 2
        assert features[0].name == "Hello World"
        assert features[1].name == "Greeting Config"
        # Topo sort: Hello World (no deps) before Greeting Config (dep on 1)
        assert features[0].id == 1
        assert features[1].id == 2

    def test_build_loop_init_real_project(
        self, dry_run_project: Path
    ) -> None:
        loop = _make_dry_run_loop(dry_run_project)
        assert loop.project_dir == dry_run_project
        assert loop.main_branch == "main"
        assert loop.branch_strategy == "sequential"
        assert loop.max_features == 2
        assert loop.drift_check is False
        assert loop.build_cmd == ""  # skip
        assert loop.test_cmd == ""   # skip
        assert loop.logs_dir == dry_run_project / "logs"
        assert loop.logs_dir.is_dir()

    def test_lock_acquired_and_released(
        self, dry_run_project: Path
    ) -> None:
        loop = _make_dry_run_loop(dry_run_project)
        assert loop.lock_file.exists()
        loop._cleanup()
        assert not loop.lock_file.exists()

    def test_no_features_exits_cleanly(
        self, dry_run_project: Path
    ) -> None:
        """Empty roadmap → run() returns without error."""
        (dry_run_project / ".specs" / "roadmap.md").write_text(
            "# Empty Roadmap\n\n"
            "| # | Feature | Source | Jira | Complexity | Deps | Status |\n"
            "|---|---------|--------|------|------------|------|--------|\n"
        )
        loop = _make_dry_run_loop(dry_run_project)
        # Should not raise
        with patch("auto_sdd.scripts.build_loop.run_claude"), patch(
            _CODEBASE_SUMMARY_PATCH, return_value=""
        ):
            loop.run()
        assert loop.loop_built == 0
        assert loop.loop_failed == 0

    def test_dep_exclude_detection(
        self, dry_run_project: Path
    ) -> None:
        """Real node_modules dir is detected for git clean exclusion."""
        (dry_run_project / "node_modules").mkdir()
        from auto_sdd.scripts.build_loop import _detect_dep_excludes
        excludes = _detect_dep_excludes(dry_run_project)
        assert "-e" in excludes
        assert "node_modules" in excludes


# ═══════════════════════════════════════════════════════════════════════════
# FULL DRY-RUN TESTS — mocked agent, everything else real
# ═══════════════════════════════════════════════════════════════════════════


class TestFullDryRun:
    """End-to-end build loop with mocked agent, real everything else."""

    def test_single_feature_builds_and_records(
        self, dry_run_project: Path
    ) -> None:
        """Build 1 feature: agent mock commits, gates pass, state saved."""
        os.environ["MAX_FEATURES"] = "1"
        loop = _make_dry_run_loop(dry_run_project)

        initial_head = _head_sha(dry_run_project)

        def mock_run_claude(
            args: list[str], **kwargs: object
        ) -> ClaudeResult:
            return _fake_agent(dry_run_project, "Hello World")

        with _mock_agent_env(mock_run_claude):
            loop.run()

        # Feature was built
        assert loop.loop_built == 1
        assert loop.loop_failed == 0
        assert "Hello World" in loop.built_feature_names

        # HEAD advanced (real git commit happened)
        assert _head_sha(dry_run_project) != initial_head

        # Working tree is clean (untracked .sdd-state is expected)
        result = _git(["status", "--porcelain"], dry_run_project)
        tracked_dirty = [
            l for l in result.stdout.splitlines()
            if l.strip() and not l.startswith("??")
            and ".sdd-state/" not in l
        ]
        assert tracked_dirty == []

        # Resume state is cleaned up after a full success (0 failures).
        # This is correct: state only persists for partial runs needing resume.
        state_file = dry_run_project / ".sdd-state" / "resume.json"
        assert not state_file.exists(), (
            "Resume state should be cleaned after 0-failure run"
        )

        # Build summary written
        summaries = list(
            (dry_run_project / "logs").glob("build-summary-*.json")
        )
        assert len(summaries) == 1
        summary = json.loads(summaries[0].read_text())
        assert summary["features_built"] == 1
        assert summary["features_failed"] == 0
        assert len(summary["features"]) == 1
        assert summary["features"][0]["name"] == "Hello World"
        assert summary["features"][0]["status"] == "built"

    def test_two_features_build_sequentially(
        self, dry_run_project: Path
    ) -> None:
        """Build 2 features in topo order, both succeed."""
        os.environ["MAX_FEATURES"] = "2"
        loop = _make_dry_run_loop(dry_run_project)
        call_count = 0

        def mock_run_claude(
            args: list[str], **kwargs: object
        ) -> ClaudeResult:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _fake_agent(dry_run_project, "Hello World")
            return _fake_agent(dry_run_project, "Greeting Config")

        with _mock_agent_env(mock_run_claude):
            loop.run()

        assert loop.loop_built == 2
        assert loop.loop_failed == 0
        assert loop.built_feature_names == [
            "Hello World", "Greeting Config"
        ]

        # Both features in summary
        summaries = list(
            (dry_run_project / "logs").glob("build-summary-*.json")
        )
        summary = json.loads(summaries[0].read_text())
        assert summary["features_built"] == 2
        names = [f["name"] for f in summary["features"]]
        assert names == ["Hello World", "Greeting Config"]

    def test_build_failure_recorded(
        self, dry_run_project: Path
    ) -> None:
        """Agent returns BUILD_FAILED → recorded as failure."""
        os.environ["MAX_FEATURES"] = "1"
        loop = _make_dry_run_loop(dry_run_project)

        def mock_run_claude(
            args: list[str], **kwargs: object
        ) -> ClaudeResult:
            return ClaudeResult(
                output="BUILD_FAILED: could not compile\n",
                exit_code=1,
            )

        with _mock_agent_env(mock_run_claude):
            loop.run()

        assert loop.loop_built == 0
        assert loop.loop_failed == 1
        assert "Hello World" in loop.loop_skipped

    def test_credit_exhaustion_halts(
        self, dry_run_project: Path
    ) -> None:
        """Credit exhaustion in agent output → SystemExit."""
        os.environ["MAX_FEATURES"] = "1"
        loop = _make_dry_run_loop(dry_run_project)

        def mock_run_claude(
            args: list[str], **kwargs: object
        ) -> ClaudeResult:
            return ClaudeResult(
                output="Error: insufficient_quota\n",
                exit_code=1,
            )

        with pytest.raises(SystemExit):
            with _mock_agent_env(mock_run_claude):
                loop.run()

    def test_progress_blocks_in_output(
        self, dry_run_project: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """BUILD PROGRESS blocks appear in log output."""
        os.environ["MAX_FEATURES"] = "1"
        loop = _make_dry_run_loop(dry_run_project)

        def mock_run_claude(
            args: list[str], **kwargs: object
        ) -> ClaudeResult:
            return _fake_agent(dry_run_project, "Hello World")

        with caplog.at_level(logging.INFO):
            with _mock_agent_env(mock_run_claude):
                loop.run()

        log_text = caplog.text
        # Progress blocks should appear at multiple phases
        assert log_text.count("BUILD PROGRESS") >= 3
        assert "Hello World" in log_text
        assert "======" in log_text
        # Phases should be labeled
        assert "starting build" in log_text
        assert "invoking agent" in log_text

    def test_resume_skips_completed(
        self, dry_run_project: Path
    ) -> None:
        """Resume state from prior run → skips already-built features."""
        os.environ["MAX_FEATURES"] = "2"

        # Pre-seed resume state as if feature 1 already built
        state_dir = dry_run_project / ".sdd-state"
        state_dir.mkdir(exist_ok=True)
        (state_dir / "resume.json").write_text(json.dumps({
            "feature_index": 0,
            "branch_strategy": "sequential",
            "completed_features": ["Hello World"],
            "current_branch": "main",
        }))

        loop = _make_dry_run_loop(dry_run_project)
        call_count = 0

        def mock_run_claude(
            args: list[str], **kwargs: object
        ) -> ClaudeResult:
            nonlocal call_count
            call_count += 1
            return _fake_agent(dry_run_project, "Greeting Config")

        with _mock_agent_env(mock_run_claude):
            loop.run()

        # Only feature 2 was built (feature 1 skipped via resume)
        assert call_count == 1
        assert loop.loop_built == 1
        assert "Greeting Config" in loop.built_feature_names

    def test_chained_branch_strategy(
        self, dry_run_project: Path
    ) -> None:
        """Chained strategy creates real branches that chain off each other."""
        os.environ["MAX_FEATURES"] = "1"
        os.environ["BRANCH_STRATEGY"] = "chained"
        loop = _make_dry_run_loop(dry_run_project)

        def mock_run_claude(
            args: list[str], **kwargs: object
        ) -> ClaudeResult:
            return _fake_agent(dry_run_project, "Hello World")

        with _mock_agent_env(mock_run_claude):
            loop.run()

        assert loop.loop_built == 1

        # Branch was created — chained uses auto/chained-TIMESTAMP format
        branches = _branch_list(dry_run_project)
        assert any(b.startswith("auto/chained-") for b in branches), (
            f"Expected auto/chained-* branch, got: {branches}"
        )

    def test_head_not_advanced_fails_gate(
        self, dry_run_project: Path
    ) -> None:
        """Agent claims FEATURE_BUILT but doesn't commit → gate fails."""
        os.environ["MAX_FEATURES"] = "1"
        loop = _make_dry_run_loop(dry_run_project)

        def mock_run_claude(
            args: list[str], **kwargs: object
        ) -> ClaudeResult:
            # Return FEATURE_BUILT signal but don't actually commit
            return ClaudeResult(
                output=(
                    "FEATURE_BUILT: Hello World\n"
                    "SPEC_FILE: .specs/hello-world.md\n"
                    "SOURCE_FILES: hello-world.ts\n"
                ),
                exit_code=0,
            )

        with _mock_agent_env(mock_run_claude):
            loop.run()

        # Gate should catch the lie — no commit means HEAD didn't advance
        assert loop.loop_built == 0
        assert loop.loop_failed == 1

    def test_dirty_tree_fails_gate(
        self, dry_run_project: Path
    ) -> None:
        """Agent commits but leaves uncommitted files → gate fails."""
        os.environ["MAX_FEATURES"] = "1"
        loop = _make_dry_run_loop(dry_run_project)

        def mock_run_claude(
            args: list[str], **kwargs: object
        ) -> ClaudeResult:
            # Commit something (advances HEAD) but leave a dirty file
            (dry_run_project / "feature.ts").write_text("export const x = 1;\n")
            _git(["add", "feature.ts"], dry_run_project)
            _git(["commit", "-m", "feat: partial"], dry_run_project)
            (dry_run_project / "leftover.ts").write_text("oops\n")

            spec = dry_run_project / ".specs" / "hello-world.md"
            spec.write_text("---\nfeature: Hello World\n---\n")

            return ClaudeResult(
                output=(
                    "FEATURE_BUILT: Hello World\n"
                    f"SPEC_FILE: {spec}\n"
                    "SOURCE_FILES: feature.ts\n"
                ),
                exit_code=0,
            )

        with _mock_agent_env(mock_run_claude):
            loop.run()

        # NOTE: untracked files are warnings, not gate failures.
        # The dirty-tree gate only checks tracked (modified/staged) files.
        # Since leftover.ts is untracked, the build still succeeds.
        assert loop.loop_built == 1
        assert loop.loop_failed == 0

    def test_signal_fallback_drift_clean(
        self, dry_run_project: Path
    ) -> None:
        """Agent emits NO_DRIFT but no FEATURE_BUILT → inferred success."""
        os.environ["MAX_FEATURES"] = "1"
        loop = _make_dry_run_loop(dry_run_project)

        def mock_run_claude(
            args: list[str], **kwargs: object
        ) -> ClaudeResult:
            # Commit a file (advances HEAD, clean tree) but no FEATURE_BUILT
            (dry_run_project / "feature.ts").write_text("export const x = 1;\n")
            _git(["add", "-A"], dry_run_project)
            _git(["commit", "-m", "feat: hello world"], dry_run_project)
            return ClaudeResult(
                output="NO_DRIFT\nAll checks passed.\n",
                exit_code=0,
            )

        with _mock_agent_env(mock_run_claude):
            loop.run()

        # Should infer success from NO_DRIFT + HEAD advanced + clean tree
        assert loop.loop_built == 1
        assert loop.loop_failed == 0

    def test_build_summary_structure_complete(
        self, dry_run_project: Path
    ) -> None:
        """Build summary JSON has all required fields."""
        os.environ["MAX_FEATURES"] = "1"
        loop = _make_dry_run_loop(dry_run_project)

        def mock_run_claude(
            args: list[str], **kwargs: object
        ) -> ClaudeResult:
            return _fake_agent(dry_run_project, "Hello World")

        with _mock_agent_env(mock_run_claude):
            loop.run()

        summaries = list(
            (dry_run_project / "logs").glob("build-summary-*.json")
        )
        summary = json.loads(summaries[0].read_text())

        # Top-level required fields
        assert "timestamp" in summary
        assert "total_time_seconds" in summary
        assert isinstance(summary["total_time_seconds"], int)
        assert "model" in summary
        assert "branch_strategy" in summary
        assert summary["branch_strategy"] == "sequential"
        assert "features_built" in summary
        assert "features_failed" in summary
        assert "total_tests" in summary
        assert "features" in summary

        # Per-feature required fields
        feat = summary["features"][0]
        assert "name" in feat
        assert "status" in feat
        assert "model" in feat
        assert "time_seconds" in feat
        assert isinstance(feat["time_seconds"], int)
        assert feat["time_seconds"] >= 0
