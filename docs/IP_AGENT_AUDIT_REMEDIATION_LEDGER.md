# IP Agent audit remediation ledger

This ledger turns the 2026-07-29 audit into executable work. It complements
`IP_AGENT_PRODUCT_LEDGER.md`: the product ledger measures customer completion,
while this file records concrete defects, evidence, acceptance gates and the
order in which they will be closed.

## Status vocabulary

- `done`: implemented and verified by the acceptance evidence in this ledger.
- `verifying`: implementation exists, but the named gate has not completed yet.
- `ready`: locally actionable without real customer credentials or paid calls.
- `external gate`: requires a real account, OS permission, explicit human
  approval, paid-provider authorization or another external dependency.

## Audit snapshot

The audit does **not** show that Personal-IP was written only in the frontend.
The backend has owner-scoped repositories, migrations, routers, native tools
and immutable ledgers. The break is between implementation and proof: the two
mocked Playwright scenarios exercised the UI, while the real-backend Playwright
suite contained no Personal-IP flow.

Anonymous local SQLite evidence at audit time:

| Record | Count |
| --- | ---: |
| Platform accounts | 5 |
| Platform observations | 27 |
| Preflights | 0 |
| Publish receipts | 0 |
| Metric observations | 0 |
| Retrospectives | 0 |
| Evidence promotions | 0 |
| Strategy versions | 0 |
| Video productions / events | 3 / 26 |

This means the base and collection surface exist, but the main
strategy-to-publication-to-learning loop has not yet produced persisted local
evidence.

## Remediation register

