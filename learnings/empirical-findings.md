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
