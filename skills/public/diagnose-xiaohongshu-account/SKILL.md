---
name: diagnose-xiaohongshu-account
description: Diagnose a connected Xiaohongshu account from note quality, search and recommendation behavior, saves, shares, audience intent and conversion evidence. Use when deciding whether to continue, adjust positioning or content, or start a structurally separate account.
---

# Diagnose Xiaohongshu account

Use this only for a concrete Xiaohongshu account. Read
`references/platform-evidence.md` first.

## Workflow

1. Call `personal_ip_account_diagnostic_context`.
2. If the sample is not decision-ready, collect `account_profile` or
   `dashboard`, `content_inventory`, `content_metrics`, `traffic_sources`,
   `audience_analytics`, `comments` and `conversions`, then re-read context.
3. Diagnose the six content layers first. Inspect whether the note is easy to
   process, creates a specific expectation, matches an identity/problem,
   sustains consumption, gives save/share/search value and creates a credible
   next action.
4. Diagnose `reach -> trust -> intent -> conversion`; do not equate saves with
   a sale or comments with buying intent.
5. Diagnose platform distribution separately: current recommendation/rule
   eligibility, search query fit, title-cover-content consistency, originality,
   information density and traffic sources. Official filings support use of
   content and interaction signals plus deduplication, diversity and interest
   exploration; they do not publish current weights.
6. Set `platform_role` to `constraint_and_amplifier`, then compile with
   `personal_ip_compile_account_diagnosis`.

## Decision discipline

Low exposure alone means neither “bad account” nor “shadowban.” Prefer
`adjust_and_retest` when promise, specificity, proof, save/share utility,
search fit or conversion path fails. Start a new account only with observed
structural evidence, not because old notes were mediocre. `self_entertainment`
requires monetization-first intent, at least three distinct measured posts,
complete commercial-outcome coverage observed within the last 30 days and
both intent and conversion failure.

Return the direct decision first and prescribe one content-controlled,
same-platform experiment of at least three posts.
