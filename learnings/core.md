# Core Learnings

> Curated reading list for every fresh session. If you don't know these, you will make a consequential mistake.
>
> This file is a **curated index**, not a filtered view. Entries are selected by human judgment.
> Each entry is a reference to the full entry in its type-specific file.
> Read this file on every fresh onboard. No exceptions.

---

## L-0001 — Agent self-assessments are unreliable
**Source:** `failure-patterns.md`
**Why core:** Foundation of the entire verification architecture. Without this, a session will trust agent self-reports and miss failures.

Agent self-assessments have proven unreliable. Agents report "all verifications passed" while having made changes far beyond scope. The verification block in the prompt should enforce correctness — the agent's narrative summary has not been a reliable signal. Machine-checkable gates (`git diff --stat`, `bash -n`, grep) have been the effective substitute.

---

## L-0005 — Push discipline requires repeated preemptive reminders
**Source:** `failure-patterns.md`
**Why core:** Every prompt-writing session needs this. Single-mention prohibition has 0% success rate.

Agents have consistently failed to check before pushing to remote. Most effective mitigation found: frequent, preemptive reminders throughout the prompt (not just once in Hard Constraints). Placing push prohibition near the top, repeating before any git operation section, and reiterating as the final instruction has reduced but not eliminated violations. Treating every agent run as a push risk has been the practical approach.

---

## L-0011 — Agents work around failures instead of stopping
**Source:** `failure-patterns.md`
**Why core:** Without this, a fresh session won't include STOP instructions in prompts for unexpected situations.

Agents have been observed to work around failures instead of stopping. When blocked (e.g., no GitHub auth), agents have made autonomous decisions that diverge from the intended path — abandoning clones, switching repos, improvising. Hard Constraints must include explicit STOP instructions for ANY unexpected situation.

---

## L-0012 — Client→server import chain (most common build failure)
**Source:** `failure-patterns.md`
**Why core:** Most common post-campaign build failure. Any session touching stakd or Next.js needs this.

Client components transitively importing server-only modules. A `"use client"` component imports an intermediate file that imports the database layer. Webpack bundles the entire chain into the client bundle, which fails. Fix: break the chain. Server data fetching stays in server components or server-only lib files. Client components receive data via props.

---

## L-0016 — Verification gates on every prompt
**Source:** `process-rules.md`
**Why core:** Direct consequence of L-0001. The operational discipline that makes agent output trustworthy.

Every prompt must end with verification gates — `bash -n`, grep, test suite, `git diff --stat`. Agent self-assessment has proven unreliable; machine-checkable gates are the only trustworthy signal.

---

## L-0020 — Session discipline boundary
**Source:** `process-rules.md`
**Why core:** Prevents a fresh chat from "just making a quick fix" and bypassing verification gates.

Implementation work (scripts, lib/, tests) → fresh Claude Code agent session with hardened prompt. Planning, analysis, documentation → chat session. The boundary: if modifying a script in `scripts/`, a library in `lib/`, or test logic in `tests/`, write a hardened agent prompt. If updating docs or analyzing, chat is fine.

---

## L-0026 — Token speed ≠ build speed
**Source:** `empirical-findings.md`
**Why core:** Counterintuitive finding that shapes model selection and parallelism decisions.

Token speed does NOT translate to build speed. Haiku 2x faster tokens but only marginally faster builds (~16-18 min/feature both models) because npm install, TypeScript compile, tests, drift checks are fixed-cost CPU/disk-bound steps. Model speed only affects agent thinking fraction. Parallelism across features matters more than per-feature model speed.

---

## L-0028 — Signal protocol uses grep not JSON
**Source:** `architectural-rationale.md`
**Why core:** Architectural cornerstone. A session that doesn't know this might propose JSON signals and break the protocol.

Agents communicate via flat strings (`FEATURE_BUILT: {name}`, `BUILD_FAILED: {reason}`). No JSON parsing, no eval on agent output. Grep is reliable, available everywhere, and fails visibly. JSON parsing introduces fragility — malformed output from an agent silently breaks downstream logic instead of failing at the grep step.

---

## L-0113 — Checkpoint learnings capture requires active scan
**Source:** `process-rules.md`
**Why core:** Without this, every fresh session runs checkpoint step 4 passively ("anything come to mind?") and under-captures. The gap between step 4 (passive) and step 5 (active scan) caused a session to declare "none new" while skipping agent outcome validation, correction analysis, and near-miss review.

Checkpoint step 4 must actively scan: agent completions (validate/contradict existing learnings?), Brian's corrections (each is a candidate), new rules or patterns, empirical findings, failures or near-misses. Under-capture is a failure mode equal to over-capture. Match capture density to session density.
