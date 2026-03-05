# Campaign Intelligence System — Design Plan
## Eval Sidecar → Learning Loop → Predictive Guidance

> Status: Design phase. No implementation started.
> Author: Brian Fischman + Claude, 2026-03-04
> Depends on: Bash→Python conversion (COMPLETE), eval sidecar (COMPLETE), auto-QA pipeline (COMPLETE)

---

## 1. Problem Statement

The build loop produces features. The eval sidecar scores them. Auto-QA validates them at runtime. But none of these systems *learn*. Campaign N's failures don't reduce Campaign N+1's failure rate. Intra-campaign, feature 20's prompt has no knowledge of patterns discovered in features 1-19 beyond a flat `repeated_mistakes` string.

The gap is a closed-loop intelligence system that:
- **Detects** patterns in build and runtime outcomes (mechanical, not agent-judged)
- **Injects** relevant findings into subsequent build prompts (intra-campaign, real-time)
- **Accumulates** structured data across campaigns (cross-campaign, offline)
- **Predicts** which features are likely to fail and why (trained model, improving over time)
- **Self-evaluates** which injections actually improved outcomes (meta-learning)

---

## 2. Architecture Overview

### 2.1 Three Signal Sources

| Source | Timing | Signal Type | Examples |
|--------|--------|-------------|----------|
| Build loop | During build | Compile-time outcomes | Exit codes, retries, duration, drift/test results |
| Eval sidecar | Per-commit, intra-campaign | Quality assessment | Scope, compliance, integration, type redecls, conventions |
| Auto-QA | Post-campaign | Runtime behavior | Broken routes, auth bypasses, AC failures, interaction bugs |

### 2.2 Data Flow

```
Build Loop ──────────────┐
                         ├──▶ Vector Store ──▶ Pattern Analysis ──▶ Risk Profile
Eval Sidecar ────────────┤       (JSONL)        (pluggable rules)    (compact JSON)
                         │                            │                    │
Auto-QA (post-campaign) ─┘                            │                    │
                                                      ▼                    ▼
                                              Campaign Findings    build_feature_prompt()
                                                (.md report)       (injected warnings)
                                                      │
                                                      ▼
                                              Learnings Candidates
                                              (graph-schema, human review)
```

### 2.3 Storage Architecture

**Single vector store, multiple writers, sectioned schema.**

Each signal source owns its section of the feature vector. Writers only know their own schema. The store handles merge and persistence. New signal sources register new sections — zero changes to existing code.

```python
@dataclass
class FeatureVector:
    # Identity (immutable after creation)
    feature_id: int
    feature_name: str
    campaign_id: str
    build_order_position: int
    timestamp: str

    # Extensible sections — each writer owns its section
    sections: dict[str, Any] = field(default_factory=dict)
```

**API** (`vector_store.py`):
- `create_vector(identity) -> vector_id`
- `update_section(vector_id, section_name, data) -> None`
- `get_vector(vector_id) -> FeatureVector`
- `query_vectors(filters) -> list[FeatureVector]`

Backend: JSONL initially. Abstracted behind query interface so SQLite swap is internal-only if needed at scale (Phase 3+).

---

## 3. Feature Vector Schema

### 3.1 Identity (immutable, set at feature start)

| Field | Type | Source | Derivable? |
|-------|------|--------|------------|
| feature_id | int | Roadmap topo sort | ✅ exists |
| feature_name | str | Roadmap topo sort | ✅ exists |
| campaign_id | str | Generated at campaign start | ⚠️ trivial addition |
| build_order_position | int | Build loop idx param | ✅ exists |
| timestamp | str | ISO datetime at vector creation | ✅ trivial |

### 3.2 Section: `pre_build_v1` (written before agent runs)

| Field | Type | Source | Derivable? |
|-------|------|--------|------------|
| complexity_tier | str (S/M/L/XL) | Feature.complexity | ✅ exists |
| dependency_count | int | Topo sort graph in-edges | ✅ exists (needs extraction) |
| depends_on_completed | int | Compare deps vs built_feature_names | ✅ derivable at build time |
| depends_on_pending | int | dependency_count - depends_on_completed | ✅ derived |
| branch_strategy | str | Config | ✅ exists |
| estimated_file_count | int | Heuristic from complexity tier | ⚠️ rough, improves with data |

