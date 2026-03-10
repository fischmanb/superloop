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
Date: 2026-03-01
Related: L-00109 (related_to), L-00016 (related_to)

Checkpoint step 4 (learnings) must use active scan, not passive recall. The original wording "if any surfaced: flag" produced under-capture — a short session was declared "none new" without reviewing agent outcomes, corrections, or near-misses. Step 5 (methodology signals) already had active scan language ("scan session for...") and produced rich output. Step 4 needed the same structure. Active scan categories: agent completions (validate/contradict existing learnings?), Brian's corrections (each is a candidate), new rules or patterns, empirical findings, failures or near-misses. Under-capture is a failure mode equal to over-capture. Match capture density to session density.

---

## L-00114
Type: process_rule
Tags: documentation, propagation, protocol
Confidence: high
Status: active
Date: 2026-03-01
Related: L-00113 (depends_on)

Protocol changes must propagate to all consumption points. A rule has (at minimum) a definition point (e.g. checkpoint.md), a summary point (e.g. ONBOARDING.md), and a delivery point (e.g. core.md that fresh sessions read). Changing one without the others creates silent drift — the protocol says one thing, the onboarding path teaches another. Discovered when L-00113 was written to checkpoint.md and ONBOARDING.md but not core.md until Brian corrected. Checklist for any protocol change: (1) definition file, (2) ONBOARDING.md summary, (3) core.md if it's a constitutional learning, (4) any ACTIVE-CONSIDERATIONS references.

---

## L-00115
Type: process_rule
Tags: documentation, counts, staleness, maintenance
Confidence: high
Status: active
Date: 2026-03-01
Related: L-00114 (related_to)

Numeric references in documentation rot silently. ONBOARDING.md said "38 entries" when actual was 57. ACTIVE-CONSIDERATIONS said "63 graph-compliant" and "~47 old-format" — both wrong. Nobody noticed because prose ages gracefully but numbers go stale on every commit. Mitigation: `/verify-learnings-counts` slash command performs mechanical count and compares against documentation claims. Wired into checkpoint step 4 propagation check.

---

## L-00116
Type: process_rule
Tags: checkpoint, learnings, defaults
Confidence: high
Status: active
Date: 2026-03-01
Related: L-00113 (depends_on)

"Nothing to capture" must never be the default assumption. The default should be "something to capture" and the scan must find reasons to skip, not reasons to include. The checkpoint immediately after L-00113 was committed demonstrated the failure: the AI performed the new active scan categories but still concluded "no new learnings" — because the default was still passive. The bias must flip: assume every session produces learnings unless the scan proves otherwise.

---

## L-00117
Type: process_rule
Tags: protocol, adoption, latency
Confidence: high
Status: active
Date: 2026-03-01
Related: L-00113 (depends_on), L-00116 (related_to)

New protocol rules have a one-response adoption latency. L-00113 codified active scan. The very next checkpoint executed step 4 with the new categories but still under-captured — the behavioral pattern hadn't changed despite the written rule changing. A fresh session reading L-00113 cold would likely apply it more faithfully than the session that just wrote it, because the session that wrote it still carries the old behavioral inertia. Implication: after writing a new process rule, explicitly test it in the same session by re-running the step it modifies. Mechanical enforcement: `/verify-propagation` step 5 flags self-test requirement when process-rules.md has new entries.

---

## L-00118
Type: process_rule
Tags: core-learnings, onboarding, delivery
Confidence: high
Status: active
Date: 2026-03-01
Related: L-00114 (depends_on)

core.md is the actual delivery mechanism for learnings to fresh sessions. If a learning isn't in core.md, fresh sessions won't know it exists unless they happen to read the type-specific file. The onboarding protocol reads core.md — it does not read all type files. Therefore any learning that would cause a consequential mistake if missed must be in core.md. The selection criterion: "if a fresh session doesn't know this, will it make a mistake that matters?" If yes, it's core.

---

## L-00127
Type: process_rule
Tags: response-scope, work-items, planning
Confidence: high
Status: active
Date: 2026-03-01
Related: L-00113 (related_to)

Count work items BEFORE the first tool call, every response. The instruction exists in memory ("Count work items BEFORE first tool call. >3 distinct work items or >15 tool calls = split across responses") but was not followed in the response that failed — it attempted learnings capture, three file integrations, and system wiring all at once. The count must be explicit and visible, not implicit. State "N work items this response, splitting M for next" before starting work. A failed response wastes more time than two successful ones.

---

## L-00128
Type: process_rule
Tags: learnings, enforcement, mechanical-vs-prose
Confidence: high
Status: active
Date: 2026-03-01
Related: L-00113 (depends_on), L-00115 (validates), L-00116 (validates)

Learnings that remain prose get ignored; learnings that become mechanical checks get followed. L-00113 (active scan) was prose — the very next checkpoint under-captured. `/verify-learnings-counts` (L-00115) is mechanical — it runs grep, compares numbers, reports discrepancies. The pattern: when a learning identifies a recurring failure mode, the fix is not a better-worded rule but a tool or command that enforces the rule without requiring the AI to remember it. Prose rules require behavioral compliance. Mechanical checks require only invocation.

---

## L-00131
Type: process_rule
Tags: checkpoint, context-loss, multi-response
Confidence: high
Status: active
Date: 2026-03-01
Related: L-00130 (depends_on), L-00127 (related_to)

Multi-response checkpoints must stash progress incrementally. Checkpoints spanning multiple responses are vulnerable to the same context loss L-00130 addresses. Each completed step must be written to files before proceeding to the next. Pattern: write learnings to stash file → commit or update .onboarding-state → proceed to methodology signals → stash again. If context dies mid-checkpoint, the completed steps survive. Instruction origin: Brian's "stash as you go to prevent lost progress."

---

## L-00133
Type: process_rule
Tags: methodology, review, corpus-analysis
Confidence: high
Status: active
Date: 2026-03-01
Related: L-00124 (extends), L-00128 (related_to)

Corpus-level review is a distinct operation from keyword-based signal scanning. `/review-signals` greps HOW-I-WORK for keywords matching existing learnings. Reading the full corpus end-to-end revealed structure that keyword matching cannot: emergent clusters (prompt engineering, agent autonomy, session types, capture philosophy), a philosophical foundation ("we want to be 1"), and accumulation-without-curation debt. Periodic full-read review — not just keyword scan — surfaces patterns that exist between entries, not within them.

---

## L-00135
Type: process_rule
Tags: prompts, agents, compression
Confidence: high
Status: active
Date: 2026-03-01
Related: L-00016 (extends), L-00020 (related_to)

"Half the length and do not solve the thing the agent will be able to solve. Show them where to look if you must for success." Calibrate spec prescriptiveness by agent capability — only lock down decisions an agent would high-percentage get wrong. Token cost and agent behavior efficiency are the quality metrics, not just output correctness. Distinguish boilerplate (load-bearing rules proven by failure) from verbosity (excess words expressing those rules). Cut verbosity, keep the rules.

---

## L-00136
Type: process_rule
Tags: capture, sessions, meta-work
Confidence: high
Status: active
Date: 2026-03-01
Related: L-00116 (extends), L-00113 (related_to)

High-lucidity sessions — systematic, meta-level, philosophical about the system — are rare and perishable. "I may not be this lucid tomorrow, so do what you can when you can." The AI should recognize these windows and maximize capture density because the next session may be purely task-focused. The learnings system exists to encode lucid-state decisions so they persist into less-lucid states. Corollary: zero features built with 24 learnings produced is a productive session when the lucidity is there.

---

## L-00137
Type: process_rule
Tags: prompts, agents, quality
Confidence: high
Status: active
Date: 2026-03-01
Related: L-00016 (depends_on), L-00001 (related_to)

