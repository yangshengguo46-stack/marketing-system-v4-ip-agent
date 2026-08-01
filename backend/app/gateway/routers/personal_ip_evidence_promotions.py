"""Read-only compatibility endpoints for historical evidence promotions."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request

from app.gateway.deps import get_current_user_from_request, get_personal_ip_evidence_promotion_repo

router = APIRouter(prefix="/api/personal-ip/evidence-promotions", tags=["personal-ip"])


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


@router.get("")
async def list_personal_ip_evidence_promotions(
    request: Request,
    status: Literal["approved"] | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, Any]]:
    return await get_personal_ip_evidence_promotion_repo(request).list(
        await _current_user_id(request),
        status=status,
        limit=limit,
    )


@router.get("/{promotion_id}/export")
async def export_personal_ip_evidence(promotion_id: str, request: Request) -> dict[str, Any]:
    try:
        manifest = await get_personal_ip_evidence_promotion_repo(request).export_approved(
            promotion_id,
            owner_user_id=await _current_user_id(request),
        )
    except ValueError as exc:
        raise _repository_error(exc) from exc
    if manifest is None:
        raise HTTPException(status_code=404, detail="Personal-IP evidence promotion not found")
    return manifest


@router.get("/{promotion_id}")
async def get_personal_ip_evidence_promotion(promotion_id: str, request: Request) -> dict[str, Any]:
    promotion = await get_personal_ip_evidence_promotion_repo(request).get(
        promotion_id,
        owner_user_id=await _current_user_id(request),
    )
    if promotion is None:
        raise HTTPException(status_code=404, detail="Personal-IP evidence promotion not found")
    return promotion
