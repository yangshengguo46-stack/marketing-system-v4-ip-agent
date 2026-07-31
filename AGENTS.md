# AGENTS.md

This file provides guidance to AI coding agents (Claude Code, Codex, and others) when working with code in this repository. It is the source of truth; the sibling `CLAUDE.md` imports it via `@AGENTS.md`.

It is the **monorepo orientation layer**: it maps the whole repo and points to the
module guides that own the depth. For anything inside a module, read that module's
guide rather than expecting full detail here:

- **[backend/AGENTS.md](backend/AGENTS.md)** — backend depth: harness/app split, agent &
  middleware chain, sandbox, MCP, skills, memory, IM channels, persistence/migrations,
  config system, test layout.
- **[frontend/AGENTS.md](frontend/AGENTS.md)** — frontend depth: Next.js App Router layout,
  thread/streaming data flow, code style, commands.

## What is DeerFlow

DeerFlow is a LangGraph-based AI super-agent system with a full-stack architecture. The
backend runs a "super agent" with sandboxed execution, persistent memory, subagent
delegation, and extensible tools (built-in, MCP, community), all per-thread isolated. The
frontend is a Next.js chat UI. External IM platforms (Feishu, Slack, Telegram, Discord,
DingTalk) bridge into the same agent through the Gateway.

## Service Topology

A single `make dev` / Docker stack runs four cooperating services:

| Service         | Port   | Role                                                                |
| --------------- | ------ | ------------------------------------------------------------------- |
| **Nginx**       | `2026` | Unified reverse-proxy entry point — open this in the browser        |
| **Gateway API** | `8001` | FastAPI REST API + embedded LangGraph-compatible agent runtime      |
| **Frontend**    | `3000` | Next.js web interface                                               |
| **Provisioner** | `8002` | Optional — only when sandbox is configured for provisioner/K8s mode |

Nginx is the single public entry: it serves the frontend and proxies `/api/langgraph/*`
to the Gateway's LangGraph runtime, rewriting it to Gateway's native `/api/*` routes; all
other `/api/*` go straight to the Gateway REST routers. See
[backend/AGENTS.md](backend/AGENTS.md) for the runtime and router detail.

## Repository Map

```
deer-flow/
├── Makefile                        # Root orchestration: drives the full stack (dev/start/stop, docker, setup)
├── config.example.yaml             # Template → copy to config.yaml (gitignored) at repo root
├── extensions_config.example.json  # Template → copy to extensions_config.json (gitignored): MCP servers + skills
├── backend/                        # Python backend — see backend/AGENTS.md
│   ├── Makefile                    # Per-module backend commands (dev, gateway, test, lint, migrate-rev)
│   ├── packages/harness/           # deerflow-harness package (import: deerflow.*) — agent framework
│   └── app/                        # FastAPI Gateway + IM channels (import: app.*)
├── frontend/                       # Next.js frontend (pnpm) — see frontend/AGENTS.md
├── docker/                         # docker-compose files, nginx config, provisioner
├── skills/                         # Agent skills: public/ (committed), custom/ (gitignored)
├── contracts/                      # Cross-component JSON contracts (e.g. subagent status, skill review)
├── scripts/                        # Root orchestration scripts invoked by the Makefile (check, configure, doctor, support_bundle, serve, nginx, docker, deploy, setup_wizard)
├── tests/                          # Root-level tests (currently tests/skills/ — public skill tests)
└── docs/                           # Cross-cutting docs, plans, and design notes
```

Runtime config lives at the **repo root**: copy `config.example.yaml` → `config.yaml`
(main app config) and `extensions_config.example.json` → `extensions_config.json` (MCP
servers + skills). Both real files are gitignored and may be edited at runtime via the
Gateway API. Config schema and resolution order are documented in
[backend/AGENTS.md](backend/AGENTS.md).

IP Agent distribution note:

- `IP_AGENT.md` is the product setup and capability-routing guide;
  `THIRD_PARTY_BYTE.md` records copied ByteDance/Volcengine components and pins.
- `docs/IP_AGENT_PRODUCT_LEDGER.md` is the delivery source of truth. Update its
  acceptance gates and weighted score only when a real product path is added,
  removed or verified; do not equate schemas or mocked tests with completion.
- `docs/IP_AGENT_AUDIT_REMEDIATION_LEDGER.md` records audit findings and their
  executable acceptance gates. Update an item to done only after the named
  command or external acceptance completes.
- Python launch/test targets use `uv run python -m ...`, not generated console
  scripts, so a copied or moved checkout does not depend on stale virtualenv
  shebangs.
- `product/defaults/` owns the product agent/owner defaults, while
  `product/volcengine/capabilities.yaml` is the auditable media routing policy.
