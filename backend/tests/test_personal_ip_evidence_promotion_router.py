from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from app.gateway.routers import personal_ip_evidence_promotions as router_module


@pytest.mark.asyncio
async def test_evidence_promotion_router_proposes_decides_and_exports(monkeypatch) -> None:
    repository = SimpleNamespace(
        propose=AsyncMock(return_value={"id": "promotion-1", "status": "proposed"}),
        decide=AsyncMock(return_value={"id": "promotion-1", "status": "approved"}),
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
        decided = await client.post(
            "/api/personal-ip/evidence-promotions/promotion-1/decisions",
            json={
                "decision_key": "approve:v1",
                "decision": "approved",
                "rationale": "三个独立样本均支持。",
                "confirmed_by_user": True,
                "occurred_at": "2026-07-25T08:00:00Z",
            },
        )
        exported = await client.get("/api/personal-ip/evidence-promotions/promotion-1/export")

    assert proposed.status_code == 201
    assert decided.status_code == 200
    assert exported.status_code == 200
    assert repository.propose.await_args.kwargs["owner_user_id"] == "user-1"
    decision_kwargs = repository.decide.await_args.kwargs
    assert decision_kwargs["confirmed_by_user"] is True
    assert decision_kwargs["occurred_at"].isoformat() == "2026-07-25T08:00:00+00:00"
    assert repository.export_approved.await_args.kwargs["owner_user_id"] == "user-1"


@pytest.mark.asyncio
async def test_evidence_promotion_router_requires_human_confirmation(monkeypatch) -> None:
    repository = SimpleNamespace(decide=AsyncMock())
    app = FastAPI()
    app.state.personal_ip_evidence_promotion_repo = repository
    app.include_router(router_module.router)

    async def current_user(_request):
        return SimpleNamespace(id="user-1")

    monkeypatch.setattr(router_module, "get_current_user_from_request", current_user)
    async with httpx.AsyncClient(base_url="http://test", transport=httpx.ASGITransport(app=app)) as client:
        response = await client.post(
            "/api/personal-ip/evidence-promotions/promotion-1/decisions",
            json={
                "decision_key": "approve:v1",
                "decision": "approved",
                "rationale": "智能体自行批准不算。",
                "confirmed_by_user": False,
            },
        )

    assert response.status_code == 422
