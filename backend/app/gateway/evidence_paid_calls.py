"""Gateway boundary for one-time paid evidence-provider decisions.

The persistence and admission implementation is injected by the application.
This module deliberately contains no fallback store: an unavailable service
must fail closed instead of turning a browser click into an unaudited provider
call.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any, Literal, Protocol, runtime_checkable

from fastapi import HTTPException, Request

EvidencePaidCallDecision = Literal["approve", "reject"]


class EvidencePaidCallNotFoundError(LookupError):
    """The owner-scoped request does not exist."""


class EvidencePaidCallConflictError(RuntimeError):
    """The request digest, version or state no longer matches."""


class EvidencePaidCallUnapprovableError(ValueError):
    """The request cannot be approved under the current server policy."""


@runtime_checkable
class EvidencePaidCallService(Protocol):
    """App-injected, atomic paid-call decision service.

    Implementations must derive owner, run, provider, capability, source and
    cost from persisted server state. ``decide`` must atomically compare the
    digest and version, reject expired or non-positive cost caps, and record an
    append-only decision. It must not submit or execute the provider call.
    """

    async def list_requests(
        self,
        *,
        owner_user_id: str,
        thread_id: str,
    ) -> Sequence[Mapping[str, Any]]: ...

    async def decide(
        self,
        *,
        owner_user_id: str,
        thread_id: str,
        request_id: str,
        decision: EvidencePaidCallDecision,
        request_digest: str,
        expected_version: int,
    ) -> Mapping[str, Any]: ...


@runtime_checkable
class EvidencePaidCallRepository(Protocol):
    async def list_thread(
        self,
        *,
        owner_user_id: str,
        thread_id: str,
    ) -> list[dict[str, Any]]: ...

    async def get(
        self,
        scope_id: str,
        *,
        owner_user_id: str,
    ) -> dict[str, Any] | None: ...

    async def approve(
        self,
        scope_id: str,
        *,
        owner_user_id: str,
        event_key: str,
        expected_request_digest: str,
        approval_digest: str,
        expected_event_count: int | None = None,
    ) -> dict[str, Any] | None: ...

    async def reject(
        self,
        scope_id: str,
        *,
        owner_user_id: str,
        event_key: str,
        expected_request_digest: str,
        decision_digest: str,
        reason_code: str,
        expected_event_count: int | None = None,
    ) -> dict[str, Any] | None: ...


def _decision_proof(
    *,
    owner_user_id: str,
    thread_id: str,
    request_id: str,
    decision: EvidencePaidCallDecision,
    request_digest: str,
    expected_version: int,
) -> tuple[str, str]:
    payload = {
        "contract_version": "ip-agent-evidence-paid-call-decision-v1",
        "owner_user_id": owner_user_id,
        "thread_id": thread_id,
        "request_id": request_id,
        "decision": decision,
        "request_digest": request_digest,
        "expected_version": expected_version,
    }
    proof = hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    event_key = f"owner-decision:{decision}:{expected_version}:{request_digest[:16]}"
    return event_key, proof


class GatewayEvidencePaidCallService:
    """Gateway adapter over the append-only paid-call repository.

    A decision only records the Owner's exact choice. Provider reservation,
    grant consumption, submission and automatic run continuation are separate
    operations and are intentionally absent here.
    """

    def __init__(self, repository: EvidencePaidCallRepository) -> None:
        self._repository = repository

    async def list_requests(
        self,
        *,
        owner_user_id: str,
        thread_id: str,
    ) -> Sequence[Mapping[str, Any]]:
        return await self._repository.list_thread(
            owner_user_id=owner_user_id,
            thread_id=thread_id,
        )

    async def decide(
        self,
        *,
        owner_user_id: str,
        thread_id: str,
        request_id: str,
        decision: EvidencePaidCallDecision,
        request_digest: str,
        expected_version: int,
    ) -> Mapping[str, Any]:
        current = await self._repository.get(
            request_id,
            owner_user_id=owner_user_id,
        )
        if current is None or current.get("thread_id") != thread_id:
            raise EvidencePaidCallNotFoundError

        event_key, proof_digest = _decision_proof(
            owner_user_id=owner_user_id,
            thread_id=thread_id,
            request_id=request_id,
            decision=decision,
            request_digest=request_digest,
            expected_version=expected_version,
        )
        try:
            if decision == "approve":
                result = await self._repository.approve(
                    request_id,
                    owner_user_id=owner_user_id,
                    event_key=event_key,
                    expected_request_digest=request_digest,
                    approval_digest=proof_digest,
                    expected_event_count=expected_version,
                )
            else:
                result = await self._repository.reject(
                    request_id,
                    owner_user_id=owner_user_id,
                    event_key=event_key,
                    expected_request_digest=request_digest,
                    decision_digest=proof_digest,
                    reason_code="owner_rejected_paid_call",
                    expected_event_count=expected_version,
                )
        except ValueError as exc:
            message = str(exc).lower()
            if decision == "approve" and ("cannot be approved" in message or "expired" in message or "positive quoted maximum" in message or "operator cap" in message):
                raise EvidencePaidCallUnapprovableError from exc
            raise EvidencePaidCallConflictError from exc
        if result is None:
            raise EvidencePaidCallNotFoundError
        return result


def get_evidence_paid_call_service(request: Request) -> EvidencePaidCallService:
    service = getattr(request.app.state, "evidence_paid_call_service", None)
    if service is None:
        raise HTTPException(
            status_code=503,
            detail="Evidence paid-call service not available",
        )
    return service


__all__ = [
    "EvidencePaidCallConflictError",
    "EvidencePaidCallDecision",
    "EvidencePaidCallNotFoundError",
    "EvidencePaidCallRepository",
    "EvidencePaidCallService",
    "EvidencePaidCallUnapprovableError",
    "GatewayEvidencePaidCallService",
    "get_evidence_paid_call_service",
]
