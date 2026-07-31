# AGENTS.md

This file provides guidance to AI coding agents (Claude Code, Codex, and others) when working with the DeerFlow frontend. It is the source of truth; the sibling `CLAUDE.md` imports it via `@AGENTS.md`.

## Project Overview

DeerFlow Frontend is a Next.js 16 web interface for an AI agent system. It communicates with a LangGraph-based backend to provide thread-based AI conversations with streaming responses, artifacts, and a skills/tools system.

**Stack**: Next.js 16, React 19, TypeScript 5.8, Tailwind CSS 4, pnpm 10.26.2. Requires Node.js 22+ and pnpm 10.26.2+.

### Core dependencies

- **LangGraph SDK** (`@langchain/langgraph-sdk` ^1.5.3) — Agent orchestration and streaming
- **LangChain Core** (`@langchain/core` ^1.1.15) — Fundamental AI building blocks
- **TanStack Query** (`@tanstack/react-query` ^5.90.17) — Server state management
- **UI**: Shadcn UI, MagicUI, React Bits, and Vercel AI SDK elements (generated from registries — see Code Style)

## Commands

| Command          | Purpose                                           |
| ---------------- | ------------------------------------------------- |
| `pnpm dev`       | Dev server with Turbopack (http://localhost:3000) |
| `pnpm build`     | Production build                                  |
| `pnpm check`     | Lint + type check (run before committing)         |
| `pnpm lint`      | ESLint only                                       |
| `pnpm lint:fix`  | ESLint with auto-fix                              |
| `pnpm format`    | Prettier check (`pnpm format:write` to apply)     |
| `pnpm test`      | Run unit tests with Rstest                        |
| `pnpm test:e2e`  | Run E2E tests with Playwright (Chromium)          |
| `pnpm typecheck` | TypeScript type check (`tsc --noEmit`)            |
| `pnpm start`     | Start production server                           |

Unit tests live under `tests/unit/` and mirror the `src/` layout (e.g., `tests/unit/core/api/stream-mode.test.ts` tests `src/core/api/stream-mode.ts`). Powered by Rstest; import source modules via the `@/` path alias.

`pnpm-workspace.yaml` preserves the audited ignored-build policy across pnpm 10
and 11. pnpm 11 defaults `strictDepBuilds` to a hard failure, so the workspace
sets it false and explicitly denies the existing `esbuild`, `sharp`, and
`unrs-resolver` build scripts through both the v10 and v11 policy fields. The
source clean-install gate further lowers registry concurrency and applies one
bounded network retry; ordinary frontend commands keep their normal defaults.

E2E tests under `tests/e2e/` use Playwright with Chromium and mock backend APIs
through `page.route()`; their production build startup budget is 300 seconds.
Cross-stack contracts live under `tests/e2e-real-backend/` and run a real
Next.js server against a real Gateway with temporary migrated SQLite and a
deterministic replay model:
`pnpm exec playwright test -c playwright.real-backend.config.ts`. The
real-backend config must explicitly clear `NEXT_PUBLIC_BACKEND_BASE_URL` and
`NEXT_PUBLIC_LANGGRAPH_BASE_URL` so developer `.env` files cannot bypass its
same-origin temporary Gateway.

## Architecture

```
Frontend (Next.js) ──▶ LangGraph SDK ──▶ LangGraph Backend (lead_agent)
                                              ├── Sub-Agents
                                              └── Tools & Skills
```

The frontend is a stateful chat application. Users create **threads** (conversations), send messages, set thread-scoped `/goal` completion conditions, and receive streamed AI responses. The backend orchestrates agents that can produce **artifacts** (files/code), **todos**, and goal state updates.

### Source Layout (`src/`)

- **`app/`** — Next.js App Router. Routes include `/` (landing), `/workspace/chats/[thread_id]` (chat), `/workspace/agents/[agent_name]` and `/workspace/agents/new` (custom agents), `/blog/…`, the `(auth)/{login,setup,auth/callback}` flow, `/[lang]/docs/…`, and `/api/…` route handlers (e.g. `/api/memory`).
- **`components/`** — React components:
  - `ui/` — Shadcn UI primitives (auto-generated, ESLint-ignored)
  - `ai-elements/` — Vercel AI SDK elements (auto-generated, ESLint-ignored)
  - `workspace/` — Chat page components (messages, artifacts, settings)
  - `landing/` — Landing page sections
  - `docs/` — Docs / MDX rendering components
- **`core/`** — Business logic, the heart of the app. Domains include `threads/` (creation, streaming, state), `api/` (LangGraph client singleton), `agents/` (custom agents), `auth/` (authentication), `artifacts/`, `channels/` (IM connections), `i18n/` (en-US, zh-CN), `settings/`, `memory/`, `skills/`, `messages/`, `mcp/`, `models/`, `input-polish/` (pre-send draft rewrite API), `voice-input/` (browser speech-recognition helpers), `suggestions/`, `tasks/`, `todos/`, `tools/`, `workspace-changes/` (run-scoped changed-file summaries and diff fetching), `config/`, `notification/`, `blog/`, plus rendering helpers (`rehype/`, `streamdown/`) and `utils/`.
- **`hooks/`** — Shared React hooks
- **`lib/`** — Utilities (`cn()` from clsx + tailwind-merge)
- **`content/`** — MDX content (blog posts, docs) rendered by the app
- **`styles/`** — Global CSS with Tailwind v4 `@import` syntax and CSS variables for theming
- **`typings/`** — Ambient TypeScript declarations
- Root files: `env.js` (env validation), `mdx-components.ts` (MDX component map)

### Data Flow

1. Optional composer helpers such as `core/input-polish` can rewrite the local draft before submission, and `core/voice-input` can transcribe browser microphone input into that same local draft; confirmed user input then flows to thread hooks (`core/threads/hooks.ts`) → LangGraph SDK streaming
2. Stream events update thread state (messages, artifacts, todos, goal)
3. `useThreadHistory` loads persisted conversation pages from `GET /api/threads/{id}/messages/page`, preserving the backend's thread-global event `seq`; rendering overlays checkpoint/live copies at their matching canonical identities (a summarized checkpoint may contain a protected early input plus a recent tail), suppresses checkpoint/transient prefixes whose canonical position is still behind an unloaded cursor page instead of collapsing that unknown gap before a recent anchor, then adds optimistic messages without timestamp re-sorting. History invalidation preserves already-loaded pages so their established ordering positions are not discarded.
4. Stop actions call the LangGraph SDK stream stop path; `core/threads/hooks.ts` invalidates current-thread, thread-history, token-usage, and sidebar/search caches immediately and schedules one follow-up refetch because SDK stop may finish via abort + fire-and-forget cancel before backend title finalization commits
5. TanStack Query manages server state; localStorage stores user settings
6. Components subscribe to thread state and render updates

Composer drafts are tab-scoped browser state. `core/threads/composer-draft.ts` stores only text plus the selected slash-skill name in `sessionStorage`, keyed by user, agent, and logical conversation scope. New-chat pages pass the stable scope `"new"` because their runtime `threadId` is a fresh UUID on every reload; established conversations use their real thread ID. `InputBox` waits for enabled skills before restoring a skill chip, degrades a missing/disabled skill back to editable slash text, and clears the stored draft through `SendMessageOptions.onSent` only after the send passes the in-flight guard. Attachments, sidecar quotes, voice state, and polish undo state are not persisted.

Auth UI note: the login page's "keep me signed in" option submits only `remember_me` to the Gateway and may persist only the email address through `core/auth/remember-login.ts`. Passwords and tokens must never be stored in frontend storage; the `HttpOnly access_token` and readable `csrf_token` cookies remain Gateway-owned.

`/goal` and `/compact` are built-in composer commands, not skill activations. `src/components/workspace/input-box.tsx` intercepts `/goal`, `/goal clear`, and `/goal <condition>` before normal chat submission, calling Gateway `GET/PUT/DELETE /api/threads/{thread_id}/goal`. Setting `/goal <condition>` also submits the condition text as the next user task so the agent starts running immediately; status and clear do not start a run. Goal and compact requests are tied to the current `threadId` with an `AbortController`, so switching threads or unmounting the composer aborts in-flight requests and stale responses cannot update the new thread's composer state. The chat pages render `GoalStatus` above the composer from `AgentThreadState.goal`, with local optimistic state until the next stream `values` update arrives. `/compact` calls `POST /api/threads/{thread_id}/compact` to summarize older active context while leaving the full visible chat history intact; it is skipped on new/empty threads and blocked server-side while a run is in flight.

Human input requests are a structured message protocol layered on normal chat history. The backend writes request payloads to `ToolMessage.artifact.human_input`, `src/core/messages/human-input.ts` owns the runtime validators/types, and `src/components/workspace/messages/human-input-card.tsx` renders the reusable card. `MessageList` owns answered/latest/pending state for visible cards, but derives answered responses from raw `thread.messages` because replies are hidden; pending cards clear when the hidden reply appears, when dispatch is dropped, or when a new `thread.error` reports an async stream failure. Page-level submit callbacks must send a normal human message and put `hide_from_ui: true` plus the response payload in the fourth `sendMessage(..., options)` argument as `options.additionalKwargs`; the third argument remains run context such as `{ agent_name }`. Composer entry points should disable normal bottom input while `hasOpenHumanInputRequest(...)` is true so users answer through the card and preserve response metadata.

Follow-up suggestion generation must also stay disabled while an unanswered human-input card is open. The card already owns the next user decision; calling `POST /api/threads/{id}/suggestions` in parallel would spend an unrelated model request and compete with that required answer. Keep this guard in the pure input-box helper and cover both the blocked-card and ordinary-completed-turn cases with unit tests.

Tool-calling AI messages stay in an `assistant:processing` group, but the
customer UI must not render their free-form assistant text, raw reasoning, raw
tool names, Skill names, commands or local paths. `message-list.tsx` mounts
`MessageGroup` for that group; `message-group.tsx` projects only allowlisted
customer-safe activity labels from `core/tools/utils.ts` and shows the generic
thinking label before the first useful tool call arrives. Keep this processing
surface live during long browser/model operations so the product never appears
frozen, while implementation detail remains hidden. The list-level generic
thinking placeholder exists only before the current human turn has any
assistant surface; once an `assistant:processing`, normal assistant,
clarification, file or subagent group exists, that group exclusively owns the
status so two thinking rows can never stack.

### Key Patterns

- **Server Components by default**, `"use client"` only for interactive components
- **Thread hooks** (`useThreadStream`, `useSubmitThread`, `useThreads`) are the primary API interface
- **Thread routes** — construct Web UI chat paths through `core/threads/utils.ts::pathOfThread()`, which percent-encodes both custom agent names and thread IDs before inserting them into route segments
- **LangGraph client** is a singleton obtained via `getAPIClient()` in `core/api/`
- **Environment validation** uses `@t3-oss/env-nextjs` with Zod schemas (`src/env.js`). Skip with `SKIP_ENV_VALIDATION=1`
- **Subtask step history and runtime metadata** (`core/tasks/`) — the subtask card shows a subagent's full step timeline (#3779): its assistant reasoning turns interleaved with the tools it ran. `Subtask.steps[]` is accumulated live from `task_running` events (appended via `mergeSteps`, not overwritten) and backfilled on expand for historical runs by `fetchSubtaskSteps`, which pages the events endpoint scoped to one task (GET `/runs/{runId}/events?event_types=subagent.step&task_id=…&after_seq=…`) until a short page, so the run-wide limit can't truncate the timeline. `task_started` carries the effective `model_name`; `task_running` carries a cumulative usage snapshot after each completed LLM call. `core/tasks/lifecycle.ts` normalizes these additive events, and `computeNextSubtask` keeps the largest cumulative total so replayed or late SSE frames cannot double-count or roll the folded card backward. Terminal ToolMessage metadata (`subagent_model_name` / `subagent_token_usage`) restores the same values from normal history after reload; no per-card event fetch is needed. `core/tasks/steps.ts` is the pure step model: `messageToStep` (live), `eventsToSteps` (reload), `mergeSteps` (dedup by `message_index`), and `stepsForDisplay` (what the card renders — keeps tool steps + AI steps with text, drops the trailing final-answer AI step when completed since it's shown as `result`). `core/tasks/context.tsx`'s `useUpdateSubtask` applies updates against a `tasksRef` mirroring the latest state (not a closure snapshot), so a late-resolving `fetchSubtaskSteps` backfill merges into current state instead of clobbering SSE steps or sibling subtasks that arrived meanwhile. The owning `run_id` is carried onto history content messages in `buildVisibleHistoryMessages` so the card can resolve the events endpoint.

### Interaction Ownership

- `src/app/workspace/chats/[thread_id]/page.tsx` owns composer busy-state wiring.
- `src/core/personal-ip/` owns account API hooks and
  the fixed browser-platform registry. It also owns the versioned operating
  cockpit query for the six-stage business loop and nine-stage video line;
  account/subject mutations must invalidate that cockpit query.
  `/workspace/dashboard` is the customer-facing owner-wide operating read
  model and its sidebar entry stays immediately above `新对话`. It may aggregate
  only persisted `window_total`/`delta` observations, must keep missing
  coverage distinct from zero and may mark paid-traffic review candidates only
  after at least three same-platform post samples. The CTA starts evaluation;
  it never starts spend.
  `/workspace/personal-ip` always renders
  all eight supported platforms; `src/components/workspace/personal-ip/` owns
  account editing and the manual-login dialog. Account login uses the
  account-scoped browser lifecycle socket, never a synthetic chat thread.
  `native_window` presentation is the normal local path and shows only a compact
  status dialog while the user operates the real Chromium window;
  `embedded_stream` is the no-display server fallback. Empty platforms create a
  minimal account slot before opening login; QR, CAPTCHA and MFA remain user
  actions. An `account_authenticated` stream event closes the login dialog and
  shows success; it carries no credential or business-data payload. The
  portfolio derives the customer-facing 未添加 / 待登录 / 已登录 /
  采集受限 / 可执行 states from non-secret account metadata and records only a
  non-secret login marker after that event. Later detailed collection remains an
  agent/browser responsibility.
  Settings renders MineContext in the dedicated `本地上下文` section; the
  operating portfolio must not duplicate it. This control surface must keep
  operator availability distinct from owner consent and running state. The
  customer UI exposes one enable action rather than scope/purpose checkboxes:
  new owners receive every supported scope and Personal-IP purpose and the
  workspace bootstrap starts the local runtime automatically. Internal purpose
  ids such as `hllm_user_profile` must never be rendered. Show retention,
  evidence count, one persistent opt-out action and one all-local-data deletion
  action. The product default enables bounded screen summaries, while file
  watching remains off unless an exact directory is configured.
  Whole Personal-IP portability and erasure live in the separate
  `数据与备份` Settings section. Export downloads the versioned credential-free
  owner backup; restore accepts that file only through the server's
  same-owner/empty-scope digest verification. Permanent deletion must first
  fetch a fresh server preview and keep its exact phrase, backup
  acknowledgement and state digest visible in the confirmation surface.
  Never implement deletion as a one-click action or cache a confirmation
  across state changes.
  The Skill catalog is not a customer surface: omit the Skills Settings
  section, Skill autocomplete/chips, agent Skill badges, and internal Skill
  tool/path steps from conversations, subtask timelines, copy and exports.
  Keep built-in slash commands such as `/goal` and `/compact`; internal Skill
  execution and persistence remain unchanged.
  Never accept or cache an expanded account record as run authority; the Gateway
  resolves it again for the authenticated owner. Keep the portfolio page a thin
  subject and account surface: subjects may be people, brands, products or
  organizations, and DeerFlow conversation tools create and advance business
  or video workflows instead of duplicating them as form-heavy applications.
  The account editor contains only subject assignment, platform identity and
  login metadata. Never restore per-account audience, promise, content-pillar,
  voice or business-goal fields: canonical operating strategy is subject-level
  and versioned. First-use entity/business discovery, benchmark research,
  differentiation thesis, positioning alternatives, name/avatar/bio decisions
  and pilot validation
  belong to the natural Agent conversation and private backend strategy ledger;
  never add a questionnaire, stage-field inspector or “建模完成” shortcut to
  the customer UI. The operating dashboard shows useful business outcomes and
  queues, not private strategy documents or a second editable modeling form.
  New-chat welcome copy must ask what the user wants to advance, not which
  account they want to operate. A true first-use customer may start with one
  goal, topic, script, asset or link and must not be told to create/connect an
  account until the requested operation actually needs one. First-use
  incubation stays in the ordinary composer: the backend marks active adaptive
  narrative-interview replies in `additional_kwargs`, and `InputBox` must
  suppress generic follow-up-suggestion requests while the latest assistant
  marker is active. Do not replace the composer with clarification cards,
  choices, a field-progress surface or a second intake UI.
  Video production is task-native rather than a global customer page.
  `personal_ip_begin_video_production` records the current DeerFlow
  `thread_id`; `/workspace/chats/[thread_id]` detects that owner-scoped binding
  and replaces the ordinary chat canvas with the human/agent workbench. Each
  new video therefore starts in a new conversation and returns to the same
  workbench through normal thread history. The legacy
  `/workspace/personal-ip/video` route remains only for old local projects to
  bind their previously persisted thread; it must not appear in the sidebar or
  dashboard and must not become a global project switcher again.
  `core/personal-ip/video-productions.ts` owns its list/read-model,
  confirmation and server-compiled timeline-revision mutations. The page must
  display evidence from the
  immutable production ledger—including provider/model/task ids, cost state,
  failures, retries, artifact hashes and QA—without exposing credentials or
  inventing durable client state. Its director layout folds the nine-stage ledger into
  four user-facing stages (`设定 → 分镜 → 剪辑 → 成片`), with shots on
  the left, preview/version/instruction and timeline in the center, and project
  references on the right. Mount exactly one editable timeline in the lower
  dock, and only during the edit stage; setup, storyboard and delivery never
  mount it. In the edit stage the upper canvas is a render monitor and revision
  summary, while the lower dock exposes all manual and Agent edit controls. Do
  not expose a separate pipeline shortcut rail: picture, sound
  and QA capabilities are selected internally by the Agent through the same
  controlled composer. Hide both side rails in the edit stage so the preview
  and timeline use the recovered width; users return to storyboard for shot
  regeneration or setup for character, scene and style changes. The
  selected clip uses Jianying-style direct manipulation: move it by dragging
  the clip body and trim it by dragging either edge. Do not mount a selected
  clip status/toolbar row, a persistent numeric inspector or a second
  `TimelineEditor`; version, transition, volume and text changes go through
  the Agent. Keep one Agent composer in that edit surface. Do not ask the user for a
  second free-text "manual revision note"; derive its immutable receipt intent
  from the typed operations. Shot and timeline prompts use a persistent native
  `ip-agent` thread with production/target context; ids select one operation
  and never scope conversation authority. Manual drag/trim/split/copy/delete/
  volume/caption changes remain local drafts until Save, then compile through
  the same `timeline_revision_compiled` contract as Agent edits. Never persist
  pointer movement or overwrite earlier candidates/revisions. Only candidate
  selection, real paid calls and real publishing are meaningful confirmations;
  evidence promotion stays automatic. Candidate version tiles must remain
  directly previewable before selection. The smooth-motion action only
  pre-fills the native Agent workflow: measure cadence first, create a separate
  motion-compensated candidate only when recommended, then re-run QA and let
  the user compare versions.
  Setup is also a candidate work surface: its left rail lists only character,
  scene, prop and image artifacts (never document/video receipts), the selected
  asset version is previewed centrally, and its persistent `ip-agent` composer
  carries `target=setup` plus the selected asset identity. Generated versions
  stay append-only and enter the production through standard media receipts;
  adoption updates the asset manifest only after the user chooses a version.
  Keep adopt, user-library and new-version shortcuts hidden on each left-rail
  thumbnail until hover/focus; do not duplicate those actions below or over the
  central preview.
  Storyboard keeps the selected-shot Agent composer pinned at the bottom of the
  central work surface. Do not expose the raw shot-contract or continuity-
  evidence accordion there; the Agent continues to consume those records
  internally, while generation tasks and candidate confirmation remain
  available through their focused views.
  Hide the timeline dock throughout setup and storyboard. The setup Agent
  composer and the storyboard shot composer are their only bottom editing
  controls.
  Delivery is a full-width viewer, not another editor or evidence console.
  Hide both side rails and the timeline dock; expose only the final player and
  one `保存到本地` action. Delivery QA, contract versions, raw refs, hashes and
  publish checkpoints remain internal or in receipts.
- `src/app/workspace/chats/[thread_id]/page.tsx` owns branch-from-turn submission and navigation; sidecar `MessageList` instances do not receive the branch action.
- `src/app/workspace/chats/[thread_id]/page.tsx` gates the Workspace Browser trigger and browser right panel on `/api/features -> browser_control.enabled`; default/failed feature discovery hides the browser control so optional backend installs do not show a dead Live socket.
- `src/app/workspace/chats/[thread_id]/page.tsx` and `src/app/workspace/agents/[agent_name]/chats/[thread_id]/page.tsx` own active-goal display state for their composer overlays.
- `src/components/workspace/messages/message-list.tsx` owns human-input card answered/latest/pending gating; entry pages only translate a submitted card response into `sendMessage` calls.
- `src/components/workspace/browser-view/browser-view-panel.tsx` forwards each physical pointer click as one `click` input; do not also emit `down`/`up` for the same gesture because the remote Playwright click would run twice.
- `src/core/threads/hooks.ts` owns pre-submit upload state and thread submission.

## Code Style

- **Imports**: Enforced ordering (builtin → external → internal → parent → sibling), alphabetized, newlines between groups. Use inline type imports: `import { type Foo }`.
- **Unused variables**: Prefix with `_`.
- **Class names**: Use `cn()` from `@/lib/utils` for conditional Tailwind classes.
- **Path alias**: `@/*` maps to `src/*`.
- **Components**: `ui/` and `ai-elements/` are generated from registries (Shadcn, MagicUI, React Bits, Vercel AI SDK) — don't manually edit these.

## Environment

Backend API URLs are optional; an nginx proxy is used by default:

```
NEXT_PUBLIC_BACKEND_BASE_URL=http://localhost:8001
NEXT_PUBLIC_IP_AGENT_TEST_MODE=1
NEXT_PUBLIC_LANGGRAPH_BASE_URL=http://localhost:8001/api
```

Leave these unset for the standard `make dev` / Docker flow, where nginx serves the public `/api/langgraph/*` prefix and rewrites it to Gateway's native `/api/*` routes.
Only `make ip-test-start` should set `NEXT_PUBLIC_IP_AGENT_TEST_MODE=1`; the
workspace then renders the persistent test-mode data-isolation banner. Do not
derive this indicator from a query string or local storage, because the backend
database and owner filesystem must actually be isolated before the UI claims
test mode.

## Resources

- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [LangChain Core Concepts](https://js.langchain.com/docs/concepts)
- [TanStack Query Documentation](https://tanstack.com/query/latest)
- [Next.js App Router](https://nextjs.org/docs/app)

## Contributing

When adding features:

1. Follow the established `src/` structure
2. Add TypeScript types and proper error handling
3. Write unit tests under `tests/unit/` (`pnpm test`), mocked browser scenarios
   under `tests/e2e/` (`pnpm test:e2e`), and cross-stack contracts under
   `tests/e2e-real-backend/`
4. Run `pnpm check` before committing
5. Update this `AGENTS.md` when architecture, commands, or conventions change

Mock artifact Route Handlers must keep dynamic paths statically anchored below
`public/demo/threads`, reject traversal segments, and verify the resolved real path
remains inside the selected thread. Do not resolve a caller-controlled suffix directly
against `process.cwd()`: that can leak files and makes Next.js trace the whole project.