Prompt review catches errors dramatically cheaper than output rework. Brian reviewed 5 agent prompts line-by-line before execution, catching 5 violations that would have caused full re-runs. Quality-gating at the prompt layer (input) is the highest-leverage checkpoint in agent-based workflows. Post-execution QA is necessary but is the expensive fallback, not the primary defense.

---

## L-00138
Type: process_rule
Tags: rules, design, precision
Confidence: high
Status: active
Date: 2026-03-01
Related: L-00128 (related_to)

When a rule feels wrong, replace it with the actual constraint it was proxying for — don't tweak the number. Flat 10-call limit → "be purposeful, stop at natural decision boundaries." Arbitrary recursion depth → diagnose spiraling by purposelessness, not depth. The diagnostic for constraint quality: does the rule penalize correct behavior? If yes, it's a proxy — find the real constraint. Brian demands logical precision: "IFF" means the biconditional. "Generally fine" is not a rule.

---

## L-00140
Type: process_rule
Tags: review, methodology, corpus-analysis
Confidence: high
Status: active
Date: 2026-03-01
Related: L-00133 (extends), L-00124 (related_to)

"Read each line closely, tell me your impressions" is not a summary request — it's a structural audit. Identify emergent clusters across entries, find the philosophical foundation, surface gaps between what the document promises (curated sections) and what exists (raw accumulation only), assess maturity signals, and report inter-entry relationships no single entry reveals. Close read differs from keyword scan (L-00133's /review-signals) by operating on structure and meaning, not pattern matching. The output is cluster identification + gap analysis + maturity assessment, not a précis.

---

## L-00141
Type: process_rule
Tags: methodology, capture, curation
Confidence: high
Status: active
Date: 2026-03-01
Related: L-00140 (depends_on), L-00133 (related_to)

In HOW-I-WORK corpus, Brian's direct quotes ("we want to be 1", "half the length", "I may not be this lucid tomorrow") carry more signal per token than the third-person observations wrapping them. When curating accumulation entries into sections, quotes should survive verbatim — the surrounding gloss can be compressed or restructured. Curation heuristic inferred from the close-read process itself: the entries that anchored cluster identification were quotes, not observations.

---

## L-00142
- **Type:** process-rule
- **Tags:** [agent-prompts, scope-sizing, verification, blast-radius]
- **Confidence:** high — demonstrated by schema-standardization agent overscope
- **Status:** active
- **Date:** 2026-03-01
- **Related:** L-00143, L-00127, L-00131

Agent prompts that bundle independent migrations into one dispatch create debugging surface area proportional to the product, not the sum, of their scopes. Schema standardization prompt combined two orthogonal operations: mechanical rename (L-NNNN → L-NNNNN, 414 references) and judgment-heavy conversion (70 HOW-I-WORK entries needing Type/Tags/Confidence classification). If the rename breaks, the diff contains both changes. If a classification is wrong, you're reviewing it inside a 414-line rename diff. One agent prompt per independent migration. Verification is only as good as the isolation of what you're verifying.

---

## L-00143
- **Type:** process-rule
- **Tags:** [scope-sizing, active-scan, verification, context-limits, agent-prompts, response-discipline, token-budget, calibration]
- **Confidence:** high — synthesized from L-00127, L-00131, L-00142 and repeated scope failures
- **Status:** active
- **Date:** 2026-03-01
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

## L-00146
- **Type:** process-rule
- **Tags:** [dispatch-sequencing, dependencies, merge-order, preconditions]
- **Confidence:** high — Dispatch 4 agent couldn't find Dispatch 1's output
- **Status:** active
- **Date:** 2026-03-01
- **Related:** L-00142, L-00143, L-00131

When dispatch N depends on dispatch N-1's output files, the merge of N-1 to the working branch is a precondition of N, not a follow-up. Dispatch 4 (replace token proxy) couldn't find `lib/general-estimates.sh` because the checkpoint branch carrying Dispatch 1's output hadn't been merged to main. The agent created the file from scratch — correct decision in this case (no prior content to preserve), but a larger file with existing logic would have been silently overwritten. Dispatch dependency = merge dependency. State this explicitly in the dispatch prompt's Preconditions section: "Requires [branch] merged to [target]. Verify with: `git log --oneline [target] | grep [commit-msg-fragment]`".

## L-00150
- **Type:** process-rule
- **Tags:** [execution-routing, prompt-indirection, desktop-commander, context-limits]
- **Confidence:** high — three checkpoint prompts failed before direct execution succeeded
- **Status:** active
- **Date:** 2026-03-01
- **Related:** L-00147, L-00143, M-00073

When the execution environment is available, execute directly instead of writing prompts. Three checkpoint prompts were written, downloaded, and failed when pasted into Code tab sessions with existing context. The work could have been done directly via Desktop Commander from claude.ai. Writing a prompt to hand off to another Claude instance adds indirection, context overhead, and a failure mode (the prompt itself consuming tokens in an already-loaded session). Direct execution is faster and eliminates the handoff failure class. Exception: agent dispatches that create branches need Claude Code's git permissions and branch isolation.

## L-00151
- **Type:** process-rule
- **Tags:** [pre-work-verification, redundant-work, scope-sizing, state-check]
- **Confidence:** high — an agent prompt was written for 5 work items that were already complete
- **Status:** active
- **Date:** 2026-03-01
- **Related:** L-00142, L-00143

Before writing an agent prompt, verify that the target work items aren't already done. A prompt was written for 5 changes (core injection, scope format, token reporting, behavioral compliance, core maintenance) — all 5 had already been completed by two earlier agent sessions working on related tasks. The prompt was scoped, estimated, and ready to run for work that didn't exist. A 30-second grep of each target file for the expected output string would have caught this. Rule: for each work item in any planned agent prompt, grep the target file for the expected artifact before writing the prompt. If the artifact exists, skip the item.

---

## L-00155
- **Type:** process-rule
- **Tags:** [rule-infrastructure-gap, prose-vs-mechanical, dependency-ordering, L-00128]
- **Confidence:** high — observed three times in one session
- **Status:** active
- **Date:** 2026-03-01
- **Related:** L-00128, L-00143, L-00142

A process rule that references infrastructure which doesn't exist yet is decoration. This session wrote L-00143 (scope sizing ritual requiring `estimate_general_tokens()`), then wrote agent prompts saying "use the estimator" — but the estimator function didn't exist for three more dispatches. The rule was real, the prompts referenced it, and nothing worked because the dependency wasn't built yet. This is L-00128 (prose gets ignored) at the meta level: the rule about using the tool was itself prose until the tool existed. Countermeasure: when writing a process rule, immediately check whether its dependencies exist. If not, the first dispatch must build the dependency, and subsequent rules/dispatches must wait.

---

## L-00159
- **Type:** process-rule
- **Tags:** [migration-debt, language-migration, compound-cost, bash-to-python]
- **Confidence:** high — lib/general-estimates.sh written in bash during active bash→Python migration
- **Status:** active
- **Date:** 2026-03-01
- **Related:** L-00111, L-00124

Writing new infrastructure in the outgoing language during a migration creates compound debt. The session identified that Dispatch 1 would create `lib/general-estimates.sh` — a new bash file — while the project was actively converting bash to Python. Claude flagged this ("building infrastructure in the outgoing language") and recommended Python implementation. The agent wrote bash anyway because the prompt specified bash. The file now works, passes tests, and needs to be migrated. New code written in the old language has double cost: the effort to write it plus the effort to migrate it. During active migrations, new infrastructure should use the target language unless there's a blocking dependency on the old system.

