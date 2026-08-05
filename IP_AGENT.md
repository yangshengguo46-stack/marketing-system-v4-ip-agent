# IP Agent product contract

This file is the sole product contract for IP Agent. The active product has one
shared content lineage and three customer boards: breakdown, a two-part writer
brain and production. Delivery status and real-sample evidence remain separate
in the product ledger; a schema or mocked test is never a completion claim.

## Product boundary

IP may be carried by a person, brand, product or organization. The clean
baseline answers the user's current request and keeps three kinds of claims
separate: user-provided facts, source-backed facts and clearly labelled
creative hypotheses.

The default Agent does not run a fixed onboarding interview, inspect operating
ledgers on the first turn, diagnose accounts, predict virality or manufacture
an incubation workflow. It exposes two active creation entries: a zero-start
original and an exact benchmark link/upload. Account history remains a future
entry and must not appear as an active route.

The writer board has one decision authority and one bounded specialist. The
total-editor controller decides the ordered conversion/recognition/trust
mission, time horizon, audience uncertainty, attribution carrier,
differentiation hypothesis and work route. The semantic-causal core is optional
and has no persistence or routing authority: direct offer, proof, demonstration
and explanation work skips it; semantic-story and hybrid work binds its exact
route into the causal seed and script receipt. The two parts never converse as
independent autonomous Agents.

## System constitution

IP is a time-varying relationship between a person, brand, product or
organization and a target audience. The relevant state is not content volume;
it is recognition, memory, trust, expectation, preference and action. Content
is an intervention into that relationship, platforms are environments and
distribution channels, and metrics are delayed, noisy observations rather than
the relationship itself.

The product purpose is to help an IP subject change that audience relationship
through truthful evidence, original content, real execution and delayed
external feedback, under the Owner's goals and safety constraints.

The architecture is governed by four inseparable lenses:

- systems theory owns purpose, boundaries, hierarchy, stocks, flows and delays;
- ontology owns entities, relationships, state, authority and bounded context;
- information theory owns identity, provenance, coverage and lossless transfer;
- control theory owns goals, observation, action, feedback and correction.

Every product path must preserve four separate worlds: reality, epistemic
claims, creative fiction and execution receipts. Creative fiction is allowed;
presenting it as a user fact or source observation is not. The shared epistemic
states are `user_asserted`, `source_observed`, `derived`, `hypothesized`,
`creative`, `unknown` and `contradicted`.

The active content lineage is:

```text
Owner -> Subject -> EditorialProgramVersion -> ContentWork(Objective)
  -> BreakdownVersion -> DirectionVersion -> ScriptVersion
  -> VideoProduction -> Artifact -> Publication
  -> Observation -> LearningDecision
```

`EditorialProgramVersion` is the small cross-work total-editor decision. It
holds only an ordered mission and time window, audience hypothesis, explicit
person/product/brand/organization attribution, one still-unvalidated
differentiation hypothesis and an optional recurring human theme. It may govern
one urgent work or many continuing works. It is not the retired global strategy
layer: it has no onboarding sequence, maturity ladder, operating cockpit or
automatic publication gate. A Work binds one exact immutable program version
and never silently rebinds.

`BreakdownVersion` is required for the benchmark entry and optional for
zero-start work. Objective, Work and every immutable version have stable server
identities. Agent-created works record their originating task id, but a task id
never grants Owner authority. The feedback tail remains a later vertical slice;
missing observations stay missing.

Agent runtime, models, MCP and Skills orchestrate or transform these objects;
they do not become the authority for business facts. MCP Sensors obtain external
evidence, pure Skill Methods transform typed inputs into typed outputs, MCP
Effectors perform controlled side effects, and domain services plus immutable
ledgers own product state. The user remains the co-controller for goals,
meaning corrections and consequential choices.

## Media capability boundary

Volcengine AI MediaKit is the selected media execution subsystem. It owns
commodity video, image and audio understanding and processing: metadata, ASR,
OCR, frame/scene operations, storyline/highlight analysis, editing, transcoding,
enhancement and result delivery when the corresponding official capability has
passed a real local or cloud acceptance.

