# Personal-IP video production workbench

The video production workbench is a thin, human/agent co-editing surface for
DeerFlow's existing Personal-IP video line. It is mounted inside the production
task at `/workspace/chats/{thread_id}` instead of occupying a global product
page. A new video begins as a new conversation; once the Agent creates the
production, that same task turns into the four-stage workbench. Leaving it puts
the task back in ordinary history, and reopening the history item restores the
same production.

## Ownership and source of truth

DeerFlow remains the only agent runtime and write orchestrator. A production's
immutable request and append-only `personal_ip_video_production_events` ledger
remain the business truth. The workbench does not create a video agent, restore
the removed Video Studio Evidence Runtime, persist a projection, or introduce a
second state machine.

Creation, execution and recovery stay in conversation through the native tools:

- `personal_ip_begin_video_production`
- `personal_ip_compile_video_plan`
- `personal_ip_compile_video_asset_manifest`
- `personal_ip_compile_video_storyboard`
- `personal_ip_compile_video_narration`
- `personal_ip_compile_video_material_selection`
- `personal_ip_compile_video_narration_timing`
- `personal_ip_compile_video_continuity`
- `personal_ip_compile_generated_shot_qa`
- `personal_ip_compile_approved_video_assembly`
- `personal_ip_compile_video_timeline_revision`
- `personal_ip_lock_video_final_edit`
- `personal_ip_render_locked_video_delivery`
- `personal_ip_record_video_production_event`
- `personal_ip_ingest_media_execution`
- `personal_ip_read_video_production`

Every new request declares exactly one mode: `faceless_material` for daily
Personal-IP material videos, or `generative_cinematic` for short drama,
micro-film and advertising. Both modes use the same request/event ledger. A
mode is a domain contract, not another agent or workflow runtime.

Use the typed compiler tools for authoring and validation. Manual timeline
operations use the same timeline compiler through the Gateway. The generic event
tool remains available for low-level provider callbacks and legacy receipts;
it is not a substitute for a server-validated plan, rights manifest,
storyboard, material selection, narration/timing, continuity, QA or assembly
contract.

The Gateway exposes the existing owner-scoped production list/detail/event
routes plus:

```text
GET /api/personal-ip/video-productions?thread_id={thread_id}
POST /api/personal-ip/video-productions/{production_id}/thread
GET /api/personal-ip/video-productions/{production_id}/workbench
POST /api/personal-ip/video-productions/{production_id}/timeline-revisions
POST /api/personal-ip/video-productions/{production_id}/final-edit-lock
```

`deerflow.personal_ip.video_workbench` derives that response at read time from
the production and its ordered events. The `personal-ip-video-workbench-v1`
response groups the same receipts into the nine stages, production mode,
compiled contracts, blueprint, rights-aware assets, storyboard, shots, tasks,
candidates, continuity hash chain, computed QA, admitted/revised timeline,
final-edit identity, delivery QA and raw event detail.

Optional rich fields are deliberately tolerant: old events continue to render,
while newer events can include asset lineage, structured storyboard shots,
continuity bridges, failure scope, automated QA or normalized timeline tracks.
The projection never computes approval, retries work or fills absent evidence.

## UI boundary

The workbench provides:

- a four-stage director rail (`设定 → 分镜 → 剪辑 → 成片`) that folds
  the nine-stage ledger into user-facing production language;
- a left shot rail, central 16:9 preview and candidate-version strip, embedded
  persistent DeerFlow conversation pinned to the bottom, and right reference-
  material rail for character, scene, prop and audio during storyboard; the
  raw shot-contract/continuity accordion and four-track lower dock are absent
  until the user enters their focused internal/editing surfaces;
- an edit-stage monitor above that single timeline. It previews the latest
  render and summarizes the current revision; it never mounts a second editor
  or independent local draft;
- no side rails in the edit stage: the monitor and timeline use the recovered
  width; shot regeneration returns to storyboard, while character, scene and
  style changes return to setup;
