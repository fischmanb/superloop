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
Date: 2026-03-01
Related: L-00133 (related_to)

Brian distinguishes between reusable principles (learnings) and actionable items (active considerations). When a finding is "here are 4 clusters that need curation," that's a task, not a learning — even though the method that surfaced it (L-00133) is a reusable principle. The classification criterion is: will a future session need this as a behavioral rule, or does it describe work to be done?

---

## M-00069
Type: observation
Tags: compaction, resilience, architecture
Confidence: high
Status: active
Date: 2026-03-01
Related: L-00130 (related_to)

Brian treats compaction survival as a real test, not a thought experiment. When the session's own context was compacted and the file-based architecture allowed resumption, the reaction was "are we killing it?" — the system proved itself under the exact condition it was designed for, in the same session that designed it.

---

## M-00070
Type: preference
Tags: corpus-review, curation, maturity
Confidence: high
Status: active
Date: 2026-03-01
Related: L-00140 (related_to)

Brian values full corpus reads at maturity inflection points. 60+ accumulated entries without a single curation pass is a debt signal. The instruction "read each line closely, tell me your impressions" is not a summary request — it's a structural audit. The output he valued was cluster identification and gap analysis, not a précis.

---

## M-00071
Type: principle
Tags: review, close-read, methodology, corpus-analysis
Confidence: high
Status: active
Date: 2026-03-01
Related: L-00140 (related_to), L-00133 (related_to)

Brian's definition of "close read" is a structural audit, not a summary. The expected output is cluster identification across entries, gap analysis between what a document promises and what exists, and maturity assessment of the overall system. This differs from keyword-based signal scanning (L-00133's `/review-signals`) by operating on structure and meaning, not pattern matching. When Brian says "read each line closely, tell me your impressions," the word "impressions" means structural findings — emergent groupings, philosophical foundations, inter-entry relationships no single entry reveals — not a précis or executive summary.

---

## M-00072
Type: observation
Tags: scope-discipline, recursive-application
Confidence: high
Status: active
Date: 2026-03-01
Related: L-00143 (validates)

Brian enforces scope discipline recursively — pointed out that Claude's own response about scope estimation didn't use the scope estimator. The system must apply to itself, not just to agents it dispatches.

---

## M-00073
Type: workflow_fact
Tags: interface-routing, desktop-app, code-tab
Confidence: high
Status: active
Date: 2026-03-01
Related: L-00130 (related_to)

Desktop app Chat tab cannot access local filesystem. Checkpoint protocol requires Code tab (Claude Code). Session routing is a precondition for protocol execution, not an afterthought.

---

## M-00074
Type: observation
Tags: proxy-metrics, calibration, false-confidence
Confidence: high
Status: active
Date: 2026-03-01
Related: L-00145 (validates), L-00143 (related_to)

Token estimation proxy formula produced data that would miscalibrate the estimator it feeds. Confidently wrong data is worse than no data. Brian's instinct to question the report ("does this seem right to you?") caught what the mechanical check could not — the formula validated its own output.

---

## M-00075
Type: preference
Tags: operational-friction, documentation, shell-escaping
Confidence: high
Status: active
Date: 2026-03-01
Related: M-00073

Brian treats small operational friction (zsh `!` escaping in filenames/commit messages) as worth documenting and fixing immediately rather than working around silently. Pattern: if a sharp edge cuts once, file it down before it cuts again. Consistent with L-00128 — prose workarounds get forgotten, mechanical fixes persist.

---

## M-00076
- **Type:** workflow_fact
- **Tags:** [slash-commands, naming-convention, shell-escaping]
- **Confidence:** high
- **Status:** active
- **Date:** 2026-03-01
- **Related:** M-00075, M-00073

`!` prefix in Claude Code slash command filenames escapes the `/`, making the command unreachable. `!learn.md` had to be renamed to `extract-learnings.md`. Naming convention: avoid shell-special characters (`!`, `$`, `#`, backticks, etc.) in command filenames.

---

## M-00077
- **Type:** workflow_fact
- **Tags:** [interface-routing, chat-vs-code, workflow-design]
- **Date:** 2026-03-01
- **Related:** M-00076, L-00152

