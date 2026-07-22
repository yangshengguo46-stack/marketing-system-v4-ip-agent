# Personal-IP video production workbench

The video production workbench is a thin, read-oriented operating surface for
DeerFlow's existing Personal-IP video line. Open it at
`/workspace/personal-ip/video`.

## Ownership and source of truth

DeerFlow remains the only agent runtime and write orchestrator. A production's
immutable request and append-only `personal_ip_video_production_events` ledger
remain the business truth. The workbench does not create a video agent, restore
the removed Video Studio Evidence Runtime, persist a projection, or introduce a
second state machine.

Creation, execution and recovery stay in conversation through the native tools:

- `personal_ip_begin_video_production`
- `personal_ip_record_video_production_event`
- `personal_ip_read_video_production`

The Gateway exposes the existing owner-scoped production list/detail/event
routes plus:

```text
GET /api/personal-ip/video-productions/{production_id}/workbench
```

`deerflow.personal_ip.video_workbench` derives that response at read time from
the production and its ordered events. The `personal-ip-video-workbench-v1`
response groups the same receipts into the nine stages, blueprint, assets,
storyboard, shots, tasks, candidates, consistency, timeline, delivery QA and
raw event detail.

## UI boundary

The workbench provides:

- a searchable production list and nine-stage status rail;
- script/idea and immutable delivery/provider/budget context;
- character, scene and prop assets with artifact hashes;
- storyboard, per-shot tasks, failure categories, attempts and `retry_of`;
- candidate comparison, selection state and consistency checks;
- voice/finishing tracks, exact-output delivery QA and raw receipts;
- provider, model, provider task id and known/estimated/unknown cost state;
- a recovery instruction that returns execution to DeerFlow instead of
  rebuilding state in chat.

It intentionally has no project-creation or execution form. The only mutation
surface records an existing `review_recorded` event through the generic ledger
endpoint. The workbench presents confirmation UI only for candidate selection,
real paid-provider calls and real publishing. Evidence promotion is automatic
and never asks the user for approval.

Artifact references are rendered without query strings or fragments. The read
model exposes receipt metadata and hashes, not secrets or credential-bearing
URLs.

## Local acceptance

The workbench understands the receipts produced by
`scripts/personal_ip_video_e2e.py`, including simulated provider/model/task
identity, retry lineage, local artifact hashes and
`personal-ip-delivery-qa-v1`. Run the free resumable acceptance twice:

```bash
make ffmpeg-toolchain
make video-e2e-local
make video-e2e-local
```

The second run must retain the same production and event count. These commands
do not invoke Seedream, Seedance, speech or cloud MediaKit. Do not run paid
checkpoints without explicit approval in the active user session.

## Jellyfish reference and license

The layout was informed by the Apache-2.0 Jellyfish repository at commit
`a9678194ddf2d9be3ccbe78d4287d87d5089e123`, specifically its project lobby,
tabbed project workbench, asset manager, task center, readiness panel and
timeline-track organization. No Jellyfish source file or component was copied;
only those generic information-architecture patterns were adapted to the
existing DeerFlow design system and immutable-ledger contract.

Reference paths inspected:

- `front/src/pages/aiStudio/project/ProjectLobby.tsx`
- `front/src/pages/aiStudio/project/ProjectWorkbench/index.tsx`
- `front/src/pages/aiStudio/assets/AssetManager.tsx`
- `front/src/pages/aiStudio/components/TaskCenter.tsx`
- `front/src/pages/aiStudio/chapter/components/ChapterStudioVideoReadinessPanel.tsx`
- `front/src/pages/aiStudio/editor/VideoEditor.tsx`
- `front/src/pages/aiStudio/projectFlowStats.ts`

## Verification

Backend coverage lives in
`tests/test_personal_ip_video_workbench.py` and the Personal-IP video router
tests. Frontend pure helpers are covered by
`tests/unit/core/personal-ip-video-productions.test.ts`; the browser acceptance
is `tests/e2e/personal-ip-video-workbench.spec.ts` at a 1440×900 viewport.
