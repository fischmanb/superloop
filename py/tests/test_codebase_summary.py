"""Tests for auto_sdd.lib.codebase_summary.

Mirrors the bash test suite in tests/test-codebase-summary.sh (23 assertions)
with equivalent Python coverage using pytest.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from auto_sdd.lib.codebase_summary import generate_codebase_summary


# ── Fixture: create_fixture_project ──────────────────────────────────────────


@pytest.fixture
def fixture_project(tmp_path: Path) -> Path:
    """A temporary project directory matching the bash test fixture.

    Structure:
      src/components/Button.tsx  (has export default, local import target)
      src/components/Header.tsx  (has export default, imports ./Button)
      src/types/index.ts         (export type User, export interface ApiResponse)
      src/utils/helpers.ts       (export function, NOT a type export)
      .specs/learnings/general.md
    """
    # src/components/Button.tsx
    components = tmp_path / "src" / "components"
    components.mkdir(parents=True)
    (components / "Button.tsx").write_text(
        "import React from 'react';\n"
        "\n"
        "interface ButtonProps {\n"
        "  label: string;\n"
        "  onClick: () => void;\n"
        "}\n"
        "\n"
        "export default function Button({ label, onClick }: ButtonProps) {\n"
        "  return <button onClick={onClick}>{label}</button>;\n"
        "}\n"
    )

    # src/components/Header.tsx
    (components / "Header.tsx").write_text(
        "import React from 'react';\n"
        "import Button from './Button';\n"
        "\n"
        "export default function Header() {\n"
        "  return (\n"
        "    <header>\n"
        "      <h1>My App</h1>\n"
        "      <Button label=\"Menu\" onClick={() => {}} />\n"
        "    </header>\n"
        "  );\n"
        "}\n"
    )

    # src/types/index.ts
    types_dir = tmp_path / "src" / "types"
    types_dir.mkdir(parents=True)
    (types_dir / "index.ts").write_text(
        "export type User = {\n"
        "  id: string;\n"
        "  name: string;\n"
        "  email: string;\n"
        "};\n"
        "\n"
        "export interface ApiResponse {\n"
        "  data: unknown;\n"
        "  status: number;\n"
        "  message: string;\n"
        "}\n"
    )

    # src/utils/helpers.ts
    utils_dir = tmp_path / "src" / "utils"
    utils_dir.mkdir(parents=True)
    (utils_dir / "helpers.ts").write_text(
        "export function formatDate(date: Date): string {\n"
        "  return date.toISOString().split('T')[0];\n"
        "}\n"
    )

    # .specs/learnings/general.md
    learnings_dir = tmp_path / ".specs" / "learnings"
    learnings_dir.mkdir(parents=True)
    (learnings_dir / "general.md").write_text(
        "# General Learnings\n"
        "\n"
        "- **Pattern**: Use semantic tokens for colors instead of hardcoded hex values.\n"
        "- **Pattern**: Always validate user input at the boundary.\n"
    )

    return tmp_path


# ── Test: normal project scan ────────────────────────────────────────────────
# Mirrors bash test_normal_project: 13 assertions


class TestNormalProject:
    """Normal project scan — section headers, components, types, imports, learnings."""

    def test_exits_successfully(self, fixture_project: Path) -> None:
        """Bash assertion: 'normal project exits 0'."""
        output = generate_codebase_summary(fixture_project)
        assert isinstance(output, str), "Expected string output"

    def test_has_component_registry_header(self, fixture_project: Path) -> None:
        output = generate_codebase_summary(fixture_project)
        assert "## Component Registry" in output, "Missing Component Registry header"

    def test_has_type_exports_header(self, fixture_project: Path) -> None:
        output = generate_codebase_summary(fixture_project)
        assert "## Type Exports" in output, "Missing Type Exports header"

    def test_has_import_graph_header(self, fixture_project: Path) -> None:
        output = generate_codebase_summary(fixture_project)
        assert "## Import Graph" in output, "Missing Import Graph header"

    def test_has_recent_learnings_header(self, fixture_project: Path) -> None:
        output = generate_codebase_summary(fixture_project)
        assert "## Recent Learnings" in output, "Missing Recent Learnings header"

    def test_button_in_component_registry(self, fixture_project: Path) -> None:
        output = generate_codebase_summary(fixture_project)
        assert "Button.tsx" in output, "Button.tsx not in component registry"

    def test_header_in_component_registry(self, fixture_project: Path) -> None:
        output = generate_codebase_summary(fixture_project)
        assert "Header.tsx" in output, "Header.tsx not in component registry"

    def test_button_has_export_default(self, fixture_project: Path) -> None:
        output = generate_codebase_summary(fixture_project)
        assert "Button.tsx  (export default: yes)" in output, (
            "Button.tsx should show export default: yes"
        )

    def test_user_type_in_exports(self, fixture_project: Path) -> None:
        output = generate_codebase_summary(fixture_project)
        assert "User" in output, "User type not in type exports"

    def test_apiresponse_in_exports(self, fixture_project: Path) -> None:
        output = generate_codebase_summary(fixture_project)
        assert "ApiResponse" in output, "ApiResponse interface not in type exports"

    def test_header_imports_button(self, fixture_project: Path) -> None:
        output = generate_codebase_summary(fixture_project)
        assert "Header.tsx" in output, "Header.tsx not found in import graph"

    def test_import_path_present(self, fixture_project: Path) -> None:
        output = generate_codebase_summary(fixture_project)
        assert "./Button" in output, "import path ./Button not present"

    def test_learnings_content(self, fixture_project: Path) -> None:
        output = generate_codebase_summary(fixture_project)
        assert "semantic tokens" in output, "Learnings content missing"


# ── Test: empty project ──────────────────────────────────────────────────────
# Mirrors bash test_empty_project: 6 assertions


class TestEmptyProject:
    """Empty project (no src/, no .specs/) — still produces all section headers."""

    def test_exits_successfully(self, tmp_path: Path) -> None:
        """Bash assertion: 'empty project exits 0'."""
        output = generate_codebase_summary(tmp_path)
        assert isinstance(output, str), "Expected string output"

    def test_has_component_registry_header(self, tmp_path: Path) -> None:
        output = generate_codebase_summary(tmp_path)
        assert "## Component Registry" in output

    def test_has_type_exports_header(self, tmp_path: Path) -> None:
        output = generate_codebase_summary(tmp_path)
        assert "## Type Exports" in output

    def test_has_import_graph_header(self, tmp_path: Path) -> None:
        output = generate_codebase_summary(tmp_path)
        assert "## Import Graph" in output

    def test_has_recent_learnings_header(self, tmp_path: Path) -> None:
        output = generate_codebase_summary(tmp_path)
        assert "## Recent Learnings" in output

    def test_no_components_message(self, tmp_path: Path) -> None:
        output = generate_codebase_summary(tmp_path)
        assert "No .tsx/.jsx files found" in output, "Missing no-components message"

    def test_no_learnings_message(self, tmp_path: Path) -> None:
        output = generate_codebase_summary(tmp_path)
        assert "No learnings directory found." in output, "Missing no-learnings message"


# ── Test: MAX_LINES truncation ───────────────────────────────────────────────
# Mirrors bash test_max_lines_truncation: 3 assertions


class TestMaxLinesTruncation:
    """MAX_LINES truncation — output is capped, truncation notice appears."""

    def test_exits_successfully(self, fixture_project: Path) -> None:
        output = generate_codebase_summary(fixture_project, max_lines=20)
        assert isinstance(output, str), "Expected string output"

    def test_truncation_notice_present(self, fixture_project: Path) -> None:
        output = generate_codebase_summary(fixture_project, max_lines=20)
        assert "[Summary truncated at 20 lines]" in output, "Truncation notice missing"

    def test_line_count_within_limit(self, fixture_project: Path) -> None:
        output = generate_codebase_summary(fixture_project, max_lines=20)
        # The output has a trailing newline on every line, so splitting on \n
        # gives lines + one empty string at the end.
        lines = output.split("\n")
        # Remove trailing empty string from the final newline
        if lines and lines[-1] == "":
            lines = lines[:-1]
        assert len(lines) <= 21, (
            f"Line count ({len(lines)}) exceeds MAX_LINES + 1 (21)"
        )


# ── Test: error handling (ValueError) ───────────────────────────────────────
# Additional tests for Python-specific behavior (replaces bash exit code checks)


class TestErrorHandling:
    """Error handling for invalid inputs."""

    def test_raises_on_nonexistent_directory(self, tmp_path: Path) -> None:
        nonexistent = tmp_path / "does_not_exist"
        with pytest.raises(ValueError, match="does not exist"):
            generate_codebase_summary(nonexistent)

    def test_raises_on_file_not_directory(self, tmp_path: Path) -> None:
        a_file = tmp_path / "not_a_dir.txt"
        a_file.write_text("hello")
        with pytest.raises(ValueError, match="not a directory"):
            generate_codebase_summary(a_file)


# ── Test: component cap truncation ──────────────────────────────────────────


class TestComponentCapTruncation:
    """Component registry caps at 50 entries."""

    def test_component_cap_message(self, tmp_path: Path) -> None:
        """When >50 component files exist, truncation message appears."""
        components_dir = tmp_path / "src" / "components"
        components_dir.mkdir(parents=True)
        for i in range(55):
            (components_dir / f"Comp{i:03d}.tsx").write_text(
                f"export default function Comp{i:03d}() {{ return null; }}\n"
            )
        output = generate_codebase_summary(tmp_path)
        assert "... and 5 more components (truncated at 50)" in output


# ── Test: no local imports ──────────────────────────────────────────────────


class TestNoLocalImports:
    """Import graph shows 'no local imports' when none exist."""

    def test_no_local_imports_message(self, tmp_path: Path) -> None:
        """Components with only external imports show 'No local imports found.'."""
        components_dir = tmp_path / "src" / "components"
        components_dir.mkdir(parents=True)
        (components_dir / "Solo.tsx").write_text(
            "import React from 'react';\n"
            "export default function Solo() { return null; }\n"
        )
        output = generate_codebase_summary(tmp_path)
        assert "No local imports found." in output


# ── Test: empty learnings files are skipped ─────────────────────────────────


class TestEmptyLearningsSkipped:
    """Empty .md files in learnings dir are skipped."""

    def test_empty_learnings_file_skipped(self, tmp_path: Path) -> None:
        learnings_dir = tmp_path / ".specs" / "learnings"
        learnings_dir.mkdir(parents=True)
        (learnings_dir / "empty.md").write_text("")
        output = generate_codebase_summary(tmp_path)
        assert "No learnings files found." in output

    def test_mixed_empty_and_nonempty(self, tmp_path: Path) -> None:
        """Non-empty files are included even when empty files exist."""
        learnings_dir = tmp_path / ".specs" / "learnings"
        learnings_dir.mkdir(parents=True)
        (learnings_dir / "empty.md").write_text("")
        (learnings_dir / "real.md").write_text("Real content here.\n")
        output = generate_codebase_summary(tmp_path)
        assert "Real content here." in output
        assert "No learnings files found." not in output


# ── Test: no type exports message ───────────────────────────────────────────


class TestNoTypeExports:
    """When no type/interface exports exist, shows fallback message."""

    def test_no_type_exports_message(self, tmp_path: Path) -> None:
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "index.ts").write_text(
            "export function hello(): string { return 'hi'; }\n"
        )
        output = generate_codebase_summary(tmp_path)
        assert "No type/interface exports found." in output
