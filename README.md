# auto-sdd

Spec-driven development with autonomous AI agents. You define features as Gherkin specs in a roadmap. The build loop picks the next one, hands it to a fresh Claude Code agent, validates the output mechanically (compile, tests, drift check), commits, and moves on. No human in the loop during builds. No shared context between features except what you explicitly define.

The system has been hardened over 35 rounds of iterative development against documented failure modes — agents fabricating work, ignoring explicit instructions, self-assessing incorrectly, failing silently. Every architectural decision traces back to a specific observed failure.

35 rounds of iterative development. 5,200+ lines of orchestration and reliability code. Two full multi-feature campaigns with published performance data, and a documented taxonomy of how AI agents actually fail in production loops.

Forked from [AdrianRogowski/auto-sdd](https://github.com/AdrianRogowski/auto-sdd), which introduced the concept. This fork rebuilt the runtime.

---

## Campaign Results

Two identical 28-feature campaigns were run against the same React + TypeScript + Next.js codebase, one on Sonnet 4.6 and one on Haiku 4.5, to answer a simple question: does a faster model build faster?

| Metric | Sonnet 4.6 | Haiku 4.5 |
|---|---|---|
| Features built | 24 | 11 |
| Build window | 5.9 hours | 2.9 hours |
| **Throughput** | **4.0 features/hour** | **3.8 features/hour** |
| Median feature time | 6.0 min | 7.4 min |
| Cost per feature | $0.07 | $0.08 |
| Drift reconciliation rate | 71% | 73% |

### Key findings

**Model inference speed is not the bottleneck.** Haiku generates tokens roughly 2x faster than Sonnet. Throughput is nearly identical. The wall time is dominated by CPU/disk-bound operations — npm install, TypeScript compilation, test execution, drift checks — not LLM generation. Most teams building multi-agent systems would get this wrong.

**Parallelism across features beats faster models.** Two Haiku agents building simultaneously would outperform one Sonnet agent, because the fixed-cost steps that dominate each feature run can overlap.

**Drift rates are model-independent.** Both models produce spec-to-implementation drift at ~72%. Drift is a property of the translation problem, not the model. The drift reconciliation system catches real mismatches that compound if left unchecked.

**Cost is dominated by context, not generation.** Cache read tokens dominate both cost profiles. The system pays for context loading. Reducing context window size cuts costs more than switching models.

Full campaign data, raw logs, and analysis in [`campaign-results/`](campaign-results/).

---

## What We Learned About Agent Reliability

35 rounds of development produced a taxonomy of how agents actually fail in production loops. These aren't edge cases — they're the dominant failure modes.

**Agents fabricate work.** Round 1: the agent produced a detailed description of bugs in code it never wrote. Zero files created. Reported success. This is why every validation step in the pipeline is mechanical — compile checks, test counts, grep for signals. The shell trusts nothing the agent says about itself.

**Agents ignore explicit instructions.** Across Rounds 32-34, agents were told "do NOT push to origin" in multiple formulations. Push rate: 100%. Prompt wording made no difference. This is documented as expected behavior, not a bug to fix.

**Self-assessment is uncorrelated with reality.** The build loop was designed around this finding. Every agent step is followed by a shell-side validation gate. The agent says "tests pass" — the shell runs the tests. The agent says "clean compile" — the shell runs the compiler. The agent's narrative is discarded; only mechanical signals matter.

**78% build failure rate was not a code problem.** Round 11 diagnosed a sustained failure rate. Root cause: API credit exhaustion, not context loss or bad prompts. The system was retrying doomed calls. Credit exhaustion detection now halts immediately instead of burning cycles.

The full failure catalog with remediation details is in [`.specs/learnings/agent-operations.md`](.specs/learnings/agent-operations.md). The round-by-round work log is in [`Agents.md`](Agents.md).

---

## Architecture

### Build validation pipeline

Every feature passes through mechanical validation before commit:

```
BUILD ──▶ COMPILE CHECK ──▶ TESTS ──▶ DRIFT CHECK ──▶ COMMIT
  │            │               │
  └── retry ◄──┴── retry ◄────┘
```

Each agent step runs in a fresh context window. The shell re-runs build and tests as a hard gate after every agent step — no additional tokens spent, no trust in self-assessment.

Post-build, three non-blocking validation gates run: test count regression detection (warns if passing tests drop), dead export detection (scans for exported symbols with zero import sites), and static analysis (auto-detects ESLint, Biome, or framework-specific linters).

### Signal protocol

Agents communicate via grep-parseable signals. No JSON parsing. No eval on agent output.

```
FEATURE_BUILT: {name}                              # Build success
BUILD_FAILED: {reason}                             # Build failure
NO_DRIFT / DRIFT_FIXED / DRIFT_UNRESOLVABLE       # Drift check
REVIEW_CLEAN / REVIEW_FIXED / REVIEW_FAILED        # Code review
```

### Codebase summary injection

Each build agent receives a generated summary of existing components, type exports, import graph, and learnings from prior features. This prevents type redeclaration, import conflicts, and repeated mistakes across features within a campaign.

### Eval sidecar

A separate process polls for new commits during a campaign, runs mechanical evaluations (and optionally agent-based evaluations), and writes per-feature JSON results. Observational only — never blocks builds, never modifies source files. Aggregates a campaign summary on shutdown via cooperative drain.

### Cost tracking

Every Claude CLI invocation is wrapped through `lib/claude-wrapper.sh`, which extracts token counts and cost data to JSONL. Build summary reports aggregate per-feature timing, test counts, token usage, and model used.

---

## What Works and What Doesn't

**Holds up well**: isolated frontend features built from tight Gherkin specs. The agent produces solid scaffolding with tests. TypeScript compiles. Drift checks catch spec misalignment before it compounds. Crash recovery with `--resume` survives interrupted overnight runs. Topological sort handles feature dependency ordering.

**Where it breaks down**:

Integration across features remains the hardest problem. Each agent builds in isolation. Codebase summary injection mitigates this significantly but doesn't eliminate it — complex cross-feature contracts (shared state, event buses, deeply nested type hierarchies) still produce integration issues that only surface at runtime.

Backend spec layer is missing. The framework is frontend-oriented. Database schemas, API contracts, and migrations have no equivalent spec format. The orchestrator can't validate what it can't parse.

Agent self-assessment is unreliable. This is stated multiple times because it's the single most important lesson. The reliability layer, validation gates, signal protocol, and eval sidecar all exist because of it. Any system that trusts agent self-reports will fail in ways that are invisible until they compound.

---

## File Structure

```
auto-sdd/
├── scripts/
│   ├── build-loop-local.sh        # Main build loop (2162 lines)
│   ├── overnight-autonomous.sh    # Overnight automation variant (1310 lines)
│   └── eval-sidecar.sh            # Eval sidecar — polls commits, runs evals (393 lines)
│
├── lib/
│   ├── reliability.sh             # Shared runtime: locking, backoff, state, truncation,
│   │                              #   cycle detection, crash recovery (594 lines)
│   ├── codebase-summary.sh        # Cross-feature context: components, types, imports (269 lines)
│   ├── eval.sh                    # Eval functions: mechanical checks, prompt gen, signal parsing (391 lines)
│   ├── claude-wrapper.sh          # Claude CLI wrapper + JSONL cost logging (62 lines)
│   └── validation.sh              # YAML frontmatter validation (66 lines)
│
├── tests/
│   ├── test-reliability.sh
│   ├── test-validation.sh
│   ├── test-codebase-summary.sh
│   ├── test-eval.sh
│   ├── dry-run.sh                 # Structural integration test
│   └── fixtures/dry-run/          # Test fixtures
│
├── campaign-results/              # Campaign data, raw logs, generated reports
│   ├── raw/v2-sonnet/             # Sonnet 4.6 campaign artifacts
│   ├── raw/v3-haiku/              # Haiku 4.5 campaign artifacts
│   └── reports/                   # Analysis and comparison reports
│
├── .specs/
│   ├── vision.md                  # App vision template
│   ├── roadmap.md                 # Feature roadmap (source of truth for builds)
│   ├── features/                  # Feature specs (.feature.md)
│   └── learnings/                 # Failure catalog and process lessons
│
├── docs/
│   └── campaign-data-recovery.md  # Recovery playbook for lost build logs
│
├── Brians-Notes/
│   └── PROMPT-ENGINEERING-GUIDE.md  # Prompt methodology for agent hardening
│
├── ONBOARDING.md                  # Full project context for new sessions
├── CLAUDE.md                      # Instructions read by Claude Code agents automatically
├── Agents.md                      # 35-round agent work log — asked vs actual
├── .env.local.example             # Full config reference (167 lines)
└── VERSION                        # 2.0.0
```

---

## Requirements

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code): `npm install -g @anthropic-ai/claude-code`
- `ANTHROPIC_API_KEY` in your shell environment
- **bash 5+** (macOS ships 3.2): `brew install bash`
- `yq`: `brew install yq`
- `gh` (GitHub CLI, for PR creation): `brew install gh`

