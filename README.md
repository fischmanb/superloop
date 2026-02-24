# auto-sdd

> Spec-driven development with autonomous Claude Code agents — hardened for production use.

Forked from [AdrianRogowski/auto-sdd](https://github.com/AdrianRogowski/auto-sdd).
The original introduced a compelling concept: Gherkin specs driving AI agents through a feature build loop. This fork completes the runtime — adding the reliability layer, test suite, crash recovery, and Claude Code CLI support needed to run it against real projects.

---

## What it does

You write a feature roadmap. The loop picks the next pending feature, hands it to a Claude Code agent with a fresh context, validates the output, commits the result, and moves on. Repeat until the roadmap is done.

Each agent invocation is isolated. No context rot. No shared state between features except what you explicitly define in the spec.

**Validated end-to-end**: the loop produced a working React + TypeScript + Vite app — WeekView calendar component (12 passing tests) and ClientSwitcher coach panel (7 passing tests) — TypeScript clean, running at localhost:5173.

---

## What this fork adds

The upstream project provided the orchestration concept and slash commands. Production use required a second pass:

| Area | Upstream | This fork |
|------|----------|-----------|
| CLI support | Cursor (`agent`) | Claude Code (`claude`) — `--force` removed, all `command -v` checks updated |
| Reliability | None | `lib/reliability.sh` — locking, exponential backoff, context truncation, cycle detection |
| Crash recovery | None | `--resume` flag; JSON state persisted in `.sdd-state/` across interruptions |
| Test suite | None | 64 assertions across unit tests, validation tests, and structural dry-run |
| Bug fixes | — | 7 bare `local` statements outside functions; broken comment-line grep filter; `MAX_FEATURES_PER_RUN` env key silently ignored |
| Documentation | README | `Agents.md` — agent work log with verified outcomes vs claimed outcomes; `ARCHITECTURE.md`; `Brians-Notes/` |

The reliability library is ~385 lines handling the failure modes that matter in overnight runs: stale locks, rate limit backoff, context budget enforcement, dependency cycles in the roadmap, and state recovery after a crash.

---

## Architecture

### Two systems in one repo

**System 1 — Orchestration** (actively developed):
`scripts/build-loop-local.sh` and `scripts/overnight-autonomous.sh` call Claude Code agents with a fresh context per feature. `lib/reliability.sh` is the shared runtime for both.

**System 2 — Local LLM pipeline** (original prototype):
`stages/`, `framework/ai-dev`, `lib/common.sh`, `lib/models.sh`. Multi-stage pipeline (plan → build → review → fix) designed for locally-hosted models. Not currently wired into the main orchestration scripts.

### Build validation pipeline

Every feature goes through this before a commit is made:

```
┌──────────┐  ┌─────────────┐  ┌───────────┐  ┌─────────────┐  ┌──────────┐
│  BUILD   │─▶│ BUILD CHECK │─▶│   TESTS   │─▶│ DRIFT CHECK │─▶│  COMMIT  │
│ (agent)  │  │  (compile)  │  │ (npm test)│  │   (agent)   │  │          │
└──────────┘  └─────────────┘  └───────────┘  └─────────────┘  └──────────┘
     │              │                │               │
     └── retry ◄────┴── retry ◄──────┘               │
                                                      ▼
                                           build + tests re-run
```

Each agent step runs in a fresh context window. The shell re-runs build and tests as a hard gate after every agent step — no additional tokens, no trust in self-assessment.

### Signal protocol

Build agents must emit one of:
```
FEATURE_BUILT: {feature name}
SPEC_FILE: {path to .feature.md}
SOURCE_FILES: {comma-separated source paths}
```
or `NO_FEATURES_READY` | `BUILD_FAILED: {reason}`

Drift and review agents have their own signal contracts. The orchestrator parses these with grep — no JSON parsing, no eval on agent output.

---

## File structure

```
auto-sdd/
├── scripts/
│   ├── build-loop-local.sh        # Main build loop — features from roadmap (1311 lines)
│   ├── overnight-autonomous.sh    # Overnight automation with Slack/Jira (790 lines)
│   ├── generate-mapping.sh        # Auto-generate .specs/mapping.md from frontmatter
│   ├── nightly-review.sh          # Extract learnings from today's commits
│   ├── setup-overnight.sh         # Install launchd scheduled jobs (macOS)
│   └── uninstall-overnight.sh     # Remove launchd jobs
│
├── lib/
│   ├── reliability.sh             # Shared runtime: locking, backoff, state, truncation,
│   │                              #   cycle detection, file counting (385 lines)
│   ├── validation.sh              # YAML frontmatter validation for generate-mapping.sh
│   ├── common.sh                  # HTTP/parsing helpers (system 2, not sourced by main scripts)
│   └── models.sh                  # Model endpoint management (system 2, not sourced by main scripts)
│
├── stages/                        # Multi-invocation local LLM pipeline (system 2)
│   ├── 01-plan.sh                 # Spec → plan.json
│   ├── 02-build.sh                # plan.json → source files
│   ├── 03-review.sh               # files → review.json
│   └── 04-fix.sh                  # review.json → fixed files
│
├── framework/
│   └── ai-dev                     # CLI entry point for stages/ pipeline
│
├── tests/
│   ├── test-reliability.sh        # Unit tests for lib/reliability.sh (54 assertions)
│   ├── test-validation.sh         # Unit tests for lib/validation.sh (10 assertions)
│   ├── dry-run.sh                 # Structural integration test (no agent needed)
│   └── fixtures/dry-run/          # Test fixtures: roadmap.md, vision.md
│
├── .claude/commands/              # Claude Code slash commands
├── .cursor/                       # Cursor rules, commands, hooks
│
├── .specs/
│   ├── vision.md                  # App vision
│   ├── roadmap.md                 # Feature roadmap (single source of truth)
│   ├── features/                  # Feature specs (.feature.md files)
│   ├── learnings/                 # Cross-cutting patterns by category
│   └── mapping.md                 # Auto-generated routing table
│
├── Brians-Notes/
│   ├── SETUP.md                   # Mac Studio setup guide
│   └── HANDOFF-PROMPT.md          # Prompt templates for agent sessions
│
├── CLAUDE.md                      # Agent instructions (universal)
├── Agents.md                      # Agent work log — what was asked vs what happened
├── ARCHITECTURE.md                # Design decisions for stages/ pipeline
├── .env.local.example             # Full config reference (167 lines)
├── VERSION                        # Framework version (semver)
└── .gitignore                     # Excludes .sdd-state/, .build-worktrees/, logs/
```

---

## Requirements

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code): `npm install -g @anthropic-ai/claude-code`
- `ANTHROPIC_API_KEY` in your shell environment
- `yq`: `brew install yq`
- bash 5+: `brew install bash` on macOS
- `gh` (GitHub CLI) for PR creation: `brew install gh`

