# How I Work with Generative AI

> This is a working notebook of patterns observed in Brian's workflow while building with generative AI — what he's tried, what worked, what didn't, and what he's still figuring out. These aren't rules or best practices. They're high-signal observations from one person's approach. Take what's useful, ignore what isn't.
>
> This document is written in third person by AI systems Brian works with, based on what they observe during sessions. Brian curates and edits as he sees fit. First-person voice is reserved for content Brian writes directly.

---

## Accumulation

Raw captures from checkpoint scans. Brian prunes and curates into sections above as the document matures.

- (2026-03-01) Brian prefers not to embed specific counts, line numbers, or other volatile metrics in documentation — especially human-facing docs like READMEs — because work moves fast and these numbers don't get updated. Structure descriptions age better than snapshot metrics.
- (2026-03-01) Brian draws a sharp distinction between "AI" (the broader field, including his ML background) and "Generative AI" (LLM and agent tooling specifically). These are not interchangeable terms in his usage.
- (2026-03-01) Brian favors capture-biased systems over precision-biased ones. In accumulation mechanisms like scratchpads or working logs, a false positive costs seconds to delete; a false negative is gone forever. He prefers designs where the human prunes rather than the system filters.
- (2026-03-01) Brian gravitates toward high-leverage meta-tooling — a single command that replaces a fragile multi-step manual process — over incremental feature work. The checkpoint command emerged from this pattern.
- (2026-03-01) Brian keeps unproven concepts out of public-facing documentation. README reflects what works, not what's planned. Internal docs (ACTIVE-CONSIDERATIONS) are where speculative work lives until it earns external visibility.
- (2026-03-01) Brian does not want AI systems writing in first person on his behalf. Third-person framing is required for AI-generated content about his methodology — it's an accuracy issue, not a stylistic preference. First person misrepresents authorship.
- (2026-03-01) Brian treats meta-work (tooling, organization, process design) as legitimate investment but gates it behind productive output. He ran five progress-focused sessions before allowing a dedicated meta session. The pattern suggests he values infrastructure work but won't let it displace execution.
- (2026-03-01) Context window pressure is an open concern. Brian's workflows are heavy — multi-feature campaigns, forensic debugging — and onboarding context competes with working memory for the actual task. The question of what a fresh chat *needs* to read vs. what's practical remains unresolved. Tiered onboarding, lazy loading, and hard caps on ONBOARDING.md size are all on the table.