---

## L-00163
- **Type:** process-rule
- **Tags:** [learnings-quality, self-containment, jargon, system-legibility, actionability]
- **Confidence:** high — Brian corrected L-00151 for using project-internal jargon ("dispatch") that future readers wouldn't understand
- **Status:** active
- **Date:** 2026-03-01
- **Related:** L-00128, L-00141

Every learning entry must be self-contained, use system-legible language, and be actionable where possible. Project-internal jargon (e.g., "dispatch" meaning "agent prompt") makes entries opaque to a fresh Claude instance that onboards without session context. Each entry is read by future instances that may never have seen the term — if the entry requires external context to parse, it fails at its purpose. Three requirements: (1) define or avoid jargon — use plain descriptions a new reader can follow; (2) include enough context that the learning is understandable without reading other entries; (3) state a concrete countermeasure or action, not just an observation. An entry that says "dispatches should be sequenced" teaches nothing; "agent prompts with file dependencies must verify those files exist before execution" is actionable.


---

## L-00164
- **Type:** process-rule
- **Tags:** [token-estimation, calibration-loop, mechanical-enforcement, prompt-structure, L-00162-enforcement]
- **Confidence:** high — Phase 4a prompt shipped without Token Usage Report; chat session wrote prose estimate without calling estimate_general_tokens
- **Status:** active
- **Date:** 2026-03-01
- **Related:** L-00143 (related_to), L-00162 (depends_on), L-00155 (related_to)

Token estimation must be wired into both chat-session scope rituals and agent prompt structure. Phase 4a agent prompt omitted the Token Usage Report section entirely; the chat session wrote a prose scope estimate ("~15,000 tokens") without calling `estimate_general_tokens` or showing arithmetic. Both are violations of L-00143 (scope sizing ritual) and L-00162 (estimation without computation is decoration) that survived because neither was mechanically enforced at prompt-writing time. The calibration loop in `general-estimates.jsonl` received no data from the session until Brian manually ran the report. Countermeasure: (1) memory slot 18 enforces chat-side — call `estimate_general_tokens` or compute manually before writing agent prompts; (2) Token Usage Report is now a required section in both `PROMPT-ENGINEERING-GUIDE.md` (section 5) and `conventions.md`, making omission a visible structural gap in any prompt review; (3) every agent prompt template must include the `source lib/general-estimates.sh` + `get_session_actual_tokens` + `append_general_estimate` block as a verification step equal in status to `git diff --stat`.

---

**L-00165**
- **Type:** empirical_finding
- **Tags:** token-estimation, calibration, orchestration
- **Confidence:** high
- **Status:** active
- **Date:** 2026-03-02
- **Related:** L-00162 (depends_on), L-00164 (related_to)

Token estimation calibration from Phase 4 reveals a consistent pattern: mechanical conversion (Phase 4a, support modules) ran -16.7% over estimate (15k est → 18k actual); orchestration+dedup conversion (Phase 4b, BuildLoop) ran -30% over estimate (18k est → 28k actual). Orchestration code with deduplication mandates runs significantly hotter than mechanical translation because the agent must reason about control flow refactoring, not just syntax conversion. Calibration rule: apply 1.3x multiplier to estimates for orchestration-heavy agent prompts. Phase 5 (overnight-autonomous.sh) estimated at 20k using this multiplier.

---

**L-00166**
- **Type:** process_rule
- **Tags:** conversion, scope-estimation, deduplication
- **Confidence:** high
- **Status:** active
- **Date:** 2026-03-02
- **Related:** L-00111 (related_to), L-00165 (related_to)

When converting variant scripts that share a codebase, diff function lists between the source bash and existing Python modules before scoping the conversion. overnight-autonomous.sh was 1,310 lines but ~80% was copy-pasted from build-loop-local.sh — functions already converted as Python modules in Phases 1-4. Actual new code: ~300 lines. Without this check, the conversion would have been scoped as a 1,310-line job instead of a 300-line composition task. The check is mechanical: extract function names from both scripts, compare, and subtract already-converted functions.

---

**L-00167**
- **Type:** failure_pattern
- **Tags:** external-communication, verification, honesty
- **Confidence:** high
- **Status:** active
- **Date:** 2026-03-02
- **Related:** L-00171 (related_to)

Described the eval sidecar as "a learning system that makes each successive build smarter" for external stakeholder communication. When challenged ("does it actually do that?"), source code review revealed: EVAL_NOTES is a one-line string field, there is no learnings extraction, no cross-feature pattern analysis, and the campaign summary produces tallies not insights. Aspiration was stated as implemented fact. Countermeasure: read the implementation (specific functions, data structures, output formats) before summarizing capabilities for external audiences. The test: can you point to the function that does this?

---

**L-00168**
- **Type:** failure_pattern
- **Tags:** checkpoint, protocol-compliance, context-management
- **Confidence:** high
- **Status:** active
- **Date:** 2026-03-02
- **Related:** L-00070 (related_to), M-00087 (related_to)

When Brian said "checkpoint," executed steps 1 (read state), 7 (commit), and a partial step 8 (update state), skipping steps 2-6 entirely (flush captures, decisions, learnings, methodology signals, ONBOARDING.md drift check). This is the exact failure mode checkpoints exist to prevent — context drift across session boundaries when learnings and state aren't flushed. The 8 steps are a deterministic checklist precisely because the temptation to shortcut under time pressure is predictable. Execute sequentially without optimization.

---

**L-00169**
- **Type:** empirical_finding
- **Tags:** communication, documentation, stakeholder
- **Confidence:** medium
- **Status:** active
- **Date:** 2026-03-02
- **Related:** L-00167 (related_to)

ASCII flow diagram of the build loop system was immediately useful for external stakeholder communication. Brian's boss reviewed it and asked clarifying questions within the same session. Worth creating for any system with >3 interacting components, especially when the system will be explained to people outside the immediate development context. HTML export with explicit dark text styling needed for readability in downloaded artifacts (markdown rendered pale grey).

---

**L-00170**
- **Type:** architecture_gap
- **Tags:** eval-sidecar, learning-system, quality-gate
- **Confidence:** high
- **Status:** active
- **Date:** 2026-03-02
- **Related:** L-00167 (related_to)

The eval sidecar has a documented gap between its current implementation (quality gate) and its intended purpose (learning system). Current: per-commit mechanical scoring (diff stats, type redeclarations) + agent eval scoring (framework compliance, scope assessment, integration quality) + repeated_mistakes string fed back into next build prompt + campaign-end aggregate tallies. Missing: structured learnings extraction from build outcomes, cross-feature pattern analysis, decision quality evaluation, "what worked and why" synthesis. EVAL_NOTES is a one-line string, not structured data. Campaign summary counts pass/warn/fail but doesn't produce actionable findings. Gap tracked in ACTIVE-CONSIDERATIONS #4, blocked on migration completion + real Python campaign data.

---

**L-00171**
- **Type:** process_rule
- **Tags:** verification, honesty, grounding
- **Confidence:** high
- **Status:** active
- **Date:** 2026-03-02
- **Related:** L-00167 (depends_on)

The implementation-grounding test: when describing what a system does, the claim is valid only if you can point to the specific function, data structure, or output format that implements it. If you cannot, the capability is aspirational and must be stated as such. This applies to both external communication (stakeholder descriptions) and internal planning (agent prompt design). Derived from the eval sidecar incident where "extracts learnings and analyzes patterns" was stated as implemented when the actual implementation is a one-line EVAL_NOTES string field.


---

## L-00172 — Scope audit prompts to general principles, not symptoms of known examples

