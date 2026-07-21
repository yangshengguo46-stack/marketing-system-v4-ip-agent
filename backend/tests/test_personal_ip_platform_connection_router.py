from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from app.gateway.routers import personal_ip_platform_connections as router_module
from deerflow.personal_ip.douyin_oauth import DouyinMiniAppIdentity, DouyinOAuthGrant


@pytest.mark.asyncio
async def test_douyin_authorization_session_and_completion_never_return_credentials(monkeypatch) -> None:
    repository = SimpleNamespace(
        create_oauth_state=AsyncMock(
            return_value={
                "state": "opaque-state-long-enough",
                "expires_at": "2026-07-21T12:10:00Z",
                "requested_scopes": ["ma.video.bind"],
            }
        ),
        consume_oauth_state=AsyncMock(
            return_value={
                "owner_user_id": "user-1",
                "account_id": "acct-1",
                "platform": "douyin",
                "requested_scopes": ["ma.video.bind"],
            }
        ),
        store_grant=AsyncMock(
            return_value={
                "id": "platform-conn-1",
                "account_id": "acct-1",
                "platform": "douyin",
                "status": "connected",
                "external_user_id": "mini-open-id",
                "scopes": ["ma.video.bind"],
            }
        ),
    )
    oauth_client = SimpleNamespace(
        app_id="tt-app-id",
        exchange_permission_ticket=AsyncMock(
            return_value=DouyinOAuthGrant(
                access_token="act.must-not-leak",
                refresh_token="rft.must-not-leak",
                oauth_open_id="oauth-open-id",
                expires_in=1_296_000,
                refresh_expires_in=2_592_000,
                scopes=["ma.video.bind"],
            )
        ),
        exchange_login_code=AsyncMock(return_value=DouyinMiniAppIdentity(open_id="mini-open-id", union_id="union-id")),
    )
    app = FastAPI()
    app.state.personal_ip_platform_connection_repo = repository
    app.include_router(router_module.router)

    async def current_user(_request):
        return SimpleNamespace(id="user-1")

    monkeypatch.setattr(router_module, "get_current_user_from_request", current_user)
    monkeypatch.setattr(router_module, "_get_douyin_oauth_client", lambda: oauth_client)
    monkeypatch.setattr(router_module, "_utc_now", lambda: datetime(2026, 7, 21, 12, 0, tzinfo=UTC))

    async with httpx.AsyncClient(base_url="http://test", transport=httpx.ASGITransport(app=app)) as client:
        started = await client.post(
            "/api/personal-ip/platform-connections/douyin/authorization-sessions",
            json={"account_id": "acct-1"},
        )
        completed = await client.post(
            "/api/personal-ip/platform-connections/douyin/authorization-sessions/complete",
            json={
                "state": "opaque-state-long-enough",
                "authorization_ticket": "permission-ticket",
                "login_code": "login-code",
            },
        )

    assert started.status_code == 201
    assert started.json()["authorization_channel"] == "douyin_mini_app"
    assert started.json()["mini_app_api"] == "tt.showDouyinOpenAuth"
    assert started.json()["app_id"] == "tt-app-id"
    assert started.json()["scope_list"] == ["ma.video.bind"]
    assert "secret" not in str(started.json()).lower()

    assert completed.status_code == 200
    assert completed.json()["status"] == "connected"
    response_text = completed.text
    assert "act.must-not-leak" not in response_text
    assert "rft.must-not-leak" not in response_text
    store_kwargs = repository.store_grant.await_args.kwargs
    assert store_kwargs["owner_user_id"] == "user-1"
    assert store_kwargs["account_id"] == "acct-1"
    assert store_kwargs["external_user_id"] == "mini-open-id"
    assert store_kwargs["access_token"] == "act.must-not-leak"


