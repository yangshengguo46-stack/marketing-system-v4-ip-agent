"""Owner- and thread-scoped MediaKit evidence paid-call decisions."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.gateway.authz import get_auth_context, require_permission
from app.gateway.evidence_paid_calls import (
    EvidencePaidCallConflictError,
    EvidencePaidCallNotFoundError,
    EvidencePaidCallUnapprovableError,
    get_evidence_paid_call_service,
)

router = APIRouter(prefix="/api/threads", tags=["ip-agent-evidence"])

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_SAFE_TEXT_FORBIDDEN_RE = re.compile(
    r"(?:https?://|file://|(?:token|cookie|password|secret|api[_-]?key)\s*[:=])",
    re.IGNORECASE,
)
_SAFE_OBJECT_REF_FORBIDDEN_RE = re.compile(
    r"(?:https?://|file://|[/\\]|(?:token|cookie|password|secret|api[_-]?key)\s*[:=])",
    re.IGNORECASE,
)
_PROVIDER_DISPLAY_NAMES = {
    "volcengine-mediakit": "火山引擎 AI MediaKit",
    "mediakit-cloud": "火山引擎 AI MediaKit",
}
_CAPABILITY_LABELS = {
    "asr": "语音转写",
    "ocr": "画面文字识别",
    "scene_segmentation": "场景分割",
    "storyline": "剧情理解",
}


class EvidencePaidCallDecisionRequest(BaseModel):
    """The complete browser-supplied decision payload.

    No owner, thread, run, provider, capability, source or cost field is
    accepted. Those values remain server authoritative.
    """

    model_config = ConfigDict(extra="forbid")

    decision: Literal["approve", "reject"]
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_version: int = Field(ge=1)


class EvidencePaidCallObjectView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    safe_ref: str = Field(min_length=1, max_length=96)
    sha256_prefix: str = Field(pattern=r"^[0-9a-f]{8,12}$")
    sha256_suffix: str = Field(pattern=r"^[0-9a-f]{8,12}$")
    duration_seconds: Decimal = Field(gt=0, max_digits=12, decimal_places=3)

    @field_validator("safe_ref")
    @classmethod
    def reject_path_url_or_secret_label(cls, value: str) -> str:
        clean = " ".join(value.split())
        if _SAFE_OBJECT_REF_FORBIDDEN_RE.search(clean):
            raise ValueError("unsafe evidence object reference")
        return clean


class EvidencePaidCallCostView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit_kind: Literal["provider_quote", "local_risk_limit", "unquoted"]
    maximum_amount_micros: int | None = Field(default=None, ge=0)
    currency: str = Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    billing_basis: str = Field(min_length=1, max_length=160)

    @field_validator("billing_basis")
    @classmethod
    def reject_path_url_or_secret_basis(cls, value: str) -> str:
        clean = " ".join(value.split())
        if _SAFE_TEXT_FORBIDDEN_RE.search(clean):
            raise ValueError("unsafe billing basis")
        return clean


class EvidencePaidCallRequestView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["ip-agent-evidence-paid-call-request-v2"] = "ip-agent-evidence-paid-call-request-v2"
    request_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    version: int = Field(ge=1)
    status: Literal[
        "pending",
        "approved",
        "rejected",
        "expired",
        "reserved",
        "consumed",
        "settled",
        "cancelled",
        "reconciliation_required",
    ]
    object: EvidencePaidCallObjectView
    provider: Literal["火山引擎 AI MediaKit"]
    capability: Literal["asr", "ocr", "scene_segmentation", "storyline"]
    capability_label: str = Field(min_length=1, max_length=32)
    single_use: Literal[True] = True
    cost: EvidencePaidCallCostView
    created_at: datetime
    expires_at: datetime
    approvable: bool
    unapprovable_reason: (
        Literal[
            "maximum_cost_not_quoted",
            "maximum_cost_not_positive",
            "expired",
            "not_pending",
        ]
        | None
    ) = None
    provider_content_hash_attested: Literal[False] = False
    successful_result_coverage: Literal["partial"] = "partial"


class EvidencePaidCallRequestList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["ip-agent-evidence-paid-call-request-list-v2"] = "ip-agent-evidence-paid-call-request-list-v2"
    requests: list[EvidencePaidCallRequestView]


def _required_text(raw: Mapping[str, Any], key: str) -> str:
    value = str(raw.get(key) or "").strip()
    if not value:
        raise ValueError(f"missing {key}")
    return value


def _aware_datetime(raw: Mapping[str, Any], key: str) -> datetime:
    value = raw.get(key)
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(_required_text(raw, key).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"{key} must include timezone")
    return parsed.astimezone(UTC)


def _normalized_status(value: Any, *, expires_at: datetime) -> str:
    status = str(value or "").strip().lower()
    aliases = {
        "requested": "pending",
        "admitted": "consumed",
        "released": "cancelled",
        "budget_rejected": "rejected",
    }
    normalized = aliases.get(status, status)
    if normalized == "pending" and expires_at <= datetime.now(UTC):
        return "expired"
    return normalized


def _duration_seconds(raw: Mapping[str, Any]) -> Decimal:
    if raw.get("source_duration_millis") is not None:
        return (Decimal(str(raw["source_duration_millis"])) / Decimal(1_000)).quantize(Decimal("0.001"))
    return Decimal(str(raw.get("duration_seconds") or "0")).quantize(Decimal("0.001"))


def _owner_user_id(request: Request) -> str:
    auth = get_auth_context(request)
    if auth is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return str(auth.require_user().id)


def _billing_basis(raw: Mapping[str, Any], capability: str) -> str:
    explicit = str(raw.get("billing_basis") or "").strip()
    if explicit:
        return explicit
    price_version = str(raw.get("price_version") or "").strip()
    suffix = f"，价格版本 {price_version}" if price_version else ""
    return f"按一次{_CAPABILITY_LABELS[capability]}任务计费{suffix}"


def build_evidence_paid_call_view(raw: Mapping[str, Any]) -> EvidencePaidCallRequestView:
    """Project an internal request onto the credential-free customer view."""

    provider_key = _required_text(raw, "provider").lower().replace("_", "-")
    provider = _PROVIDER_DISPLAY_NAMES.get(provider_key)
    if provider is None:
        raise ValueError("unsupported evidence paid-call provider")
    capability = _required_text(raw, "capability").lower()
    if capability not in _CAPABILITY_LABELS:
        raise ValueError("unsupported evidence paid-call capability")
    source_sha256 = _required_text(raw, "source_sha256").lower()
    if not _SHA256_RE.fullmatch(source_sha256):
        raise ValueError("invalid source_sha256")
    request_id = _required_text(raw, "request_id" if raw.get("request_id") else "id")
    if not _REQUEST_ID_RE.fullmatch(request_id):
        raise ValueError("invalid request_id")

    created_at = _aware_datetime(raw, "created_at")
    expires_at = _aware_datetime(raw, "expires_at")
    status = _normalized_status(raw.get("status"), expires_at=expires_at)
    maximum_amount_micros = raw.get("maximum_amount_micros")
    if isinstance(maximum_amount_micros, bool):
        maximum_amount_micros = None
    elif maximum_amount_micros is not None:
        maximum_amount_micros = int(maximum_amount_micros)
        if maximum_amount_micros < 0:
            maximum_amount_micros = None

    reason: str | None = None
    price_status = str(raw.get("price_status") or "unknown").strip().lower()
    if price_status not in {"quoted", "operator_capped"}:
        reason = "maximum_cost_not_quoted"
    elif maximum_amount_micros is None or maximum_amount_micros <= 0:
        reason = "maximum_cost_not_positive"
    elif status == "expired":
        reason = "expired"
    elif status != "pending":
        reason = "not_pending"

    return EvidencePaidCallRequestView.model_validate(
        {
            "request_id": request_id,
            "request_digest": _required_text(raw, "request_digest").lower(),
            "version": int(raw.get("version") or raw.get("event_count") or 0),
            "status": status,
            "object": {
                "safe_ref": _required_text(raw, "object_ref_label"),
                "sha256_prefix": source_sha256[:12],
                "sha256_suffix": source_sha256[-12:],
                "duration_seconds": _duration_seconds(raw),
            },
            "provider": provider,
            "capability": capability,
            "capability_label": _CAPABILITY_LABELS[capability],
            "single_use": True,
            "cost": {
                "limit_kind": {
                    "quoted": "provider_quote",
                    "operator_capped": "local_risk_limit",
                }.get(price_status, "unquoted"),
                "maximum_amount_micros": maximum_amount_micros,
                "currency": _required_text(raw, "currency").upper(),
                "billing_basis": _billing_basis(raw, capability),
            },
            "created_at": created_at,
            "expires_at": expires_at,
            "approvable": reason is None,
            "unapprovable_reason": reason,
            "provider_content_hash_attested": False,
            "successful_result_coverage": "partial",
        }
    )


def _decision_error(exc: Exception) -> HTTPException:
    if isinstance(exc, EvidencePaidCallNotFoundError):
        return HTTPException(status_code=404, detail="Evidence paid-call request not found")
    if isinstance(exc, EvidencePaidCallConflictError):
        return HTTPException(status_code=409, detail="Evidence paid-call request changed; reload before deciding")
    if isinstance(exc, EvidencePaidCallUnapprovableError):
        return HTTPException(status_code=422, detail="Evidence paid-call request cannot be approved")
    raise exc


@router.get(
    "/{thread_id}/evidence-paid-call-requests",
    response_model=EvidencePaidCallRequestList,
)
@require_permission("threads", "read", owner_check=True, require_existing=True)
async def list_evidence_paid_call_requests(
    thread_id: str,
    request: Request,
) -> EvidencePaidCallRequestList:
    owner_user_id = _owner_user_id(request)
    raw_requests = await get_evidence_paid_call_service(request).list_requests(
        owner_user_id=owner_user_id,
        thread_id=thread_id,
    )
    try:
        views = [build_evidence_paid_call_view(raw) for raw in raw_requests]
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=500,
            detail="Evidence paid-call request is not safe to display",
        ) from exc
    return EvidencePaidCallRequestList(requests=views)


@router.post(
    "/{thread_id}/evidence-paid-call-requests/{request_id}/decision",
    response_model=EvidencePaidCallRequestView,
)
@require_permission("threads", "write", owner_check=True, require_existing=True)
async def decide_evidence_paid_call_request(
    thread_id: str,
    request_id: str,
    body: EvidencePaidCallDecisionRequest,
    request: Request,
) -> EvidencePaidCallRequestView:
    owner_user_id = _owner_user_id(request)
    service = get_evidence_paid_call_service(request)

    # The service remains the atomic authority. This pre-check additionally
    # guarantees that this HTTP surface never forwards an approval for a
    # missing/non-positive cap, even if an injected adapter is incomplete.
    raw_requests = await service.list_requests(
        owner_user_id=owner_user_id,
        thread_id=thread_id,
    )
    candidate = next(
        (build_evidence_paid_call_view(raw) for raw in raw_requests if str(raw.get("request_id") or raw.get("id") or "") == request_id),
        None,
    )
    if candidate is None:
        raise HTTPException(status_code=404, detail="Evidence paid-call request not found")
    if body.decision == "approve" and not candidate.approvable:
        raise HTTPException(
            status_code=422,
            detail="Evidence paid-call request cannot be approved",
        )

    try:
        decided = await service.decide(
            owner_user_id=owner_user_id,
            thread_id=thread_id,
            request_id=request_id,
            decision=body.decision,
            request_digest=body.request_digest,
            expected_version=body.expected_version,
        )
        return build_evidence_paid_call_view(decided)
    except (
        EvidencePaidCallConflictError,
        EvidencePaidCallNotFoundError,
        EvidencePaidCallUnapprovableError,
    ) as exc:
        raise _decision_error(exc) from exc


__all__ = [
    "EvidencePaidCallDecisionRequest",
    "EvidencePaidCallRequestList",
    "EvidencePaidCallRequestView",
    "build_evidence_paid_call_view",
    "router",
]
