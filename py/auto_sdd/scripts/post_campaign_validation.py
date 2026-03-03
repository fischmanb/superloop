"""Post-campaign validation orchestrator with Phases 0–4a.

Boots a target project, validates it can start, discovers routes (Phase 1),
generates acceptance criteria from specs (Phase 2a), runs gap detection
(Phase 2b), validates acceptance criteria via Playwright (Phase 3), and
builds a failure catalog from results (Phase 4a).
Phases 4b–5 are stubs pending future milestones.

Usage:
    python -m auto_sdd.scripts.post_campaign_validation

Configuration is read from environment variables:
    PROJECT_DIR          Required. Path to the target project.
    FLUSH_MODE           "auto" (default) or "manual".
    VALIDATION_TIMEOUT   Seconds for Phase 0 health check (default 60).
"""
from __future__ import annotations

import argparse
import atexit
import hashlib
import json
import logging
import os
import re
import signal as signal_mod
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from auto_sdd.lib.claude_wrapper import (
    AgentTimeoutError,
    ClaudeOutputError,
    run_claude,
)

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

PHASE_ORDER: list[str] = [
    "0", "1", "2a", "2b", "3", "3b", "4a", "4b", "5",
]

EXIT_ALL_PASS = 0
EXIT_PARTIAL = 1
EXIT_RUNTIME_FAILED = 2
EXIT_INFRA_FAILURE = 3

_COMMON_PORTS = [3000, 3001, 5173, 8080]

_PORT_RE = re.compile(
    r"(?:localhost|127\.0\.0\.1|0\.0\.0\.0)[:\s]+(\d{2,5})"
    r"|(?:port)\s+(\d{2,5})"
    r"|https?://[^:/\s]+:(\d{2,5})",
    re.IGNORECASE,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256(data: str) -> str:
    return "sha256:" + hashlib.sha256(data.encode()).hexdigest()[:16]


def _atomic_write_json(path: Path, obj: object) -> None:
    """Write JSON atomically via temp-file-then-rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(obj, indent=2) + "\n"
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.stem)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(data)
        os.rename(tmp, str(path))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _read_json(path: Path) -> Any:
    """Read a JSON file, returning None if missing."""
    if not path.exists():
        return None
    return json.loads(path.read_text())


# ── Document Registry ────────────────────────────────────────────────────────


class DocumentRegistry:
    """Tracks versioned validation artifacts per the spec's Document Versioning."""

    def __init__(self, registry_path: Path, run_id: str, flush_mode: str) -> None:
        self.registry_path = registry_path
        self.run_id = run_id
        self.flush_mode = flush_mode
        self._docs: list[dict[str, Any]] = []
        self._pending: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        existing = _read_json(self.registry_path)
        if existing and isinstance(existing, dict):
            if existing.get("run_id") == self.run_id:
                raw = existing.get("documents", [])
                if isinstance(raw, list):
                    self._docs = raw

    def save(self) -> None:
        payload: dict[str, Any] = {
            "run_id": self.run_id,
            "flush_mode": self.flush_mode,
            "documents": self._docs,
        }
        _atomic_write_json(self.registry_path, payload)

    def _next_version(self, doc_id: str) -> int:
        versions = [
            d["version"] for d in self._docs if d["id"] == doc_id
        ]
        return max(versions, default=0) + 1

    def _prune_old_versions(self, doc_id: str, keep: int = 3) -> None:
        """Retain only the last *keep* versions of a document."""
        matching = [d for d in self._docs if d["id"] == doc_id]
        if len(matching) <= keep:
            return
        matching.sort(key=lambda d: d["version"])
        to_remove = matching[: len(matching) - keep]
        remove_set = {(d["id"], d["version"]) for d in to_remove}
        self._docs = [
            d for d in self._docs
            if (d["id"], d["version"]) not in remove_set
        ]

    def register(
        self,
        doc_id: str,
        phase: str,
        path: Path,
        content: str,
    ) -> dict[str, Any]:
        """Register a document.  In auto mode, writes immediately.
        In manual mode, holds in pending until flushed."""
        version = self._next_version(doc_id)
        entry: dict[str, Any] = {
            "id": doc_id,
            "phase": phase,
            "version": version,
            "path": str(path),
            "checksum": _sha256(content),
            "flushed_at": None,
            "status": "pending",
        }
        if version > 1:
            entry["supersedes"] = f"{doc_id}.v{version - 1}.json"

        if self.flush_mode == "auto":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            entry["flushed_at"] = _now_iso()
            entry["status"] = "final"
            self._docs.append(entry)
            self._prune_old_versions(doc_id)
            self.save()
        else:
            entry["_content"] = content
            self._pending.append(entry)
            self._docs.append(entry)
            self.save()

        return entry

    def flush_pending(self, phase_filter: str | None = None) -> int:
        """Write pending documents to disk. Returns count flushed."""
        flushed = 0
        remaining: list[dict[str, Any]] = []
        for entry in self._pending:
            if phase_filter is not None and entry["phase"] != phase_filter:
                remaining.append(entry)
                continue
            content = entry.pop("_content", "")
            p = Path(entry["path"])
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
            entry["flushed_at"] = _now_iso()
            entry["status"] = "final"
            flushed += 1
        self._pending = remaining
        if flushed:
            self.save()
        return flushed

    @property
    def pending_count(self) -> int:
        return len(self._pending)


# ── Validation State ─────────────────────────────────────────────────────────


class ValidationState:
    """Tracks which phases completed, supports --resume."""

    def __init__(self, state_path: Path, run_id: str) -> None:
        self.state_path = state_path
        self.run_id = run_id
        self.completed_phases: list[str] = []
        self.phase_timestamps: dict[str, str] = {}
        self.started_at: str = _now_iso()
        self._load()

    def _load(self) -> None:
        existing = _read_json(self.state_path)
        if existing and isinstance(existing, dict):
            if existing.get("run_id") == self.run_id:
                raw_phases = existing.get("completed_phases", [])
                if isinstance(raw_phases, list):
                    self.completed_phases = [str(p) for p in raw_phases]
                raw_ts = existing.get("phase_timestamps", {})
                if isinstance(raw_ts, dict):
                    self.phase_timestamps = {
                        str(k): str(v) for k, v in raw_ts.items()
                    }
                started = existing.get("started_at", "")
                if isinstance(started, str) and started:
                    self.started_at = started

    def save(self) -> None:
        payload: dict[str, Any] = {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "completed_phases": self.completed_phases,
            "phase_timestamps": self.phase_timestamps,
        }
        _atomic_write_json(self.state_path, payload)

    def mark_complete(self, phase: str) -> None:
        if phase not in self.completed_phases:
            self.completed_phases.append(phase)
        self.phase_timestamps[phase] = _now_iso()
        self.save()

    def is_complete(self, phase: str) -> bool:
        return phase in self.completed_phases


# ── Package Manager / Dev Server Detection ───────────────────────────────────


def detect_package_manager(project_dir: Path) -> str:
    """Detect package manager from lock files.  Falls back to npm."""
    if (project_dir / "pnpm-lock.yaml").exists():
        return "pnpm"
    if (project_dir / "yarn.lock").exists():
        return "yarn"
    if (project_dir / "package-lock.json").exists():
        return "npm"
    return "npm"


def detect_dev_command(project_dir: Path) -> str | None:
    """Read package.json scripts and pick the dev command name.

    Checks for ``dev``, ``start``, ``serve`` in that order.
    Returns the script name (not the full command), or None.
    """
    pkg_json_path = project_dir / "package.json"
    if not pkg_json_path.exists():
        return None

    try:
        pkg = json.loads(pkg_json_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    scripts: Any = pkg.get("scripts", {})
    if not isinstance(scripts, dict):
        return None

    for candidate in ("dev", "start", "serve"):
        if candidate in scripts:
            return candidate
    return None


def parse_port_from_output(output: str) -> int | None:
    """Extract a port number from dev server stdout/stderr."""
    for match in _PORT_RE.finditer(output):
        for group in match.groups():
            if group is not None:
                port = int(group)
                if 1024 <= port <= 65535:
                    return port
    return None


def health_check(
    url: str,
    timeout: float = 60.0,
    initial_backoff: float = 1.0,
) -> bool:
    """Poll *url* with exponential backoff until HTTP 200 or timeout."""
    deadline = time.monotonic() + timeout
    backoff = initial_backoff
    while time.monotonic() < deadline:
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, OSError, ValueError):
            pass
        remaining = deadline - time.monotonic()
        sleep_time = min(backoff, max(remaining, 0))
        if sleep_time <= 0:
            break
        time.sleep(sleep_time)
        backoff = min(backoff * 2, 16.0)
    return False


def _find_seed_script(project_dir: Path) -> Path | None:
    """Look for qa-seed.ts / .js / .sh in the project's scripts/ dir."""
    scripts_dir = project_dir / "scripts"
    for ext in ("ts", "js", "sh"):
        candidate = scripts_dir / f"qa-seed.{ext}"
        if candidate.exists():
            return candidate
    return None


def _run_seed_script(
    seed_path: Path,
    project_dir: Path,
    teardown: bool = False,
) -> tuple[bool, dict[str, Any] | None, str]:
    """Run a QA seed script.  Returns (success, credentials_dict, error_msg)."""
    cmd: list[str] = []
    ext = seed_path.suffix
    if ext == ".ts":
        cmd = ["npx", "tsx", str(seed_path)]
    elif ext == ".js":
        cmd = ["node", str(seed_path)]
    elif ext == ".sh":
        cmd = ["bash", str(seed_path)]
    else:
        return False, None, f"Unknown seed script extension: {ext}"

    if teardown:
        cmd.append("--teardown")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(project_dir),
            timeout=60,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, None, f"Seed script execution failed: {exc}"

    if result.returncode != 0:
        return False, None, (
            f"Seed script exited {result.returncode}: "
            f"{result.stderr.strip()[:500]}"
        )

    if teardown:
        return True, None, ""

    # Parse JSON credentials from stdout
    stdout = result.stdout.strip()
    try:
        creds = json.loads(stdout)
        if isinstance(creds, dict):
            return True, creds, ""
        return False, None, "Seed script stdout was not a JSON object"
    except json.JSONDecodeError:
        return False, None, (
            f"Could not parse credentials JSON from seed script stdout: "
            f"{stdout[:200]}"
        )


# ── Phase 0: Runtime Bootstrap ───────────────────────────────────────────────


class Phase0Result:
    """Structured result of Phase 0."""

    def __init__(self) -> None:
        self.status: str = "RUNTIME_FAILED"
        self.port: int | None = None
        self.url: str = ""
        self.auth_status: str = "AUTH_SETUP_SKIPPED"
        self.auth_email: str = ""
        self.build_output: str = ""
        self.dev_output: str = ""
        self.error: str = ""
        self.package_manager: str = ""
        self.dev_command: str = ""
        self.server_process: subprocess.Popen[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "port": self.port,
            "url": self.url,
            "auth_status": self.auth_status,
            "auth_email": self.auth_email,
            "package_manager": self.package_manager,
            "dev_command": self.dev_command,
            "error": self.error,
            "timestamp": _now_iso(),
        }


class Phase1Result:
    """Structured result of Phase 1 (Discovery Agent)."""

    def __init__(self) -> None:
        self.status: str = "DISCOVERY_FAILED"
        self.routes_found: list[dict[str, Any]] = []
        self.navigation_graph: dict[str, Any] = {}
        self.global_issues: list[str] = []
        self.unreachable_dead_ends: list[str] = []
        self.error: str = ""
        self.screenshot_dir: str = ""
        self.route_count: int = 0
        self.agent_duration_ms: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "routes_found": self.routes_found,
            "navigation_graph": self.navigation_graph,
            "global_issues": self.global_issues,
            "unreachable_dead_ends": self.unreachable_dead_ends,
            "error": self.error,
            "screenshot_dir": self.screenshot_dir,
            "route_count": self.route_count,
            "agent_duration_ms": self.agent_duration_ms,
            "timestamp": _now_iso(),
        }


