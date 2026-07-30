---
name: diagnose-tiktok-account
description: Diagnose a connected TikTok account using content behavior, For You eligibility, audience and conversion evidence. Use when deciding whether to continue, adjust content, repair recommendation eligibility, or create a structurally separate account.
---

# Diagnose TikTok account

Use this only for a concrete TikTok account. Read
`references/platform-evidence.md` first.

## Workflow

1. Call `personal_ip_account_diagnostic_context`.
2. If the sample is not decision-ready, collect current `account_profile` or
   `dashboard`, `content_inventory`, `content_metrics`, `traffic_sources`,
   `audience_analytics`, `comments` and `conversions`; then re-read context.
3. Diagnose the six content layers before distribution: comprehension,
   expectation and attention, identity/emotion, consumption, social
   transmission and behavior/conversion.
4. Diagnose `reach -> trust -> intent -> conversion`; full watch, likes or
   follows do not automatically prove purchase intent.
5. Diagnose For You eligibility, originality/duplicate status, disclosed
   commercial content, traffic sources and audience fit separately. TikTok's
   official descriptions identify interaction, content and lower-weight device
   signals plus diversity and safety controls, but current weights are not
   public.
6. Set `platform_role` to `constraint_and_amplifier`, then compile with
   `personal_ip_compile_account_diagnosis`.

## Decision discipline

Low views, follower count and prior viral history are not sufficient reasons
to abandon an account. Prefer `adjust_and_retest` for content or funnel
failure, and repair eligibility where possible. Start a new account only with
current platform-observed structural evidence. In monetization-first mode,
`self_entertainment` requires at least three distinct measured posts and
complete commercial-outcome evidence observed within the last 30 days showing
both intent and conversion failure.

Lead with the direct decision, then content diagnosis, eligibility/distribution
constraint, evidence coverage and one controlled experiment.
