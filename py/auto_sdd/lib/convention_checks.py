"""Campaign Intelligence System — Mechanical Convention Checks.

Static analysis checks for code quality patterns that are deterministic
and verifiable. No AI agent calls — all checks are pure file/diff analysis.

Checks:
- import_boundaries: server/client import boundary violations
- type_safety: TypeScript `any` usage, Python untyped function params
- code_duplication: duplicate string literals and near-identical function bodies
- error_handling: bare except, empty catch blocks, log-only catch
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ConventionViolation:
    """A single convention check violation."""

    pattern: str  # "import_boundaries", "type_safety", "code_duplication", "error_handling"
    assessment: str  # "followed", "deviated", "violated"
    evidence: str  # specific file:line or description
    severity: str  # "cosmetic", "maintainability", "correctness"


@dataclass
class ConventionCheckResult:
    """Aggregate result of all convention checks."""

    compliance: str  # "followed", "partial", "violated"
    violations: list[ConventionViolation] = field(default_factory=list)
    checks_run: list[str] = field(default_factory=list)


# ── Config loading ───────────────────────────────────────────────────────────


_DEFAULT_CONFIG: dict[str, Any] = {
    "convention_checks": {
        "enabled": True,
        "checks": {
            "import_boundaries": True,
            "type_safety": True,
            "code_duplication": True,
            "error_handling": True,
        },
        "thresholds": {
            "any_type_per_file_warn": 3,
            "duplicate_string_min_length": 20,
            "duplicate_function_min_lines": 5,
        },
    }
}


def load_eval_config(project_dir: Path) -> dict[str, Any]:
    """Load eval config from project directory.

    Checks for .sdd-config/eval-dimensions.yaml (via PyYAML if available),
    then .sdd-config/eval-dimensions.json. Returns defaults if neither exists.
    """
    config_dir = project_dir / ".sdd-config"

    # Try YAML first (if PyYAML is available)
    yaml_path = config_dir / "eval-dimensions.yaml"
    if yaml_path.is_file():
        try:
            import yaml  # type: ignore[import-untyped]
            with open(yaml_path) as f:
                data = yaml.safe_load(f)
            if isinstance(data, dict):
                return data
        except ImportError:
            pass
        except Exception:
            pass

    # Try JSON fallback
    json_path = config_dir / "eval-dimensions.json"
    if json_path.is_file():
        try:
            with open(json_path) as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    return dict(_DEFAULT_CONFIG)


def _get_config_value(config: dict[str, Any], *keys: str, default: Any = None) -> Any:
    """Safely traverse nested config keys."""
    current: Any = config
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current


# ── File reading helpers ──────────────────────────────────────────────────────


def _read_file_lines(project_dir: Path, filepath: str) -> list[str]:
    """Read file lines, returning empty list if file doesn't exist."""
    full_path = project_dir / filepath
    if not full_path.is_file():
        return []
    try:
        return full_path.read_text().splitlines()
    except OSError:
        return []


# ── Import boundary patterns ────────────────────────────────────────────────

_CLIENT_DIRS = {"client/", "src/components/"}
_SERVER_DIRS = {"server/", "src/api/", "db/", "models/"}

_PYTHON_IMPORT_RE = re.compile(
    r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))"
)
_TS_IMPORT_RE = re.compile(
    r"""^\s*import\s+.*?\s+from\s+['"]([^'"]+)['"]"""
)


def _is_under_dirs(filepath: str, dirs: set[str]) -> bool:
    """Check if filepath starts with any of the given directory prefixes."""
    for d in dirs:
        if filepath.startswith(d):
            return True
    return False


def _extract_import_sources(lines: list[str], filepath: str) -> list[str]:
    """Extract import source paths from file lines."""
    sources: list[str] = []
    is_ts = filepath.endswith((".ts", ".tsx", ".js", ".jsx"))
    is_py = filepath.endswith(".py")

    for line in lines:
        if is_ts:
            m = _TS_IMPORT_RE.match(line)
            if m:
                sources.append(m.group(1))
        elif is_py:
            m = _PYTHON_IMPORT_RE.match(line)
            if m:
                src = m.group(1) or m.group(2) or ""
                if src:
                    sources.append(src.replace(".", "/"))
    return sources


