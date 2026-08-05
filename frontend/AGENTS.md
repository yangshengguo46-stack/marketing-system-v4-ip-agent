# Frontend guide

## Overview

The frontend is a Next.js App Router application under `src/app`. Shared UI
lives in `src/components`; API clients, query hooks and domain types live in
`src/core`.

## Commands

Run from `frontend/`:

```bash
pnpm install
pnpm dev
pnpm check
pnpm test
pnpm build
```

Use focused `pnpm exec rstest ...` while editing and complete checks before
handoff.

## Data and interaction ownership

Server APIs and persisted thread state are authoritative. TanStack Query hooks
own fetch/cache invalidation. Components may hold transient interaction drafts
but must not create a parallel durable workflow store.

`新对话` creates a task; `历史对话` opens the complete task index. Keep `工作台`
immediately above `新对话` in the workspace sidebar.

Personal-IP customer surfaces retain:

- `/workspace/content` for the shared Breakdown, Writer Brain and Production
  content lineage;
- `/workspace/personal-ip` for subjects, accounts and platform login;
- `/workspace/dashboard` for factual Owner-wide observations;
- Settings for MineContext consent and data lifecycle.

The content workspace remains exactly those three boards; do not add a strategy,
semantic-core or operations board. Writer Brain presents the one
total-editor/operations decision: current outcome priority, time horizon,
audience hypothesis and uncertainty, attribution carrier, hypothesized
differentiation and chosen content route. It may show an optional recurring human theme only when the bound Editorial
Program contains one. The semantic-causal core is an internal bounded helper
for `semantic_story`/`hybrid`, not a peer Agent or customer workflow.

Frontend lineage types and projections must preserve this order:

```text
EditorialProgramVersion -> ContentWork -> DirectionVersion -> ScriptVersion -> VideoProduction
```

They must remain readable for historical v1 Directions that have no Program
binding. Do not render internal Owner ids, operation keys, run ids or
decision/route digests. Outcome, time horizon, carrier and route are independent
values; do not infer one from another. Differentiation always renders as a
hypothesis, never as validated positioning or market proof.

The task-bound video workbench is a retained implementation projection over the
immutable production ledger. It is customer-reachable only when the product
runtime profile explicitly enables it; the default profile currently keeps that
entry off.

The dashboard must read existing subject, account, metrics, platform
observation, publish-receipt and video-production APIs directly. Show source
status and observation time. Missing values render `未采集`, never zero. Do not
restore cockpit stages, Agent to-do queues, high-potential/boost labels,
paid-traffic judgments or continue/adjust/restart verdicts.

The default IP Agent exposes no Skills or retired portfolio orchestration. Its
bounded content tools operate the shared lineage without exposing their names
or internal steps. Customer UI must not show Skill names, paths, internal tool
routing or research assets as shipped capability.

Platform login is user-completed in an Owner/account-isolated browser session;
never render raw credentials, profile paths, cookies or tokens. Publish and
video UI must preserve server validation and append-only receipt semantics.

The video workbench is task-bound. Setup and storyboard hide the timeline;
editing mounts one timeline; delivery is a full-width final viewer. Client
pointer movement remains a draft until an explicit save compiles a server
revision. Do not create a second video runtime or mutable projection database.

## Code style

- Use the `@/*` path alias and inline type imports.
- Follow the configured import ordering and ESLint rules.
- Prefix intentionally unused variables with `_`.
- Use `cn()` for conditional classes.
- Do not manually edit generated registry components in `ui/` or
  `ai-elements/` unless their generation workflow explicitly permits it.
- Keep accessible names and keyboard/focus behavior for interactive controls.

The current IP Agent product contract is `../IP_AGENT.md`;
`../docs/IP_AGENT_PRODUCT_LEDGER.md` is the only current product-status record.
The audit closeout and capability inventory under `../docs/` are supporting
history/inventory, not competing delivery ledgers.
