"""Tests for auto_sdd.lib.codebase_summary.

Covers the agent-generated summary pipeline: file tree generation,
caching, agent invocation (mocked), fallback on failure, and learnings
integration.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from auto_sdd.lib.codebase_summary import (
    _FILE_TREE_CAP,
    _generate_file_tree,
    _read_recent_learnings,
    generate_codebase_summary,
)


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def project_with_files(tmp_path: Path) -> Path:
    """Minimal project with a few files in nested dirs."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hi')\n")
    (tmp_path / "src" / "utils.py").write_text("def helper(): pass\n")
    (tmp_path / "README.md").write_text("# Project\n")
    return tmp_path


@pytest.fixture
def project_with_learnings(tmp_path: Path) -> Path:
    """Project with .specs/learnings/ populated."""
    learnings = tmp_path / ".specs" / "learnings"
    learnings.mkdir(parents=True)
    (learnings / "general.md").write_text(
        "# General Learnings\n\n"
        "- Use semantic tokens for colors.\n"
    )
    return tmp_path


# ── File tree generator ─────────────────────────────────────────────────────


class TestFileTreeGenerator:
    """_generate_file_tree: produces correct output, respects exclusions, truncates."""

    def test_produces_file_listing(self, project_with_files: Path) -> None:
        tree = _generate_file_tree(project_with_files)
        assert "src/main.py" in tree
        assert "src/utils.py" in tree
        assert "README.md" in tree

    def test_excludes_node_modules(self, tmp_path: Path) -> None:
        nm = tmp_path / "node_modules" / "pkg"
        nm.mkdir(parents=True)
        (nm / "index.js").write_text("")
        (tmp_path / "app.js").write_text("")
        tree = _generate_file_tree(tmp_path)
        assert "app.js" in tree
        assert "node_modules" not in tree

    def test_excludes_git_dir(self, tmp_path: Path) -> None:
        git = tmp_path / ".git" / "objects"
        git.mkdir(parents=True)
        (git / "abc123").write_text("")
        (tmp_path / "src.py").write_text("")
        tree = _generate_file_tree(tmp_path)
        assert "src.py" in tree
        assert ".git" not in tree

    def test_excludes_pycache(self, tmp_path: Path) -> None:
        cache = tmp_path / "__pycache__"
        cache.mkdir()
        (cache / "mod.cpython-312.pyc").write_text("")
        (tmp_path / "mod.py").write_text("")
        tree = _generate_file_tree(tmp_path)
        assert "mod.py" in tree
        assert "__pycache__" not in tree

    def test_truncates_at_cap(self, tmp_path: Path) -> None:
        for i in range(_FILE_TREE_CAP + 10):
            (tmp_path / f"file_{i:04d}.txt").write_text("")
        tree = _generate_file_tree(tmp_path)
        assert f"truncated at {_FILE_TREE_CAP} files" in tree

    def test_empty_directory(self, tmp_path: Path) -> None:
        tree = _generate_file_tree(tmp_path)
        assert tree == ""


# ── Cache layer ──────────────────────────────────────────────────────────────


