# Campaign Report: stakd-v2 (Sonnet)

## Summary

| Metric | Value |
|---|---|
| Model | claude-sonnet-4-6 (Haiku 4.5 sidecar for evals) |
| Features built | 24 / 28 |
| Build window | 10:54 – 16:50 EST (5.9h) |
| Throughput | 4.0 features/hour |
| Median feature time | 6.0 min |
| Mean feature time | 8.8 min |
| Min / Max (clean) | 2.6 min / 53.5 min |
| Outliers (>60m) | 1 |
| Total API cost (logged) | $1.73 |
| Cost per feature | $0.07 |
| Drift reconciliations | 17 / 24 (71%) |

## Notes

- Campaign initialized 2026-02-26 16:10 EST (spec file init)
- Build loop started 2026-02-27 ~10:48 EST
- Cost log only captures sidecar eval sessions (Haiku), not primary Sonnet build agent
- Build logs exist but in deleted inodes (tee PIDs still open) — lost when campaign stops
- No sidecar evals for v2 campaign (sidecar not configured)

## Feature Build Log

| # | Time | Duration | Feature |
|---|---|---|---|
| 1 | 10:54 | 1124.4m ⚠️ | feat(foundation): project setup — Next.js 15, Tailwind, Drizzle, env |
| 2 | 11:01 | 4.5m | feat(layout): core layout shell — header, nav, mobile menu, footer |
| 3 | 11:09 | 6.6m | feat(auth): sign up — users table, bcrypt hashing, JWT session, API +  |
| 4 | 11:16 | 4.0m | feat(auth): log in — login API, LoginForm, page, 10 tests |
| 5 | 11:23 | 5.0m | feat(db): deal model & database schema — deals + deal_participants tab |
| 6 | 11:29 | 2.8m | feat(db): agent/user profile model & schema — agent_profiles table, 9  |
| 7 | 11:38 | 6.4m | feat(landing): landing page — hero, search bar, market filters, trendi |
| 8 | 12:33 | 53.5m ⚠️ | feat(ui): dark mode toggle — ThemeProvider, anti-FOUC, localStorage pe |
| 9 | 12:39 | 3.3m | feat(social): social links in footer + ShareButton component (#26) |
| 10 | 12:45 | 4.2m | feat(marketing): email newsletter signup in footer (#27) |
| 11 | 12:55 | 6.5m | feat(auth): session management & protected routes (#5) |
| 12 | 13:02 | 3.3m | feat(deals): Deal card component (status, image, amount, participants) |
| 13 | 13:16 | 11.2m | feat(news): News section / industry news feed (#19) |
| 14 | 13:28 | 7.6m | feat(deals): Deals list page (feed, filters, pagination) (#9) |
| 15 | 13:42 | 9.0m | feat(deals): Submit deal form & flow (#14) |
| 16 | 15:08 | 85.9m ⚠️ | feat(settings): User settings & profile edit (#25) |
| 17 | 15:19 | 4.8m | feat(agents): Agent profile page (#15) |
| 18 | 15:28 | 5.5m | feat(deals): Deal detail page (#10) |
| 19 | 15:36 | 4.7m | feat(deals): Market/submarket filters — neighborhood dropdown (#12) |
| 20 | 15:47 | 6.9m | feat(deals): Search (address, advanced filters) (#13) |
| 21 | 16:02 | 11.2m | feat(rankings): Rankings page — top brokers, investors, lenders (#16) |
| 22 | 16:29 | 22.3m | feat(listings): Listings page — active for-sale/for-lease (#17) |
| 23 | 16:43 | 7.7m | feat(map): Map view — deal locations, gated for logged-in (#18) |
| 24 | 16:50 | 2.6m | feat(trending): Trending deals (homepage) — #21 |

⚠️ = >30 min (likely retry or stuck agent)

## Cost Log Entries

- 2026-02-27T21:50:30Z: $1.21 (32 turns, 168s)
- 2026-02-27T21:51:44Z: $0.52 (16 turns, 72s)
