from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from app.gateway.routers import personal_ip_content as router_module


async def _current_user(_request):
    return SimpleNamespace(id="owner-1")


@pytest.mark.asyncio
async def test_content_router_derives_owner_and_exposes_lineage(monkeypatch) -> None:
    repo = SimpleNamespace(
        create=AsyncMock(return_value={"content_work": {"id": "content-work-1"}, "replayed": False}),
        list=AsyncMock(return_value=[{"id": "content-work-1"}]),
        get_lineage=AsyncMock(return_value={"content_work": {"id": "content-work-1"}, "script_versions": []}),
        append=AsyncMock(return_value={"content_work_id": "content-work-1", "script_version": {"id": "script-1"}}),
        archive=AsyncMock(return_value={"id": "content-work-1", "status": "archived"}),
    )
    app = FastAPI()
    app.state.personal_ip_content_repo = repo
    app.include_router(router_module.router)
    monkeypatch.setattr(router_module, "get_current_user_from_request", _current_user)

    create_body = {
        "idempotency_key": "run-1:tool-1",
        "title": "零启动内容",
        "entry_route": "zero_start",
        "objective": {"desired_change": "让观众理解一个选择"},
    }
    append_body = {
        "idempotency_key": "run-2:tool-1",
        "direction": {
            "premise": "一个选择",
            "audience_situation": "正在犹豫的人",
            "core_tension": "两种需要无法同时满足",
            "content_promise": "看清代价",
            "creative_route": "事实口述",
            "rationale": "只使用明确归因的事实。",
            "truth_mode": "factual",
        },
    }

    async with httpx.AsyncClient(base_url="http://test", transport=httpx.ASGITransport(app=app)) as client:
        created = await client.post("/api/personal-ip/content-works", json=create_body)
        listed = await client.get("/api/personal-ip/content-works")
        fetched = await client.get("/api/personal-ip/content-works/content-work-1")
        appended = await client.post("/api/personal-ip/content-works/content-work-1/versions", json=append_body)
        archived = await client.post("/api/personal-ip/content-works/content-work-1/archive")

    assert created.status_code == 201
    assert listed.status_code == 200
    assert fetched.status_code == 200
    assert appended.status_code == 201
    assert archived.status_code == 200
    repo.create.assert_awaited_once()
    assert repo.create.await_args.kwargs["owner_user_id"] == "owner-1"
    repo.get_lineage.assert_awaited_once_with("content-work-1", owner_user_id="owner-1")
    assert repo.append.await_args.kwargs["owner_user_id"] == "owner-1"
    repo.archive.assert_awaited_once_with("content-work-1", owner_user_id="owner-1")


@pytest.mark.asyncio
async def test_content_router_rejects_cross_reference_conflict(monkeypatch) -> None:
    repo = SimpleNamespace(
        append=AsyncMock(side_effect=ValueError("direction version does not belong to this Owner and content work")),
    )
    app = FastAPI()
    app.state.personal_ip_content_repo = repo
    app.include_router(router_module.router)
    monkeypatch.setattr(router_module, "get_current_user_from_request", _current_user)

    body = {
        "idempotency_key": "run-2:tool-2",
        "script": {
            "title": "事实稿",
            "story_mode": "factual",
            "script_text": "Owner 表示今天完成了第一步。",
            "direction_version_id": "direction-other-owner",
            "claim_basis": [
                {
                    "claim": "今天完成了第一步",
                    "state": "user_asserted",
                    "usage": "attributed_fact",
                }
            ],
        },
    }
    async with httpx.AsyncClient(base_url="http://test", transport=httpx.ASGITransport(app=app)) as client:
        response = await client.post("/api/personal-ip/content-works/content-work-1/versions", json=body)

    assert response.status_code == 409
    assert "does not belong" in response.json()["detail"]
