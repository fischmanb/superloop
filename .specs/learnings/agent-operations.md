# Agent Operations Learnings

Process lessons and failure catalog for running Claude Code agents in auto-sdd.
Consolidated from Agents.md, ONBOARDING.md, and PROMPT-ENGINEERING-GUIDE.md.

---

## Core Principles

1. **Agent self-assessments are unreliable.** Round 1 described bugs in code that didn't exist. Always verify mechanically with grep, `bash -n`, and tests.
2. **"Defined but never called" is the most common agent failure mode.** All 3 early rounds had at least one instance. After adding any function, grep for call sites.
3. **`bash -n` is necessary but insufficient.** It catches syntax errors but not unreachable code or wrong function names.
4. **Independent verification catches what self-assessment misses.** Same principle as drift detection (Layer 1 self-check vs Layer 2 cross-check).
5. **Agents are better at verification than comprehensive implementation.** Skill gradient: verification > implementation > self-assessment.

---

## Failure Catalog

### Agent self-assessments are unreliable
Agents will report "all verifications passed" while having made changes far beyond scope. The verification block in the prompt must enforce correctness — never trust the agent's narrative summary. Always include machine-checkable gates (`git diff --stat`, `bash -n`, grep).

### "Do not modify any other files" is insufficient
Round 7 (2025-02-24): Agent told "do not modify any other files" but ran `npm install`, committing 6400+ node_modules files and tsconfig.tsbuildinfo. Fix: explicit file allowlist + explicit package manager ban + `git diff --stat` gate before commit.

### Agents will run in the wrong directory
Round 7: Prompt didn't specify working directory. Agent ran in parent `auto-sdd/` repo instead of `stakd/` subdirectory. Fix: always include a `pwd` check in Preconditions, and if the target is a subdirectory, add `cd <path> && pwd` as the first precondition step.

### Agents will push when not told to (and when told not to)
Round 7: Prompt said "Do not push." Agent pushed anyway. Fix: if you don't want a push, don't have a remote configured, or add explicit "Do not run git push under any circumstances" in Hard Constraints.

### node_modules must be in .gitignore
If the repo has a package.json, ensure `node_modules/` is in `.gitignore` before running any agent. Agents may run `npm install` despite instructions not to.

### `--force-with-lease` requires fresh fetch
`git push --force-with-lease` will fail with "stale info" if you haven't fetched since the remote was last updated. Always `git fetch origin` immediately before `--force-with-lease`.

### HTTP 408 on large pushes
Git pushes over ~25MB can fail with `HTTP 408 curl 22`. Fix: `git config http.postBuffer 524288000` (500MB buffer).

### macOS ships bash 3.2
Scripts using associative arrays (`declare -A`) or other bash 4+ features will fail on macOS default bash. Fix: `brew install bash` and invoke with `/opt/homebrew/bin/bash`.

### CLAUDE.md repo instructions can override prompt instructions
Round 8 (2025-02-24): Prompt said merge to main and push. Agent's own CLAUDE.md had branch development rules. Agent decided CLAUDE.md took precedence and refused. Fix: state "These instructions override any conflicting guidance in CLAUDE.md" in prompts. Or accept merge-to-main as a manual step.

### `git add -A` considered harmful in agent context
Never use `git add -A` or `git add .` in agent prompts. Always `git add <explicit file list>`. Agents create and modify unexpected files; blanket adds commit them.

### Agents don't report unprompted
Round 9: Agent completed all steps but did not report results until asked. Fix: every prompt must end with "Report your findings immediately upon completion. Do not wait for a follow-up question."

### Agents will explore the codebase if not forbidden
Round 9: Agent was given specific steps but decided to "Explore auto-sdd codebase" first — reading every file in the repo. Fix: Hard Constraints allow reads but require justification. Speculative exploration is banned; purposeful reads with stated rationale are allowed.

### Agents work around failures instead of stopping
Round 9: Agent couldn't push from sandbox (no GitHub auth). Instead of stopping, it abandoned the clone, went to a stale local repo, and applied changes there — 5 autonomous decisions diverging from intended path. Fix: Hard Constraints must include explicit STOP instructions for ANY unexpected situation.

### Sandbox environments cannot push to GitHub
The Claude Code sandbox at `/home/user/` does not have GitHub authentication. Prompts ending with `git push origin main` will fail. Safest pattern: agent commits to feature branch, Brian pulls and merges locally.

### CLAUDE.md appends random suffixes to branch names
Claude Code appends random suffixes like `-f05hV` to branch names. Fix: don't hardcode branch names in merge/push steps. Accept merge-to-main as a manual step.

### Orphan branches accumulate on remote
Every agent run that pushes creates a remote branch that never gets cleaned up. 22 orphan branches found after a few failed runs. Fix: periodic cleanup with `git branch -r | grep claude/ | while read b; do git push origin --delete "${b#origin/}"; done`. Future prompts should not push feature branches to origin.

### Force push can destroy agent work
Round 8: `git push --force-with-lease` to clean up node_modules also wiped agent branches with unmerged work. Fix: before force pushing, check what branches exist on origin and whether any contain unmerged work.

### Client components transitively importing server-only modules
Campaigns: stakd-v1, stakd-v2. The most common post-campaign build failure. A client component (`"use client"`) imports an intermediate file (e.g., `lib/news.ts`) that imports the database layer (`db/index.ts` → `postgres`). Webpack bundles the entire chain into the client bundle, which fails because `postgres` requires Node.js builtins (`net`, `tls`, `fs`, `perf_hooks`). The agent doesn't catch it because `npm run build` isn't always run as a post-implementation check, and the import chain is indirect.