### 3.3 Section: `build_signals_v1` (written after build completes)

| Field | Type | Source | Derivable? |
|-------|------|--------|------------|
| build_success | bool | FEATURE_BUILT signal | ✅ already parsed |
| retry_count | int | Build loop attempt counter | ✅ already tracked |
| retry_succeeded | bool | success AND retry_count > 0 | ✅ derived |
| agent_model | str | Config | ✅ already logged |
| build_duration_seconds | int | time.time() delta | ✅ already computed |
| drift_check_passed | bool | check_drift result | ✅ exists |
| test_check_passed | bool | check_tests result | ✅ exists |
| injections_received | list[str] | build_feature_prompt return | ⚠️ needs prompt_builder change |
| component_types | list[str] | Post-hoc from diff file paths | ⚠️ needs derivation logic |
| touches_shared_modules | bool | "shared"/"db" in component_types | ✅ derived from above |

### 3.4 Section: `eval_signals_v1` (written by eval sidecar per-commit)

| Field | Type | Source | Derivable? |
|-------|------|--------|------------|
| files_added | int | Mechanical eval diff_stats | ✅ exists |
| files_modified | int | Mechanical eval diff_stats | ✅ exists |
| lines_added | int | Mechanical eval diff_stats | ✅ exists |
| lines_removed | int | Mechanical eval diff_stats | ✅ exists |
| type_redeclarations | int | Mechanical eval | ✅ exists |
| framework_compliance | str | Agent eval signal | ✅ exists |
| scope_assessment | str | Agent eval signal | ✅ exists |
| integration_quality | str | Agent eval signal | ✅ exists |
| repeated_mistakes | str | Agent eval signal | ✅ exists |
| eval_notes | str | Agent eval signal | ✅ exists |

### 3.5 Section: `convention_signals_v1` (Round 4 — eval prompt revision)

| Field | Type | Source | Derivable? |
|-------|------|--------|------------|
| convention_compliance | str (followed/partial/violated) | Revised eval agent | ⚠️ needs eval prompt change |
| violations | list[dict] | Revised eval agent | ⚠️ needs new signal parsing |

Each violation entry:
```json
{
  "pattern": "import_boundaries|state_management|error_handling|type_safety|code_reuse|naming|testing|component_architecture",
  "assessment": "followed|deviated|violated",
  "evidence": "specific file:line or description",
  "severity": "cosmetic|maintainability|correctness"
}
```

### 3.6 Section: `runtime_signals_v1` (backfilled by auto-QA post-campaign)

| Field | Type | Source | Derivable? |
|-------|------|--------|------------|
| runtime_failures_caused | int | Auto-QA failure catalog | ⚠️ needs file→feature join |
| failure_types | list[str] | Auto-QA failure categories | ⚠️ needs join |
| ac_pass_rate | float | Auto-QA AC validation | ⚠️ needs join |
| rca_root_causes | list[str] | Auto-QA RCA output | ⚠️ needs join |
| fix_attempted | bool | Auto-QA fix agent | ⚠️ needs join |
| fix_succeeded | bool | Auto-QA fix agent | ⚠️ needs join |
| cross_feature_interaction | bool | RCA file intersection | ⚠️ needs analysis |

### 3.7 Outcome (derived, computed after all sections populated)

| Field | Type | Derivation |
|-------|------|-----------|
| fully_successful | bool | build_success AND drift AND test AND runtime_failures == 0 |
| build_only_success | bool | build_success AND runtime_failures > 0 |
| failure_mode | str | First failing gate: compile/test/drift/runtime/interaction |

---

## 4. Detection: Pluggable Pattern Analysis

### 4.1 Rule Protocol

