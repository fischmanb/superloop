"""Tests for auto_sdd.scripts.generate_mapping — mapping.md generation."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from auto_sdd.scripts.generate_mapping import (
    FeatureSpec,
    _escape_pipes,
    _parse_list,
    _parse_scalar,
    extract_frontmatter,
    generate_mapping,
    main,
    parse_feature_spec,
)


# ── Helper to create spec files ──────────────────────────────────────────────


def _write_spec(
    features_dir: Path,
    domain: str,
    filename: str,
    *,
    feature: str = "Test Feature",
    source: str = "src/test.ts",
    status: str = "stub",
    tests: list[str] | None = None,
    components: list[str] | None = None,
    extra_frontmatter: str = "",
    body: str = "# Feature\n",
) -> Path:
    """Create a feature spec file with frontmatter."""
    domain_dir = features_dir / domain
    domain_dir.mkdir(parents=True, exist_ok=True)
    spec_file = domain_dir / filename

    fm_lines = [
        "---",
        f"feature: {feature}",
        f"domain: {domain}",
        f"source: {source}",
        f"status: {status}",
    ]
    if tests:
        fm_lines.append("tests:")
        for t in tests:
            fm_lines.append(f"  - {t}")
    if components:
        fm_lines.append("components:")
        for c in components:
            fm_lines.append(f"  - {c}")
    if extra_frontmatter:
        fm_lines.append(extra_frontmatter)
    fm_lines.append("---")
    fm_lines.append(body)

    spec_file.write_text("\n".join(fm_lines))
    return spec_file


# ── extract_frontmatter tests ────────────────────────────────────────────────


class TestExtractFrontmatter:
    """Tests for extract_frontmatter."""

    def test_valid_frontmatter(self, tmp_path: Path) -> None:
        spec = tmp_path / "spec.md"
        spec.write_text("---\nfeature: auth\ndomain: core\n---\n# Body\n")
        lines = extract_frontmatter(spec)
        assert lines == ["feature: auth", "domain: core"]

    def test_no_frontmatter(self, tmp_path: Path) -> None:
        spec = tmp_path / "spec.md"
        spec.write_text("# No frontmatter\nJust body.\n")
        lines = extract_frontmatter(spec)
        assert lines == []

    def test_multiple_dashes_in_body(self, tmp_path: Path) -> None:
        spec = tmp_path / "spec.md"
        spec.write_text(
            "---\nfeature: auth\n---\n# Body\n---\nHorizontal rule\n---\n"
        )
        lines = extract_frontmatter(spec)
        assert lines == ["feature: auth"]

    def test_empty_frontmatter(self, tmp_path: Path) -> None:
        spec = tmp_path / "spec.md"
        spec.write_text("---\n---\n# Body\n")
        lines = extract_frontmatter(spec)
        assert lines == []

    def test_single_marker_only(self, tmp_path: Path) -> None:
        spec = tmp_path / "spec.md"
        spec.write_text("---\nfeature: auth\n# No closing marker\n")
        lines = extract_frontmatter(spec)
        # Returns everything after first marker since second is never hit
        assert "feature: auth" in lines


# ── _parse_scalar tests ───────────────────────────────────────────────────────


class TestParseScalar:
    """Tests for _parse_scalar."""

    def test_simple_value(self) -> None:
        lines = ["feature: auth login", "domain: core"]
        assert _parse_scalar(lines, "feature", "Unknown") == "auth login"

    def test_missing_key_returns_default(self) -> None:
        lines = ["feature: auth"]
        assert _parse_scalar(lines, "domain", "unknown") == "unknown"

    def test_quoted_value(self) -> None:
        lines = ['feature: "my feature"']
        assert _parse_scalar(lines, "feature", "Unknown") == "my feature"

    def test_single_quoted_value(self) -> None:
        lines = ["feature: 'my feature'"]
        assert _parse_scalar(lines, "feature", "Unknown") == "my feature"

    def test_empty_value_returns_default(self) -> None:
        lines = ["feature:"]
        assert _parse_scalar(lines, "feature", "Unknown") == "Unknown"


# ── _parse_list tests ─────────────────────────────────────────────────────────


class TestParseList:
    """Tests for _parse_list."""

    def test_block_list(self) -> None:
        lines = ["tests:", "  - test1.ts", "  - test2.ts", "status: done"]
        result = _parse_list(lines, "tests")
        assert result == ["test1.ts", "test2.ts"]

    def test_inline_list(self) -> None:
        lines = ["components: [Button, Card, Modal]"]
        result = _parse_list(lines, "components")
        assert result == ["Button", "Card", "Modal"]

    def test_missing_key_returns_empty(self) -> None:
        lines = ["feature: auth"]
        result = _parse_list(lines, "tests")
        assert result == []

    def test_empty_block_list(self) -> None:
        lines = ["tests:", "status: done"]
        result = _parse_list(lines, "tests")
        assert result == []

    def test_quoted_items_in_inline_list(self) -> None:
        lines = ["components: ['Button', 'Card']"]
        result = _parse_list(lines, "components")
        assert result == ["Button", "Card"]


# ── parse_feature_spec tests ─────────────────────────────────────────────────


class TestParseFeatureSpec:
    """Tests for parse_feature_spec."""

    def test_valid_spec(self, tmp_path: Path) -> None:
        features_dir = tmp_path / "features"
        spec = _write_spec(
            features_dir,
            "auth",
            "login.feature.md",
            feature="Login",
            source="src/login.ts",
            status="implemented",
            tests=["tests/login.test.ts"],
            components=["LoginForm"],
        )
        result = parse_feature_spec(spec)
        assert result is not None
        assert result.feature == "Login"
        assert result.domain == "auth"
        assert result.source == "src/login.ts"
        assert result.status == "implemented"
        assert result.tests == ["tests/login.test.ts"]
        assert result.components == ["LoginForm"]
        assert result.file_path == spec

    def test_minimal_spec(self, tmp_path: Path) -> None:
        spec = tmp_path / "minimal.feature.md"
        spec.write_text("---\nfeature: Test\ndomain: core\n---\n# Body\n")
        result = parse_feature_spec(spec)
        assert result is not None
        assert result.feature == "Test"
        assert result.status == "stub"
        assert result.tests == []
        assert result.components == []

    def test_missing_required_field_returns_none(self, tmp_path: Path) -> None:
        spec = tmp_path / "bad.feature.md"
        spec.write_text("---\nfeature: Test\n---\n# Body\n")
        result = parse_feature_spec(spec)
        assert result is None

    def test_no_frontmatter_returns_none(self, tmp_path: Path) -> None:
        spec = tmp_path / "nofm.feature.md"
        spec.write_text("# Just body\n")
        result = parse_feature_spec(spec)
        assert result is None

    def test_invalid_file_returns_none(self, tmp_path: Path) -> None:
        spec = tmp_path / "nonexistent.feature.md"
        result = parse_feature_spec(spec)
        assert result is None


# ── _escape_pipes tests ──────────────────────────────────────────────────────


class TestEscapePipes:
    """Tests for _escape_pipes."""

    def test_no_pipes(self) -> None:
        assert _escape_pipes("hello world") == "hello world"

    def test_single_pipe(self) -> None:
        assert _escape_pipes("a|b") == "a\\|b"

    def test_multiple_pipes(self) -> None:
        assert _escape_pipes("a|b|c") == "a\\|b\\|c"


# ── generate_mapping tests ───────────────────────────────────────────────────


class TestGenerateMapping:
    """Tests for generate_mapping."""

    def test_empty_specs_dir(self, tmp_path: Path) -> None:
        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()
        content = generate_mapping(specs_dir)
        assert "Feature ↔ Test ↔ Component Mapping" in content
        assert "_No features yet_" in content
        assert "**Total** | **0**" in content

    def test_single_feature(self, tmp_path: Path) -> None:
        specs_dir = tmp_path / ".specs"
        features_dir = specs_dir / "features"
        _write_spec(
            features_dir,
            "auth",
            "login.feature.md",
            feature="Login",
            status="implemented",
        )
        content = generate_mapping(specs_dir)
        assert "Login" in content
        assert "implemented" in content
        assert "| **Total** | **1**" in content

    def test_multiple_features_counted(self, tmp_path: Path) -> None:
        specs_dir = tmp_path / ".specs"
        features_dir = specs_dir / "features"
        _write_spec(
            features_dir, "auth", "login.feature.md",
            feature="Login", status="stub",
        )
        _write_spec(
            features_dir, "auth", "signup.feature.md",
            feature="Signup", status="specced",
        )
        _write_spec(
            features_dir, "dashboard", "overview.feature.md",
            feature="Overview", status="implemented",
        )
        content = generate_mapping(specs_dir)
        assert "| **Total** | **3**" in content
        assert "| stub | 1 |" in content
        assert "| specced | 1 |" in content
        assert "| implemented | 1 |" in content

    def test_status_grouping_sections(self, tmp_path: Path) -> None:
        specs_dir = tmp_path / ".specs"
        features_dir = specs_dir / "features"
        _write_spec(
            features_dir, "auth", "login.feature.md",
            feature="Login", status="stub",
        )
        _write_spec(
            features_dir, "auth", "signup.feature.md",
            feature="Signup", status="tested",
        )
        content = generate_mapping(specs_dir)
        assert "### Stub" in content
        assert "### Tested" in content
        assert "Login" in content
        assert "Signup" in content

    def test_empty_status_shows_none(self, tmp_path: Path) -> None:
        specs_dir = tmp_path / ".specs"
        features_dir = specs_dir / "features"
        _write_spec(
            features_dir, "auth", "login.feature.md",
            feature="Login", status="stub",
        )
        content = generate_mapping(specs_dir)
        # specced, tested, implemented sections should show _None_
        # (only stub has entries)
        lines = content.splitlines()
        # Find "### Specced" and check next non-empty line is _None_
        for i, line in enumerate(lines):
            if line == "### Specced":
                next_content = ""
                for j in range(i + 1, len(lines)):
                    if lines[j].strip():
                        next_content = lines[j].strip()
                        break
                assert next_content == "_None_"
                break

    def test_pipe_in_feature_name_escaped(self, tmp_path: Path) -> None:
        specs_dir = tmp_path / ".specs"
        features_dir = specs_dir / "features"
        _write_spec(
            features_dir, "core", "pipe.feature.md",
            feature="A|B Feature", status="stub",
        )
        content = generate_mapping(specs_dir)
        assert "A\\|B Feature" in content

    def test_design_system_components(self, tmp_path: Path) -> None:
        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()
        ds_dir = specs_dir / "design-system" / "components"
        ds_dir.mkdir(parents=True)
        (ds_dir / "button.md").write_text("# Button\n\nStatus: Documented\n")
        (ds_dir / "card.md").write_text("# Card\n\nStatus: Stub\n")
        (ds_dir / "_template.md").write_text("# Template\n")

        content = generate_mapping(specs_dir)
        assert "button" in content
        assert "card" in content
        assert "_template" not in content
        assert "stub" in content.lower()

    def test_no_design_components(self, tmp_path: Path) -> None:
        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()
        content = generate_mapping(specs_dir)
        assert "_No components documented_" in content

    def test_legend_present(self, tmp_path: Path) -> None:
        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()
        content = generate_mapping(specs_dir)
        assert "## Legend" in content
        assert "stub" in content
        assert "specced" in content
        assert "tested" in content
        assert "implemented" in content

    def test_footer_present(self, tmp_path: Path) -> None:
        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()
        content = generate_mapping(specs_dir)
        assert "## How This File Works" in content
        assert "### Frontmatter Format" in content

    def test_tests_and_components_in_table(self, tmp_path: Path) -> None:
        specs_dir = tmp_path / ".specs"
        features_dir = specs_dir / "features"
        _write_spec(
            features_dir, "core", "feat.feature.md",
            feature="Feat",
            tests=["tests/a.test.ts", "tests/b.test.ts"],
            components=["Button", "Card"],
        )
        content = generate_mapping(specs_dir)
        assert "tests/a.test.ts" in content
        assert "Button" in content

    def test_no_tests_shows_dash(self, tmp_path: Path) -> None:
        specs_dir = tmp_path / ".specs"
        features_dir = specs_dir / "features"
        _write_spec(
            features_dir, "core", "feat.feature.md",
            feature="MyUniqueFeat",
        )
        content = generate_mapping(specs_dir)
        # The row should have "-" for tests and components
        lines = [
            line for line in content.splitlines()
            if "MyUniqueFeat" in line and "|" in line
        ]
        assert len(lines) == 1
        assert "| - |" in lines[0]

    def test_invalid_specs_skipped(self, tmp_path: Path) -> None:
        specs_dir = tmp_path / ".specs"
        features_dir = specs_dir / "features" / "core"
        features_dir.mkdir(parents=True)

        # Valid spec
        _write_spec(
            specs_dir / "features", "core", "good.feature.md",
            feature="Good",
        )
        # Invalid spec (no frontmatter)
        bad = features_dir / "bad.feature.md"
        bad.write_text("# No frontmatter\n")

        content = generate_mapping(specs_dir)
        assert "Good" in content
        assert "| **Total** | **1**" in content


# ── CLI (main) tests ─────────────────────────────────────────────────────────


class TestMainCli:
    """Tests for the CLI entry point."""

    def test_validate_only_success(self, tmp_path: Path) -> None:
        specs_dir = tmp_path / ".specs"
        features_dir = specs_dir / "features"
        _write_spec(
            features_dir, "core", "good.feature.md",
            feature="Good",
        )
        with pytest.raises(SystemExit) as exc_info:
            with patch(
                "sys.argv",
                ["generate_mapping", "--validate-only", "--specs-dir", str(specs_dir)],
            ):
                main()
        assert exc_info.value.code == 0

    def test_validate_only_failure(self, tmp_path: Path) -> None:
        specs_dir = tmp_path / ".specs"
        features_dir = specs_dir / "features" / "core"
        features_dir.mkdir(parents=True)
        bad = features_dir / "bad.feature.md"
        bad.write_text("# No frontmatter\n")

        with pytest.raises(SystemExit) as exc_info:
            with patch(
                "sys.argv",
                ["generate_mapping", "--validate-only", "--specs-dir", str(specs_dir)],
            ):
                main()
        assert exc_info.value.code == 1

    def test_generate_mode_writes_file(self, tmp_path: Path) -> None:
        specs_dir = tmp_path / ".specs"
        features_dir = specs_dir / "features"
        _write_spec(
            features_dir, "core", "feat.feature.md",
            feature="Feat",
        )
        with patch(
            "sys.argv",
            ["generate_mapping", "--specs-dir", str(specs_dir)],
        ):
            main()

        output = specs_dir / "mapping.md"
        assert output.exists()
        content = output.read_text()
        assert "Feat" in content

    def test_validate_only_no_features_dir(self, tmp_path: Path) -> None:
        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()
        with pytest.raises(SystemExit) as exc_info:
            with patch(
                "sys.argv",
                ["generate_mapping", "--validate-only", "--specs-dir", str(specs_dir)],
            ):
                main()
        assert exc_info.value.code == 0