- **Type:** process_rule
- **Tags:** prompt-engineering, audit, generalization
- **Confidence:** high
- **Status:** active
- **Date:** 2026-03-03
- **Related:** L-00143 (related_to), L-00163 (related_to)

When writing audit or evaluation prompts, frame checks as general principles rather than specific known symptoms. An audit prompt that says "check for client→server import chains" catches one failure mode. A prompt that says "check for dependency boundary violations where a module in layer A transitively reaches layer C" catches the class. Symptom-scoped prompts encode the last failure; principle-scoped prompts catch the next one. Derived from project-agnostic audit (Round 46) where initial framing was overly coupled to stakd-specific patterns.

---

## L-00173 — Apply settled design reasoning to analogous modules without being prompted

- **Type:** process_rule
- **Tags:** consistency, design-decisions, agent-behavior
- **Confidence:** high
- **Status:** active
- **Date:** 2026-03-03
- **Related:** L-00011 (related_to)

When a design decision is settled for one module (e.g., use `sh` instead of `bash` for portability in build_gates.py), apply the same reasoning to all analogous modules in the same codebase without waiting to be told. Each module that shares the same constraints should inherit the same solution. Requiring the operator to re-state settled reasoning per module is a process failure — it means the agent treated the decision as local when it was systemic. Derived from Rounds 47-49 where portability fixes had to be applied file-by-file after the principle was already established.

---

## L-00174 — Do not add speculative ecosystem support without confirming targets

- **Type:** process_rule
- **Tags:** scope, assumptions, stakeholder-alignment
- **Confidence:** high
- **Status:** active
- **Date:** 2026-03-03
- **Related:** L-00143 (related_to)

Before adding support for languages, frameworks, or ecosystems not already present in the project, ask the operator what they actually target. Adding Go dead-export scanning or Rust import counting to a Python/TypeScript project is speculative scope expansion — it costs implementation time, increases test surface, and adds code that may never execute against real data. If the operator wants broad ecosystem support, they'll say so. Default to what exists. Derived from Round 48 where multilang eval patterns were added without confirming Brian's target stack.

---

## L-00176 — Prompt pipelining: write next prompt while current agent executes

- **Type:** process_rule
- **Tags:** throughput, prompt-engineering, pipeline-design
- **Confidence:** high
- **Status:** active
- **Date:** 2026-03-03
- **Related:** L-00175 (related_to), L-00143 (related_to)

When dispatching sequential agent prompts, the next prompt can be written while the current agent executes — provided the current phase's output schema is deterministic. The prompt references the schema contract, not the actual output data. Preconditions in the next prompt verify the prior phase landed (grep-checks for expected classes/functions). Applied across Phases 4a→4b→5 of the auto-QA pipeline: Phase 4b prompt was written before 4a returned, Phase 5 before 4b returned. Zero rework from this approach. The prerequisite is that output schemas are fully specified before implementation — if the schema might change during implementation, pipelining creates rework risk. Saves significant wall-clock time in multi-phase pipelines.

---

## L-00178 — Chat sessions must gate-check elaborate prompt work against problem layer

- **Type:** process_rule
- **Tags:** prompt-engineering, over-engineering, solution-layer, gate-check
- **Confidence:** high
- **Status:** active
- **Date:** 2026-03-04
- **Related:** L-00001 (reinforces), L-00177 (derived from same incident), L-00125 (related_to)

When a user proposes or begins building an elaborate agent prompt, the chat session must ask: is the problem actually in the agent behavior layer, or is it in infrastructure, detection, or gating? A prior session helped build a 377-line prompt with 62 constraint patterns, a web-verification ceremony, and a detection+injection pipeline in prompt_builder.py — all to prevent transitive import violations. The actual root cause was a 10-line detection ordering bug in build_gates.py where `tsc --noEmit` matched before `next build`. The chat never questioned whether prompting was the right layer. This is L-00001 applied to solution design: the same way agents' self-assessments shouldn't be trusted, agents' compliance with injected rules shouldn't be the primary enforcement mechanism when a mechanical gate can catch the violation directly.

**300-line rule**: If any single solution's prompt content would exceed 300 lines, the chat must stop and perform an alternatives analysis before proceeding. Enumerate at least two non-prompting alternatives (build gate, linter, test, existing tooling). The chat may still proceed with the prompt approach if it validates that no mechanical alternative exists — but it must show the analysis. The gate-check question: "Does a build tool, linter, test, or existing gate already enforce this constraint? If yes, ensure it runs. If no, then consider prompt injection."

Mechanical enforcement in prompt_builder.py: `MAX_INJECTED_SECTION_LINES` (150) and `MAX_TOTAL_PROMPT_LINES` (400) catch programmatic injection bloat at test time. Never blocking at runtime.

---

## L-00179 — Speculative ecosystem coverage without observed failures is waste

- **Type:** process_rule
- **Tags:** scope, speculation, maintenance-cost, yagni
- **Confidence:** high
- **Status:** active
- **Date:** 2026-03-04
- **Related:** L-00174 (reinforces), L-00143 (related_to)

Do not build preventive infrastructure for ecosystems that have zero observed failures. The Round 50 prompt included 50 constraint patterns across Go, Rust, Python, and general TypeScript — ecosystems where no transitive boundary violation had ever occurred in actual campaigns. Each pattern requires maintenance (docs change, frameworks evolve, false patterns mislead agents). The only observed failures were in Next.js. Writing 50 speculative patterns to prevent hypothetical failures in 5 other ecosystems is engineering effort with no data justifying it. When observed failures emerge in a new ecosystem, add coverage then — the marginal cost of a single constraint file is low. The upfront cost of maintaining six files with 62 patterns against zero signal is not.

## L-00180 — Silent instruction overrides are never acceptable

- **Type:** process-rule
- **Tags:** chat-discipline, Brian-correction, communication
- **Status:** active
- **Date:** 2026-03-04
- **Related:** L-00178 (reinforces)

When deviating from an explicit Brian instruction, always state what you're doing differently and why in the same response. Silent overrides — even when the reasoning is sound — are never acceptable. Brian must always know when his instructions are being modified and the rationale. This was triggered by repeatedly ignoring the stash-reads instruction without explanation, which caused wasted tool calls, a failed response, and extra billing costs.

## L-00181 — Stash key findings from file reads to a scratch file; never re-read same regions

- **Type:** process-rule
- **Tags:** tool-efficiency, chat-discipline, Brian-correction
- **Status:** active
- **Date:** 2026-03-04
- **Related:** L-00180 (reinforces)

When reading files for investigation, stash key findings (function locations, patterns, class boundaries) to a local scratch file (e.g. `/tmp/sdd-scratch.md`) after first read. Never re-read the same file regions across tool calls. This is a hard rule. Violating it caused 11+ redundant reads across two responses, one of which failed to complete, burning Extra Usage billing.

## L-00185 — pytest --durations=0 is the first tool for slow test diagnosis

- **Type:** process-rule
- **Tags:** test-diagnosis, surgical-targeting, efficiency
- **Status:** active
- **Date:** 2026-03-04
- **Related:** L-00184 (same session)

`pytest --durations=0` is the first tool for slow test diagnosis. It shows wall time per test, sorted descending. In both `test_overnight_autonomous` and `test_build_loop`, it immediately isolated the 2-3 tests responsible for 99%+ of runtime. No need to bisect, profile, or add timing instrumentation.

## L-00186 — The scratch file stash pattern works and is mandatory

- **Type:** process-rule
- **Tags:** scratch-file, tool-efficiency, stash-reads
- **Status:** active
- **Date:** 2026-03-04
- **Related:** L-00181 (operationalizes)

