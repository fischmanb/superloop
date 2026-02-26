#!/bin/bash
# eval-sidecar.sh
# Runs alongside the build loop, watching for new feature commits and evaluating them.
# Purely observational — never modifies the project, never blocks the build, fails gracefully.
#
# Usage:
#   PROJECT_DIR=/path/to/project ./scripts/eval-sidecar.sh
#   EVAL_AGENT=true EVAL_INTERVAL=60 ./scripts/eval-sidecar.sh
#
# CONFIGURATION (env vars):
#   PROJECT_DIR       - Project directory (required)
#   EVAL_INTERVAL     - Poll interval in seconds (default: 30)
#   EVAL_AGENT        - Run agent evals in addition to mechanical (default: true)
#   EVAL_MODEL        - Model for agent evals (falls back to AGENT_MODEL)
#   EVAL_OUTPUT_DIR   - Output directory for eval results (default: $PROJECT_DIR/logs/evals)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$(dirname "$SCRIPT_DIR")/lib"

# ── Validate required config ──────────────────────────────────────────────
if [ -z "${PROJECT_DIR:-}" ]; then
    echo "ERROR: PROJECT_DIR is required" >&2
    exit 1
fi

if [ ! -d "$PROJECT_DIR" ]; then
    echo "ERROR: PROJECT_DIR does not exist: $PROJECT_DIR" >&2
    exit 1
fi

# ── Config with defaults ──────────────────────────────────────────────────
EVAL_INTERVAL="${EVAL_INTERVAL:-30}"
EVAL_AGENT="${EVAL_AGENT:-true}"
EVAL_MODEL="${EVAL_MODEL:-${AGENT_MODEL:-}}"
EVAL_OUTPUT_DIR="${EVAL_OUTPUT_DIR:-$PROJECT_DIR/logs/evals}"

# ── Drain sentinel ──────────────────────────────────────────────────────
# The build loop writes this file to signal "finish up". The sidecar sees it,
# drains remaining unevaluated commits, generates the campaign summary, and exits.
DRAIN_SENTINEL="$PROJECT_DIR/.sdd-eval-drain"

# ── Source libraries ──────────────────────────────────────────────────────
source "$LIB_DIR/reliability.sh"
source "$LIB_DIR/eval.sh"
source "$LIB_DIR/claude-wrapper.sh"

# ── Logging ───────────────────────────────────────────────────────────────
log()     { echo "[$(date '+%H:%M:%S')] [eval-sidecar] $1"; }
warn()    { echo "[$(date '+%H:%M:%S')] [eval-sidecar] ⚠ $1"; }
success() { echo "[$(date '+%H:%M:%S')] [eval-sidecar] ✓ $1"; }
error()   { echo "[$(date '+%H:%M:%S')] [eval-sidecar] ✗ $1"; }

# ── Agent command builder (same pattern as build-loop-local.sh) ───────────
agent_cmd() {
    local model="${EVAL_MODEL:-}"
    local cmd="bash $LIB_DIR/claude-wrapper.sh -p --dangerously-skip-permissions"
    if [ -n "$model" ]; then
        cmd="$cmd --model $model"
    fi
    echo "$cmd"
}

# ── Print config summary ─────────────────────────────────────────────────
log "=== Eval Sidecar Starting ==="
log "PROJECT_DIR:    $PROJECT_DIR"
log "EVAL_INTERVAL:  ${EVAL_INTERVAL}s"
log "EVAL_AGENT:     $EVAL_AGENT"
log "EVAL_MODEL:     ${EVAL_MODEL:-<default>}"
log "EVAL_OUTPUT_DIR: $EVAL_OUTPUT_DIR"
log "=============================="

# ── Ensure output directory ───────────────────────────────────────────────
mkdir -p "$EVAL_OUTPUT_DIR"

# ── Clean up stale sentinel from prior SIGKILL/crash ─────────────────────
rm -f "$DRAIN_SENTINEL"

# ── State tracking ────────────────────────────────────────────────────────
# Track the last evaluated commit so we only process new ones
LAST_EVALUATED_COMMIT=""
AGENT_EVALS_DISABLED=false
EVAL_COUNT=0
EVAL_ERRORS=0
DRAINING=false

