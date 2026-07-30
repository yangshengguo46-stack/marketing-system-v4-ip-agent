# IP Agent — ByteDance/Volcengine-first DeerFlow distribution

This distribution keeps DeerFlow as the local agent runtime and uses the
ByteDance/Volcengine stack as its default capability layer.

## What is already wired

- Doubao reasoning and vision through DeerFlow's Volcengine provider.
- Seedream image generation and reference editing.
- Seedance video generation with first-frame or multi-image references.
- Doubao Speech through the existing podcast/TTS pipeline.
- The five official AI MediaKit Skills for editing, video understanding,
  image processing and audio processing.
- HLLM-Creator's complete source plus a privacy-bounded adapter for aggregate
  audience history, personalized creative generation and later shared-model
  fine-tuning.
- A first-party cinematic Personal-IP method matrix for evidence intake,
  desire and behavior, long-arc and episode writing, genre, emotion, directing,
  cinematography, performance, editing, sound, production design, continuity
  review and an eight-track 96-module curriculum. Its bundled research index
  contains 358 films, 393 creators or teams and 304 evidence-labeled mechanism
  cards.
- A default `ip-agent` with portfolio-wide coordination, approval and receipt
  rules.
- Settings → Data & backup provides a credential-free owner export, verified
  same-owner restore into an empty scope, and strongly confirmed whole-domain
  deletion. Permanent deletion is never inferred from ordinary conversation:
  it requires a fresh server preview, backup acknowledgement, the exact
  confirmation phrase and local-context deletion.

UI-TARS is a default-off, source-auditable local computer organ. DeerFlow calls
it for one visual desktop step only after native Browser Control cannot finish
the work or a native desktop application is genuinely required; Agent TARS is
not included. MineContext is a native, default-on local observation source with
a persistent Settings opt-out; it never replaces DeerFlow as the agent brain.
AgentKit is not used as the
runtime because it duplicates DeerFlow in the cloud. Data Agent is not part of
the distribution.

The cinematic method matrix is private operating intelligence, not a second
agent runtime or customer-facing Skill catalog. Evidence intake appends
subject-level strategy versions and credential-free evidence references.
Blind predictions, publishing, metrics, retrospectives and rule promotion use
the existing Personal-IP native services. The bundled curriculum CLI is
read-only and may generate plans or assessment templates, but it cannot create
a parallel project or completion ledger.

The operating entity may be a person, brand, product or organization. IP is
modeled as an influence asset rather than a synonym for a creator account:
the product stores an immutable `ip-differentiation-thesis-v1` lineage with
the intended public influence, choice field, proprietary truth, reason to
choose and believe, explicit sacrifice, recurring dramatic engine,
distinctive encoding and falsifiable validation. Strategy positioning and
launch work must reference a pilot or adopted differentiation version.
Recognition, trust, intent, adoption, conversion, economic and extension
effects are sealed as owner-scoped observations; missing coverage remains
missing. A product is a first-class subject in the Gateway and portfolio UI.

## First run

```bash
cp .env.example .env
make setup
make ip-init
make install
make doctor
make dev
```

Choose Volcengine in the setup wizard and place your Ark API key in
`VOLCENGINE_API_KEY`.

After a source update, `make doctor` reports whether the installed product
agent is stale. Run `make ip-refresh` to update the managed `ip-agent`
instructions and configuration without replacing `USER.md`.

To build the pinned AI MediaKit CLI source used by the bundled Skills:

```bash
make volcengine-install
make volcengine-doctor
```

To install the exact local source-renderer dependencies:

```bash
make video-renderers-install
make video-renderers-verify
```

HyperFrames 0.7.57 is the default interactive renderer. Remotion 4.0.488 is
also enabled for MVP validation and renders deterministic PNG frames through
software Chromium before project-local FFmpeg finishing. Confirm current
Remotion license eligibility before distributing a customer installation
package.