- `scripts/init_ip_agent.py` installs those defaults into a normal DeerFlow
  workspace. `make ip-refresh` updates only the product-owned `ip-agent`
  `SOUL.md`/`config.yaml` and preserves `USER.md`; `make doctor` must warn when
  an installed product agent is stale. Both commands must resolve the same
  `DEER_FLOW_HOME` as the local launcher, defaulting to
  `backend/.deer-flow`; root `.deer-flow` remains the project-local toolchain
  location. Keep this as a source distribution:
  integrate upstream DeerFlow changes without replacing native source modules
  with binary wrappers.
- `third_party/volcengine/mediakit-cli` is the pinned MediaKit Go source.
  `scripts/mediakit_source.py` builds it into ignored `.deer-flow/bin`; do not
  reintroduce the upstream prebuilt `mediakit` file or a global npm installer.
- `third_party/bytedance/HLLM` is the complete pinned HLLM/HLLM-Creator source.
  Keep upstream model code intact and its heavy PyTorch/DeepSpeed environment
  separate from the Gateway. Personal-IP integration belongs in the thin
  `deerflow.personal_ip.hllm_creator` adapter and the versioned
  `deerflow.personal_ip.audience_provider` service contract; do not copy the
  model implementation into DeerFlow. The same contract must support current
  HLLM-Lite and a future full HLLM-Creator cloud deployment. `make hllm-doctor`
  verifies the pin without downloading weights; `make hllm-lite` runs the
  local-only Doubao-backed sidecar on port 9128.
- `third_party/volcengine/MineContext` is the complete Apache-2.0 source pinned
  at `171c7a9ea8091e326ddcf0f10718aa1b58c83c65`. Keep DeerFlow as the only
  agent brain. `deerflow.personal_ip.minecontext` may run it only as a
  default-on, owner-isolated loopback sidecar with a persistent owner opt-out.
  New-owner startup may enable bounded screen summaries but must never override
  an inactive consent. Never place raw screenshots, full screen/file text,
  paths, vectors or credentials in model evidence. Preserve source/observation
  time, partial coverage, retention, stop/revoke/delete controls and the
  `personal-ip-local-context-evidence-v1` boundary. Normal `make install` must
  install from the vendored source; do not add an opaque prebuilt MineContext
  executable.
- `scripts/install_ffmpeg_toolchain.py` owns the pinned project-local FFmpeg
  build. Service launch and MediaKit diagnosis must prefer its `bin` directory;
  do not silently fall back to a feature-incomplete system FFmpeg.
- `deerflow.personal_ip.generated_shot_qa` owns deterministic local generated-
  shot measurement. `personal_ip_run_local_generated_shot_qa` may resolve only
  current-owner/current-thread `/mnt/user-data` paths, must offload FFmpeg and
  filesystem work from the async tool loop, and must seal the measured hashes,
  contact sheet, motion-cadence evidence, mechanical-only report and
  server-computed gate into the existing append-only video ledger. It must
  never create a second QA state store or claim human/final approval.
- `deerflow.personal_ip.frame_interpolation` owns the optional local smooth-
  motion derivative. `personal_ip_interpolate_video_candidate` accepts only a
  successful checksummed candidate in the current owner/task, uses the pinned
  FFmpeg `minterpolate` motion-compensation filter (never duplicate-frame FPS
  conversion), writes a non-overwriting candidate receipt, and requires fresh
  QA plus human selection. Frozen/repeated source runs should be regenerated,
  not disguised by interpolation.
- `deerflow.personal_ip.material_inspection` owns local, frame-grounded source
  inspection for `faceless_material`. The native tool must require a
  rights-cleared asset and storyboard shot from the latest compiled contracts,
  resolve only current-owner/current-thread `/mnt/user-data` paths, compare the
  local source hash with the manifest when present, use only the project-pinned
  FFmpeg/ffprobe, and seal timestamped frames/contact sheet/report into the
  existing video ledger. Mechanical inspection must require a later semantic
  assessment; it must never fabricate relevance or silently approve material.
- New-console Doubao Speech uses one `VOLCENGINE_TTS_API_KEY` sent as
  `X-Api-Key`; `VOLCENGINE_TTS_ACCESS_TOKEN` is a temporary local compatibility
  alias. Do not make AppID a product-wide prerequisite. Protocol-specific
  legacy/async endpoints may declare their own additional requirements.
- `podcast-generation` may set per-line `voice_type`, `speech_rate`,
  `loudness_rate` and `context_text`/`context_texts` only on the new-console
  V3 single-key route. Validate every control before provider execution and
  reject unsupported legacy execution instead of silently degrading. Receipts
  may contain context count and SHA-256 only; never persist the raw performance
  direction.
- Personal-IP account data is the product-owned domain boundary. It must remain
  owner-scoped, enter runs through validated server context, and never be trusted
  from a caller-supplied expanded object.
