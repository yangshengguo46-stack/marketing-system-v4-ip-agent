# IP Agent video production workbench handoff

Date: 2026-07-22

Branch: `parallel/video-workbench`

Baseline: `3e56b0a`

## Delivered

- Added the pure `personal-ip-video-workbench-v1` projection and an owner-scoped
  Gateway read endpoint derived from the existing immutable production ledger.
- Added the dedicated `/workspace/personal-ip/video` master-detail workbench
  for projects, nine stages, script/blueprint, assets, storyboard, tasks and
  retries, candidates and consistency, voice/timeline, delivery QA and receipt
  details.
- Kept creation, progression and recovery in DeerFlow conversations through the
  native begin/event/read tools. No second runtime, state machine, migration or
  mutable projection was introduced.
- Restricted workbench confirmations to candidate selection, real paid calls
  and real publishing. Evidence promotion remains automatic.
- Preserved provider/model/task id, cost state, failure category, attempt,
  `retry_of`, artifact/hash and QA evidence while stripping query/fragment data
  from displayed artifact references.
- Connected the read model to the receipt shape emitted by the existing free
  local video E2E.

## Reference provenance

Jellyfish commit `a9678194ddf2d9be3ccbe78d4287d87d5089e123`
(Apache-2.0) was inspected for project-lobby, tabbed-workbench, asset/task,
readiness and timeline information architecture. No Jellyfish code or assets
were copied into DeerFlow. The inspected paths are recorded in
`docs/VIDEO_WORKBENCH.md`.

## Verification

- Backend focused workbench/router tests: 7 passed.
- Related Personal-IP/video backend regression: 38 passed.
- Frontend unit suite: 702 passed.
- Frontend ESLint and TypeScript: passed.
- Production build: passed.
- Relevant Personal-IP Playwright acceptance on Chromium: 2 passed (portfolio
  plus video workbench).
- Browser-controlled desktop inspection: 1440×900; heading, task tab and
  `provider_timeout` recovery evidence verified.
- Free local video E2E: passed twice with the same production id, 11 events,
  final SHA256 and zero paid calls. The second run re-hashed and resumed all
  successful receipts without duplicating events.

Local acceptance result:

```text
production_id: video-production-257e248b609145a48450dd924fd35072
status/current_stage: completed/delivery
event_count: 11 on both runs
finisher: ffmpeg
qa_passed: true
paid_calls_executed: 0
final size: 42081 bytes
final sha256: c9289f71072fda815941a0c47e4e8efbbebaa3813b0896c5a6c9367870d8f9e8
```

The broader Playwright suite was also attempted. Its unrelated legacy chat,
landing and mobile-sidebar assertions still look for the upstream DeerFlow
placeholder/welcome/brand strings, while this branch intentionally renders the
IP Agent copy (for example, “Name the account, platform, and outcome…”). The
run was stopped after 82/105 cases; this workbench did not change those pages.
The scoped Personal-IP suite above is clean.

Screenshot deliverable:
`outputs/video-workbench-1440x900.png` in the Codex task output directory.

## Real API acceptance still required

No paid Seedream, Seedance, speech or cloud MediaKit request was made. With an
explicit approval in a future active user session:

1. Inspect the generated paid checkpoints and authorize the exact call count.
2. Execute one Seedream asset request and ingest its authoritative receipt.
3. Execute one Seedance shot request, including a real failed/retried task if
   available, and verify provider task id, cost state and `retry_of` in the
   workbench.
4. Execute one Doubao Speech request and verify its voice/timeline receipt.
5. Prefer local MediaKit finishing; use cloud MediaKit only if separately
   approved, then verify final artifact hash and exact-output delivery QA.
6. Exercise a real publish confirmation only after the authenticated platform
   page proves the final public URL.

Every provider result must be ingested through the existing event/receipt
pipeline. Do not reconstruct receipts from console text or expose credentials.
