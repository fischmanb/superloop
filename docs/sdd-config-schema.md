# .sdd-config/project.yaml — Schema Reference

Superloop reads `.sdd-config/project.yaml` from the project root at campaign
startup, before any env var defaults are applied. Values in this file act as
project-committed defaults. Any env var set at launch time takes precedence.

**Priority chain (highest to lowest):**
1. Env var set in shell at launch
2. `.sdd-config/project.yaml`
3. Auto-detection (reads package.json scripts, Cargo.toml, etc.)
4. Hardcoded defaults in build_loop

## Supported Keys

| Key               | Env var           | Type    | Default       | Description |
|-------------------|-------------------|---------|---------------|-------------|
| `build_cmd`       | BUILD_CHECK_CMD   | string  | auto-detect   | Command to verify the build after each feature |
| `test_cmd`        | TEST_CHECK_CMD    | string  | auto-detect   | Command to run the test suite (one-shot, not watch mode) |
| `lint_cmd`        | LINT_CHECK_CMD    | string  | auto-detect   | Command to run the linter |
| `build_model`     | BUILD_MODEL       | string  | CLI default   | Claude model for build agents |
| `agent_model`     | AGENT_MODEL       | string  | CLI default   | Claude model for all agents (overridden by step-specific models) |
| `max_retries`     | MAX_RETRIES       | int     | 1             | Retry attempts per feature on build failure |
| `agent_timeout`   | AGENT_TIMEOUT     | int     | 1800          | Seconds before an agent invocation times out |
| `branch_strategy` | BRANCH_STRATEGY   | string  | chained       | Branch naming strategy: `chained` or `isolated` |
| `min_retry_delay` | MIN_RETRY_DELAY   | int     | 30            | Minimum seconds between retry attempts |
| `drift_check`     | DRIFT_CHECK       | bool    | true          | Run drift check after each successful feature |
| `post_build_steps`| POST_BUILD_STEPS  | string  | test,dead-code,lint | Comma-separated post-build gates |

## Keys intentionally excluded from project.yaml

These are **runtime decisions** made by the human launching the campaign.
They do not belong in version-controlled project config.

| Key              | Env var         | Why excluded |
|------------------|-----------------|--------------|
| `max_features`   | MAX_FEATURES    | Runtime cap ("build 5 today"). Omit to build all pending. Hardcoding the current pending count is always wrong — it goes stale the moment you add a feature. |
| `auto_approve`   | AUTO_APPROVE    | Controls agent-level confirmation prompts. Runtime decision, not project property. |
| `skip_preflight` | SKIP_PREFLIGHT  | Bypasses the human pre-flight review gate. Must never be committed — the whole point is a human sees the plan before the campaign runs. |

## SKIP_PREFLIGHT vs AUTO_APPROVE

These are intentionally separate flags:

- `SKIP_PREFLIGHT=true` — skip the human pre-flight build plan review (shown once before the campaign starts)
- `AUTO_APPROVE=true` — skip per-agent confirmation prompts during the build

For a fully unattended run: set both at launch time, never commit either.

## YAML Format

Flat key: value only. No nesting, no lists, no anchors. Comments with `#`.

```yaml
build_cmd: NODE_ENV=production next build
test_cmd: npx vitest run --passWithNoTests
lint_cmd: npm run lint
build_model: claude-sonnet-4-6
max_retries: 2
agent_timeout: 1800
```

## Why This Exists

Env vars at launch time are not committed — they're easy to forget, inconsistent
across machines, and require re-declaration on every campaign restart. This file
makes the project's operational configuration explicit, version-controlled, and
self-documenting. A new machine, a new collaborator, or a resumed campaign picks
up the right configuration without any environment setup.
