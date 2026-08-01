from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from app.gateway.routers import personal_ip_evidence_promotions as router_module


@pytest.mark.asyncio
async def test_evidence_promotion_router_is_read_only_legacy_access(monkeypatch) -> None:
    repository = SimpleNamespace(
        list=AsyncMock(return_value=[{"id": "promotion-1", "status": "approved"}]),
        get=AsyncMock(return_value={"id": "promotion-1", "status": "approved"}),
        export_approved=AsyncMock(return_value={"contract_version": "personal-ip-approved-evidence-v1"}),
    )
    app = FastAPI()
    app.state.personal_ip_evidence_promotion_repo = repository
    app.include_router(router_module.router)

    async def current_user(_request):
        return SimpleNamespace(id="user-1")

    monkeypatch.setattr(router_module, "get_current_user_from_request", current_user)
    async with httpx.AsyncClient(
        base_url="http://test",
        transport=httpx.ASGITransport(app=app),
    ) as client:
        create = await client.post(
            "/api/personal-ip/evidence-promotions",
            json={"claim": "不再由服务器晋升"},
        )
        listed = await client.get("/api/personal-ip/evidence-promotions")
        detail = await client.get("/api/personal-ip/evidence-promotions/promotion-1")
        exported = await client.get("/api/personal-ip/evidence-promotions/promotion-1/export")

    assert create.status_code == 405
    assert listed.json()[0]["id"] == "promotion-1"
    assert detail.json()["id"] == "promotion-1"
    assert exported.status_code == 200
    repository.list.assert_awaited_once_with("user-1", status=None, limit=100)
    repository.get.assert_awaited_once_with("promotion-1", owner_user_id="user-1")
