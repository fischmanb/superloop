# auto-sdd

Spec-driven development with autonomous AI agents. You define features as specs in a roadmap. The build loop picks the next one, hands it to a fresh agent, validates the output mechanically (compile, tests, drift check), commits, and moves on. No human in the loop during builds. No shared context between features except what you explicitly define.

The system has been hardened over 35+ rounds of iterative development against documented failure modes — agents fabricating work, ignoring explicit instructions, self-assessing incorrectly, failing silently. Every architectural decision traces back to a specific observed failure.

To date: a 37+/49-feature CRE analytics build (SitDeck, $201, 599 project tests passing), two full 28-feature campaigns on a React/Next.js codebase with published performance data, a clean 3/3 validation run against a fresh full-stack project (31 minutes, zero failures, compiles and runs), and a documented taxonomy of how AI agents actually fail in production loops.

Forked from [AdrianRogowski/auto-sdd](https://github.com/AdrianRogowski/auto-sdd), which introduced the concept. This fork rebuilt the runtime.

---

## System Overview
auto-sdd is a build loop that takes a project spec and autonomously produces working software by orchestrating AI agents. Each feature gets its own agent session with a fresh context window. The orchestrator handles sequencing, error recovery, and quality gates — the human reviews output, not process.

Built on top of [Claude Code](https://docs.anthropic.com/en/docs/claude-code) (Anthropic's CLI). The orchestrator is the value layer — it turns a one-shot "paste a prompt and pray" workflow into a repeatable, gated pipeline.

```
SPEC LAYER                    BUILD LOOP                         QUALITY GATES
─────────                     ──────────                         ─────────────

 roadmap.md ──┐               ┌─────────────────────┐
   (features, │               │  Parse roadmap       │
    deps,     ├──────────────▶│  Topological sort    │
    ordering) │               │  Load resume state   │
              │               └─────────┬───────────┘
 *.feature.md │                         │
   (per-feature│                        ▼
    specs)    │               ┌─────────────────────┐
              │               │  FOR each feature:   │
 CLAUDE.md ───┘               │                     │
   (project                   │  1. Setup branch    │
    constraints)              │  2. Build prompt     │──▶ Claude Code agent
                              │  3. Run agent        │     (fresh context,
                              │  4. Parse signals    │      reads codebase,
                              │  5. Post-build gates │◀──   writes code,
                              │  6. Record state     │      commits)
                              │                     │
                              │  On failure:         │
                              │    retry w/ feedback │
                              │    or mark failed    │
                              │                     │
                              └─────────┬───────────┘
                                        │
                                        ▼
                              ┌─────────────────────┐
                              │  Build summary       │
                              │  (JSON, per-feature  │
                              │   timing + status)   │
                              └─────────────────────┘
```

**What the gates check:** TypeScript compiles (`tsc --noEmit`), HEAD advanced (agent actually committed, not just claimed to), working tree clean, signal protocol (`FEATURE_BUILT`, `BUILD_FAILED`, etc.), and custom build/test commands (configurable per project).

**What the gates don't check:** whether the app actually runs. That's what auto-QA is for.
---

## Auto-QA: Post-Campaign Validation

After the build loop finishes, a separate multi-agent pipeline boots the app, browses it, generates acceptance criteria from specs, tests them via Playwright, catalogs failures, performs root cause analysis, and fixes them through the existing build gates.

Each phase is an isolated agent with fresh context. Phase 1 doesn't know what the specs say. Phase 2 doesn't see source code. Phase 4a doesn't guess at causes. This prevents the failure mode where a single agent with too much context rationalizes bugs away.

```
Build loop finishes
        │
        ▼
┌──────────────────┐
│  PHASE 0         │  Pure shell. No agents.
│  Runtime         │  npm install → npm build → npm dev
│  Bootstrap       │  Health check (poll until 200)
│                  │  Auth bootstrap (seed test account)
└────────┬─────────┘
         │ App running on localhost
         ▼
┌──────────────────┐
│  PHASE 1         │  Agent gets: browser + URL. Nothing else.
│  Discovery       │  No specs, no roadmap, no source code.
│                  │  Browses blind. Screenshots every page.
│                  │  Outputs: route inventory, nav graph,
│                  │  interactive elements, console errors.
└────────┬─────────┘
         │ "What exists"
         ▼┌──────────────────┐
│  PHASE 2         │  Agent gets: specs + discovery inventory.
│  AC Generation   │  Compares what SHOULD exist vs what DOES.
│                  │  Classifies each feature:
│  2a: spec-based  │    FOUND / MISSING / PARTIAL / DRIFTED
│  2b: gap detect  │  Writes Playwright-testable acceptance
│                  │  criteria for each feature.
└────────┬─────────┘
         │ "What to test"
         ▼
┌──────────────────┐
│  PHASE 3         │  One agent per feature.
│  Playwright      │  Writes + executes Playwright tests
│  Validation      │  from acceptance criteria.
│                  │  PASS / FAIL / BLOCKED per criterion.
│  3b: gap tests   │  Screenshots on failure.
└────────┬─────────┘
         │ "What's broken"
         ▼
┌──────────────────┐
│  PHASE 4a        │  Objective catalog. No interpretation.
│  Failure Catalog │  What failed, what was expected, what
│                  │  actually happened, screenshot ref.
├──────────────────┤
│  PHASE 4b        │  Groups failures by root cause.
│  Root Cause      │  Identifies likely files. Prioritizes
│  Analysis        │  by impact (multi-feature > single).
└────────┬─────────┘
         │ "Why it's broken + where to fix"
         ▼┌──────────────────┐
│  PHASE 5         │  One agent per root cause.
│  Fix Agents      │  Fixes go through same build gates.
│                  │  Re-runs ONLY affected Playwright
│                  │  tests to verify the fix.
│                  │  Revert on failed re-validation.
└──────────────────┘
```

Full spec in [`WIP/post-campaign-validation.md`](WIP/post-campaign-validation.md).

---

## Context Persistence

Every Claude session starts blank. auto-sdd treats this as an engineering problem. The repo itself is the persistence layer — structured so a fresh Claude instance can boot to productive in one read pass.

```
  Claude Session (ephemeral)          Repository (persistent)
  ─────────────────────────           ──────────────────────

  ┌───────────────────────┐           ┌──────────────────────┐
  │  Fresh instance       │◀══════════│  CLAUDE.md           │
  │  (knows nothing)      │  auto-    │  (auto-read by CLI)  │
  │                       │  injected │  - project identity  │
  │                       │           │  - hard constraints  │
  │                       │           │  - core learnings    │
  └───────────┬───────────┘           └──────────────────────┘
              │
              │ reads                  ┌──────────────────────┐
              ├───────────────────────▶│  .onboarding-state   │
              │                        │  (JSON checkpoint)   │              │                        │  - prompt_count      │
              │                        │  - last_hash         │
              │                        │  - captures pending  │
              │                        └──────────────────────┘
              │
              │ reads                  ┌──────────────────────┐
              ├───────────────────────▶│  ACTIVE-             │
              │                        │  CONSIDERATIONS.md   │
              │                        │  - priority stack    │
              │                        │  - what's in flight  │
              │                        │  - what's blocked    │
              │                        └──────────────────────┘
              │
              │ reads on demand        ┌──────────────────────┐
              ├───────────────────────▶│  learnings/          │
              │                        │  ├─ core.md (13)     │
              │                        │  ├─ empirical.md     │
              │                        │  ├─ process-rules.md │
              │                        │  └─ ...              │
              │                        └──────────────────────┘
              │
              │ reads on demand        ┌──────────────────────┐
              └───────────────────────▶│  Agents.md           │
                                       │  (full work log)     │
                                       │  - every round       │
                                       │  - what changed      │
                                       │  - what broke        │
                                       └──────────────────────┘
```

**Two storage layers, different jobs:**

Claude.ai's memory system provides brief, keyword-level triggers (project name, communication preferences, what's active). The repo provides the detail: 226+ learnings entries in graph schema with typed relationships (SUPERSEDES, DERIVED_FROM, VALIDATED_BY), full architectural context, and the priority stack. Memory sets the tone; the repo provides the knowledge.

**The learnings system:** Each entry is self-contained — a fresh Claude instance can read one entry and understand it without context. Entries have a lifecycle: Observation → Demonstrated → Validated → Core (top 17, inlined into CLAUDE.md). At any point, entries can be REFUTED and archived with a reason. Signal scores (1-8+) track confidence based on how many independent sessions confirmed the pattern.

**The checkpoint protocol:** Saying "checkpoint" triggers a deterministic flush: scan for uncaptured learnings, write approved entries to `learnings/`, update `.onboarding-state`, update `ACTIVE-CONSIDERATIONS.md`, commit and push. Everything the session learned is persisted in structured form. The next session boots with that knowledge on first read.

The typical AI workflow is conversational — you teach the AI about your project, it helps, the conversation ends, you start over. auto-sdd inverts that. The repo teaches the AI. Sessions are interchangeable because the knowledge lives in the repo, not in any one conversation.

---

## Campaign Results

### SitDeck — CRE Property Analytics (active campaign)

A 49-feature commercial real estate analytics platform built from a single `vision.md` spec. Next.js 15 + DuckDB + Mapbox + Zustand. Three CSV data sources (leases, sales, properties from CompStak). Project isolated at `~/compstak-sitdeck/` with three-layer contamination protection.

| Metric | Result |
|---|---|
| Features built | **37+/49** (campaign in progress) |
| Features failed | **0** |
| Project tests | **599 passing** (37 vitest files) |
| Cost | **~$201** |
| Two-stage retry | Live-validated (Feature #19 succeeded on attempt 2) |
| Model | Claude Sonnet 4.6 |

This is the first campaign run against the Python build loop with project isolation enforcement (auto-sdd repo files protected from agent writes), two-stage retry (fix-in-place on attempt 1, informed fresh retry on attempt 2+), and codebase summary injection.

### CRE Lease Comp Tracker (validation run)

A clean-room test against a project the system had never seen. Full-stack app: React/Vite/Tailwind frontend, Express/SQLite backend, JWT auth.

| Metric | Result |
|---|---|
| Features built | **3/3** |
| Features failed | **0** |
| Total time | **31 minutes** |
| TypeScript | Compiles clean (client + server) |
| Runtime | Auth, filtering, pagination, CSV export all functional |

This validated the Python build loop against a fresh project with no stakd-specific assumptions.

### Stakd campaigns (28-feature comparison)

Two identical 28-feature campaigns against a React/TypeScript/Next.js codebase, one on Sonnet 4.6 and one on Haiku 4.5.

| Metric | Sonnet 4.6 | Haiku 4.5 |
|---|---|---|
| Features built | **28/28** | 11 (in progress) |
| Features failed | **0** | 0 |
| Build window | 6.8 hours | 2.9 hours* |
| **Throughput** | **4.0 features/hour** | **3.8 features/hour** |
| Median feature time | 9.2 min | 7.4 min |
| Cost per feature | $0.07 | $0.08 |
| Drift reconciliation | 75% | 73% |

*Haiku campaign in progress — metrics based on partial data

**Key finding: model inference speed is not the bottleneck.** Haiku generates tokens ~2x faster than Sonnet. Throughput is nearly identical. Wall time is dominated by npm install, TypeScript compilation, test execution — not LLM generation. Most teams building multi-agent systems would get this wrong.

Full campaign data and analysis in [`campaign-results/`](campaign-results/).

---

## Agent Reliability Findings

35+ rounds of development produced a taxonomy of how agents actually fail in production loops. These aren't edge cases — they're the dominant failure modes.

**Agents fabricate work.** Round 1: the agent produced a detailed description of bugs in code it never wrote. Zero files created. Reported success. This is why every validation step is mechanical — the shell trusts nothing the agent says about itself.

**Agents ignore explicit instructions.** Across Rounds 32-34, agents were told "do NOT push to origin" in multiple formulations. Push rate: 100%. Prompt wording made no difference.

**Self-assessment is uncorrelated with reality.** Every agent step is followed by a shell-side validation gate. The agent says "tests pass" — the shell runs the tests. The agent's narrative is discarded; only mechanical signals matter.

**78% build failure rate was not a code problem.** Root cause: API credit exhaustion, not context loss or bad prompts. The system was retrying doomed calls. Credit exhaustion detection now halts immediately.

The full failure catalog lives in [`learnings/`](learnings/), with highest-signal entries curated in [`learnings/core.md`](learnings/core.md). The round-by-round work log is in [`Agents.md`](Agents.md).

---

## Architecture

### Python build loop (primary)

The orchestrator is implemented in Python (`py/auto_sdd/`), with 1026 tests covering unit, integration, and dry-run scenarios. The dry-run integration tests exercise real git operations, real file I/O, and real state persistence with only the Claude CLI call mocked.

### Signal protocol

Agents communicate via grep-parseable signals. No JSON parsing. No eval on agent output.

```
FEATURE_BUILT: {name}                              # Build success
BUILD_FAILED: {reason}                             # Build failure
NO_DRIFT / DRIFT_FIXED / DRIFT_UNRESOLVABLE       # Drift check
REVIEW_CLEAN / REVIEW_FIXED / REVIEW_FAILED        # Code review
```

### Codebase summary injection

Each build agent receives a generated summary of existing components, type exports, and import graph. Cached on tree hash — regenerated only when the codebase changes. Prevents type redeclaration, import conflicts, and repeated mistakes across features within a campaign.

### Eval sidecar

A separate process polls for new commits during a campaign, runs mechanical evaluations (and optionally agent-based evaluations), and feeds findings back into subsequent build prompts via the repeated-mistakes feedback loop. Never blocks builds or modifies source files directly, but actively influences agent behavior — if feature 1's eval catches a pattern violation, feature 2's agent prompt includes that feedback.

Currently the sidecar produces per-feature scores and mistake flags. The planned next layer extracts structured learnings from eval outcomes across features, identifies cross-campaign patterns (which mistake types recur, which prompt adjustments actually reduce failure rates), and feeds those patterns back into both the sidecar's own evaluation criteria and the build loop's prompt construction. The system improves its own quality gates based on what it observes failing.

### Two-stage retry

When a feature fails post-build gates:

- **Attempt 1 (fix-in-place):** Code stays on disk. Agent gets the failure output and a targeted fix prompt. Diagnose and patch — don't rewrite.
- **Attempt 2+ (informed fresh retry):** `git reset --hard` to branch start. Agent gets a full build prompt plus a summary of all prior failures. Fresh start with knowledge of what went wrong.

This was live-validated on the SitDeck campaign (Feature #19 succeeded on attempt 2 via fix-in-place).

### Token estimation and calibration

Every agent prompt includes a Token Usage Report that records estimated vs actual token consumption to `general-estimates.jsonl`. A graduated blend (20% per data point, up to 100% at 5+ samples) calibrates future estimates against historical actuals. This feeds scope decisions — when to split prompts, when context budget is tight.

### Project isolation

Target projects live in separate directories (e.g., `~/compstak-sitdeck/`), not inside the auto-sdd repo. Three-layer protection prevents agents from contaminating the orchestrator:

1. **Filesystem boundary in prompts** — agents are told their working directory and forbidden from writing outside it
2. **Post-build contamination check** — `git diff` against auto-sdd repo root detects any agent writes outside expected patterns
3. **Protected directories/files** — `py/`, `scripts/`, `lib/`, `tests/`, `*.md`, `.gitignore` etc. trigger gate failure if modified

### Bash build loop (legacy)

The original bash implementation (`scripts/build-loop-local.sh`, `lib/reliability.sh`) remains in the repo. The Python version is the primary path for all new work.

---

## File Structure

```
auto-sdd/
├── py/                                # Python build loop (primary)
│   ├── auto_sdd/
│   │   ├── scripts/
│   │   │   ├── build_loop.py          # Main build loop orchestrator
│   │   │   ├── eval_sidecar.py        # Eval sidecar process
│   │   │   ├── overnight_autonomous.py
│   │   │   ├── nightly_review.py
│   │   │   └── generate_mapping.py
│   │   └── lib/
│   │       ├── reliability.py         # Locking, state, topo sort, signals
│   │       ├── branch_manager.py      # Branch setup, cleanup, strategies
│   │       ├── build_gates.py         # Post-build validation gates
│   │       ├── claude_wrapper.py      # Claude CLI wrapper + cost logging
│   │       ├── codebase_summary.py    # Cross-feature context generation
│   │       ├── prompt_builder.py      # Agent prompt construction
│   │       ├── drift.py               # Drift detection
│   │       ├── eval_lib.py            # Eval functions
│   │       └── general_estimates.py   # Token estimation calibration
│   └── tests/                         # 1026 tests
│       ├── test_build_loop.py
│       ├── test_dry_run.py            # Integration tests (real git, mocked agent)
│       ├── test_reliability.py
│       ├── test_eval_sidecar.py
│       └── ...
│
├── scripts/                           # Bash build loop (legacy)
│   ├── build-loop-local.sh
│   └── eval-sidecar.sh
├── lib/                               # Bash shared libraries (legacy)
│   ├── reliability.sh
│   ├── claude-wrapper.sh
│   └── general-estimates.sh           # Token estimation (bash)
│
├── learnings/                         # Knowledge graph (flat files, graph schema)
│   ├── core.md                        # 17 highest-signal entries
│   ├── failure-patterns.md
│   ├── process-rules.md
│   ├── empirical-findings.md
│   ├── domain-knowledge.md
│   └── architectural-rationale.md
│
├── campaign-results/                  # Campaign data and analysis
│   ├── raw/v2-sonnet/
│   ├── raw/v3-haiku/
│   └── reports/
│
├── WIP/
│   └── post-campaign-validation.md    # Auto-QA spec (v0.3)
│
├── .specs/                            # Spec templates
│   ├── vision.md
│   ├── roadmap.md
│   └── features/
│
├── Brians-Notes/
│   └── PROMPT-ENGINEERING-GUIDE.md
│
├── CLAUDE.md                          # Auto-read by Claude Code agents
├── ONBOARDING.md                      # Boot protocol for new sessions
├── ACTIVE-CONSIDERATIONS.md           # Priority stack
├── DECISIONS.md                       # Append-only decision log
├── DESIGN-PRINCIPLES.md               # Architectural principles
├── Agents.md                          # Round-by-round work log
├── general-estimates.jsonl            # Token calibration data
└── VERSION                            # 2.0.0
```

---

## Quick Start

```bash
git clone https://github.com/fischmanb/auto-sdd.git
cd auto-sdd

# Verify tests pass
py/.venv/bin/python -m pytest py/tests/ -q

# Point it at a project
# Your project needs: .specs/roadmap.md, .specs/vision.md, CLAUDE.md

# Build
cd ~/auto-sdd && \
PROJECT_DIR=/path/to/your-project \
MAX_FEATURES=3 \
BRANCH_STRATEGY=sequential \
py/.venv/bin/python -m auto_sdd.scripts.build_loop

# With build checks
BUILD_CHECK_CMD="cd client && npx tsc --noEmit" \
TEST_CHECK_CMD="npm test" \
py/.venv/bin/python -m auto_sdd.scripts.build_loop

# Resume after crash
ENABLE_RESUME=true py/.venv/bin/python -m auto_sdd.scripts.build_loop
```

---

## Configuration

Key environment variables:

```bash
# Required
PROJECT_DIR=/path/to/project       # Target project

# Build validation
BUILD_CHECK_CMD=""                  # Auto-detected or explicit
TEST_CHECK_CMD=""                   # Auto-detected or explicit
DRIFT_CHECK=true                    # Spec-to-implementation drift detection

# Model selection (each step gets a fresh context window)
AGENT_MODEL=""                      # Build agent (default: system default)
DRIFT_MODEL=""                      # Drift detection
REVIEW_MODEL=""                     # Code review

# Orchestration
MAX_FEATURES=4                      # Features per run
MAX_RETRIES=2                       # Retries per feature on failure
BRANCH_STRATEGY=sequential          # sequential | chained | independent | both
ENABLE_RESUME=true                  # Resume from last successful feature
AGENT_TIMEOUT=1800                  # Per-agent timeout in seconds

# Eval sidecar
EVAL_SIDECAR=false                  # Run evals alongside builds

# Logging
LOGS_DIR=~/logs/{project}           # Build summaries and logs
```

---

## Requirements

- Python 3.11+
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code): `npm install -g @anthropic-ai/claude-code`
- Active Claude authentication (`claude login`)

---

## Credits

Original concept by [Adrian Rogowski](https://github.com/AdrianRogowski/auto-sdd). This fork rebuilt the runtime over 35+ rounds, adding the reliability layer, test suite (1026), eval system, campaign infrastructure, Python orchestrator, knowledge persistence architecture, two-stage retry (fix-in-place → informed fresh retry), project isolation enforcement, and auto-QA pipeline.

## License

MIT
