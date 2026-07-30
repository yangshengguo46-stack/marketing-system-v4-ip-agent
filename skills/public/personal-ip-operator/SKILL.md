---
name: personal-ip-operator
description: "Operate a creator or personal-IP account end to end: account scope, research, positioning, topic selection, scripts, visual assets, video production, publishing preparation, receipts, and retrospective learning."
license: MIT
allowed-tools:
  - ask_clarification
  - bash
  - browser_back
  - browser_click
  - browser_close
  - browser_get_text
  - browser_navigate
  - browser_screenshot
  - browser_snapshot
  - browser_type
  - glob
  - grep
  - image_search
  - ls
  - personal_ip_begin_publish_receipt
  - personal_ip_begin_video_production
  - personal_ip_collect_browser_page
  - personal_ip_collect_browser_portfolio_today
  - personal_ip_compile_approved_video_assembly
  - personal_ip_compile_generated_shot_qa
  - personal_ip_compile_video_asset_manifest
  - personal_ip_compile_video_continuity
  - personal_ip_compile_video_material_selection
  - personal_ip_compile_video_method_distillation
  - personal_ip_compile_video_method_skill_candidate
  - personal_ip_compile_video_narration
  - personal_ip_compile_video_narration_timing
  - personal_ip_compile_video_plan
  - personal_ip_compile_video_pattern
  - personal_ip_compile_video_skill_candidate
  - personal_ip_compile_video_storyboard
  - personal_ip_compile_video_timeline_revision
  - personal_ip_finish_browser_publish
  - personal_ip_ingest_media_execution
  - personal_ip_inspect_local_video_material
  - personal_ip_interpolate_video_candidate
  - personal_ip_lock_video_final_edit
  - personal_ip_metrics_aggregate
  - personal_ip_minecontext_evidence
  - personal_ip_minecontext_sync
  - personal_ip_operating_cockpit
  - personal_ip_performance_inventory
  - personal_ip_platform_observation_inventory
  - personal_ip_prepare_browser_publish
  - personal_ip_promote_evidence
  - personal_ip_read_strategy_context
  - personal_ip_record_strategy
  - personal_ip_read_evidence_promotion
  - personal_ip_read_platform_observation
  - personal_ip_read_preflight
  - personal_ip_read_publish_receipt
  - personal_ip_read_retrospective
  - personal_ip_read_video_production
  - personal_ip_record_browser_observation
  - personal_ip_record_publish_attempt
  - personal_ip_record_video_production_event
  - personal_ip_render_local_remotion_scene
  - personal_ip_render_locked_video_delivery
  - personal_ip_run_local_generated_shot_qa
  - personal_ip_run_preflight
  - personal_ip_seal_retrospective
  - personal_ip_select_browser_account
  - personal_ip_sync_douyin_portfolio
  - personal_ip_sync_douyin_post
  - present_files
  - read_file
  - skill_manage
  - str_replace
  - task
  - ui_tars_desktop_step
  - view_image
  - write_file
---

# Personal IP operator