The `/tmp/sdd-scratch.md` pattern works. Stash diagnostic findings (durations output, line numbers, root cause) after first tool call, then execute fixes from the stash with zero re-reads. This session: one `--durations` call → stash → 3 edits → done. Previous session without stashing: 11+ reads across two responses, one failed to complete.

## L-00187 — Brian's design pressure test is a deliberate 3-step sequence

- **Type:** process-rule
- **Tags:** design-methodology, pressure-test, Brian-pattern
- **Status:** active
- **Date:** 2026-03-04
- **Related:** L-00178 (complementary)

Brian's design pressure test is a deliberate 3-step sequence: (1) commit the plan to a file first — this creates accountability and a reviewable artifact, (2) pressure test against the stated goal — does the plan actually achieve what it claims?, (3) pressure test for simplicity — can the same outputs be achieved via simpler, more extensible, or more efficient means? The order matters: committing first prevents retroactive plan-washing. Goal testing catches fundamental gaps. Simplicity testing catches over-engineering. Results feed back as concrete revisions to the committed plan. First observed during the campaign intelligence system design (`WIP/campaign-intelligence-system.md`), where it surfaced 7 improvements including project-configurable quality dimensions, mechanical convention checks, round consolidation, and cold-start seeding.

## L-00188 — Build foundations early when the data model is clear; feature-flag capabilities that aren't yet validated

- **Type:** process-rule
- **Tags:** architecture, YAGNI, foundation, Brian-pattern
- **Status:** active
- **Date:** 2026-03-04
- **Related:** L-00187 (same session)

Brian rejects pure YAGNI when the data model is clear and the implementation plan is concrete. "I don't want to defer for the counter-argument reasons" — when you know the API surface and the extension points, building the abstraction early is cheaper than refactoring raw code later. The middle path for capabilities that are needed but not yet validated: include the infrastructure, feature-flag it off. This avoids both premature activation AND later refactor debt. Observed during the campaign intelligence system design (`WIP/campaign-intelligence-system.md`): `vector_store.py` (the JSONL-backed feature vector store) was kept in the first implementation round rather than deferred to the fifth, because the sectioned schema and CRUD API were well-defined across a 6-round plan. The pattern rule registry was included from the second round but gated behind `ENABLE_PATTERN_ANALYSIS` env var until validated with real campaign data.

## L-00189 — Separate intra-run real-time feedback from cross-run accumulated learning

- **Type:** process-rule
- **Tags:** design-methodology, signal-sources, system-thinking, Brian-pattern
- **Status:** active
- **Date:** 2026-03-04
- **Related:** L-00187 (same session)

When designing a learning system, separate Application into (a) intra-run real-time feedback and (b) cross-run accumulated learning. They have different data availability (partial vs complete), different latency requirements (must be fast vs can be offline), and different feedback loops (injection into next feature vs model training between campaigns). Also: always ask what other systems produce signals that should feed the model. During the campaign intelligence system design, Brian connected auto-QA's runtime signals and the eval sidecar's build-time signals into one unified feature vector — neither system alone captures the full picture. A feature can pass all build gates and still break the app at runtime (stakd-v2: 28/28 features built, `npm run build` fails on transitive import).

## L-00190 — Quantitative outcome signals are insufficient; capture qualitative choice signals mechanically

- **Type:** process-rule
- **Tags:** design-methodology, qualitative-signals, Brian-correction
- **Status:** active
- **Date:** 2026-03-04
- **Related:** L-00189 (complementary)

Quantitative outcome signals (pass/fail, counts, durations) are necessary but insufficient for a learning system. Qualitative signals about *choices* — did the agent use proper abstractions, follow project conventions, maintain architectural boundaries — predict downstream failures that outcome metrics miss. The stakd-v2 transitive import (28/28 built, app broken) is the canonical example: all quantitative gates passed, but a convention violation (server import from client component) caused the failure. Mechanical static analysis (import graph validation, type coverage, duplication detection) should capture qualitative signals where possible, with agent judgment reserved for genuinely subjective dimensions only. Identified during the campaign intelligence system design when Brian asked whether the system captured qualitative code choices — it didn't.

## L-00191 — Learnings must be self-contained: always include project and context references

- **Type:** process-rule
- **Tags:** learnings-quality, self-contained, meta-learning, Brian-correction
- **Status:** active
- **Date:** 2026-03-04
- **Related:** L-00180 (same class — communication discipline)

Every learning entry must be legible to a fresh reader with no session context. References to implementation details (round numbers, file names, design phases) must be grounded with the project or plan they belong to. "Round 2" means nothing without "Round 2 of the campaign intelligence system (`WIP/campaign-intelligence-system.md`)." This applies to all new captures going forward AND should be checked during checkpoint step 4 active scan — if an existing learning contains ungrounded references, flag it for revision. The failure mode: learnings that made sense in-session become cryptic within a week because the context evaporated.

## L-00192 — Validate infrastructure against real data before building intelligence on top of it

- **Type:** process-rule
- **Tags:** dependency-ordering, validation-first, Brian-pattern
- **Status:** active
- **Date:** 2026-03-04
- **Related:** L-00187 (complementary), L-00188 (same session)

Don't build intelligence on top of unvalidated infrastructure. Brian reordered the campaign intelligence system (`WIP/campaign-intelligence-system.md`) below auto-QA validation against the CRE lease tracker project because CIS's value proposition depends on auto-QA producing validated runtime signals. Build-only CIS is just a fancier eval sidecar. General principle: when System B consumes System A's output, validate System A against real data before building System B. The cost of discovering System A doesn't work after building System B is high — it can reshape what System B needs to capture.

## L-00194 — Methodology observations go straight to graph schema; no raw accumulation backlog

- **Type:** process-rule
- **Tags:** methodology-capture, graph-schema, process-change, Brian-correction
- **Status:** active
- **Date:** 2026-03-04
- **Related:** L-00191 (same class — capture quality)

M-entries (methodology observations in `HOW-I-WORK-WITH-GENERATIVE-AI.md`) must be written in graph schema format from the start — same as L-entries. Same format, same quality bar, same self-contained requirement (L-00191). The prior approach was to dump raw notes in an "Accumulation" section and "periodically curate" them into graph schema. "Periodic curation" had no trigger, no cadence, and no definition — it was deferred work that never fired. The raw notes were harder to find and use than schema entries. Going forward: every observation either meets the bar for a graph-schema M-entry or isn't worth capturing. The Accumulation section is a backlog to clear, not an active intake.

## L-00196 — The merge/push approval gate is absolute — no implicit approval, no exceptions for small changes

- **Type:** process-rule
- **Tags:** merge-push-discipline, repeated-violation, Brian-correction
- **Status:** active
- **Date:** 2026-03-05
- **Related:** L-00180 (same class — communication discipline)

Every `git push` to origin and every `git merge` to main requires Brian's explicit "yes" in the immediately preceding message. No implicit approval, no "obvious" exceptions, no batching a push with a commit that wasn't approved. This was violated three times in one session (2026-03-05): unauthorized merge of the token report branch, direct commit+push of agent timeout fix, direct commit+push of monorepo fallback fix. Each felt "obvious" or "small." The rule exists precisely because small changes feel safe and bypass scrutiny. Brian's words: "don't push without clarity on whether you can!!!" The cost of asking is one message. The cost of violating is trust erosion.

## L-00198 — "Stash" means save locally; disambiguate urgent save directives before acting

- **Type:** process-rule
- **Tags:** disambiguation, push-vs-save, destructive-default, Brian-correction
- **Status:** active
- **Date:** 2026-03-05
- **Related:** L-00196 (same class — push discipline)