`make install` installs the exact MineContext source runtime. These commands
verify or reinstall it:

```bash
make minecontext-verify
make minecontext-install
make minecontext-doctor
```

MineContext is enabled in the shipped configuration. The first workspace load
starts bounded screen summaries for a new owner with every Personal-IP purpose
available internally. Folder monitoring remains off until an exact directory
is configured. “关闭本地上下文” persists an opt-out; clearing local data removes
captured evidence without allowing the next page load to silently restart it.

The model-facing boundary is `personal-ip-local-context-evidence-v1`. It
contains a hashed source-record reference, source kind, processed context type,
observation/seal times, bounded title/summary/keywords, partial-coverage notice,
redaction count and digest. It never includes raw screenshots, complete screen
text, raw document content, paths, vectors, cookies, tokens, passwords or API
keys. A preflight can opt into selected evidence ids only when both `preflight`
and `hllm_user_profile` purposes were authorized; the same sealed projection is
preserved in its later retrospective.

The repository contains the MediaKit Go source under
`third_party/volcengine/mediakit-cli`; the incompatible upstream arm64
executable is not used. The install target prepares two project-local source
builds without asking the customer to install them by hand:

- checksum-pinned Go builds MediaKit into `.deer-flow/bin`;
- checksum-pinned FFmpeg 8.1.2 builds into `.deer-flow/toolchains/ffmpeg` with
  libass, FreeType, Fontconfig, FriBidi, HarfBuzz, OpenH264 and VideoToolbox.

The FFmpeg downloader resumes interrupted transfers and uses the official
FFmpeg GitHub repository archive, avoiding a hard dependency on ffmpeg.org.
Both binary directories are added to the service PATH automatically. Cloud
MediaKit uses its own `MEDIAKIT_API_KEY`; without that key, trim, concat,
subtitle, mix and probe continue to run locally.

## Optional UI-TARS desktop fallback

Browser Control remains the first choice for every web platform. UI-TARS is
for DOM-inaccessible visual controls and native desktop windows only. Its
selected upstream SDK/operator source is fixed under
`third_party/bytedance/UI-TARS-desktop`; the Agent TARS task loop and upstream
precompiled libnut packages are not installed.

Configure `ui_tars` in `config.yaml`; for a remote model endpoint, export the
environment variable named by `api_key_env`, then run:

```bash
make ui-tars-install
make ui-tars-doctor
make ui-tars-start
```

On macOS, grant Screen Recording and Accessibility to the Python executable
used to launch the operator, then restart it. The native tool
`ui_tars_desktop_step` requires a Browser Control failure category or
`native_desktop_required`; web fallbacks additionally require a completed
Browser Control call in the current run. It executes at most one action and returns an
append-only receipt. Whole-screen images are pixelated locally before any
model request; only the privacy-transformed screenshot, its digest and a
relative evidence reference are stored. Cookies, tokens, passwords, browser
profile paths and raw screen text are forbidden. Publishing, sending, deletion,
settings changes and payment still require a matching structured DeerFlow
`risk_confirmation` response. Account ids select one operation target and do
not narrow portfolio authority.

## Video delivery acceptance

Run the complete credential-free acceptance after building the local media
toolchain:

```bash
make volcengine-install
make video-e2e-local
make video-e2e-local
```

The second identical run is the recovery check. Successful receipts are
re-hashed and reused, failed attempts remain immutable, event keys replay
idempotently, and the final delivery is allowed only after FFprobe,
delivery-spec and full-decode QA pass for the exact final artifact. Seedream,
Seedance and speech are simulated in this target; local MediaKit and FFmpeg are
real. No paid API is called.

The native `personal_ip_render_local_remotion_scene` tool accepts a
`personal-ip-render-scene-v1` file from the current task, creates a verified
candidate MP4 and seals the exact renderer version, input/output hashes, probe
and local zero-cost receipt in the production ledger.

