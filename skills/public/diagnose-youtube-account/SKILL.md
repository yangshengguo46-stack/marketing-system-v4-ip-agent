---
name: diagnose-youtube-account
description: Diagnose a connected YouTube channel using content appeal, engagement, satisfaction, search and recommendation surfaces, audience intent and conversion evidence. Use when deciding whether the channel should continue, adjust formats, or be structurally separated.
---

# Diagnose YouTube account

Use this only for a concrete YouTube account. Read
`references/platform-evidence.md` first.

## Workflow

1. Call `personal_ip_account_diagnostic_context`.
2. If evidence is insufficient, collect current `account_profile` or
   `dashboard`, `content_inventory`, `content_metrics`, `traffic_sources`,
   `audience_analytics`, `comments` and `conversions`; then re-read context.
3. Diagnose content first. Map packaging and opening promise to appeal,
   consumption/retention to engagement, and expressed value or return behavior
   to satisfaction without pretending those are one-to-one causal metrics.
4. Diagnose `reach -> trust -> intent -> conversion`; subscribers and watch
   time alone are not commercial conversion.
5. Diagnose Home, Up Next, Shorts and Search separately. Use audience and
   per-video evidence, recommendation eligibility and current policy status.
   YouTube documents personalization and long-term viewer satisfaction, not a
   fixed universal ranking formula or a favored upload format.
6. Set `platform_role` to `constraint_and_amplifier`, then compile with
   `personal_ip_compile_account_diagnosis`.

## Decision discipline

One weak video or low channel views cannot justify starting over. Prefer
`adjust_and_retest` for packaging, promise delivery, retention, audience fit,
proof or conversion-path failures. Start a separate channel only with
platform-observed structural evidence such as an irreconcilable audience or
identity/business conflict. `self_entertainment` requires monetization-first
intent, at least three distinct measured videos, complete commercial-outcome
coverage observed within the last 30 days, and observed intent plus conversion
failure.

Return the decision first and specify one same-surface, content-controlled
experiment of at least three publications.
