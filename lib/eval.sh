#!/usr/bin/env bash
# lib/eval.sh — Eval function library for assessing completed feature builds
#
# Source this file, then call the provided functions.
# No code runs at source time.
#
# Functions provided:
#   run_mechanical_eval <project_dir> <commit_hash>
#   generate_eval_prompt <project_dir> <commit_hash>
#   parse_eval_signal <signal_name> <output>
#   write_eval_result <output_dir> <feature_name> <mechanical_json> <agent_output>

# Guard against double-sourcing
if [ "${_EVAL_SH_LOADED:-}" = "true" ]; then
    return 0 2>/dev/null || true
fi
_EVAL_SH_LOADED=true

# ── run_mechanical_eval ──────────────────────────────────────────────────────
# Deterministic, agent-free checks against a commit.
# Outputs JSON to stdout.
# Returns 0 on success, 1 with error JSON on failure.
#
# Usage: run_mechanical_eval <project_dir> <commit_hash>
run_mechanical_eval() {
    local project_dir="${1:-}"
    local commit_hash="${2:-}"

    if [ -z "$project_dir" ]; then
        echo '{"error": "run_mechanical_eval: project_dir is required"}'
        return 1
    fi

    if [ ! -d "$project_dir" ]; then
        echo "{\"error\": \"run_mechanical_eval: directory does not exist: $project_dir\"}"
        return 1
    fi

    if [ -z "$commit_hash" ]; then
        echo '{"error": "run_mechanical_eval: commit_hash is required"}'
        return 1
    fi

    # Verify the commit exists
    if ! git -C "$project_dir" cat-file -t "$commit_hash" >/dev/null 2>&1; then
        echo "{\"error\": \"run_mechanical_eval: commit not found: $commit_hash\"}"
        return 1
    fi

    # Check for merge commit (more than one parent)
    local parent_count
    parent_count=$(git -C "$project_dir" rev-list --parents -n 1 "$commit_hash" | awk '{print NF - 1}')
    if [ "$parent_count" -gt 1 ]; then
        echo "{\"commit\": \"$commit_hash\", \"skipped\": true, \"reason\": \"merge commit\"}"
        return 0
    fi

    # Extract feature name from commit message (first line)
    local commit_msg
    commit_msg=$(git -C "$project_dir" log -1 --format='%s' "$commit_hash")
    local feature_name
    feature_name=$(echo "$commit_msg" | sed 's/^[^:]*: //')

    # Check if first commit (no parents)
    local is_first_commit=false
    if [ "$parent_count" -eq 0 ]; then
        is_first_commit=true
    fi

    # Get diff stats
    local files_changed=0
    local lines_added=0
    local lines_removed=0
    local files_list="[]"
    local test_files_touched=false
    local diff_stat=""

    if [ "$is_first_commit" = true ]; then
        # First commit: diff against empty tree (4b825dc — the well-known empty tree hash)
        local empty_tree
        empty_tree=$(git -C "$project_dir" hash-object -t tree /dev/null 2>/dev/null | tr -d '[:space:]')
        diff_stat=$(git -C "$project_dir" diff --numstat "$empty_tree" "$commit_hash" 2>/dev/null || true)
    else
        diff_stat=$(git -C "$project_dir" diff --numstat "${commit_hash}^" "$commit_hash" 2>/dev/null || true)
    fi

    if [ -n "$diff_stat" ]; then
        # Count files changed
        files_changed=$(echo "$diff_stat" | wc -l | tr -d ' ')

        # Sum lines added and removed
        lines_added=$(echo "$diff_stat" | awk '{s+=$1} END {print s+0}')
        lines_removed=$(echo "$diff_stat" | awk '{s+=$2} END {print s+0}')

        # Build files list as JSON array
        local files_json=""
        while IFS=$'\t' read -r added removed filepath; do
            [ -z "$filepath" ] && continue
            if [ -n "$files_json" ]; then
                files_json="${files_json},"
            fi
            files_json="${files_json}\"${filepath}\""

            # Check if test files were touched
            case "$filepath" in
                *test*|*spec*|*__tests__*)
                    test_files_touched=true
                    ;;
            esac
        done <<< "$diff_stat"
        files_list="[${files_json}]"
    fi

    # Get the diff content for type analysis
    local diff_content=""
    if [ "$is_first_commit" = true ]; then
        local empty_tree2
        empty_tree2=$(git -C "$project_dir" hash-object -t tree /dev/null 2>/dev/null | tr -d '[:space:]')
        diff_content=$(git -C "$project_dir" diff "$empty_tree2" "$commit_hash" 2>/dev/null || true)
    else
        diff_content=$(git -C "$project_dir" diff "${commit_hash}^" "$commit_hash" 2>/dev/null || true)
    fi

    # Count new type/interface exports in the diff (lines starting with +)
    local new_type_exports=0
    if [ -n "$diff_content" ]; then
        new_type_exports=$(echo "$diff_content" | grep -c '^+.*export \(type\|interface\) ' 2>/dev/null || true)
        new_type_exports=$(echo "$new_type_exports" | tr -d '[:space:]')
        new_type_exports="${new_type_exports:-0}"
    fi

    # Check for type redeclarations: new export type/interface names that already exist in the project
    local type_redeclarations=0
    local redeclared_names="[]"
    if [ "$new_type_exports" -gt 0 ]; then
        # Extract new type/interface names from the diff
        local new_type_names
        new_type_names=$(echo "$diff_content" | grep '^+.*export \(type\|interface\) ' | \
            sed 's/^+//' | awk '{
                for (i=1; i<=NF; i++) {
                    if ($i == "type" || $i == "interface") {
                        name = $(i+1)
                        gsub(/[{=<(].*/, "", name)
                        if (name != "") print name
                        break
                    }
                }
            }' | sort -u)

        if [ -n "$new_type_names" ]; then
            # Get list of changed files to exclude from search
            local changed_files_list
            if [ "$is_first_commit" = true ]; then
                changed_files_list=""
            else
                changed_files_list=$(git -C "$project_dir" diff --name-only "${commit_hash}^" "$commit_hash" 2>/dev/null || true)
            fi

            local redecl_json=""
            while IFS= read -r type_name; do
                [ -z "$type_name" ] && continue
                # Search for this type name in existing codebase (at the parent commit)
                local existing_count=0
                if [ "$is_first_commit" = false ]; then
                    # Check if this type name exists in the project at the parent commit
                    # Look in all .ts/.tsx files that were NOT changed in this commit
                    existing_count=$(git -C "$project_dir" grep -l "export \(type\|interface\) ${type_name}" "${commit_hash}^" -- '*.ts' '*.tsx' 2>/dev/null | wc -l | tr -d ' ')
                fi
                if [ "$existing_count" -gt 0 ]; then
                    type_redeclarations=$((type_redeclarations + 1))
                    if [ -n "$redecl_json" ]; then
                        redecl_json="${redecl_json},"
                    fi
                    redecl_json="${redecl_json}\"${type_name}\""
                fi
            done <<< "$new_type_names"
            if [ -n "$redecl_json" ]; then
                redeclared_names="[${redecl_json}]"
            fi
        fi
    fi

    # Count import statements in the diff (new imports added)
    local import_count=0
    if [ -n "$diff_content" ]; then
        import_count=$(echo "$diff_content" | grep -c '^+.*import ' 2>/dev/null || echo "0")
    fi

    # Construct JSON output
    cat <<JSONEOF
{
  "commit": "$commit_hash",
  "feature_name": $(printf '%s' "$feature_name" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))' 2>/dev/null || echo "\"$feature_name\""),
  "files_changed": $files_changed,
  "files": $files_list,
  "lines_added": $lines_added,
  "lines_removed": $lines_removed,
  "new_type_exports": $new_type_exports,
  "type_redeclarations": $type_redeclarations,
  "redeclared_type_names": $redeclared_names,
  "import_count": $import_count,
  "test_files_touched": $test_files_touched
}
JSONEOF
    return 0
}