# ── Campaign summary on exit ─────────────────────────────────────────────
generate_campaign_summary() {
    local timestamp
    timestamp=$(date -u +%Y%m%d-%H%M%S)
    local campaign_file="$EVAL_OUTPUT_DIR/eval-campaign-${timestamp}.json"

    log "Generating campaign summary..."

    # Collect all eval JSON files
    local eval_files=()
    while IFS= read -r -d '' f; do
        eval_files+=("$f")
    done < <(find "$EVAL_OUTPUT_DIR" -maxdepth 1 -name 'eval-*.json' ! -name 'eval-campaign-*' -print0 2>/dev/null)

    local total=${#eval_files[@]}

    if [ "$total" -eq 0 ]; then
        log "No eval results to summarize"
        return 0
    fi

    # Aggregate signals
    local fw_pass=0 fw_warn=0 fw_fail=0
    local scope_focused=0 scope_moderate=0 scope_sprawling=0
    local int_clean=0 int_minor=0 int_major=0
    local total_type_redeclarations=0
    local features_with_issues=""
    local features_with_issues_count=0

    for eval_file in "${eval_files[@]}"; do
        # Parse mechanical type_redeclarations
        local redecl
        redecl=$(awk -F': ' '/"type_redeclarations"/{gsub(/[^0-9]/,"",$2); print $2}' "$eval_file" 2>/dev/null || echo "0")
        redecl="${redecl:-0}"
        total_type_redeclarations=$((total_type_redeclarations + redecl))

        # Parse feature name from mechanical
        local fname
        fname=$(awk -F'"' '/"feature_name"/{print $4}' "$eval_file" 2>/dev/null || echo "unknown")

        # Track issues: type redeclarations > 0 means an issue
        local has_issue=false
        if [ "$redecl" -gt 0 ]; then
            has_issue=true
        fi

        # Parse agent eval signals if available
        local agent_avail
        agent_avail=$(awk -F': ' '/"agent_eval_available"/{gsub(/[[:space:],]/,"",$2); print $2}' "$eval_file" 2>/dev/null || echo "false")

        if [ "$agent_avail" = "true" ]; then
            local fw
            fw=$(awk -F'"' '/"framework_compliance"/{print $4}' "$eval_file" 2>/dev/null || echo "")
            case "$fw" in
                pass) fw_pass=$((fw_pass + 1)) ;;
                warn) fw_warn=$((fw_warn + 1)); has_issue=true ;;
                fail) fw_fail=$((fw_fail + 1)); has_issue=true ;;
            esac

            local sc
            sc=$(awk -F'"' '/"scope_assessment"/{print $4}' "$eval_file" 2>/dev/null || echo "")
            case "$sc" in
                focused)   scope_focused=$((scope_focused + 1)) ;;
                moderate)  scope_moderate=$((scope_moderate + 1)) ;;
                sprawling) scope_sprawling=$((scope_sprawling + 1)); has_issue=true ;;
            esac

            local iq
            iq=$(awk -F'"' '/"integration_quality"/{print $4}' "$eval_file" 2>/dev/null || echo "")
            case "$iq" in
                clean)        int_clean=$((int_clean + 1)) ;;
                minor_issues) int_minor=$((int_minor + 1)) ;;
                major_issues) int_major=$((int_major + 1)); has_issue=true ;;
            esac
        fi

        if [ "$has_issue" = true ]; then
            features_with_issues_count=$((features_with_issues_count + 1))
            if [ -n "$features_with_issues" ]; then
                features_with_issues="${features_with_issues},"
            fi
            # Escape feature name for JSON
            local escaped_fname
            escaped_fname=$(printf '%s' "$fname" | sed 's/\\/\\\\/g; s/"/\\"/g')
            features_with_issues="${features_with_issues}\"${escaped_fname}\""
        fi
    done

    # Write campaign JSON
    cat > "$campaign_file" <<CAMPAIGNJSON
{
  "campaign_timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "total_features_evaluated": $total,
  "type_redeclarations_total": $total_type_redeclarations,
  "framework_compliance": {
    "pass": $fw_pass,
    "warn": $fw_warn,
    "fail": $fw_fail
  },
  "scope_assessment": {
    "focused": $scope_focused,
    "moderate": $scope_moderate,
    "sprawling": $scope_sprawling
  },
  "integration_quality": {
    "clean": $int_clean,
    "minor_issues": $int_minor,
    "major_issues": $int_major
  },
  "features_with_issues_count": $features_with_issues_count,
  "features_with_issues": [${features_with_issues}]
}
CAMPAIGNJSON

    # Print human-readable summary
    echo ""
    log "╔══════════════════════════════════════════════╗"
    log "║         EVAL CAMPAIGN SUMMARY                ║"
    log "╠══════════════════════════════════════════════╣"
    log "║ Total features evaluated: $total"
    log "║ Type redeclarations:      $total_type_redeclarations"
    log "╠══════════════════════════════════════════════╣"
    log "║ Framework Compliance:"
    log "║   pass: $fw_pass  warn: $fw_warn  fail: $fw_fail"
    log "║ Scope Assessment:"
    log "║   focused: $scope_focused  moderate: $scope_moderate  sprawling: $scope_sprawling"
    log "║ Integration Quality:"
    log "║   clean: $int_clean  minor: $int_minor  major: $int_major"
    log "╠══════════════════════════════════════════════╣"
    log "║ Features with issues: $features_with_issues_count"
    if [ "$features_with_issues_count" -gt 0 ]; then
        # Print each feature name from the JSON list
        echo "$features_with_issues" | tr ',' '\n' | sed 's/"//g' | while IFS= read -r issuename; do
            [ -z "$issuename" ] && continue
            log "║   - $issuename"
        done
    fi
    log "╚══════════════════════════════════════════════╝"
    log "Campaign file: $campaign_file"
}