When Brian says "stash" or "push it" during imminent context loss (compaction warning), default to the least-destructive interpretation: save locally, not push to remote. Disambiguate before acting. On 2026-03-05, "you are about to get compacted push it" was interpreted as `git push origin main` instead of "persist the work locally so it survives." A confidential IP assessment was pushed to a public repository visible to Brian's boss. The correct action was to write the file locally and confirm before any remote operation. General rule: when a directive is ambiguous between a reversible action (local save) and an irreversible action (public push), always choose reversible and confirm.

---

## L-00199
Type: process_rule
Tags: build-loop, knowledge-system, async, critical-path
Confidence: high
Status: active
Date: 2026-03-07T23:00:00-05:00
Related: L-00001 (related_to)

Knowledge extraction from builds must be entirely async and post-hoc. The build loop's critical path is sacred. Any extraction added to the critical path (even lightweight) compounds across a 45-feature campaign into meaningful wall-time loss. The correct insertion point is the eval sidecar — it already runs async after each commit.

---

## L-00200
Type: process_rule
Tags: knowledge-graph, architecture, sqlite, graphrag
Confidence: high
Status: active
Date: 2026-03-07T23:00:00-05:00
Related: L-00199 (requires)

The typed knowledge graph uses SQLite + FTS5 + embeddings, NOT Microsoft GraphRAG. GraphRAG discovers structure via community detection on unknown corpora. Superloop's structure is already known (universal → framework → technology → instance). Typed edges (instance_of, generalizes_to, requires, conflicts_with, supersedes, caused_by) are written explicitly at extraction time, not discovered. SQLite is portable, zero-infra, and continuously writable without reindexing.

---

## L-00201
Type: process_rule
Tags: knowledge-graph, synthesis, preprocessing, build-loop
Confidence: medium
Status: planned
Date: 2026-03-07T23:00:00-05:00
Related: L-00200 (instance_of)
Related: L-00199 (requires)

Implementation order for knowledge graph: write path first (knowledge_store.py + sidecar extension), read path second (spec_preprocessor.py). A preprocessor with an empty knowledge base is a no-op. Get data accumulating before building the read path. BFS on dependency chain + semantic similarity + BM25 keyword pass → synthesis call → inject as "Build Intelligence" section in spec.

---

## L-00207
Type: process_rule
Tags: generalization, lint, build-gates, project-agnostic, package-json
Confidence: high
Status: active
Date: 2026-03-08T00:00:00-05:00
Related: L-00205 (instance_of)
Related: L-00003 (related_to)

When fixing a detection gap, do not add the specific missing filename or tool to an enumeration list. Enumerate-by-config-file is a pattern that is always one ecosystem version behind. The correct fix is to read what the project itself declares: `package.json` scripts for JS/TS ecosystems, `pyproject.toml` tool sections for Python, `Cargo.toml` for Rust. If the project says `"lint": "next lint"`, run `npm run lint` — that is the project's own declaration of how it lints itself, and it will remain correct across tool version changes. This generalizes to all ecosystem-level detection: prefer reading the project's own build/test/lint declarations over inferring from config file presence.

## L-00209 — hardcoding pending feature count in project.yaml silently caps campaign when roadmap changes
ID: L-00209
Type: node
Tags: max_features, project-yaml, sdd-config, hardcoded-count, roadmap, runtime-vs-config, campaign-cap
Confidence: high
Status: active
Date: 2026-03-08T00:00:00-05:00
Related: L-00207 (related_to)

`max_features: 44` was written into `.sdd-config/project.yaml` to match the current pending feature count. This is wrong in two ways: (1) the count goes stale the moment a feature is added or completed, silently capping future campaigns at an arbitrary number with no warning; (2) `MAX_FEATURES` is a runtime cap ("only build N features today"), not a project property — it belongs at launch time, not in version-controlled config. The correct behavior when `MAX_FEATURES` is unset is to build all pending features, which the build loop derives at runtime from the roadmap. General rule: never hardcode a count that is derivable from a source of truth. Config files declare policies (how to build, what model to use, how many retries); they do not snapshot counts that change as the project evolves.


---

## L-00210
Type: process-rule
Tags: !wrap, !learn, checkpoint, extract-learnings.md, checkpoint.md, compound-command, HANDOFF-PROTOCOL.md, .specs
Confidence: high
Status: active
Date: 2026-03-08
Related: M-00092 (same session)

Before designing any command that may integrate existing protocols, read every protocol file it subsumes.

---

## L-00211
Type: process-rule
Tags: in-context-inference, compaction, .onboarding-state, memory, repo-files, read-first, incomplete-knowledge, design
Confidence: high
Status: active
Date: 2026-03-08
Related: L-00210 (related_to), L-00212 (related_to)

Logic in user chats must never be built from in-context inference without first reading the relevant files. Context may be incomplete: post-compaction state is lossy, memories lag behind writes, long sessions drift from file reality. The constituent files are the spec. Read them.

---

## L-00212 — When filesystem access is available, files are authoritative over context; read and stash immediately
ID: L-00212
Type: process_rule
Tags: Desktop-Commander, compaction, context-cache, sdd-scratch, file-stash, onboarding-state, tool-access, session-start
Confidence: high
Status: active
Date: 2026-03-08
Related: L-00211 (related_to), L-00130 (related_to), L-00213 (related_to)

When filesystem access is available, files are the authoritative source. In-context knowledge is a lossy cache: compaction drops state, memories lag behind writes, and long sessions drift from file reality. The rule: the moment tool access is established or re-established, read the relevant protocol files and stash key findings to /tmp/sdd-scratch.md before any other work. A read without a stash is discarded the moment the next tool call executes. This applies on session start, after compaction events, after a sequence of prompt-only exchanges, and after any gap where file state may have advanced without context reflecting it. The compaction boundary — not elapsed time — is what invalidates context. When in doubt, read. Stashing is not optional.

---

## L-00213 — Learnings body must be the prevention rule maximally generalized, not an incident description
ID: L-00213
Type: process_rule
Tags: extract-learnings.md, learnings-body, rule-authoring, generalization, knowledge-capture
Confidence: high
Status: active
Date: 2026-03-08
Related: L-00163 (related_to), L-00212 (instance_of)

A learnings body that describes what happened — the incident, the sequence, the context — is malformed. The body must be the rule that prevents the failure in the broadest possible set of future cases. L-00163 requires a concrete countermeasure; this extends it: the countermeasure must generalize across cases, not just fix the instance that prompted it. Test: read only the body. Does it tell a future instance what to do in any situation where this failure mode could occur? Or does it describe a past situation? If the latter, rewrite it. The incident that surfaced the rule belongs in a comment or Related field at most — not in the body.

---

## L-00214 — Handoff run commands must reference the canonical entry point or the archived path will be invoked
ID: L-00214
Type: process_rule
Tags: handoff.md, build-loop-local.sh, build_loop.py, python-migration, dead-code, run-command, ACTIVE-CONSIDERATIONS.md
Confidence: high
Status: active
Date: 2026-03-08
Related: L-00130 (related_to), L-00125 (related_to)

When a handoff or ACTIVE-CONSIDERATIONS.md entry includes a run command, it must reference the current canonical entry point — not the path that was valid at time of writing. The bash loop (`scripts/build-loop-local.sh`) was archived as dead code after the bash→Python migration. A handoff written before or during that transition propagated the bash command forward, and the next session launched the archived loop without noticing. The correct entry point is `py/auto_sdd/scripts/build_loop.py` via `.venv/bin/python -m auto_sdd.scripts.build_loop`. Rule: before writing any run command into a handoff or ACTIVE-CONSIDERATIONS.md, verify the entry point against INDEX.md or the current codebase. If the entry point changed during the session, update every location that references the old one before closing.

---