| ID | Priority | Area | Audit finding | Acceptance gate | Status |
| --- | --- | --- | --- | --- | --- |
| AUD-ENG-001 | P0 | Relocation | Local Python console scripts retained shebangs from the deleted source directory, breaking Make targets after the project move. | Local Make, serve and container launchers invoke `python -m pytest` / `python -m uvicorn`; relocation regression passes. | done |
| AUD-ENG-002 | P0 | Relocation | The current backend and MineContext virtual environments still contain stale generated entrypoints/editable-install metadata. | Rebuild both ignored runtimes in the new directory; `make minecontext-doctor` and entrypoint scan show no old path. | done |
| AUD-ENG-003 | P0 | Packaging | The package test fixture copied MineContext runtime bytecode and force-added it, so ordinary prior imports broke source-package acceptance. | Package tests exclude runtime bytecode from the synthetic source checkout and all package tests pass. | done |
| AUD-TST-001 | P0 | Full stack | Personal-IP had two Playwright scenarios, both fully mocking backend APIs; the real-backend suite had none. | Real Next.js + real Gateway + temporary migrated SQLite: create subject through UI, read it through the API, insert an account through the API, reload and render the stored account. | done |
| AUD-TST-002 | P0 | Frontend startup | Default Playwright allowed 120 seconds, while the audited production build needed about 165 seconds. | Default web-server startup timeout is 300 seconds and the mock suite can reach test execution. | done |
| AUD-TST-003 | P0 | Test isolation | Mocked web-fetch tests used the machine's live DNS; Clash RFC 2544 fake-IP answers caused 11 false failures. | Browserless, Crawl4AI and fastCRW unit tests inject deterministic public DNS while private/metadata rejection tests remain active. | done |
| AUD-TST-004 | P0 | Full-stack isolation | The real-backend Playwright build inherited `frontend/.env` and could call a developer gateway on port 8001 instead of its temporary replay gateway. | The config explicitly clears both public backend URLs and forces same-origin rewrites to the ephemeral gateway. | done |
| AUD-QA-001 | P0 | Regression | The full backend suite had environment-sensitive failures and the root suite had one package-fixture failure. | Root suite, backend suite, frontend unit suite and `pnpm check` are green from the moved checkout. | done |
| AUD-QA-002 | P1 | Build performance | Next production build is unusually slow and reports whole-project NFT tracing from a dynamic artifact route. | Scope the traced filesystem path, remove the warning and record a repeatable build time below the Playwright startup budget. | done |
| AUD-LOOP-001 | P0 | Strategy | No local strategy version or launch-ready natural incubation has been persisted. | Complete one natural subject conversation through real benchmark evidence, alternatives, launch package, pilot and validation. | external gate |
| AUD-LOOP-002 | P0 | Closed loop | Local preflight, publish, metric, retrospective and promotion tables are empty. | Seal three distinct publications from blind prediction through measured retrospective and one policy-approved evidence promotion. | external gate |
| AUD-DIST-001 | P1 | Platforms | Evidence is concentrated in Douyin/WeChat/Xiaohongshu; X, Instagram, YouTube and TikTok have no accepted evidence. | Run the account/login/collection/publish/recovery matrix per platform with explicit coverage states. | external gate |
| AUD-VID-001 | P1 | Video | Local video E2E simulates paid providers; paid calls executed by that gate are zero. | Accept one full multi-shot generative production and one real faceless-material production with immutable provider/cost/QA receipts. | external gate |
| AUD-COMP-001 | P1 | Publishing compliance | Publish requests remain generic JSON and do not yet enforce platform-specific disclosure, commercial-partnership or moderation fields. | Add versioned per-platform compliance schemas, validation and receipt evidence before prepare/finish. | done |
| AUD-COST-001 | P1 | Cost control | Video budgets are recorded but not enforced as admission limits. | Reserve, accumulate and reject over-budget paid operations before provider submission; test retries and concurrent reservations. | done |
| AUD-DATA-001 | P1 | Data lifecycle | MineContext deletion exists, but whole Personal-IP export/backup/restore/delete is absent. | Owner-scoped export, verified restore and destructive-delete flow cover every Personal-IP repository without leaking credentials. | done |
| AUD-OBS-001 | P2 | Operations | Product observability is mostly optional and the local doctor reports missing nginx and unconfigured web tools. | Define the supported local/prod profile, make required health checks green and surface loop/provider/cost failures in the operating console. | done |
| AUD-OS-001 | P2 | Desktop fallback | UI-TARS source and permission checks exist, but the runtime/model are disabled and no live desktop acceptance was executed. | Explicitly enable, approve and run one sanitized macOS fallback receipt without exposing raw screenshots or credentials. | external gate |
| AUD-ONB-001 | P0 | First use | New owners shared the returning-owner cockpit entry and could scan every empty strategy/publish/metric/retro/video repository before answering the first request. | Startup-context unit/tool tests prove that an empty owner reads only subjects/accounts, returns `new_owner`, and defensively skips the full cockpit; welcome copy does not require an account. | done |
| AUD-ONB-002 | P0 | First reply | A first-use orientation could still enter the generic research/Skill loop, spend multiple provider calls and stall behind browser search or CAPTCHA before showing any answer. | Real Next.js + real Gateway + isolated empty SQLite returns one provisional route and one entity-sensitive clarification within three seconds on a cold local runtime; its structured answer advances to a target-group/core-problem question without repeating the first. Both runs use 0 model calls, 0 tokens, no follow-up-suggestion request and no web/Skill/ledger operation; concrete script/asset/link tests still reach the normal model path. | done |
| AUD-ONB-003 | P0 | Narrative interview | The fast first-use path is still a deterministic pair of clarification cards. It collects fields but cannot reflect the user's language, revise a hypothesis, change the next question from the answer, or preserve narrative and disclosure control. | Real Next.js + real Gateway + isolated SQLite proves ordinary conversational onboarding with no intake cards; person, brand, product and organization openings use entity-appropriate grand-tour invitations; three materially different answers produce answer-grounded different follow-ups with one main question per turn; skip/correct/private/stop requests are honored; earliest-memory and sensitive-history prompts are never the default and are not repeated after refusal; direct tasks bypass incubation; confirmed facts, tentative interpretations and evidence gaps remain distinct; bounded interviewer calls do not regress to the full-agent 80k-token path. | done |
| AUD-CAL-001 | P0 | Content evidence | Pilot/preflight guidance separated hypotheses from evidence in prose, but formal contracts could still contain neural shorthand or unsupported viral certainty and did not freeze distribution assumptions. | Strategy v4 and audience-preflight v2 tests require evidence level, observable mechanism, predicted signal, failure condition, distribution assumptions and uncertainty; neural shortcuts and viral guarantees are rejected; a first pilot with no account history stays an explicit unmeasured cold-start hypothesis. | done |
| AUD-DIAG-001 | P0 | Account diagnosis | Connected accounts had collection and metrics surfaces but no unified evidence-bound decision for continuing, adjusting or starting over; platform folklore could outrank content and low reach could be mistaken for a dead account. | Native context/compiler tests cover owner scope, seven content layers, the full commercial funnel, three distinct measured posts, complete commercial-outcome coverage from observations no older than 30 days, server-bound intent/conversion states, non-hostile language, repairable restrictions, latest-within-24-hours/same-reason/seven-day/exhausted-remediation structural evidence and rejection of low-reach-only replacement; all eight platform Skills validate against dated first-party sources. | done |
| AUD-IP-001 | P0 | IP scope | The operating model still treated IP mainly as a creator strategy; products were not first-class subjects and no immutable contract connected influence, differentiation, creative encoding and observed adoption/economic effects. | Migration 0020, repository and native-tool tests prove owner isolation, idempotency, product subjects, candidate/pilot gates, three-supportive-observation downstream validation, strategy/preflight/cockpit/account-diagnosis linkage; strategy v4 separates influence, behavioral and economic goals; the differentiation Skill validates and frontend type/check plus the real-backend product-subject scenario pass. | done |
| AUD-BENCH-001 | P0 | Benchmark judgment | A named benchmark triggered generic deep research; after CAPTCHA/search failure the Agent changed the question into broad restaurant advice and presented secondary snippets as a completed professional analysis. | Empty-owner IP/business distress enters narrative intake without tools; named-benchmark research removes the generic research Skill, uses at most two discovery searches across compaction, rejects clarification cards and image-search drift, stops after two blocked page verifications and replaces any final claim that lacks a verified representative work with one ordinary artifact request. Real UI + Gateway replay of “请看看贵厨笔记这个对标账号” ends with the account-page/three-video request and no restaurant playbook. | done |
| AUD-SRCH-001 | P0 | Search safety | The public fallback could return query-irrelevant adult spam when Ark Web Search was not activated. | Fallback calls DuckDuckGo with strict safe search, accepts public URLs only, removes unsafe and query-irrelevant entries, reports filtered coverage and returns no evidence when the exact live query has no safe relevant result. | done |