```python
@dataclass
class Finding:
    rule_name: str
    confidence: float  # 0-1
    evidence: list[str]  # feature names or descriptions
    recommendation: str  # injection-ready warning text

@dataclass
class PatternRule:
    name: str
    min_samples: int  # don't fire until N features observed
    detect: Callable[[list[FeatureVector]], list[Finding]]
```

Rules are registered in a list. The analysis runner calls all registered rules, filters by min_samples, and collects findings. Adding a new detector = defining a function + appending to the registry.

### 4.2 Initial Rules (Phase 1, Round 3)

**Co-occurrence rule**: For each pair of categorical signals, compute co-occurrence rates. Flag when two signals co-occur at >2x their independent base rates. E.g., "scope_assessment=sprawling AND integration_quality=major co-occur in 80% of cases vs 15% expected independently."

**Temporal decay rule**: Compare signal distributions in first-half vs second-half of campaign. Flag if failure rates increase (possible context degradation or dependency cascading in chained strategy).

**Retry effectiveness rule**: For features with retry_count > 0, compute success rate. Compare build_model vs retry_model outcomes. Flag if retries consistently fail (wasted time) or consistently succeed (the feature needed two passes).

**Shared module risk rule**: For features where touches_shared_modules=true, compute failure rate vs features that don't. Flag if shared module involvement predicts failure.

### 4.3 Later Rules

**Phase 2 — Model prediction rule**: Trained classifier (scikit-learn, logistic regression or gradient-boosted tree) predicts `fully_successful` from pre-build + build signals. Outputs per-feature risk score + top contributing factors. Rule fires by producing a Finding with the model's prediction and feature importances.

**Phase 3 — Injection effectiveness rule**: For each injection type, compare outcomes of features that received it vs similar features that didn't. Uses `injections_received` field + outcome. Produces findings like "Warning about import boundaries reduced integration failures by 40%." Prunes ineffective injections from the active set.

---

## 5. Application: Intra-Campaign Injection

### 5.1 Enriched Feedback Path

Today: `read_latest_eval_feedback()` reads the single most recent eval JSON and formats non-passing fields as advisory text. This gets injected into `build_feature_prompt()`.

Target: After every N evaluated commits (configurable, default 3), run all registered pattern rules on accumulated vectors from the current campaign. Produce a compact `risk_context` that supplements the existing eval feedback.

```
build_feature_prompt reads:
├── codebase_summary     (cached on tree hash — what exists)
├── eval_feedback        (latest eval — what just happened)
└── risk_context         (pattern analysis — what history predicts)  ← NEW
```

### 5.2 Risk Context Format

```
## Campaign Intelligence (features 1-12 analyzed)

⚠ SHARED MODULE RISK: 4 of 5 features touching db/ had integration_quality=major.
  This feature's spec references database operations.
  → Verify server/client component boundaries before committing.

⚠ SCOPE TREND: scope_assessment trending from focused (features 1-5) to moderate
  (features 6-12). Possible context accumulation in chained strategy.
  → Keep changes minimal. Touch only files required by the spec.

📊 Confidence: based on 12 features in current campaign.
```

### 5.3 Separation from Codebase Summary

Codebase summary: cached on git tree hash, describes code structure. Changes when code changes.
Risk context: derived from campaign vectors, describes build outcome patterns. Changes as features complete.
Different lifecycles, different cache keys, different injection points. Composed together in prompt_builder but stored and refreshed independently.

---

## 6. Application: Cross-Campaign Learning

### 6.1 Accumulated Vector Dataset

All campaign vectors persist in `logs/feature-vectors.jsonl`. Each campaign appends. The file grows monotonically. After N campaigns, it contains N × features_per_campaign records with all sections populated (runtime_signals backfilled after auto-QA).

### 6.2 Pre-Campaign Risk Profiling (Phase 2)

Before a campaign starts, the model reads the accumulated dataset and the new campaign's roadmap. For each pending feature, it computes a risk profile based on pre-build characteristics matched against historical outcomes.

Output: `logs/risk-profile-{campaign_id}.json` — per-feature risk scores and top risk factors. `build_feature_prompt` reads the relevant entry before each feature build.