class TestCacheLayer:
    """Cache: hit returns cached content, miss triggers agent call."""

    @patch("auto_sdd.lib.codebase_summary._call_agent")
    @patch("auto_sdd.lib.codebase_summary._get_tree_hash")
    def test_cache_hit_skips_agent(
        self,
        mock_hash: MagicMock,
        mock_agent: MagicMock,
        project_with_files: Path,
    ) -> None:
        tree_hash = "abc123def456"
        mock_hash.return_value = tree_hash

        # Pre-populate cache
        cache_dir = project_with_files / ".auto-sdd-cache"
        cache_dir.mkdir()
        cache_file = cache_dir / f"codebase-summary-{tree_hash}.md"
        cache_file.write_text("cached summary content")

        result = generate_codebase_summary(project_with_files)
        assert "cached summary content" in result
        mock_agent.assert_not_called()

    @patch("auto_sdd.lib.codebase_summary._call_agent")
    @patch("auto_sdd.lib.codebase_summary._get_tree_hash")
    def test_cache_miss_calls_agent(
        self,
        mock_hash: MagicMock,
        mock_agent: MagicMock,
        project_with_files: Path,
    ) -> None:
        mock_hash.return_value = "abc123"
        mock_agent.return_value = "agent generated summary"

        result = generate_codebase_summary(project_with_files)
        assert "agent generated summary" in result
        mock_agent.assert_called_once()

    @patch("auto_sdd.lib.codebase_summary._call_agent")
    @patch("auto_sdd.lib.codebase_summary._get_tree_hash")
    def test_cache_written_after_agent_call(
        self,
        mock_hash: MagicMock,
        mock_agent: MagicMock,
        project_with_files: Path,
    ) -> None:
        tree_hash = "newhash789"
        mock_hash.return_value = tree_hash
        mock_agent.return_value = "fresh summary"

        generate_codebase_summary(project_with_files)
        cached_file = project_with_files / ".auto-sdd-cache" / f"codebase-summary-{tree_hash}.md"
        assert cached_file.exists()
        assert cached_file.read_text() == "fresh summary"

    @patch("auto_sdd.lib.codebase_summary._call_agent")
    @patch("auto_sdd.lib.codebase_summary._get_tree_hash")
    def test_cache_gitignore_created(
        self,
        mock_hash: MagicMock,
        mock_agent: MagicMock,
        project_with_files: Path,
    ) -> None:
        mock_hash.return_value = "somehash"
        mock_agent.return_value = "content"

        generate_codebase_summary(project_with_files)
        gitignore = project_with_files / ".auto-sdd-cache" / ".gitignore"
        assert gitignore.exists()
        assert gitignore.read_text() == "*\n"


# ── Cache key changes with tree hash ────────────────────────────────────────


class TestCacheKeyChanges:
    """Cache key changes when tree hash changes."""

    @patch("auto_sdd.lib.codebase_summary._call_agent")
    @patch("auto_sdd.lib.codebase_summary._get_tree_hash")
    def test_different_hash_triggers_new_agent_call(
        self,
        mock_hash: MagicMock,
        mock_agent: MagicMock,
        project_with_files: Path,
    ) -> None:
        # Pre-populate cache with old hash
        cache_dir = project_with_files / ".auto-sdd-cache"
        cache_dir.mkdir()
        (cache_dir / "codebase-summary-oldhash.md").write_text("old summary")

        # Return a different hash
        mock_hash.return_value = "newhash"
        mock_agent.return_value = "new summary"

        result = generate_codebase_summary(project_with_files)
        assert "new summary" in result
        mock_agent.assert_called_once()


# ── Agent call ───────────────────────────────────────────────────────────────


class TestAgentCall:
    """Agent call: verify prompt structure and output returned."""

    @patch("auto_sdd.lib.codebase_summary._get_tree_hash")
    @patch("auto_sdd.lib.codebase_summary.run_claude", create=True)
    def test_prompt_contains_file_tree(
        self,
        mock_run_claude: MagicMock,
        mock_hash: MagicMock,
        project_with_files: Path,
    ) -> None:
        mock_hash.return_value = None  # skip cache

        mock_result = MagicMock()
        mock_result.output = "agent output"
        mock_run_claude.return_value = mock_result

        with patch("auto_sdd.lib.codebase_summary._call_agent") as mock_call:
            mock_call.return_value = "agent output"
            result = generate_codebase_summary(project_with_files)
            assert result == "agent output"

    @patch("auto_sdd.lib.codebase_summary._get_tree_hash")
    def test_call_agent_uses_run_claude(
        self,
        mock_hash: MagicMock,
        project_with_files: Path,
    ) -> None:
        mock_hash.return_value = None

        mock_result = MagicMock()
        mock_result.output = "structured summary"

        with patch("auto_sdd.lib.claude_wrapper.run_claude", return_value=mock_result):
            from auto_sdd.lib.codebase_summary import _call_agent
            output = _call_agent(project_with_files, "file_tree_text")
            assert output == "structured summary"

    @patch("auto_sdd.lib.codebase_summary._get_tree_hash")
    def test_agent_prompt_structure(
        self,
        mock_hash: MagicMock,
        project_with_files: Path,
    ) -> None:
        """Verify the prompt sent to run_claude contains expected structure."""
        mock_hash.return_value = None

        mock_result = MagicMock()
        mock_result.output = "result"

        with patch("auto_sdd.lib.claude_wrapper.run_claude", return_value=mock_result) as mock_rc:
            from auto_sdd.lib.codebase_summary import _call_agent
            _call_agent(project_with_files, "src/main.py\nsrc/utils.py")

            args_list = mock_rc.call_args[0][0]
            assert args_list[0] == "-p"
            assert args_list[1] == "--dangerously-skip-permissions"
            prompt = args_list[2]
            assert "src/main.py" in prompt
            assert "Key modules" in prompt
            assert "100 lines" in prompt


