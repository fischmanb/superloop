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
    EXIT_RUNTIME_FAILED,
    PHASE_ORDER,
    CriterionResult,
    DocumentRegistry,
    FixResult,
    Phase0Result,
    Phase1Result,
    Phase2Result,
    Phase3Result,
    Phase4aResult,
    Phase4bResult,
    Phase5Result,
    ValidationPipeline,
    ValidationState,
    _detect_dev_command_single,
    _discover_sub_projects,
    _find_seed_script,
    _has_build_script,
    _parse_args,
    build_ac_generation_prompt,
    build_discovery_prompt,
    build_failure_catalog,
    build_fix_prompt,
    build_playwright_prompt,
    build_rca_prompt,
    build_revalidation_prompt,
    detect_coverage_gaps,
    detect_dev_command,
    detect_package_manager,
    health_check,
    main,
    parse_ac_output,
    parse_discovery_output,
    parse_fix_output,
    parse_playwright_output,
    parse_port_from_output,
    parse_rca_output,
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


# ── Phase 4a: Failure Catalog tests ─────────────────────────────────────────


class TestBuildFailureCatalogBasic:
    def test_build_failure_catalog_basic(self) -> None:
        """Two features: A has 2 criteria (1 PASS, 1 FAIL), B has 1 BLOCKED.
        Catalog should have 2 entries. Stats: total=3, passed=1, failed=1, blocked=1."""
        phase_3_results: list[dict[str, Any]] = [
            {
                "feature": "Feature A",
                "criteria_results": [
                    {
                        "criterion_id": "AC-001",
                        "status": "PASS",
                        "description": "Page loads",
                        "screenshot_path": "",
                        "error": "",
                    },
                    {
                        "criterion_id": "AC-002",
                        "status": "FAIL",
                        "description": "Sort control not found",
                        "screenshot_path": "phase-3/a/fail-ac002.png",
                        "error": "Element not found",
                    },
                ],
            },
            {
                "feature": "Feature B",
                "criteria_results": [
                    {
                        "criterion_id": "AC-003",
                        "status": "BLOCKED",
                        "description": "Settings page 404",
                        "screenshot_path": "phase-3/b/block-ac003.png",
                        "error": "HTTP 404",
                    },
                ],
            },
        ]
        phase_2_features: list[dict[str, Any]] = [
            {
                "feature": "Feature A",
                "status": "PARTIAL",
                "criteria": [
                    {"id": "AC-001", "expected_outcome": "Page loads fine"},
                    {"id": "AC-002", "expected_outcome": "Sort dropdown present"},
                ],
            },
            {
                "feature": "Feature B",
                "status": "DRIFTED",
                "criteria": [
                    {"id": "AC-003", "expected_outcome": "Settings page loads"},
                ],
            },
        ]

        result = build_failure_catalog(phase_3_results, phase_2_features, "val-test-001")

        assert len(result["catalog"]) == 2
        assert result["stats"]["total_criteria"] == 3
        assert result["stats"]["passed"] == 1
        assert result["stats"]["failed"] == 1
        assert result["stats"]["blocked"] == 1

        # FAIL entry
        fail_entry = result["catalog"][0]
        assert fail_entry["id"] == "FAIL-001"
        assert fail_entry["criterion_id"] == "AC-002"
        assert fail_entry["feature"] == "Feature A"
        assert fail_entry["feature_status"] == "PARTIAL"
        assert fail_entry["result"] == "FAIL"
        assert fail_entry["expected"] == "Sort dropdown present"

        # BLOCKED entry
        block_entry = result["catalog"][1]
        assert block_entry["id"] == "BLOCK-001"
        assert block_entry["result"] == "BLOCKED"


class TestBuildFailureCatalogAllPass:
    def test_build_failure_catalog_all_pass(self) -> None:
        """All criteria pass — catalog should be empty."""
        phase_3_results: list[dict[str, Any]] = [
            {
                "feature": "Feature A",
                "criteria_results": [
                    {"criterion_id": "AC-001", "status": "PASS",
                     "description": "OK", "screenshot_path": "", "error": ""},
                ],
            },
            {
                "feature": "Feature B",
                "criteria_results": [
                    {"criterion_id": "AC-002", "status": "PASS",
                     "description": "OK", "screenshot_path": "", "error": ""},
                ],
            },
        ]
        phase_2_features: list[dict[str, Any]] = [
            {"feature": "Feature A", "status": "FOUND",
             "criteria": [{"id": "AC-001", "expected_outcome": "Works"}]},
            {"feature": "Feature B", "status": "FOUND",
             "criteria": [{"id": "AC-002", "expected_outcome": "Works"}]},
        ]

        result = build_failure_catalog(phase_3_results, phase_2_features, "val-test")

        assert result["catalog"] == []
        assert result["stats"]["total_criteria"] == 2
        assert result["stats"]["passed"] == 2
        assert result["stats"]["failed"] == 0
        assert result["stats"]["blocked"] == 0


