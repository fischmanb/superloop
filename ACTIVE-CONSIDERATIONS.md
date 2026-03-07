# Active Considerations

> What's next and what's in-flight. Priority stack is the execution plan; everything below it is context a fresh chat should pick up.
>
> Split from ONBOARDING.md (2026-03-01) to keep onboarding focused on orientation.

---

### Priority stack (updated 2026-03-07)

Ordered by efficiency gain per complexity added:

1. **SitDeck build campaign — BLOCKED on roadmap generation prompt.**
   - **Purpose**: Head-to-head comparison — same `vision.md` input, Adrian's simpler system (74 features, no verification loops, no learning layer) vs. Superloop (full CIS, auto-QA, verified output). Demonstrates Superloop capability AND generates CIS training data for Rounds 5-6.
   - Vision file exists in TWO locations: `~/auto-sdd/vision.md` (committed at fc5f36d, repo root) AND `~/compstak-sitdeck/.specs/vision.md` (copy). Either is usable by agent.
   - `~/compstak-sitdeck/.specs/` directory exists, waiting for roadmap + feature stubs.
   - **Blocker**: Agent prompts degraded in quality last session. Multiple failed attempts. Need proper prompt following PROMPT-ENGINEERING-GUIDE.md to decompose vision into ~70-feature roadmap.
   - Roadmap format: `| # | Feature | Source | Jira | Complexity | Dependencies | Status |` (parsed by `reliability.py:_parse_roadmap_rows`)
   - **Sequence after roadmap**: (1) Initialize Next.js project at `~/compstak-sitdeck/` — project dir does NOT exist yet, build command will fail without this step. (2) Copy CompStak CSV data to `~/compstak-sitdeck/_shared-csv-data/`. (3) Run `cd ~/auto-sdd/py && PROJECT_DIR=~/compstak-sitdeck .venv/bin/python -m auto_sdd.scripts.build_loop`
   - Record of breakthrough context: `Brians-Notes/itsalive.md` and `Brians-Notes/records/itsalive.md` (two copies, local only)
2. **CIS Rounds 1-4 COMPLETE. Rounds 5-6 need campaign data from #1.**
   - **Round 1a** ✅: Vector store + JSONL backend + schema (32 tests)
   - **Round 1b** ✅: Wire writers into build_loop, eval_sidecar, prompt_builder, overnight_autonomous (26 tests)
   - **Round 2** ✅: Pattern analysis — 4 rules (co-occurrence, temporal decay, retry effectiveness, shared module risk). Feature-flagged `ENABLE_PATTERN_ANALYSIS`. Risk context injection. (41 tests)
   - **Round 3** ✅: Convention checks — 4 mechanical static analysis checks (import boundaries, type safety, code duplication, error handling). Project-configurable. 2 new pattern rules. (46 tests)
   - **Round 4** ✅: Runtime attribution — `backfill_runtime_signals()` joins auto-QA failures to feature vectors via file path intersection. `files_touched` in build_signals. 3 new runtime pattern rules. 9 total rules. (20 tests)
   - **Token measurement fix** ✅: Project-scoped session discovery, compaction-safe summing, auto-logging from `run_claude()`, `estimate_from_history()`, `source_breakdown`
   - **Round 5** (blocked on campaign data): Cross-campaign ML model (scikit-learn classifier)
   - **Round 6** (needs 3+ campaigns): Meta-learner (injection effectiveness, adaptive weighting)
   - Full plan: `WIP/campaign-intelligence-system.md`
3. **Auto-QA validation — PROVEN. Second run 3/3 fixes succeeded.**
   - Run 2 (val-20260306-004027): 36 min, $6.95. 29/32 pass, 3 fail, 0 blocked. 3/3 fix agents succeeded.
   - Verified live via Chrome browser. All fixes committed to CRE.
   - Plan: `WIP/auto-qa-cre-validation.md`
