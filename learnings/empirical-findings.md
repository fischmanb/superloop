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

---

## L-0121
Type: empirical_finding
Tags: agents, prompts, first-dispatch, validation
Confidence: medium
Status: active
Date: 2026-03-02T03:00:00-05:00
Related: L-0109 (validates), L-0045 (validates)

Phase 2 agent (eval-sidecar conversion) succeeded on first dispatch: 31 tests, 77 assertions, mypy --strict clean, exactly 3 files modified (hard constraint). This is the first agent run using both the prompt engineering guide (L-0109) and dependency signatures instead of full source (L-0045) together. Single data point — not yet validated per Brian's demonstrated/validated distinction — but directionally supports the approach. Phase 1 also succeeded on first dispatch for all 5 agents. Combined: 6/6 first-dispatch successes since adopting the guide.

---

## L-0122
Type: empirical_finding
Tags: agents, hard-constraints, boundary-enforcement
Confidence: high
Status: active
Date: 2026-03-02T03:00:00-05:00
Related: L-0001 (related_to), L-0016 (related_to), L-0121 (related_to)

Hard constraints boundary enforcement worked under pressure. The Phase 2 agent noticed .gitignore needed Python cache entries but correctly stayed within its 3-file boundary (eval_sidecar.py, test_eval_sidecar.py, Agents.md). The agent wanted to do more and flagged it in its summary instead of acting. This validates the hard constraints pattern from a different angle than L-0001/L-0016 — those are about agents exceeding scope silently; this shows an agent recognizing a legitimate need and correctly deferring it.

---

## L-0123
Type: empirical_finding
Tags: agents, preconditions, resilience
Confidence: medium
Status: active
Date: 2026-03-02T03:00:00-05:00
Related: L-0112 (related_to)

Agent precondition check (HEAD hash) was invalidated by L-0112 coordination failure, but the agent produced correct output anyway. The precondition advanced from 6be9b74 to a67c60c (a learnings/ACTIVE-CONSIDERATIONS commit — no code changes). Either the agent didn't enforce the precondition strictly, or it adapted. The outcome was fine because the commit didn't touch any dependency, but this is a near-miss: if the intervening commit had modified a file the agent depended on, the output could have been silently wrong. Precondition checks exist for the bad case, not the good case.

---

## L-0132
Type: empirical_finding
Tags: context-loss, validation, compaction
Confidence: high
Status: active
Date: 2026-03-02T05:00:00-05:00
Related: L-0130 (validates)

L-0130 (design for context loss) was validated by real compaction event in the same session that wrote it. File-based architecture survived: .onboarding-state, learnings files, ACTIVE-CONSIDERATIONS.md, and transcript provided enough state for replacement context to resume work without asking "where were we?" Per L-0123's language distinction between "demonstrated" and "validated": the original writing was demonstration; this compaction event is confirming validation.
