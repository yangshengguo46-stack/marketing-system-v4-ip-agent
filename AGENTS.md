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

| Service         | Port   | Role                                                                 |
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
- `product/defaults/` owns the product agent/owner defaults, while
  `product/volcengine/capabilities.yaml` is the auditable media routing policy.
- `scripts/init_ip_agent.py` installs those defaults into a normal DeerFlow
  workspace. Keep this as a source distribution: integrate upstream DeerFlow
  changes without replacing native source modules with binary wrappers.
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
  default-off, explicitly authorized, owner-isolated loopback sidecar. Never
  auto-start capture or place raw screenshots, full screen/file text, paths,
  vectors or credentials in model evidence. Preserve source/observation time,
  partial coverage, retention, stop/revoke/delete controls and the
  `personal-ip-local-context-evidence-v1` boundary. `make minecontext-install`
  must install from the vendored source; do not add an opaque prebuilt
  MineContext executable.
- `scripts/install_ffmpeg_toolchain.py` owns the pinned project-local FFmpeg
  build. Service launch and MediaKit diagnosis must prefer its `bin` directory;
  do not silently fall back to a feature-incomplete system FFmpeg.
- Personal-IP account data is the product-owned domain boundary. It must remain
  owner-scoped, enter runs through validated server context, and never be trusted
  from a caller-supplied expanded object.
- Personal-IP preflights are immutable model request/receipt snapshots under
  `deerflow.persistence.personal_ip_preflights` and migration
  `0008_personal_ip_preflights`. Account ids are operation targets in the
  snapshot, never thread authority. Do not add a prediction rewrite endpoint.
- Personal-IP publishing receipts live in
  `deerflow.persistence.personal_ip_publish_receipts` and migration
  `0009_personal_ip_publish_receipts`. Keep the initial request immutable,
  attempts append-only and terminal publication status monotonic. API,
  UI-TARS, browser and manual executors share this one receipt contract.
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
  exist and open manual login through the account-scoped Live Browser route.
  The user—not the agent—completes QR, CAPTCHA and MFA. Each account uses an
  owner/account-isolated persistent profile. Successful login emits a boolean
  event and closes the login dialog. This credential boundary must not suppress
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
- Personal-IP video production lives in
  `deerflow.persistence.personal_ip_video_productions` and migration
  `0015_personal_ip_video_productions`. Keep the initial idea/script, delivery
  spec, provider policy and budget immutable; record blueprint, assets,
  storyboard, per-shot generation/failure/retry, consistency, selection,
  finishing and delivery as idempotent append-only events. Providers and model
  versions are receipt fields, not orchestration state. A production completes
  only through a successful `delivery_completed` event, and that event requires
  a preceding successful `personal-ip-delivery-qa-v1` receipt for the exact
  output refs. `scripts/personal_ip_video_e2e.py` is the credential-free local
  acceptance/resume path; it must keep paid providers simulated unless the
  active user session explicitly approves the generated paid checkpoints.
  `deerflow.personal_ip.video_workbench` and Gateway
  `GET /api/personal-ip/video-productions/{production_id}/workbench` are a pure,
  owner-scoped read model over that same production and event stream. Keep the
  frontend workbench read-oriented: it may record only meaningful confirmation
  events through the existing event endpoint, and must never create a parallel
  video runtime, mutable projection table or chat-derived recovery state.
- `deerflow.personal_ip.operating_cockpit` is the owner-scoped read model that
  joins the six-stage operating loop and nine-stage video line. The Gateway
  route and native `personal_ip_operating_cockpit` tool must use the same
  service, stay whole-portfolio, expose explicit pending queues and report
  bounded-history coverage. The native begin/event/read video tools are the
  agent's write/resume surface; chat history is never the production ledger.

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
