"""Evidence-bound differentiation thesis for people, brands, products and organizations.

The contract separates a strategic choice from its expression. A candidate has
to state who should choose the operated entity, what alternatives exist, which
proprietary truths support the choice and what the entity deliberately gives
up. A pilot additionally needs a repeatable dramatic engine, distinctive
encoding and falsifiable tests. Observed status promotion is enforced by the
persistence layer because only the repository can inspect sealed observations.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

PERSONAL_IP_DIFFERENTIATION_METHOD_VERSION = "ip-differentiation-thesis-v1"

DIFFERENTIATION_STATUSES = (
    "candidate",
    "pilot",
    "provisionally_adopted",
    "validated",
    "retired",
)

DIFFERENTIATION_ENTITY_TYPES = {
    "person",
    "brand",
    "product",
    "organization",
    "portfolio",
}

DIFFERENTIATION_OBSERVATION_TYPES = {
    "recognition",
    "trust",
    "intent",
    "adoption",
    "conversion",
    "economic",
    "extension",
}

DIFFERENTIATION_OBSERVATION_SOURCES = {
    "platform_metrics",
    "platform_observation",
    "retrospective",
    "audience_feedback",
    "user_research",
    "commercial_record",
    "product_telemetry",
}

_DOWNSTREAM_OBSERVATION_TYPES = {"intent", "adoption", "conversion", "economic"}
_UNSUPPORTED_CAUSAL_TERMS = ("多巴胺", "镜像神经元", "蔡格尼克")
_ABSOLUTE_OUTCOME_PHRASES = ("必爆", "一定会火", "一定能火", "保证完播", "保证涨粉")

_CANDIDATE_OBJECT_FIELDS = {
    "primary_entity",
    "decision_context",
    "proprietary_truth",
    "strategic_difference",
    "validation",
}
_PILOT_OBJECT_FIELDS = {
    "contrast_field",
    "dramatic_engine",
    "distinctive_encoding",
    "operating_fit",
}


def _ensure_json_size(value: Any, *, field: str, limit: int = 200_000) -> None:
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must contain JSON values") from exc
    if len(encoded.encode("utf-8")) > limit:
        raise ValueError(f"{field} exceeds {limit} bytes")


def _object(value: Any, *, field: str, required: bool = True) -> dict[str, Any]:
    if value is None and not required:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    result = dict(value)
    if required and not result:
        raise ValueError(f"{field} must not be empty")
    _ensure_json_size(result, field=field)
    return result


def _list(
    value: Any,
    *,
    field: str,
    minimum: int = 1,
    maximum: int = 100,
) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{field} must be a list")
    result = list(value)
    if not minimum <= len(result) <= maximum:
        raise ValueError(f"{field} must contain {minimum} to {maximum} items")
    _ensure_json_size(result, field=field)
    return result


def _text(value: Any, *, field: str, limit: int = 2000) -> str:
    result = " ".join(str(value or "").split())
    if not result or len(result) > limit:
        raise ValueError(f"{field} must contain 1 to {limit} characters")
    return result


def _behavioral_claim(value: Any, *, field: str) -> str:
    result = _text(value, field=field)
    if any(term in result for term in _UNSUPPORTED_CAUSAL_TERMS):
        raise ValueError(f"{field} must use observable behavior instead of unsupported causal shorthand")
    if any(phrase in result for phrase in _ABSOLUTE_OUTCOME_PHRASES):
        raise ValueError(f"{field} must be falsifiable and cannot guarantee a viral outcome")
    return result


def _required_text_list(value: Any, *, field: str, minimum: int = 1) -> list[str]:
    return [_text(item, field=f"{field}[{index}]") for index, item in enumerate(_list(value, field=field, minimum=minimum))]


def differentiation_status_index(status: str) -> int:
    key = str(status or "").strip()
    try:
        return DIFFERENTIATION_STATUSES.index(key)
    except ValueError as exc:
        raise ValueError("unsupported differentiation status") from exc


def validate_differentiation_transition(previous_status: str | None, target_status: str) -> str:
    """Allow an in-place revision, one forward step or explicit retirement."""

    target = DIFFERENTIATION_STATUSES[differentiation_status_index(target_status)]
    if previous_status is None:
        if target != "candidate":
            raise ValueError("the first differentiation status must be candidate")
        return target
    previous = DIFFERENTIATION_STATUSES[differentiation_status_index(previous_status)]
    if previous == "retired":
        if target != "retired":
            raise ValueError("a retired differentiation thesis cannot be reopened")
        return target
    if target == "retired":
        return target
    previous_index = differentiation_status_index(previous)
    target_index = differentiation_status_index(target)
    if target_index not in {previous_index, previous_index + 1}:
        next_status = DIFFERENTIATION_STATUSES[min(previous_index + 1, DIFFERENTIATION_STATUSES.index("validated"))]
        raise ValueError(f"next differentiation status must be {next_status} or retired")
    return target


def _validate_primary_entity(value: dict[str, Any]) -> None:
    entity_type = _text(value.get("entity_type"), field="primary_entity.entity_type", limit=32)
    if entity_type not in DIFFERENTIATION_ENTITY_TYPES:
        raise ValueError("primary_entity.entity_type is unsupported")
    _text(value.get("name"), field="primary_entity.name")
    _text(value.get("role"), field="primary_entity.role")


def _validate_decision_context(value: dict[str, Any]) -> None:
    _text(value.get("category"), field="decision_context.category")
    for field in (
        "target_publics",
        "jobs_to_be_done",
        "alternatives",
        "points_of_parity",
        "desired_influence",
        "desired_outcomes",
    ):
        _required_text_list(value.get(field), field=f"decision_context.{field}")
    _text(value.get("time_horizon"), field="decision_context.time_horizon")


def _validate_proprietary_truth(value: dict[str, Any]) -> None:
    for field in (
        "rare_capabilities",
        "mechanisms",
        "history",
        "relationships_access",
        "rights_assets",
    ):
        _required_text_list(value.get(field), field=f"proprietary_truth.{field}")
    _list(value.get("evidence_refs"), field="proprietary_truth.evidence_refs")


def _validate_strategic_difference(value: dict[str, Any]) -> None:
    for field in (
        "value_created",
        "meaning_created",
        "reason_to_choose",
        "relevance_hypothesis",
    ):
        _behavioral_claim(value.get(field), field=f"strategic_difference.{field}")
    for field in ("reason_to_believe", "sacrifice", "copy_requirements"):
        _required_text_list(value.get(field), field=f"strategic_difference.{field}")


def _validate_contrast_field(value: dict[str, Any]) -> None:
    for field in (
        "competitor_territories",
        "category_cliches",
        "anti_benchmarks",
        "distant_analogues",
    ):
        _required_text_list(value.get(field), field=f"contrast_field.{field}")
    _text(value.get("cultural_tension"), field="contrast_field.cultural_tension")


def _validate_dramatic_engine(value: dict[str, Any]) -> None:
    for field in (
        "protagonist",
        "public_desire",
        "counterforce",
        "recurring_choice",
        "cost_and_state_change",
        "relationship_engine",
        "world",
        "genre_emotional_promise",
        "point_of_view",
    ):
        _text(value.get(field), field=f"dramatic_engine.{field}")
    _required_text_list(value.get("event_generators"), field="dramatic_engine.event_generators", minimum=3)


def _validate_distinctive_encoding(value: dict[str, Any]) -> None:
    for field in (
        "verbal_signals",
        "visual_signals",
        "sonic_signals",
        "character_signals",
        "spatial_ritual_signals",
        "behavioral_product_signals",
        "invariants",
        "controlled_variables",
        "forbidden_combinations",
        "attribution_targets",
    ):
        _required_text_list(value.get(field), field=f"distinctive_encoding.{field}")


def _validate_operating_fit(value: dict[str, Any]) -> None:
    for field in (
        "capacity_constraints",
        "evidence_supply",
        "channel_constraints",
        "cost_risk",
        "extension_rules",
    ):
        _required_text_list(value.get(field), field=f"operating_fit.{field}")


def _validate_validation(value: dict[str, Any], *, status: str) -> None:
    _text(value.get("evidence_level"), field="validation.evidence_level")
    _list(value.get("observations"), field="validation.observations", minimum=0)
    _list(value.get("inferences"), field="validation.inferences", minimum=0)
    hypotheses = _required_text_list(value.get("hypotheses"), field="validation.hypotheses")
    for index, hypothesis in enumerate(hypotheses):
        _behavioral_claim(hypothesis, field=f"validation.hypotheses[{index}]")
    tests = _list(value.get("tests"), field="validation.tests")
    for index, raw in enumerate(tests):
        test = _object(raw, field=f"validation.tests[{index}]")
        for field in ("test_id", "observation_window", "success_signal"):
            _text(test.get(field), field=f"validation.tests[{index}].{field}")
        _behavioral_claim(test.get("prediction"), field=f"validation.tests[{index}].prediction")
        _behavioral_claim(
            test.get("failure_condition"),
            field=f"validation.tests[{index}].failure_condition",
        )
    _required_text_list(value.get("failure_conditions"), field="validation.failure_conditions")
    if status == "retired":
        _text(value.get("retirement_reason"), field="validation.retirement_reason")


def validate_differentiation_snapshot(
    *,
    status: str,
    primary_entity: Mapping[str, Any] | None,
    supporting_entities: Sequence[Mapping[str, Any]] | None,
    decision_context: Mapping[str, Any] | None,
    contrast_field: Mapping[str, Any] | None,
    proprietary_truth: Mapping[str, Any] | None,
    strategic_difference: Mapping[str, Any] | None,
    dramatic_engine: Mapping[str, Any] | None,
    distinctive_encoding: Mapping[str, Any] | None,
    operating_fit: Mapping[str, Any] | None,
    validation: Mapping[str, Any] | None,
    evidence_refs: Sequence[Mapping[str, Any]],
) -> None:
    """Validate the semantic completeness required for one thesis status."""

    status_key = DIFFERENTIATION_STATUSES[differentiation_status_index(status)]
    documents = {
        "primary_entity": primary_entity,
        "decision_context": decision_context,
        "contrast_field": contrast_field,
        "proprietary_truth": proprietary_truth,
        "strategic_difference": strategic_difference,
        "dramatic_engine": dramatic_engine,
        "distinctive_encoding": distinctive_encoding,
        "operating_fit": operating_fit,
        "validation": validation,
    }
    normalized = {field: _object(documents[field], field=field, required=field in _CANDIDATE_OBJECT_FIELDS) for field in documents}
    _validate_primary_entity(normalized["primary_entity"])
    _validate_decision_context(normalized["decision_context"])
    _validate_proprietary_truth(normalized["proprietary_truth"])
    _validate_strategic_difference(normalized["strategic_difference"])
    _validate_validation(normalized["validation"], status=status_key)

    supporting = _list(supporting_entities or [], field="supporting_entities", minimum=0)
    for index, raw in enumerate(supporting):
        entity = _object(raw, field=f"supporting_entities[{index}]")
        entity_type = _text(
            entity.get("entity_type"),
            field=f"supporting_entities[{index}].entity_type",
            limit=32,
        )
        if entity_type not in DIFFERENTIATION_ENTITY_TYPES:
            raise ValueError(f"supporting_entities[{index}].entity_type is unsupported")
        _text(entity.get("name"), field=f"supporting_entities[{index}].name")
        _text(entity.get("role"), field=f"supporting_entities[{index}].role")

    refs = _list(evidence_refs, field="evidence_refs")
    for index, raw in enumerate(refs):
        ref = _object(raw, field=f"evidence_refs[{index}]")
        _text(ref.get("kind"), field=f"evidence_refs[{index}].kind", limit=64)
        _text(ref.get("id"), field=f"evidence_refs[{index}].id", limit=128)

    if differentiation_status_index(status_key) >= differentiation_status_index("pilot") and status_key != "retired":
        for field in _PILOT_OBJECT_FIELDS:
            if not normalized[field]:
                raise ValueError(f"{field} is required before pilot")
        _validate_contrast_field(normalized["contrast_field"])
        _validate_dramatic_engine(normalized["dramatic_engine"])
        _validate_distinctive_encoding(normalized["distinctive_encoding"])
        _validate_operating_fit(normalized["operating_fit"])


def downstream_observation_types() -> frozenset[str]:
    """Return outcome types that prove influence progressed toward action."""

    return frozenset(_DOWNSTREAM_OBSERVATION_TYPES)