> **Note:** This subsumes the previously standalone "Historical build estimator" (which would have correlated t-shirt sizes with actual build metrics). The feature vector schema already captures complexity_tier → build_duration → outcome, and the cross-campaign model provides the self-correcting estimation capability. No separate estimator needed.

### 6.3 Meta-Learning (Phase 3)

After 3+ campaigns, the system has enough data to evaluate its own interventions:
- Which injection types correlate with improved outcomes?
- Do warned features actually perform better than similar unwarned features?
- Which pattern rules produce findings that lead to actionable improvements?

The meta-learner trains on `injections_received` + outcome, controlling for pre-build characteristics. It adjusts injection weights and prunes ineffective warnings.

---

## 7. Auto-QA Integration

### 7.1 The Join Problem

Auto-QA operates per-app (runtime validation). Feature vectors are per-feature (build-time). The join key is **file paths**: auto-QA's RCA traces failures to files, eval sidecar's diff_stats map files to features.

### 7.2 Feature Attribution

Post auto-QA run, a `backfill_runtime_signals()` function:
1. Reads the campaign's feature vectors (file paths from eval diff_stats)
2. Reads auto-QA's failure catalog (affected files from RCA)
3. For each failure, intersects affected files with each feature's diff files
4. Writes `runtime_signals_v1` section to matching vectors
5. Sets `cross_feature_interaction=true` when a failure maps to >1 feature

### 7.3 Feedback Into Detection

Runtime signals feed the same pattern rule system. New rules enabled by runtime data:
- **Import boundary rule**: Features violating import boundaries (convention signal) → runtime import errors (runtime signal). Predictive link.
- **Auth coverage rule**: Features adding routes without auth checks → auth bypass failures.
- **Interaction risk rule**: Features in later build positions with many dependencies → higher cross_feature_interaction rate.

---

## 8. Implementation Rounds

> Revised 2026-03-04 after pressure testing. Key changes: Rounds 1+2 collapsed (value in 2 rounds not 3), single risk-context file replaces read_latest_eval_feedback chain, rule registry included from Round 2 but feature-flagged until needed, project-configurable quality dimensions, mechanical convention checks prioritized over agent judgment, manual seeding from stakd post-mortems.

### Round 1: Vector Store + Schema + Wire Writers
- **New file**: `py/auto_sdd/lib/vector_store.py`
- FeatureVector dataclass with identity + sections dict
- JSONL-backed CRUD: create_vector, update_section, get_vector, query_vectors
- Section schemas defined: pre_build_v1, build_signals_v1, eval_signals_v1
- Tests: `py/tests/test_vector_store.py`
- Build loop: create_vector at feature start, update_section("build_signals_v1") at feature end
- Eval sidecar: update_section("eval_signals_v1") in _evaluate_commit
- campaign_id generation (timestamp + strategy + model)
- build_feature_prompt returns (prompt, injections_list) tuple; callers updated
- Post-hoc component_types derivation from diff file paths
- Seed with manual findings from stakd-v2 post-mortem (transitive imports, scope creep in later features, chained strategy cascading failures) — stored as vectors with `source: manual`
- Tests for store, wiring, and seeding
- **Touches**: new vector_store.py + test, build_loop.py, prompt_builder.py, overnight_autonomous.py (caller update), eval_sidecar.py, test files
- **Estimated tokens**: ~22k active (may need 2 sub-rounds if cascading signature changes push over budget)

### Round 2: Analysis Framework + Intra-Campaign Injection
- PatternRule protocol + rule registry (feature-flagged: `ENABLE_PATTERN_ANALYSIS` env var, default false until validated)
- Initial rules: co-occurrence, temporal decay, retry effectiveness, shared module risk
- Intra-campaign: after every N evaluated commits (configurable, default 3), run registered rules on accumulated vectors
- Eval sidecar writes `risk-context.md` to eval output dir (replaces current `read_latest_eval_feedback` chain entirely)
- build_feature_prompt reads risk-context.md directly — single writer, single reader, one file
- generate_campaign_findings() markdown report from rule outputs
- Tests for rules, analysis runner, risk-context output, and prompt integration
- **Touches**: eval_sidecar.py, prompt_builder.py, drift.py (remove read_latest_eval_feedback or deprecate), test files
- **Estimated tokens**: ~18k active