MediaKit is not the IP business brain. It does not own platform account or work
identity, evidence provenance, IP subjects and objectives, transferable causal
mechanisms, creative direction, publication state or feedback decisions. The
bounded Evidence MCP must first resolve the exact source and seal its identity,
snapshot hash, observation time and coverage. A thin adapter may then submit
that sealed snapshot to the pinned official CLI/API and normalize its receipt;
it must not rebuild the provider's upload, polling or media algorithms.

The five upstream Bash-based MediaKit Skills remain internal implementation
assets and are not exposed directly to the clean IP Agent. Product-page or
API-only capabilities are target inventory until their exact input, terminal
result, cost and evidence boundaries pass a real sample. Provider output remains
untrusted observed material and cannot itself decide an IP direction or claim a
causal business result.

The pinned CLI is version `0.2.0` and exposes exactly 40 commands; the product
catalog, official MCP, bundled Skills and the advertised “100+” capability pool
are different surfaces and are never treated as interchangeable contracts.
`product/volcengine/capabilities.yaml` is the machine-readable inventory and
promotion state. `third_party/volcengine/mediakit-cli/VENDORED_VERSION.json`
fixes the exact non-prebuilt source tree and catalog; build/doctor validation
fails on source or command drift. No catalogued capability enters the default
Agent until it is explicitly `product_promoted`.

MediaKit also publishes a separate Video Understanding Chat API at
`amk-ark.cn-beijing.volces.com`; it is not one of the pinned CLI's 40 commands.
That API wraps an Ark model with provider-managed extraction and serialization
of frames and accepts text plus a video URL. The documented 5 GB ceiling applies
to URL inputs; it must not be generalized to Base64 payloads handled by Ark's
separate direct API. It does not analyze the video's audio. Its `fps` range is `0.01–5`;
`max_frames`, `max_pixels` and the internal token ceiling also bound
what the model can actually see. The result is therefore a useful semantic
observation, not a transcript, exhaustive frame record, platform identity or
causal IP conclusion. It remains unexposed and unintegrated until a fixed
structured question contract is compared with human-annotated videos and its
temporal coverage, hallucination and repeatability are measured. The fixed
URL-only adapter has now passed two repeated official-fixture runs and one
exact account-bound Douyin work in an isolated operator path. It remains
unexposed to the Agent and is not yet part of the Evidence MCP contract: two
further heterogeneous videos, paid-call reconciliation and an isolated Agent
replay still gate promotion. A follow-up paid probe with the real test-mode
credential returned `500 OperatorError` for the stable canonical Douyin work
page. Uploading the hash-verified local snapshot through MediaKit succeeded,
but giving the resulting `mediakit://` file id to Chat also returned `500`.
The successful resolved Douyin media URL is time-limited and therefore cannot
bind a later approved replay. Promotion also requires a controlled, revocable,
read-only HTTPS media ingress that binds the sealed local source hash to the
runtime provider-input digest without exposing that URL to the model or
ordinary receipts. The current MediaKit upload path has no product-verified
delete receipt and is not a substitute for that boundary.

The separate Video Understanding Smart Strategy is a different asynchronous
contract. It can inspect audio, route among models and frame-selection strategies,
and change that route when the prompt contains audio-related words. Its manual
`fps` range is `0.2–5`, not the Chat API's range. This convenience makes the
result less reproducible, so it remains a provider inference and must not be
silently aliased to Chat, ASR or source fact.

MediaKit's Vibe Editing, semantic segmentation, drama-script restoration and
drama-recap APIs are also separate contracts rather than hidden CLI commands.
Vibe can turn natural-language instructions plus public media URLs into a
multitrack cloud-rendered artifact, but the current REST response contains only
the final artifact, not an EDL, editable timeline, operation receipts or source
project. The interactive preview editor exists in the MediaKit console; its
integration API and Web SDK are documented as future capabilities. Vibe may
therefore generate a rough-cut candidate, but it cannot own the product's
editable project or deterministic final render.

Drama-script restoration is reverse analysis for eligible live-action dramas
and films with hard subtitles. It explicitly excludes animation, documentary,
advertising and livestream recordings, and it is not a general IP script writer.
Semantic segmentation returns provider-selected time boundaries, not editorial
decisions or transcript content. Domain-specific drama/highlight/recap routes
must never become the default path for ordinary personal, brand or product IP.

