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

The operating portfolio at `/workspace/personal-ip` always shows all eight
platforms. A platform with no account offers **登录账号**; clicking it creates a
minimal local account slot and immediately opens the real platform page. Each
existing account has its own login/open action, so multiple accounts on one
platform never share a browser profile.

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
   product's explicit approval and immutable receipt flow.

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
