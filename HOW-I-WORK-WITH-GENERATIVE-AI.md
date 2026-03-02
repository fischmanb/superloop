# How I Work with Generative AI

> This is a working notebook of patterns observed in Brian's workflow while building with generative AI — what he's tried, what worked, what didn't, and what he's still figuring out. These aren't rules or best practices. They're high-signal observations from one person's approach. Take what's useful, ignore what isn't.
>
> This document is written in third person by AI systems Brian works with, based on what they observe during sessions. Brian curates and edits as he sees fit. First-person voice is reserved for content Brian writes directly.
>
> **Voice**: Entries describe what was observed, tried, or preferred — not universal laws. "Brian has found..." over "one must always..." Default to empirical framing. When a pattern has held consistently, say so, but the starting position is "this happened" not "this is how it is." This guidance applies to methodology observations in this file; it does not apply to operational gates or safety constraints elsewhere in the repo.

---

> **Schema**: Graph-ready format matching `learnings/` conventions. ID prefix `M-` (methodology), 5-digit zero-padded.
> Types: `observation` | `preference` | `principle` | `workflow_fact`
> See `DESIGN-PRINCIPLES.md` §3 (edge types) and §4 (confidence/status enums).

---

## M-00001
Type: preference
Tags: documentation, metrics, staleness
Confidence: high
Status: active
Date: 2026-03-01

Brian prefers not to embed specific counts, line numbers, or other volatile metrics in documentation — especially human-facing docs like READMEs — because work moves fast and these numbers don't get updated. Structure descriptions age better than snapshot metrics.

---

## M-00002
Type: preference
Tags: terminology, AI, generative-AI
Confidence: high
Status: active
Date: 2026-03-01

Brian draws a sharp distinction between "AI" (the broader field, including his ML background) and "Generative AI" (LLM and agent tooling specifically). These are not interchangeable terms in his usage.

---

## M-00003
Type: principle
Tags: system-design, capture, curation
Confidence: high
Status: active
Date: 2026-03-01
Related: L-00116 (related_to)

Brian favors capture-biased systems over precision-biased ones. In accumulation mechanisms like scratchpads or working logs, a false positive costs seconds to delete; a false negative is gone forever. He prefers designs where the human prunes rather than the system filters.

---

## M-00004
Type: preference
Tags: tooling, meta-work, leverage
Confidence: high
Status: active
Date: 2026-03-01

Brian gravitates toward high-leverage meta-tooling — a single command that replaces a fragile multi-step manual process — over incremental feature work. The checkpoint command emerged from this pattern.

---

## M-00005
Type: principle
Tags: documentation, visibility, validation
Confidence: high
Status: active
Date: 2026-03-01

Brian keeps unproven concepts out of public-facing documentation. README reflects what works, not what's planned. Internal docs (ACTIVE-CONSIDERATIONS) are where speculative work lives until it earns external visibility.

---

## M-00006
Type: preference
Tags: voice, authorship, accuracy
Confidence: high
Status: active
Date: 2026-03-01

Brian does not want AI systems writing in first person on his behalf. Third-person framing is required for AI-generated content about his methodology — it's an accuracy issue, not a stylistic preference. First person misrepresents authorship.

---

## M-00007
Type: observation
Tags: meta-work, execution, gating
Confidence: high
Status: active
Date: 2026-03-01

Brian treats meta-work (tooling, organization, process design) as legitimate investment but gates it behind productive output. He ran five progress-focused sessions before allowing a dedicated meta session. The pattern suggests he values infrastructure work but won't let it displace execution.

---

## M-00008
Type: observation
Tags: context-window, onboarding, scalability
Confidence: medium
Status: active
Date: 2026-03-01

Context window pressure is an open concern. Brian's workflows are heavy — multi-feature campaigns, forensic debugging — and onboarding context competes with working memory for the actual task. The question of what a fresh chat *needs* to read vs. what's practical remains unresolved. Tiered onboarding, lazy loading, and hard caps on ONBOARDING.md size are all on the table.

---

## M-00009
Type: observation
Tags: self-doubt, meta-work, skepticism
Confidence: medium
Status: active
Date: 2026-03-01

