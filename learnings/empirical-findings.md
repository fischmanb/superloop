# Empirical Findings

> Data-driven measurements or discoveries. Distinct from `failure_pattern` — these are measurements, not failure modes.
>
> Schema: see `DESIGN-PRINCIPLES.md` §3 (edge types) and §4 (confidence/status enums).
> ID range: global sequential `L-XXXXX` shared across all learnings files.

---

## L-00024
Type: empirical_finding
Tags: verification, bash, testing
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00
Related: L-00016 (related_to)

`bash -n` is necessary but insufficient. It catches syntax errors but not unreachable code or wrong function names. Must be combined with other gates (grep for call sites, test suite, `git diff --stat`).

---

## L-00025
Type: empirical_finding
Tags: agent-behavior, capability-gradient
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00
Related: L-00001 (related_to)

Agents are better at verification than comprehensive implementation. Skill gradient: verification > implementation > self-assessment. Design workflows to exploit this — let agents verify each other's work rather than trusting self-reports.

---

## L-00026
Type: empirical_finding
Tags: performance, model-speed, build-speed, parallelism
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00

Token speed does NOT translate to build speed. Haiku 2x faster tokens but only marginally faster builds (~16-18 min/feature both models) because npm install, TypeScript compile, tests, drift checks are fixed-cost CPU/disk-bound steps that dominate wall time. Model speed only affects agent thinking fraction. Parallelism across features matters more than per-feature model speed.

---

## L-00107
Type: empirical_finding
Tags: agents, parallel, merge
Confidence: high
Status: active
Date: 2026-03-01T20:00:00-05:00
Related: L-00039 (related_to)

Zero-cross-dependency design eliminates merge conflicts on source files. 5 parallel agents, 5 branches, zero source/test file conflicts during integration merge. Only Agents.md conflicted (all agents append to same file). The Phase 0 decision to ensure zero cross-dependencies between conversion targets paid off exactly as designed. Implication: when planning parallel agent work, invest in dependency analysis upfront — the merge tax is near-zero if targets are truly independent.

---

## L-00108
Type: empirical_finding
Tags: hardware, execution, agents
Confidence: high
Status: active
Date: 2026-03-01T20:00:00-05:00
Related: L-00107 (related_to)

Sequential execution sufficient for Phase 1 on MacBook Air. Mac Studio was deemed necessary for 5 parallel agents. In practice, sequential execution on MacBook Air M3/16GB completed all 5 conversions in one session. Each agent ~5-10 min. The bottleneck was prompt engineering and review, not compute. Parallelism optimization was premature for this workload size.

---

## L-00121
Type: empirical_finding
Tags: agents, prompts, first-dispatch, validation
Confidence: medium
Status: active
Date: 2026-03-02T03:00:00-05:00
Related: L-00109 (validates), L-00045 (validates)

Phase 2 agent (eval-sidecar conversion) succeeded on first dispatch: 31 tests, 77 assertions, mypy --strict clean, exactly 3 files modified (hard constraint). This is the first agent run using both the prompt engineering guide (L-00109) and dependency signatures instead of full source (L-00045) together. Single data point — not yet validated per Brian's demonstrated/validated distinction — but directionally supports the approach. Phase 1 also succeeded on first dispatch for all 5 agents. Combined: 6/6 first-dispatch successes since adopting the guide.

---

## L-00122
Type: empirical_finding
Tags: agents, hard-constraints, boundary-enforcement
Confidence: high
Status: active
Date: 2026-03-02T03:00:00-05:00
Related: L-00001 (related_to), L-00016 (related_to), L-00121 (related_to)

Hard constraints boundary enforcement worked under pressure. The Phase 2 agent noticed .gitignore needed Python cache entries but correctly stayed within its 3-file boundary (eval_sidecar.py, test_eval_sidecar.py, Agents.md). The agent wanted to do more and flagged it in its summary instead of acting. This validates the hard constraints pattern from a different angle than L-00001/L-00016 — those are about agents exceeding scope silently; this shows an agent recognizing a legitimate need and correctly deferring it.

---

## L-00123
Type: empirical_finding
Tags: agents, preconditions, resilience
Confidence: medium
Status: active
Date: 2026-03-02T03:00:00-05:00
Related: L-00112 (related_to)

Agent precondition check (HEAD hash) was invalidated by L-00112 coordination failure, but the agent produced correct output anyway. The precondition advanced from 6be9b74 to a67c60c (a learnings/ACTIVE-CONSIDERATIONS commit — no code changes). Either the agent didn't enforce the precondition strictly, or it adapted. The outcome was fine because the commit didn't touch any dependency, but this is a near-miss: if the intervening commit had modified a file the agent depended on, the output could have been silently wrong. Precondition checks exist for the bad case, not the good case.

---

## L-00132
Type: empirical_finding
Tags: context-loss, validation, compaction
Confidence: high
Status: active
Date: 2026-03-02T05:00:00-05:00
Related: L-00130 (validates)

L-00130 (design for context loss) was validated by real compaction event in the same session that wrote it. File-based architecture survived: .onboarding-state, learnings files, ACTIVE-CONSIDERATIONS.md, and transcript provided enough state for replacement context to resume work without asking "where were we?" Per L-00123's language distinction between "demonstrated" and "validated": the original writing was demonstration; this compaction event is confirming validation.

