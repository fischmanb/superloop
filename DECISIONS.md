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
