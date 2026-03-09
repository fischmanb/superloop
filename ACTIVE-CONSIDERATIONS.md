# Active Considerations

> What's next and what's in-flight. Priority stack is the execution plan; everything below it is context a fresh chat should pick up.
>
> Split from ONBOARDING.md (2026-03-01) to keep onboarding focused on orientation.

---

### Priority stack (updated 2026-03-09 — post isolation enforcement session)

Ordered by efficiency gain per complexity added:

1. **SitDeck build campaign — 36/49 features built, merged to main.**
   - Campaign ran Mar 7-8. App compiles and boots. 13 features remain pending.
   - Campaign branch merged to main in compstak-sitdeck, orphan branches deleted.
   - Project moved to `~/compstak-sitdeck/` (separate from auto-sdd).
   - $201 API cost across 239 agent invocations.
   - **Not yet done**: browser-level widget verification, resume build for remaining 13 features, ~90 untracked log/eval files in auto-sdd need gitignore decisions.
   - Full assessment in Agents.md ("SitDeck Build Campaign Assessment" round).
   - **Run command**: `caffeinate -diw $$ & cd ~/auto-sdd/py && AUTO_APPROVE=true PROJECT_DIR=~/compstak-sitdeck LOGS_DIR=~/auto-sdd/logs/compstak-sitdeck .venv/bin/python -m auto_sdd.scripts.build_loop`
2. **CIS Rounds 5-6 — need campaign data from #1.**
   - Campaign data exists (feature-vectors.jsonl in ~/compstak-sitdeck/.sdd-state/). May be unblocked.
   - Full plan: `WIP/campaign-intelligence-system.md`
3. **Auto-QA validation — run against SitDeck for scale proof.**
   - Plan: `WIP/auto-qa-cre-validation.md`
4. **Seed data & distribution** — Blocked on stable vector schema.
5. **Extract errors.py/signals.py/state.py from reliability.py** — Low urgency.
6. **Local model integration** — Not started.
7. **Adaptive routing** — Deprioritized.

### Repo hygiene — partially done

- ~90 untracked files in auto-sdd (`logs/compstak-sitdeck/evals/`, `logs/compstak-sitdeck/build-*.log`, `logs/validation/val-*`). Need gitignore decisions (step 4 of triage plan `WIP/plans/3_8_2026.md`).
- Dozens of orphan branches in auto-sdd (`auto/chained-*`, `claude/*`) — step 6.
- Test suite not yet run post-campaign — step 7.

### Knowledge graph build intelligence — DESIGNED, NOT STARTED

- **WIP:** `WIP/knowledge-graph-build-intelligence.md` (207 lines)

### Other active items

- **auto-sdd vs superloop naming asymmetry**: Local dir is `~/auto-sdd`, GitHub repo is `fischmanb/superloop`. No functional impact, doc-layer confusion only. Deferred to later session.
- **HOW-I-WORK corpus curation**: 84+ entries. 4+ clusters ready for formalization.
- **Learnings graph-schema conversion**: Some old-format entries may remain in `.specs/learnings/`.
- **Memory slot optimization**: 15/30 slots. Not urgent. (L-00095)

### Completed (archive — remove when no longer useful for context)

- **Project isolation enforcement (2026-03-09)**: Three-layer protection: prompt FILESYSTEM BOUNDARY directive, chmod write-protection of auto-sdd source/docs during agent execution (dirs + root files), post-agent `_check_repo_contamination()` audit on every `run_claude()` return. Contract: `WIP/project-isolation-contract.md`. 92 tests.
- **Project directory segregation (2026-03-09)**: compstak-sitdeck moved from `~/auto-sdd/compstak-sitdeck/` to `~/compstak-sitdeck/`. All path references updated. Explicit `LOGS_DIR` preserves telemetry pipeline.
- **SitDeck campaign branch merged + cleanup (2026-03-09)**: 60 commits fast-forwarded to main. 46 orphan branches deleted.
- **Campaign artifacts committed (2026-03-09)**: Stashed campaign data (cost log, eval sidecar, learnings, estimates, test file) committed to clean working tree.
- **SitDeck roadmap + feature stubs (2026-03-07)**: 44 widgets across 3 phases.
- **L-00012 demoted from core (2026-03-08)**: Core count back to 17.
- **Repo rename + unfork (2026-03-06)**: Renamed to `superloop` on GitHub.
- **Bash→Python conversion**: ALL PHASES COMPLETE. 970+ tests.
- **auto-QA pipeline**: ALL PHASES COMPLETE. Run 2: 29/32 pass, 3/3 fixes.
- **Learnings system**: L-00001–L-00220+, M-00001–M-00094+, 17 curated in core.md.
- **Campaign intelligence system design**: `WIP/campaign-intelligence-system.md`.
