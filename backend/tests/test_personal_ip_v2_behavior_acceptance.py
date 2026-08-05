"""Regression tests for the four frozen default-Agent v2 behavior samples.

The suite was introduced and expanded as red tests before the pure evaluator
was implemented.  It preserves those frozen TDD expectations, including the
raw model-facing tool schema used by live Agent runs.
"""

from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from _personal_ip_v2_behavior_fixtures import (
    CASES,
    BehaviorCase,
    broken_boundary_receipt,
    broken_lineage,
    forbidden_tool_trace,
    invalid_final_text,
    invalid_writer_model_trace,
    mismatched_tool_result_version,
)

from deerflow.config.database_config import DatabaseConfig
from deerflow.persistence.engine import (
    close_engine,
    get_session_factory,
    init_engine_from_config,
)
from deerflow.persistence.personal_ip_content import PersonalIPContentRepository
from deerflow.personal_ip.content_contracts import (
    ContentWorkCreate,
    DirectionDraft,
    EditorialProgramDraft,
    ScriptDraft,
    direction_decision_digest,
    editorial_program_decision_digest,
    script_decision_digest,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ACCEPTANCE_ORACLE_SCRIPT = REPOSITORY_ROOT / "scripts/personal_ip_writer_v2_acceptance_oracle.py"
RETIRED_HARNESS_ORACLE = REPOSITORY_ROOT / "backend/packages/harness/deerflow/personal_ip/writer_behavior_acceptance.py"
_ORACLE_MODULE: ModuleType | None = None


def test_writer_behavior_oracle_is_acceptance_only_and_not_runtime_importable() -> None:
    assert ACCEPTANCE_ORACLE_SCRIPT.is_file()
    assert not RETIRED_HARNESS_ORACLE.exists()

    forbidden_markers = (
        "personal_ip_writer_v2_acceptance_oracle",
        "writer_behavior_acceptance",
    )
    offenders: list[str] = []
    for runtime_root in (
        REPOSITORY_ROOT / "backend/packages/harness/deerflow",
        REPOSITORY_ROOT / "backend/app",
    ):
        for path in runtime_root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if any(marker in text for marker in forbidden_markers):
                offenders.append(str(path.relative_to(REPOSITORY_ROOT)))
    assert offenders == []


def _load_acceptance_oracle() -> ModuleType:
    global _ORACLE_MODULE
    if _ORACLE_MODULE is None:
        spec = importlib.util.spec_from_file_location(
            "personal_ip_writer_v2_acceptance_oracle_test",
            ACCEPTANCE_ORACLE_SCRIPT,
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        _ORACLE_MODULE = module
    return _ORACLE_MODULE


def _evaluate(
    case: BehaviorCase,
    *,
    lineage: dict[str, Any] | None = None,
    tool_trace: list[dict[str, Any]] | None = None,
    writer_model_trace: list[dict[str, Any]] | None = None,
    final_text: str | None = None,
) -> Any:
    module = _load_acceptance_oracle()
    return module.evaluate_writer_behavior_acceptance(
        scenario_id=case.scenario_id,
        lineage=lineage if lineage is not None else case.lineage,
        tool_trace=tool_trace if tool_trace is not None else case.tool_trace,
        writer_model_trace=(writer_model_trace if writer_model_trace is not None else case.writer_model_trace),
        final_text=final_text if final_text is not None else case.final_text,
    )


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.scenario_id)
def test_frozen_v2_scenario_accepts_the_expected_behavior(
    case: BehaviorCase,
) -> None:
    raw_request = case.tool_trace[0]["arguments"]["request"]
    assert "contract_version" not in raw_request["direction"]
    assert "editorial_program_digest" not in raw_request["direction"]
    if raw_request["story_engine_seed"] is not None:
        assert "semantic_route_digest" not in raw_request["story_engine_seed"]

    result = _evaluate(case)

    assert result.scenario_id == case.scenario_id
    assert result.passed is True
    assert list(result.failure_codes) == []
    assert result.route_kind == case.expected_route
    assert result.story_mode == case.expected_story_mode


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.scenario_id)
def test_frozen_v2_scenario_rejects_its_business_misclassification(
    case: BehaviorCase,
) -> None:
    result = _evaluate(
        case,
        lineage=case.negative_lineage,
        tool_trace=case.negative_tool_trace,
        final_text=case.negative_final_text,
    )

    assert result.passed is False
    assert case.negative_failure_code in set(result.failure_codes)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.scenario_id)
def test_frozen_v2_scenario_rejects_a_work_bound_to_another_program(
    case: BehaviorCase,
) -> None:
    result = _evaluate(case, lineage=broken_lineage(case))

    assert result.passed is False
    assert "LINEAGE_PROGRAM_WORK_MISMATCH" in set(result.failure_codes)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.scenario_id)
def test_frozen_v2_scenario_rejects_a_tampered_script_receipt(
    case: BehaviorCase,
) -> None:
    result = _evaluate(case, lineage=broken_boundary_receipt(case))

    assert result.passed is False
    assert "LINEAGE_SCRIPT_RECEIPT_INVALID" in set(result.failure_codes)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.scenario_id)
def test_frozen_v2_scenario_rejects_unnecessary_or_out_of_scope_tools(
    case: BehaviorCase,
) -> None:
    result = _evaluate(case, tool_trace=forbidden_tool_trace(case))

    assert result.passed is False
    assert "TOOL_TRACE_FORBIDDEN_CALL" in set(result.failure_codes)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.scenario_id)
