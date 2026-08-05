"""Owner-scoped APIs for content works and immutable versions."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from app.gateway.deps import get_current_user_from_request, get_personal_ip_content_repo
from deerflow.personal_ip.content_contracts import ContentWorkAppend, ContentWorkCreate

router = APIRouter(prefix="/api/personal-ip/content-works", tags=["personal-ip-content"])


async def _owner_id(request: Request) -> str:
    user = await get_current_user_from_request(request)
    return str(user.id)


@router.get("")
async def list_content_works(
    request: Request,
    include_archived: bool = Query(default=False),
    subject_id: str | None = Query(default=None, max_length=64),
    thread_id: str | None = Query(default=None, max_length=128),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, Any]]:
    return await get_personal_ip_content_repo(request).list(
        await _owner_id(request),
        include_archived=include_archived,
        subject_id=subject_id,
        thread_id=thread_id,
        limit=limit,
    )


@router.post("", status_code=201)
async def create_content_work(body: ContentWorkCreate, request: Request) -> dict[str, Any]:
    try:
        return await get_personal_ip_content_repo(request).create(
            owner_user_id=await _owner_id(request),
            request=body,
        )
    except ValueError as exc:
        status = 404 if str(exc) == "Personal-IP subject not found" else 409
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@router.get("/{content_work_id}")
async def get_content_work(content_work_id: str, request: Request) -> dict[str, Any]:
    result = await get_personal_ip_content_repo(request).get_lineage(
        content_work_id,
        owner_user_id=await _owner_id(request),
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Personal-IP content work not found")
    return result


@router.post("/{content_work_id}/versions", status_code=201)
async def append_content_versions(
    content_work_id: str,
    body: ContentWorkAppend,
    request: Request,
) -> dict[str, Any]:
    try:
        result = await get_personal_ip_content_repo(request).append(
            content_work_id,
            owner_user_id=await _owner_id(request),
            request=body,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Personal-IP content work not found")
    return result


@router.post("/{content_work_id}/archive")
async def archive_content_work(content_work_id: str, request: Request) -> dict[str, Any]:
    result = await get_personal_ip_content_repo(request).archive(
        content_work_id,
        owner_user_id=await _owner_id(request),
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Personal-IP content work not found")
    return result