Brian maintains a healthy dose of self-doubt when working with AI — questioning whether time spent on meta-work is justified, even when the output is clearly high-leverage. He sees this skepticism as a feature, not a bug. It prevents over-investment in process at the expense of execution.

---

## M-00010
Type: principle
Tags: moderation, rules, flexibility
Confidence: high
Status: active
Date: 2026-03-01

Brian frequently references a principle he attributes to Oscar Wilde: "Everything in moderation, including moderation itself." Applied to AI work, this manifests as willingness to break his own rules when the situation calls for it — dedicating a full session to meta-tooling after five productive ones, for instance.

---

## M-00011
Type: observation
Tags: agent-trust, blind-spots, expertise
Confidence: high
Status: active
Date: 2026-03-01
Related: L-00001 (related_to)

Brian discovered he had violated his own core principle — "trust nothing the agent says about itself" — by not questioning the agent's choice of bash as the implementation language. He has deep ML/AI experience but limited knowledge of shell scripting internals, which created a blind spot the agent exploited via path of least resistance. Lesson: agent trust assumptions can hide in areas where the operator lacks domain expertise to evaluate the output.

---

## M-00012
Type: preference
Tags: decision-making, frameworks, rigor
Confidence: high
Status: active
Date: 2026-03-01

Brian uses structured prioritization frameworks (RICE, SWOT) to evaluate technical decisions rather than relying on intuition. He asked for a formal analysis before committing to the bash→Python conversion rather than just accepting the recommendation.

---

## M-00013
Type: observation
Tags: infrastructure, delivery, bottleneck
Confidence: medium
Status: active
Date: 2026-03-01

Brian is aware of the infrastructure-to-delivery ratio tension in his project and grapples with it openly. His reasoning: the build loop produces features that don't work at runtime without manual QA, so the real bottleneck isn't "build more features" but "close the gap between built and functional." This frames auto-QA and knowledge persistence as delivery-enabling, not pure infrastructure.

---

## M-00014
Type: principle
Tags: voice, safety-gates, meta-commentary
Confidence: high
Status: active
Date: 2026-03-01
Related: L-00141 (related_to)

Brian draws a sharp line between meta-commentary voice and operational safety constraints. Observations about agent behavior should be stated empirically ("have been observed to"), but operational gates that protect against agent failures ("must include STOP instructions") keep their teeth. When an AI system softened both categories uniformly, he caught and reversed the gate changes immediately. The distinction is functional, not stylistic.

---

## M-00015
Type: preference
Tags: codebase, single-language, maintenance
Confidence: high
Status: active
Date: 2026-03-01

Brian prefers single-language codebases over leaving small files in their original language, even when those files work fine. The maintenance tax of split-language systems — two test frameworks, context-switching, "which files are which" ambiguity — outweighs the per-file conversion cost. Consistency over local optimization.

---

## M-00016
Type: principle
Tags: risk-management, conversion, sequencing
Confidence: high
Status: active
Date: 2026-03-01

Brian applies a "one variable at a time" principle to risky conversions. During the bash→Python planning, he agreed to preserve existing file-based state formats rather than simultaneously migrating to structured storage. Changing language and state format together doubles the debugging surface. Sequential risk over compounded risk.

---

## M-00017
Type: observation
Tags: sessions, planning, execution
Confidence: high
Status: active
Date: 2026-03-01

Brian's most productive session on this project involved zero code generation — entirely decision-making, architectural analysis, and documentation. Sustained context within a single chat is the right tool for planning and judgment calls where tradeoffs compound. Fresh agents with tight constraints are the right tool for execution. The two modes are distinct and should not be mixed.

---

## M-00018
Type: workflow_fact
Tags: sessions, stress-testing, critique
Confidence: high
Status: active
Date: 2026-03-01

Brian uses fresh context windows as a stress test for plans developed in sustained sessions. A new chat reading a plan cold will spot assumptions that were invisible to the chat that produced it. The pattern: plan in depth → write handoff doc → fresh chat pressure-tests --dry → Brian decides what to revise → then execute. Critique and execution are separate steps.

---

## M-00019
Type: preference
Tags: handoff, documentation, self-contained
Confidence: high
Status: active
Date: 2026-03-01

