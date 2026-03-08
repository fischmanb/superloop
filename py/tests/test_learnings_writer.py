"""Tests for learnings_writer module."""
from __future__ import annotations

from pathlib import Path
import pytest
from auto_sdd.lib.learnings_writer import write_learning, _default_repo_dir


class TestDefaultRepoDir:
    def test_returns_path(self) -> None:
        result = _default_repo_dir()
        assert isinstance(result, Path)

    def test_contains_learnings_dir_or_py(self) -> None:
        result = _default_repo_dir()
        # The repo root should contain the py/ directory
        assert (result / "py").is_dir() or result.name == "auto-sdd"


class TestWriteLearning:
    def test_writes_project_local(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()
        write_learning(
            summary="test finding",
            detail="some detail here",
            category="drift",
            project_name="my-project",
            feature_name="F-001",
            project_dir=project_dir,
            repo_dir=tmp_path / "repo",
        )
        local_file = project_dir / ".specs" / "learnings" / "general.md"
        assert local_file.exists()
        content = local_file.read_text()
        assert "test finding" in content
        assert "some detail here" in content
        assert "drift" in content

    def test_writes_repo_level_pending(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / "repo"
        write_learning(
            summary="repo finding",
            detail="repo detail",
            category="retry",
            project_name="my-project",
            feature_name="F-002",
            repo_dir=repo_dir,
        )
        pending_file = repo_dir / "learnings" / "pending.md"
        assert pending_file.exists()
        content = pending_file.read_text()
        assert "repo finding" in content
        assert "RETRY" in content
        assert "my-project" in content
        assert "F-002" in content

    def test_appends_on_multiple_calls(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / "repo"
        for i in range(3):
            write_learning(
                summary=f"finding {i}",
                detail=f"detail {i}",
                category="drift",
                project_name="proj",
                repo_dir=repo_dir,
            )
        content = (repo_dir / "learnings" / "pending.md").read_text()
        assert "finding 0" in content
        assert "finding 1" in content
        assert "finding 2" in content

    def test_no_project_dir_skips_local(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / "repo"
        # Should not raise even with no project_dir
        write_learning(
            summary="no local",
            detail="detail",
            category="retry",
            project_name="proj",
            project_dir=None,
            repo_dir=repo_dir,
        )
        pending_file = repo_dir / "learnings" / "pending.md"
        assert pending_file.exists()

    def test_no_repo_dir_uses_default(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        # Should not raise (writes to actual repo learnings/pending.md)
        # We just check it doesn't crash; don't assert file location
        write_learning(
            summary="default repo",
            detail="detail",
            category="drift",
            project_name="proj",
            project_dir=project_dir,
            repo_dir=None,
        )

    def test_os_error_does_not_raise(self, tmp_path: Path) -> None:
        # Write to a path that can't be created (file where dir should be)
        blocker = tmp_path / "blocked"
        blocker.write_text("I am a file, not a directory")
        # repo_dir points to the file — mkdir will fail
        write_learning(
            summary="should not raise",
            detail="detail",
            category="drift",
            project_name="proj",
            repo_dir=blocker,
        )
