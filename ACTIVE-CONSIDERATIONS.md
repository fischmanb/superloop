# Active Considerations

> What's next and what's in-flight. Priority stack is the execution plan; everything below it is context a fresh chat should pick up.
>
> Split from ONBOARDING.md (2026-03-01) to keep onboarding focused on orientation.

---

### Priority stack (updated 2026-03-01, late evening)

Ordered by efficiency gain per complexity added:

1. **stakd 28-feature campaign — v2 COMPLETE, v3 STALLED.**
   - **stakd-v2 (Sonnet 4.6)**: ✅ 28/28 features built. Post-campaign `npm run build` fails — client component (NewsCategoryFilter.tsx) transitively imports postgres via news.ts → db/index.ts. Same root cause as stakd-v1. Fix prompt drafted, pending execution.
   - **stakd-v3 (Haiku 4.5)**: ⏸️ Stalled at 11/28 features. Hung `claude` process (PID 94635) killed 2026-02-28. Build loop needs restart.
   - **Throughput finding**: Token speed does NOT translate to build speed. Haiku 2x faster tokens but only marginally faster builds (~16-18 min/feature both models) because npm install, TypeScript compile, tests, drift checks are fixed-cost CPU/disk-bound steps. Parallelism across features matters more than per-feature model speed.
   - **Build logs**: `stakd-v2/logs/build-*.log` and `stakd-v3/logs/build-*.log`.
   - Round 35 merged to main and pushed to origin.
   - **Data snapshot**: `~/auto-sdd/campaign-results/` — raw/ and reports/ per campaign variant.
2. **Bash→Python conversion — Phases 0–3 COMPLETE (2026-03-01).**
   - Plan: `WIP/bash-to-python-conversion.md` (authoritative).
   - Phase 0: `py/auto_sdd/conventions.md` (481 lines), `py/pyproject.toml`, `py/tests/conftest.py`, dependency map + interface stubs.
   - **Phase 1 DONE**: 5 lib modules converted. 210 pytest assertions, mypy --strict clean. Merged at `bed34a4`.
   - **Phase 2 DONE**: eval-sidecar converted. 31 tests, 77 assertions, mypy --strict clean. Merged to main.
   - **Phase 3 DONE**: build-loop-local decomposition analysis. 10 logical sections, 2-agent sequential split (4a: support modules, 4b: core orchestration). Key finding: 3+1 duplicated success-recording blocks → single `_record_build_result()`. Full analysis in `WIP/bash-to-python-conversion.md`.
   - **Phase 4a DONE**: 4 support modules (build_gates, drift, branch_manager, prompt_builder). 1,714 lines, 103 tests. Merged at `b534d22`.
   - **Phase 4b DONE**: BuildLoop class (core orchestration, 3+1 dedup, json.dumps summary). 1,521 lines, 40 tests. Merged at `6dc6497`. 384 tests total, zero regressions.
   - **Phase 5 DONE**: OvernightRunner (overnight-autonomous.sh → Python). Composition over subclass. 640 lines, 70 tests. Merged at `9bf0f05`. 454 tests total, zero regressions.
   - **Phase 6 DONE**: Final scripts (nightly_review, generate_mapping, general_estimates). 760 lines impl + 890 lines tests. 114 new tests. Merged at `b7114f8`. 568 tests total, zero regressions.
   - **CONVERSION COMPLETE.** All bash scripts and libs have Python equivalents. Remaining: integration test against real project, retire bash test suites (2,149 lines), extract errors.py/signals.py/state.py from reliability.py monolith (conventions specify these but Phase 1 inlined them).
   - **Post-conversion audit COMPLETE (2026-03-03).** Project-agnostic audit found 30 findings (5 BLOCKING, 9 WARNING, 9 INFO, 7 CLEAN). 16 non-INFO findings resolved in Rounds 47-49: codebase summary replaced with agent-generated (cached on tree hash), eval/dead-export scan extended to Python/Rust/Go, infrastructure hardened (tempdir, sh, sidecar fallback, configurable branch). Finding #27 (fcntl/Windows) deferred. 7 remaining findings are INFO-only.
3. ~~**Build loop design improvements — folded into Phase 4 (2026-03-01).**~~ ✅ DONE — L-00111 patterns wired into Phase 4 prompts.
4. **Eval sidecar gap: quality gate → learning system (post-migration).**
   - Current: per-commit scoring (compliance, scope, integration) + `repeated_mistakes` feedback into next build prompt. Campaign summary is aggregate tallies only.
   - Gap: no learnings extraction, no cross-feature pattern analysis, no decision evaluation, no "what worked and why" synthesis. EVAL_NOTES is a one-line string, not structured.
   - Target: full learning loop — extract actionable patterns from build outcomes, synthesize across features, feed structured insights (not just mistake flags) back into prompts. Campaign summary should produce findings, not just counts.
   - Blocked on: migration completion + at least one real Python build campaign for data.
