# IP Agent — ByteDance/Volcengine-first DeerFlow distribution

This distribution keeps DeerFlow as the local agent runtime and uses the
ByteDance/Volcengine stack as its default capability layer.

## What is already wired

- Doubao reasoning and vision through DeerFlow's Volcengine provider.
- Seedream image generation and reference editing.
- Seedance video generation with first-frame or multi-image references.
- Doubao Speech through the existing podcast/TTS pipeline.
- The five official AI MediaKit Skills for editing, video understanding,
  image processing and audio processing.
- HLLM-Creator's complete source plus a privacy-bounded adapter for aggregate
  audience history, personalized creative generation and later shared-model
  fine-tuning.
- A default `ip-agent` with portfolio-wide coordination, approval and receipt
  rules.

UI-TARS and MineContext remain optional local connectors. AgentKit is not used
as the runtime because it duplicates DeerFlow in the cloud. Data Agent is not
part of the distribution.

## First run

```bash
cp .env.example .env
make setup
make ip-init
make install
make dev
```

Choose Volcengine in the setup wizard and place your Ark API key in
`VOLCENGINE_API_KEY`.

To build the pinned AI MediaKit CLI source used by the bundled Skills:

```bash
make volcengine-install
make volcengine-doctor
```

The repository contains the MediaKit Go source under
`third_party/volcengine/mediakit-cli`; the incompatible upstream arm64
executable is not used. The install target prepares two project-local source
builds without asking the customer to install them by hand:

- checksum-pinned Go builds MediaKit into `.deer-flow/bin`;
- checksum-pinned FFmpeg 8.1.2 builds into `.deer-flow/toolchains/ffmpeg` with
  libass, FreeType, Fontconfig, FriBidi, HarfBuzz, OpenH264 and VideoToolbox.

The FFmpeg downloader resumes interrupted transfers and uses the official
FFmpeg GitHub repository archive, avoiding a hard dependency on ffmpeg.org.
Both binary directories are added to the service PATH automatically. Cloud
MediaKit uses its own `MEDIAKIT_API_KEY`; without that key, trim, concat,
subtitle, mix and probe continue to run locally.

## Important environment variables

```dotenv
VOLCENGINE_API_KEY=
VOLCENGINE_IMAGE_MODEL=doubao-seedream-5-0-260128
VOLCENGINE_VIDEO_MODEL=doubao-seedance-2-0-260128
MEDIAKIT_API_KEY=
VOLCENGINE_TTS_APPID=
VOLCENGINE_TTS_ACCESS_TOKEN=
```

Generation URLs may expire, so outputs are downloaded immediately. Paid batch
generation and publishing are approval-gated by the default Agent policy.

HLLM-Creator is not installed into the Gateway Python environment. Its model
runtime is an optional, separately sized service because the official model
asset is large and the reproduction training configuration is multi-node GPU.
The full source is already present in the distribution; see
`docs/HLLM_CREATOR_INTEGRATION.md` before configuring weights or training. Run
`make hllm-doctor` to verify the source pin and required upstream files.

See `product/volcengine/capabilities.yaml` for the complete routing policy.
