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
| AUD-QA-001 | P0 | Regression | The full backend suite had environment-sensitive failures and the root suite had one package-fixture failure. | Root suite, backend suite, frontend unit suite and `pnpm check` are green from the moved checkout. | verifying |
| AUD-QA-002 | P1 | Build performance | Next production build is unusually slow and reports whole-project NFT tracing from a dynamic artifact route. | Scope the traced filesystem path, remove the warning and record a repeatable build time below the Playwright startup budget. | ready |
| AUD-LOOP-001 | P0 | Strategy | No local strategy version or launch-ready natural incubation has been persisted. | Complete one natural subject conversation through real benchmark evidence, alternatives, launch package, pilot and validation. | external gate |
| AUD-LOOP-002 | P0 | Closed loop | Local preflight, publish, metric, retrospective and promotion tables are empty. | Seal three distinct publications from blind prediction through measured retrospective and one policy-approved evidence promotion. | external gate |
| AUD-DIST-001 | P1 | Platforms | Evidence is concentrated in Douyin/WeChat/Xiaohongshu; X, Instagram, YouTube and TikTok have no accepted evidence. | Run the account/login/collection/publish/recovery matrix per platform with explicit coverage states. | external gate |
| AUD-VID-001 | P1 | Video | Local video E2E simulates paid providers; paid calls executed by that gate are zero. | Accept one full multi-shot generative production and one real faceless-material production with immutable provider/cost/QA receipts. | external gate |
| AUD-COMP-001 | P1 | Publishing compliance | Publish requests remain generic JSON and do not yet enforce platform-specific disclosure, commercial-partnership or moderation fields. | Add versioned per-platform compliance schemas, validation and receipt evidence before prepare/finish. | ready |
| AUD-COST-001 | P1 | Cost control | Video budgets are recorded but not enforced as admission limits. | Reserve, accumulate and reject over-budget paid operations before provider submission; test retries and concurrent reservations. | ready |
| AUD-DATA-001 | P1 | Data lifecycle | MineContext deletion exists, but whole Personal-IP export/backup/restore/delete is absent. | Owner-scoped export, verified restore and destructive-delete flow cover every Personal-IP repository without leaking credentials. | ready |
| AUD-OBS-001 | P2 | Operations | Product observability is mostly optional and the local doctor reports missing nginx and unconfigured web tools. | Define the supported local/prod profile, make required health checks green and surface loop/provider/cost failures in the operating console. | ready |
| AUD-OS-001 | P2 | Desktop fallback | UI-TARS source and permission checks exist, but the runtime/model are disabled and no live desktop acceptance was executed. | Explicitly enable, approve and run one sanitized macOS fallback receipt without exposing raw screenshots or credentials. | external gate |

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
- `root`: full suite, 104 passed.
- `frontend`: unit suite, 88 files / 719 tests passed; `pnpm check` passed.
- Mocked Personal-IP Playwright scenarios: 2 passed against the production
  server.
- Real-backend Personal-IP Playwright: 1 passed against real Next.js, real
  Gateway and temporary SQLite at migration head `0019`.
- Relocated runtimes: backend and MineContext rebuilt offline; old source-path
  references are 0 and `make minecontext-doctor` passes.
