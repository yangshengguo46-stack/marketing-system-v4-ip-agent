"""Owner-scoped immutable Personal-IP retrospective endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator

from app.gateway.deps import get_current_user_from_request, get_personal_ip_retrospective_repo

router = APIRouter(prefix="/api/personal-ip/retrospectives", tags=["personal-ip"])


class PersonalIPRetrospectiveSealRequest(BaseModel):
    review_key: str = Field(min_length=1, max_length=256)
    publish_receipt_id: str = Field(min_length=1, max_length=64)
    horizon: str = Field(min_length=1, max_length=32)
    metric_observation_ids: list[str] = Field(min_length=1, max_length=100)

    @field_validator("review_key", "publish_receipt_id", "horizon")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        return value.strip()


async def _current_user_id(request: Request) -> str:
    user = await get_current_user_from_request(request)
    return str(user.id)


def _repository_error(exc: ValueError) -> HTTPException:
    detail = str(exc)
    if "already seals" in detail:
        return HTTPException(status_code=409, detail=detail)
    if "not found" in detail:
        return HTTPException(status_code=404, detail=detail)
    return HTTPException(status_code=422, detail=detail)


@router.post("", status_code=201)
async def seal_personal_ip_retrospective(
    body: PersonalIPRetrospectiveSealRequest,
    request: Request,
) -> dict[str, Any]:
    try:
        return await get_personal_ip_retrospective_repo(request).seal(
            owner_user_id=await _current_user_id(request),
            review_key=body.review_key,
            publish_receipt_id=body.publish_receipt_id,
            horizon=body.horizon,
            metric_observation_ids=body.metric_observation_ids,
        )
    except ValueError as exc:
        raise _repository_error(exc) from exc


@router.get("")
async def list_personal_ip_retrospectives(
    request: Request,
    account_id: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, Any]]:
    return await get_personal_ip_retrospective_repo(request).list(
        await _current_user_id(request),
        account_id=account_id,
        limit=limit,
    )


@router.get("/{retrospective_id}")
async def get_personal_ip_retrospective(retrospective_id: str, request: Request) -> dict[str, Any]:
    retrospective = await get_personal_ip_retrospective_repo(request).get(
        retrospective_id,
        owner_user_id=await _current_user_id(request),
    )
    if retrospective is None:
        raise HTTPException(status_code=404, detail="Personal-IP retrospective not found")
    return retrospective