# ── Trap for clean exit ───────────────────────────────────────────────────
cleanup() {
    log "Shutting down (evaluated $EVAL_COUNT commits, $EVAL_ERRORS errors)..."
    generate_campaign_summary
    exit 0
}
trap cleanup SIGINT SIGTERM

# ── Main loop ─────────────────────────────────────────────────────────────

# Initialize: set last evaluated to current HEAD so we only eval NEW commits
LAST_EVALUATED_COMMIT=$(git -C "$PROJECT_DIR" rev-parse HEAD 2>/dev/null || echo "")
if [ -z "$LAST_EVALUATED_COMMIT" ]; then
    error "Could not determine HEAD commit in $PROJECT_DIR"
    exit 1
fi
log "Starting from commit: ${LAST_EVALUATED_COMMIT:0:8}"

while true; do
    # Check for drain sentinel — cooperative shutdown from build loop
    if [ -f "$DRAIN_SENTINEL" ]; then
        if [ "$DRAINING" = false ]; then
            log "Drain sentinel detected — processing remaining evals..."
            DRAINING=true
        fi
    fi

    # Sleep between polls (skip during drain to process remaining quickly)
    if [ "$DRAINING" = false ]; then
        sleep "$EVAL_INTERVAL"
    fi

    # Get current HEAD
    current_head=$(git -C "$PROJECT_DIR" rev-parse HEAD 2>/dev/null || echo "")
    if [ -z "$current_head" ]; then
        if [ "$DRAINING" = true ]; then
            warn "Could not read HEAD during drain — finishing"
            break
        fi
        warn "Could not read HEAD — will retry next cycle"
        continue
    fi

    # If HEAD hasn't changed
    if [ "$current_head" = "$LAST_EVALUATED_COMMIT" ]; then
        if [ "$DRAINING" = true ]; then
            # No more commits to evaluate — drain complete
            break
        fi
        continue
    fi

    # Get list of new commits since last evaluated (oldest first, skip merges)
    new_commits=$(git -C "$PROJECT_DIR" log --reverse --no-merges --format='%H' "${LAST_EVALUATED_COMMIT}..${current_head}" 2>/dev/null || echo "")

    if [ -z "$new_commits" ]; then
        # Only merge commits since last check, or range error — advance pointer
        LAST_EVALUATED_COMMIT="$current_head"
        if [ "$DRAINING" = true ]; then
            break
        fi
        continue
    fi

    while IFS= read -r commit_hash; do
        [ -z "$commit_hash" ] && continue

        commit_short="${commit_hash:0:8}"
        commit_msg=$(git -C "$PROJECT_DIR" log -1 --format='%s' "$commit_hash" 2>/dev/null || echo "<unknown>")

        log "Evaluating $commit_short: $commit_msg"

        # ── Mechanical eval ───────────────────────────────────────────
        mechanical_json=""
        feature_name=""
        set +e
        mechanical_json=$(run_mechanical_eval "$PROJECT_DIR" "$commit_hash" 2>/dev/null)
        mech_exit=$?
        set -e

        if [ $mech_exit -ne 0 ]; then
            warn "Mechanical eval failed for $commit_short — skipping"
            EVAL_ERRORS=$((EVAL_ERRORS + 1))
            continue
        fi

        # Extract feature name from mechanical JSON
        feature_name=$(echo "$mechanical_json" | awk -F'"' '/"feature_name"/{print $4}' 2>/dev/null || echo "$commit_short")
        feature_name="${feature_name:-$commit_short}"

        # Check if this was a skipped merge commit (shouldn't happen since --no-merges, but be safe)
        was_skipped=$(echo "$mechanical_json" | awk -F': ' '/"skipped"/{gsub(/[[:space:],]/,"",$2); print $2}' 2>/dev/null || echo "false")
        if [ "$was_skipped" = "true" ]; then
            log "Skipped merge commit $commit_short"
            continue
        fi

        # ── Agent eval (if enabled) ──────────────────────────────────
        agent_output=""

        if [ "$EVAL_AGENT" = "true" ] && [ "$AGENT_EVALS_DISABLED" = false ]; then
            log "Running agent eval for $commit_short..."

            set +e
            eval_prompt=$(generate_eval_prompt "$PROJECT_DIR" "$commit_hash" 2>/dev/null)
            prompt_exit=$?
            set -e

            if [ $prompt_exit -ne 0 ]; then
                warn "Failed to generate eval prompt for $commit_short — mechanical only"
                EVAL_ERRORS=$((EVAL_ERRORS + 1))
            else
                # Run agent with backoff
                agent_output_file=$(mktemp)

                set +e
                run_agent_with_backoff "$agent_output_file" $(agent_cmd) "$eval_prompt"
                agent_exit=$AGENT_EXIT
                set -e

                if [ -f "$agent_output_file" ]; then
                    agent_output=$(cat "$agent_output_file")
                    rm -f "$agent_output_file"
                fi

                # Credit exhaustion detection (same pattern as build loop)
                if [ $agent_exit -ne 0 ] && echo "$agent_output" | grep -qiE '(credit|billing|insufficient_quota|quota exceeded|402 Payment|429 Too Many|payment required)' 2>/dev/null; then
                    warn "API credits exhausted — disabling agent evals for remainder of run"
                    AGENT_EVALS_DISABLED=true
                    agent_output=""
                elif [ $agent_exit -ne 0 ]; then
                    warn "Agent eval failed for $commit_short (exit $agent_exit) — mechanical only"
                    EVAL_ERRORS=$((EVAL_ERRORS + 1))
                    agent_output=""
                fi
            fi
        fi

        # ── Write result ──────────────────────────────────────────────
        set +e
        result_file=$(write_eval_result "$EVAL_OUTPUT_DIR" "$feature_name" "$mechanical_json" "$agent_output" 2>/dev/null)
        write_exit=$?
        set -e

        if [ $write_exit -ne 0 ]; then
            warn "Failed to write eval result for $commit_short"
            EVAL_ERRORS=$((EVAL_ERRORS + 1))
        else
            EVAL_COUNT=$((EVAL_COUNT + 1))
            success "Eval complete for $commit_short → $result_file"
        fi

    done <<< "$new_commits"

    # Advance pointer
    LAST_EVALUATED_COMMIT="$current_head"
done

# ── Drain complete — generate full campaign summary and exit ──────────────
if [ "$DRAINING" = true ]; then
    log "Drain complete — all commits evaluated"
    generate_campaign_summary
    rm -f "$DRAIN_SENTINEL"
    log "Exiting cleanly (evaluated $EVAL_COUNT commits, $EVAL_ERRORS errors)"
    exit 0
fi
