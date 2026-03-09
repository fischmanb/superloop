# Project Isolation Contract

## 1. Principle

Target projects and the auto-sdd build system are **separate trust domains** with separate git repositories on separate filesystem paths. All data flow between them must pass through enumerated pipelines defined in this document. Any cross-boundary read or write not listed here is **contamination** and must be treated as a build failure.

## 2. Pipeline Inventory

| Pipeline name | Direction | Source Component | Write Target | Purpose | Enforced? |
|----------|-----------|-----------------|--------------|---------|-----------|
| Build agent code writes | auto-sdd → project | `build_loop.py:_build_feature()` (agent invoked with `cwd=project_dir`) | `<project_dir>/**` (any file the agent creates/modifies) | Feature implementation — specs, source, tests | No |
| Codebase summary cache | auto-sdd → project | `codebase_summary.py:_write_cache()` L114–121 | `<project_dir>/.auto-sdd-cache/codebase-summary-<hash>.md` | Cache structural summary by git tree hash | No |
| Project-local learnings | auto-sdd → project | `learnings_writer.py:write_learning()` L96–116 | `<project_dir>/.specs/learnings/general.md` | Append build findings for agent prompt injection | No |
| Resume state | auto-sdd → project | `reliability.py:write_state()` via `build_loop.py` L769–771 | `<project_dir>/.sdd-state/resume.json` | Track completed features for campaign resume | No |
| Feature vectors | auto-sdd → project | `vector_store.py:VectorStore` via `build_loop.py` L499–500 | `<project_dir>/.sdd-state/feature-vectors.jsonl` | Campaign intelligence feature vector storage | No |
| Risk context | auto-sdd → project | `pattern_analysis.py:generate_risk_context()` | `<project_dir>/.sdd-state/risk-context.md` | Risk analysis output for prompt injection | No |
| Spec drift reconciliation | auto-sdd → project | Drift-check agent (invoked by `build_loop.py`) | `<project_dir>/.specs/**` | Agent writes reconciled specs during drift fix | No |
| Roadmap updates | auto-sdd → project | Build agent (invoked by `build_loop.py`) | `<project_dir>/.specs/roadmap.md` | Agent marks features as completed | No |
| Drain sentinel | auto-sdd → project | `eval_sidecar.py:run_polling_loop()` L596–600 | `<project_dir>/.sdd-eval-drain` | Signal eval sidecar to drain and exit | No |
| Repo-level learnings | auto-sdd ← project (write to auto-sdd) | `learnings_writer.py:write_learning()` L118–142 | `<auto-sdd>/learnings/pending.md` | Queue findings for human review and promotion | No |
| Build summary | build loop telemetry | `build_loop.py:write_build_summary()` L1682–1688 | `<logs_dir>/build-summary-<ts>.json` | Campaign-level build results | Yes (LOGS_DIR) |
| Cost log | build loop telemetry | `build_loop.py` via `prompt_builder.py` | `<logs_dir>/cost-log.jsonl` | Per-invocation token/cost tracking | Yes (LOGS_DIR) |
| Eval results | eval sidecar telemetry | `eval_lib.py:write_eval_result()` L536–600 | `<logs_dir>/evals/eval-<feature>.json` | Per-feature mechanical + agent eval results | Yes (LOGS_DIR) |
| Eval campaign summary | eval sidecar telemetry | `eval_sidecar.py:generate_campaign_summary()` L192–352 | `<logs_dir>/evals/eval-campaign-<ts>.json` | Aggregate eval statistics | Yes (LOGS_DIR) |
| Eval sidecar log | build loop telemetry | `build_loop.py` L1734–1745 | `<logs_dir>/eval-sidecar.log` | Sidecar stdout/stderr capture | Yes (LOGS_DIR) |
| Retry context | build loop telemetry | `build_loop.py` L1074–1089 | `<logs_dir>/evals/retry-context/<hash>.retry.json` | Failed attempt context for eval prompt injection | Yes (LOGS_DIR) |
| Project config read | project → auto-sdd (read only) | `project_config.py:load_project_config()` | N/A (read `<project_dir>/.sdd-config/project.yaml`) | Project-specific env var defaults | N/A (read) |
| Codebase summary read | project → auto-sdd (read only) | `codebase_summary.py:_read_recent_learnings()` L139–172 | N/A (read `<project_dir>/.specs/learnings/*.md`) | Inject learnings into codebase summary prompt | N/A (read) |
| Constraint injection | project → auto-sdd (read only) | `prompt_builder.py:build_feature_prompt()` | N/A (reads constraints, injects into agent prompt) | Hardcoded constraints for build agent prompt | N/A (read) |

