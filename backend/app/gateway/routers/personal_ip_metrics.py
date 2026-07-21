"""Owner-scoped metric observation and cross-platform aggregate endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator

from app.gateway.deps import get_current_user_from_request, get_personal_ip_metric_repo

router = APIRouter(prefix="/api/personal-ip/metrics", tags=["personal-ip"])


class PersonalIPMetricObservationRequest(BaseModel):
    observation_key: str = Field(min_length=1, max_length=256)
    series_key: str | None = Field(default=None, max_length=256)
    account_id: str = Field(min_length=1, max_length=64)
    receipt_id: str | None = Field(default=None, max_length=64)
    scope: Literal["account", "post"]
    metric_mode: Literal["window_total", "delta", "snapshot"]
    source: Literal["platform_api", "ui_tars", "browser", "manual"]
    status: Literal["observed", "partial", "unavailable"]
    window_started_at: datetime | None = None
    window_ended_at: datetime | None = None
    observed_at: datetime
    metrics: dict[str, int | float] = Field(default_factory=dict)
    coverage: dict[str, Any] = Field(default_factory=dict)

    @field_validator("observation_key", "account_id")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        return value.strip()


async def _current_user_id(request: Request) -> str:
    user = await get_current_user_from_request(request)
    return str(user.id)


def _repository_error(exc: ValueError) -> HTTPException:
    detail = str(exc)
    if "already records" in detail:
        return HTTPException(status_code=409, detail=detail)
    if "not found" in detail:
        return HTTPException(status_code=404, detail=detail)
    return HTTPException(status_code=422, detail=detail)


@router.post("", status_code=201)
async def record_personal_ip_metric(
    body: PersonalIPMetricObservationRequest,
    request: Request,
) -> dict[str, Any]:
    try:
        return await get_personal_ip_metric_repo(request).record(
            owner_user_id=await _current_user_id(request),
            observation_key=body.observation_key,
            series_key=body.series_key,
            account_id=body.account_id,
            receipt_id=body.receipt_id,
            scope=body.scope,
            metric_mode=body.metric_mode,
            source=body.source,
            status=body.status,
            window_started_at=body.window_started_at,
            window_ended_at=body.window_ended_at,
            observed_at=body.observed_at,
            metrics=body.metrics,
            coverage=body.coverage,
        )
    except ValueError as exc:
        raise _repository_error(exc) from exc


@router.get("/aggregate")
async def aggregate_personal_ip_metrics(
    request: Request,
    window_started_at: datetime = Query(),
    window_ended_at: datetime = Query(),
) -> dict[str, Any]:
    try:
        return await get_personal_ip_metric_repo(request).aggregate(
            owner_user_id=await _current_user_id(request),
            window_started_at=window_started_at,
            window_ended_at=window_ended_at,
        )
    except ValueError as exc:
        raise _repository_error(exc) from exc


@router.get("")
async def list_personal_ip_metrics(
    request: Request,
    account_id: str | None = Query(default=None, max_length=64),
    receipt_id: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, Any]]:
    return await get_personal_ip_metric_repo(request).list(
        await _current_user_id(request),
        account_id=account_id,
        receipt_id=receipt_id,
        limit=limit,
    )


@router.get("/{observation_id}")
async def get_personal_ip_metric(observation_id: str, request: Request) -> dict[str, Any]:
    observation = await get_personal_ip_metric_repo(request).get(
        observation_id,
        owner_user_id=await _current_user_id(request),
    )
    if observation is None:
        raise HTTPException(status_code=404, detail="Personal-IP metric observation not found")
    return observation
