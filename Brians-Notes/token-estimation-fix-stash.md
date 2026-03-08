# Token Estimation Fix — Investigation Stash (2026-03-06)

## Problem
Token estimates in agent prompts are fiction. No calibration against actuals.
Data is collected but never read back before writing next estimate.

## Data Found
- Root `general-estimates.jsonl`: 10 entries (mixed bash-era + python)
- `py/general-estimates.jsonl`: 2 entries (CIS rounds only — CWD bug creates duplicate file)
- Estimates range: 12,000-21,000 (always similar numbers)
- Actuals range: 572-54,663 (wildly variable)
- Average estimation error: 965.4% (from py/ file, 2 samples)

## Root Cause: get_session_actual_tokens is broken
- `_find_most_recent_session_jsonl()` finds most recent .jsonl by mtime across ALL projects
- Agent runs during compaction get split across multiple session files — measurement reads only the tail
- CIS Round 1a: estimated 12,000, "actual" 572 — the 572 was post-compaction tail, not real total
- CIS Round 2: estimated 18,000, actual 54,663 — possibly correct but 3x off from estimate
- Session files are in `~/.claude/projects/{encoded-cwd}/{uuid}.jsonl`
- Multiple project dirs: auto-sdd, auto-sdd-py, auto-sdd-stakd, auto-sdd-stakd-v2, cre-lease-tracker

## Session File Structure
- Each project gets its own dir under ~/.claude/projects/
- Multiple JSONL files per project (one per session/conversation?)
- CRE lease tracker has the most recent files (from auto-QA agent runs)
- auto-sdd-py has the CIS round files (from Code tab agents)
- Finding "which session file belongs to which agent prompt" is the core problem

## What Needs Fixing
1. **Merge JSONL files** — one canonical location at repo root, not root + py/
2. **Fix session file discovery** — need to find the session file that matches the CURRENT agent run, not just "most recent globally"
3. **Handle compaction** — if a session spans multiple files (compaction splits), sum all files from that session
4. **Pre-prompt calibration** — before writing estimated_tokens_pre, query historical actuals for similar activity types
5. **Enforce in prompt engineering guide** — mandatory query_estimate_actuals() call before writing any estimate

## Possible Fix Approaches
- Option A: Pass session ID explicitly to the token report script (agent knows its own session)
- Option B: Filter by CWD — agent runs in project dir, find session files for THAT project only
- Option C: Filter by time window — agent started at time T, find session files modified after T
- Option D: Sum ALL session files for the project dir modified within the run window

## CIS Status at Stash Time
- Rounds 1a, 1b, 2 MERGED to main at 0377847
- Round 3 prompt DELIVERED to Brian, agent running
- Main at 0377847, remote is github.com/fischmanb/superloop
- Repo renamed from auto-sdd to superloop (local path unchanged ~/auto-sdd)

## Next Actions
1. Fix the measurement (Option B or D most promising)
2. Merge the two JSONL files
3. Add pre-prompt calibration query to prompt engineering guide
4. Update the token report template to use correct session discovery


## Session File Discovery (from investigation before compaction)

### Key finding: session files are per-project-CWD
- `~/.claude/projects/-Users-brianfischman-auto-sdd-py/` — agents run from py/ dir
- `~/.claude/projects/-Users-brianfischman-auto-sdd/` — agents run from repo root
- `~/.claude/projects/-Users-brianfischman-cre-lease-tracker/` — auto-QA agents

### Most recent files by project:
- auto-sdd-py: latest 2026-03-04 15:01, 405KB (this is where CIS agent sessions live)
- auto-sdd: latest 2026-03-03 14:46 (older, pre-CIS)
- cre-lease-tracker: latest 2026-03-05 20:16 (auto-QA Phase 5 agents)

### The fix should:
- Filter by project CWD, not global most-recent
- Sum all session files within a time window for the agent run
- The agent prompt includes a timestamp — use that as the "after" filter
- Option B (filter by CWD) + Option D (sum files in time window) combined

### CIS Round 3 status:
- Prompt delivered to Brian, agent should be running
- Branch name unknown until agent reports back
- Main at 0377847

### Other state:
- IP doc removed from repo but in git history at d68fd70
- IP doc saved locally at ~/Desktop/IP-UTILITY-SIGNIFICANCE.md  
- Repo: github.com/fischmanb/superloop (unforked, renamed)
- Local path unchanged: ~/auto-sdd
- Medium draft at conversation outputs (not in repo)
- Proof deck at Brians-Notes/superloop-deck-2026-03-05.pdf
- Project Locomotive at Brians-Notes/project-locomotive.md (local only, not committed)
