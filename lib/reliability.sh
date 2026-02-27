#!/usr/bin/env bash
# lib/reliability.sh — Shared reliability utilities for SDD orchestration scripts
#
# Source this file after defining logging functions (log, warn, success, error).
# All functions use global variables — set them before calling.
#
# Required globals (set before calling the relevant functions):
#   LOCK_FILE           - Path to lock file (acquire_lock/release_lock)
#   PROJECT_DIR         - Project root (check_circular_deps)
#   STATE_DIR           - State directory (write_state/read_state/clean_state)
#   STATE_FILE          - State file path (write_state/read_state/clean_state)
#   BUILT_FEATURE_NAMES - Bash array of completed features (completed_features_json)
#
# Optional globals with defaults:
#   MAX_AGENT_RETRIES   - Max retries for agent calls (default: 5)
#   BACKOFF_MAX_SECONDS - Max backoff delay in seconds (default: 60)
#   MAX_CONTEXT_TOKENS  - Context budget for drift checks (default: 100000)
#   PARALLEL_VALIDATION - Enable parallel drift checks (default: false)
#
# Functions provided:
#   acquire_lock, release_lock
#   write_state, read_state, completed_features_json, clean_state
#   run_agent_with_backoff  (sets global AGENT_EXIT)
#   truncate_for_context
#   check_circular_deps
#   emit_topo_order
#   get_cpu_count, run_parallel_drift_checks
#   count_files  (returns associative array via nameref)
#
# Notes:
#   - run_parallel_drift_checks requires check_drift() to be defined by caller
#   - acquire_lock sets a trap on INT/TERM/EXIT to clean up the lock file

# Guard against double-sourcing
if [ "${_RELIABILITY_SH_LOADED:-}" = "true" ]; then
    return 0 2>/dev/null || true
fi
_RELIABILITY_SH_LOADED=true

# ── Defaults for reliability config ──────────────────────────────────────────
MAX_AGENT_RETRIES="${MAX_AGENT_RETRIES:-5}"
BACKOFF_MAX_SECONDS="${BACKOFF_MAX_SECONDS:-60}"
MAX_CONTEXT_TOKENS="${MAX_CONTEXT_TOKENS:-100000}"
PARALLEL_VALIDATION="${PARALLEL_VALIDATION:-false}"

# ── Fallback logging (caller should define these before sourcing) ────────────
if ! declare -f log >/dev/null 2>&1; then
    log() { echo "[$(date '+%H:%M:%S')] $1"; }
fi
if ! declare -f warn >/dev/null 2>&1; then
    warn() { echo "[$(date '+%H:%M:%S')] ⚠ $1"; }
fi
if ! declare -f success >/dev/null 2>&1; then
    success() { echo "[$(date '+%H:%M:%S')] ✓ $1"; }
fi
if ! declare -f error >/dev/null 2>&1; then
    error() { echo "[$(date '+%H:%M:%S')] ✗ $1"; }
fi

# ── Concurrency lock ────────────────────────────────────────────────────────
# Uses global LOCK_FILE. Caller must set LOCK_FILE before calling.

acquire_lock() {
    if [ -f "$LOCK_FILE" ]; then
        local existing_pid
        existing_pid=$(cat "$LOCK_FILE" 2>/dev/null || echo "")
        if [ -n "$existing_pid" ] && kill -0 "$existing_pid" 2>/dev/null; then
            error "Another instance is already running (PID: $existing_pid)"
            error "Lock file: $LOCK_FILE"
            error "If this is stale, remove $LOCK_FILE manually"
            exit 4
        else
            warn "Removing stale lock file (PID $existing_pid no longer running)"
            rm -f "$LOCK_FILE"
        fi
    fi
    echo $$ > "$LOCK_FILE"
    trap 'rm -f "$LOCK_FILE"' INT TERM EXIT
}

release_lock() {
    rm -f "$LOCK_FILE"
}

# ── Resume state persistence ────────────────────────────────────────────────
# Uses globals STATE_DIR, STATE_FILE, BUILT_FEATURE_NAMES[].

