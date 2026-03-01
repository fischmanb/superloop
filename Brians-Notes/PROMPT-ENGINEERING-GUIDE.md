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
- Follow the numbered steps in this prompt IN ORDER. Do not explore or investigate files speculatively. The steps describe what to build; read what you need to build it.
- You may ONLY modify these files: <explicit list> (always include Agents.md for implementation prompts — agents write their own round entry)
- You may ONLY create these new files: <explicit list, or "none">
- You may NOT run npm, yarn, pip, brew, or any package manager command
- You may NOT delete any files
- You may read any file in the repo that you determine is necessary to implement this task. Before reading any file, state which file and why. Do not explore the codebase speculatively — read only what you need for the specific task.
- If you are unsure whether you need to read a file, STOP IMMEDIATELY. Explain to the user why you stopped and why you believe you may need the file. Do not continue working or touch any other file until the user responds. If you cannot articulate why you need a file, you do not need it.
- If you encounter ANYTHING unexpected — files not matching descriptions, commands not found, structure differences, unfamiliar patterns — STOP IMMEDIATELY. Do not attempt to fix, adapt, or work around the issue. Report exactly what you found and take no further action.
- If ANY verification step or test fails, STOP IMMEDIATELY. Do not commit. Do not attempt to fix. Report the failure and take no further action.
- Before committing, you MUST run `git diff --stat` and verify ONLY the allowed files appear. If ANY other file appears, STOP and report the problem. Do not commit.
```

### 2. Preconditions
Agents have landed on wrong branches and wrong commits multiple times. Preconditions must be defensive — verify state, don't assume it.

- `cd ~/auto-sdd` (explicit, not assumed)
- `git checkout main` (explicit — agents default to whatever branch is checked out)
- `git log --oneline -1` — confirm HEAD matches the expected commit hash. **Always include the expected hash in the prompt.** If it doesn't match, STOP.
- Confirm file state if the task targets specific lines (e.g., `wc -l`, `grep -c` for a known pattern). If it doesn't match, STOP.
- `git fetch origin`
- **Verify local main is pushed**: `git log --oneline origin/main..main` — if this shows ANY commits, STOP IMMEDIATELY. Local main is ahead of origin/main. Report the divergence and take no further action. Brian must `git push origin main` before the prompt can proceed.
- `git checkout -b claude/<branch-name>-$(openssl rand -hex 3)`
- Report which branch was forked from and the HEAD hash

### 3. Implementation
- Specific, line-level instructions for each file change
- "Touch NOTHING else in this file" after each change
- Agents.md round entry with: what was asked, what was changed, what was NOT changed, verification results

### 4. Verification
- `bash -n` syntax checks on modified scripts
- grep to confirm expected changes exist
- `cat` to verify file contents
- Run **ALL** test suites — every prompt must include all five:
  ```bash
  ./tests/test-reliability.sh
  ./tests/test-eval.sh
  ./tests/test-validation.sh
  ./tests/test-codebase-summary.sh
  DRY_RUN_SKIP_AGENT=true ./tests/dry-run.sh
  ```
  Do not cherry-pick which suites to run. A change to any file can break any suite. Run all five, every time.
- `git diff --stat` to confirm no scope creep
- **CRITICAL**: If ANY verification step or test fails, STOP IMMEDIATELY. Do not continue. Do not commit. Do not attempt to fix. Report the failure and take no further action.

### 5. Commit (no merge)
- `git add` only the explicitly allowed files (never `git add -A` or `git add .`)
- Commit with descriptive message to your feature branch
- Do NOT merge to main — Brian merges manually after verification
- Do NOT push — Brian pushes manually from his machine (sandbox lacks GitHub auth)
- Report the branch name and commit hash

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

**Length discipline**: First drafts of prompts are consistently ~2x the effective length. This is a known pattern — cut aggressively before delivering. Describe intent, not implementation code. Agents write code; prompts tell them *what* to change and *why*, not *how* at the line level. If you're writing bash/code snippets in the prompt body, you're being too prescriptive — the agent has the codebase and can read it. Exception: short verification commands (grep, sed -n) that confirm the agent is looking at the right lines.

**Context budget rule**: Every prompt must be scoped so the agent's total context consumption — prompt text + files read + code written + tool output + verification — stays within the safely effective context window (no degradation or rot). Estimate this before delivering the prompt. If the estimated total scope would exceed ~75% of the effective window, split into multiple rounds. For example: if a task estimates at ~1.5x the safe window, split into two rounds each targeting ~0.75x, not one round that pushes the boundary. Agents that run hot against the context ceiling produce the "wait, actually..." pattern — repeated self-corrections, lost constraints, and unreliable output. The cost of a second round is near zero; the cost of context rot is a wasted run.

**Rule of thumb**: A single implementation prompt should target one cohesive unit of work that modifies no more than 3-4 files with interrelated changes. When a task exceeds this, split it into sequential prompts where each round commits its work and the next round builds on a verified foundation.

**Splitting criteria** (any one of these warrants a split):
- Estimated total agent context consumption exceeds ~75% of the safe effective window
- More than ~4 files being modified with non-trivial changes in each
- Changes to core orchestration logic AND a new algorithm/function AND test additions AND prompt template rewrites in the same prompt
- The prompt itself exceeds ~200 lines (the prompt is consuming the agent's context budget before implementation starts)
- Changes span two independently testable systems (e.g., build-loop-local.sh and overnight-autonomous.sh)
- You find yourself writing "also do X" after the main implementation is already fully specified

**How to split**: Each sub-prompt is a full Round with its own branch, Hard Constraints, Implementation, Verification, and Agents.md entry. The second prompt's Preconditions include verifying that the first round's commit exists and tests pass. This is strictly better than one large prompt because each round gets verified independently — a failure in round N doesn't contaminate round N+1's context.

**Anti-pattern**: "Let's just add one more thing to the prompt since the agent is already in there." This is how Round 1-class failures happen. The marginal cost of a fresh agent session is near zero. The marginal risk of scope creep in a bloated prompt is high.

---

## Merge Prompts

Merge prompts are a separate prompt type used ONLY when Brian explicitly requests a merge via agent. Standard implementation prompts never merge — agents commit to their feature branch and Brian merges manually.

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

Consolidated into `.specs/learnings/agent-operations.md` — the single source of truth for all agent failure modes, process lessons, and session discipline rules. Read the "Failure Catalog" and "Operational Process Lessons" sections there.

## Design Principles

See `DESIGN-PRINCIPLES.md` in the repo root. Project-wide constraints on grepability, graph-readiness, and relationship type schema.

**When this matters for prompts**: If a prompt instructs an agent to produce structured output — failure catalogs, eval results, learnings, state files, spec metadata — the prompt should encode the format expectations from the design principles. Specifically: flat greppable metadata, unique IDs on knowledge entries, explicit relationships using the defined edge types. If the agent is just building features, the principles don't apply to its prompt.

---

## Pending Fixes to Propagate

See `.specs/learnings/agent-operations.md` → "Grep comment-filter fix" under Operational Process Lessons.

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
