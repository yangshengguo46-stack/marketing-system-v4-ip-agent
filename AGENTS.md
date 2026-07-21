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
- Personal-IP performance observations live in
  `deerflow.persistence.personal_ip_metrics` and migration
  `0010_personal_ip_metrics`. The `/api/personal-ip/metrics/aggregate` route is
  portfolio-wide by design: never add a thread-bound account restriction.
  Aggregate only additive `window_total`/`delta` fields, take the latest
  observation for an identical account/scope/series/window, exclude cumulative snapshots,
  and expose missing/partial/unavailable account coverage explicitly.
- Personal-IP retrospective evidence lives in
  `deerflow.persistence.personal_ip_retrospectives` and migration
  `0011_personal_ip_retrospectives`. A retrospective must join one published
  receipt to its original preflight and same-receipt post observations, freeze
  the selected variant plus outcomes under an evidence digest, and remain
  `pending_human_review`. Do not auto-promote a retrospective into training or
  invent a score when HLLM-Lite returned none.
- Personal-IP evidence promotion lives in
  `deerflow.persistence.personal_ip_evidence_promotions` and migration
  `0012_personal_ip_evidence_promotions`. A proposal needs at least three
  complete retrospectives from distinct publish receipts; different horizons
  of one post count once and partial observations do not satisfy the threshold.
  Approval/rejection is terminal, requires explicit authenticated-user
  confirmation and rationale, and is the only path to the approved-evidence
  export contract. Preserve source status/comparison provenance in exports.
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
  performance inventory, aggregation and encrypted Douyin post sync. Gateway installs the repository
  bundle through `deerflow.personal_ip.runtime`; this app-to-harness injection
  preserves the harness import firewall. The aggregate tool intentionally has
  no account filter. Keep `product/defaults/agents/ip-agent/SOUL.md` and
  `skills/public/personal-ip-operator/SKILL.md` aligned: conversations cover the
  full portfolio, while account ids are only concrete operation targets.
- Official Douyin post counters remain immutable cumulative snapshots. From the
  second observation onward, `PersonalIPMetricCollectionService` may derive an
  exact-interval delta from the immediately preceding monotonic snapshot in the
  same post series. Derived deltas are always `partial` with
  `scope_limit=tracked_post_only`; never relabel them complete account totals or
  infer data before the baseline timestamp.

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

## Commands: Root vs. Module

**Root `make` targets drive the whole stack** (run from the repo root):

```bash
make setup       # Interactive setup wizard (recommended for new users)
make doctor      # Check configuration and system requirements
make support-bundle  # Generate redacted troubleshooting summary, AI issue draft, and optional zip
make config      # Generate local config files from the examples
make check       # Check that required tools are installed
make install     # Install all dependencies (frontend + backend + pre-commit hooks)
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