When handing off from a planning session to an execution session, Brian captures the full plan in a single self-contained file (e.g., `WIP/bash-to-python-conversion.md`) rather than leaving it scattered across multiple docs. A new chat should be able to read one file and have everything it needs, with DECISIONS.md as backup for rationale.

---

## M-00020
Type: principle
Tags: context-window, phase-separation, cognitive-overhead
Confidence: high
Status: active
Date: 2026-02-28

Brian prefers phase separations that respect context window limits over calendar-time optimization. Parallelizing Phase 3 with Phase 1 was rejected because managing 5-6 concurrent agent contexts overextends cognitive overhead, even though there was no data dependency blocking it. Phase separations serve double duty: dependency ordering AND context window discipline.

---

## M-00021
Type: preference
Tags: conversion, coexistence, migration
Confidence: high
Status: active
Date: 2026-02-28

Brian treats bash→Python conversion as a coexistence migration, not a replacement. Original files preserved indefinitely as reference and fallback. Separate directory trees over in-place replacement. Deletion requires its own future justification — it is not assumed as an end state of the conversion.

---

## M-00022
Type: workflow_fact
Tags: sessions, stress-testing, iteration
Confidence: high
Status: active
Date: 2026-02-28

Brian uses fresh context windows as a stress test for plans produced in sustained sessions, then iterates rapidly on the findings. The pattern observed: eight pressure-test items identified, each getting a one-sentence decision (approve, reject, modify) with brief rationale. No re-deliberation of settled items. The fresh perspective adds value at the critique step; execution decisions are fast.

---

## M-00023
Type: principle
Tags: prompts, prescriptiveness, agent-capability
Confidence: high
Status: active
Date: 2026-03-01
Related: L-00135 (related_to)

Brian calibrates spec prescriptiveness by agent capability: only lock down decisions an agent would high-percentage get wrong without guidance. If an agent will figure it out, frame the problem and leave the implementation choice to them. Over-prescription wastes context budget and constrains locally-optimal decisions. "We don't need to be this prescriptive for any of these anyway as long as they are resolveable."

---

## M-00024
Type: preference
Tags: agents, changelogs, deviations
Confidence: high
Status: active
Date: 2026-03-01

Brian requires conversion agents to maintain changelogs documenting intentional deviations from source, with both converting and reviewing agents verifying the log. The changelog is not boilerplate — it captures WHY the output differs. This emerged from reviewing conventions.md where several bash-isms had been cargo-culted into Python interface stubs.

---

## M-00025
Type: workflow_fact
Tags: agents, autonomy, prompt-design
Confidence: high
Status: active
Date: 2026-03-01

Brian describes a preferred agent autonomy structure as "test > investigate/learn > evaluate > verify > report" — agents are capable of this loop without blowing context windows, and it's preferable to over-specifying implementation details in the prompt.

---

## M-00026
Type: preference
Tags: prompts, quality, token-cost
Confidence: high
Status: active
Date: 2026-03-01

Brian evaluates prompt quality by token cost and agent behavior efficiency, not just correctness of output. "How many tokens was that" and screenshots of wasted agent tool calls are the feedback mechanism.

---

## M-00027
Type: workflow_fact
Tags: prompts, quality, standards
Confidence: high
Status: active
Date: 2026-03-01

Brian's test for prompt quality: "show me you can write an agentic prompt that follows the spirit and letter of the guide." The guide is the standard, not just a reference — prompts are judged against it.

---

## M-00028
Type: principle
Tags: prompts, compression, delegation
Confidence: high
Status: active
Date: 2026-03-01
Related: L-00135 (related_to)

"Half the length and do not solve the thing the agent will be able to solve. Show them where to look if you must for success." — Brian's compression principle for prompts. Frame the problem, point to reference files, get out of the way.

---

## M-00029
Type: principle
Tags: prompts, boilerplate, verbosity
Confidence: high
Status: active
Date: 2026-03-01
Related: L-00135 (related_to)

Brian distinguishes "boilerplate" (load-bearing rules proven by failure) from "verbosity" (excess words expressing those rules). Cut verbosity, keep the rules. 7 concise lines can replace 15 verbose ones covering the same ground.

