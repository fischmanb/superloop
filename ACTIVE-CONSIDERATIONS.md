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

- **Learnings system — IMPLEMENTED (2026-03-01)**: Complete. 38 entries, 8 in core.md. Remaining: back-references not fully bidirectional.
- **Knowledge graph for workflow continuity (2026-02-28)**: Personal workflow tool for cross-session context. *Design phase — no implementation started.*
- **`HOW-I-WORK-WITH-GENERATIVE-AI.md` (2026-03-01)**: Repo-agnostic methodology document at repo root. Checkpoint step 5 auto-captures methodology signals to accumulation section; Brian curates into prose. Bootstrapped with 8 captures. Context window onboarding cost is an open question.
- **State format migration (2026-03-01)**: Post-Python-conversion project. Current file-based state preserved during bash→Python conversion. Future consideration: SQLite or structured JSON for queryable state ("show me all features that failed with error X across all rounds"). Not started, intentionally deferred — one variable at a time.
- **Learnings graph-schema conversion (2026-03-01)**: ~112 entries across learnings files, only 3 are graph-compliant (L-0045/46/47). Need agent prompts to convert: (1) agent-operations.md ~27 old entries, (2) design+general+performance+security ~57 entries. Assign sequential L-IDs, add Status/Confidence/Tags/Related fields with real edge types. Two agent prompts planned. Blocks: Prompt 3 (L-0042/43/44) runs first.
- **ONBOARDING.md checkpoint expansion (2026-03-01)**: Prompt 1 branch lost (not on remote or local). Task: expand checkpoint section so protocol scope is visible inline without reading checkpoint.md. Needs re-run or manual edit.
- **Port to Mac Studio for Phase 1 (2026-03-01)**: Clone repo, install Claude Desktop. Five parallel agents will choke MacBook Air. Current doc/prompt work fine on Air. Studio for Phase 1 onward.