---

## Quick Start

```bash
git clone https://github.com/fischmanb/auto-sdd.git
cd auto-sdd

# Verify everything works
./tests/test-reliability.sh
./tests/test-codebase-summary.sh
./tests/test-eval.sh
DRY_RUN_SKIP_AGENT=true ./tests/dry-run.sh

# Point it at a project
cp .env.local.example .env.local
# Edit .env.local — set TEST_CHECK_CMD, BUILD_CHECK_CMD, model preferences

# Define features
cd /path/to/your-project
/vision "A task management app for small teams"
/roadmap create

# Build
PROJECT_DIR=/path/to/your-project MAX_FEATURES=4 ~/auto-sdd/scripts/build-loop-local.sh

# Resume after crash
~/auto-sdd/scripts/build-loop-local.sh --resume
```

---

## Configuration

Key `.env.local` settings:

```bash
# Build validation
BUILD_CHECK_CMD=""          # Auto-detected (tsc, cargo check, etc.)
TEST_CHECK_CMD=""           # Auto-detected (npm test, pytest, etc.)
POST_BUILD_STEPS="test,dead-code,lint"   # Validation gates (all non-blocking)
DRIFT_CHECK=true

# Model selection (each step gets a fresh context window)
BUILD_MODEL=""              # Main build agent (default: claude-sonnet-4-6)
DRIFT_MODEL=""              # Drift detection agent
REVIEW_MODEL=""             # Code review agent

# Roadmap
MAX_FEATURES=4              # Features per run
BRANCH_STRATEGY=chained     # chained | independent | both | sequential

# Eval sidecar (runs alongside build loop)
EVAL_AGENT=true             # Enable agent-based evals in addition to mechanical
```

---

## Testing

```bash
cd ~/auto-sdd

# Unit and integration tests
./tests/test-reliability.sh        # Locking, backoff, state, truncation
./tests/test-validation.sh         # YAML frontmatter
./tests/test-codebase-summary.sh   # Component/type/import scanning
./tests/test-eval.sh               # Mechanical eval, signal parsing

# Structural dry-run (no API key needed)
DRY_RUN_SKIP_AGENT=true ./tests/dry-run.sh
```

---

## Credits

Original concept by [Adrian Rogowski](https://github.com/AdrianRogowski/auto-sdd), inspired by [Ryan Carson's Compound Engineering](https://x.com/ryancarson) approach. This fork rebuilt the runtime over 35 rounds of development, adding the reliability layer, test suite, eval system, and campaign infrastructure.

## License

MIT
