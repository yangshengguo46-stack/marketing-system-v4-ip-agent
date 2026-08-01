# Backend guide

## Layout

- `packages/harness/deerflow/` is the reusable agent framework: agents,
  middleware, tools, sandbox, memory and persistence.
- `app/gateway/` is the FastAPI application, dependency injection and routes.
- `app/channels/` contains IM adapters.
- `tests/` contains backend regression and acceptance coverage.

The harness must not import `app.*`. App-owned repositories and services are
installed through explicit runtime injection.

## Commands

Run from `backend/`:

```bash
uv sync
uv run python -m pytest tests/ -q
uvx ruff check .
uvx ruff format --check .
make gateway
make migrate-rev MSG="describe change"
```

Root Make targets own the full stack and product acceptances.

## Runtime and persistence

The Gateway exposes REST routes and a LangGraph-compatible run surface. Keep
authentication and Owner authority server-derived. Caller-supplied account or
resource ids are operation targets only and require Owner validation.

Persistence models are registered through
`deerflow.persistence.models.Base`. Schema changes require an Alembic revision.
Test both a database upgraded from the prior head and a fresh bootstrap; fresh
`Base.metadata.create_all()` must not resurrect retired tables.

Agent tools are assembled from configured, built-in, MCP, ACP, sub-Agent,
Skill-management and self-modification sources. Operator `tool_allowlist`, when
set, is the final filter over the assembled set. `memory_enabled: false` must
remove both memory prompt injection and memory middleware/update behavior.

System-prompt capability sections must reflect the actual toolset: no Skill,
file-writing, self-modification, memory or sub-Agent instructions when the
corresponding capability is unavailable.

## IP Agent

Follow `../IP_AGENT.md`. The clean IP Agent has an empty Skill list, disabled
memory and an exact eight-tool read-only allowlist. Because it has no
Personal-IP tools, do not attach the Personal-IP context middleware or make
startup ledger reads.

The retired semantic layer includes strategy, differentiation, asset
observation, preflight/HLLM-Lite prediction, retrospective, evidence promotion,
startup/operating cockpit and narrative interview. Do not register its models,
repositories, routes, dependencies or tools. Old endpoints must remain 404.

Retained Personal-IP domains are:

- subjects and accounts;
- encrypted platform connections and OAuth state;
- publish receipts and attempts;
- metrics and credential-free platform observations;
- video productions and append-only events;
- whole-domain backup/restore/delete.

Publishing continues to enforce rights, moderation, commercial/AI disclosure
and post-specific proof. Video continues to enforce rights, immutable plans and
receipts, paid-call reservations, exact paths/hashes/candidate identity, QA and
idempotency. Data lifecycle must classify every live `personal_ip_*` table and
must never export credentials.

`0021_personal_ip_semantic_layer_retirement` must refuse a non-empty retired
table and require a verified Owner backup. Never weaken this guard in tests or
production. Its downgrade recreates empty compatibility schemas only.

Research adapters under `../product/research/ip-agent/` are non-runtime. No
module under `deerflow`, Gateway route or production tool may import them.

## Engineering conventions

- Keep async handlers non-blocking; offload blocking filesystem, subprocess and
  media work.
- Use typed request/response contracts and sanitize external errors.
- Never log tokens, cookies, passwords, raw OAuth state, raw screenshots or
  unbounded provider payloads.
- Preserve append-only and monotonic receipt semantics.
- Prefer focused tests while editing, then run the complete backend suite and
  the relevant root acceptance targets.