- no edit-stage pipeline shortcut palette: rough assembly, candidate review,
  motion QA/interpolation, narration, music/mix, caption alignment, continuity
  and final QA remain Agent capabilities invoked through the one controlled
  composer;
- Jianying-style direct timeline manipulation: drag the clip body to move and
  drag either edge to trim. There is no selected-clip toolbar or persistent
  numeric inspector; version, transition, volume and text changes go through
  the Agent;
- a full-width delivery viewer with no side rails or timeline dock. It exposes
  only the final player and one `保存到本地` action; delivery QA, contract
  versions, refs, hashes and publish checkpoints stay internal or in receipts;
- script/idea and immutable delivery/provider/budget context;
- character, scene and prop assets with version, source hash, lineage,
  camera-coverage and generation-route evidence when recorded;
- storyboard first/last-frame semantics, motion, preserve/change constraints,
  per-shot tasks, failure categories, attempts and `retry_of`;
- candidate comparison, selection state, automated QA, adjacent-shot state
  bridges and exact local recovery scope;
- directly adjustable video/dialogue/music/subtitle tracks with reorder, trim,
  split, duplicate, delete, candidate replacement, volume, caption and
  transition decisions;
- voice/finishing tracks, clip timing/source hash, immutable edit revisions,
  final-edit lock, exact-output delivery QA and raw receipts;
- owner-scoped, SHA-256-addressed inline playback for local candidate and final
  media. Browsers never receive a raw host path; the Gateway re-resolves the
  artifact from that production's successful receipts, verifies its current
  hash/size and serves byte ranges for seeking;
- provider, model, provider task id and known/estimated/unknown cost state;
- a recovery instruction that returns execution to DeerFlow instead of
  rebuilding state in chat.

It intentionally has no second project database or execution runtime. Selected
shot and timeline prompts use a persistent native `ip-agent` thread; production,
shot and candidate ids are operation context, never conversation authority.
The production's immutable `thread_id` is presentation/navigation ownership,
not an account or data-authorization boundary. One task owns one production;
starting another video means starting another native conversation.
Image/video regeneration must append a new candidate version and preserve every
old candidate.

Direct manipulation is a local draft until Save. Save sends one complete
four-track snapshot plus typed edit decisions to the server compiler, which
appends `timeline_revision_compiled`; pointer movement is never persisted.
The client derives the receipt intent from those typed operations instead of
asking for a second free-text revision note. The expanded timeline therefore
contains one conversation box only: the persistent Agent composer.
Restoring any historical revision creates another append-only decision instead
of deleting history. Both user and Agent edits use this contract. It seals the
useful `video-use` finishing rules—word-boundary cuts, 30 ms boundary fades,
overlay PTS shift, output-timeline subtitle offsets, subtitles last and
post-render self-QA—without importing `video-use`'s separate project file as
product truth.

Every revision remains an editable rough cut. Before delivery QA, a user or
Agent deliberately seals the latest revision with `final_edit_locked`. A later
revision invalidates that lock; the repository rejects stale-lock QA and
delivery. Candidate selection, real paid-provider calls and real publishing
remain the only confirmation UI. Evidence promotion is automatic.

After the lock, the normal local final path is
`personal_ip_render_locked_video_delivery`. It accepts only a production id,
resolves selected video and voice from successful checksummed receipts already
in that production, runs the project-pinned FFmpeg/ffprobe toolchain off the
async event loop, writes a revision-addressed output without overwriting prior
deliveries, fully decodes and probes the file, and appends
`media_processing_completed`, `delivery_qa_completed` and
`delivery_completed`. It never invokes a cloud generator or publishes.

Artifact references are rendered without query strings or fragments. The read
model exposes receipt metadata and hashes, not secrets or credential-bearing
URLs.

Project selection, active view, focused shot and an unsaved drag are ephemeral
navigation/draft state only. A displayed edit is durable only after its sealed
timeline-revision receipt returns.

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

