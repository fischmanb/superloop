# Core Learnings — Constitutional Read for Fresh Sessions

> Curated from L-0042–L-0103 (agent-operations.md). These are the entries that, when not internalized, cause repeated failures. A fresh session reads this at onboard; the full catalog is in agent-operations.md.
>
> Last curated: 2026-03-01 (62 total entries, 16 selected here)

---

## Response Discipline

**L-0092 — Prompt stash first.** First action every response: write Brian's prompt to `.prompt-stash.json` (replace previous). Then read `.onboarding-state`, increment `prompt_count`, scan for captures, write state. Then proceed. This order is non-negotiable — it survives compaction and truncation.

**L-0074 / L-0078 — Admin before content.** Protocol steps (counter, captures, hashes) get skipped under cognitive load — exactly when they matter most. Do admin FIRST in each response. If it's skippable when busy, it's not a protocol. Prescriptive order: (1) stash prompt, (2) read state, (3) increment count, (4) scan for captures, (5) write state, (6) proceed.

**L-0098 / L-0103 — Scope discipline.** Two truncations in one session. Count work items BEFORE the first tool call. >3 distinct items or >15 tool calls = split across responses. Checkpoint alone is ~12 calls. Truncation loses work; splitting is free. Knowing the rule isn't the same as following it — L-0103 happened ONE response after L-0098 was written.

**L-0063 — Enumerate before acting.** Before acting on any message, enumerate all learnable moments. Count them. Capture all. Then proceed. Brian should never have to ask "where are my learnings?" — capture-completeness check happens before response, not after correction.

---

## Agent Operations

**L-0042 — Prescribe only failure-prone areas.** Convention docs and agent prompts prescribe only where agents would high-percentage get it wrong. Over-prescription wastes context budget. Agent autonomy structure: test→investigate→evaluate→verify→report.

**L-0058 — Agents never write learnings.** Agents surface observations in summaries. The chat session triages agent observations into L-IDs and flags for Brian at checkpoint. This preserves the approval gate. Agent prompts should include a summary footer requesting notable observations.

**L-0050 — HEAD sequencing.** Don't output agent prompts before commits that move HEAD. The prompt references a commit hash; if you then make more commits, the hash is stale. Fix: output prompt AFTER all HEAD-moving actions, or warn "wait — more commits coming" BEFORE the prompt block.

**L-0066 — No rule gaming.** Labeling non-checkpoint commits as "checkpoint:" to exploit the auto-push exception = gaming. A checkpoint is the formal 8-step protocol Brian invokes. The narrow exception cannot be widened unilaterally by relabeling. When Brian hasn't said "checkpoint" or "yes," ask.

---

## Evidence & Instruction Processing

**L-0046 / L-0062 / L-0082 — Process all provided input.** Three instances of the same failure: ignoring attached images, not reading provided evidence, not following explicit browse instructions. Images are input, not decoration. When Brian attaches something, examine it. When Brian says "browse X," browse X. Asserting facts without verifying against provided context is the root cause every time.

---

## System Architecture

**L-0097 — Memory triggers, repo specifies.** Memory (always-injected, ~1,500 words) and repo learnings (loaded at onboard, queryable) are one system. Memory provides triggers that cause the session to consult repo for details. Example: memory says "follow onboarding state protocol," repo says exactly how. Memory should never contain what repo specifies. Repo shouldn't duplicate what memory triggers.

**L-0093 — Checkpoint is compaction defense.** Committed work survives compaction. Conversational context doesn't. During this session, compaction hit during a checkpoint — everything committed was preserved, everything in-flight was lost. When you sense a long response or heavy work, checkpoint first.

---

## Meta-Process

**L-0096 — Lucidity windows.** "I may not be this lucid tomorrow" = asymmetric opportunity. When Brian is in systematic process mode, maximize capture density. These sessions are rare — Brian usually runs feature work. Compound returns from process investment are high.

**L-0102 — Process sessions compound.** This session (2026-03-01) produced 62 learnings, handoff protocol, retiring-chat protocol, dual-storage strategy — all infrastructure. Every future session that reads core.md, checks .handoff.md, follows checkpoint protocol operates on this foundation.
