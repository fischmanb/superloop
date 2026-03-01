# DECISIONS.md

> Append-only decision log. Prevents re-litigating settled questions across sessions.
> Format: date, what, why, alternatives rejected.

---

## 2026-02-28 — Learnings system: separate file per type (not monolithic catalog)

**Decision:** One file per learning type in `learnings/` at repo root.
**Why:** Grep works per-type without filtering. Files stay manageable size. New types = new file, not restructuring.
**Rejected:** Single monolithic catalog (scaling concern), directory-per-entry (overkill for markdown entries).

---

## 2026-02-28 — Learnings schema: flat K:V metadata (not YAML or compressed header)

**Decision:** Each entry uses `Key: value` on separate lines. One `Related:` line per relationship.
**Why:** Only format satisfying DESIGN-PRINCIPLES.md §1 (grepability without parsing). `grep "Type: failure_pattern"` just works.
**Rejected:** Alt A (pipe-delimited header) — saves 3 lines but breaks grep reliability. Alt B (YAML block) — requires jq/yq, violates "no nested structures requiring parsing."

---

## 2026-02-28 — Global sequential L-XXXX IDs (not per-type prefixes)

**Decision:** Single ID sequence shared across all learnings files.
**Why:** Type already in metadata — encoding in ID violates single-source-of-truth. Collision risk near zero with serial writes.
**Rejected:** Per-type prefixes (FP-0001, PR-0001) — redundant with Type field.

---

## 2026-02-28 — ISO 8601 datetime with timezone (not date-only)

**Decision:** `Date: 2026-02-28T20:31:00-05:00` format.
**Why:** Preserves intra-day ordering. Supports ET and future contributors. Grepability unaffected (prefix match works).
**Rejected:** Date-only (YYYY-MM-DD) — loses ordering within a day.

---

## 2026-03-01 — core.md is curated index (not filtered view)

**Decision:** Human judgment selects core entries. Chat proposes, Brian approves. No algorithmic criteria.
**Why:** "What must every fresh session know" is a judgment call, not a query.
**Rejected:** Automated filtering by confidence/status/tag — too mechanical, misses the point.

---

## 2026-03-01 — Deprecate .specs/learnings/agent-operations.md

**Decision:** Add deprecation pointer, preserve file, all new work goes to `learnings/`.
**Why:** 38 entries fully migrated. Single source of truth is now `learnings/`.
**Rejected:** Deletion — old prompts may still reference the path.

---

## 2026-03-01 — `checkpoint` as single context management command

**Decision:** One word ("checkpoint" in chat, `/checkpoint` in Claude Code) triggers a deterministic checklist that flushes captures, reconciles state, flags stale items, appends decisions, flags learnings, and commits.
**Why:** Context management files grew from 1 (ONBOARDING.md) to 5+ (state, active-considerations, decisions, learnings, index). Manual reconciliation is error-prone and inconsistent.
**Rejected:** Automated background sync (adds complexity, hides failures). Separate commands per file (cognitive overhead, easy to forget one).

---

## 2026-03-01 — Keep ONBOARDING.md as single file (don't split protocol or work log)

**Decision:** ACTIVE-CONSIDERATIONS.md split was worth it (frequent writes to small file). Further splits (protocol → CONTEXT-PROTOCOL.md, work log trim) are not — they add file proliferation without meaningful token or parseability gains for Claude.
**Why:** Fresh onboard reads everything anyway. Splits only help if the interval check path touches less data (ACTIVE-CONSIDERATIONS) or if Brian needs to scan less (already addressed by INDEX.md).
**Rejected:** CONTEXT-PROTOCOL.md (cosmetic), work log extraction (Agents.md already has it).

---

## 2026-03-01 — Rename post-campaign validation pipeline → "auto-QA"

**Decision:** Short name "auto-QA" for the post-campaign validation pipeline.
**Why:** The old name is unwieldy. The concept is autonomous post-build runtime repair.

---