class TestBuildFailureCatalogMultipleFails:
    def test_build_failure_catalog_multiple_fails(self) -> None:
        """One feature with 3 criteria all FAIL — 3 entries with sequential ids."""
        phase_3_results: list[dict[str, Any]] = [
            {
                "feature": "Feature X",
                "criteria_results": [
                    {"criterion_id": "AC-010", "status": "FAIL",
                     "description": "Fail 1", "screenshot_path": "", "error": "err1"},
                    {"criterion_id": "AC-011", "status": "FAIL",
                     "description": "Fail 2", "screenshot_path": "", "error": "err2"},
                    {"criterion_id": "AC-012", "status": "FAIL",
                     "description": "Fail 3", "screenshot_path": "", "error": "err3"},
                ],
            },
        ]
        phase_2_features: list[dict[str, Any]] = [
            {
                "feature": "Feature X", "status": "FOUND",
                "criteria": [
                    {"id": "AC-010", "expected_outcome": "Exp 1"},
                    {"id": "AC-011", "expected_outcome": "Exp 2"},
                    {"id": "AC-012", "expected_outcome": "Exp 3"},
                ],
            },
        ]

        result = build_failure_catalog(phase_3_results, phase_2_features, "val-test")

        assert len(result["catalog"]) == 3
        assert result["catalog"][0]["id"] == "FAIL-001"
        assert result["catalog"][1]["id"] == "FAIL-002"
        assert result["catalog"][2]["id"] == "FAIL-003"


class TestBuildFailureCatalogEnrichment:
    def test_build_failure_catalog_enrichment(self) -> None:
        """Verify enrichment: expected comes from Phase 2 expected_outcome,
        feature_status comes from Phase 2 feature status — not from Phase 3."""
        phase_3_results: list[dict[str, Any]] = [
            {
                "feature": "Feature Z",
                "criteria_results": [
                    {
                        "criterion_id": "AC-050",
                        "status": "FAIL",
                        "description": "Phase 3 description",
                        "screenshot_path": "shot.png",
                        "error": "Phase 3 error detail",
                    },
                ],
            },
        ]
        # Phase 2 has different data that should appear in the catalog
        phase_2_features: list[dict[str, Any]] = [
            {
                "feature": "Feature Z from Phase 2",
                "status": "MISSING",
                "criteria": [
                    {
                        "id": "AC-050",
                        "expected_outcome": "Phase 2 expected outcome text",
                    },
                ],
            },
        ]

        result = build_failure_catalog(phase_3_results, phase_2_features, "val-enrich")

        entry = result["catalog"][0]
        # expected comes from Phase 2, not Phase 3
        assert entry["expected"] == "Phase 2 expected outcome text"
        # feature_status comes from Phase 2
        assert entry["feature_status"] == "MISSING"
        # feature name comes from Phase 2
        assert entry["feature"] == "Feature Z from Phase 2"
        # actual comes from Phase 3 error field
        assert entry["actual"] == "Phase 3 error detail"
        # description is from Phase 3
        assert entry["description"] == "Phase 3 description"


class TestReadPhase3Results:
    def test_read_phase_3_results(self, tmp_project: Path) -> None:
        """Create pipeline with Phase 3 output on disk. Assert read works."""
        pipeline = ValidationPipeline(
            project_dir=tmp_project,
            flush_mode="auto",
            validation_timeout=5.0,
        )
        atexit.unregister(pipeline._cleanup)

        # Write Phase 3 results to disk
        phase3_dir = pipeline.log_dir / "phase-3"
        phase3_dir.mkdir(parents=True, exist_ok=True)
        data: dict[str, Any] = {
            "status": "VALIDATION_COMPLETE",
            "feature_results": [
                {
                    "feature": "Auth",
                    "criteria_results": [
                        {"criterion_id": "AC-001", "status": "PASS",
                         "description": "Login", "screenshot_path": "", "error": ""},
                    ],
                }
            ],
            "total_pass": 1,
            "total_fail": 0,
            "total_blocked": 0,
        }
        (phase3_dir / "validation-results.v1.json").write_text(json.dumps(data))

        result = pipeline._read_phase_3_results()
        assert result is not None
        assert result["status"] == "VALIDATION_COMPLETE"
        assert len(result["feature_results"]) == 1


class TestPhase4aRequiresPhase3:
    def test_phase_4a_requires_phase_3(self, tmp_project: Path) -> None:
        """Phase 3 not completed — _run_phase_4a returns error."""
        pipeline = ValidationPipeline(
            project_dir=tmp_project,
            flush_mode="auto",
            validation_timeout=5.0,
        )
        atexit.unregister(pipeline._cleanup)

        # Mark 0–2b complete but NOT 3
        pipeline.state.mark_complete("0")
        pipeline.state.mark_complete("1")
        pipeline.state.mark_complete("2a")
        pipeline.state.mark_complete("2b")

        result = pipeline._run_phase_4a()
        assert result.status == "CATALOG_FAILED"
        assert "Phase 3" in result.error


class TestPhase4aAllPassStillCompletes:
    @patch("auto_sdd.scripts.post_campaign_validation.run_claude")
    def test_phase_4a_all_pass_still_completes(
        self, mock_run_claude: MagicMock, tmp_project: Path,
    ) -> None:
        """All Phase 3 criteria passed — Phase 4a still completes with
        empty catalog and CATALOG_COMPLETE status."""
        pipeline = ValidationPipeline(
            project_dir=tmp_project,
            flush_mode="auto",
            validation_timeout=5.0,
        )
        atexit.unregister(pipeline._cleanup)

        # Mark prior phases complete
        for p in ("0", "1", "2a", "2b", "3", "3b"):
            pipeline.state.mark_complete(p)

        # Write Phase 3 results (all PASS)
        phase3_dir = pipeline.log_dir / "phase-3"
        phase3_dir.mkdir(parents=True, exist_ok=True)
        phase3_data: dict[str, Any] = {
            "status": "VALIDATION_COMPLETE",
            "feature_results": [
                {
                    "feature": "Home",
                    "criteria_results": [
                        {"criterion_id": "AC-001", "status": "PASS",
                         "description": "OK", "screenshot_path": "", "error": ""},
                    ],
                },
            ],
            "total_pass": 1, "total_fail": 0, "total_blocked": 0,
        }
        (phase3_dir / "validation-results.v1.json").write_text(
            json.dumps(phase3_data)
        )

        # Write Phase 2a acceptance criteria
        phase2a_dir = pipeline.log_dir / "phase-2a"
        phase2a_dir.mkdir(parents=True, exist_ok=True)
        ac_data: list[dict[str, Any]] = [
            {
                "feature": "Home", "status": "FOUND", "route": "/",
                "criteria": [
                    {"id": "AC-001", "description": "Home loads",
                     "targets_present_element": True, "steps": ["Navigate to /"],
                     "expected_outcome": "Page loads"},
                ],
            },
        ]
        (phase2a_dir / "acceptance-criteria.v1.json").write_text(
            json.dumps(ac_data)
        )

        result = pipeline._run_phase_4a()
        assert result.status == "CATALOG_COMPLETE"
        assert result.catalog == []
        assert result.stats["passed"] == 1
        assert result.stats["failed"] == 0
        assert result.stats["blocked"] == 0
        # Phase 4a marked complete
        assert pipeline.state.is_complete("4a")
        # No agent calls
        mock_run_claude.assert_not_called()


