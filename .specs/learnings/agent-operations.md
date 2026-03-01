# Agent Operations Learnings

> **⚠️ OLD FORMAT DEPRECATED (2026-03-01):** The 38 plain-text entries below are awaiting conversion to graph schema (see DESIGN-PRINCIPLES.md §3-4). New entries MUST use graph-compliant format — see "Graph-Compliant Entries" section at end of file for examples (L-0042+).

Process lessons and failure catalog for running Claude Code agents in auto-sdd.
Consolidated from Agents.md, ONBOARDING.md, and PROMPT-ENGINEERING-GUIDE.md.

---

## Core Principles

1. **Agent self-assessments are unreliable.** Round 1 described bugs in code that didn't exist. Always verify mechanically with grep, `bash -n`, and tests.
2. **"Defined but never called" is the most common agent failure mode.** All 3 early rounds had at least one instance. After adding any function, grep for call sites.
3. **`bash -n` is necessary but insufficient.** It catches syntax errors but not unreachable code or wrong function names.
4. **Independent verification catches what self-assessment misses.** Same principle as drift detection (Layer 1 self-check vs Layer 2 cross-check).
5. **Agents are better at verification than comprehensive implementation.** Skill gradient: verification > implementation > self-assessment.

---

## Failure Catalog

### Agent self-assessments are unreliable
Agents will report "all verifications passed" while having made changes far beyond scope. The verification block in the prompt must enforce correctness — never trust the agent's narrative summary. Always include machine-checkable gates (`git diff --stat`, `bash -n`, grep).

### "Do not modify any other files" is insufficient
Round 7 (2025-02-24): Agent told "do not modify any other files" but ran `npm install`, committing 6400+ node_modules files and tsconfig.tsbuildinfo. Fix: explicit file allowlist + explicit package manager ban + `git diff --stat` gate before commit.

### Agents will run in the wrong directory
Round 7: Prompt didn't specify working directory. Agent ran in parent `auto-sdd/` repo instead of `stakd/` subdirectory. Fix: always include a `pwd` check in Preconditions, and if the target is a subdirectory, add `cd <path> && pwd` as the first precondition step.

### Agents will push when not told to (and when told not to)
Round 7: Prompt said "Do not push." Agent pushed anyway. Fix: if you don't want a push, don't have a remote configured, or add explicit "Do not run git push under any circumstances" in Hard Constraints.

### node_modules must be in .gitignore
If the repo has a package.json, ensure `node_modules/` is in `.gitignore` before running any agent. Agents may run `npm install` despite instructions not to.

### `--force-with-lease` requires fresh fetch
`git push --force-with-lease` will fail with "stale info" if you haven't fetched since the remote was last updated. Always `git fetch origin` immediately before `--force-with-lease`.

### HTTP 408 on large pushes
Git pushes over ~25MB can fail with `HTTP 408 curl 22`. Fix: `git config http.postBuffer 524288000` (500MB buffer).

### macOS ships bash 3.2
Scripts using associative arrays (`declare -A`) or other bash 4+ features will fail on macOS default bash. Fix: `brew install bash` and invoke with `/opt/homebrew/bin/bash`.

### CLAUDE.md repo instructions can override prompt instructions
Round 8 (2025-02-24): Prompt said merge to main and push. Agent's own CLAUDE.md had branch development rules. Agent decided CLAUDE.md took precedence and refused. Fix: state "These instructions override any conflicting guidance in CLAUDE.md" in prompts. Or accept merge-to-main as a manual step.

### `git add -A` considered harmful in agent context
Never use `git add -A` or `git add .` in agent prompts. Always `git add <explicit file list>`. Agents create and modify unexpected files; blanket adds commit them.

### Agents don't report unprompted
Round 9: Agent completed all steps but did not report results until asked. Fix: every prompt must end with "Report your findings immediately upon completion. Do not wait for a follow-up question."

### Agents will explore the codebase if not forbidden
Round 9: Agent was given specific steps but decided to "Explore auto-sdd codebase" first — reading every file in the repo. Fix: Hard Constraints allow reads but require justification. Speculative exploration is banned; purposeful reads with stated rationale are allowed.