class Phase2Result:
    """Structured result of Phase 2 (AC Generation + Gap Detection)."""

    def __init__(self) -> None:
        self.status: str = "AC_GENERATION_FAILED"
        self.features: list[dict[str, Any]] = []
        self.gap_report: dict[str, Any] | None = None
        self.total_criteria_count: int = 0
        self.error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "features": self.features,
            "gap_report": self.gap_report,
            "total_criteria_count": self.total_criteria_count,
            "error": self.error,
            "timestamp": _now_iso(),
        }


class CriterionResult:
    """Result of validating a single acceptance criterion."""

    def __init__(self) -> None:
        self.criterion_id: str = ""
        self.status: str = "BLOCKED"
        self.description: str = ""
        self.screenshot_path: str = ""
        self.error: str = ""
        self.retries: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "criterion_id": self.criterion_id,
            "status": self.status,
            "description": self.description,
            "screenshot_path": self.screenshot_path,
            "error": self.error,
            "retries": self.retries,
        }


class Phase3Result:
    """Structured result of Phase 3 (Playwright Validation)."""

    def __init__(self) -> None:
        self.status: str = "VALIDATION_FAILED"
        self.feature_results: list[dict[str, Any]] = []
        self.total_pass: int = 0
        self.total_fail: int = 0
        self.total_blocked: int = 0
        self.error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "feature_results": self.feature_results,
            "total_pass": self.total_pass,
            "total_fail": self.total_fail,
            "total_blocked": self.total_blocked,
            "error": self.error,
            "timestamp": _now_iso(),
        }


class Phase4aResult:
    """Structured result of Phase 4a (Failure Catalog)."""

    def __init__(self) -> None:
        self.status: str = "CATALOG_FAILED"
        self.catalog: list[dict[str, Any]] = []
        self.stats: dict[str, int] = {}
        self.error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "catalog": self.catalog,
            "stats": self.stats,
            "error": self.error,
            "timestamp": _now_iso(),
        }


# ── Phase 1 helpers ──────────────────────────────────────────────────────────


def build_discovery_prompt(
    app_url: str,
    credentials: dict[str, Any] | None,
    screenshot_dir: str,
) -> str:
    """Build the agent prompt for Phase 1 discovery.

    The agent browses the app with no spec knowledge and inventories
    what it finds.
    """
    login_block = ""
    if credentials:
        email = credentials.get("email", "")
        password = credentials.get("password", "")
        login_block = (
            f"\n\nFirst, log in to the application using these credentials:\n"
            f"  Email: {email}\n"
            f"  Password: {password}\n"
            f"After logging in, begin systematic browsing.\n"
        )

    return (
        f"You are a QA discovery agent. Browse the web application at {app_url} "
        f"systematically using Playwright."
        f"{login_block}"
        f"\n\nInstructions:\n"
        f"- Visit every discoverable page by following navigation links, buttons, "
        f"sidebar items, and menu entries.\n"
        f"- On each page: inventory all interactive elements (buttons, links, forms, "
        f"inputs, dropdowns), note any console errors, note any visual issues "
        f"(broken layouts, missing images, overlapping text).\n"
        f"- Take a screenshot of each distinct page and save it to: {screenshot_dir}\n"
        f"- Maximum 20 routes. If you discover more than 20 distinct routes, stop "
        f"and note \"discovered 20+ routes, stopped at limit\".\n"
        f"- Maximum 5 minutes of browsing.\n"
        f"- Do NOT assume anything about what should exist. Report only what you "
        f"actually observe.\n"
        f"\n"
        f"Output your findings as a single JSON block fenced with ``` markers, "
        f"using this exact schema:\n"
        f"```json\n"
        f'{{\n'
        f'  "routes_found": [\n'
        f'    {{\n'
        f'      "url": "/path",\n'
        f'      "screenshot_path": "discovery/page.png",\n'
        f'      "interactive_elements": ["button:Submit", "link:Home"],\n'
        f'      "console_errors": [],\n'
        f'      "visual_issues": []\n'
        f'    }}\n'
        f'  ],\n'
        f'  "navigation_graph": {{"/": ["/dashboard"]}},\n'
        f'  "global_issues": [],\n'
        f'  "unreachable_dead_ends": []\n'
        f'}}\n'
        f"```\n"
    )


