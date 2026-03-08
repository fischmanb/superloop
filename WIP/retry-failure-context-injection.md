# Retry Failure Context Injection

When a build fails and the loop retries, the retry prompt has no knowledge of what went wrong. The agent starts fresh and often repeats the same mistake.

## Idea

Capture the failure output (last N lines of agent output, build error, test failure message) and inject into the retry prompt as a "Prior attempt failed with:" block — same pattern as the eval sidecar feedback loop but scoped to a single feature's retry cycle rather than across features.

## Implementation sketch

In `scripts/build-loop-local.sh`:
- Capture build check stderr (tsc, npm run build) and test failure output to a per-attempt temp file (e.g. `.sdd-state/attempt-{n}-failure.log`) — NOT raw agent output
- On retry (`attempt > 0`), read the failure log and prepend to `build_retry_prompt()`:

```
Prior attempt failed with the following error:
<build_failure>
...compiler errors / test failures / npm stderr...
</build_failure>
Do not repeat the same approach. Diagnose what went wrong and try differently.
```

- Clear temp logs after a successful build

Same fix needed in `build_retry_prompt_overnight()` in `scripts/overnight-autonomous.sh`.

## What to capture (and what NOT to)

**Capture:**
- `tsc --noEmit` stderr — compiler errors, type mismatches, missing imports
- `npm run build` stderr — bundler errors, missing modules
- `npm test` / `pytest` failure output — failing test names and assertion errors
- The agent's `BUILD_FAILED` signal line if present

**Do NOT capture:**
- Raw agent stdout — it's verbose boilerplate (token estimates, roadmap updates, git output) that buries the signal
- The entire build log — keep injected failure output bounded to ~50 lines

## Notes

- Most retries fail because of environment state (bad import path, missing env var, wrong DuckDB schema) — these show up in compiler/test output, not agent prose
- Inserting agent prose into the retry prompt just gives the agent back its own hallucinations to re-read
- Related prior art: eval sidecar injects findings across features; this is the within-feature analog scoped to a single retry cycle