Brian uses Chat tab (claude.ai / Desktop) for interactive sessions — planning, reviews, extract-learnings, checkpoints — and Code tab for agent dispatches that need git/branch permissions. He expects workflows like "extract learnings" and "checkpoint" to work from Chat via natural language + Desktop Commander, not requiring Code tab infrastructure. Interface routing is deliberate: Chat for thinking, Code for executing.

---

## M-00078
- **Type:** workflow_fact
- **Tags:** [desktop-commander, execution-style, act-dont-instruct]
- **Date:** 2026-03-01
- **Related:** M-00077, L-00150

Brian expects Claude to execute operations (git merges, pushes, conflict resolution, file edits) directly via Desktop Commander from Chat tab — not present bash blocks to copy-paste. "Execute using desktop commander as always." Desktop Commander is Claude's hands. When Claude has the tools to act, it should act. Writing instructions for Brian to execute manually is wasting his time.

---

## M-00079
- **Type:** workflow_fact
- **Tags:** [correction-style, calibration-signals, communication-pattern]
- **Date:** 2026-03-01
- **Related:** M-00020

Brian's correction style is blunt and specific ("you dope", "you loon", "you scoped badly", "you failed"). These are calibration signals, not hostility. Each correction pinpoints exactly what went wrong and what the expected behavior was. Claude should take corrections immediately and apply them — no defensive hedging, no excessive apology, no multi-paragraph acknowledgment of the mistake. Fix the thing and keep moving.

---

## M-00080
- **Type:** methodology_signal
- **Tags:** [show-your-work, transparency, verification, estimation]
- **Date:** 2026-03-01
- **Related:** L-00128, L-00143, L-00155

"Show your work" is a general principle, not just for token estimates. A bare number ("Estimated: ~12k tokens") is decoration that no one can verify. The full calculation (files × lines × tokens/line + overhead = total) is verifiable and exposes errors. This applies to scope estimates, dependency counts, risk assessments — any claim that includes a number. If the number can't be reverse-engineered from the shown work, it's a guess labeled as an estimate. L-00128 (prose gets ignored) is the failure mode; showing the work is the countermeasure.

---

## M-00081
- **Type:** workflow_fact
- **Tags:** [multi-interface, session-architecture, chat-code-dc]
- **Date:** 2026-03-01
- **Related:** M-00077, L-00152

Brian's sessions routinely cross three interfaces with different capabilities: (1) Chat tab for interactive thinking — planning, reviews, learnings extraction, checkpoint coordination; (2) Code tab for agent dispatches needing git branch creation, isolation, and push permissions; (3) Desktop Commander (from Chat) for direct filesystem and git operations on main. The interfaces have different permission models and Claude should know which one it's operating in. Chat + DC can do most things except create new branches. Code tab is for isolated agent work that needs branch protection.

---

## M-00082
- **Type:** observation
- **Tags:** [quality-probing, calibration-test, output-verification]
- **Date:** 2026-03-01
- **Related:** M-00079, L-00145

Brian actively probes output quality rather than passively consuming it. "Does this seem right to you?" is typically a calibration test, not a genuine question — he already suspects the answer and is checking whether Claude catches the problem independently. In this session, he pasted a token report with a broken proxy formula and asked if it seemed right. The correct response is to analyze critically, not to affirm. When Brian asks "does this look right," treat it as a challenge to find what's wrong.

---

## M-00083
- **Type:** principle
- **Tags:** [recursive-self-application, meta-process, eat-your-own-cooking]
- **Date:** 2026-03-01
- **Related:** L-00143, L-00162, M-00080

Brian demands recursive self-application: the system must use its own rules on itself. A session about scope estimation must itself use scope estimation. Brian corrected Claude when a response about the scope estimator didn't use the scope estimator: "that response did not complete, which means you did not use the scope estimator." Rules that apply to agents also apply to the session producing the agents. If the meta-process can't follow its own rules, the rules don't work.

---

## M-00084
- **Type:** observation
- **Tags:** [failure-as-output, emergent-rules, same-session-learning]
- **Date:** 2026-03-01
- **Related:** L-00160, L-00162, L-00155

Process rules emerge from failures in the same session they're needed. L-00143 (scope sizing) was born from context blowouts during the session. L-00145 (proxy formula broken) from the session's own broken reports. L-00147 (context accounting) from the session's own wrong ceiling calculations. The session's failures ARE the session's primary output — the code changes are secondary to the process rules extracted from what went wrong. A session that produces zero failures is either not pushing hard enough or not scanning for them.