- Whole-domain Personal-IP data lifecycle is owned by
  `deerflow.personal_ip.data_lifecycle`. Every `personal_ip_*` table must be
  classified as an exported dataset or an explicit secret/deletion-only table.
  Never export credential ciphertext or one-use OAuth state. Restore is
  same-owner and empty-scope only, verifies dataset plus manifest digests, and
  restores platform connections revoked so reauthorization is mandatory.
  Permanent deletion requires a fresh server preview, the exact confirmation
  phrase, backup acknowledgement and MineContext deletion; stale state digests
  fail closed. Run `make personal-ip-data-lifecycle-acceptance`.
- Keep the Chinese workspace sidebar distinction explicit: `新对话` creates a
  thread, while `历史对话` opens the complete thread index from immediately
  below `定时任务`. Do not label both entries simply as `对话`.
- Keep `工作台` immediately above `新对话` in the workspace sidebar.
  `/workspace/dashboard` is the owner-wide operating read model for real
  metric observations, platform growth, recent works and agent queues;
  `/workspace/personal-ip` remains the subject, account and platform-login
  surface. MineContext consent, lifecycle, retention and deletion belong to the
  dedicated `本地上下文` section inside Settings, not the operating portfolio.
  New owners receive every supported local-context scope and Personal-IP
  purpose internally and the workspace starts bounded screen summaries by
  default, without exposing backend scope or purpose ids as checkboxes.
  “关闭” persists an opt-out; it must not be undone by the next page load.
  Missing observations must remain missing, never synthetic zeroes. A
  paid-traffic review candidate needs at least three same-platform post samples
  and only authorizes evaluation, never spend.
- Treat the Skill catalog as private product implementation. Do not render a
  Skill-management section in customer Settings, Skill autocomplete/chips in
  chat, agent Skill badges, or Skill names/paths/tool steps in conversations,
  subtask timelines, copy and ordinary exports. Internal discovery, execution,
  evolution, audit and owner isolation remain enabled. Customer-facing agent
  output describes work and results, not which Skill was selected.
- Personal-IP preflights are immutable model request/receipt snapshots under
  `deerflow.persistence.personal_ip_preflights` and migration
  `0008_personal_ip_preflights`. Account ids are operation targets in the
  snapshot, never thread authority. Do not add a prediction rewrite endpoint.
- Personal-IP publishing receipts live in
  `deerflow.persistence.personal_ip_publish_receipts` and migration
  `0009_personal_ip_publish_receipts`. Keep the initial request immutable,
  attempts append-only and terminal publication status monotonic. API,
  UI-TARS, browser and manual executors share this one receipt contract.
  Every new request must carry a
  `personal-ip-publish-compliance-v1` declaration. The repository derives the
  target platform, validates rights, moderation and the exact
  commercial/AI-disclosure plan, then seals its own versioned policy receipt;
  callers may not supply that receipt. A `published` attempt additionally
  requires `personal-ip-publish-compliance-evidence-v1` bound to the sealed
  receipt with evidence refs for the applied disclosures. Sensitive-topic
  declarations require documented human review. Keep policy source URLs and
  review dates in the receipt and fail closed when the contract is missing.
  Browser proof must identify a post-specific public URL on the selected one
  of eight platforms; a creator dashboard, home page or same-host list is not
  success evidence. Prepare may append a new pending handoff after `failed` or
  `unknown`; an identical finish callback replays without requiring the live
  page again, while a conflicting callback remains rejected. Run
  `make personal-ip-publish-acceptance` for the local-only recovery matrix.
- Personal-IP performance observations live in
  `deerflow.persistence.personal_ip_metrics` and migration
  `0010_personal_ip_metrics`. The `/api/personal-ip/metrics/aggregate` route is
  portfolio-wide by design: never add a thread-bound account restriction.
  Aggregate only additive `window_total`/`delta` fields, replace progressive
  same-start `window_total` polls with the latest cutoff for that series, take
  the latest observation for an otherwise identical window, exclude cumulative snapshots,
  and expose mutually exclusive missing/partial/unavailable account coverage
  explicitly. Aggregation is over the owner's active account set only and also
  reports per-metric coverage; an absent `views` field must stay absent, never
  become zero.
- Personal-IP retrospective evidence lives in
  `deerflow.persistence.personal_ip_retrospectives` and migration
  `0011_personal_ip_retrospectives`. A retrospective must join one published
  receipt to its original preflight and same-receipt post observations, freeze
  the selected variant plus outcomes under an evidence digest. Partial evidence
  remains `insufficient_evidence`; complete evidence becomes
  `eligible_for_policy_evaluation`. Never invent a score when HLLM-Lite
  returned none.
