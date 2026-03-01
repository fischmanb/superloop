# Process Rules

> Prescriptive operational discipline. Often the fix for a `failure_pattern`.
>
> Schema: see `DESIGN-PRINCIPLES.md` §3 (edge types) and §4 (confidence/status enums).
> ID range: global sequential `L-XXXX` shared across all learnings files.

---

## L-0014
Type: process_rule
Tags: prompt-engineering, agent-behavior, conciseness
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00

Keeping agent prompts concise — describing intent, not implementation code — has produced better results. Prescriptive prompts (pasting exact code to insert) have caused agents to copy without understanding, miss edge cases, and fail when context differs slightly. Intent-based prompts ("add a guard that exits if CLAUDECODE is set") have produced better results because the agent reasons about placement and integration.

---

## L-0015
Type: process_rule
Tags: prompt-engineering, scope, agent-behavior
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00

Scope to ≤3-4 files per round, independently testable. Larger scopes increase agent confusion and make failures harder to diagnose.

---

## L-0016
Type: process_rule
Tags: prompt-engineering, verification, gates
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00
Related: L-0001 (depends_on)

Every prompt must end with verification gates — `bash -n`, grep, test suite, `git diff --stat`. Agent self-assessment has proven unreliable; machine-checkable gates are the only trustworthy signal.

---

## L-0017
Type: process_rule
Tags: git, agent-behavior, origin, merge-conflicts
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00

Push main to origin before running agent prompts. Claude Code agents fork from `origin/main`, not local `main`. Stale origin → merge conflicts after every round. Observed: Rounds 21-23 all forked from stale origin/main.

---

## L-0018
Type: process_rule
Tags: git, approval, permissions
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00

Edit approval ≠ commit approval. Approving a file edit does not implicitly approve committing it. Each operation requires its own explicit "yes." Violation: commit 2f77ea9.

---

## L-0019
Type: process_rule
Tags: git, push-discipline, agent-behavior
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00
Related: L-0005 (depends_on)

Agents should commit locally but not push. Brian pushes to GitHub manually. This is a design constraint, not a fixable behavior — agents ignore push restrictions (see L-0005).

---

## L-0020
Type: process_rule
Tags: session-discipline, agent-sessions, chat-sessions
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00

Implementation work (scripts, lib/, tests) → fresh Claude Code agent session with hardened prompt. Planning, analysis, documentation → chat session (claude.ai with Desktop Commander). The boundary: if modifying a script in `scripts/`, a library in `lib/`, or test logic in `tests/`, write a hardened agent prompt. If updating docs or analyzing, chat is fine.

---

## L-0021
Type: process_rule
Tags: session-discipline, desktop-commander, temptation
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00
Related: L-0020 (depends_on)

Desktop Commander gives chat full filesystem access — making it tempting to "just make a quick fix." Resist. Write the agent prompt instead. Quick fixes in chat bypass the verification gates that catch agent mistakes.

---

## L-0022
Type: process_rule
Tags: grep, verification, comment-filter
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00

Use the corrected grep comment-filter pattern. Verification blocks must use:
```bash
grep -rn "pattern" scripts/ | grep -v ":#\|: #"
```
Not `grep -v "^\s*#"` — that pattern fails because `grep -rn` prepends `filename:linenum:` before the `#`.

---

## L-0023
Type: process_rule
Tags: learnings, organization, repo-structure
Confidence: high
Status: active
Date: 2026-02-28T20:31:00-05:00

Learnings/patterns belong in the main `learnings/` catalog (previously `.specs/learnings/`), not in project-specific directories (e.g., `stakd/.specs/learnings/`). Project-specific dirs only get fixes specific to that build/app.