# ── Fallback on failure ─────────────────────────────────────────────────────


class TestFallback:
    """Fallback: agent failure returns empty string, no crash."""

    @patch("auto_sdd.lib.codebase_summary._call_agent")
    @patch("auto_sdd.lib.codebase_summary._get_tree_hash")
    def test_agent_exception_returns_empty(
        self,
        mock_hash: MagicMock,
        mock_agent: MagicMock,
        project_with_files: Path,
    ) -> None:
        mock_hash.return_value = "somehash"
        mock_agent.side_effect = RuntimeError("agent exploded")

        result = generate_codebase_summary(project_with_files)
        assert result == ""

    @patch("auto_sdd.lib.codebase_summary._call_agent")
    @patch("auto_sdd.lib.codebase_summary._get_tree_hash")
    def test_timeout_returns_empty(
        self,
        mock_hash: MagicMock,
        mock_agent: MagicMock,
        project_with_files: Path,
    ) -> None:
        mock_hash.return_value = "somehash"
        mock_agent.side_effect = TimeoutError("timed out")

        result = generate_codebase_summary(project_with_files)
        assert result == ""

    @patch("auto_sdd.lib.codebase_summary._call_agent")
    @patch("auto_sdd.lib.codebase_summary._get_tree_hash")
    def test_no_tree_hash_still_works(
        self,
        mock_hash: MagicMock,
        mock_agent: MagicMock,
        project_with_files: Path,
    ) -> None:
        """When git tree hash is None (not a git repo), agent is still called."""
        mock_hash.return_value = None
        mock_agent.return_value = "summary without cache"

        result = generate_codebase_summary(project_with_files)
        assert "summary without cache" in result
        mock_agent.assert_called_once()


# ── Learnings integration ────────────────────────────────────────────────────