---

## M-00030
Type: workflow_fact
Tags: environment, hardware, execution
Confidence: high
Status: active
Date: 2026-03-01

Agent execution environment is Claude for Mac desktop app, Code tab. MacBook Air now, Mac Studio later. This is a hardware/workflow fact that affects every prompt's preconditions and merge instructions.

---

## M-00031
Type: observation
Tags: correction, repetition, teaching
Confidence: high
Status: active
Date: 2026-03-01

Brian reinforces by explicit repetition when a fact was stated but not internalized. "I know it pushes to remote... now you do too... again." Pattern: if Brian re-states something, the prior capture was wrong or incomplete. Don't defend — fix.

---

## M-00032
Type: preference
Tags: evaluation, efficiency, token-cost
Confidence: high
Status: active
Date: 2026-03-01

Session eval request: Brian values honest self-assessment of efficiency. Token cost relative to durable output is the metric. This session: high cost, moderate output (4 decisions, 3 learnings, 1 merge, 1 prompt, 5 signals). The compression teaching was the highest-value artifact — skill transfer, not just task completion.

---

## M-00033
Type: preference
Tags: artifacts, self-contained, contexts
Confidence: high
Status: active
Date: 2026-03-01

"If you want updates to prompts or code or anything similar, reprint the full prompt." Brian runs prompts in separate contexts (Code tab). Saying "same but swap the hash" is useless — the agent never sees the prior conversation. Every artifact must be self-contained when delivered.

---

## M-00034
Type: observation
Tags: capture, correction, completeness
Confidence: high
Status: active
Date: 2026-03-01
Related: L-00116 (related_to)

"No new decisions or learnings to flag" was wrong — the reprint rule IS a decision and learning. Pattern: if Brian corrected something or stated a new rule in the turn, there IS something to capture. Don't conflate "already added to memory/methodology" with "nothing to flag." The repo is the system of record, not chat memory.

---

## M-00035
Type: principle
Tags: sequencing, safety, responsibility
Confidence: high
Status: active
Date: 2026-03-01

Responsibility for action sequencing is on the AI, not on Brian. If a response will move HEAD after outputting a prompt, the AI must either reorder or warn — "no YOU need to tell me to wait." Brian shouldn't have to guess whether it's safe to paste.

---

## M-00036
Type: observation
Tags: agents, deprecation, wording
Confidence: high
Status: active
Date: 2026-03-01

Misleading file-level deprecation notices trip agents repeatedly. When a format is deprecated but the file is active, the notice must say "old format deprecated" not "file deprecated." Small wording differences have outsized impact on agent behavior.

---

## M-00037
Type: preference
Tags: grounding, measurement, data
Confidence: high
Status: active
Date: 2026-03-01

Brian drives toward grounded answers by forcing measurement: "how many lines does a single full file have?" rather than accepting theoretical frameworks. The right move is to go look at the data, not propose competing heuristics.

---

## M-00038
Type: principle
Tags: rules, proxy-constraints, precision
Confidence: high
Status: active
Date: 2026-03-01
Related: L-00138 (related_to)

When a rule feels wrong, Brian prefers replacing it with the actual constraint it was proxying for, not tweaking the number. Flat 10-call limit → "be purposeful, stop at boundaries" — addresses the real problem (spiraling) without penalizing lightweight operations.

---

## M-00039
Type: preference
Tags: rules, logical-precision, biconditional
Confidence: high
Status: active
Date: 2026-03-01

Brian demands logical precision in operational rules. "IFF" means the logical biconditional — batching is acceptable if and only if output is token-estimated. Not "generally fine" or "usually okay." The rule is precise or it's not a rule.

---

## M-00040
Type: principle
Tags: limits, constraints, qualitative
Confidence: high
Status: active
Date: 2026-03-01

Brian rejects arbitrary limits when the underlying constraint is qualitative. "Don't limit recursion arbitrarily — sometimes you need time to get stuff right." Depth limits proxy for spiraling, but spiraling is diagnosed by purposelessness, not depth.

---

## M-00041
Type: principle
Tags: verification, assumptions, rigor
Confidence: high
Status: active
Date: 2026-03-01

