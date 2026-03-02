"""Tests for auto_sdd.lib.branch_manager."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from auto_sdd.lib.branch_manager import (
    BranchSetupError,
    BranchSetupResult,
    InsufficientDiskSpaceError,
    check_disk_space,
    cleanup_all_worktrees,
    cleanup_branch_chained,
    cleanup_branch_independent,
    cleanup_branch_sequential,
    cleanup_merged_branches,
    setup_branch_chained,
    setup_branch_independent,
    setup_branch_sequential,
)


# ── setup_branch_chained ─────────────────────────────────────────────────────


class TestSetupBranchChained:
    @patch("auto_sdd.lib.branch_manager._run_git")
    def test_creates_branch_from_main(
        self, mock_git: MagicMock, tmp_path: Path
    ) -> None:
        # All git commands succeed
        mock_git.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = setup_branch_chained(tmp_path, "auth", None, "main")
        assert result.branch_name.startswith("auto/chained-")
        assert result.worktree_path is None

    @patch("auto_sdd.lib.branch_manager._run_git")
    def test_creates_branch_from_last_branch(
        self, mock_git: MagicMock, tmp_path: Path
    ) -> None:
        mock_git.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = setup_branch_chained(
            tmp_path, "dashboard", "auto/chained-prev", "main"
        )
        assert result.branch_name.startswith("auto/chained-")

    @patch("auto_sdd.lib.branch_manager._run_git")
    def test_falls_back_to_main_on_checkout_failure(
        self, mock_git: MagicMock, tmp_path: Path
    ) -> None:
        def side_effect(
            args: list[str], *a: object, **kw: object
        ) -> MagicMock:
            if args == ["checkout", "auto/chained-missing"]:
                return MagicMock(returncode=1, stdout="", stderr="error")
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_git.side_effect = side_effect
        result = setup_branch_chained(
            tmp_path, "feat", "auto/chained-missing", "main"
        )
        assert result.branch_name.startswith("auto/chained-")

    @patch("auto_sdd.lib.branch_manager._run_git")
    def test_raises_on_branch_creation_failure(
        self, mock_git: MagicMock, tmp_path: Path
    ) -> None:
        def side_effect(
            args: list[str], *a: object, **kw: object
        ) -> MagicMock:
            if args[0] == "checkout" and "-b" in args:
                return MagicMock(returncode=1, stdout="", stderr="error")
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_git.side_effect = side_effect
        with pytest.raises(BranchSetupError):
            setup_branch_chained(tmp_path, "feat", None, "main")


# ── setup_branch_independent ─────────────────────────────────────────────────


class TestSetupBranchIndependent:
    @patch("auto_sdd.lib.branch_manager.check_disk_space")
    @patch("auto_sdd.lib.branch_manager._run_git")
    def test_creates_worktree(
        self,
        mock_git: MagicMock,
        mock_disk: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_git.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = setup_branch_independent(tmp_path, "feat", "main")
        assert result.branch_name.startswith("auto/auto-independent-")
        assert result.worktree_path is not None

    @patch("auto_sdd.lib.branch_manager.check_disk_space")
    @patch("auto_sdd.lib.branch_manager._run_git")
    def test_raises_on_worktree_failure(
        self,
        mock_git: MagicMock,
        mock_disk: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_git.return_value = MagicMock(
            returncode=1, stdout="", stderr="fatal"
        )
        with pytest.raises(BranchSetupError):
            setup_branch_independent(tmp_path, "feat", "main")


# ── setup_branch_sequential ──────────────────────────────────────────────────


class TestSetupBranchSequential:
    @patch("auto_sdd.lib.branch_manager._run_git")
    def test_returns_current_branch(
        self, mock_git: MagicMock, tmp_path: Path
    ) -> None:
        mock_git.return_value = MagicMock(
            returncode=0, stdout="my-branch\n", stderr=""
        )
        result = setup_branch_sequential(tmp_path)
        assert result.branch_name == "my-branch"

    @patch("auto_sdd.lib.branch_manager._run_git")
    def test_defaults_to_main(
        self, mock_git: MagicMock, tmp_path: Path
    ) -> None:
        mock_git.return_value = MagicMock(
            returncode=0, stdout="", stderr=""
        )
        result = setup_branch_sequential(tmp_path)
        assert result.branch_name == "main"


# ── cleanup_branch_chained ───────────────────────────────────────────────────


class TestCleanupBranchChained:
    def test_returns_current_branch(self) -> None:
        result = cleanup_branch_chained("auto/chained-20240101")
        assert result == "auto/chained-20240101"


# ── cleanup_branch_independent ───────────────────────────────────────────────


class TestCleanupBranchIndependent:
    @patch("auto_sdd.lib.branch_manager._run_git")
    def test_removes_worktree(
        self, mock_git: MagicMock, tmp_path: Path
    ) -> None:
        wt_path = tmp_path / "worktree"
        wt_path.mkdir()
        mock_git.return_value = MagicMock(returncode=0)
        cleanup_branch_independent(wt_path, tmp_path, "auto/feat")
        assert mock_git.called

    def test_noop_for_none(self, tmp_path: Path) -> None:
        # Should not raise
        cleanup_branch_independent(None, tmp_path)

    def test_noop_for_missing_dir(self, tmp_path: Path) -> None:
        cleanup_branch_independent(
            tmp_path / "nonexistent", tmp_path
        )


# ── cleanup_branch_sequential ────────────────────────────────────────────────


class TestCleanupBranchSequential:
    def test_is_noop(self) -> None:
        cleanup_branch_sequential()  # Should not raise


# ── check_disk_space ─────────────────────────────────────────────────────────


class TestCheckDiskSpace:
    @patch("auto_sdd.lib.branch_manager.shutil.disk_usage")
    def test_passes_with_enough_space(
        self, mock_usage: MagicMock, tmp_path: Path
    ) -> None:
        mock_usage.return_value = MagicMock(
            free=10 * 1024 * 1024 * 1024  # 10 GB
        )
        check_disk_space(tmp_path, 5120)  # Should not raise

    @patch("auto_sdd.lib.branch_manager.shutil.disk_usage")
    def test_raises_on_low_space(
        self, mock_usage: MagicMock, tmp_path: Path
    ) -> None:
        mock_usage.return_value = MagicMock(
            free=100 * 1024 * 1024  # 100 MB
        )
        with pytest.raises(InsufficientDiskSpaceError):
            check_disk_space(tmp_path, 5120)

    @patch("auto_sdd.lib.branch_manager.shutil.disk_usage")
    def test_handles_os_error(
        self, mock_usage: MagicMock, tmp_path: Path
    ) -> None:
        mock_usage.side_effect = OSError("cannot stat")
        check_disk_space(tmp_path, 5120)  # Should not raise


# ── cleanup_all_worktrees ────────────────────────────────────────────────────


class TestCleanupAllWorktrees:
    def test_noop_if_no_worktrees_dir(self, tmp_path: Path) -> None:
        cleanup_all_worktrees(tmp_path)  # Should not raise

    @patch("auto_sdd.lib.branch_manager._run_git")
    def test_removes_worktree_dirs(
        self, mock_git: MagicMock, tmp_path: Path
    ) -> None:
        wt_dir = tmp_path / ".build-worktrees"
        wt_dir.mkdir()
        (wt_dir / "wt1").mkdir()
        (wt_dir / "wt2").mkdir()
        mock_git.return_value = MagicMock(returncode=0)
        cleanup_all_worktrees(tmp_path)
        # Should have been called for each worktree
        assert mock_git.call_count >= 2


# ── cleanup_merged_branches ──────────────────────────────────────────────────


class TestCleanupMergedBranches:
    @patch("auto_sdd.lib.branch_manager._run_git")
    def test_no_merged_branches(
        self, mock_git: MagicMock, tmp_path: Path
    ) -> None:
        mock_git.return_value = MagicMock(
            returncode=0, stdout="  main\n  develop\n"
        )
        count = cleanup_merged_branches(tmp_path, "main")
        assert count == 0

    @patch("auto_sdd.lib.branch_manager._run_git")
    def test_deletes_merged_auto_branches(
        self, mock_git: MagicMock, tmp_path: Path
    ) -> None:
        def side_effect(
            args: list[str], *a: object, **kw: object
        ) -> MagicMock:
            if args == ["branch", "--merged"]:
                return MagicMock(
                    returncode=0,
                    stdout="  main\n  auto/chained-20240101\n  auto/independent-20240102\n",
                )
            if args[0] == "branch" and args[1] == "-d":
                return MagicMock(returncode=0)
            return MagicMock(returncode=0)

        mock_git.side_effect = side_effect
        count = cleanup_merged_branches(tmp_path, "main")
        assert count == 2

    @patch("auto_sdd.lib.branch_manager._run_git")
    def test_handles_delete_failure(
        self, mock_git: MagicMock, tmp_path: Path
    ) -> None:
        def side_effect(
            args: list[str], *a: object, **kw: object
        ) -> MagicMock:
            if args == ["branch", "--merged"]:
                return MagicMock(
                    returncode=0,
                    stdout="  auto/chained-20240101\n",
                )
            if args[0] == "branch" and args[1] == "-d":
                return MagicMock(returncode=1, stderr="error")
            return MagicMock(returncode=0)

        mock_git.side_effect = side_effect
        count = cleanup_merged_branches(tmp_path, "main")
        assert count == 0
