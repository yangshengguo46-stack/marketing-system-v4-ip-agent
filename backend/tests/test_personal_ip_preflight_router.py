from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from app.gateway.routers import personal_ip_preflights as router_module
from deerflow.personal_ip.audience_provider import AudiencePreflightRequest, AudiencePreflightResult
from deerflow.personal_ip.hllm_creator import HLLMCreatorAdapter


def _payload() -> tuple[dict, AudiencePreflightRequest, AudiencePreflightResult]:
    example = HLLMCreatorAdapter().build_example(
        history=[
            {
                "content_id": "published-1",
                "published_at": "2026-07-20T08:00:00Z",
                "platform": "douyin",
                "title": "历史内容",
                "content_type": "short_video",
                "metrics": {"views": 1000},
            }
        ],
        audience_profile={"cohort_label": "测试群体"},
        creator_profile={"voice": ["直接"]},
        target={"content_id": "draft-1", "title": "待发布", "description": "预演"},
    )
    request = AudiencePreflightRequest(example=example, variant_count=1)
    result = AudiencePreflightResult(
        provider="hllm-lite",
        model_version="doubao-test",
        algorithm_version="lite-v0",
        request_digest=request.request_digest,
        audience_basis="aggregate_account_cohort",
        variants=[{"variant_id": "v1", "text": "候选"}],
    )
    return (
        {
            "operation_key": "preflight:draft-1:v1",
            "subject_ids": ["subject-1"],
            "target_account_ids": ["acct-1", "acct-2"],
            "model_request": request.to_payload(),
            "provider_receipt": result.model_dump(mode="json"),
        },
        request,
        result,
    )


@pytest.mark.asyncio
async def test_preflight_router_seals_validated_model_contract(monkeypatch) -> None:
    payload, request, _ = _payload()
    repository = SimpleNamespace(seal=AsyncMock(return_value={"id": "preflight-1", "status": "sealed"}))
    app = FastAPI()
    app.state.personal_ip_preflight_repo = repository
    app.include_router(router_module.router)

    async def current_user(_request):
        return SimpleNamespace(id="user-1")

    monkeypatch.setattr(router_module, "get_current_user_from_request", current_user)
    async with httpx.AsyncClient(base_url="http://test", transport=httpx.ASGITransport(app=app)) as client:
        response = await client.post("/api/personal-ip/preflights", json=payload)

    assert response.status_code == 201
    kwargs = repository.seal.await_args.kwargs
    assert kwargs["owner_user_id"] == "user-1"
    assert kwargs["target_account_ids"] == ["acct-1", "acct-2"]
    assert kwargs["request"].request_digest == request.request_digest


@pytest.mark.asyncio
async def test_preflight_router_rejects_contract_tampering_before_storage(monkeypatch) -> None:
    payload, _, _ = _payload()
    payload["model_request"]["audience_basis"] = "individual_viewers"
    repository = SimpleNamespace(seal=AsyncMock())
    app = FastAPI()
    app.state.personal_ip_preflight_repo = repository
    app.include_router(router_module.router)

    async def current_user(_request):
        return SimpleNamespace(id="user-1")

    monkeypatch.setattr(router_module, "get_current_user_from_request", current_user)
    async with httpx.AsyncClient(base_url="http://test", transport=httpx.ASGITransport(app=app)) as client:
        response = await client.post("/api/personal-ip/preflights", json=payload)

    assert response.status_code == 422
    repository.seal.assert_not_awaited()