# Write state atomically (write to temp, then mv)
write_state() {
    local feature_index="$1"
    local strategy="$2"
    local completed_json="$3"
    local current_branch="$4"
    mkdir -p "$STATE_DIR"
    # Escape backslashes first, then double quotes (same pattern as completed_features_json)
    local escaped_strategy
    escaped_strategy=$(printf '%s' "$strategy" | sed 's/\\/\\\\/g; s/"/\\"/g')
    local escaped_branch
    escaped_branch=$(printf '%s' "$current_branch" | sed 's/\\/\\\\/g; s/"/\\"/g')
    local tmpfile
    tmpfile=$(mktemp "$STATE_DIR/resume.XXXXXX")
    cat > "$tmpfile" << STATEJSON
{
  "feature_index": $feature_index,
  "branch_strategy": "$escaped_strategy",
  "completed_features": $completed_json,
  "current_branch": "$escaped_branch",
  "timestamp": "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
}
STATEJSON
    mv "$tmpfile" "$STATE_FILE"
    # Validate JSON if jq is available
    if command -v jq >/dev/null 2>&1; then
        if ! jq . "$STATE_FILE" >/dev/null 2>&1; then
            echo "ERROR: write_state produced invalid JSON in $STATE_FILE" >&2
            return 1
        fi
    else
        echo "SKIP: jq not available — JSON validation skipped" >&2
    fi
}

