from __future__ import annotations

import httpx
import pytest

from app.gateway.app import app

RETIRED_PATHS = (
    "/api/personal-ip/cockpit",
    "/api/personal-ip/preflights",
    "/api/personal-ip/retrospectives",
    "/api/personal-ip/evidence-promotions",
)


@pytest.mark.asyncio
async def test_retired_personal_ip_api_paths_return_404() -> None:
    registered = {getattr(route, "path", None) for route in app.routes}
    assert registered.isdisjoint(RETIRED_PATHS)

    transport = httpx.ASGITransport(app=app.router)
    async with httpx.AsyncClient(base_url="http://test", transport=transport) as client:
        for path in RETIRED_PATHS:
            response = await client.get(path)
            assert response.status_code == 404, path
