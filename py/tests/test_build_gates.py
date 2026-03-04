"""Tests for auto_sdd.lib.build_gates."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from auto_sdd.lib.build_gates import (
    BuildCheckResult,
    DeadExportResult,
    agent_cmd,
    check_build,
    check_dead_exports,
    check_lint,
    check_tests,
    check_working_tree_clean,
    clean_working_tree,
    detect_build_check,
    detect_lint_check,
    detect_test_check,
    run_cmd_safe,
    should_run_step,
)


# ── detect_build_check ──────────────────────────────────────────────────────


class TestDetectBuildCheck:
    def test_override_returns_override(self, tmp_path: Path) -> None:
        assert detect_build_check(tmp_path, "my-build-cmd") == "my-build-cmd"

    def test_override_skip_returns_empty(self, tmp_path: Path) -> None:
        assert detect_build_check(tmp_path, "skip") == ""

    def test_tsconfig_build_json(self, tmp_path: Path) -> None:
        (tmp_path / "tsconfig.build.json").touch()
        result = detect_build_check(tmp_path)
        assert "tsconfig.build.json" in result

    def test_tsconfig_json(self, tmp_path: Path) -> None:
        (tmp_path / "tsconfig.json").touch()
        result = detect_build_check(tmp_path)
        assert "tsc --noEmit" in result

    def test_pyproject_toml(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").touch()
        (tmp_path / "app.py").write_text("print('hello')")
        result = detect_build_check(tmp_path)
        assert "py_compile" in result

    def test_cargo_toml(self, tmp_path: Path) -> None:
        (tmp_path / "Cargo.toml").touch()
        assert detect_build_check(tmp_path) == "cargo check"

    def test_go_mod(self, tmp_path: Path) -> None:
        (tmp_path / "go.mod").touch()
        assert detect_build_check(tmp_path) == "go build ./..."

    def test_package_json_with_build(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text('{"scripts": {"build": "next build"}}')
        assert detect_build_check(tmp_path) == "npm run build"

    def test_no_detection(self, tmp_path: Path) -> None:
        assert detect_build_check(tmp_path) == ""

    def test_nextjs_config_js(self, tmp_path: Path) -> None:
        (tmp_path / "next.config.js").touch()
        (tmp_path / "tsconfig.json").touch()
        (tmp_path / "package.json").write_text('{"scripts": {"build": "next build"}}')
        assert detect_build_check(tmp_path) == "npm run build"

    def test_nextjs_config_mjs(self, tmp_path: Path) -> None:
        (tmp_path / "next.config.mjs").touch()
        (tmp_path / "package.json").write_text('{"scripts": {"build": "next build"}}')
        assert detect_build_check(tmp_path) == "npm run build"

    def test_nextjs_config_ts(self, tmp_path: Path) -> None:
        (tmp_path / "next.config.ts").touch()
        (tmp_path / "package.json").write_text('{"scripts": {"build": "next build"}}')
        assert detect_build_check(tmp_path) == "npm run build"

    def test_nextjs_beats_tsconfig(self, tmp_path: Path) -> None:
        """Next.js detection takes priority over generic tsconfig."""
        (tmp_path / "next.config.js").touch()
        (tmp_path / "tsconfig.json").touch()
        (tmp_path / "tsconfig.build.json").touch()
        (tmp_path / "package.json").write_text('{"scripts": {"build": "next build"}}')
        result = detect_build_check(tmp_path)
        assert result == "npm run build"
        assert "tsc" not in result

    def test_nextjs_without_build_script_falls_through(self, tmp_path: Path) -> None:
        """Next.js config present but no build script → falls to tsconfig."""
        (tmp_path / "next.config.js").touch()
        (tmp_path / "tsconfig.json").touch()
        (tmp_path / "package.json").write_text('{"scripts": {"dev": "next dev"}}')
        result = detect_build_check(tmp_path)
        assert "tsc --noEmit" in result


# ── detect_test_check ────────────────────────────────────────────────────────


class TestDetectTestCheck:
    def test_override_returns_override(self, tmp_path: Path) -> None:
        assert detect_test_check(tmp_path, "my-test-cmd") == "my-test-cmd"

    def test_override_skip_returns_empty(self, tmp_path: Path) -> None:
        assert detect_test_check(tmp_path, "skip") == ""

    def test_package_json_with_test(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text('{"scripts": {"test": "jest"}}')
        assert detect_test_check(tmp_path) == "npm test"

    def test_package_json_no_test_specified(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text(
            '{"scripts": {"test": "no test specified"}}'
        )
        assert detect_test_check(tmp_path) == ""

    def test_pytest_ini(self, tmp_path: Path) -> None:
        (tmp_path / "pytest.ini").touch()
        assert detect_test_check(tmp_path) == "pytest"

    def test_cargo_toml(self, tmp_path: Path) -> None:
        (tmp_path / "Cargo.toml").touch()
        assert detect_test_check(tmp_path) == "cargo test"

    def test_no_detection(self, tmp_path: Path) -> None:
        assert detect_test_check(tmp_path) == ""


# ── detect_lint_check ────────────────────────────────────────────────────────


class TestDetectLintCheck:
    def test_eslintrc_js(self, tmp_path: Path) -> None:
        (tmp_path / ".eslintrc.js").touch()
        assert "eslint" in detect_lint_check(tmp_path)

    def test_eslint_flat_config(self, tmp_path: Path) -> None:
        (tmp_path / "eslint.config.js").touch()
        assert "eslint" in detect_lint_check(tmp_path)

    def test_biome(self, tmp_path: Path) -> None:
        (tmp_path / "biome.json").touch()
        assert "biome" in detect_lint_check(tmp_path)

    def test_ruff_toml(self, tmp_path: Path) -> None:
        (tmp_path / "ruff.toml").touch()
        assert detect_lint_check(tmp_path) == "ruff check ."

    def test_cargo_clippy(self, tmp_path: Path) -> None:
        (tmp_path / "Cargo.toml").touch()
        assert "clippy" in detect_lint_check(tmp_path)

    def test_no_detection(self, tmp_path: Path) -> None:
        assert detect_lint_check(tmp_path) == ""


# ── check_build ──────────────────────────────────────────────────────────────


class TestCheckBuild:
    def test_empty_cmd_skips(self, tmp_path: Path) -> None:
        result = check_build("", tmp_path)
        assert result.success is True
        assert result.output == ""

    @patch("auto_sdd.lib.build_gates.run_cmd_safe")
    def test_successful_build(
        self, mock_run: object, tmp_path: Path
    ) -> None:
        from unittest.mock import MagicMock
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "ok"
        mock_proc.stderr = ""
        assert isinstance(mock_run, MagicMock)
        mock_run.return_value = mock_proc

        result = check_build("make build", tmp_path)
        assert result.success is True

    @patch("auto_sdd.lib.build_gates.run_cmd_safe")
    def test_failed_build(
        self, mock_run: object, tmp_path: Path
    ) -> None:
        from unittest.mock import MagicMock
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stdout = "error: type mismatch"
        mock_proc.stderr = ""
        assert isinstance(mock_run, MagicMock)
        mock_run.return_value = mock_proc

        result = check_build("make build", tmp_path)
        assert result.success is False
        assert "type mismatch" in result.output


# ── check_tests ──────────────────────────────────────────────────────────────


class TestCheckTests:
    def test_empty_cmd_skips(self, tmp_path: Path) -> None:
        result = check_tests("", tmp_path)
        assert result.success is True
        assert result.test_count is None

    @patch("auto_sdd.lib.build_gates.run_cmd_safe")
    def test_parses_test_count(
        self, mock_run: object, tmp_path: Path
    ) -> None:
        from unittest.mock import MagicMock
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "Tests 42 passed, 0 failed"
        mock_proc.stderr = ""
        assert isinstance(mock_run, MagicMock)
        mock_run.return_value = mock_proc

        result = check_tests("npm test", tmp_path)
        assert result.success is True
        assert result.test_count == 42

    @patch("auto_sdd.lib.build_gates.run_cmd_safe")
    def test_parses_pytest_count(
        self, mock_run: object, tmp_path: Path
    ) -> None:
        from unittest.mock import MagicMock
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "===== 15 passed in 3.2s ====="
        mock_proc.stderr = ""
        assert isinstance(mock_run, MagicMock)
        mock_run.return_value = mock_proc

        result = check_tests("pytest", tmp_path)
        assert result.success is True
        assert result.test_count == 15

    @patch("auto_sdd.lib.build_gates.run_cmd_safe")
    def test_failed_tests(
        self, mock_run: object, tmp_path: Path
    ) -> None:
        from unittest.mock import MagicMock
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stdout = "FAILED test_foo"
        mock_proc.stderr = ""
        assert isinstance(mock_run, MagicMock)
        mock_run.return_value = mock_proc

        result = check_tests("pytest", tmp_path)
        assert result.success is False


# ── check_dead_exports ───────────────────────────────────────────────────────


class TestCheckDeadExports:
    def test_no_source_files(self, tmp_path: Path) -> None:
        result = check_dead_exports(tmp_path)
        assert result.count == 0
        assert result.dead_exports == []

    def test_finds_dead_export(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.ts").write_text("export function unusedFn() { return 1; }")
        (src / "b.ts").write_text("export function usedFn() { return 2; }")
        result = check_dead_exports(tmp_path)
        # Both are "dead" since neither references the other
        assert result.count >= 1

    def test_used_export_not_flagged(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.ts").write_text("export function sharedFn() { return 1; }")
        (src / "b.ts").write_text("import { sharedFn } from './a';\nsharedFn();")
        result = check_dead_exports(tmp_path)
        dead_syms = [e.split(": ")[1] for e in result.dead_exports if ": " in e]
        assert "sharedFn" not in dead_syms

    def test_go_exported_symbol_detected(self, tmp_path: Path) -> None:
        """Go uppercase-initial func/type is detected as an export."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "handler.go").write_text(
            "package handlers\n\n"
            "func HandleRequest() {}\n"
            "type Config struct {}\n"
        )
        (src / "other.go").write_text("package handlers\n\nfunc init() {}\n")
        result = check_dead_exports(tmp_path)
        dead_syms = [e.split(": ")[1] for e in result.dead_exports if ": " in e]
        assert "HandleRequest" in dead_syms
        assert "Config" in dead_syms

    def test_go_unexported_symbol_not_flagged(self, tmp_path: Path) -> None:
        """Go lowercase-initial symbols are not exports and should not appear."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "internal.go").write_text(
            "package internal\n\n"
            "func helperFunc() {}\n"
            "type config struct {}\n"
        )
        (src / "other.go").write_text("package internal\n")
        result = check_dead_exports(tmp_path)
        dead_syms = [e.split(": ")[1] for e in result.dead_exports if ": " in e]
        assert "helperFunc" not in dead_syms
        assert "config" not in dead_syms

    def test_go_used_export_not_flagged(self, tmp_path: Path) -> None:
        """Go exported symbol referenced in another file is not dead."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "types.go").write_text(
            "package models\n\ntype UserModel struct { Name string }\n"
        )
        (src / "service.go").write_text(
            "package models\n\nvar u UserModel\n"
        )
        result = check_dead_exports(tmp_path)
        dead_syms = [e.split(": ")[1] for e in result.dead_exports if ": " in e]
        assert "UserModel" not in dead_syms


