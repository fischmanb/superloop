# Active Considerations

> What's next and what's in-flight. Priority stack is the execution plan; everything below it is context a fresh chat should pick up.
>
> Split from ONBOARDING.md (2026-03-01) to keep onboarding focused on orientation.

---

### Priority stack (updated 2026-03-02, evening)

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
   - **Phase 1 DONE**: 5 lib modules converted (reliability, eval, codebase-summary, validation, claude-wrapper). 210 pytest assertions, mypy --strict clean. Merged to main at `bed34a4`. See L-00105–L-00110.
   - **Phase 2 DONE**: eval-sidecar.sh (393L) → `py/auto_sdd/scripts/eval_sidecar.py`. 31 tests, 77 assertions, mypy --strict clean. Branch `claude/implement-hard-constraints-8IMAC` at `e532a54`, not yet merged to main.
   - **Phase 3 next**: Build-loop-local decomposition analysis (chat session). Identify sub-units for Phase 4 conversion.
3. **Build loop design improvements for Phase 4 (2026-03-01).**
   - L-00111: 6 meta-process patterns from the bash→Python conversion that the build loop should implement. Highest leverage: context budget estimation before dispatch, conventions doc injection, mechanical prompt quality gate.
   - These are design inputs for Phase 4 (build-loop-local conversion), not separate tasks. When Phase 3 decomposes build-loop-local into sub-units, these patterns inform the new architecture.
4. **auto-QA (post-campaign validation pipeline)** — Multi-agent pipeline: boot app, Playwright browse, generate ACs from specs, test, catalog failures, RCA, fix through build gates. Seven phases (0-5, Phase 4 split into 4a+4b). Spec: `WIP/post-campaign-validation.md` (v0.3). *Spec complete, implementation not started. Will be implemented in Python post-conversion.*
5. **Local model integration** — Replace cloud API with local LM Studio on Mac Studio. Reference: `archive/local-llm-pipeline/`. *Not started.*
6. **Adaptive routing / parallelism** — Only if data from 1–3 justifies complexity. *Deprioritized.*

### Historical build estimator (designed, not yet built)

Correlates t-shirt sizes with actual metrics from `logs/build-summary-*.json`. Writes to `logs/estimation-model.json`. Self-correcting after each `write_build_summary()`. Build after stakd campaign provides real data.

### Other active items

- **Learnings system — IMPLEMENTED (2026-03-02)**: 85+ graph-compliant entries (L-00001–L-00151, non-contiguous), 13 curated in `core.md`, all inlined into CLAUDE.md. Schema standardization complete (5-digit IDs). Token calibration infrastructure: general-estimates.jsonl + 4 functions in lib/general-estimates.sh (write: append_general_estimate + get_session_actual_tokens; read: query_estimate_actuals + estimate_general_tokens). Remaining: old-format conversion (Prompts 4/5), index.md stale.
- **Replace token estimation proxy — DONE (Dispatch 4, 2026-03-02)**: `get_session_actual_tokens` reads Claude Code JSONL session logs. Token report now distinguishes active_tokens (input+output, for calibration) from cumulative_tokens (incl cache reads). Merged to main. See L-00145, L-00148, L-00149.
- **Wire L-00143 into active infrastructure** — ✅ DONE (2026-03-02). query_estimate_actuals + estimate_general_tokens added (d1a1a72). Calibration read loop closed.
- **Dispatch 2: core learnings mechanical wiring** — ✅ DONE (2026-03-02). All 5 items landed across prior agents (L-00143 engrain + checkpoint agents).
- **Dispatch 3: wire estimate_general_tokens into scope sizing ritual read path** — ✅ DONE (2026-03-02). Functions added directly, no agent needed (d1a1a72).
- **Core learnings inline into CLAUDE.md** — ✅ DONE (2026-03-02). 13 entries compressed into ~256-word block. Merged at f7be98c.
- **HOW-I-WORK corpus curation (2026-03-02)**: 74 entries converted to graph schema (M-00001–M-00074). Full corpus read identified 4+ coherent clusters ready for formalization. Action: curate entries into named sections, promote mature patterns to learnings.
- **Knowledge graph for workflow continuity (2026-02-28)**: Personal workflow tool for cross-session context. *Design phase — no implementation started.*
- **State format migration (2026-03-01)**: Post-Python-conversion project. Current file-based state preserved during bash→Python conversion. Not started, intentionally deferred — one variable at a time.
- **Learnings graph-schema conversion (2026-03-02)**: Schema standardization complete. Some old-format entries may remain in `.specs/learnings/` files. Two agent prompts ready (Prompts 4 & 5) for converting those.
- **Response scope discipline (2026-03-02)**: Formalized as L-00143 scope sizing ritual. Supersedes ad-hoc ">3 items = split" rule with systematic verification-isolation-based sizing.
- **Slash commands & skills — Code-only (2026-03-02)**: Both `.claude/commands/` and `.claude/skills/` only work in Claude Code (terminal). They do NOT work in Claude.ai Chat tab or Desktop Chat. For Chat-based workflows (extract-learnings, checkpoint), rely on Claude's memory + Desktop Commander + natural language triggers. Skills were created anyway for Code tab agent use.
- **CLAUDE.md audit (2026-03-01)**: Root CLAUDE.md 468 lines, ~80% stale SDD scaffold (L-00087, L-00094). stakd/CLAUDE.md has battle-tested Next.js 15 patterns not in root. Tasks: (1) strip root to ~100-150 lines of operational content, (2) evaluate whether stakd-specific patterns should be in learnings or stay project-local.
- **Memory slot optimization (2026-03-01)**: 15/30 slots, ~1,500 words always-injected. Not urgent now but monitor. (L-00095)
- **ONBOARDING.md overhaul for efficient context (2026-03-01)**: Checkpoint expansion DONE. Remaining: broader audit after graph conversion lands.