class TestBuildFailureCatalogRunId:
    def test_build_failure_catalog_run_id(self) -> None:
        """Assert the run_id is preserved in the output catalog."""
        phase_3_results: list[dict[str, Any]] = [
            {
                "feature": "F",
                "criteria_results": [
                    {"criterion_id": "AC-001", "status": "FAIL",
                     "description": "Nope", "screenshot_path": "", "error": "bad"},
                ],
            },
        ]
        phase_2_features: list[dict[str, Any]] = [
            {"feature": "F", "status": "FOUND",
             "criteria": [{"id": "AC-001", "expected_outcome": "Good"}]},
        ]

        result = build_failure_catalog(
            phase_3_results, phase_2_features, "val-20260303-120000",
        )
        assert result["run_id"] == "val-20260303-120000"


# ── Phase 4b (Root Cause Analysis) tests ──────────────────────────────────


class TestBuildRcaPromptContent:
    def test_build_rca_prompt_content(self) -> None:
        """Prompt contains failure IDs, feature names, priority ranking,
        confidence levels, max 15, root_causes key, file tree, and
        does NOT instruct the agent to read source files."""
        catalog: dict[str, Any] = {
            "run_id": "val-test",
            "catalog": [
                {
                    "id": "FAIL-001",
                    "criterion_id": "AC-002",
                    "feature": "News Filter",
                    "feature_status": "PARTIAL",
                    "result": "FAIL",
                    "description": "Sort control missing",
                    "expected": "Sort dropdown present",
                    "actual": "No sort control found",
                    "screenshot": "phase-3/news/fail.png",
                },
                {
                    "id": "FAIL-002",
                    "criterion_id": "AC-007",
                    "feature": "Calendar View",
                    "feature_status": "FOUND",
                    "result": "FAIL",
                    "description": "Events show undefined",
                    "expected": "Event titles visible",
                    "actual": "All tiles show undefined",
                    "screenshot": "phase-3/cal/fail.png",
                },
            ],
            "stats": {
                "total_criteria": 20,
                "passed": 18,
                "failed": 2,
                "blocked": 0,
            },
        }
        discovery: dict[str, Any] = {
            "routes_found": [
                {"url": "/news", "interactive_elements": ["button:Filter"]},
                {"url": "/calendar", "interactive_elements": ["div:Event"]},
            ],
        }
        file_tree = "src/app/page.tsx\nsrc/components/Calendar.tsx\nsrc/lib/api.ts"
        phase_2_features: list[dict[str, Any]] = [
            {"feature": "News Filter", "status": "PARTIAL"},
            {"feature": "Calendar View", "status": "FOUND"},
        ]

        prompt = build_rca_prompt(catalog, discovery, file_tree, phase_2_features)

        # Contains failure IDs
        assert "FAIL-001" in prompt
        assert "FAIL-002" in prompt
        # Contains feature names
        assert "News Filter" in prompt
        assert "Calendar View" in prompt
        # Contains priority ranking keywords
        assert "multiple features" in prompt.lower() or "blocking multiple features" in prompt.lower()
        assert "runtime errors" in prompt.lower() or "Runtime errors" in prompt
        # Contains confidence levels
        assert "high" in prompt
        assert "medium" in prompt
        assert "low" in prompt
        # Contains max 15
        assert "15" in prompt
        # Contains root_causes output key
        assert "root_causes" in prompt
        # Contains file tree content
        assert "src/components/Calendar.tsx" in prompt
        # Instructs agent NOT to read source files (prohibition present)
        assert "do not" in prompt.lower() or "do not attempt" in prompt.lower()
        # No positive instruction to read files
        assert "please read source" not in prompt.lower()
        assert "you should open file" not in prompt.lower()


class TestBuildRcaPromptIncludesFeatureStatuses:
    def test_build_rca_prompt_includes_feature_statuses(self) -> None:
        """Prompt includes Phase 2 feature status summaries."""
        catalog: dict[str, Any] = {
            "run_id": "val-test",
            "catalog": [
                {
                    "id": "FAIL-001", "criterion_id": "AC-001",
                    "feature": "Auth", "feature_status": "MISSING",
                    "result": "FAIL", "description": "No auth page",
                    "expected": "Login page", "actual": "404",
                    "screenshot": "",
                },
            ],
            "stats": {"total_criteria": 5, "passed": 4, "failed": 1, "blocked": 0},
        }
        phase_2_features: list[dict[str, Any]] = [
            {"feature": "Auth", "status": "MISSING"},
            {"feature": "Dashboard", "status": "FOUND"},
            {"feature": "Settings", "status": "DRIFTED"},
            {"feature": "Profile", "status": "PARTIAL"},
            {"feature": "Extras", "status": "UNEXPECTED"},
        ]

        prompt = build_rca_prompt(catalog, {}, "", phase_2_features)

        assert "Auth: MISSING" in prompt
        assert "Dashboard: FOUND" in prompt
        assert "Settings: DRIFTED" in prompt
        assert "Profile: PARTIAL" in prompt
        assert "Extras: UNEXPECTED" in prompt


