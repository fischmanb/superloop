---
description: Scan HOW-I-WORK methodology signals for patterns that should graduate to learnings
---

Review methodology signals: $ARGUMENTS

## Purpose
HOW-I-WORK-WITH-GENERATIVE-AI.md has two zones: structured methodology entries (M-XXXXX, graph-schema)
and a raw `## Accumulation` section at the bottom (pre-learnings staging area). Raw observations
accumulate there (checkpoint step 5) before being synthesized into actionable rules or converted
to M-entries. This command closes the feedback loop (L-00124) by surfacing patterns that should
become learnings or protocol changes.

## Process

### 1. Read Accumulation Section
Read the `## Accumulation` section of `HOW-I-WORK-WITH-GENERATIVE-AI.md`.
Also scan existing M-entries for themes relevant to the review.

### 2. Cluster by Theme
Group entries that share a common pattern. Look for:
- Same principle stated multiple ways across different dates
- Observations that describe a failure mode already seen in `learnings/failure-patterns.md`
- Observations that describe a process Brian enforces but that has no corresponding L-number
- Observations that contradict or refine an existing learning

### 3. Check Against Existing Learnings
For each cluster, search `learnings/*.md` for existing coverage:
- `grep -l "relevant-keyword" learnings/*.md`
- If already captured → mark signal as "covered by L-XXXXX"
- If partially captured → flag for refinement
- If not captured → candidate for new learning

### 4. Report

```
## Signal Review

Accumulation entries scanned: 30
Clusters identified: 5

Already covered:
  - "agent trust assumptions" cluster (3 entries) → covered by L-00001, L-00005
  - "context window pressure" (2 entries) → covered by L-00130

Candidates for new learnings:
  - "prompt compression" cluster (4 entries): Brian's prompt quality criteria
    (token cost, agent efficiency, compression principle). No existing learning.
  - "phase separation" cluster (2 entries): cognitive overhead as a constraint
    on parallelism. Not in learnings.

Refinement candidates:
  - "fresh context as stress test" (2 entries) → L-00117 covers adoption latency
    but not the deliberate plan→critique→execute pattern Brian uses.
```

### 5. Action
- New learning candidates: write them (get next L-number, follow graph schema)
- Refinement candidates: update existing learning body text
- Covered entries: optionally mark in Accumulation with `[→ L-XXXXX]` so future
  reviews skip them (Brian's call — don't auto-mark without permission)
- All actions follow normal checkpoint propagation (run `/verify-propagation` after)

## When to Run
- During checkpoint step 4 methodology signals review (L-00124)
- Periodically when Accumulation section grows beyond ~20 unprocessed entries
- When `$ARGUMENTS` contains "quick": cluster and report only, no writes