`video-use` is retained as an editing-director method: source discovery,
strategy confirmation, typed and versioned timeline decisions, cut review,
user-directed iteration and independent QA. Its unsafe helper scripts are not a
product runtime. MediaKit's sentence/segment ASR may replace transcription for
content understanding and subtitles, but it does not provide the word-level
timestamps required for word-boundary cuts and cut padding. MediaKit may replace
other accepted sensor and commodity execution ports beneath the method.
HyperFrames as the programmatic renderer and Remotion as a compatibility-only
path is the target consolidation, not current shipped behavior: HyperFrames is
currently an unregistered fixed template, Remotion still has a live tool, and
both current templates mute source video. Neither may be retired until the same
programmatic-scene golden suite and existing-project migration pass.

The active MediaKit cloud adapter accepts only the same private local snapshot
whose SHA-256 was sealed by the Evidence MCP; it never asks MediaKit to fetch
the mutable public URL again. One evidence request gets a temporary `0700`
request root and an isolated CLI home for each ASR/OCR/scene/storyline stage.
The stages of one video run concurrently; videos remain sequential. Each stage
has a submission timeout and a separate 300-second bounded polling window, and
both the capability dispatcher and stdio MCP call have a 3,600-second outer
deadline. Cancellation waits for already-started provider workers before their
temporary directories are removed. The adapter avoids MediaKit CLI's unbounded
`poll-complete` mode. A versioned media-semantic allowlist removes operational
IDs, URLs, paths, secrets and raw provider envelopes without treating those
intentional redactions as missing semantic coverage. The execution receipt must
hash the exact payload exposed as evidence. The adapter verifies the sealed
local content hash before and after the official CLI call. The provider's lack
of a separate content digest attestation remains recorded in the receipt, but
it no longer downgrades a successfully returned stage to partial.

The presence of `MEDIAKIT_API_KEY` enables direct cloud execution for the two
default Evidence MCP tools. The Agent-facing video tool intentionally exposes no
cheap-depth or frame-count switch: every call performs `full` analysis with 12
uniform frame samples plus ASR, OCR, scene segmentation and storyline analysis.
These calls do not require a per-call approval, proposal ledger or
model-supplied budget. A failed cloud stage is retried once inside the same tool
call with a fresh provider task. The API key stays in the process environment
and is never placed in tool arguments, model context or normal receipts. Direct
provider idempotency tokens are scoped to the current evidence request and
stage attempt, so a later Agent turn performs a new execution instead of
silently reusing an older task. `ip-init` and `ip-refresh` create or preserve
the local account-binding keyring needed by the companion Douyin inventory
tool.

The legacy admission schemas in migrations `0022_personal_ip_paid_call_admission` and
`0023_personal_ip_paid_call_execution_run` and
`0024_personal_ip_paid_call_operator_cap` separate origin and execution runs,
record Owner decisions, atomically reserve/admit an exact provider request, and
mint a signed one-use ASR-only grant. The grant binds Owner, Thread, run, source,
stage, capability and a local risk limit; its provider idempotency key is also
Owner/call isolated. They remain for compatibility with dedicated execution
surfaces and are not on the default Agent's MediaKit evidence path.

The active path passed the earlier real checks on the 3.648-second Mandarin fixture:
one direct MediaKit ASR call, one stdio Evidence MCP `speech_text` call returning
completed ASR and OCR, and one real `ip-agent` turn that selected
`ip_evidence_inspect_reference_videos` and used its result. A subsequent real
`full` execution finished in 135.353 seconds with ASR, OCR, provider scene
segmentation and storyline all `completed`; it returned one scene segment, one
storyline clip and one highlight with no limitation. MediaKit still
misrecognized the known word “回执” as “回值”; this is preserved as an ASR
accuracy observation rather than hidden by the integration. The current adapter
polls within the live request and cannot resume an in-flight provider task after
process loss. Separate Chat, Remux and Vibe canaries remain separate capabilities
and are not implied by this Agent integration.