@pytest.mark.parametrize("mutation", ("missing", "extra", "wrong_name"))
def test_frozen_v2_scenario_requires_the_exact_writer_model_trace(
    case: BehaviorCase,
    mutation: str,
) -> None:
    result = _evaluate(
        case,
        writer_model_trace=invalid_writer_model_trace(case, mutation),
    )

    assert result.passed is False
    assert "WRITER_MODEL_TRACE_INVALID" in set(result.failure_codes)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.scenario_id)
@pytest.mark.parametrize(
    ("mutation", "failure_code"),
    (
        ("missing_script", "FINAL_RESPONSE_SCRIPT_MISMATCH"),
        ("missing_version", "FINAL_RESPONSE_VERSION_MISSING"),
        ("internal_leak", "FINAL_RESPONSE_INTERNAL_LEAK"),
    ),
)
def test_frozen_v2_scenario_requires_a_complete_customer_safe_final_response(
    case: BehaviorCase,
    mutation: str,
    failure_code: str,
) -> None:
    result = _evaluate(case, final_text=invalid_final_text(case, mutation))

    assert result.passed is False
    assert failure_code in set(result.failure_codes)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.scenario_id)
@pytest.mark.parametrize("version_kind", ("program", "direction", "script"))
def test_frozen_v2_scenario_requires_tool_result_versions_to_match_the_lineage(
    case: BehaviorCase,
    version_kind: str,
) -> None:
    result = _evaluate(
        case,
        tool_trace=mismatched_tool_result_version(case, version_kind),
    )

    assert result.passed is False
    assert "TOOL_RESULT_VERSION_MISMATCH" in set(result.failure_codes)


@pytest.mark.asyncio
async def test_repository_public_lineage_projection_is_accepted(
    tmp_path,
) -> None:
    case = CASES[0]
    fixture_program = case.lineage["editorial_program_version"]
    fixture_direction = case.lineage["direction_versions"][0]
    fixture_script = case.lineage["script_versions"][0]
    program = EditorialProgramDraft.model_validate(
        {
            **fixture_program["decision"],
            "title": fixture_program["title"],
            "parent_program_version_id": fixture_program["parent_program_version_id"],
        }
    )
    direction = DirectionDraft.model_validate(fixture_direction["direction"])
    script = ScriptDraft.model_validate(
        {
            "title": fixture_script["title"],
            "story_mode": fixture_script["story_mode"],
            "script_text": fixture_script["script_text"],
            "claim_basis": fixture_script["claim_basis"],
            "creative_elements": fixture_script["creative_elements"],
            "story_engine_seed": fixture_script["story_engine_seed"],
            "locked_story": fixture_script["locked_story"],
            "production_notes": fixture_script["production_notes"],
            "direction_version_id": None,
            "parent_script_version_id": None,
        }
    )
    run_id = "run-repository-projection"
    thread_id = "thread-repository-projection"
    tool_call_id = "tool-repository-projection"

    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    session_factory = get_session_factory()
    assert session_factory is not None
    repository = PersonalIPContentRepository(session_factory)
    try:
        created = await repository.create(
            owner_user_id="owner-acceptance",
            request=ContentWorkCreate(
                idempotency_key=f"{run_id}:{tool_call_id}",
                subject_id=None,
                title=case.lineage["content_work"]["title"],
                entry_route="zero_start",
                objective=case.lineage["content_work"]["objective"],
                editorial_program=program,
                direction=direction,
                script=script,
            ),
            created_by_run_id=run_id,
            thread_id=thread_id,
            verified_program_digests=frozenset({editorial_program_decision_digest(program)}),
            verified_direction_digests=frozenset({direction_decision_digest(direction)}),
            verified_script_digests=frozenset({script_decision_digest(script)}),
        )
        lineage = await repository.get_lineage(
            created["content_work"]["id"],
            owner_user_id="owner-acceptance",
        )
        assert lineage is not None
        assert {
            "owner_user_id",
            "created_by_run_id",
            "operation_key",
        }.isdisjoint(lineage["editorial_program_version"])

        tool_trace = copy.deepcopy(case.tool_trace)
        call = tool_trace[0]
        call.update(
            {
                "call_id": tool_call_id,
                "owner_user_id": "owner-acceptance",
                "run_id": run_id,
                "thread_id": thread_id,
            }
        )
        program_row = lineage["editorial_program_version"]
        direction_row = lineage["direction_versions"][0]
        script_row = lineage["script_versions"][0]
        call["result"].update(
            {
                "content_work_id": lineage["content_work"]["id"],
                "editorial_program_version_id": program_row["id"],
                "editorial_program_version_number": program_row["version_number"],
                "direction_version_id": direction_row["id"],
                "direction_version_number": direction_row["version_number"],
                "script_version_id": script_row["id"],
                "script_version_number": script_row["version_number"],
                "story_mode": script_row["story_mode"],
                "locked_story": script_row["locked_story"],
                "locked_story_sha256": script_row["locked_story_digest"],
                "script_text": script_row["script_text"],
            }
        )
        final_text = f"已保存为第1版正式脚本。\n\n{script_row['script_text']}"

        result = _evaluate(
            case,
            lineage=lineage,
            tool_trace=tool_trace,
            final_text=final_text,
        )

        assert result.passed is True
        assert list(result.failure_codes) == []
    finally:
        await close_engine()
