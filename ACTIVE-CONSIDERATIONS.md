# Active Considerations

> What's next and what's in-flight. Priority stack is the execution plan; everything below it is context a fresh chat should pick up.
>
> Split from ONBOARDING.md (2026-03-01) to keep onboarding focused on orientation.

---

### Priority stack (updated 2026-03-09 — post session 2)

Ordered by efficiency gain per complexity added:

1. **SitDeck build campaign — 37+/49 features built, pipeline validated, resume for remaining features.**
   - Feature #19 (Rent Potential) built successfully 2026-03-09 with two-stage retry (fix-in-place on attempt 2). 599 tests passing. Drift auto-fixed.
   - Build still running — additional features may have completed.
   - Project at `~/compstak-sitdeck/` with `project.yaml` committed (npx fix applied).
   - Two-stage retry system live-validated (8533639). Codebase summary timeout fixed (63edac4).
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

### Knowledge graph build intelligence — DESIGNED, NOT STARTED

- **WIP:** `WIP/knowledge-graph-build-intelligence.md` (207 lines)

### Other active items

- **Build launches are Brian-only**: Brian runs all builds in Terminal himself. Chat sessions provide run commands and pre-flight context but never launch build_loop.

- **auto-sdd vs superloop naming asymmetry**: Local dir is `~/auto-sdd`, GitHub repo is `fischmanb/superloop`. No functional impact, doc-layer confusion only. Deferred.
- **ONBOARDING.md reconciliation needed**: File is stale — describes pre-campaign, pre-isolation state. Needs full refresh to match current reality (project segregated, isolation enforcement, 1026 tests, L-00226/M-00095).
- **HOW-I-WORK corpus curation**: 84+ entries. 4+ clusters ready for formalization.
- **Memory slot optimization**: 15/30 slots. Not urgent. (L-00095)


- **docs/ directory restructure (2026-03-09)**: Single organized entry point at docs/README.md — system/, operations/, guides/, knowledge/, plans/, history/. 5 new files, 29 total. de0d5d7.

### Completed (archive — remove when no longer useful for context)

- **Two-stage retry system (2026-03-09)**: Fix-in-place (attempt 1) before informed fresh retry (attempt 2+). Live-validated on Feature #19. 8533639.
- **Codebase summary timeout fix (2026-03-09)**: Excluded SDD metadata from file tree, timeout bumped to 300s (SUMMARY_TIMEOUT env var). 63edac4.

- **Integration pipeline test (2026-03-09)**: 8 tests covering full build loop with isolation layers — single-feature build, prompt boundary, chmod protection/restore, root file protection, contamination check clean/dirty, config loading, log derivation. 1026 total tests.
- **Credit exhaustion test fix (2026-03-09)**: Two tests broken by prior refactor (31ef249) — mocks returned output text instead of raising CreditExhaustionError. Fixed.
- **Repo triage complete (2026-03-09)**: logs/ gitignored (23 tracked files untracked), 45 orphan branches deleted in auto-sdd, working tree clean.
- **Project isolation enforcement (2026-03-09)**: Three-layer protection. Contract: `WIP/project-isolation-contract.md`. 92 build_loop tests.
- **Project directory segregation (2026-03-09)**: compstak-sitdeck at `~/compstak-sitdeck/`. Nested dir issue found and flattened. project.yaml recovered and committed to project git.
- **SitDeck campaign (2026-03-08)**: 36/49 features built, merged to main, orphan branches deleted. $201 cost.
- **Learnings system**: L-00001–L-00226, M-00001–M-00095, 17 curated in core.md.
