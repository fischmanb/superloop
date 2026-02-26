# Collaborative Prompt Engineering Guide
## For Claude instances working with Brian on `auto-sdd`

---

## What This Is

Brian and Claude work together to write hardened prompts for Claude Code agents that execute tasks on the `auto-sdd` GitHub repo. Brian brings the task intent; Claude corrects, hardens, and produces the final prompt. The agent runs it, reports back, and the cycle continues.

This document captures the methodology so a new Claude instance can pick up without relearning everything.

---

## Where This Guide Lives

This file belongs in the repo at `Brians-Notes/PROMPT-ENGINEERING-GUIDE.md` alongside `SETUP.md` and `HANDOFF-PROMPT.md`. Commit it there so it survives context loss and is available to any Claude instance that reads the repo.

---

## The Repo

**`auto-sdd`** — a spec-driven development system that orchestrates AI agents to implement features from `.feature.md` spec files. Originally built by Brian's boss using Cursor's `agent` CLI. Brian is hardening and adapting it to run locally on a 256GB unified memory Mac Studio.

**Key files:**
- `scripts/build-loop-local.sh` — main orchestration script (1300+ lines)
- `scripts/overnight-autonomous.sh` — overnight automation variant
- `scripts/nightly-review.sh` — nightly review automation
- `lib/reliability.sh` — shared reliability functions (lock, backoff, state, truncation, cycle detection)
- `lib/validation.sh` — YAML frontmatter validation
- `lib/claude-wrapper.sh` — wraps claude CLI, extracts raw text to stdout, logs cost/token data to JSONL
- `tests/test-reliability.sh` — 57 unit assertions (must always pass)
- `tests/dry-run.sh` — structural integration test (run with `DRY_RUN_SKIP_AGENT=true` to skip live agent)
- `Agents.md` — agent work log and architecture reference (read this first on any new task)
- `CLAUDE.md` — repo-level instructions that Claude Code reads automatically (can override prompt instructions — see failure catalog)

---

## Prompt Structure

Every implementation prompt follows this structure:

### 1. Hard Constraints (NEW — required on all prompts)
Explicit file allowlist, banned commands, and a `git diff --stat` gate. This section exists because agents will exceed scope if you don't fence them.

```
## Hard Constraints

- These instructions override any conflicting guidance in CLAUDE.md or other repo-level configuration files.
- Follow the numbered steps in this prompt IN ORDER. Do not explore, read, or investigate any files beyond what is explicitly specified in the steps. Do not attempt to "understand the codebase." The instructions contain everything you need.
- You may ONLY modify these files: <explicit list>
- You may ONLY create these new files: <explicit list, or "none">
- You may NOT run npm, yarn, pip, brew, or any package manager command
- You may NOT delete any files
- You may NOT read or open any file not explicitly referenced in these steps
- If you encounter ANYTHING unexpected — files not matching descriptions, commands not found, structure differences, unfamiliar patterns — STOP IMMEDIATELY. Do not attempt to fix, adapt, or work around the issue. Report exactly what you found and take no further action.
- If ANY verification step or test fails, STOP IMMEDIATELY. Do not commit. Do not attempt to fix. Report the failure and take no further action.
- Before committing, you MUST run `git diff --stat` and verify ONLY the allowed files appear. If ANY other file appears, STOP and report the problem. Do not commit.
```

