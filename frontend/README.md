# DeerFlow Frontend

Like the original DeerFlow 1.0, we would love to give the community a minimalistic and easy-to-use web interface with a more modern and flexible architecture.

## Tech Stack

- **Framework**: [Next.js 16](https://nextjs.org/) with [App Router](https://nextjs.org/docs/app)
- **UI**: [React 19](https://react.dev/), [Tailwind CSS 4](https://tailwindcss.com/), [Shadcn UI](https://ui.shadcn.com/), [MagicUI](https://magicui.design/) and [React Bits](https://reactbits.dev/)
- **AI Integration**: [LangGraph SDK](https://www.npmjs.com/package/@langchain/langgraph-sdk) and [Vercel AI Elements](https://vercel.com/ai-sdk/ai-elements)

## Quick Start

### Prerequisites

- Node.js 22+
- pnpm 10.26.2+

### Installation

```bash
# Install dependencies
pnpm install

# Copy environment variables
cp .env.example .env
# Edit .env with your configuration
```

### Development

```bash
# Start development server
pnpm dev

# The app will be available at http://localhost:3000
```

### Build & Test

```bash
# Type check
pnpm typecheck

# Check formatting
pnpm format

# Apply formatting
pnpm format:write

# Lint
pnpm lint

# Run unit tests
pnpm test

# One-time setup: install Playwright Chromium browser
pnpm exec playwright install chromium

# Run E2E tests (builds and starts production server automatically)
pnpm test:e2e

# Run real Next.js + real Gateway + temporary SQLite E2E tests
pnpm exec playwright test -c playwright.real-backend.config.ts

# Build for production
pnpm build

# Start production server
pnpm start
```

## Site Map

```
├── /                    # Landing page
├── /chats               # Chat list
├── /chats/new           # New chat page
├── /chats/[thread_id]   # A specific chat page
├── /workspace/dashboard         # Owner-wide real operating metrics and queues
├── /workspace/personal-ip       # Subjects, accounts and platform login
└── /workspace/personal-ip/video # Human/agent video director and edit workbench
```

The operating dashboard reads persisted Personal-IP observations rather than
demo data. It shows explicit missing/partial coverage, seven-day growth,
platform contribution, recent-work performance and safe paid-traffic review
candidates. A candidate is an evaluation prompt only; it cannot authorize
spend.

Early person/business discovery, benchmark research, naming, visual direction
and pilot decisions remain a natural Agent conversation. The dashboard does
not expose private strategy documents, a questionnaire or a premature “model
complete” state.
The account editor therefore manages only subject assignment, platform,
display identity and login metadata; it does not duplicate positioning fields.

MineContext consent and local-data lifecycle controls live under Settings →
Local context, keeping the operating portfolio focused on subjects and platform
accounts. It starts for new owners with all Personal-IP purposes and bounded
screen summaries selected internally. The customer sees only disable/re-enable,
retention and local-data deletion controls.

## Configuration

### Environment Variables

Key environment variables (see `.env.example` for full list):

```bash
# Backend API URL (optional, uses local Next.js/nginx proxy by default)
NEXT_PUBLIC_BACKEND_BASE_URL="http://localhost:8001"
# LangGraph-compatible API URL (optional, uses local Next.js/nginx proxy by default)
NEXT_PUBLIC_LANGGRAPH_BASE_URL="http://localhost:8001/api"
```

During a running conversation, the UI shows concise customer-facing activity
such as “正在理解你的需求”, “正在读取账号的最新数据” and “正在汇总各平台
数据”. It does not render raw tool names, Skill names, commands, paths or model
reasoning. This keeps long browser/model operations visibly alive without
turning internal implementation details into a customer surface.

## Project Structure

```
tests/
├── e2e/                    # Browser interactions with mocked backend APIs
├── e2e-real-backend/       # Real Next.js/Gateway/temporary-SQLite contracts
└── unit/                   # Unit tests (mirrors src/ layout)
src/
├── app/                    # Next.js App Router pages
│   ├── api/                # API routes
│   ├── workspace/          # Main workspace pages
│   └── mock/               # Mock/demo pages
├── components/             # React components
│   ├── ui/                 # Reusable UI components
│   ├── workspace/          # Workspace-specific components
│   ├── landing/            # Landing page components
│   └── ai-elements/        # AI-related UI elements
├── core/                   # Core business logic
│   ├── api/                # API client & data fetching
│   ├── artifacts/          # Artifact management
│   ├── config/              # App configuration
│   ├── i18n/               # Internationalization
│   ├── mcp/                # MCP integration
│   ├── messages/           # Message handling
│   ├── models/             # Data models & types
│   ├── settings/           # User settings
│   ├── skills/             # Skills system
│   ├── threads/            # Thread management
│   ├── todos/              # Todo system
│   └── utils/              # Utility functions
├── hooks/                  # Custom React hooks
├── lib/                    # Shared libraries & utilities
├── server/                 # Server-side code
│   └── better-auth/        # Authentication setup and session helpers
└── styles/                 # Global styles
```

## Scripts

| Command             | Description                             |
| ------------------- | --------------------------------------- |
| `pnpm dev`          | Start development server with Turbopack |
| `pnpm build`        | Build for production                    |
| `pnpm start`        | Start production server                 |
| `pnpm test`         | Run unit tests with Rstest              |
| `pnpm test:e2e`     | Run E2E tests with Playwright           |
| `pnpm format`       | Check formatting with Prettier          |
| `pnpm format:write` | Apply formatting with Prettier          |
| `pnpm lint`         | Run ESLint                              |
| `pnpm lint:fix`     | Fix ESLint issues                       |
| `pnpm typecheck`    | Run TypeScript type checking            |
| `pnpm check`        | Run both lint and typecheck             |

## Development Notes

- Uses pnpm workspaces (see `packageManager` in package.json)
- Turbopack enabled by default in development for faster builds
- Environment validation can be skipped with `SKIP_ENV_VALIDATION=1` (useful for Docker)
- Backend API URLs are optional; nginx proxy is used by default in development
- The Personal-IP video director lets users click any candidate version to
  preview it. “检查流畅度/生成流畅版” fills the embedded Agent command for
  cadence QA and a non-overwriting motion-compensated derivative; it does not
  bypass normal QA or candidate selection.
- The video workbench keeps four customer stages (`设定 → 分镜 → 剪辑 → 成片`).
  Selected-shot and timeline prompts stream through the native `ip-agent`.
  Direct clip edits are drafts until Save, then the backend seals one shared
  append-only timeline revision; the browser does not own a second edit
  database.
- The setup stage mirrors the shot workflow for visual assets: generated
  character, scene, prop and image versions appear in the left rail, the
  selected version opens in the central preview, and one embedded Agent
  composer handles generation, revision and adoption without overwriting old
  versions. Adopt, library and new-version actions appear only while hovering a
  left-rail thumbnail; the central preview does not repeat them. The unrelated
  timeline dock is hidden while setup is active.
- The edit stage mounts one timeline only: the lower dock expands into the
  complete manual/Agent editor, while the upper canvas monitors the latest
  render and current revision instead of duplicating timeline tracks.
- The timeline has one Agent composer. Manual revision intent is generated from
  typed clip operations, so the UI does not show a second note input that looks
  like another chat box.

## License

MIT License. See [LICENSE](../LICENSE) for details.