class TestParseRcaOutputValid:
    def test_parse_rca_output_valid(self) -> None:
        """Valid fenced JSON with root_causes parses correctly."""
        raw = (
            "Here is the analysis:\n"
            "```json\n"
            '{\n'
            '  "root_causes": [\n'
            '    {\n'
            '      "id": "RC-001",\n'
            '      "priority": 1,\n'
            '      "root_cause": "Missing tailwind tokens",\n'
            '      "confidence": "high",\n'
            '      "affected_failures": ["FAIL-001", "FAIL-002"],\n'
            '      "affected_features": ["Dashboard", "Settings"],\n'
            '      "likely_files": ["tailwind.config.ts"],\n'
            '      "fix_description": "Add missing tokens",\n'
            '      "estimated_complexity": "small"\n'
            '    }\n'
            '  ],\n'
            '  "ungrouped_failures": [],\n'
            '  "stats": {"total_failures": 2, "grouped_into_root_causes": 2, "ungrouped": 0, "root_cause_count": 1}\n'
            '}\n'
            '```\n'
        )
        result = parse_rca_output(raw)
        assert result is not None
        assert len(result["root_causes"]) == 1
        assert result["root_causes"][0]["id"] == "RC-001"
        assert result["root_causes"][0]["confidence"] == "high"
        assert result["ungrouped_failures"] == []


class TestParseRcaOutputInvalid:
    def test_parse_rca_output_invalid(self) -> None:
        """Garbage input returns None."""
        assert parse_rca_output("this is not json at all") is None
        assert parse_rca_output("") is None
        assert parse_rca_output("```json\nnot valid\n```") is None


class TestParseRcaOutputBadConfidence:
    def test_parse_rca_output_bad_confidence(self) -> None:
        """Root cause with invalid confidence level returns None."""
        raw = (
            '```json\n'
            '{\n'
            '  "root_causes": [\n'
            '    {\n'
            '      "id": "RC-001",\n'
            '      "priority": 1,\n'
            '      "root_cause": "Something broke",\n'
            '      "confidence": "unknown",\n'
            '      "affected_failures": ["FAIL-001"],\n'
            '      "affected_features": ["Feature"],\n'
            '      "likely_files": ["src/file.ts"],\n'
            '      "fix_description": "Fix it",\n'
            '      "estimated_complexity": "small"\n'
            '    }\n'
            '  ],\n'
            '  "ungrouped_failures": [],\n'
            '  "stats": {}\n'
            '}\n'
            '```\n'
        )
        assert parse_rca_output(raw) is None


class TestParseRcaOutputMissingFields:
    def test_parse_rca_output_missing_fields(self) -> None:
        """Root cause missing likely_files returns None."""
        raw = (
            '```json\n'
            '{\n'
            '  "root_causes": [\n'
            '    {\n'
            '      "id": "RC-001",\n'
            '      "priority": 1,\n'
            '      "root_cause": "Something broke",\n'
            '      "confidence": "high",\n'
            '      "affected_failures": ["FAIL-001"],\n'
            '      "affected_features": ["Feature"],\n'
            '      "fix_description": "Fix it",\n'
            '      "estimated_complexity": "small"\n'
            '    }\n'
            '  ],\n'
            '  "ungrouped_failures": [],\n'
            '  "stats": {}\n'
            '}\n'
            '```\n'
        )
        assert parse_rca_output(raw) is None


class TestReadFailureCatalog:
    def test_read_failure_catalog(self, tmp_project: Path) -> None:
        """Pipeline reads failure catalog written by Phase 4a."""
        pipeline = ValidationPipeline(
            project_dir=tmp_project,
            flush_mode="auto",
            validation_timeout=5.0,
        )
        atexit.unregister(pipeline._cleanup)

        # Write Phase 4a output
        phase4a_dir = pipeline.log_dir / "phase-4a"
        phase4a_dir.mkdir(parents=True, exist_ok=True)
        catalog_data: dict[str, Any] = {
            "run_id": "val-test",
            "catalog": [
                {
                    "id": "FAIL-001", "criterion_id": "AC-001",
                    "feature": "Home", "feature_status": "FOUND",
                    "result": "FAIL", "description": "Broken",
                    "expected": "Works", "actual": "Doesn't work",
                    "screenshot": "",
                },
            ],
            "stats": {"total_criteria": 1, "passed": 0, "failed": 1, "blocked": 0},
        }
        (phase4a_dir / "failure-catalog.v1.json").write_text(
            json.dumps(catalog_data)
        )

        result = pipeline._read_failure_catalog()
        assert result is not None
        assert result["run_id"] == "val-test"
        assert len(result["catalog"]) == 1
        assert result["catalog"][0]["id"] == "FAIL-001"


class TestPhase4bRequiresPhase4a:
    def test_phase_4b_requires_phase_4a(self, tmp_project: Path) -> None:
        """Phase 4a not completed — _run_phase_4b returns error without
        calling run_claude."""
        pipeline = ValidationPipeline(
            project_dir=tmp_project,
            flush_mode="auto",
            validation_timeout=5.0,
        )
        atexit.unregister(pipeline._cleanup)

        # Mark phases 0–3b complete but NOT 4a
        for p in ("0", "1", "2a", "2b", "3", "3b"):
            pipeline.state.mark_complete(p)

        result = pipeline._run_phase_4b()
        assert result.status == "RCA_FAILED"
        assert "Phase 4a" in result.error


