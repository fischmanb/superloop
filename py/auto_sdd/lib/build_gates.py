# CONVERSION CHANGELOG (from scripts/build-loop-local.sh lines 361–670)
# - detect_build_check / detect_test_check / detect_lint_check: accept
#   project_dir (Path) + optional override (str|None) instead of reading
#   globals and using shell builtins. Return str (command) or empty string.
# - check_build / check_tests / check_lint: return typed BuildCheckResult
#   instead of setting LAST_BUILD_OUTPUT / LAST_TEST_OUTPUT globals and
#   returning shell exit codes. The caller stores these results.
# - check_tests extracts test count via regex, same patterns as bash. Returns
#   it inside BuildCheckResult.test_count.
# - check_dead_exports: returns DeadExportResult instead of printing to
#   stdout. Scanning logic faithfully reproduces the bash find + grep approach
#   using pathlib + re.
# - should_run_step: accepts the step set directly, not a global.
# - run_cmd_safe: thin wrapper around subprocess.run with timeout.
# - agent_cmd: returns list[str] instead of a shell string.
# - LAST_BUILD_OUTPUT / LAST_TEST_OUTPUT global state is eliminated; the
#   caller stores BuildCheckResult values.
"""Build gate detection and execution for the SDD build loop.

Provides auto-detection of build, test, and lint commands for various
project types, and functions to execute those checks with typed results.
"""
from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Result types ─────────────────────────────────────────────────────────────


@dataclass
class BuildCheckResult:
    """Result of a build/test/lint check."""

    success: bool
    output: str
    test_count: int | None = None


@dataclass
class DeadExportResult:
    """Result of a dead-export scan."""

    dead_exports: list[str] = field(default_factory=list)
    count: int = 0


# ── Detection functions ──────────────────────────────────────────────────────


def detect_build_check(
    project_dir: Path,
    override: str | None = None,
) -> str:
    """Auto-detect the build check command for a project.

    Args:
        project_dir: Root of the project.
        override: Explicit command from config.  ``"skip"`` disables.

    Returns:
        Command string, or empty string if none detected / skipped.
    """
    if override is not None:
        if override == "skip":
            return ""
        return override

    # Framework-specific builds (must precede generic tsconfig)
    # Next.js: `next build` catches server/client boundary violations
    # that `tsc --noEmit` misses (L-00012). Must check before tsconfig
    # because Next.js projects always have tsconfig.json too.
    nextjs_configs = [
        "next.config.js",
        "next.config.mjs",
        "next.config.ts",
        "next.config.cjs",
    ]
    if any((project_dir / cfg).exists() for cfg in nextjs_configs):
        pkg = project_dir / "package.json"
        if pkg.exists():
            try:
                if '"build"' in pkg.read_text():
                    return "npm run build"
            except OSError:
                pass

    # TypeScript
    if (project_dir / "tsconfig.build.json").exists():
        return "npx tsc --noEmit --project tsconfig.build.json"
    if (project_dir / "tsconfig.json").exists():
        return "npx tsc --noEmit"

    # Python
    if (project_dir / "pyproject.toml").exists() or (
        project_dir / "setup.py"
    ).exists():
        py_files = list(project_dir.rglob("*.py"))
        # Filter out venv
        py_files = [
            p
            for p in py_files
            if "venv" not in p.parts and ".venv" not in p.parts
        ]
        first = str(py_files[0].relative_to(project_dir)) if py_files else "main.py"
        return f"python -m py_compile {first}"

    # Rust
    if (project_dir / "Cargo.toml").exists():
        return "cargo check"

    # Go
    if (project_dir / "go.mod").exists():
        return "go build ./..."

    # Node.js with build script
    pkg = project_dir / "package.json"
    if pkg.exists():
        try:
            text = pkg.read_text()
            if '"build"' in text:
                return "npm run build"
        except OSError:
            pass

    return ""


def detect_test_check(
    project_dir: Path,
    override: str | None = None,
) -> str:
    """Auto-detect the test check command for a project.

    Args:
        project_dir: Root of the project.
        override: Explicit command from config.  ``"skip"`` disables.

    Returns:
        Command string, or empty string if none detected / skipped.
    """
    if override is not None:
        if override == "skip":
            return ""
        return override

    pkg = project_dir / "package.json"
    if pkg.exists():
        try:
            text = pkg.read_text()
            if '"test"' in text and "no test specified" not in text:
                return "npm test"
        except OSError:
            pass

    if (project_dir / "pytest.ini").exists() or (
        project_dir / "conftest.py"
    ).exists():
        return "pytest"

    pyproject = project_dir / "pyproject.toml"
    if pyproject.exists():
        try:
            text = pyproject.read_text()
            if "pytest" in text:
                return "pytest"
        except OSError:
            pass

    if (project_dir / "Cargo.toml").exists():
        return "cargo test"

    if (project_dir / "go.mod").exists():
        return "go test ./..."

    return ""