## L-00215 — Indirect signal inference about process state is unreliable when the operator has direct terminal visibility
ID: L-00215
Type: process_rule
Tags: pgrep, log-file, build_loop.py, claude-subprocess, process-state, operator-visibility, terminal
Confidence: high
Status: active
Date: 2026-03-08
Related: L-00212 (related_to)

When the operator has a terminal open and reports a process is running, that report is authoritative over indirect signals. A build loop suspended on a 1800s agent subprocess shows no new log file, no build_loop pid (it handed off to the claude subprocess), and no new git commits — all of which read as "not running" from indirect inspection. Express uncertainty about what the process is doing, not whether it exists. Corollary: indirect signals (pgrep, log recency, git log) are valid when the operator has no direct visibility; they are not valid as a rebuttal to an operator's direct observation.

---

## L-00216 — Build command re-detection must run after the agent, not before
ID: L-00216
Type: process_rule
Tags: detect_build_check, build_loop.py, build_cmd, next.config.ts, F-0, scaffold-features, re-detection
Confidence: high
Status: active
Date: 2026-03-08
Related: L-00012 (related_to)

Re-detecting build/test commands before the agent runs is wrong for scaffold features that create the config files detection depends on. A feature like F-0 (Project Setup) creates `next.config.ts` — if `detect_build_check` runs before the agent, it finds nothing and returns `""`, and the build gate is skipped for that feature. Re-detection must always happen after `build_result` is captured, so the post-build gates see the project structure the agent actually produced.

---

## L-00217 — SPEC_FILE agent signal must be resolved against project_dir, not loop cwd
ID: L-00217
Type: process_rule
Tags: SPEC_FILE, _validate_required_signals, build_loop.py, drift.py, project_dir, cwd, path-resolution
Confidence: high
Status: active
Date: 2026-03-08
Related: L-00216 (related_to)

When an agent emits a relative `SPEC_FILE` path (e.g., `.specs/features/infrastructure/F-000-project-setup.feature.md`), the loop must resolve it against `project_dir`, not the process working directory. The loop runs from `py/` — a relative path resolves to `py/.specs/...` which does not exist, causing `_validate_required_signals` to return False and silently skip drift checks for every feature. Fix: `(project_dir / spec_file).exists()` when the path is not absolute and `project_dir` is known.

---

## L-00216 — Build command re-detection must run after the agent, not before
ID: L-00216
Type: process_rule
Tags: detect_build_check, build_loop.py, next.config.ts, build_cmd, re-detection, F-0
Confidence: high
Status: active
Date: 2026-03-08
Related: L-00012 (related_to)

Re-detect build/test commands immediately after the agent returns, not before it runs. Pre-agent detection reads the filesystem before the agent has created any new files — scaffolding features (e.g., F-0) create the very config files (next.config.ts, package.json) that enable detection. Running detection before the agent means the first feature that introduces the build system runs with no build gate. Fix: move detect_build_check/detect_test_check calls to the line immediately after build_result is captured, before any gate logic.

---

## L-00217 — SPEC_FILE signal paths must be resolved against project_dir, not loop cwd
ID: L-00217
Type: process_rule
Tags: SPEC_FILE, _validate_required_signals, build_loop.py, project_dir, relative-path, drift-check
Confidence: high
Status: active
Date: 2026-03-08
Related: L-00214 (related_to)

When validating agent-emitted signals that reference file paths (SPEC_FILE, SOURCE_FILES), resolve relative paths against project_dir, not the Python process cwd. The build loop runs from ~/auto-sdd/py/ but agents emit paths relative to the project root (e.g., .specs/features/infrastructure/F-000.feature.md). Path.exists() on an unresolved relative path silently fails, causing drift checks to be skipped for every feature. Fix: in _validate_required_signals, resolve against project_dir before calling .exists(). Extend this pattern to any future signal that emits a project-relative path.

---

## L-00219 — Chat response scope must match request scope exactly

Type: process_rule
Tags: chat-session, scope, response-boundaries, scope-discipline
Confidence: high
Status: active
Date: 2026-03-09
Related: L-00143 (related_to)

Chat responses default to expansive exploration unless explicitly constrained. When Brian asks to "review build logs and report," that means read the build logs and report — not also explore git history, run the test suite, tally costs, and check project state. Prevention rule: before the first tool call, enumerate exactly what was requested. If the request names specific artifacts (build logs), read those and stop. Do not extrapolate adjacent work items. If confused about scope, ask — don't guess expansively. This complements L-00143 (scope sizing ritual) but applies specifically to the chat interface where the temptation is to "be helpful" by exploring beyond the request boundary.

---

## L-00221 — Merge/push action must never share a response with the approval request

Type: process_rule
Tags: git-merge, git-push, merge-gate, response-boundary, ONBOARDING.md
Confidence: high
Status: active
Date: 2026-03-09
Related: L-00005 (related_to), L-00219 (related_to)

The ONBOARDING.md merge/push rule creates a forced wait state: the response presenting the merge request must END there. The merge command goes in the NEXT response, only after Brian's explicit approval in the intervening message. Asking "Merge?" and then running the merge in the same response defeats the gate — the question becomes rhetorical theater, and permission is inferred from context rather than granted explicitly. This was observed directly: "Merge?" followed immediately by `git merge` and `git push` in the same response, without waiting. Prevention rule: when a merge or push is appropriate, end the response with the request. Do not include any git merge or git push command in that response. The next response may only proceed after Brian's explicit "yes" or equivalent.

---

## L-00223 — Working tree must be clean before dispatching agent prompts

Type: process_rule
Tags: git-status, working-tree, agent-dispatch, hard-constraints, clean-state
Confidence: high
Status: active
Date: 2026-03-09
Related: L-00222 (related_to), L-00130 (related_to)

Agents correctly STOP when they encounter pre-existing dirty tracked files outside their allowlist — the hard constraints say "if you encounter ANYTHING unexpected, STOP IMMEDIATELY." This is correct behavior but blocks the implementation. The chat session dispatching the prompt is responsible for ensuring a clean working tree before delivery. Prevention rule: before delivering any agent prompt, run `git status --short` and verify either (a) the working tree is clean, or (b) all dirty files are on the agent's allowlist. If dirty files exist outside the allowlist, commit or stash them first. This is especially important for `general-estimates.jsonl` which is frequently dirty from local token estimates (see L-00222).

---

## L-00226 — Agent prompts must be deliverable as a single copyable block with no internal fenced code blocks

Type: process_rule
Tags: prompt-engineering, copy-paste, code-block, prompt-delivery, triple-backtick
Confidence: high
Status: active
Date: 2026-03-09
Related: L-00178 (related_to), L-00163 (related_to)

Prompts with internal triple-backtick code blocks (e.g., for Agents.md entry templates, bash snippets, or Python examples) create multiple fenced regions when the prompt itself is delivered inside a fenced block. This breaks single-block copy-paste — the user has to manually reassemble pieces. Observed directly: an Agents.md template block inside the prompt split it into three separate blocks. Prevention rule: never use triple-backtick fencing inside a prompt body. Use indentation (4-space) for code samples, or describe the content textually and let the agent write it based on what it actually did. Additionally, do not pre-write the Agents.md entry — the agent writes its own based on its actual work, which is more accurate than a template written before execution.


## L-00229 — Chat sessions must never launch build_loop; Brian runs all builds in Terminal for operational visibility
Type: process_rule
Tags: build_loop, Terminal, chat-session, operational-visibility, start_process, Desktop-Commander
Confidence: high
Status: active
Date: 2026-03-09
Related: L-00020 (related_to)

