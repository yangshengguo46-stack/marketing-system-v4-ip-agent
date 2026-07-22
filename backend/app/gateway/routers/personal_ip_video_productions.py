"""Auditable Personal-IP video production orchestration endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.gateway.deps import get_current_user_from_request, get_personal_ip_video_production_repo

router = APIRouter(prefix="/api/personal-ip/video-productions", tags=["personal-ip"])

VideoEventType = Literal[
    "blueprint_sealed",
    "asset_registered",
    "storyboard_sealed",
    "shot_generation_requested",
    "shot_generation_completed",
    "shot_generation_failed",
    "consistency_checked",
    "candidate_selected",
    "review_requested",
    "review_recorded",
    "voice_generated",
    "edit_completed",
    "delivery_completed",
]


class PersonalIPVideoProductionBeginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_key: str = Field(min_length=1, max_length=256)
    title: str = Field(min_length=1, max_length=256)
    subject_id: str | None = Field(default=None, max_length=64)
    target_account_ids: list[str] = Field(default_factory=list, max_length=200)
    source_kind: Literal["idea", "script"]
    source: dict[str, Any]
    delivery_spec: dict[str, Any]
    provider_policy: dict[str, Any] = Field(default_factory=dict)
    budget: dict[str, Any] = Field(default_factory=dict)

    @field_validator("operation_key", "title")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        return value.strip()


class PersonalIPVideoProductionEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_key: str = Field(min_length=1, max_length=256)
    event_type: VideoEventType
    status: Literal["planned", "running", "succeeded", "failed", "awaiting_review", "approved", "rejected"]
    entity_type: Literal["production", "character", "scene", "prop", "shot", "candidate", "audio", "timeline", "delivery"]
    entity_id: str = Field(min_length=1, max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict)
    input_refs: list[str] = Field(default_factory=list, max_length=500)
    output_refs: list[str] = Field(default_factory=list, max_length=500)
    provider: str = Field(default="deerflow", min_length=1, max_length=80)
    model: str | None = Field(default=None, max_length=160)
    provider_task_id: str | None = Field(default=None, max_length=256)
    cost: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime | None = None

    @field_validator("event_key", "entity_id", "provider")
    @classmethod
    def strip_event_text(cls, value: str) -> str:
        return value.strip()


async def _current_user_id(request: Request) -> str:
    user = await get_current_user_from_request(request)
    return str(user.id)


def _repository_error(exc: ValueError) -> HTTPException:
    detail = str(exc)
    if "already records" in detail or "terminal" in detail:
        return HTTPException(status_code=409, detail=detail)
    if "not found" in detail:
        return HTTPException(status_code=404, detail=detail)
    return HTTPException(status_code=422, detail=detail)


@router.post("", status_code=201)
async def begin_personal_ip_video_production(
    body: PersonalIPVideoProductionBeginRequest,
    request: Request,
) -> dict[str, Any]:
    try:
        return await get_personal_ip_video_production_repo(request).begin(
            owner_user_id=await _current_user_id(request),
            **body.model_dump(),
        )
    except ValueError as exc:
        raise _repository_error(exc) from exc


@router.post("/{production_id}/events")
async def append_personal_ip_video_production_event(
    production_id: str,
    body: PersonalIPVideoProductionEventRequest,
    request: Request,
) -> dict[str, Any]:
    try:
        production = await get_personal_ip_video_production_repo(request).append_event(
            production_id,
            owner_user_id=await _current_user_id(request),
            **body.model_dump(),
        )
    except ValueError as exc:
        raise _repository_error(exc) from exc
    if production is None:
        raise HTTPException(status_code=404, detail="Personal-IP video production not found")
    return production


@router.get("")
async def list_personal_ip_video_productions(
    request: Request,
    status: Literal["draft", "running", "awaiting_review", "blocked", "completed", "cancelled"] | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, Any]]:
    return await get_personal_ip_video_production_repo(request).list(
        await _current_user_id(request),
        status=status,
        limit=limit,
    )


@router.get("/{production_id}")
async def get_personal_ip_video_production(production_id: str, request: Request) -> dict[str, Any]:
    production = await get_personal_ip_video_production_repo(request).get(
        production_id,
        owner_user_id=await _current_user_id(request),
    )
    if production is None:
        raise HTTPException(status_code=404, detail="Personal-IP video production not found")
    return production
