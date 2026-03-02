#!/usr/bin/env bash
# general-estimates.sh — manages general-estimates.jsonl for calibrating
# scope estimates on general system activities (chat responses, agent prompts,
# checkpoints, schema migrations, etc.).
#
# Parallel to cost-log.jsonl / claude-wrapper.sh which tracks build-loop costs.
# This tracks estimation accuracy so future scope estimates can be data-driven.
#
# Usage:
#   source lib/general-estimates.sh
#   append_general_estimate '{"timestamp":"...","activity_type":"...","estimated_tokens_pre":12000,"approx_actual_tokens":8500,...}'
#   query_estimate_actuals "checkpoint"
#   estimate_general_tokens "checkpoint" 15000

set -uo pipefail

GENERAL_ESTIMATES_FILE="${GENERAL_ESTIMATES_FILE:-./general-estimates.jsonl}"

# Usage: append_general_estimate <json_string>
# Appends a single JSON line to general-estimates.jsonl.
# Validates required fields before writing.
# Auto-computes estimation_error_pct if not provided.
append_general_estimate() {
    local json="$1"
    local estimates_file="${GENERAL_ESTIMATES_FILE}"

    # Validate required fields exist
    local required_fields=("timestamp" "activity_type" "estimated_tokens_pre" "approx_actual_tokens")
    for field in "${required_fields[@]}"; do
        if ! echo "$json" | jq -e ".$field" >/dev/null 2>&1; then
            echo "[general-estimates] ERROR: missing required field '$field'" >&2
            return 1
        fi
    done

    # Compute estimation_error_pct if not provided
    if ! echo "$json" | jq -e ".estimation_error_pct" >/dev/null 2>&1; then
        local est actual error_pct
        est=$(echo "$json" | jq ".estimated_tokens_pre")
        actual=$(echo "$json" | jq ".approx_actual_tokens")
        if [ "$actual" -gt 0 ]; then
            error_pct=$(printf "%.1f" "$(echo "scale=4; (($est - $actual) / $actual) * 100" | bc)")
            json=$(echo "$json" | jq -c --arg ep "$error_pct" '. + {estimation_error_pct: ($ep | tonumber)}')
        fi
    fi

    echo "$json" >> "$estimates_file"
    echo "[general-estimates] Appended: $(echo "$json" | jq -r '.activity_type') (error: $(echo "$json" | jq -r '.estimation_error_pct')%)" >&2
}

# Usage: query_estimate_actuals [activity_type]
# Returns calibrated estimate data for a given activity type.
# If no activity_type provided, returns summary of all types.
query_estimate_actuals() {
    local activity_type="${1:-}"
    local estimates_file="${GENERAL_ESTIMATES_FILE}"

    if [ ! -f "$estimates_file" ] || [ ! -s "$estimates_file" ]; then
        echo "[general-estimates] No actuals data yet. Using heuristic defaults." >&2
        return 1
    fi

    if [ -n "$activity_type" ]; then
        # Return stats for specific activity type
        jq -s --arg at "$activity_type" '
            [.[] | select(.activity_type == $at)] |
            if length == 0 then
                {activity_type: $at, sample_count: 0, message: "No data for this type. Use heuristics."}
            else
                {
                    activity_type: $at,
                    sample_count: length,
                    avg_actual_tokens: ([.[].approx_actual_tokens] | add / length | floor),
                    avg_estimation_error_pct: ([.[].estimation_error_pct] | add / length | . * 10 | floor / 10),
                    min_actual: ([.[].approx_actual_tokens] | min),
                    max_actual: ([.[].approx_actual_tokens] | max),
                    avg_tool_calls: ([.[].tool_calls] | add / length | . * 10 | floor / 10),
                    calibration_ready: (length >= 5)
                }
            end
        ' "$estimates_file"
    else
        # Return summary of all activity types
        jq -s '
            group_by(.activity_type) | map({
                activity_type: .[0].activity_type,
                sample_count: length,
                avg_actual_tokens: ([.[].approx_actual_tokens] | add / length | floor),
                avg_estimation_error_pct: ([.[].estimation_error_pct] | add / length | . * 10 | floor / 10),
                calibration_ready: (length >= 5)
            }) | sort_by(.activity_type)
        ' "$estimates_file"
    fi
}

# Usage: estimate_general_tokens <activity_type> <fallback_estimate>
# Returns calibrated estimate if actuals exist, otherwise returns fallback.
# This is the general-system equivalent of estimate_feature_tokens().
#
# Blending strategy (prevents single-outlier override):
#   <5 samples: weight actuals at (N/5), heuristic at (1 - N/5)
#     1 sample:  20% actuals, 80% heuristic
#     3 samples: 60% actuals, 40% heuristic
#   5+ samples:  100% actuals
estimate_general_tokens() {
    local activity_type="$1"
    local fallback="$2"
    local estimates_file="${GENERAL_ESTIMATES_FILE}"

    if [ ! -f "$estimates_file" ] || [ ! -s "$estimates_file" ]; then
        echo "$fallback"
        return 0
    fi

    local avg
    avg=$(jq -s --arg at "$activity_type" --argjson fb "$fallback" '
        [.[] | select(.activity_type == $at)] |
        if length >= 5 then
            [.[].approx_actual_tokens] | add / length | floor
        elif length >= 1 then
            # Blend: weight actuals at (N/5), heuristic at (1 - N/5)
            (([.[].approx_actual_tokens] | add / length) * (length / 5) +
             ($fb * (1 - length / 5))) | floor
        else
            $fb
        end
    ' "$estimates_file" 2>/dev/null)

    if [ -z "$avg" ] || [ "$avg" = "null" ]; then
        echo "$fallback"
    else
        echo "$avg"
    fi
}
