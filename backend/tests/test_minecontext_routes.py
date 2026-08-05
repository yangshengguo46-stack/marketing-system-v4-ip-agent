from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway.routers import personal_ip_minecontext as router_module


class _StatusOnlyMineContext:
    def __init__(self) -> None:
        self.status_calls: list[str] = []

    def status(self, owner_user_id: str) -> dict[str, Any]:
        self.status_calls.append(owner_user_id)
        return {"authorized": False, "running": False}

    def ensure_default(self, _owner_user_id: str) -> dict[str, Any]:
        raise AssertionError("GET status must not authorize or start MineContext")


class _ExplicitEnableMineContext:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int, bool]] = []

    def enable_default(
        self,
        owner_user_id: str,
        *,
        retention_days: int,
        continuous_screen_capture_confirmed: bool,
    ) -> dict[str, Any]:
        self.calls.append(
            (
                owner_user_id,
                retention_days,
                continuous_screen_capture_confirmed,
            )
        )
        return {"authorized": True, "running": True}


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(router_module.router)
    return app


@pytest.mark.asyncio
async def test_status_route_calls_read_only_status(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _StatusOnlyMineContext()
    request = object()
    monkeypatch.setattr(router_module, "get_minecontext_service", lambda _request: service)

    async def owner_id(_request: object) -> str:
        return "owner-a"

    monkeypatch.setattr(router_module, "_owner_id", owner_id)

    result = await router_module.minecontext_status(request)  # type: ignore[arg-type]

    assert result == {"authorized": False, "running": False}
    assert service.status_calls == ["owner-a"]


def test_enable_route_rejects_missing_or_false_screen_confirmation() -> None:
    with TestClient(_app()) as client:
        missing = client.post(
            "/api/personal-ip/minecontext/enable",
            json={"retention_days": 30},
        )
        rejected = client.post(
            "/api/personal-ip/minecontext/enable",
            json={
                "retention_days": 30,
                "continuous_screen_capture_confirmed": False,
            },
        )

    assert missing.status_code == 422
    assert rejected.status_code == 422


def test_enable_route_passes_explicit_confirmation_to_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _ExplicitEnableMineContext()
    monkeypatch.setattr(router_module, "get_minecontext_service", lambda _request: service)

    async def owner_id(_request: object) -> str:
        return "owner-a"

    monkeypatch.setattr(router_module, "_owner_id", owner_id)

    with TestClient(_app()) as client:
        response = client.post(
            "/api/personal-ip/minecontext/enable",
            json={
                "retention_days": 45,
                "continuous_screen_capture_confirmed": True,
            },
        )

    assert response.status_code == 200
    assert response.json() == {"authorized": True, "running": True}
    assert service.calls == [("owner-a", 45, True)]
