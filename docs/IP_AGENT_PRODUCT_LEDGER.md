# IP Agent product ledger

This ledger measures whether an ordinary customer can complete the Personal-IP
operating loop. It is deliberately stricter than source-code completion. A
schema, mocked test or configured model is not counted as a finished product
until its real execution path, evidence and user interaction are usable.

Last audited: 2026-07-22. The baseline audit began at commit `fd78208`; the
checkbox state also includes the current ledger change set.

## Current completion

**Weighted product completion: 71%.** The native agent and backend foundation
are about 83% complete; the lower product number reflects the deliberately
deferred eight-platform acceptance work, unfinished real publishing and the
absence of one accepted paid video production.

| Ledger area | Weight | Complete | Current evidence | Completion gate still open |
|---|---:|---:|---|---|
| DeerFlow and Volcengine foundation | 10% | 90% | Native DeerFlow runtime; Doubao/Seedream/Seedance routing; vendored MediaKit source and project-local FFmpeg | Release-grade installer and a full paid-call acceptance run |
| Portfolio, accounts and browser login | 10% | 85% | Eight fixed platform entries; owner/account-isolated Chromium profiles; real Douyin login persisted across restart; automatic dialog close | Connected-state summaries and full eight-platform acceptance matrix |
| Persona/fan modelling and preflight | 20% | 65% | HLLM source pin; HLLM-Lite provider contract; aggregate audience adapter; immutable preflight receipt; native agent tool and detailed receipt view; personality/Maslow/Jung/existence lenses | Detailed real platform inputs and calibrated ranker |
| Publishing and receipts | 15% | 70% | Immutable publish request; append-only attempts; atomic browser prepare/finish tools; selected-profile binding; live public-post URL/id verification across eight platform domains | Eight-platform end-to-end execution and recovery verification; official API publishers where available |
| Metrics, retrospectives and evidence promotion | 20% | 65% | Normalized observations; exact snapshot deltas; portfolio aggregate; Douyin official post collector; detailed browser-evidence contract; real persisted-login Douyin capture; immutable retrospective; policy-gated automatic evidence promotion | Extend detailed collection across the other seven platforms and scheduled coverage |
| Video production | 15% | 72% | Seedance/Seedream/Doubao Speech scripts emit one credential-free executor receipt with task/request ids and checksummed outputs; MediaKit/FFmpeg have a verified execution wrapper; native ingestion derives immutable stage events; nine-stage production ledger remains provider-independent | Exercise the paid providers and complete one accepted script-to-delivery production |
| Product UI, packaging and acceptance | 10% | 65% | DeerFlow UI skin; Personal-IP portfolio/login workspace; six-stage operating cockpit; detailed read-only receipt/evidence views; nine-stage video-line status; source-distribution bootstrap | Clean-machine package test and customer onboarding |

Weighted score: `9 + 8.5 + 13 + 10.5 + 13 + 10.8 + 6.5 = 71.3`, displayed as 71%.

## Product truth

The only product-owned loop is:

`persona/fan model -> preflight -> publish receipt -> observed outcome -> retrospective -> evidence promotion`

Video production is the second product workflow. Agent runtime, browser,
computer use, memory, Skills, MCP and generation/media primitives should remain
native DeerFlow or ByteDance/Volcengine capabilities with the thinnest product
adaptation possible.

A conversation always has authority to coordinate the authenticated user's
complete portfolio. An account id selects the exact target of one operation; it
must never become a conversation filter.

Raw passwords, cookies and access/refresh tokens never enter model context.
That boundary does not limit authorized business-data collection: account and
content inventories, post metrics, audience analytics, traffic sources,
comments, conversions and platform receipts should be collected as completely
as the creator backend permits, with source, observation time, pagination and
coverage evidence.

## Delivery queue

### Deferred acceptance — platform login and real operating data

- [x] Add one versioned, platform-neutral browser observation/evidence contract.
- [x] Collect detailed authenticated Douyin creator data into that contract.
- [x] Expose the collector as a native DeerFlow portfolio tool without returning
      credentials or local profile paths.
- [x] Verify the collector against the existing real logged-in Douyin profile.
- [x] Reuse one account-isolated, credential-free direct collector across all
      eight platforms; keep unverified platform pages explicitly partial.
- [ ] During final end-to-end acceptance, extend verified collection to WeChat
      Channels, WeChat Official Accounts and Xiaohongshu, then X, Instagram,
      YouTube and TikTok. Do not let this block the product framework phase.

### P1 — execute and show the loop

- [x] Add one owner-scoped operating cockpit shared by the Gateway, user
      workspace and native DeerFlow tool. It joins all six business stages,
      exposes explicit queues and never filters conversation scope by account.
- [x] Bind Browser Control publication to an immutable pending receipt and
      require a live selected-platform post URL/id before sealing success.
- [x] Show the six-stage operating line and pending counts in the Personal-IP
      workspace.
- [x] Add detailed read interactions for preflight, publication attempts,
      observed metrics, retrospectives and automatically promoted evidence.
- [ ] Run the full portfolio question acceptance case: “今天全平台浏览量多少？”
      The answer must report totals plus missing, partial and unavailable
      coverage instead of saying “不知道” or treating missing data as zero.

### P1 — finish video as a workflow, not only model calls

- [x] Establish the provider-independent request and nine-stage orchestration
      contract for script understanding, assets, storyboard, per-shot
      generation, consistency, selection, finishing and delivery.
- [x] Persist provider/model/task ids, costs, artifacts, failures, retries,
      human decisions and final delivery as idempotent append-only receipts.
- [x] Expose owner-scoped begin/event/read tools natively to DeerFlow and show
      the production line in the Personal-IP cockpit.
- [x] Bind Seedance, Seedream and speech scripts plus MediaKit/FFmpeg execution
      to one verified receipt contract and native ingestion tool.
- [ ] Exercise real paid Seedance, Seedream, speech and cloud MediaKit calls and
      preserve their returned identifiers and artifacts in the production.
- [ ] Complete one real Seedance-to-MediaKit/FFmpeg acceptance production.

### P2 — customer delivery

- [ ] Build and verify a clean-machine source installation package.
- [ ] Add first-run diagnostics for model keys, optional paid MediaKit,
      Chromium profiles and platform capability availability.
- [ ] Complete an eight-platform login/restore/collect/publish acceptance matrix.

## Counting rules

- `done`: a real path was exercised and produces durable evidence.
- `implemented`: code and tests exist but the product acceptance gate remains.
- `configured`: capability routing exists; no end-to-end credit is implied.
- Optional official APIs improve scale but do not block browser-first use.
- Percentages change only when an open gate above is closed or newly discovered
  product scope is explicitly added to this ledger.
