# campaign-results/

Live testing data from auto-sdd v2.0.0 build campaigns on the stakd application.

## What This Is

Two parallel campaigns building the same 28-feature stakd application from identical specs:
- **v2 (Sonnet 4.6)**: Primary campaign, started 2026-02-27 10:48 EST
- **v3 (Haiku 4.5)**: Comparison campaign, started 2026-02-27 13:08 EST

Same machine, same specs, same build loop. Different models.

## Structure

```
campaign-results/
├── raw/
│   ├── v2-sonnet/          # Raw data: git log, cost log, roadmap, resume state
│   └── v3-haiku/           # Raw data + sidecar eval JSONs
├── reports/
│   ├── v2-sonnet/          # Timing, throughput, overhead analysis
│   ├── v3-haiku/           # Same + sidecar eval analysis
│   └── campaign-comparison.md   # Head-to-head findings
├── generate-reports.py     # Script to regenerate reports from raw data
└── README.md
```

## Key Finding

**Model token speed ≠ build speed.** Haiku generates tokens ~2x faster than Sonnet, but both produce features at ~4 features/hour. The bottleneck is CPU/disk (npm, tsc, tests), not LLM inference. Parallelism across features > per-feature model speed.

## Regenerating Reports

```bash
cd ~/auto-sdd/campaign-results
python3 generate-reports.py
```

Reports are generated from raw data (git logs, cost logs, eval JSONs). Re-run after campaigns complete for final numbers.
