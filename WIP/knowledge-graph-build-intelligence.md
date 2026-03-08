# Knowledge Graph Build Intelligence System

## Vision

A compounding knowledge system for autonomous software development that gets smarter across every build campaign. Each campaign contributes structured knowledge — mistakes, resolutions, best practices, patterns — to a typed graph. Future campaigns query that graph at preprocessing time to inject better plans, not just warnings, into each feature spec before the build agent touches it.

The system is **prescriptive, not just reactive**. It doesn't warn "agents got Geo Point wrong." It synthesizes: "given what's been tried before on map features using DuckDB, here is the best approach."

---

## Architecture

### Storage: SQLite + FTS5 + Embeddings

One local SQLite database (`~/.auto-sdd/knowledge.db`) shared across all campaigns.

**Tables:**

```sql
-- Core knowledge nodes
CREATE TABLE nodes (
  id          TEXT PRIMARY KEY,        -- uuid
  type        TEXT NOT NULL,           -- 'principle' | 'pattern' | 'instance' | 'mistake' | 'resolution'
  level       TEXT NOT NULL,           -- 'universal' | 'framework' | 'technology' | 'project'
  title       TEXT NOT NULL,
  body        TEXT NOT NULL,           -- full text, indexed by FTS5
  tags        TEXT NOT NULL,           -- JSON array: domains, technologies, file patterns
  campaign    TEXT,                    -- null for universal/framework nodes
  feature_id  INTEGER,                 -- null for non-instance nodes
  created_at  TEXT NOT NULL,
  embedding   BLOB                     -- float32 vector via Anthropic embeddings API
);

-- Typed edges between nodes
CREATE TABLE edges (
  src         TEXT NOT NULL REFERENCES nodes(id),
  dst         TEXT NOT NULL REFERENCES nodes(id),
  rel         TEXT NOT NULL,           -- 'generalizes_to' | 'instance_of' | 'requires' | 'conflicts_with' | 'supersedes' | 'caused_by'
  weight      REAL DEFAULT 1.0,
  created_at  TEXT NOT NULL
);

-- FTS5 index for BM25
CREATE VIRTUAL TABLE nodes_fts USING fts5(
  title, body, tags,
  content='nodes', content_rowid='rowid'
);

-- Per-campaign feature outcomes (raw material for node extraction)
CREATE TABLE feature_outcomes (
  id          TEXT PRIMARY KEY,
  campaign    TEXT NOT NULL,
  feature_id  INTEGER NOT NULL,
  feature_name TEXT NOT NULL,
  domain      TEXT,
  source      TEXT NOT NULL,           -- 'drift_check' | 'eval_sidecar' | 'build_failure' | 'manual'
  raw_output  TEXT,                    -- structured failure output (tsc errors, test failures)
  resolution  TEXT,                    -- what actually worked
  created_at  TEXT NOT NULL
);
```

### Node Taxonomy

```
universal        General software engineering principles
  └─ framework   Framework-specific patterns (Next.js App Router, tRPC, DuckDB)
       └─ tech   Technology-specific implementation details
            └─ instance  Project/feature-specific observations
```

Mistakes and resolutions are `instance` nodes. When the same lesson appears across 3+ campaigns, it gets promoted to `technology` or `framework` level by the promotion job.

### Graph Structure

The typed edges encode relationships that vector search cannot. Examples:

- `instance_of` — "agent forgot initDuckDBViews()" → "lazy initialization pattern in server components"
- `generalizes_to` — "Next.js cold-start DuckDB issue" → "stateful singleton pattern"
- `requires` — "DuckDB map query" → "initDuckDBViews() called on startup"
- `conflicts_with` — "Server Component" ↔ "client-side state mutation"
- `caused_by` — "tRPC type error" → "missing zod schema on input"
- `supersedes` — "use initDuckDBViews() with guard" supersedes "call getDB() directly"

BFS from the upcoming feature's domain + dependency chain → traverses the graph → retrieves the relevant subgraph → feeds synthesis.

---

## Data Flow

### Write path (post-build, async, never on critical path)

```
feature build completes
    → build-loop-local.sh signals completion
    → eval sidecar already running async — extend it:
         1. Read drift check output + eval findings for this feature
         2. Extract structured failure output (tsc errors, test failures, agent BUILD_FAILED signal)
         3. Extract resolution (what the agent did that worked, from its final output)
         4. Write raw record to feature_outcomes table
         5. Call Anthropic embeddings API on the outcome text
         6. Write candidate node(s) to nodes table with embedding
         7. Create edges: instance_of (domain), caused_by (if error chain detected)
```

