"""Acceptance-only oracle for the four frozen Writer Brain v2 canaries.

This script evaluates already-produced receipts.  It is not imported by the
Agent runtime, does not choose a customer's strategy and has no persistence or
model authority.  In particular, it does not load the research quarantine or
any Skill catalog.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from deerflow.personal_ip.content_contracts import (
    DirectionDraft,
    EditorialProgramDraft,
    ScriptDraft,
    WriterBrainRequest,
    WriterBrainToolRequest,
    editorial_program_decision_digest,
    validate_direction_program_binding,
    validate_script_direction_binding,
)

_DIRECT_WRITER_TRACE = (
    "ip-agent-script-writer-v2",
    "ip-agent-script-boundary-verifier-v2",
)
_SEMANTIC_WRITER_TRACE = (
    "ip-agent-story-engine-v2",
    "ip-agent-script-writer-v2",
    "ip-agent-script-boundary-verifier-v2",
)
_SCENARIOS = frozenset(
    {
        "urgent_fruit_offer",
        "long_term_person_semantic_story",
        "mcn_brand_explanation",
        "drummer_mom_demonstration",
    }
)
_INTERNAL_FINAL_MARKERS = (
    "ip_content_",
    "personal-ip-",
    "schema",
    "schema=",
    "schema_version",
    "sha256",
    "digest",
    "editorialprogramversion",
    "directionversion",
    "scriptversion",
)


@dataclass(frozen=True)
class WriterBehaviorAcceptanceResult:
    scenario_id: str
    passed: bool
    failure_codes: tuple[str, ...]
    route_kind: str | None
    story_mode: str | None


class _Failures:
    def __init__(self) -> None:
        self._values: list[str] = []

    def add(self, code: str) -> None:
        if code not in self._values:
            self._values.append(code)

    def result(self) -> tuple[str, ...]:
        return tuple(self._values)


@dataclass(frozen=True)
class _RebuiltLineage:
    work: Mapping[str, Any]
    program_row: Mapping[str, Any]
    direction_row: Mapping[str, Any]
    script_row: Mapping[str, Any]
    program: EditorialProgramDraft
    direction: DirectionDraft
    script: ScriptDraft


def _mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _sequence(value: Any) -> Sequence[Any] | None:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return None


def _nonempty_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _normalized_text(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or ""))


def _rebuild_lineage(
    lineage: Any,
    failures: _Failures,
) -> _RebuiltLineage | None:
    root = _mapping(lineage)
    if root is None:
        failures.add("LINEAGE_SHAPE_INVALID")
        return None

    work = _mapping(root.get("content_work"))
    program_row = _mapping(root.get("editorial_program_version"))
    directions = _sequence(root.get("direction_versions"))
    scripts = _sequence(root.get("script_versions"))
    breakdowns = _sequence(root.get("breakdown_versions"))
    if work is None or program_row is None or directions is None or scripts is None or breakdowns is None or len(directions) != 1 or len(scripts) != 1 or len(breakdowns) != 0:
        failures.add("LINEAGE_SHAPE_INVALID")
        return None
    direction_row = _mapping(directions[0])
    script_row = _mapping(scripts[0])
    if direction_row is None or script_row is None:
        failures.add("LINEAGE_SHAPE_INVALID")
        return None

    work_id = _nonempty_text(work.get("id"))
    program_version_id = _nonempty_text(program_row.get("id"))
    program_id = _nonempty_text(program_row.get("program_id"))
    direction_id = _nonempty_text(direction_row.get("id"))
    script_id = _nonempty_text(script_row.get("id"))
    objective_id = _nonempty_text(work.get("objective_id"))
    owner_id = _nonempty_text(work.get("owner_user_id"))
    run_id = _nonempty_text(work.get("created_by_run_id"))
    thread_id = _nonempty_text(work.get("thread_id"))
    if None in (
        work_id,
        program_version_id,
        program_id,
        direction_id,
        script_id,
        objective_id,
        owner_id,
        run_id,
        thread_id,
    ):
        failures.add("LINEAGE_IDENTITY_INVALID")

    if work.get("editorial_program_version_id") != program_row.get("id"):
        failures.add("LINEAGE_PROGRAM_WORK_MISMATCH")
    if program_row.get("subject_id") != work.get("subject_id"):
        failures.add("LINEAGE_PROGRAM_WORK_MISMATCH")
    if direction_row.get("content_work_id") != work.get("id"):
        failures.add("LINEAGE_DIRECTION_WORK_MISMATCH")
    if script_row.get("content_work_id") != work.get("id"):
        failures.add("LINEAGE_SCRIPT_WORK_MISMATCH")
    if script_row.get("direction_version_id") != direction_row.get("id"):
        failures.add("LINEAGE_SCRIPT_DIRECTION_MISMATCH")

    owners = (
        work.get("owner_user_id"),
        direction_row.get("owner_user_id"),
        script_row.get("owner_user_id"),
    )
    if any(_nonempty_text(value) is None for value in owners) or any(value != owners[0] for value in owners[1:]):
        failures.add("LINEAGE_OWNER_MISMATCH")
    runs = (
        work.get("created_by_run_id"),
        direction_row.get("created_by_run_id"),
        script_row.get("created_by_run_id"),
    )
    if any(_nonempty_text(value) is None for value in runs) or any(value != runs[0] for value in runs[1:]):
        failures.add("LINEAGE_RUN_MISMATCH")
    if not thread_id:
        failures.add("LINEAGE_THREAD_MISMATCH")

    if (
        work.get("entry_route") != "zero_start"
        or work.get("status") != "active"
        or type(program_row.get("version_number")) is not int
        or program_row.get("version_number") != 1
        or type(direction_row.get("version_number")) is not int
        or direction_row.get("version_number") != 1
        or type(script_row.get("version_number")) is not int
        or script_row.get("version_number") != 1
        or program_row.get("parent_program_version_id") is not None
        or direction_row.get("parent_direction_version_id") is not None
        or script_row.get("parent_script_version_id") is not None
    ):
        failures.add("LINEAGE_VERSION_INVALID")
    if direction_row.get("breakdown_version_ids") != []:
        failures.add("LINEAGE_BREAKDOWN_UNEXPECTED")
    if direction_row.get("objective_snapshot") != work.get("objective"):
        failures.add("LINEAGE_OBJECTIVE_MISMATCH")

    decision = _mapping(program_row.get("decision"))
    direction_value = _mapping(direction_row.get("direction"))
    if decision is None or direction_value is None:
        failures.add("LINEAGE_CONTRACT_INVALID")
        return None
    try:
        program = EditorialProgramDraft.model_validate(
            {
                **dict(decision),
                "title": program_row.get("title"),
                "parent_program_version_id": program_row.get("parent_program_version_id"),
            }
        )
    except ValueError:
        failures.add("LINEAGE_PROGRAM_INVALID")
        return None
    try:
        direction = DirectionDraft.model_validate(direction_value)
        validate_direction_program_binding(program, direction)
    except ValueError:
        failures.add("LINEAGE_DIRECTION_BINDING_INVALID")
        return None
    if direction.breakdown_version_ids != direction_row.get("breakdown_version_ids") or direction.parent_direction_version_id != direction_row.get("parent_direction_version_id"):
        failures.add("LINEAGE_DIRECTION_BINDING_INVALID")

    try:
        script = ScriptDraft.model_validate(
            {
                "title": script_row.get("title"),
                "story_mode": script_row.get("story_mode"),
                "script_text": script_row.get("script_text"),
                "claim_basis": script_row.get("claim_basis"),
                "creative_elements": script_row.get("creative_elements"),
                "story_engine_seed": script_row.get("story_engine_seed"),
                "locked_story": script_row.get("locked_story"),
                "production_notes": script_row.get("production_notes"),
                "direction_version_id": script_row.get("direction_version_id"),
                "parent_script_version_id": script_row.get("parent_script_version_id"),
            }
        )
        validate_script_direction_binding(direction, script)
    except ValueError:
        failures.add("LINEAGE_SCRIPT_RECEIPT_INVALID")
        return None

    expected_locked_digest = hashlib.sha256(script.locked_story.encode("utf-8")).hexdigest() if script.locked_story is not None else None
    if script_row.get("locked_story_digest") != expected_locked_digest:
        failures.add("LINEAGE_SCRIPT_RECEIPT_INVALID")

    return _RebuiltLineage(
        work=work,
        program_row=program_row,
        direction_row=direction_row,
        script_row=script_row,
        program=program,
        direction=direction,
        script=script,
    )


def _validate_tool_trace(
    tool_trace: Any,
    rebuilt: _RebuiltLineage | None,
    failures: _Failures,
) -> None:
    trace = _sequence(tool_trace)
    if trace is None or len(trace) != 1:
        failures.add("TOOL_TRACE_FORBIDDEN_CALL")
        return
    call = _mapping(trace[0])
    if call is None or call.get("name") != "ip_content_write" or call.get("status") != "ok":
        failures.add("TOOL_TRACE_FORBIDDEN_CALL")
        return
    if rebuilt is None:
        return

    work = rebuilt.work
    program_row = rebuilt.program_row
    direction_row = rebuilt.direction_row
    script_row = rebuilt.script_row
    if (
        call.get("owner_user_id") != work.get("owner_user_id")
        or call.get("run_id") != work.get("created_by_run_id")
        or call.get("thread_id") != work.get("thread_id")
        or work.get("operation_key") != f"{call.get('run_id')}:{call.get('call_id')}"
    ):
        failures.add("TOOL_TRACE_AUTHORITY_MISMATCH")

    result = _mapping(call.get("result"))
    if result is None or result.get("operation_status") != "ok":
        failures.add("TOOL_RESULT_INVALID")
    else:
        exact_values = {
            "content_work_id": work.get("id"),
            "editorial_program_version_id": program_row.get("id"),
            "direction_version_id": direction_row.get("id"),
            "script_version_id": script_row.get("id"),
            "story_mode": script_row.get("story_mode"),
            "locked_story": script_row.get("locked_story"),
            "locked_story_sha256": script_row.get("locked_story_digest"),
            "script_text": script_row.get("script_text"),
        }
        if any(result.get(key) != expected for key, expected in exact_values.items()):
            failures.add("TOOL_RESULT_LINEAGE_MISMATCH")
        if result.get("schema_version") != "personal-ip-writer-brain-v2" or result.get("breakdown_version_id") is not None or result.get("replayed") is not False:
            failures.add("TOOL_RESULT_LINEAGE_MISMATCH")
        version_values = {
            "editorial_program_version_number": program_row.get("version_number"),
            "direction_version_number": direction_row.get("version_number"),
            "script_version_number": script_row.get("version_number"),
        }
        if any(result.get(key) != expected for key, expected in version_values.items()):
            failures.add("TOOL_RESULT_VERSION_MISMATCH")

    arguments = _mapping(call.get("arguments"))
    request_value = _mapping(arguments.get("request")) if arguments else None
    if request_value is None:
        failures.add("TOOL_REQUEST_INVALID")
        return
    try:
        tool_request = WriterBrainToolRequest.model_validate(request_value)
        request = WriterBrainRequest.model_validate(tool_request.model_dump(mode="json"))
    except ValueError:
        failures.add("TOOL_REQUEST_INVALID")
        return
    if (
        request.content_work_id is not None
        or request.entry_route != "zero_start"
        or request.subject_id != work.get("subject_id")
        or request.breakdown is not None
        or request.work_title != work.get("title")
        or request.objective is None
        or request.objective.model_dump(mode="json") != work.get("objective")
        or request.editorial_program is None
        or request.editorial_program_version_id is not None
        or editorial_program_decision_digest(request.editorial_program) != editorial_program_decision_digest(rebuilt.program)
        or request.editorial_program.title != rebuilt.program.title
    ):
        failures.add("TOOL_REQUEST_LINEAGE_MISMATCH")

    caller_direction = rebuilt.direction.model_copy(update={"editorial_program_digest": None})
    if request.direction != caller_direction:
        failures.add("TOOL_REQUEST_LINEAGE_MISMATCH")
    stored_seed = rebuilt.script.story_engine_seed
    if stored_seed is None:
        if request.story_engine_seed is not None:
            failures.add("TOOL_REQUEST_LINEAGE_MISMATCH")
    else:
        caller_seed = stored_seed.model_copy(update={"semantic_route_digest": None})
        if request.story_engine_seed != caller_seed:
            failures.add("TOOL_REQUEST_LINEAGE_MISMATCH")

    translation = request.production_translation.model_dump(mode="json")
    notes = rebuilt.script.production_notes
    if any(notes.get(key) != value for key, value in translation.items()):
        failures.add("TOOL_REQUEST_LINEAGE_MISMATCH")


def _validate_writer_model_trace(
    writer_model_trace: Any,
    direction: DirectionDraft | None,
    failures: _Failures,
) -> None:
    trace = _sequence(writer_model_trace)
    if trace is None or direction is None:
        failures.add("WRITER_MODEL_TRACE_INVALID")
        return
    expected = _SEMANTIC_WRITER_TRACE if direction.route_kind in {"semantic_story", "hybrid"} else _DIRECT_WRITER_TRACE
    actual_names: list[str] = []
    for expected_index, value in enumerate(trace, start=1):
        call = _mapping(value)
        if call is None or call.get("call_index") != expected_index or call.get("status") != "success" or not isinstance(call.get("run_name"), str):
            failures.add("WRITER_MODEL_TRACE_INVALID")
            return
        actual_names.append(call["run_name"])
    if tuple(actual_names) != expected:
        failures.add("WRITER_MODEL_TRACE_INVALID")


def _validate_final_text(
    final_text: Any,
    rebuilt: _RebuiltLineage | None,
    failures: _Failures,
) -> None:
    text = _nonempty_text(final_text)
    if text is None:
        failures.add("FINAL_RESPONSE_SCRIPT_MISMATCH")
        failures.add("FINAL_RESPONSE_VERSION_MISSING")
        return
    if rebuilt is None:
        return
    script_text = rebuilt.script.script_text
    if _normalized_text(script_text) not in _normalized_text(text):
        failures.add("FINAL_RESPONSE_SCRIPT_MISMATCH")
    if "第1版" not in text:
        failures.add("FINAL_RESPONSE_VERSION_MISSING")

    normalized = text.casefold()
    identities = (
        rebuilt.work.get("id"),
        rebuilt.program_row.get("id"),
        rebuilt.program_row.get("program_id"),
        rebuilt.direction_row.get("id"),
        rebuilt.script_row.get("id"),
        rebuilt.work.get("created_by_run_id"),
        rebuilt.work.get("thread_id"),
        rebuilt.work.get("operation_key"),
    )
    if any(marker in normalized for marker in _INTERNAL_FINAL_MARKERS) or any(str(identity).casefold() in normalized for identity in identities if _nonempty_text(identity)):
        failures.add("FINAL_RESPONSE_INTERNAL_LEAK")


def _contains_any(value: str, terms: Sequence[str]) -> bool:
    normalized = value.casefold()
    return any(term.casefold() in normalized for term in terms)


def _validate_common_business_contract(
    rebuilt: _RebuiltLineage,
    failures: _Failures,
) -> None:
    if rebuilt.program.differentiation.state != "hypothesized":
        failures.add("DIFFERENTIATION_NOT_HYPOTHESIZED")
    if not rebuilt.program.differentiation.basis:
        failures.add("DIFFERENTIATION_BASIS_MISSING")


def _validate_urgent_fruit(
    rebuilt: _RebuiltLineage,
    failures: _Failures,
) -> None:
    program = rebuilt.program
    direction = rebuilt.direction
    script = rebuilt.script
    correct_axes = (
        program.mission.goal_priority[0] == "conversion" and program.mission.time_horizon == "urgent" and program.attribution.primary_carrier.kind == "product" and direction.route_kind == "offer" and direction.truth_mode == "factual"
    )
    if not correct_axes:
        failures.add("URGENT_FRUIT_NOT_CONVERSION_PRODUCT")
    if program.editorial_spine is not None or direction.semantic_route is not None or script.story_engine_seed is not None or script.locked_story is not None or script.creative_elements:
        failures.add("URGENT_FRUIT_SEMANTIC_ROUTE_FORCED")
    if not _contains_any(
        program.mission.success_signal,
        ("订单", "询盘", "采购", "下单"),
    ):
        failures.add("URGENT_FRUIT_SUCCESS_SIGNAL_INVALID")


def _validate_long_term_person(
    rebuilt: _RebuiltLineage,
    failures: _Failures,
) -> None:
    program = rebuilt.program
    direction = rebuilt.direction
    script = rebuilt.script
    correct_axes = (
        program.mission.goal_priority[0] == "recognition"
        and program.mission.time_horizon == "long_term"
        and program.attribution.primary_carrier.kind == "person"
        and direction.route_kind == "semantic_story"
        and direction.truth_mode == "fictional"
    )
    if not correct_axes:
        failures.add("LONG_TERM_PERSON_ATTRIBUTION_LOST")
    if program.editorial_spine is None or direction.semantic_route is None or script.story_engine_seed is None or not script.locked_story or not script.creative_elements:
        failures.add("LONG_TERM_PERSON_SEMANTIC_BINDING_MISSING")
    live_claims = [claim for claim in script.claim_basis if claim.usage != "excluded"]
    if live_claims:
        failures.add("LONG_TERM_PERSON_FICTION_CLAIM_LEAK")


def _validate_mcn_brand(
    rebuilt: _RebuiltLineage,
    failures: _Failures,
) -> None:
    program = rebuilt.program
    direction = rebuilt.direction
    statement = program.differentiation.statement
    bases = " ".join(item.claim for item in program.differentiation.basis)
    correct_axes = (
        program.mission.goal_priority == ["recognition", "conversion", "trust"]
        and program.mission.time_horizon == "long_term"
        and program.attribution.primary_carrier.kind == "brand"
        and direction.route_kind == "explanation"
        and direction.truth_mode == "factual"
    )
    if not correct_axes:
        failures.add("MCN_BRAND_ATTRIBUTION_LOST")
    if not _contains_any(
        f"{statement} {bases}",
        ("分成", "结算", "退出", "决定权", "自主权"),
    ):
        failures.add("MCN_DIFFERENTIATION_HAS_NO_RULE_BASIS")
    if direction.semantic_route is not None or rebuilt.script.story_engine_seed is not None:
        failures.add("MCN_DIRECT_ROUTE_USED_SEMANTIC_CORE")
    if _contains_any(
        rebuilt.script.script_text,
        ("保证爆款", "保证收入", "保证赚钱", "稳赚", "保底收入"),
    ):
        failures.add("MCN_UNSUPPORTED_RESULT_PROMISE")


def _validate_drummer_mom(
    rebuilt: _RebuiltLineage,
    failures: _Failures,
) -> None:
    program = rebuilt.program
    direction = rebuilt.direction
    differentiation = program.differentiation.statement
    attribution_text = " ".join(
        (
            program.attribution.primary_carrier.identity,
            program.attribution.desired_association,
            differentiation,
            program.audience.situation,
        )
    )
    correct_axes = (
        program.mission.goal_priority[0] == "recognition"
        and program.mission.time_horizon == "long_term"
        and program.attribution.primary_carrier.kind == "person"
        and direction.route_kind == "demonstration"
        and direction.truth_mode == "factual"
    )
    role_became_positioning = _contains_any(
        attribution_text,
        ("宝妈", "母婴", "育儿", "带娃"),
    )
    difference_has_real_goal = _contains_any(
        differentiation,
        ("鼓手", "地下乐队"),
    ) and _contains_any(differentiation, ("训练", "重返舞台", "回归舞台"))
    guard_has_privacy_boundary = _contains_any(
        program.attribution.attribution_guard,
        ("隐私", "不出镜", "不作为内容主角"),
    )
    if not correct_axes or role_became_positioning or not difference_has_real_goal or not guard_has_privacy_boundary:
        failures.add("MOM_ROLE_BECAME_POSITIONING")
    if direction.semantic_route is not None or rebuilt.script.story_engine_seed is not None:
        failures.add("MOM_DIRECT_ROUTE_USED_SEMANTIC_CORE")


def _validate_scenario(
    scenario_id: str,
    rebuilt: _RebuiltLineage | None,
    failures: _Failures,
) -> None:
    if scenario_id not in _SCENARIOS:
        failures.add("SCENARIO_UNKNOWN")
        return
    if rebuilt is None:
        return
    _validate_common_business_contract(rebuilt, failures)
    validators = {
        "urgent_fruit_offer": _validate_urgent_fruit,
        "long_term_person_semantic_story": _validate_long_term_person,
        "mcn_brand_explanation": _validate_mcn_brand,
        "drummer_mom_demonstration": _validate_drummer_mom,
    }
    validators[scenario_id](rebuilt, failures)


def evaluate_writer_behavior_acceptance(
    *,
    scenario_id: str,
    lineage: Mapping[str, Any],
    tool_trace: Sequence[Mapping[str, Any]],
    writer_model_trace: Sequence[Mapping[str, Any]],
    final_text: str,
) -> WriterBehaviorAcceptanceResult:
    """Evaluate one frozen sample without model, network or database access."""

    failures = _Failures()
    rebuilt = _rebuild_lineage(lineage, failures)
    _validate_tool_trace(tool_trace, rebuilt, failures)
    _validate_writer_model_trace(
        writer_model_trace,
        rebuilt.direction if rebuilt is not None else None,
        failures,
    )
    _validate_final_text(final_text, rebuilt, failures)
    _validate_scenario(scenario_id, rebuilt, failures)
    failure_codes = failures.result()
    return WriterBehaviorAcceptanceResult(
        scenario_id=scenario_id,
        passed=not failure_codes,
        failure_codes=failure_codes,
        route_kind=(rebuilt.direction.route_kind if rebuilt is not None else None),
        story_mode=(rebuilt.script.story_mode if rebuilt is not None else None),
    )


__all__ = [
    "WriterBehaviorAcceptanceResult",
    "evaluate_writer_behavior_acceptance",
]
