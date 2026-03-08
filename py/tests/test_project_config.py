"""Tests for project_config.py — load_project_config and _parse_flat_yaml."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from auto_sdd.lib.project_config import (
    CONFIG_DIR,
    CONFIG_FILENAME,
    _parse_flat_yaml,
    load_project_config,
)


# ── _parse_flat_yaml ──────────────────────────────────────────────────────────


class TestParseFlatYaml:
    def test_basic_key_value(self) -> None:
        result = _parse_flat_yaml("build_cmd: npm run build\n")
        assert result["build_cmd"] == "npm run build"

    def test_strips_comments(self) -> None:
        result = _parse_flat_yaml("# this is a comment\nbuild_cmd: make build\n")
        assert "build_cmd" in result
        assert len(result) == 1

    def test_strips_blank_lines(self) -> None:
        result = _parse_flat_yaml("\n\nbuild_cmd: cargo build\n\n")
        assert result == {"build_cmd": "cargo build"}

    def test_double_quoted_value(self) -> None:
        result = _parse_flat_yaml('test_cmd: "npx vitest run --passWithNoTests"\n')
        assert result["test_cmd"] == "npx vitest run --passWithNoTests"

    def test_single_quoted_value(self) -> None:
        result = _parse_flat_yaml("lint_cmd: 'npm run lint'\n")
        assert result["lint_cmd"] == "npm run lint"

    def test_numeric_value(self) -> None:
        result = _parse_flat_yaml("max_features: 100\n")
        assert result["max_features"] == "100"

    def test_bool_value(self) -> None:
        result = _parse_flat_yaml("auto_approve: true\n")
        assert result["auto_approve"] == "true"

    def test_unknown_keys_preserved(self) -> None:
        result = _parse_flat_yaml("unknown_key: some_value\n")
        assert result["unknown_key"] == "some_value"

    def test_empty_input(self) -> None:
        assert _parse_flat_yaml("") == {}

    def test_multiline(self) -> None:
        yaml = (
            "build_cmd: npm run build\n"
            "test_cmd: npx vitest run\n"
            "max_retries: 2\n"
        )
        result = _parse_flat_yaml(yaml)
        assert result["build_cmd"] == "npm run build"
        assert result["test_cmd"] == "npx vitest run"
        assert result["max_retries"] == "2"


# ── load_project_config ───────────────────────────────────────────────────────


class TestLoadProjectConfig:
    def _write_config(self, tmp_path: Path, content: str) -> None:
        config_dir = tmp_path / CONFIG_DIR
        config_dir.mkdir()
        (config_dir / CONFIG_FILENAME).write_text(content)

    def test_returns_empty_when_no_file(self, tmp_path: Path) -> None:
        result = load_project_config(tmp_path)
        assert result == {}

    def test_sets_env_var_from_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("BUILD_CHECK_CMD", raising=False)
        self._write_config(tmp_path, "build_cmd: npm run build\n")
        load_project_config(tmp_path)
        assert os.environ.get("BUILD_CHECK_CMD") == "npm run build"

    def test_does_not_override_existing_env_var(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("BUILD_CHECK_CMD", "cargo build")
        self._write_config(tmp_path, "build_cmd: npm run build\n")
        load_project_config(tmp_path)
        assert os.environ["BUILD_CHECK_CMD"] == "cargo build"

    def test_unknown_keys_ignored(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._write_config(tmp_path, "totally_unknown_key: value\n")
        # Should not raise and should not pollute environment
        result = load_project_config(tmp_path)
        assert result.get("totally_unknown_key") == "value"

    def test_multiple_keys_set(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("TEST_CHECK_CMD", raising=False)
        monkeypatch.delenv("MAX_FEATURES", raising=False)
        monkeypatch.delenv("AUTO_APPROVE", raising=False)
        self._write_config(
            tmp_path,
            "test_cmd: npx vitest run --passWithNoTests\n"
            "max_features: 100\n"
            "auto_approve: true\n",
        )
        load_project_config(tmp_path)
        assert os.environ.get("TEST_CHECK_CMD") == "npx vitest run --passWithNoTests"
        assert os.environ.get("MAX_FEATURES") == "100"
        assert os.environ.get("AUTO_APPROVE") == "true"

    def test_returns_parsed_dict(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("LINT_CHECK_CMD", raising=False)
        self._write_config(tmp_path, "lint_cmd: npm run lint\n")
        result = load_project_config(tmp_path)
        assert result == {"lint_cmd": "npm run lint"}
