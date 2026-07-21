from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest

from deerflow.config.database_config import DatabaseConfig
from deerflow.persistence.channel_connections.sql import ChannelCredentialCipher
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine_from_config
from deerflow.persistence.personal_ip_accounts import PersonalIPAccountRepository
from deerflow.persistence.personal_ip_metrics import PersonalIPMetricRepository
from deerflow.persistence.personal_ip_platform_connections import PersonalIPPlatformConnectionRepository
from deerflow.persistence.personal_ip_publish_receipts import PersonalIPPublishReceiptRepository
from deerflow.personal_ip.douyin_oauth import DouyinMiniAppOAuthClient
from deerflow.personal_ip.platform_metrics import (
    DouyinAuthorizedMetricCollectionService,
    DouyinVideoMetricCollector,
    PersonalIPMetricCollectionService,
    PlatformMetricCollectionError,
)

NOW = datetime(2026, 7, 22, 8, 0, tzinfo=UTC)


def _success_transport(request: httpx.Request) -> httpx.Response:
    assert request.url == httpx.URL("https://open.douyin.com/api/apps/v1/video/query/?open_id=open-123")
    assert request.headers["access-token"] == "secret-token"
    assert request.headers["content-type"] == "application/json"
    assert json.loads(request.content) == {"item_ids": ["item-1", "item-private", "item-missing"]}
    return httpx.Response(
        200,
        json={
            "err_no": 0,
            "err_msg": "",
            "log_id": "log-123",
            "data": {
                "extra": {"error_code": 0, "logid": "nested-log", "now": 1784707200000},
                "data": {
                    "list": [
                        {
                            "item_id": "item-1",
                            "create_time": 1784600000,
                            "video_status": 5,
                            "is_reviewed": True,
                            "statistics": {
                                "play_count": 300,
                                "digg_count": 20,
                                "comment_count": 10,
                                "share_count": 4,
                                "download_count": 2,
                                "forward_count": 1,
                            },
                        },
                        {
                            "item_id": "item-private",
                            "create_time": 0,
                            "statistics": {},
                        },
                    ]
                },
            },
        },
    )


@pytest.mark.asyncio
async def test_douyin_collector_calls_official_endpoint_and_preserves_coverage() -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(_success_transport)) as client:
        collector = DouyinVideoMetricCollector(
            access_token="secret-token",
            open_id="open-123",
            client=client,
            clock=lambda: NOW,
        )
        result = await collector.collect_video_snapshots(["item-1", "item-private", "item-missing"])

    assert result[0].external_item_id == "item-1"
    assert result[0].status == "observed"
    assert result[0].metrics == {
        "comments": 10,
        "downloads": 2,
        "forwards": 1,
        "likes": 20,
        "shares": 4,
        "views": 300,
    }
    assert result[0].coverage["provider_log_id"] == "log-123"
    assert result[1].status == "unavailable"
    assert result[1].coverage["reason"] == "private_or_unavailable"
    assert result[2].status == "unavailable"
    assert result[2].coverage["reason"] == "not_returned_or_private"


@pytest.mark.asyncio
async def test_douyin_collector_classifies_provider_error_without_leaking_token() -> None:
    def error_transport(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"err_no": 28001008, "err_msg": "access_token过期", "log_id": "log-expired"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(error_transport)) as client:
        collector = DouyinVideoMetricCollector(access_token="secret-token", open_id="open-123", client=client)
        with pytest.raises(PlatformMetricCollectionError) as captured:
            await collector.collect_video_snapshots(["item-1"])

    assert captured.value.category == "authentication"
    assert captured.value.retryable is False
    assert captured.value.provider_code == 28001008
    assert "secret-token" not in str(captured.value)


