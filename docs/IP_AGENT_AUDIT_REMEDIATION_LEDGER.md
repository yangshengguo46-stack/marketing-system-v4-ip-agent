# IP Agent audit remediation closeout

Status: frozen historical closeout as of 2026-08-01.

This file records the completed clean-baseline and semantic-retirement audit.
It is not a current product-status source and must not receive new feature,
MediaKit, writer-brain or production progress. Current reachability and the
only active delivery sequence live in `docs/IP_AGENT_PRODUCT_LEDGER.md`.
Historical implementation detail remains available in Git.

The historical rows below used this vocabulary. `done` means that the named
remediation action and its acceptance completed at closeout; it never means a
replacement product capability was delivered:

- `done`: implementation and named acceptance completed;
- `verifying`: implementation exists but the full gate is still running;
- `pending`: intentionally not implemented;
- `external gate`: requires credentials, paid calls, OS permission or human
  approval.

## Two-phase purification

| ID | Finding | Required result | Status |
| --- | --- | --- | --- |
| CLEAN-01 | Tool, Skill, memory and self-modification sources polluted the default Agent | Final exact read-only allowlist after all tool assembly; empty Skills; memory disabled | done — commit `1c87fd8a` |
| CLEAN-02 | The 359-line soul and generic system prompt described unavailable behavior | Soul under 40 lines; capability-sensitive prompt sections; nearby search links | done — commit `1c87fd8a` |
| CLEAN-03 | First-use middleware scanned ledgers and imposed a scripted interview | Clean IP Agent bypasses Personal-IP context middleware and goes directly to the model | done — commit `1c87fd8a` |
| CLEAN-04 | Phase-one baseline needed real-provider proof | Four fixed Doubao cases; simple dialogue one model call/zero tools; input size reduced at least 50% | done — commit `1c87fd8a` |
| RETIRE-01 | Strategy, differentiation and asset-observation semantics remained live | Repositories, models, tools, DI and customer surfaces removed | done |
| RETIRE-02 | Preflight, HLLM-Lite prediction, retrospective and promotion formed a conflicting judgment loop | Runtime code/routes/tools removed; publishing no longer carries `preflight_id` | done |
| RETIRE-03 | Startup/cockpit and narrative interview still created hidden orchestration | Fixed opening, forced schema, session marker and operating tools removed | done |
| RETIRE-04 | Method distillation and Skill promotion were mixed into production runtime | Python adapters moved to research quarantine; production imports are zero | done |
| RETIRE-05 | Old tables could return through bootstrap or unsafe migration | 0021 refuses non-empty tables, drops empty legacy tables and `preflight_id`; fresh DB remains clean; downgrade restores empty schema only | done |
| RETIRE-06 | Cockpit UI still published unsupported business judgments | Dashboard reads fact APIs directly and removes potential/boost/continue-adjust-restart conclusions | done |
| RETIRE-07 | Accumulated documentation described retired code as current | `IP_AGENT.md` is sole contract; root/module guides compressed; product state and historical closeout were separated | done |
| RETIRE-08 | Physical cleanup might change clean-Agent behavior | Run the same four real Doubao replays and compare answers, tool calls and input scale with phase one | done |
| NEXT-01 | There was no coherent replacement IP architecture after retirement | Record a first-principles target only after the clean baseline is accepted | done — the target boundary was documented; no runtime replacement was claimed, and current implementation status is owned only by the product ledger |

## Historical phase-two acceptance gate

All of the following must pass before `RETIRE-*` becomes `done`:

1. Backend full test suite and Ruff.
2. Frontend lint/typecheck, unit tests and factual-dashboard coverage.
3. Root Skill/package architecture tests.
4. Migration upgrade from 0020, fresh bootstrap, non-empty fail-closed check and
   empty-schema downgrade.
5. Retired API paths return 404 and retired tables are absent at head.
6. `make personal-ip-data-lifecycle-acceptance`.
7. `make personal-ip-publish-acceptance`.
8. `make personal-ip-observability-acceptance`.
9. `make personal-ip-cost-acceptance`.
10. `make video-e2e-local`.
11. Identical real Doubao replay matrix with no unexpected answer, tool-call or
    input-size drift from phase one.
12. Refresh product defaults, factory-reset the isolated test profile and leave
    it ready for the next manual E2E.

Completed evidence on 2026-08-01:

- backend: `8940 passed, 71 skipped`; Ruff passed;
- frontend: 90 unit-test files and 730 tests passed; `pnpm check` passed;
- root architecture/package tests: 111 passed; focused package/Skill tests: 12 passed;
- migration 0021 upgrade, fresh bootstrap, non-empty refusal and empty-schema
  downgrade passed; retired APIs return 404 and retired tables are absent at
  head;
- data lifecycle, publishing, observability and cost acceptances passed with
  8/3, 56, 94/3 and 29 tests respectively;
- local video E2E completed with 11 ledger events, successful QA, zero paid
  calls and output SHA-256
  `f0e6604ace19f32eca3c810ff92320ce0a957dc86b348b000983b8cfec019544`;
- real-backend Playwright portfolio acceptance passed;
- real Doubao replay preserved the clean baseline: the simple IP question and
  the Chinese-grammar question each used one model call and zero tools; the
  account-name-only case used one `web_search`, then requested the platform or
  home-page link through `ask_clarification`, without inventing an account or
  video analysis. First-call inputs remained about 3.2k tokens, consistent
  with phase one and more than 50% below the pre-cleanup baseline.

The current-fact replay encountered an external coverage limit: Ark Web Search
was not activated for the configured account and the DuckDuckGo fallback
returned no results. The Agent disclosed that it could not verify the fact and
did not fabricate a citation. Activating a citation-bearing search provider is
an external configuration gate, not a reason to restore semantic middleware or
add a new server-side quality gate.

## External gates recorded at closeout

- Real login, collection and publication acceptance for all eight platforms.
- Real UI-TARS and MineContext OS-permission acceptance.
- Real paid multi-shot and real faceless-material video delivery.

These were the remaining external gates on the closeout date. Their current
state must be read from the product ledger, not inferred from this history.
