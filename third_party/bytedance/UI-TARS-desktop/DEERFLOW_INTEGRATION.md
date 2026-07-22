# UI-TARS source boundary in DeerFlow

This directory preserves the selected upstream UI-TARS SDK, action parser,
shared contracts and NutJS operator source from commit
`c2ad42e3eb9b27830db41a3e6f51ca7179d9b168` under Apache-2.0.

DeerFlow does not launch Agent TARS or the upstream `GUIAgent` task loop. The
lead agent remains the only planner and invokes one bounded desktop step at a
time through `ui_tars_desktop_step`.

The upstream NutJS package manifest names platform `libnut` packages that ship
native artifacts. They are retained as source provenance but are deliberately
not installed by this distribution. The managed macOS operator instead uses
the operating system's `screencapture`, Accessibility and AppleScript surfaces;
no precompiled UI-TARS/libnut binary is checked in or downloaded. Other
platforms may use `mode: connect` with an independently audited local operator.

The DeerFlow adapter lives under
`backend/packages/harness/deerflow/community/ui_tars`. It ports the upstream
single-action format and normalized coordinate contract, applies local
whole-screen pixelation before any model request, keeps raw screenshots and
credentials out of model/log receipts, and writes only privacy-transformed
evidence locally.
