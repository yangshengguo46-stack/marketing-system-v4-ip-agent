from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from app.gateway.routers import personal_ip_evidence_promotions as router_module


@pytest.mark.asyncio
async def test_evidence_promotion_router_auto_promotes_and_exports(monkeypatch) -> None:
    repository = SimpleNamespace(
        propose=AsyncMock(return_value={"id": "promotion-1", "status": "approved"}),
        export_approved=AsyncMock(return_value={"contract_version": "personal-ip-approved-evidence-v1"}),
    )
    app = FastAPI()
    app.state.personal_ip_evidence_promotion_repo = repository
    app.include_router(router_module.router)

    async def current_user(_request):
        return SimpleNamespace(id="user-1")

    monkeypatch.setattr(router_module, "get_current_user_from_request", current_user)
    async with httpx.AsyncClient(base_url="http://test", transport=httpx.ASGITransport(app=app)) as client:
        proposed = await client.post(
            "/api/personal-ip/evidence-promotions",
            json={
                "proposal_key": "pattern:v1",
                "evidence_type": "content_pattern",
                "claim": "直接开门见山更有效。",
                "retrospective_ids": ["retro-1", "retro-2", "retro-3"],
                "minimum_support": 3,
            },
        )
        removed_decision = await client.post(
            "/api/personal-ip/evidence-promotions/promotion-1/decisions",
            json={"decision": "approved"},
        )
        exported = await client.get("/api/personal-ip/evidence-promotions/promotion-1/export")

    assert proposed.status_code == 201
    assert proposed.json()["status"] == "approved"
    assert removed_decision.status_code == 404
    assert exported.status_code == 200
    assert repository.propose.await_args.kwargs["owner_user_id"] == "user-1"
    assert repository.export_approved.await_args.kwargs["owner_user_id"] == "user-1"
