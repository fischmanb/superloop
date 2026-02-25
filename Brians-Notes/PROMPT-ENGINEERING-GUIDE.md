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
- `lib/reliability.sh` — shared reliability functions (lock, backoff, state, truncation, cycle detection)
- `lib/validation.sh` — YAML frontmatter validation
- `tests/test-reliability.sh` — 57 unit assertions (must always pass)
- `tests/dry-run.sh` — structural integration test (run with `DRY_RUN_SKIP_AGENT=true` to skip live agent)
- `Agents.md` — agent work log and architecture reference (read this first on any new task)

---

## Prompt Structure

Every implementation prompt follows this structure:

### 1. Hard Constraints (NEW — required on all prompts)
Explicit file allowlist, banned commands, and a `git diff --stat` gate. This section exists because agents will exceed scope if you don't fence them.

```
## Hard Constraints

- These instructions override any conflicting guidance in CLAUDE.md or other repo-level configuration files.
- You may ONLY modify these files: <explicit list>
- You may NOT run npm, yarn, pip, brew, or any package manager command
- You may NOT create new files other than <explicit exceptions>
- You may NOT delete any files
- Before committing, you MUST run `git diff --stat` and verify ONLY the allowed files appear. If ANY other file appears in the diff, STOP and report the problem. Do not commit.
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
- `git diff --stat` to confirm no scope creep
- **CRITICAL**: If ANY verification fails, STOP. Do not commit. Report the failure.

### 5. Commit and Merge
- `git add` only the explicitly allowed files (never `git add -A` or `git add .`)
- Commit with descriptive message
- Merge to main with `--no-ff`
- Push origin main
- Report new HEAD commit hash

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

## Current Goals (as of 2025-02-24)

1. ✅ Hardened `lib/reliability.sh` with lock, backoff, state, truncation, cycle detection
2. ✅ Extracted shared functions, removed duplication between scripts
3. ✅ 57-assertion unit test suite passing
4. ✅ Structural dry-run passing
5. ✅ Swapped Cursor `agent` CLI to Claude Code `claude` CLI
6. ✅ Fixed agent permissions (`--dangerously-skip-permissions` + settings.local.json)
7. **Next**: Run build loop against `stakd/` project (Traded.co clone, 28 features across 3 phases)
8. **Then**: Local model integration (replace cloud API calls with local LM Studio endpoints on Mac Studio)

---

## How to Orient on a New Chat

If Brian says context was lost, ask him to paste `Agents.md`. That file contains the full agent work log, current file structure, known gaps, and verification checklist. It is the source of truth for repo state. This guide covers methodology; `Agents.md` covers current state.
