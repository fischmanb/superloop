"""Tests for auto_sdd.lib.validation — frontmatter validation."""

from pathlib import Path

import pytest

from auto_sdd.lib.validation import (
    REQUIRED_FIELDS,
    InvalidSpecError,
    validate_frontmatter,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def valid_spec(tmp_path: Path) -> Path:
    """A feature spec with complete, valid frontmatter."""
    spec = tmp_path / "valid.feature.md"
    spec.write_text(
        "---\n"
        "feature: User Login\n"
        "domain: auth\n"
        "source: src/auth/login.tsx\n"
        "status: specced\n"
        "created: 2026-01-15\n"
        "---\n"
        "# Feature: User Login\n"
        "\n"
        "## Scenario: Happy path\n"
        "Given a registered user\n"
        "When they submit valid credentials\n"
        "Then they are redirected to the dashboard\n"
    )
    return spec


# ── Tests: valid frontmatter ─────────────────────────────────────────────────


def test_validate_frontmatter_valid_spec(valid_spec: Path) -> None:
    """Valid frontmatter with all required fields passes."""
    assert validate_frontmatter(valid_spec) is True


def test_validate_frontmatter_uses_sample_spec_fixture(
    sample_spec: Path,
) -> None:
    """The shared sample_spec fixture from conftest also passes."""
    assert validate_frontmatter(sample_spec) is True


# ── Tests: missing required fields ───────────────────────────────────────────


def test_validate_frontmatter_missing_feature_field(tmp_path: Path) -> None:
    """Missing 'feature' field returns False."""
    spec = tmp_path / "no-feature.feature.md"
    spec.write_text(
        "---\n"
        "domain: auth\n"
        "status: specced\n"
        "---\n"
        "# Some content\n"
    )
    assert validate_frontmatter(spec) is False


def test_validate_frontmatter_missing_domain_field(tmp_path: Path) -> None:
    """Missing 'domain' field returns False."""
    spec = tmp_path / "no-domain.feature.md"
    spec.write_text(
        "---\n"
        "feature: User Login\n"
        "status: specced\n"
        "---\n"
        "# Some content\n"
    )
    assert validate_frontmatter(spec) is False


# ── Tests: malformed markers ─────────────────────────────────────────────────


def test_validate_frontmatter_missing_opening_marker(tmp_path: Path) -> None:
    """File without opening --- marker returns False."""
    spec = tmp_path / "no-open.feature.md"
    spec.write_text(
        "feature: User Login\n"
        "domain: auth\n"
        "---\n"
        "# Some content\n"
    )
    assert validate_frontmatter(spec) is False


def test_validate_frontmatter_missing_closing_marker(tmp_path: Path) -> None:
    """File without closing --- marker returns False."""
    spec = tmp_path / "no-close.feature.md"
    spec.write_text(
        "---\n"
        "feature: User Login\n"
        "domain: auth\n"
        "status: specced\n"
        "# Some content without closing marker\n"
    )
    assert validate_frontmatter(spec) is False


def test_validate_frontmatter_empty_file(tmp_path: Path) -> None:
    """Empty file returns False."""
    spec = tmp_path / "empty.feature.md"
    spec.write_text("")
    assert validate_frontmatter(spec) is False


# ── Tests: edge cases ────────────────────────────────────────────────────────


def test_validate_frontmatter_nonexistent_file(tmp_path: Path) -> None:
    """File that does not exist returns False."""
    missing = tmp_path / "does-not-exist.feature.md"
    assert validate_frontmatter(missing) is False


def test_validate_frontmatter_validate_only_param(valid_spec: Path) -> None:
    """validate_only parameter is accepted without changing behavior."""
    assert validate_frontmatter(valid_spec, validate_only=True) is True


def test_validate_frontmatter_status_not_required(tmp_path: Path) -> None:
    """Status field is NOT required — matches bash behavior."""
    spec = tmp_path / "no-status.feature.md"
    spec.write_text(
        "---\n"
        "feature: User Login\n"
        "domain: auth\n"
        "---\n"
        "# Some content\n"
    )
    assert validate_frontmatter(spec) is True


def test_required_fields_constant() -> None:
    """REQUIRED_FIELDS contains exactly feature and domain."""
    assert REQUIRED_FIELDS == frozenset({"feature", "domain"})


def test_validate_frontmatter_closing_marker_beyond_20_lines(
    tmp_path: Path,
) -> None:
    """Closing marker beyond line 20 is treated as missing."""
    spec = tmp_path / "late-close.feature.md"
    # 1 line for opening ---, 19 filler lines, then closing ---  on line 21
    filler = "".join(f"line: {i}\n" for i in range(19))
    spec.write_text(f"---\nfeature: X\ndomain: Y\n{filler}---\n# Body\n")
    assert validate_frontmatter(spec) is False
