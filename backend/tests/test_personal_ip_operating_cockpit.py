from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from app.gateway.routers import personal_ip_cockpit as router_module
from deerflow.personal_ip.operating_cockpit import PersonalIPOperatingCockpitService


def _repos():
    return {
        "subjects": SimpleNamespace(list=AsyncMock(return_value=[{"id": "subject-1"}])),
        "accounts": SimpleNamespace(
            list=AsyncMock(
                return_value=[
                    {
                        "id": "acct-ready",
                        "platform": "douyin",
                        "primary_audience": "创业者",
                        "promise_to_audience": "讲清 AI 商业落地",
                        "content_pillars": ["AI"],
                        "business_goal": "获客",
                    },
                    {
                        "id": "acct-needs-model",
                        "platform": "xiaohongshu",
                        "primary_audience": "",
                        "promise_to_audience": "",
                        "content_pillars": [],
                        "business_goal": "",
                    },
                ]
            )
        ),
        "preflights": SimpleNamespace(
            list=AsyncMock(
                return_value=[
                    {
                        "id": "preflight-1",
                        "status": "sealed",
                        "target_account_ids": ["acct-ready"],
                        "created_at": "2026-07-22T01:00:00Z",
                    }
                ]
            )
        ),
        "publish_receipts": SimpleNamespace(
            list=AsyncMock(
                return_value=[
                    {
                        "id": "receipt-1",
                        "preflight_id": "preflight-1",
                        "account_id": "acct-ready",
                        "platform": "douyin",
                        "status": "published",
                        "published_at": "2026-07-22T02:00:00Z",
                    }
                ]
            )
        ),
        "metrics": SimpleNamespace(
            list=AsyncMock(
                return_value=[
                    {
                        "id": "metric-1",
                        "receipt_id": "receipt-1",
                        "account_id": "acct-ready",
                        "platform": "douyin",
                        "status": "partial",
                        "observed_at": "2026-07-22T03:00:00Z",
                    }
                ]
            )
        ),
        "platform_observations": SimpleNamespace(
            list=AsyncMock(
                return_value=[
                    {
                        "id": "platform-observation-1",
                        "account_id": "acct-ready",
                        "platform": "douyin",
                        "dataset": "dashboard",
                        "status": "partial",
                        "observed_at": "2026-07-22T03:10:00Z",
                    }
                ]
            )
        ),
        "retrospectives": SimpleNamespace(list=AsyncMock(return_value=[])),
        "evidence_promotions": SimpleNamespace(
            list=AsyncMock(
                return_value=[
                    {
                        "id": "promotion-1",
                        "evidence_type": "content_pattern",
                        "claim": "开头直给结果提高完播",
                        "status": "proposed",
                        "updated_at": "2026-07-22T04:00:00Z",
                    }
                ]
            )
        ),
        "video_productions": SimpleNamespace(
            list=AsyncMock(
                return_value=[
                    {
                        "id": "video-production-running",
                        "title": "智能体微电影",
                        "status": "blocked",
                        "current_stage": "generation",
                        "event_count": 8,
                        "updated_at": "2026-07-22T05:00:00Z",
                    },
                    {
                        "id": "video-production-complete",
                        "title": "已交付短片",
                        "status": "completed",
                        "current_stage": "delivery",
                        "event_count": 16,
                        "updated_at": "2026-07-22T04:00:00Z",
                    },
                ]
            )
        ),
    }


@pytest.mark.asyncio
async def test_operating_cockpit_closes_the_portfolio_workflow_read_model() -> None:
    repos = _repos()
    result = await PersonalIPOperatingCockpitService(**repos).build(owner_user_id="user-1")

    assert result["contract_version"] == "personal-ip-operating-cockpit-v1"
    assert result["portfolio"] == {
        "subject_count": 1,
        "account_count": 2,
        "platform_count": 2,
        "platforms": ["douyin", "xiaohongshu"],
    }
    assert result["stages"]["modeling"]["pending"] == 1
    assert result["stages"]["preflight"]["total"] == 1
    assert result["stages"]["publishing"]["published"] == 1
    assert result["stages"]["performance"]["metric_observations"] == 1
    assert result["stages"]["performance"]["platform_observations"] == 1
    assert result["stages"]["retrospective"]["pending"] == 1
    assert result["stages"]["evidence"]["pending"] == 1
    assert result["queues"]["accounts_needing_model_input"] == ["acct-needs-model"]
    assert result["queues"]["published_receipts_awaiting_retrospective"] == ["receipt-1"]
    assert result["queues"]["evidence_awaiting_decision"] == ["promotion-1"]
    assert result["video"]["production_count"] == 2
    assert result["video"]["blocked_production_ids"] == ["video-production-running"]
    assert result["video"]["stages"]["generation"] == 1
    assert result["video"]["stages"]["delivery"] == 1
    assert "records" not in result["recent"]["platform_observations"][0]
    repos["accounts"].list.assert_awaited_once_with("user-1", include_archived=False)
    repos["metrics"].list.assert_awaited_once_with("user-1", limit=500)
    repos["video_productions"].list.assert_awaited_once_with("user-1", limit=500)


@pytest.mark.asyncio
async def test_operating_cockpit_router_uses_authenticated_owner(monkeypatch) -> None:
    build = AsyncMock(return_value={"contract_version": "personal-ip-operating-cockpit-v1", "stages": {}})
    app = FastAPI()
    app.include_router(router_module.router)

    async def current_user(_request):
        return SimpleNamespace(id="user-1")

    monkeypatch.setattr(router_module, "get_current_user_from_request", current_user)
    monkeypatch.setattr(
        router_module,
        "_cockpit_service",
        lambda _request: SimpleNamespace(build=build),
    )

    async with httpx.AsyncClient(base_url="http://test", transport=httpx.ASGITransport(app=app)) as client:
        response = await client.get("/api/personal-ip/cockpit")

    assert response.status_code == 200
    assert response.json()["contract_version"] == "personal-ip-operating-cockpit-v1"
    build.assert_awaited_once_with(owner_user_id="user-1")
