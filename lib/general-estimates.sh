#!/usr/bin/env bash
# lib/general-estimates.sh — Token estimation and actual usage tracking
#
# Source this file, then call the provided functions.
# No code runs at source time.
#
# Functions provided:
#   get_session_actual_tokens [session_jsonl_path]
#   append_general_estimate <json_string>
#
# TOKEN REPORTING: Agent prompts should use get_session_actual_tokens()
# instead of the proxy formula (lines × 4 + 5000).
# See L-00145 for why the proxy was retired.
#
# Template for agent prompt Token Usage Report sections:
#
#   source lib/general-estimates.sh
#   echo "=== TOKEN USAGE REPORT ==="
#   echo "activity_type: [name]"
#   echo "estimated_tokens_pre: [N]"
#   ACTUAL_TOKENS=$(get_session_actual_tokens)
#   echo "actual_tokens_data: $ACTUAL_TOKENS"
#   TOTAL=$(echo "$ACTUAL_TOKENS" | jq '.total_tokens // 0')
#   echo "actual_total_tokens: $TOTAL"
#   echo "estimation_error_pct: $(echo "scale=1; (([EST] - $TOTAL) / $TOTAL) * 100" | bc)"
#   echo "source: $(echo "$ACTUAL_TOKENS" | jq -r '.source')"
#   echo "=== END REPORT ==="

# Guard against double-sourcing
if [ "${_GENERAL_ESTIMATES_SH_LOADED:-}" = "true" ]; then
    return 0 2>/dev/null || true
fi
_GENERAL_ESTIMATES_SH_LOADED=true

# Default estimates file location (relative to repo root)
GENERAL_ESTIMATES_FILE="${GENERAL_ESTIMATES_FILE:-general-estimates.jsonl}"

# ── get_session_actual_tokens ────────────────────────────────────────────────
# Reads Claude Code's local JSONL session data and returns actual token counts.
#
# The JSONL files live at ~/.claude/projects/<encoded-cwd>/<session-id>.jsonl
# Each assistant entry has message.usage with:
#   input_tokens, output_tokens, cache_creation_input_tokens, cache_read_input_tokens
#
# Usage: get_session_actual_tokens [path_to_jsonl]
#   If no path given, finds the most recent JSONL in ~/.claude/projects/
#
# Output: JSON object to stdout with fields:
#   input_tokens, output_tokens, cache_creation_tokens, cache_read_tokens,
#   total_tokens, api_calls, source
#
# Returns 0 on success, 1 on failure (with error JSON on stdout).
# See L-00145 for why this replaces the proxy formula.
get_session_actual_tokens() {
    local jsonl_path="${1:-}"

    # If no explicit path, find the most recent session JSONL
    if [ -z "$jsonl_path" ]; then
        local claude_projects_dir="$HOME/.claude/projects"
        if [ ! -d "$claude_projects_dir" ]; then
            echo '{"error": "Claude projects directory not found", "source": "none"}'
            return 1
        fi

        jsonl_path=$(find "$claude_projects_dir" -name "*.jsonl" -type f -printf '%T+ %p\n' 2>/dev/null \
            | sort -r | head -1 | awk '{print $2}')

        if [ -z "$jsonl_path" ]; then
            echo '{"error": "No JSONL session files found", "source": "none"}'
            return 1
        fi
    fi

    if [ ! -f "$jsonl_path" ]; then
        echo "{\"error\": \"JSONL file not found: $jsonl_path\", \"source\": \"none\"}"
        return 1
    fi

    # Parse the JSONL: filter assistant entries, extract message.usage, sum fields
    python3 -c "
import json, sys

input_total = 0
output_total = 0
cache_creation_total = 0
cache_read_total = 0
api_calls = 0

with open(sys.argv[1]) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if data.get('type') != 'assistant':
            continue
        usage = data.get('message', {}).get('usage', {})
        if not usage:
            continue
        api_calls += 1
        input_total += usage.get('input_tokens', 0)
        output_total += usage.get('output_tokens', 0)
        cache_creation_total += usage.get('cache_creation_input_tokens', 0)
        cache_read_total += usage.get('cache_read_input_tokens', 0)

result = {
    'input_tokens': input_total,
    'output_tokens': output_total,
    'cache_creation_tokens': cache_creation_total,
    'cache_read_tokens': cache_read_total,
    'total_tokens': input_total + output_total + cache_creation_total + cache_read_total,
    'api_calls': api_calls,
    'source': 'jsonl_direct'
}
print(json.dumps(result))
" "$jsonl_path" 2>/dev/null

    if [ $? -ne 0 ]; then
        echo '{"error": "Failed to parse JSONL", "source": "none"}'
        return 1
    fi

    return 0
}

# ── append_general_estimate ──────────────────────────────────────────────────
# Appends a JSON record to the general-estimates JSONL file.
#
# Usage: append_general_estimate <json_string>
#   json_string: a valid JSON object to append as one line
#
# The file path is controlled by GENERAL_ESTIMATES_FILE (default: general-estimates.jsonl).
append_general_estimate() {
    local json_string="${1:-}"

    if [ -z "$json_string" ]; then
        echo "append_general_estimate: json_string is required" >&2
        return 1
    fi

    # Validate JSON before appending
    if ! echo "$json_string" | jq -e '.' >/dev/null 2>&1; then
        echo "append_general_estimate: invalid JSON: $json_string" >&2
        return 1
    fi

    # Compact and append
    echo "$json_string" | jq -c '.' >> "$GENERAL_ESTIMATES_FILE"
}