@pytest.mark.asyncio
async def test_collection_service_writes_official_snapshot_to_existing_receipt(tmp_path) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    accounts = PersonalIPAccountRepository(sf)
    receipts = PersonalIPPublishReceiptRepository(sf)
    metrics = PersonalIPMetricRepository(sf)
    account = await accounts.create(owner_user_id="user-1", platform="douyin", display_name="抖音账号")
    receipt = await receipts.begin(
        owner_user_id="user-1",
        operation_key="publish:collector",
        idempotency_key="idem:collector",
        account_id=account["id"],
        preflight_id=None,
        executor="platform_api",
        request_payload={"caption": "测试"},
    )
    await receipts.record_attempt(
        receipt["id"],
        owner_user_id="user-1",
        attempt_key="published",
        status="published",
        result_payload={"item_id": "item-1"},
        external_post_id="item-1",
        occurred_at=datetime(2026, 7, 21, 8, 0, tzinfo=UTC),
    )

    def one_item_transport(_request: httpx.Request) -> httpx.Response:
        assert json.loads(_request.content) == {"item_ids": ["item-1"]}
        return httpx.Response(
            200,
            json={
                "err_no": 0,
                "log_id": "log-123",
                "data": {
                    "data": {
                        "list": [
                            {
                                "item_id": "item-1",
                                "create_time": 1784600000,
                                "statistics": {"play_count": 300, "digg_count": 20, "comment_count": 10, "share_count": 4},
                            }
                        ]
                    }
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(one_item_transport)) as client:
        collector = DouyinVideoMetricCollector(access_token="secret-token", open_id="open-123", client=client, clock=lambda: NOW)
        service = PersonalIPMetricCollectionService(metrics=metrics, publish_receipts=receipts)
        observation = await service.collect_published_post(
            owner_user_id="user-1",
            account_id=account["id"],
            publish_receipt_id=receipt["id"],
            observation_key="douyin:item-1:2026-07-22T08:00:00Z",
            collector=collector,
        )

    assert observation["source"] == "platform_api"
    assert observation["metric_mode"] == "snapshot"
    assert observation["metrics"]["views"] == 300
    assert observation["coverage"]["scope"] == "ma.video.bind"
    await close_engine()


@pytest.mark.asyncio
async def test_authorized_collection_refreshes_expired_token_server_side_and_retries(tmp_path) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    accounts = PersonalIPAccountRepository(sf)
    receipts = PersonalIPPublishReceiptRepository(sf)
    metrics = PersonalIPMetricRepository(sf)
    connections = PersonalIPPlatformConnectionRepository(
        sf,
        cipher=ChannelCredentialCipher.from_key("test-only-credential-key"),
    )
    account = await accounts.create(owner_user_id="user-1", platform="douyin", display_name="抖音账号")
    receipt = await receipts.begin(
        owner_user_id="user-1",
        operation_key="publish:authorized-collector",
        idempotency_key="idem:authorized-collector",
        account_id=account["id"],
        preflight_id=None,
        executor="platform_api",
        request_payload={"caption": "测试"},
    )
    await receipts.record_attempt(
        receipt["id"],
        owner_user_id="user-1",
        attempt_key="published",
        status="published",
        result_payload={"item_id": "item-1"},
        external_post_id="item-1",
        occurred_at=datetime(2026, 7, 21, 8, 0, tzinfo=UTC),
    )
    connection = await connections.store_grant(
        owner_user_id="user-1",
        account_id=account["id"],
        platform="douyin",
        external_user_id="mini-open-id",
        oauth_open_id="oauth-open-id",
        access_token="act.expired",
        refresh_token="rft.secret",
        scopes=["ma.video.bind"],
        access_expires_at=datetime(2026, 7, 20, 8, 0, tzinfo=UTC),
        refresh_expires_at=datetime(2026, 8, 20, 8, 0, tzinfo=UTC),
        now=datetime(2026, 7, 1, 8, 0, tzinfo=UTC),
    )
    calls: list[str] = []

    def transport(request: httpx.Request) -> httpx.Response:
        if request.url == httpx.URL("https://open.douyin.com/oauth/refresh_token/"):
            calls.append("refresh")
            assert b"refresh_token=rft.secret" in request.content
            return httpx.Response(
                200,
                json={
                    "data": {
                        "access_token": "act.new",
                        "refresh_token": "rft.secret",
                        "open_id": "oauth-open-id",
                        "error_code": 0,
                        "expires_in": 1_296_000,
                        "refresh_expires_in": 2_592_000,
                        "scope": "ma.video.bind",
                    },
                    "message": "success",
                },
            )
        token = request.headers["access-token"]
        calls.append(token)
        if token == "act.expired":
            return httpx.Response(
                200,
                json={"err_no": 28001008, "err_msg": "access_token过期", "log_id": "expired-log"},
            )
        assert token == "act.new"
        return httpx.Response(
            200,
            json={
                "err_no": 0,
                "log_id": "fresh-log",
                "data": {
                    "data": {
                        "list": [
                            {
                                "item_id": "item-1",
                                "create_time": 1784600000,
                                "statistics": {
                                    "play_count": 900,
                                    "digg_count": 50,
                                    "comment_count": 20,
                                    "share_count": 8,
                                },
                            }
                        ]
                    }
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http_client:
        service = DouyinAuthorizedMetricCollectionService(
            connections=connections,
            metrics=metrics,
            publish_receipts=receipts,
            oauth_client=DouyinMiniAppOAuthClient(
                app_id="tt-app-id",
                app_secret="app-secret",
                client=http_client,
            ),
            http_client=http_client,
            clock=lambda: NOW,
        )
        observation = await service.collect_published_post(
            owner_user_id="user-1",
            connection_id=connection["id"],
            publish_receipt_id=receipt["id"],
            observation_key="douyin:item-1:authorized-refresh",
        )

    assert calls == ["act.expired", "refresh", "act.new"]
    assert observation["metrics"]["views"] == 900
    credentials = await connections.get_credentials(connection["id"], owner_user_id="user-1")
    assert credentials == {"access_token": "act.new", "refresh_token": "rft.secret"}
    await close_engine()


@pytest.mark.asyncio
async def test_consecutive_official_snapshots_derive_a_partial_exact_interval_delta(tmp_path) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    accounts = PersonalIPAccountRepository(sf)
    receipts = PersonalIPPublishReceiptRepository(sf)
    metrics = PersonalIPMetricRepository(sf)
    connections = PersonalIPPlatformConnectionRepository(
        sf,
        cipher=ChannelCredentialCipher.from_key("test-only-credential-key"),
    )
    account = await accounts.create(owner_user_id="user-1", platform="douyin", display_name="抖音账号")
    receipt = await receipts.begin(
        owner_user_id="user-1",
        operation_key="publish:snapshot-delta",
        idempotency_key="idem:snapshot-delta",
        account_id=account["id"],
        preflight_id=None,
        executor="platform_api",
        request_payload={"caption": "测试"},
    )
    await receipts.record_attempt(
        receipt["id"],
        owner_user_id="user-1",
        attempt_key="published",
        status="published",
        result_payload={"item_id": "item-1"},
        external_post_id="item-1",
        occurred_at=datetime(2026, 7, 21, 0, 0, tzinfo=UTC),
    )
    connection = await connections.store_grant(
        owner_user_id="user-1",
        account_id=account["id"],
        platform="douyin",
        external_user_id="mini-open-id",
        oauth_open_id="oauth-open-id",
        access_token="act.valid",
        refresh_token="rft.valid",
        scopes=["ma.video.bind"],
        access_expires_at=datetime(2026, 8, 1, tzinfo=UTC),
        refresh_expires_at=datetime(2026, 8, 20, tzinfo=UTC),
        now=datetime(2026, 7, 1, tzinfo=UTC),
    )
    current_metrics = {"play_count": 100, "digg_count": 10, "comment_count": 2, "share_count": 1}

    def transport(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "err_no": 0,
                "log_id": "snapshot-log",
                "data": {
                    "data": {
                        "list": [
                            {
                                "item_id": "item-1",
                                "create_time": 1784600000,
                                "statistics": dict(current_metrics),
                            }
                        ]
                    }
                },
            },
        )

    observed_at = datetime(2026, 7, 21, 0, 5, tzinfo=UTC)

    def clock() -> datetime:
        return observed_at

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http_client:
        service = DouyinAuthorizedMetricCollectionService(
            connections=connections,
            metrics=metrics,
            publish_receipts=receipts,
            oauth_client=DouyinMiniAppOAuthClient(
                app_id="tt-app-id",
                app_secret="app-secret",
                client=http_client,
            ),
            http_client=http_client,
            clock=clock,
        )
        baseline = await service.collect_published_post(
            owner_user_id="user-1",
            connection_id=connection["id"],
            publish_receipt_id=receipt["id"],
            observation_key="douyin:item-1:baseline",
        )
        current_metrics.update(play_count=160, digg_count=16, comment_count=5, share_count=3)
        observed_at = datetime(2026, 7, 21, 12, 5, tzinfo=UTC)
        current = await service.collect_published_post(
            owner_user_id="user-1",
            connection_id=connection["id"],
            publish_receipt_id=receipt["id"],
            observation_key="douyin:item-1:current",
        )

    assert baseline["derived_delta"] is None
    delta = current["derived_delta"]
    assert delta is not None
    assert delta["metric_mode"] == "delta"
    assert delta["status"] == "partial"
    assert delta["metrics"] == {"comments": 3, "likes": 6, "shares": 2, "views": 60}
    assert delta["window_started_at"] == "2026-07-21T00:05:00+00:00"
    assert delta["window_ended_at"] == "2026-07-21T12:05:00+00:00"
    assert delta["coverage"]["scope_limit"] == "tracked_post_only"

    aggregate = await metrics.aggregate(
        owner_user_id="user-1",
        window_started_at=datetime(2026, 7, 21, 0, 0, tzinfo=UTC),
        window_ended_at=datetime(2026, 7, 22, 0, 0, tzinfo=UTC),
    )
    assert aggregate["totals"]["views"] == 60
    assert aggregate["coverage"]["partial_account_ids"] == [account["id"]]
    await close_engine()
