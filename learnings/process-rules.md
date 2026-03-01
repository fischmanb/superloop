# Process Rules

> Prescriptive operational discipline. Often the fix for a `failure_pattern`.
>
> Schema: see `DESIGN-PRINCIPLES.md` §3 (edge types) and §4 (confidence/status enums).
> ID range: global sequential `L-XXXX` shared across all learnings files.

---

## L-0014
Type: process_rule
Tags: prompt-engineering, agent-behavior, conciseness
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00

Keeping agent prompts concise — describing intent, not implementation code — has produced better results. Prescriptive prompts (pasting exact code to insert) have caused agents to copy without understanding, miss edge cases, and fail when context differs slightly. Intent-based prompts ("add a guard that exits if CLAUDECODE is set") have produced better results because the agent reasons about placement and integration.

---

## L-0015
Type: process_rule
Tags: prompt-engineering, scope, agent-behavior
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00

Scope to ≤3-4 files per round, independently testable. Larger scopes increase agent confusion and make failures harder to diagnose.

---

## L-0016
Type: process_rule
Tags: prompt-engineering, verification, gates
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00
Related: L-0001 (depends_on)

Every prompt must end with verification gates — `bash -n`, grep, test suite, `git diff --stat`. Agent self-assessment has proven unreliable; machine-checkable gates are the only trustworthy signal.

---

## L-0017
Type: process_rule
Tags: git, agent-behavior, origin, merge-conflicts
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00

Push main to origin before running agent prompts. Claude Code agents fork from `origin/main`, not local `main`. Stale origin → merge conflicts after every round. Observed: Rounds 21-23 all forked from stale origin/main.

---

## L-0018
Type: process_rule
Tags: git, approval, permissions
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00

Edit approval ≠ commit approval. Approving a file edit does not implicitly approve committing it. Each operation requires its own explicit "yes." Violation: commit 2f77ea9.

---

## L-0019
Type: process_rule
Tags: git, push-discipline, agent-behavior
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00
Related: L-0005 (depends_on)

Agents should commit locally but not push. Brian pushes to GitHub manually. This is a design constraint, not a fixable behavior — agents ignore push restrictions (see L-0005).

---

## L-0020
Type: process_rule
Tags: session-discipline, agent-sessions, chat-sessions
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00

Implementation work (scripts, lib/, tests) → fresh Claude Code agent session with hardened prompt. Planning, analysis, documentation → chat session (claude.ai with Desktop Commander). The boundary: if modifying a script in `scripts/`, a library in `lib/`, or test logic in `tests/`, write a hardened agent prompt. If updating docs or analyzing, chat is fine.

---

## L-0021
Type: process_rule
Tags: session-discipline, desktop-commander, temptation
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00
Related: L-0020 (depends_on)

Desktop Commander gives chat full filesystem access — making it tempting to "just make a quick fix." Resist. Write the agent prompt instead. Quick fixes in chat bypass the verification gates that catch agent mistakes.

---

## L-0022
Type: process_rule
Tags: grep, verification, comment-filter
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00

Use the corrected grep comment-filter pattern. Verification blocks must use:
```bash
grep -rn "pattern" scripts/ | grep -v ":#\|: #"
```
Not `grep -v "^\s*#"` — that pattern fails because `grep -rn` prepends `filename:linenum:` before the `#`.

---

## L-0023
Type: process_rule
Tags: learnings, organization, repo-structure
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00

Learnings/patterns belong in the main `learnings/` catalog (previously `.specs/learnings/`), not in project-specific directories (e.g., `stakd/.specs/learnings/`). Project-specific dirs only get fixes specific to that build/app.


---

### L-0040
- **Type:** process_rule
- **Tags:** session-discipline, tool-limits
- **Confidence:** high
- **Date:** 2026-02-28T21:30:00-05:00
- **Source:** Brian correction during Phase 0 checkpoint
- **Body:** The 10 tool call limit per response protects against context loss if a response exceeds context window limits. Each tool call must be one logical operation. Batching multiple operations into a single shell command (e.g., `mkdir && touch && git add && commit && push`) games the limit and defeats the purpose. The constraint is on logical operations performed, not literal tool invocations counted.