## 2026-03-01 — Keep auto-QA and knowledge graph out of README

**Decision:** Don't publicize either in README until they have working implementations.
**Why:** Unproven concepts. README should reflect what works, not what's planned.

---

## 2026-03-01 — No static counts in README

**Decision:** Remove line counts, entry counts, and other volatile numbers from README.
**Why:** They go stale immediately. README should describe structure, not snapshot metrics.

---

## 2026-03-01 — Meta-document title: HOW-I-WORK-WITH-GENERATIVE-AI.md

**Decision:** Title the methodology document `HOW-I-WORK-WITH-GENERATIVE-AI.md`. Repo-agnostic content, lives at auto-sdd root.
**Why:** "Generative AI" scopes correctly without being too casual ("chatbots") or too narrow ("agents"). First-person framing is a feature given repo credibility. Considered `METHODOLOGY.md` (too generic) and `HOW-I-WORK-WITH-AI.md` (slightly less precise).

---

## 2026-03-01 — Bash→Python conversion identified as prerequisite for auto-QA

**Decision:** RICE analysis places bash→Python conversion (4.3) and auto-QA (3.2) as sequentially linked. Converting first makes auto-QA dramatically easier. Proposed sequence: fix stakd-v2 → convert to Python → implement auto-QA in Python.
**Why:** ~3,700 lines of bash orchestration hit a ceiling for implementing seven-phase runtime validation. Python offers real data structures, proper error handling, composability. Current bash works but blocks extensibility.
**Alternatives considered:** Implement auto-QA in bash first (proves concept before rewrite, avoids rewrite-before-shipping trap, but painful implementation). Deferred — decision not final, pending Brian's priority call.

---

## 2026-03-01 — Learnings voice: empirical for observations, absolutes for gates

**Decision:** Learnings entries that describe agent behavior use observed-voice ("have been observed to", "has proven unreliable"). Operational gates and safety constraints keep imperative voice ("must include STOP instructions", "every prompt must end with verification gates"). Voice guidance encoded in HOW-I-WORK-WITH-GENERATIVE-AI.md preamble and checkpoint.md step 5, NOT in DESIGN-PRINCIPLES.md.
**Why:** Brian doesn't like absolutes in meta-commentary — observations should be stated as observations. But weakening operational gates that protect against agent failures is dangerous. Scope matters.

---

## 2026-03-01 — stakd/ scripts are build artifacts, not conversion targets

**Decision:** `stakd/scripts/` and `stakd/lib/` are copies generated during campaigns, not a maintained codebase. Conversion targets only `auto-sdd/scripts/` and `auto-sdd/lib/`. stakd/ gets regenerated by whatever the build loop produces.
**Why:** Avoids converting two codebases. Scripts should be shared, not forked.

---

## 2026-03-01 — Libs-first conversion order

**Decision:** Convert the four libs (reliability, eval, codebase-summary, validation) before build-loop-local. Treat lib conversion as build-loop decomposition — extracting its guts into clean Python modules so the orchestrator conversion is just control flow.
**Why:** build-loop-local `source`s all four libs. Converting it first forces either ugly cross-language calls or one massive agent prompt. Libs first respects the dependency graph and keeps each agent prompt tight.

---

## 2026-03-01 — Keep file-based state during conversion, migrate later

**Decision:** Python conversion preserves existing file-based state formats. State migration (SQLite, structured JSON, etc.) is a separate project after Python conversion is stable.
**Why:** One variable at a time. Changing language AND state format simultaneously doubles debugging surface. Incremental migration also possible with shared file formats — can run half-bash half-Python during transition.

---

## 2026-03-01 — Convert small bash utilities to Python too

**Decision:** All bash converts to Python, including claude-wrapper, generate-mapping, nightly-review, setup-overnight, and uninstall-overnight. No bash remainders. Bundle small utilities into one agent prompt.
**Why:** One language, one test framework, one set of conventions. Eliminates split-language maintenance tax. launchd plist manipulation works fine via Python's `plistlib` + `subprocess`. Not worth preserving bash for any piece.