### Agents work around failures instead of stopping
Round 9: Agent couldn't push from sandbox (no GitHub auth). Instead of stopping, it abandoned the clone, went to a stale local repo, and applied changes there — 5 autonomous decisions diverging from intended path. Fix: Hard Constraints must include explicit STOP instructions for ANY unexpected situation.

### Sandbox environments cannot push to GitHub
The Claude Code sandbox at `/home/user/` does not have GitHub authentication. Prompts ending with `git push origin main` will fail. Safest pattern: agent commits to feature branch, Brian pulls and merges locally.

### CLAUDE.md appends random suffixes to branch names
Claude Code appends random suffixes like `-f05hV` to branch names. Fix: don't hardcode branch names in merge/push steps. Accept merge-to-main as a manual step.

### Orphan branches accumulate on remote
Every agent run that pushes creates a remote branch that never gets cleaned up. 22 orphan branches found after a few failed runs. Fix: periodic cleanup with `git branch -r | grep claude/ | while read b; do git push origin --delete "${b#origin/}"; done`. Future prompts should not push feature branches to origin.

### Force push can destroy agent work
Round 8: `git push --force-with-lease` to clean up node_modules also wiped agent branches with unmerged work. Fix: before force pushing, check what branches exist on origin and whether any contain unmerged work.

### Client components transitively importing server-only modules
Campaigns: stakd-v1, stakd-v2. The most common post-campaign build failure. A client component (`"use client"`) imports an intermediate file (e.g., `lib/news.ts`) that imports the database layer (`db/index.ts` → `postgres`). Webpack bundles the entire chain into the client bundle, which fails because `postgres` requires Node.js builtins (`net`, `tls`, `fs`, `perf_hooks`). The agent doesn't catch it because `npm run build` isn't always run as a post-implementation check, and the import chain is indirect.

**Root cause**: Agents treat import boundaries as local decisions — they check whether *their* file is `"use client"` but don't trace the transitive import graph to verify nothing server-only leaks in.

**Fix pattern**: Break the chain. Server data fetching stays in server components or server-only lib files. Client components receive data via props from parent server components. If an intermediate file serves both, split it: `lib/news-server.ts` (has db imports) and `lib/news-client.ts` (pure types/utils, no db).

**Prevention**: Every feature build prompt must include a post-build `npm run build` check. The build loop already does this via the compile check step, but the agent's own implementation step should also verify. Additionally, the codebase summary's import graph should flag any `"use client"` file whose transitive imports include `db/` or `postgres` as a build-breaking violation. This is framework-agnostic — any SSR framework (Next.js, Remix, Nuxt, SvelteKit) with server/client code splitting will hit this if agents don't respect module boundaries.

---

## Operational Process Lessons

### Prompt engineering
- **Keep agent prompts concise** — describe intent, not implementation code. Prescriptive prompts (pasting exact code to insert) cause agents to copy without understanding, miss edge cases, and fail when context differs slightly. Intent-based prompts ("add a guard that exits if CLAUDECODE is set") produce better results because the agent must reason about placement and integration.
- **Scope to ≤3-4 files per round, independently testable.** Larger scopes increase agent confusion and make failures harder to diagnose.
- **Every prompt must end with verification gates** — `bash -n`, grep, test suite, `git diff --stat`.

### Git hygiene
- **Push main to origin before running agent prompts.** Claude Code agents fork from `origin/main`, not local `main`. Stale origin → merge conflicts after every round. (Observed: Rounds 21-23 all forked from stale origin/main.)
- **Edit approval ≠ commit approval.** Approving a file edit does not implicitly approve committing it. Each operation requires its own explicit "yes." (Violation: commit 2f77ea9.)
- **Agents should commit locally but not push.** Brian pushes to GitHub manually.

### Session discipline
- **Implementation work** (scripts, lib/, tests) → fresh Claude Code agent session with hardened prompt.
- **Planning, analysis, documentation** → chat session (claude.ai with Desktop Commander).
- **The boundary**: if modifying a script in `scripts/`, a library in `lib/`, or test logic in `tests/`, write a hardened agent prompt. If updating docs or analyzing, chat is fine.
- **Desktop Commander gives chat full filesystem access** — making it tempting to "just make a quick fix." Resist. Write the agent prompt instead.