# ── generate_eval_prompt ─────────────────────────────────────────────────────
# Outputs a prompt string for a fresh eval agent.
# The prompt instructs the agent to assess framework compliance, scope, etc.
#
# Usage: generate_eval_prompt <project_dir> <commit_hash>
generate_eval_prompt() {
    local project_dir="${1:-}"
    local commit_hash="${2:-}"

    if [ -z "$project_dir" ] || [ -z "$commit_hash" ]; then
        echo "generate_eval_prompt: project_dir and commit_hash are required" >&2
        return 1
    fi

    # Get the diff for the prompt
    local parent_count
    parent_count=$(git -C "$project_dir" rev-list --parents -n 1 "$commit_hash" 2>/dev/null | awk '{print NF - 1}')
    parent_count="${parent_count:-1}"

    local diff_cmd
    if [ "$parent_count" -eq 0 ]; then
        local empty_tree
        empty_tree=$(git -C "$project_dir" hash-object -t tree /dev/null)
        diff_cmd="git -C $project_dir diff $empty_tree $commit_hash"
    else
        diff_cmd="git -C $project_dir diff ${commit_hash}^ $commit_hash"
    fi

    local diff_content
    diff_content=$(eval "$diff_cmd" 2>/dev/null || true)

    # Read CLAUDE.md if it exists
    local claude_md_content=""
    if [ -f "$project_dir/CLAUDE.md" ]; then
        claude_md_content=$(cat "$project_dir/CLAUDE.md")
    fi

    # Read learnings index if it exists
    local learnings_content=""
    if [ -f "$project_dir/.specs/learnings/index.md" ]; then
        learnings_content=$(cat "$project_dir/.specs/learnings/index.md")
    fi

    cat <<PROMPTEOF
You are an eval agent reviewing commit $commit_hash.

IMPORTANT: do NOT modify any files, do NOT commit, do NOT ask for user input. You are read-only.

## Your Task

Review the following diff and assess the quality of this commit against the project's standards.

## Project Standards (CLAUDE.md)

$claude_md_content

## Recent Learnings

$learnings_content

## Diff to Review

$diff_content

## Assessment Criteria

1. **Framework Compliance**: Does the code follow the project's spec-driven development workflow? Are specs, tests, and implementation consistent?
2. **Scope Discipline**: Is the commit focused on a single feature/fix, or does it sprawl across unrelated concerns?
3. **Integration Quality**: Are imports clean? Are types properly used? Does the code integrate well with existing patterns?
4. **Repeated Mistakes**: Does this commit repeat any mistakes documented in learnings?

## Required Output Signals

You MUST output these exact signals (one per line) in your response:

EVAL_COMPLETE: true
EVAL_FRAMEWORK_COMPLIANCE: <pass|warn|fail>
EVAL_SCOPE_ASSESSMENT: <focused|moderate|sprawling>
EVAL_INTEGRATION_QUALITY: <clean|minor_issues|major_issues>
EVAL_REPEATED_MISTAKES: <none|comma-separated list of repeated mistakes>
EVAL_NOTES: <one-line summary of your assessment>
PROMPTEOF
    return 0
}