### Round 3: Convention Eval Signals
- **Mechanical convention checks first** (higher trust, lower cost):
  - Import boundary validation: static analysis of actual import graph against allowed dependency rules
  - Type safety: count `any` types, untyped function parameters
  - Code duplication: detect duplicate string literals or similar function bodies
- **Agent eval only for genuinely subjective dimensions**: naming quality, architectural appropriateness
- Structured signal format: pattern/assessment/evidence/severity (mechanical checks weighted higher in model)
- Project-configurable quality dimensions: `.sdd-config/eval-dimensions.yaml` defines which checks to run, what categories exist, and per-project convention rules
- Eval prompt generator reads config to know what to ask the agent (only for non-mechanical dimensions)
- New section: convention_signals_v1
- Register convention-based pattern rules in registry (feature-flagged same as Round 2)
- Tests
- **Touches**: eval_lib.py, eval_sidecar.py, new config file, test files
- **Estimated tokens**: ~15k active

### Phase 2 (after 1+ real Python campaigns):

**Round 4: Auto-QA Feature Attribution**
- backfill_runtime_signals() joins auto-QA failures to feature vectors via file paths
- runtime_signals_v1 section population
- New pattern rules using runtime data (import boundary rule, auth coverage rule, interaction risk rule)
- **Touches**: post_campaign_validation.py or new module, vector_store.py (minor), test files

**Round 5: Cross-Campaign Model**
- scikit-learn classifier on accumulated vectors
- Pre-campaign risk profiling
- Risk profile consumption in build_feature_prompt
- Model evaluation / reporting
- Enable pattern analysis feature flag by default (validated by this point)

### Phase 3 (after 3+ campaigns):

**Round 6: Meta-Learner**
- Injection effectiveness analysis
- Adaptive injection weighting
- Ineffective warning pruning
- Self-evaluation reporting

---

## 9. Dependencies and Sequencing

```
Round 1 (vector store + wire writers)
  ├──▶ Round 2 (analysis + injection, feature-flagged)
  │      └──▶ Round 3 (convention eval, mechanical + agent)
  │
  └──▶ [Run real Python campaign — produces data]
         ├──▶ Round 4 (auto-QA attribution)
         └──▶ Round 5 (cross-campaign model, unflag pattern analysis)
                └──▶ [Run 2 more campaigns]
                       └──▶ Round 6 (meta-learner)
```

---

## 10. Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Detection method | Statistical rules (mechanical) | Agent judgment is unverifiable (L-00182 pattern). Deterministic detection is testable, reproducible. |
| Schema extensibility | Sectioned dict, not flat dataclass | New signal sources register sections without schema changes. Old vectors gracefully miss new sections. |
| Storage | JSONL behind vector_store.py abstraction | Build foundation right — future rounds extend through API, not refactor. SQLite swap internal-only if needed. |
| Rule registry | Included from Round 2, feature-flagged (`ENABLE_PATTERN_ANALYSIS`) | Registry protocol exists from the start so rules are additive. Feature flag prevents premature activation before validation. |
| Intra-campaign threshold | Every N commits (configurable) | Too frequent = noisy with small sample. Too rare = delayed injection. N=3 balances signal vs noise. |
| Component type derivation | Post-hoc from diff file paths | Pre-build derivation from specs requires frontmatter changes. Post-hoc is accurate and free. |
| Convention eval | Mechanical first, agent eval only for subjective dimensions | Import boundaries, type safety, code duplication are statically analyzable. Agent judgment reserved for naming, architecture. Mechanical signals weighted higher. |
| Quality dimensions | Project-configurable via `.sdd-config/eval-dimensions.yaml` | Hardcoded signal names make the system auto-sdd-specific. Config-driven dimensions generalize to any project. |
| ML approach | Simple classifiers (logistic regression, GBT) | Interpretable, verifiable, sufficient for categorical features × small N. Not neural/opaque. |
| Vector ownership | Single store module, multiple section writers | Avoids coordination bugs from multi-writer access to same fields. |
| Codebase summary separation | Separate from vector store | Different cache lifecycles (tree hash vs campaign). Avoids bloating every prompt with historical data. |
| Feedback data flow | Eval sidecar writes risk-context.md, prompt builder reads it directly | Replaces read_latest_eval_feedback chain. Single writer, single reader, one file. Simpler than multi-hop advisory string. |
| Auto-QA join | File path intersection | Only reliable join key between per-app failures and per-feature builds. |
| Cold start | Seed with manual findings from stakd post-mortems | Eliminates blank-slate problem. System starts with human knowledge, augments with data. |
| Round structure | Rounds 1+2 collapsed; value in 2 rounds not 3 | First round produces vectors AND wires writers. Second round produces analysis AND injection. No pure-infrastructure rounds with zero user value. |