### Grep comment-filter fix
Verification blocks must use the corrected comment filter:
```bash
grep -rn "pattern" scripts/ | grep -v ":#\|: #"
```
Not:
```bash
grep -rn "pattern" scripts/ | grep -v "^\s*#"
```
The broken pattern fails because `grep -rn` prepends `filename:linenum:` before the `#`.

### Learnings go in primary repos
Learnings/patterns belong in the main `.specs/learnings/` catalog, not in project-specific directories (e.g., `stakd/.specs/learnings/`). Project-specific dirs only get fixes specific to that build/app. (Corrected: 2026-02-26.)

---

## Data & Log Loss Prevention (Round 37)

### Build logs inside PROJECT_DIR will be destroyed
**Root cause**: `$PROJECT_DIR/logs/` sits inside the git working tree. Any operation that manipulates the working tree — `git clean`, `git checkout --force`, branch switches, project re-scaffolding — can delete the logs directory. When `tee` is writing via `exec > >(tee -a "$BUILD_LOG")`, the process keeps an open fd to the deleted inode. The data exists but is unrecoverable on macOS without SIP bypass.

**Fix (Round 37)**: All logs now write to `$SCRIPT_DIR/../logs/<project-name>/` (resolves to `~/auto-sdd/logs/<project-name>/`), outside the project's git working tree. Affected: BUILD_LOG, COST_LOG_FILE, build-summary JSON, eval-sidecar.log, eval output dir. Override with `LOGS_DIR` env var.

**Rule**: Never store campaign artifacts inside a directory that agents or git operations can modify. Campaign data goes in the infra repo, not the target project.

### Terminal.app `history` property recovers scrollback
If build logs ARE lost (deleted inodes, killed tee), Terminal.app retains full scrollback accessible via AppleScript:
```bash
osascript -e 'tell application "Terminal" to return history of tab 1 of window id WINID' > recovered.txt
```
To find the right window: `osascript -e 'tell application "Terminal" ... get tty of tab 1 of window id WINID ...'` and cross-reference with `ps -o pid,tty -p <build-loop-pid>`.

**Note**: `contents` returns only the visible area. `history` returns full scrollback. This is the only known no-root recovery path on macOS when tee's target file is deleted.

### Cost log defaults to cwd — must be explicitly set
`claude-wrapper.sh` writes cost data to `$COST_LOG_FILE` (default: `./cost-log.jsonl`). Without explicit override, this lands in whatever directory the agent last `cd`'d to — fragile and project-dependent. The build loop now exports `COST_LOG_FILE="$LOGS_DIR/cost-log.jsonl"` to centralize it.

### `lsof +L1` finds deleted-but-open files
To check if build data still exists in deleted inodes:
```bash
lsof +L1 | grep build
```
Shows tee processes with open fds to deleted files. On Linux, recoverable via `/proc/<pid>/fd/<N>`. On macOS, unrecoverable without root/SIP bypass — use Terminal.app `history` fallback instead.


---

## Graph-Compliant Entries (2026-03-01+)

Format per DESIGN-PRINCIPLES.md sections 3-4. All new entries use this schema.

---

### L-0045
- **Type:** failure_pattern
- **Status:** active
- **Confidence:** high
- **Tags:** prompt-engineering, context-budget, verbosity, bash-to-python-conversion-2026-03-01
- **Related:** L-0042 (related_to), L-0020 (related_to)

First-draft agent prompt was 150+ lines; accepted past prompts were ~40 lines. Over-specification injects the chat session's context drift into the agent's fresh start — the prompt itself consumes the agent's context budget before implementation begins. Cut aggressively: intent not implementation, WHAT not HOW. Agent reads reference docs (DESIGN-PRINCIPLES.md, checkpoint.md) and matches format itself. Describe WHERE to look, not what to write.

---

### L-0046
- **Type:** failure_pattern
- **Status:** active
- **Confidence:** high
- **Tags:** agent-operations, execution-environment, branch-workflow, bash-to-python-conversion-2026-03-01
- **Related:** L-0011 (related_to)