---

---

**M-00085**
- **Type:** observation
- **Tags:** verification, escalation, source-grounding
- **Confidence:** high
- **Status:** active
- **Date:** 2026-03-02
- **Related:** L-00167 (related_to), L-00171 (related_to)

Brian tests capability claims with escalating precision. Pattern observed: lets initial description sit, then probes with domain knowledge ("it's meant to do more than that, does it not evaluate the build process/decisions and find learnings?"), then delivers the grounding test ("does it actually do that?"). Responses that survive this sequence are source-grounded (traceable to specific functions/data structures), not documentation-grounded (derived from comments or aspirational design docs). The escalation gives Claude opportunity to self-correct before the direct challenge.

---

**M-00086**
- **Type:** preference
- **Tags:** communication, external-stakeholder, concision
- **Confidence:** high
- **Status:** active
- **Date:** 2026-03-02
- **Related:** M-00085 (related_to), L-00169 (related_to)

External-facing answers need text-message concision. When Brian asked for a response to his boss about the eval sidecar, the first attempt was too detailed (multiple paragraphs, implementation specifics). Boss questions want what-it-does and why-it-matters, not how-it-works. One paragraph max. The audience determines the compression ratio — technical collaborators get architecture; executives get function and value.

---

**M-00087**
- **Type:** principle
- **Tags:** checkpoint, context-management, value-preservation
- **Confidence:** high
- **Status:** active
- **Date:** 2026-03-02
- **Related:** L-00168 (depends_on), L-00070 (related_to)

The checkpoint protocol is the primary value-preservation mechanism across session boundaries, not administrative overhead. Brian flagged both the missed 8-step execution AND the learnings deficit ("there should always be far more learnings proposed"). The checkpoint isn't bookkeeping — it's how session value (observations, patterns, corrections, calibration data) survives context loss. Skipping steps means that value is destroyed. A session that produces good work but shortcuts the checkpoint is strictly worse than a session that does less work but preserves it fully.

---

## M-00088

- **Type:** observation
- **Tags:** trust-building, session-arc, calibration, correction-as-tuning
- **Confidence:** high
- **Status:** active
- **Date:** 2026-03-04
- **Related:** M-00084 (related_to), L-00180 (related_to)

Brian's session arc follows a deliberate calibration pattern: let Claude fail on small tasks, correct sharply, verify the correction takes hold in the same session, then escalate to high-leverage design work once execution is reliable. Observed 2026-03-04: session began with test fixes that required heavy handholding (redundant file reads, failed response, Extra Usage billing). Brian corrected with L-00180 (silent overrides) and L-00181 (stash reads). Once the `test_build_loop` fix completed cleanly using the corrected approach, Brian immediately escalated to product architecture — campaign intelligence system design, auto-QA prioritization, seed data strategy. The corrections aren't punishment; they're tuning. Trust is earned on small things (fix tests without re-reading files), then extended to big things (design the intelligence system).

---

## M-00089

- **Type:** observation
- **Tags:** validation-loop, fast-iteration, run-then-fix
- **Confidence:** high
- **Status:** active
- **Date:** 2026-03-05
- **Related:** L-00192 (validates_principle), M-00088 (complementary)

Brian validates infrastructure through fast iteration loops rather than exhaustive pre-analysis. During auto-QA validation against CRE (`WIP/auto-qa-cre-validation.md`): ran Phase 0 → port conflict (pre-existing servers) → killed, re-ran → health check timeout (wrong path) → merged health fix, re-ran → both ports healthy → full pipeline → Phase 0 failed (root package.json created by previous Phase 1 agent) → fixed fallback logic, re-ran → Phase 0 passed, Phase 1 timed out → increased timeout. Four iterations in rapid succession, each revealing the next real blocker. This is faster and more reliable than trying to predict all failure modes in advance, because production failures are often interaction effects invisible to analysis (e.g., a Phase 1 agent creating artifacts that break Phase 0 on re-run).

---

## M-00090

- **Type:** observation
- **Tags:** artifact-lifecycle, test-infrastructure, beyond-immediate-scope
- **Confidence:** high
- **Status:** active
- **Date:** 2026-03-05
- **Related:** M-00089 (same session)

