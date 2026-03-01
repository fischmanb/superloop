---
description: Update all context management files. Run before ending a session, before a risky operation, or on demand.
---

checkpoint: $ARGUMENTS

## What This Does

Single command to ensure all context management files are current. Prevents context loss across sessions.

## Checklist (execute in order)

### 1. State File
- Read `~/auto-sdd/.onboarding-state`
- If `pending_captures` is non-empty → proceed to step 2
- If empty → skip to step 3

### 2. Flush Captures
- Read `ACTIVE-CONSIDERATIONS.md`
- Staleness scan: flag any items marked ✅, "complete", "merged", or "done" — report to Brian, do not auto-remove
- Append `pending_captures` to the appropriate section (priority stack items → stack, everything else → "Other active items")
- Clear `pending_captures`

### 3. Decisions
- Review what was discussed this session
- If any questions were settled with explicit decisions: append to `DECISIONS.md` (date, what, why, rejected alternatives)
- If none → skip

### 4. Learnings
- If any failure patterns, process rules, empirical findings, architectural rationale, or domain knowledge surfaced: flag for Brian with proposed entry (type, tags, body)
- Do NOT auto-write to learnings files — Brian approves entries

### 5. ONBOARDING.md Drift Check
- `md5 -q ~/auto-sdd/ONBOARDING.md` (or `md5sum` on Linux)
- Compare to `last_check_hash` in `.onboarding-state`
- If changed: note what changed (another session or Brian edited it)
- Update hash

### 6. Commit
- `git add .onboarding-state ACTIVE-CONSIDERATIONS.md DECISIONS.md`
- Only add other files if they were modified (ONBOARDING.md, INDEX.md)
- `git commit -m "checkpoint: <brief summary of what was flushed>"`
- Ask Brian before pushing

### 7. Update State
Write `.onboarding-state`:
```json
{
  "last_check_ts": "<now ISO>",
  "last_check_hash": "<current ONBOARDING.md hash>",
  "prompt_count": 0,
  "pending_captures": []
}
```

## Options

- `/checkpoint` — full checklist
- `/checkpoint --dry` — report what would be flushed/flagged without writing
- `checkpoint` in chat — same checklist, chat session executes it
