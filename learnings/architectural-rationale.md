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