4. **Seed data & distribution strategy — V1 plan: ship curated seed packs.**
   - Full plan: `WIP/seed-data-distribution.md`
   - New users cold-start with zero campaign data; seed packs provide immediate value from Brian's campaigns
   - V1: `seed-data/` directory with curated vectors, patterns, model weights. V2: tiered community packs. V3: global sync (if adoption warrants).
   - **Blocked on**: stable vector schema from CIS Round 1. Schema is the interface contract for all distribution strategies.
5. **Integration test of Python build pipeline against real project** — may combine with #1 (run campaign then auto-QA in sequence).
6. **Extract `errors.py`/`signals.py`/`state.py` from `reliability.py` monolith** — Conventions specify these modules but Phase 1 inlined them. Low urgency.
7. **Local model integration** — Replace cloud API with local LM Studio on Mac Studio. Reference: `archive/local-llm-pipeline/`. *Not started.*
8. **Adaptive routing / parallelism** — Only if data from campaigns justifies complexity. *Deprioritized.*

### Other active items

- **HOW-I-WORK corpus curation**: 84+ entries (M-00001–M-00084+). 4+ coherent clusters ready for formalization. Action: curate entries into named sections, promote mature patterns to learnings.
- **Core learnings demotion review**: core.md at 17 entries (threshold 15). L-00012 (client→server import chain) is stakd/Next.js-specific — candidate for demotion. Review after next campaign.
- **Learnings graph-schema conversion**: Schema standardization complete. Some old-format entries may remain in `.specs/learnings/` files. Two agent prompts ready (Prompts 4 & 5) for converting those.
- **Memory slot optimization**: 15/30 slots, ~1,500 words always-injected. Not urgent but monitor. (L-00095)

### Completed (archive — remove when no longer useful for context)

- **stakd 28-feature campaign**: v2 COMPLETE (28/28 Sonnet 4.6, post-build import error known), v3 STALLED at 11/28 Haiku 4.5. Key finding: token speed ≠ build speed (infra bottlenecks dominate). Data in `campaign-results/`.
- **Repo rename + unfork (2026-03-06)**: Renamed to `superloop` on GitHub, unforked from Adrian's repo. Local path `~/auto-sdd` unchanged. Remote: `https://github.com/fischmanb/superloop.git`.
- **IP scrub (2026-03-07)**: `Brians-Notes/IP-UTILITY-SIGNIFICANCE.md` removed from all git history via filter-repo. Force-pushed to all branches.
- **Bash→Python conversion**: ALL PHASES COMPLETE (0-6). Post-conversion audit complete (30 findings, 16 resolved, 7 INFO-only). 970 tests, ~17s.
- **auto-QA pipeline**: ALL PHASES COMPLETE (0-5). Run 2: 29/32 pass, 3/3 fix agents succeeded, verified live. Next: SitDeck campaign for scale proof.
- **Learnings system**: IMPLEMENTED. L-00001–L-00198, M-00001–M-00090+, 17 curated in core.md.
- **Test suite reliability (2026-03-04)**: Orphan cleanup, hang fixes (generate_codebase_summary mock), build_loop 162s→0.1s. 740 tests, 15.86s, zero hangs.
- **L-00178 enforcement (2026-03-04)**: 300-line prompt rule across 5 surfaces (tests, runtime, CLAUDE.md, core.md, process-rules).
- **Next.js detection fix (2026-03-04)**: `detect_build_check()` priority ordering + package.json validation.
- **Hard constraints fixes (2026-03-03)**: run_claude() cwd, retry model chain, AGENT_TIMEOUT configurable.
- **Project-agnostic audit (2026-03-03)**: 3 remediation rounds (47-49). Agent-based summary, multilang eval, infra portability.
- **Campaign intelligence system design (2026-03-04)**: Full plan pressure-tested and committed. Sectioned vector store, pluggable analysis rules (feature-flagged), mechanical detection, project-configurable quality dimensions, auto-QA integration path. `WIP/campaign-intelligence-system.md`.
