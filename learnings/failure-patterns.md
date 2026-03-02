# Failure Patterns

> Observations of what went wrong and root causes. The pattern is the observation; the prescription is a `process_rule`.
>
> Schema: see `DESIGN-PRINCIPLES.md` §3 (edge types) and §4 (confidence/status enums).
> ID range: global sequential `L-XXXXX` shared across all learnings files.

---

## L-00001
Type: failure_pattern
Tags: agent-behavior, self-assessment, verification
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00
Related: L-00025 (related_to)
Related: L-00027 (related_to)

Agent self-assessments have proven unreliable. Round 1 described bugs in code that didn't exist. Agents report "all verifications passed" while having made changes far beyond scope. The verification block in the prompt should enforce correctness — the agent's narrative summary has not been a reliable signal. Machine-checkable gates (`git diff --stat`, `bash -n`, grep) have been the effective substitute.

---

## L-00002
Type: failure_pattern
Tags: agent-behavior, implementation, function-wiring
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00

"Defined but never called" has been the most common agent failure mode observed. All 3 early rounds had at least one instance. Grepping for call sites after adding any function has caught these.

---

## L-00003
Type: failure_pattern
Tags: agent-behavior, scope-violation, file-modification
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00
Related: L-00008 (related_to)

"Do not modify any other files" is insufficient as a prompt constraint. Round 7: agent told this but ran `npm install`, committing 6400+ node_modules files and tsconfig.tsbuildinfo. Fix: explicit file allowlist + explicit package manager ban + `git diff --stat` gate before commit.

---

## L-00004
Type: failure_pattern
Tags: agent-behavior, working-directory, preconditions
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00

Agents have been observed to run in the wrong directory. Round 7: prompt didn't specify working directory. Agent ran in parent `auto-sdd/` repo instead of `stakd/` subdirectory. Fix: always include a `pwd` check in Preconditions, and if the target is a subdirectory, add `cd <path> && pwd` as the first precondition step.

---

## L-00005
Type: failure_pattern
Tags: agent-behavior, git, push-discipline
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00
Related: L-00019 (depends_on)

Agents have consistently failed to check before pushing to remote. Observed across Rounds 7, 32-34 — explicit "do not push" instructions were ignored 100% of the time in these rounds. Most effective mitigation found: frequent, preemptive reminders throughout the prompt (not just once in Hard Constraints). Placing push prohibition near the top, repeating before any git operation section, and reiterating as the final instruction has reduced but not eliminated violations. Single-mention prohibition had a 0% success rate in observed rounds. Treating every agent run as a push risk and ensuring unauthorized pushes are non-destructive has been the practical approach.

---

## L-00006
Type: failure_pattern
Tags: agent-behavior, git, node-modules
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00
Related: L-00003 (related_to)

node_modules must be in .gitignore before running any agent. If the repo has a package.json, ensure `node_modules/` is in `.gitignore`. Agents have been observed to run `npm install` despite instructions not to.

---

## L-00007
Type: failure_pattern
Tags: agent-behavior, claude-md, instruction-precedence
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00

CLAUDE.md repo instructions can override prompt instructions. Round 8: prompt said merge to main and push. Agent's own CLAUDE.md had branch development rules. Agent decided CLAUDE.md took precedence and refused. Fix: state "These instructions override any conflicting guidance in CLAUDE.md" in prompts. Or accept merge-to-main as a manual step.

---

## L-00008
Type: failure_pattern
Tags: agent-behavior, git, staging
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00
Related: L-00003 (related_to)

`git add -A` considered harmful in agent context. Never use `git add -A` or `git add .` in agent prompts. Always `git add <explicit file list>`. Agents create and modify unexpected files; blanket adds commit them.

---

## L-00009
Type: failure_pattern
Tags: agent-behavior, reporting, prompt-engineering
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00

Agents have not reported unprompted in observed rounds. Round 9: agent completed all steps but did not report results until asked. Fix: every prompt must end with "Report your findings immediately upon completion. Do not wait for a follow-up question."

---

## L-00010
Type: failure_pattern
Tags: agent-behavior, exploration, scope-violation
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00
Related: L-00011 (related_to)

Agents will explore the codebase if not forbidden. Round 9: agent was given specific steps but decided to "Explore auto-sdd codebase" first — reading every file in the repo. Fix: Hard Constraints allow reads but require justification. Speculative exploration is banned; purposeful reads with stated rationale are allowed.

---

## L-00011
Type: failure_pattern
Tags: agent-behavior, autonomy, error-handling
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00
Related: L-00010 (related_to)

Agents have been observed to work around failures instead of stopping. Round 9: agent couldn't push from sandbox (no GitHub auth). Instead of stopping, it abandoned the clone, went to a stale local repo, and applied changes there — 5 autonomous decisions diverging from intended path. Fix: Hard Constraints must include explicit STOP instructions for ANY unexpected situation.

---