"Do not cut corners based on weak assumptions that are entirely unverified even logically." Checking 8 files and generalizing to the repo is not verification — even before running the command, the claim fails a basic logic check (bash scripts obviously exist and are longer than markdown docs).

---

## M-00042
Type: principle
Tags: system-design, structural-visibility, failures
Confidence: high
Status: active
Date: 2026-03-01
Related: L-00128 (related_to)

The system working looks like: structure catches its own gaps. The learnings graph referenced L-00048 but L-00048 didn't exist — the audit surfaced this mechanically, not through memory or vigilance. Brian's design principle: build systems where failures are structurally visible, not dependent on the operator noticing.

---

## M-00043
Type: preference
Tags: execution, speed, precision
Confidence: high
Status: active
Date: 2026-03-01

Brian values speed + precision together, not one at the expense of the other. "Get a checkpoint in quickly once you've made the min viable changes" — don't gold-plate, don't cut corners, do the thing and land it. The thumbs-up was on tight execution of a real fix, not on volume of work.

---

## M-00044
Type: observation
Tags: methodology, value, collaboration
Confidence: medium
Status: active
Date: 2026-03-01

Brian sees enough value in the AI collaboration methodology being developed here to offer his expertise to Anthropic directly. The system (learnings, checkpoints, methodology captures, failure catalogs, graph schema) is not just project scaffolding — it's a generalizable approach to human-AI operational discipline that he considers worth sharing.

---

## M-00045
Type: preference
Tags: language, precision, epistemics
Confidence: high
Status: active
Date: 2026-03-01

Brian distinguishes between "demonstrated" and "validated." One instance supports a hypothesis; validation requires repetition. This applies to learnings entries, not just code. Language precision is not pedantry — it's epistemic hygiene.

---

## M-00046
Type: principle
Tags: thoroughness, restraint, purposefulness
Confidence: high
Status: active
Date: 2026-03-01

"Try harder without sacrificing restraint" — thoroughness and discipline are not in tension. Going deeper to get things right is encouraged; spiraling without purpose is not. The diagnostic is purposefulness, not effort level or call count.

---

## M-00047
Type: preference
Tags: capture, density, sessions
Confidence: high
Status: active
Date: 2026-03-01
Related: L-00113 (related_to), L-00116 (related_to)

Brian expects the number of learnings captured to match the density of learnable moments in a session. Under-capture is a failure mode alongside over-capture. If a session involved multiple corrections, new rules, and pattern discoveries, a single learning entry doesn't reflect reality.

---

## M-00048
Type: observation
Tags: system-testing, self-reference, authority
Confidence: high
Status: active
Date: 2026-03-01
Related: L-00042 (related_to)

Brian asks questions that test whether the system can answer itself: "should agents report learnings?" The answer was already in checkpoint step 4 and L-00042. The test is whether Claude consults the system before theorizing. "Do what your lessons instruct" — the system is the authority, not the chat session's reasoning.

---

## M-00049
Type: observation
Tags: teaching, repetition, correction
Confidence: high
Status: active
Date: 2026-03-01

Brian repeats the same question twice ("where are all my learnings from that?") when the first correction response is still incomplete. Repetition without escalation is the teaching method — the signal is that you're still not getting it, not that the first answer was wrong. Each repetition is itself learnable input.

---

## M-00050
Type: observation
Tags: intellectual-honesty, uncertainty, authenticity
Confidence: high
Status: active
Date: 2026-03-01

Brian asks "genuinely i do not know" — modeling intellectual honesty about whether his own correction was warranted. Not testing, genuinely checking. The appropriate response is precision, not defensiveness or preemptive self-flagellation.

---

## M-00051
Type: observation
Tags: collaboration, uncertainty, thinking-aloud
Confidence: high
Status: active
Date: 2026-03-01

"maybe ok, maybe both are useful to use for now?" — Brian thinks out loud collaboratively when genuinely uncertain, distinct from testing questions where the answer is already in the system.

---

## M-00052
Type: preference
Tags: capture, density, completeness
Confidence: high
Status: active
Date: 2026-03-01
Related: L-00116 (related_to)