class TestLearningsIntegration:
    """Learnings are appended to agent-generated summary."""

    @patch("auto_sdd.lib.codebase_summary._call_agent")
    @patch("auto_sdd.lib.codebase_summary._get_tree_hash")
    def test_learnings_appended_to_agent_summary(
        self,
        mock_hash: MagicMock,
        mock_agent: MagicMock,
        project_with_learnings: Path,
    ) -> None:
        mock_hash.return_value = "hash1"
        mock_agent.return_value = "agent summary"

        result = generate_codebase_summary(project_with_learnings)
        assert "agent summary" in result
        assert "## Recent Learnings" in result
        assert "semantic tokens" in result

    def test_read_recent_learnings_with_content(
        self, project_with_learnings: Path
    ) -> None:
        text = _read_recent_learnings(project_with_learnings)
        assert "## Recent Learnings" in text
        assert "semantic tokens" in text

    def test_read_recent_learnings_empty_dir(self, tmp_path: Path) -> None:
        text = _read_recent_learnings(tmp_path)
        assert text == ""

    def test_read_recent_learnings_empty_files(self, tmp_path: Path) -> None:
        learnings = tmp_path / ".specs" / "learnings"
        learnings.mkdir(parents=True)
        (learnings / "empty.md").write_text("")
        text = _read_recent_learnings(tmp_path)
        assert text == ""

    def test_read_recent_learnings_truncation(self, tmp_path: Path) -> None:
        learnings = tmp_path / ".specs" / "learnings"
        learnings.mkdir(parents=True)
        # Write enough lines to trigger truncation (cap is 40)
        content = "\n".join(f"line {i}" for i in range(60))
        (learnings / "big.md").write_text(content)
        text = _read_recent_learnings(tmp_path)
        assert "truncated at 40 lines" in text

    @patch("auto_sdd.lib.codebase_summary._call_agent")
    @patch("auto_sdd.lib.codebase_summary._get_tree_hash")
    def test_learnings_appended_to_cached_summary(
        self,
        mock_hash: MagicMock,
        mock_agent: MagicMock,
        project_with_learnings: Path,
    ) -> None:
        tree_hash = "cachehash"
        mock_hash.return_value = tree_hash

        # Pre-populate cache
        cache_dir = project_with_learnings / ".auto-sdd-cache"
        cache_dir.mkdir()
        (cache_dir / f"codebase-summary-{tree_hash}.md").write_text(
            "cached agent output"
        )

        result = generate_codebase_summary(project_with_learnings)
        assert "cached agent output" in result
        assert "## Recent Learnings" in result
        mock_agent.assert_not_called()


# ── Error handling ───────────────────────────────────────────────────────────


class TestErrorHandling:
    """Error handling for invalid inputs."""

    def test_raises_on_nonexistent_directory(self, tmp_path: Path) -> None:
        nonexistent = tmp_path / "does_not_exist"
        with pytest.raises(ValueError, match="does not exist"):
            generate_codebase_summary(nonexistent)

    def test_raises_on_file_not_directory(self, tmp_path: Path) -> None:
        a_file = tmp_path / "not_a_dir.txt"
        a_file.write_text("hello")
        with pytest.raises(ValueError, match="not a directory"):
            generate_codebase_summary(a_file)


# ── End-to-end integration ───────────────────────────────────────────────────


class TestEndToEnd:
    """Integration: generate_codebase_summary end-to-end with mocked agent."""

    @patch("auto_sdd.lib.codebase_summary._call_agent")
    @patch("auto_sdd.lib.codebase_summary._get_tree_hash")
    def test_full_flow(
        self,
        mock_hash: MagicMock,
        mock_agent: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Full flow: files + learnings + agent call → combined output."""
        # Set up project files
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.py").write_text("print('app')\n")

        # Set up learnings
        learnings = tmp_path / ".specs" / "learnings"
        learnings.mkdir(parents=True)
        (learnings / "general.md").write_text("# Learnings\n\n- Key insight\n")

        mock_hash.return_value = "e2ehash"
        mock_agent.return_value = "## Summary\n\n- app.py is the entry point\n"

        result = generate_codebase_summary(tmp_path)

        # Agent output present
        assert "## Summary" in result
        assert "app.py is the entry point" in result

        # Learnings appended
        assert "## Recent Learnings" in result
        assert "Key insight" in result

        # Cache was written
        cache_file = tmp_path / ".auto-sdd-cache" / "codebase-summary-e2ehash.md"
        assert cache_file.exists()

    @patch("auto_sdd.lib.codebase_summary._call_agent")
    @patch("auto_sdd.lib.codebase_summary._get_tree_hash")
    def test_empty_project_with_agent_failure(
        self,
        mock_hash: MagicMock,
        mock_agent: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Empty project + agent failure → empty string."""
        mock_hash.return_value = None
        mock_agent.side_effect = FileNotFoundError("claude not found")

        result = generate_codebase_summary(tmp_path)
        assert result == ""
