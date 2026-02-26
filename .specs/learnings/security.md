# Security Learnings

Security patterns for this codebase.

---

## Authentication

### 2026-02-26 (stakd campaign audit)
- **Pattern**: Custom HMAC-SHA256 session tokens — `createSessionToken(userId)` produces `base64url(payload).hmac(payload)`. No JWT library dependency. Payload contains `{ userId, exp }`.
- **Pattern**: `verifySessionToken()` checks signature match AND expiration. Returns typed payload or null — callers null-check the result, never trust a bare token string.
- **Pattern**: Timing-safe comparison not used in dev — `signature !== expected` is vulnerable to timing attacks. Production should use `crypto.timingSafeEqual()`.

---

## Cookies & Tokens

### 2026-02-26 (stakd campaign audit)
- **Pattern**: Session cookie config: `httpOnly: true`, `secure: process.env.NODE_ENV === 'production'`, `sameSite: 'lax'`, `path: '/'`, `maxAge: 7 days`.
- **Pattern**: Login route uses pre-computed bcrypt dummy hash for timing-attack resistance — when email not found, still runs `bcrypt.compare(password, DUMMY_HASH)` so response time is constant regardless of user existence.
- **Pattern**: Logout deletes session cookie by setting `maxAge: 0`.

---

## Input Validation

<!-- Sanitization, validation libraries, patterns -->

_No learnings yet._

---

## API Security

### 2026-02-26 (stakd campaign audit)
- **Pattern**: API routes read session cookie directly — no bearer token pattern. Consistent with cookie-based auth model.
- **Pattern**: Registration hashes password with bcrypt before DB insert. Salt rounds via `bcrypt.hash(password, 10)`.

---

## Middleware Auth

### 2026-02-26 (stakd campaign audit)
- **Pattern**: Edge middleware reads session cookie, calls edge-compatible HMAC verification (Web Crypto `subtle.importKey` + `subtle.sign`, not Node.js `crypto`). Sets `x-user-id` header on authenticated requests.
- **Pattern**: Protected routes defined as path prefixes in middleware config. Unauthenticated requests to protected paths redirect to login.
- **Pattern**: Server pages call `cookies()` from `next/headers` to read session token, then `verifySessionToken()` to validate. Token never exposed to client JS.

---

## Secrets Management

### 2026-02-26 (stakd campaign audit)
- **Pattern**: Session secret in `.env.local` with obvious dev fallback (`'dev-secret-change-in-production'`). Production must override.
