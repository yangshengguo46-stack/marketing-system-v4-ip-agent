"""Detailed credential-free platform business-data observation endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.gateway.deps import (
    get_current_user_from_request,
    get_personal_ip_account_repo,
    get_personal_ip_platform_observation_repo,
)
from deerflow.community.browser_automation.session import BrowserSessionCapacityError
from deerflow.persistence.personal_ip_platform_observations.sql import validate_credential_free_payload
from deerflow.personal_ip.browser_collection import (
    DouyinBrowserCollectionError,
    DouyinBrowserCollectionService,
    acquire_account_browser_session,
)

router = APIRouter(prefix="/api/personal-ip/platform-observations", tags=["personal-ip"])


class PersonalIPPlatformObservationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observation_key: str = Field(min_length=1, max_length=256)
    account_id: str = Field(min_length=1, max_length=64)
    dataset: Literal[
        "account_profile",
        "audience_analytics",
        "comments",
        "content_inventory",
        "content_metrics",
        "conversions",
        "dashboard",
        "platform_receipts",
        "traffic_sources",
    ]
    source: Literal["platform_api", "ui_tars", "browser", "manual"]
    status: Literal["observed", "partial", "unavailable"]
    source_url: str = Field(min_length=1, max_length=4096)
    observed_at: datetime
    records: list[dict[str, Any]] = Field(default_factory=list, max_length=2000)
    summary: dict[str, Any] = Field(default_factory=dict)
    coverage: dict[str, Any] = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)

    @field_validator("observation_key", "account_id", "source_url")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def reject_credential_material(self):
        validate_credential_free_payload(
            {
                "records": self.records,
                "summary": self.summary,
                "coverage": self.coverage,
                "evidence": self.evidence,
            },
            field="platform_observation",
        )
        return self


class DouyinBrowserCollectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str = Field(min_length=1, max_length=64)
    observation_key: str = Field(min_length=1, max_length=256)
    dataset: Literal[
        "account_profile",
        "audience_analytics",
        "comments",
        "content_inventory",
        "content_metrics",
        "conversions",
        "dashboard",
        "platform_receipts",
        "traffic_sources",
    ]
    target_url: str | None = Field(default=None, min_length=1, max_length=4096)

    @field_validator("account_id", "observation_key", "target_url")
    @classmethod
    def strip_collection_text(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value


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


def _douyin_browser_collection_service(request: Request) -> DouyinBrowserCollectionService:
    return DouyinBrowserCollectionService(
        accounts=get_personal_ip_account_repo(request),
        observations=get_personal_ip_platform_observation_repo(request),
    )


@router.post("/collect/browser/douyin", status_code=201)
async def collect_douyin_browser_observation(
    body: DouyinBrowserCollectionRequest,
    request: Request,
) -> dict[str, Any]:
    owner_user_id = await _current_user_id(request)
    account = await get_personal_ip_account_repo(request).get(body.account_id, owner_user_id=owner_user_id)
    if account is None or account.get("status") != "active" or account.get("platform") != "douyin":
        raise HTTPException(status_code=404, detail="Active Douyin account not found")
    try:
        with acquire_account_browser_session(owner_user_id=owner_user_id, account=account) as session:
            return await _douyin_browser_collection_service(request).collect_creator_page(
                owner_user_id=owner_user_id,
                account_id=body.account_id,
                observation_key=body.observation_key,
                dataset=body.dataset,
                target_url=body.target_url,
                session=session,
            )
    except BrowserSessionCapacityError as exc:
        raise HTTPException(status_code=429, detail="Browser session capacity is full") from exc
    except DouyinBrowserCollectionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise _repository_error(exc) from exc


@router.post("", status_code=201)
async def record_personal_ip_platform_observation(
    body: PersonalIPPlatformObservationRequest,
    request: Request,
) -> dict[str, Any]:
    try:
        return await get_personal_ip_platform_observation_repo(request).record(
            owner_user_id=await _current_user_id(request),
            observation_key=body.observation_key,
            account_id=body.account_id,
            dataset=body.dataset,
            source=body.source,
            status=body.status,
            source_url=body.source_url,
            observed_at=body.observed_at,
            records=body.records,
            summary=body.summary,
            coverage=body.coverage,
            evidence=body.evidence,
        )
    except ValueError as exc:
        raise _repository_error(exc) from exc


@router.get("")
async def list_personal_ip_platform_observations(
    request: Request,
    account_id: str | None = Query(default=None, max_length=64),
    dataset: str | None = Query(default=None, max_length=32),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, Any]]:
    return await get_personal_ip_platform_observation_repo(request).list(
        await _current_user_id(request),
        account_id=account_id,
        dataset=dataset,
        limit=limit,
    )


@router.get("/{observation_id}")
async def get_personal_ip_platform_observation(observation_id: str, request: Request) -> dict[str, Any]:
    observation = await get_personal_ip_platform_observation_repo(request).get(
        observation_id,
        owner_user_id=await _current_user_id(request),
    )
    if observation is None:
        raise HTTPException(status_code=404, detail="Personal-IP platform observation not found")
    return observation
