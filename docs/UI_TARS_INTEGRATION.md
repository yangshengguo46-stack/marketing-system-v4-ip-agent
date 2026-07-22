# UI-TARS native integration

## Boundary

DeerFlow is the only agent brain. This integration does not ship or start
Agent TARS and does not call UI-TARS `GUIAgent.run()`. The lead agent plans the
task and invokes `ui_tars_desktop_step` for one bounded visual action. Browser
Control remains the default for web pages; valid fallback reasons are
`browser_dom_unavailable`, `browser_action_failed` and
`native_desktop_required`. Web fallback reasons are accepted only after a
completed Browser Control call appears in the current DeerFlow run; a model's
unsupported assertion alone cannot skip Browser Control.

An optional Personal-IP `account_id` is owner-validated as the concrete action
target. It never filters portfolio context, tool availability, memory or any
other conversation authority.

## Pinned source and runtime

The source archive includes these selected Apache-2.0 paths from
`bytedance/UI-TARS-desktop` commit
`c2ad42e3eb9b27830db41a3e6f51ca7179d9b168`, package version `1.2.3`:

- `packages/ui-tars/sdk`
- `packages/ui-tars/action-parser`
- `packages/ui-tars/shared`
- `packages/ui-tars/operators/nut-js`

`VENDORED_VERSION.json` pins the selected tree digest. The upstream NutJS
manifest is retained for provenance, but this distribution does not install
its precompiled `libnut-*` dependencies. The managed macOS operator uses
`screencapture`, Accessibility and AppleScript already provided by the OS.
Other systems may use `mode: connect` only with a separately audited loopback
operator that implements the same one-step contract. Give the Gateway and that
operator the same random `UI_TARS_OPERATOR_TOKEN` (at least 32 characters); the
doctor reports only whether it is configured, never its value.

## Configuration and lifecycle

The `config.yaml` defaults are deliberately off:

```yaml
ui_tars:
  enabled: false
  mode: managed
  endpoint: http://127.0.0.1:9137
  model: ""
  api_base: ""
  api_key_env: UI_TARS_API_KEY
  request_timeout_seconds: 60
  screenshot_privacy: pixelated
  pixelation_block_size: 24
```

Only loopback HTTP is accepted for the operator endpoint. Model endpoints must
use HTTPS or loopback HTTP. The configured key field is an environment-variable
name, never a credential value.

```bash
make ui-tars-install
make ui-tars-doctor
make ui-tars-start
make ui-tars-status
make ui-tars-stop
```

`install` verifies the source tree and writes a local installation receipt with
`precompiled_native_binaries: false`. `doctor` diagnoses the source pin, model
configuration, process/connection, Screen Recording and Accessibility without
capturing a screen or prompting for access. The managed lifecycle token, PID,
logs, transformed evidence and receipts live under ignored `.deer-flow/ui-tars`
with private file modes.

## Privacy and audit contract

The managed operator captures raw screen bytes into a private temporary file,
immediately transforms the whole image with block pixelation, deletes the raw
file and sends only the transformed image to the configured UI-TARS model. Raw
screenshots are never returned to DeerFlow or written to receipts. Setting
`screenshot_privacy: blocked` disables model steps entirely.

Instructions containing credential-like material are rejected. Model and log
payloads recursively omit Cookie, Token, password, secret, authorization and
browser-profile fields. Typed content is rejected when credential-like, and a
typing action cannot submit a form in the same step.

Every attempted step writes `deerflow-ui-tars-receipt-v1` JSONL with:

- sanitized action intent;
- target application/window and optional account target;
- DeerFlow task id and exact UI-TARS model id;
- result and executed action type;
- fallback reason and failure category;
- privacy-transformed screenshot reference and SHA-256 when available;
- structured approval request id when applicable.

Publishing, sending, deletion, system/account setting changes and payment are
classified as high impact. The native tool proceeds only when its request id
matches a prior `ask_clarification` request of type `risk_confirmation` and a
later structured affirmative response in the same DeerFlow state. A plain
model argument cannot manufacture that approval.

## Safe validation

Unit/integration tests use generated images, fake model responses, fake desktop
backends and temporary state. They never publish, send messages, delete data,
change system settings, request permissions or make paid model calls. Real
acceptance is intentionally left to a human-controlled desktop session.
