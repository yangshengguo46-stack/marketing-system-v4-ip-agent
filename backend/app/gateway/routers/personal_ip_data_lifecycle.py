"""Owner-scoped Personal-IP backup, restore and destructive-delete endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.gateway.deps import (
    get_current_user_from_request,
    get_personal_ip_data_lifecycle_service,
)

router = APIRouter(prefix="/api/personal-ip/data", tags=["personal-ip"])


class PersonalIPRestoreRequest(BaseModel):
    backup: dict[str, Any]


class PersonalIPDeleteConfirmationRequest(BaseModel):
    schema_version: Literal["personal-ip-destructive-delete-confirmation-v1"]
    owner_user_id: str = Field(min_length=1, max_length=64)
    state_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirmation_phrase: str = Field(min_length=1, max_length=64)
    backup_acknowledged: bool
    artifact_files_acknowledged: bool
    delete_local_context: bool


async def _owner_id(request: Request) -> str:
    return str((await get_current_user_from_request(request)).id)


@router.get("/export")
async def export_personal_ip_data(request: Request) -> JSONResponse:
    owner_user_id = await _owner_id(request)
    backup = await get_personal_ip_data_lifecycle_service(request).export_backup(owner_user_id)
    date = datetime.now(UTC).date().isoformat()
    return JSONResponse(
        content=backup,
        headers={
            "Content-Disposition": (f'attachment; filename="personal-ip-backup-{date}.json"'),
            "Cache-Control": "no-store",
        },
    )


@router.post("/restore")
async def restore_personal_ip_data(
    body: PersonalIPRestoreRequest,
    request: Request,
) -> dict[str, Any]:
    try:
        return await get_personal_ip_data_lifecycle_service(request).restore_backup(
            await _owner_id(request),
            body.backup,
        )
    except ValueError as exc:
        status = 409 if "requires an empty owner scope" in str(exc) else 422
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@router.get("/delete-preview")
async def preview_personal_ip_delete(request: Request) -> dict[str, Any]:
    return await get_personal_ip_data_lifecycle_service(request).preview_delete(await _owner_id(request))


@router.post("/delete")
async def delete_all_personal_ip_data(
    body: PersonalIPDeleteConfirmationRequest,
    request: Request,
) -> dict[str, Any]:
    try:
        return await get_personal_ip_data_lifecycle_service(request).delete_all(
            await _owner_id(request),
            body.model_dump(),
        )
    except ValueError as exc:
        status = 409 if "state changed" in str(exc) else 422
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
