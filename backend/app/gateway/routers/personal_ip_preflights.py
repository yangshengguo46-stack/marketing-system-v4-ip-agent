"""Owner-scoped immutable Personal-IP audience preflight endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator

from app.gateway.deps import get_current_user_from_request, get_personal_ip_preflight_repo
from deerflow.personal_ip.audience_provider import (
    AUDIENCE_PREFLIGHT_CONTRACT_VERSION,
    AudiencePreflightRequest,
    AudiencePreflightResult,
)

router = APIRouter(prefix="/api/personal-ip/preflights", tags=["personal-ip"])


class PersonalIPPreflightSealRequest(BaseModel):
    operation_key: str = Field(min_length=1, max_length=256)
    subject_ids: list[str] = Field(default_factory=list, max_length=200)
    target_account_ids: list[str] = Field(default_factory=list, max_length=200)
    model_request: dict[str, Any]
    provider_receipt: dict[str, Any]

    @field_validator("operation_key")
    @classmethod
    def strip_operation_key(cls, value: str) -> str:
        return value.strip()


async def _current_user_id(request: Request) -> str:
    user = await get_current_user_from_request(request)
    return str(user.id)


def _validated_model_contract(
    body: PersonalIPPreflightSealRequest,
) -> tuple[AudiencePreflightRequest, AudiencePreflightResult]:
    payload = body.model_request
    if payload.get("contract_version") != AUDIENCE_PREFLIGHT_CONTRACT_VERSION:
        raise ValueError("Unsupported audience preflight contract")
    request = AudiencePreflightRequest(
        example=payload.get("example"),
        variant_count=payload.get("variant_count", 3),
    )
    if request.to_payload() != payload:
        raise ValueError("Audience preflight request was modified outside its contract")
    result = AudiencePreflightResult.model_validate(body.provider_receipt)
    if result.request_digest != request.request_digest:
        raise ValueError("Audience provider receipt does not match its request")
    if result.audience_basis != request.audience_basis:
        raise ValueError("Audience provider receipt uses a different audience basis")
    return request, result


@router.post("", status_code=201)
async def seal_personal_ip_preflight(
    body: PersonalIPPreflightSealRequest,
    request: Request,
) -> dict[str, Any]:
    try:
        model_request, provider_receipt = _validated_model_contract(body)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        return await get_personal_ip_preflight_repo(request).seal(
            owner_user_id=await _current_user_id(request),
            operation_key=body.operation_key,
            subject_ids=body.subject_ids,
            target_account_ids=body.target_account_ids,
            request=model_request,
            result=provider_receipt,
        )
    except ValueError as exc:
        status_code = 409 if "operation_key" in str(exc) else 422
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.get("")
async def list_personal_ip_preflights(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, Any]]:
    return await get_personal_ip_preflight_repo(request).list(
        await _current_user_id(request),
        limit=limit,
    )


@router.get("/{preflight_id}")
async def get_personal_ip_preflight(preflight_id: str, request: Request) -> dict[str, Any]:
    preflight = await get_personal_ip_preflight_repo(request).get(
        preflight_id,
        owner_user_id=await _current_user_id(request),
    )
    if preflight is None:
        raise HTTPException(status_code=404, detail="Personal-IP preflight not found")
    return preflight