def parse_discovery_output(raw_output: str) -> dict[str, Any] | None:
    """Extract and validate the discovery JSON from agent output.

    Looks for a fenced JSON code block first, then tries the full output
    as inline JSON.  Returns None if parsing or validation fails.
    """
    # Try fenced code block first
    fence_pattern = re.compile(r"```(?:json)?\s*\n?(.*?)```", re.DOTALL)
    match = fence_pattern.search(raw_output)
    candidate = match.group(1).strip() if match else None

    parsed: dict[str, Any] | None = None

    if candidate:
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                parsed = obj
        except (json.JSONDecodeError, ValueError):
            pass

    # Fallback: try to find a JSON object in the raw output
    if parsed is None:
        # Look for the outermost { ... } containing routes_found
        brace_start = raw_output.find("{")
        if brace_start != -1:
            # Find matching closing brace
            depth = 0
            for i in range(brace_start, len(raw_output)):
                if raw_output[i] == "{":
                    depth += 1
                elif raw_output[i] == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            obj = json.loads(raw_output[brace_start : i + 1])
                            if isinstance(obj, dict):
                                parsed = obj
                        except (json.JSONDecodeError, ValueError):
                            pass
                        break

    if parsed is None:
        return None

    # Validate required keys
    if "routes_found" not in parsed or not isinstance(parsed["routes_found"], list):
        return None
    if "navigation_graph" not in parsed or not isinstance(parsed["navigation_graph"], dict):
        return None

    return parsed


# ── Phase 2 helpers ──────────────────────────────────────────────────────────

_VALID_STATUSES = {"FOUND", "MISSING", "PARTIAL", "DRIFTED", "UNEXPECTED"}


def build_ac_generation_prompt(
    roadmap_content: str,
    feature_specs: dict[str, str],
    discovery_inventory: dict[str, Any],
) -> str:
    """Build the agent prompt for Phase 2a: Spec-Based AC Writer.

    Instructs the agent to compare specs against discovery inventory,
    classify each feature, and generate Playwright-testable acceptance criteria.
    """
    specs_block = ""
    for name, content in feature_specs.items():
        specs_block += f"\n--- {name} ---\n{content}\n"

    discovery_json = json.dumps(discovery_inventory, indent=2)

    return (
        "You are a QA acceptance-criteria writer. Your job is to compare "
        "feature specifications against a discovery inventory (what actually "
        "exists in the running application) and produce testable acceptance "
        "criteria.\n\n"
        "## Roadmap\n\n"
        f"{roadmap_content}\n\n"
        "## Feature Specifications\n"
        f"{specs_block}\n\n"
        "## Discovery Inventory (from Phase 1)\n\n"
        f"```json\n{discovery_json}\n```\n\n"
        "## Instructions\n\n"
        "For each feature in the roadmap that is marked as built, compare "
        "its spec against the discovery inventory. Classify the match using "
        "exactly one of these statuses:\n\n"
        "- **FOUND**: Feature's route and primary UI elements exist in "
        "discovery and match spec expectations.\n"
        "- **MISSING**: Feature is in the roadmap/specs but has no "
        "corresponding route or UI elements in discovery.\n"
        "- **PARTIAL**: Route exists but only some spec'd behaviors/elements "
        "are present.\n"
        "- **DRIFTED**: Feature exists in discovery but doesn't match spec "
        "(different route, different UI pattern, renamed elements).\n\n"
        "For each feature, write concrete Playwright-testable acceptance "
        "criteria. No more than 10 criteria per feature. Each criterion must "
        "be verifiable through browser interaction alone — no file system "
        "access, no code inspection.\n\n"
        "For FOUND and PARTIAL features, ground criteria in actual discovered "
        "routes/elements. For MISSING features, write criteria based on spec "
        "alone. For DRIFTED features, write criteria per the spec's intent "
        "and include a drift_notes field.\n\n"
        "Additionally, identify any routes or interactive elements in the "
        "discovery inventory that do NOT correspond to any feature in the "
        "roadmap/specs. Include these as entries with status 'UNEXPECTED'.\n\n"
        "For each criterion, set targets_present_element to true if the "
        "element/route exists in the discovery inventory, or false if the "
        "criterion tests for something not found in discovery (these are "
        "likely to fail or be blocked during validation).\n\n"
        "Output a JSON array (fenced with ``` markers) of feature objects "
        "using this exact schema:\n"
        "```json\n"
        "[\n"
        "  {\n"
        '    "feature": "Feature Name",\n'
        '    "status": "FOUND|MISSING|PARTIAL|DRIFTED|UNEXPECTED",\n'
        '    "route": "/path",\n'
        '    "match_notes": "description of match quality",\n'
        '    "criteria": [\n'
        "      {\n"
        '        "id": "AC-001",\n'
        '        "description": "What is being tested",\n'
        '        "targets_present_element": true,\n'
        '        "steps": ["step 1", "step 2"],\n'
        '        "expected_outcome": "What should happen"\n'
        "      }\n"
        "    ],\n"
        '    "drift_notes": null\n'
        "  }\n"
        "]\n"
        "```\n"
    )


def detect_coverage_gaps(
    features: list[dict[str, Any]],
    discovery_inventory: dict[str, Any],
) -> dict[str, Any]:
    """Mechanically detect gaps between AC criteria and discovery inventory.

    Pure Python — no agent call needed.  Compares discovery routes against
    criteria coverage and flags criteria targeting absent elements.

    Returns a dict with 'uncovered_routes' and 'likely_broken' lists.
    """
    # Collect all routes referenced in criteria
    covered_routes: set[str] = set()
    for feat in features:
        route = feat.get("route")
        if isinstance(route, str) and route:
            covered_routes.add(route)
        for criterion in feat.get("criteria", []):
            if isinstance(criterion, dict):
                for step in criterion.get("steps", []):
                    if isinstance(step, str) and step.lower().startswith("navigate to "):
                        # Extract route from "Navigate to /path"
                        parts = step.split(maxsplit=2)
                        if len(parts) >= 3:
                            covered_routes.add(parts[2].strip())

    # Collect all routes from discovery
    discovered_routes: set[str] = set()
    routes_found = discovery_inventory.get("routes_found", [])
    if isinstance(routes_found, list):
        for route_entry in routes_found:
            if isinstance(route_entry, dict):
                url = route_entry.get("url", "")
                if isinstance(url, str) and url:
                    discovered_routes.add(url)

    # Uncovered routes: in discovery but not in any criterion
    uncovered = sorted(discovered_routes - covered_routes)

    # Likely broken: criteria where targets_present_element is False
    likely_broken: list[dict[str, str]] = []
    for feat in features:
        feat_name = feat.get("feature", "unknown")
        for criterion in feat.get("criteria", []):
            if isinstance(criterion, dict):
                if criterion.get("targets_present_element") is False:
                    likely_broken.append({
                        "criterion_id": str(criterion.get("id", "")),
                        "feature": str(feat_name),
                        "reason": "targets_present_element is False",
                    })

    return {
        "uncovered_routes": uncovered,
        "likely_broken": likely_broken,
    }


def parse_ac_output(raw_output: str) -> list[dict[str, Any]] | None:
    """Extract and validate the AC JSON array from agent output.

    Looks for a fenced JSON code block first, then tries to find an inline
    JSON array.  Validates each feature dict has the required fields.
    Returns None if parsing or validation fails.
    """
    # Try fenced code block first
    fence_pattern = re.compile(r"```(?:json)?\s*\n?(.*?)```", re.DOTALL)
    match = fence_pattern.search(raw_output)
    candidate = match.group(1).strip() if match else None

    parsed: list[dict[str, Any]] | None = None

    if candidate:
        try:
            obj = json.loads(candidate)
            if isinstance(obj, list):
                parsed = obj
        except (json.JSONDecodeError, ValueError):
            pass

    # Fallback: try to find a JSON array in the raw output
    if parsed is None:
        bracket_start = raw_output.find("[")
        if bracket_start != -1:
            depth = 0
            for i in range(bracket_start, len(raw_output)):
                if raw_output[i] == "[":
                    depth += 1
                elif raw_output[i] == "]":
                    depth -= 1
                    if depth == 0:
                        try:
                            obj = json.loads(raw_output[bracket_start : i + 1])
                            if isinstance(obj, list):
                                parsed = obj
                        except (json.JSONDecodeError, ValueError):
                            pass
                        break

    if parsed is None:
        return None

    # Validate each feature dict
    for item in parsed:
        if not isinstance(item, dict):
            return None
        if not isinstance(item.get("feature"), str):
            return None
        status = item.get("status")
        if not isinstance(status, str) or status not in _VALID_STATUSES:
            return None
        if not isinstance(item.get("criteria"), list):
            return None

    return parsed


