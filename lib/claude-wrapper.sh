#!/usr/bin/env bash
# claude-wrapper.sh — wraps claude CLI to capture cost/usage data
# Runs claude with --output-format json, extracts .result as raw text to stdout,
# appends cost metadata to $COST_LOG_FILE as JSONL.
set -euo pipefail

COST_LOG="${COST_LOG_FILE:-./cost-log.jsonl}"

tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT

claude "$@" --output-format json > "$tmp" 2>/dev/null
claude_exit=$?

if jq -e '.result' "$tmp" > /dev/null 2>&1; then
    jq -r '.result // empty' "$tmp"

    jq -c '{
        timestamp: (now | todate),
        cost_usd: .total_cost_usd,
        input_tokens: .usage.input_tokens,
        output_tokens: .usage.output_tokens,
        cache_creation_tokens: .usage.cache_creation_input_tokens,
        cache_read_tokens: .usage.cache_read_input_tokens,
        duration_ms: .duration_ms,
        duration_api_ms: .duration_api_ms,
        num_turns: .num_turns,
        model: (.modelUsage | keys[0] // "unknown"),
        session_id: .session_id,
        stop_reason: .stop_reason
    }' "$tmp" >> "$COST_LOG" 2>/dev/null
else
    cat "$tmp" >&2
    echo "WRAPPER_ERROR: claude did not return valid JSON. Raw output sent to stderr." >&1
fi

exit $claude_exit
