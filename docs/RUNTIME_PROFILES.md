# DeerFlow runtime profiles

This file is the source of truth for supported ingress profiles and their
health checks. A profile is healthy only when its required path is usable;
optional capabilities are reported separately and do not impersonate a failed
runtime.

| Profile | Intended use | Public entry | Required ingress | Doctor command | Start command |
| --- | --- | --- | --- | --- | --- |
| `local-direct` | Trusted single-machine development | `http://localhost:3000` | Next.js calls Gateway `:8001` directly; the exact frontend origin is in `GATEWAY_CORS_ORIGINS` | `make doctor PROFILE=local-direct` | `make dev-direct` |
| `local-proxy` | Local same-origin development and proxy debugging | `http://localhost:2026` | Host nginx uses the bundled local configuration | `make doctor PROFILE=local-proxy` | `make dev` |
| `production` | Customer deployment | Deployment ingress | Bundled Docker ingress or a managed host reverse proxy | `make doctor PROFILE=production` | `make up` for the bundled stack |

Plain `make doctor` uses `PROFILE=auto`: it selects `local-direct` when the
direct frontend/CORS contract is complete, otherwise it selects an installed
host nginx `local-proxy`. If neither route is complete, it fails with the
`local-direct` repair instructions. `local-direct` is not a production bypass:
`serve.sh --no-nginx` rejects `--prod`, and public deployments still require
authenticated, trusted ingress.

Web search, web fetch, web capture and UI-TARS are optional organs. A missing
optional organ is shown as skipped. A configured but malformed provider, an
unsafe literal secret or a required product dependency remains a warning or
failure.

The Personal-IP operating cockpit is the runtime failure surface for the
customer and Agent. It reports sanitized, owner-scoped alerts in three
categories:

- `loop`: failed/unknown publication, unavailable observations and blocked
  workflow state;
- `provider`: failed video-provider execution without forwarding raw provider
  payloads;
- `cost`: rejected budget admission and exhausted video budget.

Video budget admission rejection is an append-only
`personal-ip-video-budget-rejection-v1` event. It records the requested maximum,
available amount and stable reason code, but not request refs, credentials or
raw provider errors. The cockpit reads active production events and budget
state from the authoritative video ledger; it does not create another state
store.

## Acceptance

```bash
make doctor
make personal-ip-observability-acceptance
```
