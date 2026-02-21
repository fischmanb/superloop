#!/bin/bash
# lib/validation.sh — Shared validation utilities for SDD orchestration scripts
#
# Source this file after defining logging/color variables if needed.
# Provides YAML frontmatter validation for feature spec files.
#
# Required globals (set before sourcing or by caller):
#   RED, YELLOW, NC  - ANSI color codes (fallback provided if unset)
#
# Functions provided:
#   validate_frontmatter  (validates YAML frontmatter in feature spec files)

# Guard against double-sourcing
if [ "${_VALIDATION_SH_LOADED:-}" = "true" ]; then
    return 0 2>/dev/null || true
fi
_VALIDATION_SH_LOADED=true

# ── Fallback color codes (caller can override before sourcing) ────────────────
RED="${RED:-\033[0;31m}"
YELLOW="${YELLOW:-\033[1;33m}"
NC="${NC:-\033[0m}"

# ── YAML frontmatter validation ──────────────────────────────────────────────

# Validate that a feature spec has well-formed YAML frontmatter.
# Checks for balanced --- markers and required fields.
# Returns 0 if valid, 1 if invalid.
validate_frontmatter() {
    local file="$1"
    local validate_only="${2:-false}"

    # Check first line is ---
    if ! head -1 "$file" | grep -q "^---$"; then
        echo -e "${YELLOW}Warning: $file — missing opening --- marker, skipping${NC}" >&2
        return 1
    fi

    # Check for closing --- within first 20 lines
    local marker_count
    marker_count=$(head -20 "$file" | grep -c "^---$" 2>/dev/null || echo "0")
    if [ "$marker_count" -lt 2 ]; then
        echo -e "${YELLOW}Warning: $file — missing closing --- marker in first 20 lines, skipping${NC}" >&2
        return 1
    fi

    # Check required fields exist in frontmatter
    local frontmatter
    frontmatter=$(awk 'BEGIN{c=0} /^---$/{c++; if(c==2) exit; next} c==1{print}' "$file")

    local has_feature has_domain has_status
    has_feature=$(echo "$frontmatter" | grep -c "^feature:" 2>/dev/null) || true
    has_domain=$(echo "$frontmatter" | grep -c "^domain:" 2>/dev/null) || true
    has_status=$(echo "$frontmatter" | grep -c "^status:" 2>/dev/null) || true

    if [ "$has_feature" -eq 0 ]; then
        echo -e "${YELLOW}Warning: $file — missing required field 'feature', skipping${NC}" >&2
        return 1
    fi
    if [ "$has_domain" -eq 0 ]; then
        echo -e "${YELLOW}Warning: $file — missing required field 'domain', skipping${NC}" >&2
        return 1
    fi

    return 0
}
