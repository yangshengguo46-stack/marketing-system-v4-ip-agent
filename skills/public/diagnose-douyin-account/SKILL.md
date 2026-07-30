---
name: diagnose-douyin-account
description: Diagnose a connected Douyin creator account when the user asks whether to keep it, adjust content, or start a new account. Uses owner-scoped content, funnel, conversion, recommendation-eligibility and official-platform evidence; never treats low views or folklore traffic-pool formulas as proof that the account is dead.
---

# Diagnose Douyin account

Use this only for a concrete Douyin account. Read
`references/platform-evidence.md` before interpreting platform mechanics.

## Workflow

1. Call `personal_ip_account_diagnostic_context` with the exact account id.
2. If `sample.decision_ready` is false, collect the missing current evidence
   with `personal_ip_collect_browser_page`. Prioritize `account_profile` or
   `dashboard`, `content_inventory`, `content_metrics`, `traffic_sources`,
   `audience_analytics`, `comments` and `conversions`. Re-read the context.
3. Diagnose content first, in this order:
   `processing_access`, `attention_prediction`, `emotion_identity`,
   `narrative_consumption`, `social_transmission`, `behavior_conversion`.
   Test observable behavior; never present dopamine, mirror neurons or the
   Zeigarnik effect as measured causes.
4. Diagnose `reach -> trust -> intent -> conversion`. Missing data stays
   `unmeasured`; zero is valid only when the platform evidence explicitly
   observed zero.
5. Diagnose Douyin distribution separately: recommendation eligibility,
   content duplication/originality, community-rule status, traffic sources and
   audience fit. Official public descriptions support interaction and viewing
   signals, diversification and exploration—not a fixed traffic-pool ladder or
   current signal weights.
6. Set `platform_role` to `constraint_and_amplifier`, then call
   `personal_ip_compile_account_diagnosis` with the complete assessment.

## Decision discipline

- Prefer `adjust_and_retest` for weak content mechanisms or a failed funnel.
- Use `continue_current_account` only with an observed trust, intent or
  conversion signal and no active recommendation restriction.
- Use `start_new_account` only with platform-observed structural evidence.
  Low views, an old account, slow follower growth or one failed post is
  insufficient.
- Use `self_entertainment` only in monetization-first mode after at least three
  distinct measured posts and complete commercial-outcome coverage observed
  within the last 30 days show both intent and conversion failure. Describe
  the operating gap directly without insulting the user.

Return the decision first, then the content diagnosis, platform constraint,
evidence coverage and one controlled three-or-more-post experiment.
