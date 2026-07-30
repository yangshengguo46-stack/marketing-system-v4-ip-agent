---
name: diagnose-wechat-official-account
description: Diagnose a connected WeChat Official Account when the user asks whether it should continue, change direction, or restart. Evaluates article value, subscriber and sharing behavior, search and recommendation surfaces, and the full commercial funnel without inventing a universal WeChat ranking formula.
---

# Diagnose WeChat Official Account

Use this only for a concrete `wechat_official` account. Read
`references/platform-evidence.md` first.

## Workflow

1. Call `personal_ip_account_diagnostic_context`.
2. If evidence is insufficient, collect current `account_profile` or
   `dashboard`, `content_inventory`, `content_metrics`, `traffic_sources`,
   `audience_analytics`, `comments` and `conversions`; then re-read context.
3. Diagnose content mechanisms first: processing access, expectation and
   attention, identity/emotion, reading consumption, social transmission and
   behavior/conversion.
4. Diagnose `reach -> trust -> intent -> conversion`. Separate subscriber
   delivery, chat/Moments forwarding, Search and 看一看 or other recommendation
   surfaces when the console exposes them; they are not one funnel stage.
5. Use current in-product rule/status evidence for account eligibility.
   Tencent's public 看一看 ranking material supports recall/ranking/mixing and
   multi-objective signals for that surface only. It does not disclose current
   Official Account-wide weights.
6. Set `platform_role` to `constraint_and_amplifier`, then compile with
   `personal_ip_compile_account_diagnosis`.

## Decision discipline

Do not recommend a new account because open rate or follower growth is low.
Prefer a controlled adjustment to topic promise, title/cover, evidence,
structure, sharing utility or conversion path. Starting over requires
platform-observed structural evidence. In monetization-first mode, the
`self_entertainment` label requires at least three distinct measured
publications, complete commercial-outcome coverage observed within the last 30
days, and observed failure of both intent and conversion.

Return a direct keep/adjust/new-account conclusion, the content failure point,
surface-specific platform constraint, evidence gaps and the next experiment.
