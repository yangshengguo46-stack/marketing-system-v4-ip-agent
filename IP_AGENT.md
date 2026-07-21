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
- A default `ip-agent` with portfolio-wide coordination, approval and receipt
  rules.

UI-TARS and MineContext remain optional local connectors. AgentKit is not used
as the runtime because it duplicates DeerFlow in the cloud. Data Agent is not
part of the distribution.

## First run

```bash
cp .env.example .env
make setup
make ip-init
make install
make dev
```

Choose Volcengine in the setup wizard and place your Ark API key in
`VOLCENGINE_API_KEY`.

To build the pinned AI MediaKit CLI source used by the bundled Skills:

```bash
make volcengine-install
make volcengine-doctor
```

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

## Important environment variables

```dotenv
VOLCENGINE_API_KEY=
VOLCENGINE_IMAGE_MODEL=doubao-seedream-5-0-260128
VOLCENGINE_VIDEO_MODEL=doubao-seedance-2-0-260128
PERSONAL_IP_AUDIENCE_BASE_URL=http://127.0.0.1:9128
PERSONAL_IP_AUDIENCE_TOKEN=
PERSONAL_IP_AUDIENCE_MODEL=doubao-seed-2-0-pro-260215
DOUYIN_MINI_APP_ID=
DOUYIN_MINI_APP_SECRET=
PERSONAL_IP_CREDENTIAL_KEY=
MEDIAKIT_API_KEY=
VOLCENGINE_TTS_APPID=
VOLCENGINE_TTS_ACCESS_TOKEN=
```

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

Observed performance enters through `POST /api/personal-ip/metrics`. Use
`window_total` or `delta` only when the collector knows the exact interval;
store lifetime/cumulative counters as `snapshot`. Query
`GET /api/personal-ip/metrics/aggregate` with a start and end time to aggregate
all active accounts. The result reports totals by platform/account plus
partial, unavailable and missing account coverage. It deliberately excludes
cumulative snapshots from daily totals and does not treat unavailable data as
zero. Post-level observations reference the matching publish receipt, which is
the bridge to later prediction-versus-actual review.

Seal that review through `POST /api/personal-ip/retrospectives` after the
publish receipt is confirmed and one or more post-level observations exist.
The service derives the selected candidate from the immutable publish request,
finds it in the original provider receipt, snapshots the actual metrics and
computes an evidence digest. A partial observation remains partial, and a Lite
candidate without `match_score` remains `unscored`. Every retrospective starts
as `pending_human_review`; no single post can automatically become a training
example or rewrite its original prediction.

Cross-sample rules are proposed through
`POST /api/personal-ip/evidence-promotions`. At least three complete
retrospectives from three different published posts must support the claim;
multiple observation horizons for one post count only once and partial data
does not fill the quota. The agent may assemble the candidate, but the terminal
decision endpoint requires an explicit authenticated-user confirmation and
rationale. Only an approved proposal can be exported as
`personal-ip-approved-evidence-v1`, with each source's complete/partial and
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

See `product/volcengine/capabilities.yaml` for the complete routing policy.
