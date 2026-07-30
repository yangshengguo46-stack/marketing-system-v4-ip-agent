# Parser routing

Prefer the smallest commercially usable stack that produces timestamped
evidence.

| Need | First choice | Optional local model | Boundary |
|---|---|---|---|
| Metadata, cuts, ASR, OCR | ByteDance MediaKit | none | CLI/source is bundled; deeper cloud analysis needs a separate MediaKit key |
| Story arc and highlights | MediaKit storyline/highlights | Marlin-2B | Preserve coverage and timestamps |
| Detailed visual descriptions | MediaKit + vision model | ByteDance Tarsier2 | No audio understanding |
| Audio-visual understanding | MediaKit ASR + visual output | ByteDance video-SALMONN 2+ | Run as an optional model service |
| Multi-shot narration and transitions | MediaKit stack | ByteDance Shot2Story | Do not import its noncommercial dataset annotations |
| Temporal evidence verification | Existing timestamps | VideoMind | Use as verifier, not source of business truth |

Vidi2.5 and Vidi-Edit are architectural references only in this product route.
Their published repository is noncommercial and does not provide a
production-ready open Vidi-Edit implementation. Do not vendor their code or
weights.

Every optional model must sit behind a provider adapter. MediaKit remains the
fallback so the Skill compiler works without downloading large weights.
