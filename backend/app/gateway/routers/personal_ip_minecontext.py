"""User-visible consent and lifecycle controls for the local MineContext source."""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.gateway.deps import get_current_user_from_request, get_minecontext_service
from deerflow.personal_ip.minecontext import MineContextConsent, MineContextPurpose, MineContextScope

router = APIRouter(prefix="/api/personal-ip/minecontext", tags=["personal-ip"])


class MineContextSyncRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    source_kind: MineContextScope
    purpose: MineContextPurpose
    context_types: list[str] = Field(default_factory=list, max_length=20)
    limit: int = Field(default=10, ge=1, le=100)


async def _owner_id(request: Request) -> str:
    return str((await get_current_user_from_request(request)).id)


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=409, detail=str(exc))


@router.get("")
async def minecontext_status(request: Request) -> dict[str, Any]:
    return await asyncio.to_thread(get_minecontext_service(request).status, await _owner_id(request))


@router.post("/authorize")
async def authorize_minecontext(body: MineContextConsent, request: Request) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(get_minecontext_service(request).authorize, await _owner_id(request), body)
    except (PermissionError, RuntimeError, ValueError) as exc:
        raise _http_error(exc) from exc


@router.post("/start")
async def start_minecontext(request: Request) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(get_minecontext_service(request).start, await _owner_id(request))
    except (PermissionError, RuntimeError, ValueError) as exc:
        raise _http_error(exc) from exc


@router.post("/stop")
async def stop_minecontext(request: Request) -> dict[str, Any]:
    return await asyncio.to_thread(get_minecontext_service(request).stop, await _owner_id(request))


@router.post("/revoke")
async def revoke_minecontext(request: Request) -> dict[str, Any]:
    return await asyncio.to_thread(get_minecontext_service(request).revoke, await _owner_id(request))


@router.post("/sync")
async def sync_minecontext(body: MineContextSyncRequest, request: Request) -> dict[str, Any]:
    try:
        records = await asyncio.to_thread(
            get_minecontext_service(request).sync,
            await _owner_id(request),
            query=body.query,
            source_kind=body.source_kind,
            purpose=body.purpose,
            context_types=body.context_types,
            limit=body.limit,
        )
        return {"schema_version": "personal-ip-local-context-sync-v1", "records": records, "count": len(records)}
    except (PermissionError, RuntimeError, ValueError) as exc:
        raise _http_error(exc) from exc


@router.delete("/data")
async def delete_minecontext_data(
    request: Request,
    scope: Literal["evidence", "all"] = Query(default="evidence"),
) -> dict[str, Any]:
    return await asyncio.to_thread(get_minecontext_service(request).clear, await _owner_id(request), scope=scope)
