"""Post-campaign validation orchestrator with Phase 0 (Runtime Bootstrap).

Boots a target project, validates it can start, detects runtime issues, and
orchestrates multi-phase validation.  Phases 1–5 are stubs pending future
milestones.

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

        # Phases 1–5 (stubs)
        for phase in PHASE_ORDER[1:]:
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
