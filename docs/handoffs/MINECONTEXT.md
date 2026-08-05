# MineContext native integration handoff

Date: 2026-07-22
Branch: `parallel/minecontext-integration`
Baseline: `3e56b0a36406c53070a37500278f6b64570be519`

## Outcome

MineContext is a native Personal-IP local observation source while DeerFlow
remains the only agent brain. The integration now ships enabled and
automatically starts bounded screen summaries for a new owner. An explicit
Settings opt-out persists across page loads. The customer surface exposes only
status, retention, disable/re-enable and complete local-data deletion.

## Upstream and license evidence

- Official Git: <https://github.com/volcengine/MineContext>
- Exact commit: `171c7a9ea8091e326ddcf0f10718aa1b58c83c65`
- Git tree: `b185239b776e176ad25faf584050cf0c31226108`
- Commit date: `2026-05-07T21:23:05+08:00`
- License: Apache-2.0
- Snapshot comparison: the supplied research snapshot was byte-for-byte equal
  to the official checkout at that commit (excluding `.git`).
- Distribution: all 504 official tracked source files are under
  `third_party/volcengine/MineContext`; no opaque MineContext executable is
  shipped.
- Upstream contained `LICENSE` but no `NOTICE`. The distribution preserves the
  license and adds a provenance NOTICE plus `VENDORED_VERSION.json` containing
  the exact commit/tree, a 504-file `UPSTREAM_FILES.sha256` manifest and focused
  checksums for LICENSE, `pyproject.toml`, CLI and the processed-context search
  boundary.

`make minecontext-verify` checks the pin without installing or starting
anything. `make minecontext-install` creates an ignored project-local virtual
environment and installs the vendored source in editable mode. `make
minecontext-doctor` verifies that the runtime resolves back to that source.

## Lifecycle and privacy boundary

Startup config is `minecontext` in `config.example.yaml` and defaults to
`enabled: true`. `make install` builds the isolated runtime. The first workspace
status request or native evidence operation starts a new owner's bounded screen
summary sidecar; an explicit opt-out remains off. Per-owner state lives under
`.deer-flow/users/<owner>/minecontext` with `0700` directories and `0600`
files. A process binds only to loopback and uses a per-start random API key that
is never returned to the frontend or model.

The product default uses bounded continuous screen summaries at no less than a
60-second interval and the literal target `all_displays`, matching what this
upstream pin can actually enforce. Folder watching remains off when no exact
directory is configured; configured paths must be existing absolute directories
and broad root/home-directory watches are rejected.

The generated upstream config disables MineContext consumption, content
generation, completion, web search tools and cross-context merging. Only
MineContext's processed vector-search summary endpoint is bridged into
DeerFlow. The child environment is an allowlist. It reuses
`VOLCENGINE_API_KEY` for the default Doubao vision and embedding models; six
`MINECONTEXT_*` settings remain optional overrides. Other Gateway credentials
are not inherited.

## Evidence contract and downstream flow

The only model-facing contract is
`personal-ip-local-context-evidence-v1`. Its allowlist is:

- hashed upstream record reference, provider and exact upstream commit;
- authorized semantic/source kind and processed context type;
- observation and seal times;
- bounded title, summary and keywords;
- relevance, partial-coverage warning, redaction count and digest.

Raw screenshots, full screen text, raw document content, local paths, vectors,
embeddings, cookies, tokens, passwords, API keys, email addresses and phone
numbers are excluded. Secret-like text and URL query/fragment values are
redacted before persistence. Retention pruning occurs on status, store and
read; evidence is owner-isolated and unavailable after revoke.

Native DeerFlow tools are `personal_ip_minecontext_sync` and
`personal_ip_minecontext_evidence`. For a new owner they may idempotently
apply the product default and start the sidecar; they never override a user's
explicit opt-out and have no account/thread filter. Selected evidence can enter
the HLLM `user_profile` only as
`personal-ip-hllm-context-evidence-v1`, marked
`observational_partial_revisable`. A preflight requires both `preflight` and
`hllm_user_profile` purposes, seals the projection in the immutable model
request, and carries the same allowlisted projection into its retrospective.

## API and UI

Owner-authenticated routes:

- `GET /api/personal-ip/minecontext`
- `POST /api/personal-ip/minecontext/enable`
- `POST /api/personal-ip/minecontext/authorize`
- `POST /api/personal-ip/minecontext/start`
- `POST /api/personal-ip/minecontext/stop`
- `POST /api/personal-ip/minecontext/revoke`
- `POST /api/personal-ip/minecontext/sync`
- `DELETE /api/personal-ip/minecontext/data?scope=evidence|all`

Every workspace mounts a lightweight status bootstrap. For a new owner it
performs a read-only status request: it does not create consent, launch a
sidecar or capture a screen. Settings requires an explicit owner confirmation
before bounded screen collection can start, and exposes status, retention,
persistent disable/re-enable, evidence count and deletion semantics. Internal
scope and purpose identifiers are not customer controls.

## Packaging and verification

The source-package required-path contract includes the MineContext verifier,
LICENSE, NOTICE, README, version manifest, packaging metadata, CLI and search
boundary. Package smoke extraction runs `minecontext_source.py verify` without
installing dependencies or accessing credentials. Clean install therefore
contains the complete source, and normal `make install` builds the optional
isolated runtime. Installation alone never authorizes collection. `make doctor`
verifies the source pin; when operator-disabled it does not require a runtime or
provider credentials, and when enabled it reports only missing variable names,
never their values.

All automated tests use local synthetic fixtures and temporary owner
directories. They do not inspect host screenshots, documents, browser profiles
or user files.

## Verification results

Final command results are recorded here before branch handoff:

- Backend full suite: `8734 passed, 54 skipped`.
- Backend focused MineContext/config/doctor/tool/HLLM/retro suite: `95 passed`.
- Root source/package and clean-install suite: `94 passed`, including the
  runtime-Python and no-bytecode doctor regressions.
- Frontend suite: 84 files / `700 passed`; `pnpm check` and production build
  both passed (the build emitted only the repository's existing timestamp and
  output-file-tracing warnings).
- Full clean source package: 2,847 files; archive verification, extraction and
  smoke test passed. Smoke verified the complete 504-file upstream hash
  manifest without installing or starting MineContext.
- Runtime source install: Python 3.12.13 project-local environment, 133
  packages, editable MineContext 0.1.0 from the pinned vendored directory;
  `minecontext-doctor` confirmed the import resolves to that directory.
- `make doctor` reached and passed the MineContext source/license pin checks;
  its overall non-zero status was expected in this developer checkout because
  unrelated local config, nginx and deployment prerequisites are absent.

## Human authorization acceptance still required

No automated test grants OS capture permission or reads real private data.
Before production enablement, a human owner must:

1. confirm the default status is visible in Settings and approve the OS
   screen-recording prompt;
2. confirm that the default `all_displays` target genuinely matches the
   intended scope;
3. if enabling file watching, choose a dedicated fixture/test directory and
   confirm no parent, home or unrelated directory is traversed;
4. disable the feature, restart Gateway, and confirm the explicit opt-out does
   not auto-resume; then re-enable it once from Settings;
5. revoke authorization and verify runtime/raw data disappears while sealed
   summaries follow the displayed deletion choice;
6. inspect one real processed result to confirm only the minimized contract
   reaches preflight/HLLM/retrospective logs; and
7. run evidence-only and delete-all actions, then verify owner A cannot read
   owner B's state.