def _import_path_under_dirs(import_src: str, dirs: set[str]) -> bool:
    """Check if an import source references a restricted directory."""
    # Normalize: strip leading ./ or ../
    normalized = import_src.lstrip("./")
    for d in dirs:
        d_stripped = d.rstrip("/")
        if normalized.startswith(d_stripped + "/") or normalized == d_stripped:
            return True
    return False


def check_import_boundaries(
    project_dir: Path, diff_files: list[str]
) -> list[ConventionViolation]:
    """Check for server/client import boundary violations."""
    violations: list[ConventionViolation] = []

    for filepath in diff_files:
        lines = _read_file_lines(project_dir, filepath)
        if not lines:
            continue

        import_sources = _extract_import_sources(lines, filepath)
        is_client = _is_under_dirs(filepath, _CLIENT_DIRS)
        is_server = _is_under_dirs(filepath, _SERVER_DIRS)

        for src in import_sources:
            if is_client and _import_path_under_dirs(src, _SERVER_DIRS):
                violations.append(ConventionViolation(
                    pattern="import_boundaries",
                    assessment="violated",
                    evidence=f"{filepath}: client file imports from server path '{src}'",
                    severity="correctness",
                ))
            elif is_server and _import_path_under_dirs(src, _CLIENT_DIRS):
                violations.append(ConventionViolation(
                    pattern="import_boundaries",
                    assessment="violated",
                    evidence=f"{filepath}: server file imports from client path '{src}'",
                    severity="correctness",
                ))

        # Transitive check: follow imports one level deep
        if is_client:
            for src in import_sources:
                transitive_path = _resolve_import_path(project_dir, filepath, src)
                if transitive_path:
                    trans_lines = _read_file_lines(project_dir, transitive_path)
                    trans_imports = _extract_import_sources(trans_lines, transitive_path)
                    for tsrc in trans_imports:
                        if _import_path_under_dirs(tsrc, _SERVER_DIRS):
                            violations.append(ConventionViolation(
                                pattern="import_boundaries",
                                assessment="violated",
                                evidence=(
                                    f"{filepath}: transitively imports server module "
                                    f"via {transitive_path} -> '{tsrc}'"
                                ),
                                severity="correctness",
                            ))
        elif is_server:
            for src in import_sources:
                transitive_path = _resolve_import_path(project_dir, filepath, src)
                if transitive_path:
                    trans_lines = _read_file_lines(project_dir, transitive_path)
                    trans_imports = _extract_import_sources(trans_lines, transitive_path)
                    for tsrc in trans_imports:
                        if _import_path_under_dirs(tsrc, _CLIENT_DIRS):
                            violations.append(ConventionViolation(
                                pattern="import_boundaries",
                                assessment="violated",
                                evidence=(
                                    f"{filepath}: transitively imports client module "
                                    f"via {transitive_path} -> '{tsrc}'"
                                ),
                                severity="correctness",
                            ))

    return violations


def _resolve_import_path(
    project_dir: Path, importer: str, import_src: str
) -> str:
    """Try to resolve an import source to a real file path relative to project_dir."""
    if import_src.startswith("."):
        # Relative import — resolve from importer's directory
        importer_dir = str(Path(importer).parent)
        candidate = str(Path(importer_dir) / import_src)
    else:
        candidate = import_src

    # Normalize
    candidate = candidate.replace("\\", "/")
    # Strip leading ./
    while candidate.startswith("./"):
        candidate = candidate[2:]

    # Try common extensions
    extensions = ["", ".ts", ".tsx", ".js", ".jsx", ".py"]
    for ext in extensions:
        full = project_dir / (candidate + ext)
        if full.is_file():
            return candidate + ext

    # Try as directory with index
    for idx in ["index.ts", "index.tsx", "index.js", "index.jsx", "__init__.py"]:
        full = project_dir / candidate / idx
        if full.is_file():
            return f"{candidate}/{idx}"

    return ""


