# Vendored source

This directory contains source required to build the customer distribution
without relying on opaque runtime binaries.

## AI MediaKit CLI

- Upstream: `volcengine/mediakit-cli`
- Commit: `279e5bb97e97c6875ae2c6891c2c3fa9a43f39c0`
- License: MIT
- Local path: `third_party/volcengine/mediakit-cli`

The upstream repository tracked a prebuilt macOS arm64 file named `mediakit`.
It is intentionally excluded because this distribution builds the CLI from Go
source for the customer's own platform. Run `make mediakit-build`; the local
artifact is written to the ignored `.deer-flow/bin/` directory.

## FFmpeg toolchain

- Upstream: `FFmpeg/FFmpeg`
- Tag: `n8.1.2`
- License mode: LGPL; GPL and non-free configure modes are disabled
- Build script: `scripts/install_ffmpeg_toolchain.py`

Run `make ffmpeg-toolchain` to download the checksum-pinned official source,
resume interrupted downloads, install the declared macOS build dependencies
and produce `.deer-flow/toolchains/ffmpeg/bin/{ffmpeg,ffprobe}`. Customer
release bundles can include the verified download cache and compiled artifact,
so end users do not need to install FFmpeg manually.

## HLLM-Creator

- Upstream: `bytedance/HLLM`
- Commit: `864f17221c04a2d3082d9a072df00616bc7e6dab`
- License: Apache-2.0
- Local path: `third_party/bytedance/HLLM`

The full upstream source is included and checksum-pinned by
`VENDORED_VERSION.json`. The research model dependencies and weights are kept
out of DeerFlow's ordinary backend environment. See
`docs/HLLM_CREATOR_INTEGRATION.md` for the thin-adapter and model-service
boundary.

## UI-TARS desktop operator/SDK

- Upstream: `bytedance/UI-TARS-desktop`
- Commit: `c2ad42e3eb9b27830db41a3e6f51ca7179d9b168`
- Package versions: `1.2.3`
- License: Apache-2.0
- Local path: `third_party/bytedance/UI-TARS-desktop`

The selected SDK, action parser, shared types and NutJS operator source are
included and tree-digest pinned. Agent TARS and its orchestration runtime are
not included. The upstream precompiled libnut dependencies are not installed;
DeerFlow's managed macOS adapter uses system desktop APIs and keeps one-step
execution under the DeerFlow lead agent. Run `make ui-tars-install` to verify
the source and register the local source-only installation receipt.

## MineContext

- Upstream: `volcengine/MineContext`
- Commit: `171c7a9ea8091e326ddcf0f10718aa1b58c83c65`
- Git tree: `b185239b776e176ad25faf584050cf0c31226108`
- License: Apache-2.0
- Local path: `third_party/volcengine/MineContext`

The full official source is included. `VENDORED_VERSION.json` pins provenance
and `UPSTREAM_FILES.sha256` pins all 504 official blobs; the local NOTICE
records that upstream had no NOTICE
file at this commit. Run `make minecontext-verify` without installing anything,
or `make minecontext-install && make minecontext-doctor` to create and check an
isolated runtime from this source. No capture starts as part of verification,
installation, doctor, Gateway boot or package smoke testing.
