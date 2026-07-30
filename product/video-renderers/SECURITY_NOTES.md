# Renderer dependency security notes

`npm audit` on the pinned HyperFrames `0.7.57` tree currently reports:

- `GHSA-frvp-7c67-39w9` in the transitive Hono static server;
- `GHSA-xcpc-8h2w-3j85` in transitive `adm-zip`;
- `GHSA-f88m-g3jw-g9cj` in transitive `sharp`/libvips.

The renderer accepts only current-task files, never publishes its preview
server, and uses a fixed local project plus an explicit Chromium path. These
boundaries reduce exposure but do not erase the advisories. HyperFrames has no
non-drifting fix for the Hono and sharp findings at this pin, so every renderer
upgrade must repeat the source, license, deterministic-output and dependency
audit before changing `version-policy.json`.
