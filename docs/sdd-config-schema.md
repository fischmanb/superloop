# .sdd-config/project.yaml — Schema Reference

Superloop reads `.sdd-config/project.yaml` from the project root at campaign
startup, before any env var defaults are applied. Values in this file act as
project-committed defaults. Any env var set at launch time takes precedence.

**Priority chain (highest to lowest):**
1. Env var set in shell at launch (e.g. `BUILD_MODEL=x bash build-loop-local.sh`)
2. `.sdd-config/project.yaml`
3. Auto-detection (build_gates.detect_* reads package.json scripts, Cargo.toml, etc.)
4. Hardcoded defaults in build_loop

## Supported Keys

| Key               | Env var           | Type    | Default       | Description |
|-------------------|-------------------|---------|---------------|-------------|
| `build_cmd`       | BUILD_CHECK_CMD   | string  | auto-detect   | Command to verify the build after each feature |
| `test_cmd`        | TEST_CHECK_CMD    | string  | auto-detect   | Command to run the test suite (one-shot, not watch mode) |
| `lint_cmd`        | LINT_CHECK_CMD    | string  | auto-detect   | Command to run the linter |
| `build_model`     | BUILD_MODEL       | string  | CLI default   | Claude model for build agents |
| `agent_model`     | AGENT_MODEL       | string  | CLI default   | Claude model for all agents (overridden by step-specific models) |
| `max_features`    | MAX_FEATURES      | int     | 25            | Maximum features to build in one campaign run |
| `max_retries`     | MAX_RETRIES       | int     | 1             | Retry attempts per feature on build failure |
| `agent_timeout`   | AGENT_TIMEOUT     | int     | 1800          | Seconds before an agent invocation times out |
| `auto_approve`    | AUTO_APPROVE      | bool    | false         | Skip the pre-flight confirmation prompt |
| `branch_strategy` | BRANCH_STRATEGY   | string  | chained       | Branch naming strategy: `chained` or `isolated` |
| `min_retry_delay` | MIN_RETRY_DELAY   | int     | 30            | Minimum seconds between retry attempts |
| `drift_check`     | DRIFT_CHECK       | bool    | true          | Run drift check after each successful feature |
| `post_build_steps`| POST_BUILD_STEPS  | string  | test,dead-code,lint | Comma-separated post-build gates |

## YAML Format

Flat key: value only. No nesting, no lists, no anchors. Comments with `#`.

```yaml
build_cmd: NODE_ENV=production next build
test_cmd: npx vitest run --passWithNoTests
lint_cmd: npm run lint
build_model: claude-sonnet-4-6
max_features: 100
max_retries: 2
agent_timeout: 1800
auto_approve: true
```

## Why This Exists

Env vars at launch time are not committed — they're easy to forget, inconsistent
across machines, and require re-declaration on every campaign restart. This file
makes the project's operational configuration explicit, version-controlled, and
self-documenting. A new machine, a new collaborator, or a resumed campaign picks
up the right configuration without any environment setup.
