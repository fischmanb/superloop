# Design Principles

> Standing constraints for all work on `auto-sdd` — code, documentation, knowledge capture, agent prompts, and any future tooling.
>
> These are not suggestions. They are enforced through review (chat sessions, prompt engineering) and advisory warnings (eval sidecar). They are never build-blocking.

---

## 1. Grepability

Every structured artifact (learnings, state files, specs, metadata) must be greppable by its key fields without parsing logic. No nested structures that require jq, regex groups, or multi-line matching to extract meaning. If `grep -i "tag:prompt-engineering"` can't find relevant entries, the format is wrong.

This means: flat key-value metadata, one logical entry per block, consistent delimiters, IDs and tags on their own lines. Content can be prose; metadata cannot be.

**Why**: The primary consumer of these files today is Claude grepping markdown in a chat session. The secondary consumer is a future script building a graph. Both need the same thing — fast, reliable extraction without brittle parsing.

**Test**: Can you find every entry related to topic X with a single `grep` command and no post-processing? If not, the format violates this principle.

---

## 2. Graph-readiness

All knowledge capture should be structured so that the transition to a graph store is a format conversion, not a knowledge extraction project. This means:

- **Unique IDs** on every discrete knowledge entry (learning, decision, finding)
- **Explicit relationships** between entries, using a small fixed set of edge types (see §3)
- **Consistent metadata** (type, tags, date, confidence, status) that maps directly to node properties
- **No implicit knowledge** — if two things are related, there's a `Related:` field saying so. Don't rely on proximity in the file or shared section headings to imply connection.

**Why**: We are building toward a knowledge graph for cross-session context retrieval. Every piece of structured knowledge written today is a node we won't have to extract later. The cost of adding an ID and a `Related:` field at write time is near zero. The cost of retroactively extracting relationships from prose across hundreds of entries is prohibitive.

**Test**: Can a script parse this file into a JSON adjacency list (nodes + edges) without natural language understanding? If not, the format violates this principle.

---

## 3. Relationship type schema (graph edge types)

Defined here, enforced everywhere. Keep the set small — every new edge type increases graph density and query complexity. Specificity belongs in tags and body text, not edge types.

| Edge type | Meaning | Directionality | Example |
|-----------|---------|----------------|---------|
| `related_to` | General topical connection. Default when the relationship exists but doesn't fit a stronger type. | Bidirectional | L-00042 (push discipline) ↔ L-00015 (agent behavior) |
| `supersedes` | This entry replaces or updates an earlier one. The earlier entry's status should be `superseded`. | Directional | L-00051 (revised retry logic) → supersedes → L-00030 (original retry logic) |
| `depends_on` | This entry's validity or applicability requires the referenced entry to hold. | Directional | L-00060 (sidecar feedback) → depends_on → L-00045 (eval system) |
| `contradicts` | These entries are in tension. Both may be valid in different contexts, or one may be wrong. Requires human judgment to resolve. | Bidirectional | L-00070 (concise prompts faster) ↔ contradicts ↔ L-00071 (terse prompts miss requirements) |

**Rules:**
- Every `Related:` field must specify the edge type: `Related: L-00015 (related_to), L-00030 (supersedes)`
- No new edge types without Brian's approval. If none of these four fit, use `related_to` and add context in the body.
- `supersedes` and `depends_on` are directional. `related_to` and `contradicts` are bidirectional.
- When an entry is created with a relationship, the referenced entry should be updated to include the back-reference. This is a maintenance task, not a blocker — missing back-references get caught during periodic sweeps.

---

## When to apply

These principles apply unevenly across contexts. The goal is precision, not blanket enforcement.

**Always applies:**
- Knowledge capture (learnings, findings, process rules)
- Documentation that will be consumed by future sessions or agents
- Structured output that other processes grep or parse (eval results, state files, failure catalogs)
- Prompt engineering — prompts that produce structured output should encode format expectations

**Selectively applies:**
- Validation pipeline phases: Phase 4a (Failure Catalog) and Phase 4b (RCA) outputs must be greppable and graph-ready. Phase 1 (Discovery) should be intentionally blind — no priors about format.
- CLAUDE.md agent instructions — only when agents are instructed to produce structured metadata. Feature build agents don't need these principles.

**Does not apply:**
- Feature build prompts — agents building React components don't need to know about graph-readiness
- Intentionally blind exploration (early QA phases, investigation prompts)
- Conversational analysis in chat sessions

**Enforcement level:** Advisory, never blocking. A build that produces non-greppable eval output is still a successful build. Principle violations are caught in review (chat sessions examining outputs) and optionally flagged by the eval sidecar as warnings. They never fail a build or block a commit.

---

## 4. Learnings entry enums

Defined here, enforced in all `learnings/` files. Same philosophy as the edge type schema — small fixed sets, specificity belongs in tags and body text.

### Confidence

| Value | Meaning |
|-------|---------|
| `high` | Observed repeatedly or verified mechanically (tests, grep, build data). |
| `medium` | Observed once or inferred from data. Plausible but not yet confirmed by repetition. |
| `low` | Hypothesis or single anecdote. May not generalize. |

### Status

| Value | Meaning |
|-------|---------|
| `active` | Current and applicable. Surfaced in core.md and fresh onboard reads. |
| `superseded` | Replaced by a newer entry. Must have a `supersedes` edge from the replacement. Retained for graph history, not surfaced in core.md. |
| `deprecated` | No longer relevant — conditions changed, tool changed, approach abandoned. Not replaced by a specific entry. Retained for graph history, not surfaced in core.md. |

**Rules:**
- No new values without Brian's approval.
- `superseded` entries must be reachable via `supersedes` edge from the entry that replaced them. If there's no replacement, use `deprecated`.
- Status changes are edits to existing entries, not new entries. Update the status field in place.

---

## Maintaining this file

This file is a constitution, not a changelog. It should be short, stable, and authoritative. Changes require Brian's explicit approval.

- **Adding a principle**: Rare. Must apply project-wide, not just to one subsystem.
- **Adding an edge type**: Requires justification that none of the existing four cover the relationship. Brian approves.
- **Updating "When to apply"**: As new subsystems ship (validation pipeline, learnings system), update the selective application guidance.