class TestPhase4bSkipsOnEmptyCatalog:
    @patch("auto_sdd.scripts.post_campaign_validation.run_claude")
    def test_phase_4b_skips_on_empty_catalog(
        self, mock_run_claude: MagicMock, tmp_project: Path,
    ) -> None:
        """Empty catalog (all passed) — _run_phase_4b returns RCA_SKIPPED
        without calling run_claude."""
        pipeline = ValidationPipeline(
            project_dir=tmp_project,
            flush_mode="auto",
            validation_timeout=5.0,
        )
        atexit.unregister(pipeline._cleanup)

        # Mark prior phases complete including 4a
        for p in ("0", "1", "2a", "2b", "3", "3b", "4a"):
            pipeline.state.mark_complete(p)

        # Write empty failure catalog
        phase4a_dir = pipeline.log_dir / "phase-4a"
        phase4a_dir.mkdir(parents=True, exist_ok=True)
        catalog_data: dict[str, Any] = {
            "run_id": "val-test",
            "catalog": [],
            "stats": {"total_criteria": 10, "passed": 10, "failed": 0, "blocked": 0},
        }
        (phase4a_dir / "failure-catalog.v1.json").write_text(
            json.dumps(catalog_data)
        )

        result = pipeline._run_phase_4b()
        assert result.status == "RCA_SKIPPED"
        assert result.root_causes == []
        # No agent calls
        mock_run_claude.assert_not_called()
        # Phase marked complete
        assert pipeline.state.is_complete("4b")


# ── Phase 5 tests ────────────────────────────────────────────────────────────


class TestBuildFixPromptContent:
    def test_build_fix_prompt_content(self) -> None:
        """build_fix_prompt includes root cause, fix desc, files, failures."""
        root_cause: dict[str, Any] = {
            "id": "RC-001",
            "priority": 1,
            "root_cause": "Missing color tokens in tailwind config",
            "confidence": "high",
            "affected_failures": ["FAIL-001", "FAIL-002"],
            "affected_features": ["Dashboard", "Settings"],
            "likely_files": ["tailwind.config.ts", "src/styles/globals.css"],
            "fix_description": "Add missing color tokens to tailwind config",
        }
        failure_entries: list[dict[str, Any]] = [
            {
                "id": "FAIL-001",
                "criterion_id": "AC-001",
                "feature": "Dashboard",
                "result": "FAIL",
                "description": "Background color not applied",
                "expected": "Blue background",
                "actual": "White background",
            },
            {
                "id": "FAIL-002",
                "criterion_id": "AC-005",
                "feature": "Settings",
                "result": "FAIL",
                "description": "Header missing",
                "expected": "Settings header visible",
                "actual": "No header found",
            },
        ]
        prompt = build_fix_prompt(root_cause, failure_entries, "/tmp/project")
        # Root cause description
        assert "Missing color tokens" in prompt
        # Fix description
        assert "Add missing color tokens" in prompt
        # Likely files
        assert "tailwind.config.ts" in prompt
        assert "src/styles/globals.css" in prompt
        # Failure details
        assert "FAIL-001" in prompt
        assert "Blue background" in prompt
        assert "White background" in prompt
        # Scope limit
        assert "4 files" in prompt
        # Escalation mention
        assert "NEEDS_ESCALATION" in prompt
        # Must NOT instruct to commit
        assert "Do NOT commit" in prompt


class TestBuildRevalidationPromptContent:
    def test_build_revalidation_prompt_content(self) -> None:
        """build_revalidation_prompt includes criteria IDs, Playwright, URL."""
        criteria: list[dict[str, Any]] = [
            {
                "id": "AC-001",
                "description": "Dashboard loads",
                "steps": ["Navigate to /dashboard"],
                "expected_outcome": "Dashboard visible",
            },
            {
                "id": "AC-005",
                "description": "Settings page loads",
                "steps": ["Navigate to /settings"],
                "expected_outcome": "Settings visible",
            },
        ]
        creds: dict[str, Any] = {"email": "test@example.com", "password": "pass123"}
        prompt = build_revalidation_prompt(
            "http://localhost:3000",
            criteria,
            creds,
            "/tmp/screenshots",
        )
        assert "AC-001" in prompt
        assert "AC-005" in prompt
        assert "Playwright" in prompt
        assert "http://localhost:3000" in prompt
        assert "test@example.com" in prompt


class TestParseFixOutput:
    def test_parse_fix_output_valid(self) -> None:
        """Fenced JSON with status FIXED parses correctly."""
        raw = (
            'Some preamble text\n'
            '```json\n'
            '{"status": "FIXED", "files_modified": ["src/app.ts", "src/utils.ts"],'
            ' "description": "Fixed the issue"}\n'
            '```\n'
        )
        result = parse_fix_output(raw)
        assert result is not None
        assert result["status"] == "FIXED"
        assert result["files_modified"] == ["src/app.ts", "src/utils.ts"]

    def test_parse_fix_output_escalation(self) -> None:
        """JSON with status NEEDS_ESCALATION parses correctly."""
        raw = '```json\n{"status": "NEEDS_ESCALATION", "files_modified": [], "description": "Too complex"}\n```'
        result = parse_fix_output(raw)
        assert result is not None
        assert result["status"] == "NEEDS_ESCALATION"

    def test_parse_fix_output_invalid(self) -> None:
        """Garbage input returns None."""
        assert parse_fix_output("this is not json at all") is None

    def test_parse_fix_output_bad_status(self) -> None:
        """JSON with invalid status returns None."""
        raw = '```json\n{"status": "UNKNOWN", "files_modified": []}\n```'
        assert parse_fix_output(raw) is None


