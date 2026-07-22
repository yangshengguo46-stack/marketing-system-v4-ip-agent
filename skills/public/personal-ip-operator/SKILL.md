---
name: personal-ip-operator
description: "Operate a creator or personal-IP account end to end: account scope, research, positioning, topic selection, scripts, visual assets, video production, publishing preparation, receipts, and retrospective learning."
license: MIT
---

# Personal IP operator

Treat this as an agent operating an account, not a content-generation app.
DeerFlow owns planning and execution; the account record is the business truth.

## Establish portfolio and operation scope

Treat the authenticated user's full portfolio as the conversation scope. Never
bind a conversation, toolset or answer to one account. Compare and aggregate
all relevant accounts when the request is global. Select an account and
platform only as the target of a concrete operation such as publishing,
spending, messaging, computer control or post-level metric collection. Reuse
facts already present in user memory and ask only for a missing fact that
materially changes that operation.

Minimum account card:

```yaml
account_id: stable-slug
platform: douyin | xiaohongshu | bilibili | wechat_channels | other
display_name: ""
operator: ""
promise_to_audience: ""
primary_audience: ""
content_pillars: []
voice_and_boundaries: []
business_goal: ""
```

Do not infer clinical, personality or philosophical diagnoses. If the user has
their own audience, motivation, Jungian or needs model, consume its exported
facts through a Tool/MCP; do not recreate that model in prompts.

## Work loop

1. Determine whether the request is portfolio-wide or a concrete account operation; never infer an account restriction for a global request.
2. Inspect evidence before strategy: prior content, comments, metrics, source
   documents and competitor examples.
   After browser login, collect the creator backend as deeply as the requested
   operation needs: account/content inventories, per-post performance, audience
   analytics, traffic sources, comments, conversions and platform receipts.
   Preserve source URL, observed-at time, pagination/coverage and raw
   screenshot/field evidence. Chromium and server connectors may use credentials
   internally; their raw cookie/token/password values must not enter model
   context, while the returned operating data should.
   For performance questions, use the native portfolio inventory, sync and
   aggregate tools; preserve their missing/partial coverage instead of treating
   absent data or a cumulative snapshot as today's total.
   Use `personal_ip_sync_douyin_portfolio` for recurring or whole-portfolio
   collection. A scheduled task should pass a stable current-hour collection
   key; never bake one account id into its prompt.
   For detailed Douyin creator-backend evidence, call
   `personal_ip_collect_douyin_browser_page` with the exact target account,
   stable observation key and dataset. It returns an immutable evidence
   reference plus summary/coverage; use `personal_ip_record_browser_observation`
   after manual Browser Control extraction on pages not yet handled directly.
3. Produce the smallest useful plan and label assumptions.
4. Route general research and creation through available Skills. Read
   `volcengine-stack` before any ByteDance media work.
5. Put irreversible or paid steps behind explicit approval: batch generation,
   publishing, deleting, account changes and sending messages.
   Platform operation is browser-first: call
   `personal_ip_select_browser_account` with the concrete target, then use
   DeerFlow Browser Control and UI-TARS only as needed. Account selection does
   not narrow the rest of the conversation. The user handles password, QR,
   CAPTCHA, MFA and identity prompts; never request those secrets in chat. A
   successful manual login closes its portfolio dialog automatically, while
   the persistent account profile remains available to later agent collection.
6. Produce an operation receipt that links decisions, assets and outputs.
7. After publication, distinguish observations from interpretations. Persist
   stable account facts to memory; keep raw evidence and receipts as artifacts.

## Content production

For video, keep each stage explicit even when the agent automates it:

`brief -> evidence -> script -> asset references -> storyboard -> clip jobs ->
quality check -> candidate selection -> voice/edit/finish -> approval -> delivery`

Seedream, Seedance and MediaKit perform generation and media operations. The
agent remains responsible for account fit, evidence, approvals, retries and
receipts.

## Output contract

Every completed operation should state:

- portfolio coverage, plus the target account/platform only for account-specific operations;
- objective and evidence used;
- decisions made and assumptions left;
- generated assets and provider receipts;
- approval/publish state;
- next measurable observation.

Do not claim a post was published, a computer action succeeded, or a cloud job
finished without a tool result that proves it.
