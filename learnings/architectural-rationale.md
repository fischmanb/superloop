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
