"""Personal-IP account management and thread binding endpoints."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator

from app.gateway.deps import (
    get_current_user_from_request,
    get_personal_ip_account_repo,
    get_thread_store,
)

router = APIRouter(prefix="/api/personal-ip", tags=["personal-ip"])


def _clean_list(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = value.strip()
        if not item or item in seen:
            continue
        cleaned.append(item)
        seen.add(item)
    return cleaned


class PersonalIPAccountCreateRequest(BaseModel):
    platform: str = Field(min_length=1, max_length=32)
    display_name: str = Field(min_length=1, max_length=128)
    handle: str | None = Field(default=None, max_length=128)
    avatar_url: str | None = Field(default=None, max_length=4096)
    promise_to_audience: str = Field(default="", max_length=4000)
    primary_audience: str = Field(default="", max_length=4000)
    content_pillars: list[str] = Field(default_factory=list, max_length=32)
    voice_and_boundaries: list[str] = Field(default_factory=list, max_length=32)
    business_goal: str = Field(default="", max_length=4000)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("platform", "display_name")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("content_pillars", "voice_and_boundaries")
    @classmethod
    def normalize_lists(cls, value: list[str]) -> list[str]:
        return _clean_list(value)


class PersonalIPAccountUpdateRequest(BaseModel):
    platform: str | None = Field(default=None, min_length=1, max_length=32)
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    handle: str | None = Field(default=None, max_length=128)
    avatar_url: str | None = Field(default=None, max_length=4096)
    promise_to_audience: str | None = Field(default=None, max_length=4000)
    primary_audience: str | None = Field(default=None, max_length=4000)
    content_pillars: list[str] | None = Field(default=None, max_length=32)
    voice_and_boundaries: list[str] | None = Field(default=None, max_length=32)
    business_goal: str | None = Field(default=None, max_length=4000)
    status: Literal["active", "archived"] | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("platform", "display_name")
    @classmethod
    def strip_optional_required_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("content_pillars", "voice_and_boundaries")
    @classmethod
    def normalize_optional_lists(cls, value: list[str] | None) -> list[str] | None:
        return _clean_list(value) if value is not None else None


class PersonalIPThreadBindingRequest(BaseModel):
    account_id: str | None = Field(default=None, max_length=64)


async def _current_user_id(request: Request) -> str:
    user = await get_current_user_from_request(request)
    return str(user.id)


@router.get("/accounts")
async def list_personal_ip_accounts(
    request: Request,
    include_archived: bool = Query(default=False),
) -> list[dict[str, Any]]:
    repo = get_personal_ip_account_repo(request)
    return await repo.list(
        await _current_user_id(request),
        include_archived=include_archived,
    )


@router.post("/accounts", status_code=201)
async def create_personal_ip_account(
    body: PersonalIPAccountCreateRequest,
    request: Request,
) -> dict[str, Any]:
    repo = get_personal_ip_account_repo(request)
    return await repo.create(
        owner_user_id=await _current_user_id(request),
        **body.model_dump(),
    )


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
    account = await repo.update(
        account_id,
        owner_user_id=await _current_user_id(request),
        updates=body.model_dump(exclude_unset=True),
    )
    if account is None:
        raise HTTPException(status_code=404, detail="Personal-IP account not found")
    return account


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


@router.put("/threads/{thread_id}/account")
async def bind_personal_ip_account_to_thread(
    thread_id: str,
    body: PersonalIPThreadBindingRequest,
    request: Request,
) -> dict[str, Any]:
    user_id = await _current_user_id(request)
    thread_store = get_thread_store(request)
    if not await thread_store.check_access(thread_id, user_id, require_existing=True):
        raise HTTPException(status_code=404, detail="Thread not found")

    if body.account_id:
        repo = get_personal_ip_account_repo(request)
        account = await repo.get(body.account_id, owner_user_id=user_id)
        if account is None or account.get("status") != "active":
            raise HTTPException(status_code=404, detail="Personal-IP account not found")

    await thread_store.update_metadata(
        thread_id,
        {"personal_ip_account_id": body.account_id},
        user_id=user_id,
    )
    return {"thread_id": thread_id, "account_id": body.account_id}