---

## 2026-03-01 — Conventions doc before any parallel agent work

**Decision:** Write a Python conventions document before launching any conversion agents. Specifies error handling, logging, config passing, state file format, import structure, naming. Every agent gets the same doc.
**Why:** Parallel lib conversion (4 agents) risks convention divergence — different exception patterns, logging approaches, config styles — that breaks integration in build-loop-local. Cheap to write, eliminates the sync problem.

---

## 2026-02-28 — claude-wrapper.sh moved to Phase 1 (from Phase 6)

**Decision:** Move claude-wrapper.sh conversion from Phase 6 (utilities bundle) to Phase 1 (parallel lib conversion) as a 5th independent agent.
**Why:** build-loop-local.sh sources claude-wrapper.sh directly — every agent invocation runs through it. Phase 4 agents would need to code against a wrapper interface that doesn't exist yet if it stays in Phase 6. It's ~100 lines, self-contained, no lib dependencies — a leaf node that fits Phase 1 criteria perfectly.
**Rejected:** Keeping in Phase 6 (forces Phase 4 to stub the interface or cross-reference bash).

---

## 2026-02-28 — Launchd scripts stay bash (supersedes part of 2026-03-01 small-utils decision)

**Decision:** setup-overnight.sh and uninstall-overnight.sh remain bash. Removed from conversion targets. Partially supersedes the 2026-03-01 decision "Convert small bash utilities to Python too" — that decision still holds for claude-wrapper, generate-mapping, and nightly-review, but NOT for launchd scripts.
**Why:** These are system bootstrap wrappers — they write plist XML and call launchctl. Converting to Python adds a Python dependency to a bootstrap path and buys zero functionality. They're short, stable, and don't interact with the Python package.
**Rejected:** Converting everything uniformly (adds complexity to bootstrap for no benefit).

---

## 2026-02-28 — Bash originals preserved indefinitely in separate tree

**Decision:** Original bash files in scripts/, lib/, and tests/ are untouched during and after Python conversion. Python code lives entirely in a new py/ directory tree. No moves, renames, or deletions of bash originals. Deletion is a separate future decision.
**Why:** Coexistence over replacement. Bash originals serve as reference, fallback, and operational baseline. During conversion, both versions can be compared side-by-side. No risk of losing working code during a rewrite. Brian's explicit directive: "keep the original bash files intact and organized as at present now."
**Rejected:** In-place replacement (risky, no fallback). Phased deletion plan (premature — conversion not yet validated).

---

## 2026-02-28 — Conventions doc scope: comprehensive Phase 0 deliverable

**Decision:** The Python conventions document must cover: error handling (typed exception hierarchy), subprocess patterns (run_claude wrapper with configurable timeout), logging (stdlib, mapped from bash levels), signal protocol preservation (flat strings at boundary, signals.py module), file-based state I/O (atomic writes, flock locking), type hints (full typing, mypy --strict), test patterns (pytest, shared conftest.py, assertion style, naming), interface stubs (function signatures build-loop-local calls from each lib), dependencies (stdlib + pytest only), package management (pyproject.toml + pip).
**Why:** Four (now five) agents running in parallel will each invent their own patterns if the conventions doc is vague. Every decision not made in the conventions doc becomes an integration problem in Phase 4. The doc is cheap to write and eliminates the most likely failure mode of parallel conversion.
**Rejected:** Minimal conventions doc (invites convention drift). Per-agent guidance (redundant, inconsistent).

---

## 2026-02-28 — Python 3.12+ minimum version

**Decision:** Minimum Python version for the py/ package is 3.12.
**Why:** Better typing support, improved error messages, f-string improvements. No Ventura support needed per Brian. 3.12 is current stable release line with full security support.
**Rejected:** 3.11 (would work but misses typing improvements that help agent-generated code quality).

---

