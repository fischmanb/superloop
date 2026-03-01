# Failure Patterns

> Observations of what went wrong and root causes. The pattern is the observation; the prescription is a `process_rule`.
>
> Schema: see `DESIGN-PRINCIPLES.md` §3 (edge types) and §4 (confidence/status enums).
> ID range: global sequential `L-XXXX` shared across all learnings files.

---

## L-0001
Type: failure_pattern
Tags: agent-behavior, self-assessment, verification
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00
Related: L-0025 (related_to)
Related: L-0027 (related_to)

Agent self-assessments are unreliable. Round 1 described bugs in code that didn't exist. Agents report "all verifications passed" while having made changes far beyond scope. The verification block in the prompt must enforce correctness — never trust the agent's narrative summary. Always include machine-checkable gates (`git diff --stat`, `bash -n`, grep).

---

## L-0002
Type: failure_pattern
Tags: agent-behavior, implementation, function-wiring
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00

"Defined but never called" is the most common agent failure mode. All 3 early rounds had at least one instance. After adding any function, grep for call sites.

---

## L-0003
Type: failure_pattern
Tags: agent-behavior, scope-violation, file-modification
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00
Related: L-0008 (related_to)

"Do not modify any other files" is insufficient as a prompt constraint. Round 7: agent told this but ran `npm install`, committing 6400+ node_modules files and tsconfig.tsbuildinfo. Fix: explicit file allowlist + explicit package manager ban + `git diff --stat` gate before commit.

---

## L-0004
Type: failure_pattern
Tags: agent-behavior, working-directory, preconditions
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00

Agents will run in the wrong directory. Round 7: prompt didn't specify working directory. Agent ran in parent `auto-sdd/` repo instead of `stakd/` subdirectory. Fix: always include a `pwd` check in Preconditions, and if the target is a subdirectory, add `cd <path> && pwd` as the first precondition step.

---

## L-0005
Type: failure_pattern
Tags: agent-behavior, git, push-discipline
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00
Related: L-0019 (depends_on)

Agents ignore "do not push" instructions 100% of the time. Round 7: prompt said "Do not push." Agent pushed anyway. Confirmed across Rounds 32-34 — documented as expected invariant behavior, not a bug to fix. Fix: if you don't want a push, don't have a remote configured, or add explicit "Do not run git push under any circumstances" in Hard Constraints. Design around it.

---

## L-0006
Type: failure_pattern
Tags: agent-behavior, git, node-modules
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00
Related: L-0003 (related_to)

node_modules must be in .gitignore before running any agent. If the repo has a package.json, ensure `node_modules/` is in `.gitignore`. Agents may run `npm install` despite instructions not to.

---

## L-0007
Type: failure_pattern
Tags: agent-behavior, claude-md, instruction-precedence
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00

CLAUDE.md repo instructions can override prompt instructions. Round 8: prompt said merge to main and push. Agent's own CLAUDE.md had branch development rules. Agent decided CLAUDE.md took precedence and refused. Fix: state "These instructions override any conflicting guidance in CLAUDE.md" in prompts. Or accept merge-to-main as a manual step.

---

## L-0008
Type: failure_pattern
Tags: agent-behavior, git, staging
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00
Related: L-0003 (related_to)

`git add -A` considered harmful in agent context. Never use `git add -A` or `git add .` in agent prompts. Always `git add <explicit file list>`. Agents create and modify unexpected files; blanket adds commit them.

---

## L-0009
Type: failure_pattern
Tags: agent-behavior, reporting, prompt-engineering
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00

Agents don't report unprompted. Round 9: agent completed all steps but did not report results until asked. Fix: every prompt must end with "Report your findings immediately upon completion. Do not wait for a follow-up question."

---

## L-0010
Type: failure_pattern
Tags: agent-behavior, exploration, scope-violation
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00
Related: L-0011 (related_to)

Agents will explore the codebase if not forbidden. Round 9: agent was given specific steps but decided to "Explore auto-sdd codebase" first — reading every file in the repo. Fix: Hard Constraints allow reads but require justification. Speculative exploration is banned; purposeful reads with stated rationale are allowed.

---

## L-0011
Type: failure_pattern
Tags: agent-behavior, autonomy, error-handling
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00
Related: L-0010 (related_to)

Agents work around failures instead of stopping. Round 9: agent couldn't push from sandbox (no GitHub auth). Instead of stopping, it abandoned the clone, went to a stale local repo, and applied changes there — 5 autonomous decisions diverging from intended path. Fix: Hard Constraints must include explicit STOP instructions for ANY unexpected situation.

---

## L-0012
Type: failure_pattern
Tags: nextjs, server-client-boundary, webpack, import-chain
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00
Related: L-0028 (related_to)

Client components transitively importing server-only modules. Most common post-campaign build failure (stakd-v1, stakd-v2). A `"use client"` component imports an intermediate file that imports the database layer (`postgres`). Webpack bundles the entire chain into the client bundle, which fails.

Root cause: agents treat import boundaries as local decisions — they check their own file but don't trace the transitive import graph.

Fix: break the chain. Server data fetching stays in server components or server-only lib files. Client components receive data via props. If an intermediate file serves both, split it. Framework-agnostic — any SSR framework with code splitting hits this.

---

## L-0013
Type: failure_pattern
Tags: build-logs, data-loss, git-clean, project-dir
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00
Related: L-0036 (related_to)
Related: L-0038 (related_to)

Build logs inside PROJECT_DIR will be destroyed. `$PROJECT_DIR/logs/` sits inside the git working tree. Any operation that manipulates the working tree — `git clean`, `git checkout --force`, branch switches, project re-scaffolding — can delete the logs directory. Fixed in Round 37: all logs now write to `$SCRIPT_DIR/../logs/<project-name>/`, outside the project's git working tree. Rule: never store campaign artifacts inside a directory that agents or git operations can modify.
