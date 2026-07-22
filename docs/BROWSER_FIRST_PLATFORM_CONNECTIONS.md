# Browser-first platform connections

The Personal-IP product operates social accounts through local browser login
state by default. Official platform APIs are optional connectors and are not a
prerequisite for using the agent.

## Supported account families

The first registry covers Douyin, WeChat Channels, WeChat Official Accounts,
Xiaohongshu, X, Instagram, YouTube and TikTok. Each operated account receives a
separate persistent Chromium profile under its authenticated owner's local
DeerFlow data directory.

The model never receives the profile path, cookie database, password or other
credential material. The user completes passwords, QR scans, CAPTCHA, MFA and
identity checks in the live browser. The agent must not bypass those controls.

This credential boundary is not a business-data restriction. Chromium still
uses its cookies automatically, and server-side connectors may use encrypted
tokens internally. After login, the agent may inspect the authenticated creator
backend in detail: account and content lists, post-level metrics, audience
analytics, traffic sources, comments, conversions and platform receipts.
Collection should retain source URL, observation time, pagination/coverage and
screenshot or raw-field evidence so later analysis can distinguish observation
from inference. Authentication-secret values stay outside model context;
authorized operating data belongs in the Personal-IP evidence loop.

The durable boundary is `personal-ip-platform-observation-v1`. Each immutable
row identifies its owner, exact operated account, platform, dataset, source,
status and observation time; detailed records, direct summaries, coverage and
evidence remain separate fields. Creator-page query strings and fragments are
not retained. Credential-like keys and raw Bearer/JWT/token values are rejected
recursively, including if they are nested inside a captured record. Browser
Control can seal its authorized findings through the native
`personal_ip_record_browser_observation` tool.

`personal_ip_collect_browser_page` is the shared direct collection path for all
eight account families. It derives the platform from the owner-scoped account,
reuses that account's browser session and optionally navigates only to a
query-free URL on the platform's registered creator host. It extracts rendered
page text, headings, tables/grids, metric cards and sanitized links, then seals
the page with explicit pagination coverage and a screenshot SHA-256 digest. It
never accesses browser storage, credential headers or network response bodies.

The shared path deliberately reports generic pages as partial. Platform
adapters establish stronger completeness rules only after their rendered UI has
been verified. Douyin currently has verified dashboard and content-inventory
parsers; its content inventory becomes complete only when the declared count
matches the parsed items and the page reports that no more works remain. The
older `personal_ip_collect_douyin_browser_page` entry remains a compatibility
wrapper, not a second collector.

Dashboard collection also has credential-free rendered-label adapters for all
eight platforms. They normalize direct counts such as 播放量、阅读次数、Views and
Post views while retaining the exact matched label and displayed window in the
platform observation. The adapters do not turn a count into a daily metric by
themselves: `personal_ip_collect_browser_portfolio_today` scans every active
account and writes `window_total` rows only when the rendered page explicitly
labels the data as 今日/今天/Today. A 7-day, 28-day, yesterday or unknown window
is stored as detailed evidence but recorded as unavailable for the requested
today window, never silently reinterpreted.

The same whole-portfolio path is available through
`POST /api/personal-ip/metrics/collect/browser-portfolio-today`. It accepts a
stable collection key plus the start and collection cutoff of today, but no
account id. Each account gets its own immutable detailed observation and metric
observation. The response includes all configured accounts plus an eight-entry
platform coverage map; collection failures remain missing, login or window
limitations remain unavailable, and direct rendered counts remain partial
until platform-specific completeness is proven. The returned aggregate omits
`totals.views` when no account supplied a valid today view count and includes
per-metric account coverage, so callers cannot confuse absence with zero.

The native tool returns the captured business records to the agent as well as
sealing them durably. For later analysis,
`personal_ip_platform_observation_inventory` lists recent evidence across the
whole portfolio without an account filter, and
`personal_ip_read_platform_observation` reads one owner-scoped observation with
its full records and provenance. This makes detailed creator data available for
analysis without ever making the browser's authentication material readable.

The operating portfolio at `/workspace/personal-ip` always shows all eight
platforms. A platform with no account offers **登录账号**; clicking it creates a
minimal local account slot and immediately opens the real platform page. Each
existing account has its own login/open action, so multiple accounts on one
platform never share a browser profile.

The Live route emits only an `account_authenticated` boolean event when a
conservative platform URL rule recognizes successful login. The Web UI closes
the login dialog automatically. This small event does not limit what the agent
may collect afterward through Browser Control or an official API.

## Runtime contract

1. The account-scoped Live route validates the authenticated owner and active
   account before deriving the persistent profile directory. It does not create
   or depend on a chat thread.
2. `personal_ip_select_browser_account(account_id)` validates that the account
   belongs to the authenticated user and selects it as the concrete browser
   target for the current thread.
3. Selection does not narrow conversation authority. Portfolio questions still
   inspect every account; the selected account only determines which persistent
   browser profile subsequent browser actions operate.
4. The selection tool returns the platform's creator/start URL but never a local
   filesystem path.
5. DeerFlow Browser Control uses the account profile first. UI-TARS is the
   visual/desktop fallback when DOM browser actions cannot complete the task.
6. Publishing, sending, deleting and account-setting changes still require the
   product's explicit approval. Browser publication uses
   `personal_ip_prepare_browser_publish` before submission and
   `personal_ip_finish_browser_publish` afterward; success is sealed only when
   the selected live browser visibly opens the declared platform post URL/id.

Closing an in-memory browser session releases Chromium resources but preserves
the account profile and its login state. Deleting an account does not silently
delete the profile directory; destructive cleanup requires a separate explicit
operation.

## Official APIs

Official OAuth/API connections remain useful for high-volume collection,
deterministic publishing and lower-cost scheduled jobs. They are optional:

- ordinary users can operate their already logged-in creator backends locally;
- enterprise customers can bring their own approved application credentials;
- product-owned cloud authorization can be added later without changing the
  account, receipt, retrospective or evidence contracts.

An official connector may improve an account's capabilities, but it must never
become a conversation permission boundary or prevent browser-first operation.
