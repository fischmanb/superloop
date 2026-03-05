# Seed Data & Distribution Strategy

> Status: Design phase. V1 plan: seed packs. Future: tiered packs, global sync.
> Author: Brian Fischman + Claude, 2026-03-04
> Depends on: Campaign Intelligence System (`WIP/campaign-intelligence-system.md`), stable vector schema

---

## 1. Problem Statement

Every new auto-sdd user cold-starts with zero campaign data. The CIS learning loop needs 3+ campaigns before predictions become useful. First-time users get no value from the intelligence system until they've invested significant compute and time. This is an unacceptable onboarding experience for a product that claims to self-improve.

---

## 2. Options Considered

### A. Cold start (rejected)
Every user starts empty. First 3 campaigns are calibration. Worst UX, simplest implementation.

### B. Seed packs (V1 plan — selected)
Ship auto-sdd with pre-built learnings from Brian's campaigns. Curated feature vectors, initial model weights, known patterns. New users start informed. Updated as more campaigns run.

- **Pros**: Immediate value, curated quality, controlled distribution, no privacy concerns
- **Cons**: One-directional (users don't contribute back), limited by campaign diversity, staleness risk

### C. Tiered/community seed packs (V2)
Stratified by ecosystem: "Next.js patterns," "Python API patterns," "monorepo patterns." Community contributes packs via PRs. Quality-reviewed before inclusion.

- **Pros**: Targeted relevance, scales curation, community participation
- **Cons**: Pack authoring overhead, quality control, versioning
- **Prerequisite**: Stable vector schema + pack format spec + 2-3 ecosystem-diverse campaigns

### D. Global sync (V3, if adoption warrants)
All instances report anonymized vectors to a central service (or public Git repo). Cross-user model trained on aggregate data. Network effect — every campaign improves predictions for everyone.

- **Pros**: Compounding value, strongest model, automatic improvement
- **Cons**: Privacy (anonymized vectors still reveal project structure), trust, hosted infrastructure, garbage-in risk, regulatory complexity
- **Viable at**: 10+ active users generating campaign data
- **Lightweight variant**: Public GitHub repo of anonymized vectors. `auto-sdd sync --contribute` pushes, `auto-sdd sync --pull` fetches aggregate model. Git as transport, no custom infrastructure.

### E. Federated learning (alternative to D)
Local model training, shared model weights (not raw data). Privacy-preserving network effects.

- **Pros**: Privacy-preserving, network effects without raw data sharing
- **Cons**: Hard to implement well, requires compatible model architectures, nontrivial weight aggregation
- **Viable at**: Significant adoption + stable model architecture

---

## 3. V1 Plan: Seed Packs

### 3.1 What ships

A `seed-data/` directory in the auto-sdd repo containing:
- `vectors.jsonl` — curated feature vectors from Brian's campaigns (stakd-v2, CRE, future campaigns)
- `patterns.json` — pre-computed pattern findings (co-occurrence rules, risk factors)
- `model-weights/` — initial trained model (once Phase 2 of CIS produces one)
- `SEED-MANIFEST.md` — documents what's included: campaign count, project types, vector count, model version, last updated date

### 3.2 How it loads

`vector_store.py` checks for `seed-data/vectors.jsonl` on first campaign run. If present and no local vectors exist, imports seed vectors with `source: "seed"` metadata. Local campaign data always takes precedence in model training — seeds provide the prior, local data updates the posterior.

### 3.3 Schema stability requirement

**The vector schema must be stable before seed packs ship.** Seed packs are serialized vectors — if the schema changes, old packs break. CIS Round 1 must produce a schema versioned explicitly (e.g., `schema_version: "1.0"`). The vector store reads the version and handles migration or skips incompatible seeds with a warning.

### 3.4 Update cadence

After each real campaign, Brian reviews and optionally updates the seed pack:
- New vectors appended (with anonymization if project-specific details are sensitive)
- Pattern findings recomputed
- Model retrained on expanded dataset
- SEED-MANIFEST.md updated with new counts and date

### 3.5 Anonymization

Seed vectors strip: project paths, feature names (replaced with generic IDs), commit hashes, branch names. Retain: complexity tier, component types, signal values, outcomes, temporal position. The patterns and model weights are inherently anonymized — they're statistical aggregates.

---

## 4. Migration Path: V1 → V2 → V3

```
V1: Seed packs (Brian's data)
 └──▶ V2: Tiered community packs (ecosystem-specific, PR-contributed)
       └──▶ V3: Global sync (anonymized vector sharing, aggregate model)
             └──▶ V3b: Federated learning (if privacy requirements demand it)
```

Each transition is additive. V2 adds a contribution pathway. V3 adds a sync mechanism. The vector schema and pack format from V1 remain the interface contract throughout.

---

## 5. Critical Design Dependency

The vector schema defined in CIS Round 1 (`WIP/campaign-intelligence-system.md`) is the foundation for all distribution strategies. Get it wrong and every seed pack, community contribution, and sync protocol breaks on schema change. The schema must:
- Be explicitly versioned
- Support forward-compatible section addition (already true — sectioned dict design)
- Define a stable identity format that works across projects (no project-specific paths in identity fields)
- Include `source` metadata on every vector (`"local"`, `"seed"`, `"community"`, `"sync"`)

---

## 6. Open Questions

1. **Anonymization completeness**: Are complexity tiers + component types + signal values sufficient for useful seeds, or do pattern findings degrade without feature names?
2. **Seed freshness**: Should auto-sdd check for updated seed packs (e.g., from a GitHub release) or only use what ships with the install?
3. **Local override**: If a user's local data contradicts a seed pattern, should the seed pattern be automatically demoted or require manual review?
4. **Licensing**: Seed data derived from private projects — does this need a separate data license from the code license?
