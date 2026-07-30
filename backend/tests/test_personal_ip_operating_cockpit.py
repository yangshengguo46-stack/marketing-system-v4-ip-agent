from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from app.gateway.routers import personal_ip_cockpit as router_module
from deerflow.personal_ip.operating_cockpit import (
    PersonalIPOperatingCockpitService,
    PersonalIPStartupContextService,
)


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
        "brand": SimpleNamespace(
            list_strategies=AsyncMock(
                return_value=[
                    {
                        "id": "strategy-1",
                        "subject_id": "subject-1",
                        "version": 8,
                        "stage": "commercial_signal_observed",
                        "mode": "monetization_first",
                    }
                ]
            ),
        ),
        "differentiation": SimpleNamespace(
            list_versions=AsyncMock(
                return_value=[
                    {
                        "id": "difference-1",
                        "subject_id": "subject-1",
                        "version": 4,
                        "thesis_key": "ip-agent-core",
                        "status": "validated",
                    }
                ]
            ),
            list_observations=AsyncMock(
                return_value=[
                    {
                        "id": "ip-observation-1",
                        "subject_id": "subject-1",
                        "differentiation_version_id": "difference-1",
                        "thesis_key": "ip-agent-core",
                        "observation_type": "adoption",
                        "coverage_status": "complete",
                    }
                ]
            ),
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
                    },
                    {
                        "id": "receipt-failed",
                        "preflight_id": "preflight-failed",
                        "account_id": "acct-ready",
                        "platform": "douyin",
                        "status": "failed",
                        "updated_at": "2026-07-22T05:30:00Z",
                    },
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
                        "status": "approved",
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
                        "thread_id": "thread-video-running",
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
            ),
            get=AsyncMock(
                return_value={
                    "id": "video-production-running",
                    "title": "智能体微电影",
                    "status": "blocked",
                    "current_stage": "generation",
                    "thread_id": "thread-video-running",
                    "budget_state": {
                        "currency": "CNY",
                        "hard_limit": 10.0,
                        "reserved": 0.0,
                        "spent": 10.0,
                        "available": 0.0,
                        "active_reservation_count": 0,
                    },
                    "events": [
                        {
                            "id": "video-event-provider-failed",
                            "event_type": "shot_generation_failed",
                            "status": "failed",
                            "provider": "volcengine",
                            "stage": "generation",
                            "entity_type": "shot",
                            "entity_id": "shot-01",
                            "occurred_at": "2026-07-22T05:00:00Z",
                        },
                        {
                            "id": "video-event-budget-rejected",
                            "event_type": "budget_reservation_rejected",
                            "status": "rejected",
                            "provider": "deerflow_budget_guard",
                            "stage": "generation",
                            "entity_type": "shot",
                            "entity_id": "shot-02",
                            "occurred_at": "2026-07-22T05:10:00Z",
                            "payload": {"reason_code": "hard_limit_exceeded"},
                        },
                    ],
                }
            ),
        ),
    }


@pytest.mark.asyncio
async def test_startup_context_short_circuits_a_true_new_owner() -> None:
    subjects = SimpleNamespace(list=AsyncMock(return_value=[]))
    accounts = SimpleNamespace(list=AsyncMock(return_value=[]))

    result = await PersonalIPStartupContextService(
        subjects=subjects,
        accounts=accounts,
    ).build(owner_user_id="user-new")

    assert result == {
        "contract_version": "personal-ip-startup-context-v1",
        "experience": "new_owner",
        "portfolio": {"subject_count": 0, "account_count": 0},
        "should_read_operating_cockpit": False,
        "next_step": "respond_to_current_request",
    }
    subjects.list.assert_awaited_once_with("user-new", include_archived=False)
    accounts.list.assert_awaited_once_with("user-new", include_archived=False)


