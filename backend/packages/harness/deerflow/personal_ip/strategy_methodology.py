"""Private operating strategy contract for Personal-IP incubation.

The strategy is the sole subject-level source of truth. It requires person
evidence, commercial logic, real benchmarks, positioning alternatives, a
launch package and observed operating signals before scaling.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

PERSONAL_IP_STRATEGY_METHOD_VERSION = "personal-ip-strategy-v1"

STRATEGY_MODES = {"monetization_first", "influence_first"}
STRATEGY_STAGES = (
    "evidence_collecting",
    "person_model_draft",
    "business_model_draft",
    "benchmark_researching",
    "positioning_candidates",
    "launch_package_ready",
    "pilot_running",
    "commercial_signal_observed",
    "scaling",
)

_PERSON_MODEL_FIELDS = {
    "basic_facts",
    "history",
    "expertise_evidence",
    "values_boundaries",
    "media_presence",
    "capacity_constraints",
    "open_questions",
}
_BUSINESS_MODEL_FIELDS = {
    "primary_goal",
    "existing_assets",
    "buyer_segments",
    "paid_problems",
    "offer_options",
    "proof",
    "primary_monetization_path",
    "reserved_paths",
    "economics_constraints",
    "open_questions",
}
_BENCHMARK_ROLES = {"business_model", "content_system", "identity_expression"}
_VALIDATION_EVIDENCE_KINDS = {
    "metric_observation",
    "platform_observation",
    "retrospective",
    "publish_receipt",
    "commercial_signal",
    "audience_feedback",
}


def _json_object(value: Any, *, field: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    normalized = dict(value)
    _ensure_json_size(normalized, field=field)
    return normalized


def _json_list(value: Any, *, field: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{field} must be a list")
    normalized = list(value)
    _ensure_json_size(normalized, field=field)
    return normalized


def _ensure_json_size(value: Any, *, field: str, limit: int = 200_000) -> None:
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must contain JSON values") from exc
    if len(encoded.encode("utf-8")) > limit:
        raise ValueError(f"{field} exceeds {limit} bytes")


def _required_text(value: Any, *, field: str, limit: int = 1000) -> str:
    text = " ".join(str(value or "").split())
    if not text or len(text) > limit:
        raise ValueError(f"{field} must contain 1 to {limit} characters")
    return text


def _required_list(value: Any, *, field: str, minimum: int = 1, maximum: int = 100) -> list[Any]:
    items = _json_list(value, field=field)
    if not minimum <= len(items) <= maximum:
        raise ValueError(f"{field} must contain {minimum} to {maximum} items")
    return items


def normalize_evidence_refs(
    value: Sequence[Mapping[str, Any]],
    *,
    required: bool,
) -> list[dict[str, str]]:
    """Keep small credential-free references to immutable evidence."""

    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError("evidence_refs must be a list")
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for raw in value:
        if not isinstance(raw, Mapping):
            raise ValueError("each evidence reference must be an object")
        kind = _required_text(raw.get("kind"), field="evidence_refs.kind", limit=64)
        evidence_id = _required_text(raw.get("id"), field="evidence_refs.id", limit=128)
        key = (kind, evidence_id)
        if key in seen:
            continue
        seen.add(key)
        result.append({"kind": kind, "id": evidence_id})
    if required and not result:
        raise ValueError("at least one real evidence reference is required")
    if len(result) > 200:
        raise ValueError("evidence_refs may contain at most 200 items")
    return result


def strategy_stage_index(stage: str) -> int:
    try:
        return STRATEGY_STAGES.index(str(stage or "").strip())
    except ValueError as exc:
        raise ValueError("unsupported Personal-IP strategy stage") from exc


def validate_strategy_transition(previous_stage: str | None, target_stage: str) -> str:
    """Allow revisions in place or one deliberate forward step."""

    target = STRATEGY_STAGES[strategy_stage_index(target_stage)]
    if previous_stage is None:
        if target != STRATEGY_STAGES[0]:
            raise ValueError("the first strategy stage must be evidence_collecting")
        return target
    previous_index = strategy_stage_index(previous_stage)
    target_index = strategy_stage_index(target)
    if target_index not in {previous_index, previous_index + 1}:
        raise ValueError(f"next strategy stage must be {STRATEGY_STAGES[min(previous_index + 1, len(STRATEGY_STAGES) - 1)]}")
    return target


def _validate_person_model(model: dict[str, Any]) -> None:
    missing = sorted(_PERSON_MODEL_FIELDS - set(model))
    if missing:
        raise ValueError("person_model is missing: " + ", ".join(missing))
    basic = _json_object(model["basic_facts"], field="person_model.basic_facts")
    for field in ("age_context", "gender_context", "occupation", "location_context"):
        _required_text(basic.get(field), field=f"person_model.basic_facts.{field}")
    _required_list(model["history"], field="person_model.history")
    _required_list(model["expertise_evidence"], field="person_model.expertise_evidence")
    _required_list(model["values_boundaries"], field="person_model.values_boundaries")
    presence = _json_object(model["media_presence"], field="person_model.media_presence")
    _required_text(presence.get("photo_status"), field="person_model.media_presence.photo_status")
    _required_text(presence.get("voice_status"), field="person_model.media_presence.voice_status")
    _required_list(model["capacity_constraints"], field="person_model.capacity_constraints")
    _json_list(model["open_questions"], field="person_model.open_questions")


def _validate_business_model(model: dict[str, Any], *, mode: str) -> None:
    missing = sorted(_BUSINESS_MODEL_FIELDS - set(model))
    if missing:
        raise ValueError("business_model is missing: " + ", ".join(missing))
    for field in ("primary_goal",):
        _required_text(model.get(field), field=f"business_model.{field}")
    for field in (
        "existing_assets",
        "buyer_segments",
        "paid_problems",
        "offer_options",
        "proof",
        "reserved_paths",
        "economics_constraints",
    ):
        _required_list(model.get(field), field=f"business_model.{field}")
    path = _json_object(
        model.get("primary_monetization_path"),
        field="business_model.primary_monetization_path",
    )
    for field in ("buyer", "paid_problem", "offer", "conversion_path"):
        _required_text(path.get(field), field=f"business_model.primary_monetization_path.{field}")
    _json_list(model.get("open_questions"), field="business_model.open_questions")
    if mode == "influence_first" and not model.get("reserved_paths"):
        raise ValueError("influence_first still requires reserved monetization paths")


def _validate_benchmarks(research: dict[str, Any]) -> None:
    benchmarks = _required_list(
        research.get("benchmarks"),
        field="benchmark_research.benchmarks",
        minimum=3,
        maximum=100,
    )
    roles: set[str] = set()
    for index, raw in enumerate(benchmarks):
        item = _json_object(raw, field=f"benchmark_research.benchmarks[{index}]")
        for field in ("benchmark_id", "platform", "source_url", "role", "why_relevant"):
            _required_text(item.get(field), field=f"benchmark_research.benchmarks[{index}].{field}")
        role = str(item["role"]).strip()
        if role not in _BENCHMARK_ROLES:
            raise ValueError(f"benchmark_research.benchmarks[{index}].role is unsupported")
        roles.add(role)
        for field in ("observations", "borrow", "avoid"):
            _required_list(item.get(field), field=f"benchmark_research.benchmarks[{index}].{field}")
    if roles != _BENCHMARK_ROLES:
        raise ValueError("benchmark research must cover business_model, content_system and identity_expression")


def _validate_positioning(candidates: list[Any]) -> None:
    if not 2 <= len(candidates) <= 3:
        raise ValueError("positioning_candidates must contain 2 to 3 alternatives")
    ids: set[str] = set()
    for index, raw in enumerate(candidates):
        item = _json_object(raw, field=f"positioning_candidates[{index}]")
        for field in (
            "candidate_id",
            "working_title",
            "buyer",
            "problem",
            "promise",
            "difference",
            "monetization_path",
        ):
            _required_text(item.get(field), field=f"positioning_candidates[{index}].{field}")
        candidate_id = str(item["candidate_id"]).strip()
        if candidate_id in ids:
            raise ValueError("positioning candidate ids must be unique")
        ids.add(candidate_id)
        for field in ("proof", "content_pillars", "risks"):
            _required_list(item.get(field), field=f"positioning_candidates[{index}].{field}")


def _validate_launch_package(package: dict[str, Any], *, candidate_ids: set[str]) -> None:
    selected = _required_text(
        package.get("selected_candidate_id"),
        field="launch_package.selected_candidate_id",
    )
    if selected not in candidate_ids:
        raise ValueError("launch_package.selected_candidate_id must reference a positioning candidate")
    _required_list(package.get("name_options"), field="launch_package.name_options", minimum=3)
    _required_list(package.get("bio_options"), field="launch_package.bio_options", minimum=2)
    _required_list(package.get("handle_checks"), field="launch_package.handle_checks")
    _json_object(package.get("avatar_direction"), field="launch_package.avatar_direction")
    _required_list(package.get("pinned_content"), field="launch_package.pinned_content", minimum=3)
    _required_list(package.get("pilot_experiments"), field="launch_package.pilot_experiments", minimum=3)
    _required_text(package.get("conversion_path"), field="launch_package.conversion_path")
    _required_list(package.get("success_metrics"), field="launch_package.success_metrics")
    _required_list(package.get("adjustment_rules"), field="launch_package.adjustment_rules")


def validate_strategy_snapshot(
    *,
    stage: str,
    mode: str,
    person_model: dict[str, Any],
    business_model: dict[str, Any],
    benchmark_research: dict[str, Any],
    positioning_candidates: list[Any],
    launch_package: dict[str, Any],
    validation: dict[str, Any],
    evidence_refs: list[dict[str, str]],
) -> None:
    """Validate all prerequisites needed to enter the requested stage."""

    stage_index = strategy_stage_index(stage)
    if mode not in STRATEGY_MODES:
        raise ValueError("strategy mode must be monetization_first or influence_first")
    if stage_index >= strategy_stage_index("business_model_draft"):
        _validate_person_model(person_model)
    if stage_index >= strategy_stage_index("benchmark_researching"):
        _validate_business_model(business_model, mode=mode)
    if stage_index >= strategy_stage_index("positioning_candidates"):
        _validate_benchmarks(benchmark_research)
    if stage_index >= strategy_stage_index("launch_package_ready"):
        _validate_positioning(positioning_candidates)
        _validate_launch_package(
            launch_package,
            candidate_ids={str(item["candidate_id"]).strip() for item in positioning_candidates},
        )
    if stage_index >= strategy_stage_index("pilot_running"):
        _required_text(validation.get("pilot_started_at"), field="validation.pilot_started_at")
        _required_list(validation.get("experiment_ids"), field="validation.experiment_ids")
    if stage_index >= strategy_stage_index("commercial_signal_observed"):
        _required_list(validation.get("commercial_signals"), field="validation.commercial_signals")
        if not any(ref.get("kind") in _VALIDATION_EVIDENCE_KINDS for ref in evidence_refs):
            raise ValueError("commercial signals require observed platform or commercial evidence")
        decision = _json_object(validation.get("validation_decision"), field="validation.validation_decision")
        _required_text(decision.get("selected_candidate_id"), field="validation.validation_decision.selected_candidate_id")
        _required_text(decision.get("decision"), field="validation.validation_decision.decision")
        _required_list(decision.get("supporting_evidence"), field="validation.validation_decision.supporting_evidence")
