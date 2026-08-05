# AGENTS.md

This is the monorepo orientation guide for coding agents. Read
`backend/AGENTS.md` or `frontend/AGENTS.md` before changing that module.

## Repository

DeerFlow is a LangGraph-based full-stack agent system.

| Service | Port | Purpose |
| --- | ---: | --- |
| Nginx | 2026 | Unified optional proxy |
| Gateway | 8001 | FastAPI and embedded agent runtime |
| Frontend | 3000 | Next.js workspace |
| Provisioner | 8002 | Optional sandbox provisioner |

Main paths:

- `backend/packages/harness/`: agent framework and persistence;
- `backend/app/`: Gateway and integrations;
- `frontend/`: customer application;
- `product/defaults/`: product-owned Agent defaults;
- `product/research/`: non-runtime research quarantine;
- `skills/public/`: Skill source catalog;
- `third_party/`: pinned upstream source;
- `docs/`: product ledgers and cross-cutting documentation.

Runtime configuration lives at repo root in ignored `config.yaml` and
`extensions_config.json`. Python commands use `uv run python -m ...`; do not
depend on generated console-script shebangs from another checkout.

## IP Agent boundary

`IP_AGENT.md` is the only current product contract. The default IP Agent has no
Skills or memory and exposes eight read-only baseline tools, the two
MediaKit-backed Evidence MCP tools and four bounded `ip_content_*` tools. A
configured `MEDIAKIT_API_KEY` authorizes
those evidence tools to run ASR/OCR/scene/storyline analysis directly; do not
restore the retired per-call approval gate. It does not mount retired
Personal-IP portfolio context orchestration. Do not reintroduce strategy,
differentiation, preflight, retrospective, evidence-promotion, startup-cockpit
or narrative-interview semantics outside a new approved architecture.

Dedicated Owner surfaces retain subject/account facts, credential-isolated
platform connections, publishing receipts, metrics/observations and video
production. The workspace dashboard is factual only; missing observations stay
missing. Account ids select operation targets and never define conversation
authority.

Stable execution boundaries remain mandatory: Owner isolation, credential
secrecy, OAuth state, rights and disclosure, deletion,
path/hash/candidate consistency, immutable receipts and idempotency. Never
weaken one of these as “semantic cleanup.”

Research in `product/research/`, the cinematic Skill catalog and
`third_party/` is not active product capability. Production Python packages,
routes and tools must not import the research quarantine.

Migration `0021_personal_ip_semantic_layer_retirement` fails closed if a table
scheduled for retirement is non-empty. Require a verified Owner backup rather
than bypassing that guard. Downgrade restores empty schemas only.

Current product status has one authority:

- `docs/IP_AGENT_PRODUCT_LEDGER.md` — the only current delivery truth, organized
  around breakdown, writer brain and production;
- `docs/IP_AGENT_AUDIT_REMEDIATION_LEDGER.md` — frozen historical audit closeout,
  not a current delivery record;
- `docs/IP_AGENT_SKILL_CAPABILITY_BOUNDARY_LEDGER.md` — generated capability
  inventory, not a completion ledger.

## Commands

```bash
make setup
make doctor
make dev-direct
make ip-refresh
make ip-test-reset
make ip-test-start
make ip-test-status
make ip-test-stop
make personal-ip-data-lifecycle-acceptance
make personal-ip-publish-acceptance
make personal-ip-observability-acceptance
make personal-ip-cost-acceptance
make video-e2e-local
```

Use module commands from the corresponding guide. Keep user changes in a dirty
worktree intact. Update the product ledger only for an actually reachable and
verified path; schemas and mocked tests alone are not completion evidence.

## Cross-cutting conventions

- Preserve the harness/app import boundary; inject app-owned implementations
  rather than importing the Gateway from the harness.
- Keep async request paths non-blocking and offload filesystem/media work.
- Keep secrets and raw provider payloads out of logs, model context and normal
  exports.
- Add migrations for persistent schema changes and verify both fresh bootstrap
  and upgrade paths.
- Treat customer-visible Skill names, paths and internal tool steps as private
  implementation details.
