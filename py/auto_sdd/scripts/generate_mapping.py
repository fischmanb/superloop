# CONVERSION CHANGELOG (from scripts/generate-mapping.sh)
# - YAML parsing: bash uses yq (with grep fallback); Python uses a simple
#   regex parser since PyYAML is not in dependencies. The frontmatter format
#   is simple key: value pairs, so regex is sufficient and reliable.
# - extract_frontmatter: bash uses awk; Python uses line-by-line iteration
#   with the same two-marker logic.
# - validate_frontmatter: delegates to validation.validate_frontmatter()
#   from the already-converted lib module.
# - Color codes (RED, GREEN, YELLOW, NC): replaced by logger messages.
# - Output file writing: bash uses cat heredocs + echo >> ; Python builds
#   the full string then writes atomically.
# - Design system component listing: bash globs *.md; Python uses
#   pathlib.glob() with the same _template.md exclusion.
# - Array extraction (tests, components): bash uses yq or "see spec"
#   fallback; Python parses YAML list items (lines starting with "  - ").
"""Generate ``.specs/mapping.md`` from feature spec YAML frontmatter.

Reads all ``*.feature.md`` files under ``.specs/features/``, parses their
YAML frontmatter, and produces a Markdown table mapping features to tests,
components, and status.
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from auto_sdd.lib.validation import validate_frontmatter

logger = logging.getLogger(__name__)

# ── Data structures ───────────────────────────────────────────────────────────


@dataclass
class FeatureSpec:
    """Parsed feature spec metadata."""

    feature: str
    domain: str
    source: str
    status: str  # stub | specced | tested | implemented
    tests: list[str]
    components: list[str]
    file_path: Path


# ── Frontmatter extraction ────────────────────────────────────────────────────


def extract_frontmatter(file_path: Path) -> list[str]:
    """Extract YAML lines between the first two ``---`` markers.

    Returns an empty list if the file has no valid frontmatter.
    """
    lines = file_path.read_text().splitlines()
    result: list[str] = []
    marker_count = 0

    for line in lines:
        if line == "---":
            marker_count += 1
            if marker_count == 2:
                break
            continue
        if marker_count == 1:
            result.append(line)

    return result


# ── Frontmatter parsing ──────────────────────────────────────────────────────


def _parse_scalar(lines: list[str], key: str, default: str) -> str:
    """Extract a scalar value from frontmatter lines.

    Looks for ``key: value`` patterns. Returns *default* if not found.
    """
    pattern = re.compile(rf"^{re.escape(key)}:\s*(.*)")
    for line in lines:
        m = pattern.match(line)
        if m:
            val = m.group(1).strip()
            # Strip surrounding quotes
            if len(val) >= 2 and val[0] in ('"', "'") and val[-1] == val[0]:
                val = val[1:-1]
            return val or default
    return default


def _parse_list(lines: list[str], key: str) -> list[str]:
    """Extract a YAML list from frontmatter lines.

    Handles both inline ``key: [a, b]`` and block format::

        key:
          - item1
          - item2
    """
    items: list[str] = []
    in_list = False

    for i, line in enumerate(lines):
        # Check for key line
        if re.match(rf"^{re.escape(key)}:", line):
            # Check for inline list: key: [a, b, c]
            inline_match = re.search(r"\[(.+)]", line)
            if inline_match:
                for item in inline_match.group(1).split(","):
                    item = item.strip().strip("'\"")
                    if item:
                        items.append(item)
                return items
            # Otherwise, expect block list on following lines
            in_list = True
            continue

        if in_list:
            stripped = line.strip()
            if stripped.startswith("- "):
                items.append(stripped[2:].strip().strip("'\""))
            elif stripped and not stripped.startswith("#"):
                # Hit a new key or non-list content — stop
                break

    return items


def parse_feature_spec(file_path: Path) -> FeatureSpec | None:
    """Parse frontmatter into FeatureSpec. Returns None if invalid.

    Uses :func:`~auto_sdd.lib.validation.validate_frontmatter` to check
    structural validity, then extracts fields with regex.
    """
    if not validate_frontmatter(file_path):
        return None

    fm_lines = extract_frontmatter(file_path)
    if not fm_lines:
        return None

    return FeatureSpec(
        feature=_parse_scalar(fm_lines, "feature", "Unknown"),
        domain=_parse_scalar(fm_lines, "domain", "unknown"),
        source=_parse_scalar(fm_lines, "source", "-"),
        status=_parse_scalar(fm_lines, "status", "stub"),
        tests=_parse_list(fm_lines, "tests"),
        components=_parse_list(fm_lines, "components"),
        file_path=file_path,
    )


# ── Mapping generation ────────────────────────────────────────────────────────

_VALID_STATUSES = ("stub", "specced", "tested", "implemented")


def _escape_pipes(text: str) -> str:
    """Escape pipe characters for Markdown tables."""
    return text.replace("|", "\\|")


def generate_mapping(specs_dir: Path) -> str:
    """Generate complete ``mapping.md`` content from feature specs.

    Scans ``{specs_dir}/features/`` for ``*.feature.md`` files, parses
    their frontmatter, and builds the Markdown mapping document.
    """
    features_dir = specs_dir / "features"
    specs: list[FeatureSpec] = []

    if features_dir.is_dir():
        for spec_file in sorted(features_dir.rglob("*.feature.md")):
            parsed = parse_feature_spec(spec_file)
            if parsed is not None:
                specs.append(parsed)

    parts: list[str] = []

    # Header
    parts.append("# Feature ↔ Test ↔ Component Mapping\n")
    parts.append("_Auto-generated from feature specs. Do not edit directly._")
    parts.append(
        "_Regenerate with: `./scripts/generate-mapping.sh`_\n"
    )

    # Legend
    parts.append("## Legend\n")
    parts.append("| Status | Meaning |")
    parts.append("|--------|---------|")
    parts.append("| stub | Spec created, not yet tested |")
    parts.append("| specced | Spec complete with scenarios |")
    parts.append("| tested | Tests written |")
    parts.append("| implemented | Feature complete |\n")
    parts.append("---\n")

    # Features table
    parts.append("## Features\n")
    parts.append(
        "| Domain | Feature | Source | Tests | Components | Status |"
    )
    parts.append(
        "|--------|---------|--------|-------|------------|--------|"
    )

    # Status counters
    counts: dict[str, int] = {s: 0 for s in _VALID_STATUSES}

    if not specs:
        parts.append("| _No features yet_ | | | | | |")
    else:
        for spec in specs:
            # Count by status
            if spec.status in counts:
                counts[spec.status] += 1

            # Build table row
            rel_path = str(spec.file_path)
            # Try to make relative to current dir
            try:
                rel_path = str(spec.file_path.relative_to(Path.cwd()))
            except ValueError:
                pass

            feature_escaped = _escape_pipes(spec.feature)
            source_escaped = _escape_pipes(spec.source)
            tests_str = _escape_pipes(
                ", ".join(spec.tests) if spec.tests else "-"
            )
            components_str = _escape_pipes(
                ", ".join(spec.components) if spec.components else "-"
            )

            parts.append(
                f"| {spec.domain} "
                f"| [{feature_escaped}]({rel_path}) "
                f"| `{source_escaped}` "
                f"| {tests_str} "
                f"| {components_str} "
                f"| {spec.status} |"
            )

    total = len(specs)

    # Summary section
    parts.append("\n---\n")
    parts.append("## Summary\n")
    parts.append("| Status | Count |")
    parts.append("|--------|-------|")
    for status in _VALID_STATUSES:
        parts.append(f"| {status} | {counts[status]} |")
    parts.append(f"| **Total** | **{total}** |\n")
    parts.append("---\n")

    # By Status section
    parts.append("## By Status\n")
    for status in _VALID_STATUSES:
        status_capitalized = status[0].upper() + status[1:]
        parts.append(f"### {status_capitalized}\n")

        status_specs = [s for s in specs if s.status == status]
        if not status_specs:
            parts.append("_None_\n")
        else:
            for spec in status_specs:
                rel_path = str(spec.file_path)
                try:
                    rel_path = str(spec.file_path.relative_to(Path.cwd()))
                except ValueError:
                    pass
                parts.append(f"- [{spec.feature}]({rel_path})")
            parts.append("")

    # Design system section
    parts.append("---\n")
    parts.append("## Design System\n")
    parts.append(
        "See `.specs/design-system/tokens.md` for token reference.\n"
    )
    parts.append("### Documented Components\n")
    parts.append("| Component | Status | Source |")
    parts.append("|-----------|--------|--------|")

    ds_dir = specs_dir / "design-system" / "components"
    found_components = False
    if ds_dir.is_dir():
        for comp_file in sorted(ds_dir.glob("*.md")):
            if comp_file.name == "_template.md":
                continue
            comp_name = comp_file.stem
            comp_status = "documented"
            try:
                content = comp_file.read_text()
                if "Status" in content and "Stub" in content:
                    comp_status = "stub"
            except OSError:
                pass
            rel_path = str(comp_file)
            try:
                rel_path = str(comp_file.relative_to(Path.cwd()))
            except ValueError:
                pass
            parts.append(
                f"| {comp_name} | {comp_status} | [doc]({rel_path}) |"
            )
            found_components = True

    if not found_components:
        parts.append("| _No components documented_ | | |")

    # Footer
    parts.append("\n---\n")
    parts.append("## How This File Works\n")
    parts.append(
        "This file is **auto-generated** from feature spec YAML frontmatter.\n"
    )
    parts.append("**Do not edit this file directly.** Instead:")
    parts.append(
        "1. Update the feature spec's YAML frontmatter"
    )
    parts.append(
        "2. Run `./scripts/generate-mapping.sh` "
        "(or it runs automatically via Cursor hook)\n"
    )
    parts.append("### Frontmatter Format\n")
    parts.append("```yaml")
    parts.append("---")
    parts.append("feature: Feature Name")
    parts.append("domain: domain-name")
    parts.append("source: path/to/source.tsx")
    parts.append("tests:")
    parts.append("  - path/to/test.ts")
    parts.append("components:")
    parts.append("  - ComponentName")
    parts.append("status: stub | specced | tested | implemented")
    parts.append("created: YYYY-MM-DD")
    parts.append("updated: YYYY-MM-DD")
    parts.append("---")
    parts.append("```")

    return "\n".join(parts) + "\n"


# ── CLI entry point ───────────────────────────────────────────────────────────


def main() -> None:
    """CLI entry point. Supports ``--validate-only`` flag."""
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(
        description="Generate .specs/mapping.md from feature spec frontmatter"
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only validate frontmatter, do not generate mapping",
    )
    parser.add_argument(
        "--specs-dir",
        type=Path,
        default=Path(".specs"),
        help="Path to .specs directory (default: .specs)",
    )
    args = parser.parse_args()

    specs_dir: Path = args.specs_dir
    features_dir = specs_dir / "features"

    if args.validate_only:
        logger.info("Validating frontmatter in feature specs...")
        validation_errors = 0
        if features_dir.is_dir():
            for spec_file in sorted(features_dir.rglob("*.feature.md")):
                if not validate_frontmatter(spec_file, validate_only=True):
                    validation_errors += 1
        if validation_errors > 0:
            logger.error(
                "Found %d file(s) with invalid frontmatter",
                validation_errors,
            )
            sys.exit(1)
        else:
            logger.info("All feature specs have valid frontmatter")
            sys.exit(0)

    output_path = specs_dir / "mapping.md"
    content = generate_mapping(specs_dir)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content)

    # Count features for summary message
    feature_count = 0
    if features_dir.is_dir():
        for spec_file in features_dir.rglob("*.feature.md"):
            if validate_frontmatter(spec_file):
                feature_count += 1

    logger.info("Generated %s with %d features", output_path, feature_count)


if __name__ == "__main__":
    main()