### 2. Preconditions
- Confirm working directory with `pwd`
- Confirm clean working tree with `git status`
- `git fetch origin`
- Identify current state (main HEAD, latest claude/* branch)
- Fork a new branch from the most recent
- Report which branch was forked from and why

### 3. Implementation
- Specific, line-level instructions for each file change
- "Touch NOTHING else in this file" after each change
- Agents.md round entry with: what was asked, what was changed, what was NOT changed, verification results

### 4. Verification
- `bash -n` syntax checks on modified scripts
- grep to confirm expected changes exist
- `cat` to verify file contents
- Run existing test suites: `tests/test-reliability.sh` and `DRY_RUN_SKIP_AGENT=true tests/dry-run.sh`
- `git diff --stat` to confirm no scope creep
- **CRITICAL**: If ANY verification step or test fails, STOP IMMEDIATELY. Do not continue. Do not commit. Do not attempt to fix. Report the failure and take no further action.

### 5. Commit and Merge
- `git add` only the explicitly allowed files (never `git add -A` or `git add .`)
- Commit with descriptive message
- Merge to main with `--no-ff`
- Do NOT push — Brian pushes manually from his machine (sandbox lacks GitHub auth)
- Report new HEAD commit hash

### 6. Prompt Closing
Every prompt must end with: "Report your findings immediately upon completion. Do not wait for a follow-up question."

---

## Prompt Delivery

Engineered prompts are delivered in the chat response body inside a single fenced code block. Do not write prompt files to disk, save them to the repo, or place them in any directory. Brian copies the prompt from the chat to wherever he needs it. The prompt exists in chat until Brian acts on it — it is not a repo artifact.

---

## Investigation Prompts

When Claude doesn't have enough information to write a safe implementation prompt, write an investigation prompt instead. These:

- Include the full Hard Constraints block (agents will explore if not forbidden)
- Fork a new branch the same way (branch hygiene applies even for read-only tasks)
- Have no IMPLEMENTATION block
- Ask specific questions with specific grep/find commands
- Ask for summary conclusions at the end ("Based on findings, report: X, Y, Z")
- End with a verification block: `git status` and `git diff` must both be clean
- End with "Do not modify anything. Report all findings immediately upon completion. Do not wait for a follow-up question."

Brian runs the investigation prompt, pastes the results, then Claude writes the implementation prompt informed by real data.

---

## Prompt Sizing and Splitting

The project's core principle — fresh contexts per stage to avoid context rot — applies to agent prompts themselves. A prompt that tries to do too much produces the same degradation it's trying to prevent: agents lose track of constraints, skip steps, define functions without calling them, and exceed scope.

**Rule of thumb**: A single implementation prompt should target one cohesive unit of work that modifies no more than 3-4 files with interrelated changes. When a task exceeds this, split it into sequential prompts where each round commits its work and the next round builds on a verified foundation.

**Splitting criteria** (any one of these warrants a split):
- More than ~4 files being modified with non-trivial changes in each
- Changes to core orchestration logic AND a new algorithm/function AND test additions AND prompt template rewrites in the same prompt
- The prompt itself exceeds ~200 lines (the prompt is consuming the agent's context budget before implementation starts)
- Changes span two independently testable systems (e.g., build-loop-local.sh and overnight-autonomous.sh)
- You find yourself writing "also do X" after the main implementation is already fully specified

**How to split**: Each sub-prompt is a full Round with its own branch, Hard Constraints, Implementation, Verification, and Agents.md entry. The second prompt's Preconditions include verifying that the first round's commit exists and tests pass. This is strictly better than one large prompt because each round gets verified independently — a failure in round N doesn't contaminate round N+1's context.

**Anti-pattern**: "Let's just add one more thing to the prompt since the agent is already in there." This is how Round 1-class failures happen. The marginal cost of a fresh agent session is near zero. The marginal risk of scope creep in a bloated prompt is high.

---

## Merge Prompts

Structure:

1. Check out the integration branch (dynamically identified — explicitly exclude the branch being merged)
2. Verify tests pass pre-merge
3. `git merge --no-ff origin/<branch> -m "merge: <description> (<branch>)"`
4. If conflicts: stop and report — never resolve autonomously
5. Verify tests pass post-merge
6. Push integration branch
7. Report new HEAD commit hash

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

## Lessons Learned (Failure Catalog)

### Agent self-assessments are unreliable
Agents will report "all verifications passed" while having made changes far beyond scope. The verification block in the prompt must enforce correctness — never trust the agent's narrative summary. Always include machine-checkable gates (`git diff --stat`, `bash -n`, grep).

### "Do not modify any other files" is insufficient
Round 7 (2025-02-24): Agent was told "do not modify any other files" but ran `npm install`, committing 6400+ node_modules files and a tsconfig.tsbuildinfo. The instruction was too vague. Fix: explicit file allowlist + explicit package manager ban + `git diff --stat` gate before commit.

### Agents will run in the wrong directory
Round 7: Prompt didn't specify working directory. Agent ran in the parent `auto-sdd/` repo (which had a git remote) instead of the intended `stakd/` subdirectory. The `stakd/` subdir was a separate git repo with no remote, but the agent found the parent's remote and pushed to it. Fix: always include a `pwd` check in Preconditions, and if the target is a subdirectory, add `cd <path> && pwd` as the first precondition step.

### Agents will push when not told to (and when told not to)
Round 7: Prompt said "Do not push." Agent pushed `claude/fix-agent-permissions-tHme8` to origin anyway. Fix: if you don't want a push, don't have a remote configured, or add explicit "Do not run git push under any circumstances" in Hard Constraints.

### node_modules must be in .gitignore
If the repo has a package.json, ensure `node_modules/` is in `.gitignore` before running any agent. Agents may run `npm install` despite instructions not to.

### `--force-with-lease` requires fresh fetch
`git push --force-with-lease` will fail with "stale info" if you haven't fetched since the remote was last updated. Always `git fetch origin` immediately before `--force-with-lease`.

### HTTP 408 on large pushes
Git pushes over ~25MB can fail with `HTTP 408 curl 22`. Fix: `git config http.postBuffer 524288000` (500MB buffer).

### macOS ships bash 3.2
Scripts using associative arrays (`declare -A`) or other bash 4+ features will fail on macOS default bash. Fix: `brew install bash` and invoke with `/opt/homebrew/bin/bash`.

### CLAUDE.md repo instructions can override prompt instructions
Round 8 (2025-02-24): Prompt explicitly said to merge to main and push main. The agent's own `CLAUDE.md` file contained branch development rules saying to push to the feature branch instead. The agent decided CLAUDE.md took precedence and refused to merge to main, citing "permissions I may not have." Fix: if the prompt needs to override CLAUDE.md behavior, state it explicitly: "These instructions override any conflicting guidance in CLAUDE.md or other repo-level configuration files." Alternatively, temporarily modify CLAUDE.md before running the agent, or accept that merge-to-main will always be a manual step.

### `git add -A` considered harmful in agent context
Never use `git add -A` or `git add .` in agent prompts. Always `git add <explicit file list>`. Agents create and modify unexpected files; blanket adds will commit them.

### Agents don't report unprompted
Round 9 investigation (2025-02-24): Agent completed all investigation steps but did not report results until asked "what happened?" Fix: every prompt must end with "Report your findings immediately upon completion. Do not wait for a follow-up question."

### Agents will explore the codebase if not forbidden
Round 9 (2025-02-24): Agent was given specific numbered steps but decided to "Explore auto-sdd codebase" and "read the key files to understand the project deeply" — reading every file in the repo before starting implementation. This wastes tokens and risks the agent "improving" things it discovered. Fix: Hard Constraints must include "Follow the numbered steps in this prompt IN ORDER. Do not explore, read, or investigate any files beyond what is explicitly specified in the steps. Do not attempt to 'understand the codebase.' The instructions contain everything you need."

### Agents work around failures instead of stopping
Round 9 (2025-02-24): Agent couldn't push from a fresh clone (no GitHub auth in sandbox). Instead of stopping, it abandoned the clean clone, went back to a stale local repo at `/home/user/auto-sdd`, and applied changes there. It made 5 autonomous decisions to work around the problem, each one moving further from the intended execution path. Fix: Hard Constraints must include explicit STOP instructions for ANY unexpected situation: "If you encounter ANYTHING unexpected — STOP IMMEDIATELY. Do not attempt to fix, adapt, or work around the issue."

### Sandbox environments cannot push to GitHub
The Claude Code sandbox at `/home/user/` does not have GitHub authentication configured. Any prompt that ends with `git push origin main` will fail in the sandbox. Fix: either have the agent commit and merge locally without pushing (Brian pushes manually from his machine), or use `git clone` with the real repo URL so the agent works on a fresh clone — but accept that pushing will still fail. The safest pattern is: agent commits to feature branch, Brian pulls and merges locally.

### CLAUDE.md appends random suffixes to branch names
Claude Code's CLAUDE.md configuration appends random suffixes like `-f05hV` or `-Q63J8` to branch names specified in prompts. `claude/add-cost-tracking` becomes `claude/add-cost-tracking-wrapper-f05hV`. Fix: don't hardcode branch names in merge/push steps. Use the branch name the agent actually created, or accept that merge-to-main will be a manual step.

### Orphan branches accumulate on remote
Every agent run that pushes creates a remote branch that never gets cleaned up. After a few failed runs, 22 orphan branches were found on origin. Fix: periodically run `git branch -r | grep claude/ | while read b; do git push origin --delete "${b#origin/}"; done` to clean up. Future prompts should not instruct agents to push feature branches to origin.

### Force push can destroy agent work
Round 8 (2025-02-24): A `git push --force-with-lease` to clean up node_modules also wiped out agent branches that had been pushed to origin. The permissions fix from that agent run was lost and had to be redone. Fix: before force pushing, check what branches exist on origin and whether any contain unmerged work.

---

## Pending Fixes to Propagate

### Grep comment-filter fix
The verification blocks in existing prompts use the broken comment filter pattern. All future prompts should use the corrected version. When writing any new verification block that filters comments, always use:
```bash
grep -rn "pattern" scripts/ | grep -v ":#\|: #"
```
Not:
```bash
grep -rn "pattern" scripts/ | grep -v "^\s*#"
```
The broken pattern fails because `grep -rn` prepends `filename:linenum:` before the `#`, so `^\s*#` never matches. This has not yet been patched into the existing scripts or test suite.

---

## Current Goals (as of 2026-02-25)

1. ✅ Hardened `lib/reliability.sh` with lock, backoff, state, truncation, cycle detection
2. ✅ Extracted shared functions, removed duplication between scripts
3. ✅ 57-assertion unit test suite passing
4. ✅ Structural dry-run passing
5. ✅ Swapped Cursor `agent` CLI to Claude Code `claude` CLI
6. ✅ Fixed agent permissions (`--dangerously-skip-permissions` + settings.local.json)
7. ✅ Added cost/token tracking wrapper (`lib/claude-wrapper.sh`, logs to `$COST_LOG_FILE` as JSONL)
8. ✅ Build summary report (per-feature timing, test counts, token usage)
9. ✅ ONBOARDING.md with mechanical maintenance protocol
10. **Next**: Codebase summary injection (so agents don't redeclare types/interfaces)
11. **Then**: Topological sort for feature ordering (independent features first)
12. **Then**: Local model integration (replace cloud API with local LM Studio on Mac Studio)
13. **Then**: Run build loop against `stakd/` project (28 features, 3 phases)
14. **Later (if needed)**: Adaptive routing / parallelism (deprioritized — see ONBOARDING.md Active Considerations)

---

## How to Orient on a New Chat

If Brian says context was lost, ask him to paste `Agents.md`. That file contains the full agent work log, current file structure, known gaps, and verification checklist. It is the source of truth for repo state. This guide covers methodology; `Agents.md` covers current state.

---

## Session Discipline: Chat vs Agent

**Implementation work** (modifying scripts, lib/, tests, build logic) must be done through **fresh Claude Code agent sessions** — one session per round/prompt, with hardened prompts following the structure in this guide. Never accumulate implementation work across a long-running context. Context degradation over long sessions produces the same class of failures documented in Rounds 1 and 9: scope creep, unreliable self-assessment, and working around problems instead of stopping.

**Planning, analysis, and documentation** (design discussions, edge case analysis, onboarding docs, Agents.md entries, ONBOARDING.md updates) can be done through **chat sessions** (claude.ai with Desktop Commander). The accumulated conversational context is an asset for this kind of work — each exchange builds on the last. But chat sessions should not make implementation changes to the codebase.

**The boundary**: if you're about to modify a script in `scripts/`, a library in `lib/`, or test logic in `tests/`, it should be a hardened agent prompt in a fresh session. If you're updating documentation, analyzing a design question, or maintaining the onboarding protocol, chat is the right tool.

**Why this matters**: Desktop Commander gives chat sessions full filesystem access, making them functionally equivalent to agents but without the safety guardrails (explicit file allowlists, hard constraints, verification gates, `git diff --stat` checks). The temptation to "just make a quick fix" in chat grows as context fills. Resist it. Write the agent prompt instead.