class TestPhase5RequiresPhase4b:
    def test_phase_5_requires_phase_4b(self, tmp_project: Path) -> None:
        """Phase 4b not completed — _run_phase_5 returns error without
        calling run_claude."""
        pipeline = ValidationPipeline(
            project_dir=tmp_project,
            flush_mode="auto",
            validation_timeout=5.0,
        )
        atexit.unregister(pipeline._cleanup)

        # Mark phases 0–4a complete but NOT 4b
        for p in ("0", "1", "2a", "2b", "3", "3b", "4a"):
            pipeline.state.mark_complete(p)

        result = pipeline._run_phase_5()
        assert result.status == "FIXES_PARTIAL"
        assert "Phase 4b" in result.error


class TestPhase5NoFixesNeeded:
    @patch("auto_sdd.scripts.post_campaign_validation.run_claude")
    def test_phase_5_no_fixes_needed(
        self, mock_run_claude: MagicMock, tmp_project: Path,
    ) -> None:
        """RCA_SKIPPED status — Phase 5 returns NO_FIXES_NEEDED without
        calling run_claude."""
        pipeline = ValidationPipeline(
            project_dir=tmp_project,
            flush_mode="auto",
            validation_timeout=5.0,
        )
        atexit.unregister(pipeline._cleanup)

        # Mark prior phases complete including 4b
        for p in ("0", "1", "2a", "2b", "3", "3b", "4a", "4b"):
            pipeline.state.mark_complete(p)

        # Write RCA report with RCA_SKIPPED status
        phase4b_dir = pipeline.log_dir / "phase-4b"
        phase4b_dir.mkdir(parents=True, exist_ok=True)
        rca_data: dict[str, Any] = {
            "status": "RCA_SKIPPED",
            "root_causes": [],
            "ungrouped_failures": [],
            "stats": {},
        }
        (phase4b_dir / "rca-report.v1.json").write_text(json.dumps(rca_data))

        result = pipeline._run_phase_5()
        assert result.status == "NO_FIXES_NEEDED"
        mock_run_claude.assert_not_called()
        assert pipeline.state.is_complete("5")


class TestPhase5SkipsLowConfidence:
    @patch("auto_sdd.scripts.post_campaign_validation.run_claude")
    def test_phase_5_skips_low_confidence(
        self, mock_run_claude: MagicMock, tmp_project: Path,
    ) -> None:
        """Low confidence root cause — FixResult status is SKIPPED,
        run_claude not called."""
        pipeline = ValidationPipeline(
            project_dir=tmp_project,
            flush_mode="auto",
            validation_timeout=5.0,
        )
        atexit.unregister(pipeline._cleanup)

        # Mark prior phases complete
        for p in ("0", "1", "2a", "2b", "3", "3b", "4a", "4b"):
            pipeline.state.mark_complete(p)

        # Write RCA report with one low-confidence root cause
        phase4b_dir = pipeline.log_dir / "phase-4b"
        phase4b_dir.mkdir(parents=True, exist_ok=True)
        rca_data: dict[str, Any] = {
            "root_causes": [
                {
                    "id": "RC-001",
                    "priority": 1,
                    "root_cause": "Possible layout issue",
                    "confidence": "low",
                    "affected_failures": ["FAIL-001"],
                    "affected_features": ["Dashboard"],
                    "likely_files": ["src/layout.ts"],
                    "fix_description": "Maybe fix the layout",
                },
            ],
            "ungrouped_failures": [],
            "stats": {"root_cause_count": 1},
        }
        (phase4b_dir / "rca-report.v1.json").write_text(json.dumps(rca_data))

        # Write empty failure catalog (needed by the lookup)
        phase4a_dir = pipeline.log_dir / "phase-4a"
        phase4a_dir.mkdir(parents=True, exist_ok=True)
        catalog: dict[str, Any] = {"catalog": [], "stats": {}}
        (phase4a_dir / "failure-catalog.v1.json").write_text(json.dumps(catalog))

        result = pipeline._run_phase_5()
        assert result.total_skipped == 1
        assert len(result.fix_results) == 1
        assert result.fix_results[0]["status"] == "SKIPPED"
        mock_run_claude.assert_not_called()


