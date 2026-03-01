# Empirical Findings

> Data-driven measurements or discoveries. Distinct from `failure_pattern` — these are measurements, not failure modes.
>
> Schema: see `DESIGN-PRINCIPLES.md` §3 (edge types) and §4 (confidence/status enums).
> ID range: global sequential `L-XXXX` shared across all learnings files.

---

## L-0024
Type: empirical_finding
Tags: verification, bash, testing
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00
Related: L-0016 (related_to)

`bash -n` is necessary but insufficient. It catches syntax errors but not unreachable code or wrong function names. Must be combined with other gates (grep for call sites, test suite, `git diff --stat`).

---

## L-0025
Type: empirical_finding
Tags: agent-behavior, capability-gradient
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00
Related: L-0001 (related_to)

Agents are better at verification than comprehensive implementation. Skill gradient: verification > implementation > self-assessment. Design workflows to exploit this — let agents verify each other's work rather than trusting self-reports.

---

## L-0026
Type: empirical_finding
Tags: performance, model-speed, build-speed, parallelism
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00

Token speed does NOT translate to build speed. Haiku 2x faster tokens but only marginally faster builds (~16-18 min/feature both models) because npm install, TypeScript compile, tests, drift checks are fixed-cost CPU/disk-bound steps that dominate wall time. Model speed only affects agent thinking fraction. Parallelism across features matters more than per-feature model speed.

---

## L-0107
Type: empirical_finding
Tags: agents, parallel, merge
Confidence: high
Status: active
Date: 2026-03-01T20:00:00-05:00
Related: L-0039 (related_to)

Zero-cross-dependency design eliminates merge conflicts on source files. 5 parallel agents, 5 branches, zero source/test file conflicts during integration merge. Only Agents.md conflicted (all agents append to same file). The Phase 0 decision to ensure zero cross-dependencies between conversion targets paid off exactly as designed. Implication: when planning parallel agent work, invest in dependency analysis upfront — the merge tax is near-zero if targets are truly independent.

---

## L-0108
Type: empirical_finding
Tags: hardware, execution, agents
Confidence: high
Status: active
Date: 2026-03-01T20:00:00-05:00
Related: L-0107 (related_to)

Sequential execution sufficient for Phase 1 on MacBook Air. Mac Studio was deemed necessary for 5 parallel agents. In practice, sequential execution on MacBook Air M3/16GB completed all 5 conversions in one session. Each agent ~5-10 min. The bottleneck was prompt engineering and review, not compute. Parallelism optimization was premature for this workload size.
