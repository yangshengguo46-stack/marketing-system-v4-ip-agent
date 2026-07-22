# UI-TARS native integration handoff

## Delivered boundary

DeerFlow remains the only agent brain. This change does not include or start
Agent TARS and never calls the upstream `GUIAgent.run()` loop. The optional
`ui_tars_desktop_step` tool is absent from the model schema by default and
performs at most one model prediction and one allowlisted desktop action per
DeerFlow call when enabled.

Browser Control is mandatory first for web work. A web fallback is rejected
unless the current run contains a completed DeerFlow Browser Control tool call;
native desktop work uses the separate `native_desktop_required` reason. A
Personal-IP account id is owner-validated only as the concrete operation target
and does not filter portfolio context or session authority.

## Source and runtime

The formal source package now includes Apache-2.0 UI-TARS SDK, action-parser,
shared and NutJS operator source version `1.2.3`, byte-identical to
`bytedance/UI-TARS-desktop` commit
`c2ad42e3eb9b27830db41a3e6f51ca7179d9b168`. `VENDORED_VERSION.json` fixes the
selected 58-file tree digest. No `.node`, `.dylib`, `.so`, executable or other
precompiled UI-TARS/libnut payload is included or installed.

The managed macOS operator is DeerFlow-owned source and uses system
`screencapture`, CoreGraphics/Accessibility diagnosis and AppleScript. Other
platforms may use only an independently audited loopback operator in `connect`
mode with a shared `UI_TARS_OPERATOR_TOKEN`. Lifecycle commands are:

```bash
make ui-tars-install
make ui-tars-start
make ui-tars-status
make ui-tars-doctor
make ui-tars-stop
```

## Privacy, approval and audit

Raw screenshots use a mode-600 temporary file, are transformed with
whole-screen block pixelation locally, and are then deleted. Only the
transformed image can reach the configured model or evidence store. Intent,
model responses and receipts are bounded and recursively strip credential,
Cookie, Token, password, authorization and browser-profile fields. Typed
credential-like content is rejected, and typing cannot submit a form in the
same step.

Every attempt appends a `deerflow-ui-tars-receipt-v1` record with sanitized
intent, target application/window/account, DeerFlow task id, exact model id,
result/action, fallback reason, transformed evidence reference/digest and
failure category. Publish/send/delete/settings/payment work proceeds only when
the request id matches a prior structured `risk_confirmation` request and a
later affirmative human response in the same DeerFlow state.

## Verification completed

- UI-TARS/doctor/source-package tests: `85 passed`.
- Full backend suite: `8731 passed, 54 skipped, 12 warnings` in 401.14 seconds.
- Strict blocking-I/O suite: `49 passed`; the project-wide static inventory
  reported 34 existing findings and none in the new UI-TARS files.
- Source-only install receipt: fixed source/digest verified,
  `precompiled_native_binaries: false`.
- Credential-free clean install: `passed_with_doctor_diagnostics` across source
  archive smoke test, config bootstrap, IP initialization, dependency install,
  backend import/repeatable migration and frontend production build. Doctor
  diagnostics were the expected missing customer model/nginx/optional local
  toolchain checks; it verified the UI-TARS source and reported the organ
  disabled by default.
- No real publish, message send, deletion, system-settings mutation or paid
  model call was performed.

The containing Git commit is reported in the final task handoff.

## Human desktop/model acceptance still required

1. On the intended macOS host, set `ui_tars.enabled: true`, choose a test model
   id and HTTPS or loopback OpenAI-compatible `api_base`, and set the named API
   key only when the model endpoint is remote.
2. Run `make ui-tars-install && make ui-tars-doctor`. Grant Screen Recording
   and Accessibility to the exact Python/host application that will launch the
   operator, then restart it. These permissions were deliberately not
   requested or changed automatically.
3. Run `make ui-tars-start` and confirm `make ui-tars-status` reports
   `deerflow_is_only_brain: true`, `max_steps_per_call: 1`, the expected model
   id, healthy source and both desktop permissions.
4. In a throwaway local window containing no secrets, first verify a reversible
   native action such as focus, scroll or non-submitting text. For web content,
   first exercise Browser Control and only then a DOM-inaccessible visual
   fallback. Confirm exactly one action occurs and inspect the private JSONL
   receipt plus pixelated evidence under `.deer-flow/ui-tars`.
5. Without executing a real irreversible action, confirm a publish-like test
   intent is rejected as `approval_required` when no matching structured
   confirmation exists. Any real publish/send/delete/settings/payment or paid
   model acceptance remains a separate human-approved exercise.
6. For non-macOS `connect` mode, separately audit the loopback operator against
   the same one-step, privacy, approval and receipt contract, then provide the
   same random `UI_TARS_OPERATOR_TOKEN` to it and the Gateway process.