### Read path (pre-build, in spec preprocessor)

```
spec preprocessor invoked for feature N
    1. Parse feature N's domain, tags, dependency chain from roadmap.md
    2. BFS from feature N's deps → collect node IDs of their outcomes
    3. Semantic query: embed the feature spec → cosine similarity against nodes.embedding
    4. BM25 query: keywords from spec → FTS5 search on nodes_fts
    5. Merge BFS results + semantic results + BM25 results, rank by combined score
    6. Retrieve top-N nodes + their edges (1-hop neighborhood)
    7. Call synthesis model with subgraph + feature spec:
       "Given these prior outcomes and best practices, what is the best implementation
        approach for this feature? Be specific and concrete."
    8. Inject synthesis into feature spec's Implementation Notes as:
       "## Build Intelligence\n{synthesis}"
    9. Commit enriched spec
```

### Promotion job (nightly / post-campaign)

```
for each technology-level cluster of instance nodes:
    if 3+ instances share the same lesson (by semantic similarity > threshold):
        create or update a technology-level node
        add instance_of edges from instances to promoted node
        flag promoted node for human review (optional)
```

---

## Integration Points

### Extends eval sidecar (`scripts/eval-sidecar.sh` / `py/eval_sidecar.py`)

Add second job to existing sidecar. Sidecar already runs async after each feature — zero critical path impact.

### New module: `py/spec_preprocessor.py`

Called from `build-loop-local.sh` before agent invocation:
```bash
python3 "$SCRIPT_DIR/../py/spec_preprocessor.py" "$PROJECT_DIR" "$feature_id"
```

Reads: `roadmap.md`, feature spec, `~/.auto-sdd/knowledge.db`
Writes: enriched feature spec + commit

### New module: `py/knowledge_store.py`

Shared library for read/write against `knowledge.db`. Used by both sidecar (write) and preprocessor (read).

---

## What to Capture (and What Not To)

**Capture:**
- `tsc --noEmit` stderr — compiler errors, type mismatches, missing imports
- `npm run build` stderr — bundler errors
- `npm test` / `pytest` failure output — test names and assertion errors
- Agent's `BUILD_FAILED` signal + the line before it (often contains the diagnosis)
- Drift check output — spec vs. code mismatches
- Eval sidecar findings — repeated mistake classifications

**Do NOT capture:**
- Raw agent stdout prose — verbose, noisy, buries signal
- Entire build logs — too large, extract structured outputs instead

---

## Compounding Value Over Time

| Campaigns run | System capability |
|---|---|
| 1 | Baseline — no prior knowledge, preprocessor is a no-op |
| 2-3 | First intra-build patterns emerge (DuckDB, tRPC, map coordinate format) |
| 5+ | Technology-level nodes promote, cross-project patterns visible |
| 10+ | Framework-level nodes stabilize, synthesis becomes prescriptive |
| 20+ | Universal principles emerge, system approaches domain expertise |

Each campaign is a training run. The graph is the model. Fine-tuning is deferred until the corpus is large enough to be worth it (100+ campaigns, diverse project types) — at that point the same structured data is already in the right format for SFT.

---

## Implementation Order

1. `py/knowledge_store.py` — SQLite schema, read/write, embedding calls
2. Extend eval sidecar — write path, outcome extraction
3. `py/spec_preprocessor.py` — read path, BFS + semantic + BM25, synthesis call
4. Wire into `build-loop-local.sh` — one line before agent invocation
5. Promotion job — post-campaign, optional initially

Start with (1) and (2) — the write path. Get data accumulating before building the read path. The preprocessor with an empty knowledge base is a no-op, which is fine.

---

## Notes

- Knowledge DB lives at `~/.auto-sdd/knowledge.db` — outside any project repo, shared globally
- Embeddings via Anthropic API (`voyage-3` or equivalent) — called async, never on critical path
- SQLite is portable, zero-infra, continuously writable — no reindexing required (unlike GraphRAG)
- The graph structure is *typed and explicit* — not discovered via community detection (GraphRAG) but written at extraction time based on known taxonomy. This is the key architectural difference from Microsoft's GraphRAG, which is designed for unknown structure in document corpora. Our structure is known.
- Fine-tuning / SFT deferred: the same `feature_outcomes` + `nodes` data is already in the right format when the time comes