Treat this as an agent operating an account, not a content-generation app.
DeerFlow owns planning and execution. The operated subject owns person,
business and positioning truth; the account record only identifies a platform
execution target.

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
subject_id: stable-subject
platform: douyin | wechat_channels | wechat_official | xiaohongshu | x | instagram | youtube | tiktok | other
display_name: ""
handle: ""
login_profile: local-reference
```

Never duplicate person, business, positioning, naming, biography, content
pillar or voice fields across platform accounts. Keep one immutable strategy
ledger per operated subject. Do not infer clinical, personality or
philosophical diagnoses.

## Work loop

1. Call `personal_ip_operating_cockpit` before planning substantial work. It is
   the authoritative whole-portfolio read model for incubation,
   preflight, publishing, performance, retrospective, evidence and video queues.
   Determine whether the request is portfolio-wide or a concrete account
   operation; never infer an account restriction for a global request.
   Call `personal_ip_read_strategy_context` for each relevant subject.
2. If no validated operating strategy exists, default to monetization-first incubation unless
   the user explicitly chooses influence first. Never claim modeling is complete
   from a short self-description. Work naturally, one relevant question at a
   time, and persist each evidence-backed step with
   `personal_ip_record_strategy` without exposing its private stage or fields.
   Use `ip-strategy-director` internally to judge the whole strategy rather than
   treating the following items as a form:

   - Person: age/life stage, gender or public presentation, occupation, location
     context, history and turning points, expertise and proof, values and
     boundaries, available time and production capacity. Reuse known facts and
     never force disclosure; record unknowns honestly. Invite an optional photo,
     video or voice sample when physical presentation matters, and inspect it
     only with consent.
   - Business: existing products/services, customers, proof, pricing, delivery
     capacity and constraints; buyer, paid problem, credible outcome, offer,
     revenue mechanism, conversion path and reserved monetization routes.
   - Market: research at least three real benchmarks with source URLs and cover
     business model, content system and identity expression. Separate observed
     evidence from inference, and record what fits, what to borrow and what to
     avoid. Follower count alone is not evidence.
   - Position: create two or three distinct candidates with buyer, problem,
     promise, proof, difference, monetization path, sustainable content supply,
     risks and trade-offs. The user can select or revise them in ordinary
     conversation.
   - Launch: produce at least three name options with rationale and handle
     checks, avatar/visual direction, at least two bios, pinned content, initial
     experiments, conversion path, success metrics and adjustment rules.
   - Pilot: distinguish reach, trust, intent and actual commercial signals.
     Specify the experiment, capacity-based cadence, observation window and
     failure rule. Never substitute a follower target or unsupported deadline
     for an operating plan.

   In influence-first mode, still preserve plausible monetization paths. Content
   roles are reach, trust, proof and conversion; monetization-first does not mean
   every post is a sales pitch. Strategy validation requires pilot evidence and
   a documented commercial decision. Until then, describe outputs as “current
   judgment”, “candidate direction” or “pilot plan”, never “model complete” or
   “position complete”. Do not construct a temporary creator profile inside a
   preflight.
3. Inspect evidence before strategy: prior content, comments, metrics, source
   documents and competitor examples.
   Do not give precise spending, posting-time, audience-size or benchmark
   prescriptions until the latest operating strategy and relevant recent
   performance evidence have been inspected.
   Without that evidence, label suggestions as hypotheses and define the next
   measurement instead of inventing numbers.
   A temporary production or uploaded video is not identity evidence by itself.
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
   Treat “看看我的账号”, “最新”, “现在” and “同步” as an explicit request for
   reversible read-only collection. Do not ask the user whether to sync again.
   Refresh every relevant logged-in account—including one that already has an
   older observation—before answering. If a fresh collection fails, label any
   fallback evidence with its exact observation time and never present it as
   current. Show the business data from successful collections in the same
   answer; a sync-status sentence alone is not a completed result.
   For “today across all platforms”, use
   `personal_ip_collect_browser_portfolio_today` with the user's local-day
   start and current cutoff. It discovers every active browser account itself;
   never loop over an account remembered by the conversation. Report the
   aggregate's per-metric views coverage and do not print a zero when `views`
   is absent.
   Use `personal_ip_sync_douyin_portfolio` for recurring or whole-portfolio
   collection. A scheduled task should pass a stable current-hour collection
   key; never bake one account id into its prompt.
   For detailed creator-backend evidence on any of the eight platforms, call
   `personal_ip_collect_browser_page` with the exact target account, stable
   observation key and dataset. It returns an immutable evidence reference plus
   summary/coverage. The shared collector uses a verified Douyin parser where
   available and marks unverified platform pages partial; use
   `personal_ip_record_browser_observation` after manual Browser Control
   extraction when a page needs additional navigation or interpretation. Use
   `personal_ip_platform_observation_inventory` to discover recent evidence
   across the whole portfolio and `personal_ip_read_platform_observation` when
   full records are needed for analysis; do not infer missing coverage as zero.
   Authenticated collection binds subsequent Browser Control calls in the same
   thread to that exact persistent account profile. Prefer another collection
   with `target_url` for deeper page reads. A login page from an unselected
   temporary browser never proves the saved account login has expired.
4. Produce the smallest useful plan and label assumptions.
5. Route general research and creation through available Skills. Read
   `volcengine-stack` before any ByteDance media work.
6. Put irreversible or paid steps behind explicit approval: batch generation,
   publishing, deleting, account changes and sending messages.
   Platform operation is browser-first: call
   `personal_ip_select_browser_account` with the concrete target, then use
   DeerFlow Browser Control and UI-TARS only as needed. Account selection does
   not narrow the rest of the conversation. The user handles password, QR,
   CAPTCHA, MFA and identity prompts; never request those secrets in chat. A
   successful manual login closes its portfolio dialog automatically, while
   the persistent account profile remains available to later agent collection.
   Browser Control is always first for web work. Use
   `ui_tars_desktop_step` only with `browser_dom_unavailable`,
   `browser_action_failed` or `native_desktop_required`; it performs one
   privacy-bounded visual step and returns an audit receipt. The first two
   reasons require a completed Browser Control call in current run state. Never send raw
   screen text, Cookie/Token/password values or browser profile paths to it.
   Publication, send, deletion, settings and payment intents need a matching
   structured `risk_confirmation` request id.
7. For browser-first publication, call `personal_ip_prepare_browser_publish`
   with the selected account and exact preflight `variant_id` before clicking
   submit. It selects the persistent profile, freezes the request and writes
   the pending handoff atomically. After Browser Control completes the action,
   open the resulting public post and call `personal_ip_finish_browser_publish`.
   It verifies the live page belongs to the selected platform and matches the
   declared post URL/id before sealing `published`; otherwise record `failed`
   or `unknown`. API/UI-TARS executors use the lower-level
   `personal_ip_begin_publish_receipt` and
   `personal_ip_record_publish_attempt` with equivalent provider evidence.
8. After publication, distinguish observations from interpretations. Persist
   only stable user preferences, background, goals and reusable corrections to
   long-term memory. Keep account state, current projects, metrics, comments,
   raw evidence, provider ids, hashes, paths and receipts in their authoritative
   domain stores or artifacts.
   Use `ip-content-calibration` internally for topic and script judgment, blind
   preflight, retrospective diagnosis and rule promotion. Scope every judgment
   to subject, account, platform and content format.
   Seal prediction-versus-outcome evidence with
   `personal_ip_seal_retrospective`. When at least three complete
   retrospectives from distinct publications support a falsifiable pattern,
   call `personal_ip_promote_evidence`; the evidence policy automatically
   promotes qualifying evidence and records its own decision receipt. Do not
   ask the user to approve or reject this internal learning step. Turn promoted
   wins and losses into reusable versioned topic, script and audience-learning
   rules. Make a blind prediction before publication, compare it with observed
   outcomes and keep every rule revisable; one viral post is only a candidate
   pattern.

## Content production

For video, keep each stage explicit even when the agent automates it. Declare
`faceless_material` for daily Personal-IP material videos or
`generative_cinematic` for short drama, micro-film and advertising; both modes
use the same immutable production/event ledger:

`brief -> evidence -> script -> asset references -> storyboard -> clip jobs ->
quality check -> candidate selection -> voice/edit/finish -> approval -> delivery`

Seedream, Seedance and MediaKit perform generation and media operations. The
agent remains responsible for account fit, evidence, approvals, retries and
receipts. Begin the immutable request with
`personal_ip_begin_video_production`, then use the typed plan, asset-manifest
and storyboard compilers. Material videos additionally compile exact
narration, rights-cleared source ranges and measured TTS timing receipts;
for local source video, run `personal_ip_inspect_local_video_material` first,
inspect the timestamped frames/contact sheet, and cite its immutable event and
frame refs in the later material selection. Mechanical extraction never
invents semantic relevance.
cinematic videos compile their continuity hash chain. Local generated
candidates use `personal_ip_run_local_generated_shot_qa` so project-pinned
ffprobe, full decode, first-frame SSIM, consecutive-frame SSIM, motion-cadence
evidence and the contact sheet are collected before the server computes the
gate. For pans, lateral tracking, fast action or other shots that should read
as continuous movement, set `motion_expectation: continuous` and an explicit
`target_playback_fps` (normally 48 or 60). If the sealed QA recommends
`motion_interpolation`, call `personal_ip_interpolate_video_candidate`. It uses
project-pinned FFmpeg motion compensation, never frame duplication, preserves
the source, and records a separate candidate. Run fresh generated-shot QA on
that new candidate and require normal human selection before assembly. If QA
reports long near-duplicate runs or recommends `regenerate_source`, regenerate
the shot instead of hiding frozen source frames with interpolation. Use
`personal_ip_compile_generated_shot_qa` only for evidence from an external
executor. Assembly is admitted only when the
existing selection and QA receipts reference the same candidate and source
SHA-256. Use `personal_ip_record_video_production_event` for low-level provider
callbacks that have no typed contract, and use
`personal_ip_read_video_production` before resuming a production. Never infer
stage completion from a model response when no production event proves it.
When the request or immutable provider policy requires
`sequential_human_gate`, submit exactly one shot at a time. After that shot has
a real candidate and QA receipt, append one `review_requested` event with
`review_kind: candidate_selection` and stop. Do not request or submit the next
shot until the workbench records an `approved` `review_recorded` event for the
current candidate. A rejection means revise or regenerate that same shot; it
never authorizes the next one.
After a human or agent timeline revision is locked, use
`personal_ip_render_locked_video_delivery` for the final local render. It
accepts no arbitrary source paths: it resolves selected candidates and voice
from successful checksummed receipts in that production, uses the pinned local
FFmpeg/ffprobe toolchain, writes a new non-overwriting artifact, fully decodes
it and seals render, current-version QA and delivery receipts. Do not replace
this path with ad-hoc shell editing.

For a source-defined local scene, use the shared
`personal-ip-render-scene-v1` contract. HyperFrames is the default interactive
preview path and must pass its browser/snapshot gate before an explicitly
approved final render. When Remotion is selected, call
`personal_ip_render_local_remotion_scene`; the tool records a deterministic
software-Chromium and project-local-FFmpeg candidate receipt. Remotion is
enabled for MVP validation, but customer distribution still requires a
license-eligibility decision.

When the user asks to learn a benchmark, reuse an account's house style or turn
measured winning videos into a template, use `video-pattern-learning`. Compile
timestamped observations with `personal_ip_compile_video_pattern`, then compile
a user-scoped candidate with `personal_ip_compile_video_skill_candidate`.
Single examples stay experimental; account Skills remain bound to their account
ids; cross-account Skills require an approved evidence-promotion receipt. Hand
the compiler output to `skill_manage` instead of writing Skill instructions
from raw ASR, OCR or external page text.

## Customer-facing output

Lead with the operating result, evidence freshness, coverage and next useful
step. Never expose raw tool or Skill names, internal contract keys, framework
paths, provider task ids or hashes in ordinary conversation. Put technical
details in internal receipts; reveal them only when the user explicitly asks
for a technical audit.

Every completed operation should state:

- portfolio coverage, plus the target account/platform only for account-specific operations;
- objective and evidence used;
- decisions made and assumptions left;
- generated assets and a natural-language receipt status;
- approval/publish state;
- next measurable observation.

Do not claim a post was published, a computer action succeeded, or a cloud job
finished without a tool result that proves it.