# ── Type safety check ────────────────────────────────────────────────────────

_TS_ANY_RE = re.compile(r"\bany\b")
_PY_DEF_RE = re.compile(r"^\s*def\s+\w+\s*\(([^)]*)\)")


def check_type_safety(
    project_dir: Path, diff_files: list[str],
    threshold: int = 3,
) -> list[ConventionViolation]:
    """Check for type safety issues in modified files."""
    violations: list[ConventionViolation] = []

    for filepath in diff_files:
        lines = _read_file_lines(project_dir, filepath)
        if not lines:
            continue

        is_ts = filepath.endswith((".ts", ".tsx", ".js", ".jsx"))
        is_py = filepath.endswith(".py")

        if is_ts:
            any_count = 0
            any_locations: list[str] = []
            for lineno, line in enumerate(lines, 1):
                # Skip comments and strings (simple heuristic)
                stripped = line.strip()
                if stripped.startswith("//") or stripped.startswith("*"):
                    continue
                matches = _TS_ANY_RE.findall(line)
                if matches:
                    any_count += len(matches)
                    any_locations.append(f"{filepath}:{lineno}")

            if any_count > threshold:
                violations.append(ConventionViolation(
                    pattern="type_safety",
                    assessment="violated",
                    evidence=f"{filepath}: {any_count} 'any' type annotations (threshold: {threshold}). Locations: {', '.join(any_locations[:5])}",
                    severity="maintainability",
                ))
            elif any_count > 0:
                violations.append(ConventionViolation(
                    pattern="type_safety",
                    assessment="deviated",
                    evidence=f"{filepath}: {any_count} 'any' type annotations",
                    severity="maintainability",
                ))

        elif is_py:
            untyped_count = 0
            untyped_locations: list[str] = []
            for lineno, line in enumerate(lines, 1):
                m = _PY_DEF_RE.match(line)
                if m:
                    params_str = m.group(1).strip()
                    if not params_str:
                        continue
                    params = [p.strip() for p in params_str.split(",")]
                    for param in params:
                        # Skip self, cls, *args, **kwargs
                        param_name = param.split("=")[0].strip()
                        if param_name in ("self", "cls") or param_name.startswith("*"):
                            continue
                        # Check for type annotation (contains ':')
                        if ":" not in param:
                            untyped_count += 1
                            untyped_locations.append(f"{filepath}:{lineno}")

            if untyped_count > threshold:
                violations.append(ConventionViolation(
                    pattern="type_safety",
                    assessment="violated",
                    evidence=f"{filepath}: {untyped_count} untyped function parameters (threshold: {threshold}). Locations: {', '.join(untyped_locations[:5])}",
                    severity="maintainability",
                ))
            elif untyped_count > 0:
                violations.append(ConventionViolation(
                    pattern="type_safety",
                    assessment="deviated",
                    evidence=f"{filepath}: {untyped_count} untyped function parameters",
                    severity="maintainability",
                ))

    return violations


# ── Code duplication check ───────────────────────────────────────────────────