- Personal-IP evidence promotion lives in
  `deerflow.persistence.personal_ip_evidence_promotions` and migration
  `0012_personal_ip_evidence_promotions`. A promotion needs at least three
  complete retrospectives from distinct publish receipts; different horizons
  of one post count once and partial observations do not satisfy the threshold.
  Passing that deterministic policy automatically approves the promotion and
  stores a policy decision receipt. Evidence promotion is internal learning,
  not a user approval task. Preserve source status/comparison provenance in
  approved-evidence exports; exporting does not mutate a live model.
- The first real platform collector is
  `deerflow.personal_ip.platform_metrics.DouyinVideoMetricCollector`. It calls
  only Douyin's fixed official video-query URL and emits post-level cumulative
  snapshots; do not treat them as daily deltas. Never accept/log raw access
  tokens through a public Gateway route. `make douyin-metrics-smoke` is a
  developer-only env-based check. Production `ma.video.bind` authorization is
  mini-app based: `tt.showDouyinOpenAuth` permission ticket plus `tt.login`
  code, one-use hashed state, server-side exchange and encrypted account-level
  credentials under migration `0013_personal_ip_platform_connections`.
  Connections are operation resources, never thread authority; disconnect
  wipes the encrypted token row. Authorized metric collection accepts only a
  connection id plus publish receipt id, refreshes once after an authentication
  failure, and keeps all credential material out of the agent context. See
  `docs/DOUYIN_METRICS.md`.
- `deerflow.tools.builtins.personal_ip_tools` exposes native whole-portfolio
  performance inventory, aggregation, one-post sync and failure-isolated
  portfolio Douyin sync. Gateway installs the repository bundle through
  `deerflow.personal_ip.runtime`; this app-to-harness injection preserves the
  harness import firewall. The aggregate and portfolio-sync tools intentionally
  have no account filter. Keep `product/defaults/agents/ip-agent/SOUL.md` and
  `skills/public/personal-ip-operator/SKILL.md` aligned: conversations cover
  the full portfolio, while account ids are only concrete operation targets.
- Official Douyin post counters remain immutable cumulative snapshots. From the
  second observation onward, `PersonalIPMetricCollectionService` may derive an
  exact-interval delta from the immediately preceding monotonic snapshot in the
  same post series. Derived deltas are always `partial` with
  `scope_limit=tracked_post_only`; never relabel them complete account totals or
  infer data before the baseline timestamp.
- Personal-IP platform operation is browser-first for Douyin, WeChat Channels,
  WeChat Official Accounts, Xiaohongshu, X, Instagram, YouTube and TikTok.
  `/workspace/personal-ip` must render all eight entries even before accounts
  exist. Local interactive installs open manual login in a real headed Chromium
  window; the account-scoped socket owns its lifecycle and falls back to an
  embedded Live stream only when the Gateway has no graphical desktop. The
  user—not the agent—completes QR, CAPTCHA and MFA. Each account uses an
  owner/account-isolated persistent profile. Successful login emits a boolean
  event, closes the native browser and dismisses the login dialog. This
  credential boundary must not suppress
  detailed authorized business-data collection: account/content inventories,
  metrics, audience analytics, comments and receipts should retain source,
  observed-at and coverage evidence while raw credential values stay out of
  model context.
  `personal_ip_select_browser_account` selects only the concrete operation
  target. Browser Control resolves that selection to an owner/account-isolated
  persistent Chromium profile; it never narrows conversation authority or
  exposes the profile path/cookies/passwords to the model. See
  `docs/BROWSER_FIRST_PLATFORM_CONNECTIONS.md`.
- UI-TARS is a default-off local desktop fallback, not another agent runtime.
  The selected Apache-2.0 upstream source is pinned under
  `third_party/bytedance/UI-TARS-desktop`; do not install its precompiled libnut
  packages or introduce Agent TARS. `deerflow.community.ui_tars` owns the
  source-only single-step service, local pixelation boundary, permission
  diagnosis and append-only audit receipts. Browser Control stays first for
  web work. Web fallbacks require a completed Browser Control call in current
  run state, not only a claimed reason. `ui_tars_desktop_step` requires an explicit browser failure/native
  desktop reason, validates an optional account as an operation target only,
  and requires a structured risk confirmation for high-impact work. Run
  `make ui-tars-doctor`; see `docs/UI_TARS_INTEGRATION.md`.
