"""Owner-scoped Personal-IP subject and account registry endpoints."""

from __future__ import annotations

import asyncio
import logging
import shutil
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator

from app.gateway.deps import (
    get_current_user_from_request,
    get_personal_ip_account_repo,
    get_personal_ip_subject_repo,
)
from deerflow.community.browser_automation import get_browser_session_manager
from deerflow.config.paths import get_paths
from deerflow.personal_ip.browser_profiles import build_browser_account_target

router = APIRouter(prefix="/api/personal-ip", tags=["personal-ip"])
logger = logging.getLogger(__name__)


class PersonalIPAccountCreateRequest(BaseModel):
    subject_id: str | None = Field(default=None, max_length=64)
    platform: str = Field(min_length=1, max_length=32)
    display_name: str = Field(min_length=1, max_length=128)
    handle: str | None = Field(default=None, max_length=128)
    avatar_url: str | None = Field(default=None, max_length=4096)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("platform", "display_name")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        return value.strip()


class PersonalIPAccountUpdateRequest(BaseModel):
    subject_id: str | None = Field(default=None, max_length=64)
    platform: str | None = Field(default=None, min_length=1, max_length=32)
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    handle: str | None = Field(default=None, max_length=128)
    avatar_url: str | None = Field(default=None, max_length=4096)
    status: Literal["active", "archived"] | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("platform", "display_name")
    @classmethod
    def strip_optional_required_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


class PersonalIPSubjectCreateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=128)
    subject_type: Literal["creator", "brand", "organization"] = "creator"
    relationship: Literal["self", "client", "partner"] = "self"
    description: str = Field(default="", max_length=4000)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("display_name")
    @classmethod
    def strip_display_name(cls, value: str) -> str:
        return value.strip()


class PersonalIPSubjectUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    subject_type: Literal["creator", "brand", "organization"] | None = None
    relationship: Literal["self", "client", "partner"] | None = None
    description: str | None = Field(default=None, max_length=4000)
    status: Literal["active", "archived"] | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("display_name")
    @classmethod
    def strip_optional_display_name(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


async def _current_user_id(request: Request) -> str:
    user = await get_current_user_from_request(request)
    return str(user.id)


@router.get("/subjects")
async def list_personal_ip_subjects(
    request: Request,
    include_archived: bool = Query(default=False),
) -> list[dict[str, Any]]:
    repo = get_personal_ip_subject_repo(request)
    return await repo.list(
        await _current_user_id(request),
        include_archived=include_archived,
    )


@router.post("/subjects", status_code=201)
async def create_personal_ip_subject(
    body: PersonalIPSubjectCreateRequest,
    request: Request,
) -> dict[str, Any]:
    repo = get_personal_ip_subject_repo(request)
    return await repo.create(
        owner_user_id=await _current_user_id(request),
        **body.model_dump(),
    )


@router.get("/subjects/{subject_id}")
async def get_personal_ip_subject(subject_id: str, request: Request) -> dict[str, Any]:
    repo = get_personal_ip_subject_repo(request)
    subject = await repo.get(subject_id, owner_user_id=await _current_user_id(request))
    if subject is None:
        raise HTTPException(status_code=404, detail="Personal-IP subject not found")
    return subject


@router.patch("/subjects/{subject_id}")
async def update_personal_ip_subject(
    subject_id: str,
    body: PersonalIPSubjectUpdateRequest,
    request: Request,
) -> dict[str, Any]:
    repo = get_personal_ip_subject_repo(request)
    subject = await repo.update(
        subject_id,
        owner_user_id=await _current_user_id(request),
        updates=body.model_dump(exclude_unset=True),
    )
    if subject is None:
        raise HTTPException(status_code=404, detail="Personal-IP subject not found")
    return subject


@router.delete("/subjects/{subject_id}")
async def delete_personal_ip_subject(
    subject_id: str,
    request: Request,
) -> dict[str, bool]:
    user_id = await _current_user_id(request)
    subject_repo = get_personal_ip_subject_repo(request)
    subject = await subject_repo.get(subject_id, owner_user_id=user_id)
    if subject is None:
        raise HTTPException(status_code=404, detail="Personal-IP subject not found")
    accounts = await get_personal_ip_account_repo(request).list(
        user_id,
        include_archived=True,
        subject_id=subject_id,
    )
    if accounts:
        raise HTTPException(
            status_code=409,
            detail="Detach or reassign this subject's accounts before deleting it",
        )
    await subject_repo.delete(subject_id, owner_user_id=user_id)
    return {"success": True}


@router.get("/accounts")
async def list_personal_ip_accounts(
    request: Request,
    include_archived: bool = Query(default=False),
    subject_id: str | None = Query(default=None, max_length=64),
) -> list[dict[str, Any]]:
    repo = get_personal_ip_account_repo(request)
    return await repo.list(
        await _current_user_id(request),
        include_archived=include_archived,
        subject_id=subject_id,
    )


@router.post("/accounts", status_code=201)
async def create_personal_ip_account(
    body: PersonalIPAccountCreateRequest,
    request: Request,
) -> dict[str, Any]:
    repo = get_personal_ip_account_repo(request)
    try:
        return await repo.create(
            owner_user_id=await _current_user_id(request),
            **body.model_dump(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/accounts/{account_id}")
async def get_personal_ip_account(account_id: str, request: Request) -> dict[str, Any]:
    repo = get_personal_ip_account_repo(request)
    account = await repo.get(account_id, owner_user_id=await _current_user_id(request))
    if account is None:
        raise HTTPException(status_code=404, detail="Personal-IP account not found")
    return account


@router.patch("/accounts/{account_id}")
async def update_personal_ip_account(
    account_id: str,
    body: PersonalIPAccountUpdateRequest,
    request: Request,
) -> dict[str, Any]:
    repo = get_personal_ip_account_repo(request)
    try:
        account = await repo.update(
            account_id,
            owner_user_id=await _current_user_id(request),
            updates=body.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if account is None:
        raise HTTPException(status_code=404, detail="Personal-IP account not found")
    return account


@router.post("/accounts/{account_id}/logout")
async def logout_personal_ip_account(
    account_id: str,
    request: Request,
) -> dict[str, Any]:
    """End one platform login and erase its persisted browser credentials."""
    user_id = await _current_user_id(request)
    repo = get_personal_ip_account_repo(request)
    account = await repo.get(account_id, owner_user_id=user_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Personal-IP account not found")

    profile_dir = get_paths().browser_profile_dir(account_id, user_id=user_id)
    try:
        target = build_browser_account_target(
            owner_user_id=user_id,
            account_id=account_id,
            platform=account["platform"],
            display_name=account["display_name"],
            user_data_dir=profile_dir,
        )
        await get_browser_session_manager().close_session(target.session_key)
        if profile_dir.exists():
            await asyncio.to_thread(shutil.rmtree, profile_dir)
    except (OSError, ValueError) as exc:
        logger.exception(
            "Failed to clear browser login for account_id=%s user_id=%s",
            account_id,
            user_id,
        )
        raise HTTPException(status_code=500, detail="Platform logout failed") from exc

    metadata = dict(account.get("metadata") or {})
    metadata.pop("browser_authenticated_at", None)
    metadata.update(
        {
            "browser_authenticated": False,
            "connection_mode": "local_browser_profile",
            "connection_state": "pending_login",
            "execution_ready": False,
            "logged_out_at": datetime.now(UTC).isoformat(),
        },
    )
    updated = await repo.update(
        account_id,
        owner_user_id=user_id,
        updates={"metadata": metadata},
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Personal-IP account not found")
    return updated


@router.delete("/accounts/{account_id}")
async def delete_personal_ip_account(
    account_id: str,
    request: Request,
) -> dict[str, bool]:
    repo = get_personal_ip_account_repo(request)
    deleted = await repo.delete(
        account_id,
        owner_user_id=await _current_user_id(request),
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Personal-IP account not found")
    return {"success": True}
