# Process Rules

> Prescriptive operational discipline. Often the fix for a `failure_pattern`.
>
> Schema: see `DESIGN-PRINCIPLES.md` §3 (edge types) and §4 (confidence/status enums).
> ID range: global sequential `L-XXXXX` shared across all learnings files.

---

## L-00014
Type: process_rule
Tags: prompt-engineering, agent-behavior, conciseness
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00

Keeping agent prompts concise — describing intent, not implementation code — has produced better results. Prescriptive prompts (pasting exact code to insert) have caused agents to copy without understanding, miss edge cases, and fail when context differs slightly. Intent-based prompts ("add a guard that exits if CLAUDECODE is set") have produced better results because the agent reasons about placement and integration.

---

## L-00015
Type: process_rule
Tags: prompt-engineering, scope, agent-behavior
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00

Scope to ≤3-4 files per round, independently testable. Larger scopes increase agent confusion and make failures harder to diagnose.

---

## L-00016
Type: process_rule
Tags: prompt-engineering, verification, gates
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00
Related: L-00001 (depends_on)

Every prompt must end with verification gates — `bash -n`, grep, test suite, `git diff --stat`. Agent self-assessment has proven unreliable; machine-checkable gates are the only trustworthy signal.

---

## L-00017
Type: process_rule
Tags: git, agent-behavior, origin, merge-conflicts
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00

Push main to origin before running agent prompts. Claude Code agents fork from `origin/main`, not local `main`. Stale origin → merge conflicts after every round. Observed: Rounds 21-23 all forked from stale origin/main.

---

## L-00018
Type: process_rule
Tags: git, approval, permissions
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00

Edit approval ≠ commit approval. Approving a file edit does not implicitly approve committing it. Each operation requires its own explicit "yes." Violation: commit 2f77ea9.

---

## L-00019
Type: process_rule
Tags: git, push-discipline, agent-behavior
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00
Related: L-00005 (depends_on)

Agents should commit locally but not push. Brian pushes to GitHub manually. This is a design constraint, not a fixable behavior — agents ignore push restrictions (see L-00005).

---

## L-00020
Type: process_rule
Tags: session-discipline, agent-sessions, chat-sessions
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00

Implementation work (scripts, lib/, tests) → fresh Claude Code agent session with hardened prompt. Planning, analysis, documentation → chat session (claude.ai with Desktop Commander). The boundary: if modifying a script in `scripts/`, a library in `lib/`, or test logic in `tests/`, write a hardened agent prompt. If updating docs or analyzing, chat is fine.

---

## L-00021
Type: process_rule
Tags: session-discipline, desktop-commander, temptation
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00
Related: L-00020 (depends_on)

Desktop Commander gives chat full filesystem access — making it tempting to "just make a quick fix." Resist. Write the agent prompt instead. Quick fixes in chat bypass the verification gates that catch agent mistakes.

---

## L-00022
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

## L-00023
Type: process_rule
Tags: learnings, organization, repo-structure
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00

Learnings/patterns belong in the main `learnings/` catalog (previously `.specs/learnings/`), not in project-specific directories (e.g., `stakd/.specs/learnings/`). Project-specific dirs only get fixes specific to that build/app.


---

### L-00040
- **Type:** process_rule
- **Tags:** session-discipline, tool-limits
- **Confidence:** high
- **Date:** 2026-02-28T21:30:00-05:00
- **Source:** Brian correction during Phase 0 checkpoint
- **Body:** The 10 tool call limit per response protects against context loss if a response exceeds context window limits. Each tool call must be one logical operation. Batching multiple operations into a single shell command (e.g., `mkdir && touch && git add && commit && push`) games the limit and defeats the purpose. The constraint is on logical operations performed, not literal tool invocations counted.



---

## L-00109
Type: process_rule
Tags: prompts, agents, review
Confidence: high
Status: active
Date: 2026-03-01T20:00:00-05:00
Related: L-00104 (related_to)

Prompt engineering review before execution prevents rework. Brian caught 5 violations in draft prompts before any agent ran: wrong branch naming convention, abbreviated hard constraints missing full template clauses, over-prescribed interfaces (violating L-00045/L-00042), nested markdown inside code blocks, wrong verification scope (bash suites for Python-only changes). Fixing prompts costs minutes; fixing agent output costs full re-runs. Always review prompts against the guide before handing to agents.

---

## L-00110
Type: process_rule
Tags: testing, verification
Confidence: high
Status: active
Date: 2026-03-01T20:00:00-05:00
Related: L-00109 (related_to)