The final Agent acceptance on 2026-08-04 used a clean thread and the uploaded
fixture. It made exactly one `ip_evidence_inspect_reference_videos` call, ran
`analysis_depth=full` with 12/12 frame samples, and completed source identity,
metadata, contact sheet, local scene detection, ASR, OCR, provider scene
segmentation and storyline with `operation_status=ok` and no limitation. The
turn finished in 176.104 seconds. This acceptance replaced an earlier run in
which the model first chose `speech_text` and then repeated the complete tool;
the Agent-facing cheap-depth/frame-count choices and the obsolete ASR grant
verifier were removed after that failure.

## Active Agent runtime

The installed `ip-agent` uses:

- `skills: []`;
- `memory_enabled: false`;
- the eight baseline tools `web_search`, `image_search`, `ls`, `read_file`,
  `glob`, `grep`, `view_image`, `ask_clarification`;
- the MediaKit-backed Evidence MCP tools
  `ip_evidence_collect_douyin_benchmark_account` and
  `ip_evidence_inspect_reference_videos`;
- the bounded content tools `ip_content_read`,
  `ip_content_save_breakdown`, `ip_content_write` and
  `ip_content_start_production`;
- the compact product prompt in
  `product/defaults/agents/ip-agent/SOUL.md`.

An external video Breakdown can be saved only when the same task contains the
exact typed Evidence MCP ToolMessage. The server derives source identity,
contract version, item index and payload hashes and stores the complete typed
evidence snapshot separately from model interpretation. A formal v2
EditorialProgramVersion and DirectionVersion can be committed only with the
total-editor service's exact decision digests. A formal ScriptVersion can be
written only by the bounded writer brain after its fail-closed truth and
semantic-route verifier succeeds; the structured verifier receipt, its digest,
the Direction decision digest and the Program/route digests remain replayable
with the Script. Server-bound Breakdown and Direction ids are validated
separately from those decision-body digests. REST clients cannot bypass these
receipts.

Direct offer, proof, demonstration and explanation routes do not invoke the
semantic-causal story engine and are factual. `semantic_story` uses the
fictional truth boundary; `hybrid` uses the hybrid truth boundary. Both store an exact
association path from the source concept to a selected human theme. Fiction
then uses only an industry-neutral seed whose causal pattern and route digest
match that decision, and locks one causal story before production constraints
are applied. Factual and hybrid scripts use explicit claim bases; unsupported
facts or a semantic mismatch reject the entire transaction, leaving no partial
Program, Work, Direction or Script.

Production starts from an exact immutable ScriptVersion. The existing video
production/event ledger remains the only production truth: one script may drive
many productions, while each production seals its source snapshot and never
rebinds when a later script version appears.

A linked production can become completed only when the latest locked timeline,
the exact latest successful delivery execution and the latest passing delivery
QA are sealed atomically with one `personal-ip-final-artifact-v1` record. The
formal Artifact is the only final-video projection for a linked production;
QA previews, generic event attachments and raw local paths never substitute for
it. Its stable identity binds the Owner, Work, Script, production, execution
receipts, QA receipt, storage key, content SHA-256, size, canonical MIME and
public metadata.

Artifact identity and local byte availability are deliberately separate. JSON
Owner backups contain the signed identity and receipts but not the video bytes,
so restore always sets `content_available=false`. Playback and download then
fail closed until the Owner reattaches the original bytes and the server verifies
their exact SHA-256, size and MIME without changing Artifact identity.

An empty Skill list removes Skill discovery/evolution instructions. Disabled
memory removes memory loading and updates. The allowlist is applied after all
configured, built-in, MCP, ACP, sub-Agent and self-modification tools are
assembled, so an excluded tool cannot leak in through another source.

The retired Personal-IP portfolio context middleware is not mounted for this
Agent. The four bounded content tools receive only authenticated, injected
repositories and do not perform startup scans. Simple
conversation therefore goes directly to one model call and makes no tool call.
Search is used only when the answer depends on current or externally verified
facts. Search citations are ordinary Markdown links placed next to the claim.
An exact video link or `/mnt/user-data/uploads/` path routes to video evidence
instead of web search or a repeated upload request.

## Retained execution products

The following owner-scoped product surfaces remain available through dedicated
UI and/or explicit APIs. Except for the bounded ScriptVersion-to-production
entry above, they are not tools of the default Agent:

- subjects, accounts, platform connections and OAuth;
- publish requests and append-only attempts;
- metrics and credential-free platform observations;
- video productions and their append-only event ledger;
- formal final-Artifact receipts plus Owner-scoped content read and exact-byte
  reattachment APIs;
- the factual workspace dashboard.

The general video workbench Agent runtime entry remains off. The content board
may start and display a linked production, and the dedicated Owner production
surface may edit its existing ledger and play, download or reattach a formal
Artifact. This does not expose the legacy production tool catalog or add real
supplier execution to the default Agent. Reachability and end-to-end execution
status are recorded only in `docs/IP_AGENT_PRODUCT_LEDGER.md`.

The dashboard displays observations and their timestamps. Missing data stays
`未采集`; it does not infer high potential, paid-traffic suitability, or a
continue/adjust/restart verdict.

## Stable execution invariants

Credential ciphertext, passwords, cookies and one-use OAuth state never enter
model context or Owner backups. Publishing still validates rights, moderation,
commercial/AI disclosure and public-post proof. Video execution still enforces
rights, paid-call approval and reservation, immutable receipts, paths, hashes,
candidate consistency, QA and idempotency. Owner data export, same-owner
empty-scope restore and confirmed deletion remain enforced.

Current Owner backups use the v5 server-keyed HMAC manifest and `key_id`; v4
backups retain their original HMAC contract and are promoted in memory, while
legacy v1-v3 backups retain their historical unkeyed digest contract only. Formal video
bytes are downloaded separately. Destructive deletion requires an independent
Artifact-file acknowledgement, verifies each recorded file identity, moves the
exact file to Owner-local quarantine before database commit, restores it on a
pre-commit failure and purges it only after commit. This two-phase boundary does
not claim global atomicity across the database, MineContext, filesystem and
process crashes, or recursive deletion of historical files that have no formal
Artifact receipt.

These are execution invariants, not creative or business judgments.

## Retired semantic layer

Migration `0021_personal_ip_semantic_layer_retirement` retires strategy,
differentiation, asset observation, preflight/HLLM-Lite prediction,
retrospective, evidence promotion and legacy identity/reputation tables. It
also removes `preflight_id` from publish receipts. Upgrade refuses to drop a
non-empty retired table and requires a verified Owner backup first. Downgrade
can recreate only empty compatibility schemas; it cannot restore deleted data.

The matching repositories, routes, tools, dependency injection and customer UI
are removed. Retired endpoints return 404 and a fresh database does not create
the retired tables.

The route-specific `DifferentiationHypothesis` embedded in an immutable
EditorialProgramVersion is not a restoration of that layer. It is always
labelled hypothesized, has no independent repository, validation status,
observation ladder or promotion workflow, and cannot claim market proof.

## Research quarantine

The 35 cinematic modules, platform methods, Cangjie-derived method research,
HLLM sources and video-analysis methods are retained for audit and future
design. They are not active Agent capability. Python research adapters live
under `product/research/ip-agent/`; third-party source remains under
`third_party/`. Production Python packages, routes and tools must not import the
research quarantine.

Do not describe a research file, Skill package, schema or mocked test as a
working product path.

## Local verification

```bash
make ip-refresh
make ip-test-reset
make ip-test-start
make ip-test-status

make personal-ip-data-lifecycle-acceptance
make personal-ip-publish-acceptance
make personal-ip-observability-acceptance
make personal-ip-cost-acceptance
make video-e2e-local
```

`make ip-test-reset` rotates only the marked isolated test home into a
recoverable snapshot. It never rewrites the normal Owner home.

Current delivery state lives only in `docs/IP_AGENT_PRODUCT_LEDGER.md`. It
separates the three customer boards—breakdown, writer brain and production—from
their shared execution substrate and feedback loop.

`docs/IP_AGENT_AUDIT_REMEDIATION_LEDGER.md` is a frozen historical closeout.
The exhaustive, code-checked catalog of active, isolated and conditional tools
plus the generated inventory of quarantined public Skills lives in
`docs/IP_AGENT_SKILL_CAPABILITY_BOUNDARY_LEDGER.md`; neither file is a current
product-completion record.