## Execution order

1. Restore reproducible engineering gates after relocation.
2. Keep at least one Personal-IP path in the real frontend/backend/SQLite E2E
   suite and expand it whenever a loop stage is implemented.
3. Prove one Douyin gold loop end to end before expanding all eight platforms.
4. Accept full multi-shot and faceless-material video paths.
5. Add compliance, enforced cost limits and whole-product data lifecycle.
6. Expand the real-account matrix to the remaining platforms and desktop
   fallback.

## First-wave acceptance evidence

- `backend`: relocation + web-tool isolation regression group, 73 passed.
- `backend`: local eight-platform publish/recovery acceptance, 58 passed.
- `root`: full suite, 108 passed.
- `frontend`: unit suite, 90 files / 729 tests passed; `pnpm check` passed.
- Mocked Personal-IP Playwright scenarios: 2 passed against the production
  server.
- Real-backend IP portfolio Playwright: 1 passed against real Next.js, real
  Gateway and temporary SQLite at migration head `0020`; the UI created a
  product subject, the API read the persisted row, an account was attached and
  the refreshed UI rendered both.
- IP influence-asset regression: 331 backend Personal-IP/migration tests
  passed; strategy v4, account diagnosis v2 and the differentiation package
  passed Ruff; the internal differentiation capability validated and the
  seven routing/stack constraints passed.
