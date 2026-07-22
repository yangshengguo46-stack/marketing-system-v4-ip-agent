# IP Agent clean-install handoff

Date: 2026-07-22

Branch: `parallel/clean-install`

Baseline: `439f3093297cedd5f1718704719708b1db18dba3`

## Scope and isolation

The acceptance path builds the source archive through
`scripts/package_ip_agent.py`, verifies its manifest, extracts it into a new
temporary directory and runs with an allowlisted environment only. HOME,
TMPDIR, XDG, uv, npm and pnpm cache roots all point inside that directory. Host
proxy variables, API keys, tokens, credentials and user config are not passed
through.

The archive member audit confirmed that it did not contain `.git`, `.env` or
`.env.*` runtime variants, root runtime config, `.deer-flow`,
`.playwright-mcp`, browser profiles, `node_modules`, `.venv` or Python caches.
The only packaged IP Agent `config.yaml` is the versioned product default.

Primary repeatable command:

```bash
make ip-clean-install
```

For a retained workspace and credential-free JSON result:

```bash
python3 scripts/clean_install_ip_agent.py \
  --workspace /new/empty/path \
  --report /safe/report/path.json
```

The default command requires a committed tree. `--allow-dirty` exists only for
development validation of already tracked changes.

## Validation environment

- Host: macOS Darwin x86_64
- Host Python: 3.14.3; packaged `backend/.python-version`: 3.12
- Installed project Python: 3.12.13
- Node.js: 26.4.0
- pnpm: 11.9.0
- uv: 0.11.11
- Docker: not installed; the true temporary-directory isolation path was used
- nginx: not installed

No credential-bearing file or existing credential value was inspected.

## Commands and results

| Gate | Command | Result |
| --- | --- | --- |
| Source archive | `python3 scripts/package_ip_agent.py build --output <temp>/ip-agent-source.tar.gz --smoke` | Passed; manifest, per-file hashes, extraction, default-agent install and compile smoke verified |
| Pristine extraction | automatic archive/tree audit | Passed; forbidden local/runtime paths absent |
| Config bootstrap | `make config` | Passed using example files only |
| IP Agent init | `make ip-init` | Passed; default profile, SOUL and agent config installed under isolated `.deer-flow` |
| Backend dependencies | `cd backend && uv sync` via `make install` | Passed with Python 3.12.13; macOS Intel used the binary-compatible `cryptography` 48.0.1 wheel and did not download Rust |
| Frontend dependencies | `cd frontend && pnpm install` via `make install` | Passed after isolated-cache network retries; pnpm 11 ignored-build policy remained explicit and non-fatal |
| Source-archive hooks | `python3 scripts/install_dev_hooks.py` via `make install` | Passed by intentionally skipping hooks because `.git` is absent |
| Doctor | `make doctor` | Executed; core source/config/profile checks passed, with expected customer/system diagnostics below |
| Backend import/schema | clean-room backend import plus two SQLite `init_engine` calls | Passed; empty bootstrap stamped `0016_personal_ip_auto_evidence`, second versioned bootstrap was a no-op upgrade |
| Frontend production | `cd frontend && pnpm build` | Passed; 81 static pages generated and TypeScript completed |

The production build emitted non-blocking warnings about missing Git metadata
for Nextra, Node 26 deprecations, anonymous Next.js telemetry and one broad NFT
trace from an existing mock artifact route. It exited successfully.

## Issues fixed

1. `make install` failed in a source archive at `pre-commit install` because the
   archive intentionally has no `.git`. Repository-only hook installation now
   skips cleanly outside a Git checkout.
2. `cryptography` 49 has no macOS x86_64 wheel and caused an implicit Rust
   toolchain download. The harness now selects 48.0.1 only on macOS Intel while
   leaving other platforms on the normal range.
3. An over-restrictive uv environment switch ignored the packaged
   `.python-version`, selected Python 3.14 and exposed the locked
   `onnxruntime` ABI gap. The clean room now isolates HOME/XDG without disabling
   project-local uv configuration.
4. pnpm 11 made the repository's explicit ignored-build list fatal and wrote
   placeholder policy entries. The workspace now carries explicit v10/v11
   deny policy with `strictDepBuilds: false`.
5. Empty `models:` produced three secondary `NoneType` doctor errors. Provider
   checks now treat it as an empty list and leave the actionable setup failure.
6. npm registry timeouts near the end of an empty-cache install were classified
   poorly. The acceptance runner now labels network/ABI/permission/Docker/system
   failures separately, uses lower clean-room registry concurrency and performs
   one bounded retry inside the same isolated cache.

## External diagnostics and remaining customer actions

- Network access is required for first-time PyPI and npm downloads. During this
  run, npm registry requests repeatedly timed out after most of the 1064 locked
  packages had downloaded. Reusing only that run's isolated cache completed the
  install. On a restricted network, allow outbound PyPI/npm access or provide an
  approved internal mirror; the script reports the failed stage without copying
  host proxy credentials.
- nginx is absent on this host. Install it with the platform command printed by
  `make doctor`, or use the Docker route. Docker itself was not available here;
  Docker-only setup was not attempted.
- The clean example config intentionally has no model and no customer keys. Run
  `make setup`, configure at least one model and provide the referenced
  environment variable names before expecting doctor to become ready.
- Project-local FFmpeg, source-built MediaKit and Playwright Chromium are
  optional heavier toolchains and were not built in this core clean-install
  pass. Doctor prints their exact opt-in commands. HLLM/MediaKit remain source
  distributions; no opaque binary replacement was introduced.

## Test evidence

```bash
cd backend && PYTHONPATH=. uv run pytest \
  tests/test_dependency_platform_compatibility.py \
  tests/test_doctor_clean_install.py tests/test_doctor.py -q
PYTHONPATH=. backend/.venv/bin/python -m pytest \
  tests/test_package_ip_agent.py tests/test_init_ip_agent.py \
  tests/test_install_dev_hooks.py tests/test_clean_install_ip_agent.py -q
cd frontend && pnpm exec rstest run tests/unit/config/pnpm-policy.test.ts
cd frontend && pnpm check
```

All listed tests and checks passed. `docs/IP_AGENT_PRODUCT_LEDGER.md` was not
modified.
