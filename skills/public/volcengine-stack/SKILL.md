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

For every paid or externally visible operation, return or save:

```yaml
provider: volcengine
capability: seedream | seedance | doubao-speech | mediakit
model_or_tool: "..."
task_id: "..."
inputs: []
parameters: {}
status: succeeded | failed | cancelled
outputs: []
cost_note: "unknown until billing API is connected"
created_at: "ISO-8601"
```

Never invent a cost. Mark it unknown until an authoritative usage or billing
source is connected.