- Relocated runtimes: backend and MineContext rebuilt offline; old source-path
  references are 0 and `make minecontext-doctor` passes.
- First-use/evidence remediation: Personal-IP/HLLM regression 273 passed;
  Skill/catalog regression 101 passed; six affected Skill packages validated;
  frontend 90 files / 729 tests and `pnpm check` passed. Two independent
  forward tests confirmed the cold-start and anti-viral-guarantee behavior.
- Deterministic first-reply acceptance: the in-app Next.js UI ran against a
  real Gateway and isolated empty SQLite at migration head
  `0020_personal_ip_differentiation`. A fresh cold-runtime run completed in
  2.063 seconds with 0 model calls, 0 input/output tokens and exactly one
  `ask_clarification`; the visible response gave the provisional
  value/audience -> positioning hypotheses -> benchmark/pilot -> observed
  calibration route and one person-evidence question. Ten seconds after the
  card appeared, the UI had made no follow-up-suggestion request. The original
  owner portfolio (1 subject, 5 accounts) was never modified.
- Deterministic first-answer continuation acceptance: on a second isolated
  empty-owner thread, the initial evidence question completed in 2.278 seconds
  and its structured answer advanced in 0.817 seconds to the target-group and
  actionable/paid-problem question. Both runs recorded 0 model calls and 0
  tokens; the first question appeared only once. This replaced the observed
  pre-fix continuation path, which had spent 82,255 input tokens across two
  provider calls before asking the same second intake question.
- Adaptive narrative-interview acceptance supersedes the two deterministic
  clarification cards above. One Playwright scenario passed against real
  Next.js, real Gateway and isolated SQLite in 3.5 minutes including the
  production build. The same ordinary conversational opening received three
  materially different user stories and returned three answer-grounded
  reflections and three different follow-up questions. The composer stayed
  enabled, no `human-input-card` rendered and no follow-up-suggestion request
  occurred while the interview marker was active. The first opening used zero
  model calls; later turns sent only the latest bounded visible exchange and
  one private structured interviewer schema, then rendered the result as
  ordinary assistant text. Focused middleware tests also cover all four entity
  openings, correction/skip/private/stop control, sensitive-memory
  non-defaults, direct-task bypass and same-turn transition to the full Agent
  when enough evidence exists.
- Benchmark-judgment acceptance replayed the reported “贵厨笔记” failure through
  the live Next.js UI and Gateway. “普通人打造个人IP难度会不会很大呀？” entered the
  zero-tool narrative opening. The named benchmark made exactly two discovery
  searches, did not search generic restaurant operations, did not render a
  clarification card and ended with a normal account-page/three-video request
  because no representative work was verified. Focused middleware and product
  stack/search regression passed 106 tests and three changed internal method
  packages passed deterministic review. The public fallback regression passed
  15 provider tests; the exact previously polluted query returned zero safe
  results and no adult entry. The complete backend passed 9,046 tests with 71
  explicit external-dependency skips, and the root suite passed 111 tests. A
  final own-account/benchmark scope refinement then passed its 58 focused
  regressions and Ruff.
- Full-backend gate: `make test` passed 8,979 tests with 71 explicit
  live/external-dependency skips in 629.51 seconds. The autouse fixture now
  isolates auth and owner-contract tests from a checkout-local
  `DEER_FLOW_AUTH_DISABLED=1`; real-model client and agent-factory tests require
  dedicated opt-in environment flags, so ordinary regression runs do not spend
  provider credentials merely because local `.env` or `config.yaml` files
  exist.
