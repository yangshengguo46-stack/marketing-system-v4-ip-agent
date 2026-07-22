from __future__ import annotations

import json
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from deerflow.personal_ip.runtime import PersonalIPRuntimeServices, configure_personal_ip_runtime
from deerflow.tools.builtins import (
    personal_ip_collect_douyin_browser_page_tool,
    personal_ip_metrics_aggregate_tool,
    personal_ip_performance_inventory_tool,
    personal_ip_record_browser_observation_tool,
    personal_ip_select_browser_account_tool,
    personal_ip_sync_douyin_portfolio_tool,
    personal_ip_sync_douyin_post_tool,
)
from deerflow.tools.builtins.personal_ip_tools import (
    _personal_ip_collect_douyin_browser_page,
    _personal_ip_metrics_aggregate,
    _personal_ip_performance_inventory,
    _personal_ip_record_browser_observation,
    _personal_ip_select_browser_account,
    _personal_ip_sync_douyin_portfolio,
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
    assert personal_ip_collect_douyin_browser_page_tool.name == "personal_ip_collect_douyin_browser_page"
    assert personal_ip_performance_inventory_tool.name == "personal_ip_performance_inventory"
    assert personal_ip_record_browser_observation_tool.name == "personal_ip_record_browser_observation"
    assert personal_ip_select_browser_account_tool.name == "personal_ip_select_browser_account"
    assert personal_ip_sync_douyin_portfolio_tool.name == "personal_ip_sync_douyin_portfolio"
    assert personal_ip_sync_douyin_post_tool.name == "personal_ip_sync_douyin_post"
    assert {
        "personal_ip_metrics_aggregate",
        "personal_ip_collect_douyin_browser_page",
        "personal_ip_performance_inventory",
        "personal_ip_record_browser_observation",
        "personal_ip_select_browser_account",
        "personal_ip_sync_douyin_portfolio",
        "personal_ip_sync_douyin_post",
    } <= names
    schema = personal_ip_metrics_aggregate_tool.tool_call_schema.model_json_schema()
    assert "account_id" not in schema.get("properties", {})


@pytest.mark.asyncio
async def test_collect_douyin_browser_page_tool_uses_account_profile_and_returns_evidence_reference(monkeypatch) -> None:
    accounts = SimpleNamespace(
        get=AsyncMock(
            return_value={
                "id": "acct-1",
                "platform": "douyin",
                "display_name": "抖音号",
                "status": "active",
            }
        )
    )
    observations = SimpleNamespace()
    configure_personal_ip_runtime(
        PersonalIPRuntimeServices(
            accounts=accounts,
            connections=SimpleNamespace(),
            metrics=SimpleNamespace(),
            publish_receipts=SimpleNamespace(),
            platform_observations=observations,
        )
    )
    collect = AsyncMock(
        return_value={
            "id": "platform-observation-1",
            "account_id": "acct-1",
            "platform": "douyin",
            "dataset": "dashboard",
            "status": "partial",
            "source_url": "https://creator.douyin.com/creator-micro/home",
            "records": [{"visible_text": "昨日播放 1200"}],
            "summary": {"visible_text_characters": 11},
            "coverage": {"pages_scanned": 1},
            "evidence_digest": "b" * 64,
        }
    )
    monkeypatch.setattr(
        "deerflow.tools.builtins.personal_ip_tools._douyin_browser_collection_service",
        lambda _services: SimpleNamespace(collect_creator_page=collect),
    )
    session = SimpleNamespace()

    @contextmanager
    def acquire(**kwargs):
        assert kwargs["owner_user_id"] == "user-1"
        assert kwargs["account"]["id"] == "acct-1"
        yield session

    monkeypatch.setattr("deerflow.tools.builtins.personal_ip_tools.acquire_account_browser_session", acquire)

    raw = await _personal_ip_collect_douyin_browser_page(
        SimpleNamespace(context={"user_id": "user-1"}),
        account_id="acct-1",
        observation_key="douyin:dashboard:2026-07-21T12",
        dataset="dashboard",
        target_url="",
    )
    payload = json.loads(raw)

    assert payload["status"] == "partial"
    assert payload["record_count"] == 1
    assert payload["evidence_digest"] == "b" * 64
    assert "visible_text" not in payload
    collect.assert_awaited_once_with(
        owner_user_id="user-1",
        account_id="acct-1",
        observation_key="douyin:dashboard:2026-07-21T12",
        dataset="dashboard",
        target_url=None,
        session=session,
    )


@pytest.mark.asyncio
async def test_record_browser_observation_tool_seals_detailed_business_data_without_credentials() -> None:
    observations = SimpleNamespace(
        record=AsyncMock(
            return_value={
                "id": "platform-observation-1",
                "account_id": "acct-1",
                "platform": "douyin",
                "dataset": "content_inventory",
                "status": "partial",
                "source_url": "https://creator.douyin.com/creator-micro/data/video",
                "records": [{"title": "第一条", "metrics": {"views": 1200}}],
                "summary": {"content_count": 1},
                "coverage": {"pages_scanned": 1, "has_more": True},
                "evidence_digest": "a" * 64,
            }
        )
    )
    configure_personal_ip_runtime(
        PersonalIPRuntimeServices(
            connections=SimpleNamespace(),
            metrics=SimpleNamespace(),
            publish_receipts=SimpleNamespace(),
            platform_observations=observations,
        )
    )

    raw = await _personal_ip_record_browser_observation(
        SimpleNamespace(context={"user_id": "user-1"}),
        observation_key="douyin:content:2026-07-21T12",
        account_id="acct-1",
        dataset="content_inventory",
        status="partial",
        source_url="https://creator.douyin.com/creator-micro/data/video",
        observed_at="2026-07-21T12:00:00+08:00",
        records=[{"title": "第一条", "metrics": {"views": 1200}}],
        summary={"content_count": 1},
        coverage={"pages_scanned": 1, "has_more": True},
        evidence={"capture_refs": ["artifact://browser/capture.png"]},
    )
    payload = json.loads(raw)

    assert payload == {
        "account_id": "acct-1",
        "coverage": {"has_more": True, "pages_scanned": 1},
        "dataset": "content_inventory",
        "evidence_digest": "a" * 64,
        "id": "platform-observation-1",
        "platform": "douyin",
        "record_count": 1,
        "source_url": "https://creator.douyin.com/creator-micro/data/video",
        "status": "partial",
        "summary": {"content_count": 1},
    }
    kwargs = observations.record.await_args.kwargs
    assert kwargs["owner_user_id"] == "user-1"
    assert kwargs["source"] == "browser"
    assert kwargs["records"][0]["metrics"]["views"] == 1200


@pytest.mark.asyncio
async def test_performance_inventory_lists_all_connections_and_published_receipts_without_tokens() -> None:
    connections = SimpleNamespace(
        list=AsyncMock(
            return_value=[
                {
                    "id": "platform-conn-1",
                    "account_id": "acct-1",
                    "platform": "douyin",
                    "status": "connected",
                    "scopes": ["ma.video.bind"],
                }
            ]
        )
    )
    receipts = SimpleNamespace(
        list=AsyncMock(
            return_value=[
                {
                    "id": "publish-1",
                    "account_id": "acct-1",
                    "platform": "douyin",
                    "status": "published",
                    "external_post_id": "item-1",
                    "published_at": "2026-07-21T08:00:00Z",
                    "request": {"caption": "must not be copied into inventory"},
                    "attempts": [{"result": {"access_token": "must-not-leak"}}],
                },
                {"id": "publish-planned", "account_id": "acct-2", "platform": "bilibili", "status": "planned"},
            ]
        )
    )
    configure_personal_ip_runtime(
        PersonalIPRuntimeServices(
            connections=connections,
            metrics=SimpleNamespace(),
            publish_receipts=receipts,
        )
    )
    result = await _personal_ip_performance_inventory(SimpleNamespace(context={"user_id": "user-1"}), published_limit=50)
    payload = json.loads(result)

    assert payload["status"] == "ok"
    assert payload["connections"][0]["id"] == "platform-conn-1"
    assert payload["published_receipts"] == [
        {
            "account_id": "acct-1",
            "external_post_id": "item-1",
            "id": "publish-1",
            "platform": "douyin",
            "published_at": "2026-07-21T08:00:00Z",
            "status": "published",
        }
    ]
    assert "must-not-leak" not in result
    connections.list.assert_awaited_once_with("user-1", include_revoked=False)
    receipts.list.assert_awaited_once_with("user-1", limit=50)


@pytest.mark.asyncio
async def test_portfolio_sync_collects_every_connected_douyin_publication_and_isolates_failures(monkeypatch) -> None:
    connections = SimpleNamespace(
        list=AsyncMock(
            return_value=[
                {"id": "conn-1", "account_id": "acct-1", "platform": "douyin", "status": "connected"},
                {"id": "conn-2", "account_id": "acct-2", "platform": "douyin", "status": "connected"},
                {"id": "conn-bili", "account_id": "acct-3", "platform": "bilibili", "status": "connected"},
            ]
        )
    )
    receipts = SimpleNamespace(
        list=AsyncMock(
            return_value=[
                {"id": "publish-1", "account_id": "acct-1", "platform": "douyin", "status": "published"},
                {"id": "publish-2", "account_id": "acct-2", "platform": "douyin", "status": "published"},
                {"id": "publish-no-connection", "account_id": "acct-4", "platform": "douyin", "status": "published"},
                {"id": "publish-bili", "account_id": "acct-3", "platform": "bilibili", "status": "published"},
            ]
        )
    )
    configure_personal_ip_runtime(
        PersonalIPRuntimeServices(
            connections=connections,
            metrics=SimpleNamespace(),
            publish_receipts=receipts,
        )
    )
    collect = AsyncMock(
        side_effect=[
            {
                "id": "metric-1",
                "account_id": "acct-1",
                "receipt_id": "publish-1",
                "status": "observed",
                "derived_delta": None,
            },
            ValueError("provider secret detail must not escape"),
        ]
    )
    monkeypatch.setattr(
        "deerflow.tools.builtins.personal_ip_tools._authorized_douyin_service",
        lambda _services: SimpleNamespace(collect_published_post=collect),
    )

    raw = await _personal_ip_sync_douyin_portfolio(
        SimpleNamespace(context={"user_id": "user-1"}),
        collection_key="hourly:2026-07-21T12+08:00",
        published_limit=500,
    )
    payload = json.loads(raw)

    assert payload["status"] == "partial"
    assert payload["synced_count"] == 1
    assert payload["baseline_count"] == 1
    assert payload["delta_count"] == 0
    assert payload["failed_count"] == 1
    assert payload["coverage"]["missing_connection_account_ids"] == ["acct-4"]
    assert payload["coverage"]["possibly_truncated"] is False
    assert payload["results"] == [
        {
            "account_id": "acct-1",
            "connection_id": "conn-1",
            "delta_id": None,
            "metric_id": "metric-1",
            "publish_receipt_id": "publish-1",
            "status": "observed",
        }
    ]
    assert payload["failures"] == [
        {
            "account_id": "acct-2",
            "category": "invalid_request",
            "connection_id": "conn-2",
            "publish_receipt_id": "publish-2",
            "retryable": False,
        }
    ]
    assert "secret" not in raw.lower()
    assert collect.await_count == 2
    for call in collect.await_args_list:
        assert call.kwargs["owner_user_id"] == "user-1"
        assert call.kwargs["observation_key"].startswith("portfolio-douyin:")
        assert len(call.kwargs["observation_key"]) == len("portfolio-douyin:") + 64
    connections.list.assert_awaited_once_with("user-1", include_revoked=False)
    receipts.list.assert_awaited_once_with("user-1", limit=500)


@pytest.mark.asyncio
async def test_select_browser_account_uses_an_account_scoped_persistent_profile(tmp_path, monkeypatch) -> None:
    from deerflow.config.paths import Paths
    from deerflow.personal_ip.browser_profiles import clear_browser_account_target, get_browser_account_target

    accounts = SimpleNamespace(
        get=AsyncMock(
            return_value={
                "id": "acct-youtube",
                "owner_user_id": "user-1",
                "platform": "youtube",
                "display_name": "YouTube 主账号",
                "status": "active",
            }
        )
    )
    configure_personal_ip_runtime(
        PersonalIPRuntimeServices(
            accounts=accounts,
            connections=SimpleNamespace(),
            metrics=SimpleNamespace(),
            publish_receipts=SimpleNamespace(),
        )
    )
    monkeypatch.setattr("deerflow.tools.builtins.personal_ip_tools.get_paths", lambda: Paths(tmp_path))
    runtime = SimpleNamespace(context={"user_id": "user-1", "thread_id": "thread-1"})
    clear_browser_account_target(owner_user_id="user-1", thread_id="thread-1")

    raw = await _personal_ip_select_browser_account(runtime, account_id="acct-youtube")
    payload = json.loads(raw)
    target = get_browser_account_target(owner_user_id="user-1", thread_id="thread-1")

    assert payload == {
        "account_id": "acct-youtube",
        "connection_mode": "browser_profile",
        "display_name": "YouTube 主账号",
        "platform": "youtube",
        "start_url": "https://studio.youtube.com/",
        "status": "ok",
    }
    assert target is not None
    assert target.session_key == "account:user-1:acct-youtube"
    assert target.user_data_dir == tmp_path / "users" / "user-1" / "browser-profiles" / "acct-youtube"
    assert target.user_data_dir.is_dir()
    assert "password" not in raw.lower()
    accounts.get.assert_awaited_once_with("acct-youtube", owner_user_id="user-1")
    clear_browser_account_target(owner_user_id="user-1", thread_id="thread-1")