def detect_lint_check(project_dir: Path) -> str:
    """Auto-detect the linter command for a project.

    Args:
        project_dir: Root of the project.

    Returns:
        Command string, or empty string if none detected.
    """
    # ESLint legacy config files
    eslint_legacy = [
        ".eslintrc.js",
        ".eslintrc.json",
        ".eslintrc.yml",
        ".eslintrc.yaml",
        ".eslintrc.cjs",
        ".eslintrc.mjs",
    ]
    for name in eslint_legacy:
        if (project_dir / name).exists():
            return "npx eslint . --max-warnings=0"

    # ESLint flat config
    eslint_flat = [
        "eslint.config.js",
        "eslint.config.mjs",
        "eslint.config.cjs",
        "eslint.config.ts",
    ]
    for name in eslint_flat:
        if (project_dir / name).exists():
            return "npx eslint . --max-warnings=0"

    # ESLint via package.json
    pkg = project_dir / "package.json"
    if pkg.exists():
        try:
            text = pkg.read_text()
            if '"eslintConfig"' in text:
                return "npx eslint . --max-warnings=0"
        except OSError:
            pass

    # Biome
    if (project_dir / "biome.json").exists() or (
        project_dir / "biome.jsonc"
    ).exists():
        return "npx biome check ."

    # Python: flake8
    if (project_dir / ".flake8").exists():
        return "flake8 ."
    setup_cfg = project_dir / "setup.cfg"
    if setup_cfg.exists():
        try:
            text = setup_cfg.read_text()
            if "[flake8]" in text:
                return "flake8 ."
        except OSError:
            pass

    # Python: ruff
    if (project_dir / "ruff.toml").exists():
        return "ruff check ."
    pyproject = project_dir / "pyproject.toml"
    if pyproject.exists():
        try:
            text = pyproject.read_text()
            if "[tool.ruff]" in text:
                return "ruff check ."
        except OSError:
            pass

    # Rust: clippy
    if (project_dir / "Cargo.toml").exists():
        return "cargo clippy -- -D warnings"

    # Go: golangci-lint
    for name in [".golangci.yml", ".golangci.yaml", ".golangci.json"]:
        if (project_dir / name).exists():
            return "golangci-lint run"

    return ""


# ── Execution functions ──────────────────────────────────────────────────────


_TEST_COUNT_RE = re.compile(
    r"(?:Tests\s+)?(\d+)\s+(?:passed|tests?\s+passed)"
)
_PYTEST_COUNT_RE = re.compile(r"(\d+)\s+passed")


def run_cmd_safe(
    cmd: str,
    project_dir: Path,
    *,
    timeout: int = 600,
) -> subprocess.CompletedProcess[str]:
    """Run a shell command safely with timeout.

    Args:
        cmd: Shell command string.
        project_dir: Working directory.
        timeout: Seconds before kill.

    Returns:
        CompletedProcess with stdout/stderr captured.
    """
    return subprocess.run(
        ["sh", "-c", cmd],
        capture_output=True,
        text=True,
        cwd=str(project_dir),
        timeout=timeout,
    )


def check_build(
    cmd: str,
    project_dir: Path,
    *,
    timeout: int = 600,
) -> BuildCheckResult:
    """Run the build check command and return a typed result.

    Args:
        cmd: Build command (empty string skips).
        project_dir: Project root.
        timeout: Subprocess timeout in seconds.

    Returns:
        BuildCheckResult with success flag and output.
    """
    if not cmd:
        logger.info("No build check configured (set BUILD_CHECK_CMD to enable)")
        return BuildCheckResult(success=True, output="")

    logger.info("Running build check: %s", cmd)
    try:
        proc = run_cmd_safe(cmd, project_dir, timeout=timeout)
    except subprocess.TimeoutExpired:
        logger.error("Build check timed out after %ds", timeout)
        return BuildCheckResult(success=False, output="Build check timed out")

    combined = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode == 0:
        logger.info("✓ Build check passed")
        return BuildCheckResult(success=True, output="")
    else:
        # Keep last 50 lines for diagnostics
        lines = combined.splitlines()
        tail = "\n".join(lines[-50:]) if len(lines) > 50 else combined
        logger.error("Build check failed")
        return BuildCheckResult(success=False, output=tail)


