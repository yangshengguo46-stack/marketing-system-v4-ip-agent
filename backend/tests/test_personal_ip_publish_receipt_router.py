from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from app.gateway.routers import personal_ip_publish_receipts as router_module


@pytest.mark.asyncio
async def test_publish_router_begins_operation_and_appends_attempt(monkeypatch) -> None:
    repository = SimpleNamespace(
        begin=AsyncMock(return_value={"id": "publish-1", "status": "planned"}),
        get=AsyncMock(return_value={"id": "publish-1", "executor": "platform_api"}),
        record_attempt=AsyncMock(return_value={"id": "publish-1", "status": "published"}),
    )
    app = FastAPI()
    app.state.personal_ip_publish_receipt_repo = repository
    app.include_router(router_module.router)

    async def current_user(_request):
        return SimpleNamespace(id="user-1")

    monkeypatch.setattr(router_module, "get_current_user_from_request", current_user)
    async with httpx.AsyncClient(base_url="http://test", transport=httpx.ASGITransport(app=app)) as client:
        created = await client.post(
            "/api/personal-ip/publish-receipts",
            json={
                "operation_key": "publish:draft-1:douyin",
                "idempotency_key": "idem-draft-1-douyin",
                "account_id": "acct-1",
                "preflight_id": "preflight-1",
                "executor": "platform_api",
                "request": {"caption": "候选文案"},
            },
        )
        attempted = await client.post(
            "/api/personal-ip/publish-receipts/publish-1/attempts",
            json={
                "attempt_key": "attempt-1",
                "status": "published",
                "result": {"post_id": "post-1"},
                "external_post_id": "post-1",
                "external_url": "https://example.com/post-1",
                "occurred_at": "2026-07-21T08:00:00Z",
            },
        )

    assert created.status_code == 201
    assert attempted.status_code == 200
    begin_kwargs = repository.begin.await_args.kwargs
    assert begin_kwargs["owner_user_id"] == "user-1"
    assert begin_kwargs["account_id"] == "acct-1"
    attempt_kwargs = repository.record_attempt.await_args.kwargs
    assert attempt_kwargs["status"] == "published"
    assert attempt_kwargs["occurred_at"].isoformat() == "2026-07-21T08:00:00+00:00"


@pytest.mark.asyncio
async def test_publish_router_requires_composite_tools_for_browser_receipts(monkeypatch) -> None:
    repository = SimpleNamespace(
        begin=AsyncMock(),
        get=AsyncMock(return_value={"id": "publish-1", "executor": "browser"}),
        record_attempt=AsyncMock(),
    )
    app = FastAPI()
    app.state.personal_ip_publish_receipt_repo = repository
    app.include_router(router_module.router)

    async def current_user(_request):
        return SimpleNamespace(id="user-1")

    monkeypatch.setattr(router_module, "get_current_user_from_request", current_user)
    async with httpx.AsyncClient(base_url="http://test", transport=httpx.ASGITransport(app=app)) as client:
        created = await client.post(
            "/api/personal-ip/publish-receipts",
            json={
                "operation_key": "publish:draft-1:browser",
                "idempotency_key": "idem-draft-1-browser",
                "account_id": "acct-1",
                "executor": "browser",
                "request": {"caption": "候选文案"},
            },
        )
        attempted = await client.post(
            "/api/personal-ip/publish-receipts/publish-1/attempts",
            json={
                "attempt_key": "attempt-1",
                "status": "published",
                "result": {"confirmation": "未经 live proof"},
                "external_post_id": "post-1",
            },
        )

    assert created.status_code == 422
    assert attempted.status_code == 422
    repository.begin.assert_not_awaited()
    repository.record_attempt.assert_not_awaited()


@pytest.mark.asyncio
async def test_publish_router_rejects_unsupported_executor_before_repository(monkeypatch) -> None:
    repository = SimpleNamespace(begin=AsyncMock())
    app = FastAPI()
    app.state.personal_ip_publish_receipt_repo = repository
    app.include_router(router_module.router)

    async def current_user(_request):
        return SimpleNamespace(id="user-1")

    monkeypatch.setattr(router_module, "get_current_user_from_request", current_user)
    async with httpx.AsyncClient(base_url="http://test", transport=httpx.ASGITransport(app=app)) as client:
        response = await client.post(
            "/api/personal-ip/publish-receipts",
            json={
                "operation_key": "publish:test",
                "idempotency_key": "idem-test",
                "account_id": "acct-1",
                "executor": "untrusted-script",
                "request": {"caption": "测试"},
            },
        )

    assert response.status_code == 422
    repository.begin.assert_not_awaited()
