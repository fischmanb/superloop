# Build Loop Failure Investigation — Findings Log
# Started: 2026-02-26
# Purpose: Comprehensive audit of all build loop issues across stakd campaign + prior runs

## Finding #1: Credit exhaustion with no early halt
- **Source**: stakd build.log lines 239-856
- **Impact**: 14 features × 6 attempts = 84 wasted API calls over ~12 minutes
- **Root cause**: Credit exhaustion detection (Round 13) not effective — agent exits with code 1, backoff only handles HTTP 429
- **Fix needed**: Detect "Credit balance is too low" in agent output, halt immediately

## Finding #2: Rapid retry burn (4-second cycles)
- **Source**: stakd build.log
- **Impact**: No backoff between retries for instant-fail agents
- **Root cause**: Exponential backoff keyed on rate limit, not generic failure
- **Fix needed**: Minimum delay between retries regardless of failure type

## Finding #3: Agent "use client" + server import pattern confusion
- **Source**: This session — stakd map page
- **Impact**: All localhost routes 500'd
- **Root cause**: Agent saw Leaflet + ssr:false, incorrectly added "use client" to server component
- **Fix needed**: CLAUDE.md rule for Next.js 15 server/client boundary; codebase summary injection

## Finding #4: Cascade module failure
- **Source**: This session — stakd map page
- **Impact**: Single broken module poisoned webpack graph; /news, /data, middleware all 500'd with map error
- **Root cause**: Next.js 15 webpack compilation — one bad module cascades
- **Fix needed**: Per-route smoke test in validation, not just compile check

## Finding #5: NODE_ENV=production in shell environment
- **Source**: This session + prior session
- **Impact**: Tailwind PostCSS fails on cold start; masked by .next cache on warm starts
- **Root cause**: Transient shell variable, not in config files
- **Fix needed**: Build loop should set NODE_ENV=development explicitly for dev builds

## Finding #6: `local` outside function context (line 1344)
- **Source**: Smoke test run (Feb 22) — "Recovering lost project context" chat
- **Impact**: Loop crashes after completing features during cleanup/summary
- **Root cause**: Bare `local` statement outside function — bash syntax error
- **Fix needed**: Already fixed in Round 6 (7 bare locals), but this one survived

## Finding #7: MAX_FEATURES / MAX_FEATURES_PER_RUN env var mismatch
- **Source**: Smoke test run — "Recovering lost project context" chat
- **Impact**: Loop ignores .env.local cap, runs all features uncapped
- **Root cause**: .env.local has MAX_FEATURES_PER_RUN, script reads MAX_FEATURES
- **Fix needed**: Script should read both, prefer MAX_FEATURES_PER_RUN

## Finding #8: Nested Claude Code session block
- **Source**: Smoke test run — "Recovering lost project context" chat
- **Impact**: Loop hangs silently when run from inside Claude Code
- **Root cause**: CLAUDECODE env var blocks child claude -p processes
- **Fix needed**: Detect CLAUDECODE at startup, warn and exit with instructions

## Finding #9: Permission prompts blocking unattended runs
- **Source**: Smoke test run — "Recovering lost project context" chat
- **Impact**: Loop hangs waiting for interactive input during overnight runs
- **Root cause**: -p flag doesn't fully suppress prompts; needs --dangerously-skip-permissions
- **Fix needed**: Already fixed by adding flag to agent_cmd()

## Finding #10: Credit exhaustion retry burn (quantified)
- **Source**: stakd build.log — 14 features × 6 attempts = 84 failed calls
- **Impact**: 12 minutes wasted on guaranteed-fail retries
- **Root cause**: Same as #1 — no string-match detection on "Credit balance is too low"
- **Fix needed**: grep agent output for credit/billing errors before retry

