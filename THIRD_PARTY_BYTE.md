# ByteDance and Volcengine components

This distribution is based on ByteDance DeerFlow and retains its MIT license.

The directories `skills/public/byted-mediakit-*` come from
`volcengine/mediakit-cli` at commit
`279e5bb97e97c6875ae2c6891c2c3fa9a43f39c0`. Each directory retains the
upstream MIT `LICENSE`. Their `permissions: [shell]` frontmatter is translated
to DeerFlow's equivalent `allowed-tools: [bash]`; the skill bodies and command
contracts are otherwise unchanged.

The distribution calls commercial Volcengine APIs when their credentials are
configured. Open-source licenses do not include API usage; billing and service
terms are governed by Volcengine.
