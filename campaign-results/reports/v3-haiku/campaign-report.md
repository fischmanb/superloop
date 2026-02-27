# Campaign Report: stakd-v3 (Haiku 4.5)

## Summary

| Metric | Value |
|---|---|
| Model | claude-haiku-4-5-20251001 |
| Features built | 11 / 28 |
| Build window | 13:11 – 16:04 EST (2.9h) |
| Throughput | 3.8 features/hour |
| Median feature time | 7.4 min |
| Mean feature time | 10.0 min |
| Min / Max (clean) | 3.8 min / 34.9 min |
| Outliers (>60m) | 0 |
| Total API cost (logged) | $0.89 |
| Cost per feature | $0.08 |
| Drift reconciliations | 8 / 11 (73%) |
| Sidecar evals | 3 eval JSONs |

## Notes

- Campaign initialized 2026-02-27 13:05 EST
- Build loop started 2026-02-27 ~13:08 EST
- Cost log captures all sessions (single model — Haiku for both build and eval)
- Build logs exist but in deleted inodes (tee PID still open)
- Sidecar evals captured for 3 features (partial — not all features triggered eval)
- Campaign still running at snapshot (11/28 complete)

## Feature Build Log

| # | Time | Duration | Feature |
|---|---|---|---|
| 1 | 13:11 | 5.2m | feat: implement project setup (feature #1) - Next.js, Tailwind, DB, en |
| 2 | 13:23 | 6.5m | feat: implement core layout (feature #2) - Header, Footer, MobileMenu |
| 3 | 13:29 | 3.8m | feat: implement auth sign up (feature #3) - registration form, API, da |
| 4 | 13:36 | 5.6m | feat: implement auth login (feature #4) - session management, API endp |
| 5 | 13:43 | 4.5m | feat: implement deal model & database schema (feature #6) |
| 6 | 15:07 | 34.9m ⚠️ | feat: implement agent profile model & database schema (feature #7) |
| 7 | 15:21 | 9.9m | feat: implement landing page with hero, search, and market filters (fe |
| 8 | 15:31 | 7.2m | feat: implement dark mode toggle (feature #24) |
| 9 | 15:44 | 11.2m | feat: implement social links feature (footer, share) #26 |
| 10 | 15:53 | 8.4m | feat: implement email newsletter signup in footer #27 |
| 11 | 16:04 | 7.6m | feat: implement Auth Session & protected routes #5 |

## Cost Log Entries

- 2026-02-27T20:57:55Z: $0.26 (4 turns, 54s)
- 2026-02-27T21:07:00Z: $0.42 (2 turns, 122s)
- 2026-02-27T21:07:59Z: $0.21 (4 turns, 27s)

## Sidecar Eval Summary

Three eval checkpoints captured:

1. **Email newsletter signup (footer)** — framework_compliance: warn, scope: focused, integration: minor_issues
   - Note: completed_features array omitted Social Links despite being built
2. **Auth Session & protected routes #5** — framework_compliance: warn, scope: focused, integration: minor_issues
   - Note: Header.tsx server component has invalid onClick handler (RSC error)
3. **Mark feature #5 complete** — framework_compliance: pass, scope: focused, integration: clean
   - Bookkeeping commit correctly separated from implementation
