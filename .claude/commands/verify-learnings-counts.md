---
description: Count learnings entries and reconcile vs documentation claims
---

Verify learnings counts: $ARGUMENTS

## Process

### 1. Count Actual Entries
Run: `grep -ch "^## L-" learnings/*.md` per file.
Sum for total. Also count core.md curated entries separately.
Get highest L-number: `grep -h "^## L-" learnings/*.md | sort -t'-' -k2 -n | tail -1`
Also count methodology entries: `grep -c "^## M-" HOW-I-WORK-WITH-GENERATIVE-AI.md`
Get highest M-number: `grep -h "^## M-" HOW-I-WORK-WITH-GENERATIVE-AI.md | sort -t'-' -k2 -n | tail -1`

### 2. Compare Against Documentation Claims
Check these files for numeric claims about learnings:
- `ONBOARDING.md` — key files table row for learnings/, learnings section prose
- `ACTIVE-CONSIDERATIONS.md` — learnings system line, graph-schema conversion line
- `learnings/core.md` — any count in header/comments

### 3. Report

```
## Learnings Count Verification

Actual:
  Total entries (type files): 59
  Core curated entries: 10
  Highest ID: L-00124
  By file:
    process-rules.md: 15
    failure-patterns.md: 12
    empirical-findings.md: 8
    architectural-rationale.md: 5
    domain-knowledge.md: 19

Documentation claims:
  ONBOARDING.md key files table: "59 graph-format entries (L-00001–L-00124)" ✅
  ONBOARDING.md prose: "59 graph-format entries" ✅
  ACTIVE-CONSIDERATIONS.md: "59 graph-compliant" ✅

Discrepancies: NONE
```

### 4. Fix
If discrepancies found, update documentation to match actual counts.
This is a mechanical fix — no Brian approval needed for count corrections.

## When to Run

- During checkpoint step 4 propagation check (L-00114)
- After writing new learnings entries
- When `--quick` flag: just report counts, skip doc comparison
