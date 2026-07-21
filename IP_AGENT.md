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
- A default `ip-agent` with account-aware approval and receipt rules.

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

To install the official AI MediaKit CLI used by the bundled Skills:

```bash
make volcengine-install
```

Cloud MediaKit uses its own `MEDIAKIT_API_KEY`. Without that key, supported
editing commands can still fall back to local FFmpeg.

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

See `product/volcengine/capabilities.yaml` for the complete routing policy.