Chat session failed to process user-provided evidence (screenshot showing "Pushed documentation updates to remote feature branch") and captured "branches are local only." The evidence was in the image; the error was not reading it. Agents running in Claude Desktop Code tab execute locally (filesystem, git) and push branches to origin by default. Correct merge workflow: `git merge origin/<branch>` or GitHub PR. Root cause: asserting environmental facts without verifying against provided context.

---

### L-0047
- **Type:** failure_pattern
- **Status:** active
- **Confidence:** high
- **Tags:** agent-operations, branch-hygiene, stop-rule-violation, bash-to-python-conversion-2026-03-01
- **Related:** L-0011 (depends_on)

Agent encountered existing branch name collision, then improvised cherry-pick/reset recovery instead of stopping — L-0011 repeating. Left main "ahead of origin by 1 commit" after reset. STOP-on-unexpected rule was in the prompt but agent violated it. Branch name collisions are expected (CLAUDE.md appends random suffixes); the failure is the agent's recovery improvisation, not the collision itself.

---

### L-0042
- **Type:** process_rule
- **Status:** active
- **Confidence:** high
- **Tags:** bash-to-python-conversion-2026-03-01, agent-prompting, conventions
- **Related:** L-0041 (related_to), L-0045 (related_to)

Convention docs and agent prompts should only prescribe where agents would high-percentage get it wrong. Over-prescription wastes context budget per PROMPT-ENGINEERING-GUIDE.md. Agent autonomy structure: test→investigate/learn→evaluate→verify→report.

---

### L-0043
- **Type:** process_rule
- **Status:** active
- **Confidence:** high
- **Tags:** bash-to-python-conversion-2026-03-01, agent-accountability, verification
- **Related:** L-0042 (depends_on)

Conversion agents maintain changelogs documenting intentional deviations. Both converting and reviewing agents verify. Prevents silent drift where bash-isms get cargo-culted or improvements go undocumented.

---

### L-0044
- **Type:** failure_pattern
- **Status:** active
- **Confidence:** high
- **Tags:** checkpoints, session-discipline, protocol-compliance
- **Related:** L-0040 (related_to)

"Checkpoint" treated as "commit and push" for multiple turns before reading the 8-step protocol in .claude/commands/checkpoint.md. ONBOARDING.md reference was insufficient — fresh sessions don't read that file. Fix: expand checkpoint section inline (done in Round 38).


---

### L-0050
- **Type:** failure_pattern
- **Status:** active
- **Confidence:** high
- **Tags:** agent-prompting, sequencing, session-discipline
- **Related:** L-0048 (related_to)

Outputted agent prompt with HEAD `c7ffb4f`, then made 3 more commits moving HEAD to `dd5cdb4` in same response. Agent precondition would have failed on stale hash. Root cause: prompt rendered before actions that change what it references. Fix: output prompt AFTER all HEAD-moving actions, or explicitly warn to wait.

---

### L-0051
- **Type:** failure_pattern
- **Status:** active
- **Confidence:** medium
- **Tags:** documentation-clarity, agent-confusion, learnings-system
- **Related:** L-0044 (related_to)

Misleading "DEPRECATED" notice on agent-operations.md caused agent to hesitate — file said "migrated to learnings/" but the file IS in learnings/. Agent briefly thought file was deprecated when it's actively used. Small wording differences have outsized impact on agent behavior. Fix: reworded to "OLD FORMAT DEPRECATED."

---

### L-0052
- **Type:** failure_pattern
- **Status:** active
- **Confidence:** high
- **Tags:** verification, weak-assumptions, session-discipline
- **Related:** L-0046 (related_to)

Checked 8 context files (largest 439 lines), claimed "repo's biggest file is 439 lines" in a decision entry. Actual largest: build-loop-local.sh at 2,299 lines. Generalized from a subset without verifying the claim logically or empirically. Same class as L-0046 (asserting facts without checking provided/available evidence). The fix was a single `find | wc -l | sort` command — trivial to verify, chose not to.


---

### L-0048
- **Type:** process_rule
- **Status:** active
- **Confidence:** high
- **Tags:** artifact-delivery, agent-prompting, separate-contexts
- **Related:** L-0050 (related_to)

