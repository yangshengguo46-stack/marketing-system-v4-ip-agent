"""Owner-scoped Personal-IP publish operation and attempt endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.gateway.deps import get_current_user_from_request, get_personal_ip_publish_receipt_repo

router = APIRouter(prefix="/api/personal-ip/publish-receipts", tags=["personal-ip"])


class PersonalIPPublishBeginRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    operation_key: str = Field(min_length=1, max_length=256)
    idempotency_key: str = Field(min_length=1, max_length=256)
    account_id: str = Field(min_length=1, max_length=64)
    executor: Literal["platform_api", "ui_tars", "browser", "manual"]
    request_payload: dict[str, Any] = Field(alias="request")

    @field_validator("operation_key", "idempotency_key", "account_id")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        return value.strip()


class PersonalIPPublishAttemptRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    attempt_key: str = Field(min_length=1, max_length=256)
    status: Literal["pending", "published", "failed", "unknown", "deleted"]
    result_payload: dict[str, Any] = Field(default_factory=dict, alias="result")
    occurred_at: datetime | None = None
    external_post_id: str | None = Field(default=None, max_length=256)
    external_url: str | None = Field(default=None, max_length=4096)

    @field_validator("attempt_key")
    @classmethod
    def strip_attempt_key(cls, value: str) -> str:
        return value.strip()


async def _current_user_id(request: Request) -> str:
    user = await get_current_user_from_request(request)
    return str(user.id)


def _repository_error(exc: ValueError) -> HTTPException:
    detail = str(exc)
    if "already records" in detail or "cannot transition" in detail or "cannot be replaced" in detail:
        return HTTPException(status_code=409, detail=detail)
    if "not found" in detail or "outside the sealed" in detail:
        return HTTPException(status_code=404, detail=detail)
    return HTTPException(status_code=422, detail=detail)


@router.post("", status_code=201)
async def begin_personal_ip_publish(
    body: PersonalIPPublishBeginRequest,
    request: Request,
) -> dict[str, Any]:
    try:
        if body.executor == "browser":
            raise ValueError("browser receipts must use personal_ip_prepare_browser_publish")
        return await get_personal_ip_publish_receipt_repo(request).begin(
            owner_user_id=await _current_user_id(request),
            operation_key=body.operation_key,
            idempotency_key=body.idempotency_key,
            account_id=body.account_id,
            executor=body.executor,
            request_payload=body.request_payload,
        )
    except ValueError as exc:
        raise _repository_error(exc) from exc


@router.post("/{receipt_id}/attempts")
async def record_personal_ip_publish_attempt(
    receipt_id: str,
    body: PersonalIPPublishAttemptRequest,
    request: Request,
) -> dict[str, Any]:
    try:
        repository = get_personal_ip_publish_receipt_repo(request)
        owner_user_id = await _current_user_id(request)
        existing = await repository.get(receipt_id, owner_user_id=owner_user_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Personal-IP publish receipt not found")
        if existing.get("executor") == "browser":
            raise ValueError("browser receipts must use personal_ip_finish_browser_publish")
        receipt = await repository.record_attempt(
            receipt_id,
            owner_user_id=owner_user_id,
            attempt_key=body.attempt_key,
            status=body.status,
            result_payload=body.result_payload,
            occurred_at=body.occurred_at,
            external_post_id=body.external_post_id,
            external_url=body.external_url,
        )
    except ValueError as exc:
        raise _repository_error(exc) from exc
    if receipt is None:
        raise HTTPException(status_code=404, detail="Personal-IP publish receipt not found")
    return receipt


@router.get("")
async def list_personal_ip_publish_receipts(
    request: Request,
    account_id: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, Any]]:
    return await get_personal_ip_publish_receipt_repo(request).list(
        await _current_user_id(request),
        account_id=account_id,
        limit=limit,
    )


@router.get("/{receipt_id}")
async def get_personal_ip_publish_receipt(receipt_id: str, request: Request) -> dict[str, Any]:
    receipt = await get_personal_ip_publish_receipt_repo(request).get(
        receipt_id,
        owner_user_id=await _current_user_id(request),
    )
    if receipt is None:
        raise HTTPException(status_code=404, detail="Personal-IP publish receipt not found")
    return receipt
