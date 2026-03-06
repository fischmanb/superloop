# Retiring Chat Handoff Protocol

When a chat session is approaching end-of-life (context growing long, compactions happening, Brian signals wrap-up, or session has accomplished its goals), execute this protocol to ensure continuity.

## Triggers

- Brian says "wrap up", "hand off", "new chat", "retiring this chat"
- 2+ compactions have occurred in the session
- Session has been running for 4+ hours with substantial work
- Context window feels constrained (tool outputs being truncated, responses getting cut off)

## Steps

### 1. Final Checkpoint
Run the full 8-step checkpoint protocol. Everything committed and pushed.

### 2. Create Handoff File
Write `~/auto-sdd/.handoff.md` with:

```markdown
# Session Handoff — [DATE]

## Session Summary
[1-3 sentences: what this session accomplished]

## Commits This Session
[list of commit hashes and one-line descriptions]

## Incomplete Work
[items started but not finished, with current state]

## Pending Decisions
[decisions that need Brian's input, with context]

## Unpushed Commits
[any local commits not yet on origin]

## Active Priorities for Next Session
[ordered list of what the next session should do first]

## Context the Next Session Needs
[anything non-obvious that took this session time to learn/discover]

## Files Modified This Session
[key files touched, so next session knows where to look]
```

### 3. Update ACTIVE-CONSIDERATIONS.md
Ensure all open items are current. This is the persistent cross-session state.

### 4. Flush Pending Captures
Any `pending_captures` in `.onboarding-state` must be written as learnings or explicitly dropped with reason.

### 5. Clear Prompt Stash
`.prompt-stash.json` can be cleared — content has been mined.

### 6. Final Push
Push all remaining commits (Brian approves if non-checkpoint).

## For the Next Session

The fresh session's onboarding should:
1. Read ONBOARDING.md (standard)
2. Read `.handoff.md` if it exists (session-specific continuity)
3. Read ACTIVE-CONSIDERATIONS.md (current priorities)
4. Read core.md (constitutional learnings)
5. Move `.handoff.md` to `archive/handoffs/handoff-{DATE}.md` after absorbing it (create dir if needed). Never delete handoffs — they form a session history.

## Notes

- The handoff file is NOT a replacement for learnings. Anything reusable goes in `/learnings`. The handoff is for ephemeral session-specific state.
- Keep it under 50 lines. The next session has limited context budget too.
- If the session was purely process work (no feature code), say so — the next session may need to context-switch to feature work.