- Detailed creator-backend evidence lives in
  `deerflow.persistence.personal_ip_platform_observations` and migration
  `0014_personal_ip_platform_observations`. Preserve the immutable
  `personal-ip-platform-observation-v1` contract and recursively reject raw
  credential fields/values. Business records should remain detailed and carry
  source URL, observed time, coverage and evidence; source URL queries and
  fragments must not be persisted. `personal_ip_record_browser_observation`
  is the native sealing tool after Browser Control reads an authorized page.
  `deerflow.personal_ip.browser_collection` and
  `personal_ip_collect_browser_page` provide one rendered-DOM collector for all
  eight browser-first platforms while reusing the same persistent account
  browser session. Generic pages remain partial until a verified
  platform-specific adapter proves completeness; the Douyin endpoint/tool stay
  compatibility wrappers over this service. Native inventory/read tools expose
  the credential-free detailed evidence to analysis; inventory remains
  portfolio-wide and an observation id selects only the exact read target.
  `personal_ip_collect_browser_portfolio_today` and the matching Gateway route
  scan the authenticated owner's complete active account set with no account
  argument. Rendered-label adapters may seal a partial account `window_total`
  only when the page explicitly displays 今日/今天/Today; other windows are
  unavailable for that request, collection failures stay missing, and all
  detailed page evidence remains in platform observations.
  Account-status/最新/同步 requests are authorization for reversible read-only
  collection and must not trigger a second clarification. Route dashboard
  reads to the registered creator dashboard, tolerate a Playwright
  DOMContentLoaded timeout only when subsequent same-platform URL/login and
  rendered-DOM checks still pass, and allow local proxy RFC 2544 fake-IP
  answers for public creator hosts under the same narrow SSRF policy as Browser
  Control. Always return `observed_at`; never silently relabel an older
  observation as the current result.
- Public-web research is search-first, not browser-first. The Volcengine Ark
  provider exposes Responses API Web Search through the ordinary `web_search`
  contract, reuses `VOLCENGINE_API_KEY`, keeps provider storage disabled and
  returns citation-bearing evidence. When the account reports `ToolNotOpen`,
  the configured DuckDuckGo fallback avoids opening an interactive browser and
  caches that unavailable capability for the Gateway process. Browser Control
  remains the path for rendered-source verification, user-supplied pages,
  authenticated creator surfaces and interaction.
- Personal-IP video production lives in
  `deerflow.persistence.personal_ip_video_productions` and migration
  `0015_personal_ip_video_productions`; migration
  `0018_video_production_threads` binds each production to exactly one
  customer-visible DeerFlow task thread. A new video starts from a new native
  conversation, the production workbench replaces that task's ordinary chat
  canvas after creation, and leaving it returns the task to normal persisted
  history. Do not restore a global video-project switcher in customer
  navigation. Keep the initial idea/script, delivery
  spec, provider policy and budget immutable; record blueprint, assets,
  storyboard, per-shot generation/failure/retry, consistency, selection,
  finishing and delivery as idempotent append-only events. Providers and model
  versions are receipt fields, not orchestration state. A production completes
  only through a successful `delivery_completed` event, and that event requires
  a preceding successful `personal-ip-delivery-qa-v1` receipt for the exact
  output refs. `scripts/personal_ip_video_e2e.py` is the credential-free local
  acceptance/resume path; it must keep paid providers simulated unless the
  active user session explicitly approves the generated paid checkpoints.
  Its `ingest-real` command verifies already-emitted real provider, finishing
  and QA receipts and idempotently seals them into a production; it must never
  make or reconstruct a provider call.
  `deerflow.personal_ip.video_budget` owns paid-call admission on that same
  event ledger. A paid production freezes currency and `hard_limit`; each
  provider attempt needs a distinct server reservation before submission.
  Reservation is serialized against spent plus all active reservations, so
  retries and concurrent calls cannot overbook the limit. A trusted workbench
  approval must match the exact reservation request when approval is enabled;
  generic agent events cannot mint that approval. Settle every called attempt,
  including failures and proven zero cost, from a provider receipt. Unknown
  cost stays reserved; release is allowed only when no provider call occurred.
  Provider-request events declare `billing_mode`; paid requests bind the active
  reservation and an estimate within its maximum, while free requests require
  known zero cost. Keep reservation/settlement/release receipts append-only and
  do not create a mutable parallel cost ledger.
  New requests must declare `faceless_material` or `generative_cinematic`.
  `deerflow.personal_ip.video_contracts` owns the pure, server-validated plan,
  rights manifest, storyboard, material selection, narration/TTS timing,
  continuity, generated-shot QA, exact-hash assembly and shared human/agent
  timeline-revision contracts. Expose
  those through native typed tools and
  seal them as events in the existing ledger; never let an arbitrary generic
  payload impersonate one of those contracts. Generic events remain for
  low-level provider callbacks and legacy receipts. Candidate admission must
  prove that selection, QA and assembly reference the same candidate and
  source SHA-256.
  Source-defined local scenes use the exact renderer tree in
  `product/video-renderers`. HyperFrames 0.7.57 is the default interactive
  renderer and must pass `check --snapshots` before an explicitly approved
  final render. Remotion 4.0.488 is available for MVP rendering through
  `personal_ip_render_local_remotion_scene`; it must use software Chromium,
  deterministic PNG frames and the project-local FFmpeg finisher before its
  candidate receipt is sealed. Never restore hard-coded legacy branding.
  Reconfirm Remotion license eligibility before distributing a customer
  installation package.
  `deerflow.personal_ip.video_workbench` and Gateway
  `GET /api/personal-ip/video-productions/{production_id}/workbench` are a pure,
  owner-scoped read model over that same production and event stream. The
  frontend may submit server-compiled timeline revisions through
  `POST /api/personal-ip/video-productions/{production_id}/timeline-revisions`
  and meaningful confirmation events, but must never persist pointer movement,
  create a parallel video runtime, mutable projection table or chat-derived
  recovery state. The director UI mounts one editable timeline in the lower
  dock only during the edit stage; setup, storyboard and delivery never mount
  it. The edit-stage upper canvas is monitoring/revision context, not a second
  editor. It exposes one Agent composer and derives manual-revision
  intent from typed operations rather than a second free-text note box. In the
  edit stage, do not expose a separate pipeline shortcut rail: picture, sound
  and QA capabilities are selected internally by the Agent through the same
  controlled composer. Hide both side rails so the preview and timeline use
  the recovered width; users return to storyboard for shot regeneration or
  setup for character, scene and style changes. Use
  Jianying-style direct manipulation for selected clips: drag the
  clip body to move it and drag either edge to trim it. Do not add a selected
  clip status/toolbar row or a persistent numeric inspector above or below the
  timeline; version, transition, volume and text changes go through the Agent.
  The setup stage lists only visual asset candidates in the left rail, previews
  the selected version centrally and sends generation/revision/adoption through
  one persistent `ip-agent` setup composer. Keep every generated version in the
  immutable ledger and keep the timeline dock hidden throughout setup and
  storyboard.
  The delivery stage is a full-width viewer, not another editor or evidence
  console. Hide both side rails and the timeline dock; expose only the final
  player and one `保存到本地` action. Delivery QA, contract versions, raw refs,
  hashes and publish checkpoints remain internal or in receipts.
  Shot/timeline conversations use ordinary DeerFlow threads;
  exact ids are operation targets only and never conversation authority.
