"""Whole-portfolio Personal-IP operating cockpit endpoint."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from app.gateway.deps import (
    get_current_user_from_request,
    get_personal_ip_account_repo,
    get_personal_ip_brand_repo,
    get_personal_ip_evidence_promotion_repo,
    get_personal_ip_metric_repo,
    get_personal_ip_platform_observation_repo,
    get_personal_ip_preflight_repo,
    get_personal_ip_publish_receipt_repo,
    get_personal_ip_retrospective_repo,
    get_personal_ip_subject_repo,
    get_personal_ip_video_production_repo,
)
from deerflow.personal_ip.operating_cockpit import PersonalIPOperatingCockpitService

router = APIRouter(prefix="/api/personal-ip/cockpit", tags=["personal-ip"])


def _cockpit_service(request: Request) -> PersonalIPOperatingCockpitService:
    return PersonalIPOperatingCockpitService(
        subjects=get_personal_ip_subject_repo(request),
        accounts=get_personal_ip_account_repo(request),
        brand=get_personal_ip_brand_repo(request),
        preflights=get_personal_ip_preflight_repo(request),
        publish_receipts=get_personal_ip_publish_receipt_repo(request),
        metrics=get_personal_ip_metric_repo(request),
        platform_observations=get_personal_ip_platform_observation_repo(request),
        retrospectives=get_personal_ip_retrospective_repo(request),
        evidence_promotions=get_personal_ip_evidence_promotion_repo(request),
        video_productions=get_personal_ip_video_production_repo(request),
    )


@router.get("")
async def get_personal_ip_operating_cockpit(request: Request) -> dict[str, Any]:
    user = await get_current_user_from_request(request)
    return await _cockpit_service(request).build(owner_user_id=str(user.id))