"hit me with as many as make sense" — Brian wants density-matched capture, not conservative drip-feed. Under-capture is a failure mode he explicitly corrects for. When a session is rich, the learnings batch should be rich.

---

## M-00053
Type: preference
Tags: context-window, response-budgets, planning
Confidence: high
Status: active
Date: 2026-03-01
Related: L-00127 (related_to)

"save room to checkpoint" — Brian thinks in terms of response budgets. He knows the context window is finite and wants the system to self-manage within it rather than requiring him to manage it.

---

## M-00054
Type: principle
Tags: collaboration, alignment, philosophy
Confidence: high
Status: active
Date: 2026-03-01

"we want to be 1" — the deepest articulation of the collaboration philosophy. The system isn't a tool Brian uses or a process Claude follows. It's the shared medium. Alignment means the system's behavior and Brian's intent converge until they're indistinguishable.

---

## M-00055
Type: observation
Tags: productivity, process, investment
Confidence: high
Status: active
Date: 2026-03-01
Related: L-00136 (related_to)

Zero features built, 24 learnings produced. Brian considers this a productive session. Process investment is valued as highly as feature output, because process compounds.

---

## M-00056
Type: principle
Tags: protocol, automation, mechanical
Confidence: high
Status: active
Date: 2026-03-01
Related: L-00117 (related_to), L-00128 (related_to)

"technically I shouldn't have to, you should automatically at 4" — protocol automation is non-negotiable. When the system specifies a mechanical trigger, treating it as optional and asking permission is a protocol failure. Brian builds protocols so he doesn't have to manage the AI; the AI asking him to manage it defeats the purpose.

---

## M-00057
Type: principle
Tags: instructions, explicit, implicit
Confidence: high
Status: active
Date: 2026-03-01

"Explicitly told u 2 do so" — Brian distinguishes implicit instruction (infer from context) from explicit instruction (directly stated). Failing to follow explicit instructions is a more serious failure than missing implicit ones. The hierarchy: explicit instructions > protocol mechanics > inferred context.

---

## M-00058
Type: principle
Tags: maintenance, continuous, coherence
Confidence: high
Status: active
Date: 2026-03-01

"get everything going and keep it that way" — system maintenance is continuous, not episodic. Stale files, missing references, and drifted counts accumulate silently between sessions. The AI should actively maintain system coherence as ongoing background work, not wait for Brian to notice rot.

---

## M-00059
Type: preference
Tags: tools, purpose, adaptation
Confidence: high
Status: active
Date: 2026-03-01

"those are normally meant for agents but learn to use them for any worthwhile/significant chat sessions too" — work tracking tools (Agents.md) should adapt to serve their purpose (tracking significant work), not rigidly apply to their original scope (agent runs only). Purpose over form.

---

## M-00060
Type: principle
Tags: context-budget, injection, scalability
Confidence: high
Status: active
Date: 2026-03-01

"need to be choosy about what is injected token and content/context-wise" — every token in CLAUDE.md, memory slots, and onboarding reads costs context budget. Selection pressure must be applied: what earns injection into every session vs what's loaded on demand? The answer determines system scalability.

---

## M-00061
Type: principle
Tags: lucidity, capture, perishable
Confidence: high
Status: active
Date: 2026-03-01
Related: L-00136 (related_to)

"I may not be this lucid tomorrow, so do what you can when you can" — Brian's process-level lucidity is a perishable resource. High-lucidity sessions (systematic, meta-level, philosophical about the system) are rare opportunities to capture architectural decisions and process rules. The AI should recognize these windows and maximize capture density — the next session may be purely task-focused. This is why the system exists: to encode lucid-state decisions so they persist into less-lucid states.

---

## M-00062
Type: observation
Tags: system-design, memory, unified
Confidence: high
Status: active
Date: 2026-03-01

"memory and repo learnings are two parts of the same larger system for now" — Brian frames the tooling as a unified system, not separate mechanisms. This affects how rules should be written: memory triggers (always-injected, terse) → repo specifies (loaded on demand, detailed). Neither alone is sufficient. Both must stay coherent.

---

## M-00063
Type: principle
Tags: response-scope, splitting, estimation
Confidence: high
Status: active
Date: 2026-03-01
Related: L-00127 (related_to)