- `deerflow.personal_ip.operating_cockpit.PersonalIPStartupContextService` is
  the first new-conversation read and may inspect only active subject/account
  existence. `new_owner` must continue from the user's current request without
  scanning empty workflow ledgers; `returning_owner`, resume and portfolio
  work may proceed to the full cockpit. `deerflow.personal_ip.operating_cockpit`
  is the owner-scoped read model that
  joins the six-stage operating loop and nine-stage video line. The Gateway
  route and native `personal_ip_operating_cockpit` tool must use the same
  service, stay whole-portfolio, expose explicit pending queues and report
  bounded-history coverage. Its v6 alert surface derives sanitized loop,
  provider and cost failures from authoritative receipts and the video ledger;
  never forward raw provider payloads or create a parallel alert store. Budget
  admission rejection is an append-only
  `personal-ip-video-budget-rejection-v1` event. The native
  begin/compile/execute/read video tools
  are the agent's write/resume surface; chat history is never the production
  ledger.
- A server-validated empty Personal-IP portfolio plus an orientation/incubation
  request is a bounded narrative-interview boundary. Its first reply is normal
  conversation with one entity-sensitive grand-tour invitation, using zero
  provider calls and zero web/Skill/ledger reads. Later intake turns use only
  recent visible dialogue plus a private forced response schema: reflect a
  user-specific fact, keep meaning hypotheses correctable, ask at most one
  material question, and declare when evidence is ready for the full agent.
  Do not default to earliest memory or sensitive history; skip/stop/correct and
  internal-only boundaries belong to the user. Supplied script, asset, link and
  direct-strategy operations bypass or interrupt this boundary.
- `deerflow.personal_ip.video_method_distillation` adapts the MIT-licensed
  Cangjie RIA-TV++ workflow for long-form video, recorded courses, interviews
  and podcasts. It may consume only a sealed `personal-ip-video-pattern-v1`
  plus timestamped, hashed abstract evidence. Raw transcript/OCR and
  prompt-like source text must never become Skill instructions. Each method
  needs two independent source contexts, trigger/non-trigger/edge tests and a
  sibling decoy when applicable. The compiler emits one atomic candidate plus
  reference/eval files; installation remains explicit through `skill_manage`,
  and portable use still requires three distinct measured publications.
