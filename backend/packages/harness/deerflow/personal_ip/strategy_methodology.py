"""Private operating strategy contract for influence-asset incubation.

The strategy is the sole subject-level source of truth for a person, brand,
product or organization. Influence is the common asset-building mechanism;
behavioral and economic outcomes are explicit objective axes rather than an
alternative operating mode.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

PERSONAL_IP_STRATEGY_METHOD_VERSION = "personal-ip-strategy-v4"

# Retained only so existing rows and callers remain readable while the product
# migrates away from the old false either/or choice.
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
_NON_PERSON_MODEL_FIELDS = {
    "entity_type",
    "basic_facts",
    "history",
    "capability_evidence",
    "values_boundaries",
    "public_interfaces",
    "capacity_constraints",
    "stakeholders",
    "open_questions",
}
_BUSINESS_MODEL_FIELDS = {
    "primary_goal",
    "objective_system",
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
_OBJECTIVE_DOMAINS = {"influence", "behavioral", "economic"}
_BENCHMARK_ROLES = {"business_model", "content_system", "identity_expression"}
_PILOT_ROLES = {"reach", "trust", "proof", "conversion"}
_PILOT_EVIDENCE_LEVELS = {
    "general_prior",
    "market_referenced",
    "account_observed",
    "promoted_rule",
}
_PILOT_MECHANISM_LAYERS = {
    "processing_access",
    "attention_prediction",
    "emotion_identity",
    "narrative_consumption",
    "social_transmission",
    "behavior_conversion",
    "platform_distribution",
}
_UNSUPPORTED_CAUSAL_TERMS = ("多巴胺", "镜像神经元", "蔡格尼克")
_ABSOLUTE_OUTCOME_PHRASES = ("必爆", "一定会火", "一定能火", "保证完播", "保证涨粉")
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


def _validate_non_person_model(
    model: dict[str, Any],
    *,
    subject_type: str,
) -> None:
    missing = sorted(_NON_PERSON_MODEL_FIELDS - set(model))
    if missing:
        raise ValueError("subject_model is missing: " + ", ".join(missing))
    entity_type = _required_text(
        model.get("entity_type"),
        field="subject_model.entity_type",
        limit=32,
    )
    if entity_type != subject_type:
        raise ValueError("subject_model.entity_type must match the operated subject")
    basic = _json_object(model["basic_facts"], field="subject_model.basic_facts")
    for field in ("category", "lifecycle_stage", "operating_context"):
        _required_text(
            basic.get(field),
            field=f"subject_model.basic_facts.{field}",
        )
    for field in (
        "history",
        "capability_evidence",
        "values_boundaries",
        "public_interfaces",
        "capacity_constraints",
        "stakeholders",
    ):
        _required_list(model.get(field), field=f"subject_model.{field}")
    _json_list(model.get("open_questions"), field="subject_model.open_questions")


def _validate_subject_model(
    model: dict[str, Any],
    *,
    subject_type: str,
) -> None:
    if subject_type == "creator":
        _validate_person_model(model)
        return
    if subject_type not in {"brand", "product", "organization"}:
        raise ValueError("unsupported Personal-IP subject type")
    _validate_non_person_model(model, subject_type=subject_type)


def _validate_objective_goal(
    raw: Any,
    *,
    field: str,
    goal_field: str,
    actor_field: str,
) -> None:
    goal = _json_object(raw, field=field)
    _required_text(goal.get(goal_field), field=f"{field}.{goal_field}")
    _required_text(goal.get(actor_field), field=f"{field}.{actor_field}")
    _required_text(goal.get("success_signal"), field=f"{field}.success_signal")


def _validate_objective_system(value: Any) -> None:
    system = _json_object(value, field="business_model.objective_system")
    if system.get("asset_mechanism") != "influence":
        raise ValueError("business_model.objective_system.asset_mechanism must be influence")
    goal_specs = (
        ("influence_goals", "goal", "target_public"),
        ("behavioral_goals", "behavior", "target_public"),
        ("economic_goals", "outcome", "beneficiary"),
    )
    for list_field, goal_field, actor_field in goal_specs:
        goals = _required_list(
            system.get(list_field),
            field=f"business_model.objective_system.{list_field}",
        )
        for index, raw in enumerate(goals):
            _validate_objective_goal(
                raw,
                field=f"business_model.objective_system.{list_field}[{index}]",
                goal_field=goal_field,
                actor_field=actor_field,
            )
    horizon = _json_object(
        system.get("time_horizon"),
        field="business_model.objective_system.time_horizon",
    )
    for field in ("pilot_window", "operating_horizon"):
        _required_text(
            horizon.get(field),
            field=f"business_model.objective_system.time_horizon.{field}",
        )
    priorities = [
        _required_text(
            item,
            field="business_model.objective_system.priority_order",
            limit=32,
        )
        for item in _required_list(
            system.get("priority_order"),
            field="business_model.objective_system.priority_order",
            minimum=3,
            maximum=3,
        )
    ]
    if set(priorities) != _OBJECTIVE_DOMAINS or len(set(priorities)) != 3:
        raise ValueError("business_model.objective_system.priority_order must order influence, behavioral and economic once each")
    _required_list(
        system.get("guardrails"),
        field="business_model.objective_system.guardrails",
    )
    _json_list(
        system.get("not_optimizing_now"),
        field="business_model.objective_system.not_optimizing_now",
    )


def _validate_business_model(model: dict[str, Any]) -> None:
    missing = sorted(_BUSINESS_MODEL_FIELDS - set(model))
    if missing:
        raise ValueError("business_model is missing: " + ", ".join(missing))
    for field in ("primary_goal",):
        _required_text(model.get(field), field=f"business_model.{field}")
    _validate_objective_system(model.get("objective_system"))
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


def _validate_behavioral_hypothesis(value: Any, *, field: str) -> str:
    text = _required_text(value, field=field, limit=2000)
    lowered = text.lower()
    unsupported = [term for term in _UNSUPPORTED_CAUSAL_TERMS if term.lower() in lowered]
    if unsupported:
        raise ValueError(f"{field} must use observable audience behavior instead of unsupported causal shorthand: {', '.join(unsupported)}")
    if any(phrase in text for phrase in _ABSOLUTE_OUTCOME_PHRASES):
        raise ValueError(f"{field} must be falsifiable and cannot guarantee a viral outcome")
    return text


def _validate_pilot_experiments(value: Any) -> set[str]:
    experiments = _required_list(
        value,
        field="launch_package.pilot_experiments",
        minimum=3,
        maximum=30,
    )
    experiment_ids: set[str] = set()
    for index, raw in enumerate(experiments):
        field = f"launch_package.pilot_experiments[{index}]"
        item = _json_object(raw, field=field)
        experiment_id = _required_text(item.get("experiment_id"), field=f"{field}.experiment_id", limit=128)
        if experiment_id in experiment_ids:
            raise ValueError("launch_package pilot experiment ids must be unique")
        experiment_ids.add(experiment_id)
        role = _required_text(item.get("role"), field=f"{field}.role", limit=32)
        if role not in _PILOT_ROLES:
            raise ValueError(f"{field}.role is unsupported")
        _required_text(item.get("target_audience"), field=f"{field}.target_audience")
        _validate_behavioral_hypothesis(
            item.get("content_hypothesis"),
            field=f"{field}.content_hypothesis",
        )
        evidence_level = _required_text(
            item.get("evidence_level"),
            field=f"{field}.evidence_level",
            limit=40,
        )
        if evidence_level not in _PILOT_EVIDENCE_LEVELS:
            raise ValueError(f"{field}.evidence_level is unsupported")
        evidence_refs = _json_list(item.get("evidence_refs"), field=f"{field}.evidence_refs")
        if evidence_level != "general_prior" and not evidence_refs:
            raise ValueError(f"{field}.evidence_refs are required for {evidence_level}")
        mechanisms = _required_list(
            item.get("mechanism_hypotheses"),
            field=f"{field}.mechanism_hypotheses",
            maximum=8,
        )
        for mechanism_index, mechanism_raw in enumerate(mechanisms):
            mechanism_field = f"{field}.mechanism_hypotheses[{mechanism_index}]"
            mechanism = _json_object(mechanism_raw, field=mechanism_field)
            layer = _required_text(mechanism.get("layer"), field=f"{mechanism_field}.layer", limit=40)
            if layer not in _PILOT_MECHANISM_LAYERS:
                raise ValueError(f"{mechanism_field}.layer is unsupported")
            _validate_behavioral_hypothesis(
                mechanism.get("claim"),
                field=f"{mechanism_field}.claim",
            )
            _required_text(
                mechanism.get("predicted_signal"),
                field=f"{mechanism_field}.predicted_signal",
            )
            _required_text(
                mechanism.get("failure_condition"),
                field=f"{mechanism_field}.failure_condition",
            )
        _required_list(
            item.get("distribution_assumptions"),
            field=f"{field}.distribution_assumptions",
        )
        _required_text(
            item.get("observation_window"),
            field=f"{field}.observation_window",
        )
        _required_text(item.get("failure_rule"), field=f"{field}.failure_rule")
        _required_text(item.get("uncertainty"), field=f"{field}.uncertainty")
    return experiment_ids


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
    _validate_pilot_experiments(package.get("pilot_experiments"))
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
    subject_type: str = "creator",
) -> None:
    """Validate all prerequisites needed to enter the requested stage."""

    stage_index = strategy_stage_index(stage)
    if mode not in STRATEGY_MODES:
        raise ValueError("strategy mode must be monetization_first or influence_first")
    if stage_index >= strategy_stage_index("business_model_draft"):
        _validate_subject_model(person_model, subject_type=subject_type)
    if stage_index >= strategy_stage_index("benchmark_researching"):
        _validate_business_model(business_model)
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
        experiment_ids = {str(item.get("experiment_id") or "").strip() for item in launch_package.get("pilot_experiments", []) if isinstance(item, Mapping)}
        running_ids = {_required_text(item, field="validation.experiment_ids") for item in _required_list(validation.get("experiment_ids"), field="validation.experiment_ids")}
        if not running_ids.issubset(experiment_ids):
            raise ValueError("validation.experiment_ids must reference launch-package pilot experiments")
    if stage_index >= strategy_stage_index("commercial_signal_observed"):
        _required_list(validation.get("commercial_signals"), field="validation.commercial_signals")
        if not any(ref.get("kind") in _VALIDATION_EVIDENCE_KINDS for ref in evidence_refs):
            raise ValueError("commercial signals require observed platform or commercial evidence")
        decision = _json_object(validation.get("validation_decision"), field="validation.validation_decision")
        _required_text(decision.get("selected_candidate_id"), field="validation.validation_decision.selected_candidate_id")
        _required_text(decision.get("decision"), field="validation.validation_decision.decision")
        _required_list(decision.get("supporting_evidence"), field="validation.validation_decision.supporting_evidence")
