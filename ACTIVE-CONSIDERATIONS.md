# Active Considerations

> What's next and what's in-flight. Priority stack is the execution plan; everything below it is context a fresh chat should pick up.
>
> Split from ONBOARDING.md (2026-03-01) to keep onboarding focused on orientation.

---

### Priority stack (updated 2026-03-08 — post SitDeck campaign assessment)

Ordered by efficiency gain per complexity added:

1. **SitDeck build campaign — 36/49 features built, assessment in progress.**
   - Campaign ran Mar 7-8. 9 failed build attempts on Mar 7 (PATH issue, config parser bugs, signal parsing), followed by successful overnight run.
   - App compiles (`next build` clean) and boots (`next dev` returns 200).
   - Currently on branch `auto/chained-20260308-193835` in ~/compstak-sitdeck, 60 commits ahead of main.
   - 13 features remain pending. $201 API cost across 239 agent invocations.
   - **Not yet done**: merge campaign branch to main, browser-level widget verification, auto-sdd repo state cleanup (many uncommitted files), learnings capture for campaign failure patterns.
   - Full assessment in Agents.md ("SitDeck Build Campaign Assessment" round, 2026-03-08).
   - **Run command**: `caffeinate -diw $$ & cd ~/auto-sdd/py && AUTO_APPROVE=true PROJECT_DIR=~/compstak-sitdeck LOGS_DIR=~/auto-sdd/logs/compstak-sitdeck .venv/bin/python -m auto_sdd.scripts.build_loop`
2. **CIS Rounds 1-4 COMPLETE. Rounds 5-6 need campaign data from #1.**
   - Campaign data from SitDeck now exists (feature-vectors.jsonl in ~/compstak-sitdeck/.sdd-state/). Rounds 5-6 may be unblocked pending assessment of data quality.
   - Full plan: `WIP/campaign-intelligence-system.md`
3. **Auto-QA validation — PROVEN. Second run 3/3 fixes succeeded.**
   - Run 2 (val-20260306-004027): 36 min, $6.95. 29/32 pass, 3 fail, 0 blocked. 3/3 fix agents succeeded.
   - Next: run against SitDeck for scale proof.
   - Plan: `WIP/auto-qa-cre-validation.md`
4. **Seed data & distribution strategy — V1 plan: ship curated seed packs.**
   - Full plan: `WIP/seed-data-distribution.md`
   - **Blocked on**: stable vector schema from CIS Round 1.
5. **Extract `errors.py`/`signals.py`/`state.py` from `reliability.py` monolith** — Low urgency.
6. **Local model integration** — Not started.
7. **Adaptive routing / parallelism** — Deprioritized.

### Knowledge graph build intelligence — DESIGNED, NOT STARTED

- **WIP:** `WIP/knowledge-graph-build-intelligence.md` (207 lines)
- Write path first (get data accumulating), read path second (preprocessor with empty DB is no-op).

### Other active items

- **HOW-I-WORK corpus curation**: 84+ entries (M-00001–M-00084+). 4+ coherent clusters ready for formalization.
- **Learnings graph-schema conversion**: Schema standardization complete. Some old-format entries may remain in `.specs/learnings/` files.
- **Memory slot optimization**: 15/30 slots, ~1,500 words always-injected. Not urgent but monitor. (L-00095)
- **Scope discipline**: Session correction — chat responses exceeded requested scope. Read instructions literally, stop at natural boundaries, don't extrapolate. (Captured 2026-03-08.)

### Completed (archive — remove when no longer useful for context)

- **SitDeck roadmap + feature stubs generated (2026-03-07)**: 44 widgets across 3 phases. Roadmap committed, feature stubs in `.specs/features/`.
- **L-00012 demoted from core (2026-03-08)**: Next.js-specific transitive import learning removed from core.md. Core count back to 17.
- **Integration test of Python build pipeline (2026-03-08)**: Effectively completed via SitDeck campaign — Python build loop ran 239 agent invocations end-to-end.
- **stakd 28-feature campaign**: v2 COMPLETE (28/28 Sonnet 4.6), v3 STALLED at 11/28 Haiku 4.5. Data in `campaign-results/`.
- **Repo rename + unfork (2026-03-06)**: Renamed to `superloop` on GitHub. Local path `~/auto-sdd` unchanged.
- **IP scrub (2026-03-07)**: `Brians-Notes/IP-UTILITY-SIGNIFICANCE.md` removed from all git history.
- **Bash→Python conversion**: ALL PHASES COMPLETE (0-6). 970 tests, ~17s.
- **auto-QA pipeline**: ALL PHASES COMPLETE (0-5). Run 2: 29/32 pass, 3/3 fix agents succeeded.
- **Learnings system**: IMPLEMENTED. L-00001–L-00217+, M-00001–M-00093+, 17 curated in core.md.
- **Campaign intelligence system design (2026-03-04)**: Full plan committed. `WIP/campaign-intelligence-system.md`.
