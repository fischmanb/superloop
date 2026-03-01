# CONVERSION CHANGELOG (from lib/validation.sh)
# - validate_only parameter: preserved in signature for interface contract
#   compliance but remains a no-op, matching bash behavior where it is
#   accepted but never acted upon.
# - has_status: bash checks for the 'status' field but never uses the result
#   to determine pass/fail. Python mirrors this: status is not a required
#   field for validation.
# - Color codes (RED, YELLOW, NC): replaced by structured logging via
#   logger.warning(). No ANSI escape codes in Python output.
# - Guard against double-sourcing (_VALIDATION_SH_LOADED): not applicable
#   in Python module system; omitted.
# - Return type: bash returns exit code 0/1. Python returns bool.
# - Error reporting: bash writes to stderr with echo -e. Python uses
#   logger.warning(), which by default goes to stderr via logging config.
# - InvalidSpecError defined inline per task instructions (errors.py does
#   not exist yet).

"""Validation utilities for SDD feature spec files."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Inline exception hierarchy (until errors.py exists) ──────────────────────


class AutoSddError(Exception):
    """Base for all auto-sdd errors."""


class InvalidSpecError(AutoSddError):
    """Feature spec fails frontmatter validation."""


# ── Constants ────────────────────────────────────────────────────────────────

REQUIRED_FIELDS: frozenset[str] = frozenset({"feature", "domain"})
_FRONTMATTER_MARKER: str = "---"
_MAX_HEADER_LINES: int = 20


# ── Public API ───────────────────────────────────────────────────────────────


def validate_frontmatter(file_path: Path, validate_only: bool = False) -> bool:
    """Validate that a feature spec has well-formed YAML frontmatter.

    Checks for balanced ``---`` markers within the first 20 lines and
    verifies that the required fields (``feature``, ``domain``) are present.

    Args:
        file_path: Path to the feature spec file.
        validate_only: Accepted for interface compatibility; currently unused
            (mirrors bash behavior).

    Returns:
        ``True`` if frontmatter is valid, ``False`` otherwise.
    """
    try:
        lines = file_path.read_text().splitlines()
    except OSError:
        logger.warning("%s — could not read file, skipping", file_path)
        return False

    # Check first line is ---
    if not lines or lines[0] != _FRONTMATTER_MARKER:
        logger.warning(
            "%s — missing opening --- marker, skipping", file_path
        )
        return False

    # Check for closing --- within first 20 lines
    header = lines[:_MAX_HEADER_LINES]
    marker_count = sum(1 for line in header if line == _FRONTMATTER_MARKER)
    if marker_count < 2:
        logger.warning(
            "%s — missing closing --- marker in first 20 lines, skipping",
            file_path,
        )
        return False

    # Extract frontmatter between the two --- markers
    frontmatter_lines = _extract_frontmatter(lines)

    # Check required fields
    present_fields = {
        line.split(":", 1)[0]
        for line in frontmatter_lines
        if ":" in line
    }

    for field in sorted(REQUIRED_FIELDS):
        if field not in present_fields:
            logger.warning(
                "%s — missing required field '%s', skipping",
                file_path,
                field,
            )
            return False

    return True


# ── Private helpers ──────────────────────────────────────────────────────────


def _extract_frontmatter(lines: list[str]) -> list[str]:
    """Return lines between the first and second ``---`` markers."""
    result: list[str] = []
    marker_seen = 0
    for line in lines:
        if line == _FRONTMATTER_MARKER:
            marker_seen += 1
            if marker_seen == 2:
                break
            continue
        if marker_seen == 1:
            result.append(line)
    return result