def check_code_duplication(
    project_dir: Path, diff_files: list[str],
    min_string_length: int = 20,
    min_function_lines: int = 5,
) -> list[ConventionViolation]:
    """Check for duplicate string literals and near-identical function bodies."""
    violations: list[ConventionViolation] = []

    # Collect string literals and function bodies from all diff files
    string_occurrences: dict[str, list[str]] = {}  # string -> [file1, file2, ...]
    function_bodies: list[tuple[str, int, list[str]]] = []  # (filepath, lineno, normalized_lines)

    _STRING_RE = re.compile(r"""(?:["'])(.{20,}?)(?:["'])""")

    for filepath in diff_files:
        lines = _read_file_lines(project_dir, filepath)
        if not lines:
            continue

        # String literals
        for line in lines:
            for m in _STRING_RE.finditer(line):
                literal = m.group(1)
                if len(literal) >= min_string_length:
                    if literal not in string_occurrences:
                        string_occurrences[literal] = []
                    if filepath not in string_occurrences[literal]:
                        string_occurrences[literal].append(filepath)

        # Function bodies — collect contiguous function blocks
        is_py = filepath.endswith(".py")
        is_ts = filepath.endswith((".ts", ".tsx", ".js", ".jsx"))

        if is_py:
            _collect_python_functions(filepath, lines, min_function_lines, function_bodies)
        elif is_ts:
            _collect_ts_functions(filepath, lines, min_function_lines, function_bodies)

    # Report duplicate strings across 2+ files
    for literal, files in string_occurrences.items():
        if len(files) >= 2:
            violations.append(ConventionViolation(
                pattern="code_duplication",
                assessment="deviated",
                evidence=f"String literal '{literal[:40]}...' duplicated across: {', '.join(files[:5])}",
                severity="maintainability",
            ))

    # Report near-identical function bodies
    for i in range(len(function_bodies)):
        for j in range(i + 1, len(function_bodies)):
            fp_i, ln_i, body_i = function_bodies[i]
            fp_j, ln_j, body_j = function_bodies[j]
            if fp_i == fp_j:
                continue  # Skip same-file comparisons
            if len(body_i) >= min_function_lines and body_i == body_j:
                violations.append(ConventionViolation(
                    pattern="code_duplication",
                    assessment="violated",
                    evidence=(
                        f"Near-identical function bodies ({len(body_i)} lines): "
                        f"{fp_i}:{ln_i} and {fp_j}:{ln_j}"
                    ),
                    severity="maintainability",
                ))

    return violations


def _normalize_line(line: str) -> str:
    """Normalize a line for comparison: strip whitespace."""
    return line.strip()


def _collect_python_functions(
    filepath: str,
    lines: list[str],
    min_lines: int,
    out: list[tuple[str, int, list[str]]],
) -> None:
    """Extract Python function bodies as normalized line lists."""
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith("def "):
            start = i
            indent = len(lines[i]) - len(lines[i].lstrip())
            body: list[str] = []
            i += 1
            while i < len(lines):
                if lines[i].strip() == "":
                    i += 1
                    continue
                current_indent = len(lines[i]) - len(lines[i].lstrip())
                if current_indent <= indent:
                    break
                body.append(_normalize_line(lines[i]))
                i += 1
            if len(body) >= min_lines:
                out.append((filepath, start + 1, body))
        else:
            i += 1


