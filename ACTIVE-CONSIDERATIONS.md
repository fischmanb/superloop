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
2. **Bash→Python conversion (2026-03-01)** — ~3,700 lines of bash orchestration across 6 files hit a ceiling for extensibility. RICE score 4.3, sequentially linked to auto-QA (implementing 7-phase validation in bash would be painful). Proposed sequence: stakd-v2 fix → convert → auto-QA in Python. SWOT/RICE analysis in DECISIONS.md.
   - **Conversion plan (2026-03-01)**:
     - Phase 0: Write Python conventions doc + investigate build-loop-local internal structure (chat)
     - Phase 1: Parallel lib conversion — reliability.py, eval.py, codebase_summary.py, validation.py (4 agents, zero cross-deps)
     - Phase 2: eval_sidecar.py (depends on eval.py, sequential after Phase 1)
     - Phase 3: build-loop-local decomposition analysis (chat — identify sub-units)
     - Phase 4: build-loop-local conversion (possibly 2-3 agents on sub-units, sequential integration)
     - Phase 5: overnight-autonomous conversion (sequential after Phase 4)
     - Phase 6: Small utilities bundle — claude-wrapper, generate-mapping, nightly-review (1 agent)
     - Phase 7: Integration testing — end-to-end dry run
   - **Key decisions**: Libs-first (dependency graph), keep file-based state (one variable at a time), conventions doc before parallel work, only launchd scripts stay bash. All decisions logged in DECISIONS.md.
   - **State format migration**: Deferred to post-conversion. Current file-based state preserved. Structured migration (SQLite, typed JSON) is a separate project. Logged as active consideration below.
3. **auto-QA (post-campaign validation pipeline)** — Multi-agent pipeline: boot app, Playwright browse, generate ACs from specs, test, catalog failures, RCA, fix through build gates. Seven phases (0-5, Phase 4 split into 4a+4b). Spec: `WIP/post-campaign-validation.md` (v0.3). *Spec complete, implementation not started. Blocked on language decision.*
3. **Local model integration** — Replace cloud API with local LM Studio on Mac Studio. Reference: `archive/local-llm-pipeline/`. *Not started.*
4. **Adaptive routing / parallelism** — Only if data from 1–3 justifies complexity. *Deprioritized.*

### Historical build estimator (designed, not yet built)

Correlates t-shirt sizes with actual metrics from `logs/build-summary-*.json`. Writes to `logs/estimation-model.json`. Self-correcting after each `write_build_summary()`. Build after stakd campaign provides real data.

### Other active items

- **Learnings system — IMPLEMENTED (2026-03-01)**: Complete. 38 entries, 8 in core.md. Remaining: back-references not fully bidirectional.
- **Knowledge graph for workflow continuity (2026-02-28)**: Personal workflow tool for cross-session context. *Design phase — no implementation started.*
- **`HOW-I-WORK-WITH-GENERATIVE-AI.md` (2026-03-01)**: Repo-agnostic methodology document at repo root. Checkpoint step 5 auto-captures methodology signals to accumulation section; Brian curates into prose. Bootstrapped with 8 captures. Context window onboarding cost is an open question.
- **State format migration (2026-03-01)**: Post-Python-conversion project. Current file-based state preserved during bash→Python conversion. Future consideration: SQLite or structured JSON for queryable state ("show me all features that failed with error X across all rounds"). Not started, intentionally deferred — one variable at a time.