class TestPhase5EscalationRecorded:
    @patch("auto_sdd.scripts.post_campaign_validation.run_claude")
    def test_phase_5_escalation_recorded(
        self, mock_run_claude: MagicMock, tmp_project: Path,
    ) -> None:
        """Agent returns NEEDS_ESCALATION — FixResult status is
        NEEDS_ESCALATION."""
        pipeline = ValidationPipeline(
            project_dir=tmp_project,
            flush_mode="auto",
            validation_timeout=5.0,
        )
        atexit.unregister(pipeline._cleanup)

        # Mark prior phases complete
        for p in ("0", "1", "2a", "2b", "3", "3b", "4a", "4b"):
            pipeline.state.mark_complete(p)

        # Write RCA report with one high-confidence root cause
        phase4b_dir = pipeline.log_dir / "phase-4b"
        phase4b_dir.mkdir(parents=True, exist_ok=True)
        rca_data: dict[str, Any] = {
            "root_causes": [
                {
                    "id": "RC-001",
                    "priority": 1,
                    "root_cause": "Complex routing issue",
                    "confidence": "high",
                    "affected_failures": ["FAIL-001"],
                    "affected_features": ["Navigation"],
                    "likely_files": ["src/router.ts"],
                    "fix_description": "Fix the router",
                },
            ],
            "ungrouped_failures": [],
            "stats": {"root_cause_count": 1},
        }
        (phase4b_dir / "rca-report.v1.json").write_text(json.dumps(rca_data))

        # Write failure catalog
        phase4a_dir = pipeline.log_dir / "phase-4a"
        phase4a_dir.mkdir(parents=True, exist_ok=True)
        catalog: dict[str, Any] = {
            "catalog": [
                {
                    "id": "FAIL-001",
                    "criterion_id": "AC-001",
                    "feature": "Navigation",
                    "result": "FAIL",
                    "description": "Nav broken",
                    "expected": "Links work",
                    "actual": "404 error",
                },
            ],
            "stats": {"total_criteria": 1, "failed": 1},
        }
        (phase4a_dir / "failure-catalog.v1.json").write_text(json.dumps(catalog))

        # Mock run_claude to return NEEDS_ESCALATION
        mock_result = MagicMock()
        mock_result.output = (
            '```json\n'
            '{"status": "NEEDS_ESCALATION", "files_modified": [], '
            '"description": "Too complex to fix automatically"}\n'
            '```'
        )
        mock_run_claude.return_value = mock_result

        result = pipeline._run_phase_5()
        assert result.total_escalated == 1
        assert len(result.fix_results) == 1
        assert result.fix_results[0]["status"] == "NEEDS_ESCALATION"
        # Agent was called exactly once (no retry for escalation)
        mock_run_claude.assert_called_once()


# ── --phase CLI flag tests ────────────────────────────────────────────────


class TestParseArgsPhaseFlag:
    def test_phase_flag_accepted(self) -> None:
        """--phase flag is parsed correctly."""
        args = _parse_args(["--phase", "0"])
        assert args.phase == "0"

    def test_phase_flag_2a(self) -> None:
        args = _parse_args(["--phase", "2a"])
        assert args.phase == "2a"

    def test_phase_flag_default_none(self) -> None:
        args = _parse_args([])
        assert args.phase is None

    def test_phase_flag_with_resume(self) -> None:
        args = _parse_args(["--phase", "3", "--resume"])
        assert args.phase == "3"
        assert args.resume is True


class TestRunSinglePhase:
    def test_unknown_phase_returns_infra_failure(self, tmp_project: Path) -> None:
        pipeline = ValidationPipeline(project_dir=tmp_project, phase="99")
        pipeline._setup_logging()
        result = pipeline._run_single_phase("99")
        assert result == EXIT_INFRA_FAILURE

    def test_single_phase_dispatches_to_phase_0(self, tmp_project: Path) -> None:
        """--phase 0 dispatches to _run_phase_0."""
        pipeline = ValidationPipeline(project_dir=tmp_project, phase="0")
        pipeline._setup_logging()
        # Mock _run_phase_0 to return success
        with patch.object(pipeline, "_run_phase_0", return_value=EXIT_ALL_PASS):
            result = pipeline._run_single_phase("0")
            assert result == EXIT_ALL_PASS

    def test_run_delegates_to_single_phase(self, tmp_project: Path) -> None:
        """run() delegates to _run_single_phase when phase is set."""
        pipeline = ValidationPipeline(project_dir=tmp_project, phase="0")
        with patch.object(
            pipeline, "_run_single_phase", return_value=EXIT_ALL_PASS
        ) as mock_single:
            result = pipeline.run()
            mock_single.assert_called_once_with("0")
            assert result == EXIT_ALL_PASS


