"""Cross-sample Personal-IP evidence proposal, decision and export endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator

from app.gateway.deps import get_current_user_from_request, get_personal_ip_evidence_promotion_repo

router = APIRouter(prefix="/api/personal-ip/evidence-promotions", tags=["personal-ip"])


class PersonalIPEvidenceProposalRequest(BaseModel):
    proposal_key: str = Field(min_length=1, max_length=256)
    evidence_type: Literal["audience_pattern", "content_pattern", "platform_pattern", "training_cohort"]
    claim: str = Field(min_length=1, max_length=2000)
    retrospective_ids: list[str] = Field(min_length=3, max_length=100)
    minimum_support: int = Field(default=3, ge=3, le=100)

    @field_validator("proposal_key", "claim")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        return value.strip()


class PersonalIPEvidenceDecisionRequest(BaseModel):
    decision_key: str = Field(min_length=1, max_length=256)
    decision: Literal["approved", "rejected"]
    rationale: str = Field(min_length=1, max_length=2000)
    confirmed_by_user: Literal[True]
    occurred_at: datetime | None = None

    @field_validator("decision_key", "rationale")
    @classmethod
    def strip_decision_text(cls, value: str) -> str:
        return value.strip()


async def _current_user_id(request: Request) -> str:
    user = await get_current_user_from_request(request)
    return str(user.id)


def _repository_error(exc: ValueError) -> HTTPException:
    detail = str(exc)
    if "already records" in detail or "terminal decision" in detail:
        return HTTPException(status_code=409, detail=detail)
    if "not found" in detail:
        return HTTPException(status_code=404, detail=detail)
    return HTTPException(status_code=422, detail=detail)


@router.post("", status_code=201)
async def propose_personal_ip_evidence(
    body: PersonalIPEvidenceProposalRequest,
    request: Request,
) -> dict[str, Any]:
    try:
        return await get_personal_ip_evidence_promotion_repo(request).propose(
            owner_user_id=await _current_user_id(request),
            proposal_key=body.proposal_key,
            evidence_type=body.evidence_type,
            claim=body.claim,
            retrospective_ids=body.retrospective_ids,
            minimum_support=body.minimum_support,
        )
    except ValueError as exc:
        raise _repository_error(exc) from exc


@router.post("/{promotion_id}/decisions")
async def decide_personal_ip_evidence(
    promotion_id: str,
    body: PersonalIPEvidenceDecisionRequest,
    request: Request,
) -> dict[str, Any]:
    try:
        promotion = await get_personal_ip_evidence_promotion_repo(request).decide(
            promotion_id,
            owner_user_id=await _current_user_id(request),
            decision_key=body.decision_key,
            decision=body.decision,
            rationale=body.rationale,
            confirmed_by_user=body.confirmed_by_user,
            occurred_at=body.occurred_at,
        )
    except ValueError as exc:
        raise _repository_error(exc) from exc
    if promotion is None:
        raise HTTPException(status_code=404, detail="Personal-IP evidence promotion not found")
    return promotion


@router.get("")
async def list_personal_ip_evidence_promotions(
    request: Request,
    status: Literal["proposed", "approved", "rejected"] | None = Query(default=None),
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
