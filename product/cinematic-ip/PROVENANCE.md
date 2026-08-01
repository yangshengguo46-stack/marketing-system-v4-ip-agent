# Cinematic Personal-IP method stack provenance

## Origin

This is first-party project material imported from the owner's
`cinematic-ip-skill-matrix` workspace at schema version `4.0.0` on 2026-07-30.
It is not a vendored agent runtime.

The import retains:

- 35 method packages and their OpenAI interface metadata;
- the 358-film, 393-creator/team and 304-mechanism SQLite research index;
- the eight-track, 96-module curriculum;
- compact source provenance and the evidence/rights registry.

Cached BFI/WGA pages, source-build scripts, old audits, standalone tests and the
duplicate top-level research datasets are not redistributed. The packaged
SQLite index contains compact factual metadata and original synthesis, not
cached page media or copied article prose.

## Product adaptations

- Removed both copies of the standalone `ip_os.py` runtime.
- Replaced local project/JSONL state with subject-level strategy versions,
  Personal-IP preflights, publication receipts, metrics and retrospectives.
- Made the curriculum CLI read-only by removing its completion-ledger writer.
- Kept platform accounts as concrete operation targets, never person or
  conversation authority.
- Added customer-output privacy rules so package names, paths, tool steps and
  internal routing remain private.
- Routed long-form video-to-method compilation to the existing timestamped,
  hash-sealed video-method pipeline.

## Verification

Run:

```bash
python3 -m pytest tests/test_ip_agent_skill_stack.py -q
python3 skills/public/run-cinematic-curriculum/scripts/curriculum_cli.py \
  show --track screenwriting --week 1
python3 skills/public/query-cinematic-library/scripts/query_library.py --help
```

The product test verifies the exact 35-package matrix, default-agent enablement,
research and curriculum counts, source hashes and the absence of a parallel
state writer.