To prepare the real-provider boundary without crossing it:

```bash
make video-e2e-paid-checkpoints
```

This writes `.deer-flow/acceptance/video-e2e/paid-checkpoints.json` with one
explicit command per Seedream, Seedance, speech and optional cloud MediaKit
checkpoint. The file records `executed: false`; obtain explicit approval in the
active user session before running any listed command. Ingest every emitted
`personal-ip-media-execution-v1` receipt through
`personal_ip_ingest_media_execution` immediately after its provider call.
After the approved batch and local finishing/QA are complete, run
`scripts/personal_ip_video_e2e.py ingest-real` with the acceptance root. It
verifies the existing artifacts and receipts, then idempotently seals them into
the Personal-IP ledger without making another provider call. The 2026-07-23
minimal Seedream/Seedance/Speech acceptance passed; full multi-shot,
material-video and optional cloud MediaKit acceptance remain separate gates.

`make doctor` has an IP Agent Product section. It verifies the complete
ByteDance/Volcengine source bundle, all eight browser-first platform entries,
Ark and speech credentials, optional cloud MediaKit status, the project-local
FFmpeg and source-built MediaKit CLI, Playwright Chromium, the installed IP
Agent profile and account-isolated browser-profile storage. It reports only
whether credentials exist; it never prints their values.

To create the customer-facing source package:

```bash
make ip-package
```

The command accepts only a committed tree, archives every tracked source file,
adds a per-file SHA-256 manifest, excludes `.env`, `config.yaml`, `.deer-flow`,
browser profiles, virtual environments and `node_modules`, verifies the
archive, extracts it into a temporary clean directory, installs the default IP
Agent profile there and compiles the product scripts. The archive and its
checksum are written to `dist/`. A recipient can independently verify it with:

```bash
make ip-package-verify PACKAGE=/path/to/ip-agent-source-<commit>.tar.gz
```

Before handing the archive to a customer, run the complete clean-room gate from
a committed checkout:

```bash
make ip-clean-install
```

This builds the archive through `scripts/package_ip_agent.py`, extracts it under
a new temporary directory, supplies only an allowlisted environment with fresh
HOME and dependency caches, and runs `make config`, `make ip-init`,
`make install`, `make doctor`, a repeatable SQLite migration/import probe and
the frontend production build. Missing credentials and optional local media
toolchains remain explicit doctor diagnostics; no existing secret values are
read or copied. A source archive skips repository-only pre-commit hooks because
it intentionally contains no `.git` metadata.

## Important environment variables

```dotenv
VOLCENGINE_API_KEY=
VOLCENGINE_IMAGE_MODEL=doubao-seedream-5-0-260128
VOLCENGINE_VIDEO_MODEL=doubao-seedance-2-0-260128
VOLCENGINE_TTS_API_KEY=
PERSONAL_IP_AUDIENCE_BASE_URL=http://127.0.0.1:9128
PERSONAL_IP_AUDIENCE_TOKEN=
PERSONAL_IP_AUDIENCE_MODEL=doubao-seed-2-0-pro-260215
DOUYIN_MINI_APP_ID=
DOUYIN_MINI_APP_SECRET=
PERSONAL_IP_CREDENTIAL_KEY=
MEDIAKIT_API_KEY=
MINECONTEXT_VLM_BASE_URL=
MINECONTEXT_VLM_API_KEY=
MINECONTEXT_VLM_MODEL=
MINECONTEXT_EMBEDDING_BASE_URL=
MINECONTEXT_EMBEDDING_API_KEY=
MINECONTEXT_EMBEDDING_MODEL=
VOLCENGINE_TTS_APPID=
VOLCENGINE_TTS_ACCESS_TOKEN=
```

The new-console Speech V3 path needs only `VOLCENGINE_TTS_API_KEY`. Narration
script lines can optionally set `voice_type`, `speech_rate`, `loudness_rate`
and `context_text`/`context_texts`; provider receipts store only sanitized
control values plus the context count and digest.

