---
name: diagnose-instagram-account
description: Diagnose a connected Instagram account from content, audience behavior, recommendation eligibility and conversion evidence. Use when the user asks whether to continue, adjust Reels or other formats, repair eligibility, or create a structurally separate account.
---

# Diagnose Instagram account

Use this only for a concrete Instagram account. Read
`references/platform-evidence.md` first.

## Workflow

1. Call `personal_ip_account_diagnostic_context`.
2. If the sample is not decision-ready, collect current Account Status or
   `account_profile`, `dashboard`, `content_inventory`, `content_metrics`,
   `traffic_sources`, `audience_analytics`, `comments` and `conversions`; then
   re-read context.
3. Diagnose the six content layers before platform distribution. Evaluate
   comprehension, promise, identity/emotion, consumption, sends/shares and
   behavior/conversion as observable mechanisms.
4. Diagnose `reach -> trust -> intent -> conversion`; do not treat likes or
   follows as purchases.
5. Diagnose Feed, Stories, Explore and Reels as distinct surfaces. Account
   Status and recommendation eligibility are structural evidence: eligibility
   permits recommendation but never guarantees it. Inspect originality and
   negative feedback without inventing weights.
6. Set `platform_role` to `constraint_and_amplifier`, then compile with
   `personal_ip_compile_account_diagnosis`.

## Decision discipline

Low reach alone cannot trigger a new account. If content or funnel evidence
fails while the account remains eligible, use `adjust_and_retest`. Repair an
active restriction when possible. Start a new account only when current
platform evidence proves a persistent structural problem. `self_entertainment`
requires monetization-first intent, at least three distinct measured posts,
complete commercial-outcome coverage observed within the last 30 days and
failed intent plus conversion.

Return the decision first, then content, surface/eligibility constraint,
coverage and one controlled experiment.