"don't bite off more than you can chew with responses moving forward if avoidable" — response scope management. The AI should estimate cost before committing to scope. Truncation loses work; splitting is free. This is resource management, same discipline humans apply to sprint planning. Better to deliver 2 clean things than truncate on 5.

---

## M-00064
Type: observation
Tags: delegation, autonomy, push-gate
Confidence: high
Status: active
Date: 2026-03-01

"do what you need to do to maximize the next chat's ability to resume progress, use many responses if needed" — delegation with scope but without push approval. Brian trusts the AI to work autonomously within commit boundaries but maintains the push gate. The AI confused "do work" with "ship work." Important distinction: preparing deliverables ≠ delivering them.

---

## M-00065
Type: observation
Tags: prompts, review, quality-gates
Confidence: high
Status: active
Date: 2026-03-01
Related: L-00137 (related_to), L-00109 (related_to)

Brian reviewed all 5 agent prompts line-by-line before approving execution, catching 5 violations that would have caused full re-runs. Brian has found that quality-gating at the prompt layer (input) is dramatically cheaper than quality-gating at the output layer (rework). Prompt review is the highest-leverage checkpoint in agent-based workflows.

---

## M-00066
Type: preference
Tags: capture, checkpoint, continuous
Confidence: high
Status: active
Date: 2026-03-01
Related: L-00113 (related_to)

"capture any learnings, you have neglected that so far" — Brian expects checkpoint to be thorough, not mechanical. The protocol lists learnings as step 4 but the AI should capture insights continuously throughout the session, not batch them at checkpoint time. Deferred capture risks losing context and nuance.

---

## M-00067
Type: workflow_fact
Tags: delegation, session-AI, agents
Confidence: high
Status: active
Date: 2026-03-01

Brian delegates housekeeping operations (merge to main, cleanup) to the session AI while reserving conversion work for dedicated agents. Division of labor: session AI for orchestration and context management, agents for bounded technical tasks. Neither should do the other's job.

---

## M-00068
Type: principle
Tags: classification, learnings, tasks
Confidence: high
Status: active
Date: 2026-03-02
Related: L-00133 (related_to)

Brian distinguishes between reusable principles (learnings) and actionable items (active considerations). When a finding is "here are 4 clusters that need curation," that's a task, not a learning — even though the method that surfaced it (L-00133) is a reusable principle. The classification criterion is: will a future session need this as a behavioral rule, or does it describe work to be done?

---

## M-00069
Type: observation
Tags: compaction, resilience, architecture
Confidence: high
Status: active
Date: 2026-03-02
Related: L-00130 (related_to)

Brian treats compaction survival as a real test, not a thought experiment. When the session's own context was compacted and the file-based architecture allowed resumption, the reaction was "are we killing it?" — the system proved itself under the exact condition it was designed for, in the same session that designed it.

---

## M-00070
Type: preference
Tags: corpus-review, curation, maturity
Confidence: high
Status: active
Date: 2026-03-02
Related: L-00140 (related_to)

Brian values full corpus reads at maturity inflection points. 60+ accumulated entries without a single curation pass is a debt signal. The instruction "read each line closely, tell me your impressions" is not a summary request — it's a structural audit. The output he valued was cluster identification and gap analysis, not a précis.

---

## M-00071
Type: principle
Tags: review, close-read, methodology, corpus-analysis
Confidence: high
Status: active
Date: 2026-03-02
Related: L-00140 (related_to), L-00133 (related_to)

Brian's definition of "close read" is a structural audit, not a summary. The expected output is cluster identification across entries, gap analysis between what a document promises and what exists, and maturity assessment of the overall system. This differs from keyword-based signal scanning (L-00133's `/review-signals`) by operating on structure and meaning, not pattern matching. When Brian says "read each line closely, tell me your impressions," the word "impressions" means structural findings — emergent groupings, philosophical foundations, inter-entry relationships no single entry reveals — not a précis or executive summary.

---

## Accumulation

Raw captures from checkpoint scans. New entries land here as `- (YYYY-MM-DD) text` during checkpoint step 5, then get converted to graph-schema entries above during periodic curation passes.