Verification scope must match change scope. Python-only changes need only mypy --strict + pytest. Bash test suites (5 suites) only needed when bash files are modified. Running irrelevant test suites wastes time and creates false confidence signals ("all bash tests pass" is meaningless when no bash changed). Added to PROMPT-ENGINEERING-GUIDE.md as explicit rule.

---

## L-00113
Type: process_rule
Tags: checkpoint, learnings, capture, meta
Confidence: high
Status: active
Date: 2026-03-02T02:30:00-05:00
Related: L-00109 (related_to), L-00016 (related_to)

Checkpoint step 4 (learnings) must use active scan, not passive recall. The original wording "if any surfaced: flag" produced under-capture — a short session was declared "none new" without reviewing agent outcomes, corrections, or near-misses. Step 5 (methodology signals) already had active scan language ("scan session for...") and produced rich output. Step 4 needed the same structure. Active scan categories: agent completions (validate/contradict existing learnings?), Brian's corrections (each is a candidate), new rules or patterns, empirical findings, failures or near-misses. Under-capture is a failure mode equal to over-capture. Match capture density to session density.

---

## L-00114
Type: process_rule
Tags: documentation, propagation, protocol
Confidence: high
Status: active
Date: 2026-03-02T03:00:00-05:00
Related: L-00113 (depends_on)

Protocol changes must propagate to all consumption points. A rule has (at minimum) a definition point (e.g. checkpoint.md), a summary point (e.g. ONBOARDING.md), and a delivery point (e.g. core.md that fresh sessions read). Changing one without the others creates silent drift — the protocol says one thing, the onboarding path teaches another. Discovered when L-00113 was written to checkpoint.md and ONBOARDING.md but not core.md until Brian corrected. Checklist for any protocol change: (1) definition file, (2) ONBOARDING.md summary, (3) core.md if it's a constitutional learning, (4) any ACTIVE-CONSIDERATIONS references.

---

## L-00115
Type: process_rule
Tags: documentation, counts, staleness, maintenance
Confidence: high
Status: active
Date: 2026-03-02T03:00:00-05:00
Related: L-00114 (related_to)

Numeric references in documentation rot silently. ONBOARDING.md said "38 entries" when actual was 57. ACTIVE-CONSIDERATIONS said "63 graph-compliant" and "~47 old-format" — both wrong. Nobody noticed because prose ages gracefully but numbers go stale on every commit. Mitigation: `/verify-learnings-counts` slash command performs mechanical count and compares against documentation claims. Wired into checkpoint step 4 propagation check.

---

## L-00116
Type: process_rule
Tags: checkpoint, learnings, defaults
Confidence: high
Status: active
Date: 2026-03-02T03:00:00-05:00
Related: L-00113 (depends_on)

"Nothing to capture" must never be the default assumption. The default should be "something to capture" and the scan must find reasons to skip, not reasons to include. The checkpoint immediately after L-00113 was committed demonstrated the failure: the AI performed the new active scan categories but still concluded "no new learnings" — because the default was still passive. The bias must flip: assume every session produces learnings unless the scan proves otherwise.

---

## L-00117
Type: process_rule
Tags: protocol, adoption, latency
Confidence: high
Status: active
Date: 2026-03-02T03:00:00-05:00
Related: L-00113 (depends_on), L-00116 (related_to)

New protocol rules have a one-response adoption latency. L-00113 codified active scan. The very next checkpoint executed step 4 with the new categories but still under-captured — the behavioral pattern hadn't changed despite the written rule changing. A fresh session reading L-00113 cold would likely apply it more faithfully than the session that just wrote it, because the session that wrote it still carries the old behavioral inertia. Implication: after writing a new process rule, explicitly test it in the same session by re-running the step it modifies. Mechanical enforcement: `/verify-propagation` step 5 flags self-test requirement when process-rules.md has new entries.

---

## L-00118
Type: process_rule
Tags: core-learnings, onboarding, delivery
Confidence: high
Status: active
Date: 2026-03-02T03:00:00-05:00
Related: L-00114 (depends_on)

core.md is the actual delivery mechanism for learnings to fresh sessions. If a learning isn't in core.md, fresh sessions won't know it exists unless they happen to read the type-specific file. The onboarding protocol reads core.md — it does not read all type files. Therefore any learning that would cause a consequential mistake if missed must be in core.md. The selection criterion: "if a fresh session doesn't know this, will it make a mistake that matters?" If yes, it's core.

---

## L-00127
Type: process_rule
Tags: response-scope, work-items, planning
Confidence: high
Status: active
Date: 2026-03-02T03:45:00-05:00
Related: L-00113 (related_to)