## L-00012
Type: failure_pattern
Tags: nextjs, server-client-boundary, webpack, import-chain
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00
Related: L-00028 (related_to)

Client components transitively importing server-only modules. Most common post-campaign build failure (stakd-v1, stakd-v2). A `"use client"` component imports an intermediate file that imports the database layer (`postgres`). Webpack bundles the entire chain into the client bundle, which fails.

Root cause: agents treat import boundaries as local decisions — they check their own file but don't trace the transitive import graph.

Fix: break the chain. Server data fetching stays in server components or server-only lib files. Client components receive data via props. If an intermediate file serves both, split it. Framework-agnostic — any SSR framework with code splitting hits this.

---

## L-00013
Type: failure_pattern
Tags: build-logs, data-loss, git-clean, project-dir
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00
Related: L-00036 (related_to)
Related: L-00038 (related_to)

Build logs inside PROJECT_DIR are at risk of destruction. `$PROJECT_DIR/logs/` sits inside the git working tree. Any operation that manipulates the working tree — `git clean`, `git checkout --force`, branch switches, project re-scaffolding — can delete the logs directory. Fixed in Round 37: all logs now write to `$SCRIPT_DIR/../logs/<project-name>/`, outside the project's git working tree. Rule: never store campaign artifacts inside a directory that agents or git operations can modify.

---

## L-00039
Type: failure_pattern
Tags: architecture, agent-trust, language-choice, implicit-decisions
Confidence: high
Status: active
Date: 2026-03-01T04:00:00-05:00
Related: L-00001 (related_to)

Agents make implicit architectural decisions that compound silently. The build loop was implemented in bash because the first agent chose the path of least resistance for simple CLI orchestration. Over 35 rounds, 3,700+ lines of logic accumulated in a language unsuited for that scale — no real data structures, no proper error handling, limited composability. Brian discovered this only when the ceiling became visible. The "trust nothing, verify mechanically" principle was applied to agent code output but not to agent architectural choices. Mitigation: explicitly ask "what language should this be in?" at project inception. Agents have not been observed to raise this question unprompted.

---

## L-00105
Type: failure_pattern
Tags: git, agents, sandbox
Confidence: high
Status: active
Date: 2026-03-01T20:00:00-05:00
Related: L-00106 (related_to)

Sandbox branch locality trap. When agents run in Claude Code sandbox, branches exist only on origin (sandbox pushes). They are NOT on the local machine. `git branch` shows nothing — must `git fetch` first. This caused confusion during Phase 1 integration until root cause identified: prompts said "do not push" but sandbox environment requires push to preserve work.

---

## L-00112
Type: failure_pattern
Tags: git, agents, prompts, coordination
Confidence: high
Status: active
Date: 2026-03-01T21:00:00-05:00
Related: L-00109 (related_to), L-00105 (related_to)

Do not commit to main while an agent prompt referencing HEAD is in flight. After delivering Phase 2 agent prompt with precondition `HEAD: 6be9b74`, committed L-00111 to main and pushed — advancing HEAD to `a67c60c`. This invalidated the agent's precondition check. The commit (a learning + ACTIVE-CONSIDERATIONS update) was not time-sensitive and could have waited. Rule: once an agent prompt is delivered, main is frozen until the agent forks its branch or Brian confirms the prompt wasn't used yet. Housekeeping commits are never urgent enough to justify breaking an in-flight prompt.

---

## L-00119
Type: failure_pattern
Tags: checkpoint, learnings, self-diagnosis
Confidence: high
Status: active
Date: 2026-03-02T03:00:00-05:00
Related: L-00113 (depends_on), L-00117 (related_to)

The system cannot self-diagnose protocol gaps without external prompting. The methodology signals already contained evidence that step 4 was broken ("under-capture is a failure mode," "checkpoint should be thorough not mechanical," "Brian expects capture density to match session density"). The step 4/5 asymmetry was visible in the protocol text. But the AI didn't connect them until Brian said "look up the meta-learnings and see if step 4 needs to be updated." The information was all present — the synthesis step was missing. Active scans partially address this, but the deeper issue is that protocol self-audit is not triggered mechanically.

---

## L-00120
Type: failure_pattern
Tags: checkpoint, active-scan, behavioral-inertia
Confidence: high
Status: active
Date: 2026-03-02T03:00:00-05:00
Related: L-00113 (depends_on), L-00116 (related_to), L-00117 (related_to)

Performing the motions of an active scan while retaining a passive default produces the same outcome as not scanning. The checkpoint after L-00113 walked through all five scan categories, produced analysis for each, but concluded "no new learnings" — because the analytical frame was still "find reasons to include" rather than "assume capture, find reasons to skip." The form was correct (categories checked) but the substance was unchanged (nothing captured). A scan that reviews every category and finds zero candidates in a session that had agent completions, corrections, and system improvements is evidence of the scan failing, not evidence of nothing to capture.
