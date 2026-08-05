from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from app.gateway.routers import personal_ip_data_lifecycle as router_module
from deerflow.personal_ip.data_lifecycle import DELETE_CONFIRMATION_PHRASE


async def _current_user(_request):
    return SimpleNamespace(id="user-1")


@pytest.mark.asyncio
async def test_data_lifecycle_router_binds_every_operation_to_authenticated_owner(
    monkeypatch,
) -> None:
    service = SimpleNamespace(
        export_backup=AsyncMock(
            return_value={
                "schema_version": "personal-ip-owner-backup-v1",
                "owner_user_id": "user-1",
            }
        ),
        restore_backup=AsyncMock(
            return_value={
                "schema_version": "personal-ip-owner-restore-receipt-v1",
                "verified": True,
            }
        ),
        preview_delete=AsyncMock(
            return_value={
                "schema_version": "personal-ip-destructive-delete-preview-v1",
                "state_digest": "a" * 64,
            }
        ),
        delete_all=AsyncMock(
            return_value={
                "schema_version": "personal-ip-destructive-delete-receipt-v1",
                "deleted_records": 3,
            }
        ),
    )
    app = FastAPI()
    app.state.personal_ip_data_lifecycle_service = service
    app.include_router(router_module.router)
    monkeypatch.setattr(router_module, "get_current_user_from_request", _current_user)

    confirmation = {
        "schema_version": "personal-ip-destructive-delete-confirmation-v1",
        "owner_user_id": "user-1",
        "state_digest": "a" * 64,
        "confirmation_phrase": DELETE_CONFIRMATION_PHRASE,
        "backup_acknowledged": True,
        "artifact_files_acknowledged": True,
        "delete_local_context": True,
    }
    async with httpx.AsyncClient(
        base_url="http://test",
        transport=httpx.ASGITransport(app=app),
    ) as client:
        exported = await client.get("/api/personal-ip/data/export")
        restored = await client.post(
            "/api/personal-ip/data/restore",
            json={"backup": {"schema_version": "personal-ip-owner-backup-v1"}},
        )
        preview = await client.get("/api/personal-ip/data/delete-preview")
        deleted = await client.post("/api/personal-ip/data/delete", json=confirmation)

    assert exported.status_code == 200
    assert exported.headers["content-disposition"].startswith('attachment; filename="personal-ip-backup-')
    assert restored.status_code == 200
    assert preview.status_code == 200
    assert deleted.status_code == 200
    service.export_backup.assert_awaited_once_with("user-1")
    service.restore_backup.assert_awaited_once_with(
        "user-1",
        {"schema_version": "personal-ip-owner-backup-v1"},
    )
    service.preview_delete.assert_awaited_once_with("user-1")
    service.delete_all.assert_awaited_once()
    assert service.delete_all.await_args.args[0] == "user-1"


@pytest.mark.asyncio
async def test_data_lifecycle_router_rejects_restore_conflict_and_stale_delete(
    monkeypatch,
) -> None:
    service = SimpleNamespace(
        restore_backup=AsyncMock(side_effect=ValueError("Personal-IP restore requires an empty owner scope; delete existing data first")),
        delete_all=AsyncMock(side_effect=ValueError("Personal-IP state changed after the delete preview; prepare a fresh confirmation")),
    )
    app = FastAPI()
    app.state.personal_ip_data_lifecycle_service = service
    app.include_router(router_module.router)
    monkeypatch.setattr(router_module, "get_current_user_from_request", _current_user)

    async with httpx.AsyncClient(
        base_url="http://test",
        transport=httpx.ASGITransport(app=app),
    ) as client:
        restore = await client.post(
            "/api/personal-ip/data/restore",
            json={"backup": {"schema_version": "personal-ip-owner-backup-v1"}},
        )
        delete_response = await client.post(
            "/api/personal-ip/data/delete",
            json={
                "schema_version": "personal-ip-destructive-delete-confirmation-v1",
                "owner_user_id": "user-1",
                "state_digest": "b" * 64,
                "confirmation_phrase": DELETE_CONFIRMATION_PHRASE,
                "backup_acknowledged": True,
                "artifact_files_acknowledged": True,
                "delete_local_context": True,
            },
        )

    assert restore.status_code == 409
    assert delete_response.status_code == 409
