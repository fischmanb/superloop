---
description: Scan current session for uncaptured learnings and output in graph schema format
---

# Extract Learnings from Current Session

Scan this session for uncaptured learnings and output them in graph schema format.

**This command applies to ALL session types — build campaigns AND regular chat sessions.** Chat corrections are a primary source of M-entries (methodology signals) and process-rule L-entries. If Brian corrected Claude's behavior, named a wrong pattern, or articulated a principle during the chat, that is a learning and must be captured here. Don't wait for a build campaign to run `!learn`.

## Process

### 1. Read current state
```bash
cat learnings/process-rules.md learnings/empirical-findings.md learnings/core.md learnings/architecture-decisions.md | grep "^## [LM]-" | sort
```
Get the highest L-number and M-number currently in use. Stash the output to `/tmp/sdd-scratch.md` — the next tool call will discard anything held only in context.

### 2. Read HOW-I-WORK accumulation section
```bash
tail -100 HOW-I-WORK-WITH-GENERATIVE-AI.md
```
Check for pending methodology signals in the Accumulation section.

### 3. Scan the session

Review everything discussed in this session. For each potential learning, classify it:

**L-entries** (learnings about the system, process, or engineering):
- **process-rule:** How work should be done. Prescriptive.
- **empirical-finding:** What was observed. Descriptive.
- **architecture-decision:** Why the system is built this way. Explanatory.

**M-entries** (methodology signals about Brian's working style):
- **observation:** Something Brian did or said that reveals how he works.
- **preference:** A stated or demonstrated preference.
- **principle:** A belief or value Brian operates from.
- **workflow_fact:** A concrete fact about Brian's workflow or tools.

### 4. Deduplicate

For each candidate, check: is this already captured by an existing L- or M-entry? If yes, skip it. If it extends or refines an existing entry, note the relation but still capture it separately.

### 5. Output

For each new learning, output in graph schema format:

```
## L-NNNNN
Type: [type]
Tags: [concrete, searchable tags]
Confidence: [high/medium/low]
Status: active
Date: [today]
Related: [L-NNNNN, M-NNNNN references]

[Body text. Specific. Concrete details — commands, file names, exact failure modes. No examples unless the example is code. A learning that could apply to any project is too vague.]
```

### Title field — critical authoring rule

The title appears in the header line and is the primary navigational surface for any agent that has never encountered this learning. It must work standalone — an agent skimming `## L-NNNNN — [title]` lines must be able to determine relevance without reading the body.

**Formula:** [specific component/flag/file] + [what it did wrong or what happened] + [consequence, if not already implied]

**Wrong:** `flag-conflation`, `AUTO_APPROVE issue`, `config problem`  
These name the category of mistake. A future agent encountering the same symptom won't find them.

**Right:** `AUTO_APPROVE flag in project.yaml silently bypasses human pre-flight review`  
Names the exact artifact, what it did, and what that caused. Recognizable from the symptom side.

**Test:** Read only the header line. Can a future agent encountering the same symptom for the first time determine in under 3 seconds whether to read this entry? If not, rewrite the title.

**Generalizability check:** Does the title apply only to this exact one-time bug, or to a pattern that could recur? If one-time-only, broaden the title slightly while keeping it specific (e.g., not "the April 8 build failure" but "build loop silently swallows SIGTERM before cleanup completes").

### Tags field — critical authoring rule

Tags are the primary searchable surface of a learning. They must be **concrete and specific**, not abstract categorizations.

**Wrong:** `flag-conflation`, `static-count-in-config`, `bad-abstraction`
These describe the *type* of mistake, not the mistake itself. A future reader searching for the actual problem won't find them.

**Right:** `AUTO_APPROVE, SKIP_PREFLIGHT, pre-flight-review, project-yaml, human-gate`
These are the actual tokens, flags, filenames, and concepts involved. A reader searching for any of them finds this entry.

**Test:** Could someone find this learning by searching for the thing that broke? If not, the tags are wrong. Tags should answer: what were the specific flags, files, commands, or system components involved?

### 6. Confirmation

After outputting all candidates, ask Brian:
- "N learnings extracted (X L-entries, Y M-entries). Write them to their respective files?"
- Wait for approval before writing.
- If Brian says yes: write each to the correct file, increment counts, commit with message `learnings: L-NNNNN–L-NNNNN, M-NNNNN–M-NNNNN from !learn scan`

### 7. Token report

After writing, run the standard token usage report and append to general-estimates.jsonl with activity_type "learn-scan".

## What counts as a learning

**YES — capture these:**
- Something broke and the failure mode wasn't obvious
- A heuristic was proven wrong by measurement
- A process step was missing and its absence caused a problem
- Brian corrected Claude's behavior in a way that reveals a principle
- A tool or system behaved differently than expected
- A decision was made with explicit tradeoff reasoning

**NO — skip these:**
- Restating existing learnings in different words
- Observations that are obvious from the codebase
- Things that only apply to this exact moment and have no future relevance
- Vague "we should be more careful" sentiments without specifics (L-00117)