The interactive one-shot acceptance was also completed through the visible
workbench on 2026-07-24: a human trim was sealed as
`timeline_revision_compiled`, the revision was locked, and the embedded
`ip-agent` called `personal_ip_render_locked_video_delivery`. The ledger grew
from 13 to 16 events; the new 1-second 360×640/24fps MPEG4+AAC output passed
decode, duration, aspect-ratio and audio checks, and its disk SHA-256 matched
the delivery receipt. This proves the human-edit-to-Agent-delivery path, not
the still-open full multi-shot acceptance.

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

## Read-only legacy Video Studio audit

The user's existing `/Users/yangyucheng/projects/video-studio` worktree was
audited at HEAD `37ad124` while it contained unrelated uncommitted and untracked
work. It remained strictly read-only. The audit covered the three workbench UI
variants, `src/main.tsx`, their tests, asset/timeline/shot/QA algorithms,
`workflow_routes.py`, director/media route tests and research note
`docs/research/17-asset-first-storyboard-native-production.md`.

The legacy workbench's director-desk spatial layout was intentionally
reimplemented with the current design primitives. Only pure domain algorithms
and ledger-compatible contracts were adapted:
mode-specific plans and shots, material rights and frame-grounded ranges,
exact narration/TTS timing receipts, continuity state hashing, generated-shot
gates and exact-hash assembly admission. No legacy CSS file, mutable project
store, Evidence Runtime, WorkGraph state machine, Kanban scheduler,
account/session binding or credential surface was copied.
Local generated-shot evidence is now produced by
`personal_ip_run_local_generated_shot_qa`: it restricts inputs to the current
owner/task, runs the project-pinned FFmpeg/ffprobe binaries off the async event
loop, writes first-frame/contact-sheet/mechanical QA artifacts, computes SSIM
and internal-cut observations, then seals the server-computed gate in the
existing production ledger. The report is explicitly mechanical-only and does
not create a user-approval queue.
The same QA now records near-duplicate transitions, longest stalled runs,
motion-delta variation and an explainable action. Continuous pans, lateral
tracking and action shots may declare a 48/60fps playback target. When QA
returns `motion_interpolation`, `personal_ip_interpolate_video_candidate`
creates a new checksummed candidate through the pinned FFmpeg `minterpolate`
motion-compensation path. It never duplicates frames or overwrites the source.
Long repeated-frame runs route to source regeneration; an interpolated
candidate always receives fresh QA and normal human comparison/selection.
For `faceless_material`, `personal_ip_inspect_local_video_material` provides
the corresponding pre-selection path. It verifies the current manifest's
rights and optional source hash, restricts the file to the current owner/task,
extracts ordered timestamped frames plus a contact sheet with project-pinned
FFmpeg, and seals `personal-ip-video-material-inspection-v1` into the same
asset stage. Its receipt explicitly requires a later semantic assessment; the
agent must inspect and cite the frame refs when compiling the exact source
range.
The source renderer tree now lives at `product/video-renderers`. HyperFrames
0.7.57 compiles the shared `personal-ip-render-scene-v1` input into a
brand-neutral project and passes the full browser, motion, layout, contrast and
snapshot gate; final HyperFrames rendering remains blocked until the preview
is explicitly approved. Remotion 4.0.488 consumes the same scene contract
through `personal_ip_render_local_remotion_scene`. Its deterministic mode fixes
Chromium to software rendering, captures PNG frames, finishes them with the
project-local OpenH264 FFmpeg build and seals the verified output as a
`shot_generation_completed` candidate receipt. Remotion is currently an MVP
renderer; customer distribution requires a separate license-eligibility gate.
The implementation inventory is in `docs/VIDEO_PIPELINE_MIGRATION_LEDGER.md`;
the original workbench decision matrix remains in
`docs/handoffs/VIDEO_WORKBENCH.md`.

## Verification

Backend coverage lives in
`tests/test_personal_ip_video_workbench.py` and the Personal-IP video router
tests. Frontend pure helpers are covered by
`tests/unit/core/personal-ip-video-productions.test.ts`; the browser acceptance
is `tests/e2e/personal-ip-video-workbench.spec.ts` at a 1440×900 viewport.