---

## L-0109
Type: process_rule
Tags: prompts, agents, review
Confidence: high
Status: active
Date: 2026-03-01T20:00:00-05:00
Related: L-0104 (related_to)

Prompt engineering review before execution prevents rework. Brian caught 5 violations in draft prompts before any agent ran: wrong branch naming convention, abbreviated hard constraints missing full template clauses, over-prescribed interfaces (violating L-0045/L-0042), nested markdown inside code blocks, wrong verification scope (bash suites for Python-only changes). Fixing prompts costs minutes; fixing agent output costs full re-runs. Always review prompts against the guide before handing to agents.

---

## L-0110
Type: process_rule
Tags: testing, verification
Confidence: high
Status: active
Date: 2026-03-01T20:00:00-05:00
Related: L-0109 (related_to)

Verification scope must match change scope. Python-only changes need only mypy --strict + pytest. Bash test suites (5 suites) only needed when bash files are modified. Running irrelevant test suites wastes time and creates false confidence signals ("all bash tests pass" is meaningless when no bash changed). Added to PROMPT-ENGINEERING-GUIDE.md as explicit rule.

---

## L-0113
Type: process_rule
Tags: checkpoint, learnings, capture, meta
Confidence: high
Status: active
Date: 2026-03-02T02:30:00-05:00
Related: L-0109 (related_to), L-0016 (related_to)

Checkpoint step 4 (learnings) must use active scan, not passive recall. The original wording "if any surfaced: flag" produced under-capture — a short session was declared "none new" without reviewing agent outcomes, corrections, or near-misses. Step 5 (methodology signals) already had active scan language ("scan session for...") and produced rich output. Step 4 needed the same structure. Active scan categories: agent completions (validate/contradict existing learnings?), Brian's corrections (each is a candidate), new rules or patterns, empirical findings, failures or near-misses. Under-capture is a failure mode equal to over-capture. Match capture density to session density.

---

## L-0114
Type: process_rule
Tags: documentation, propagation, protocol
Confidence: high
Status: active
Date: 2026-03-02T03:00:00-05:00
Related: L-0113 (depends_on)

Protocol changes must propagate to all consumption points. A rule has (at minimum) a definition point (e.g. checkpoint.md), a summary point (e.g. ONBOARDING.md), and a delivery point (e.g. core.md that fresh sessions read). Changing one without the others creates silent drift — the protocol says one thing, the onboarding path teaches another. Discovered when L-0113 was written to checkpoint.md and ONBOARDING.md but not core.md until Brian corrected. Checklist for any protocol change: (1) definition file, (2) ONBOARDING.md summary, (3) core.md if it's a constitutional learning, (4) any ACTIVE-CONSIDERATIONS references.

---

## L-0115
Type: process_rule
Tags: documentation, counts, staleness, maintenance
Confidence: high
Status: active
Date: 2026-03-02T03:00:00-05:00
Related: L-0114 (related_to)

Numeric references in documentation rot silently. ONBOARDING.md said "38 entries" when actual was 57. ACTIVE-CONSIDERATIONS said "63 graph-compliant" and "~47 old-format" — both wrong. Nobody noticed because prose ages gracefully but numbers go stale on every commit. Mitigation: `/verify-learnings-counts` slash command performs mechanical count and compares against documentation claims. Wired into checkpoint step 4 propagation check.

---

## L-0116
Type: process_rule
Tags: checkpoint, learnings, defaults
Confidence: high
Status: active
Date: 2026-03-02T03:00:00-05:00
Related: L-0113 (depends_on)

"Nothing to capture" must never be the default assumption. The default should be "something to capture" and the scan must find reasons to skip, not reasons to include. The checkpoint immediately after L-0113 was committed demonstrated the failure: the AI performed the new active scan categories but still concluded "no new learnings" — because the default was still passive. The bias must flip: assume every session produces learnings unless the scan proves otherwise.

