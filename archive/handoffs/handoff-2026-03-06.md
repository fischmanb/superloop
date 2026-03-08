# Session Handoff — 2026-03-06 (Final)

## Repo State
- **Repo**: `github.com/fischmanb/superloop` (renamed from auto-sdd, unforked)
- **Local path**: `~/auto-sdd` (unchanged)
- **Main**: `a1381a6` (checkpoint with CIS Rounds 1-4, learnings, decisions)
- **Tests**: 970 passing, ~17s
- **Remote**: `origin` → `https://github.com/fischmanb/superloop.git`

## What Was Accomplished This Session

### Auto-QA Second Run — FULL SUCCESS
- Run 2 (val-20260306-004027): 36 min, $6.95
- 29/32 pass, 3 fail, 0 blocked. **3/3 fix agents succeeded.**
- All fixes committed to CRE, verified live via Chrome browser
- Fixed `detect_dev_command` early return bug (commit 469ae56)

### CIS Rounds 1-4 Complete
- **1a**: Vector store + schema (32 tests)
- **1b**: Wire writers into pipeline (26 tests)
- **2**: Pattern analysis + intra-campaign injection, 4 rules, feature-flagged (41 tests)
- **3**: Mechanical convention checks, 4 static analysis checks, 2 new pattern rules (46 tests)
- **4**: Runtime attribution via file path join, 3 new runtime pattern rules (20 tests)
- **Total pattern rules**: 9 (Round 2: 4, Round 3: 2, Round 4: 3)

### Token Measurement Fix
- Code fix (ceb99cf): project-scoped session discovery, compaction-safe summing, absolute estimates path
- Wrapper fix (1296160): run_claude() auto-logs tokens, estimate_from_history(), source_breakdown
- Remaining: Desktop app Code tab agents don't write session JSONL — wrapper fix captures pipeline agents only

### Repo Rename + Unfork
- Unforked from Adrian's repo on GitHub
- Renamed to `superloop`
- Local path unchanged: `~/auto-sdd`
- Remote updated and working

### Proof Materials Created
- Deck: `Brians-Notes/superloop-deck-2026-03-05.pdf` (10 slides, no core IP)
- Medium draft: `/mnt/user-data/outputs/medium-draft.md` (not in repo, holding for scale proof)
- GIF: `auto-sdd-cre-proof.gif` in Downloads (browser walkthrough)

### IP Assessment
- REMOVED from repo at commit 79d88be (was accidentally pushed)
- Still in git history at d68fd70 — needs scrub or accept risk
- Local copy at `~/Desktop/IP-UTILITY-SIGNIFICANCE.md`
- Adrian = Brian's boss at CompStak. No employment contract/NDA/IP assignment exists.

### Project Locomotive
- Finance/trading application of superloop pattern
- At `Brians-Notes/project-locomotive.md` (local only, NOT committed, CONFIDENTIAL)

## BLOCKED: SitDeck Campaign Setup

### What needs to happen
The upstream author of auto-sdd's original architecture already built SitDeck using his simpler version of the system from the same vision.md. His roadmap had 74 features. Brian is re-running the same vision through Superloop as a head-to-head comparison — same input, different system. This demonstrates:
1. Superloop's capability vs the original auto-sdd on identical input
2. A working SitDeck app (real product value)
3. CIS training data with ~70 features (enables Rounds 5-6)

### What went wrong
Multiple failed attempts to get a Code tab agent to read the vision file and generate a roadmap. Root causes:
- Code tab agent CWD is `/home/user/auto-sdd/`, different from Mac filesystem
- Untracked files not visible to agent (fixed by committing vision.md)
- Agent kept trying to build/install instead of just writing the roadmap
- Prompt quality degraded as session went long — stopped following prompt engineering guide

### Current state of files
- `~/auto-sdd/vision.md` — committed at fc5f36d (the full SitDeck vision, 497 lines)
- `~/compstak-sitdeck/.specs/vision.md` — copy placed here but project dir not initialized
- `~/compstak-sitdeck/.specs/` — directory exists, empty except vision.md

### What the next prompt needs to do
1. Agent reads vision.md (it's committed in the auto-sdd repo now, or use the copy at ~/compstak-sitdeck/.specs/vision.md)
2. Agent writes ONLY: `~/compstak-sitdeck/.specs/roadmap.md` + `~/compstak-sitdeck/.specs/features/*.feature.md`
3. Agent does NOT initialize a project, install deps, run npm, or build anything
4. Roadmap must use the exact table format the build loop parser expects (see reliability.py `_parse_roadmap_rows`)
5. Target ~70 features (Adrian's roadmap had 74)
6. **The prompt MUST follow the prompt engineering guide** — hard constraints, preconditions, verification, scope discipline

### Roadmap table format required
```
| # | Feature | Source | Jira | Complexity | Dependencies | Status |
|---|---------|--------|------|------------|-------------|--------|
| 1 | Feature name | vision.md | - | L | - | ⬜ |
```
Columns: id, name, source, jira (always -), complexity (S/M/L/XL), deps (comma-separated IDs or -), status (⬜)

### After roadmap is generated
- Initialize the Next.js project separately
- Copy CompStak CSV data to `~/compstak-sitdeck/_shared-csv-data/`
- Run: `cd ~/auto-sdd/py && PROJECT_DIR=~/compstak-sitdeck .venv/bin/python -m auto_sdd.scripts.build_loop`
- This launches the full CIS-instrumented build campaign

## CIS Remaining Rounds

| Round | Status | Blocker |
|---|---|---|
| 5 | Needs campaign data | Run SitDeck campaign first |
| 6 | Needs 3+ campaigns | Run SitDeck + one more |

## Key Rules
- **Merge/push**: ALWAYS ask before git push/merge. Only exception: formal checkpoint commits
- **"Stash"**: means save locally, NOT git push (L-00198)
- **Brians-Notes/**: local only, do NOT commit without permission
- **project-locomotive.md**: CONFIDENTIAL
- **Full prompt reprints**: ALWAYS reprint complete prompts. Never "same as before but change X"
- **Agent environment**: Code tab CWD is NOT the same as Mac filesystem paths. Use relative paths or committed files.

## Uncommitted Local Files
- `Brians-Notes/project-locomotive.md` — finance curriculum (confidential)
- `Brians-Notes/token-estimation-fix-stash.md` — investigation notes
- `Brians-Notes/session-handoff-2026-03-06.md` — this file

## Learnings State
- L-00001 through L-00198
- M-00001 through M-00090
- Core learnings: 17 entries in core.md