## Finding #11: No codebase summary between features
- **Source**: Smoke test — "Feature 2 built without knowledge of Feature 1's types"
- **Impact**: Type redeclarations, interface drift, luck-based compatibility
- **Root cause**: Each agent gets fresh context with only its own spec
- **Fix needed**: Codebase summary injection (priority #1 on roadmap)

## Finding #12: Agent Next.js 15 server/client boundary confusion
- **Source**: This session — map page diagnosis
- **Impact**: Entire app broken by one misplaced directive
- **Root cause**: Agent doesn't understand dynamic(ssr:false) is FOR server components
- **Fix needed**: Add Next.js 15 patterns to CLAUDE.md; framework-specific rules

## Finding #13: Unused imports left behind by agents
- **Source**: Drift check on Feature 2 (core layout) — MobileMenu.tsx unused useState
- **Impact**: Lint warnings compound across features
- **Fix needed**: Add lint check to post-build validation pipeline

## Finding #14: Model switching mid-run undocumented
- **Source**: Smoke test (Opus→Sonnet) + stakd campaign (Opus→Haiku)
- **Impact**: No documentation of quality/cost tradeoffs per model
- **Root cause**: Model selection is config-driven but not logged per-feature
- **Fix needed**: Log model used per feature in build summary

## Finding #15: Cost data — $39.05 for 21 features on Haiku 4.5
- **Source**: stakd cost-log.jsonl — 20 sessions
- **Impact**: Informational — ~$1.95/feature avg including drift checks
- **Detail**: Cache read tokens 5-6M per session (effective caching)

## Finding #16: Context overload in chat sessions (meta-process issue)
- **Source**: This session — Brian observed assistant hitting context limits
- **Impact**: Assistant tries to do too much per prompt, loses coherence
- **Fix needed**: Break logic — report findings incrementally, get go-ahead before continuing

---
# INVESTIGATION CONTINUES BELOW — append new findings as discovered


## Git Log — Full Stakd Build History (newest first)

```
42d7a3a fix: extract DealMapLoader client wrapper — resolve Next.js 15 ssr:false server component error and cascade 500s
0a8cfb9 fix: reconcile spec drift for Data / Analytics Page (CompStak Insights)
2f140e6 feat: complete feature #28 - Data / analytics page (CompStak insights)
5d7c272 chore: start feature #28 - Data / analytics page (CompStak insights)
e64a045 fix: reconcile spec drift for Email Newsletter Signup
d62d0bd feat: complete feature #27 - Email newsletter signup (footer)
e00118e chore: start feature #27 - Email newsletter signup (footer)
d2f1cd5 feat: complete feature #25 - User settings & profile edit
de63af4 chore: start feature #25 - User settings & profile edit
0459c5f fix: reconcile spec drift for Dark Mode Toggle
766e7ff feat: complete feature #24 - Dark mode toggle
728f6f8 chore: start feature #24 - Dark mode toggle
e2a8be1 feat: complete feature #26 - Social links (footer, share)
3672ec1 feat: complete feature #23 - CompStak API integration (comps link on deal)
6530c5b chore: start feature #23 - CompStak API integration (comps link on deal)
c9522e0 On auto/chained-20260225-094223: partial feature 4 work
dd05f35 index on auto/chained-20260225-094223: 153f75b chore: start feature #26 - Social links (footer, share)
153f75b chore: start feature #26 - Social links (footer, share)
aaf9348 fix: reconcile spec drift for User settings & profile edit
cc0ff65 feat: complete feature #25 - User settings & profile edit
faa49d1 chore: start feature #25 - User settings & profile edit
51d702c fix: reconcile spec drift for Dark Mode Toggle
8b54479 feat: complete feature #24 - Dark mode toggle
8418196 chore: start feature #24 - Dark mode toggle
5df1e09 fix: reconcile spec drift for CompStak API integration (comps link on deal)
8a50a53 feat: complete feature #23 - CompStak API integration (comps link on deal)
dec59eb chore: start feature #23 - CompStak API integration (comps link on deal)
4c779d0 fix: reconcile spec drift for Top brokers sidebar (deals page)
93cebe3 feat: complete feature #22 - Top brokers sidebar (deals page)
c188530 chore: start feature #22 - Top brokers sidebar (deals page)
7cc7968 fix: reconcile spec drift for Landing page (hero, search bar, market filters)
82d425f fix: replace dotAll regex flag (/s) with [\s\S] in landing-page tests
c040d21 feat: complete feature #21 - Trending deals (homepage)
569eff8 chore: start feature #21 - Trending deals (homepage)
126b2cf fix: reconcile spec drift for News Section / Industry News Feed
fdacda4 fix: replace dotAll regex flag (/s) with [\s\S] for ES2018 compat
bb21eda chore: mark feature #20 (Awards categories) complete in roadmap
daa11d9 feat: complete feature #20 - Awards categories
30a1ffe chore: start feature #20 - Awards categories
fbce50a chore: mark feature #19 (News section) complete in roadmap
28e7ff6 feat: complete feature #19 - News section / industry news feed
7b6ea54 compound: learnings from map view implementation
54ebf50 feat: complete feature #18 - Map view (deal locations, gated for logged-in)
28d9d49 chore: start feature #18 - Map view
ca2a2a7 fix: reconcile spec drift for Listings page
d16473d compound: learnings from listings page implementation
6f36ec5 feat: complete feature #17 - Listings page (active for-sale/for-lease)
d1f99f2 chore: start feature #17 - Listings page
c734802 fix: reconcile spec drift for Rankings page
15d49d7 compound: learnings from rankings page implementation
d3c3097 feat: complete feature #16 - Rankings page
70be7ad chore: start feature #16 - Rankings page
f370a67 fix: reconcile spec drift for Agent profile page
87b9706 compound: learnings from agent profile page implementation
d8c29e9 feat: complete feature #15 - Agent profile page
65aadab chore: start feature #15 - Agent profile page
3ba8e6c fix: reconcile spec drift for Submit deal form & flow
41111cc compound: learnings from submit deal form & flow implementation
5c787a9 feat: complete feature #14 - Submit deal form & flow
dbc3eb1 chore: start feature #14 - Submit deal form & flow
ec9d70a fix: reconcile spec drift for Search (address, advanced filters)
9c657be compound: learnings from search & advanced filters implementation
d1d5802 feat: complete feature #13 - Search (address, advanced filters)
d237dcf chore: start feature #13 - Search (address, advanced filters)
b2df585 compound: learnings from market/submarket filter implementation
777087f feat: complete feature #12 - Market/submarket filters
21abd30 chore: start feature #12 - Market/submarket filters
0a6b846 fix: reconcile spec drift for deal card component
237b16d feat: complete feature #11 - Deal card component
8fcad77 chore: start feature #11 - Deal card component
4cd81ef compound: learnings from deal detail page implementation
62bd5b7 feat: complete feature #10 - Deal detail page
7b14f2a chore: start feature #10 - Deal detail page
b9ea60e fix: reconcile spec drift for deals list page
3e818fb feat: complete feature #9 - Deals list page
c71fdc9 chore: start feature #9 - Deals list page
9be91de feat: complete feature #8 - Landing page (full TDD cycle)
9d251b6 compound: learnings from landing page implementation
4c00d57 chore: start feature #8 - Landing page
0f63e99 merge: 7 completed features from first build run
```

## Observations from git log

1. Features 23-26 appear TWICE — duplicate commits with different hashes (e.g., feature #24 built at 8b54479 and again at 766e7ff). Suggests the loop restarted mid-run and rebuilt already-completed features. Resume state may have been lost or not checked.

2. Feature #26 (Social links) has a stash commit (dd05f35 "index on auto/chained-20260225-094223") and a "partial feature 4 work" commit (c9522e0). This is anomalous — suggests agent crash or context exhaustion mid-feature, with git stash used for recovery.

3. Several features have NO "chore: start" commit (e.g., #19 News section, #26 Social links). The start commit is the branch point marker — missing it means the agent may have been building on dirty state.

4. Regex compat fix appears twice: 82d425f and fdacda4 — both replace dotAll /s flag with [\s\S]. Agent used ES2022 regex feature that fails in test runner. Same bug hit twice = not captured in learnings for reuse.

5. Features 8-28 built in second run on Haiku 4.5. Feature #8 (Landing page) was the first in this run, starting from merge commit 0f63e99.


## Timeline Reconstruction — Three Runs

### Run 1 (Feb 24, 5:08pm - 11:09pm EST) — Opus
- Branch range: auto/chained-20260224-221046 through auto/chained-20260224-230607
- Built: Features 1-7 successfully
- Failed: Features 8-21 — credit exhaustion. 84 failed API calls in ~12 minutes.
- Build log: ~/auto-sdd/stakd/build.log (1119 lines, this run only)
- Model: claude-opus-4-6

### Run 2 (Feb 25, 1:00am - 3:20am EST) — Haiku 4.5
- Branch range: auto/chained-20260225-005354 through auto/chained-20260225-032034
- Built: Features 8-22 (15 features in ~2.5 hours)
- Merge commit 0f63e99 at start: "merge: 7 completed features from first build run"
- Model: claude-haiku-4-5-20251001 (from cost-log.jsonl)
- No build log captured for this run

### Run 3a (Feb 25, 8:29am - 10:31am EST) — Haiku 4.5
- Branch range: auto/chained-20260225-082932 through auto/chained-20260225-094223
- Built: Features 23-25 successfully
- Failed: Feature 26 (Social links) — 4 retry branches created in 35 seconds (094148, 094200, 094211, 094223), all pointing to same commit
- Crash: Stash created at 10:31am with partial feature 26 work (Footer.tsx modified, resume.json updated)
- Resume state in stash showed feature_index: 3, completed: [23, 24, 25]

### Run 3b (Feb 25, 10:33am - 11:10am EST) — Haiku 4.5
- Branch range: auto/chained-20260225-103319 through auto/chained-20260225-111009
- REBUILT features 23-25 (resume state was in stash, not on disk)
- Then built 26-28 successfully
- Total branches: 39 local branches created across all runs

## New Findings

### Finding #17: Resume state lost on crash — features rebuilt
After run 3a crashed mid-feature-26, the resume.json was stashed (not committed). Run 3b started fresh from feature 22's endpoint and rebuilt features 23-25 unnecessarily. Cost: ~$9.42 wasted (3 features × ~$3.14 avg build session cost, doubled because originals + rebuilds).
Root cause: resume.json is tracked in working tree, not committed to git. Stash captures it but the next run starts clean.
Fix: Commit resume.json on each feature completion, or write to a path outside the git tree.

### Finding #18: Rapid branch creation during retry burn
4 branches created in 35 seconds while feature 26 repeatedly failed. Each retry creates a new branch (chained strategy). The agent fails immediately, loop creates next branch, retries.
Root cause: No delay between branch creation and retry. Branch naming is timestamp-based at second resolution.
Fix: Minimum delay between retries + don't create a new branch until agent actually produces output.

### Finding #19: 39 orphan branches never cleaned up
Each feature attempt creates a branch. Failed attempts leave dead branches. No cleanup step in the loop. After 3 runs: 39 branches, most orphaned.
Fix: Post-run cleanup step that deletes branches not in the final chain.

### Finding #20: No build log for runs 2 and 3
Only run 1's build.log was captured (first run output piped to file). Runs 2 and 3 have no build log — only git history and cost-log.jsonl as forensic sources.
Fix: Build log should be auto-rotated per run with timestamp in filename.

### Finding #21: Dotall regex (/s) used twice, fixed twice
Agent used ES2022 regex feature in tests at features #19 and #21. Same fix applied both times ([\s\S]* replacement). The learning from the first fix (fdacda4) wasn't available to the agent building the next feature (82d425f).
Root cause: No cross-feature context. Learnings captured in .specs/learnings/ but not injected into build prompt.
Fix: Include recent learnings in build prompt; add "no /s flag" to CLAUDE.md.

### Finding #22: Security learnings file completely empty
Despite building 7 features involving auth (cookies, sessions, JWT, protected routes), the security.md learnings file has zero entries. The /compound command either wasn't triggered for those features or didn't classify auth patterns as security learnings.
Impact: Security patterns not captured for reuse. Each feature re-discovers auth patterns independently.

### Finding #23: No codebase-summary.md generated
.specs/codebase-summary.md doesn't exist. This is the #1 documented gap in the auto-sdd README — each agent builds without knowledge of prior features. Would have prevented the map page "use client" bug (agent would know other pages use server components with cookies).

### Finding #24: 5-hour gap between runs indicates manual restart
Run 1 ended ~11pm, Run 2 started ~1am (2 hour gap). Run 2 ended ~3:20am, Run 3 started ~8:29am (5 hour gap). These gaps indicate manual restarts, not automatic recovery. The overnight-autonomous.sh script either wasn't used or doesn't handle credit exhaustion recovery.


## Findings from Batch 2 (learnings files + CLAUDE.md audit)

### Finding #25: CLAUDE.md has zero Next.js-specific rules
stakd/CLAUDE.md is 432 lines of generic SDD workflow. Zero mention of: server components, client components, "use client" directive, dynamic imports, Next.js 15 params-as-Promise, App Router specifics. The agent had no framework-specific guidance. Would have prevented finding #3/#12 (map page bug).
Fix: Add a "## Next.js 15 Rules" section to CLAUDE.md covering server/client boundary, dynamic imports, cookies/headers imports, metadata exports.

### Finding #26: Incomplete learnings contributed to map page bug
Two learnings in .specs/learnings/ are correct but incomplete in ways that contributed to the bug:
- performance.md: "Browser-API-dependent libraries must use `dynamic(ssr:false)`" — correct, but doesn't specify WHERE (must be in a client wrapper component, not a server page with "use client" added)
- general.md: "Next.js App Router requires 'use client' for interactive components using hooks" — correct for hook-using components, but agent generalized "interactive" to include pages with dynamic imports
The map page agent followed both learnings and got the wrong result because neither learning captured the full pattern.
Fix: Update both learnings with the complete pattern: client wrapper component for dynamic(ssr:false), server page stays server component.

### Finding #27: security.md completely empty despite 7+ auth features
Confirmed by file read. Features built: auth session, protected routes, cookie verification, JWT tokens, admin gating, form submission auth, API route auth. Zero security learnings captured. /compound either wasn't triggered or didn't classify these as security patterns.
Fix: Manual /compound pass over auth-related features, or add "security" keyword triggers to compound classification.

### Finding #28: Stash confirms resume state wasn't committed
`git stash list` shows: "stash@{0}: On auto/chained-20260225-094223: partial feature 4 work"
The stash contains the resume.json that should have persisted across the crash. Because resume.json lives in the working tree (not committed per-feature), the crash lost it. Run 3b rebuilt features 23-25 unnecessarily.
Fix (same as #17): Commit resume.json after each feature, or write to a path outside git.


## Findings from Batch 3 (config audit + cost analysis)

### Finding #29: Credit exhaustion detection wasn't in the build script during ANY stakd run
Round 13 (credit exhaustion halt) was merged to auto-sdd main at Feb 25 10:30am EST. Stakd Run 1 was Feb 24 ~5pm. Run 2 was Feb 25 ~1am. Run 3 was Feb 25 ~8:30am. ALL three runs predate the merge. The fix existed as a branch but was never in the script version that ran. This fully explains why Run 1 burned 84 wasted API calls — there was literally no detection code present.
Fix: Already fixed in current main. But exposes a process gap — should verify script version before launching a multi-hour build campaign.

### Finding #30: auto-sdd .env.local is stale smoke-test config
.env.local still has ADHD Calendar smoke test settings (BUILD_MODEL=claude-opus-4-6, MAX_FEATURES_PER_RUN=1). Stakd runs overrode these via command-line env vars. No stakd-specific config file exists.
Fix: Either create per-project .env files or document that CLI overrides are the expected pattern.

### Finding #31: stakd .env.local has no build loop config
stakd/.env.local has only 4 lines (AGENT_MODEL, DATABASE_URL, NEXTAUTH_SECRET, NEXTAUTH_URL). No build loop config. All build loop settings came from auto-sdd/.env.local + CLI overrides.
Fix: Informational — this is fine if CLI overrides are documented. But means build settings are not reproducible without knowing the exact command used.

### Finding #32: Cost breakdown — build vs drift sessions
From cost-log.jsonl analysis (Haiku 4.5 runs only, 20 sessions):
- 10 build sessions (>30 turns): avg $3.14, avg 60 turns
- 10 drift/small sessions (≤15 turns): avg $0.77, avg 8 turns
- Most expensive single session: $4.57 (73 turns, 9.5 min)
- Total: $39.04 across 90.8 minutes of API time
- Drift checks cost ~25% of build cost but are essential for quality
Note: This excludes Run 1 (Opus) which has no cost-log entry. Opus would be significantly more expensive per feature.

### Finding #33: design.md has good learnings but nothing about server/client boundary
design.md is 82 lines of useful UI patterns (grid layouts, tabs, avatars, responsive design). Zero mention of the server/client component distinction that caused the map page bug. This is a classification gap — the agent captured the UI patterns but not the architectural pattern (where dynamic imports belong).
Fix: Same as #26 — update learnings with the complete server/client boundary pattern.


## Findings from Batch 4 (branch archaeology + stash analysis)

### Finding #34: Run 3a built 3 features that were never merged
9 unmerged branches in stakd. Three have real drift-reconciled work:
- auto/chained-20260225-082932: CompStak API integration
- auto/chained-20260225-084204: Dark Mode Toggle  
- auto/chained-20260225-090335: User settings & profile edit
These are features 23-25 from run 3a. They completed successfully (drift reconciled) but the crash at feature 26 prevented the merge cascade. Run 3b rebuilt all three from scratch.
Waste: ~$9.42 (3 × $3.14 avg build cost) — the original builds + the rebuilds.

### Finding #35: Feature 26 crash created 6 rapid-retry branches
6 branches all pointing to commit 153f75b ("chore: start feature #26 - Social links"):
- auto/chained-20260225-092241 through -094223 (4 branches in 2 minutes)
- Plus auto/chained-20260225-094148 and -103319
Confirms finding #18 (rapid branch creation). The loop created a new branch per retry attempt, all from the same starting commit.

### Finding #36: Stash confirms partial feature 26 work exists
`stash@{0}: On auto/chained-20260225-094223: partial feature 4 work` — mislabeled as "feature 4" but on a feature-26 branch. This is the work-in-progress that was lost when run 3a crashed. Could potentially be applied to avoid rebuilding, but run 3b already rebuilt it.

---

## Synthesis: Prioritized Remediation

### P0 — Must fix before next build campaign

1. **Commit resume.json on each feature completion** (findings #17, #28, #34)
   Impact: $9.42 wasted on stakd alone. Any crash loses all progress since last merge.
   Fix: `git add .sdd-state/resume.json && git commit -m "state: checkpoint"` after each feature merge.

2. **Framework-specific rules in CLAUDE.md** (findings #3, #12, #25, #26, #33)
   Impact: Root cause of the cascade 500 bug that took down all routes.
   Fix: Add Next.js 15 section to CLAUDE.md covering: server/client boundary, dynamic import pattern (client wrapper, not "use client" on page), metadata exports (server only), cookies/headers imports (server only).

3. **Merge latest build-loop fixes before launching campaigns** (finding #29)
   Impact: All 3 stakd runs used a script version without credit exhaustion detection.
   Fix: Process checklist — verify `git log --oneline main | head -5` shows expected fixes before starting.

### P1 — Should fix, prevents significant waste

4. **Codebase summary injection between features** (findings #11, #21, #23)
   Impact: Each agent builds blind. Same bugs fixed twice. Type conflicts by luck not design.
   Fix: Generate codebase-summary.md after each feature (component registry, type manifest, import graph). Already identified in ONBOARDING.md as next priority.

5. **Minimum retry delay + branch reuse on retry** (findings #2, #18, #35)
   Impact: 6 orphan branches from 2 minutes of retries. 84 wasted API calls in 12 minutes.
   Fix: 30-second minimum between retries. Reuse branch on retry instead of creating new one.

6. **Capture learnings for security, architecture, framework patterns** (findings #22, #27, #33)
   Impact: 7+ auth features built with zero security learnings captured. No architectural patterns in design.md.
   Fix: Add post-build learning extraction step, or at minimum populate security.md and add architecture section to design.md from the stakd campaign.

### P2 — Nice to have, reduces maintenance burden

7. **Branch cleanup after campaign** (findings #19, #35)
   Impact: 39 local branches (29 merged, 9 unmerged with stale work, 1 main). Noise.
   Fix: `git branch --merged main | grep -v main | xargs git branch -d` after each campaign.

8. **Per-project .env or documented CLI overrides** (findings #30, #31)
   Impact: Build settings not reproducible. Only Brian knows the exact command used.
   Fix: Either stakd/.env.build or document the override command in the campaign log.

9. **Build log capture for all runs** (finding #20)
   Impact: Only run 1 had a build.log. Forensics for runs 2-3 relied on git + cost-log.
   Fix: `tee` to timestamped log file. Already in the script but not used consistently.

10. **Cost-log for Opus runs** (finding #32)
    Impact: Run 1 (Opus) has no cost data. Can't compare Opus vs Haiku cost/quality.
    Fix: Ensure claude-wrapper.sh is in the PATH for all runs.

### Not fixing (acceptable risk)

- **Stash recovery** (#36): Run 3b already rebuilt the work. Stash is forensic only.
- **Model switching docs** (#14): Low priority, Brian controls this manually.

---

## Investigation Complete

**36 findings** across 4 batches:
- Batch 1 (findings 1-16): build.log, cost-log, git log, prior chat transcripts
- Batch 2 (findings 17-28): learnings files, CLAUDE.md audit, prior chat deep dive  
- Batch 3 (findings 29-33): config audit, cost analysis, design.md
- Batch 4 (findings 34-36): branch archaeology, stash analysis, unmerged work

**Root cause chain for cascade 500s**: Agent pattern confusion (#3) → "use client" + server imports on map page (#12) → webpack module graph poisoned (#4) → all routes 500. Enabled by: no Next.js rules in CLAUDE.md (#25), incomplete learnings (#26), no codebase summary (#23).

**Total identified waste**: ~$15+ (credit exhaustion retries + rebuilt features + Opus run without cost tracking)

**Existing failure catalog** (PROMPT-ENGINEERING-GUIDE.md) has 16 entries covering agent behavior patterns. Zero overlap with the 36 build loop findings — these are complementary. The existing catalog covers "what agents do wrong in single prompts." This investigation covers "what goes wrong in multi-hour autonomous campaigns."