# ── Phase 3 helpers ──────────────────────────────────────────────────────

_VALID_PLAYWRIGHT_STATUSES = {"PASS", "FAIL", "BLOCKED"}


def build_playwright_prompt(
    app_url: str,
    feature: dict[str, Any],
    credentials: dict[str, Any] | None,
    screenshot_dir: str,
) -> str:
    """Build the agent prompt for Phase 3: Playwright Validation.

    Instructs the agent to test ONE feature's acceptance criteria using
    Playwright against the running app.
    """
    login_block = ""
    if credentials:
        email = credentials.get("email", "")
        password = credentials.get("password", "")
        login_block = (
            f"\n\nBefore testing, log in to the application:\n"
            f"  Email: {email}\n"
            f"  Password: {password}\n"
            f"Complete the login flow and verify you are authenticated "
            f"before proceeding to test criteria.\n"
        )

    feature_name = feature.get("feature", "Unknown")
    criteria = feature.get("criteria", [])
    criteria_block = ""
    for criterion in criteria:
        if isinstance(criterion, dict):
            cid = criterion.get("id", "???")
            desc = criterion.get("description", "")
            steps = criterion.get("steps", [])
            expected = criterion.get("expected_outcome", "")
            steps_text = "\n".join(f"      {i+1}. {s}" for i, s in enumerate(steps))
            criteria_block += (
                f"\n  - **{cid}**: {desc}\n"
                f"    Steps:\n{steps_text}\n"
                f"    Expected: {expected}\n"
            )

    return (
        f"You are a QA validation agent. Test the feature \"{feature_name}\" "
        f"against the running application at {app_url} using Playwright."
        f"{login_block}"
        f"\n\n## Acceptance Criteria to Test\n"
        f"{criteria_block}"
        f"\n## Instructions\n\n"
        f"For each criterion above:\n"
        f"1. Navigate to the appropriate route.\n"
        f"2. Follow the steps exactly as described.\n"
        f"3. Check whether the expected outcome is met.\n"
        f"4. Report the result as VALIDATION_PASS, VALIDATION_FAIL, or "
        f"VALIDATION_BLOCKED.\n"
        f"5. On failure or block, take a screenshot and save it to: "
        f"{screenshot_dir}\n\n"
        f"**Retry policy:** If a criterion fails due to a transient issue "
        f"(element not loaded yet, page still rendering, click didn't land), "
        f"retry up to max 3 times before marking it as failed.\n\n"
        f"**Infrastructure failure:** If Playwright itself crashes or becomes "
        f"unresponsive, report INFRA_FAILURE for all remaining criteria and "
        f"stop testing.\n\n"
        f"Output your results as a single JSON object fenced with ``` markers, "
        f"using this exact schema:\n"
        f"```json\n"
        f'{{\n'
        f'  "results": [\n'
        f'    {{\n'
        f'      "criterion_id": "AC-001",\n'
        f'      "status": "PASS",\n'
        f'      "description": "What was tested",\n'
        f'      "screenshot_path": "",\n'
        f'      "error": ""\n'
        f'    }}\n'
        f'  ]\n'
        f'}}\n'
        f"```\n"
    )


def parse_playwright_output(raw_output: str) -> list[dict[str, Any]] | None:
    """Extract and validate Playwright validation results from agent output.

    Looks for a fenced JSON code block first, then tries inline JSON.
    Returns the list of per-criterion results, or None if parsing or
    validation fails.
    """
    # Try fenced code block first
    fence_pattern = re.compile(r"```(?:json)?\s*\n?(.*?)```", re.DOTALL)
    match = fence_pattern.search(raw_output)
    candidate = match.group(1).strip() if match else None

    parsed: dict[str, Any] | None = None

    if candidate:
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                parsed = obj
        except (json.JSONDecodeError, ValueError):
            pass

    # Fallback: try to find a JSON object in the raw output
    if parsed is None:
        brace_start = raw_output.find("{")
        if brace_start != -1:
            depth = 0
            for i in range(brace_start, len(raw_output)):
                if raw_output[i] == "{":
                    depth += 1
                elif raw_output[i] == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            obj = json.loads(raw_output[brace_start : i + 1])
                            if isinstance(obj, dict):
                                parsed = obj
                        except (json.JSONDecodeError, ValueError):
                            pass
                        break

    if parsed is None:
        return None

    # Must have a "results" key with a list
    results = parsed.get("results")
    if not isinstance(results, list):
        return None

    # Validate each result entry
    for item in results:
        if not isinstance(item, dict):
            return None
        if not isinstance(item.get("criterion_id"), str):
            return None
        status = item.get("status")
        if not isinstance(status, str) or status not in _VALID_PLAYWRIGHT_STATUSES:
            return None

    return results


# ── Phase 4a helpers ─────────────────────────────────────────────────────


def build_failure_catalog(
    phase_3_results: list[dict[str, Any]],
    phase_2_features: list[dict[str, Any]],
    run_id: str,
) -> dict[str, Any]:
    """Build a structured failure catalog from Phase 3 results.

    Pure Python — no agent call needed.  Collects all FAIL and BLOCKED
    criteria from Phase 3, enriches them with Phase 2 metadata (feature
    name, feature status, expected_outcome), and produces a catalog with
    stats.

    Same mechanical pattern as detect_coverage_gaps().
    """
    # Build lookup: criterion_id → {feature, feature_status, expected_outcome}
    criterion_lookup: dict[str, dict[str, str]] = {}
    for feat in phase_2_features:
        feat_name = str(feat.get("feature", "unknown"))
        feat_status = str(feat.get("status", "unknown"))
        for criterion in feat.get("criteria", []):
            if isinstance(criterion, dict):
                cid = str(criterion.get("id", ""))
                if cid:
                    criterion_lookup[cid] = {
                        "feature": feat_name,
                        "feature_status": feat_status,
                        "expected_outcome": str(
                            criterion.get("expected_outcome", "")
                        ),
                    }

    # Iterate Phase 3 results, collect failures and blocked
    catalog: list[dict[str, Any]] = []
    total_criteria = 0
    passed = 0
    failed = 0
    blocked = 0
    fail_seq = 0
    block_seq = 0

    for feature_result in phase_3_results:
        for cr in feature_result.get("criteria_results", []):
            if not isinstance(cr, dict):
                continue
            total_criteria += 1
            status = str(cr.get("status", ""))
            cid = str(cr.get("criterion_id", ""))

            if status == "PASS":
                passed += 1
                continue

            # Lookup Phase 2 metadata
            meta = criterion_lookup.get(cid, {})

            if status == "FAIL":
                failed += 1
                fail_seq += 1
                entry_id = f"FAIL-{fail_seq:03d}"
            else:
                # BLOCKED or anything else
                blocked += 1
                block_seq += 1
                entry_id = f"BLOCK-{block_seq:03d}"

            # actual: prefer error field, fall back to description
            error_val = str(cr.get("error", ""))
            actual = error_val if error_val else str(cr.get("description", ""))

            catalog.append({
                "id": entry_id,
                "criterion_id": cid,
                "feature": meta.get("feature", "unknown"),
                "feature_status": meta.get("feature_status", "unknown"),
                "result": "FAIL" if status == "FAIL" else "BLOCKED",
                "description": str(cr.get("description", "")),
                "expected": meta.get("expected_outcome", ""),
                "actual": actual,
                "screenshot": str(cr.get("screenshot_path", "")),
            })

    stats = {
        "total_criteria": total_criteria,
        "passed": passed,
        "failed": failed,
        "blocked": blocked,
    }

    return {
        "run_id": run_id,
        "catalog": catalog,
        "stats": stats,
    }


