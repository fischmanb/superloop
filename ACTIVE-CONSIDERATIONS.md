# Active Considerations

> What's next and what's in-flight. Priority stack is the execution plan; everything below it is context a fresh chat should pick up.
>
> Split from ONBOARDING.md (2026-03-01) to keep onboarding focused on orientation.

---

### Priority stack (updated 2026-03-04, late evening)

Ordered by efficiency gain per complexity added:

1. **Auto-QA validation against CRE lease tracker — zero production runs to date.**
   - 96 tests pass but pipeline has never run against a real project. Must validate before building intelligence on top.
   - Target project: `~/cre-lease-tracker` (3 features built, small/controlled, exercises multi-feature interactions)
   - **Next action: investigation** — verify CRE builds/boots, check auto-QA entry point interface (`main()` in `post_campaign_validation.py`), confirm Playwright availability, determine if auto-QA boots the app or expects it running
   - Then: run full auto-QA pipeline, document findings, fix whatever breaks
   - Produces first real runtime signal data for CIS
2. **Campaign intelligence system — design complete, implementation blocked on #1.**
   - Full plan: `WIP/campaign-intelligence-system.md` (pressure-tested, revised)
   - CIS value depends on auto-QA producing validated runtime signals. Build-only CIS is just a fancier eval sidecar.
   - 3 Phase 1 rounds: (1) vector store + wire writers, (2) analysis framework + intra-campaign injection, (3) convention eval signals
   - Phase 2 (after real campaign): auto-QA feature attribution, cross-campaign ML model
   - Phase 3 (after 3+ campaigns): meta-learner
3. **Investigate Playwright validation granularity — may be critically simplistic.**
   - How does auto-QA's Playwright validation capture UI interactions? Screenshots? What timing/granularity?
   - Animations, transitions, dropdowns, multi-step interactions — how is each visual state verified?
   - If it's just "take screenshot, check text exists," that misses: dropdown renders correctly, options are all present and work, animations complete, hover states, loading states, error states.
   - Could require burst screenshots (frame-like capture), DOM state assertions alongside visual checks, or Playwright's built-in waitForSelector/toBeVisible patterns.
   - Investigation folded into #1's agent prompt. Findings determine whether auto-QA's Playwright approach needs redesign before running against CRE.
4. **Seed data & distribution strategy — V1 plan: ship curated seed packs.**
   - Full plan: `WIP/seed-data-distribution.md`
   - New users cold-start with zero campaign data; seed packs provide immediate value from Brian's campaigns
   - V1: `seed-data/` directory with curated vectors, patterns, model weights. V2: tiered community packs. V3: global sync (if adoption warrants).
   - **Blocked on**: stable vector schema from CIS Round 1. Schema is the interface contract for all distribution strategies.
5. **Integration test of Python build pipeline against real project** — may combine with #1 (run campaign then auto-QA in sequence).
4. **Extract `errors.py`/`signals.py`/`state.py` from `reliability.py` monolith** — Conventions specify these modules but Phase 1 inlined them. Low urgency.
5. **Local model integration** — Replace cloud API with local LM Studio on Mac Studio. Reference: `archive/local-llm-pipeline/`. *Not started.*
6. **Adaptive routing / parallelism** — Only if data from campaigns justifies complexity. *Deprioritized.*

### Historical build estimator (designed, not yet built)

Correlates t-shirt sizes with actual metrics from `logs/build-summary-*.json`. Writes to `logs/estimation-model.json`. Self-correcting after each `write_build_summary()`. Build after a real Python campaign provides data.

### Other active items

- **HOW-I-WORK corpus curation**: 84+ entries (M-00001–M-00084+). 4+ coherent clusters ready for formalization. Action: curate entries into named sections, promote mature patterns to learnings.
- **Core learnings demotion review**: core.md at 17 entries (threshold 15). L-00012 (client→server import chain) is stakd/Next.js-specific — candidate for demotion. Review after next campaign.
- **Learnings graph-schema conversion**: Schema standardization complete. Some old-format entries may remain in `.specs/learnings/` files. Two agent prompts ready (Prompts 4 & 5) for converting those.
- **Memory slot optimization**: 15/30 slots, ~1,500 words always-injected. Not urgent but monitor. (L-00095)

### Completed (archive — remove when no longer useful for context)

- **stakd 28-feature campaign**: v2 COMPLETE (28/28 Sonnet 4.6, post-build import error known), v3 STALLED at 11/28 Haiku 4.5. Key finding: token speed ≠ build speed (infra bottlenecks dominate). Data in `campaign-results/`.
- **Bash→Python conversion**: ALL PHASES COMPLETE (0-6). Post-conversion audit complete (30 findings, 16 resolved, 7 INFO-only). 740 tests, 15.86s.
- **auto-QA pipeline**: ALL PHASES COMPLETE (0-5). 96 tests. Next: live validation run against real project.
- **Learnings system**: IMPLEMENTED. 191+ entries (L-00001–L-00191, M-00001–M-00087+), 17 curated in core.md.
- **Test suite reliability (2026-03-04)**: Orphan cleanup, hang fixes (generate_codebase_summary mock), build_loop 162s→0.1s. 740 tests, 15.86s, zero hangs.
- **L-00178 enforcement (2026-03-04)**: 300-line prompt rule across 5 surfaces (tests, runtime, CLAUDE.md, core.md, process-rules).
- **Next.js detection fix (2026-03-04)**: `detect_build_check()` priority ordering + package.json validation.
- **Hard constraints fixes (2026-03-03)**: run_claude() cwd, retry model chain, AGENT_TIMEOUT configurable.
- **Project-agnostic audit (2026-03-03)**: 3 remediation rounds (47-49). Agent-based summary, multilang eval, infra portability.
- **Campaign intelligence system design (2026-03-04)**: Full plan pressure-tested and committed. Sectioned vector store, pluggable analysis rules (feature-flagged), mechanical detection, project-configurable quality dimensions, auto-QA integration path. `WIP/campaign-intelligence-system.md`.
