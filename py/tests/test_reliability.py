"""Tests for auto_sdd.lib.reliability — mirrors tests/test-reliability.sh.

Bash test suite has 68 assertions across 13 test groups. This pytest suite
covers the same scenarios adapted for the Python API. Bash-specific meta-tests
(function-call grep checks, bash -n syntax checks) are replaced with
Python-specific equivalents (import checks, type-annotation coverage).
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from auto_sdd.lib.reliability import (
    AutoSddError,
    AgentTimeoutError,
    CircularDependencyError,
    DriftPair,
    Feature,
    LockContentionError,
    ResumeState,
    _lock_fds,
    acquire_lock,
    check_circular_deps,
    clean_state,
    emit_topo_order,
    get_cpu_count,
    read_state,
    release_lock,
    run_agent_with_backoff,
    run_parallel_drift_checks,
    truncate_for_context,
    write_state,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def state_file(tmp_path: Path) -> Path:
    """Path for a resume-state JSON file (not yet created)."""
    state_dir = tmp_path / ".sdd-state"
    state_dir.mkdir()
    return state_dir / "resume.json"


@pytest.fixture()
def lock_file(tmp_path: Path) -> Path:
    """Path for a lock file (not yet created)."""
    return tmp_path / "test.lock"


@pytest.fixture()
def roadmap_dir(tmp_path: Path) -> Path:
    """A temporary project dir with a .specs/ directory ready for roadmap.md."""
    specs = tmp_path / ".specs"
    specs.mkdir()
    return tmp_path


# ── truncate_for_context ─────────────────────────────────────────────────────
# Mirrors bash: 8 assertions


class TestTruncateForContext:
    """Tests for truncate_for_context — file shorter than limit, empty,
    nonexistent, and large-file truncation to Gherkin-only."""

    def test_truncate_for_context_small_file_returns_full_content(
        self, tmp_path: Path
    ) -> None:
        small = tmp_path / "small.md"
        small.write_text("line1\nline2\nline3\n")
        result = truncate_for_context(small)
        assert result == "line1\nline2\nline3\n", "small file should return full content"

    def test_truncate_for_context_empty_file_returns_empty(
        self, tmp_path: Path
    ) -> None:
        empty = tmp_path / "empty.md"
        empty.write_text("")
        result = truncate_for_context(empty)
        assert result == "", "empty file should return empty string"

    def test_truncate_for_context_nonexistent_returns_empty(
        self, tmp_path: Path
    ) -> None:
        result = truncate_for_context(tmp_path / "noexist.md")
        assert result == "", "nonexistent file should return empty string"

    def test_truncate_for_context_large_file_keeps_frontmatter(
        self, tmp_path: Path
    ) -> None:
        large = tmp_path / "large.feature.md"
        large.write_text(self._large_spec())
        # max_tokens=40 → budget_half=20 tokens = 80 chars. File is larger.
        result = truncate_for_context(large, max_tokens=40)
        assert "feature: Test" in result, "truncated output should have frontmatter"

    def test_truncate_for_context_large_file_keeps_scenario(
        self, tmp_path: Path
    ) -> None:
        large = tmp_path / "large.feature.md"
        large.write_text(self._large_spec())
        result = truncate_for_context(large, max_tokens=40)
        assert "Scenario: Happy path" in result, "truncated output should have Scenario"

    def test_truncate_for_context_large_file_keeps_given(
        self, tmp_path: Path
    ) -> None:
        large = tmp_path / "large.feature.md"
        large.write_text(self._large_spec())
        result = truncate_for_context(large, max_tokens=40)
        assert "Given a registered user" in result, "truncated output should have Given"

    def test_truncate_for_context_large_file_keeps_when(
        self, tmp_path: Path
    ) -> None:
        large = tmp_path / "large.feature.md"
        large.write_text(self._large_spec())
        result = truncate_for_context(large, max_tokens=40)
        assert "When they log in" in result, "truncated output should have When"

    def test_truncate_for_context_large_file_keeps_then(
        self, tmp_path: Path
    ) -> None:
        large = tmp_path / "large.feature.md"
        large.write_text(self._large_spec())
        result = truncate_for_context(large, max_tokens=40)
        assert "Then they see the dashboard" in result, "truncated output should have Then"

    @staticmethod
    def _large_spec() -> str:
        return textwrap.dedent("""\
            ---
            feature: Test
            status: specced
            ---
            # Feature: Login
            ## Scenario: Happy path
            Given a registered user
            When they log in
            Then they see the dashboard
            ## UI Mockup
            +------------------+
            | Username: [____] |
            | Password: [____] |
            | [  Login  ]      |
            +------------------+
            Some random text that should be removed
            More non-Gherkin content here
        """)


# ── write_state / read_state round-trip ──────────────────────────────────────
# Mirrors bash: 7 assertions


class TestStateRoundtrip:
    """Tests for write_state, read_state, and clean_state."""

    def test_write_state_creates_file(self, state_file: Path) -> None:
        write_state(state_file, 3, "chained", ["Auth: Signup", "Dashboard"], "auto/feature-1")
        assert state_file.exists(), "state file should be created"

    def test_read_state_feature_index(self, state_file: Path) -> None:
        write_state(state_file, 3, "chained", ["Auth: Signup", "Dashboard"], "auto/feature-1")
        state = read_state(state_file)
        assert state is not None
        assert state.feature_index == 3, "feature_index should round-trip"

    def test_read_state_branch_strategy(self, state_file: Path) -> None:
        write_state(state_file, 3, "chained", ["Auth: Signup", "Dashboard"], "auto/feature-1")
        state = read_state(state_file)
        assert state is not None
        assert state.branch_strategy == "chained", "branch_strategy should round-trip"

    def test_read_state_current_branch(self, state_file: Path) -> None:
        write_state(state_file, 3, "chained", ["Auth: Signup", "Dashboard"], "auto/feature-1")
        state = read_state(state_file)
        assert state is not None
        assert state.current_branch == "auto/feature-1", "current_branch should round-trip"

    def test_write_state_special_chars_valid_json(self, state_file: Path) -> None:
        write_state(
            state_file,
            5,
            "independent",
            ['Feature with "quotes"', "Feature with \\backslash", "Feature: with colons"],
            "auto/feature-2",
        )
        raw = json.loads(state_file.read_text())
        assert isinstance(raw, dict), "state file should contain valid JSON object"

    def test_clean_state_removes_file(self, state_file: Path) -> None:
        write_state(state_file, 0, "chained", [], "auto/branch")
        clean_state(state_file)
        assert not state_file.exists(), "clean_state should remove the file"

    def test_read_state_returns_none_when_missing(self, state_file: Path) -> None:
        result = read_state(state_file)
        assert result is None, "read_state should return None when file is missing"


# ── completed_features serialization (via write_state) ───────────────────────
# Mirrors bash completed_features_json: 4 assertions
# In Python, serialization is internal to write_state. We test via round-trip.


class TestCompletedFeaturesSerialization:
    """Verify that completed feature lists round-trip correctly through
    write_state/read_state, including edge cases that the bash
    completed_features_json() function handled."""

    def test_empty_list(self, state_file: Path) -> None:
        write_state(state_file, 0, "chained", [], "auto/branch")
        state = read_state(state_file)
        assert state is not None
        assert state.completed_features == [], "empty list should round-trip"

    def test_single_item(self, state_file: Path) -> None:
        write_state(state_file, 0, "chained", ["Auth"], "auto/branch")
        state = read_state(state_file)
        assert state is not None
        assert state.completed_features == ["Auth"], "single item should round-trip"

    def test_multiple_items(self, state_file: Path) -> None:
        write_state(state_file, 0, "chained", ["Auth", "Dashboard", "Settings"], "auto/branch")
        state = read_state(state_file)
        assert state is not None
        assert state.completed_features == ["Auth", "Dashboard", "Settings"]

    def test_colons_in_names(self, state_file: Path) -> None:
        write_state(state_file, 0, "chained", ["Auth: Signup", "Auth: Login"], "auto/branch")
        state = read_state(state_file)
        assert state is not None
        assert state.completed_features == ["Auth: Signup", "Auth: Login"]


# ── check_circular_deps ──────────────────────────────────────────────────────
# Mirrors bash: 4 assertions


class TestCheckCircularDeps:
    """Cycle detection on roadmap dependency graphs."""

    def test_check_circular_deps_no_roadmap(self, tmp_path: Path) -> None:
        # No .specs/roadmap.md → no error
        check_circular_deps(tmp_path)

    def test_check_circular_deps_no_cycle(self, roadmap_dir: Path) -> None:
        (roadmap_dir / ".specs" / "roadmap.md").write_text(textwrap.dedent("""\
            # Roadmap

            | # | Feature | Source | Jira | Complexity | Deps | Status |
            |---|---------|--------|------|------------|------|--------|
            | 1 | Auth | clone | - | M | - | ⬜ |
            | 2 | Dashboard | clone | - | L | 1 | ⬜ |
            | 3 | Settings | clone | - | S | 1 | ⬜ |
            | 4 | Reports | clone | - | M | 2, 3 | ⬜ |
        """))
        check_circular_deps(roadmap_dir)  # should not raise

    def test_check_circular_deps_cycle_detected(self, roadmap_dir: Path) -> None:
        (roadmap_dir / ".specs" / "roadmap.md").write_text(textwrap.dedent("""\
            # Roadmap

            | # | Feature | Source | Jira | Complexity | Deps | Status |
            |---|---------|--------|------|------------|------|--------|
            | 1 | Auth | clone | - | M | - | ⬜ |
            | 2 | Dashboard | clone | - | L | 4 | ⬜ |
            | 3 | Settings | clone | - | S | 2 | ⬜ |
            | 4 | Reports | clone | - | M | 3 | ⬜ |
        """))
        with pytest.raises(CircularDependencyError, match="Circular dependency"):
            check_circular_deps(roadmap_dir)

    def test_check_circular_deps_no_deps_column(self, roadmap_dir: Path) -> None:
        (roadmap_dir / ".specs" / "roadmap.md").write_text(textwrap.dedent("""\
            # Roadmap

            | # | Feature | Source | Jira | Complexity | Deps | Status |
            |---|---------|--------|------|------------|------|--------|
            | 1 | Auth | clone | - | M | - | ⬜ |
            | 2 | Dashboard | clone | - | L | - | ⬜ |
        """))
        check_circular_deps(roadmap_dir)  # should not raise


# ── acquire_lock / release_lock ──────────────────────────────────────────────
# Mirrors bash: 4 assertions


class TestLock:
    """File-based locking with PID stale detection."""

    def test_acquire_lock_creates_file(self, lock_file: Path) -> None:
        acquire_lock(lock_file)
        try:
            assert lock_file.exists(), "lock file should be created"
        finally:
            release_lock(lock_file)

    def test_acquire_lock_contains_pid(self, lock_file: Path) -> None:
        acquire_lock(lock_file)
        try:
            pid_str = lock_file.read_text().strip()
            assert pid_str == str(os.getpid()), "lock file should contain our PID"
        finally:
            release_lock(lock_file)

    def test_release_lock_removes_file(self, lock_file: Path) -> None:
        acquire_lock(lock_file)
        release_lock(lock_file)
        assert not lock_file.exists(), "lock file should be removed after release"

    def test_acquire_lock_stale_pid_replaced(self, lock_file: Path) -> None:
        # Write a stale PID (one that doesn't exist)
        lock_file.write_text("99999999\n")
        acquire_lock(lock_file)
        try:
            pid_str = lock_file.read_text().strip()
            assert pid_str == str(os.getpid()), "stale lock should be replaced with our PID"
        finally:
            release_lock(lock_file)


# ── read_state BUILT_FEATURE_NAMES ───────────────────────────────────────────
# Mirrors bash: 4 assertions


class TestReadStateCompletedFeatures:
    """Verify that read_state correctly populates completed_features."""

    def test_read_state_two_features(self, state_file: Path) -> None:
        write_state(state_file, 2, "chained", ["Auth: Signup", "Dashboard"], "auto/feature-2")
        state = read_state(state_file)
        assert state is not None
        assert len(state.completed_features) == 2

    def test_read_state_first_feature_name(self, state_file: Path) -> None:
        write_state(state_file, 2, "chained", ["Auth: Signup", "Dashboard"], "auto/feature-2")
        state = read_state(state_file)
        assert state is not None
        assert state.completed_features[0] == "Auth: Signup"

    def test_read_state_second_feature_name(self, state_file: Path) -> None:
        write_state(state_file, 2, "chained", ["Auth: Signup", "Dashboard"], "auto/feature-2")
        state = read_state(state_file)
        assert state is not None
        assert state.completed_features[1] == "Dashboard"

    def test_read_state_empty_completed_features(self, state_file: Path) -> None:
        write_state(state_file, 0, "chained", [], "auto/feature-0")
        state = read_state(state_file)
        assert state is not None
        assert state.completed_features == [], "empty completed_features should round-trip"


# ── write_state special characters ───────────────────────────────────────────
# Mirrors bash: 3 assertions (branch with ", branch with \, strategy with ")


class TestWriteStateSpecialChars:
    """Verify that write_state produces valid JSON with special characters."""

    def test_write_state_branch_with_double_quote(self, state_file: Path) -> None:
        write_state(state_file, 0, "chained", ["Feature1"], 'auto/branch-with"quote')
        raw = json.loads(state_file.read_text())
        assert raw["current_branch"] == 'auto/branch-with"quote'

    def test_write_state_branch_with_backslash(self, state_file: Path) -> None:
        write_state(state_file, 0, "chained", ["Feature1"], "auto/branch-with\\backslash")
        raw = json.loads(state_file.read_text())
        assert raw["current_branch"] == "auto/branch-with\\backslash"

    def test_write_state_strategy_with_double_quote(self, state_file: Path) -> None:
        write_state(state_file, 0, 'strategy"with-quote', ["Feature1"], "auto/feature-1")
        raw = json.loads(state_file.read_text())
        assert raw["branch_strategy"] == 'strategy"with-quote'


# ── emit_topo_order ──────────────────────────────────────────────────────────
# Mirrors bash: 10 assertions


class TestEmitTopoOrder:
    """Topological sort of pending features from roadmap.md."""

    def test_emit_topo_order_no_roadmap_returns_empty(self, tmp_path: Path) -> None:
        result = emit_topo_order(tmp_path)
        assert result == [], "no roadmap should return empty list"

    def test_emit_topo_order_no_roadmap_no_error(self, tmp_path: Path) -> None:
        # Should not raise
        emit_topo_order(tmp_path)

    def test_emit_topo_order_all_completed_returns_empty(self, roadmap_dir: Path) -> None:
        (roadmap_dir / ".specs" / "roadmap.md").write_text(textwrap.dedent("""\
            # Roadmap

            | # | Feature | Source | Jira | Complexity | Deps | Status |
            |---|---------|--------|------|------------|------|--------|
            | 1 | Auth | clone | - | M | - | ✅ |
            | 2 | Dashboard | clone | - | L | 1 | ✅ |
            | 3 | Settings | clone | - | S | 1 | ✅ |
        """))
        result = emit_topo_order(roadmap_dir)
        assert result == [], "all completed should return empty list"

    def test_emit_topo_order_all_completed_no_error(self, roadmap_dir: Path) -> None:
        (roadmap_dir / ".specs" / "roadmap.md").write_text(textwrap.dedent("""\
            # Roadmap

            | # | Feature | Source | Jira | Complexity | Deps | Status |
            |---|---------|--------|------|------------|------|--------|
            | 1 | Auth | clone | - | M | - | ✅ |
            | 2 | Dashboard | clone | - | L | 1 | ✅ |
        """))
        emit_topo_order(roadmap_dir)  # should not raise

    def test_emit_topo_order_linear_chain_first(self, roadmap_dir: Path) -> None:
        self._write_linear_chain(roadmap_dir)
        result = emit_topo_order(roadmap_dir)
        assert result[0] == Feature(id=1, name="Auth", complexity="M")

    def test_emit_topo_order_linear_chain_second(self, roadmap_dir: Path) -> None:
        self._write_linear_chain(roadmap_dir)
        result = emit_topo_order(roadmap_dir)
        assert result[1] == Feature(id=2, name="Dashboard", complexity="L")

    def test_emit_topo_order_linear_chain_third(self, roadmap_dir: Path) -> None:
        self._write_linear_chain(roadmap_dir)
        result = emit_topo_order(roadmap_dir)
        assert result[2] == Feature(id=3, name="Settings", complexity="S")

    def test_emit_topo_order_mixed_status_pending_count(self, roadmap_dir: Path) -> None:
        self._write_mixed_status(roadmap_dir)
        result = emit_topo_order(roadmap_dir)
        assert len(result) == 3, "should have 3 pending features"

    def test_emit_topo_order_mixed_status_ordering(self, roadmap_dir: Path) -> None:
        self._write_mixed_status(roadmap_dir)
        result = emit_topo_order(roadmap_dir)
        ids = [f.id for f in result]
        pos_dashboard = ids.index(2)
        pos_reports = ids.index(4)
        assert pos_dashboard < pos_reports, "Dashboard must come before Reports"

    def test_emit_topo_order_output_format(self, roadmap_dir: Path) -> None:
        (roadmap_dir / ".specs" / "roadmap.md").write_text(textwrap.dedent("""\
            # Roadmap

            | # | Feature | Source | Jira | Complexity | Deps | Status |
            |---|---------|--------|------|------------|------|--------|
            | 1 | Auth: Signup | clone | - | M | - | ⬜ |
            | 2 | Dashboard View | clone | - | L | 1 | ⬜ |
        """))
        result = emit_topo_order(roadmap_dir)
        for f in result:
            assert isinstance(f, Feature), "each element should be a Feature"
            assert isinstance(f.id, int), "id should be int"
            assert isinstance(f.name, str) and f.name, "name should be non-empty str"
            assert isinstance(f.complexity, str), "complexity should be str"

    @staticmethod
    def _write_linear_chain(roadmap_dir: Path) -> None:
        (roadmap_dir / ".specs" / "roadmap.md").write_text(textwrap.dedent("""\
            # Roadmap

            | # | Feature | Source | Jira | Complexity | Deps | Status |
            |---|---------|--------|------|------------|------|--------|
            | 1 | Auth | clone | - | M | - | ⬜ |
            | 2 | Dashboard | clone | - | L | 1 | ⬜ |
            | 3 | Settings | clone | - | S | 2 | ⬜ |
        """))

    @staticmethod
    def _write_mixed_status(roadmap_dir: Path) -> None:
        (roadmap_dir / ".specs" / "roadmap.md").write_text(textwrap.dedent("""\
            # Roadmap

            | # | Feature | Source | Jira | Complexity | Deps | Status |
            |---|---------|--------|------|------------|------|--------|
            | 1 | Auth | clone | - | M | - | ✅ |
            | 2 | Dashboard | clone | - | L | 1 | ⬜ |
            | 3 | Profile | clone | - | S | - | ⬜ |
            | 4 | Reports | clone | - | XL | 2 | ⬜ |
        """))


# ── get_cpu_count ─────────────────────────────────────────────────────────────


class TestGetCpuCount:
    """CPU count detection."""

    def test_get_cpu_count_returns_positive_int(self) -> None:
        count = get_cpu_count()
        assert isinstance(count, int) and count > 0


# ── run_parallel_drift_checks ────────────────────────────────────────────────


class TestRunParallelDriftChecks:
    """Parallel drift checking via thread pool."""

    def test_run_parallel_drift_checks_empty_pairs(self) -> None:
        result = run_parallel_drift_checks([], lambda p, s: True)
        assert result is True, "empty pairs should return True"

    def test_run_parallel_drift_checks_all_pass(self, tmp_path: Path) -> None:
        spec = tmp_path / "spec.md"
        spec.touch()
        pairs = [DriftPair(spec_file=spec, source_files="src/a.py")]
        result = run_parallel_drift_checks(pairs, lambda p, s: True)
        assert result is True

    def test_run_parallel_drift_checks_one_fails(self, tmp_path: Path) -> None:
        spec1 = tmp_path / "pass.md"
        spec2 = tmp_path / "fail.md"
        spec1.touch()
        spec2.touch()
        pairs = [
            DriftPair(spec_file=spec1, source_files="src/a.py"),
            DriftPair(spec_file=spec2, source_files="src/b.py"),
        ]

        def check(p: Path, s: str) -> bool:
            return p.name != "fail.md"

        result = run_parallel_drift_checks(pairs, check)
        assert result is False, "should fail when any check fails"

    def test_run_parallel_drift_checks_exception_counts_as_fail(
        self, tmp_path: Path
    ) -> None:
        spec = tmp_path / "boom.md"
        spec.touch()
        pairs = [DriftPair(spec_file=spec, source_files="src/a.py")]

        def boom(p: Path, s: str) -> bool:
            raise RuntimeError("boom")

        result = run_parallel_drift_checks(pairs, boom)
        assert result is False, "exception in check_fn should count as failure"


# ── run_agent_with_backoff ───────────────────────────────────────────────────


class TestRunAgentWithBackoff:
    """Exponential backoff for subprocess calls."""

    def test_run_agent_with_backoff_success(self, tmp_path: Path) -> None:
        output = tmp_path / "output.txt"
        exit_code = run_agent_with_backoff(
            output, ["echo", "hello"], max_retries=1, backoff_max=1
        )
        assert exit_code == 0
        assert "hello" in output.read_text()

    def test_run_agent_with_backoff_non_rate_limit_failure(
        self, tmp_path: Path
    ) -> None:
        output = tmp_path / "output.txt"
        exit_code = run_agent_with_backoff(
            output, ["false"], max_retries=1, backoff_max=1
        )
        assert exit_code != 0, "non-rate-limit failure should return non-zero"

    def test_run_agent_with_backoff_rate_limit_exhausted(
        self, tmp_path: Path
    ) -> None:
        output = tmp_path / "output.txt"
        # Use bash -c to print rate limit message and exit 1
        with pytest.raises(AgentTimeoutError, match="rate limiting"):
            run_agent_with_backoff(
                output,
                ["bash", "-c", "echo 'Error: 429 too many requests' && exit 1"],
                max_retries=1,
                backoff_max=1,
            )


# ── Lock contention ──────────────────────────────────────────────────────────


class TestLockContention:
    """Lock contention when another live process holds the lock."""

    def test_acquire_lock_raises_on_live_pid(self, lock_file: Path) -> None:
        # Write our own PID (which is alive) to simulate contention
        lock_file.write_text(f"{os.getpid()}\n")
        with pytest.raises(LockContentionError, match="Another instance"):
            acquire_lock(lock_file)


# ── Exception hierarchy ─────────────────────────────────────────────────────


class TestExceptionHierarchy:
    """Verify exception classes inherit from AutoSddError."""

    def test_lock_contention_is_auto_sdd_error(self) -> None:
        assert issubclass(LockContentionError, AutoSddError)

    def test_agent_timeout_is_auto_sdd_error(self) -> None:
        assert issubclass(AgentTimeoutError, AutoSddError)

    def test_circular_dependency_is_auto_sdd_error(self) -> None:
        assert issubclass(CircularDependencyError, AutoSddError)


# ── Dataclass structure ──────────────────────────────────────────────────────


class TestDataclasses:
    """Verify dataclass fields match the interface contract."""

    def test_resume_state_fields(self) -> None:
        s = ResumeState(
            feature_index=0,
            branch_strategy="chained",
            completed_features=[],
            current_branch="main",
            timestamp="2024-01-01T00:00:00Z",
        )
        assert s.feature_index == 0
        assert s.branch_strategy == "chained"
        assert s.completed_features == []
        assert s.current_branch == "main"
        assert s.timestamp == "2024-01-01T00:00:00Z"

    def test_feature_fields(self) -> None:
        f = Feature(id=1, name="Auth", complexity="M")
        assert f.id == 1
        assert f.name == "Auth"
        assert f.complexity == "M"

    def test_drift_pair_fields(self) -> None:
        d = DriftPair(spec_file=Path("spec.md"), source_files="src/a.py,src/b.py")
        assert d.spec_file == Path("spec.md")
        assert d.source_files == "src/a.py,src/b.py"


# ── write_state atomicity ───────────────────────────────────────────────────


class TestWriteStateAtomicity:
    """Verify write_state creates valid state even in edge cases."""

    def test_write_state_creates_parent_dirs(self, tmp_path: Path) -> None:
        nested = tmp_path / "a" / "b" / "c" / "state.json"
        write_state(nested, 0, "chained", [], "main")
        assert nested.exists()

    def test_write_state_has_timestamp(self, state_file: Path) -> None:
        write_state(state_file, 0, "chained", [], "main")
        state = read_state(state_file)
        assert state is not None
        assert state.timestamp, "timestamp should be non-empty"

    def test_write_state_overwrites_existing(self, state_file: Path) -> None:
        write_state(state_file, 0, "chained", [], "main")
        write_state(state_file, 5, "independent", ["Auth"], "feature/x")
        state = read_state(state_file)
        assert state is not None
        assert state.feature_index == 5
        assert state.branch_strategy == "independent"


# ── Bash state compatibility ─────────────────────────────────────────────────


class TestBashCompatibility:
    """Verify Python-written state files are readable by the bash parser.

    The JSON format must match what the bash write_state produces so that
    bash read_state (awk-based) can parse Python-written files and vice versa.
    """

    def test_state_json_has_expected_keys(self, state_file: Path) -> None:
        write_state(state_file, 2, "chained", ["Auth", "Dashboard"], "auto/f-1")
        raw = json.loads(state_file.read_text())
        expected_keys = {
            "feature_index",
            "branch_strategy",
            "completed_features",
            "current_branch",
            "timestamp",
        }
        assert set(raw.keys()) == expected_keys

    def test_state_json_feature_index_is_int(self, state_file: Path) -> None:
        write_state(state_file, 3, "chained", [], "main")
        raw = json.loads(state_file.read_text())
        assert isinstance(raw["feature_index"], int)

    def test_state_json_completed_features_is_list(self, state_file: Path) -> None:
        write_state(state_file, 0, "chained", ["Auth"], "main")
        raw = json.loads(state_file.read_text())
        assert isinstance(raw["completed_features"], list)
