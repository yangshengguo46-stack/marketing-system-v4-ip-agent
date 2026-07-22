from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from app.gateway.routers import personal_ip_metrics as router_module


@pytest.mark.asyncio
async def test_metric_router_records_and_aggregates_the_whole_portfolio(monkeypatch) -> None:
    repository = SimpleNamespace(
        record=AsyncMock(return_value={"id": "metric-1", "platform": "douyin"}),
        aggregate=AsyncMock(return_value={"totals": {"views": 320}, "coverage": {"missing_account_ids": []}}),
    )
    app = FastAPI()
    app.state.personal_ip_metric_repo = repository
    app.include_router(router_module.router)

    async def current_user(_request):
        return SimpleNamespace(id="user-1")

    monkeypatch.setattr(router_module, "get_current_user_from_request", current_user)
    async with httpx.AsyncClient(base_url="http://test", transport=httpx.ASGITransport(app=app)) as client:
        created = await client.post(
            "/api/personal-ip/metrics",
            json={
                "observation_key": "douyin:2026-07-21",
                "account_id": "acct-1",
                "scope": "account",
                "metric_mode": "window_total",
                "source": "platform_api",
                "status": "observed",
                "window_started_at": "2026-07-21T00:00:00Z",
                "window_ended_at": "2026-07-22T00:00:00Z",
                "observed_at": "2026-07-22T00:05:00Z",
                "metrics": {"views": 320},
                "coverage": {},
            },
        )
        aggregate = await client.get(
            "/api/personal-ip/metrics/aggregate",
            params={
                "window_started_at": "2026-07-21T00:00:00Z",
                "window_ended_at": "2026-07-22T00:00:00Z",
            },
        )

    assert created.status_code == 201
    assert aggregate.status_code == 200
    assert aggregate.json()["totals"]["views"] == 320
    assert repository.record.await_args.kwargs["owner_user_id"] == "user-1"
    aggregate_kwargs = repository.aggregate.await_args.kwargs
    assert aggregate_kwargs["owner_user_id"] == "user-1"
    assert "account_id" not in aggregate_kwargs


@pytest.mark.asyncio
async def test_metric_router_maps_idempotency_conflict(monkeypatch) -> None:
    repository = SimpleNamespace(
        record=AsyncMock(side_effect=ValueError("observation_key already records a different observation")),
    )
    app = FastAPI()
    app.state.personal_ip_metric_repo = repository
    app.include_router(router_module.router)

    async def current_user(_request):
        return SimpleNamespace(id="user-1")

    monkeypatch.setattr(router_module, "get_current_user_from_request", current_user)
    async with httpx.AsyncClient(base_url="http://test", transport=httpx.ASGITransport(app=app)) as client:
        response = await client.post(
            "/api/personal-ip/metrics",
            json={
                "observation_key": "duplicate",
                "account_id": "acct-1",
                "scope": "account",
                "metric_mode": "snapshot",
                "source": "manual",
                "status": "observed",
                "observed_at": "2026-07-22T00:05:00Z",
                "metrics": {"views": 1},
                "coverage": {},
            },
        )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_metric_router_collects_with_server_side_connection_without_raw_token(monkeypatch) -> None:
    repository = SimpleNamespace()
    service = SimpleNamespace(
        collect_published_post=AsyncMock(
            return_value={
                "id": "metric-1",
                "account_id": "acct-1",
                "receipt_id": "publish-1",
                "source": "platform_api",
                "metrics": {"views": 900},
            }
        )
    )
    app = FastAPI()
    app.state.personal_ip_metric_repo = repository
    app.include_router(router_module.router)

    async def current_user(_request):
        return SimpleNamespace(id="user-1")

    monkeypatch.setattr(router_module, "get_current_user_from_request", current_user)
    monkeypatch.setattr(router_module, "_get_authorized_douyin_service", lambda _request: service)
    async with httpx.AsyncClient(base_url="http://test", transport=httpx.ASGITransport(app=app)) as client:
        response = await client.post(
            "/api/personal-ip/metrics/collect/douyin",
            json={
                "connection_id": "platform-conn-1",
                "publish_receipt_id": "publish-1",
                "observation_key": "douyin:item-1:2026-07-21T12:00:00Z",
            },
        )

    assert response.status_code == 201
    assert response.json()["metrics"]["views"] == 900
    assert "token" not in response.text.lower()
    service.collect_published_post.assert_awaited_once_with(
        owner_user_id="user-1",
        connection_id="platform-conn-1",
        publish_receipt_id="publish-1",
        observation_key="douyin:item-1:2026-07-21T12:00:00Z",
    )


@pytest.mark.asyncio
async def test_metric_router_collects_browser_today_for_whole_portfolio(monkeypatch) -> None:
    service = SimpleNamespace(
        collect_today=AsyncMock(
            return_value={
                "status": "partial",
                "aggregate": {
                    "totals": {"views": 200},
                    "coverage": {"missing_account_ids": ["acct-missing"]},
                },
            }
        )
    )
    app = FastAPI()
    app.include_router(router_module.router)

    async def current_user(_request):
        return SimpleNamespace(id="user-1")

    monkeypatch.setattr(router_module, "get_current_user_from_request", current_user)
    monkeypatch.setattr(router_module, "_get_browser_portfolio_service", lambda _request: service)
    async with httpx.AsyncClient(base_url="http://test", transport=httpx.ASGITransport(app=app)) as client:
        response = await client.post(
            "/api/personal-ip/metrics/collect/browser-portfolio-today",
            json={
                "collection_key": "today:2026-07-22T12+08:00",
                "window_started_at": "2026-07-22T00:00:00+08:00",
                "window_ended_at": "2026-07-22T12:00:00+08:00",
            },
        )

    assert response.status_code == 201
    assert response.json()["aggregate"]["totals"]["views"] == 200
    kwargs = service.collect_today.await_args.kwargs
    assert kwargs["owner_user_id"] == "user-1"
    assert "account_id" not in kwargs
