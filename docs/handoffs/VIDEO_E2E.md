# IP Agent video script-to-delivery handoff

Date: 2026-07-22

Branch: `parallel/video-e2e`

Baseline: `439f3093297cedd5f1718704719708b1db18dba3`

## Delivered boundary

The Personal-IP video line now has one recoverable acceptance path from an
immutable script through blueprint, asset, storyboard, generation retry,
consistency, selection, speech, finishing, delivery QA and delivery. DeerFlow
remains the only agent runtime. Provider scripts and the official MediaKit CLI
are executors; the append-only Personal-IP production ledger remains the source
of truth.

`scripts/personal_ip_video_e2e.py` has two deliberately separate commands:

- `local` runs a fully free acceptance. Seedream, Seedance and speech responses
  are simulated with project-local FFmpeg, while their receipts carry realistic
  request/task/download/retry evidence. Final mux uses the source-built official
  MediaKit CLI when available and otherwise uses an explicit local FFmpeg
  fallback.
- `paid-checkpoints` writes four real-provider command checkpoints and marks
  every one `requires_explicit_user_approval: true` and `executed: false`. It
  never invokes a provider.

Every executor writes `personal-ip-media-execution-v1`. Successful local files
are hashed at receipt creation; declared inputs and outputs are re-hashed before
resume.
Downloaded outputs retain a query-free `source_ref` and `downloaded_at`.
Retries retain `attempt` and `retry_of`; failures retain category and
retryability. Cost remains `unknown` with a reason unless authoritative usage
exists, in which case `known` or `estimated`, amount, currency and basis are
stored.

The repository now refuses `delivery_completed` unless an earlier successful
`personal-ip-delivery-qa-v1` event covers the exact same output refs. QA runs
FFprobe, validates duration/aspect/audio requirements and performs a full
FFmpeg decode.

## Free local acceptance

```bash
make volcengine-install
make video-e2e-local
make video-e2e-local
```

The second identical command is intentional: it proves recovery without
re-running succeeded executors or duplicating events. A different immutable
input under the same operation key is rejected. A failed attempt is never
overwritten; retry with a new receipt/event key, incremented `attempt`, and
`retry_of` pointing to the failed attempt.

Validated twice on 2026-07-22 with the pinned local FFmpeg 8.1.2 and official
MediaKit source commit `279e5bb97e97c6875ae2c6891c2c3fa9a43f39c0`:

```text
production_id: video-production-4c348c531f7945fba0f900772082bcd3
status/current_stage: completed/delivery
event_count: 11 on both runs
finisher: mediakit-cli
qa_passed: true
paid_calls_executed: 0
final size: 55068 bytes
final sha256: f0e6604ace19f32eca3c810ff92320ce0a957dc86b348b000983b8cfec019544
```

The immutable event order was:

```text
blueprint_sealed
asset_generation_completed
storyboard_sealed
shot_generation_failed
shot_generation_completed
consistency_checked
candidate_selected
voice_generated
media_processing_completed
delivery_qa_completed
delivery_completed
```

Runtime evidence is intentionally ignored by Git under
`.deer-flow/acceptance/video-e2e/`: `acceptance-summary.json`, input snapshots,
verified outputs, immutable receipts and `ledger/deerflow.db`.

## Paid provider gate

Do not run any command in this section until the active user session explicitly
approves the stated batch. Preparing or inspecting checkpoints is free:

```bash
make video-e2e-paid-checkpoints
```

Inspect `.deer-flow/acceptance/video-e2e/paid-checkpoints.json`. It contains
copy-ready `argv`, shell-rendered `command`, working directory and receipt path
for these checkpoints:

| Checkpoint | Credential prerequisite | Planned call |
| --- | --- | --- |
| Seedream | `VOLCENGINE_API_KEY` and configured image model | one 9:16 preview image |
| Seedance | `VOLCENGINE_API_KEY` and configured video model | one 2-second 9:16 preview clip |
| Doubao Speech | `VOLCENGINE_TTS_APPID` and `VOLCENGINE_TTS_ACCESS_TOKEN` | one short voice-over |
| MediaKit cloud, optional | `MEDIAKIT_API_KEY` and `make volcengine-install` | one mux submission |

Before approval, report exactly four possible paid calls, the table above, and
that provider cost is unknown until an authoritative provider receipt or billing
source is available. After approval, execute one checkpoint at a time from its
recorded `cwd`. Immediately ingest its emitted receipt through
`personal_ip_ingest_media_execution`; do not rebuild task IDs, request IDs,
download evidence, errors or cost from console text. For an asynchronous cloud
MediaKit task, ingest the running submission receipt, then wrap query/download
as a new terminal receipt and ingest it under a new event key.

Deterministic finishing does not require cloud MediaKit. Prefer the official
local command through `run_media_executor.py`, then run delivery QA and append
`delivery_completed` only after the successful QA event. This supplies a real
paid-generation acceptance without adding an unnecessary cloud finishing fee.

## Implementation and verification notes

- `run_media_executor.py` now supports capability mapping, task/request IDs,
  query-free download provenance, attempt/retry links, known/estimated/unknown
  cost, retryable failures and hash-verified resume.
- Receipt normalization preserves that evidence and rejects credential-bearing
  payloads.
- The production repository enforces the exact-output delivery QA gate.
- The Gateway event schema exposes every event type already accepted by the
  repository, including delivery QA.
- The source package and doctor inventories include the acceptance runner and
  QA implementation.
- `cd backend && make test`: 8,658 passed, 54 skipped; changed-file Ruff
  check/format, 105 focused Personal-IP/media tests, 69 doctor/package tests and
  vendored MediaKit Go tests also passed. Full-repository Ruff rules pass; its
  format check still reports three unchanged baseline test files
  (`test_doctor.py`, `test_personal_ip_context.py`,
  `test_personal_ip_subject_repository.py`).
- No Seedream, Seedance, speech or cloud MediaKit call was made during this
  work. Only local build, FFmpeg, FFprobe and MediaKit execution occurred.

## Merge

Merge `parallel/video-e2e` into the target branch. The work is based directly on
`439f309`; it does not include or merge another parallel branch. Keep
`docs/IP_AGENT_PRODUCT_LEDGER.md` from the target branch unchanged.
