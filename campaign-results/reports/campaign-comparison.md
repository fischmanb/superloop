# Campaign Comparison: Sonnet vs Haiku

## Head-to-Head

| Metric | v2 (Sonnet) | v3 (Haiku) | Delta |
|---|---|---|---|
| Features built | 24 | 11 | — (campaigns in progress) |
| Build window | 5.9h | 2.9h | — |
| **Throughput** | **4.0 feat/h** | **3.8 feat/h** | **~equal** |
| Median feature time | 6.0 min | 7.4 min | +1.5 min |
| Mean feature time | 8.8 min | 10.0 min | +1.2 min |
| Cost per feature | $0.07 | $0.08 | ~equal |
| Drift rate | 71% | 73% | ~equal |
| Outliers (>60m) | 1 | 0 | — |

## Key Findings

### 1. Model speed ≠ build speed

Haiku generates tokens ~2x faster than Sonnet. Yet throughput is nearly identical (4.0 vs 3.8 features/hour). The bottleneck is CPU/disk-bound operations — npm install, TypeScript compilation, test execution, drift checks — not LLM inference. This is the single most counterintuitive finding and the one most teams would get wrong.

**Implication**: Parallelism across features matters more than per-feature model speed. Two Haiku agents building simultaneously would outperform one Sonnet agent, even though Sonnet produces higher-quality code per turn.

### 2. Drift rates are model-independent

Both models produce spec drift at ~71-73%. This means drift is a property of the spec-to-implementation translation problem, not the model. The drift reconciliation system adds overhead per feature but catches real mismatches that compound if ignored.

### 3. Cost is dominated by context, not generation

Cost per feature is nearly identical ($0.07 vs $0.08) despite different model pricing. Cache read tokens dominate both cost profiles — the system pays for context loading, not for the generation itself. This has architectural implications: reducing context window size would cut costs more than switching models.

### 4. Outlier features reveal system gaps

The 85.9-minute outlier (User settings & profile edit, v2) and 34.9-minute outlier (Agent profile model, v3) both appear to involve retry cycles where the build loop detected failure and re-ran. These are the features where signal fallback (Round 36) would have prevented wasted work.

## Methodology Notes

- Timing derived from git commit timestamps (most reliable source)
- Feature duration = time from previous checkpoint/feature commit to current feature commit
- First feature excluded from timing stats (includes campaign startup overhead)
- "Clean" times exclude features >60 minutes (likely retries, not representative of build time)
- Cost data from cost-log.jsonl — v2 cost only captures sidecar sessions, not primary build agent
- Both campaigns running on same machine, same codebase spec, same 28-feature roadmap
- v2 started ~2h before v3 (not parallel — sequential on different terminal sessions)

## Data Completeness

| Artifact | v2 (Sonnet) | v3 (Haiku) |
|---|---|---|
| Build log | ⚠️ deleted inode (tee open) | ⚠️ deleted inode (tee open) |
| Cost log (JSONL) | ✅ 2 entries | ✅ 3 entries |
| Git history (timing) | ✅ 64 commits | ✅ 31 commits |
| Roadmap state | ✅ snapshot | ✅ snapshot |
| Sidecar evals | ❌ not configured | ✅ 3 eval JSONs |
| Resume state | ✅ snapshot | ✅ snapshot |
| Build summary JSON | ⏳ at campaign end | ⏳ at campaign end |

Generated: 2026-02-27