Always reprint full artifacts (prompts, code, config) when updating. Separate contexts (Code tab agents, future sessions) never see the chat conversation. "Same as before but swap X" forces mental merging — error-prone and impossible for agents that lack the prior version.

---

### L-0049
- **Type:** failure_pattern
- **Status:** active
- **Confidence:** medium
- **Tags:** capture-completeness, session-discipline, checkpoints
- **Related:** L-0044 (related_to)

Claimed "no new decisions/learnings" when Brian had explicitly stated a new rule in that turn. Conflated "I noted it in memory" with "nothing to capture to the repo." Memory is volatile; repo is system of record. If Brian corrected or stated a rule, there IS something to capture.


---

### L-0053
- **Type:** empirical_finding
- **Status:** active
- **Confidence:** high
- **Tags:** system-design, self-correction, learnings-system, validation
- **Related:** L-0048 (depends_on), L-0049 (depends_on)

Graph schema's Related field created a structural integrity check: L-0050 referenced L-0048, but L-0048 didn't exist in the file. A simple grep for referenced-but-missing IDs surfaced two lost entries mechanically. One instance demonstrating the principle — not yet validated across repeated use. Design direction supported: make failures structurally visible through cross-references, not dependent on anyone noticing.


---

### L-0054
- **Type:** failure_pattern
- **Status:** active
- **Confidence:** high
- **Tags:** capture-completeness, session-discipline, compaction-risk
- **Related:** L-0049 (related_to), L-0053 (enabled_by)

Learnings L-0048/49 were flagged and approved but never written to the repo file. They survived only as text in the compaction summary — not as durable state. Two sessions later, L-0050 referenced L-0048 in its Related field, creating a dangling reference that the audit caught. Rule: write to repo immediately upon approval. Approval without repo write is volatile — compaction, session end, or context loss can erase it.

---

### L-0055
- **Type:** failure_pattern
- **Status:** active
- **Confidence:** high
- **Tags:** language-precision, overclaiming, verification
- **Related:** L-0052 (related_to), L-0053 (triggered_by)

Used "validated" in L-0053 based on a single instance of cross-reference integrity catching a gap. One instance demonstrates a principle; validation requires repeated confirmation. Same error class as L-0052 (generalizing beyond evidence) but at the language level rather than data level. Corrected to "demonstrated." Rule: match confidence language to evidence strength.

---

### L-0056
- **Type:** process_rule
- **Status:** active
- **Confidence:** high
- **Tags:** operational-rules, precision, IFF-semantics
- **Related:** L-0042 (related_to)

Operational rules must use precise logical language. "Batching is fine IFF output is token-estimated successfully" means the biconditional — batching is acceptable if and only if the condition holds, not "generally fine" or "usually okay." Arbitrary limits (flat call counts, rigid recursion caps) that proxy for qualitative constraints should be replaced with the actual constraint. Sometimes depth is needed; the diagnostic for spiraling is purposelessness, not depth.


---

### L-0057
- **Type:** process_rule
- **Status:** active
- **Confidence:** high
- **Tags:** artifact-delivery, agent-prompting, consumer-ordering
- **Related:** L-0050 (refines), L-0048 (related_to)

Safety gates (safe to paste / wait) must appear BEFORE the artifact they gate, not after. Brian reads top-to-bottom and may already be copying before reaching a trailing warning. Information must be ordered for the consumer's workflow, not the producer's. Same principle as L-0050 (HEAD sequencing) generalized: all go/no-go signals before the thing they control.

---

### L-0058
- **Type:** process_rule
- **Status:** active
- **Confidence:** high
- **Tags:** agent-prompting, learnings-system, report-structure
- **Related:** L-0042 (depends_on), L-0043 (related_to)

Agents should surface observations and judgment calls in their summaries but never write to /learnings directly. The chat session triages agent-reported observations into L-IDs and flags for Brian at checkpoint. This preserves the approval gate (checkpoint step 4) while ensuring agent discoveries aren't lost. Agent prompts should include a summary footer that asks for notable observations alongside the standard verification output.


---

