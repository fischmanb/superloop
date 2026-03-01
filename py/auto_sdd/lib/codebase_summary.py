# CONVERSION CHANGELOG (from lib/codebase-summary.sh)
# - _gcs_append() inlined: bash nested function with closure over `output`,
#   `total_lines`, `truncated`. In Python, replaced by a _SummaryBuilder class
#   that encapsulates the same state.
# - Component search uses pathlib glob instead of `find`. Sort is by string
#   comparison on relative path (matching bash `find ... | sort`).
# - Type export extraction uses re instead of grep+awk. The regex faithfully
#   reproduces the bash pattern: `export (type|interface) <Name>`.
# - Import graph extraction uses re instead of grep -oE. Same regex pattern.
# - Learnings section iterates sorted *.md files (bash glob order is
#   locale-dependent; Python sorted() is deterministic).
# - project_dir is Path, not str. max_lines is int, not str.
# - Raises ValueError for missing/non-directory project_dir instead of
#   returning exit code 1 + stderr message. This follows conventions.md
#   guidance: "Raise specific exceptions, never bare Exception."

"""Generate a concise codebase summary for build agent prompts.

Public API:
    generate_codebase_summary(project_dir, max_lines=200) -> str
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


class _SummaryBuilder:
    """Accumulates output lines, respecting a max_lines cap.

    Mirrors the bash _gcs_append() closure pattern: tracks total lines
    emitted and stops appending once the cap is hit, inserting a
    truncation notice instead.
    """

    def __init__(self, max_lines: int) -> None:
        self._max_lines = max_lines
        self._lines: list[str] = []
        self._total: int = 0
        self._truncated: bool = False

    def append(self, line: str) -> None:
        """Append a single line, respecting the max_lines cap."""
        if self._truncated:
            return
        self._total += 1
        if self._total > self._max_lines:
            self._truncated = True
            self._lines.append(f"[Summary truncated at {self._max_lines} lines]")
            return
        self._lines.append(line)

    @property
    def truncated(self) -> bool:
        return self._truncated

    def build(self) -> str:
        """Return accumulated output as a single string with trailing newlines."""
        # Each line gets a trailing newline, matching bash's printf '%s' on
        # output that was built with newline-terminated concatenation.
        return "".join(line + "\n" for line in self._lines)


# Regex for extracting `export type Name` or `export interface Name`
_TYPE_EXPORT_RE = re.compile(
    r"export\s+(?:type|interface)\s+([A-Za-z_]\w*)"
)

# Regex for extracting local relative imports: from './' or from '../'
_LOCAL_IMPORT_RE = re.compile(
    r"""from\s+['"](\.\./[^'"]*|\.\/[^'"]*)['"]\s*"""
)


def _find_component_files(project_dir: Path) -> list[Path]:
    """Find .tsx and .jsx files under src/ and app/, sorted by relative path."""
    results: list[Path] = []
    for subdir_name in ("src", "app"):
        subdir = project_dir / subdir_name
        if subdir.is_dir():
            for ext in ("*.tsx", "*.jsx"):
                results.extend(subdir.rglob(ext))
    # Sort by relative path string, matching bash `find ... | sort`
    results.sort(key=lambda p: str(p.relative_to(project_dir)))
    return results


def _has_export_default(filepath: Path) -> bool:
    """Check if a file contains 'export default'."""
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
        return "export default" in content
    except OSError:
        return False


def _build_component_registry(
    builder: _SummaryBuilder,
    project_dir: Path,
    component_files: list[Path],
) -> None:
    """Section 1: Component Registry."""
    component_cap = 50

    builder.append("## Component Registry")
    builder.append("")

    if not component_files:
        builder.append("No .tsx/.jsx files found under src/ or app/.")
    else:
        total_components = len(component_files)
        displayed = 0
        for filepath in component_files:
            if displayed >= component_cap:
                remaining = total_components - component_cap
                builder.append(
                    f"... and {remaining} more components (truncated at {component_cap})"
                )
                break
            relpath = filepath.relative_to(project_dir)
            has_default = "yes" if _has_export_default(filepath) else "no"
            builder.append(f"  {relpath}  (export default: {has_default})")
            displayed += 1

    builder.append("")


def _find_type_exports(
    project_dir: Path,
) -> list[tuple[str, str]]:
    """Find type/interface exports in .ts and .tsx files under src/ and app/.

    Returns list of (relative_path, type_name) tuples.
    """
    results: list[tuple[str, str]] = []
    for subdir_name in ("src", "app"):
        subdir = project_dir / subdir_name
        if not subdir.is_dir():
            continue
        for ext in ("*.ts", "*.tsx"):
            for filepath in sorted(subdir.rglob(ext), key=lambda p: str(p)):
                try:
                    content = filepath.read_text(
                        encoding="utf-8", errors="replace"
                    )
                except OSError:
                    continue
                for match in _TYPE_EXPORT_RE.finditer(content):
                    relpath = str(filepath.relative_to(project_dir))
                    results.append((relpath, match.group(1)))
    return results


