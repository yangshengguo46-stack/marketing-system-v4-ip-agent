from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from app.gateway.routers import personal_ip_retrospectives as router_module


@pytest.mark.asyncio
async def test_retrospective_router_seals_owner_scoped_evidence(monkeypatch) -> None:
    repository = SimpleNamespace(
        seal=AsyncMock(return_value={"id": "retro-1", "status": "measured"}),
        list=AsyncMock(return_value=[{"id": "retro-1"}]),
    )
    app = FastAPI()
    app.state.personal_ip_retrospective_repo = repository
    app.include_router(router_module.router)

    async def current_user(_request):
        return SimpleNamespace(id="user-1")

    monkeypatch.setattr(router_module, "get_current_user_from_request", current_user)
    async with httpx.AsyncClient(base_url="http://test", transport=httpx.ASGITransport(app=app)) as client:
        created = await client.post(
            "/api/personal-ip/retrospectives",
            json={
                "review_key": "retro:post-1:t+1d",
                "publish_receipt_id": "publish-1",
                "horizon": "t+1d",
                "metric_observation_ids": ["metric-1"],
            },
        )
        listed = await client.get("/api/personal-ip/retrospectives")

    assert created.status_code == 201
    assert listed.status_code == 200
    assert repository.seal.await_args.kwargs["owner_user_id"] == "user-1"
    assert repository.seal.await_args.kwargs["metric_observation_ids"] == ["metric-1"]
    assert repository.list.await_args.args == ("user-1",)


@pytest.mark.asyncio
async def test_retrospective_router_maps_conflicting_evidence_to_409(monkeypatch) -> None:
    repository = SimpleNamespace(
        seal=AsyncMock(side_effect=ValueError("review key or publish horizon already seals different evidence")),
    )
    app = FastAPI()
    app.state.personal_ip_retrospective_repo = repository
    app.include_router(router_module.router)

    async def current_user(_request):
        return SimpleNamespace(id="user-1")

    monkeypatch.setattr(router_module, "get_current_user_from_request", current_user)
    async with httpx.AsyncClient(base_url="http://test", transport=httpx.ASGITransport(app=app)) as client:
        response = await client.post(
            "/api/personal-ip/retrospectives",
            json={
                "review_key": "duplicate",
                "publish_receipt_id": "publish-1",
                "horizon": "t+1d",
                "metric_observation_ids": ["metric-1"],
            },
        )

    assert response.status_code == 409