Generation URLs may expire, so outputs are downloaded immediately. Paid batch
generation and publishing are approval-gated by the default Agent policy.

HLLM-Creator is not installed into the Gateway Python environment. Its model
runtime is an optional, separately sized service because the official model
asset is large and the reproduction training configuration is multi-node GPU.
The full source is already present in the distribution; see
`docs/HLLM_CREATOR_INTEGRATION.md` before configuring weights or training. Run
`make hllm-doctor` to verify the source pin and required upstream files.

The audience provider uses one stable `/v1/preflight` contract. The current
deployment can run HLLM-Lite; a future GPU-backed HLLM-Creator cloud service
uses the same request and receipt, so the DeerFlow agent and evidence loop do
not change when the provider is upgraded.

Start the current lightweight provider with `make hllm-lite`. It calls the
configured Doubao Ark model to produce audience-conditioned creative variants.
Version 0 deliberately leaves `match_score` empty until the small ranking model
has been trained from real publish outcomes; it never presents an LLM guess as
a calibrated prediction.

Validated results are sealed through `POST /api/personal-ip/preflights`. The
snapshot stores the exact model request, provider/model/algorithm versions,
candidate receipt and concrete target account ids. Reusing the same operation
key is idempotent only for the byte-equivalent prediction; a different result
cannot overwrite the original preflight.

Publishing uses `/api/personal-ip/publish-receipts`. Begin the operation before
calling a platform API, UI-TARS, the native browser or a manual handoff, then
append every attempt with its platform task/post id and result. Operation and
idempotency keys cannot be reused for different requests; attempt keys cannot
be rewritten, and a confirmed publication cannot later be downgraded to a
failure. The selected account is recorded as this operation's target only.
Every begin request must include `personal-ip-publish-compliance-v1` with the
commercial relationship, synthetic-media state, sensitive topics, confirmed
rights, passed moderation and the exact disclosure plan for that platform.
The server derives the platform from the account and freezes its own
source-linked policy receipt. A `published` attempt must provide
`personal-ip-publish-compliance-evidence-v1`, bind it to that receipt and cite
credential-free proof that every required disclosure was applied. Sensitive
topics require documented human review; a successful upload alone cannot
satisfy this gate.

Observed performance enters through `POST /api/personal-ip/metrics`. Use
`window_total` or `delta` only when the collector knows the exact interval;
store lifetime/cumulative counters as `snapshot`. Query
`GET /api/personal-ip/metrics/aggregate` with a start and end time to aggregate
all active accounts. The result reports totals by platform/account plus
partial, unavailable and missing account coverage. It deliberately excludes
cumulative snapshots from daily totals and does not treat unavailable data as
zero. Repeated same-start `window_total` polls replace the earlier cutoff for
their series, so a morning count and an afternoon count are not double-counted.
Post-level observations reference the matching publish receipt, which is
the bridge to later prediction-versus-actual review.

Seal that review through `POST /api/personal-ip/retrospectives` after the
publish receipt is confirmed and one or more post-level observations exist.
The service derives the selected candidate from the immutable publish request,
finds it in the original provider receipt, snapshots the actual metrics and
computes an evidence digest. A partial observation remains partial, and a Lite
candidate without `match_score` remains `unscored`. Partial evidence remains
`insufficient_evidence`; complete evidence becomes
`eligible_for_policy_evaluation`. No single post can become a promoted pattern
or rewrite its original prediction.

Cross-sample rules are promoted through
`POST /api/personal-ip/evidence-promotions`. At least three complete
retrospectives from three different published posts must support the claim;
multiple observation horizons for one post count only once and partial data
does not fill the quota. Passing the rule automatically creates an approved
promotion with a deterministic policy decision receipt; there is no user
approval step. It can be exported immediately as
`personal-ip-approved-evidence-v1`, with each source's completeness and
scored/unscored provenance intact. Export is a candidate for later dataset or
model versioning, not an automatic live-model update.