- Frontend NFT/build gate: the mock artifact route now anchors every dynamic
  lookup under `public/demo/threads`, rejects path and symlink escapes and no
  longer leaks the absolute checkout path in its download header. Four route
  regressions passed; the complete frontend suite passed 89 files / 723 tests;
  `pnpm check` passed. Two consecutive warning-free production builds completed
  in 127.70 and 125.64 seconds, below the 300-second Playwright startup budget.
- Publishing-compliance gate: all eight supported platforms now use the
  immutable `personal-ip-publish-compliance-v1` declaration plus a distinct
  dated policy version and source-linked server receipt. Prepare rejects
  missing rights, moderation or an inexact commercial/AI disclosure plan;
  sensitive topics require documented human review. A published finish
  requires `personal-ip-publish-compliance-evidence-v1` bound to that receipt
  and non-empty disclosure evidence refs. The focused contract/repository
  regression passed 43 tests, the local eight-platform publish/recovery
  acceptance passed 59, the complete Personal-IP backend regression passed
  308, Ruff passed and the seven IP Agent routing/stack constraints passed.
- Video-cost gate: `personal_ip_reserve_video_budget`,
  `personal_ip_settle_video_budget` and
  `personal_ip_release_video_budget` now write server-owned append-only events
  in the existing production ledger. The state fold admits a paid attempt only
  when settled spend plus every active maximum remains within the immutable
  hard limit. SQLite uses `BEGIN IMMEDIATE` and other databases use a row lock,
  so concurrent reservations cannot overbook. Failed attempts remain charged,
  retries require new reservations, unknown billing remains reserved and an
  admitted provider request cannot be released. Meaningful paid approvals must
  come from the authenticated workbench path and match the exact reservation;
  generic agent events cannot forge them. `make personal-ip-cost-acceptance`
  passed 34 tests, the complete Personal-IP backend regression passed 315,
  Ruff/format passed and all seven IP Agent routing/stack constraints passed.
- Whole-data lifecycle gate: every registered `personal_ip_*` table is now
  structurally classified as an exported dataset or a secret/deletion-only
  table. The versioned backup is owner-bound and canonical-digest verified;
  encrypted platform tokens and one-use OAuth state never enter it. Restore is
  empty-scope only, verifies the post-insert digest in the same transaction and
  restores connection shells as revoked so login is mandatory. Permanent
  deletion rechecks a fresh state digest under a write lock, requires the exact
  phrase plus backup acknowledgement, and removes business rows, encrypted
  credentials, OAuth state and MineContext local data. Settings exposes the
  download, file restore and strong-confirmation flow. `make
  personal-ip-data-lifecycle-acceptance` passed 8 backend and 3 frontend tests;
  the complete Personal-IP backend regression passed 320, the complete
  frontend suite passed 90 files / 726 tests, `pnpm check`, Ruff/format,
  persistence bootstrap and Gateway route registration all passed.
- Runtime-observability gate: `docs/RUNTIME_PROFILES.md` now defines
  auto-detected `local-direct`, explicit nginx-backed `local-proxy` and
  production ingress profiles. `make doctor` selected this checkout's direct
  `3000 -> 8001` route and completed Ready with zero errors and warnings;
  absent web organs were explicit skips, while malformed providers and literal
  secrets remain unhealthy. `serve.sh --prod --no-nginx` failed closed before
  service startup. Operating cockpit v6 projects unresolved publication,
  collection, video-provider and budget failures from authoritative receipts
  and active video ledgers into sanitized loop/provider/cost alerts. Hard-limit
  rejection now seals `personal-ip-video-budget-rejection-v1` before returning
  the error, without request refs or raw provider payloads. `make
  personal-ip-observability-acceptance` passed 88 backend tests, 4 frontend
  tests and `pnpm check`; `make personal-ip-cost-acceptance` passed 34 tests;
  Ruff and shell syntax checks passed.
