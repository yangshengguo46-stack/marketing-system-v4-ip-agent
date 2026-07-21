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
