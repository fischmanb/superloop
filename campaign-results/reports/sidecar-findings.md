# Sidecar Eval Findings — v3 Haiku Campaign

## Source Data

5 eval JSONs from `campaign-results/raw/v3-haiku/evals/`, covering features #5, #26, #27 and associated state commits. Only v3 (Haiku) had the sidecar configured; v2 (Sonnet) did not.

## Finding 1: Framework Compliance Is Consistently "warn"

Every eval returned `framework_compliance: "warn"`. Zero passes. The agents build working features but treat SDD protocol bookkeeping as optional:

- Agents.md missing round entries
- Roadmap left at 🔄 instead of marked ✅
- Spec frontmatter mismatches (file paths, response messages)

**Root cause**: The agent treats instructions as soft suggestions ranked by perceived importance. "Make the feature work" outranks "update the tracking docs." This is the instruction-ignoring failure mode — not a refusal, but a silent deprioritization.

**Impact**: Accumulated bookkeeping drift means the system's own state files become unreliable. Downstream agents reading roadmap.md or Agents.md get stale data.

## Finding 2: Scope Creep Is Detectable

Feature #26 (social links) was flagged `scope_assessment: "moderate"` instead of `"focused"`. The agent introduced a deal detail page that wasn't part of the feature spec.

**Why it matters**: Unspec'd code enters the dependency graph. The next feature builds on top of it. Now you have unauthorized abstractions that no spec covers, no test validates against a contract, and no future agent knows was accidental.

**Sidecar caught it. Build loop didn't.** The build compiled, tests passed, feature shipped. The scope violation is invisible to mechanical checks.

## Finding 3: Repeated Mistakes Persist Across Features

Feature #26 flagged `repeated_mistakes: "isApproved_filter_missing_on_deal_detail_page"`. The agent had already omitted this authorization filter in an earlier feature and did it again.

**This is the core argument for sidecar → agent feedback.** The sidecar detects the pattern. The agent doesn't know the sidecar exists. The same mistake repeats because there's no feedback loop.

## Finding 4: Test Quality Is Weak Despite Test Coverage

Feature #27 (newsletter signup): "a trivially-passing test for subscription ID that doesn't verify actual response shape."

The agent satisfies the mechanical check (`test_files_touched: true`) without writing a meaningful test. This maps to the self-assessment unreliability finding from agent-operations.md — the agent produces artifacts that look correct (green tests, committed files) but don't actually prove correctness.

**The build loop sees**: tests exist, tests pass. ✅
**The sidecar sees**: tests don't test the right thing. ⚠️

## Finding 5: Server/Client Boundary Violations

Feature #5 (auth session): onClick handler placed on a server component (Header.tsx). This is a React Server Components architecture violation that causes a runtime error in the browser.

- TypeScript compiles fine (no type error for onClick on JSX)
- Tests may pass if they don't render in a real RSC environment
- The app breaks when a user clicks the button

**This is the highest-severity class of sidecar finding** — a bug that passes all mechanical gates and only manifests at runtime.

## The Gap: Sidecar Findings Don't Reach the Agent

Current architecture:

```
Build Agent → builds feature → commits
Sidecar → evaluates commit → writes eval JSON
                                    ↓
                              (sits in a file)
```

The eval JSON is never read by the build agent. The agent that built feature #5 with the RSC violation doesn't know the sidecar flagged it. The agent that builds feature #6 doesn't know about the isApproved pattern.

### What a Feedback Loop Would Look Like

```
Build Agent → builds feature → commits
Sidecar → evaluates commit → writes eval JSON
                                    ↓
                            Build Loop reads eval
                                    ↓
                    If issues found → inject into next agent prompt:
                    "Previous feature had these issues: [...]
                     Avoid repeating: [repeated_mistakes]
                     Fix before proceeding: [severity=high items]"
```

### Design Considerations

1. **Blocking vs advisory**: Should a sidecar "warn" block the next feature, or just inject context? Blocking adds safety but kills throughput. Advisory preserves speed but relies on the agent actually reading the context (see Finding 1 — agents deprioritize instructions).

2. **Cumulative context**: The `repeated_mistakes` field is already designed for this. A running list of known patterns could be injected into every agent prompt as a "don't do this" section.

3. **Severity gating**: High-severity findings (runtime errors like #5) should probably block. Low-severity (missing Agents.md entry) should be advisory. The sidecar already has the fields to support this — `integration_quality` and `framework_compliance` map to severity levels.

4. **Context budget**: Every injected finding costs tokens. Need to keep the feedback concise — pattern name + one-line description, not full eval JSON.

## Summary Table

| Finding | Severity | Build Loop Catches? | Sidecar Catches? | Feedback Loop Fixes? |
|---|---|---|---|---|
| Framework non-compliance | Low | ❌ | ✅ | Partially (advisory) |
| Scope creep | Medium | ❌ | ✅ | ✅ (inject scope rules) |
| Repeated mistakes | Medium | ❌ | ✅ | ✅ (inject pattern list) |
| Weak test quality | Medium | ❌ | ✅ | Partially (hard to enforce) |
| Server/client violations | **High** | ❌ | ✅ | ✅ (block + fix) |

Generated: 2026-02-28
