---
description: Extract and persist learnings from the current coding session
---

Extract learnings from this session and persist them.

## IMPORTANT: Use New Learnings System

**Do NOT write to `.specs/learnings/`.** That is the legacy location.

All new learnings go in `learnings/` using graph-schema format. See `learnings/core.md` for the format reference.

For chat sessions (claude.ai with Desktop Commander): use the checkpoint protocol (`.claude/commands/checkpoint.md` step 4) instead of this command. The checkpoint protocol has active scan categories, default-flip, self-test, and propagation checks.

For Claude Code agents: this command can still be used, but output must follow the graph-schema format below.

## Graph-Schema Learning Format

```markdown
## L-XXXXX
Type: process_rule | failure_pattern | empirical_finding | architectural_rationale | domain_knowledge
Tags: tag1, tag2, tag3
Confidence: high | medium | low
Status: active | superseded | deprecated
Date: YYYY-MM-DDTHH:MM:SS-05:00
Related: L-YYYYY (depends_on | related_to | supersedes | validates)

[Body text describing the learning — what happened, why it matters, what to do differently.]
```

## Process

1. **Reflect** on what was accomplished this session
2. **Identify** patterns, gotchas, decisions, and bug fixes using active scan categories:
   - Agent completions (validate/contradict existing learnings?)
   - Corrections (each is a candidate)
   - New rules or patterns
   - Empirical findings
   - Failures or near-misses
3. **Get next L-number**: `grep -h "^## L-" learnings/*.md | sort -t'-' -k2 -n | tail -1`
4. **Categorize** each learning by type → write to corresponding `learnings/{type}.md`
5. **Check core.md**: Does this learning belong in the curated set? (L-00118)
6. **Run** `/verify-learnings-counts` to catch count drift (L-00115)
7. **Commit** changes with message `compound: L-XXXXX–L-YYYYY from [brief description]`

## Category Routing (New System)

| Type | Where |
|------|-------|
| Process rules, session discipline | `learnings/process-rules.md` |
| Things that went wrong | `learnings/failure-patterns.md` |
| Measured outcomes, data points | `learnings/empirical-findings.md` |
| Design decisions, transferable patterns | `learnings/architectural-rationale.md` |
| Project-specific technical knowledge | `learnings/domain-knowledge.md` |
