"""Server-validated domain contracts shared by both Personal-IP video modes.

The module is deliberately pure.  It does not schedule agents, choose a model,
persist workflow state or execute media.  It only converts authoring input into
canonical receipts that can be sealed in the existing append-only production
ledger.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

VIDEO_DOMAIN_CONTRACT_VERSION = "personal-ip-video-domain-v1"
VIDEO_PRODUCTION_MODES = frozenset({"faceless_material", "generative_cinematic"})
LEGACY_VIDEO_PRODUCTION_MODE = "faceless_material"


def normalize_production_mode(value: Any) -> str:
    mode = str(value or "").strip()
    if mode not in VIDEO_PRODUCTION_MODES:
        allowed = ", ".join(sorted(VIDEO_PRODUCTION_MODES))
        raise ValueError(f"production_mode must be one of: {allowed}")
    return mode


def resolve_video_production_mode(
    production: Mapping[str, Any],
    *,
    contract: Mapping[str, Any] | None = None,
) -> str:
    """Resolve a mode without rewriting an immutable legacy request.

    Productions created before ``production_mode`` became required have no
    mode in their request snapshot.  They remain editable as
    ``faceless_material`` unless a later compiled contract already carries an
    explicit mode.
    """

    source = production.get("source")
    if not isinstance(source, Mapping):
        source = production.get("source_json")
    candidates = (
        production.get("production_mode"),
        source.get("production_mode") if isinstance(source, Mapping) else None,
        contract.get("production_mode") if isinstance(contract, Mapping) else None,
    )
    for candidate in candidates:
        if candidate is not None and str(candidate).strip():
            return normalize_production_mode(candidate)
    return LEGACY_VIDEO_PRODUCTION_MODE


def _required_text(value: Any, *, field: str, limit: int = 4_000) -> str:
    text = " ".join(str(value or "").split())
    if not text or len(text) > limit:
        raise ValueError(f"{field} must contain 1 to {limit} characters")
    return text


def _snapshot(value: Any, *, field: str, expected: type) -> Any:
    if not isinstance(value, expected):
        kind = "object" if expected is dict else "array"
        raise ValueError(f"{field} must be an {kind}")
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be JSON serializable") from exc
    return json.loads(encoded)


def _strings(value: Any, *, field: str, required: bool = True, limit: int = 500) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be an array")
    result: list[str] = []
    seen: set[str] = set()
    for raw in value:
        item = _required_text(raw, field=field, limit=2_048)
        if item not in seen:
            seen.add(item)
            result.append(item)
    if required and not result:
        raise ValueError(f"{field} must contain at least one item")
    if len(result) > limit:
        raise ValueError(f"{field} may contain at most {limit} items")
    return result


def _positive_number(value: Any, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"{field} must be a positive number")
    return float(value)


def _positive_integer(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _optional_positive_number(value: Any, *, field: str) -> float | None:
    if value is None:
        return None
    return _positive_number(value, field=field)


def _non_negative_number(value: Any, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"{field} must be a non-negative number")
    return float(value)


def _identified_objects(
    value: Any,
    *,
    field: str,
    required_fields: Sequence[str],
    require_order: bool = False,
) -> list[dict[str, Any]]:
    items = _snapshot(value, field=field, expected=list)
    if not items:
        raise ValueError(f"{field} must contain at least one item")
    result: list[dict[str, Any]] = []
    ids: set[str] = set()
    orders: set[int] = set()
    for index, raw in enumerate(items):
        if not isinstance(raw, dict):
            raise ValueError(f"{field}[{index}] must be an object")
        item = dict(raw)
        item_id = _required_text(item.get("id"), field=f"{field}[{index}].id", limit=128)
        if item_id in ids:
            singular = field[:-1] if field.endswith("s") else field
            raise ValueError(f"duplicate {singular} id: {item_id}")
        ids.add(item_id)
        item["id"] = item_id
        for name in required_fields:
            item[name] = _required_text(item.get(name), field=f"{field}[{index}].{name}")
        if require_order:
            order = _positive_integer(item.get("order"), field=f"{field}[{index}].order")
            if order in orders:
                raise ValueError(f"duplicate {field} order: {order}")
            orders.add(order)
            item["order"] = order
        result.append(item)
    if require_order:
        result.sort(key=lambda item: item["order"])
    return result


def _seal(contract: dict[str, Any]) -> dict[str, Any]:
    normalized = _snapshot(contract, field="contract", expected=dict)
    canonical = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    normalized["sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return normalized


def validate_compiled_video_contract(
    payload: Mapping[str, Any],
    *,
    contract_version: str,
    production_id: str,
    production_mode: str | None = None,
) -> dict[str, Any]:
    """Verify a sealed contract rather than trusting a caller-supplied digest."""

    normalized = _snapshot(dict(payload), field="payload", expected=dict)
    digest = str(normalized.pop("sha256", "")).strip().lower()
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError("compiled video contract digest must be a 64-character hex sha256")
    if normalized.get("contract_version") != contract_version:
        raise ValueError(f"compiled video contract must use {contract_version}")
    if normalized.get("domain_contract_version") != VIDEO_DOMAIN_CONTRACT_VERSION:
        raise ValueError(f"compiled video contract must use {VIDEO_DOMAIN_CONTRACT_VERSION}")
    if normalized.get("production_id") != production_id:
        raise ValueError("compiled video contract production_id does not match the ledger")
    if production_mode is not None and normalized.get("production_mode") != normalize_production_mode(production_mode):
        raise ValueError("compiled video contract production_mode does not match the production request")
    validation = normalized.get("validation")
    if not isinstance(validation, dict) or validation.get("passed") is not True:
        raise ValueError("compiled video contract must contain a passed server validation receipt")
    canonical = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if digest != expected:
        raise ValueError("compiled video contract digest does not match its payload")
    return {**normalized, "sha256": digest}


def compile_video_plan(*, production_id: str, production_mode: str, plan: Mapping[str, Any]) -> dict[str, Any]:
    """Compile one mode-specific director/film plan into a canonical receipt."""

    production = _required_text(production_id, field="production_id", limit=128)
    mode = normalize_production_mode(production_mode)
    normalized = _snapshot(dict(plan), field="plan", expected=dict)
    for field in ("title", "objective", "target_audience"):
        normalized[field] = _required_text(normalized.get(field), field=f"plan.{field}")
    normalized["platforms"] = _strings(normalized.get("platforms"), field="plan.platforms")

    checks = ["common_intent", "target_audience", "delivery_platforms"]
    if mode == "faceless_material":
        normalized["argument"] = _required_text(normalized.get("argument"), field="plan.argument")
        normalized["narration_language"] = _required_text(normalized.get("narration_language"), field="plan.narration_language", limit=32)
        normalized["evidence_refs"] = _strings(normalized.get("evidence_refs"), field="plan.evidence_refs")
        if not isinstance(normalized.get("measurement_plan"), dict) or not normalized["measurement_plan"]:
            raise ValueError("plan.measurement_plan must be a non-empty object")
        checks.extend(["argument", "evidence_refs", "measurement_plan"])
    else:
        normalized["logline"] = _required_text(normalized.get("logline"), field="plan.logline")
        normalized["genre"] = _required_text(normalized.get("genre"), field="plan.genre", limit=128)
        normalized["characters"] = _identified_objects(
            normalized.get("characters"),
            field="characters",
            required_fields=("name", "description"),
        )
        normalized["locations"] = _identified_objects(
            normalized.get("locations"),
            field="locations",
            required_fields=("name", "description"),
        )
        normalized["narrative_beats"] = _identified_objects(
            normalized.get("narrative_beats"),
            field="narrative_beats",
            required_fields=("purpose",),
            require_order=True,
        )
        checks.extend(["logline", "characters", "locations", "narrative_beats"])

    return _seal(
        {
            "contract_version": "personal-ip-video-plan-v1",
            "domain_contract_version": VIDEO_DOMAIN_CONTRACT_VERSION,
            "production_id": production,
            "production_mode": mode,
            "plan": normalized,
            "validation": {"passed": True, "checks": checks},
        }
    )


def compile_asset_manifest(*, production_id: str, production_mode: str, assets: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Compile an immutable asset inventory with mode-specific rights gates."""

    production = _required_text(production_id, field="production_id", limit=128)
    mode = normalize_production_mode(production_mode)
    normalized = _identified_objects(list(assets), field="assets", required_fields=("type", "name"))
    for index, asset in enumerate(normalized):
        source_ref = asset.get("source_ref") or asset.get("reference_ref")
        asset["source_ref"] = _required_text(source_ref, field=f"assets[{index}].source_ref", limit=2_048)
        if asset.get("allowed_for_use") is not True:
            raise ValueError(f"assets[{index}].allowed_for_use must be true")
        asset["allowed_for_use"] = True
        if mode == "faceless_material":
            asset["license"] = _required_text(asset.get("license"), field=f"assets[{index}].license", limit=256)
        digest = asset.get("sha256")
        if digest is not None:
            digest_text = str(digest).strip().lower()
            if len(digest_text) != 64 or any(char not in "0123456789abcdef" for char in digest_text):
                raise ValueError(f"assets[{index}].sha256 must be a 64-character hex digest")
            asset["sha256"] = digest_text

    checks = ["unique_assets", "source_reference", "usage_rights"]
    if mode == "faceless_material":
        checks.append("license_provenance")
    return _seal(
        {
            "contract_version": "personal-ip-video-asset-manifest-v1",
            "domain_contract_version": VIDEO_DOMAIN_CONTRACT_VERSION,
            "production_id": production,
            "production_mode": mode,
            "assets": normalized,
            "validation": {"passed": True, "checks": checks},
        }
    )