The first official platform collector is Douyin video data. With an approved
enterprise application, `ma.video.bind` and user authorization, it queries the
fixed official endpoint and records public-video play, like, comment and share
counters as a post `snapshot` against the publish receipt. Private or missing
videos become `unavailable`, never zero. Developers with credentials can run
`make douyin-metrics-smoke`; see `docs/DOUYIN_METRICS.md`. Production
authorization uses an approved Douyin mini-app: one-use state, permission
ticket and login code are exchanged server-side; access/refresh tokens are
encrypted per operated account, refreshable, and wiped on disconnect. No API
accepts or returns raw tokens, and platform connections never bind a session's
authority to one account. `POST /api/personal-ip/metrics/collect/douyin` takes
only the connection and publish-receipt ids; the server decrypts credentials,
retries once after an automatic refresh on expiry, verifies account ownership
and records the snapshot. Credentials never enter agent context.

The same operations are native DeerFlow tools, so the model does not need to
construct internal HTTP calls:

- `personal_ip_performance_inventory` lists sanitized active connection ids
  and recent confirmed publish receipts across the whole portfolio. It omits
  request bodies, executor results and every credential field.
- `personal_ip_metrics_aggregate` reads the authenticated user's whole active
  portfolio for a time window and has no account-filter argument. Its coverage
  reports mutually exclusive missing, partial and unavailable accounts plus
  per-metric coverage instead of converting absent fields to zero.
- `personal_ip_collect_browser_portfolio_today` scans every active account in
  the eight-platform browser registry, seals its detailed dashboard evidence,
  and returns the resulting aggregate. It accepts no account id and promotes a
  count only when the rendered page explicitly says 今日/今天/Today.
- `personal_ip_sync_douyin_post` accepts only a connection id, confirmed
  publish-receipt id and observation idempotency key. Credential resolution,
  refresh and official collection stay server-side.
- `personal_ip_sync_douyin_portfolio` is the scheduled-task entry point. It
  discovers all connected Douyin accounts and confirmed publications itself,
  isolates individual failures and returns only observation references plus
  explicit coverage. It has no account-filter argument.

Douyin post counters are cumulative snapshots, not daily totals. A first sync
creates the baseline only. Each later sync derives an exact-interval `delta`
from the preceding monotonic snapshot; the delta is explicitly `partial`
because it covers one tracked post rather than proving complete account-wide
coverage. Portfolio aggregation includes the delta, excludes the cumulative
snapshots and preserves that partial-coverage warning.

For ongoing collection, create an hourly native DeerFlow scheduled task whose
prompt calls `personal_ip_sync_douyin_portfolio` with the current local hour as
the stable `collection_key` and `published_limit=500`. The first run after
midnight establishes a baseline; later runs create contained deltas. The tool
reports a partial scan when the receipt limit is reached, an account lacks a
connection, or one post fails, so the scheduled run never silently claims full
coverage.

The default IP Agent and `personal-ip-operator` Skill explicitly treat the
portfolio as conversation scope; an account is selected only for a concrete
operation and receipt.

Detailed authenticated creator-backend data uses the immutable
`personal-ip-platform-observation-v1` contract at
`/api/personal-ip/platform-observations`. It stores account/content inventory,
content metrics, audience analytics, traffic sources, comments, conversions,
platform receipts or dashboard evidence with source URL, observed time,
pagination/coverage and capture references. Source URL query/fragment data is
discarded, and nested cookie, token, password, Authorization, secret and API-key
fields are rejected before persistence. After Browser Control reads a page, the
native `personal_ip_record_browser_observation` tool seals the detailed result
without reducing the conversation to that account.