---

## L-0117
Type: process_rule
Tags: protocol, adoption, latency
Confidence: high
Status: active
Date: 2026-03-02T03:00:00-05:00
Related: L-0113 (depends_on), L-0116 (related_to)

New protocol rules have a one-response adoption latency. L-0113 codified active scan. The very next checkpoint executed step 4 with the new categories but still under-captured — the behavioral pattern hadn't changed despite the written rule changing. A fresh session reading L-0113 cold would likely apply it more faithfully than the session that just wrote it, because the session that wrote it still carries the old behavioral inertia. Implication: after writing a new process rule, explicitly test it in the same session by re-running the step it modifies. Mechanical enforcement: `/verify-propagation` step 5 flags self-test requirement when process-rules.md has new entries.

---

## L-0118
Type: process_rule
Tags: core-learnings, onboarding, delivery
Confidence: high
Status: active
Date: 2026-03-02T03:00:00-05:00
Related: L-0114 (depends_on)

core.md is the actual delivery mechanism for learnings to fresh sessions. If a learning isn't in core.md, fresh sessions won't know it exists unless they happen to read the type-specific file. The onboarding protocol reads core.md — it does not read all type files. Therefore any learning that would cause a consequential mistake if missed must be in core.md. The selection criterion: "if a fresh session doesn't know this, will it make a mistake that matters?" If yes, it's core.

---

## L-0127
Type: process_rule
Tags: response-scope, work-items, planning
Confidence: high
Status: active
Date: 2026-03-02T03:45:00-05:00
Related: L-0113 (related_to)

Count work items BEFORE the first tool call, every response. The instruction exists in memory ("Count work items BEFORE first tool call. >3 distinct work items or >15 tool calls = split across responses") but was not followed in the response that failed — it attempted learnings capture, three file integrations, and system wiring all at once. The count must be explicit and visible, not implicit. State "N work items this response, splitting M for next" before starting work. A failed response wastes more time than two successful ones.

---

## L-0128
Type: process_rule
Tags: learnings, enforcement, mechanical-vs-prose
Confidence: high
Status: active
Date: 2026-03-02T03:45:00-05:00
Related: L-0113 (depends_on), L-0115 (validates), L-0116 (validates)

Learnings that remain prose get ignored; learnings that become mechanical checks get followed. L-0113 (active scan) was prose — the very next checkpoint under-captured. `/verify-learnings-counts` (L-0115) is mechanical — it runs grep, compares numbers, reports discrepancies. The pattern: when a learning identifies a recurring failure mode, the fix is not a better-worded rule but a tool or command that enforces the rule without requiring the AI to remember it. Prose rules require behavioral compliance. Mechanical checks require only invocation.

---

## L-0131
Type: process_rule
Tags: checkpoint, context-loss, multi-response
Confidence: high
Status: active
Date: 2026-03-02T05:00:00-05:00
Related: L-0130 (depends_on), L-0127 (related_to)

Multi-response checkpoints must stash progress incrementally. Checkpoints spanning multiple responses are vulnerable to the same context loss L-0130 addresses. Each completed step must be written to files before proceeding to the next. Pattern: write learnings to stash file → commit or update .onboarding-state → proceed to methodology signals → stash again. If context dies mid-checkpoint, the completed steps survive. Instruction origin: Brian's "stash as you go to prevent lost progress."

---

## L-0133
Type: process_rule
Tags: methodology, review, corpus-analysis
Confidence: high
Status: active
Date: 2026-03-02T05:00:00-05:00
Related: L-0124 (extends), L-0128 (related_to)

Corpus-level review is a distinct operation from keyword-based signal scanning. `/review-signals` greps HOW-I-WORK for keywords matching existing learnings. Reading the full corpus end-to-end revealed structure that keyword matching cannot: emergent clusters (prompt engineering, agent autonomy, session types, capture philosophy), a philosophical foundation ("we want to be 1"), and accumulation-without-curation debt. Periodic full-read review — not just keyword scan — surfaces patterns that exist between entries, not within them.
