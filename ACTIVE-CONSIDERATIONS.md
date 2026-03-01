# Active Considerations

> What's next and what's in-flight. Priority stack is the execution plan; everything below it is context a fresh chat should pick up.
>
> Split from ONBOARDING.md (2026-03-01) to keep onboarding focused on orientation.

---

### Priority stack (updated 2026-02-28)

Ordered by efficiency gain per complexity added:

1. **stakd 28-feature campaign — v2 COMPLETE, v3 STALLED.**
   - **stakd-v2 (Sonnet 4.6)**: ✅ 28/28 features built. Post-campaign `npm run build` fails — client component (NewsCategoryFilter.tsx) transitively imports postgres via news.ts → db/index.ts. Same root cause as stakd-v1. Fix prompt drafted, pending execution.
   - **stakd-v3 (Haiku 4.5)**: ⏸️ Stalled at 11/28 features. Hung `claude` process (PID 94635) killed 2026-02-28. Build loop needs restart.
   - **Throughput finding**: Token speed does NOT translate to build speed. Haiku 2x faster tokens but only marginally faster builds (~16-18 min/feature both models) because npm install, TypeScript compile, tests, drift checks are fixed-cost CPU/disk-bound steps. Parallelism across features matters more than per-feature model speed.
   - **Build logs**: `stakd-v2/logs/build-*.log` and `stakd-v3/logs/build-*.log`.
   - Round 35 merged to main and pushed to origin.
   - **Data snapshot**: `~/auto-sdd/campaign-results/` — raw/ and reports/ per campaign variant.
2. **Bash→Python conversion — Phases 0–2 COMPLETE (2026-03-01).**
   - Plan: `WIP/bash-to-python-conversion.md` (authoritative).
   - Phase 0: `py/auto_sdd/conventions.md` (481 lines), `py/pyproject.toml`, `py/tests/conftest.py`, dependency map + interface stubs.
   - **Phase 1 DONE**: 5 lib modules converted (reliability, eval, codebase-summary, validation, claude-wrapper). 210 pytest assertions, mypy --strict clean. Merged to main at `bed34a4`. See L-0105–L-0110.
   - **Phase 2 DONE**: eval-sidecar.sh (393L) → `py/auto_sdd/scripts/eval_sidecar.py`. 31 tests, 77 assertions, mypy --strict clean. Branch `claude/implement-hard-constraints-8IMAC` at `e532a54`, not yet merged to main.
   - **Phase 3 next**: Build-loop-local decomposition analysis (chat session). Identify sub-units for Phase 4 conversion.
3. **Build loop design improvements for Phase 4 (2026-03-01).**
   - L-0111: 6 meta-process patterns from the bash→Python conversion that the build loop should implement. Highest leverage: context budget estimation before dispatch, conventions doc injection, mechanical prompt quality gate.
   - These are design inputs for Phase 4 (build-loop-local conversion), not separate tasks. When Phase 3 decomposes build-loop-local into sub-units, these patterns inform the new architecture.
4. **auto-QA (post-campaign validation pipeline)** — Multi-agent pipeline: boot app, Playwright browse, generate ACs from specs, test, catalog failures, RCA, fix through build gates. Seven phases (0-5, Phase 4 split into 4a+4b). Spec: `WIP/post-campaign-validation.md` (v0.3). *Spec complete, implementation not started. Will be implemented in Python post-conversion.*
5. **Local model integration** — Replace cloud API with local LM Studio on Mac Studio. Reference: `archive/local-llm-pipeline/`. *Not started.*
6. **Adaptive routing / parallelism** — Only if data from 1–3 justifies complexity. *Deprioritized.*

### Historical build estimator (designed, not yet built)

Correlates t-shirt sizes with actual metrics from `logs/build-summary-*.json`. Writes to `logs/estimation-model.json`. Self-correcting after each `write_build_summary()`. Build after stakd campaign provides real data.

### Other active items

- **Learnings system — IMPLEMENTED (2026-03-01)**: 67 graph-compliant entries (L-0001–L-0133, non-contiguous), 12 curated in `core.md`. Fresh onboard path works. Remaining: old-format conversion (Prompts 4/5), index.md stale.
- **Knowledge graph for workflow continuity (2026-02-28)**: Personal workflow tool for cross-session context. *Design phase — no implementation started.*
- **`HOW-I-WORK-WITH-GENERATIVE-AI.md` (2026-03-01)**: Repo-agnostic methodology document at repo root. Checkpoint step 5 auto-captures methodology signals to accumulation section; Brian curates into prose. Bootstrapped with 8 captures. Context window onboarding cost is an open question.
- **State format migration (2026-03-01)**: Post-Python-conversion project. Current file-based state preserved during bash→Python conversion. Future consideration: SQLite or structured JSON for queryable state ("show me all features that failed with error X across all rounds"). Not started, intentionally deferred — one variable at a time.
- **Learnings graph-schema conversion (2026-03-01)**: 67 graph-compliant entries (L-0001–L-0133) across type-specific files. Some old-format entries may remain in `.specs/learnings/` files. Two agent prompts ready (Prompts 4 & 5) for converting those. Studio candidate.
- **Response scope discipline (2026-03-01)**: Two truncations + one approval gate violation in one session (L-0098, L-0103, L-0104). Rules: count work items BEFORE first tool call, >3 items = split. "Do what you need to do" ≠ "yes to push." Confidence is not approval.
- **HOW-I-WORK corpus curation (2026-03-02)**: Accumulation section has 60+ raw entries and zero curated sections. Full corpus read identified 4+ coherent clusters ready for formalization: (1) prompt engineering theory (~5 entries: token cost as quality metric, compression principle, boilerplate vs verbosity), (2) agent autonomy model (~4 entries: test→investigate→evaluate→verify→report, spec prescriptiveness calibration), (3) session type theory (~3 entries: sustained context for planning, fresh agents for execution, zero-code sessions as productive), (4) capture philosophy (~5 entries: capture-biased over precision-biased, density-matched, perishable lucidity). "We want to be 1" is the philosophical foundation connecting all clusters. Action: curate entries into named sections, promote mature patterns to learnings. L-0133 (corpus-level review) documents the method that surfaced this.
- **CLAUDE.md audit (2026-03-01)**: Root CLAUDE.md 468 lines, ~80% stale SDD scaffold (L-0087, L-0094). stakd/CLAUDE.md has battle-tested Next.js 15 patterns not in root. Tasks: (1) strip root to ~100-150 lines of operational content, (2) evaluate whether stakd-specific patterns should be in learnings or stay project-local, (3) stakd-v2/v3 versions are near-identical to stakd — no action needed. Brian confirmed root placement correct; "wrong place" = orphaned stakd versions.
- **Memory slot optimization (2026-03-01)**: 15/30 slots, ~1,500 words always-injected. Slots #10-14 situational (~300 tokens, ~30% hit rate). When approaching 20 slots, migrate situational rules to repo and trust onboarding. Not urgent now but monitor. (L-0095)
- **ONBOARDING.md overhaul for efficient context (2026-03-01)**: Checkpoint expansion DONE (Prompt 6 merged, 788f8a8). Remaining: broader audit — does a fresh session get proper bootstrap without bloat? Evaluate after graph conversion lands.