def check_tests(
    cmd: str,
    project_dir: Path,
    *,
    timeout: int = 600,
) -> BuildCheckResult:
    """Run the test suite and return a typed result with test count.

    Args:
        cmd: Test command (empty string skips).
        project_dir: Project root.
        timeout: Subprocess timeout in seconds.

    Returns:
        BuildCheckResult with success flag, output, and parsed test_count.
    """
    if not cmd:
        logger.info("No test suite configured (set TEST_CHECK_CMD to enable)")
        return BuildCheckResult(success=True, output="", test_count=None)

    logger.info("Running test suite: %s", cmd)
    try:
        proc = run_cmd_safe(cmd, project_dir, timeout=timeout)
    except subprocess.TimeoutExpired:
        logger.error("Test suite timed out after %ds", timeout)
        return BuildCheckResult(
            success=False, output="Test suite timed out", test_count=None
        )

    combined = (proc.stdout or "") + (proc.stderr or "")

    # Parse test count
    test_count: int | None = None
    match = _TEST_COUNT_RE.search(combined)
    if match:
        test_count = int(match.group(1))
    else:
        match2 = _PYTEST_COUNT_RE.search(combined)
        if match2:
            test_count = int(match2.group(1))

    if proc.returncode == 0:
        logger.info("✓ Tests passed")
        return BuildCheckResult(success=True, output="", test_count=test_count)
    else:
        lines = combined.splitlines()
        tail = "\n".join(lines[-80:]) if len(lines) > 80 else combined
        logger.error("Tests failed")
        return BuildCheckResult(success=False, output=tail, test_count=test_count)


def check_dead_exports(project_dir: Path) -> DeadExportResult:
    """Scan for exported symbols with zero import sites.

    This is a non-blocking gate — it always returns a result (never raises).

    Args:
        project_dir: Project root.

    Returns:
        DeadExportResult with list of dead exports and count.
    """
    logger.info("Scanning for dead exports...")

    source_extensions = {
        ".ts", ".tsx", ".js", ".jsx", ".py", ".rs", ".go",
    }
    exclude_dirs = {
        "node_modules", ".git", "dist", "build", ".next",
        "__pycache__", "target",
    }

    # Collect source files
    src_files: list[Path] = []
    for f in project_dir.rglob("*"):
        if not f.is_file():
            continue
        if f.suffix not in source_extensions:
            continue
        if any(part in exclude_dirs for part in f.parts):
            continue
        # Exclude test/spec files
        if ".test." in f.name or ".spec." in f.name or f.suffix == ".d.ts":
            continue
        src_files.append(f)

    if not src_files:
        logger.info("No source files found for dead export scan")
        return DeadExportResult()

    # Extract exported symbols: (file, symbol)
    ts_export_re = re.compile(
        r"export\s+(?:default\s+)?"
        r"(?:function|const|let|var|class|type|interface|enum)\s+"
        r"([A-Za-z_$][A-Za-z0-9_$]*)"
    )
    py_def_re = re.compile(r"^(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)")
    rust_pub_re = re.compile(
        r"pub\s+(?:fn|struct|enum|type|trait|const|static|mod)\s+"
        r"([A-Za-z_][A-Za-z0-9_]*)"
    )
    go_export_re = re.compile(
        r"^(?:func|type|var|const)\s+([A-Z][A-Za-z0-9_]*)"
    )

    generic_names = {
        "default", "index", "main", "test", "setup", "config", "app", "App", "mod",
    }

    exports: list[tuple[Path, str]] = []
    for f in src_files:
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        # TS/JS exports
        if f.suffix in (".ts", ".tsx", ".js", ".jsx"):
            for m in ts_export_re.finditer(content):
                exports.append((f, m.group(1)))

        # Python: module-level def/class
        if f.suffix == ".py":
            for line in content.splitlines():
                pm = py_def_re.match(line)
                if pm:
                    exports.append((f, pm.group(1)))

        # Rust: pub items
        if f.suffix == ".rs":
            for m in rust_pub_re.finditer(content):
                exports.append((f, m.group(1)))

        # Go: uppercase-initial top-level func/type/var/const
        if f.suffix == ".go":
            for line in content.splitlines():
                gm = go_export_re.match(line)
                if gm:
                    exports.append((f, gm.group(1)))

    # Check each exported symbol for references in other files
    dead: list[str] = []
    for src_file, sym in exports:
        if sym in generic_names:
            continue

        found = False
        for other in src_files:
            if other == src_file:
                continue
            try:
                other_content = other.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            # Word-boundary match
            if re.search(rf"\b{re.escape(sym)}\b", other_content):
                found = True
                break

        if not found:
            rel = src_file.relative_to(project_dir)
            dead.append(f"{rel}: {sym}")

    if dead:
        logger.warning("Found %d potentially dead export(s):", len(dead))
        for entry in dead[:20]:
            logger.warning("    %s", entry)
        if len(dead) > 20:
            logger.warning(
                "  ... and %d more (showing first 20)", len(dead) - 20
            )
    else:
        logger.info("✓ No dead exports detected")

    return DeadExportResult(dead_exports=dead, count=len(dead))