def _collect_ts_functions(
    filepath: str,
    lines: list[str],
    min_lines: int,
    out: list[tuple[str, int, list[str]]],
) -> None:
    """Extract TS/JS function bodies as normalized line lists."""
    func_re = re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+\w+|^\s*(?:const|let|var)\s+\w+\s*=\s*(?:async\s+)?\(")
    i = 0
    while i < len(lines):
        if func_re.match(lines[i]):
            start = i
            # Find opening brace
            brace_count = 0
            body: list[str] = []
            found_open = False
            j = i
            while j < len(lines):
                for ch in lines[j]:
                    if ch == "{":
                        brace_count += 1
                        found_open = True
                    elif ch == "}":
                        brace_count -= 1
                if found_open:
                    body.append(_normalize_line(lines[j]))
                if found_open and brace_count == 0:
                    break
                j += 1
            if len(body) >= min_lines:
                out.append((filepath, start + 1, body))
            i = j + 1
        else:
            i += 1


# ── Error handling check ─────────────────────────────────────────────────────

_BARE_EXCEPT_RE = re.compile(r"^\s*except\s*:\s*$")
_EXCEPT_PASS_RE = re.compile(r"^\s*except\s+\w+.*:\s*$")
_EMPTY_CATCH_RE = re.compile(r"catch\s*\([^)]*\)\s*\{\s*\}")
_LOG_ONLY_CATCH_RE = re.compile(
    r"catch\s*\([^)]*\)\s*\{\s*console\.\w+\([^)]*\)\s*;?\s*\}"
)


def check_error_handling(
    project_dir: Path, diff_files: list[str]
) -> list[ConventionViolation]:
    """Check for poor error handling patterns."""
    violations: list[ConventionViolation] = []

    for filepath in diff_files:
        lines = _read_file_lines(project_dir, filepath)
        if not lines:
            continue

        is_ts = filepath.endswith((".ts", ".tsx", ".js", ".jsx"))
        is_py = filepath.endswith(".py")
        full_content = "\n".join(lines)

        if is_ts:
            # Check for empty catch blocks
            for m in _EMPTY_CATCH_RE.finditer(full_content):
                # Find line number
                lineno = full_content[:m.start()].count("\n") + 1
                violations.append(ConventionViolation(
                    pattern="error_handling",
                    assessment="violated",
                    evidence=f"{filepath}:{lineno}: empty catch block",
                    severity="correctness",
                ))

            # Check for log-only catch
            for m in _LOG_ONLY_CATCH_RE.finditer(full_content):
                lineno = full_content[:m.start()].count("\n") + 1
                violations.append(ConventionViolation(
                    pattern="error_handling",
                    assessment="deviated",
                    evidence=f"{filepath}:{lineno}: catch block only logs error",
                    severity="correctness",
                ))

        elif is_py:
            for lineno, line in enumerate(lines, 1):
                # Bare except:
                if _BARE_EXCEPT_RE.match(line):
                    violations.append(ConventionViolation(
                        pattern="error_handling",
                        assessment="violated",
                        evidence=f"{filepath}:{lineno}: bare except clause",
                        severity="correctness",
                    ))

                # except Exception: pass (check next non-blank line)
                if _EXCEPT_PASS_RE.match(line):
                    # Look ahead for 'pass'
                    next_lineno = lineno  # lineno is 1-indexed, lines[lineno] is next
                    while next_lineno < len(lines):
                        next_line = lines[next_lineno].strip()
                        if next_line == "":
                            next_lineno += 1
                            continue
                        if next_line == "pass":
                            violations.append(ConventionViolation(
                                pattern="error_handling",
                                assessment="violated",
                                evidence=f"{filepath}:{lineno}: except with bare pass",
                                severity="correctness",
                            ))
                        break

    return violations


# ── Main entry point ─────────────────────────────────────────────────────────


def run_convention_checks(
    project_dir: Path,
    diff_files: list[str],
    config: dict[str, Any] | None = None,
) -> ConventionCheckResult:
    """Run all enabled mechanical convention checks.

    Args:
        project_dir: Root of the project.
        diff_files: List of file paths (relative to project_dir) from the diff.
        config: Optional config dict. Loaded from project if None.

    Returns:
        ConventionCheckResult with aggregated violations.
    """
    if config is None:
        config = load_eval_config(project_dir)

    cc = _get_config_value(config, "convention_checks") or {}
    if not _get_config_value(cc, "enabled", default=True):
        return ConventionCheckResult(compliance="followed", checks_run=[])

    checks_config = _get_config_value(cc, "checks") or {}
    thresholds = _get_config_value(cc, "thresholds") or {}

    all_violations: list[ConventionViolation] = []
    checks_run: list[str] = []

    if checks_config.get("import_boundaries", True):
        checks_run.append("import_boundaries")
        all_violations.extend(check_import_boundaries(project_dir, diff_files))

    if checks_config.get("type_safety", True):
        checks_run.append("type_safety")
        threshold = thresholds.get("any_type_per_file_warn", 3)
        all_violations.extend(
            check_type_safety(project_dir, diff_files, threshold=threshold)
        )

    if checks_config.get("code_duplication", True):
        checks_run.append("code_duplication")
        all_violations.extend(
            check_code_duplication(
                project_dir,
                diff_files,
                min_string_length=thresholds.get("duplicate_string_min_length", 20),
                min_function_lines=thresholds.get("duplicate_function_min_lines", 5),
            )
        )

    if checks_config.get("error_handling", True):
        checks_run.append("error_handling")
        all_violations.extend(check_error_handling(project_dir, diff_files))

    # Determine overall compliance
    if not all_violations:
        compliance = "followed"
    elif any(v.assessment == "violated" for v in all_violations):
        compliance = "violated"
    else:
        compliance = "partial"

    return ConventionCheckResult(
        compliance=compliance,
        violations=all_violations,
        checks_run=checks_run,
    )