# Read state file. Sets: RESUME_INDEX, RESUME_STRATEGY, RESUME_BRANCH, BUILT_FEATURE_NAMES[]
read_state() {
    if [ ! -f "$STATE_FILE" ]; then
        return 1
    fi
    # Parse JSON with awk (no jq dependency)
    RESUME_INDEX=$(awk -F': ' '/"feature_index"/{gsub(/[^0-9]/,"",$2); print $2}' "$STATE_FILE")
    RESUME_STRATEGY=$(awk -F'"' '/"branch_strategy"/{print $4}' "$STATE_FILE")
    RESUME_BRANCH=$(awk -F'"' '/"current_branch"/{print $4}' "$STATE_FILE")

    # Parse completed_features JSON array into BUILT_FEATURE_NAMES[]
    # Handles: empty array [], missing key, one or more feature names
    BUILT_FEATURE_NAMES=()
    local raw_names
    raw_names=$(awk '
        /"completed_features"/ {
            # Grab everything from [ to ] (may span multiple lines)
            found = 1; buf = $0
            while (found && buf !~ /\]/) {
                if ((getline line) > 0) buf = buf line
                else break
            }
            # Remove everything before [ and after ]
            gsub(/.*\[/, "", buf)
            gsub(/\].*/, "", buf)
            # Split on commas and extract quoted strings
            n = split(buf, parts, ",")
            for (i = 1; i <= n; i++) {
                val = parts[i]
                # Strip whitespace and quotes
                gsub(/^[[:space:]]*"/, "", val)
                gsub(/"[[:space:]]*$/, "", val)
                if (val != "") print val
            }
        }
    ' "$STATE_FILE" 2>/dev/null)

    if [ -n "$raw_names" ]; then
        while IFS= read -r name; do
            BUILT_FEATURE_NAMES+=("$name")
        done <<< "$raw_names"
    fi

    return 0
}

# Build JSON array of completed feature names from BUILT_FEATURE_NAMES[]
# Escapes " and \ in feature names for valid JSON output.
completed_features_json() {
    local json="["
    local first=true
    for name in "${BUILT_FEATURE_NAMES[@]}"; do
        if [ "$first" = true ]; then
            first=false
        else
            json="$json, "
        fi
        # Escape backslashes first, then double quotes
        local escaped_name
        escaped_name=$(printf '%s' "$name" | sed 's/\\/\\\\/g; s/"/\\"/g')
        json="$json\"$escaped_name\""
    done
    json="$json]"
    echo "$json"
}

clean_state() {
    rm -f "$STATE_FILE"
}

# ── Exponential backoff for agent calls ──────────────────────────────────────
# Wraps an agent command with retry logic for rate limits.
# Usage: run_agent_with_backoff <output_file> <agent_cmd_args...>
# Sets global AGENT_EXIT to the final exit code.

run_agent_with_backoff() {
    local output_file="$1"
    shift
    local agent_retry=0
    AGENT_EXIT=0

    while [ "$agent_retry" -le "$MAX_AGENT_RETRIES" ]; do
        if [ "$agent_retry" -gt 0 ]; then
            local backoff=$(( 2 ** agent_retry ))
            if [ "$backoff" -gt "$BACKOFF_MAX_SECONDS" ]; then
                backoff="$BACKOFF_MAX_SECONDS"
            fi
            warn "Rate limit detected, retrying in ${backoff}s (attempt $agent_retry/$MAX_AGENT_RETRIES)..."
            sleep "$backoff"
        fi

        set +e
        "$@" 2>&1 | tee "$output_file"
        AGENT_EXIT=${PIPESTATUS[0]}
        set -e

        # Check for rate limit indicators in output
        if [ "$AGENT_EXIT" -ne 0 ]; then
            if grep -qiE '(rate.?limit|429|too many requests|overloaded|capacity)' "$output_file" 2>/dev/null; then
                agent_retry=$((agent_retry + 1))
                continue
            fi
        fi

        # Not a rate limit error, return result
        return 0
    done

    error "Agent failed after $MAX_AGENT_RETRIES retries due to rate limiting"
    return 1
}

# ── Context budget management ────────────────────────────────────────────────
# Estimate token count of a file (rough: 4 chars = 1 token).
# If spec exceeds 50% of budget, truncate to Gherkin scenarios only.
# Usage: truncate_for_context "$file_path"
# Outputs the (possibly truncated) content to stdout.

truncate_for_context() {
    local file="$1"
    if [ ! -f "$file" ]; then
        return
    fi

    local char_count
    char_count=$(wc -c < "$file" 2>/dev/null || echo "0")
    local estimated_tokens=$(( char_count / 4 ))
    local budget_half=$(( MAX_CONTEXT_TOKENS / 2 ))

    if [ "$estimated_tokens" -gt "$budget_half" ]; then
        warn "Spec file exceeds 50% of context budget (~${estimated_tokens} tokens, budget: ${MAX_CONTEXT_TOKENS})"
        warn "Truncating to Gherkin scenarios only (removing mockups and non-essential content)"
        # Extract only YAML frontmatter + Gherkin scenarios (Given/When/Then/And/Scenario/Feature lines)
        awk '
            BEGIN { in_frontmatter=0; fm_count=0 }
            /^---$/ { fm_count++; if (fm_count<=2) { print; next } }
            fm_count==1 { print; next }
            /^#+[[:space:]]/ { print; next }
            /^[[:space:]]*(Feature|Scenario|Given|When|Then|And|But|Background|Rule):/ { print; next }
            /^[[:space:]]*(Feature|Scenario|Given|When|Then|And|But|Background|Rule)[[:space:]]/ { print; next }
            /^\*\*/ { print; next }
        ' "$file"
    else
        cat "$file"
    fi
}

# ── Circular dependency detection ────────────────────────────────────────────
# Parses roadmap.md dependency graph and detects cycles using DFS.
# Exits with code 3 if circular dependencies are found.
# Uses global PROJECT_DIR.

check_circular_deps() {
    local roadmap="${PROJECT_DIR:-.}/.specs/roadmap.md"
    if [ ! -f "$roadmap" ]; then
        return 0  # No roadmap, nothing to check
    fi

    # Parse roadmap table rows: extract feature ID and deps
    # Format: | # | Feature | Source | Jira | Complexity | Deps | Status |
    local dep_map
    dep_map=$(awk -F'|' '
        /^\|[[:space:]]*[0-9]+[[:space:]]*\|/ {
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", $2)  # ID
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", $7)  # Deps column
            if ($2 ~ /^[0-9]+$/ && $7 != "-" && $7 != "") {
                print $2 ":" $7
            }
        }
    ' "$roadmap" 2>/dev/null)

    if [ -z "$dep_map" ]; then
        return 0  # No deps to check
    fi

    # DFS cycle detection using bash associative arrays
    # (avoids awk user-defined functions which mawk doesn't support)
    local -A adj=()
    local -A nodes=()
    local -A state=()  # 0=unvisited, 1=in-stack, 2=done

    while IFS=: read -r node deps_str; do
        nodes[$node]=1
        # Parse comma-separated deps, strip non-numeric
        local dep_list=""
        IFS=',' read -ra dep_parts <<< "$deps_str"
        for dep in "${dep_parts[@]}"; do
            dep=$(echo "$dep" | tr -dc '0-9')
            [ -z "$dep" ] && continue
            dep_list="$dep_list $dep"
            nodes[$dep]=1
        done
        adj[$node]="${dep_list# }"
    done <<< "$dep_map"

    for n in "${!nodes[@]}"; do
        state[$n]=0
    done

    # Recursive DFS with cycle detection
    _check_circular_dfs() {
        local node="$1"
        local path="$2"

        if [ "${state[$node]}" = "1" ]; then
            error "Circular dependency detected in roadmap!"
            error "CYCLE: $path -> $node"
            return 1
        fi
        [ "${state[$node]}" = "2" ] && return 0

        state[$node]=1
        local neighbors="${adj[$node]:-}"
        for neighbor in $neighbors; do
            [ -z "$neighbor" ] && continue
            if ! _check_circular_dfs "$neighbor" "$path -> $neighbor"; then
                return 1
            fi
        done
        state[$node]=2
        return 0
    }

    for n in "${!nodes[@]}"; do
        if [ "${state[$n]}" = "0" ]; then
            if ! _check_circular_dfs "$n" "$n"; then
                error "Fix the dependency cycle in .specs/roadmap.md before building"
                exit 3
            fi
        fi
    done

    return 0
}

# ── Topological sort of pending features ──────────────────────────────────────
# Kahn's algorithm (BFS) over ⬜ features in roadmap.md.
# Deps pointing to ✅ features are satisfied and ignored.
# Output: one line per feature in sorted order, format ID|FEATURE_NAME|COMPLEXITY.
# Uses global PROJECT_DIR.

emit_topo_order() {
    local roadmap="${PROJECT_DIR:-.}/.specs/roadmap.md"
    if [ ! -f "$roadmap" ]; then
        return 0  # No roadmap, nothing to sort
    fi

    # Parse roadmap table rows: extract ID, feature name, complexity, deps, status
    # Format: | # | Feature | Source | Jira | Complexity | Deps | Status |
    local raw_rows
    raw_rows=$(awk -F'|' '
        /^\|[[:space:]]*[0-9]+[[:space:]]*\|/ {
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", $2)  # ID
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", $3)  # Feature name
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", $6)  # Complexity
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", $7)  # Deps
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", $8)  # Status
            if ($2 ~ /^[0-9]+$/) {
                print $2 "\t" $3 "\t" $6 "\t" $7 "\t" $8
            }
        }
    ' "$roadmap" 2>/dev/null)

    if [ -z "$raw_rows" ]; then
        return 0  # No features found
    fi

    # Build data structures: separate completed vs pending features
    local -A completed=()    # ID → 1 for ✅ features
    local -A pending_name=() # ID → feature name
    local -A pending_cmplx=() # ID → complexity
    local -A pending_deps=() # ID → space-separated dep IDs (only pending deps)
    local -A in_degree=()    # ID → count of unsatisfied deps
    local pending_ids=()     # ordered list of pending IDs

    while IFS=$'\t' read -r fid fname fcmplx fdeps fstatus; do
        [ -z "$fid" ] && continue
        if echo "$fstatus" | grep -q "✅"; then
            completed[$fid]=1
        elif echo "$fstatus" | grep -q "⬜"; then
            pending_name[$fid]="$fname"
            pending_cmplx[$fid]="$fcmplx"
            pending_ids+=("$fid")
            in_degree[$fid]=0
            pending_deps[$fid]=""
        fi
        # Skip 🔄, ⏸️, ❌ features — they are not pending
    done <<< "$raw_rows"

    # If no pending features, nothing to sort
    if [ ${#pending_ids[@]} -eq 0 ]; then
        return 0
    fi

    # Re-parse deps: only keep deps that point to other pending features
    while IFS=$'\t' read -r fid fname fcmplx fdeps fstatus; do
        [ -z "$fid" ] && continue
        # Skip if not pending
        [ -z "${pending_name[$fid]+x}" ] && continue
        if [ "$fdeps" != "-" ] && [ -n "$fdeps" ]; then
            IFS=',' read -ra dep_parts <<< "$fdeps"
            for dep in "${dep_parts[@]}"; do
                dep=$(echo "$dep" | tr -dc '0-9')
                [ -z "$dep" ] && continue
                # If dep is completed, it's satisfied — ignore
                [ -n "${completed[$dep]+x}" ] && continue
                # If dep is another pending feature, it's an unsatisfied dep
                if [ -n "${pending_name[$dep]+x}" ]; then
                    pending_deps[$fid]="${pending_deps[$fid]} $dep"
                    in_degree[$fid]=$(( ${in_degree[$fid]} + 1 ))
                fi
            done
        fi
    done <<< "$raw_rows"

    # Kahn's algorithm: BFS from nodes with in_degree 0
    local queue=()
    for fid in "${pending_ids[@]}"; do
        if [ "${in_degree[$fid]}" -eq 0 ]; then
            queue+=("$fid")
        fi
    done

    local sorted=()
    local qi=0
    while [ "$qi" -lt "${#queue[@]}" ]; do
        local current="${queue[$qi]}"
        qi=$((qi + 1))
        sorted+=("$current")

        # For each pending feature that depends on current, decrement in_degree
        for fid in "${pending_ids[@]}"; do
            for dep in ${pending_deps[$fid]}; do
                if [ "$dep" = "$current" ]; then
                    in_degree[$fid]=$(( ${in_degree[$fid]} - 1 ))
                    if [ "${in_degree[$fid]}" -eq 0 ]; then
                        queue+=("$fid")
                    fi
                fi
            done
        done
    done

    # Output sorted features
    for fid in "${sorted[@]}"; do
        echo "${fid}|${pending_name[$fid]}|${pending_cmplx[$fid]}"
    done

    return 0
}

# ── Parallel validation (M3 Ultra optimization) ─────────────────────────────

get_cpu_count() {
    if command -v nproc &>/dev/null; then
        nproc
    elif command -v sysctl &>/dev/null; then
        sysctl -n hw.ncpu 2>/dev/null || echo "4"
    else
        echo "4"
    fi
}

# Run drift checks in parallel for independent branch strategy.
# Requires check_drift() to be defined by the calling script.
# Args: array of "spec_file:source_files" pairs
# Returns 0 if all passed, 1 if any failed.
run_parallel_drift_checks() {
    if [ "$PARALLEL_VALIDATION" != "true" ]; then
        return 0  # Parallel mode not enabled
    fi

    local max_jobs
    max_jobs=$(get_cpu_count)
    log "Running parallel drift checks (max $max_jobs concurrent jobs)..."

    local pids=()
    local results_dir
    results_dir=$(mktemp -d)
    local job_count=0

    for pair in "$@"; do
        local spec_file="${pair%%:*}"
        local source_files="${pair#*:}"

        if [ -z "$spec_file" ]; then
            continue
        fi

        # Wait if we've hit the max concurrent jobs
        while [ "$job_count" -ge "$max_jobs" ]; do
            wait -n 2>/dev/null || true
            job_count=$((job_count - 1))
        done

        (
            if check_drift "$spec_file" "$source_files"; then
                echo "PASS" > "$results_dir/$(basename "$spec_file").result"
            else
                echo "FAIL" > "$results_dir/$(basename "$spec_file").result"
            fi
        ) &
        pids+=($!)
        job_count=$((job_count + 1))
    done

    # Wait for all jobs to complete
    local any_failed=false
    for pid in "${pids[@]}"; do
        wait "$pid" || true
    done

    # Check results
    for result_file in "$results_dir"/*.result; do
        if [ -f "$result_file" ] && [ "$(cat "$result_file")" = "FAIL" ]; then
            any_failed=true
            local failed_spec
            failed_spec=$(basename "$result_file" .result)
            warn "Parallel drift check failed for: $failed_spec"
        fi
    done

    rm -rf "$results_dir"

    if [ "$any_failed" = true ]; then
        return 1
    fi
    return 0
}

# ── File counting by extension ────────────────────────────────────────────────
# Count files in a directory grouped by extension.
#
# Existing structured-data patterns in this library:
#   - read_state: sets fixed global variables (not suitable for variable-key maps)
#   - completed_features_json: outputs JSON string to stdout (requires parsing)
# Neither fits a variable-key associative array, so this uses a nameref parameter.
#
# Usage:
#   declare -A counts
#   count_files "/path/to/dir" counts
#   echo "${counts[sh]}"    # number of .sh files
#   echo "${counts[none]}"  # files with no extension
#
# Returns 0 on success, 1 if directory does not exist.
# Empty directories return zero counts (not an error).

count_files() {
    local dir="$1"
    local -n _count_files_ref="$2"

    if [ ! -d "$dir" ]; then
        echo "count_files: directory does not exist: $dir" >&2
        return 1
    fi

    _count_files_ref=()

    while IFS= read -r -d '' file; do
        local basename
        basename=$(basename "$file")
        local ext
        if [[ "$basename" == *.* ]]; then
            ext="${basename##*.}"
        else
            ext="none"
        fi
        _count_files_ref[$ext]=$(( ${_count_files_ref[$ext]:-0} + 1 ))
    done < <(find "$dir" -maxdepth 1 -type f -print0 2>/dev/null)

    return 0
}