def check_lint(
    project_dir: Path,
    cmd: str | None = None,
    *,
    timeout: int = 600,
) -> BuildCheckResult:
    """Run the linter and return a typed result.

    Auto-detects the lint command if *cmd* is not provided.
    This is a non-blocking gate — always returns (success may be False
    but the caller decides whether to abort).

    Args:
        project_dir: Project root.
        cmd: Lint command (auto-detected if None).
        timeout: Subprocess timeout.

    Returns:
        BuildCheckResult with success flag and output.
    """
    lint_cmd = cmd if cmd is not None else detect_lint_check(project_dir)
    if not lint_cmd:
        logger.info("No linter config detected (skipping lint gate)")
        return BuildCheckResult(success=True, output="")

    logger.info("Running linter: %s", lint_cmd)
    try:
        proc = run_cmd_safe(lint_cmd, project_dir, timeout=timeout)
    except subprocess.TimeoutExpired:
        logger.warning("Lint check timed out after %ds", timeout)
        return BuildCheckResult(success=False, output="Lint check timed out")

    combined = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode == 0:
        logger.info("✓ Lint check passed")
        return BuildCheckResult(success=True, output="")
    else:
        lines = combined.splitlines()
        tail = "\n".join(lines[-20:]) if len(lines) > 20 else combined
        logger.warning("Lint check failed (non-blocking):")
        return BuildCheckResult(success=False, output=tail)


def should_run_step(step_name: str, post_build_steps: str) -> bool:
    """Check if a named step is in the comma-separated post_build_steps config.

    Args:
        step_name: Step to check (e.g. ``"test"``, ``"lint"``).
        post_build_steps: Comma-separated list of enabled steps.

    Returns:
        True if the step is listed.
    """
    steps = {s.strip() for s in post_build_steps.split(",") if s.strip()}
    return step_name in steps


def check_working_tree_clean(project_dir: Path) -> bool:
    """Return True if the git working tree has no uncommitted tracked changes.

    Args:
        project_dir: Path to git repo.

    Returns:
        True if clean (ignoring untracked files).
    """
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=str(project_dir),
            timeout=30,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False

    untracked: list[str] = []
    for line in result.stdout.splitlines():
        if line.startswith("??"):
            # Collect untracked file paths (strip "?? " prefix)
            untracked.append(line[3:].strip())
        else:
            return False

    if untracked:
        logger.warning(
            "Working tree clean but %d untracked file(s) present: %s",
            len(untracked),
            ", ".join(untracked[:10]),
        )

    return True


def clean_working_tree(project_dir: Path) -> None:
    """Stash uncommitted changes if the working tree is dirty.

    Args:
        project_dir: Path to git repo.
    """
    if not check_working_tree_clean(project_dir):
        logger.warning("Cleaning dirty working tree before next feature...")
        subprocess.run(
            [
                "git", "stash", "push", "-m",
                "build-loop: stashing failed feature attempt",
            ],
            capture_output=True,
            text=True,
            cwd=str(project_dir),
            timeout=30,
        )
        logger.info("✓ Stashed uncommitted changes")


def agent_cmd(model: str | None = None) -> list[str]:
    """Build the claude CLI command list for an agent invocation.

    Args:
        model: Model override (e.g. ``"opus"``).  None uses CLI default.

    Returns:
        List of command parts suitable for subprocess.
    """
    cmd = ["claude", "-p", "--dangerously-skip-permissions"]
    if model:
        cmd.extend(["--model", model])
    return cmd
