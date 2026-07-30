from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from deerflow.personal_ip.runtime import (
    PersonalIPRuntimeServices,
    configure_personal_ip_runtime,
)
from deerflow.tools.builtins.personal_ip_differentiation_tools import (
    _personal_ip_read_differentiation,
    _personal_ip_record_asset_observation,
    _personal_ip_record_differentiation,
)
from deerflow.tools.tools import BUILTIN_TOOLS


@pytest.mark.asyncio
async def test_record_differentiation_can_create_a_product_subject() -> None:
    subjects = SimpleNamespace(
        list=AsyncMock(return_value=[]),
        create=AsyncMock(
            return_value={
                "id": "subject-product",
                "display_name": "IP Agent",
                "subject_type": "product",
                "status": "active",
            }
        ),
    )
    differentiation = SimpleNamespace(
        create_version=AsyncMock(
            return_value={
                "id": "difference-1",
                "version": 1,
                "thesis_key": "ip-agent-core",
                "status": "candidate",
                "validation_summary": {"complete_observation_count": 0},
            }
        )
    )
    configure_personal_ip_runtime(
        PersonalIPRuntimeServices(
            connections=SimpleNamespace(),
            metrics=SimpleNamespace(),
            publish_receipts=SimpleNamespace(),
            subjects=subjects,
            differentiation=differentiation,
        )
    )
    runtime = SimpleNamespace(context={"user_id": "user-1"})

    result = json.loads(
        await _personal_ip_record_differentiation(
            runtime,
            operation_key="difference:1",
            thesis_key="ip-agent-core",
            status="candidate",
            display_name="IP Agent",
            subject_type="product",
            primary_entity={"entity_type": "product"},
            supporting_entities=[],
            decision_context={},
            contrast_field={},
            proprietary_truth={},
            strategic_difference={},
            dramatic_engine={},
            distinctive_encoding={},
            operating_fit={},
            validation={},
            evidence_refs=[{"kind": "product_demo", "id": "demo-1"}],
        )
    )

    assert result["operation_status"] == "ok"
    assert result["subject_id"] == "subject-product"
    assert subjects.create.await_args.kwargs["subject_type"] == "product"
    assert differentiation.create_version.await_args.kwargs["owner_user_id"] == "user-1"


@pytest.mark.asyncio
async def test_read_and_observe_differentiation_use_runtime_owner() -> None:
    differentiation = SimpleNamespace(
        get_latest=AsyncMock(return_value={"id": "difference-1", "status": "pilot"}),
        record_observation=AsyncMock(
            return_value={
                "id": "observation-1",
                "subject_id": "subject-1",
                "differentiation_version_id": "difference-1",
                "observation_type": "adoption",
                "coverage_status": "complete",
                "observed_at": "2026-07-30T08:00:00+00:00",
            }
        ),
    )
    configure_personal_ip_runtime(
        PersonalIPRuntimeServices(
            connections=SimpleNamespace(),
            metrics=SimpleNamespace(),
            publish_receipts=SimpleNamespace(),
            differentiation=differentiation,
        )
    )
    runtime = SimpleNamespace(context={"user_id": "user-1"})

    read = json.loads(await _personal_ip_read_differentiation(runtime, subject_id="subject-1"))
    observed = json.loads(
        await _personal_ip_record_asset_observation(
            runtime,
            operation_key="observation:1",
            subject_id="subject-1",
            differentiation_version_id="difference-1",
            observation_type="adoption",
            source="product_telemetry",
            observed_at="2026-07-30T08:00:00Z",
            coverage_status="complete",
            measures={"result": "supports", "activated_accounts": 2},
            evidence_refs=[{"kind": "product_telemetry", "id": "activation-1"}],
        )
    )

    assert read["differentiation"]["status"] == "pilot"
    assert observed["observation_id"] == "observation-1"
    assert differentiation.get_latest.await_args.kwargs["owner_user_id"] == "user-1"
    assert differentiation.record_observation.await_args.kwargs["observed_at"].tzinfo is not None


def test_differentiation_native_tools_are_registered() -> None:
    names = {item.name for item in BUILTIN_TOOLS}
    assert {
        "personal_ip_record_differentiation",
        "personal_ip_read_differentiation",
        "personal_ip_record_asset_observation",
    }.issubset(names)