@pytest.mark.asyncio
async def test_startup_context_routes_existing_owner_to_the_cockpit() -> None:
    result = await PersonalIPStartupContextService(
        subjects=SimpleNamespace(list=AsyncMock(return_value=[{"id": "subject-1"}])),
        accounts=SimpleNamespace(list=AsyncMock(return_value=[])),
    ).build(owner_user_id="user-returning")

    assert result["experience"] == "returning_owner"
    assert result["should_read_operating_cockpit"] is True
    assert result["next_step"] == "resume_operating_state"


@pytest.mark.asyncio
async def test_operating_cockpit_closes_the_portfolio_workflow_read_model() -> None:
    repos = _repos()
    result = await PersonalIPOperatingCockpitService(**repos).build(owner_user_id="user-1")

    assert result["contract_version"] == "personal-ip-operating-cockpit-v6"
    assert result["portfolio"] == {
        "subject_count": 1,
        "account_count": 2,
        "platform_count": 2,
        "platforms": ["douyin", "xiaohongshu"],
    }
    assert result["stages"]["modeling"]["pending"] == 0
    assert result["stages"]["modeling"]["strategies_validated"] == 1
    assert result["stages"]["modeling"]["differentiation_validated"] == 1
    assert result["stages"]["modeling"]["asset_observations"] == 1
    assert result["stages"]["preflight"]["total"] == 1
    assert result["stages"]["publishing"]["published"] == 1
    assert result["stages"]["publishing"]["failed"] == 1
    assert result["stages"]["performance"]["metric_observations"] == 1
    assert result["stages"]["performance"]["platform_observations"] == 1
    assert result["stages"]["retrospective"]["pending"] == 1
    assert result["stages"]["evidence"]["pending"] == 0
    assert result["stages"]["evidence"]["approved"] == 1
    assert result["queues"]["subjects_needing_strategy_validation"] == []
    assert result["queues"]["subjects_needing_differentiation_validation"] == []
    assert result["queues"]["published_receipts_awaiting_retrospective"] == ["receipt-1"]
    assert "evidence_awaiting_decision" not in result["queues"]
    assert result["video"]["production_count"] == 2
    assert result["video"]["blocked_production_ids"] == ["video-production-running"]
    assert result["video"]["stages"]["generation"] == 1
    assert result["video"]["stages"]["delivery"] == 1
    assert result["alerts"]["summary"] == {
        "total": 4,
        "blocking": 3,
        "warning": 1,
        "by_category": {"loop": 1, "provider": 1, "cost": 2},
    }
    assert {item["code"] for item in result["alerts"]["items"]} == {
        "publish_failed",
        "provider_execution_failed",
        "budget_reservation_rejected",
        "budget_exhausted",
    }
    assert all("payload" not in item for item in result["alerts"]["items"])
    assert "mode" not in result["recent"]["strategies"][0]
    assert "records" not in result["recent"]["platform_observations"][0]
    repos["accounts"].list.assert_awaited_once_with("user-1", include_archived=False)
    repos["metrics"].list.assert_awaited_once_with("user-1", limit=500)
    repos["video_productions"].list.assert_awaited_once_with("user-1", limit=500)
    repos["video_productions"].get.assert_awaited_once_with(
        "video-production-running",
        owner_user_id="user-1",
    )


@pytest.mark.asyncio
async def test_operating_cockpit_marks_missing_strategy_as_pending() -> None:
    repos = _repos()
    repos["brand"].list_strategies = AsyncMock(return_value=[])

    result = await PersonalIPOperatingCockpitService(**repos).build(owner_user_id="user-1")

    assert result["stages"]["modeling"]["ready"] == 0
    assert result["stages"]["modeling"]["pending"] == 1
    assert result["stages"]["modeling"]["subjects_needing_strategy"] == 1
    assert result["queues"]["subjects_needing_strategy_validation"] == ["subject-1"]


@pytest.mark.asyncio
async def test_operating_cockpit_router_uses_authenticated_owner(monkeypatch) -> None:
    build = AsyncMock(return_value={"contract_version": "personal-ip-operating-cockpit-v6", "stages": {}})
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
    assert response.json()["contract_version"] == "personal-ip-operating-cockpit-v6"
    build.assert_awaited_once_with(owner_user_id="user-1")