def _build_type_exports(
    builder: _SummaryBuilder,
    project_dir: Path,
) -> None:
    """Section 2: Type Exports."""
    type_cap = 50

    builder.append("## Type Exports")
    builder.append("")

    type_entries = _find_type_exports(project_dir)

    if not type_entries:
        builder.append("No type/interface exports found.")
    else:
        total_types = len(type_entries)
        displayed = 0
        for relpath, type_name in type_entries:
            if displayed >= type_cap:
                remaining = total_types - type_cap
                builder.append(
                    f"... and {remaining} more type exports (truncated at {type_cap})"
                )
                break
            builder.append(f"  {relpath}: {type_name}")
            displayed += 1

    builder.append("")


def _extract_local_imports(filepath: Path) -> list[str]:
    """Extract local relative import paths from a file."""
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return _LOCAL_IMPORT_RE.findall(content)


def _build_import_graph(
    builder: _SummaryBuilder,
    project_dir: Path,
    component_files: list[Path],
) -> None:
    """Section 3: Import Graph (top-level only)."""
    import_cap = 80
    import_count = 0
    has_imports = False

    builder.append("## Import Graph")
    builder.append("")

    for filepath in component_files:
        if import_count >= import_cap:
            builder.append(
                f"... (import graph truncated at {import_cap} entries)"
            )
            break

        relpath = filepath.relative_to(project_dir)
        imports = _extract_local_imports(filepath)

        for import_path in imports:
            if import_count >= import_cap:
                builder.append(
                    f"... (import graph truncated at {import_cap} entries)"
                )
                break
            builder.append(f"  {relpath} → {import_path}")
            import_count += 1
            has_imports = True

        # Break outer loop if inner hit the cap
        if import_count >= import_cap:
            break

    if not has_imports:
        builder.append("No local imports found.")

    builder.append("")


def _build_recent_learnings(
    builder: _SummaryBuilder,
    project_dir: Path,
) -> None:
    """Section 4: Recent Learnings."""
    learnings_cap = 40
    learnings_dir = project_dir / ".specs" / "learnings"

    builder.append("## Recent Learnings")
    builder.append("")

    if not learnings_dir.is_dir():
        builder.append("No learnings directory found.")
        return

    # Gather content from *.md files (sorted for determinism)
    md_files = sorted(learnings_dir.glob("*.md"))
    learnings_lines: list[str] = []
    learnings_found = False

    for md_file in md_files:
        if not md_file.is_file():
            continue
        # Skip empty files
        if md_file.stat().st_size == 0:
            continue
        learnings_found = True
        basename = md_file.name
        learnings_lines.append(f"### {basename}")
        try:
            content = md_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # Split content into lines (preserving empty lines)
        for line in content.split("\n"):
            learnings_lines.append(line)

    if not learnings_found:
        builder.append("No learnings files found.")
        return

    line_count = 0
    for lline in learnings_lines:
        if line_count >= learnings_cap:
            builder.append(
                f"... (learnings truncated at {learnings_cap} lines)"
            )
            break
        builder.append(lline)
        line_count += 1


def generate_codebase_summary(
    project_dir: Path,
    max_lines: int = 200,
) -> str:
    """Generate a structured plain-text codebase summary.

    Scans the project directory for components, type exports, import
    relationships, and learnings. Returns a multi-section summary string
    suitable for inclusion in build agent prompts.

    Args:
        project_dir: Absolute path to the project being scanned.
        max_lines: Cap on total output lines (default 200).

    Returns:
        Structured plain-text summary with four sections:
          ## Component Registry
          ## Type Exports
          ## Import Graph
          ## Recent Learnings

    Raises:
        ValueError: If project_dir does not exist or is not a directory.
    """
    if not project_dir.exists():
        raise ValueError(
            f"generate_codebase_summary: directory does not exist: {project_dir}"
        )
    if not project_dir.is_dir():
        raise ValueError(
            f"generate_codebase_summary: not a directory: {project_dir}"
        )

    logger.info("Generating codebase summary for %s (max_lines=%d)", project_dir, max_lines)

    builder = _SummaryBuilder(max_lines)

    # Find component files once (used by sections 1 and 3)
    component_files = _find_component_files(project_dir)

    # Section 1: Component Registry
    _build_component_registry(builder, project_dir, component_files)

    # Section 2: Type Exports
    _build_type_exports(builder, project_dir)

    # Section 3: Import Graph
    _build_import_graph(builder, project_dir, component_files)

    # Section 4: Recent Learnings
    _build_recent_learnings(builder, project_dir)

    result = builder.build()
    logger.info("Codebase summary generated: %d lines (truncated=%s)", builder._total, builder.truncated)
    return result
