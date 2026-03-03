"""Tests for auto_sdd.scripts.post_campaign_validation.

Unit tests for infrastructure — no live servers needed.
"""
from __future__ import annotations

import atexit
import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from auto_sdd.lib.claude_wrapper import AgentTimeoutError
from auto_sdd.scripts.post_campaign_validation import (
    EXIT_ALL_PASS,
    EXIT_INFRA_FAILURE,
    EXIT_PARTIAL,
    CriterionResult,
    DocumentRegistry,
    Phase1Result,
    Phase2Result,
    Phase3Result,
    ValidationPipeline,
    ValidationState,
    _find_seed_script,
    build_ac_generation_prompt,
    build_discovery_prompt,
    build_playwright_prompt,
    detect_coverage_gaps,
    detect_dev_command,
    detect_package_manager,
    health_check,
    parse_ac_output,
    parse_discovery_output,
    parse_playwright_output,
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


# ── Phase 1: Discovery Agent tests ───────────────────────────────────────────


class TestBuildDiscoveryPrompt:
    def test_with_credentials(self) -> None:
        prompt = build_discovery_prompt(
            app_url="http://localhost:3000",
            credentials={"email": "qa@test.local", "password": "s3cret"},
            screenshot_dir="/tmp/screenshots",
        )
        assert "http://localhost:3000" in prompt
        assert "qa@test.local" in prompt
        assert "s3cret" in prompt
        assert "Playwright" in prompt
        assert "/tmp/screenshots" in prompt
        # Must NOT contain spec-related terms
        for forbidden in ("roadmap", "spec", "feature"):
            assert forbidden not in prompt.lower(), (
                f"Prompt must not reference '{forbidden}'"
            )

    def test_without_credentials(self) -> None:
        prompt = build_discovery_prompt(
            app_url="http://localhost:5173",
            credentials=None,
            screenshot_dir="/tmp/shots",
        )
        assert "http://localhost:5173" in prompt
        assert "/tmp/shots" in prompt
        # No login instructions when no credentials
        assert "log in" not in prompt.lower()
        assert "email" not in prompt.lower()
        assert "password" not in prompt.lower()


class TestParseDiscoveryOutput:
    def test_valid_json_fenced(self) -> None:
        raw = (
            "I browsed the app and found the following:\n"
            "```json\n"
            '{\n'
            '  "routes_found": [\n'
            '    {"url": "/dashboard", "screenshot_path": "d.png",'
            '     "interactive_elements": ["button:Save"],'
            '     "console_errors": [], "visual_issues": []}\n'
            '  ],\n'
            '  "navigation_graph": {"/": ["/dashboard"]},\n'
            '  "global_issues": ["CSS not loading"],\n'
            '  "unreachable_dead_ends": ["/broken"]\n'
            '}\n'
            "```\n"
            "That's everything I found."
        )
        result = parse_discovery_output(raw)
        assert result is not None
        assert len(result["routes_found"]) == 1
        assert result["routes_found"][0]["url"] == "/dashboard"
        assert result["navigation_graph"] == {"/": ["/dashboard"]}
        assert result["global_issues"] == ["CSS not loading"]
        assert result["unreachable_dead_ends"] == ["/broken"]

    def test_inline_json(self) -> None:
        raw = (
            'Here is the result: {"routes_found": [{"url": "/"}], '
            '"navigation_graph": {"/": []}, '
            '"global_issues": [], "unreachable_dead_ends": []} done.'
        )
        result = parse_discovery_output(raw)
        assert result is not None
        assert len(result["routes_found"]) == 1
        assert result["routes_found"][0]["url"] == "/"

    def test_invalid_output(self) -> None:
        raw = "I could not browse the app. Something went wrong.\nNo JSON here."
        result = parse_discovery_output(raw)
        assert result is None

    def test_missing_routes_found_key(self) -> None:
        raw = (
            '```json\n'
            '{"navigation_graph": {"/": []}, "global_issues": []}\n'
            '```'
        )
        result = parse_discovery_output(raw)
        assert result is None


class TestPhase1Resume:
    def test_phase_1_skipped_on_resume(self, tmp_project: Path) -> None:
        state_path = tmp_project / ".sdd-state" / "validation-state.json"
        run_id = "val-resume-p1"
        state = ValidationState(state_path, run_id)
        state.mark_complete("0")
        state.mark_complete("1")

        pipeline = ValidationPipeline(
            project_dir=tmp_project,
            flush_mode="auto",
            validation_timeout=5.0,
            resume=True,
        )
        pipeline.run_id = run_id
        pipeline.state = ValidationState(state_path, run_id)

        atexit.unregister(pipeline._cleanup)
        exit_code = pipeline._run_phase_1()
        assert exit_code == EXIT_ALL_PASS


class TestPhase1RequiresPhase0:
    @patch("auto_sdd.scripts.post_campaign_validation.run_claude")
    def test_phase_1_requires_phase_0(
        self, mock_run_claude: MagicMock, tmp_project: Path,
    ) -> None:
        pipeline = ValidationPipeline(
            project_dir=tmp_project,
            flush_mode="auto",
            validation_timeout=5.0,
        )

        atexit.unregister(pipeline._cleanup)
        # Phase 0 was NOT marked complete
        exit_code = pipeline._run_phase_1()
        assert exit_code == EXIT_INFRA_FAILURE
        mock_run_claude.assert_not_called()


# ── Phase 2: AC Generation tests ─────────────────────────────────────────────


class TestBuildACGenerationPrompt:
    def test_build_ac_generation_prompt_content(self) -> None:
        roadmap = "| 1 | Auth | clone-app | - | M | - | ✅ |"
        specs = {"auth.feature.md": "Feature: Auth\nScenario: Login"}
        discovery: dict[str, Any] = {
            "routes_found": [{"url": "/login"}],
            "navigation_graph": {"/": ["/login"]},
        }
        prompt = build_ac_generation_prompt(roadmap, specs, discovery)

        # Contains the roadmap content
        assert "Auth" in prompt
        assert "clone-app" in prompt
        # Contains the spec content
        assert "Feature: Auth" in prompt
        assert "Scenario: Login" in prompt
        # Contains discovery data
        assert "/login" in prompt
        # Mentions all classification statuses
        assert "FOUND" in prompt
        assert "MISSING" in prompt
        assert "PARTIAL" in prompt
        assert "DRIFTED" in prompt
        assert "UNEXPECTED" in prompt
        # Mentions the 10-criteria cap
        assert "10" in prompt
        lower = prompt.lower()
        assert "no more than 10" in lower or "max" in lower


class TestDetectCoverageGaps:
    def test_detects_uncovered_routes(self) -> None:
        features: list[dict[str, Any]] = [
            {
                "feature": "Auth",
                "status": "FOUND",
                "route": "/login",
                "criteria": [
                    {
                        "id": "AC-001",
                        "description": "Login works",
                        "targets_present_element": True,
                        "steps": ["Navigate to /login", "Enter creds"],
                        "expected_outcome": "Logged in",
                    }
                ],
            }
        ]
        discovery: dict[str, Any] = {
            "routes_found": [
                {"url": "/login"},
                {"url": "/admin"},
                {"url": "/settings"},
            ],
            "navigation_graph": {},
        }
        result = detect_coverage_gaps(features, discovery)
        assert "/admin" in result["uncovered_routes"]
        assert "/settings" in result["uncovered_routes"]
        assert "/login" not in result["uncovered_routes"]

    def test_detects_likely_broken(self) -> None:
        features: list[dict[str, Any]] = [
            {
                "feature": "Settings",
                "status": "MISSING",
                "criteria": [
                    {
                        "id": "AC-002",
                        "targets_present_element": False,
                        "steps": ["Navigate to /settings"],
                        "expected_outcome": "Page loads",
                    }
                ],
            }
        ]
        discovery: dict[str, Any] = {
            "routes_found": [],
            "navigation_graph": {},
        }
        result = detect_coverage_gaps(features, discovery)
        assert len(result["likely_broken"]) == 1
        assert result["likely_broken"][0]["criterion_id"] == "AC-002"

    def test_empty_discovery(self) -> None:
        features: list[dict[str, Any]] = []
        discovery: dict[str, Any] = {
            "routes_found": [],
            "navigation_graph": {},
        }
        result = detect_coverage_gaps(features, discovery)
        assert result["uncovered_routes"] == []
        assert result["likely_broken"] == []


class TestParseACOutput:
    def test_parse_ac_output_valid(self) -> None:
        raw = (
            "Here are the acceptance criteria:\n"
            "```json\n"
            "[\n"
            "  {\n"
            '    "feature": "Auth",\n'
            '    "status": "FOUND",\n'
            '    "route": "/login",\n'
            '    "match_notes": "Route exists",\n'
            '    "criteria": [\n'
            "      {\n"
            '        "id": "AC-001",\n'
            '        "description": "User can log in",\n'
            '        "targets_present_element": true,\n'
            '        "steps": ["Navigate to /login", "Enter credentials"],\n'
            '        "expected_outcome": "User is logged in"\n'
            "      }\n"
            "    ],\n"
            '    "drift_notes": null\n'
            "  }\n"
            "]\n"
            "```\n"
        )
        result = parse_ac_output(raw)
        assert result is not None
        assert len(result) == 1
        assert result[0]["feature"] == "Auth"
        assert result[0]["status"] == "FOUND"
        assert len(result[0]["criteria"]) == 1
        assert result[0]["criteria"][0]["id"] == "AC-001"

    def test_parse_ac_output_invalid_status(self) -> None:
        raw = json.dumps([{
            "feature": "Auth",
            "status": "INVALID_STATUS",
            "criteria": [{"id": "AC-001"}],
        }])
        result = parse_ac_output(raw)
        assert result is None

    def test_parse_ac_output_missing_criteria(self) -> None:
        raw = json.dumps([{
            "feature": "Auth",
            "status": "FOUND",
            # no "criteria" key
        }])
        result = parse_ac_output(raw)
        assert result is None




class TestLoadSpecs:
    def test_load_specs_empty_project(self, tmp_path: Path) -> None:
        """No .specs directory at all."""
        pipeline = ValidationPipeline(
            project_dir=tmp_path,
            flush_mode="auto",
            validation_timeout=5.0,
        )
        atexit.unregister(pipeline._cleanup)

        roadmap, specs = pipeline._load_specs()
        assert roadmap == ""
        assert specs == {}

    def test_load_specs_with_roadmap_and_features(self, tmp_path: Path) -> None:
        """Roadmap and feature specs are read correctly."""
        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()
        (specs_dir / "roadmap.md").write_text("# Roadmap\n| 1 | Auth |")

        features_dir = specs_dir / "features"
        features_dir.mkdir()
        (features_dir / "auth.feature.md").write_text(
            "Feature: Auth\nScenario: Login"
        )

        pipeline = ValidationPipeline(
            project_dir=tmp_path,
            flush_mode="auto",
            validation_timeout=5.0,
        )
        atexit.unregister(pipeline._cleanup)

        roadmap, specs = pipeline._load_specs()
        assert "# Roadmap" in roadmap
        assert "auth.feature.md" in specs
        assert "Feature: Auth" in specs["auth.feature.md"]


class TestPhase2RequiresPhase1:
    @patch("auto_sdd.scripts.post_campaign_validation.run_claude")
    def test_phase_2_requires_phase_1(
        self, mock_run_claude: MagicMock, tmp_project: Path,
    ) -> None:
        pipeline = ValidationPipeline(
            project_dir=tmp_project,
            flush_mode="auto",
            validation_timeout=5.0,
        )

        atexit.unregister(pipeline._cleanup)
        # Phase 1 was NOT marked complete
        result = pipeline._run_phase_2()
        assert result.status == "AC_GENERATION_FAILED"
        mock_run_claude.assert_not_called()


class TestPhase2SingleAgentCall:
    @patch("auto_sdd.scripts.post_campaign_validation.run_claude")
    def test_phase_2_calls_agent_once(
        self, mock_run_claude: MagicMock, tmp_project: Path,
    ) -> None:
        """Phase 2 should call run_claude exactly once (2a only).
        Phase 2b uses mechanical gap detection, not an agent."""
        pipeline = ValidationPipeline(
            project_dir=tmp_project,
            flush_mode="auto",
            validation_timeout=5.0,
        )

        atexit.unregister(pipeline._cleanup)

        # Seed Phase 1 as complete with a discovery inventory on disk
        pipeline.state.mark_complete("0")
        pipeline.state.mark_complete("1")

        # Write a discovery inventory so Phase 2a can read it
        phase1_dir = pipeline.log_dir / "phase-1"
        phase1_dir.mkdir(parents=True, exist_ok=True)
        discovery_data = {
            "status": "DISCOVERY_COMPLETE",
            "routes_found": [{"url": "/"}, {"url": "/about"}],
            "navigation_graph": {"/": ["/about"]},
            "global_issues": [],
            "unreachable_dead_ends": [],
        }
        (phase1_dir / "discovery-inventory.v1.json").write_text(
            json.dumps(discovery_data)
        )

        # Phase 2a agent returns valid AC output
        valid_ac = json.dumps([{
            "feature": "Home",
            "status": "FOUND",
            "route": "/",
            "match_notes": "Route exists",
            "criteria": [
                {
                    "id": "AC-001",
                    "description": "Home page loads",
                    "targets_present_element": True,
                    "steps": ["Navigate to /"],
                    "expected_outcome": "Page loads",
                }
            ],
            "drift_notes": None,
        }])

        mock_2a_result = MagicMock()
        mock_2a_result.output = f"```json\n{valid_ac}\n```"
        mock_run_claude.return_value = mock_2a_result

        result = pipeline._run_phase_2()

        # Phase 2a output preserved
        assert result.status == "AC_GENERATION_COMPLETE"
        assert len(result.features) == 1
        assert result.features[0]["feature"] == "Home"
        # run_claude called exactly ONCE (2a only, not 2b)
        assert mock_run_claude.call_count == 1
        # Gap report should exist (mechanical detection ran)
        assert result.gap_report is not None
        # /about is uncovered (only / was in criteria)
        assert "/about" in result.gap_report.get("uncovered_routes", [])


# ── Phase 3: Playwright Validation tests ──────────────────────────────────


class TestBuildPlaywrightPromptWithCredentials:
    def test_build_playwright_prompt_with_credentials(self) -> None:
        feature: dict[str, Any] = {
            "feature": "Auth",
            "status": "FOUND",
            "route": "/login",
            "criteria": [
                {
                    "id": "AC-001",
                    "description": "User can log in",
                    "steps": ["Navigate to /login", "Enter credentials"],
                    "expected_outcome": "User is authenticated",
                },
                {
                    "id": "AC-002",
                    "description": "Login error on bad password",
                    "steps": ["Navigate to /login", "Enter wrong password"],
                    "expected_outcome": "Error message shown",
                },
            ],
        }
        credentials: dict[str, Any] = {
            "email": "qa@test.local",
            "password": "s3cret",
        }
        prompt = build_playwright_prompt(
            app_url="http://localhost:3000",
            feature=feature,
            credentials=credentials,
            screenshot_dir="/tmp/shots/auth",
        )
        assert "http://localhost:3000" in prompt
        # Login instructions present
        assert "qa@test.local" in prompt
        assert "s3cret" in prompt
        # Both criterion IDs present
        assert "AC-001" in prompt
        assert "AC-002" in prompt
        # Key output statuses mentioned
        assert "VALIDATION_PASS" in prompt
        assert "VALIDATION_FAIL" in prompt
        assert "VALIDATION_BLOCKED" in prompt
        # Screenshot dir
        assert "/tmp/shots/auth" in prompt
        # Playwright mentioned
        assert "Playwright" in prompt
        # Retry policy
        lower = prompt.lower()
        assert "retry" in lower or "3" in prompt


class TestBuildPlaywrightPromptWithoutCredentials:
    def test_build_playwright_prompt_without_credentials(self) -> None:
        feature: dict[str, Any] = {
            "feature": "Dashboard",
            "status": "FOUND",
            "route": "/dashboard",
            "criteria": [
                {
                    "id": "AC-010",
                    "description": "Dashboard loads",
                    "steps": ["Navigate to /dashboard"],
                    "expected_outcome": "Page renders",
                },
            ],
        }
        prompt = build_playwright_prompt(
            app_url="http://localhost:5173",
            feature=feature,
            credentials=None,
            screenshot_dir="/tmp/shots/dash",
        )
        # No login instructions
        assert "log in" not in prompt.lower()
        assert "email" not in prompt.lower()
        assert "password" not in prompt.lower()
        # Criteria still present
        assert "AC-010" in prompt
        assert "Dashboard loads" in prompt


class TestParsePlaywrightOutputValid:
    def test_parse_playwright_output_valid(self) -> None:
        raw = (
            "Testing complete. Results:\n"
            "```json\n"
            "{\n"
            '  "results": [\n'
            "    {\n"
            '      "criterion_id": "AC-001",\n'
            '      "status": "PASS",\n'
            '      "description": "User can log in",\n'
            '      "screenshot_path": "",\n'
            '      "error": ""\n'
            "    },\n"
            "    {\n"
            '      "criterion_id": "AC-002",\n'
            '      "status": "FAIL",\n'
            '      "description": "Login error shown",\n'
            '      "screenshot_path": "/tmp/fail-ac002.png",\n'
            '      "error": "Expected error message not found"\n'
            "    }\n"
            "  ]\n"
            "}\n"
            "```\n"
        )
        result = parse_playwright_output(raw)
        assert result is not None
        assert len(result) == 2
        assert result[0]["criterion_id"] == "AC-001"
        assert result[0]["status"] == "PASS"
        assert result[1]["criterion_id"] == "AC-002"
        assert result[1]["status"] == "FAIL"
        assert result[1]["screenshot_path"] == "/tmp/fail-ac002.png"


class TestParsePlaywrightOutputInvalid:
    def test_parse_playwright_output_invalid(self) -> None:
        raw = "I tried to test but everything broke. No JSON here."
        result = parse_playwright_output(raw)
        assert result is None


class TestParsePlaywrightOutputBadStatus:
    def test_parse_playwright_output_bad_status(self) -> None:
        raw = json.dumps({
            "results": [
                {
                    "criterion_id": "AC-001",
                    "status": "UNKNOWN",
                    "description": "Something",
                    "screenshot_path": "",
                    "error": "",
                }
            ]
        })
        result = parse_playwright_output(raw)
        assert result is None


class TestReadAcceptanceCriteriaFrom2a:
    def test_read_acceptance_criteria_from_2a(self, tmp_project: Path) -> None:
        pipeline = ValidationPipeline(
            project_dir=tmp_project,
            flush_mode="auto",
            validation_timeout=5.0,
        )
        atexit.unregister(pipeline._cleanup)

        # Write Phase 2a acceptance criteria to disk
        phase2a_dir = pipeline.log_dir / "phase-2a"
        phase2a_dir.mkdir(parents=True, exist_ok=True)
        criteria_data: list[dict[str, Any]] = [
            {
                "feature": "Auth",
                "status": "FOUND",
                "route": "/login",
                "match_notes": "Route exists",
                "criteria": [
                    {
                        "id": "AC-001",
                        "description": "Login works",
                        "targets_present_element": True,
                        "steps": ["Navigate to /login"],
                        "expected_outcome": "Logged in",
                    }
                ],
                "drift_notes": None,
            }
        ]
        (phase2a_dir / "acceptance-criteria.v1.json").write_text(
            json.dumps(criteria_data)
        )

        result = pipeline._read_acceptance_criteria()
        assert result is not None
        assert len(result) == 1
        assert result[0]["feature"] == "Auth"


class TestPhase3RequiresPhase2:
    @patch("auto_sdd.scripts.post_campaign_validation.run_claude")
    def test_phase_3_requires_phase_2(
        self, mock_run_claude: MagicMock, tmp_project: Path,
    ) -> None:
        pipeline = ValidationPipeline(
            project_dir=tmp_project,
            flush_mode="auto",
            validation_timeout=5.0,
        )
        atexit.unregister(pipeline._cleanup)

        # Phase 2a NOT marked complete
        pipeline.state.mark_complete("0")
        pipeline.state.mark_complete("1")
        # Intentionally NOT marking 2a complete

        exit_code = pipeline._run_phase_3()
        assert exit_code == EXIT_INFRA_FAILURE
        mock_run_claude.assert_not_called()


class TestPhase3Marks3bComplete:
    @patch("auto_sdd.scripts.post_campaign_validation.run_claude")
    def test_phase_3_marks_3b_complete(
        self, mock_run_claude: MagicMock, tmp_project: Path,
    ) -> None:
        pipeline = ValidationPipeline(
            project_dir=tmp_project,
            flush_mode="auto",
            validation_timeout=5.0,
        )
        atexit.unregister(pipeline._cleanup)

        # Seed prior phases as complete
        pipeline.state.mark_complete("0")
        pipeline.state.mark_complete("1")
        pipeline.state.mark_complete("2a")
        pipeline.state.mark_complete("2b")

        # Write Phase 0 runtime report (for app URL)
        phase0_dir = pipeline.log_dir / "phase-0"
        phase0_dir.mkdir(parents=True, exist_ok=True)
        (phase0_dir / "runtime-report.v1.json").write_text(
            json.dumps({"url": "http://localhost:3000", "status": "RUNTIME_READY"})
        )

        # Write Phase 2a acceptance criteria
        phase2a_dir = pipeline.log_dir / "phase-2a"
        phase2a_dir.mkdir(parents=True, exist_ok=True)
        criteria_data: list[dict[str, Any]] = [
            {
                "feature": "Auth",
                "status": "FOUND",
                "route": "/login",
                "criteria": [
                    {
                        "id": "AC-001",
                        "description": "Login works",
                        "targets_present_element": True,
                        "steps": ["Navigate to /login"],
                        "expected_outcome": "Logged in",
                    }
                ],
            }
        ]
        (phase2a_dir / "acceptance-criteria.v1.json").write_text(
            json.dumps(criteria_data)
        )

        # Mock run_claude to return valid results
        valid_results = json.dumps({
            "results": [
                {
                    "criterion_id": "AC-001",
                    "status": "PASS",
                    "description": "Login works",
                    "screenshot_path": "",
                    "error": "",
                }
            ]
        })
        mock_result = MagicMock()
        mock_result.output = f"```json\n{valid_results}\n```"
        mock_run_claude.return_value = mock_result

        exit_code = pipeline._run_phase_3()
        assert exit_code == EXIT_ALL_PASS
        # Both phases marked complete
        assert pipeline.state.is_complete("3")
        assert pipeline.state.is_complete("3b")


class TestPhase3AgentFailureContinues:
    @patch("auto_sdd.scripts.post_campaign_validation.run_claude")
    def test_phase_3_agent_failure_continues(
        self, mock_run_claude: MagicMock, tmp_project: Path,
    ) -> None:
        pipeline = ValidationPipeline(
            project_dir=tmp_project,
            flush_mode="auto",
            validation_timeout=5.0,
        )
        atexit.unregister(pipeline._cleanup)

        # Seed prior phases
        pipeline.state.mark_complete("0")
        pipeline.state.mark_complete("1")
        pipeline.state.mark_complete("2a")
        pipeline.state.mark_complete("2b")

        # Write Phase 0 runtime report
        phase0_dir = pipeline.log_dir / "phase-0"
        phase0_dir.mkdir(parents=True, exist_ok=True)
        (phase0_dir / "runtime-report.v1.json").write_text(
            json.dumps({"url": "http://localhost:3000", "status": "RUNTIME_READY"})
        )

        # Write Phase 2a acceptance criteria with TWO features
        phase2a_dir = pipeline.log_dir / "phase-2a"
        phase2a_dir.mkdir(parents=True, exist_ok=True)
        criteria_data: list[dict[str, Any]] = [
            {
                "feature": "Feature A",
                "status": "FOUND",
                "route": "/a",
                "criteria": [
                    {
                        "id": "AC-100",
                        "description": "Feature A works",
                        "steps": ["Navigate to /a"],
                        "expected_outcome": "Page loads",
                    }
                ],
            },
            {
                "feature": "Feature B",
                "status": "FOUND",
                "route": "/b",
                "criteria": [
                    {
                        "id": "AC-200",
                        "description": "Feature B works",
                        "steps": ["Navigate to /b"],
                        "expected_outcome": "Page loads",
                    }
                ],
            },
        ]
        (phase2a_dir / "acceptance-criteria.v1.json").write_text(
            json.dumps(criteria_data)
        )

        # First feature: agent times out
        # Second feature: agent succeeds
        valid_results = json.dumps({
            "results": [
                {
                    "criterion_id": "AC-200",
                    "status": "PASS",
                    "description": "Feature B works",
                    "screenshot_path": "",
                    "error": "",
                }
            ]
        })
        mock_success = MagicMock()
        mock_success.output = f"```json\n{valid_results}\n```"
        mock_run_claude.side_effect = [
            AgentTimeoutError("Agent timed out after 300s"),
            mock_success,
        ]

        exit_code = pipeline._run_phase_3()
        assert exit_code == EXIT_ALL_PASS

        # Verify: first feature's criteria should be BLOCKED
        assert len(pipeline.state.completed_phases) >= 2
        # Check the state has both "3" and "3b"
        assert pipeline.state.is_complete("3")
        assert pipeline.state.is_complete("3b")

        # Read the validation results from disk
        phase3_dir = pipeline.log_dir / "phase-3"
        report_files = list(phase3_dir.glob("validation-results.v*.json"))
        assert len(report_files) == 1
        report = json.loads(report_files[0].read_text())

        # Feature A: all criteria BLOCKED
        feature_a = report["feature_results"][0]
        assert feature_a["feature"] == "Feature A"
        assert feature_a["criteria_results"][0]["status"] == "BLOCKED"
        assert "Agent failure" in feature_a["criteria_results"][0]["error"]

        # Feature B: real results
        feature_b = report["feature_results"][1]
        assert feature_b["feature"] == "Feature B"
        assert feature_b["criteria_results"][0]["status"] == "PASS"

        # Pipeline continued (both features processed)
        assert mock_run_claude.call_count == 2