For overnight automation: macOS (launchd scheduling)

---

## Quick start

```bash
# Copy framework into your project
git clone https://github.com/fischmanb/auto-sdd.git
cd your-project
cp -r auto-sdd/.claude auto-sdd/.specs auto-sdd/scripts \
       auto-sdd/lib auto-sdd/CLAUDE.md auto-sdd/Agents.md .

# Configure
cp .env.local.example .env.local
# Edit .env.local — set TEST_CHECK_CMD, BUILD_CHECK_CMD, model preferences

# Verify the test suite passes
./tests/test-reliability.sh        # 54 assertions
./tests/test-validation.sh         # 10 assertions
DRY_RUN_SKIP_AGENT=true ./tests/dry-run.sh

# Define your app
/vision "A task management app for small teams with projects and due dates"
/roadmap create

# Build
./scripts/build-loop-local.sh
```

---

## Configuration

Key `.env.local` settings:

```bash
# Build validation
BUILD_CHECK_CMD=""          # Auto-detected (tsc, cargo check, etc.)
TEST_CHECK_CMD=""           # Auto-detected (npm test, pytest, etc.)
POST_BUILD_STEPS="test"     # Comma-separated: test, code-review
DRIFT_CHECK=true

# Model selection (each step gets a fresh context window)
AGENT_MODEL=""              # Default for all steps
BUILD_MODEL=""              # Main build agent
DRIFT_MODEL=""              # Drift detection agent
REVIEW_MODEL=""             # Code review agent

# Roadmap
MAX_FEATURES=4              # Features per run (also reads MAX_FEATURES_PER_RUN)
BASE_BRANCH=""              # Unset = current branch; "main" = overnight default

# Branch strategy
BRANCH_STRATEGY=chained     # chained | independent | both | sequential

# Resume after crash
# Run with --resume flag to pick up from last known state
```

---

## Slash commands

| Command | Purpose |
|---------|---------|
| `/spec-first <feature>` | Create feature spec with Gherkin + ASCII mockup |
| `/spec-first --full` | Create spec and build without pauses |
| `/vision` | Create or update vision.md |
| `/roadmap create` | Build roadmap from vision.md |
| `/roadmap add "feature"` | Add feature to existing roadmap |
| `/roadmap status` | Progress report |
| `/build-next` | Build next pending feature |
| `/compound` | Extract learnings from current session |
| `/catch-drift` | Detect spec ↔ code misalignment |
| `/clone-app <url>` | Analyze existing app → vision + roadmap |

---

## What vibe coding actually looks like at the seams

The loop works. It also fails in reproducible ways. Documenting both is the engineering.

**What holds up well**: isolated frontend features built from tight Gherkin specs. The agent produces solid scaffolding with tests. TypeScript compiles. The test suite catches the obvious gaps before commit.

**Where it breaks down**:

1. **Integration across features** — each agent builds without knowledge of what previous agents produced. Types get redefined. Component interfaces drift. A codebase summary passed to each agent would fix most of this; it's the next logical addition.

2. **Backend spec layer** — the framework is frontend-oriented. Database schemas, API contracts, and migrations have no equivalent spec format. The orchestrator can't validate what it can't parse.

3. **Agent self-assessment is unreliable** — Round 1 in the agent work log produced zero code while writing a detailed description of bugs in code it never wrote. The reliability layer exists partly because of this. Always verify with grep and tests, never with the agent's summary.

The productivity gain is real. So is the ceiling. Both are documented in `Agents.md`.

---

## Testing

```bash
# Unit tests — lib/reliability.sh
./tests/test-reliability.sh        # 54 assertions, all passing

# Unit tests — lib/validation.sh
./tests/test-validation.sh         # 10 assertions, all passing

# Structural integration test (no agent required)
DRY_RUN_SKIP_AGENT=true ./tests/dry-run.sh

# Full integration test (requires Claude Code + ANTHROPIC_API_KEY)
./tests/dry-run.sh
```

Verification after any change:

```bash
bash -n scripts/build-loop-local.sh
bash -n scripts/overnight-autonomous.sh
bash -n lib/reliability.sh
./tests/test-reliability.sh
DRY_RUN_SKIP_AGENT=true ./tests/dry-run.sh
```

---

## Credits

Original concept by [Adrian Rogowski](https://github.com/AdrianRogowski/auto-sdd), inspired by [Ryan Carson's Compound Engineering](https://x.com/ryancarson) approach.

## License

MIT