---

## L-00144
- **Type:** empirical-finding
- **Tags:** [near-miss, agent-prompts, scope-sizing, schema-migration]
- **Confidence:** high — direct observation
- **Status:** active
- **Date:** 2026-03-02
- **Related:** L-00142, L-00143, L-00123

Schema standardization agent succeeded despite overscoped prompt (L-00142 violation). 23 files, +1275/-501 lines, zero orphaned IDs, all verification checks passed. This is a near-miss per L-00123 language: correct outcome does not validate the process. The agent could have hit context limits on a larger repo or with more complex entries. Verification passing confirms the output was correct, not that the scope was safe. Near-misses that succeed are harder to learn from than failures — they create false confidence that bundling works.

---

## L-00145
- **Type:** empirical-finding
- **Tags:** [token-estimation, calibration, proxy-metrics, general-estimates]
- **Confidence:** high — direct observation from Dispatch 1 token report
- **Status:** active
- **Date:** 2026-03-02
- **Related:** L-00143, lib/general-estimates.sh

Token estimation formula (lines_read × 4 + lines_written × 4 + 5000) produced 5860 "actual" tokens for a run with 37 tool calls. The formula only measures file I/O — it cannot see prompt injection, CLAUDE.md/repo context auto-loaded by the agent, tool call overhead (~200 tokens per invocation), inter-call reasoning, or verification output. True consumption was likely 20-30k. The 5000 "reasoning overhead" constant masks a variable that scales with tool call count and conversation complexity. Feeding this proxy data into general-estimates.jsonl would miscalibrate the estimator — the system would learn from wrong numbers. Proxy measurement that produces confidently wrong data is worse than no measurement. Replace with actual API token counts from Claude Code session metadata.

---

## L-00147
- **Type:** empirical-finding
- **Tags:** [context-limits, scope-sizing, token-estimation, degradation-ceiling]
- **Confidence:** high — agent estimated 8.5% then hit context limit
- **Status:** active
- **Date:** 2026-03-02
- **Related:** L-00143, L-00145

Context limit estimates must account for already-consumed context, not just the planned response. An agent estimated 8.5% utilization against the full 200k context window, stated "Proceeding," then failed to complete. The degradation ceiling formula calculates available room as `max_context × quality_factor`, but this assumes an empty context window. Correct formula: `available_room = (max_context × quality_factor) - current_context_used`. Without subtracting current context (conversation history, CLAUDE.md injection, tool definitions, system prompt), the estimate is meaningless. A fresh session and a 50-message session have radically different available room despite the same ceiling calculation.

---

## L-00148
- **Type:** empirical-finding
- **Tags:** [token-estimation, proxy-metrics, calibration, magnitude-error]
- **Confidence:** high — direct comparison: proxy said 5,860, actual JSONL showed 1.9M
- **Status:** active
- **Date:** 2026-03-02
- **Related:** L-00145, L-00143

First real token measurement via `get_session_actual_tokens` showed the proxy formula was off by ~300x, not the 2x the formula's self-computed error claimed. The formula's error calculation was also wrong because it divided proxy-by-proxy. The 104.8% "overestimate" error was itself a proxy artifact — the denominator (5,860 "actual") was as wrong as the numerator (12,000 "estimated"). Real comparison: 12,000 estimated vs ~1.9M actual = 99.4% underestimate. Lesson: a broken measurement system cannot self-diagnose. Requires external ground truth (in this case, Claude Code's JSONL session logs).

## L-00149
- **Type:** empirical-finding
- **Tags:** [token-estimation, cache-tokens, calibration, active-vs-cumulative]
- **Confidence:** high — direct observation from checkpoint token report
- **Status:** active
- **Date:** 2026-03-02
- **Related:** L-00145, L-00148, L-00143

Cache tokens dominate cumulative session totals but are irrelevant to scope estimation. A checkpoint session reported 3.17M "actual" tokens — 87.6% was cache reads (re-sent context: CLAUDE.md, tool definitions, conversation history). Active computation was ~31.5k (input + output). Comparing scope estimates against cumulative tokens produces meaningless calibration data — the number scales with API call count and session length, not with the work unit being estimated. The estimator must compare against active_tokens (input + output) only. This is distinct from L-00145 (proxy formula wrong) and L-00148 (magnitude error) — those identified the proxy was broken. This identifies that even real token data needs decomposition before it's useful for calibration.

---

## L-00152
- **Type:** empirical-finding
- **Tags:** [claude-code, slash-commands, skills, chat-interface, platform-capabilities]
- **Confidence:** high — tested directly, confirmed by official docs
- **Status:** active
- **Date:** 2026-03-02
- **Related:** L-00150, M-00076

`.claude/commands/` (slash commands) and `.claude/skills/` (agent skills) only work in Claude Code (terminal). They do NOT work in claude.ai Chat tab or Claude Desktop Chat, despite docs suggesting skills work "outside of Claude Code." For cross-interface workflows (extract-learnings, checkpoint), the working path is: Claude's memory recognizes the trigger phrase + Desktop Commander provides filesystem access + natural language drives execution. No infrastructure file needed — just say the words.
