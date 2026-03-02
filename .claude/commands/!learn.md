# Extract Learnings from Current Session

You are running the `!learn` command. Scan this session for uncaptured learnings and output them in graph schema format.

## Process

### 1. Read current state
```bash
cat learnings/process-rules.md learnings/empirical-findings.md learnings/core.md learnings/architecture-decisions.md | grep "^## [LM]-" | sort
```
Get the highest L-number and M-number currently in use.

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
- **Type:** [type]
- **Tags:** [relevant tags]
- **Confidence:** [high/medium/low] — [one-line justification]
- **Status:** active
- **Date:** [today]
- **Related:** [L-NNNNN, M-NNNNN references]

[Body text. Be specific. Include concrete details from the session — commands, numbers, exact failure modes. A learning that could apply to any project is too vague.]
```

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
