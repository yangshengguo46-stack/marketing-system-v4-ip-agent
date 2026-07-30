---
name: diagnose-x-account
description: Diagnose a connected X account when deciding whether to keep it, revise content and network strategy, or start a separate account. Uses current X recommendation eligibility and open-source system evidence without confusing engagement ranking with universal content quality.
---

# Diagnose X account

Use this only for a concrete X account. Read
`references/platform-evidence.md` first.

## Workflow

1. Call `personal_ip_account_diagnostic_context`.
2. If evidence is insufficient, collect current `account_profile` or
   `dashboard`, `content_inventory`, `content_metrics`, `traffic_sources`,
   `audience_analytics`, `comments` and `conversions`; re-read context.
3. Diagnose content first: immediate comprehension, expectation gap,
   identity/emotion, thread or video consumption, reply/repost/quote utility
   and the next action.
4. Diagnose `reach -> trust -> intent -> conversion`. Replies, reposts and
   profile visits are not automatically commercial intent.
5. Diagnose platform distribution separately: recommendation eligibility,
   Following versus For You surfaces, in-network versus out-of-network
   retrieval, conversation/network fit, freshness and negative feedback.
   X's current open-source repository describes candidate and ranking
   architecture, not a guaranteed formula or stable public weights.
6. Set `platform_role` to `constraint_and_amplifier`, then compile with
   `personal_ip_compile_account_diagnosis`.

## Decision discipline

Do not declare an account dead from low impressions. Prefer
`adjust_and_retest` for weak ideas, packaging, proof, conversation fit or
conversion. Start a new account only when platform-observed structural
evidence proves that separation is necessary. In monetization-first mode,
`self_entertainment` requires three distinct measured posts, complete
commercial-outcome coverage observed within the last 30 days, and measured
intent plus conversion failure.

Lead with keep/adjust/new account, then content diagnosis, platform constraint,
coverage and one controlled experiment.