All eight browser-first platforms share the direct collector at
`POST /api/personal-ip/platform-observations/collect/browser` and the native
`personal_ip_collect_browser_page` tool. It derives the platform from the
owner-scoped account, reuses the same persistent account profile as manual
login, captures only rendered DOM business content plus a full-page screenshot
digest, and records unverified platform pages as partial single-page coverage.
The dashboard adapters retain direct rendered counts, their matched labels and
the displayed time-window label for all eight platforms. The owner-wide today
path is also exposed at
`POST /api/personal-ip/metrics/collect/browser-portfolio-today`; a longer or
unknown window is unavailable for today's query, while a collection failure
stays missing. `totals.views` is omitted when nobody supplied a valid today
view count.
The older Douyin endpoint/tool remain compatibility wrappers over the same
service. Douyin has verified dashboard/content-inventory parsing and may mark a
listing complete only when the declared count matches parsed items and the page
explicitly says there are no more works. A real persisted-login acceptance run
has captured both pages with per-post metrics; no cookies, browser storage or
request headers are read by the extractor.

The primary collector returns its credential-free detailed records immediately.
Later conversations use the whole-portfolio
`personal_ip_platform_observation_inventory` tool to locate evidence and
`personal_ip_read_platform_observation` to retrieve the owner-scoped full
records, summary, coverage and evidence provenance.

### Operating cockpit and video ledger

For a server-validated empty portfolio and an orientation/incubation request,
the first visible reply is emitted before any model or tool call as ordinary
conversation: disclosure control plus one entity-sensitive grand-tour
invitation. Later intake uses a compact reflective-interview call over recent
visible dialogue only; it can ask one answer-grounded question, stop or hand
sufficient evidence to the full operator. It does not expose a card, browse,
load Skills or inspect ledgers. Concrete script/asset/link/direction work
bypasses or interrupts that boundary. On later or non-orientation turns,
`personal_ip_startup_context` is the lightweight first read; it checks
only whether the authenticated owner has active subjects or accounts. A true
`new_owner` must not scan empty strategy, publishing, metric, retrospective or
video ledgers. A `returning_owner`, a resume request or a portfolio operating
question proceeds to the complete cockpit.

`GET /api/personal-ip/cockpit` is the shared whole-portfolio read model. It
joins the durable six-step operating loop—modeling, preflight, publish receipt,
observed performance, retrospective and evidence promotion—with explicit work
queues and bounded-history coverage. The native
`personal_ip_operating_cockpit` tool gives DeerFlow the same view; it never
takes an account filter. The cockpit also exposes sanitized blocking/warning
alerts for operating-loop failures, video-provider failures and budget
rejection/exhaustion. These are projections of existing immutable receipts and
video events, not a second mutable alert store.

### Content-first account diagnosis

After a user connects an existing account, the Agent can issue a direct
continue, adjust or new-account conclusion without mistaking platform folklore
for evidence. `personal_ip_account_diagnostic_context` loads that account's
latest strategy, published samples, metrics, creator-backend observations,
commercial outcomes and retrospectives from the authenticated owner stores.
The account id is only the diagnosis target.

Diagnosis begins with seven observable layers: processing access,
attention/prediction, emotion/identity, narrative/consumption, social
transmission, behavior/conversion and platform distribution. It then evaluates
the operating funnel `reach -> trust -> intent -> conversion`. Platform
mechanics are a constraint and amplifier: recommendation eligibility, surface
mix and current rules can explain distribution, but unpublished live weights
remain unknown and low reach alone can never prove that an account is dead.