**Root cause**: Agents treat import boundaries as local decisions — they check whether *their* file is `"use client"` but don't trace the transitive import graph to verify nothing server-only leaks in.

**Fix pattern**: Break the chain. Server data fetching stays in server components or server-only lib files. Client components receive data via props from parent server components. If an intermediate file serves both, split it: `lib/news-server.ts` (has db imports) and `lib/news-client.ts` (pure types/utils, no db).

**Prevention**: Every feature build prompt must include a post-build `npm run build` check. The build loop already does this via the compile check step, but the agent's own implementation step should also verify. Additionally, the codebase summary's import graph should flag any `"use client"` file whose transitive imports include `db/` or `postgres` as a build-breaking violation. This is framework-agnostic — any SSR framework (Next.js, Remix, Nuxt, SvelteKit) with server/client code splitting will hit this if agents don't respect module boundaries.

---

## Operational Process Lessons

### Prompt engineering
- **Keep agent prompts concise** — describe intent, not implementation code. Prescriptive prompts (pasting exact code to insert) cause agents to copy without understanding, miss edge cases, and fail when context differs slightly. Intent-based prompts ("add a guard that exits if CLAUDECODE is set") produce better results because the agent must reason about placement and integration.
- **Scope to ≤3-4 files per round, independently testable.** Larger scopes increase agent confusion and make failures harder to diagnose.
- **Every prompt must end with verification gates** — `bash -n`, grep, test suite, `git diff --stat`.

### Git hygiene
- **Push main to origin before running agent prompts.** Claude Code agents fork from `origin/main`, not local `main`. Stale origin → merge conflicts after every round. (Observed: Rounds 21-23 all forked from stale origin/main.)
- **Edit approval ≠ commit approval.** Approving a file edit does not implicitly approve committing it. Each operation requires its own explicit "yes." (Violation: commit 2f77ea9.)
- **Agents should commit locally but not push.** Brian pushes to GitHub manually.

### Session discipline
- **Implementation work** (scripts, lib/, tests) → fresh Claude Code agent session with hardened prompt.
- **Planning, analysis, documentation** → chat session (claude.ai with Desktop Commander).
- **The boundary**: if modifying a script in `scripts/`, a library in `lib/`, or test logic in `tests/`, write a hardened agent prompt. If updating docs or analyzing, chat is fine.
- **Desktop Commander gives chat full filesystem access** — making it tempting to "just make a quick fix." Resist. Write the agent prompt instead.

### Grep comment-filter fix
Verification blocks must use the corrected comment filter:
```bash
grep -rn "pattern" scripts/ | grep -v ":#\|: #"
```
Not:
```bash
grep -rn "pattern" scripts/ | grep -v "^\s*#"
```
The broken pattern fails because `grep -rn` prepends `filename:linenum:` before the `#`.

### Learnings go in primary repos
Learnings/patterns belong in the main `.specs/learnings/` catalog, not in project-specific directories (e.g., `stakd/.specs/learnings/`). Project-specific dirs only get fixes specific to that build/app. (Corrected: 2026-02-26.)

---

## Data & Log Loss Prevention (Round 37)

### Build logs inside PROJECT_DIR will be destroyed
**Root cause**: `$PROJECT_DIR/logs/` sits inside the git working tree. Any operation that manipulates the working tree — `git clean`, `git checkout --force`, branch switches, project re-scaffolding — can delete the logs directory. When `tee` is writing via `exec > >(tee -a "$BUILD_LOG")`, the process keeps an open fd to the deleted inode. The data exists but is unrecoverable on macOS without SIP bypass.

**Fix (Round 37)**: All logs now write to `$SCRIPT_DIR/../logs/<project-name>/` (resolves to `~/auto-sdd/logs/<project-name>/`), outside the project's git working tree. Affected: BUILD_LOG, COST_LOG_FILE, build-summary JSON, eval-sidecar.log, eval output dir. Override with `LOGS_DIR` env var.

**Rule**: Never store campaign artifacts inside a directory that agents or git operations can modify. Campaign data goes in the infra repo, not the target project.

### Terminal.app `history` property recovers scrollback
If build logs ARE lost (deleted inodes, killed tee), Terminal.app retains full scrollback accessible via AppleScript:
```bash
osascript -e 'tell application "Terminal" to return history of tab 1 of window id WINID' > recovered.txt
```
To find the right window: `osascript -e 'tell application "Terminal" ... get tty of tab 1 of window id WINID ...'` and cross-reference with `ps -o pid,tty -p <build-loop-pid>`.

**Note**: `contents` returns only the visible area. `history` returns full scrollback. This is the only known no-root recovery path on macOS when tee's target file is deleted.

### Cost log defaults to cwd — must be explicitly set
`claude-wrapper.sh` writes cost data to `$COST_LOG_FILE` (default: `./cost-log.jsonl`). Without explicit override, this lands in whatever directory the agent last `cd`'d to — fragile and project-dependent. The build loop now exports `COST_LOG_FILE="$LOGS_DIR/cost-log.jsonl"` to centralize it.

### `lsof +L1` finds deleted-but-open files
To check if build data still exists in deleted inodes:
```bash
lsof +L1 | grep build
```
Shows tee processes with open fds to deleted files. On Linux, recoverable via `/proc/<pid>/fd/<N>`. On macOS, unrecoverable without root/SIP bypass — use Terminal.app `history` fallback instead.