- `product/cinematic-ip/matrix.yaml` and the 35 matching first-party packages
  under `skills/public/` form the private cinematic Personal-IP methodology
  layer. Keep the bundled 358-film / 393-creator / 304-mechanism SQLite index
  and eight-track 96-module curriculum source-auditable. Its evidence intake
  must write only through subject-level `personal_ip_strategy_versions` and
  credential-free evidence references; its calibration path must reuse native
  preflights, publish receipts, metrics, retrospectives and promotions. Never
  restore the source matrix's standalone `ip_os.py`, project JSON/JSONL ledger
  or writable curriculum completion ledger. Keep customer answers free of
  package names, paths, tools and internal routing.
- Personal-IP operating truth is subject-scoped and versioned in
  `personal_ip_strategy_versions`. Platform accounts are execution targets and
  must not regain person, business, positioning, naming, audience or voice
  fields in API, UI, agent context or readiness gates. Preflight loads the
  latest launch-ready strategy server-side; a caller-provided parallel
  creator/audience profile is forbidden. First-use incubation is a natural
  `ip-agent` conversation, not a customer questionnaire surface. For a
  server-validated empty portfolio and an orientation/incubation request,
  `PersonalIPContextMiddleware` must open with an ordinary entity-appropriate
  grand-tour question and then run bounded reflective follow-ups without
  exposing or enabling research/execution tools. The ordinary composer remains
  available, and the frontend must suppress generic follow-up suggestions while
  the versioned narrative-interview marker is active. Concrete supplied scripts,
  assets, links and direct requests bypass or interrupt this delay. Strategy
  versions must cover
  entity evidence, commercial design, real benchmarks, two-to-three positioning
  alternatives, name/avatar/bio launch assets, pilot experiments and observed
  validation evidence. Influence is the common IP asset mechanism, never a mode
  competing with monetization. Strategy v4 must store separate influence,
  behavioral and economic goals, time horizons, priority order, guardrails and
  deliberate non-goals. The legacy `monetization_first` / `influence_first`
  field remains storage compatibility only and must not drive decisions. The
  agent surface uses `personal_ip_record_strategy` and
  `personal_ip_read_strategy_context`. Customer copy may say current
  judgment/candidate/pilot before observed validation, never “建模完成” or
  “定位完成”. Launch pilots must carry evidence level, target audience,
  observable mechanism hypotheses, predicted signals, failure conditions,
  distribution assumptions, observation window and uncertainty. Formal
  hypotheses reject viral guarantees and dopamine/mirror-neuron/Zeigarnik
  causal shorthand; platform allocation, competition, timing and stochastic
  feedback remain explicit. Internal stages and fields stay private. Repeated content
  outcomes become revisable versioned rules through blind prediction,
  retrospective and evidence promotion; one viral post is not permanent truth.
- Personal-IP subjects support `creator`, `brand`, `product` and
  `organization`. Migration `0020_personal_ip_differentiation` and
  `deerflow.persistence.personal_ip_differentiation` own the immutable
  `ip-differentiation-thesis-v1` lineage plus recognition/trust/intent/adoption/
  conversion/economic/extension observations. A candidate must bind intended
  influence and real alternatives to proprietary evidence, choice and belief
  reasons and explicit sacrifice. Pilot status additionally requires the
  recurring dramatic engine, stable/variable distinctive encoding, operating
  fit and falsifiable tests. Provisionally adopted requires one complete
  supportive observation; validated requires three complete supportive
  observations across two effect classes including a downstream action.
  Contradictory, mixed and inconclusive results remain evidence but cannot
  promote status. Strategy positioning onward
  must reference a pilot or adopted differentiation version. Native tools,
  preflight, account diagnosis and the owner-wide cockpit must consume the
  same owner-scoped repository; never reconstruct this thesis in a script,
  series bible, account record or chat.
- Connected-account diagnosis is content-first and evidence-bound.
  `deerflow.personal_ip.account_diagnosis` loads the authenticated account's
  current strategy, publications, metrics, creator-backend observations and
  retrospectives, then compiles one direct
  `insufficient_evidence`/`continue_current_account`/`adjust_and_retest`/
  `start_new_account` decision. Platform mechanics are recommendation
  eligibility constraints and distribution amplifiers, never the primary
  content thesis. Low reach alone must never trigger a new-account decision.
  Starting over requires platform-observed structural evidence;
  `self_entertainment` requires at least three distinct measured posts plus
  fresh, complete server evidence that influence, behavioral and economic
  outcomes all failed. A successful recognition, trust, adoption or economic
  outcome proves active IP operation even when another axis is weak; missing
  axes remain unproven. The 30-day window is an internal conservative freshness
  gate, not a platform rule. Persistent
  recommendation ineligibility requires the same normalized restriction
  reason across at least seven days, the latest status observed within 24
  hours still
  restricted and exhausted repair/appeal evidence. Keep the eight matching internal platform
  diagnosis Skills and their dated first-party evidence references aligned
  with this compiler; unpublished ranking weights remain explicitly unknown.
