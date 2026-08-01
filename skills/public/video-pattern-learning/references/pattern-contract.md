# Video pattern contract

Use the native tool schema as authoritative. This reference highlights the
semantic boundary.

## Source

Required:

- `kind`: `benchmark`, `viral`, `owned`, `generated` or `published`
- `ref`, `title`, `platform`
- `usage_rights`: `analysis_only`, `user_owned`, `licensed` or `public_domain`

Optional: `observed_at`, `content_sha256`.

## Analysis receipts

Each receipt requires:

- stable `id`, `provider`, `ref`
- `capability`: `asr`, `chaptering`, `highlight_detection`,
  `metadata_probe`, `ocr`, `scene_segmentation`, `storyline`,
  `temporal_grounding` or `visual_captioning`
- a `coverage` object that says what was and was not observed
- optional SHA-256

## Segments

Segments must be ordered and non-overlapping. Each contains:

- `id`, `start_seconds`, `end_seconds`
- abstract `narrative_role`, `visual`, `camera`, `edit`, `caption`, `voice`,
  `audio`
- `evidence_refs` resolving to declared analysis receipts

Use “none observed” when a channel is intentionally absent. Do not substitute a
raw transcript for an abstract field.

## Grammars

Provide every domain: `narrative`, `visual`, `camera`, `editing`, `captions`,
`voice`, `audio`, `platform`. A domain may have an empty array, but at least one
rule must exist overall.

Each rule contains:

- unique `id`
- one concise, reusable `rule`
- `evidence_refs`
- `confidence` from 0 to 1

Also supply non-empty `reusable_variables` and `fixed_constraints`.

## Skill scopes

- `experimental`: no account ids
- `account`: one or more account ids
- `portable`: no account ids; portability remains a revisable method judgment

The compiler returns files, not an installed Skill. Installation must pass
through `skill_manage`.