Brian thinks beyond the immediate run when evaluating test infrastructure decisions. When observing that auto-QA wiped QA credentials on cleanup, his reaction wasn't just "that broke this run" — it was "do we really wanna wipe QA credentials on an Auto-QA fail? We may not even want to do so on a pass." He traced the lifecycle: credentials are needed for manual investigation after failures, for re-running individual phases, for `--resume`, and for back-to-back runs. The cleanup behavior was designed for a single-run worldview; Brian immediately saw the multi-run, multi-mode reality. Pattern: when evaluating any side effect of a pipeline step, ask "what happens to this artifact in every mode the pipeline supports, not just the happy path."

---

## M-00091

- **Type:** principle
- **Tags:** learnings, tags, searchability, abstract-labels, chat-correction, knowledge-capture
- **Confidence:** high
- **Status:** active
- **Date:** 2026-03-08
- **Related:** L-00208 (related_to), L-00209 (related_to)

Learnings tags must be concrete and searchable — the actual flags, filenames, commands, and system components involved — not abstract classifiers describing the type of mistake. Tags like `flag-conflation` and `static-count-in-config` describe the error category; they don't name what broke. A future reader searching for `AUTO_APPROVE`, `project.yaml`, or `max_features` must be able to find the relevant entry. The test: could someone find this learning by searching for the thing that actually broke? If not, the tags are wrong. Brian's correction was immediate and also meta: "they are not semantically relevant to future builds. Should talk about the actual issue in a semantic search friendly way." He then extended it: the fix should propagate to both memory and the code/repo so no future chat has to re-derive it.

---

## Accumulation (DEPRECATED — see L-00194)

> **Process change (2026-03-04):** New methodology observations go directly into graph-schema M-entries above. This section is a backlog of raw captures that predate the change. Clear by converting to schema entries or discarding. Do NOT add new raw entries here.

- (2026-03-03) Brian enforces architectural consistency: when a design principle is established for one module (agent-based over regex), he expects it applied uniformly to analogous modules and challenges inconsistency directly ("why are you sure this should not be agent detection as well").
- (2026-03-03) Brian catches scope inflation with "what do I actually need this for" — adding Rust/Go language support without asking what ecosystems Brian actually targets was immediately flagged. YAGNI enforced empirically.
- (2026-03-03) Brian's correction style: short, precise, expects single-correction adherence. Having to repeat "you have agent(S) do it per prompt-engineering-guide.md" twice signals a process gap, not ambiguity in the instruction.
- (2026-03-03) "prompt better" is a directive meaning "you now understand the architecture, rewrite the prompt to match" — not an invitation for further discussion or clarification.