Count work items BEFORE the first tool call, every response. The instruction exists in memory ("Count work items BEFORE first tool call. >3 distinct work items or >15 tool calls = split across responses") but was not followed in the response that failed — it attempted learnings capture, three file integrations, and system wiring all at once. The count must be explicit and visible, not implicit. State "N work items this response, splitting M for next" before starting work. A failed response wastes more time than two successful ones.

---

## L-00128
Type: process_rule
Tags: learnings, enforcement, mechanical-vs-prose
Confidence: high
Status: active
Date: 2026-03-02T03:45:00-05:00
Related: L-00113 (depends_on), L-00115 (validates), L-00116 (validates)

Learnings that remain prose get ignored; learnings that become mechanical checks get followed. L-00113 (active scan) was prose — the very next checkpoint under-captured. `/verify-learnings-counts` (L-00115) is mechanical — it runs grep, compares numbers, reports discrepancies. The pattern: when a learning identifies a recurring failure mode, the fix is not a better-worded rule but a tool or command that enforces the rule without requiring the AI to remember it. Prose rules require behavioral compliance. Mechanical checks require only invocation.

---

## L-00131
Type: process_rule
Tags: checkpoint, context-loss, multi-response
Confidence: high
Status: active
Date: 2026-03-02T05:00:00-05:00
Related: L-00130 (depends_on), L-00127 (related_to)

Multi-response checkpoints must stash progress incrementally. Checkpoints spanning multiple responses are vulnerable to the same context loss L-00130 addresses. Each completed step must be written to files before proceeding to the next. Pattern: write learnings to stash file → commit or update .onboarding-state → proceed to methodology signals → stash again. If context dies mid-checkpoint, the completed steps survive. Instruction origin: Brian's "stash as you go to prevent lost progress."

---

## L-00133
Type: process_rule
Tags: methodology, review, corpus-analysis
Confidence: high
Status: active
Date: 2026-03-02T05:00:00-05:00
Related: L-00124 (extends), L-00128 (related_to)

Corpus-level review is a distinct operation from keyword-based signal scanning. `/review-signals` greps HOW-I-WORK for keywords matching existing learnings. Reading the full corpus end-to-end revealed structure that keyword matching cannot: emergent clusters (prompt engineering, agent autonomy, session types, capture philosophy), a philosophical foundation ("we want to be 1"), and accumulation-without-curation debt. Periodic full-read review — not just keyword scan — surfaces patterns that exist between entries, not within them.

---

## L-00135
Type: process_rule
Tags: prompts, agents, compression
Confidence: high
Status: active
Date: 2026-03-02T05:30:00-05:00
Related: L-00016 (extends), L-00020 (related_to)

"Half the length and do not solve the thing the agent will be able to solve. Show them where to look if you must for success." Calibrate spec prescriptiveness by agent capability — only lock down decisions an agent would high-percentage get wrong. Token cost and agent behavior efficiency are the quality metrics, not just output correctness. Distinguish boilerplate (load-bearing rules proven by failure) from verbosity (excess words expressing those rules). Cut verbosity, keep the rules.

---

## L-00136
Type: process_rule
Tags: capture, sessions, meta-work
Confidence: high
Status: active
Date: 2026-03-02T05:30:00-05:00
Related: L-00116 (extends), L-00113 (related_to)

High-lucidity sessions — systematic, meta-level, philosophical about the system — are rare and perishable. "I may not be this lucid tomorrow, so do what you can when you can." The AI should recognize these windows and maximize capture density because the next session may be purely task-focused. The learnings system exists to encode lucid-state decisions so they persist into less-lucid states. Corollary: zero features built with 24 learnings produced is a productive session when the lucidity is there.

---

## L-00137
Type: process_rule
Tags: prompts, agents, quality
Confidence: high
Status: active
Date: 2026-03-02T05:30:00-05:00
Related: L-00016 (depends_on), L-00001 (related_to)

Prompt review catches errors dramatically cheaper than output rework. Brian reviewed 5 agent prompts line-by-line before execution, catching 5 violations that would have caused full re-runs. Quality-gating at the prompt layer (input) is the highest-leverage checkpoint in agent-based workflows. Post-execution QA is necessary but is the expensive fallback, not the primary defense.

---

## L-00138
Type: process_rule
Tags: rules, design, precision
Confidence: high
Status: active
Date: 2026-03-02T05:30:00-05:00
Related: L-00128 (related_to)

When a rule feels wrong, replace it with the actual constraint it was proxying for — don't tweak the number. Flat 10-call limit → "be purposeful, stop at natural decision boundaries." Arbitrary recursion depth → diagnose spiraling by purposelessness, not depth. The diagnostic for constraint quality: does the rule penalize correct behavior? If yes, it's a proxy — find the real constraint. Brian demands logical precision: "IFF" means the biconditional. "Generally fine" is not a rule.