def compile_storyboard(*, production_id: str, production_mode: str, shots: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Compile material-video or cinematic shots without creating a runtime."""

    production = _required_text(production_id, field="production_id", limit=128)
    mode = normalize_production_mode(production_mode)
    normalized = _identified_objects(list(shots), field="shots", required_fields=(), require_order=True)
    duration = 0.0
    for index, shot in enumerate(normalized):
        shot["duration_seconds"] = _positive_number(shot.get("duration_seconds"), field=f"shots[{index}].duration_seconds")
        duration += shot["duration_seconds"]
        if mode == "faceless_material":
            for field in ("narration_text", "visual_subject", "visual_query"):
                shot[field] = _required_text(shot.get(field), field=f"shots[{index}].{field}")
            strategy = str(shot.get("composition_strategy") or "").strip()
            if strategy not in {"full_bleed", "inset_card", "letterbox"}:
                raise ValueError(f"shots[{index}].composition_strategy must be full_bleed, inset_card or letterbox")
            shot["composition_strategy"] = strategy
            refs = _strings(shot.get("claim_evidence_refs"), field=f"shots[{index}].claim_evidence_refs", required=False)
            quotes = shot.get("claim_evidence_quotes")
            if not isinstance(quotes, dict):
                raise ValueError(f"shots[{index}].claim_evidence_quotes must be an object")
            normalized_quotes = {_required_text(key, field=f"shots[{index}].claim_evidence_quotes key", limit=2_048): _required_text(value, field=f"shots[{index}].claim_evidence_quotes value", limit=8_000) for key, value in quotes.items()}
            if set(normalized_quotes) != set(refs):
                raise ValueError(f"shots[{index}].claim_evidence_quotes must exactly cover claim_evidence_refs")
            shot["claim_evidence_refs"] = refs
            shot["claim_evidence_quotes"] = normalized_quotes
            shot["negative_conditions"] = _strings(shot.get("negative_conditions"), field=f"shots[{index}].negative_conditions", required=False)
            shot["pass_criteria"] = _strings(shot.get("pass_criteria"), field=f"shots[{index}].pass_criteria")
        else:
            for field in ("scene_id", "first_frame", "last_frame", "motion", "camera", "action"):
                shot[field] = _required_text(shot.get(field), field=f"shots[{index}].{field}")
            shot["preserve_elements"] = _strings(shot.get("preserve_elements"), field=f"shots[{index}].preserve_elements")
            shot["change_elements"] = _strings(shot.get("change_elements"), field=f"shots[{index}].change_elements")

    checks = ["unique_shots", "unique_order", "positive_duration"]
    checks.extend(["evidence_grounding", "composition_strategy", "pass_criteria"] if mode == "faceless_material" else ["frame_contract", "preserve_change_contract", "camera_action_contract"])
    return _seal(
        {
            "contract_version": "personal-ip-video-storyboard-v1",
            "domain_contract_version": VIDEO_DOMAIN_CONTRACT_VERSION,
            "production_id": production,
            "production_mode": mode,
            "duration_seconds": duration,
            "shots": normalized,
            "validation": {"passed": True, "checks": checks},
        }
    )


def _sha256_text(value: Any, *, field: str) -> str:
    digest = str(value or "").strip().lower()
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError(f"{field} must be a 64-character hex digest")
    return digest


def _media_ref(value: Any, *, field: str) -> str:
    return _required_text(value, field=field, limit=2_048)


def compile_narration_contract(
    *,
    production_id: str,
    storyboard: Mapping[str, Any],
    language: str,
    segments: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Keep exact spoken copy separate from timing, captions and direction."""

    production = _required_text(production_id, field="production_id", limit=128)
    board = validate_compiled_video_contract(
        storyboard,
        contract_version="personal-ip-video-storyboard-v1",
        production_id=production,
        production_mode="faceless_material",
    )
    shots = _as_contract_list(board.get("shots"), field="storyboard.shots")
    normalized_segments = _snapshot(list(segments), field="segments", expected=list)
    if len(normalized_segments) != len(shots) or not shots:
        raise ValueError("narration segments must map one-to-one to storyboard shots")
    timecode_markup = re.compile(
        r"(?im)^\s*(?:\[?\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d{1,3})?\]?\s*"
        r"(?:-->|[-–—至到])\s*\[?\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d{1,3})?\]?|"
        r"(?:镜头|分镜|时间码|开始时间|结束时间)\s*(?:[#：:]|\d))"
    )
    result: list[dict[str, Any]] = []
    spoken: list[str] = []
    for index, (raw_segment, shot) in enumerate(zip(normalized_segments, shots, strict=True)):
        if not isinstance(raw_segment, dict):
            raise ValueError(f"segments[{index}] must be an object")
        allowed = {"id", "text", "pronunciation_hints"}
        if not set(raw_segment).issubset(allowed):
            raise ValueError("narration segments cannot contain timing or shot metadata")
        segment_id = _required_text(raw_segment.get("id"), field=f"segments[{index}].id", limit=128)
        if segment_id != shot.get("id"):
            raise ValueError("narration segment ids must match storyboard shot ids in order")
        text = _required_text(raw_segment.get("text"), field=f"segments[{index}].text", limit=1_500)
        if text != str(shot.get("narration_text") or "").strip():
            raise ValueError("narration text drifted from the approved storyboard")
        if timecode_markup.search(text):
            raise ValueError("spoken narration contains timeline or shot-label metadata")
        hints = _strings(
            raw_segment.get("pronunciation_hints") or [],
            field=f"segments[{index}].pronunciation_hints",
            required=False,
        )
        result.append(
            {
                "id": segment_id,
                "text": text,
                "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "pronunciation_hints": hints,
            }
        )
        spoken.append(text)
    return _seal(
        {
            "contract_version": "personal-ip-video-narration-v1",
            "domain_contract_version": VIDEO_DOMAIN_CONTRACT_VERSION,
            "production_id": production,
            "production_mode": "faceless_material",
            "source_storyboard_sha256": board["sha256"],
            "language": _required_text(language, field="language", limit=32),
            "segments": result,
            "spoken_text": "".join(spoken),
            "validation": {
                "passed": True,
                "checks": ["one_to_one_shot_mapping", "spoken_copy_lock", "no_timeline_markup"],
            },
        }
    )


def _as_contract_list(value: Any, *, field: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"{field} must be a non-empty array of objects")
    return [dict(item) for item in value]


def _state_key(value: Mapping[str, Any], *, field: str) -> tuple[str, str, str]:
    return (
        _required_text(value.get("domain"), field=f"{field}.domain", limit=80),
        _required_text(value.get("subject_id"), field=f"{field}.subject_id", limit=128),
        _required_text(value.get("attribute"), field=f"{field}.attribute", limit=128),
    )


def _state_sha256(state: Mapping[tuple[str, str, str], str]) -> str:
    payload = [{"domain": key[0], "subject_id": key[1], "attribute": key[2], "value": state[key]} for key in sorted(state)]
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compile_continuity_ledger(
    *,
    production_id: str,
    storyboard: Mapping[str, Any],
    initial_facts: Sequence[Mapping[str, Any]],
    shot_states: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Compile planned shot deltas into a deterministic hash-chained ledger."""

    production = _required_text(production_id, field="production_id", limit=128)
    board = validate_compiled_video_contract(
        storyboard,
        contract_version="personal-ip-video-storyboard-v1",
        production_id=production,
        production_mode="generative_cinematic",
    )
    board_shots = _as_contract_list(board.get("shots"), field="storyboard.shots")
    expected = [(str(shot.get("id")), int(shot.get("order") or 0)) for shot in board_shots]

    state: dict[tuple[str, str, str], str] = {}
    normalized_facts: list[dict[str, str]] = []
    for index, fact in enumerate(initial_facts):
        if not isinstance(fact, Mapping):
            raise ValueError(f"initial_facts[{index}] must be an object")
        key = _state_key(fact, field=f"initial_facts[{index}]")
        if key in state:
            raise ValueError("duplicate continuity fact: " + "/".join(key))
        value = _required_text(fact.get("value"), field=f"initial_facts[{index}].value")
        state[key] = value
        normalized_facts.append({"domain": key[0], "subject_id": key[1], "attribute": key[2], "value": value})

    raw_states = _as_contract_list(list(shot_states), field="shot_states")
    actual = [
        (
            _required_text(item.get("shot_id"), field=f"shot_states[{index}].shot_id", limit=128),
            _positive_integer(item.get("order"), field=f"shot_states[{index}].order"),
        )
        for index, item in enumerate(raw_states)
    ]
    if actual != expected:
        raise ValueError("shot_states must cover storyboard shots in exact contiguous order")

    initial_hash = _state_sha256(state)
    entries: list[dict[str, Any]] = []
    for index, item in enumerate(raw_states):
        shot_id, order = actual[index]
        preserve = item.get("preserve")
        changes = item.get("changes")
        if not isinstance(preserve, list) or not isinstance(changes, list):
            raise ValueError(f"shot_states[{index}] preserve and changes must be arrays")
        preserve_keys: set[tuple[str, str, str]] = set()
        normalized_preserve: list[dict[str, str]] = []
        for preserve_index, fact in enumerate(preserve):
            if not isinstance(fact, Mapping):
                raise ValueError("continuity preserve facts must be objects")
            key = _state_key(fact, field=f"shot_states[{index}].preserve[{preserve_index}]")
            if key in preserve_keys:
                raise ValueError(f"shot {shot_id} preserve facts must be unique")
            preserve_keys.add(key)
            expected_value = _required_text(fact.get("value"), field=f"shot_states[{index}].preserve[{preserve_index}].value")
            if state.get(key) != expected_value:
                raise ValueError(f"shot {shot_id} preserves missing or drifted fact {'/'.join(key)}")
            normalized_preserve.append({"domain": key[0], "subject_id": key[1], "attribute": key[2], "value": expected_value})

        change_keys: set[tuple[str, str, str]] = set()
        normalized_changes: list[dict[str, Any]] = []
        before_hash = _state_sha256(state)
        next_state = dict(state)
        for change_index, change in enumerate(changes):
            if not isinstance(change, Mapping):
                raise ValueError("continuity changes must be objects")
            key = _state_key(change, field=f"shot_states[{index}].changes[{change_index}]")
            if key in change_keys:
                raise ValueError(f"shot {shot_id} continuity change targets must be unique")
            if key in preserve_keys:
                raise ValueError(f"shot {shot_id} changes a preserved fact {'/'.join(key)}")
            change_keys.add(key)
            before = _required_text(change.get("before"), field=f"shot_states[{index}].changes[{change_index}].before")
            if next_state.get(key) != before:
                raise ValueError(f"shot {shot_id} continuity mismatch for {'/'.join(key)}: expected {before!r}, got {next_state.get(key)!r}")
            raw_after = change.get("after")
            after = None if raw_after is None else _required_text(raw_after, field=f"shot_states[{index}].changes[{change_index}].after")
            if after is None:
                next_state.pop(key, None)
            else:
                next_state[key] = after
            normalized_changes.append(
                {
                    "domain": key[0],
                    "subject_id": key[1],
                    "attribute": key[2],
                    "before": before,
                    "after": after,
                }
            )
        after_hash = _state_sha256(next_state)
        entries.append(
            {
                "shot_id": shot_id,
                "order": order,
                "before_state_sha256": before_hash,
                "preserve": normalized_preserve,
                "changes": normalized_changes,
                "after_state_sha256": after_hash,
            }
        )
        state = next_state

    return _seal(
        {
            "contract_version": "personal-ip-video-continuity-v1",
            "domain_contract_version": VIDEO_DOMAIN_CONTRACT_VERSION,
            "production_id": production,
            "production_mode": "generative_cinematic",
            "source_storyboard_sha256": board["sha256"],
            "initial_facts": normalized_facts,
            "initial_state_sha256": initial_hash,
            "entries": entries,
            "final_state_sha256": _state_sha256(state),
            "validation": {
                "passed": True,
                "checks": ["shot_coverage", "preserve_change_disjoint", "before_after_hash_chain"],
            },
        }
    )


def _normalized_artifact(value: Any, *, field: str) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return {
        "ref": _media_ref(value.get("ref"), field=f"{field}.ref"),
        "sha256": _sha256_text(value.get("sha256"), field=f"{field}.sha256"),
    }


def compile_generated_shot_qa(
    *,
    production_id: str,
    production_mode: str,
    shot_id: str,
    candidate_id: str,
    artifact: Mapping[str, Any],
    anchor: Mapping[str, Any],
    policy: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    """Compute technical/temporal gates from executor evidence server-side."""

    production = _required_text(production_id, field="production_id", limit=128)
    mode = normalize_production_mode(production_mode)
    shot = _required_text(shot_id, field="shot_id", limit=128)
    candidate = _required_text(candidate_id, field="candidate_id", limit=128)
    normalized_policy = _snapshot(dict(policy), field="policy", expected=dict)
    normalized_evidence = _snapshot(dict(evidence), field="evidence", expected=dict)
    motion_expectation = str(normalized_policy.get("motion_expectation") or "unspecified").strip().lower()
    if motion_expectation not in {"unspecified", "static", "natural", "continuous"}:
        raise ValueError("policy.motion_expectation must be static, natural, continuous or unspecified")
    enforce_motion_cadence = normalized_policy.get("enforce_motion_cadence", False)
    if not isinstance(enforce_motion_cadence, bool):
        raise ValueError("policy.enforce_motion_cadence must be a boolean")
    numeric_policy = {
        "expected_width": _positive_integer(normalized_policy.get("expected_width"), field="policy.expected_width"),
        "expected_height": _positive_integer(normalized_policy.get("expected_height"), field="policy.expected_height"),
        "expected_fps": _positive_number(normalized_policy.get("expected_fps"), field="policy.expected_fps"),
        "expected_duration_seconds": _positive_number(normalized_policy.get("expected_duration_seconds"), field="policy.expected_duration_seconds"),
        "duration_tolerance_seconds": float(normalized_policy.get("duration_tolerance_seconds", 0.2)),
        "minimum_first_frame_ssim": float(normalized_policy.get("minimum_first_frame_ssim", 0.85)),
        "maximum_internal_cut_count": int(normalized_policy.get("maximum_internal_cut_count", 0)),
        "expected_audio_stream_count": int(normalized_policy.get("expected_audio_stream_count", 0)),
        "expected_decode_error_count": int(normalized_policy.get("expected_decode_error_count", 0)),
        "motion_expectation": motion_expectation,
        "enforce_motion_cadence": enforce_motion_cadence,
        "target_playback_fps": _optional_positive_number(
            normalized_policy.get("target_playback_fps"),
            field="policy.target_playback_fps",
        ),
        "minimum_motion_fps": _optional_positive_number(
            normalized_policy.get("minimum_motion_fps"),
            field="policy.minimum_motion_fps",
        ),
        "maximum_near_duplicate_ratio": (
            None
            if normalized_policy.get("maximum_near_duplicate_ratio") is None
            else _non_negative_number(
                normalized_policy.get("maximum_near_duplicate_ratio"),
                field="policy.maximum_near_duplicate_ratio",
            )
        ),
        "maximum_near_duplicate_run_seconds": (
            None
            if normalized_policy.get("maximum_near_duplicate_run_seconds") is None
            else _non_negative_number(
                normalized_policy.get("maximum_near_duplicate_run_seconds"),
                field="policy.maximum_near_duplicate_run_seconds",
            )
        ),
        "maximum_motion_delta_cv": (
            None
            if normalized_policy.get("maximum_motion_delta_cv") is None
            else _non_negative_number(
                normalized_policy.get("maximum_motion_delta_cv"),
                field="policy.maximum_motion_delta_cv",
            )
        ),
    }
    if numeric_policy["duration_tolerance_seconds"] < 0:
        raise ValueError("policy.duration_tolerance_seconds must be non-negative")
    if not 0 <= numeric_policy["minimum_first_frame_ssim"] <= 1:
        raise ValueError("policy.minimum_first_frame_ssim must be between 0 and 1")
    maximum_near_duplicate_ratio = numeric_policy["maximum_near_duplicate_ratio"]
    if maximum_near_duplicate_ratio is not None and maximum_near_duplicate_ratio > 1:
        raise ValueError("policy.maximum_near_duplicate_ratio must be at most 1")
    cuts = normalized_evidence.get("internal_cut_transitions")
    if not isinstance(cuts, list) or any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in cuts):
        raise ValueError("evidence.internal_cut_transitions must be an array of non-negative integers")
    review_artifacts = normalized_evidence.get("review_artifacts")
    if not isinstance(review_artifacts, list) or not review_artifacts:
        raise ValueError("evidence.review_artifacts must contain a contact sheet or frame evidence")
    normalized_evidence["review_artifacts"] = [_normalized_artifact(item, field=f"evidence.review_artifacts[{index}]") for index, item in enumerate(review_artifacts)]
    width = _positive_integer(normalized_evidence.get("width"), field="evidence.width")
    height = _positive_integer(normalized_evidence.get("height"), field="evidence.height")
    fps = _positive_number(normalized_evidence.get("fps"), field="evidence.fps")
    duration = _positive_number(normalized_evidence.get("duration_seconds"), field="evidence.duration_seconds")
    audio_count = int(normalized_evidence.get("audio_stream_count", -1))
    decode_errors = int(normalized_evidence.get("decode_error_count", -1))
    first_frame_ssim = float(normalized_evidence.get("first_frame_ssim", -1))
    if not 0 <= first_frame_ssim <= 1:
        raise ValueError("evidence.first_frame_ssim must be between 0 and 1")
    normalized_evidence.update(
        {
            "width": width,
            "height": height,
            "fps": fps,
            "duration_seconds": duration,
            "audio_stream_count": audio_count,
            "decode_error_count": decode_errors,
            "first_frame_ssim": first_frame_ssim,
            "internal_cut_transitions": cuts,
        }
    )
    raw_motion_cadence = normalized_evidence.get("motion_cadence")
    motion_available = isinstance(raw_motion_cadence, Mapping) and raw_motion_cadence.get("available") is True
    motion_cadence: dict[str, Any] = {"available": False}
    if motion_available:
        motion_cadence = _snapshot(dict(raw_motion_cadence), field="evidence.motion_cadence", expected=dict)
        classification = str(motion_cadence.get("classification") or "").strip()
        if classification not in {"static", "low_motion", "active_motion"}:
            raise ValueError("evidence.motion_cadence.classification is invalid")
        for field in (
            "near_duplicate_transition_ratio",
            "longest_near_duplicate_run_seconds",
            "motion_delta_cv",
        ):
            motion_cadence[field] = _non_negative_number(
                motion_cadence.get(field),
                field=f"evidence.motion_cadence.{field}",
            )
        if motion_cadence["near_duplicate_transition_ratio"] > 1:
            raise ValueError("evidence.motion_cadence.near_duplicate_transition_ratio must be at most 1")
        source_motion_fps = _positive_number(
            motion_cadence.get("source_fps"),
            field="evidence.motion_cadence.source_fps",
        )
        if abs(source_motion_fps - fps) >= 0.01:
            raise ValueError("evidence.motion_cadence.source_fps must match evidence.fps")
        motion_cadence["source_fps"] = source_motion_fps
        interpolation_recommended = motion_cadence.get("interpolation_recommended")
        if not isinstance(interpolation_recommended, bool):
            raise ValueError("evidence.motion_cadence.interpolation_recommended must be a boolean")
    normalized_evidence["motion_cadence"] = motion_cadence
    technical = (
        width == numeric_policy["expected_width"]
        and height == numeric_policy["expected_height"]
        and abs(fps - numeric_policy["expected_fps"]) < 0.01
        and abs(duration - numeric_policy["expected_duration_seconds"]) <= numeric_policy["duration_tolerance_seconds"]
        and audio_count == numeric_policy["expected_audio_stream_count"]
        and decode_errors == numeric_policy["expected_decode_error_count"]
    )
    anchor_passed = first_frame_ssim >= numeric_policy["minimum_first_frame_ssim"]
    cuts_passed = len(cuts) <= numeric_policy["maximum_internal_cut_count"]
    motion_passed = not enforce_motion_cadence
    if motion_available:
        motion_passed = True
        if motion_expectation == "continuous" and motion_cadence["classification"] == "static":
            motion_passed = False
        if numeric_policy["minimum_motion_fps"] is not None:
            motion_passed = motion_passed and fps >= numeric_policy["minimum_motion_fps"]
        if maximum_near_duplicate_ratio is not None:
            motion_passed = motion_passed and motion_cadence["near_duplicate_transition_ratio"] <= maximum_near_duplicate_ratio
        if numeric_policy["maximum_near_duplicate_run_seconds"] is not None:
            motion_passed = motion_passed and motion_cadence["longest_near_duplicate_run_seconds"] <= numeric_policy["maximum_near_duplicate_run_seconds"]
        if numeric_policy["maximum_motion_delta_cv"] is not None:
            motion_passed = motion_passed and motion_cadence["motion_delta_cv"] <= numeric_policy["maximum_motion_delta_cv"]
    passed = technical and anchor_passed and cuts_passed
    if enforce_motion_cadence:
        passed = passed and motion_passed
    interpolation_recommended = bool(motion_available and motion_cadence.get("interpolation_recommended"))
    return _seal(
        {
            "contract_version": "personal-ip-generated-shot-qa-v1",
            "domain_contract_version": VIDEO_DOMAIN_CONTRACT_VERSION,
            "production_id": production,
            "production_mode": mode,
            "shot_id": shot,
            "candidate_id": candidate,
            "artifact": _normalized_artifact(artifact, field="artifact"),
            "anchor": _normalized_artifact(anchor, field="anchor"),
            "policy": numeric_policy,
            "evidence": normalized_evidence,
            "gates": {
                "technical": technical,
                "first_frame_anchor": anchor_passed,
                "internal_cuts": cuts_passed,
                "motion_cadence": motion_passed,
            },
            "motion_cadence_enforced": enforce_motion_cadence,
            "interpolation_recommended": interpolation_recommended,
            "automated_gate_passed": passed,
            "candidate_eligible": passed,
            "validation": {
                "passed": True,
                "checks": [
                    "technical",
                    "first_frame_anchor",
                    "internal_cuts",
                    "motion_cadence",
                ],
            },
        }
    )


def compile_approved_assembly(
    *,
    production_id: str,
    production_mode: str,
    resolution: str,
    fps: int,
    clips: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Admit only exact selected and QA-passing candidate hashes to a timeline."""

    production = _required_text(production_id, field="production_id", limit=128)
    mode = normalize_production_mode(production_mode)
    resolution_text = _required_text(resolution, field="resolution", limit=32)
    if re.fullmatch(r"[1-9][0-9]*x[1-9][0-9]*", resolution_text) is None:
        raise ValueError("resolution must use WIDTHxHEIGHT")
    fps_value = _positive_integer(fps, field="fps")
    if fps_value > 120:
        raise ValueError("fps must be at most 120")
    raw_clips = _as_contract_list(list(clips), field="clips")
    normalized: list[dict[str, Any]] = []
    ids: set[str] = set()
    timeline: list[dict[str, Any]] = []
    elapsed = 0.0
    for index, clip in enumerate(raw_clips):
        order = _positive_integer(clip.get("order"), field=f"clips[{index}].order")
        if order != index + 1:
            raise ValueError("clip order must be contiguous and start at 1")
        shot_id = _required_text(clip.get("shot_id"), field=f"clips[{index}].shot_id", limit=128)
        if shot_id in ids:
            raise ValueError(f"duplicate assembly shot id: {shot_id}")
        ids.add(shot_id)
        candidate_id = _required_text(clip.get("candidate_id"), field=f"clips[{index}].candidate_id", limit=128)
        source_sha = _sha256_text(clip.get("source_sha256"), field=f"clips[{index}].source_sha256")
        selection_sha = _sha256_text(clip.get("selection_source_sha256"), field=f"clips[{index}].selection_source_sha256")
        if selection_sha != source_sha:
            raise ValueError(f"selected source hash does not match assembly source for shot {shot_id}")
        qa_sha = _sha256_text(clip.get("qa_source_sha256"), field=f"clips[{index}].qa_source_sha256")
        if qa_sha != source_sha:
            raise ValueError(f"QA source hash does not match assembly source for shot {shot_id}")
        if clip.get("qa_passed") is not True:
            raise ValueError(f"shot {shot_id} has no passing QA receipt")
        duration = _positive_number(clip.get("duration_seconds"), field=f"clips[{index}].duration_seconds")
        normalized_clip = {
            "order": order,
            "shot_id": shot_id,
            "candidate_id": candidate_id,
            "duration_seconds": duration,
            "source_ref": _media_ref(clip.get("source_ref"), field=f"clips[{index}].source_ref"),
            "source_sha256": source_sha,
            "selection_receipt_ref": _media_ref(clip.get("selection_receipt_ref"), field=f"clips[{index}].selection_receipt_ref"),
            "selection_source_sha256": selection_sha,
            "qa_receipt_ref": _media_ref(clip.get("qa_receipt_ref"), field=f"clips[{index}].qa_receipt_ref"),
            "qa_source_sha256": qa_sha,
            "qa_passed": True,
        }
        normalized.append(normalized_clip)
        timeline.append(
            {
                "order": order,
                "shot_id": shot_id,
                "timeline_start_seconds": elapsed,
                "duration_seconds": duration,
                "source_ref": normalized_clip["source_ref"],
                "source_sha256": source_sha,
            }
        )
        elapsed += duration
    return _seal(
        {
            "contract_version": "personal-ip-approved-assembly-v1",
            "domain_contract_version": VIDEO_DOMAIN_CONTRACT_VERSION,
            "production_id": production,
            "production_mode": mode,
            "resolution": resolution_text,
            "fps": fps_value,
            "transition_policy": "hard_cut",
            "clips": normalized,
            "timeline": timeline,
            "duration_seconds": elapsed,
            "validation": {
                "passed": True,
                "checks": ["contiguous_order", "selected_hash_match", "qa_hash_match", "qa_passed"],
            },
        }
    )


_TIMELINE_TRACK_TYPES = frozenset({"video", "dialogue", "music", "subtitle"})
_EDIT_OPERATION_TYPES = frozenset(
    {
        "move",
        "trim",
        "split",
        "delete",
        "duplicate",
        "replace_candidate",
        "change_volume",
        "edit_caption",
        "add_transition",
        "restore_revision",
    }
)


def compile_timeline_revision(
    *,
    production_id: str,
    production_mode: str,
    revision_id: str,
    base_revision_id: str | None,
    author_kind: str,
    intent: str,
    fps: int,
    tracks: Sequence[Mapping[str, Any]],
    operations: Sequence[Mapping[str, Any]],
    strategy_confirmed: bool,
) -> dict[str, Any]:
    """Seal one complete edit snapshot shared by human and agent operations.

    Pointer movement is deliberately absent from this contract. The workbench
    may keep a drag draft locally, but only the resulting decision and complete
    timeline snapshot enter the append-only production ledger.
    """

    production = _required_text(production_id, field="production_id", limit=128)
    mode = normalize_production_mode(production_mode)
    revision = _required_text(revision_id, field="revision_id", limit=128)
    base_revision = _required_text(base_revision_id, field="base_revision_id", limit=128) if base_revision_id is not None and str(base_revision_id).strip() else None
    author = str(author_kind or "").strip()
    if author not in {"human", "agent"}:
        raise ValueError("author_kind must be human or agent")
    if strategy_confirmed is not True:
        raise ValueError("strategy_confirmed must be true before an edit revision is sealed")
    fps_value = _positive_integer(fps, field="fps")
    if fps_value > 120:
        raise ValueError("fps must be at most 120")

    raw_tracks = _snapshot(list(tracks), field="tracks", expected=list)
    if not raw_tracks:
        raise ValueError("tracks must contain at least one timeline track")
    normalized_tracks: list[dict[str, Any]] = []
    track_ids: set[str] = set()
    clip_ids: set[str] = set()
    duration_seconds = 0.0
    for track_index, raw_track in enumerate(raw_tracks):
        if not isinstance(raw_track, dict):
            raise ValueError(f"tracks[{track_index}] must be an object")
        track_id = _required_text(raw_track.get("id"), field=f"tracks[{track_index}].id", limit=128)
        if track_id in track_ids:
            raise ValueError(f"duplicate timeline track id: {track_id}")
        track_ids.add(track_id)
        track_type = str(raw_track.get("type") or "").strip().lower()
        if track_type not in _TIMELINE_TRACK_TYPES:
            allowed = ", ".join(sorted(_TIMELINE_TRACK_TYPES))
            raise ValueError(f"tracks[{track_index}].type must be one of: {allowed}")
        raw_clips = raw_track.get("clips")
        if not isinstance(raw_clips, list):
            raise ValueError(f"tracks[{track_index}].clips must be an array")
        normalized_clips: list[dict[str, Any]] = []
        for clip_index, raw_clip in enumerate(raw_clips):
            if not isinstance(raw_clip, dict):
                raise ValueError(f"tracks[{track_index}].clips[{clip_index}] must be an object")
            clip_field = f"tracks[{track_index}].clips[{clip_index}]"
            clip_id = _required_text(raw_clip.get("id"), field=f"{clip_field}.id", limit=128)
            if clip_id in clip_ids:
                raise ValueError(f"duplicate timeline clip id: {clip_id}")
            clip_ids.add(clip_id)
            start = _non_negative_number(raw_clip.get("start_sec"), field=f"{clip_field}.start_sec")
            duration = _positive_number(raw_clip.get("duration_sec"), field=f"{clip_field}.duration_sec")
            source_in = _non_negative_number(raw_clip.get("source_in_sec", 0), field=f"{clip_field}.source_in_sec")
            normalized_clip: dict[str, Any] = {
                "id": clip_id,
                "shot_id": str(raw_clip.get("shot_id") or "").strip() or None,
                "start_sec": round(start, 3),
                "duration_sec": round(duration, 3),
                "source_in_sec": round(source_in, 3),
                "selected_candidate_id": str(raw_clip.get("selected_candidate_id") or "").strip() or None,
                "source_ref": str(raw_clip.get("source_ref") or "").strip() or None,
                "source_sha256": None,
                "text": str(raw_clip.get("text") or "").strip() or None,
                "volume": float(raw_clip.get("volume", 1)),
                "transition": str(raw_clip.get("transition") or "none").strip(),
            }
            if normalized_clip["volume"] < 0 or normalized_clip["volume"] > 4:
                raise ValueError(f"{clip_field}.volume must be between 0 and 4")
            source_sha = raw_clip.get("source_sha256")
            if source_sha is not None and str(source_sha).strip():
                normalized_clip["source_sha256"] = _sha256_text(source_sha, field=f"{clip_field}.source_sha256")
            if track_type == "subtitle" and not normalized_clip["text"]:
                raise ValueError(f"{clip_field}.text is required for subtitle clips")
            if normalized_clip["transition"] not in {"none", "hard_cut", "crossfade", "dip_to_black"}:
                raise ValueError(f"{clip_field}.transition is unsupported")
            normalized_clips.append(normalized_clip)
            duration_seconds = max(duration_seconds, start + duration)
        normalized_clips.sort(key=lambda item: (item["start_sec"], item["id"]))
        normalized_tracks.append({"id": track_id, "type": track_type, "clips": normalized_clips})

    raw_operations = _snapshot(list(operations), field="operations", expected=list)
    if not raw_operations:
        raise ValueError("operations must record at least one edit decision")
    normalized_operations: list[dict[str, Any]] = []
    operation_ids: set[str] = set()
    for index, raw_operation in enumerate(raw_operations):
        if not isinstance(raw_operation, dict):
            raise ValueError(f"operations[{index}] must be an object")
        operation = dict(raw_operation)
        operation_id = _required_text(operation.get("id"), field=f"operations[{index}].id", limit=128)
        if operation_id in operation_ids:
            raise ValueError(f"duplicate edit operation id: {operation_id}")
        operation_ids.add(operation_id)
        operation_type = str(operation.get("type") or "").strip()
        if operation_type not in _EDIT_OPERATION_TYPES:
            allowed = ", ".join(sorted(_EDIT_OPERATION_TYPES))
            raise ValueError(f"operations[{index}].type must be one of: {allowed}")
        clip_id = str(operation.get("clip_id") or "").strip() or None
        if operation_type != "restore_revision" and not clip_id:
            raise ValueError(f"operations[{index}].clip_id is required")
        if operation_type == "move":
            _required_text(operation.get("track_id"), field=f"operations[{index}].track_id", limit=128)
            _non_negative_number(operation.get("start_sec"), field=f"operations[{index}].start_sec")
        elif operation_type == "trim":
            _non_negative_number(operation.get("source_in_sec"), field=f"operations[{index}].source_in_sec")
            _positive_number(operation.get("duration_sec"), field=f"operations[{index}].duration_sec")
        elif operation_type == "split":
            _positive_number(operation.get("at_sec"), field=f"operations[{index}].at_sec")
        elif operation_type == "duplicate":
            _required_text(operation.get("new_clip_id"), field=f"operations[{index}].new_clip_id", limit=128)
        elif operation_type == "replace_candidate":
            _required_text(operation.get("candidate_id"), field=f"operations[{index}].candidate_id", limit=128)
        elif operation_type == "change_volume":
            volume = float(operation.get("volume", -1))
            if volume < 0 or volume > 4:
                raise ValueError(f"operations[{index}].volume must be between 0 and 4")
        elif operation_type == "edit_caption":
            _required_text(operation.get("text"), field=f"operations[{index}].text", limit=8_000)
        elif operation_type == "add_transition":
            transition = str(operation.get("transition") or "").strip()
            if transition not in {"none", "hard_cut", "crossfade", "dip_to_black"}:
                raise ValueError(f"operations[{index}].transition is unsupported")
        elif operation_type == "restore_revision":
            _required_text(operation.get("revision_id"), field=f"operations[{index}].revision_id", limit=128)
        operation["id"] = operation_id
        operation["type"] = operation_type
        operation["clip_id"] = clip_id
        normalized_operations.append(operation)

    return _seal(
        {
            "contract_version": "personal-ip-video-timeline-revision-v1",
            "domain_contract_version": VIDEO_DOMAIN_CONTRACT_VERSION,
            "production_id": production,
            "production_mode": mode,
            "revision_id": revision,
            "base_revision_id": base_revision,
            "author_kind": author,
            "intent": _required_text(intent, field="intent", limit=8_000),
            "strategy_confirmed": True,
            "rough_cut": True,
            "fps": fps_value,
            "duration_seconds": round(duration_seconds, 3),
            "tracks": normalized_tracks,
            "operations": normalized_operations,
            "editing_policy": {
                "word_boundary_cuts": True,
                "cut_edge_padding_ms": {"minimum": 30, "maximum": 200},
                "audio_boundary_fade_ms": 30,
                "overlay_pts_shift_required": True,
                "subtitle_offsets_use_output_timeline": True,
                "subtitles_applied_last": True,
                "post_render_self_qa_required": True,
            },
            "validation": {
                "passed": True,
                "checks": [
                    "unique_tracks_and_clips",
                    "positive_clip_durations",
                    "complete_timeline_snapshot",
                    "strategy_confirmed",
                    "human_agent_shared_operations",
                    "video_use_finishing_policy",
                ],
            },
        }
    )


def compile_final_edit_lock(
    *,
    production_id: str,
    production_mode: str,
    lock_id: str,
    timeline_revision: Mapping[str, Any],
    locked_by: str,
    note: str,
) -> dict[str, Any]:
    """Lock the latest editable rough cut as the intentional QA input."""

    production = _required_text(production_id, field="production_id", limit=128)
    mode = normalize_production_mode(production_mode)
    revision = validate_compiled_video_contract(
        timeline_revision,
        contract_version="personal-ip-video-timeline-revision-v1",
        production_id=production,
        production_mode=mode,
    )
    actor = str(locked_by or "").strip()
    if actor not in {"human", "agent"}:
        raise ValueError("locked_by must be human or agent")
    if revision.get("rough_cut") is not True:
        raise ValueError("final edit lock requires an editable rough-cut revision")
    return _seal(
        {
            "contract_version": "personal-ip-video-final-edit-lock-v1",
            "domain_contract_version": VIDEO_DOMAIN_CONTRACT_VERSION,
            "production_id": production,
            "production_mode": mode,
            "lock_id": _required_text(lock_id, field="lock_id", limit=128),
            "locked_by": actor,
            "note": _required_text(note, field="note", limit=8_000),
            "source_revision_id": revision["revision_id"],
            "source_timeline_sha256": revision["sha256"],
            "fps": revision["fps"],
            "duration_seconds": revision["duration_seconds"],
            "track_count": len(revision["tracks"]),
            "rough_cut": False,
            "ready_for_delivery_qa": True,
            "validation": {
                "passed": True,
                "checks": [
                    "latest_timeline_identity",
                    "intentional_edit_lock",
                    "delivery_qa_input_frozen",
                ],
            },
        }
    )


def compile_narration_timing(
    *,
    production_id: str,
    narration: Mapping[str, Any],
    segments: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Reconcile exact narration text with measured TTS execution receipts."""

    production = _required_text(production_id, field="production_id", limit=128)
    narration_contract = validate_compiled_video_contract(
        narration,
        contract_version="personal-ip-video-narration-v1",
        production_id=production,
        production_mode="faceless_material",
    )
    expected_segments = _as_contract_list(narration_contract.get("segments"), field="narration.segments")
    raw_segments = _as_contract_list(list(segments), field="segments")
    if len(raw_segments) != len(expected_segments):
        raise ValueError("narration timing must cover every narration segment exactly once")
    normalized: list[dict[str, Any]] = []
    total_duration = 0.0
    for index, (raw, expected) in enumerate(zip(raw_segments, expected_segments, strict=True)):
        segment_id = _required_text(raw.get("id"), field=f"segments[{index}].id", limit=128)
        if segment_id != expected.get("id"):
            raise ValueError("narration timing segment ids must match narration order")
        text_sha = _sha256_text(raw.get("source_text_sha256"), field=f"segments[{index}].source_text_sha256")
        if text_sha != expected.get("text_sha256"):
            raise ValueError(f"narration source text hash mismatch for {segment_id}")
        characters = _positive_integer(raw.get("characters"), field=f"segments[{index}].characters")
        if characters != len(str(expected.get("text") or "")):
            raise ValueError(f"narration character count mismatch for {segment_id}")
        duration = _positive_number(raw.get("duration_seconds"), field=f"segments[{index}].duration_seconds")
        cost = _snapshot(raw.get("cost"), field=f"segments[{index}].cost", expected=dict)
        cost_status = str(cost.get("status") or "").strip()
        if cost_status not in {"known", "estimated", "unknown"}:
            raise ValueError(f"segments[{index}].cost.status must be known, estimated or unknown")
        if cost_status in {"known", "estimated"}:
            amount = cost.get("amount")
            if isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount < 0:
                raise ValueError(f"segments[{index}].cost.amount must be a non-negative number")
            cost["currency"] = _required_text(cost.get("currency"), field=f"segments[{index}].cost.currency", limit=16)
        normalized.append(
            {
                "id": segment_id,
                "source_text_sha256": text_sha,
                "characters": characters,
                "audio_ref": _media_ref(raw.get("audio_ref"), field=f"segments[{index}].audio_ref"),
                "audio_sha256": _sha256_text(raw.get("audio_sha256"), field=f"segments[{index}].audio_sha256"),
                "duration_seconds": duration,
                "provider": _required_text(raw.get("provider"), field=f"segments[{index}].provider", limit=80),
                "provider_task_id": _required_text(raw.get("provider_task_id"), field=f"segments[{index}].provider_task_id", limit=256),
                "cost": cost,
            }
        )
        total_duration += duration
    return _seal(
        {
            "contract_version": "personal-ip-video-narration-timing-v1",
            "domain_contract_version": VIDEO_DOMAIN_CONTRACT_VERSION,
            "production_id": production,
            "production_mode": "faceless_material",
            "source_narration_sha256": narration_contract["sha256"],
            "language": narration_contract.get("language"),
            "segments": normalized,
            "actual_duration_seconds": round(total_duration, 3),
            "validation": {
                "passed": True,
                "checks": ["text_hash_lock", "measured_audio", "provider_task_receipt", "cost_receipt"],
            },
        }
    )


def compile_material_selection(
    *,
    production_id: str,
    asset_manifest: Mapping[str, Any],
    storyboard: Mapping[str, Any],
    selections: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Lock frame-grounded, rights-cleared source ranges one-to-one to shots."""

    production = _required_text(production_id, field="production_id", limit=128)
    assets_contract = validate_compiled_video_contract(
        asset_manifest,
        contract_version="personal-ip-video-asset-manifest-v1",
        production_id=production,
        production_mode="faceless_material",
    )
    storyboard_contract = validate_compiled_video_contract(
        storyboard,
        contract_version="personal-ip-video-storyboard-v1",
        production_id=production,
        production_mode="faceless_material",
    )
    assets = {str(asset.get("id")): asset for asset in _as_contract_list(assets_contract.get("assets"), field="asset_manifest.assets")}
    shots = _as_contract_list(storyboard_contract.get("shots"), field="storyboard.shots")
    raw_selections = _as_contract_list(list(selections), field="selections")
    if len(raw_selections) != len(shots):
        raise ValueError("material selection must map one-to-one to storyboard shots")
    normalized: list[dict[str, Any]] = []
    selected_asset_ids: list[str] = []
    for index, (raw, shot) in enumerate(zip(raw_selections, shots, strict=True)):
        shot_id = _required_text(raw.get("shot_id"), field=f"selections[{index}].shot_id", limit=128)
        if shot_id != shot.get("id"):
            raise ValueError("material selection shot ids must match storyboard order")
        asset_id = _required_text(raw.get("asset_id"), field=f"selections[{index}].asset_id", limit=128)
        asset = assets.get(asset_id)
        if asset is None:
            raise ValueError(f"material selection references unknown asset: {asset_id}")
        if asset.get("allowed_for_use") is not True or not str(asset.get("license") or "").strip():
            raise ValueError(f"material {asset_id} is not rights-authorized")
        source_in = float(raw.get("source_in_seconds", -1))
        source_out = float(raw.get("source_out_seconds", -1))
        if source_in < 0 or source_out <= source_in:
            raise ValueError(f"material source range is invalid for shot {shot_id}")
        source_duration = source_out - source_in
        if source_duration + 0.25 < float(shot.get("duration_seconds") or 0):
            raise ValueError(f"material source range is shorter than shot {shot_id}")
        relevance = float(raw.get("semantic_relevance", -1))
        if relevance < 0.72 or relevance > 1:
            raise ValueError(f"material semantic relevance must be between 0.72 and 1 for shot {shot_id}")
        normalized.append(
            {
                "shot_id": shot_id,
                "asset_id": asset_id,
                "source_ref": asset.get("source_ref"),
                "source_sha256": asset.get("sha256"),
                "license": asset.get("license"),
                "source_in_seconds": round(source_in, 3),
                "source_out_seconds": round(source_out, 3),
                "source_duration_seconds": round(source_duration, 3),
                "semantic_relevance": round(relevance, 4),
                "semantic_evidence": _required_text(raw.get("semantic_evidence"), field=f"selections[{index}].semantic_evidence", limit=8_000),
                "inspection_refs": _strings(raw.get("inspection_refs"), field=f"selections[{index}].inspection_refs"),
                "frame_evidence_refs": _strings(raw.get("frame_evidence_refs"), field=f"selections[{index}].frame_evidence_refs"),
            }
        )
        selected_asset_ids.append(asset_id)
    counts = {asset_id: selected_asset_ids.count(asset_id) for asset_id in set(selected_asset_ids)}
    if max(counts.values(), default=0) > 2:
        raise ValueError("one material may not be reused more than twice")
    if len(counts) * 2 < len(shots):
        raise ValueError("fewer than half the shots use independent material")
    return _seal(
        {
            "contract_version": "personal-ip-video-material-selection-v1",
            "domain_contract_version": VIDEO_DOMAIN_CONTRACT_VERSION,
            "production_id": production,
            "production_mode": "faceless_material",
            "source_asset_manifest_sha256": assets_contract["sha256"],
            "source_storyboard_sha256": storyboard_contract["sha256"],
            "selections": normalized,
            "independent_asset_count": len(counts),
            "validation": {
                "passed": True,
                "checks": ["one_to_one_shots", "rights", "exact_source_ranges", "frame_evidence", "material_diversity"],
            },
        }
    )


def compile_material_inspection(
    *,
    production_id: str,
    shot_id: str,
    asset_id: str,
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    """Seal mechanical, timestamp-grounded inspection before semantic selection."""

    production = _required_text(production_id, field="production_id", limit=128)
    shot = _required_text(shot_id, field="shot_id", limit=128)
    asset = _required_text(asset_id, field="asset_id", limit=128)
    normalized = _snapshot(dict(evidence), field="evidence", expected=dict)
    source = _normalized_artifact(normalized.get("source"), field="evidence.source")
    source_in = float(normalized.get("source_in_seconds", -1))
    source_out = float(normalized.get("source_out_seconds", -1))
    if source_in < 0 or source_out <= source_in:
        raise ValueError("material inspection source range is invalid")
    probe = normalized.get("probe")
    if not isinstance(probe, dict):
        raise ValueError("evidence.probe must be an object")
    duration = _positive_number(probe.get("duration_seconds"), field="evidence.probe.duration_seconds")
    if source_out > duration + 0.05:
        raise ValueError("material inspection range exceeds source duration")
    width = _positive_integer(probe.get("width"), field="evidence.probe.width")
    height = _positive_integer(probe.get("height"), field="evidence.probe.height")
    fps = _positive_number(probe.get("fps"), field="evidence.probe.fps")
    raw_frames = normalized.get("frames")
    if not isinstance(raw_frames, list) or len(raw_frames) < 2:
        raise ValueError("evidence.frames must contain at least two timestamped frames")
    frames: list[dict[str, Any]] = []
    previous = -1.0
    for index, raw in enumerate(raw_frames):
        if not isinstance(raw, Mapping):
            raise ValueError(f"evidence.frames[{index}] must be an object")
        timestamp = float(raw.get("timestamp_seconds", -1))
        if timestamp < source_in or timestamp > source_out or timestamp < previous:
            raise ValueError("material inspection frame timestamps must be ordered inside the source range")
        previous = timestamp
        frames.append(
            {
                "timestamp_seconds": round(timestamp, 3),
                "artifact": _normalized_artifact(
                    raw.get("artifact"),
                    field=f"evidence.frames[{index}].artifact",
                ),
            }
        )
    contact_sheet = _normalized_artifact(normalized.get("contact_sheet"), field="evidence.contact_sheet")
    report = _normalized_artifact(normalized.get("report"), field="evidence.report")
    return _seal(
        {
            "contract_version": "personal-ip-video-material-inspection-v1",
            "domain_contract_version": VIDEO_DOMAIN_CONTRACT_VERSION,
            "production_id": production,
            "production_mode": "faceless_material",
            "shot_id": shot,
            "asset_id": asset,
            "source": source,
            "source_in_seconds": round(source_in, 3),
            "source_out_seconds": round(source_out, 3),
            "probe": {
                "duration_seconds": duration,
                "width": width,
                "height": height,
                "fps": fps,
                "audio_stream_count": int(probe.get("audio_stream_count", 0)),
            },
            "frames": frames,
            "contact_sheet": contact_sheet,
            "report": report,
            "mechanical_only": True,
            "semantic_assessment_required": True,
            "validation": {
                "passed": True,
                "checks": [
                    "source_hash",
                    "source_range",
                    "timestamped_frames",
                    "contact_sheet",
                ],
            },
        }
    )
