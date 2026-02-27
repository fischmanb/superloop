# Spec Authoring Learnings

Patterns from drift reconciliation during stakd campaigns. These are spec-side mistakes — cases where the spec was wrong or overspecified, not where the code drifted.

---

## Don't hardcode UI casing in Gherkin

Spec said `"FOR SALE"` / `"FOR LEASE"` (all caps). Code renders `"For Sale"` / `"For Lease"` (title case). Casing is a rendering decision — specs should describe the semantic label, not the exact string casing.

## Don't overspecify filter mechanics when UX constrains input

Spec described state/city filtering as "case-insensitive partial match via ILIKE" (implying wildcards). Code does exact case-insensitive matching because values come from dropdowns — no free-text input means no wildcard need. Describe the user-facing behavior, not the SQL implementation.

## Don't embed exact UI copy in scenarios

Spec said `"Page X of Y (Z results)"`. Component outputs `"Page X of Y (Z deals)"`. UI copy is owned by the component, not the spec. Describe pagination behavior ("shows current page, total pages, and result count") rather than exact strings.

## Use precise DB types

Spec listed `timestamp`. Drizzle schema uses `timestamp with timezone`. Use the actual type precision the ORM/DB requires — shorthand creates false drift signals.

---

_Source: stakd-v2 campaign, listings-page feature drift reconciliation (2026-02-27). 4 spec-side fixes, 0 code changes, 112/112 tests passing._