`personal_ip_compile_account_diagnosis` enforces the decision gates. Starting a
new account requires current platform-observed evidence of a persistent
recommendation restriction, legacy audience-positioning lock,
identity/business conflict or unrecoverable compliance history. Otherwise weak
content or conversion produces an adjust-and-retest experiment on the current
account. Persistent recommendation ineligibility is an internal conservative
decision gate: the same reason must remain restricted across at least seven
days, the latest status must be collected within 24 hours and still be
restricted, and repair or appeal must be exhausted. It is not a claimed
platform ranking rule. “Self-entertainment” is an operating classification
only after at least three distinct measured posts and fresh, complete IP-asset
evidence show that influence, behavioral and economic outcomes all failed.
If brand recognition, trust, product adoption or an economic outcome succeeds,
the work is operating an asset even when another outcome is still weak.
Unmeasured outcomes remain unproven. The 30-day window is an internal
conservative freshness gate, not a platform rule; this classification is not a
tone of voice for insulting the user.

Eight internal platform diagnosis Skills cover Douyin, WeChat Channels, WeChat
Official Accounts, Xiaohongshu, X, Instagram, YouTube and TikTok. Their dated
references use first-party rules, transparency pages, creator documentation
and official algorithm filings or source code. They adapt evidence collection
and surface interpretation while keeping content as the main thesis.

Audience preflight uses `personal-ip-audience-preflight-v2`. Every candidate
freezes an evidence level, observable mechanism hypotheses, predicted signals,
failure conditions, distribution assumptions and uncertainty. Formal
predictions reject viral guarantees and dopamine/mirror-neuron/Zeigarnik
shortcuts. Platform allocation, audience match, competition, timing and
stochastic social feedback remain explicit outcome uncertainty. The first
pilot may preflight with no account history only as
`cold_start_hypothesis`; its history remains empty and its variants remain
unmeasured.

Video production uses `personal-ip-video-production-v1`. Begin one immutable
idea/script request through `personal_ip_begin_video_production`, then append
blueprint, asset, storyboard, shot generation/failure/retry, consistency,
selection/review, voice/edit and delivery events through
`personal_ip_record_video_production_event`. Each event can retain provider,
model, task id, artifacts and cost without making any provider the workflow
owner. `personal_ip_read_video_production` resumes from the complete ordered
ledger; only a successful delivery event marks the project complete.
For paid providers, freeze `currency`, `hard_limit` and the approval policy in
that request. Create a paid-call review request and obtain the authenticated
workbench decision when required, then call
`personal_ip_reserve_video_budget` before each submission. The server
atomically rejects any maximum that would make settled spend plus active
reservations exceed the limit. Bind the provider request to that reservation,
then settle its authoritative actual cost with
`personal_ip_settle_video_budget`; failed attempts still count and every retry
needs a new reservation. Unknown billing leaves the maximum reserved. Use
`personal_ip_release_video_budget` only when no provider call occurred.

Long-form video, recorded-course, interview and podcast methods use the same
evidence boundary. Parse and seal a `personal-ip-video-pattern-v1` first, then
call `personal_ip_compile_video_method_distillation` with timestamped abstract
evidence and exact-span hashes. Each accepted method needs two independent
source contexts plus trigger, non-trigger, edge and sibling-confusion tests.
`personal_ip_compile_video_method_skill_candidate` emits one atomic candidate;
it never installs automatically. Save it only through `skill_manage` so
security scanning, owner isolation, version history and rollback remain active.

### Browser-first platform accounts

Douyin, WeChat Channels, WeChat Official Accounts, Xiaohongshu, X, Instagram,
YouTube and TikTok use local browser login state by default. Call
`personal_ip_select_browser_account(account_id)` before a concrete platform
operation. DeerFlow then uses a persistent Chromium profile isolated by
authenticated user and operated account; switching accounts switches the
browser target but never changes conversation authority.

Passwords, cookies and the local profile path never enter model context. The
user completes QR login, CAPTCHA, MFA and identity checks in the live browser.
Official OAuth/API integrations, including the existing Douyin connector, are
optional accelerators. See
[`docs/BROWSER_FIRST_PLATFORM_CONNECTIONS.md`](docs/BROWSER_FIRST_PLATFORM_CONNECTIONS.md).

See `product/volcengine/capabilities.yaml` for the complete routing policy.
