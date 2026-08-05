from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from deerflow.personal_ip.content_contracts import BreakdownDraft, ClaimBasis
from deerflow.personal_ip.runtime import PersonalIPRuntimeServices, configure_personal_ip_runtime
from deerflow.tools.builtins.personal_ip_content_tools import (
    _ip_content_start_production,
    ip_content_save_breakdown_tool,
    ip_content_write_tool,
)


def test_content_tool_contract_makes_evidence_refs_discoverable() -> None:
    save_description = ip_content_save_breakdown_tool.description
    write_description = ip_content_write_tool.description
    for description in (save_description, write_description):
        assert "metadata.request_id" in description
        assert "evidence://{request_id}/items/{item_index}/{token}" in description
        assert "media-metadata" in description
        assert "provider/asr" in description
        assert "request_id#field" in description
        assert "absence of music or sound effects" in description

    assert "omit" in write_description and "request.breakdown" in write_description
    breakdown_schema = BreakdownDraft.model_json_schema()
    assert "metadata.request_id" in breakdown_schema["properties"]["evidence_request_id"]["description"]
    assert "first item" in breakdown_schema["properties"]["evidence_item_index"]["description"]
    assert "coverage/asr" in breakdown_schema["$defs"]["BreakdownObservation"]["properties"]["evidence_refs"]["description"]
    claim_schema = ClaimBasis.model_json_schema()
    assert "provider/asr" in claim_schema["properties"]["evidence_refs"]["description"]


@pytest.mark.asyncio
async def test_content_production_tool_only_starts_from_linked_script_version() -> None:
    begin = AsyncMock(
        return_value={
            "id": "video-production-1",
            "contract_version": "personal-ip-video-production-v2",
            "content_work_id": "content-work-1",
            "script_version_id": "script-1",
            "status": "draft",
        }
    )
    configure_personal_ip_runtime(
        PersonalIPRuntimeServices(
            connections=SimpleNamespace(),
            metrics=SimpleNamespace(),
            publish_receipts=SimpleNamespace(),
            video_productions=SimpleNamespace(begin=begin),
        )
    )
    runtime = SimpleNamespace(
        context={
            "user_id": "owner-1",
            "run_id": "run-1",
            "thread_id": "thread-1",
        },
        tool_call_id="tool-1",
    )

    result = json.loads(
        await _ip_content_start_production(
            runtime,
            content_work_id="content-work-1",
            script_version_id="script-1",
            title="制作第一版",
            production_mode="faceless_material",
            target_account_ids=[],
            delivery_spec={"aspect_ratio": "9:16"},
            provider_policy={},
            budget={},
        )
    )

    assert result["operation_status"] == "ok"
    kwargs = begin.await_args.kwargs
    assert kwargs["owner_user_id"] == "owner-1"
    assert kwargs["operation_key"] == "run-1:tool-1"
    assert kwargs["thread_id"] == "thread-1"
    assert kwargs["content_work_id"] == "content-work-1"
    assert kwargs["script_version_id"] == "script-1"
    assert kwargs["source_kind"] == "script"
    assert kwargs["source"] == {}
    assert kwargs["subject_id"] is None

    rejected = json.loads(
        await _ip_content_start_production(
            runtime,
            content_work_id="",
            script_version_id="",
            title="不应创建",
            production_mode="faceless_material",
            target_account_ids=[],
            delivery_spec={},
            provider_policy={},
            budget={},
        )
    )
    assert rejected["status"] == "error"
    assert "are required" in rejected["message"]
    assert begin.await_count == 1
