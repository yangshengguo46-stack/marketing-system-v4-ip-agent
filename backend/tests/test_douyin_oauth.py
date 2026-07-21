from __future__ import annotations

import json

import httpx
import pytest

from deerflow.personal_ip.douyin_oauth import DouyinMiniAppOAuthClient, DouyinOAuthError


@pytest.mark.asyncio
async def test_douyin_mini_app_oauth_exchanges_permission_ticket_and_login_code() -> None:
    def transport(request: httpx.Request) -> httpx.Response:
        if request.url == httpx.URL("https://open.douyin.com/oauth/access_token/"):
            form = dict(item.split("=", 1) for item in request.content.decode().split("&"))
            assert form == {
                "client_key": "tt-app-id",
                "client_secret": "app-secret",
                "code": "permission-ticket",
                "grant_type": "authorization_code",
            }
            return httpx.Response(
                200,
                json={
                    "data": {
                        "access_token": "act.secret",
                        "error_code": 0,
                        "expires_in": 1_296_000,
                        "open_id": "oauth-open-id",
                        "refresh_expires_in": 2_592_000,
                        "refresh_token": "rft.secret",
                        "scope": "ma.video.bind",
                    },
                    "message": "success",
                },
            )
        assert request.url == httpx.URL("https://developer.toutiao.com/api/apps/v2/jscode2session")
        assert json.loads(request.content) == {
            "appid": "tt-app-id",
            "secret": "app-secret",
            "code": "login-code",
        }
        return httpx.Response(
            200,
            json={
                "err_no": 0,
                "err_tips": "success",
                "data": {"openid": "mini-open-id", "unionid": "union-id", "session_key": "session-secret"},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http_client:
        client = DouyinMiniAppOAuthClient(app_id="tt-app-id", app_secret="app-secret", client=http_client)
        grant = await client.exchange_permission_ticket("permission-ticket")
        identity = await client.exchange_login_code("login-code")

    assert grant.access_token == "act.secret"
    assert grant.refresh_token == "rft.secret"
    assert grant.oauth_open_id == "oauth-open-id"
    assert grant.scopes == ["ma.video.bind"]
    assert identity.open_id == "mini-open-id"
    assert identity.union_id == "union-id"
    assert not hasattr(identity, "session_key")


@pytest.mark.asyncio
async def test_douyin_oauth_refreshes_and_sanitizes_provider_errors() -> None:
    def success_transport(request: httpx.Request) -> httpx.Response:
        assert request.url == httpx.URL("https://open.douyin.com/oauth/refresh_token/")
        assert b"refresh_token=rft.old" in request.content
        return httpx.Response(
            200,
            json={
                "data": {
                    "access_token": "act.new",
                    "error_code": 0,
                    "expires_in": "1296000",
                    "open_id": "oauth-open-id",
                    "refresh_expires_in": "2592000",
                    "refresh_token": "rft.old",
                    "scope": "ma.video.bind",
                },
                "message": "success",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(success_transport)) as http_client:
        client = DouyinMiniAppOAuthClient(app_id="tt-app-id", app_secret="app-secret", client=http_client)
        grant = await client.refresh("rft.old")
    assert grant.access_token == "act.new"
    assert grant.expires_in == 1_296_000

    def error_transport(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": {"error_code": 10010, "description": "refresh_token rft.leaked 已过期"}, "message": "error"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(error_transport)) as http_client:
        client = DouyinMiniAppOAuthClient(app_id="tt-app-id", app_secret="app-secret", client=http_client)
        with pytest.raises(DouyinOAuthError) as captured:
            await client.refresh("rft.leaked")
    assert captured.value.category == "reauthorization_required"
    assert captured.value.provider_code == 10010
    assert "rft.leaked" not in str(captured.value)


@pytest.mark.asyncio
async def test_douyin_oauth_rejects_empty_success_credentials() -> None:
    def transport(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": {
                    "access_token": "",
                    "refresh_token": "",
                    "open_id": "",
                    "error_code": 0,
                    "expires_in": 1_296_000,
                    "refresh_expires_in": 2_592_000,
                    "scope": "ma.video.bind",
                },
                "message": "success",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http_client:
        client = DouyinMiniAppOAuthClient(app_id="tt-app-id", app_secret="app-secret", client=http_client)
        with pytest.raises(DouyinOAuthError) as captured:
            await client.exchange_permission_ticket("permission-ticket")
    assert captured.value.category == "invalid_response"
