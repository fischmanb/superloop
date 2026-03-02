# Handoff — 2026-03-02 Late Evening

## Where we are

Main branch at `307c21f` (plus uncommitted: this handoff, L-00152, M-00077, ACTIVE-CONSIDERATIONS updates).

### Just completed (this session)

- **Dispatch 3**: Added `query_estimate_actuals()` + `estimate_general_tokens()` to `lib/general-estimates.sh`. Calibration loop now closed (write + read sides both functional). Committed `d1a1a72`.
- **Core learnings inline**: Agent compressed 13 core learnings into CLAUDE.md (~256 words). Merged from `claude/inline-core-learnings-XiCTf` at `f7be98c`.
- **Duplicate M-00076 fix**: Checkpoint agent had written it twice. Fixed at `80440b7`.
- **extract-learnings skill**: Created `.claude/skills/extract-learnings/SKILL.md` — works in Code tab. For Chat tab, just say "extract learnings" and I'll run the same protocol via memory + Desktop Commander.
- **L-00152**: `.claude/commands/` and `.claude/skills/` are Code-only. Chat workflows use memory + Desktop Commander.

### Dispatch queue (empty)

All dispatches (1–4) and the core inline agent are complete. No pending dispatch prompts.

### What's next (from ACTIVE-CONSIDERATIONS priority stack)

1. **Phase 3**: Build-loop-local decomposition analysis for bash→Python Phase 4
2. **stakd-v2 build fix**: Client component import chain bug (NewsCategoryFilter.tsx → postgres)
3. **CLAUDE.md audit**: Strip root CLAUDE.md to ~100-150 lines of operational content
4. **auto-QA pipeline**: Spec complete, implementation not started

### Key files for orientation

- `ACTIVE-CONSIDERATIONS.md` — full priority stack + in-flight items
- `CLAUDE.md` — now includes Core Learnings block + Scope Discipline section
- `learnings/core.md` — 13 core entries (source of truth for the CLAUDE.md compressed block)
- `lib/general-estimates.sh` — 4 functions: get_session_actual_tokens, append_general_estimate, query_estimate_actuals, estimate_general_tokens
- `.onboarding-state` — checkpoint state file

### Chat-tab workflows

These work via memory + Desktop Commander (not slash commands):
- **"extract learnings"** → scan session, propose L/M entries in graph schema, deduplicate, write after approval
- **"checkpoint"** → flush captures, scan for learnings, update .onboarding-state, commit+push
- **"next dispatch"** → check queue, write or execute next agent prompt

### Token calibration state

2 data points in `general-estimates.jsonl`. Not yet calibration-ready (needs 5+). Current avg: 8,840 active tokens. Estimation error: +44.2% (overestimates by ~44%).