**LOGS_DIR** resolves to `<auto-sdd>/logs/<project_name>/` by default (`build_loop.py` L425–433), configurable via `LOGS_DIR` env var. All telemetry pipelines write here — inside auto-sdd, not inside the project.

## 3. Proactive Enforcement Design

### Layer 1 — Prompt-level boundary constraint

The prompt builder (`prompt_builder.py:build_feature_prompt()`) must inject a filesystem boundary directive into every build agent prompt:

```
FILESYSTEM BOUNDARY: You may ONLY write files within PROJECT_DIR: {project_dir}
You may NOT write to any path outside this directory. If you need to modify a
file outside PROJECT_DIR, STOP and report the path and reason.
```

This is injected dynamically using the resolved `project_dir` from `BuildConfig`. No per-project hardcoding.

### Layer 2 — Post-agent contamination audit

After every agent invocation in `build_loop.py:_build_feature()`, before recording the result:

1. Run `git -C <auto-sdd-repo-root> status --porcelain` to detect working tree changes.
2. Parse the output. Compare each changed path against the **expected writes allowlist** (Section 4).
3. If any path is NOT on the allowlist → mark the feature as **contaminated**:
   - Log `CONTAMINATION_DETECTED: <path>` signal.
   - Write a learning via `write_learning()` with category `"contamination"`.
   - Mark the feature as failed (do not merge to main).
4. If all changed paths are on the allowlist → proceed normally.

The auto-sdd repo root is derivable from `Path(__file__).resolve().parents[3]` (same pattern as `learnings_writer.py:_default_repo_dir()`).

## 4. Expected Writes Allowlist

Paths within auto-sdd that the build loop itself (not agents) legitimately writes during a campaign:

| Path pattern | Writer |
|-------------|--------|
| `logs/<project>/build-summary-*.json` | `build_loop.py:write_build_summary()` |
| `logs/<project>/cost-log.jsonl` | `build_loop.py` via prompt_builder |
| `logs/<project>/evals/eval-*.json` | `eval_lib.py:write_eval_result()` |
| `logs/<project>/evals/eval-campaign-*.json` | `eval_sidecar.py:generate_campaign_summary()` |
| `logs/<project>/evals/retry-context/*.retry.json` | `build_loop.py` L1084–1089 |
| `logs/<project>/eval-sidecar.log` | `build_loop.py` L1734–1745 |
| `learnings/pending.md` | `learnings_writer.py:write_learning()` |

Everything else appearing in `git status --porcelain` is contamination.

## 5. Implementation Plan

1. **Inject prompt boundary** in `prompt_builder.py:build_feature_prompt()`: Add the `FILESYSTEM BOUNDARY` directive (Section 3, Layer 1) to the prompt template string, interpolating `config.project_dir`. Insert after the existing constraint injection block (~L287). ~5 lines.

2. **Add contamination check** in `build_loop.py:_build_feature()`: After the agent subprocess returns and before `_record_build_result()`, call a new function `_check_contamination(repo_root: Path, allowlist: set[str]) -> list[str]`. This function runs `git status --porcelain` on the auto-sdd repo root and returns any paths not matching the allowlist patterns from Section 4. ~20 lines.

3. **Handle contamination**: If `_check_contamination()` returns non-empty, log `CONTAMINATION_DETECTED` signals, call `write_learning()` with category `"contamination"`, set feature status to `"contaminated"`, and skip merge. Make failure mode configurable via `CONTAMINATION_MODE` env var: `"fail"` (default, feature fails) or `"warn"` (log warning, continue). ~15 lines.

4. **Allowlist definition**: Define `_EXPECTED_WRITE_PATTERNS` as a module-level `frozenset` of glob patterns in `build_loop.py`. Match against the patterns in Section 4. ~10 lines.

5. **Test cases**:
   - Unit test: `_check_contamination()` with clean status returns empty list.
   - Unit test: `_check_contamination()` with allowlisted paths (logs/, learnings/pending.md) returns empty.
   - Unit test: `_check_contamination()` with unexpected path (e.g., `py/auto_sdd/lib/foo.py`) returns that path.
   - Integration test: mock agent that writes outside project_dir, verify feature marked contaminated.
   - Prompt test: grep built prompt for `FILESYSTEM BOUNDARY` directive.