@pytest.mark.asyncio
async def test_platform_connection_refresh_and_disconnect_are_owner_scoped(monkeypatch) -> None:
    connection = {
        "id": "platform-conn-1",
        "account_id": "acct-1",
        "platform": "douyin",
        "status": "connected",
        "external_user_id": "mini-open-id",
        "oauth_open_id": "oauth-open-id",
        "scopes": ["ma.video.bind"],
    }
    repository = SimpleNamespace(
        get=AsyncMock(return_value=connection),
        get_credentials=AsyncMock(return_value={"access_token": "act.old", "refresh_token": "rft.must-not-leak"}),
        store_grant=AsyncMock(return_value={**connection, "token_version": 2}),
        revoke=AsyncMock(return_value=True),
        list=AsyncMock(return_value=[connection]),
    )
    oauth_client = SimpleNamespace(
        app_id="tt-app-id",
        refresh=AsyncMock(
            return_value=DouyinOAuthGrant(
                access_token="act.new",
                refresh_token="rft.must-not-leak",
                oauth_open_id="oauth-open-id",
                expires_in=1_296_000,
                refresh_expires_in=2_592_000,
                scopes=["ma.video.bind"],
            )
        ),
    )
    app = FastAPI()
    app.state.personal_ip_platform_connection_repo = repository
    app.include_router(router_module.router)

    async def current_user(_request):
        return SimpleNamespace(id="user-1")

    monkeypatch.setattr(router_module, "get_current_user_from_request", current_user)
    monkeypatch.setattr(router_module, "_get_douyin_oauth_client", lambda: oauth_client)
    monkeypatch.setattr(router_module, "_utc_now", lambda: datetime(2026, 7, 21, 12, 0, tzinfo=UTC))

    async with httpx.AsyncClient(base_url="http://test", transport=httpx.ASGITransport(app=app)) as client:
        listed = await client.get("/api/personal-ip/platform-connections")
        refreshed = await client.post("/api/personal-ip/platform-connections/platform-conn-1/refresh")
        disconnected = await client.delete("/api/personal-ip/platform-connections/platform-conn-1")

    assert listed.status_code == 200
    assert refreshed.status_code == 200
    assert disconnected.status_code == 204
    assert "act.new" not in refreshed.text
    assert "rft.must-not-leak" not in refreshed.text
    repository.get.assert_awaited_once_with("platform-conn-1", owner_user_id="user-1")
    repository.get_credentials.assert_awaited_once_with("platform-conn-1", owner_user_id="user-1")
    repository.revoke.assert_awaited_once()


@pytest.mark.asyncio
async def test_douyin_completion_fails_closed_when_granted_scope_is_missing(monkeypatch) -> None:
    repository = SimpleNamespace(
        consume_oauth_state=AsyncMock(
            return_value={
                "owner_user_id": "user-1",
                "account_id": "acct-1",
                "platform": "douyin",
                "requested_scopes": ["ma.video.bind"],
            }
        ),
        store_grant=AsyncMock(),
    )
    oauth_client = SimpleNamespace(
        exchange_permission_ticket=AsyncMock(
            return_value=DouyinOAuthGrant(
                access_token="act.secret",
                refresh_token="rft.secret",
                oauth_open_id="oauth-open-id",
                expires_in=1_296_000,
                refresh_expires_in=2_592_000,
                scopes=[],
            )
        ),
        exchange_login_code=AsyncMock(return_value=DouyinMiniAppIdentity(open_id="mini-open-id", union_id="union-id")),
    )
    app = FastAPI()
    app.state.personal_ip_platform_connection_repo = repository
    app.include_router(router_module.router)

    async def current_user(_request):
        return SimpleNamespace(id="user-1")

    monkeypatch.setattr(router_module, "get_current_user_from_request", current_user)
    monkeypatch.setattr(router_module, "_get_douyin_oauth_client", lambda: oauth_client)

    async with httpx.AsyncClient(base_url="http://test", transport=httpx.ASGITransport(app=app)) as client:
        response = await client.post(
            "/api/personal-ip/platform-connections/douyin/authorization-sessions/complete",
            json={
                "state": "opaque-state-long-enough",
                "authorization_ticket": "permission-ticket",
                "login_code": "login-code",
            },
        )

    assert response.status_code == 422
    repository.store_grant.assert_not_awaited()