def run_phase_0(
    project_dir: Path,
    timeout: float = 60.0,
) -> Phase0Result:
    """Execute Phase 0: Runtime Bootstrap.

    1. Detect package manager
    2. Run production build
    3. Start dev server
    4. Health check
    5. Auth bootstrap (if seed script exists)
    """
    result = Phase0Result()

    # 1. Package manager detection
    pm = detect_package_manager(project_dir)
    result.package_manager = pm
    logger.info("Detected package manager: %s", pm)

    # 2. Production build
    logger.info("Running production build: %s run build", pm)
    try:
        build = subprocess.run(
            [pm, "run", "build"],
            capture_output=True,
            text=True,
            cwd=str(project_dir),
            timeout=300,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        result.error = f"Build command failed to execute: {exc}"
        logger.error("Build failed: %s", result.error)
        return result

    result.build_output = build.stdout + build.stderr
    if build.returncode != 0:
        result.error = (
            f"Production build failed (exit {build.returncode}): "
            f"{build.stderr.strip()[:1000]}"
        )
        logger.error("Build failed: %s", result.error)
        return result

    logger.info("Production build succeeded")

    # 3. Dev server start
    dev_cmd_name = detect_dev_command(project_dir)
    if dev_cmd_name is None:
        result.error = (
            "No dev command found in package.json scripts "
            "(looked for: dev, start, serve)"
        )
        logger.error(result.error)
        return result

    result.dev_command = dev_cmd_name
    logger.info("Starting dev server: %s run %s", pm, dev_cmd_name)

    try:
        server_proc = subprocess.Popen(
            [pm, "run", dev_cmd_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=str(project_dir),
        )
    except OSError as exc:
        result.error = f"Failed to start dev server: {exc}"
        logger.error(result.error)
        return result

    result.server_process = server_proc

    # 4. Port detection + health check
    port: int | None = None

    # Give the server a moment to emit its URL
    detection_deadline = time.monotonic() + min(timeout / 2, 15.0)
    collected_output = ""
    while time.monotonic() < detection_deadline:
        if server_proc.stdout is not None and server_proc.stdout.readable():
            # Non-blocking read via select or small timeout
            import select
            ready, _, _ = select.select([server_proc.stdout], [], [], 1.0)
            if ready:
                chunk = server_proc.stdout.readline()
                if chunk:
                    collected_output += chunk
                    logger.debug("Dev server: %s", chunk.rstrip())
                    parsed = parse_port_from_output(collected_output)
                    if parsed is not None:
                        port = parsed
                        break
        else:
            time.sleep(0.5)

        # Check if process died
        if server_proc.poll() is not None:
            rest = ""
            if server_proc.stdout is not None:
                rest = server_proc.stdout.read()
            collected_output += rest
            result.dev_output = collected_output
            result.error = (
                f"Dev server exited prematurely (code {server_proc.returncode}): "
                f"{collected_output.strip()[:500]}"
            )
            result.server_process = None
            logger.error(result.error)
            return result

    result.dev_output = collected_output

    # If we didn't parse a port, try common ports
    if port is None:
        logger.info("Could not detect port from output, trying common ports")
        for candidate_port in _COMMON_PORTS:
            url = f"http://localhost:{candidate_port}"
            try:
                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=2) as resp:
                    if resp.status == 200:
                        port = candidate_port
                        break
            except (urllib.error.URLError, OSError, ValueError):
                continue

    if port is None:
        result.error = "Could not detect dev server port"
        logger.error(result.error)
        return result

    result.port = port
    result.url = f"http://localhost:{port}"
    logger.info("Detected dev server at %s", result.url)

    # Health check with exponential backoff
    logger.info("Running health check (timeout: %.0fs)", timeout)
    if not health_check(result.url, timeout=timeout):
        result.error = (
            f"Health check failed: {result.url} did not return HTTP 200 "
            f"within {timeout}s"
        )
        logger.error(result.error)
        return result

    result.status = "RUNTIME_READY"
    logger.info("RUNTIME_READY: %s", result.url)

    # 5. Auth bootstrap
    seed_script = _find_seed_script(project_dir)
    if seed_script is None:
        result.auth_status = "AUTH_SETUP_SKIPPED"
        logger.info("No QA seed script found — skipping auth bootstrap")
    else:
        logger.info("Running QA seed script: %s", seed_script)
        ok, creds, err = _run_seed_script(seed_script, project_dir)
        if ok and creds is not None:
            result.auth_status = "AUTH_READY"
            result.auth_email = str(creds.get("email", ""))
            # Write credentials
            creds_path = project_dir / ".sdd-state" / "qa-credentials.json"
            _atomic_write_json(creds_path, creds)
            logger.info(
                "AUTH_READY: %s",
                result.auth_email,
            )
        else:
            result.auth_status = "AUTH_SETUP_FAILED"
            result.error = err
            logger.warning("AUTH_SETUP_FAILED: %s — continuing unauthenticated", err)

    return result


# ── ValidationPipeline ───────────────────────────────────────────────────────


class ValidationPipeline:
    """Manages the full post-campaign validation lifecycle."""

    def __init__(
        self,
        project_dir: Path,
        flush_mode: str = "auto",
        validation_timeout: float = 60.0,
        resume: bool = False,
    ) -> None:
        self.project_dir = project_dir.resolve()
        self.flush_mode = flush_mode
        self.validation_timeout = validation_timeout
        self.resume = resume

        self.run_id = f"val-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"

        # State dir
        self.state_dir = self.project_dir / ".sdd-state"
        self.state_dir.mkdir(parents=True, exist_ok=True)

        # Log dir
        self.log_dir = Path("logs") / "validation" / self.run_id
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # State persistence
        self.state = ValidationState(
            self.state_dir / "validation-state.json",
            self.run_id,
        )

        # Document registry
        self.doc_registry = DocumentRegistry(
            self.state_dir / "validation-docs.json",
            self.run_id,
            self.flush_mode,
        )

        # Server process reference (for cleanup)
        self._server_proc: subprocess.Popen[str] | None = None
        self._seed_script: Path | None = None

        # Register cleanup
        atexit.register(self._cleanup)

    def _cleanup(self) -> None:
        """Kill dev server, teardown QA account, wipe credentials."""
        logger.info("Running cleanup")

        # Kill dev server
        if self._server_proc is not None:
            logger.info("Terminating dev server (PID %d)", self._server_proc.pid)
            try:
                self._server_proc.terminate()
                try:
                    self._server_proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self._server_proc.kill()
            except OSError:
                pass
            self._server_proc = None

        # Teardown QA account
        if self._seed_script is not None:
            logger.info("Running QA teardown: %s --teardown", self._seed_script)
            _run_seed_script(self._seed_script, self.project_dir, teardown=True)

        # Wipe credentials
        creds_path = self.state_dir / "qa-credentials.json"
        if creds_path.exists():
            logger.info("Wiping QA credentials")
            try:
                creds_path.unlink()
            except OSError:
                pass

    def _setup_logging(self) -> None:
        """Configure structured, timestamped logging."""
        log_file = self.log_dir / "pipeline.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)

        handler = logging.FileHandler(str(log_file))
        handler.setLevel(logging.DEBUG)
        fmt = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
        handler.setFormatter(fmt)

        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.DEBUG)

        # Also log to stderr
        console = logging.StreamHandler(sys.stderr)
        console.setLevel(logging.INFO)
        console.setFormatter(fmt)
        root_logger.addHandler(console)

    def _run_phase_0(self) -> int:
        """Execute Phase 0: Runtime Bootstrap."""
        phase = "0"
        if self.resume and self.state.is_complete(phase):
            logger.info("Phase 0 already complete — skipping (resume mode)")
            return EXIT_ALL_PASS

        logger.info("═══ Phase 0: Runtime Bootstrap ═══")
        phase_result = run_phase_0(
            self.project_dir,
            timeout=self.validation_timeout,
        )

        # Track server for cleanup
        self._server_proc = phase_result.server_process
        self._seed_script = _find_seed_script(self.project_dir)

        # Write runtime report
        report = phase_result.to_dict()
        report_json = json.dumps(report, indent=2) + "\n"
        report_path = self.log_dir / "phase-0" / "runtime-report.v1.json"

        self.doc_registry.register(
            doc_id="runtime-report",
            phase=phase,
            path=report_path,
            content=report_json,
        )

        if phase_result.status == "RUNTIME_FAILED":
            logger.error(
                "Phase 0 FAILED: %s", phase_result.error,
            )
            self.state.save()
            return EXIT_RUNTIME_FAILED

        self.state.mark_complete(phase)
        logger.info("Phase 0 complete: %s", phase_result.status)
        return EXIT_ALL_PASS

    def _run_phase_1(self) -> int:
        """Execute Phase 1: Discovery Agent."""
        phase = "1"
        if self.resume and self.state.is_complete(phase):
            logger.info("Phase 1 already complete — skipping (resume mode)")
            return EXIT_ALL_PASS

        logger.info("═══ Phase 1: Discovery Agent ═══")

        # Phase 0 must have completed — we need the app URL
        if not self.state.is_complete("0"):
            logger.error("Phase 1 requires Phase 0 to be complete")
            return EXIT_INFRA_FAILURE

        # Read app URL from the Phase 0 runtime report
        report_dir = self.log_dir / "phase-0"
        app_url: str | None = None
        if report_dir.exists():
            for p in sorted(report_dir.glob("runtime-report.v*.json"), reverse=True):
                data = _read_json(p)
                if isinstance(data, dict) and data.get("url"):
                    app_url = str(data["url"])
                    break

        if not app_url:
            logger.error("Could not find app URL from Phase 0 runtime report")
            return EXIT_INFRA_FAILURE

        # Load credentials if available
        creds_path = self.project_dir / ".sdd-state" / "qa-credentials.json"
        credentials: dict[str, Any] | None = None
        if creds_path.exists():
            credentials = _read_json(creds_path)
            if not isinstance(credentials, dict):
                credentials = None

        # Create screenshot directory
        screenshot_dir = self.log_dir / "phase-1" / "screenshots"
        screenshot_dir.mkdir(parents=True, exist_ok=True)

        # Build prompt
        prompt = build_discovery_prompt(app_url, credentials, str(screenshot_dir))

        # Invoke the discovery agent
        phase1_result = Phase1Result()
        phase1_result.screenshot_dir = str(screenshot_dir)

        start_ms = int(time.monotonic() * 1000)
        try:
            claude_result = run_claude(
                ["-p", "--dangerously-skip-permissions", prompt],
                cwd=self.project_dir,
                timeout=300,
            )
        except AgentTimeoutError as exc:
            elapsed = int(time.monotonic() * 1000) - start_ms
            phase1_result.error = f"Discovery agent timed out: {exc}"
            phase1_result.agent_duration_ms = elapsed
            logger.error("Phase 1 FAILED: %s", phase1_result.error)
            self._write_phase1_report(phase1_result)
            return EXIT_PARTIAL
        except ClaudeOutputError as exc:
            elapsed = int(time.monotonic() * 1000) - start_ms
            phase1_result.error = f"Discovery agent output error: {exc}"
            phase1_result.agent_duration_ms = elapsed
            logger.error("Phase 1 FAILED: %s", phase1_result.error)
            self._write_phase1_report(phase1_result)
            return EXIT_PARTIAL

        elapsed = int(time.monotonic() * 1000) - start_ms
        phase1_result.agent_duration_ms = elapsed

        # Parse the discovery output
        parsed = parse_discovery_output(claude_result.output)
        if parsed is None:
            phase1_result.error = (
                "Failed to parse discovery JSON from agent output. "
                f"Raw output (first 500 chars): {claude_result.output[:500]}"
            )
            logger.error("Phase 1 FAILED: %s", phase1_result.error)
            self._write_phase1_report(phase1_result)
            return EXIT_PARTIAL

        # Populate result from parsed discovery
        phase1_result.status = "DISCOVERY_COMPLETE"
        phase1_result.routes_found = parsed.get("routes_found", [])
        nav_graph = parsed.get("navigation_graph", {})
        phase1_result.navigation_graph = nav_graph if isinstance(nav_graph, dict) else {}
        global_issues = parsed.get("global_issues", [])
        phase1_result.global_issues = global_issues if isinstance(global_issues, list) else []
        dead_ends = parsed.get("unreachable_dead_ends", [])
        phase1_result.unreachable_dead_ends = dead_ends if isinstance(dead_ends, list) else []
        phase1_result.route_count = len(phase1_result.routes_found)

        # Write discovery inventory
        self._write_phase1_report(phase1_result)

        self.state.mark_complete(phase)
        logger.info(
            "Phase 1 complete: %s (%d routes found)",
            phase1_result.status,
            phase1_result.route_count,
        )
        return EXIT_ALL_PASS

    def _write_phase1_report(self, result: Phase1Result) -> None:
        """Write Phase 1 discovery inventory to the doc registry."""
        report_json = json.dumps(result.to_dict(), indent=2) + "\n"
        version = self.doc_registry._next_version("discovery-inventory")
        report_path = self.log_dir / "phase-1" / f"discovery-inventory.v{version}.json"
        self.doc_registry.register(
            doc_id="discovery-inventory",
            phase="1",
            path=report_path,
            content=report_json,
        )

    def _load_specs(self) -> tuple[str, dict[str, str]]:
        """Load roadmap and feature specs from .specs/ directory.

        Returns (roadmap_content, feature_specs) where feature_specs maps
        filename to content.  Returns empty values if files don't exist.
        """
        roadmap_path = self.project_dir / ".specs" / "roadmap.md"
        roadmap_content = ""
        if roadmap_path.exists():
            roadmap_content = roadmap_path.read_text()

        feature_specs: dict[str, str] = {}
        features_dir = self.project_dir / ".specs" / "features"
        if features_dir.is_dir():
            for p in sorted(features_dir.rglob("*")):
                if p.is_file() and (
                    p.name.endswith(".feature.md") or p.name.endswith(".md")
                ):
                    feature_specs[p.name] = p.read_text()

        return roadmap_content, feature_specs

    def _read_discovery_inventory(self) -> dict[str, Any] | None:
        """Read the latest discovery inventory from Phase 1 output."""
        phase1_dir = self.log_dir / "phase-1"
        if not phase1_dir.exists():
            return None
        for p in sorted(phase1_dir.glob("discovery-inventory.v*.json"), reverse=True):
            data = _read_json(p)
            if isinstance(data, dict):
                return data
        return None

    def _run_phase_2a(self) -> list[dict[str, Any]] | None:
        """Execute Phase 2a: Spec-Based AC Writer.

        Returns the parsed features list for Phase 2b, or None on failure.
        """
        logger.info("═══ Phase 2a: Spec-Based AC Writer ═══")

        # Phase 1 must have completed — we need the discovery inventory
        if not self.state.is_complete("1"):
            logger.error("Phase 2a requires Phase 1 to be complete")
            return None

        # Read discovery inventory
        discovery = self._read_discovery_inventory()
        if discovery is None:
            logger.error("Could not read discovery inventory from Phase 1")
            return None

        # Load specs
        roadmap_content, feature_specs = self._load_specs()

        # Build prompt
        prompt = build_ac_generation_prompt(
            roadmap_content, feature_specs, discovery,
        )

        # Invoke the AC generation agent
        try:
            claude_result = run_claude(
                ["-p", "--dangerously-skip-permissions", prompt],
                cwd=self.project_dir,
                timeout=600,
            )
        except (AgentTimeoutError, ClaudeOutputError) as exc:
            logger.error("Phase 2a agent failed: %s", exc)
            return None

        # Parse the output
        features = parse_ac_output(claude_result.output)
        if features is None:
            logger.error(
                "Failed to parse AC output from agent. "
                "Raw output (first 500 chars): %s",
                claude_result.output[:500],
            )
            return None

        # Write acceptance criteria
        ac_json = json.dumps(features, indent=2) + "\n"
        version = self.doc_registry._next_version("acceptance-criteria")
        ac_path = (
            self.log_dir / "phase-2a" / f"acceptance-criteria.v{version}.json"
        )
        self.doc_registry.register(
            doc_id="acceptance-criteria",
            phase="2a",
            path=ac_path,
            content=ac_json,
        )

        self.state.mark_complete("2a")
        total = sum(len(f.get("criteria", [])) for f in features)
        logger.info(
            "Phase 2a complete: %d features, %d total criteria",
            len(features),
            total,
        )
        return features

    def _run_phase_2b(
        self, phase_2a_features: list[dict[str, Any]],
    ) -> Phase2Result:
        """Execute Phase 2b: Mechanical Gap Detection.

        Uses pure Python set operations to find uncovered routes and
        likely-broken criteria.  No agent call — instant execution.
        """
        logger.info("═══ Phase 2b: Mechanical Gap Detection ═══")

        result = Phase2Result()
        result.features = phase_2a_features
        result.total_criteria_count = sum(
            len(f.get("criteria", [])) for f in phase_2a_features
        )

        # Read discovery inventory
        discovery = self._read_discovery_inventory()
        if discovery is None:
            logger.warning("Could not read discovery inventory for gap detection")
            result.status = "AC_GENERATION_COMPLETE"
            self.state.mark_complete("2b")
            return result

        # Run mechanical gap detection
        gap_report = detect_coverage_gaps(phase_2a_features, discovery)
        result.gap_report = gap_report

        uncovered = gap_report.get("uncovered_routes", [])
        likely_broken = gap_report.get("likely_broken", [])
        logger.info(
            "Gap detection: %d uncovered routes, %d likely-broken criteria",
            len(uncovered),
            len(likely_broken),
        )

        # Write gap report
        gap_json = json.dumps(gap_report, indent=2) + "\n"
        version = self.doc_registry._next_version("gap-report")
        gap_path = self.log_dir / "phase-2b" / f"gap-report.v{version}.json"
        self.doc_registry.register(
            doc_id="gap-report",
            phase="2b",
            path=gap_path,
            content=gap_json,
        )

        result.status = "AC_GENERATION_COMPLETE"
        self.state.mark_complete("2b")
        logger.info("Phase 2b complete: %d total criteria", result.total_criteria_count)
        return result

    def _run_phase_2(self) -> Phase2Result:
        """Orchestrate Phase 2a + 2b.

        Handles the resume case: if 2a is complete but 2b is not,
        read 2a output from disk and run only 2b.
        """
        result = Phase2Result()

        phase_2a_features: list[dict[str, Any]] | None = None

        if self.resume and self.state.is_complete("2a"):
            logger.info("Phase 2a already complete — loading from disk (resume mode)")
            # Read the most recent 2a output from disk
            phase_2a_dir = self.log_dir / "phase-2a"
            if phase_2a_dir.exists():
                for p in sorted(
                    phase_2a_dir.glob("acceptance-criteria.v*.json"),
                    reverse=True,
                ):
                    data = _read_json(p)
                    if isinstance(data, list):
                        phase_2a_features = data
                        break
            if phase_2a_features is None:
                logger.error("Could not load Phase 2a output from disk for resume")
                result.error = "Phase 2a output not found on disk"
                return result
        else:
            phase_2a_features = self._run_phase_2a()
            if phase_2a_features is None:
                result.error = "Phase 2a failed"
                return result

        if self.resume and self.state.is_complete("2b"):
            logger.info("Phase 2b already complete — skipping (resume mode)")
            result.status = "AC_GENERATION_COMPLETE"
            result.features = phase_2a_features
            result.total_criteria_count = sum(
                len(f.get("criteria", [])) for f in phase_2a_features
            )
            return result

        return self._run_phase_2b(phase_2a_features)

    def _read_acceptance_criteria(self) -> list[dict[str, Any]] | None:
        """Read the latest acceptance criteria from Phase 2 output.

        Checks phase-2b dir first (has gap report alongside), falls back
        to phase-2a dir for acceptance-criteria.v*.json.
        """
        for subdir in ("phase-2b", "phase-2a"):
            phase_dir = self.log_dir / subdir
            if not phase_dir.exists():
                continue
            for p in sorted(
                phase_dir.glob("acceptance-criteria.v*.json"),
                reverse=True,
            ):
                data = _read_json(p)
                if isinstance(data, list):
                    return data
        return None

    def _run_phase_3(self) -> int:
        """Execute Phase 3: Playwright Validation.

        Tests each feature's acceptance criteria against the running app
        using one agent invocation per feature (sequential).
        Phase 3b is absorbed — UNEXPECTED features already have criteria
        in the Phase 2 output.
        """
        phase = "3"
        if self.resume and self.state.is_complete(phase):
            logger.info("Phase 3 already complete — skipping (resume mode)")
            return EXIT_ALL_PASS

        logger.info("═══ Phase 3: Playwright Validation ═══")

        # Phase 2a must have completed — we need acceptance criteria
        if not self.state.is_complete("2a"):
            logger.error("Phase 3 requires Phase 2a to be complete")
            return EXIT_INFRA_FAILURE

        # Read acceptance criteria
        features = self._read_acceptance_criteria()
        if features is None:
            logger.error("Could not read acceptance criteria from Phase 2")
            return EXIT_INFRA_FAILURE

        # Read app URL from Phase 0 runtime report
        report_dir = self.log_dir / "phase-0"
        app_url: str | None = None
        if report_dir.exists():
            for p in sorted(
                report_dir.glob("runtime-report.v*.json"), reverse=True,
            ):
                data = _read_json(p)
                if isinstance(data, dict) and data.get("url"):
                    app_url = str(data["url"])
                    break

        if not app_url:
            logger.error("Could not find app URL from Phase 0 runtime report")
            return EXIT_INFRA_FAILURE

        # Load credentials if available
        creds_path = self.project_dir / ".sdd-state" / "qa-credentials.json"
        credentials: dict[str, Any] | None = None
        if creds_path.exists():
            credentials = _read_json(creds_path)
            if not isinstance(credentials, dict):
                credentials = None

        # Iterate over each feature sequentially
        phase3_result = Phase3Result()
        any_ran = False

        for feature in features:
            feature_name = str(feature.get("feature", "unknown"))
            sanitized_name = re.sub(r"[^a-zA-Z0-9_-]", "_", feature_name).lower()
            screenshot_dir = self.log_dir / "phase-3" / sanitized_name
            screenshot_dir.mkdir(parents=True, exist_ok=True)

            criteria = feature.get("criteria", [])

            prompt = build_playwright_prompt(
                app_url, feature, credentials, str(screenshot_dir),
            )

            # Call agent with 5 minute timeout per feature
            try:
                claude_result = run_claude(
                    ["-p", "--dangerously-skip-permissions", prompt],
                    cwd=self.project_dir,
                    timeout=300,
                )
            except (AgentTimeoutError, ClaudeOutputError) as exc:
                logger.error(
                    "Phase 3 agent failed for feature '%s': %s",
                    feature_name, exc,
                )
                # Record all criteria as BLOCKED
                blocked_results: list[dict[str, Any]] = []
                for criterion in criteria:
                    if isinstance(criterion, dict):
                        cr = CriterionResult()
                        cr.criterion_id = str(criterion.get("id", ""))
                        cr.status = "BLOCKED"
                        cr.description = str(criterion.get("description", ""))
                        cr.error = f"Agent failure: {exc}"
                        blocked_results.append(cr.to_dict())
                phase3_result.feature_results.append({
                    "feature": feature_name,
                    "criteria_results": blocked_results,
                })
                phase3_result.total_blocked += len(blocked_results)
                continue

            # Parse output
            parsed = parse_playwright_output(claude_result.output)
            if parsed is None:
                logger.error(
                    "Failed to parse Playwright output for feature '%s'. "
                    "Raw (first 500 chars): %s",
                    feature_name,
                    claude_result.output[:500],
                )
                # Record all criteria as BLOCKED
                blocked_results = []
                for criterion in criteria:
                    if isinstance(criterion, dict):
                        cr = CriterionResult()
                        cr.criterion_id = str(criterion.get("id", ""))
                        cr.status = "BLOCKED"
                        cr.description = str(criterion.get("description", ""))
                        cr.error = "Failed to parse agent output"
                        blocked_results.append(cr.to_dict())
                phase3_result.feature_results.append({
                    "feature": feature_name,
                    "criteria_results": blocked_results,
                })
                phase3_result.total_blocked += len(blocked_results)
                continue

            # Collect results
            any_ran = True
            feature_criterion_results: list[dict[str, Any]] = []
            for item in parsed:
                cr = CriterionResult()
                cr.criterion_id = str(item.get("criterion_id", ""))
                cr.status = str(item.get("status", "BLOCKED"))
                cr.description = str(item.get("description", ""))
                cr.screenshot_path = str(item.get("screenshot_path", ""))
                cr.error = str(item.get("error", ""))
                feature_criterion_results.append(cr.to_dict())
                if cr.status == "PASS":
                    phase3_result.total_pass += 1
                elif cr.status == "FAIL":
                    phase3_result.total_fail += 1
                else:
                    phase3_result.total_blocked += 1

            phase3_result.feature_results.append({
                "feature": feature_name,
                "criteria_results": feature_criterion_results,
            })

        # Write validation report
        if any_ran:
            phase3_result.status = "VALIDATION_COMPLETE"
        else:
            phase3_result.status = "VALIDATION_FAILED"

        report_json = json.dumps(phase3_result.to_dict(), indent=2) + "\n"
        version = self.doc_registry._next_version("validation-results")
        report_path = (
            self.log_dir / "phase-3" / f"validation-results.v{version}.json"
        )
        self.doc_registry.register(
            doc_id="validation-results",
            phase="3",
            path=report_path,
            content=report_json,
        )

        # Mark both 3 and 3b complete (3b is absorbed)
        self.state.mark_complete("3")
        self.state.mark_complete("3b")

        logger.info(
            "Phase 3 complete: %s (pass=%d fail=%d blocked=%d)",
            phase3_result.status,
            phase3_result.total_pass,
            phase3_result.total_fail,
            phase3_result.total_blocked,
        )

        return EXIT_ALL_PASS if any_ran else EXIT_PARTIAL

    def _read_phase_3_results(self) -> dict[str, Any] | None:
        """Read the latest validation-results.v*.json from Phase 3 output."""
        phase3_dir = self.log_dir / "phase-3"
        if not phase3_dir.exists():
            return None
        for p in sorted(
            phase3_dir.glob("validation-results.v*.json"), reverse=True,
        ):
            data = _read_json(p)
            if isinstance(data, dict):
                return data
        return None

    def _run_phase_4a(self) -> Phase4aResult:
        """Execute Phase 4a: Failure Catalog.

        Collects FAIL/BLOCKED criteria from Phase 3, enriches with Phase 2
        metadata, produces structured catalog.  Pure Python — no agent call.
        """
        phase = "4a"
        result = Phase4aResult()

        if self.resume and self.state.is_complete(phase):
            logger.info("Phase 4a already complete — skipping (resume mode)")
            result.status = "CATALOG_COMPLETE"
            return result

        logger.info("═══ Phase 4a: Failure Catalog ═══")

        # Phase 3 must have completed
        if not self.state.is_complete("3"):
            result.error = "Phase 4a requires Phase 3 to be complete"
            logger.error(result.error)
            return result

        # Read Phase 3 results
        phase_3_data = self._read_phase_3_results()
        if phase_3_data is None:
            result.error = "Could not read Phase 3 results from disk"
            logger.error(result.error)
            return result

        # Read Phase 2 acceptance criteria
        phase_2_features = self._read_acceptance_criteria()
        if phase_2_features is None:
            result.error = "Could not read Phase 2 acceptance criteria"
            logger.error(result.error)
            return result

        # Generate run_id
        catalog_run_id = f"val-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"

        # Build the catalog
        catalog_data = build_failure_catalog(
            phase_3_data.get("feature_results", []),
            phase_2_features,
            catalog_run_id,
        )

        # Write catalog to disk
        catalog_json = json.dumps(catalog_data, indent=2) + "\n"
        version = self.doc_registry._next_version("failure-catalog")
        catalog_path = (
            self.log_dir / "phase-4a" / f"failure-catalog.v{version}.json"
        )
        self.doc_registry.register(
            doc_id="failure-catalog",
            phase="4a",
            path=catalog_path,
            content=catalog_json,
        )

        # Log stats
        stats = catalog_data.get("stats", {})
        logger.info(
            "Phase 4a complete: total=%d passed=%d failed=%d blocked=%d",
            stats.get("total_criteria", 0),
            stats.get("passed", 0),
            stats.get("failed", 0),
            stats.get("blocked", 0),
        )

        # Mark complete
        self.state.mark_complete(phase)

        result.status = "CATALOG_COMPLETE"
        result.catalog = catalog_data.get("catalog", [])
        result.stats = stats
        return result

    def _run_phase_stub(self, phase: str) -> int:
        """Stub for phases 1–5: raises NotImplementedError."""
        phase_names: dict[str, str] = {
            "1": "Discovery Agent",
            "2a": "Spec-Based AC Writer",
            "2b": "Gap Detection AC Writer",
            "3": "Playwright Validation",
            "3b": "Gap Tests",
            "4a": "Failure Catalog",
            "4b": "Root Cause Analysis",
            "5": "Fix Agents",
        }
        name = phase_names.get(phase, f"Phase {phase}")
        raise NotImplementedError(
            f"Phase {phase} ({name}) is not yet implemented. "
            f"See WIP/post-campaign-validation.md for the full spec."
        )

    def run(self) -> int:
        """Execute the full validation pipeline. Returns an exit code."""
        self._setup_logging()
        logger.info("Starting validation pipeline: run_id=%s", self.run_id)
        logger.info(
            "Config: project_dir=%s flush_mode=%s timeout=%.0fs resume=%s",
            self.project_dir,
            self.flush_mode,
            self.validation_timeout,
            self.resume,
        )

        # Phase 0
        exit_code = self._run_phase_0()
        if exit_code == EXIT_RUNTIME_FAILED:
            return exit_code

        # Phase 1
        exit_code = self._run_phase_1()
        if exit_code != EXIT_ALL_PASS:
            return exit_code

        # Phase 2 (AC Generation + Gap Detection)
        phase2_result = self._run_phase_2()
        if phase2_result.status == "AC_GENERATION_FAILED":
            logger.error("Phase 2 FAILED: %s", phase2_result.error)
            return EXIT_PARTIAL

        # Phase 3 (Playwright Validation — also marks 3b complete)
        exit_code = self._run_phase_3()
        if exit_code != EXIT_ALL_PASS:
            return exit_code

        # Phase 4a (Failure Catalog — mechanical, no agent)
        phase4a_result = self._run_phase_4a()
        if phase4a_result.status != "CATALOG_COMPLETE":
            logger.error("Phase 4a FAILED: %s", phase4a_result.error)
            return EXIT_PARTIAL

        # Phases 4b–5 (stubs)
        for phase in PHASE_ORDER[7:]:
            if self.resume and self.state.is_complete(phase):
                logger.info("Phase %s already complete — skipping", phase)
                continue
            try:
                self._run_phase_stub(phase)
            except NotImplementedError as exc:
                logger.info("Stopping: %s", exc)
                return EXIT_ALL_PASS

        return EXIT_ALL_PASS

    def flush_now(self) -> int:
        """Flush all pending documents (manual mode)."""
        return self.doc_registry.flush_pending()

    def flush_phase(self, phase: str) -> int:
        """Flush pending documents for a specific phase."""
        return self.doc_registry.flush_pending(phase_filter=phase)


