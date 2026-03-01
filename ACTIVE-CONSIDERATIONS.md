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
2. **Bash→Python conversion — Phase 0 COMPLETE, Phase 1 ready (2026-03-01).**
   - Plan: `WIP/bash-to-python-conversion.md` (authoritative).
   - Phase 0 deliverables DONE: `py/auto_sdd/conventions.md` (481 lines — error handling, subprocess, logging, state I/O, signal protocol, pytest patterns, interface stubs, type hints, naming conventions, dependency rules, "what not to do"), `py/pyproject.toml`, `py/tests/conftest.py`, dependency map + interface stubs in WIP doc.
   - Key decisions: claude-wrapper moved to Phase 1 (5th parallel agent), launchd scripts stay bash, bash originals preserved in separate tree (`py/`), conventions doc scope expanded with interface stubs. All logged in DECISIONS.md.
   - **Phase 1 next**: 5 parallel Claude Code agents (desktop app tabs), one per lib file + claude-wrapper. Each agent gets conventions.md + its bash source + its test file target.
   - Python 3.12+, typed exceptions, mypy --strict, pytest, stdlib-only deps.
3. **auto-QA (post-campaign validation pipeline)** — Multi-agent pipeline: boot app, Playwright browse, generate ACs from specs, test, catalog failures, RCA, fix through build gates. Seven phases (0-5, Phase 4 split into 4a+4b). Spec: `WIP/post-campaign-validation.md` (v0.3). *Spec complete, implementation not started. Will be implemented in Python post-conversion.*
3. **Local model integration** — Replace cloud API with local LM Studio on Mac Studio. Reference: `archive/local-llm-pipeline/`. *Not started.*
4. **Adaptive routing / parallelism** — Only if data from 1–3 justifies complexity. *Deprioritized.*

### Historical build estimator (designed, not yet built)

Correlates t-shirt sizes with actual metrics from `logs/build-summary-*.json`. Writes to `logs/estimation-model.json`. Self-correcting after each `write_build_summary()`. Build after stakd campaign provides real data.

### Other active items

- **Learnings system — IMPLEMENTED (2026-03-01)**: 63 graph-compliant entries (L-0042–L-0104), ~47 old-format across other files. **core.md created** — 16 curated entries, fresh onboard path works. Remaining: old-format conversion (Prompts 4/5), index.md stale.
- **Knowledge graph for workflow continuity (2026-02-28)**: Personal workflow tool for cross-session context. *Design phase — no implementation started.*
- **`HOW-I-WORK-WITH-GENERATIVE-AI.md` (2026-03-01)**: Repo-agnostic methodology document at repo root. Checkpoint step 5 auto-captures methodology signals to accumulation section; Brian curates into prose. Bootstrapped with 8 captures. Context window onboarding cost is an open question.
- **State format migration (2026-03-01)**: Post-Python-conversion project. Current file-based state preserved during bash→Python conversion. Future consideration: SQLite or structured JSON for queryable state ("show me all features that failed with error X across all rounds"). Not started, intentionally deferred — one variable at a time.
- **Learnings graph-schema conversion (2026-03-01)**: 63 graph-compliant entries (L-0042–L-0104) in agent-operations.md. ~47 old-format entries remain across design+general+performance+security files. Two agent prompts ready (Prompts 4 & 5) for converting those. Studio candidate.
- **Retiring-chat handoff protocol — ✅ DONE (2026-03-01)**: `.specs/HANDOFF-PROTOCOL.md` + ONBOARDING.md integration complete. `.handoff.md` active for next fresh session.
- **Response scope discipline (2026-03-01)**: Two truncations + one approval gate violation in one session (L-0098, L-0103, L-0104). Rules: count work items BEFORE first tool call, >3 items = split. "Do what you need to do" ≠ "yes to push." Confidence is not approval.
- **CLAUDE.md audit (2026-03-01)**: Root CLAUDE.md 468 lines, ~80% stale SDD scaffold (L-0087, L-0094). stakd/CLAUDE.md has battle-tested Next.js 15 patterns not in root. Tasks: (1) strip root to ~100-150 lines of operational content, (2) evaluate whether stakd-specific patterns should be in learnings or stay project-local, (3) stakd-v2/v3 versions are near-identical to stakd — no action needed. Brian confirmed root placement correct; "wrong place" = orphaned stakd versions.
- **core.md — ✅ CREATED (2026-03-01)**: 16 curated entries from L-0042–L-0103, 52 lines. Fresh onboard path now works as designed. Next curation: when total entries exceed ~80 or after old-format conversion adds ~47 entries.
- **Memory slot optimization (2026-03-01)**: 15/30 slots, ~1,500 words always-injected. Slots #10-14 situational (~300 tokens, ~30% hit rate). When approaching 20 slots, migrate situational rules to repo and trust onboarding. Not urgent now but monitor. (L-0095)
- **ONBOARDING.md overhaul for efficient context (2026-03-01)**: Checkpoint expansion DONE (Prompt 6 merged, 788f8a8). Remaining: broader audit — does a fresh session get proper bootstrap without bloat? Evaluate after graph conversion lands.
- **Port to Mac Studio for Phase 1 (2026-03-01)**: Clone repo, install Claude Desktop. Five parallel agents will choke MacBook Air. Current doc/prompt work fine on Air. Studio for Phase 1 onward.