# ── parse_eval_signal ────────────────────────────────────────────────────────
# Same pattern as parse_signal in build-loop-local.sh.
# Extracts the value of a named signal from agent output.
#
# Usage: parse_eval_signal <signal_name> <output>
parse_eval_signal() {
    local signal_name="$1"
    local output="$2"
    echo "$output" | awk -v sig="^${signal_name}:" '$0 ~ sig {
        val = $0
        sub(/^[^:]*:/, "", val)       # Remove everything up to and including first colon
        sub(/^[[:space:]]+/, "", val)  # Trim leading whitespace
        sub(/[[:space:]]+$/, "", val)  # Trim trailing whitespace
        last = val
    } END { print last }'
}

# ── write_eval_result ────────────────────────────────────────────────────────
# Merges mechanical JSON with parsed agent signals into a result file.
# If agent output is empty or unparseable, writes mechanical-only results.
# Must never fail because an agent didn't respond properly.
#
# Usage: write_eval_result <output_dir> <feature_name> <mechanical_json> <agent_output>
write_eval_result() {
    local output_dir="${1:-}"
    local feature_name="${2:-}"
    local mechanical_json="${3:-}"
    local agent_output="${4:-}"

    if [ -z "$output_dir" ] || [ -z "$feature_name" ]; then
        echo "write_eval_result: output_dir and feature_name are required" >&2
        return 1
    fi

    # Sanitize feature name for filename
    local safe_name
    safe_name=$(echo "$feature_name" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9._-]/-/g' | sed 's/--*/-/g' | sed 's/^-//;s/-$//')

    local output_file="$output_dir/eval-${safe_name}.json"

    # Ensure output directory exists
    mkdir -p "$output_dir"

    # If no mechanical JSON provided, use empty object
    if [ -z "$mechanical_json" ]; then
        mechanical_json='{}'
    fi

    # Try to parse agent signals
    local agent_eval_available=false
    local framework_compliance=""
    local scope_assessment=""
    local integration_quality=""
    local repeated_mistakes=""
    local eval_notes=""

    if [ -n "$agent_output" ]; then
        local eval_complete
        eval_complete=$(parse_eval_signal "EVAL_COMPLETE" "$agent_output")
        if [ "$eval_complete" = "true" ]; then
            agent_eval_available=true
            framework_compliance=$(parse_eval_signal "EVAL_FRAMEWORK_COMPLIANCE" "$agent_output")
            scope_assessment=$(parse_eval_signal "EVAL_SCOPE_ASSESSMENT" "$agent_output")
            integration_quality=$(parse_eval_signal "EVAL_INTEGRATION_QUALITY" "$agent_output")
            repeated_mistakes=$(parse_eval_signal "EVAL_REPEATED_MISTAKES" "$agent_output")
            eval_notes=$(parse_eval_signal "EVAL_NOTES" "$agent_output")
        fi
    fi

    # Build the final JSON, merging mechanical + agent data
    # Use a heredoc-based approach that doesn't depend on jq being available
    if [ "$agent_eval_available" = true ]; then
        cat > "$output_file" <<RESULTEOF
{
  "eval_timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "mechanical": $mechanical_json,
  "agent_eval_available": true,
  "agent_eval": {
    "framework_compliance": "$framework_compliance",
    "scope_assessment": "$scope_assessment",
    "integration_quality": "$integration_quality",
    "repeated_mistakes": "$repeated_mistakes",
    "eval_notes": "$eval_notes"
  }
}
RESULTEOF
    else
        cat > "$output_file" <<RESULTEOF
{
  "eval_timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "mechanical": $mechanical_json,
  "agent_eval_available": false
}
RESULTEOF
    fi

    echo "$output_file"
    return 0
}