- `skills/public/personal-ip-operator/SKILL.md` must explicitly allow every
  native `personal_ip_*` tool plus the browser/media execution surfaces it
  directs the agent to use. MediaKit skills declare restrictive
  `allowed-tools: [bash]`; their active-skill union must not reduce an operating
  conversation to shell-only work. When a production requests
  `sequential_human_gate`, the agent submits one shot, seals its candidate and
  QA, writes a candidate-selection review request, and waits for the workbench
  approval before requesting the next shot.

Skill quality review note:

- `skills/public/skill-reviewer/` is the built-in read-only skill quality reviewer.
  It uses the harness-layer `review_skill_package` tool and contracts in
  `contracts/skill_review/`. Model-visible review data is compact and
  tag-neutralized; full raw payloads stay in tool artifacts. See
  [backend/AGENTS.md](backend/AGENTS.md) for the non-activation, SkillScan, and
  `skill-creator` ownership boundaries.

Scheduled-task note:

- The scheduled-task MVP adds a workspace page at `/workspace/scheduled-tasks` plus a background scheduler service gated by `config.yaml -> scheduler.enabled`.
- Scheduled background runs are intentionally non-interactive: they execute through the normal run lifecycle, but the lead-agent toolset excludes `ask_clarification` when `context.non_interactive=true`. The key is honored only for internally-authenticated callers (the scheduler launch path); client-supplied `context.non_interactive` is dropped.
- Personal-IP metric schedules should call
  `personal_ip_sync_douyin_portfolio`, not loop over an account captured in the
  task prompt. Use a stable hourly `collection_key`; every post failure is
  isolated and returned with sanitized coverage.

## Commands: Root vs. Module

**Root `make` targets drive the whole stack** (run from the repo root):

```bash
make setup       # Interactive setup wizard (recommended for new users)
make doctor      # Check configuration and system requirements
make dev-direct  # Start trusted local frontend + Gateway without host nginx
make support-bundle  # Generate redacted troubleshooting summary, AI issue draft, and optional zip
make config      # Generate local config files from the examples
make check       # Check that required tools are installed
make install     # Install dependencies; install pre-commit hooks only in a Git checkout
make ip-clean-install  # Full credential-free source-archive acceptance gate
make dev         # Start all services with hot-reload (Gateway + Frontend + Nginx)
make start       # Start all services in production mode (local, optimized)
make stop        # Stop all running services
make up / down   # Build/stop the production Docker stack (browser at localhost:2026)
make docker-start / docker-stop / docker-logs   # Docker development environment
```

Run `make help` for the full list.
Supported ingress and doctor profiles are defined in
[docs/RUNTIME_PROFILES.md](docs/RUNTIME_PROFILES.md).

**Per-module commands drive a single module** (run inside that module):

```bash
# Backend (see backend/AGENTS.md for the full set)
cd backend && make dev        # Gateway API with reload (port 8001)
cd backend && make test       # Backend test suite
cd backend && make personal-ip-publish-acceptance  # Local-only publish/recovery gate
cd backend && make lint       # ruff check
cd backend && make format     # ruff format

# Frontend (see frontend/AGENTS.md for the full set)
cd frontend && pnpm dev       # Dev server with Turbopack (port 3000)
cd frontend && pnpm check     # Lint + type check (run before committing)
cd frontend && pnpm test      # Unit tests
```

Rule of thumb: **root `make` = the full application**; **`backend/Makefile` and `frontend/`
(`pnpm`) = per-module work.**

## Where to Go Next

- Backend work → **[backend/AGENTS.md](backend/AGENTS.md)**
- Frontend work → **[frontend/AGENTS.md](frontend/AGENTS.md)**
- Setup & install → **[Install.md](Install.md)**, **[CONTRIBUTING.md](CONTRIBUTING.md)**
- Project overview & usage → **[README.md](README.md)** (translations: `README_zh.md`,
  `README_ja.md`, `README_fr.md`, `README_ru.md`)
- Security policy → **[SECURITY.md](SECURITY.md)**
- Changes → **[CHANGELOG.md](CHANGELOG.md)**
- Cutting a release → **[RELEASING.md](RELEASING.md)**

## Cross-Cutting Conventions

These apply repo-wide; module guides own the module-specific detail.

- **Documentation update policy** — keep docs in sync with code: update `README.md` for
  user-facing changes and the relevant `AGENTS.md` for development/architecture changes in
  the same change set.
- **Test-driven development** — features and bug fixes ship with tests. Backend tests live
  in `backend/tests/` (TDD is mandatory there; see [backend/AGENTS.md](backend/AGENTS.md));
  frontend tests live in `frontend/tests/`.
- **Format before pushing** — run `make format` (backend) / `pnpm check` (frontend). Backend
  CI enforces `ruff format --check`, so formatting must be clean before a push.
