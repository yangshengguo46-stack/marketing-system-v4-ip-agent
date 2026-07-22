from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from app.gateway.routers import personal_ip_video_productions as router_module


@pytest.mark.asyncio
async def test_video_production_router_begins_and_appends_stage_receipt(monkeypatch) -> None:
    repository = SimpleNamespace(
        begin=AsyncMock(return_value={"id": "video-production-1", "status": "draft"}),
        append_event=AsyncMock(return_value={"id": "video-production-1", "status": "running"}),
    )
    app = FastAPI()
    app.state.personal_ip_video_production_repo = repository
    app.include_router(router_module.router)

    async def current_user(_request):
        return SimpleNamespace(id="user-1")

    monkeypatch.setattr(router_module, "get_current_user_from_request", current_user)
    async with httpx.AsyncClient(base_url="http://test", transport=httpx.ASGITransport(app=app)) as client:
        created = await client.post(
            "/api/personal-ip/video-productions",
            json={
                "operation_key": "video:1",
                "title": "一句话微电影",
                "subject_id": None,
                "target_account_ids": [],
                "source_kind": "idea",
                "source": {"idea": "一个智能体学会理解人"},
                "delivery_spec": {"aspect_ratio": "16:9"},
                "provider_policy": {"video": ["seedance"]},
                "budget": {"currency": "CNY", "hard_limit": 100},
            },
        )
        event = await client.post(
            "/api/personal-ip/video-productions/video-production-1/events",
            json={
                "event_key": "storyboard:v1",
                "event_type": "storyboard_sealed",
                "status": "succeeded",
                "entity_type": "production",
                "entity_id": "video-production-1",
                "payload": {"shots": 12},
                "input_refs": ["artifact://blueprint-v1.json"],
                "output_refs": ["artifact://storyboard-v1.json"],
                "provider": "doubao",
                "model": "doubao-seed-1-8",
                "cost": {"currency": "CNY", "amount": 0.1},
                "occurred_at": "2026-07-22T05:00:00Z",
            },
        )

    assert created.status_code == 201
    assert event.status_code == 200
    assert repository.begin.await_args.kwargs["owner_user_id"] == "user-1"
    assert repository.append_event.await_args.kwargs["event_type"] == "storyboard_sealed"


@pytest.mark.asyncio
async def test_video_production_router_rejects_unknown_event_type(monkeypatch) -> None:
    repository = SimpleNamespace(append_event=AsyncMock())
    app = FastAPI()
    app.state.personal_ip_video_production_repo = repository
    app.include_router(router_module.router)

    async def current_user(_request):
        return SimpleNamespace(id="user-1")

    monkeypatch.setattr(router_module, "get_current_user_from_request", current_user)
    async with httpx.AsyncClient(base_url="http://test", transport=httpx.ASGITransport(app=app)) as client:
        response = await client.post(
            "/api/personal-ip/video-productions/video-production-1/events",
            json={
                "event_key": "unsafe",
                "event_type": "run_arbitrary_shell",
                "status": "succeeded",
                "entity_type": "production",
                "entity_id": "video-production-1",
                "payload": {},
            },
        )

    assert response.status_code == 422
    repository.append_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_video_production_router_returns_ledger_derived_workbench(monkeypatch) -> None:
    repository = SimpleNamespace(
        get=AsyncMock(
            return_value={
                "id": "video-production-1",
                "title": "本地回执验收",
                "status": "running",
                "current_stage": "blueprint",
                "source_kind": "script",
                "source": {"script": "test"},
                "delivery_spec": {},
                "provider_policy": {},
                "budget": {},
                "events": [],
            }
        )
    )
    app = FastAPI()
    app.state.personal_ip_video_production_repo = repository
    app.include_router(router_module.router)

    async def current_user(_request):
        return SimpleNamespace(id="user-1")

    monkeypatch.setattr(router_module, "get_current_user_from_request", current_user)
    async with httpx.AsyncClient(base_url="http://test", transport=httpx.ASGITransport(app=app)) as client:
        response = await client.get("/api/personal-ip/video-productions/video-production-1/workbench")

    assert response.status_code == 200
    assert response.json()["contract_version"] == "personal-ip-video-workbench-v1"
    repository.get.assert_awaited_once_with("video-production-1", owner_user_id="user-1")