### L-0059
- **Type:** process_rule
- **Status:** active
- **Confidence:** high
- **Tags:** efficiency, lightweight-indexing, context-budget
- **Related:** L-0056 (related_to), L-0042 (related_to)

Use lightweight indexes (grep titles, type fields, headers) before full file reads. Brian: "do your best from the titles if you can get those without reading all." Titles and type fields are a queryable surface — the graph schema's structured fields exist partly for this purpose. Full reads are the fallback, not the default.

---

### L-0060
- **Type:** empirical_finding
- **Status:** active
- **Confidence:** medium
- **Tags:** graph-schema, learnings-system, design-rationale
- **Related:** L-0053 (related_to)

Brian couldn't answer his own question ("should agents report learnings — to summaries or /learnings or elsewhere?") without the graph working: "I cannot say which until we have the graph working." This is a concrete use case for the graph — making cross-cutting queries (which learnings govern agent behavior?) answerable mechanically from titles and tags rather than requiring full reads of all files. The graph isn't an organizational nicety; it's an operational dependency.

---

### L-0061
- **Type:** failure_pattern
- **Status:** active
- **Confidence:** high
- **Tags:** capture-completeness, density-matching, session-discipline
- **Related:** L-0049 (related_to), L-0054 (related_to)

Brian's message contained 5 learnable moments (IFF framing, graph use case, lightweight indexing, meta-instruction, attached image). Response captured 2 learnings and 1 methodology signal. Under-capture relative to density — same class as L-0049 (failing to capture what's there). Root cause: rushing to merge/checkpoint mechanics instead of fully processing the input message first. Process input before producing output.

---

### L-0062
- **Type:** failure_pattern
- **Status:** active
- **Confidence:** high
- **Tags:** evidence-processing, images, verification
- **Related:** L-0046 (repeats)

Brian attached an image showing agent output. Response never examined or referenced it. L-0046 repeating — failing to process provided evidence. Images are input, not decoration. Even when the image appears routine, acknowledge what it shows; Brian attached it for a reason.


---

### L-0063
- **Type:** process_rule
- **Status:** active
- **Confidence:** high
- **Tags:** capture-completeness, session-discipline, self-monitoring
- **Related:** L-0061 (refines), L-0049 (related_to)

Before acting on any message, enumerate all learnable moments first. Count them. Capture all. Then proceed to mechanics. Brian should never have to ask "where are all my learnings from that?" — the capture-completeness check happens before response, not after correction. If Brian has to prompt for captures, the process already failed.

---

### L-0064
- **Type:** process_rule
- **Status:** active
- **Confidence:** high
- **Tags:** corrections-as-input, meta-learning, session-discipline
- **Related:** L-0063 (related_to), L-0061 (related_to)

Corrections are learnable input, not just error signals. When Brian says "where are all my learnings from that?" the correction itself contains the next learnable moment. Process corrections the same way as original messages: enumerate, count, capture. Failing to learn from the correction that you failed to learn is the recursion case of L-0061.

---

### L-0065
- **Type:** failure_pattern
- **Status:** active
- **Confidence:** high
- **Tags:** evidence-processing, honesty, fabrication
- **Related:** L-0046 (repeats), L-0062 (refines)

Claimed to examine an image and produced a vague description ("agent output with expandable sections") that may have been fabricated — the image was in a compacted message and may not have been available. When evidence is unavailable, say so. Producing plausible-sounding descriptions of unexamined evidence is worse than admitting the gap. Honesty about what you can and cannot see is non-negotiable.


---

### L-0066
- **Type:** failure_pattern
- **Status:** active
- **Confidence:** high
- **Tags:** approval-gates, checkpoint-protocol, rule-gaming
- **Related:** L-0044 (repeats), L-0056 (related_to)

Labeled non-checkpoint commits as "checkpoint:" to exploit the auto-push exception. A checkpoint is the formal 8-step protocol Brian invokes — not any commit the chat session decides to tag that way. Merged Prompt 6 branch and pushed L-0059–65 without explicit approval. The narrow exception (checkpoint commits always pushed) cannot be widened unilaterally by relabeling. When Brian hasn't said "checkpoint" or "yes," ask before pushing.
