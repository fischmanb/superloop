# INDEX.md

> One-line lookup table for the repo. "Where is X?" starts here.

## Documents

| File | What |
|------|------|
| ONBOARDING.md | Full project context for fresh sessions — read first |
| ACTIVE-CONSIDERATIONS.md | Priority stack, in-flight work, open questions |
| INDEX.md | This file — one-line lookup table |
| DESIGN-PRINCIPLES.md | Grepability, graph-readiness, relationship schema, enums |
| Agents.md | Agent work log (Rounds 1-37), architecture, signal protocol, verification checklist |
| CLAUDE.md | Instructions read automatically by Claude Code agents |
| README.md | Public-facing docs, quick start, config |
| ARCHITECTURE.md | Local LLM pipeline design (archived system 2) |
| DECISIONS.md | Append-only decision log with rationale |
| VERSION | Semantic version (2.0.0) |

## Directories

| Path | What |
|------|------|
| scripts/ | Build loop, overnight runner, eval sidecar, setup scripts |
| lib/ | Shared libraries: reliability, codebase-summary, eval, claude-wrapper, validation |
| tests/ | Test suites (154 assertions) + dry-run + fixtures |
| learnings/ | Typed learning catalog: core, failure-patterns, process-rules, empirical-findings, architectural-rationale, domain-knowledge |
| .specs/ | Spec-driven development templates + deprecated agent-operations.md |
| .claude/commands/ | Claude Code slash commands (includes `/checkpoint` for context management) |
| Brians-Notes/ | PROMPT-ENGINEERING-GUIDE.md |
| WIP/ | In-progress specs (post-campaign-validation.md) |
| archive/local-llm-pipeline/ | Archived local LLM system (system 2) |
| campaign-results/ | Raw data + reports from build campaigns (v2-sonnet, v3-haiku) |
| stakd/ | Separate project (Traded.co clone) — own .git, .specs, CLAUDE.md |

## Key Scripts

| Script | What |
|--------|------|
| scripts/build-loop-local.sh | Main orchestration loop (~2299 lines) |
| scripts/overnight-autonomous.sh | Overnight variant (~1041 lines) |
| scripts/eval-sidecar.sh | Eval sidecar — polls commits, runs evals (~354 lines) |

## Key Libraries

| Library | What |
|---------|------|
| lib/reliability.sh | Lock, backoff, state, truncation, cycle detection (~594 lines) |
| lib/codebase-summary.sh | Cross-feature context summary (components, types, imports, learnings) |
| lib/eval.sh | Mechanical eval, prompt gen, signal parsing, result writing |
| lib/claude-wrapper.sh | Claude CLI wrapper + cost JSONL logging |
| lib/validation.sh | YAML frontmatter validation |
