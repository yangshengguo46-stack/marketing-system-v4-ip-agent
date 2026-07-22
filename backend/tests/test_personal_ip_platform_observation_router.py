from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from app.gateway.routers import personal_ip_platform_observations as router_module


@pytest.mark.asyncio
async def test_platform_observation_router_records_detailed_business_data(monkeypatch) -> None:
    repository = SimpleNamespace(
        record=AsyncMock(
            return_value={
                "id": "platform-observation-1",
                "platform": "douyin",
                "records": [{"title": "第一条", "metrics": {"views": 1200}}],
            }
        )
    )
    app = FastAPI()
    app.state.personal_ip_platform_observation_repo = repository
    app.include_router(router_module.router)

    async def current_user(_request):
        return SimpleNamespace(id="user-1")

    monkeypatch.setattr(router_module, "get_current_user_from_request", current_user)
    async with httpx.AsyncClient(base_url="http://test", transport=httpx.ASGITransport(app=app)) as client:
        response = await client.post(
            "/api/personal-ip/platform-observations",
            json={
                "observation_key": "douyin:content:2026-07-21T12",
                "account_id": "acct-1",
                "dataset": "content_inventory",
                "source": "browser",
                "status": "partial",
                "source_url": "https://creator.douyin.com/creator-micro/data/video",
                "observed_at": "2026-07-21T12:00:00Z",
                "records": [{"title": "第一条", "metrics": {"views": 1200}}],
                "summary": {"content_count": 1},
                "coverage": {"pages_scanned": 1, "has_more": True},
                "evidence": {"capture_refs": ["artifact://browser/capture.png"]},
            },
        )

    assert response.status_code == 201
    assert response.json()["records"][0]["metrics"]["views"] == 1200
    kwargs = repository.record.await_args.kwargs
    assert kwargs["owner_user_id"] == "user-1"
    assert kwargs["account_id"] == "acct-1"


@pytest.mark.asyncio
async def test_platform_observation_router_never_accepts_expanded_owner_or_credentials(monkeypatch) -> None:
    repository = SimpleNamespace(record=AsyncMock())
    app = FastAPI()
    app.state.personal_ip_platform_observation_repo = repository
    app.include_router(router_module.router)

    async def current_user(_request):
        return SimpleNamespace(id="user-1")

    monkeypatch.setattr(router_module, "get_current_user_from_request", current_user)
    async with httpx.AsyncClient(base_url="http://test", transport=httpx.ASGITransport(app=app)) as client:
        response = await client.post(
            "/api/personal-ip/platform-observations",
            json={
                "owner_user_id": "user-2",
                "observation_key": "unsafe",
                "account_id": "acct-1",
                "dataset": "account_profile",
                "source": "browser",
                "status": "observed",
                "source_url": "https://creator.douyin.com/creator-micro/home",
                "observed_at": "2026-07-21T12:00:00Z",
                "records": [{"authorization": "Bearer raw-secret"}],
                "summary": {},
                "coverage": {"complete": True},
                "evidence": {},
            },
        )

        credential_response = await client.post(
            "/api/personal-ip/platform-observations",
            json={
                "observation_key": "unsafe-credential",
                "account_id": "acct-1",
                "dataset": "account_profile",
                "source": "browser",
                "status": "observed",
                "source_url": "https://creator.douyin.com/creator-micro/home",
                "observed_at": "2026-07-21T12:00:00Z",
                "records": [{"network": {"authorization": "Bearer raw-secret"}}],
                "summary": {},
                "coverage": {"complete": True},
                "evidence": {},
            },
        )

    assert response.status_code == 422
    assert credential_response.status_code == 422
    repository.record.assert_not_awaited()


@pytest.mark.asyncio
async def test_platform_observation_router_collects_current_douyin_creator_page(monkeypatch) -> None:
    account_repository = SimpleNamespace(
        get=AsyncMock(
            return_value={
                "id": "acct-1",
                "platform": "douyin",
                "display_name": "抖音号",
                "status": "active",
            }
        )
    )
    observation_repository = SimpleNamespace()
    collect = AsyncMock(
        return_value={
            "id": "platform-observation-1",
            "account_id": "acct-1",
            "platform": "douyin",
            "dataset": "dashboard",
            "status": "partial",
            "records": [{"visible_text": "昨日播放 1200"}],
        }
    )
    app = FastAPI()
    app.state.personal_ip_account_repo = account_repository
    app.state.personal_ip_platform_observation_repo = observation_repository
    app.include_router(router_module.router)

    async def current_user(_request):
        return SimpleNamespace(id="user-1")

    monkeypatch.setattr(router_module, "get_current_user_from_request", current_user)
    monkeypatch.setattr(
        router_module,
        "_douyin_browser_collection_service",
        lambda _request: SimpleNamespace(collect_creator_page=collect),
    )
    session = SimpleNamespace()

    @contextmanager
    def acquire(**kwargs):
        assert kwargs["owner_user_id"] == "user-1"
        yield session

    monkeypatch.setattr(router_module, "acquire_account_browser_session", acquire)

    async with httpx.AsyncClient(base_url="http://test", transport=httpx.ASGITransport(app=app)) as client:
        response = await client.post(
            "/api/personal-ip/platform-observations/collect/browser/douyin",
            json={
                "account_id": "acct-1",
                "observation_key": "douyin:dashboard:2026-07-21T12",
                "dataset": "dashboard",
            },
        )

    assert response.status_code == 201
    assert response.json()["records"][0]["visible_text"] == "昨日播放 1200"
    collect.assert_awaited_once_with(
        owner_user_id="user-1",
        account_id="acct-1",
        observation_key="douyin:dashboard:2026-07-21T12",
        dataset="dashboard",
        target_url=None,
        session=session,
    )


@pytest.mark.asyncio
async def test_platform_observation_router_collects_any_browser_first_account(monkeypatch) -> None:
    account_repository = SimpleNamespace(get=AsyncMock(return_value={"id": "acct-youtube", "platform": "youtube", "status": "active"}))
    collect = AsyncMock(
        return_value={
            "id": "platform-observation-youtube",
            "account_id": "acct-youtube",
            "platform": "youtube",
            "dataset": "dashboard",
            "status": "partial",
            "records": [],
        }
    )
    app = FastAPI()
    app.state.personal_ip_account_repo = account_repository
    app.state.personal_ip_platform_observation_repo = SimpleNamespace()
    app.include_router(router_module.router)

    async def current_user(_request):
        return SimpleNamespace(id="user-1")

    monkeypatch.setattr(router_module, "get_current_user_from_request", current_user)
    monkeypatch.setattr(
        router_module,
        "_browser_platform_collection_service",
        lambda _request: SimpleNamespace(collect_creator_page=collect),
    )
    session = SimpleNamespace()

    @contextmanager
    def acquire(**kwargs):
        assert kwargs["account"]["platform"] == "youtube"
        yield session

    monkeypatch.setattr(router_module, "acquire_account_browser_session", acquire)

    async with httpx.AsyncClient(base_url="http://test", transport=httpx.ASGITransport(app=app)) as client:
        response = await client.post(
            "/api/personal-ip/platform-observations/collect/browser",
            json={
                "account_id": "acct-youtube",
                "observation_key": "youtube:dashboard:2026-07-22T10",
                "dataset": "dashboard",
            },
        )

    assert response.status_code == 201
    assert response.json()["platform"] == "youtube"
    collect.assert_awaited_once_with(
        owner_user_id="user-1",
        account_id="acct-youtube",
        observation_key="youtube:dashboard:2026-07-22T10",
        dataset="dashboard",
        target_url=None,
        session=session,
    )