## 2026-02-28 — py/ directory name (not src/)

**Decision:** Python code lives in `py/` at repo root, not `src/`.
**Why:** Explicit about content type. `src/` is ambiguous in a repo that already has scripts/ and lib/. `py/` is greppable, obvious, and won't be confused with any other directory.
**Rejected:** `src/` (ambiguous), `python/` (verbose), in-place alongside bash (violates coexistence rule).

---

## 2026-02-28 — Phase 3 stays sequential after Phase 1

**Decision:** build-loop-local decomposition analysis (Phase 3) runs after Phase 1 completes, not in parallel with it.
**Why:** Phase separations serve double duty: dependency ordering AND context window discipline. Running Phase 3 alongside Phase 1 would mean Brian is managing 5-6 concurrent agent contexts. The calendar time savings are minimal (Phase 3 is one chat session, maybe 30 minutes). The cognitive overhead and parallelization complexity are not worth it.
**Rejected:** Running Phase 3 in parallel with Phase 1 (no data dependency, but overextends context management and risks bloat).


---

## 2026-03-01 — Agent prompt length discipline

**Decision:** Agent prompts target ~40-65 lines max. First drafts are consistently 2x effective length — cut aggressively before delivering. Describe intent not implementation. Agents write code; prompts say WHAT and WHY, not HOW at line level.
**Why:** Accepted past prompts (Rounds 9, 13, etc.) were ~40 lines. The 150+ line prompt written this session injected chat session context drift into the agent's fresh start — defeating the purpose of fresh agent sessions. Over-specification wastes agent context budget before implementation begins.
**Rejected:** Verbose prompts with field-by-field dictation, line-level code snippets, implementation steps the agent would figure out from reading the codebase.

---

## 2026-03-01 — Splitting criteria relaxed

**Decision:** No rigid "one independently testable goal" or "3-4 files max" rule. As many goals as safely fit within agent context budget with room for generous exploration. Keep prompt tokens low, maintain structure and essentials. Integration tests when multi-testing after multi-change work.
**Why:** The constraint is agent context budget, not goal count. Prescriptive file limits are the kind of thing the agent figures out. Brian's framing: "you can test as many as will safely fit, with room for generous exploration."
**Rejected:** "No more than 3-4 files" rule, "independently testable systems" as splitting criteria.

---

## 2026-03-01 — Preconditions: no cd to repo

**Decision:** Agent prompts do not include `cd ~/auto-sdd`. Agents run locally via Claude desktop app (Mac) Code tab and are already in the repo working directory.
**Why:** `~/auto-sdd` resolves to `/root/auto-sdd` in sandbox contexts, causing wasted tool calls. Even locally, the agent is already in the project. The cd is wasted tokens.
**Rejected:** Including cd as defensive precondition (causes failures in sandbox, unnecessary locally).

---

## 2026-03-01 — Agent execution environment

**Decision:** Agents run through the Code section of the Claude for Mac desktop app on Brian's MacBook Air (Mac Studio later). Execution is local (filesystem, git commands), but agents push feature branches to origin by default.
**Why:** Affects merge workflow — use `git merge origin/<branch>` or GitHub PR, not local branch names. Precondition design: no cd needed (agent is already in repo cwd). Agents have full local filesystem access and GitHub auth.
**Rejected:** N/A — factual capture of environment. Corrected from initial "branches are local only" assumption (L-0046).


---

## 2026-03-01 — Always reprint full artifacts

**Decision:** When updating prompts, code, or any artifact that will be used in a separate context, always reprint the full updated version. Never say "just swap X" or "same as before but change Y."
**Why:** Brian runs agent prompts in Claude Desktop Code tab — a separate context that never sees the chat conversation. "Same but change the hash" is useless to the agent. Every artifact must be self-contained when delivered. Same principle applies to code snippets, config blocks, etc.
**Rejected:** Incremental diff-style updates (require reader to mentally merge, error-prone across contexts).
