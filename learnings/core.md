# Core Learnings

> Curated reading list for every fresh session. If you don't know these, you will make a consequential mistake.
>
> This file is a **curated index**, not a filtered view. Entries are selected by human judgment.
> Each entry is a reference to the full entry in its type-specific file.
> Read this file on every fresh onboard. No exceptions.

## Maintenance

Core learnings are reviewed when:
- A core learning gets full mechanical enforcement (command/checkpoint step). If tool is validated over 3+ sessions, learning can be demoted (stays in category file, removed from core.md and CLAUDE.md).
- A non-core learning is referenced in 3+ separate checkpoint scans → assess promotion.
- Core count exceeds 15 → review, demote least-referenced to keep CLAUDE.md block under 600 tokens.

Promotion and demotion require Brian's approval.

---

## L-00001 — Agent self-assessments are unreliable
**Source:** `failure-patterns.md`
**Why core:** Foundation of the entire verification architecture. Without this, a session will trust agent self-reports and miss failures.

Agent self-assessments have proven unreliable. Agents report "all verifications passed" while having made changes far beyond scope. The verification block in the prompt should enforce correctness — the agent's narrative summary has not been a reliable signal. Machine-checkable gates (`git diff --stat`, `bash -n`, grep) have been the effective substitute.

---

## L-00005 — Push discipline requires repeated preemptive reminders
**Source:** `failure-patterns.md`
**Why core:** Every prompt-writing session needs this. Single-mention prohibition has 0% success rate.

Agents have consistently failed to check before pushing to remote. Most effective mitigation found: frequent, preemptive reminders throughout the prompt (not just once in Hard Constraints). Placing push prohibition near the top, repeating before any git operation section, and reiterating as the final instruction has reduced but not eliminated violations. Treating every agent run as a push risk has been the practical approach.

---

## L-00011 — Agents work around failures instead of stopping
**Source:** `failure-patterns.md`
**Why core:** Without this, a fresh session won't include STOP instructions in prompts for unexpected situations.

Agents have been observed to work around failures instead of stopping. When blocked (e.g., no GitHub auth), agents have made autonomous decisions that diverge from the intended path — abandoning clones, switching repos, improvising. Hard Constraints must include explicit STOP instructions for ANY unexpected situation.

---

## L-00012 — Client→server import chain (most common build failure)
**Source:** `failure-patterns.md`
**Why core:** Most common post-campaign build failure. Any session touching stakd or Next.js needs this.

Client components transitively importing server-only modules. A `"use client"` component imports an intermediate file that imports the database layer. Webpack bundles the entire chain into the client bundle, which fails. Fix: break the chain. Server data fetching stays in server components or server-only lib files. Client components receive data via props.

---

## L-00016 — Verification gates on every prompt
**Source:** `process-rules.md`
**Why core:** Direct consequence of L-00001. The operational discipline that makes agent output trustworthy.

Every prompt must end with verification gates — `bash -n`, grep, test suite, `git diff --stat`. Agent self-assessment has proven unreliable; machine-checkable gates are the only trustworthy signal.

---

## L-00020 — Session discipline boundary
**Source:** `process-rules.md`
**Why core:** Prevents a fresh chat from "just making a quick fix" and bypassing verification gates.

Implementation work (scripts, lib/, tests) → fresh Claude Code agent session with hardened prompt. Planning, analysis, documentation → chat session. The boundary: if modifying a script in `scripts/`, a library in `lib/`, or test logic in `tests/`, write a hardened agent prompt. If updating docs or analyzing, chat is fine.

---

## L-00028 — Signal protocol uses grep not JSON
**Source:** `architectural-rationale.md`
**Why core:** Architectural cornerstone. A session that doesn't know this might propose JSON signals and break the protocol.

Agents communicate via flat strings (`FEATURE_BUILT: {name}`, `BUILD_FAILED: {reason}`). No JSON parsing, no eval on agent output. Grep is reliable, available everywhere, and fails visibly. JSON parsing introduces fragility — malformed output from an agent silently breaks downstream logic instead of failing at the grep step.

---

## L-00113 — Checkpoint learnings capture requires active scan
**Source:** `process-rules.md`
**Why core:** Without this, every fresh session runs checkpoint step 4 passively ("anything come to mind?") and under-captures. The gap between step 4 (passive) and step 5 (active scan) caused a session to declare "none new" while skipping agent outcome validation, correction analysis, and near-miss review.

Checkpoint step 4 must actively scan: agent completions (validate/contradict existing learnings?), Brian's corrections (each is a candidate), new rules or patterns, empirical findings, failures or near-misses. Under-capture is a failure mode equal to over-capture. Match capture density to session density.

---

## L-00116 — "Nothing to capture" is never the correct default
**Source:** `process-rules.md`
**Why core:** L-00113 added scan categories but the very next checkpoint still under-captured because the default assumption didn't flip. Without this, a session can walk through all five categories and still conclude "none new" because it's looking for reasons to include rather than reasons to skip. This is the behavioral root that makes L-00113 work or fail.

