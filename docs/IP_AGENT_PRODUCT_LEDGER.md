# IP Agent product ledger

This is the delivery source of truth for customer-reachable IP Agent behavior.
Schemas, research packages and mocked tests are not counted as active product
capability. `IP_AGENT.md` defines the current runtime contract; the audit ledger
contains executable gates.

Last reviewed: 2026-08-01.

## Current product state

The product is in a deliberate clean-baseline period. The former composite
completion percentage is withdrawn because the retired semantic workflow and
the future first-principles workflow are different products; carrying the old
score forward would be false precision.

| Area | Current status | Product truth | Open gate |
| --- | --- | --- | --- |
| Default IP Agent | Active | One compact prompt, no Skills, no memory, exact eight-tool read-only allowlist | Keep the fixed replay matrix as the regression baseline |
| First use | Active | Current request goes directly to the model; no cockpit scan, fixed interview or server-written opening | Keep simple first reply to one model call and zero tool calls |
| Subjects and accounts | Active | Owner-scoped facts and eight-platform connection surfaces remain | Real-account acceptance for all eight platforms remains external |
| Publishing | Active | Immutable request/attempt receipts, rights/disclosure checks and post-specific proof remain; no preflight dependency | Local recovery suite plus real per-platform publication acceptance |
| Metrics and observations | Active | Stores credential-free observations with source, coverage and observed time | Extend verified collection beyond accepted platforms |
| Workspace dashboard | Active | Facts only; missing stays `未采集` | Frontend checks and real-backend factual rendering |
| Video production | Active | Task-bound append-only ledger, paid-call, rights, hash, candidate, QA and idempotency controls remain | Local E2E plus real material and paid multi-shot external acceptance |
| Data lifecycle | Active | Owner backup, same-owner empty restore and confirmed deletion; credentials excluded | Lifecycle acceptance against migration head 0021 |
| Legacy semantic layer | Retired | Strategy, differentiation, asset observation, preflight, retrospective, evidence promotion, startup/cockpit and narrative interview are removed from runtime | Completed: old APIs 404, fresh DB stays clean and guarded upgrade refuses non-empty retirement data |
| Method library | Quarantined | Cinematic modules, platform methods, Cangjie/HLLM/video research remain inspectable but are not default Agent capability | Review under a future architecture before any promotion |
| New IP first-principles architecture | Not started | No current workflow is claimed | Define IP forms, evidence contracts and orchestration only after clean baseline acceptance |

## Active product principles

- IP may be carried by a person, brand, product or organization.
- User facts, source facts and creative hypotheses remain visibly distinct.
- The default Agent answers the current request before proposing a process.
- Public research is targeted and cited next to the supported conclusion.
- Research assets are not product features until explicitly promoted and
  verified through a reachable runtime path.
- Business and creative judgments belong to a future coherent architecture,
  not scattered server gates.
- Security and execution correctness are not “business semantics”: Owner
  isolation, credentials, OAuth, rights, disclosures, paid calls, deletion,
  paths, hashes, immutable receipts and idempotency remain enforced.

## Retired product claims

The following are no longer shipped or counted:

- automatic account continue/adjust/restart verdicts;
- strategy/differentiation versions as operating certificates;
- HLLM-Lite preflight and blind-prediction workflow;
- retrospective and evidence-promotion loops;
- cockpit stages, Agent queues, boost/high-potential judgments;
- fixed first-use narrative interviewing;
- automatic video-method or Skill-candidate promotion.

Git history preserves their implementation. Do not copy it into a hidden
“backup” package.

## Acceptance evidence

Phase one is committed as `1c87fd8a` (`refactor(ip-agent): isolate clean runtime
baseline`). Its clean runtime reduced serialized prompt/tool input by more than
50% and passed the fixed Doubao behavior cases before physical deletion.

Phase two passed the complete local gate in
`IP_AGENT_AUDIT_REMEDIATION_LEDGER.md`: full backend, frontend and root tests;
migration and retired-API checks; lifecycle, publishing, platform-observation,
cost and local-video acceptances; real-backend Playwright; and the same real
Doubao replay matrix. The physical semantic retirement is complete. Public-web
current-fact coverage still depends on an activated citation-bearing provider;
the tested unavailable path failed honestly without fabricated sources.