Brian controls all long-running build processes directly in Terminal. Chat sessions provide run commands, pre-flight context, and analysis — but never execute build_loop themselves. Discovered when chat session launched a build via Desktop Commander start_process and Brian couldn't see progress or interact with it in his Terminal. The control boundary: chat sessions write commands and analyze results, Brian executes.

## L-00230 — Every bug fix must prevent the class of bug, not just the instance
Type: process_rule
Tags: bug-fix, prevention, generalization, closed-loop, system-design, NODE_ENV, check_deps, port-cleanup, --resume
Confidence: high
Status: active
Date: 2026-03-09
Related: L-00175 (generalizes_to), L-00020 (related_to)

Fixing a bug means eliminating the category of failure, not patching the symptom. Every fix must be implemented such that the underlying bug is prevented from happening again — and to every extent possible, in any part of the system. A fix that requires a human to "run X in the shell" or "remember to set Y" is not a fix. The system must be self-healing.

Examples from a single session (2026-03-09):
- NODE_ENV=production in user's shell → didn't tell user to unset it; forced NODE_ENV=development in every subprocess the system controls (claude_wrapper.py + run_cmd_safe)
- Missing devDependencies → didn't say "run npm install"; added check_deps() gate that catches any unresolved package regardless of cause
- Stale dev server blocking port → didn't say "kill it manually"; auto-kill lingering processes on common dev ports before Phase 0
- --resume losing progress → didn't say "restart from scratch"; fixed the code to reuse existing run_id so completed phases are preserved

The test: after your fix, can a different user on a different machine hit the same class of problem? If yes, the fix is incomplete.


## L-00231 — Never claim a pipeline is connected without mechanically verifying reads exist for every write
Type: process_rule
Tags: knowledge-pipeline, data-flow, verification, eval-sidecar, learnings, write_learning, read_latest_eval_feedback, prompt_builder
Confidence: high
Status: active
Date: 2026-03-09
Related: L-00230 (instance_of), L-00175 (related_to)

Told Brian the system was "self-improving" and "compounding knowledge" when the pipeline was broken at 5 junctions: pending.md write-only (128 entries dead), repo learnings never injected (230+ L-series invisible to agents), eval history reader only read latest 1 of 113 JSONs, MistakeTracker volatile (resets every campaign), auto-QA findings trapped in logs. The write side worked. The read side was broken or capped to uselessness. Verification rule: after any claim that data flows from A to B, grep for the actual read call. If no function reads the file that another function writes, the pipe is broken regardless of what the architecture diagram says.

## L-00232 — --resume must preserve run identity; generating a new ID defeats state lookup
Type: failure_pattern
Tags: --resume, run_id, ValidationPipeline, validation-state.json, post_campaign_validation.py, state-persistence
Confidence: high
Status: active
Date: 2026-03-09
Related: L-00230 (instance_of)

ValidationPipeline.__init__() always generated a fresh run_id (`val-{timestamp}`), even with --resume. ValidationState only loads completed_phases when `existing.get("run_id") == self.run_id`, which never matched the old run. Result: --resume silently re-ran all phases from scratch, wasting the ~$7 and ~60 min from the prior partial run. Fix: when resume=True, read the existing state file and reuse its run_id. The identity of a resumable operation must be stable across invocations — any system that generates a new identity on resume has a broken resume.

## L-00233 — Phase 0 must kill lingering dev server processes before binding ports
Type: failure_pattern
Tags: Phase-0, port-3000, lsof, dev-server, health-check, post_campaign_validation.py, RUNTIME_READY
Confidence: high
Status: active
Date: 2026-03-09
Related: L-00230 (instance_of)

Phase 0 starts a dev server then health-checks it. If a previous run's dev server is still on port 3000 (from a crash, Ctrl-C, or prior smoke test), Phase 0 times out on health check — it starts a NEW server that binds a different port, then checks 3000 where the stale server doesn't respond correctly. Fix: scan ports 3000, 3001, 5173, 8080 and kill any listeners before starting. Generalizes to any pipeline step that binds a network port.

## L-00234 — Bash-to-Python migration must grep for every env var guard in the original; dropped guards are silent regressions
Type: failure_pattern
Tags: NODE_ENV, bash-to-python, migration, claude_wrapper.py, run_cmd_safe, devDependencies, npm-install
Confidence: high
Status: active
Date: 2026-03-09
Related: L-00230 (instance_of)

The bash build loop had `NODE_ENV=development` guards around agent and gate subprocess calls (Round 23). The Python rewrite dropped them — `claude_wrapper.py` and `run_cmd_safe()` inherited the parent shell's env verbatim. When the user's shell had `NODE_ENV=production`, npm silently skipped devDependencies (@tailwindcss/postcss, vitest, etc.), producing a project that looked installed but couldn't build. Fix: force `NODE_ENV=development` in every subprocess env. Prevention: during any bash-to-Python migration, grep the original bash for every `export`, `env`, and variable assignment, and verify each has a Python equivalent.

## L-00235 — nohup + tee in zsh causes process suspension; use stdin redirect + disown for background pipelines
Type: failure_pattern
Tags: nohup, tee, zsh, suspended, tty-output, disown, background-process, auto-qa
Confidence: high
Status: active
Date: 2026-03-09
Related: L-00229 (related_to)

Running `nohup command 2>&1 | tee logfile &` in zsh causes `suspended (tty output)` because tee writes to the terminal, which zsh blocks for backgrounded processes. Even `bg %1` re-suspends immediately. The process is alive but permanently frozen. Fix: redirect stdin from /dev/null and disown: `command > logfile 2>&1 < /dev/null & disown`. This fully detaches from the tty. Never use tee for background pipeline logging — write directly to a file and tail -f separately.

## L-00236 — Hardcoded agent timeouts fail at scale; timeouts must be adaptive based on project complexity
Type: empirical_finding
Tags: AGENT_TIMEOUT, timeout, Phase-3, Playwright, auto-qa, token-estimator, general-estimates.jsonl
Confidence: high
Status: active
Date: 2026-03-09
Related: L-00175 (related_to)

900s timeout killed a Phase 3 Playwright agent that was legitimately crawling a 37-feature app (19 of 20 screenshots taken). 3-feature CRE project completed in ~5 min; sitdeck needed 15+ min per complex widget feature. Hardcoded timeouts waste time on small projects and kill legitimate work on large ones. The estimator already logs actual tokens and duration per agent call in general-estimates.jsonl (181 calls, median 382s, P90 521s). Timeout should be f(estimated_tokens, historical_tokens_per_second, buffer_multiplier) with floor 120s and cap 3600s.


## L-00242 — The system cannot audit, diagnose, or capture learnings about itself; a human is the actual closed loop
Type: process_rule
Tags: self-audit, self-diagnosis, closed-loop, knowledge-pipeline, checkpoint, learnings-scan, meta-cognition
Confidence: high
Status: active
Date: 2026-03-10
Related: L-00231 (instance_of), L-00230 (instance_of)

In session 3, three outputs produced all the value: a pipeline audit (5 broken data flows), 5 agent prompts to fix them, and 11 learnings entries. All three were explicitly requested by Brian — none were produced by the system itself. The build loop didn't flag its own broken knowledge pipes. The eval sidecar didn't report that 112 of 113 findings were going nowhere. The checkpoint protocol's learnings scan was skipped repeatedly (counter reset to 0 without running). Brian had to request the audit, request the prompts, request the learnings scan, then request the scan again when it was skipped during checkpoint. The system claims to be a "self-improving closed loop" but the human is the actual loop closure. Until the system can mechanically verify its own data flow connectivity (Prompt 5's retrieval optimization loop is a start), self-improvement is a manual process that depends on the operator noticing what's broken.
