---
name: diagnose-wechat-channels-account
description: Diagnose a connected WeChat Channels account when deciding whether to continue, change content, or start over. Treats content and the reach-to-conversion funnel as primary, while current in-product WeChat evidence supplies only platform constraints and distribution context.
---

# Diagnose WeChat Channels account

Use this only for a concrete `wechat_channels` account. Read
`references/platform-evidence.md` before interpreting platform mechanics.

## Workflow

1. Call `personal_ip_account_diagnostic_context`.
2. If evidence is insufficient, collect current creator-backend
   `account_profile` or `dashboard`, `content_inventory`, `content_metrics`,
   `traffic_sources`, `audience_analytics`, `comments` and `conversions`, then
   re-read the context.
3. Diagnose the six content layers before platform distribution:
   processing access, attention/prediction, emotion/identity,
   narrative/consumption, social transmission and behavior/conversion.
4. Diagnose `reach -> trust -> intent -> conversion`. Keep an unavailable
   metric unmeasured.
5. Inspect Follow/Friends/Recommended or equivalent current traffic-source
   surfaces, sharing and recommendation eligibility only when the authenticated
   console proves them. Public WeChat material does not disclose current Video
   Accounts ranking weights. Do not convert older 看一看 engineering material
   into a Video Accounts formula or claim that friend interaction is the
   dominant current weight.
6. Set `platform_role` to `constraint_and_amplifier`, then compile with
   `personal_ip_compile_account_diagnosis`.

## Decision discipline

Weak performance normally means `adjust_and_retest`. Continue unchanged only
with a downstream trust, intent or conversion signal. Start a new account only
with platform-observed persistent restriction, audience-positioning lock,
identity/business conflict or unrecoverable compliance history. Low reach and
an old account never suffice.

For monetization-first work, `self_entertainment` requires at least three
distinct measured posts plus complete commercial-outcome coverage observed
within the last 30 days and explicit intent and conversion failures. Lead with
the decision and one controlled content experiment; present platform
mechanics as a constraint or amplifier, not the main thesis.
