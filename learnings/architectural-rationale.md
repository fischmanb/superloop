# Architectural Rationale

> Why the system is designed a certain way. Strategic design decisions and their justification.
>
> Schema: see `DESIGN-PRINCIPLES.md` §3 (edge types) and §4 (confidence/status enums).
> ID range: global sequential `L-XXXX` shared across all learnings files.

---

## L-0027
Type: architectural_rationale
Tags: verification, multi-layer, trust
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00
Related: L-0001 (related_to)
Related: L-0025 (related_to)

Independent verification catches what self-assessment misses. Same principle as drift detection (Layer 1 self-check vs Layer 2 cross-check). The build loop validates between every agent step because no single agent's claim about its own work is trustworthy.

---

## L-0028
Type: architectural_rationale
Tags: signal-protocol, grep, parsing, agent-communication
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00

Signal protocol uses grep-parseable signals, not JSON. Agents communicate via flat strings (`FEATURE_BUILT: {name}`, `BUILD_FAILED: {reason}`). No JSON parsing, no eval on agent output. Grep is reliable, available everywhere, and fails visibly. JSON parsing introduces fragility — malformed output from an agent silently breaks downstream logic instead of failing at the grep step.


---

### L-0041
- **Type:** architecture_finding
- **Tags:** bash-to-python, claude-wrapper, invocation-pattern
- **Confidence:** high
- **Date:** 2026-02-28T21:30:00-05:00
- **Source:** Dependency analysis during Phase 0
- **Body:** claude-wrapper.sh is invoked as an external command (`bash lib/claude-wrapper.sh -p ...`), never `source`d. All four consumers (build-loop-local, overnight-autonomous, eval-sidecar, nightly-review) call it the same way. The Python equivalent should be a callable function (`run_claude(prompt, **kwargs) → ClaudeResult`), not a module whose internals get imported. This distinction matters for the interface stub design — wrapper is a service boundary, not a utility library.

---

## L-0106
Type: architectural_rationale
Tags: agents, prompts, sandbox
Confidence: high
Status: active
Date: 2026-03-01T20:00:00-05:00
Related: L-0105 (related_to)

"Do not push" conflicts with ephemeral sandbox. Agent prompts said "Do NOT push" per PROMPT-ENGINEERING-GUIDE local-execution pattern. But Claude Code agents run in ephemeral sandboxes — work is lost if not pushed. CLAUDE.md's default push behavior accidentally saved all 5 branches. Resolution: agent prompts for Claude Code MUST include push as final step. Local-only execution pattern only applies when agents run on the actual local machine.

---

## L-0111
Type: architectural_rationale
Tags: build-loop, process, meta
Confidence: high
Status: active
Date: 2026-03-01T20:30:00-05:00
Related: L-0109 (related_to), L-0107 (related_to), L-0039 (related_to)

Meta-process patterns transferable to build loop. The bash→Python conversion process surfaced 6 patterns the build loop doesn't implement: (1) code-level dependency analysis before execution order — build loop uses spec-declared deps but not actual import-level edges, (2) context budget estimation before agent dispatch — build loop fires without checking if prompt + summary + spec + headroom fits the effective window, (3) conventions doc injection so agents write consistent code — build loop gives codebase summary (what exists) but not conventions (how to write), which is why type redeclarations happen, (4) interface stubs as pre-declared contracts in specs — agents get descriptions not target signatures, (5) mechanical prompt quality gate before dispatch — build loop generates and dispatches immediately with no intermediate check, (6) cross-feature failure pattern feedback mid-campaign — if feature 5 fails the same way feature 3 did, the build loop doesn't notice or adapt. Items 2/3/5 are highest leverage and directly address documented failure modes. Design input for Phase 4 build-loop conversion.

---

## L-0124
Type: architectural_rationale
Tags: methodology-signals, learnings, feedback-loop, meta
Confidence: high
Status: active
Date: 2026-03-02T03:00:00-05:00
Related: L-0113 (related_to), L-0119 (related_to)

