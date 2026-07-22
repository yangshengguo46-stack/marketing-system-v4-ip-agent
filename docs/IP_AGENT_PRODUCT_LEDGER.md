# IP Agent product ledger

This ledger measures whether an ordinary customer can complete the Personal-IP
operating loop. It is deliberately stricter than source-code completion. A
schema, mocked test or configured model is not counted as a finished product
until its real execution path, evidence and user interaction are usable.

Last audited: 2026-07-22. The baseline audit began at commit `fd78208`; the
checkbox state also includes the current ledger change set.

## Current completion

**Weighted product completion: 63%.** The native agent and backend foundation
are about 78% complete; the lower product number reflects the unfinished
multi-platform data, publishing and user-facing operating loop.

| Ledger area | Weight | Complete | Current evidence | Completion gate still open |
|---|---:|---:|---|---|
| DeerFlow and Volcengine foundation | 10% | 90% | Native DeerFlow runtime; Doubao/Seedream/Seedance routing; vendored MediaKit source and project-local FFmpeg | Release-grade installer and a full paid-call acceptance run |
| Portfolio, accounts and browser login | 10% | 85% | Eight fixed platform entries; owner/account-isolated Chromium profiles; real Douyin login persisted across restart; automatic dialog close | Connected-state summaries and full eight-platform acceptance matrix |
| Persona/fan modelling and preflight | 20% | 60% | HLLM source pin; HLLM-Lite provider contract; aggregate audience adapter; immutable preflight receipt; personality/Maslow/Jung/existence lenses | Detailed real platform inputs, calibrated ranker and user-facing preflight workflow |
| Publishing and receipts | 15% | 55% | Immutable publish request, append-only attempts, terminal-status rules and account targeting | Real browser/API publisher executors across the eight platforms and recovery verification |
| Metrics, retrospectives and evidence promotion | 20% | 55% | Normalized observations; exact snapshot deltas; portfolio aggregate; Douyin official post collector; detailed browser-evidence contract; real persisted-login Douyin dashboard/content capture; immutable retrospective; human-gated evidence promotion | Extend detailed collection across Douyin sections and the other seven platforms, scheduled coverage and user-facing review |
| Video production | 15% | 60% | Seedance/Seedream generation Skills; Doubao Speech route; official MediaKit source/Skills; local FFmpeg toolchain | One accepted script-to-delivery orchestration with assets, shot retries, selection, continuity and delivery receipt |
| Product UI, packaging and acceptance | 10% | 50% | DeerFlow UI skin; Personal-IP portfolio page; login workspace; source-distribution bootstrap | Operating cockpit for preflight/receipts/results/evidence, clean-machine package test and customer onboarding |

Weighted score: `9 + 8.5 + 12 + 8.25 + 11 + 9 + 5 = 62.75`, displayed as 63%.

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

### P0 — close the real operating-data loop

- [x] Add one versioned, platform-neutral browser observation/evidence contract.
- [x] Collect detailed authenticated Douyin creator data into that contract.
- [x] Expose the collector as a native DeerFlow portfolio tool without returning
      credentials or local profile paths.
- [x] Verify the collector against the existing real logged-in Douyin profile.
- [x] Reuse one account-isolated, credential-free direct collector across all
      eight platforms; keep unverified platform pages explicitly partial.
- [ ] Extend collection to WeChat Channels, WeChat Official Accounts and
      Xiaohongshu, then X, Instagram, YouTube and TikTok.

### P1 — execute and show the loop

- [ ] Connect real browser publishing attempts to the immutable receipt ledger.
- [ ] Add Personal-IP views for preflight, publication attempts, observed
      metrics, retrospective review and evidence approval.
- [ ] Run the full portfolio question acceptance case: “今天全平台浏览量多少？”
      The answer must report totals plus missing, partial and unavailable
      coverage instead of saying “不知道” or treating missing data as zero.

### P1 — finish video as a workflow, not only model calls

- [ ] Orchestrate script understanding, assets, storyboard, per-shot generation,
      consistency checks, retries, selection, dubbing/editing and delivery.
- [ ] Record paid task ids, costs, generated assets, chosen candidates, failures
      and final delivery as auditable receipts.
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