- (2026-03-03) Brian treats agent calls as expensive operations requiring justification. When Phase 2 used two agent calls, his first reaction was questioning speed, not correctness. Pipeline optimization means minimizing agent invocations, not just getting correct output.
- (2026-03-03) Brian prefers fixing performance problems when they surface rather than noting them as tech debt. "I want to resolve as much of the slow issues as we can" — immediate refactor over backlog entry.
- (2026-03-03) Brian trusts execution momentum when patterns are established. Six phases dispatched with minimal discussion between — "yes", "continue", "go for next response". Once the prompt template and verification pattern proved reliable in Phases 0-2, Brian stopped reviewing prompt details and focused on merge/continue.
- (2026-03-03) Brian values prompt pre-computation: writing Phase 4b prompt before 4a results returned, Phase 5 before 4b. When asked "can you write the prompt for 4b without 4a results?" he expected a yes — the output schema being deterministic was sufficient.
- (2026-03-03) Brian context-switches cleanly between deep technical work and communication needs. Mid-pipeline, he asked for a meeting explanation of auto-sdd — expected tight, comprehensive prose covering the full system, not just the current work item.
- (2026-03-04) Brian's first instinct on a stashed 377-line prompt was "is it the best solve?" — not "let's execute." The prior session built the prompt without that gate. Brian's "if not, what is? how can we be sure?" sequence forced root cause analysis that found a 10-line fix in an existing module. The prompt was an elaborate workaround for a detection ordering bug. Methodology: always ask whether the solution layer matches the problem layer before committing to execution.
- (2026-03-04) Brian treats tool call efficiency as a hard constraint, not a nice-to-have. Redundant file reads have real cost: Extra Usage billing, response truncation, wasted wall time. "I don't care if you have to stash learnings/results mid run, just stop fucking up" — the scratch file pattern is non-negotiable.
- (2026-03-04) Brian requires explicit communication when deviating from instructions. Silent overrides — even with sound reasoning — are treated as failures. "If you have to do something different than as asked, fine, BUT: I have to know you did and why — ALWAYS." The communication contract is: acknowledge the instruction, state the deviation, explain why.
- (2026-03-04) Brian values surgical targeting over comprehensive sweeps. "Challenge yourself to isolate and target-fix, rather than the longer process of running it all and timing first." When the problem space is known, skip the full diagnostic and go straight to the likely cause.
- (2026-03-04) Brian uses a "commit then pressure test" methodology for design: write the plan to a file first (creates accountability), then test it against goals, then test for simplicity. The commit step is deliberate — it prevents retroactive revision from contaminating the pressure test. "First commit the full-fidelity plan... Then pressure test the logic against the goal... Then pressure test to check if these planned implementations' outputs could be achieved via simpler, more extensible, or more efficient means."
- (2026-03-04) Brian resolves the YAGNI vs foundation tension by checking data model clarity. If the schema and API surface are known across a concrete multi-round plan, build the abstraction now. If speculative, defer. Feature flags are his preferred middle path: include infrastructure, gate activation. "I don't want to defer for the counter-argument reasons" + "instead of deferring, perhaps we just use a feature flag until needed."
- (2026-03-04) Brian instinctively connects disparate subsystems into unified data models. When shown the eval sidecar gap, he immediately asked about auto-QA as an input source and split Application into intra-campaign (real-time) vs cross-campaign (offline). He sees signal sources as a graph, not silos. "What patterns lead to build failures or runtime errors? This could be one system or native to auto-QA, but taking inputs from the inter-build model/data."
- (2026-03-04) Brian is attentive to qualitative signals, not just quantitative outcomes. When presented with a detection/analysis system, he asked "are we capturing qualitative choices in code, like best practices and convention uses?" — pushing beyond pass/fail metrics to the decisions that cause downstream failures.
- (2026-03-04) Brian maintains meta-awareness about the quality of the learning system itself. When a learning referenced "Round 2" without grounding it to a specific project/plan, he flagged it as a systemic problem: "this is a common failure in learnings I want to fix" — and asked for a meta-learning to enforce self-contained entries. He sees the learning corpus as a product with quality standards, not a dumping ground.

- (2026-03-06) M-00091: The closed-loop pattern is domain-agnostic. Brian immediately saw that the same architecture (spec → build → verify → diagnose → fix → learn) maps to quantitative trading: hypothesis = spec, implementation = strategy code, backtest = verify, failure analysis = diagnose, parameter refinement = fix, accumulated strategy knowledge = learn. The verification step requires verifiable outputs — Playwright for web apps, statistical significance gates for trading strategies. Any domain with mechanically checkable outcomes is a candidate. Brian's framing: "It's a sector-specific intelligence scaling problem."
- (2026-03-06) M-00092: Brian thinks in compounding terms, not linear timelines. When pressed on "what are the implications in two years," his correction was "it's in 6 months." Each cycle improves the next cycle, and improvement cycles run on free local compute (Mac Studio). The system rebuilds itself. His mental model: the system that exists in 6 months bears no resemblance to today's because it has recursively improved through hundreds of iterations. Linear projections based on current capability miss the compounding.
- (2026-03-06) M-00093: Brian's instinct when reaching a milestone is to share it with people who matter personally — not strategically. First text after auto-QA success was to Adrian (his boss, the upstream author). First message the next morning was to his father. The sharing impulse is relational, not promotional. The strategic questions (IP, commercialization, publication) came after, and felt secondary to "the people I care about should know."

- (2026-03-07) M-00094: Handoff files work but require established location conventions. When Brian wrote `session-handoff-2026-03-06.md` to `Brians-Notes/` instead of `.handoff.md` at repo root, the onboarding check missed it on first pass. The protocol specifies repo root; the actual file was in a subdirectory. Onboarding check should search broadly (find) not just check the canonical path. Convention drift between sessions is a real failure mode.