HOW-I-WORK-WITH-GENERATIVE-AI.md methodology signals are leading indicators of protocol gaps. The evidence that checkpoint step 4 was broken sat in methodology signals for an indeterminate number of responses: "under-capture is a failure mode," "checkpoint should be thorough not mechanical," "Brian expects capture density to match session density." These were captured as raw observations (step 5) but never fed back into protocol review (step 4) or learnings. The methodology signals file is a pre-learnings staging area — observations accumulate there before they're synthesized into actionable rules. Mechanical enforcement: `/review-signals` scans Accumulation for clusters, checks against existing learnings, and flags candidates for graduation. Wired into checkpoint step 4.

---

## L-0125
Type: architectural_rationale
Tags: meta-process, infrastructure-reuse, slash-commands, convention-drift
Confidence: high
Status: active
Date: 2026-03-02T03:30:00-05:00
Related: L-0115 (depends_on), L-0114 (related_to), L-0119 (related_to)

New meta-process infrastructure must scan existing project assets for reusable patterns before building from scratch. The checkpoint/learnings system was built in isolation from the slash command library. Four commands already embodied patterns the system needed: `/catch-drift` (source-of-truth vs claims comparison), `/check-coverage` (gap analysis), `/update-test-docs` (sync docs with reality), `/verify-test-counts` (mechanical count reconciliation). Only the last one was connected — and only after Brian pointed it out. Meanwhile, CLAUDE.md (the conventions file all agents read) still pointed to `.specs/learnings/` (old system) while the new system lives in `learnings/`. `/compound` still writes to the old location. Any agent following CLAUDE.md would write learnings to the wrong place. The pattern: when building process infrastructure, first audit existing commands and conventions files for (1) reusable patterns, (2) stale references the new system invalidates, (3) existing tooling that can be wired in mechanically.

---

## L-0129
Type: architectural_rationale
Tags: build-system, repo-agnostic, separation-of-concerns
Confidence: high
Status: active
Date: 2026-03-02T03:45:00-05:00
Related: L-0125 (related_to)

Auto-sdd's build system must remain repo-agnostic. Checkpoint tooling, learnings management, and meta-process commands (like `/verify-learnings-counts`) are auto-sdd's own development infrastructure — they exist to help develop auto-sdd itself. The build loop that auto-sdd runs to build other projects must not depend on or assume these files exist in the target repo. Mechanical integrations into the checkpoint protocol are safe (they run in auto-sdd's context). Mechanical integrations into the build loop are not (they would impose auto-sdd's structure on target repos).


---

## L-0130
Type: architectural_rationale
Tags: context-loss, compaction, file-first, resilience, mechanical-check
Confidence: high
Status: active
Date: 2026-03-02T04:15:00-05:00
Related: L-0118 (depends_on), L-0114 (related_to), L-0127 (related_to)

Design for context loss as the default, not the exception. Context windows compact, sessions end, responses fail mid-stream. The only state that survives is file state. Every response that advances work must leave enough in files that a replacement session can resume without asking "where were we?"

Mechanical self-test (run mentally before ending any response that changes project state): "If the context window were wiped after this response, could the next session pick up from file state alone?" If no — something wasn't externalized. Specifically check:

1. `.onboarding-state` — does it reflect current HEAD and work-in-progress?
2. `ACTIVE-CONSIDERATIONS.md` — does it list what's in flight and what's next?
3. Uncommitted work — is it committed, or at minimum described in a file the next session will read?
4. Multi-response plans — is the plan in a file, or only in the context that's about to die?

The onboarding protocol exists so post-compaction recovery costs 2-3 tool calls, not 20 messages of "what were we doing?" This learning is the *why* behind file-first architecture. The self-test is the *enforcement*.
---

## L-0139
Type: architectural_rationale
Tags: design, self-diagnosis, reliability
Confidence: high
Status: active
Date: 2026-03-02T05:30:00-05:00
Related: L-0128 (validates), L-0125 (related_to)

"Structure catches its own gaps." The learnings graph referenced L-0048 but L-0048 didn't exist — the audit surfaced this mechanically, not through memory or vigilance. Design principle: failures should be visible to the structure itself, not dependent on an operator noticing. This is why /verify-learnings-counts works and prose rules don't (L-0128). A system that requires attention to detect failures will accumulate undetected failures proportional to the operator's distraction.
