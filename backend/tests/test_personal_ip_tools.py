from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from deerflow.personal_ip.runtime import PersonalIPRuntimeServices, configure_personal_ip_runtime
from deerflow.tools.builtins import personal_ip_metrics_aggregate_tool, personal_ip_sync_douyin_post_tool
from deerflow.tools.builtins.personal_ip_tools import (
    _personal_ip_metrics_aggregate,
    _personal_ip_sync_douyin_post,
)
from deerflow.tools.tools import BUILTIN_TOOLS


@pytest.mark.asyncio
async def test_portfolio_metric_tool_aggregates_authenticated_users_whole_portfolio() -> None:
    metrics = SimpleNamespace(
        aggregate=AsyncMock(
            return_value={
                "totals": {"views": 1200},
                "coverage": {"missing_account_ids": ["acct-missing"]},
            }
        )
    )
    configure_personal_ip_runtime(
        PersonalIPRuntimeServices(
            connections=SimpleNamespace(),
            metrics=metrics,
            publish_receipts=SimpleNamespace(),
        )
    )
    runtime = SimpleNamespace(context={"user_id": "user-1"})

    payload = json.loads(
        await _personal_ip_metrics_aggregate(
            runtime,
            window_started_at="2026-07-21T00:00:00+08:00",
            window_ended_at="2026-07-22T00:00:00+08:00",
        )
    )

    assert payload["status"] == "ok"
    assert payload["totals"]["views"] == 1200
    assert payload["coverage"]["missing_account_ids"] == ["acct-missing"]
    kwargs = metrics.aggregate.await_args.kwargs
    assert kwargs["owner_user_id"] == "user-1"
    assert "account_id" not in kwargs


@pytest.mark.asyncio
async def test_douyin_sync_tool_uses_connection_reference_without_returning_token(monkeypatch) -> None:
    configure_personal_ip_runtime(
        PersonalIPRuntimeServices(
            connections=SimpleNamespace(),
            metrics=SimpleNamespace(),
            publish_receipts=SimpleNamespace(),
        )
    )
    collect = AsyncMock(
        return_value={
            "id": "metric-1",
            "account_id": "acct-1",
            "receipt_id": "publish-1",
            "metrics": {"views": 900},
        }
    )
    service = SimpleNamespace(collect_published_post=collect)
    monkeypatch.setattr(
        "deerflow.tools.builtins.personal_ip_tools._authorized_douyin_service",
        lambda _services: service,
    )
    runtime = SimpleNamespace(context={"user_id": "user-1"})

    result = await _personal_ip_sync_douyin_post(
        runtime,
        connection_id="platform-conn-1",
        publish_receipt_id="publish-1",
        observation_key="douyin:item-1:2026-07-21T12:00:00Z",
    )
    payload = json.loads(result)

    assert payload["status"] == "ok"
    assert payload["metrics"]["views"] == 900
    assert "token" not in result.lower()
    collect.assert_awaited_once_with(
        owner_user_id="user-1",
        connection_id="platform-conn-1",
        publish_receipt_id="publish-1",
        observation_key="douyin:item-1:2026-07-21T12:00:00Z",
    )


def test_personal_ip_native_tools_are_available_without_thread_account_binding() -> None:
    names = {tool.name for tool in BUILTIN_TOOLS}
    assert personal_ip_metrics_aggregate_tool.name == "personal_ip_metrics_aggregate"
    assert personal_ip_sync_douyin_post_tool.name == "personal_ip_sync_douyin_post"
    assert {"personal_ip_metrics_aggregate", "personal_ip_sync_douyin_post"} <= names