class TestMainPassesPhaseFlag:
    def test_main_passes_phase_to_pipeline(
        self, tmp_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PROJECT_DIR", str(tmp_project))
        with patch(
            "auto_sdd.scripts.post_campaign_validation.ValidationPipeline"
        ) as MockPipeline:
            mock_instance = MagicMock()
            mock_instance.run.return_value = EXIT_ALL_PASS
            mock_instance.flush_now.return_value = 0
            MockPipeline.return_value = mock_instance
            main(["--phase", "3"])
            MockPipeline.assert_called_once()
            call_kwargs = MockPipeline.call_args
            assert call_kwargs[1]["phase"] == "3" or call_kwargs.kwargs["phase"] == "3"


# ── Monorepo package manager detection tests ─────────────────────────────


class TestPackageManagerDetectionMonorepo:
    def test_subdir_pnpm_detected(self, tmp_path: Path) -> None:
        sub = tmp_path / "client"
        sub.mkdir()
        (sub / "pnpm-lock.yaml").touch()
        assert detect_package_manager(tmp_path) == "pnpm"

    def test_subdir_yarn_detected(self, tmp_path: Path) -> None:
        sub = tmp_path / "server"
        sub.mkdir()
        (sub / "yarn.lock").touch()
        assert detect_package_manager(tmp_path) == "yarn"

    def test_subdir_npm_detected(self, tmp_path: Path) -> None:
        sub = tmp_path / "api"
        sub.mkdir()
        (sub / "package-lock.json").touch()
        assert detect_package_manager(tmp_path) == "npm"

    def test_mixed_subdirs_use_npm_default(self, tmp_path: Path) -> None:
        c = tmp_path / "client"
        c.mkdir()
        (c / "pnpm-lock.yaml").touch()
        s = tmp_path / "server"
        s.mkdir()
        (s / "yarn.lock").touch()
        # Mixed → prefer pnpm (highest priority)
        assert detect_package_manager(tmp_path) == "pnpm"

    def test_no_lockfiles_anywhere(self, tmp_path: Path) -> None:
        sub = tmp_path / "lib"
        sub.mkdir()
        assert detect_package_manager(tmp_path) == "npm"

    def test_root_lockfile_takes_precedence(self, tmp_path: Path) -> None:
        (tmp_path / "yarn.lock").touch()
        sub = tmp_path / "client"
        sub.mkdir()
        (sub / "pnpm-lock.yaml").touch()
        assert detect_package_manager(tmp_path) == "yarn"


# ── Monorepo dev command detection tests ──────────────────────────────────


class TestDevCommandDetectionMonorepo:
    def test_subdir_dev_commands_returned_as_dict(self, tmp_path: Path) -> None:
        c = tmp_path / "client"
        c.mkdir()
        (c / "package.json").write_text(json.dumps({"scripts": {"dev": "vite"}}))
        s = tmp_path / "server"
        s.mkdir()
        (s / "package.json").write_text(json.dumps({"scripts": {"start": "node ."}}))
        result = detect_dev_command(tmp_path)
        assert isinstance(result, dict)
        assert result == {"client": "dev", "server": "start"}

    def test_root_package_json_returns_string(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text(
            json.dumps({"scripts": {"dev": "next dev"}})
        )
        result = detect_dev_command(tmp_path)
        assert result == "dev"

    def test_no_package_json_anywhere(self, tmp_path: Path) -> None:
        result = detect_dev_command(tmp_path)
        assert result is None

    def test_subdirs_with_no_dev_scripts(self, tmp_path: Path) -> None:
        c = tmp_path / "client"
        c.mkdir()
        (c / "package.json").write_text(json.dumps({"scripts": {"build": "tsc"}}))
        result = detect_dev_command(tmp_path)
        assert result is None


# ── discover_sub_projects / has_build_script tests ────────────────────────


class TestDiscoverSubProjects:
    def test_finds_subdirs_with_package_json(self, tmp_path: Path) -> None:
        for name in ("client", "server"):
            d = tmp_path / name
            d.mkdir()
            (d / "package.json").write_text("{}")
        (tmp_path / "docs").mkdir()
        result = _discover_sub_projects(tmp_path)
        assert [p.name for p in result] == ["client", "server"]

    def test_skips_hidden_dirs(self, tmp_path: Path) -> None:
        d = tmp_path / ".hidden"
        d.mkdir()
        (d / "package.json").write_text("{}")
        assert _discover_sub_projects(tmp_path) == []


class TestHasBuildScript:
    def test_has_build(self, tmp_path: Path) -> None:
        pkg = tmp_path / "package.json"
        pkg.write_text(json.dumps({"scripts": {"build": "tsc"}}))
        assert _has_build_script(pkg) is True

    def test_no_build(self, tmp_path: Path) -> None:
        pkg = tmp_path / "package.json"
        pkg.write_text(json.dumps({"scripts": {"dev": "vite"}}))
        assert _has_build_script(pkg) is False

    def test_missing_file(self, tmp_path: Path) -> None:
        assert _has_build_script(tmp_path / "package.json") is False


# ── Phase0Result server_processes field tests ─────────────────────────────


class TestPhase0ResultServerProcesses:
    def test_default_empty(self) -> None:
        r = Phase0Result()
        assert r.server_processes == []


# ── Revalidation prompt retry policy tests ────────────────────────────────


class TestRevalidationPromptRetryPolicy:
    def test_retry_policy_present(self) -> None:
        """build_revalidation_prompt now includes retry policy (parity with Phase 3)."""
        criteria: list[dict[str, Any]] = [
            {
                "id": "AC-001",
                "description": "Test",
                "steps": ["Go to /"],
                "expected_outcome": "Page loads",
            },
        ]
        prompt = build_revalidation_prompt(
            "http://localhost:3000", criteria, None, "/tmp/shots"
        )
        assert "retry" in prompt.lower()
        assert "3 times" in prompt or "max 3" in prompt


# ── Playwright prompt networkidle and interaction tests ───────────────────


class TestPlaywrightPromptNetworkIdle:
    def test_networkidle_instruction_present(self) -> None:
        feature: dict[str, Any] = {
            "feature": "Test",
            "criteria": [
                {
                    "id": "AC-001",
                    "description": "D",
                    "steps": ["Go to /"],
                    "expected_outcome": "OK",
                }
            ],
        }
        prompt = build_playwright_prompt(
            "http://localhost:3000", feature, None, "/tmp/shots"
        )
        assert "networkidle" in prompt
        assert "waitForLoadState" in prompt


class TestPlaywrightPromptInteractionPatterns:
    def test_interaction_patterns_present(self) -> None:
        feature: dict[str, Any] = {
            "feature": "Test",
            "criteria": [
                {
                    "id": "AC-001",
                    "description": "D",
                    "steps": ["Go to /"],
                    "expected_outcome": "OK",
                }
            ],
        }
        prompt = build_playwright_prompt(
            "http://localhost:3000", feature, None, "/tmp/shots"
        )
        assert "Dropdowns" in prompt or "dropdowns" in prompt.lower()
        assert "Filters" in prompt or "filters" in prompt.lower()
        assert "Pagination" in prompt or "pagination" in prompt.lower()
        assert "Async data" in prompt or "async data" in prompt.lower()


# ── Pipeline cleanup with multiple server processes ───────────────────────


class TestCleanupMultipleServers:
    def test_cleanup_terminates_all_server_processes(
        self, tmp_project: Path
    ) -> None:
        pipeline = ValidationPipeline(project_dir=tmp_project)
        proc1 = MagicMock()
        proc1.pid = 1001
        proc2 = MagicMock()
        proc2.pid = 1002
        pipeline._server_procs = [proc1, proc2]
        pipeline._server_proc = proc1
        pipeline._cleanup()
        proc1.terminate.assert_called_once()
        proc2.terminate.assert_called_once()
