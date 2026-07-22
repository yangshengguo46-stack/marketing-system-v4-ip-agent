from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from deerflow.personal_ip.runtime import PersonalIPRuntimeServices, configure_personal_ip_runtime
from deerflow.tools.builtins import personal_ip_minecontext_evidence_tool, personal_ip_minecontext_sync_tool
from deerflow.tools.builtins.minecontext_tools import _personal_ip_minecontext_evidence, _personal_ip_minecontext_sync
from deerflow.tools.tools import BUILTIN_TOOLS


@pytest.mark.asyncio
async def test_sync_tool_is_owner_scoped_and_returns_only_sealed_records() -> None:
    record = {
        "schema_version": "personal-ip-local-context-evidence-v1",
        "evidence_id": "mctx_1",
        "summary": {"title": "Project", "text": "Milestone", "keywords": []},
        "privacy": {"raw_content_included": False},
    }
    service = SimpleNamespace(sync=MagicMock(return_value=[record]))
    configure_personal_ip_runtime(
        PersonalIPRuntimeServices(
            connections=SimpleNamespace(),
            metrics=SimpleNamespace(),
            publish_receipts=SimpleNamespace(),
            minecontext=service,
        )
    )

    raw = await _personal_ip_minecontext_sync(
        SimpleNamespace(context={"user_id": "owner-a", "account_id": "must-not-narrow"}),
        query="current roadmap",
        source_kind="projects",
        purpose="preflight",
        context_types=["activity"],
        limit=5,
    )
    payload = json.loads(raw)

    assert payload["records"] == [record]
    assert "token" not in raw.lower()
    service.sync.assert_called_once_with(
        "owner-a",
        query="current roadmap",
        source_kind="projects",
        purpose="preflight",
        context_types=["activity"],
        limit=5,
    )


@pytest.mark.asyncio
async def test_evidence_tool_requires_authorized_purpose_without_account_filter() -> None:
    service = SimpleNamespace(read_evidence=MagicMock(return_value=[]))
    configure_personal_ip_runtime(
        PersonalIPRuntimeServices(
            connections=SimpleNamespace(),
            metrics=SimpleNamespace(),
            publish_receipts=SimpleNamespace(),
            minecontext=service,
        )
    )
    runtime = SimpleNamespace(context={"user_id": "owner-a"})

    payload = json.loads(
        await _personal_ip_minecontext_evidence(
            runtime,
            purpose="persona_modeling",
            source_kinds=["people", "work_activity"],
            evidence_ids=[],
            limit=10,
        )
    )

    assert payload["records"] == []
    service.read_evidence.assert_called_once_with(
        "owner-a",
        purpose="persona_modeling",
        source_kinds=["people", "work_activity"],
        evidence_ids=[],
        limit=10,
    )
    schema = personal_ip_minecontext_evidence_tool.tool_call_schema.model_json_schema()
    assert "account_id" not in schema.get("properties", {})


def test_minecontext_native_tools_are_registered() -> None:
    names = {tool.name for tool in BUILTIN_TOOLS}
    assert personal_ip_minecontext_sync_tool.name in names
    assert personal_ip_minecontext_evidence_tool.name in names
