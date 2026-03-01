# Domain Knowledge

> Framework/tool/platform-specific knowledge that agents need. External-world facts, not project-specific decisions.
>
> Schema: see `DESIGN-PRINCIPLES.md` §3 (edge types) and §4 (confidence/status enums).
> ID range: global sequential `L-XXXX` shared across all learnings files.

---

## L-0029
Type: domain_knowledge
Tags: macos, bash, compatibility
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00

macOS ships bash 3.2. Scripts using associative arrays (`declare -A`) or other bash 4+ features will fail on macOS default bash. Fix: `brew install bash` and invoke with `/opt/homebrew/bin/bash` or use `#!/usr/bin/env bash` with Homebrew bash in PATH.

---

## L-0030
Type: domain_knowledge
Tags: git, force-push, fetch
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00

`--force-with-lease` requires fresh fetch. `git push --force-with-lease` will fail with "stale info" if you haven't fetched since the remote was last updated. Always `git fetch origin` immediately before `--force-with-lease`.

---

## L-0031
Type: domain_knowledge
Tags: git, http, large-pushes
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00

HTTP 408 on large pushes. Git pushes over ~25MB can fail with `HTTP 408 curl 22`. Fix: `git config http.postBuffer 524288000` (500MB buffer).

---

## L-0032
Type: domain_knowledge
Tags: claude-code, sandbox, github, push
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00
Related: L-0005 (related_to)
Related: L-0011 (related_to)

Sandbox environments have not been able to push to GitHub. The Claude Code sandbox at `/home/user/` does not have GitHub authentication. Prompts ending with `git push origin main` have failed in this context. Pattern that has worked: agent commits to feature branch, Brian pulls and merges locally.

---

## L-0033
Type: domain_knowledge
Tags: claude-code, git, branch-naming
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00
Related: L-0034 (related_to)

CLAUDE.md appends random suffixes to branch names. Claude Code appends random suffixes like `-f05hV` to branch names. Fix: don't hardcode branch names in merge/push steps. Accept merge-to-main as a manual step.

---

## L-0034
Type: domain_knowledge
Tags: git, branch-cleanup, remote
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00
Related: L-0033 (related_to)

Orphan branches have accumulated on remote. Every agent run that pushes creates a remote branch that hasn't been cleaned up automatically. 22 orphan branches found after a few failed runs. Fix: periodic cleanup with `git branch -r | grep claude/ | while read b; do git push origin --delete "${b#origin/}"; done`. Avoiding pushing feature branches to origin has reduced this problem.

---

## L-0035
Type: domain_knowledge
Tags: git, force-push, data-loss
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00
Related: L-0030 (related_to)

Force push can destroy agent work. Round 8: `git push --force-with-lease` to clean up node_modules also wiped agent branches with unmerged work. Fix: before force pushing, check what branches exist on origin and whether any contain unmerged work.

---

## L-0036
Type: domain_knowledge
Tags: macos, terminal, scrollback, data-recovery
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00
Related: L-0013 (related_to)

Terminal.app `history` property recovers scrollback. If build logs are lost (deleted inodes, killed tee), Terminal.app retains full scrollback accessible via AppleScript:
```bash
osascript -e 'tell application "Terminal" to return history of tab 1 of window id WINID' > recovered.txt
```
`contents` returns only the visible area. `history` returns full scrollback. Only known no-root recovery path on macOS when tee's target file is deleted.

---

## L-0037
Type: domain_knowledge
Tags: cost-tracking, claude-wrapper, configuration
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00

Cost log defaults to cwd — must be explicitly set. `claude-wrapper.sh` writes cost data to `$COST_LOG_FILE` (default: `./cost-log.jsonl`). Without explicit override, this lands in whatever directory the agent last `cd`'d to. The build loop now exports `COST_LOG_FILE="$LOGS_DIR/cost-log.jsonl"` to centralize it.

---

## L-0038
Type: domain_knowledge
Tags: macos, lsof, deleted-files, data-recovery
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00
Related: L-0013 (related_to)
Related: L-0036 (related_to)

`lsof +L1` finds deleted-but-open files. Shows tee processes with open fds to deleted files. On Linux, recoverable via `/proc/<pid>/fd/<N>`. On macOS, unrecoverable without root/SIP bypass — use Terminal.app `history` fallback instead.