"Nothing to capture" must never be the default assumption. The default is "something to capture" — the scan must find reasons to skip, not reasons to include. A scan that reviews every category and finds zero candidates in a session with agent completions, corrections, and system improvements is evidence of the scan failing, not evidence of nothing to capture.

---

## L-00125 — Scan existing project assets before building new process infrastructure
**Source:** `architectural-rationale.md`
**Why core:** The checkpoint/learnings system was built without checking what slash commands and conventions files already existed. Four commands already had reusable patterns (`/catch-drift`, `/check-coverage`, `/update-test-docs`, `/verify-test-counts`). CLAUDE.md — the file every Claude Code agent reads — pointed to the old learnings location (`.specs/learnings/`) while the new system lived in `learnings/`. `/compound` wrote to the wrong place. Any process change must audit: (1) existing commands for reusable patterns, (2) CLAUDE.md and other conventions files for references the change invalidates, (3) existing tooling that can be wired in mechanically instead of rebuilt.


---

## L-00130 — Design for context loss as the default
**Source:** `architectural-rationale.md`
**Why core:** Context windows compact, sessions end, responses fail mid-stream. The only state that survives is file state. A fresh session that doesn't know this will keep plans, progress, and work-in-progress in context only — then lose it. Self-test (checkpoint step 9): "If context dies now, can the next session resume from files alone?" Check: `.onboarding-state` current? `ACTIVE-CONSIDERATIONS.md` accurate? Work committed? Multi-response plans externalized? If no — fix before responding.

---

## L-00143 — Scope sizing ritual before every prompt/response/agent run
**Source:** `process-rules.md`
**Why core:** Repeated scope failures (L-00127, L-00131, L-00142) prove that unbounded work units hit context limits, mix verification methods, and create debugging surface area. Without this, a fresh session will bundle independent changes into one agent prompt, exceed token budgets, or attempt verification that spans multiple unrelated concerns. The scope sizing ritual — count items, estimate tokens, check verification isolation, split or proceed — is the operational discipline that prevents these failures. Token budget estimation and continuous calibration from actuals apply project-wide.

---

## L-00162 — Estimation without computation is decoration
**Source:** `failure-patterns.md`
**Why core:** Complements L-00143. L-00143 says do the ritual; L-00162 says a number without arithmetic isn't a ritual — it's theater. Three estimates in one session ("8.5%", "~12k", "well within bounds") were stated, accepted, and all wrong. Each looked computed — formatted with units, placed in an Estimate section — but none showed the math. Without this, a session follows L-00143's form (has a Scope Estimate section) but not its substance (the section contains a guess, not a calculation).

---

## L-00163 — Learnings must be self-contained, system-legible, and actionable
**Source:** `process-rules.md`
**Why core:** Quality gate for the entire knowledge base. Every entry is read by future instances with no session context. Jargon, missing context, or vague observations make entries dead weight. Three requirements: (1) define or avoid jargon — use plain descriptions; (2) include enough context to be understood without reading other entries; (3) state a concrete countermeasure, not just an observation. Without this, the learnings corpus grows but its utility per entry decays.

---

## M-00087 — Checkpoint is the primary value-preservation mechanism
**Source:** `HOW-I-WORK-WITH-GENERATIVE-AI.md`
**Why core:** A session that treats checkpoint as administrative overhead will shortcut it — skipping learnings, methodology signals, and state flushes. This was observed directly: steps 2-6 skipped, 7 L-candidates and 3 M-candidates missed. The checkpoint isn't bookkeeping. It's how observations, patterns, corrections, and calibration data survive context boundaries. A session that produces good work but shortcuts the checkpoint is strictly worse than one that does less work but preserves it fully. Brian flagged both the missed steps AND the learnings deficit as equal-severity failures.

---

## L-00175 — Prefer mechanical validation over agent invocation for structural comparison
**Source:** `architectural-rationale.md`
**Why core:** Without this, a fresh session will default to dispatching an agent for every pipeline phase, including tasks that are pure data comparison. The distinction — agents for judgment, Python for structure — cuts phase execution time from minutes to milliseconds, eliminates parsing failure risk, and reduces API cost to zero for those phases. Applied in Phase 2b (gap detection) and Phase 4a (failure catalog). The heuristic: if you can write the function without an LLM, you should.

---

## L-00178 — Chat sessions must gate-check elaborate prompt work against problem layer
**Source:** `process-rules.md`
**Why core:** Without this, a chat session will help build an elaborate agent prompt without questioning whether prompting is the right solution layer. Observed directly: a prior session built a 377-line prompt with 62 constraint patterns and a detection+injection pipeline to prevent transitive import violations — when the actual root cause was a 10-line detection ordering bug in build_gates.py. **300-line rule**: if any single solution's prompt content would exceed 300 lines, the chat must stop, enumerate at least two non-prompting alternatives (build gate, linter, test, existing tooling), and validate that no mechanical alternative exists before proceeding. The gate-check: "Does a build tool, linter, test, or existing gate already enforce this constraint? If yes, ensure it runs." Mechanical enforcement: `MAX_INJECTED_SECTION_LINES` (150) and `MAX_TOTAL_PROMPT_LINES` (400) in prompt_builder.py, asserted at test time. Never blocking at runtime.
