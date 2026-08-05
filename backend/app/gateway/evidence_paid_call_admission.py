"""Gateway-owned one-shot admission for operator-capped MediaKit stages.

The resolver performs the complete database transition before issuing a
signed hidden grant.  ASR retains its compatibility route.  The derived-stage
route group can select exactly one independently approved Remux or Video
Understanding Chat capability on the shared Evidence MCP tool; it never calls
either supplier executor itself.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime
from typing import Any, Protocol

from app.gateway.evidence_direct_pay import EvidenceASRDirectPayPolicy
from deerflow.mcp.paid_admission import (
    PaidCallAdmissionClaim,
    PaidCallAdmissionRejected,
    PaidCallRouteGroupCompensationBinding,
    PaidCallRouteGroupResolution,
    PaidCallRouteGroupScope,
    PaidCallScope,
    PaidMCPToolRoute,
    PaidMCPToolRouteGroup,
    build_paid_call_grant_interceptor,
    encode_pre_admitted_paid_call_grant,
)
from deerflow.persistence.engine import get_session_factory
from deerflow.persistence.personal_ip_paid_calls import (
    EVIDENCE_ASR_DIRECT_PAY_POLICY_VERSION,
    EVIDENCE_MANAGED_REMUX_OPERATOR_CAP_POLICY_VERSION,
    EVIDENCE_VIDEO_UNDERSTANDING_CHAT_OPERATOR_CAP_POLICY_VERSION,
    AmbiguousOperatorCappedEvidenceStages,
    OperatorCappedEvidenceStagePolicy,
    PersonalIPPaidCallRepository,
)

EVIDENCE_MCP_CLIENT_NAME = "ip_evidence"
EVIDENCE_INSPECT_TOOL_NAME = "inspect_reference_videos"
MEDIAKIT_PROVIDER = "volcengine-mediakit"
MEDIAKIT_ASR_CAPABILITY = "asr"
MEDIAKIT_REMUX_CAPABILITY = "managed_https_ingress_remux"
MEDIAKIT_VIDEO_UNDERSTANDING_CHAT_CAPABILITY = "video_understanding_chat"
MEDIAKIT_DERIVED_STAGE_CAPABILITIES = (
    MEDIAKIT_REMUX_CAPABILITY,
    MEDIAKIT_VIDEO_UNDERSTANDING_CHAT_CAPABILITY,
)
MEDIAKIT_COMPOSITE_STAGE_CAPABILITIES = (
    MEDIAKIT_ASR_CAPABILITY,
    *MEDIAKIT_DERIVED_STAGE_CAPABILITIES,
)
_GRANT_SECRET_ENV = "IP_AGENT_EVIDENCE_PAID_GRANT_SECRET"
_STABLE_REASON = re.compile(r"^[A-Z][A-Z0-9_]{0,79}$")


class _AdmissionRepository(Protocol):
    async def admit_operator_capped_asr_exact(
        self,
        **kwargs: Any,
    ) -> Mapping[str, Any] | None: ...


class _RouteGroupAdmissionRepository(Protocol):
    async def admit_next_operator_capped_evidence_stage_exact(
        self,
        **kwargs: Any,
    ) -> Mapping[str, Any] | None: ...

    async def mark_operator_capped_evidence_stage_invocation_unresolved(
        self,
        **kwargs: Any,
    ) -> Mapping[str, Any] | None: ...


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _aware_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("paid-call expiry must be timezone-aware")
    return parsed.astimezone(UTC)


def _event_ref(row: Mapping[str, Any], event_type: str) -> str:
    events = row.get("events")
    if not isinstance(events, list):
        raise ValueError("paid-call admission is missing event history")
    matches = [event for event in events if isinstance(event, Mapping) and event.get("event_type") == event_type]
    if len(matches) != 1:
        raise ValueError(f"paid-call admission requires exactly one {event_type} event")
    digest = str(matches[0].get("event_digest") or "")
    if len(digest) != 64:
        raise ValueError("paid-call event digest is invalid")
    return f"paid-call-event:{digest}"


class EvidenceASRDirectPayGrantResolver:
    """Atomically admit one exact approved request, then sign its claim."""

    def __init__(
        self,
        *,
        repository: _AdmissionRepository,
        policy: EvidenceASRDirectPayPolicy,
        signing_secret: str | bytes,
        clock: Any | None = None,
        provider_configured: Callable[[], bool] | None = None,
    ) -> None:
        if not policy.enabled:
            raise ValueError("direct-pay ASR grant resolver requires an enabled policy")
        self._repository = repository
        self._policy = policy
        self._signing_secret = signing_secret
        self._clock = clock or (lambda: datetime.now(UTC))
        self._provider_configured = provider_configured or (lambda: bool(os.getenv("MEDIAKIT_API_KEY", "").strip()))

    async def reserve_approved_call(self, scope: PaidCallScope) -> str | None:
        if not self._provider_configured():
            return None
        if scope.server_name != EVIDENCE_MCP_CLIENT_NAME or scope.tool_name != EVIDENCE_INSPECT_TOOL_NAME or scope.provider != MEDIAKIT_PROVIDER or scope.capability != MEDIAKIT_ASR_CAPABILITY:
            return None
        local_limit = self._policy.local_admission_limit_micros
        duration_limit = self._policy.max_source_duration_millis
        if local_limit is None or duration_limit is None:
            return None
        now = self._clock()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise RuntimeError("direct-pay admission clock must be timezone-aware")
        now = now.astimezone(UTC)
        jti = secrets.token_urlsafe(32)
        proof_digest = _canonical_sha256(
            {
                "contract_version": "evidence-asr-direct-pay-admission-proof-v1",
                "owner_user_id": scope.owner_user_id,
                "thread_id": scope.thread_id,
                "execution_run_id": scope.run_id,
                "server_name": scope.server_name,
                "tool_name": scope.tool_name,
                "tool_args_sha256": scope.tool_args_sha256,
                "provider": scope.provider,
                "capability": scope.capability,
                "local_admission_limit_micros": local_limit,
                "max_source_duration_millis": duration_limit,
                "currency": self._policy.currency,
                "policy_version": self._policy.policy_version,
                "jti_sha256": hashlib.sha256(jti.encode("utf-8")).hexdigest(),
            }
        )
        transition_key = proof_digest[:24]
        row = await self._repository.admit_operator_capped_asr_exact(
            owner_user_id=scope.owner_user_id,
            thread_id=scope.thread_id,
            execution_run_id=scope.run_id,
            server_name=scope.server_name,
            tool_name=scope.tool_name,
            tool_args_sha256=scope.tool_args_sha256,
            max_source_duration_millis=duration_limit,
            local_admission_limit_micros=local_limit,
            currency=self._policy.currency,
            reservation_event_key=f"direct-pay-reserve:{transition_key}",
            admission_event_key=f"direct-pay-admit:{transition_key}",
            admission_jti=jti,
            admission_proof_digest=proof_digest,
            now=now,
        )
        if row is None:
            return None
        if (
            row.get("status") != "admitted"
            or row.get("owner_user_id") != scope.owner_user_id
            or row.get("thread_id") != scope.thread_id
            or row.get("execution_run_id") != scope.run_id
            or row.get("server_name") != scope.server_name
            or row.get("tool_name") != scope.tool_name
            or row.get("tool_args_sha256") != scope.tool_args_sha256
            or row.get("provider") != MEDIAKIT_PROVIDER
            or row.get("capability") != MEDIAKIT_ASR_CAPABILITY
            or row.get("maximum_amount_micros") != local_limit
            or row.get("currency") != self._policy.currency
            or int(row.get("source_duration_millis") or 0) > duration_limit
        ):
            raise RuntimeError("paid-call admission repository returned a binding mismatch")
        claim = PaidCallAdmissionClaim(
            owner_user_id=scope.owner_user_id,
            thread_id=scope.thread_id,
            run_id=scope.run_id,
            server_name=scope.server_name,
            tool_name=scope.tool_name,
            tool_args_sha256=scope.tool_args_sha256,
            provider=MEDIAKIT_PROVIDER,
            capability=MEDIAKIT_ASR_CAPABILITY,
            call_id=str(row["id"]),
            jti=jti,
            approval_ref=_event_ref(row, "approved"),
            reservation_ref=_event_ref(row, "reserved"),
            provider_request_sha256=str(row["provider_request_sha256"]),
            source_sha256=str(row["source_sha256"]),
            stage_spec_sha256=str(row["stage_digest"]),
            maximum_amount_micros=local_limit,
            currency=self._policy.currency,
            expires_at=_aware_datetime(row["expires_at"]),
        )
        return encode_pre_admitted_paid_call_grant(
            claim,
            signing_secret=self._signing_secret,
        )


_POLICY_VERSION_BY_CAPABILITY = {
    MEDIAKIT_ASR_CAPABILITY: EVIDENCE_ASR_DIRECT_PAY_POLICY_VERSION,
    MEDIAKIT_REMUX_CAPABILITY: EVIDENCE_MANAGED_REMUX_OPERATOR_CAP_POLICY_VERSION,
    MEDIAKIT_VIDEO_UNDERSTANDING_CHAT_CAPABILITY: (EVIDENCE_VIDEO_UNDERSTANDING_CHAT_OPERATOR_CAP_POLICY_VERSION),
}


def _route_group_stage_policies(
    values: Iterable[OperatorCappedEvidenceStagePolicy],
    *,
    required_capabilities: tuple[str, ...],
) -> tuple[OperatorCappedEvidenceStagePolicy, ...]:
    supplied = tuple(values)
    if any(not isinstance(value, OperatorCappedEvidenceStagePolicy) for value in supplied):
        raise ValueError("route-group stage policies contain an invalid value")
    by_capability = {value.capability: value for value in supplied}
    if len(supplied) != len(by_capability) or set(by_capability) != set(
        required_capabilities,
    ):
        raise ValueError("route group requires exactly its declared stage policies")
    normalized: list[OperatorCappedEvidenceStagePolicy] = []
    for capability in required_capabilities:
        policy = by_capability[capability]
        if (
            not isinstance(policy, OperatorCappedEvidenceStagePolicy)
            or policy.policy_version != _POLICY_VERSION_BY_CAPABILITY[capability]
            or isinstance(policy.local_admission_limit_micros, bool)
            or not isinstance(policy.local_admission_limit_micros, int)
            or policy.local_admission_limit_micros <= 0
            or isinstance(policy.max_source_duration_millis, bool)
            or not isinstance(policy.max_source_duration_millis, int)
            or policy.max_source_duration_millis <= 0
        ):
            raise ValueError("route-group capability and policy binding is invalid")
        normalized.append(policy)
    return tuple(normalized)


class EvidenceDerivedStageRouteGroupGrantResolver:
    """Admit exactly one independently approved R1 or R2 stage.

    Both stages share the user-visible ``inspect_reference_videos`` MCP route,
    but capability selection remains a database decision.  This resolver does
    not execute Remux, Video Understanding, or any other provider operation.
    """

    def __init__(
        self,
        *,
        repository: _RouteGroupAdmissionRepository,
        trusted_stage_policies: Iterable[OperatorCappedEvidenceStagePolicy],
        signing_secret: str | bytes,
        capability_configured: Callable[[str], bool],
        clock: Callable[[], datetime] | None = None,
        _route_capabilities: tuple[str, ...] = MEDIAKIT_DERIVED_STAGE_CAPABILITIES,
        _contract_namespace: str = "derived-stage",
    ) -> None:
        secret_bytes = signing_secret.encode("utf-8") if isinstance(signing_secret, str) else bytes(signing_secret)
        if len(secret_bytes) < 32:
            raise ValueError("derived-stage grant signing secret must contain at least 32 bytes")
        if not callable(capability_configured):
            raise ValueError("derived-stage capability configuration probe is required")
        if _route_capabilities not in {
            MEDIAKIT_DERIVED_STAGE_CAPABILITIES,
            MEDIAKIT_COMPOSITE_STAGE_CAPABILITIES,
        }:
            raise ValueError("unsupported evidence paid route capability set")
        if _contract_namespace not in {"derived-stage", "composite-stage"}:
            raise ValueError("unsupported evidence paid route namespace")
        self._repository = repository
        self._route_capabilities = _route_capabilities
        self._contract_namespace = _contract_namespace
        self._stage_policies = _route_group_stage_policies(
            trusted_stage_policies,
            required_capabilities=_route_capabilities,
        )
        self._policy_by_capability = {policy.capability: policy for policy in self._stage_policies}
        self._signing_secret = signing_secret
        self._capability_configured = capability_configured
        self._clock = clock or (lambda: datetime.now(UTC))

    def _now(self) -> datetime:
        observed = self._clock()
        if not isinstance(observed, datetime) or observed.tzinfo is None or observed.utcoffset() is None:
            raise RuntimeError("derived-stage admission clock must be timezone-aware")
        return observed.astimezone(UTC)

    def _scope_is_exact(self, scope: PaidCallRouteGroupScope) -> bool:
        return scope.server_name == EVIDENCE_MCP_CLIENT_NAME and scope.tool_name == EVIDENCE_INSPECT_TOOL_NAME and scope.provider == MEDIAKIT_PROVIDER and scope.allowed_capabilities == self._route_capabilities

    def _proof_digest(
        self,
        scope: PaidCallRouteGroupScope,
        *,
        enabled_policies: tuple[OperatorCappedEvidenceStagePolicy, ...],
        jti: str,
    ) -> str:
        return _canonical_sha256(
            {
                "contract_version": (f"evidence-{self._contract_namespace}-route-group-admission-proof-v1"),
                "owner_user_id": scope.owner_user_id,
                "thread_id": scope.thread_id,
                "execution_run_id": scope.run_id,
                "server_name": scope.server_name,
                "tool_name": scope.tool_name,
                "tool_args_sha256": scope.tool_args_sha256,
                "provider": scope.provider,
                "allowed_capabilities": list(scope.allowed_capabilities),
                "enabled_stage_policies": [
                    {
                        "capability": policy.capability,
                        "policy_version": policy.policy_version,
                        "local_admission_limit_micros": policy.local_admission_limit_micros,
                        "max_source_duration_millis": policy.max_source_duration_millis,
                    }
                    for policy in enabled_policies
                ],
                "currency": "CNY",
                "jti_sha256": hashlib.sha256(jti.encode("utf-8")).hexdigest(),
            }
        )

    def _require_admitted_row_matches(
        self,
        row: Mapping[str, Any],
        *,
        scope: PaidCallRouteGroupScope,
    ) -> OperatorCappedEvidenceStagePolicy:
        capability = str(row.get("capability") or "")
        policy = self._policy_by_capability.get(capability)
        if policy is None:
            raise RuntimeError("route-group repository selected an unsupported capability")
        expected = {
            "status": "admitted",
            "owner_user_id": scope.owner_user_id,
            "thread_id": scope.thread_id,
            "execution_run_id": scope.run_id,
            "server_name": scope.server_name,
            "tool_name": scope.tool_name,
            "tool_args_sha256": scope.tool_args_sha256,
            "provider": MEDIAKIT_PROVIDER,
            "capability": capability,
            "policy_version": policy.policy_version,
            "price_status": "operator_capped",
            "maximum_amount_micros": policy.local_admission_limit_micros,
            "currency": "CNY",
        }
        if any(row.get(field) != value for field, value in expected.items()):
            raise RuntimeError("route-group repository returned a binding mismatch")
        duration = row.get("source_duration_millis")
        if isinstance(duration, bool) or not isinstance(duration, int) or not 0 < duration <= policy.max_source_duration_millis:
            raise RuntimeError("route-group repository returned an invalid source duration")
        return policy

    async def reserve_approved_call_for_group(
        self,
        scope: PaidCallRouteGroupScope,
    ) -> PaidCallRouteGroupResolution:
        if not self._scope_is_exact(scope):
            return PaidCallRouteGroupResolution()
        enabled: list[OperatorCappedEvidenceStagePolicy] = []
        for policy in self._stage_policies:
            configured = self._capability_configured(policy.capability)
            if not isinstance(configured, bool):
                raise RuntimeError("derived-stage capability configuration probe must return bool")
            if configured:
                enabled.append(policy)
        enabled_policies = tuple(enabled)
        if not enabled_policies:
            return PaidCallRouteGroupResolution()
        now = self._now()
        jti = secrets.token_urlsafe(32)
        proof_digest = self._proof_digest(
            scope,
            enabled_policies=enabled_policies,
            jti=jti,
        )
        transition_key = proof_digest[:24]
        try:
            row = await self._repository.admit_next_operator_capped_evidence_stage_exact(
                owner_user_id=scope.owner_user_id,
                thread_id=scope.thread_id,
                execution_run_id=scope.run_id,
                server_name=scope.server_name,
                tool_name=scope.tool_name,
                tool_args_sha256=scope.tool_args_sha256,
                provider=scope.provider,
                trusted_stage_policies=enabled_policies,
                currency="CNY",
                reservation_event_key=(f"{self._contract_namespace}-reserve:{transition_key}"),
                admission_event_key=(f"{self._contract_namespace}-admit:{transition_key}"),
                admission_jti=jti,
                admission_proof_digest=proof_digest,
                now=now,
            )
        except AmbiguousOperatorCappedEvidenceStages as exc:
            matched = tuple(capability for capability in self._route_capabilities if capability in exc.matched_capabilities)
            if len(matched) < 2 or set(matched) != set(exc.matched_capabilities):
                raise PaidCallAdmissionRejected("PAID_CALL_RESOLUTION_INVALID") from exc
            return PaidCallRouteGroupResolution(matched_capabilities=matched)
        if row is None:
            return PaidCallRouteGroupResolution()
        selected_capability = str(row.get("capability") or "")
        admitted_call_id = str(row.get("id") or "")
        admission_jti_sha256 = hashlib.sha256(jti.encode("utf-8")).hexdigest()
        try:
            compensation_binding = PaidCallRouteGroupCompensationBinding(
                call_id=admitted_call_id,
                admission_jti_sha256=admission_jti_sha256,
            )
        except (TypeError, ValueError) as exc:
            raise PaidCallAdmissionRejected(
                "PAID_CALL_TRANSPORT_RECONCILIATION_FAILED",
            ) from exc
        try:
            policy = self._require_admitted_row_matches(row, scope=scope)
            claim = PaidCallAdmissionClaim(
                owner_user_id=scope.owner_user_id,
                thread_id=scope.thread_id,
                run_id=scope.run_id,
                server_name=scope.server_name,
                tool_name=scope.tool_name,
                tool_args_sha256=scope.tool_args_sha256,
                provider=MEDIAKIT_PROVIDER,
                capability=selected_capability,
                call_id=admitted_call_id,
                jti=jti,
                approval_ref=_event_ref(row, "approved"),
                reservation_ref=_event_ref(row, "reserved"),
                provider_request_sha256=str(row["provider_request_sha256"]),
                source_sha256=str(row["source_sha256"]),
                stage_spec_sha256=str(row["stage_digest"]),
                maximum_amount_micros=policy.local_admission_limit_micros,
                currency="CNY",
                expires_at=_aware_datetime(row["expires_at"]),
            )
            grant = encode_pre_admitted_paid_call_grant(
                claim,
                signing_secret=self._signing_secret,
            )
        except Exception:
            if selected_capability in self._policy_by_capability:
                try:
                    await self.compensate_admitted_call_for_group(
                        scope,
                        selected_capability=selected_capability,
                        compensation_binding=compensation_binding,
                        reason_code="PAID_CALL_GRANT_ISSUANCE_FAILED",
                    )
                except Exception as compensation_error:
                    raise PaidCallAdmissionRejected("PAID_CALL_TRANSPORT_RECONCILIATION_FAILED") from compensation_error
                raise
            raise PaidCallAdmissionRejected("PAID_CALL_TRANSPORT_RECONCILIATION_FAILED")
        return PaidCallRouteGroupResolution(
            matched_capabilities=(selected_capability,),
            opaque_grant=grant,
            compensation_binding=compensation_binding,
        )

    async def compensate_admitted_call_for_group(
        self,
        scope: PaidCallRouteGroupScope,
        *,
        selected_capability: str,
        compensation_binding: PaidCallRouteGroupCompensationBinding,
        reason_code: str,
    ) -> None:
        if not self._scope_is_exact(scope):
            raise RuntimeError("route-group compensation scope is invalid")
        if not isinstance(
            compensation_binding,
            PaidCallRouteGroupCompensationBinding,
        ):
            raise RuntimeError("route-group compensation binding is invalid")
        policy = self._policy_by_capability.get(selected_capability)
        if policy is None:
            raise RuntimeError("route-group compensation capability is invalid")
        if not isinstance(reason_code, str) or _STABLE_REASON.fullmatch(reason_code) is None:
            raise RuntimeError("route-group compensation reason is invalid")
        now = self._now()
        outcome_digest = _canonical_sha256(
            {
                "contract_version": (f"evidence-{self._contract_namespace}-transport-outcome-v1"),
                "owner_user_id": scope.owner_user_id,
                "thread_id": scope.thread_id,
                "execution_run_id": scope.run_id,
                "server_name": scope.server_name,
                "tool_name": scope.tool_name,
                "tool_args_sha256": scope.tool_args_sha256,
                "provider": scope.provider,
                "selected_capability": selected_capability,
                "call_id": compensation_binding.call_id,
                "admission_jti_sha256": compensation_binding.admission_jti_sha256,
                "policy_version": policy.policy_version,
                "reason_code": reason_code,
            }
        )
        row = await self._repository.mark_operator_capped_evidence_stage_invocation_unresolved(
            scope_id=compensation_binding.call_id,
            admission_jti_sha256=compensation_binding.admission_jti_sha256,
            owner_user_id=scope.owner_user_id,
            thread_id=scope.thread_id,
            execution_run_id=scope.run_id,
            server_name=scope.server_name,
            tool_name=scope.tool_name,
            tool_args_sha256=scope.tool_args_sha256,
            provider=scope.provider,
            capability=selected_capability,
            policy_version=policy.policy_version,
            event_key=(f"{self._contract_namespace}-unresolved:{outcome_digest[:24]}"),
            execution_outcome_digest=outcome_digest,
            now=now,
        )
        if row is None:
            raise RuntimeError("route-group compensation did not find the admitted stage")
        expected = {
            "id": compensation_binding.call_id,
            "admission_jti_hash": compensation_binding.admission_jti_sha256,
            "status": "reconciliation_required",
            "owner_user_id": scope.owner_user_id,
            "thread_id": scope.thread_id,
            "execution_run_id": scope.run_id,
            "server_name": scope.server_name,
            "tool_name": scope.tool_name,
            "tool_args_sha256": scope.tool_args_sha256,
            "provider": scope.provider,
            "capability": selected_capability,
            "policy_version": policy.policy_version,
            "price_status": "operator_capped",
        }
        if any(row.get(field) != value for field, value in expected.items()):
            raise RuntimeError("route-group compensation returned a binding mismatch")


class EvidenceCompositeRouteGroupGrantResolver(
    EvidenceDerivedStageRouteGroupGrantResolver,
):
    """Atomically arbitrate ASR, Remux and Video Understanding on one route."""

    def __init__(
        self,
        *,
        repository: _RouteGroupAdmissionRepository,
        trusted_stage_policies: Iterable[OperatorCappedEvidenceStagePolicy],
        signing_secret: str | bytes,
        capability_configured: Callable[[str], bool],
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        super().__init__(
            repository=repository,
            trusted_stage_policies=trusted_stage_policies,
            signing_secret=signing_secret,
            capability_configured=capability_configured,
            clock=clock,
            _route_capabilities=MEDIAKIT_COMPOSITE_STAGE_CAPABILITIES,
            _contract_namespace="composite-stage",
        )


def build_evidence_derived_stage_route_group_interceptor(
    *,
    repository: _RouteGroupAdmissionRepository,
    trusted_stage_policies: Iterable[OperatorCappedEvidenceStagePolicy],
    signing_secret: str | bytes,
    capability_configured: Callable[[str], bool],
    clock: Callable[[], datetime] | None = None,
):
    """Build the fixed shared-route transport without enabling any executor."""

    resolver = EvidenceDerivedStageRouteGroupGrantResolver(
        repository=repository,
        trusted_stage_policies=trusted_stage_policies,
        signing_secret=signing_secret,
        capability_configured=capability_configured,
        clock=clock,
    )
    return build_paid_call_grant_interceptor(
        routes=[
            PaidMCPToolRouteGroup(
                EVIDENCE_MCP_CLIENT_NAME,
                EVIDENCE_INSPECT_TOOL_NAME,
                MEDIAKIT_PROVIDER,
                MEDIAKIT_DERIVED_STAGE_CAPABILITIES,
            )
        ],
        resolver=resolver,
    )


class _DisabledResolver:
    async def reserve_approved_call(self, scope: PaidCallScope) -> None:
        del scope
        return None


def build_evidence_asr_direct_pay_grant_interceptor():
    """Build the operator-configured ASR-only hidden-grant interceptor."""

    policy = EvidenceASRDirectPayPolicy.from_environment()
    route = PaidMCPToolRoute(
        EVIDENCE_MCP_CLIENT_NAME,
        EVIDENCE_INSPECT_TOOL_NAME,
        MEDIAKIT_PROVIDER,
        MEDIAKIT_ASR_CAPABILITY,
    )
    if not policy.enabled:
        return build_paid_call_grant_interceptor(
            routes=[route],
            resolver=_DisabledResolver(),
        )
    if not os.getenv("MEDIAKIT_API_KEY", "").strip():
        return build_paid_call_grant_interceptor(
            routes=[route],
            resolver=_DisabledResolver(),
        )
    secret = os.getenv(_GRANT_SECRET_ENV, "")
    if len(secret.encode("utf-8")) < 32:
        raise RuntimeError(f"{_GRANT_SECRET_ENV} must contain at least 32 bytes when direct-pay ASR is enabled")
    session_factory = get_session_factory()
    if session_factory is None:
        raise RuntimeError("direct-pay ASR requires persistent paid-call storage")
    resolver = EvidenceASRDirectPayGrantResolver(
        repository=PersonalIPPaidCallRepository(session_factory),
        policy=policy,
        signing_secret=secret,
    )
    return build_paid_call_grant_interceptor(routes=[route], resolver=resolver)


__all__ = [
    "EVIDENCE_INSPECT_TOOL_NAME",
    "EVIDENCE_MCP_CLIENT_NAME",
    "MEDIAKIT_COMPOSITE_STAGE_CAPABILITIES",
    "MEDIAKIT_DERIVED_STAGE_CAPABILITIES",
    "MEDIAKIT_ASR_CAPABILITY",
    "MEDIAKIT_PROVIDER",
    "MEDIAKIT_REMUX_CAPABILITY",
    "MEDIAKIT_VIDEO_UNDERSTANDING_CHAT_CAPABILITY",
    "EvidenceASRDirectPayGrantResolver",
    "EvidenceCompositeRouteGroupGrantResolver",
    "EvidenceDerivedStageRouteGroupGrantResolver",
    "build_evidence_derived_stage_route_group_interceptor",
    "build_evidence_asr_direct_pay_grant_interceptor",
]
