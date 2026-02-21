# Collaborative Prompt Engineering Guide
## For Claude instances working with Brian on `auto-sdd`

---

## What This Is

Brian and Claude work together to write hardened prompts for Claude Code agents that execute tasks on the `auto-sdd` GitHub repo. Brian brings the task intent; Claude corrects, hardens, and produces the final prompt. The agent runs it, reports back, and the cycle continues.

This document captures the methodology so a new Claude instance can pick up without relearning everything.

---

## The Repo

**`auto-sdd`** — a spec-driven development system that orchestrates AI agents to implement features from `.feature.md` spec files. Originally built by Brian's boss using Cursor's `agent` CLI. Brian is hardening and adapting it to run locally on a 256GB unified memory Mac Studio.

**Key files:**
- `scripts/build-loop-local.sh` — main orchestration script (1300+ lines)
- `scripts/overnight-autonomous.sh` — overnight automation variant
- `lib/reliability.sh` — shared reliability functions (lock, backoff, state, truncation, cycle detection)
- `lib/validation.sh` — YAML frontmatter validation
- `tests/test-reliability.sh` — 57 unit assertions (must always pass)
- `tests/dry-run.sh` — structural integration test (run with `DRY_RUN_SKIP_AGENT=true` to skip live agent)
- `Agents.md` — agent work log and architecture reference (read this first on any new task)

**Current state:** Cursor `agent` CLI has been swapped to Claude Code `claude` CLI. Integration branch is the most recently committed `claude/*` branch on origin.

---

## The Workflow

### Brian's role
- Brings task intent, sometimes a rough draft prompt
- Has context on the repo state and history
- Makes judgment calls on ambiguous decisions
- Reviews agent output and reports results back

### Claude's role
- Corrects and hardens prompts before they go to the agent
- Writes investigation prompts when information is missing
- Flags gaps, risks, and uninformed decisions
- Never guesses at things that can be verified

### The cycle
1. Brian describes a task or shares a rough prompt
2. Claude identifies what's unknown or risky
3. If investigation is needed: Claude writes an investigation prompt → Brian runs it → agent reports findings → Claude writes the implementation prompt
4. Claude produces the final hardened prompt as a single copyable block
5. Brian runs it in Claude Code, reports results
6. Claude notes any gaps or corrections for next time

---

## Prompt Structure

Every agent prompt follows this structure, in order:

### 1. Branch setup (always first)
```
Before doing anything else:
1. Run `git fetch origin`
2. Identify the current canonical integration branch — it is the most recently
   committed `claude/*` branch on origin:
   git branch -r --list 'origin/claude/*' --sort=-committerdate | head -5
   Report the top result. That is your base branch.
3. Run `git checkout <that branch>`
4. Run `git pull origin <that branch>`
5. Run `git checkout -b claude/<task-description>-$(date +%s | tail -c 5)`
6. Confirm your new branch name and report the most recent commit hash
   inherited from the integration branch before proceeding.
```

**Why:** Agents get 403 errors pushing to existing branches due to GitHub token scope limits. Every agent task must fork a new branch. The integration branch name changes each round so it's always identified dynamically by recency, never hardcoded.

### 2. Task statement
One paragraph. What to do and what not to do. Explicit scope boundary.

### 3. PRECONDITIONS block
Checklist of things that must be true before any work starts. If any fails, agent stops and reports — no workarounds.

Always include:
- [ ] Correct branch confirmed
- [ ] Key files exist
- [ ] `./tests/test-reliability.sh` passes (expect 57 assertions)

### 4. INVESTIGATION block
Runs before any implementation. Answers questions that would otherwise require guessing.

Pattern:
- Targeted greps (not full file reads — those blow context)
- Specific questions with specific expected outputs
- "Document your findings before proceeding" — forces reporting before acting

### 5. IMPLEMENTATION block
Numbered steps. Specific. No wiggle room.

Each step says:
- What file
- What to change
- What the result should look like (show the new code where possible)

Ends with explicit DO NOT list covering the most likely mistakes.

### 6. VERIFICATION block
Run in order. Stop on any failure. Do not proceed to documentation if any fail.

Always include:
- `bash -n` on modified scripts
- `./tests/test-reliability.sh` (expect 57 passing)
- `DRY_RUN_SKIP_AGENT=true ./tests/dry-run.sh`
- Targeted greps confirming changes took effect
- Targeted greps confirming nothing was accidentally broken

### 7. DOCUMENTATION block
Only runs after all verification passes.

Always includes:
- Update `Agents.md` Agent Work Log with a new round entry
- Commit with a meaningful message
- `git push -u origin <branch-name>`
- Report branch name and commit hash

---

## Known Gotchas

### The grep false-negative problem
This pattern does NOT correctly filter comment lines:
```bash
grep -rn "pattern" scripts/ | grep -v "^\s*#"
```
Because `grep -rn` prepends `filename:linenum:` before the `#`, the `-v` filter never matches. Use instead:
```bash
grep -rn "pattern" scripts/ | grep -v ":#\|: #"
```

### Agent self-assessments are unreliable
Round 1 of this repo's history: agent claimed to implement 6 features, implemented none, then described bugs in code it never wrote. Always verify with grep and tests, never trust agent's own summary of what it did.

### "Defined but never called" is the most common failure mode
After any function is added, always grep for call sites. All three early rounds had at least one function defined but never wired in.

### Context window sizing
Prompts that ask agents to read multiple large files in full (1300-line scripts) risk context rot. Keep investigation greps targeted. If a task genuinely requires reading large files, split into investigation prompt first, then implementation prompt second.

### Merge prompts are their own task
Don't bolt merge logic onto implementation prompts. Merge is a separate prompt with its own preconditions and verification.

---

## Merge Protocol

When an agent task completes successfully, Brian asks for a merge prompt. Structure:

1. Check out the integration branch (dynamically identified, same pattern as above — but explicitly exclude the branch being merged)
2. Verify tests pass pre-merge
3. `git merge --no-ff origin/<branch> -m "merge: <description> (<branch>)"`
4. If conflicts: stop and report — never resolve autonomously
5. Verify tests pass post-merge
6. Push integration branch
7. Report new HEAD commit hash

---

## Investigation Prompts

When Claude doesn't have enough information to write a safe implementation prompt, write an investigation prompt instead. These:

- Fork a new branch the same way (branch hygiene applies even for read-only tasks)
- Have no IMPLEMENTATION block
- End with "Do not modify anything. Report all findings and await instruction."
- Ask specific questions with specific grep/find commands
- Ask for summary conclusions at the end ("Based on findings, report: X, Y, Z")

Brian runs the investigation prompt, pastes the results, then Claude writes the implementation prompt informed by real data.

---

## The Agents.md Work Log

Every agent task adds a round entry to `Agents.md`. Format:

```markdown
### Round N: <Title> (branch: <branch-name>)

**What was asked**: <one sentence>
**What actually happened**: <what the agent did, including any deviations>
**What was NOT changed**: <explicit scope boundary>
**Verification**: <test results>
```

Superseded branches (whose work is fully merged) are noted as such in the log with a `> ⚠️ SUPERSEDED` callout.

---

## Current Goals (as of this guide)

1. ✅ Hardened `lib/reliability.sh` with lock, backoff, state, truncation, cycle detection
2. ✅ Extracted shared functions, removed duplication between scripts
3. ✅ 57-assertion unit test suite passing
4. ✅ Structural dry-run passing
5. ✅ Swapped Cursor `agent` CLI to Claude Code `claude` CLI
6. **Next**: Live test run — `./tests/dry-run.sh` without `DRY_RUN_SKIP_AGENT=true`
7. **Then**: Local model integration (replace cloud API calls with local LM Studio endpoints on Mac Studio)

---

## How to Orient on a New Chat

If Brian says context was lost, ask him to paste `Agents.md`. That file contains the full agent work log, current file structure, known gaps, and verification checklist. It is the source of truth for repo state. This guide covers methodology; `Agents.md` covers current state.