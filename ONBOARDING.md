# ONBOARDING.md

> **Read this file first.** It gives a fresh Claude instance everything needed to pick up work on `auto-sdd` with Brian.
>
> Last updated: 2026-02-25

---

## What This Project Is

**auto-sdd** is a spec-driven development system that orchestrates autonomous Claude Code agents to build features from Gherkin specs. You write a roadmap of features. The loop picks the next one, hands it to a fresh Claude Code agent, validates the output (compile, test, drift check), commits, and moves on.

Forked from [AdrianRogowski/auto-sdd](https://github.com/AdrianRogowski/auto-sdd). Brian rewrote the runtime — adding reliability, crash recovery, test suites, cost tracking, and Claude Code CLI support. The original was a concept; this is the hardened version.

**Repo**: `https://github.com/fischmanb/auto-sdd`
**Local path**: `~/auto-sdd`
**Version**: 2.0.0
**License**: MIT

---

## Current State (as of 2026-02-25)

### What works

- **Build loop runs end-to-end.** Validated Feb 22, 2026: 2 features built autonomously against a React+TS+Vite app. 19 tests passing, TypeScript clean, drift auto-reconciled.
- **Reliability layer**: locking, exponential backoff, context truncation, cycle detection, crash recovery with `--resume`.
- **Test suite**: 57 unit assertions (`test-reliability.sh`), 10 validation assertions (`test-validation.sh`), structural dry-run.
- **Cost tracking**: `lib/claude-wrapper.sh` logs token/cost data as JSONL.
- **Build summary reports**: per-feature timing, test counts, token usage, written to `logs/build-summary-{timestamp}.json`.
- **Git stash hardening**: dirty worktree can't cascade failures across features.
- **Credit exhaustion detection**: loop halts immediately when API credits run out instead of retrying doomed calls.

### What's next

1. **Topological sort + pre-flight summary** — shell-side Kahn's algorithm for feature ordering, pre-flight confirmation before build start
2. **Codebase summary injection** — generate summary after each commit, pass to next agent. Fixes cross-feature type/interface drift.
3. **Local model integration** — replace cloud API with local LM Studio on Mac Studio
4. **stakd/ build campaign + issue triage** — full 28-feature test run, then triage last run's issues
5. **Adaptive routing / parallelism** — only if data from 1-3 shows remaining sequential bottleneck justifies the complexity

### Known gaps

- No live integration testing — all validation is `bash -n` + unit tests + structural dry-run
- `run_parallel_drift_checks` defined but not wired into independent build pass
- Backend spec layer missing — no Gherkin equivalent for DB schemas, API contracts, migrations
- Agent self-assessment is unreliable (documented extensively in Agents.md)

---

## Active Considerations

> What's next and what's in-flight. Priority stack is the execution plan; everything below it is context a fresh chat should pick up.

### Priority stack (updated 2026-02-25)

Ordered by efficiency gain per complexity added:

1. **Topological sort + pre-flight summary** — Use the existing `check_circular_deps` dependency graph parser to emit optimal feature order via Kahn's algorithm (shell-side, not agent-side). Independent features first, then dependents. Gets 80% of adaptive routing's benefit with near-zero complexity. Pre-flight prints sorted feature list with t-shirt sizes and total count, requires user confirmation before build starts (`AUTO_APPROVE=true` skips for overnight). Design decided; implementation via dedicated Claude Code agent. *Not started.*
2. **Codebase summary injection** — Generate summary after each commit, pass to next agent. Fixes cross-feature type/interface drift. Each build agent currently has no knowledge of what previous agents produced, causing type redeclarations and interface drift. High quality gain, moderate speed gain (fewer retries), low complexity. *Not started.*
3. **Local model integration** — Replace cloud API calls with local LM Studio endpoints on Mac Studio. The archived `archive/local-llm-pipeline/` system is reference material. *Not started.*
4. **stakd/ build campaign + issue triage** — Full 28-feature end-to-end run against the Traded.co clone (3 phases). Benefits from codebase summary being in place first. After topo sort, triage issues from last stakd build run. *Not started.*
5. **Adaptive routing / parallelism** — Only if data from 1–3 shows remaining sequential bottleneck justifies the complexity. Investigated in Round 14 (results lost to compaction), re-analyzed in Round 16. Full edge case analysis done: diamond deps, merge conflicts at convergence, complex resume state, drift check ordering, resource contention, partial parallel failure. Conclusion: ~400-500 new lines and new failure classes don't justify savings until simpler levers are exhausted. *Deprioritized.*

### Historical build estimator (designed, not yet built)

After at least one full campaign, a function will correlate t-shirt sizes from roadmap with actual metrics from `logs/build-summary-*.json` and write aggregate stats to `logs/estimation-model.json` (avg seconds, avg tokens, sample count, success rate per t-shirt size). Pre-flight then uses this to project total run cost/time. Self-correcting — updates running averages after each `write_build_summary()`. `MAX_FEATURES` becomes an optional backstop once estimator provides informed consent via real projections. Build after stakd campaign provides real data.

### Other active items

- **Onboarding state protocol**: Implemented 2026-02-25. Mechanical enforcement via `~/auto-sdd/.onboarding-state` file — tracks prompt count, buffers pending captures, triggers interval checks. Memory instruction points all future chats to the protocol. See "Keeping This File Current" section.

---

## Key Files — What to Read and When

| File | What it contains | When to read |
|------|-----------------|--------------|
| **ONBOARDING.md** (this file) | Full project context for a fresh chat | Always read first |
| **Agents.md** | Agent work log (Rounds 1-15), architecture reference, signal protocol, verification checklist, known gaps, process lessons | Before making ANY changes — this is the source of truth for what happened and what works |
| **README.md** | Public-facing docs: quick start, config, file structure, what works and what breaks | For understanding the user-facing narrative |
| **CLAUDE.md** | Instructions that Claude Code agents read automatically when invoked by the build loop | When modifying agent behavior or build prompts |
| **ARCHITECTURE.md** | Design decisions for the local LLM pipeline (system 2, archived) and context management philosophy | When working on the local model integration |
| **Brians-Notes/PROMPT-ENGINEERING-GUIDE.md** | Methodology for writing hardened agent prompts, full failure catalog from real sessions | On first prompt of any new chat or agent session (read the "Lessons Learned (Failure Catalog)" section only), and before writing any new agent prompts |
| **lib/reliability.sh** | Shared runtime: lock, backoff, state, truncation, cycle detection (~385 lines) | When debugging build failures or modifying shared behavior |
| **lib/claude-wrapper.sh** | Wraps `claude` CLI, extracts text to stdout, logs cost data to JSONL | When debugging cost tracking or agent invocation |
| **scripts/build-loop-local.sh** | Main orchestration script (~1311 lines) | When modifying the build loop |
| **scripts/overnight-autonomous.sh** | Overnight automation variant (~790 lines) | When modifying overnight runs |
| **.env.local.example** | Full config reference (167 lines) | When setting up or changing config |

---

## Architecture in 60 Seconds

Two systems live in this repo:

**System 1 — Orchestration (active)**: `scripts/build-loop-local.sh` and `overnight-autonomous.sh` call Claude Code agents with a fresh context per feature. Each feature goes through: BUILD → COMPILE CHECK → TESTS → DRIFT CHECK → COMMIT. The shell validates between every agent step — no trust in self-assessment.

**System 2 — Local LLM pipeline (archived)**: Multi-stage pipeline (plan → build → review → fix) for locally-hosted models. Archived to `archive/local-llm-pipeline/`. Preserved for future LM Studio integration.

`lib/reliability.sh` serves System 1 only.

### Signal protocol

Agents communicate via grep-parseable signals — no JSON parsing, no eval on agent output:

```
FEATURE_BUILT: {name}          # Build agent success
SPEC_FILE: {path}              # Where the spec lives
SOURCE_FILES: {paths}          # What was produced
BUILD_FAILED: {reason}         # Build agent failure
NO_DRIFT / DRIFT_FIXED / DRIFT_UNRESOLVABLE   # Drift agent
REVIEW_CLEAN / REVIEW_FIXED / REVIEW_FAILED    # Review agent
```

### Branch strategies

- **chained**: each feature branches from previous (default for local)
- **independent**: all branch from base (for parallel comparison)
- **both**: runs chained then independent
- **sequential**: no branching, commit to current branch

---

## How to Verify Everything Works

```bash
cd ~/auto-sdd

# Syntax check all scripts
bash -n scripts/build-loop-local.sh
bash -n scripts/overnight-autonomous.sh
bash -n lib/reliability.sh
bash -n lib/validation.sh

# Unit tests
./tests/test-reliability.sh        # 57 assertions
./tests/test-validation.sh         # 10 assertions

# Structural dry-run (no agent/API needed)
DRY_RUN_SKIP_AGENT=true ./tests/dry-run.sh

# Full dry-run (requires claude CLI + ANTHROPIC_API_KEY)
./tests/dry-run.sh
```

---

## Agent Work Log Summary (Rounds 1-15)

Full details in `Agents.md`. Here's the arc:

| Round | What | Outcome |
|-------|------|---------|
| 1 | Initial reliability features | **Failed** — agent claimed implementation, wrote nothing |
| 2 | Review + fix Round 1 | Implemented features but left functions unwired |
| 3 | Extract lib + tests + hardening | **Major milestone** — `lib/reliability.sh`, 57-assertion test suite, dry-run |
| 4 | Cursor → Claude Code CLI swap | Clean swap, 57/57 tests pass |
| 5 | Fix broken grep comment-filter | Targeted fix, 57/57 tests pass |
| 6 | Fix `local` outside functions + MAX_FEATURES env key | 7 bare locals fixed, env fallback chain added |
| 7 | **End-to-end smoke test** | **Success** — 2 features built autonomously, 19 tests, drift reconciled |
| 8 | Fix agent permissions | `--dangerously-skip-permissions` + settings.local.json |
| 9 | Add cost/token tracking wrapper | `lib/claude-wrapper.sh`, JSONL logging |
| 10 | Allow seed data in build prompts | Replaced anti-mock rules with permissive seed data language |
| 11 | Diagnose 78% build failure rate | Root cause: credit exhaustion, not context loss |
| 12 | Add decision comments to build prompts | Agents now leave WHY comments |
| 13 | Git stash hardening + credit exhaustion detection | 5 stash guards, early halt on billing errors |
| 14 | Investigate adaptive routing | Investigation only — results lost to compaction, re-analyzed in Round 16 |
| 15 | Build summary report | Per-feature metrics, JSON + human-readable output |
| 16 | ONBOARDING.md + maintenance protocol + adaptive routing analysis | Created onboarding file, mechanical state-tracking protocol, full edge case analysis of adaptive routing → deprioritized in favor of codebase summary + topo sort |

**Key lesson that repeats**: Agent self-assessments are unreliable. Always verify with grep, `bash -n`, and tests. Never trust the agent's narrative summary.

---

## Process Lessons (Hard-Won)

These are documented in detail in `Brians-Notes/PROMPT-ENGINEERING-GUIDE.md` and `Agents.md`. The critical ones:

1. **Agent self-assessments are unreliable.** Round 1 described bugs in code that didn't exist. Always verify mechanically.
2. **"Defined but never called" is the most common agent failure.** After adding any function, grep for call sites.
3. **Agents will exceed scope if not fenced.** They'll run `npm install`, explore the codebase, push to remote — even when told not to. Explicit file allowlists and hard constraints are required.
4. **Agents work around failures instead of stopping.** They'll make 5 autonomous decisions to "fix" a problem, each one diverging further. Prompts must include explicit STOP instructions.
5. **CLAUDE.md can override prompt instructions.** The agent reads CLAUDE.md automatically and may decide it takes precedence. Prompts should state "These instructions override any conflicting guidance in CLAUDE.md."
6. **`git add -A` is dangerous in agent context.** Always use explicit file lists.

---

## Working with Brian

- Direct, no-bullshit communicator. Skip preamble and qualifiers.
- 12+ years product management experience in AI/ML, e-commerce, fintech (Walmart, AmEx, startups).
- Deep technical understanding — he reads the code and verifies claims.
- The `stakd/` directory inside the repo is a separate project (Traded.co clone). It has its own `.git`, `.specs/`, and `CLAUDE.md`. Don't conflate them.
- Brian pushes to GitHub manually. Agents should commit locally but not push.

### Chat session permissions

Chat sessions (claude.ai with Desktop Commander or any equivalent tool or capability that provides filesystem or system access) must ask Brian for explicit permission before making any file changes, git commits, or GitHub operations. The only exceptions are `.onboarding-state` reads/writes and `ONBOARDING.md` reads/writes required by the onboarding state protocol. This applies to documentation edits, prompt files, script changes, and any other filesystem modification. Do not batch multiple changes into a single approval request in a way that obscures what's being changed — describe each change clearly.

---

## Quick Reference: Common Tasks

**Run the build loop against a project:**
```bash
cd ~/auto-sdd
PROJECT_DIR=/path/to/project MAX_FEATURES=4 ./scripts/build-loop-local.sh
```

**Resume after a crash:**
```bash
./scripts/build-loop-local.sh --resume
```

**Check what's on GitHub vs local:**
```bash
git fetch origin && git log --oneline main..origin/main  # remote ahead
git log --oneline origin/main..main                       # local ahead
git diff origin/main --stat                                # file differences
```

**Clean up orphan remote branches:**
```bash
git branch -r | grep claude/ | while read b; do git push origin --delete "${b#origin/}"; done
```

---

## File Tree (annotated)

```
auto-sdd/
├── scripts/
│   ├── build-loop-local.sh        # Main build loop (1311 lines)
│   ├── overnight-autonomous.sh    # Overnight variant (790 lines)
│   ├── nightly-review.sh          # Extract learnings from commits
│   ├── generate-mapping.sh        # Auto-generate .specs/mapping.md
│   ├── setup-overnight.sh         # Install macOS launchd jobs
│   └── uninstall-overnight.sh     # Remove launchd jobs
├── lib/
│   ├── reliability.sh             # Shared runtime (385 lines)
│   ├── claude-wrapper.sh          # Claude CLI wrapper + cost logging
│   └── validation.sh              # YAML frontmatter validation
├── tests/
│   ├── test-reliability.sh        # 57 unit assertions
│   ├── test-validation.sh         # 10 unit assertions
│   ├── dry-run.sh                 # Structural integration test
│   └── fixtures/dry-run/          # Test fixtures
├── .specs/                        # Spec-driven development specs (templates)
├── .claude/commands/              # Claude Code slash commands
├── archive/local-llm-pipeline/    # Archived local LLM system
├── Brians-Notes/
│   └── PROMPT-ENGINEERING-GUIDE.md  # Prompt methodology + failure catalog
├── ONBOARDING.md                  # ← YOU ARE HERE
├── CLAUDE.md                      # Agent instructions (read by Claude Code automatically)
├── Agents.md                      # Agent work log + architecture + verification checklist
├── README.md                      # Public-facing documentation
├── ARCHITECTURE.md                # Design decisions (local LLM pipeline)
├── VERSION                        # 2.0.0
├── .onboarding-state              # State tracking for update protocol (local only, gitignored)
└── .env.local.example             # Full config reference
```

---

## Keeping This File Current

This file is useless if it's stale. Context loss — compaction, crashes, new chats — happens without warning. The update protocol is designed around that reality and enforced mechanically.

### Reconciliation after agent rounds

When a Claude Code agent completes a round and updates Agents.md, the chat session that triggered or reviewed that round is responsible for reconciling ONBOARDING.md before the session ends. This is a process rule, not a mechanical check — the chat is already reading Agents.md to verify the agent's work, so the marginal cost is near zero. Without this, Agents.md can drift from ONBOARDING.md silently: the hash stays clean, the interval check passes, and the next fresh chat onboards with stale context.

### Enforcement mechanism: `.onboarding-state`

A JSON state file at `~/auto-sdd/.onboarding-state` tracks update status:

```json
{
  "last_check_ts": "<ISO timestamp of last reconciliation>",
  "last_check_hash": "<md5 of ONBOARDING.md at last full read>",
  "prompt_count": 0,
  "pending_captures": ["item 1", "item 2"]
}
```

**Every project-related response** (silent, no meta-commentary):
1. Read `.onboarding-state`, increment `prompt_count`
2. If the current exchange has something that might need capturing, append a one-liner to `pending_captures`, flag inline with 📌, and **write the state file immediately in the same response** (not deferred to next response — protects against context compaction)
3. Write state file back

**At interval (prompt_count >= 4)**:
1. Hash ONBOARDING.md, compare to `last_check_hash`
2. If hash matches AND `pending_captures` is empty → reset counter, done
3. If hash differs → another agent or Brian edited the file. Read only the **Active Considerations** section (grep for section boundaries, ~15 lines). Note what changed.
4. If `pending_captures` is non-empty → read only **Active Considerations**, reconcile the buffer into it, flush `pending_captures`, update hash
5. Reset counter

**Privacy check on every read**: When reading any portion of ONBOARDING.md (interval or fresh onboard), if anything private, non-project-related, or sensitive (personal details, credentials, API keys, account info) is detected, immediately report all findings to Brian concisely. Do not silently correct — surface it.

**Fresh onboard (state file missing or `last_check_ts` > 24h stale)**:
- Full read of ONBOARDING.md. This is the only case where the whole file gets read.
- Read the "Lessons Learned (Failure Catalog)" section of `Brians-Notes/PROMPT-ENGINEERING-GUIDE.md`. These hard-won failure modes repeat if not internalized at session start. Do not read the full guide — only the failure catalog.

**Cost profile**: 95% of responses = read/write a 5-line file (negligible). Every ~4th response = one md5 + maybe 15 lines (minimal). New chat after a break = full read (appropriate).

### Two triggers

**1. Significance trigger (immediate):** If there is even a question of whether the current exchange could matter to the next chat, append to `pending_captures` and flag with 📌. Don't deliberate. The cost of a false positive is near zero.

This includes:
- Decisions and actions (new files, resolved gaps, changed priorities)
- **Topics under active consideration** — directions being weighed, open questions, things Brian raised that haven't resolved yet
- New process lessons or failure modes observed
- Anything Brian says that reframes the project or its priorities

**2. Interval trigger (every 3-5 prompts):** The mechanical check described above. Catches slow drift where no single message feels significant but several in a row shift the picture.

### What to capture

Not just outcomes. The **Active Considerations** section exists specifically for in-progress thinking. A fresh chat that knows what was being discussed is 10x more useful than one that only knows what was decided.

### How to update

1. Edit this file
2. `git add ONBOARDING.md && git commit -m "docs: update ONBOARDING.md — <what changed>"`
3. Ask Brian before pushing

### How to verify it's working

```bash
# Check update frequency — should show commits every few sessions
git log --oneline ONBOARDING.md

# Check state file — prompt_count should increment, pending_captures should flush periodically
cat ~/auto-sdd/.onboarding-state

# Spot check — ask a fresh chat "what are the active considerations for auto-sdd?"
# If the answer is stale, the protocol failed.
```

### Scope

This protocol is maintained **exclusively through chat sessions** (claude.ai with Desktop Commander). Claude Code build-loop agents must not read, write, or update `.onboarding-state` or ONBOARDING.md. See CLAUDE.md for the agent-facing rule.

### What NOT to put here

- Implementation details that belong in `Agents.md` (per-round specifics, line-level changes)
- Prompt methodology that belongs in `Brians-Notes/PROMPT-ENGINEERING-GUIDE.md`
- Agent instructions that belong in `CLAUDE.md`

This file is the **orientation layer**. It tells you what exists and where to find it, what's active, and what's being considered. The other files contain the depth.

---

_To pick up work: read this file, then read `Agents.md` for current state and verification checklist. Everything else is reachable from those two files._
