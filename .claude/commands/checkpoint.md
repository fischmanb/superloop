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
- Active scan — review the session for learnable moments. Do not rely on recall; check each category:
  - **Agent completions**: Did an agent finish this session? What worked, failed, or surprised? Does the outcome validate or contradict existing learnings?
  - **Corrections**: Did Brian correct something? Each correction is a candidate learning.
  - **New rules or patterns**: Were any stated or discovered?
  - **Empirical findings**: Any measurements, outcomes, or data points?
  - **Failures or near-misses**: Anything that went wrong or almost did?
- For each candidate: propose entry to Brian (type, tags, body)
- Do NOT auto-write to learnings files — Brian approves entries
- Under-capture is a failure mode. Match capture density to session density. (L-0113)

### 5. Methodology Signals
- Scan session for operator-level insights: preferences, principles, reasoning patterns, workflow decisions, distinctions Brian drew, corrections that reveal generalizable observations
- Bias toward capture — a false positive costs 5 seconds to delete, a false negative is gone
- If any found: append raw notes to the accumulation section at the bottom of `HOW-I-WORK-WITH-GENERATIVE-AI.md` (create file with preamble + accumulation section if it doesn't exist)
- Format: `- (YYYY-MM-DD) <raw observation>`
- Voice: Third person ("Brian prefers...", "Brian has found..."), empirical not prescriptive. Describe what was observed/tried/preferred, not universal laws. "Brian has found X effective" over "one must always X." This does not apply to operational gates elsewhere in the repo.
- NEVER use first person. The document is written *about* Brian by AI; first-person would misrepresent authorship.

### 6. ONBOARDING.md Drift Check
- `md5 -q ~/auto-sdd/ONBOARDING.md` (or `md5sum` on Linux)
- Compare to `last_check_hash` in `.onboarding-state`
- If changed: note what changed (another session or Brian edited it)
- Update hash

### 7. Commit and Push
- `git add .onboarding-state ACTIVE-CONSIDERATIONS.md DECISIONS.md`
- Only add other files if they were modified (ONBOARDING.md, INDEX.md, HOW-I-WORK-WITH-GENERATIVE-AI.md)
- `git commit -m "checkpoint: <brief summary of what was flushed>"`
- `git push origin` — checkpoint commits are always pushed. No approval needed.

### 8. Update State
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