---

## 11. Open Questions

1. **Spec-level component classification**: Post-hoc classification from diff paths works but is reactive. Should specs include structured component_types in frontmatter for pre-build risk profiling? Trade-off: spec authoring burden vs prediction quality.

2. **Vector store location**: `logs/feature-vectors.jsonl` co-locates with build logs. Alternative: `.sdd-state/vectors/` to separate state from logs. Does it matter?

3. ~~**Convention eval categories**: Should categories be project-configurable?~~ **Decided: yes.** `.sdd-config/eval-dimensions.yaml` defines per-project categories. Initial set is a starting point, not hardcoded.

4. **Intra-campaign rule frequency**: N=3 commits is a guess. Should this self-tune based on campaign size?

5. **Cross-campaign model retraining**: Retrain from scratch each time, or incremental? Scratch is simpler and dataset is small. Incremental matters if campaigns get large.

6. **JSONL vs SQLite transition trigger**: At what data size does JSONL query performance justify migration? Probably ~1000 vectors (35+ campaigns). May never hit this.

---

## 12. Pressure Test Results (2026-03-04)

### Test 1: Does this achieve robust, generalizable, autonomous self-improving software realization?

**Strengths**: Compounding learning loop is real — each campaign feeds the next, detection improves with data, meta-learner closes the feedback loop. Sectioned schema means new signal sources don't break existing infrastructure. Mechanical detection avoids agent-judgment trap throughout.

**Weaknesses identified and addressed**:

| Gap | Resolution | Round |
|-----|-----------|-------|
| Hardcoded signal names make system auto-sdd-specific | Project-configurable quality dimensions via `.sdd-config/eval-dimensions.yaml` | Round 3 |
| Convention eval relies on unverifiable agent judgment | Mechanical checks first (static analysis for import boundaries, type safety, code duplication). Agent eval only for genuinely subjective dimensions. Mechanical weighted higher. | Round 3 |
| Cold start — first campaign gets zero value from empty model | Seed with manual findings from stakd post-mortems. System starts informed. | Round 1 |

### Test 2: Can outputs be achieved via simpler, more extensible, or more efficient means?

**Adopted simplifications**:

| Proposal | Decision |
|----------|----------|
| Defer vector_store.py to Round 5 | **Rejected** — foundation approach is justified given clear data model and 6-round plan. Build it right once. |
| Collapse Rounds 1+2 | **Accepted** — first round now produces vectors AND wires writers. Value in 2 rounds not 3. |
| Single risk-context.md file replacing read_latest_eval_feedback chain | **Accepted** — single writer (sidecar), single reader (prompt builder), one file. |
| Defer rule registry to Phase 3 | **Rejected** — registry included from Round 2 but feature-flagged (`ENABLE_PATTERN_ANALYSIS`). Protocol exists from the start so rules are additive; flag prevents premature activation. |
| Plain function list instead of registry | **Rejected** — same reasoning. Feature flag achieves the "don't use until validated" goal without requiring later refactor. |
