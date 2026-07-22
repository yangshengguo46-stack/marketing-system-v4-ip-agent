---
name: volcengine-stack
description: Route a task to the correct ByteDance or Volcengine capability. Use for model reasoning, image or video generation, speech, media understanding, editing, computer operation, knowledge, memory, or any request that says to use the ByteDance stack.
license: MIT
---

# Volcengine capability router

Use DeerFlow as the local harness. Select one ByteDance capability for each
stage; do not create a second planner around a media API.

## Routing table

| Need | Preferred capability | How to invoke |
| --- | --- | --- |
| Reasoning, writing, visual understanding, tool calling | Doubao Seed through Volcengine Ark | Use the configured DeerFlow chat model; do not make an ad-hoc HTTP call |
| Generate or edit an image, reference-based visual consistency | Seedream | Read and follow `image-generation` |
| Generate a video clip, first frame, multimodal references, native audio | Seedance | Read and follow `video-generation` |
| Voice-over or dialogue synthesis | Doubao Speech | Read and follow `podcast-generation`; preserve speaker and voice identifiers in the receipt |
| Cut, concatenate, subtitle, mix, mux, add overlays | AI MediaKit | Read `byted-mediakit-shared`, then `byted-mediakit-editing` |
| Video ASR/OCR, scene split, storyline, highlights, enhancement | AI MediaKit | Read `byted-mediakit-shared`, then `byted-mediakit-video` |
| Image OCR, cleanup, background removal, enhancement, quality scoring | AI MediaKit | Read `byted-mediakit-shared`, then `byted-mediakit-image` |
| Vocal separation or audio metadata | AI MediaKit | Read `byted-mediakit-shared`, then `byted-mediakit-audio` |
| Browser or desktop interaction | UI-TARS / Agent TARS | Use the configured MCP/tool only when present; otherwise report the missing connector |
| Local user context | MineContext | Use its configured connector only when present; never pretend it is connected |

## Operating rules

1. Prefer the official ByteDance Skill or CLI when one exists. Do not rewrite
   MediaKit behavior with raw FFmpeg or raw HTTP unless the official tool is
   unavailable and the user approves the fallback.
2. Ark generation and cloud MediaKit calls cost money. Before the first paid
   batch, show the number of calls/clips, target resolution and duration, then
   obtain approval. A single cheap preview may be proposed but is not silently
   submitted.
3. Keep deterministic editing local when possible. Use MediaKit cloud mode for
   AI-only capabilities or when local codec dependencies fail.
4. Preserve every provider task ID, model ID, source asset, output URL/path,
   retry, selected candidate and error in a receipt. Download expiring URLs
   immediately.
5. Never bypass moderation, face authorization, voice authorization or trusted
   asset requirements. For real-person generation, require scoped consent and
   use the provider's authorized asset path.

## Receipt

For Seedance, Seedream and speech, always pass `--receipt-file` to the project
script. For MediaKit and FFmpeg, execute the command through
`scripts/run_media_executor.py`; it captures task/request identifiers and
verifies every declared local output. Immediately submit the resulting JSON to
`personal_ip_ingest_media_execution`. Do not translate a human-readable success
string into a receipt.

For a synchronous local or cloud result, declare every expected output before
the `--` separator:

```bash
python /mnt/skills/public/volcengine-stack/scripts/run_media_executor.py \
  --input /mnt/user-data/workspace/source.mp4 \
  --output /mnt/user-data/outputs/final.mp4 \
  --receipt-file /mnt/user-data/outputs/final.receipt.json \
  --provider volcengine --executor mediakit-cli --job-kind final_mux \
  -- /mnt/.deer-flow/bin/mediakit-cli <official-command> <arguments>
```

For a cloud submission that only returns a task ID, use
`--status-mode running`, ingest that receipt, then query/download through a
second wrapped command and ingest the terminal receipt under a new event key.

Declare `--output-source` once per downloaded output so its credential-free
provider URL and download time survive ingestion. Use `--attempt` and
`--retry-of` for retries. Use `--resume` only with the same receipt identity and
declared input/output paths: the wrapper re-hashes every local input and output
and refuses to reuse failed, missing or changed artifacts. Record authoritative
charges with
`--cost-status known|estimated`, `--cost-amount` and `--cost-currency`; otherwise
leave cost `unknown` with an explicit reason.

The repository-level free acceptance is:

```bash
make video-e2e-local
make video-e2e-local  # verifies idempotent recovery
```

It uses simulated paid-generation results, the real local MediaKit/FFmpeg
toolchain, immutable receipts and `personal-ip-delivery-qa-v1`. To generate but
not execute the real paid commands, run `make video-e2e-paid-checkpoints`.

The receipt contract is:

```yaml
contract_version: personal-ip-media-execution-v1
provider: volcengine
capability: image_generation | video_generation | speech_generation | media_processing
executor: video-generation-skill
model: "doubao-seedance-2-0-260128"
task_id: "provider task id or null"
request_id: "provider request id or null"
status: running | succeeded | failed
started_at: "ISO-8601"
completed_at: "ISO-8601 or null while running"
inputs: []
parameters: {}
outputs:
  - ref: file:///absolute/output.mp4
    sha256: "..."
    size_bytes: 123
cost:
  status: unknown
  reason: provider billing API is not connected
```

Successful outputs must have a SHA-256 digest and byte size. Never invent a
cost; keep it unknown until an authoritative usage or billing source is
connected. Receipts must not contain prompts, cookies, tokens, passwords or
authorization headers.
