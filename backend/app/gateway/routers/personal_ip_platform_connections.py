"""Account-level platform authorization routes for the personal-IP product."""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field, field_validator

from app.gateway.deps import (
    get_current_user_from_request,
    get_personal_ip_platform_connection_repo,
)
from deerflow.personal_ip.douyin_oauth import DouyinMiniAppOAuthClient, DouyinOAuthError

router = APIRouter(prefix="/api/personal-ip/platform-connections", tags=["personal-ip"])

_DOUYIN_PLATFORM = "douyin"
_DOUYIN_VIDEO_SCOPE = "ma.video.bind"
_AUTHORIZATION_STATE_TTL = timedelta(minutes=10)


class DouyinAuthorizationSessionRequest(BaseModel):
    account_id: str = Field(min_length=1, max_length=64)

    @field_validator("account_id")
    @classmethod
    def strip_account_id(cls, value: str) -> str:
        return value.strip()


class DouyinAuthorizationCompletionRequest(BaseModel):
    state: str = Field(min_length=16, max_length=512)
    authorization_ticket: str = Field(min_length=1, max_length=2048)
    login_code: str = Field(min_length=1, max_length=2048)

    @field_validator("state", "authorization_ticket", "login_code")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        return value.strip()


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _get_douyin_oauth_client() -> DouyinMiniAppOAuthClient:
    app_id = os.environ.get("DOUYIN_MINI_APP_ID", "").strip()
    app_secret = os.environ.get("DOUYIN_MINI_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        raise HTTPException(
            status_code=503,
            detail="Douyin mini-app authorization is not configured",
        )
    return DouyinMiniAppOAuthClient(app_id=app_id, app_secret=app_secret)


async def _current_user_id(request: Request) -> str:
    user = await get_current_user_from_request(request)
    return str(user.id)


def _repository_error(exc: ValueError) -> HTTPException:
    detail = str(exc)
    if "already connected" in detail:
        return HTTPException(status_code=409, detail=detail)
    if "not found" in detail:
        return HTTPException(status_code=404, detail=detail)
    return HTTPException(status_code=422, detail=detail)


def _provider_error(exc: DouyinOAuthError) -> HTTPException:
    if exc.category == "reauthorization_required":
        return HTTPException(status_code=409, detail="Douyin authorization must be completed again")
    if exc.retryable:
        return HTTPException(status_code=503, detail="Douyin authorization service is temporarily unavailable")
    return HTTPException(status_code=422, detail="Douyin rejected the authorization request")


@router.post("/douyin/authorization-sessions", status_code=201)
async def begin_douyin_authorization(
    body: DouyinAuthorizationSessionRequest,
    request: Request,
) -> dict[str, Any]:
    owner_user_id = await _current_user_id(request)
    oauth_client = _get_douyin_oauth_client()
    now = _utc_now()
    try:
        state = await get_personal_ip_platform_connection_repo(request).create_oauth_state(
            owner_user_id=owner_user_id,
            account_id=body.account_id,
            platform=_DOUYIN_PLATFORM,
            requested_scopes=[_DOUYIN_VIDEO_SCOPE],
            expires_at=now + _AUTHORIZATION_STATE_TTL,
            now=now,
        )
    except ValueError as exc:
        raise _repository_error(exc) from exc
    return {
        **state,
        "authorization_channel": "douyin_mini_app",
        "mini_app_api": "tt.showDouyinOpenAuth",
        "app_id": oauth_client.app_id,
        "scope_list": [_DOUYIN_VIDEO_SCOPE],
        "completion_endpoint": "/api/personal-ip/platform-connections/douyin/authorization-sessions/complete",
    }


@router.post("/douyin/authorization-sessions/complete")
async def complete_douyin_authorization(
    body: DouyinAuthorizationCompletionRequest,
    request: Request,
) -> dict[str, Any]:
    owner_user_id = await _current_user_id(request)
    repository = get_personal_ip_platform_connection_repo(request)
    state = await repository.consume_oauth_state(
        state=body.state,
        owner_user_id=owner_user_id,
        now=_utc_now(),
    )
    if state is None or state["platform"] != _DOUYIN_PLATFORM:
        raise HTTPException(status_code=409, detail="Authorization session is invalid, expired, or already consumed")

    oauth_client = _get_douyin_oauth_client()
    try:
        grant, identity = await asyncio.gather(
            oauth_client.exchange_permission_ticket(body.authorization_ticket),
            oauth_client.exchange_login_code(body.login_code),
        )
        now = _utc_now()
        scopes = grant.scopes
        if _DOUYIN_VIDEO_SCOPE not in scopes:
            raise HTTPException(status_code=422, detail="Douyin video-data permission was not granted")
        return await repository.store_grant(
            owner_user_id=owner_user_id,
            account_id=state["account_id"],
            platform=_DOUYIN_PLATFORM,
            external_user_id=identity.open_id,
            oauth_open_id=grant.oauth_open_id,
            access_token=grant.access_token,
            refresh_token=grant.refresh_token,
            scopes=scopes,
            access_expires_at=now + timedelta(seconds=grant.expires_in),
            refresh_expires_at=now + timedelta(seconds=grant.refresh_expires_in),
            now=now,
        )
    except DouyinOAuthError as exc:
        raise _provider_error(exc) from exc
    except ValueError as exc:
        raise _repository_error(exc) from exc


@router.get("")
async def list_platform_connections(
    request: Request,
    include_revoked: bool = Query(default=False),
) -> list[dict[str, Any]]:
    return await get_personal_ip_platform_connection_repo(request).list(
        await _current_user_id(request),
        include_revoked=include_revoked,
    )


@router.post("/{connection_id}/refresh")
async def refresh_platform_connection(connection_id: str, request: Request) -> dict[str, Any]:
    owner_user_id = await _current_user_id(request)
    repository = get_personal_ip_platform_connection_repo(request)
    connection = await repository.get(connection_id, owner_user_id=owner_user_id)
    if connection is None:
        raise HTTPException(status_code=404, detail="Personal-IP platform connection not found")
    if connection["platform"] != _DOUYIN_PLATFORM:
        raise HTTPException(status_code=422, detail="Platform connection does not support token refresh")
    credentials = await repository.get_credentials(connection_id, owner_user_id=owner_user_id)
    if credentials is None:
        raise HTTPException(status_code=409, detail="Platform connection must be authorized again")
    try:
        grant = await _get_douyin_oauth_client().refresh(credentials["refresh_token"])
        now = _utc_now()
        return await repository.store_grant(
            owner_user_id=owner_user_id,
            account_id=connection["account_id"],
            platform=connection["platform"],
            external_user_id=connection["external_user_id"],
            oauth_open_id=grant.oauth_open_id or connection.get("oauth_open_id"),
            access_token=grant.access_token,
            refresh_token=grant.refresh_token,
            scopes=grant.scopes or connection["scopes"],
            access_expires_at=now + timedelta(seconds=grant.expires_in),
            refresh_expires_at=now + timedelta(seconds=grant.refresh_expires_in),
            now=now,
        )
    except DouyinOAuthError as exc:
        raise _provider_error(exc) from exc
    except ValueError as exc:
        raise _repository_error(exc) from exc


@router.delete("/{connection_id}", status_code=204)
async def disconnect_platform_connection(connection_id: str, request: Request) -> Response:
    deleted = await get_personal_ip_platform_connection_repo(request).revoke(
        connection_id,
        owner_user_id=await _current_user_id(request),
        now=_utc_now(),
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Personal-IP platform connection not found")
    return Response(status_code=204)
