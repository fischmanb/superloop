# Learnings Index

Cross-cutting patterns learned in this codebase. Updated via `/compound`.

## Quick Reference

| Category | File | Summary |
|----------|------|---------|
| Testing | [testing.md](./testing.md) | Mocking, assertions, test patterns |
| Performance | [performance.md](./performance.md) | Optimization, lazy loading, caching |
| Security | [security.md](./security.md) | Auth, cookies, validation |
| API & Data | [api.md](./api.md) | Endpoints, data handling, errors |
| Design System | [design.md](./design.md) | Tokens, components, accessibility |
| General | [general.md](./general.md) | Other patterns |
| Agent Operations | [agent-operations.md](./agent-operations.md) | Process lessons, failure catalog, session discipline |

---

## Recent Learnings

<!-- /compound adds recent learnings here - newest first -->

### 2026-02-26 — stakd features 1-28 campaign audit
- **Performance**: Browser-dependent lib loading via `dynamic(ssr: false)` must use client wrapper component pattern (performance.md)
- **General**: Next.js 15 server/client boundary rules, params-as-Promise, Drizzle schema exports (general.md)
- **Design**: Auth gate teasers, URL-synced tabs, responsive layout patterns, avatar fallbacks (design.md)
- **Security**: HMAC session tokens, cookie config, bcrypt timing resistance, edge middleware auth, secrets management (security.md)

---

## How This Works

1. **Feature-specific learnings** → Go in the spec file's `## Learnings` section
2. **Cross-cutting learnings** → Go in category files below
3. **General patterns** → Go in `general.md`

The `/compound` command analyzes your session and routes learnings to the right place.