---

## L-00140
Type: process_rule
Tags: review, methodology, corpus-analysis
Confidence: high
Status: active
Date: 2026-03-02T05:30:00-05:00
Related: L-00133 (extends), L-00124 (related_to)

"Read each line closely, tell me your impressions" is not a summary request — it's a structural audit. Identify emergent clusters across entries, find the philosophical foundation, surface gaps between what the document promises (curated sections) and what exists (raw accumulation only), assess maturity signals, and report inter-entry relationships no single entry reveals. Close read differs from keyword scan (L-00133's /review-signals) by operating on structure and meaning, not pattern matching. The output is cluster identification + gap analysis + maturity assessment, not a précis.

---

## L-00141
Type: process_rule
Tags: methodology, capture, curation
Confidence: high
Status: active
Date: 2026-03-02T05:30:00-05:00
Related: L-00140 (depends_on), L-00133 (related_to)

In HOW-I-WORK corpus, Brian's direct quotes ("we want to be 1", "half the length", "I may not be this lucid tomorrow") carry more signal per token than the third-person observations wrapping them. When curating accumulation entries into sections, quotes should survive verbatim — the surrounding gloss can be compressed or restructured. Curation heuristic inferred from the close-read process itself: the entries that anchored cluster identification were quotes, not observations.

---

## L-00142
- **Type:** process-rule
- **Tags:** [agent-prompts, scope-sizing, verification, blast-radius]
- **Confidence:** high — demonstrated by schema-standardization agent overscope
- **Status:** active
- **Date:** 2026-03-02
- **Related:** L-00143, L-00127, L-00131

Agent prompts that bundle independent migrations into one dispatch create debugging surface area proportional to the product, not the sum, of their scopes. Schema standardization prompt combined two orthogonal operations: mechanical rename (L-NNNN → L-NNNNN, 414 references) and judgment-heavy conversion (70 HOW-I-WORK entries needing Type/Tags/Confidence classification). If the rename breaks, the diff contains both changes. If a classification is wrong, you're reviewing it inside a 414-line rename diff. One agent prompt per independent migration. Verification is only as good as the isolation of what you're verifying.

---

## L-00143
- **Type:** process-rule
- **Tags:** [scope-sizing, active-scan, verification, context-limits, agent-prompts, response-discipline, token-budget, calibration]
- **Confidence:** high — synthesized from L-00127, L-00131, L-00142 and repeated scope failures
- **Status:** active
- **Date:** 2026-03-02
- **Related:** L-00127, L-00131, L-00142, lib/decision-log.sh

**Active Scan: before every prompt is written for an agent, or response is executed against a user prompt, or for any activity that could push limits of any kind, the proper process scope sizing rituals must be employed.**

The scope of any work unit — prompt, response, agent dispatch, or commit — must be set by its verification method and its token budget, not its task list. Two changes that require different verification strategies are different work units, regardless of thematic relatedness.

**Token budget estimation applies project-wide.** The degradation ceiling formula from lib/decision-log.sh is the canonical method for any context-consuming activity:

degradation_ceiling = max_context × quality_factor (default 0.6, calibrate from actuals)
estimated_cost = input_tokens + expected_output + reasoning_overhead
available_room = degradation_ceiling - estimated_cost

Budget allocation: 5% for build loop agents, 8–10% for general system activities. Use estimate_feature_tokens() with cost-log.jsonl actuals when available; fall back to spec_tokens × 15 for first runs.

**Continuous calibration from actuals:**
- Build loop: cost-log.jsonl already feeds estimate_feature_tokens(). Replace heuristic multipliers with empirical ratios once data exists.
- General system: general-estimates.jsonl records estimated vs actual per activity type. estimate_general_tokens() blends actuals with heuristic (graduated: 1 sample = 20% actuals, 5+ = 100%).
- Never treat a heuristic as permanent. Every default is an initial guess tagged for replacement by empirical data. Mean error >20% after 5+ runs triggers mandatory update to the source number.

**Scope sizing ritual (run before every prompt/response/dispatch):**
1. Count and classify work items. State each item's verification method in one sentence.
2. Estimate token budget via degradation ceiling with show-your-work line-by-line breakdown. If it doesn't fit at applicable %: split.
3. Check verification isolation. Different methods = different dispatches.
4. Split or proceed. Stash progress per L-00131 between units.
5. State the plan: "N items, verification per item, estimated [X of Y] tokens at N%."

Diagnostic: if verification requires more than one method, or estimated tokens exceed available room, the scope contains more than one work unit.