# ── should_run_step ──────────────────────────────────────────────────────────


class TestShouldRunStep:
    def test_step_present(self) -> None:
        assert should_run_step("test", "build,test,lint") is True

    def test_step_absent(self) -> None:
        assert should_run_step("review", "build,test,lint") is False

    def test_empty_steps(self) -> None:
        assert should_run_step("test", "") is False


# ── check_working_tree_clean ─────────────────────────────────────────────────


class TestCheckWorkingTreeClean:
    @patch("auto_sdd.lib.build_gates.subprocess.run")
    def test_clean_tree(self, mock_run: object) -> None:
        from unittest.mock import MagicMock
        assert isinstance(mock_run, MagicMock)
        mock_run.return_value = MagicMock(stdout="?? untracked.txt\n", returncode=0)
        assert check_working_tree_clean(Path("/fake")) is True

    @patch("auto_sdd.lib.build_gates.subprocess.run")
    def test_dirty_tree(self, mock_run: object) -> None:
        from unittest.mock import MagicMock
        assert isinstance(mock_run, MagicMock)
        mock_run.return_value = MagicMock(stdout=" M file.py\n", returncode=0)
        assert check_working_tree_clean(Path("/fake")) is False

    @patch("auto_sdd.lib.build_gates.subprocess.run")
    def test_check_working_tree_clean_warns_on_untracked(
        self, mock_run: object, caplog: pytest.LogCaptureFixture
    ) -> None:
        from unittest.mock import MagicMock
        assert isinstance(mock_run, MagicMock)
        mock_run.return_value = MagicMock(
            stdout="?? leftover.txt\n?? debug.log\n", returncode=0
        )
        import logging
        with caplog.at_level(logging.WARNING, logger="auto_sdd.lib.build_gates"):
            result = check_working_tree_clean(Path("/fake"))
        assert result is True
        assert "2 untracked file(s)" in caplog.text
        assert "leftover.txt" in caplog.text

    @patch("auto_sdd.lib.build_gates.subprocess.run")
    def test_check_working_tree_clean_no_warning_when_no_untracked(
        self, mock_run: object, caplog: pytest.LogCaptureFixture
    ) -> None:
        from unittest.mock import MagicMock
        assert isinstance(mock_run, MagicMock)
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        import logging
        with caplog.at_level(logging.WARNING, logger="auto_sdd.lib.build_gates"):
            result = check_working_tree_clean(Path("/fake"))
        assert result is True
        assert "untracked" not in caplog.text


# ── agent_cmd ────────────────────────────────────────────────────────────────


class TestAgentCmd:
    def test_default(self) -> None:
        cmd = agent_cmd()
        assert cmd == ["claude", "-p", "--dangerously-skip-permissions"]

    def test_with_model(self) -> None:
        cmd = agent_cmd("opus")
        assert "--model" in cmd
        assert "opus" in cmd


# ── run_cmd_safe ─────────────────────────────────────────────────────────────


class TestRunCmdSafe:
    def test_runs_command(self, tmp_path: Path) -> None:
        result = run_cmd_safe("echo hello", tmp_path)
        assert result.returncode == 0
        assert "hello" in result.stdout

    @patch("auto_sdd.lib.build_gates.subprocess.run")
    def test_uses_sh_not_bash(self, mock_run: object, tmp_path: Path) -> None:
        from unittest.mock import MagicMock
        assert isinstance(mock_run, MagicMock)
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        run_cmd_safe("echo test", tmp_path)
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "sh", f"Expected 'sh' but got '{call_args[0]}'"
        assert call_args[1] == "-c"
