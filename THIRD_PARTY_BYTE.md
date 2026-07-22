# ByteDance and Volcengine components

This distribution is based on ByteDance DeerFlow and retains its MIT license.

The directories `skills/public/byted-mediakit-*` come from
`volcengine/mediakit-cli` at commit
`279e5bb97e97c6875ae2c6891c2c3fa9a43f39c0`. Each directory retains the
upstream MIT `LICENSE`. Their `permissions: [shell]` frontmatter is translated
to DeerFlow's equivalent `allowed-tools: [bash]`; the skill bodies and command
contracts are otherwise unchanged.

The complete MediaKit Go source is vendored at
`third_party/volcengine/mediakit-cli` from the same commit. Its upstream
prebuilt macOS arm64 `mediakit` file is intentionally omitted. This product
builds a platform-local executable into `.deer-flow/bin` with
`scripts/mediakit_source.py`.

For reproducible local builds, `scripts/install_go_toolchain.py` pins official
Go `1.26.5` archives and SHA-256 values for macOS, Linux and Windows on amd64
and arm64. The downloaded compiler lives under ignored `.deer-flow/toolchains`
and is not redistributed in Git.

`scripts/install_ffmpeg_toolchain.py` pins the official FFmpeg repository tag
`n8.1.2` and its archive SHA-256. The source is downloaded with retry/resume,
then built into the project-local toolchain with the subtitle shaping chain,
OpenH264 and macOS VideoToolbox enabled. GPL and non-free configure modes are
not enabled. The customer installer may bundle the verified source archive and
compiled platform artifact; neither is treated as opaque application logic.

The distribution calls commercial Volcengine APIs when their credentials are
configured. Open-source licenses do not include API usage; billing and service
terms are governed by Volcengine.

The complete ByteDance HLLM source is vendored at
`third_party/bytedance/HLLM` at commit
`864f17221c04a2d3082d9a072df00616bc7e6dab` under Apache-2.0. The upstream
model code is retained intact. `deerflow.personal_ip.hllm_creator` only adapts
aggregate Personal-IP history to HLLM-Creator's existing parquet contract and
verifies the source pin. HLLM's published weights are separate model assets;
the HLLM-Creator directory alone is 75.8 GB and is not silently downloaded by
the ordinary DeerFlow installer. TinyLlama and Qwen base-weight terms still
apply when those weights are selected.

The selected ByteDance UI-TARS desktop SDK, action parser, shared contracts and
NutJS operator source are vendored at
`third_party/bytedance/UI-TARS-desktop` from commit
`c2ad42e3eb9b27830db41a3e6f51ca7179d9b168`, package version `1.2.3`, under
Apache-2.0. Their tree digest is fixed by `VENDORED_VERSION.json`. DeerFlow does
not include or start Agent TARS. The upstream package manifest's precompiled
libnut dependencies are deliberately not installed: the managed macOS adapter
uses local operating-system desktop APIs and performs one UI-TARS action per
DeerFlow tool call. No UI-TARS binary is redistributed.