# ── CLI ──────────────────────────────────────────────────────────────────────


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Post-campaign validation pipeline",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from last completed phase",
    )
    parser.add_argument(
        "--flush",
        choices=["auto", "manual"],
        default=None,
        help="Flush mode: auto (default) or manual",
    )
    parser.add_argument(
        "--flush-now",
        action="store_true",
        help="Flush all pending documents and exit",
    )
    parser.add_argument(
        "--flush-phase",
        type=str,
        default=None,
        help="Flush pending documents for a specific phase (e.g., 2a)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point for the post-campaign validation pipeline."""
    args = _parse_args(argv)

    project_dir_str = os.environ.get("PROJECT_DIR")
    if not project_dir_str:
        print("ERROR: PROJECT_DIR environment variable is required", file=sys.stderr)
        return EXIT_INFRA_FAILURE

    project_dir = Path(project_dir_str)
    if not project_dir.is_dir():
        print(
            f"ERROR: PROJECT_DIR does not exist: {project_dir}",
            file=sys.stderr,
        )
        return EXIT_INFRA_FAILURE

    flush_mode = args.flush or os.environ.get("FLUSH_MODE", "auto")
    validation_timeout = float(
        os.environ.get("VALIDATION_TIMEOUT", "60")
    )

    pipeline = ValidationPipeline(
        project_dir=project_dir,
        flush_mode=flush_mode,
        validation_timeout=validation_timeout,
        resume=args.resume,
    )

    # Handle flush-only modes
    if args.flush_now:
        count = pipeline.flush_now()
        logger.info("Flushed %d pending documents", count)
        return EXIT_ALL_PASS

    if args.flush_phase is not None:
        count = pipeline.flush_phase(args.flush_phase)
        logger.info("Flushed %d pending documents for phase %s", count, args.flush_phase)
        return EXIT_ALL_PASS

    return pipeline.run()


if __name__ == "__main__":
    sys.exit(main())
