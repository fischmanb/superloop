"""Tests for auto_sdd.scripts.post_campaign_validation.

Unit tests for infrastructure — no live servers needed.
"""
from __future__ import annotations

import atexit
import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from auto_sdd.scripts.post_campaign_validation import (
    DocumentRegistry,
    ValidationPipeline,
    ValidationState,
    _find_seed_script,
    detect_dev_command,
    detect_package_manager,
    health_check,
    parse_port_from_output,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()  # type: ignore[misc,unused-ignore,untyped-decorator]
def tmp_project(tmp_path: Path) -> Path:
    """Create a minimal project directory."""
    project = tmp_path / "project"
    project.mkdir()
    (project / ".sdd-state").mkdir()
    return project


@pytest.fixture()  # type: ignore[misc,unused-ignore,untyped-decorator]
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove env vars that could interfere."""
    for var in ["PROJECT_DIR", "FLUSH_MODE", "VALIDATION_TIMEOUT"]:
        monkeypatch.delenv(var, raising=False)


# ── test_package_manager_detection ───────────────────────────────────────────


class TestPackageManagerDetection:
    def test_pnpm_detected(self, tmp_path: Path) -> None:
        (tmp_path / "pnpm-lock.yaml").touch()
        assert detect_package_manager(tmp_path) == "pnpm"

    def test_yarn_detected(self, tmp_path: Path) -> None:
        (tmp_path / "yarn.lock").touch()
        assert detect_package_manager(tmp_path) == "yarn"

    def test_npm_detected(self, tmp_path: Path) -> None:
        (tmp_path / "package-lock.json").touch()
        assert detect_package_manager(tmp_path) == "npm"

    def test_fallback_to_npm(self, tmp_path: Path) -> None:
        # No lock files at all
        assert detect_package_manager(tmp_path) == "npm"

    def test_pnpm_takes_priority(self, tmp_path: Path) -> None:
        """If multiple lock files exist, pnpm wins."""
        (tmp_path / "pnpm-lock.yaml").touch()
        (tmp_path / "yarn.lock").touch()
        (tmp_path / "package-lock.json").touch()
        assert detect_package_manager(tmp_path) == "pnpm"

    def test_yarn_over_npm(self, tmp_path: Path) -> None:
        (tmp_path / "yarn.lock").touch()
        (tmp_path / "package-lock.json").touch()
        assert detect_package_manager(tmp_path) == "yarn"


# ── test_dev_command_detection ───────────────────────────────────────────────


class TestDevCommandDetection:
    def test_dev_script(self, tmp_path: Path) -> None:
        pkg = {"scripts": {"dev": "next dev", "build": "next build"}}
        (tmp_path / "package.json").write_text(json.dumps(pkg))
        assert detect_dev_command(tmp_path) == "dev"

    def test_start_script(self, tmp_path: Path) -> None:
        pkg = {"scripts": {"start": "react-scripts start", "build": "react-scripts build"}}
        (tmp_path / "package.json").write_text(json.dumps(pkg))
        assert detect_dev_command(tmp_path) == "start"

    def test_serve_script(self, tmp_path: Path) -> None:
        pkg = {"scripts": {"serve": "vite preview"}}
        (tmp_path / "package.json").write_text(json.dumps(pkg))
        assert detect_dev_command(tmp_path) == "serve"

    def test_dev_has_priority(self, tmp_path: Path) -> None:
        pkg = {"scripts": {"serve": "x", "start": "y", "dev": "z"}}
        (tmp_path / "package.json").write_text(json.dumps(pkg))
        assert detect_dev_command(tmp_path) == "dev"

    def test_no_matching_scripts(self, tmp_path: Path) -> None:
        pkg = {"scripts": {"build": "tsc", "lint": "eslint"}}
        (tmp_path / "package.json").write_text(json.dumps(pkg))
        assert detect_dev_command(tmp_path) is None

    def test_no_package_json(self, tmp_path: Path) -> None:
        assert detect_dev_command(tmp_path) is None

    def test_invalid_package_json(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text("not json!")
        assert detect_dev_command(tmp_path) is None


# ── test_port_detection_from_output ──────────────────────────────────────────


class TestPortDetectionFromOutput:
    def test_localhost_colon_port(self) -> None:
        output = "  > Local: http://localhost:3000\n"
        assert parse_port_from_output(output) == 3000

    def test_127_0_0_1_port(self) -> None:
        output = "Server running at 127.0.0.1:5173"
        assert parse_port_from_output(output) == 5173

    def test_0_0_0_0_port(self) -> None:
        output = "Listening on 0.0.0.0:8080"
        assert parse_port_from_output(output) == 8080

    def test_port_keyword(self) -> None:
        output = "Started on port 4200"
        assert parse_port_from_output(output) == 4200

    def test_url_with_port(self) -> None:
        output = "Ready at http://myhost:9090/api"
        assert parse_port_from_output(output) == 9090

    def test_no_port_found(self) -> None:
        output = "Server started successfully\nNo port info here"
        assert parse_port_from_output(output) is None

    def test_vite_output(self) -> None:
        output = (
            "  VITE v5.0.0  ready in 450 ms\n"
            "\n"
            "  ➜  Local:   http://localhost:5173/\n"
        )
        assert parse_port_from_output(output) == 5173


# ── test_health_check_success ────────────────────────────────────────────────


class TestHealthCheck:
    @patch("auto_sdd.scripts.post_campaign_validation.urllib.request.urlopen")
    def test_success_on_first_try(self, mock_urlopen: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        assert health_check("http://localhost:3000", timeout=5.0) is True

    @patch("auto_sdd.scripts.post_campaign_validation.urllib.request.urlopen")
    def test_success_after_retry(self, mock_urlopen: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        # Fail twice, succeed on third
        mock_urlopen.side_effect = [
            ConnectionRefusedError("refused"),
            ConnectionRefusedError("refused"),
            mock_resp,
        ]

        result = health_check(
            "http://localhost:3000",
            timeout=30.0,
            initial_backoff=0.01,
        )
        assert result is True

    @patch("auto_sdd.scripts.post_campaign_validation.urllib.request.urlopen")
    def test_timeout(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.side_effect = ConnectionRefusedError("refused")

        result = health_check(
            "http://localhost:3000",
            timeout=0.1,
            initial_backoff=0.01,
        )
        assert result is False


# ── test_state_persistence_roundtrip ─────────────────────────────────────────


class TestStatePersistence:
    def test_roundtrip(self, tmp_path: Path) -> None:
        state_path = tmp_path / "validation-state.json"
        run_id = "val-test-001"

        state = ValidationState(state_path, run_id)
        state.mark_complete("0")
        state.mark_complete("1")

        # Read it back
        state2 = ValidationState(state_path, run_id)
        assert state2.completed_phases == ["0", "1"]
        assert "0" in state2.phase_timestamps
        assert "1" in state2.phase_timestamps

    def test_different_run_id_ignores_stale_state(self, tmp_path: Path) -> None:
        state_path = tmp_path / "validation-state.json"

        state = ValidationState(state_path, "val-old-run")
        state.mark_complete("0")

        # New run ID should not see old state
        state2 = ValidationState(state_path, "val-new-run")
        assert state2.completed_phases == []

    def test_missing_file(self, tmp_path: Path) -> None:
        state_path = tmp_path / "nonexistent.json"
        state = ValidationState(state_path, "val-test")
        assert state.completed_phases == []


# ── test_document_registry_versioning ────────────────────────────────────────


class TestDocumentRegistryVersioning:
    def test_first_registration(self, tmp_path: Path) -> None:
        reg_path = tmp_path / "docs.json"
        reg = DocumentRegistry(reg_path, "val-test", "auto")

        doc_path = tmp_path / "phase-0" / "report.v1.json"
        entry = reg.register("runtime-report", "0", doc_path, '{"status":"ok"}')

        assert entry["version"] == 1
        assert entry["status"] == "final"
        assert doc_path.exists()

    def test_version_increments(self, tmp_path: Path) -> None:
        reg_path = tmp_path / "docs.json"
        reg = DocumentRegistry(reg_path, "val-test", "auto")

        path1 = tmp_path / "phase-0" / "report.v1.json"
        e1 = reg.register("runtime-report", "0", path1, '{"v":1}')
        assert e1["version"] == 1

        path2 = tmp_path / "phase-0" / "report.v2.json"
        e2 = reg.register("runtime-report", "0", path2, '{"v":2}')
        assert e2["version"] == 2
        assert e2.get("supersedes") == "runtime-report.v1.json"

    def test_previous_versions_retained(self, tmp_path: Path) -> None:
        reg_path = tmp_path / "docs.json"
        reg = DocumentRegistry(reg_path, "val-test", "auto")

        path1 = tmp_path / "phase-0" / "report.v1.json"
        reg.register("runtime-report", "0", path1, '{"v":1}')

        path2 = tmp_path / "phase-0" / "report.v2.json"
        reg.register("runtime-report", "0", path2, '{"v":2}')

        # Both files should exist on disk
        assert path1.exists()
        assert path2.exists()

        # Registry should have both entries
        data = json.loads(reg_path.read_text())
        runtime_docs = [d for d in data["documents"] if d["id"] == "runtime-report"]
        assert len(runtime_docs) == 2

    def test_prune_old_versions(self, tmp_path: Path) -> None:
        """After 4+ versions, only last 3 are kept in the registry."""
        reg_path = tmp_path / "docs.json"
        reg = DocumentRegistry(reg_path, "val-test", "auto")

        for i in range(5):
            p = tmp_path / f"report.v{i + 1}.json"
            reg.register("runtime-report", "0", p, f'{{"v":{i + 1}}}')

        data = json.loads(reg_path.read_text())
        runtime_docs = [d for d in data["documents"] if d["id"] == "runtime-report"]
        assert len(runtime_docs) == 3
        versions = sorted(d["version"] for d in runtime_docs)
        assert versions == [3, 4, 5]


# ── test_resume_skips_completed_phases ───────────────────────────────────────


class TestResumeSkipsCompleted:
    def test_phase_0_skipped_on_resume(self, tmp_project: Path) -> None:
        state_path = tmp_project / ".sdd-state" / "validation-state.json"
        run_id = "val-resume-test"
        state = ValidationState(state_path, run_id)
        state.mark_complete("0")

        pipeline = ValidationPipeline(
            project_dir=tmp_project,
            flush_mode="auto",
            validation_timeout=5.0,
            resume=True,
        )
        # Override run_id to match pre-seeded state
        pipeline.run_id = run_id
        pipeline.state = ValidationState(state_path, run_id)

        # Phase 0 should be skipped (returns 0 without running subprocess)
        exit_code = pipeline._run_phase_0()
        assert exit_code == 0


# ── test_auth_bootstrap_no_seed_script ───────────────────────────────────────


class TestAuthBootstrapNoSeedScript:
    def test_no_seed_script(self, tmp_project: Path) -> None:
        result = _find_seed_script(tmp_project)
        assert result is None

    def test_ts_seed_found(self, tmp_project: Path) -> None:
        scripts_dir = tmp_project / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "qa-seed.ts").touch()
        result = _find_seed_script(tmp_project)
        assert result is not None
        assert result.name == "qa-seed.ts"

    def test_js_seed_found(self, tmp_project: Path) -> None:
        scripts_dir = tmp_project / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "qa-seed.js").touch()
        result = _find_seed_script(tmp_project)
        assert result is not None
        assert result.name == "qa-seed.js"

    def test_sh_seed_found(self, tmp_project: Path) -> None:
        scripts_dir = tmp_project / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "qa-seed.sh").touch()
        result = _find_seed_script(tmp_project)
        assert result is not None
        assert result.name == "qa-seed.sh"


# ── test_flush_mode_manual_holds_output ──────────────────────────────────────


class TestFlushModeManual:
    def test_manual_holds_output(self, tmp_path: Path) -> None:
        reg_path = tmp_path / "docs.json"
        reg = DocumentRegistry(reg_path, "val-test", "manual")

        doc_path = tmp_path / "phase-0" / "report.v1.json"
        entry = reg.register("runtime-report", "0", doc_path, '{"status":"ok"}')

        # Document should NOT be on disk yet
        assert not doc_path.exists()
        assert entry["status"] == "pending"
        assert reg.pending_count == 1

    def test_manual_flush_writes_to_disk(self, tmp_path: Path) -> None:
        reg_path = tmp_path / "docs.json"
        reg = DocumentRegistry(reg_path, "val-test", "manual")

        doc_path = tmp_path / "phase-0" / "report.v1.json"
        reg.register("runtime-report", "0", doc_path, '{"status":"ok"}')
        assert not doc_path.exists()

        flushed = reg.flush_pending()
        assert flushed == 1
        assert doc_path.exists()
        assert reg.pending_count == 0

    def test_flush_phase_filter(self, tmp_path: Path) -> None:
        reg_path = tmp_path / "docs.json"
        reg = DocumentRegistry(reg_path, "val-test", "manual")

        path_0 = tmp_path / "phase-0" / "report.v1.json"
        path_1 = tmp_path / "phase-1" / "inventory.v1.json"
        reg.register("runtime-report", "0", path_0, '{"phase":0}')
        reg.register("discovery-inventory", "1", path_1, '{"phase":1}')

        # Flush only phase 0
        flushed = reg.flush_pending(phase_filter="0")
        assert flushed == 1
        assert path_0.exists()
        assert not path_1.exists()
        assert reg.pending_count == 1


# ── test_cleanup_kills_server ────────────────────────────────────────────────


class TestCleanupKillsServer:
    def test_cleanup_terminates_process(self, tmp_project: Path) -> None:
        pipeline = ValidationPipeline(
            project_dir=tmp_project,
            flush_mode="auto",
            validation_timeout=5.0,
        )

        mock_proc: MagicMock = MagicMock(spec=subprocess.Popen)
        mock_proc.pid = 12345
        mock_proc.wait.return_value = 0
        pipeline._server_proc = mock_proc

        # Unregister atexit to test manually
        atexit.unregister(pipeline._cleanup)
        pipeline._cleanup()

        mock_proc.terminate.assert_called_once()

    def test_cleanup_wipes_credentials(self, tmp_project: Path) -> None:
        pipeline = ValidationPipeline(
            project_dir=tmp_project,
            flush_mode="auto",
            validation_timeout=5.0,
        )

        creds_path = tmp_project / ".sdd-state" / "qa-credentials.json"
        creds_path.write_text('{"email":"test@test.local"}')
        assert creds_path.exists()

        atexit.unregister(pipeline._cleanup)
        pipeline._cleanup()

        assert not creds_path.exists()

    def test_cleanup_handles_no_server(self, tmp_project: Path) -> None:
        """Cleanup should not fail if there's no server process."""
        pipeline = ValidationPipeline(
            project_dir=tmp_project,
            flush_mode="auto",
            validation_timeout=5.0,
        )

        atexit.unregister(pipeline._cleanup)
        # Should not raise
        pipeline._cleanup()
