#!/usr/bin/env bash
# lib/codebase-summary.sh — Generates a concise codebase summary for build agent prompts
#
# Source this file, then call generate_codebase_summary.
# No code runs at source time.
#
# Functions provided:
#   generate_codebase_summary <PROJECT_DIR> [MAX_LINES]
#
# Arguments:
#   PROJECT_DIR  - Absolute path to the project being scanned (required)
#   MAX_LINES    - Cap on total output lines (optional, default 200)
#
# Output:
#   Structured plain-text summary to stdout with four sections:
#     ## Component Registry
#     ## Type Exports
#     ## Import Graph
#     ## Recent Learnings

# Guard against double-sourcing
if [ "${_CODEBASE_SUMMARY_SH_LOADED:-}" = "true" ]; then
    return 0 2>/dev/null || true
fi
_CODEBASE_SUMMARY_SH_LOADED=true

generate_codebase_summary() {
    local project_dir="${1:-}"
    local max_lines="${2:-200}"

    if [ -z "$project_dir" ]; then
        echo "generate_codebase_summary: PROJECT_DIR is required" >&2
        return 1
    fi

    if [ ! -d "$project_dir" ]; then
        echo "generate_codebase_summary: directory does not exist: $project_dir" >&2
        return 1
    fi

    local total_lines=0
    local truncated=false
    local output=""

    # Helper: append a line to output, respecting max_lines
    _gcs_append() {
        if [ "$truncated" = true ]; then
            return
        fi
        total_lines=$((total_lines + 1))
        if [ "$total_lines" -gt "$max_lines" ]; then
            truncated=true
            output="${output}[Summary truncated at ${max_lines} lines]
"
            return
        fi
        output="${output}${1}
"
    }

    # ── Section 1: Component Registry ──────────────────────────────────────
    _gcs_append "## Component Registry"
    _gcs_append ""

    local component_files=""
    local component_count=0
    local component_cap=50

    # Find .tsx and .jsx files under src/ or app/
    for subdir in src app; do
        local search_dir="$project_dir/$subdir"
        if [ -d "$search_dir" ]; then
            local found
            found=$(find "$search_dir" -type f \( -name '*.tsx' -o -name '*.jsx' \) 2>/dev/null | sort)
            if [ -n "$found" ]; then
                component_files="${component_files}${component_files:+
}${found}"
            fi
        fi
    done

    if [ -z "$component_files" ]; then
        _gcs_append "No .tsx/.jsx files found under src/ or app/."
    else
        local total_components
        total_components=$(echo "$component_files" | wc -l | tr -d ' ')
        local displayed=0

        while IFS= read -r filepath; do
            [ -z "$filepath" ] && continue
            if [ "$displayed" -ge "$component_cap" ]; then
                local remaining=$((total_components - component_cap))
                _gcs_append "... and ${remaining} more components (truncated at ${component_cap})"
                break
            fi

            local relpath="${filepath#"$project_dir"/}"
            local has_default="no"
            if grep -q 'export default' "$filepath" 2>/dev/null; then
                has_default="yes"
            fi
            _gcs_append "  ${relpath}  (export default: ${has_default})"
            displayed=$((displayed + 1))
        done <<< "$component_files"
    fi

    _gcs_append ""

    # ── Section 2: Type Exports ────────────────────────────────────────────
    _gcs_append "## Type Exports"
    _gcs_append ""

    local type_cap=50
    local type_count=0
    local type_entries=""

    # Find export type and export interface in .ts and .tsx files
    for subdir in src app; do
        local search_dir="$project_dir/$subdir"
        if [ -d "$search_dir" ]; then
            local matches
            matches=$(grep -rn 'export \(type\|interface\) ' "$search_dir" \
                --include='*.ts' --include='*.tsx' 2>/dev/null || true)
            if [ -n "$matches" ]; then
                type_entries="${type_entries}${type_entries:+
}${matches}"
            fi
        fi
    done

    if [ -z "$type_entries" ]; then
        _gcs_append "No type/interface exports found."
    else
        local total_types
        total_types=$(echo "$type_entries" | wc -l | tr -d ' ')
        local displayed=0

        while IFS= read -r line; do
            [ -z "$line" ] && continue
            if [ "$displayed" -ge "$type_cap" ]; then
                local remaining=$((total_types - type_cap))
                _gcs_append "... and ${remaining} more type exports (truncated at ${type_cap})"
                break
            fi

            # Parse: filepath:linenum:content
            local file_part="${line%%:*}"
            local rest="${line#*:}"
            local content="${rest#*:}"
            local relpath="${file_part#"$project_dir"/}"

            # Extract the type/interface name
            local type_name
            type_name=$(echo "$content" | awk '{
                for (i=1; i<=NF; i++) {
                    if ($i == "type" || $i == "interface") {
                        name = $(i+1)
                        # Strip trailing { or = or <
                        gsub(/[{=<].*/, "", name)
                        print name
                        exit
                    }
                }
            }')

            if [ -n "$type_name" ]; then
                _gcs_append "  ${relpath}: ${type_name}"
                displayed=$((displayed + 1))
            fi
        done <<< "$type_entries"
    fi

    _gcs_append ""

    # ── Section 3: Import Graph (top-level only) ──────────────────────────
    _gcs_append "## Import Graph"
    _gcs_append ""

    local import_cap=80
    local import_count=0
    local has_imports=false

    if [ -n "$component_files" ]; then
        while IFS= read -r filepath; do
            [ -z "$filepath" ] && continue
            if [ "$import_count" -ge "$import_cap" ]; then
                _gcs_append "... (import graph truncated at ${import_cap} entries)"
                break
            fi

            local relpath="${filepath#"$project_dir"/}"

            # Extract local imports: from './' or from '../'
            local imports
            imports=$(grep -oE "from ['\"]\.\.?/[^'\"]*['\"]" "$filepath" 2>/dev/null || true)

            if [ -n "$imports" ]; then
                while IFS= read -r import_line; do
                    [ -z "$import_line" ] && continue
                    if [ "$import_count" -ge "$import_cap" ]; then
                        _gcs_append "... (import graph truncated at ${import_cap} entries)"
                        break 2
                    fi

                    # Extract the path from "from './Foo'" or "from '../utils/bar'"
                    local import_path
                    import_path=$(echo "$import_line" | sed "s/from ['\"]//; s/['\"]//")

                    _gcs_append "  ${relpath} → ${import_path}"
                    import_count=$((import_count + 1))
                    has_imports=true
                done <<< "$imports"
            fi
        done <<< "$component_files"
    fi

    if [ "$has_imports" = false ]; then
        _gcs_append "No local imports found."
    fi

    _gcs_append ""

    # ── Section 4: Recent Learnings ───────────────────────────────────────
    _gcs_append "## Recent Learnings"
    _gcs_append ""

    local learnings_dir="$project_dir/.specs/learnings"
    local learnings_cap=40

    if [ ! -d "$learnings_dir" ]; then
        _gcs_append "No learnings directory found."
    else
        local learnings_content=""
        local learnings_found=false

        for md_file in "$learnings_dir"/*.md; do
            [ -f "$md_file" ] || continue
            # Skip empty files
            if [ ! -s "$md_file" ]; then
                continue
            fi
            learnings_found=true
            local basename
            basename=$(basename "$md_file")
            learnings_content="${learnings_content}### ${basename}
"
            learnings_content="${learnings_content}$(cat "$md_file")
"
        done

        if [ "$learnings_found" = false ]; then
            _gcs_append "No learnings files found."
        else
            local line_count=0
            while IFS= read -r lline; do
                if [ "$line_count" -ge "$learnings_cap" ]; then
                    _gcs_append "... (learnings truncated at ${learnings_cap} lines)"
                    break
                fi
                _gcs_append "$lline"
                line_count=$((line_count + 1))
            done <<< "$learnings_content"
        fi
    fi

    # Output the accumulated result
    printf '%s' "$output"
    return 0
}
