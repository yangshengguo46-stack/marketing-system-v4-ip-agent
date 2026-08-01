# IP Agent product contract

This file is the sole contract for the currently active IP Agent baseline. It
describes shipped runtime behavior, not research ambitions.

## Product boundary

IP may be carried by a person, brand, product or organization. The clean
baseline answers the user's current request and keeps three kinds of claims
separate: user-provided facts, source-backed facts and clearly labelled
creative hypotheses.

The default Agent does not run a fixed onboarding interview, inspect operating
ledgers on the first turn, diagnose accounts, predict virality or manufacture
an incubation workflow. A new first-principles IP architecture and its overall
orchestration have not started.

## Active Agent runtime

The installed `ip-agent` uses:

- `skills: []`;
- `memory_enabled: false`;
- the exact read-only tool allowlist `web_search`, `image_search`, `ls`,
  `read_file`, `glob`, `grep`, `view_image`, `ask_clarification`;
- the compact product prompt in
  `product/defaults/agents/ip-agent/SOUL.md`.

An empty Skill list removes Skill discovery/evolution instructions. Disabled
memory removes memory loading and updates. The allowlist is applied after all
configured, built-in, MCP, ACP, sub-Agent and self-modification tools are
assembled, so an excluded tool cannot leak in through another source.

The Personal-IP context middleware is not mounted for this clean Agent. Simple
conversation therefore goes directly to one model call and makes no tool call.
Search is used only when the answer depends on current or externally verified
facts. Search citations are ordinary Markdown links placed next to the claim.

## Retained execution products

The following owner-scoped product surfaces remain available through their
dedicated UI and explicit APIs, but are not tools of the default Agent:

- subjects, accounts, platform connections and OAuth;
- publish requests and append-only attempts;
- metrics and credential-free platform observations;
- video productions and their append-only event ledger;
- the factual workspace dashboard.

The dashboard displays observations and their timestamps. Missing data stays
`未采集`; it does not infer high potential, paid-traffic suitability, or a
continue/adjust/restart verdict.

## Stable safety boundaries

Credential ciphertext, passwords, cookies and one-use OAuth state never enter
model context or Owner backups. Publishing still validates rights, moderation,
commercial/AI disclosure and public-post proof. Video execution still enforces
rights, paid-call approval and reservation, immutable receipts, paths, hashes,
candidate consistency, QA and idempotency. Owner data export, same-owner
empty-scope restore and confirmed deletion remain enforced.

These are execution and safety invariants, not creative or business judgments.

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

Current delivery state and executable audit gates live in the two existing
ledgers: `docs/IP_AGENT_PRODUCT_LEDGER.md` and
`docs/IP_AGENT_AUDIT_REMEDIATION_LEDGER.md`.

The exhaustive, code-checked catalog of active, isolated and conditional tools
plus all 97 quarantined public Skills lives in
`docs/IP_AGENT_SKILL_CAPABILITY_BOUNDARY_LEDGER.md`.