5. **auto-QA (post-campaign validation pipeline) — ALL PHASES COMPLETE.** Multi-agent pipeline: boot app, Playwright browse, generate ACs from specs, test, catalog failures, RCA, fix through build gates. Seven phases (0-5, Phase 4 split into 4a+4b). Spec: `WIP/post-campaign-validation.md` (v0.3).
   - **Phase 0 DONE**: Runtime bootstrap. 41 tests. Merged at `b7feb18`.
   - **Phase 1 DONE**: Discovery Agent. +8 tests. Merged at `874cbd0`.
   - **Phase 2a+2b DONE**: AC generation + mechanical gap detection. +11 tests. Refactored at `df1d588`.
   - **Phase 3 DONE**: Playwright Validation. +9 tests. Merged at `891eda6`.
   - **Phase 4a DONE**: Failure Catalog (mechanical). +8 tests. Merged at `818b758`.
   - **Phase 4b DONE**: Root Cause Analysis (agent-based). +9 tests. Merged at `f2d88cd`.
   - **Phase 5 DONE**: Fix Agents (fix→gate→commit→revalidate→revert loop). +10 tests. Merged at `a7c1137`.
   - Implementation: `py/auto_sdd/scripts/post_campaign_validation.py` (96 tests, mypy --strict clean).
   - **NEXT: Live validation run against real project (cre-lease-tracker or stakd).**
5. **Local model integration** — Replace cloud API with local LM Studio on Mac Studio. Reference: `archive/local-llm-pipeline/`. *Not started.*
6. **Adaptive routing / parallelism** — Only if data from 1–3 justifies complexity. *Deprioritized.*

### Historical build estimator (designed, not yet built)

Correlates t-shirt sizes with actual metrics from `logs/build-summary-*.json`. Writes to `logs/estimation-model.json`. Self-correcting after each `write_build_summary()`. Build after stakd campaign provides real data.

### Other active items

- **Learnings system — IMPLEMENTED (2026-03-01)**: 100+ graph-compliant entries (L-00001–L-00163, M-00001–M-00084), 13 curated in `core.md`, all inlined into CLAUDE.md. Schema standardization complete (5-digit IDs). Token calibration infrastructure: general-estimates.jsonl + 4 functions in lib/general-estimates.sh. Remaining: old-format conversion (Prompts 4/5), index.md stale.
- **Recently completed (2026-03-03, evening)**: Hard constraints fixes — `run_claude()` cwd passthrough (agents ran in wrong dir), retry model fallback chain, summary model chain, configurable `AGENT_TIMEOUT` env var (default 1800s, was hardcoded 600). 619 tests passing. Main at `bf22cc0`.
- **Recently completed (2026-03-03, earlier)**: Project-agnostic audit + 3 remediation rounds (47-49). Agent-based codebase summary, multilang eval patterns, infra portability. Main at `d2f8792`. All branches merged and cleaned.
- **Recently completed (2026-03-01)**: Token estimation proxy replaced (L-00145/L-00148/L-00149), L-00143 wired into infrastructure (d1a1a72), core learnings inlined into CLAUDE.md (f7be98c), Dispatches 2–4 all landed. Queue empty.
- **HOW-I-WORK corpus curation (2026-03-01)**: 74 entries converted to graph schema (M-00001–M-00074). Full corpus read identified 4+ coherent clusters ready for formalization. Action: curate entries into named sections, promote mature patterns to learnings.
- **Knowledge graph for workflow continuity (2026-02-28)**: Personal workflow tool for cross-session context. *Design phase — no implementation started.*
- **State format migration (2026-03-01)**: Post-Python-conversion project. Current file-based state preserved during bash→Python conversion. Not started, intentionally deferred — one variable at a time.
- **Learnings graph-schema conversion (2026-03-01)**: Schema standardization complete. Some old-format entries may remain in `.specs/learnings/` files. Two agent prompts ready (Prompts 4 & 5) for converting those.
- **Response scope discipline (2026-03-01)**: Formalized as L-00143 scope sizing ritual. Supersedes ad-hoc ">3 items = split" rule with systematic verification-isolation-based sizing.
- **Slash commands & skills — Code-only (2026-03-01)**: Both `.claude/commands/` and `.claude/skills/` only work in Claude Code (terminal). They do NOT work in Claude.ai Chat tab or Desktop Chat. For Chat-based workflows (extract-learnings, checkpoint), rely on Claude's memory + Desktop Commander + natural language triggers. Skills were created anyway for Code tab agent use.
- **CLAUDE.md audit (2026-03-01)**: Root CLAUDE.md 468 lines, ~80% stale SDD scaffold (L-00087, L-00094). stakd/CLAUDE.md has battle-tested Next.js 15 patterns not in root. Tasks: (1) strip root to ~100-150 lines of operational content, (2) evaluate whether stakd-specific patterns should be in learnings or stay project-local.
- **Memory slot optimization (2026-03-01)**: 15/30 slots, ~1,500 words always-injected. Not urgent now but monitor. (L-00095)
- **ONBOARDING.md overhaul for efficient context (2026-03-01)**: Checkpoint expansion DONE. Remaining: broader audit after graph conversion lands.

