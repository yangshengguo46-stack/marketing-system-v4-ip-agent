"""Hidden, single-use paid-call grants for MCP tools.

This module owns only the transport and verification boundary.  It does not
issue grants, persist nonce state, approve spend, or call a provider.  A
Gateway-owned resolver must atomically reserve and admit an already-approved
call before returning an opaque grant.  The MCP-side verifier independently
checks the signed claim, invocation binding and in-process one-shot transport
use before returning a typed claim.

The opaque grant travels in MCP request metadata, never in model-visible tool
arguments.  The persistent implementation is deliberately dependency-injected
so an in-memory replay cache cannot accidentally become product truth.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import threading
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from mcp.server.fastmcp import Context
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator, model_validator

from deerflow.runtime.user_context import resolve_runtime_user_id

PAID_CALL_GRANT_HEADER = "X-DeerFlow-Paid-Call-Grant"
PAID_CALL_SELECTED_CAPABILITY_HEADER = "X-DeerFlow-Paid-Call-Selected-Capability"
_MAX_GRANT_LENGTH = 16_384
_SHA256_PATTERN = r"^[0-9a-f]{64}$"


class PaidCallAdmissionRejected(RuntimeError):
    """Fail-closed rejection carrying only a stable, non-secret reason code."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


class _StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PaidCallScope(_StrictContract):
    """Trusted Gateway scope used to find and reserve an approved call."""

    owner_user_id: str = Field(min_length=1, max_length=128)
    thread_id: str = Field(min_length=1, max_length=256)
    run_id: str = Field(min_length=1, max_length=256)
    server_name: str = Field(min_length=1, max_length=128)
    tool_name: str = Field(min_length=1, max_length=128)
    tool_args_sha256: str = Field(pattern=_SHA256_PATTERN)
    provider: str = Field(min_length=1, max_length=128)
    capability: str = Field(min_length=1, max_length=128)


class PaidCallInvocation(_StrictContract):
    """Facts independently observable at the MCP provider-call boundary."""

    server_name: str = Field(min_length=1, max_length=128)
    tool_name: str = Field(min_length=1, max_length=128)
    tool_args_sha256: str = Field(pattern=_SHA256_PATTERN)
    provider: str = Field(min_length=1, max_length=128)
    capability: str = Field(min_length=1, max_length=128)


class PaidCallRouteGroupScope(_StrictContract):
    """Trusted Gateway scope for one tool with several paid capabilities.

    The resolver must atomically inspect the allowed capability set and return
    zero, one, or several matches through :class:`PaidCallRouteGroupResolution`.
    It must reserve/admit only when exactly one capability matched.
    """

    owner_user_id: str = Field(min_length=1, max_length=128)
    thread_id: str = Field(min_length=1, max_length=256)
    run_id: str = Field(min_length=1, max_length=256)
    server_name: str = Field(min_length=1, max_length=128)
    tool_name: str = Field(min_length=1, max_length=128)
    tool_args_sha256: str = Field(pattern=_SHA256_PATTERN)
    provider: str = Field(min_length=1, max_length=128)
    allowed_capabilities: tuple[str, ...] = Field(min_length=2, max_length=32)

    @field_validator("allowed_capabilities")
    @classmethod
    def _validate_allowed_capabilities(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not capability or len(capability) > 128 for capability in value):
            raise ValueError("allowed capabilities must contain 1 to 128 characters")
        if len(set(value)) != len(value):
            raise ValueError("allowed capabilities must be unique")
        return value


class PaidCallRouteGroupInvocation(_StrictContract):
    """MCP-observed invocation with one Gateway-selected capability."""

    server_name: str = Field(min_length=1, max_length=128)
    tool_name: str = Field(min_length=1, max_length=128)
    tool_args_sha256: str = Field(pattern=_SHA256_PATTERN)
    provider: str = Field(min_length=1, max_length=128)
    allowed_capabilities: tuple[str, ...] = Field(min_length=2, max_length=32)
    selected_capability: str = Field(min_length=1, max_length=128)

    @field_validator("allowed_capabilities")
    @classmethod
    def _validate_allowed_capabilities(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not capability or len(capability) > 128 for capability in value):
            raise ValueError("allowed capabilities must contain 1 to 128 characters")
        if len(set(value)) != len(value):
            raise ValueError("allowed capabilities must be unique")
        return value

    @model_validator(mode="after")
    def _require_selected_capability_allowed(self) -> PaidCallRouteGroupInvocation:
        if self.selected_capability not in self.allowed_capabilities:
            raise ValueError("selected capability must be allowed")
        return self


class PaidCallAdmissionClaim(PaidCallScope):
    """Typed receipt returned only after one atomic admission transition.

    ``provider_request_sha256`` binds the exact provider request, while
    ``tool_args_sha256`` binds the outer MCP call.  The business adapter must
    compare the former fields again immediately before provider submission.
    """

    contract_version: Literal["deerflow-paid-call-admission-v1"] = "deerflow-paid-call-admission-v1"
    call_id: str = Field(min_length=1, max_length=256)
    jti: str = Field(min_length=16, max_length=256)
    approval_ref: str = Field(min_length=1, max_length=512)
    reservation_ref: str = Field(min_length=1, max_length=512)
    provider_request_sha256: str = Field(pattern=_SHA256_PATTERN)
    source_sha256: str = Field(pattern=_SHA256_PATTERN)
    stage_spec_sha256: str = Field(pattern=_SHA256_PATTERN)
    maximum_amount_micros: int = Field(gt=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    expires_at: datetime
    admission_state: Literal["admitted"] = "admitted"

    @field_validator("expires_at")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("expires_at must be timezone-aware")
        return value.astimezone(UTC)


class VerifiedPaidCallGrant(PaidCallAdmissionClaim):
    """A valid signed claim whose local one-shot JTI is not consumed yet.

    The callbacks are process-private Pydantic attributes.  They cannot cross
    the MCP transport or be supplied by model-visible tool arguments.
    """

    _consume_once_async: Callable[[PaidCallAdmissionClaim], Awaitable[None]] = PrivateAttr()
    _consume_once_sync: Callable[[PaidCallAdmissionClaim], None] | None = PrivateAttr(
        default=None,
    )


def _grant_secret(value: str | bytes) -> bytes:
    secret = value.encode("utf-8") if isinstance(value, str) else bytes(value)
    if len(secret) < 32:
        raise ValueError("paid-call grant signing secret must contain at least 32 bytes")
    return secret


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError) as exc:
        raise PaidCallAdmissionRejected("PAID_CALL_GRANT_INVALID") from exc


def encode_pre_admitted_paid_call_grant(
    claim: PaidCallAdmissionClaim,
    *,
    signing_secret: str | bytes,
) -> str:
    """Sign a claim whose exact reservation and admission already committed."""

    payload = json.dumps(
        claim.model_dump(mode="json"),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    encoded_payload = _b64url_encode(payload)
    signature = hmac.new(
        _grant_secret(signing_secret),
        f"v1.{encoded_payload}".encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"v1.{encoded_payload}.{_b64url_encode(signature)}"


class SignedPreAdmittedGrantVerifier:
    """Verify a Gateway-admitted grant and consume its JTI separately.

    Durable one-shot truth is the Gateway transaction that moved the exact
    scope from ``approved`` through ``reserved`` to ``admitted`` before this
    token was issued.  The local replay set is an additional transport guard;
    it is not used as product state.
    """

    def __init__(self, *, signing_secret: str | bytes) -> None:
        self._secret = _grant_secret(signing_secret)
        self._verified_claims: set[tuple[str, str]] = set()
        self._consumed_jti: set[str] = set()
        self._lock = threading.Lock()

    @staticmethod
    def _claim_sha256(claim: PaidCallAdmissionClaim) -> str:
        payload = json.dumps(
            claim.model_dump(mode="json"),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    async def verify(
        self,
        opaque_grant: str,
        invocation: PaidCallInvocation | PaidCallRouteGroupInvocation,
    ) -> PaidCallAdmissionClaim:
        """Verify signature and exact invocation binding without consuming JTI."""

        try:
            version, encoded_payload, encoded_signature = opaque_grant.split(".")
        except ValueError as exc:
            raise PaidCallAdmissionRejected("PAID_CALL_GRANT_INVALID") from exc
        if version != "v1":
            raise PaidCallAdmissionRejected("PAID_CALL_GRANT_INVALID")
        expected_signature = hmac.new(
            self._secret,
            f"v1.{encoded_payload}".encode("ascii"),
            hashlib.sha256,
        ).digest()
        signature = _b64url_decode(encoded_signature)
        if not hmac.compare_digest(expected_signature, signature):
            raise PaidCallAdmissionRejected("PAID_CALL_GRANT_INVALID")
        try:
            raw_payload = json.loads(_b64url_decode(encoded_payload))
            claim = PaidCallAdmissionClaim.model_validate(raw_payload)
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise PaidCallAdmissionRejected("PAID_CALL_GRANT_INVALID") from exc
        _require_claim_matches_invocation(claim, invocation)
        fingerprint = self._claim_sha256(claim)
        with self._lock:
            if claim.jti in self._consumed_jti:
                raise PaidCallAdmissionRejected("PAID_CALL_GRANT_REPLAYED")
            self._verified_claims.add((claim.jti, fingerprint))
        return claim

    def _consume_verified_once_sync(self, claim: PaidCallAdmissionClaim) -> None:
        fingerprint = self._claim_sha256(claim)
        with self._lock:
            if claim.jti in self._consumed_jti:
                raise PaidCallAdmissionRejected("PAID_CALL_GRANT_REPLAYED")
            if (claim.jti, fingerprint) not in self._verified_claims:
                raise PaidCallAdmissionRejected("PAID_CALL_GRANT_NOT_VERIFIED")
            self._consumed_jti.add(claim.jti)
            self._verified_claims = {item for item in self._verified_claims if item[0] != claim.jti}

    async def consume_once(self, claim: PaidCallAdmissionClaim) -> None:
        """Atomically consume one claim that this verifier previously verified."""

        self._consume_verified_once_sync(claim)

    async def verify_and_admit_once(
        self,
        opaque_grant: str,
        invocation: PaidCallInvocation | PaidCallRouteGroupInvocation,
    ) -> PaidCallAdmissionClaim:
        """Compatibility API for callers that still require one-step consume."""

        claim = await self.verify(opaque_grant, invocation)
        await self.consume_once(claim)
        return claim


class PaidCallGrantResolver(Protocol):
    """Gateway callback that atomically reserves a matching approved call.

    Returning ``None`` means there is no exact approved call.  Implementations
    must never mint a grant from runtime identity alone.
    """

    async def reserve_approved_call(self, scope: PaidCallScope) -> str | None: ...


class PaidCallRouteGroupCompensationBinding(_StrictContract):
    """Private identity of the exact admission a transport may compensate."""

    call_id: str = Field(min_length=1, max_length=256)
    admission_jti_sha256: str = Field(pattern=_SHA256_PATTERN)


class PaidCallRouteGroupResolution(_StrictContract):
    """Atomic route-group selection returned by a trusted Gateway resolver.

    Zero matches carries no grant.  One match carries the signed grant for
    that exact capability.  Multiple matches carry no grant and cause the
    transport to fail closed before invoking MCP.
    """

    matched_capabilities: tuple[str, ...] = Field(default=(), max_length=32)
    opaque_grant: str | None = Field(
        default=None,
        min_length=16,
        max_length=_MAX_GRANT_LENGTH,
        repr=False,
    )
    compensation_binding: PaidCallRouteGroupCompensationBinding | None = Field(
        default=None,
        repr=False,
    )

    @field_validator("matched_capabilities")
    @classmethod
    def _validate_matched_capabilities(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not capability or len(capability) > 128 for capability in value):
            raise ValueError("matched capabilities must contain 1 to 128 characters")
        if len(set(value)) != len(value):
            raise ValueError("matched capabilities must be unique")
        return value

    @model_validator(mode="after")
    def _validate_cardinality(self) -> PaidCallRouteGroupResolution:
        if len(self.matched_capabilities) == 1 and (self.opaque_grant is None or self.compensation_binding is None):
            raise ValueError(
                "one matched capability requires a signed grant and exact compensation binding",
            )
        if len(self.matched_capabilities) != 1 and (self.opaque_grant is not None or self.compensation_binding is not None):
            raise ValueError(
                "zero or multiple matched capabilities cannot carry admission state",
            )
        return self


class PaidCallRouteGroupResolver(Protocol):
    """Gateway callback that atomically selects one capability for a route group."""

    async def reserve_approved_call_for_group(
        self,
        scope: PaidCallRouteGroupScope,
    ) -> PaidCallRouteGroupResolution: ...

    async def compensate_admitted_call_for_group(
        self,
        scope: PaidCallRouteGroupScope,
        *,
        selected_capability: str,
        compensation_binding: PaidCallRouteGroupCompensationBinding,
        reason_code: str,
    ) -> None: ...


class PaidCallGrantVerifier(Protocol):
    """MCP callback that verifies one already-admitted, one-shot grant."""

    async def verify_and_admit_once(
        self,
        opaque_grant: str,
        invocation: PaidCallInvocation | PaidCallRouteGroupInvocation,
    ) -> PaidCallAdmissionClaim | Mapping[str, Any]: ...


class TwoPhasePaidCallGrantVerifier(Protocol):
    """Verifier whose valid claim is consumed only at provider submission."""

    async def verify(
        self,
        opaque_grant: str,
        invocation: PaidCallInvocation | PaidCallRouteGroupInvocation,
    ) -> PaidCallAdmissionClaim | Mapping[str, Any]: ...

    async def consume_once(self, claim: PaidCallAdmissionClaim) -> None: ...


@dataclass(frozen=True, slots=True)
class PaidMCPToolRoute:
    server_name: str
    tool_name: str
    provider: str
    capability: str


@dataclass(frozen=True, slots=True)
class PaidMCPToolRouteGroup:
    """One MCP tool route whose paid capability is selected server-side."""

    server_name: str
    tool_name: str
    provider: str
    allowed_capabilities: tuple[str, ...]

    def __post_init__(self) -> None:
        capabilities = tuple(self.allowed_capabilities)
        if len(capabilities) < 2:
            raise ValueError("paid MCP route group requires at least two capabilities")
        if any(not isinstance(capability, str) or not capability or len(capability) > 128 for capability in capabilities):
            raise ValueError("paid MCP route-group capabilities must contain 1 to 128 characters")
        if len(set(capabilities)) != len(capabilities):
            raise ValueError("paid MCP route-group capabilities must be unique")
        object.__setattr__(self, "allowed_capabilities", capabilities)


def canonical_tool_args_sha256(arguments: Mapping[str, Any]) -> str:
    """Hash the exact JSON arguments crossing the MCP transport boundary."""

    try:
        encoded = json.dumps(
            dict(arguments),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PaidCallAdmissionRejected("TOOL_ARGUMENTS_NOT_CANONICAL_JSON") from exc
    return hashlib.sha256(encoded).hexdigest()


def _trusted_scope_from_request(
    request: Any,
    route: PaidMCPToolRoute,
) -> PaidCallScope | None:
    runtime = getattr(request, "runtime", None)
    context = getattr(runtime, "context", None)
    if not isinstance(context, Mapping):
        return None

    thread_id = context.get("thread_id")
    run_id = context.get("run_id")
    if not all(isinstance(value, str) and value for value in (thread_id, run_id)):
        return None
    try:
        owner_user_id = resolve_runtime_user_id(runtime)
    except RuntimeError:
        return None

    arguments = getattr(request, "args", None)
    if not isinstance(arguments, Mapping):
        raise PaidCallAdmissionRejected("TOOL_ARGUMENTS_MISSING")
    return PaidCallScope(
        owner_user_id=owner_user_id,
        thread_id=thread_id,
        run_id=run_id,
        server_name=route.server_name,
        tool_name=route.tool_name,
        tool_args_sha256=canonical_tool_args_sha256(arguments),
        provider=route.provider,
        capability=route.capability,
    )


def _trusted_group_scope_from_request(
    request: Any,
    route: PaidMCPToolRouteGroup,
) -> PaidCallRouteGroupScope | None:
    runtime = getattr(request, "runtime", None)
    context = getattr(runtime, "context", None)
    if not isinstance(context, Mapping):
        return None

    thread_id = context.get("thread_id")
    run_id = context.get("run_id")
    if not all(isinstance(value, str) and value for value in (thread_id, run_id)):
        return None
    try:
        owner_user_id = resolve_runtime_user_id(runtime)
    except RuntimeError:
        return None

    arguments = getattr(request, "args", None)
    if not isinstance(arguments, Mapping):
        raise PaidCallAdmissionRejected("TOOL_ARGUMENTS_MISSING")
    return PaidCallRouteGroupScope(
        owner_user_id=owner_user_id,
        thread_id=thread_id,
        run_id=run_id,
        server_name=route.server_name,
        tool_name=route.tool_name,
        tool_args_sha256=canonical_tool_args_sha256(arguments),
        provider=route.provider,
        allowed_capabilities=route.allowed_capabilities,
    )


def _without_reserved_paid_headers(headers: Any) -> tuple[dict[str, Any], bool]:
    if headers is None:
        return {}, False
    if not isinstance(headers, Mapping):
        raise PaidCallAdmissionRejected("INVALID_MCP_HEADERS")
    filtered: dict[str, Any] = {}
    removed = False
    reserved = {
        PAID_CALL_GRANT_HEADER.casefold(),
        PAID_CALL_SELECTED_CAPABILITY_HEADER.casefold(),
    }
    for key, value in headers.items():
        if str(key).casefold() in reserved:
            removed = True
            continue
        filtered[str(key)] = value
    return filtered, removed


def _validate_opaque_grant(value: Any) -> str:
    if not isinstance(value, str) or not (16 <= len(value) <= _MAX_GRANT_LENGTH):
        raise PaidCallAdmissionRejected("INVALID_PAID_CALL_GRANT")
    if any(ord(character) < 0x21 or ord(character) > 0x7E for character in value):
        raise PaidCallAdmissionRejected("INVALID_PAID_CALL_GRANT")
    return value


def _validate_selected_capability(value: Any) -> str:
    if not isinstance(value, str) or not (1 <= len(value) <= 128):
        raise PaidCallAdmissionRejected("INVALID_PAID_CALL_SELECTED_CAPABILITY")
    if any(ord(character) < 0x21 or ord(character) > 0x7E for character in value):
        raise PaidCallAdmissionRejected("INVALID_PAID_CALL_SELECTED_CAPABILITY")
    return value


def build_paid_call_grant_interceptor(
    *,
    routes: Iterable[PaidMCPToolRoute | PaidMCPToolRouteGroup],
    resolver: PaidCallGrantResolver | PaidCallRouteGroupResolver,
) -> Callable[[Any, Callable[[Any], Awaitable[Any]]], Awaitable[Any]]:
    """Build an interceptor that injects only a server-reserved paid grant.

    Existing caller-supplied values under either reserved header are stripped.
    Missing runtime identity or a resolver miss simply produces no grant; the
    MCP provider boundary must still reject any attempted paid execution.
    """

    route_map: dict[
        tuple[str, str],
        PaidMCPToolRoute | PaidMCPToolRouteGroup,
    ] = {}
    has_single_route = False
    has_route_group = False
    for route in routes:
        key = (route.server_name, route.tool_name)
        if key in route_map:
            raise ValueError(
                "duplicate paid MCP server/tool route; use one explicit route group",
            )
        route_map[key] = route
        has_route_group = has_route_group or isinstance(route, PaidMCPToolRouteGroup)
        has_single_route = has_single_route or isinstance(route, PaidMCPToolRoute)
    if has_single_route and not callable(getattr(resolver, "reserve_approved_call", None)):
        raise ValueError("single paid MCP routes require a single-route resolver")
    if has_route_group and not callable(
        getattr(resolver, "reserve_approved_call_for_group", None),
    ):
        raise ValueError("paid MCP route groups require a route-group resolver")
    if has_route_group and not callable(
        getattr(resolver, "compensate_admitted_call_for_group", None),
    ):
        raise ValueError("paid MCP route groups require an admitted-call compensation callback")

    async def compensate_route_group(
        *,
        scope: PaidCallRouteGroupScope,
        selected_capability: str,
        compensation_binding: PaidCallRouteGroupCompensationBinding,
        reason_code: str,
    ) -> None:
        callback = getattr(resolver, "compensate_admitted_call_for_group")
        try:
            result = await callback(
                scope,
                selected_capability=selected_capability,
                compensation_binding=compensation_binding,
                reason_code=reason_code,
            )
            if result is not None:
                raise TypeError("compensation callback must return None")
        except BaseException as exc:
            raise PaidCallAdmissionRejected(
                "PAID_CALL_TRANSPORT_RECONCILIATION_FAILED",
            ) from exc

    async def shielded_compensate_route_group(
        *,
        scope: PaidCallRouteGroupScope,
        selected_capability: str,
        compensation_binding: PaidCallRouteGroupCompensationBinding,
        reason_code: str,
    ) -> bool:
        cancellation_observed = False
        compensation_task = asyncio.create_task(
            compensate_route_group(
                scope=scope,
                selected_capability=selected_capability,
                compensation_binding=compensation_binding,
                reason_code=reason_code,
            )
        )
        while not compensation_task.done():
            try:
                await asyncio.shield(compensation_task)
            except asyncio.CancelledError:
                cancellation_observed = True
                continue
        compensation_task.result()
        return cancellation_observed

    def validate_route_group_resolution(
        route: PaidMCPToolRouteGroup,
        resolution: Any,
    ) -> tuple[
        str | None,
        str | None,
        PaidCallRouteGroupCompensationBinding | None,
    ]:
        if not isinstance(resolution, PaidCallRouteGroupResolution):
            raise PaidCallAdmissionRejected("PAID_CALL_RESOLUTION_INVALID")
        allowed = set(route.allowed_capabilities)
        if any(capability not in allowed for capability in resolution.matched_capabilities):
            raise PaidCallAdmissionRejected(
                "PAID_CALL_CAPABILITY_NOT_ALLOWED",
            )
        if len(resolution.matched_capabilities) > 1:
            raise PaidCallAdmissionRejected(
                "PAID_CALL_CAPABILITY_AMBIGUOUS",
            )
        selected = resolution.matched_capabilities[0] if resolution.matched_capabilities else None
        return selected, resolution.opaque_grant, resolution.compensation_binding

    async def resolve_route_group(
        *,
        route: PaidMCPToolRouteGroup,
        scope: PaidCallRouteGroupScope,
    ) -> tuple[
        str | None,
        str | None,
        PaidCallRouteGroupCompensationBinding | None,
    ]:
        group_resolver = getattr(
            resolver,
            "reserve_approved_call_for_group",
        )
        admission_task = asyncio.create_task(group_resolver(scope))
        try:
            resolution = await asyncio.shield(admission_task)
        except asyncio.CancelledError as cancellation:
            while not admission_task.done():
                try:
                    await asyncio.shield(admission_task)
                except asyncio.CancelledError:
                    continue
            if admission_task.cancelled():
                raise PaidCallAdmissionRejected(
                    "PAID_CALL_RESERVATION_OUTCOME_UNRESOLVED",
                ) from cancellation
            try:
                resolution = admission_task.result()
            except PaidCallAdmissionRejected as exc:
                if exc.reason_code == "PAID_CALL_TRANSPORT_RECONCILIATION_FAILED":
                    raise
                raise PaidCallAdmissionRejected(
                    "PAID_CALL_RESERVATION_OUTCOME_UNRESOLVED",
                ) from exc
            except asyncio.CancelledError as exc:
                raise PaidCallAdmissionRejected(
                    "PAID_CALL_RESERVATION_OUTCOME_UNRESOLVED",
                ) from exc
            except BaseException as exc:
                raise PaidCallAdmissionRejected(
                    "PAID_CALL_RESERVATION_OUTCOME_UNRESOLVED",
                ) from exc
            try:
                selected, opaque_grant, compensation_binding = validate_route_group_resolution(route, resolution)
            except PaidCallAdmissionRejected as exc:
                if exc.reason_code == "PAID_CALL_CAPABILITY_AMBIGUOUS":
                    raise cancellation
                raise PaidCallAdmissionRejected(
                    "PAID_CALL_TRANSPORT_RECONCILIATION_FAILED",
                ) from exc
            if selected is not None:
                if compensation_binding is None:
                    raise PaidCallAdmissionRejected(
                        "PAID_CALL_TRANSPORT_RECONCILIATION_FAILED",
                    )
                await shielded_compensate_route_group(
                    scope=scope,
                    selected_capability=selected,
                    compensation_binding=compensation_binding,
                    reason_code="PAID_CALL_RESERVATION_CANCELLED",
                )
            raise cancellation
        return validate_route_group_resolution(route, resolution)

    async def interceptor(request: Any, handler: Callable[[Any], Awaitable[Any]]) -> Any:
        headers, removed_untrusted = _without_reserved_paid_headers(
            getattr(request, "headers", None),
        )
        route = route_map.get((str(request.server_name), str(request.name)))
        if route is None:
            if removed_untrusted:
                return await handler(request.override(headers=headers or None))
            return await handler(request)

        try:
            selected_capability: str | None = None
            compensation_binding: PaidCallRouteGroupCompensationBinding | None = None
            if isinstance(route, PaidMCPToolRouteGroup):
                scope = _trusted_group_scope_from_request(request, route)
                if scope is None:
                    opaque_grant = None
                else:
                    (
                        selected_capability,
                        opaque_grant,
                        compensation_binding,
                    ) = await resolve_route_group(
                        route=route,
                        scope=scope,
                    )
            else:
                scope = _trusted_scope_from_request(request, route)
                if scope is None:
                    opaque_grant = None
                else:
                    single_resolver = getattr(resolver, "reserve_approved_call")
                    raw_resolution = await single_resolver(scope)
                    if raw_resolution is not None and not isinstance(
                        raw_resolution,
                        str,
                    ):
                        raise PaidCallAdmissionRejected(
                            "PAID_CALL_RESOLUTION_INVALID",
                        )
                    opaque_grant = raw_resolution
        except PaidCallAdmissionRejected:
            raise
        except Exception as exc:
            raise PaidCallAdmissionRejected("PAID_CALL_RESERVATION_FAILED") from exc
        if opaque_grant is None:
            if removed_untrusted:
                return await handler(request.override(headers=headers or None))
            return await handler(request)

        if isinstance(route, PaidMCPToolRouteGroup):
            if scope is None or selected_capability is None or compensation_binding is None:
                raise PaidCallAdmissionRejected("PAID_CALL_RESOLUTION_INVALID")
            try:
                headers[PAID_CALL_GRANT_HEADER] = _validate_opaque_grant(opaque_grant)
                headers[PAID_CALL_SELECTED_CAPABILITY_HEADER] = _validate_selected_capability(
                    selected_capability,
                )
                downstream_request = request.override(headers=headers)
                result = await handler(downstream_request)
            except asyncio.CancelledError:
                await shielded_compensate_route_group(
                    scope=scope,
                    selected_capability=selected_capability,
                    compensation_binding=compensation_binding,
                    reason_code="PAID_CALL_TRANSPORT_CANCELLED",
                )
                raise
            except PaidCallAdmissionRejected as exc:
                cancelled_during_compensation = await shielded_compensate_route_group(
                    scope=scope,
                    selected_capability=selected_capability,
                    compensation_binding=compensation_binding,
                    reason_code=exc.reason_code,
                )
                if cancelled_during_compensation:
                    raise asyncio.CancelledError
                raise
            except Exception as exc:
                cancelled_during_compensation = await shielded_compensate_route_group(
                    scope=scope,
                    selected_capability=selected_capability,
                    compensation_binding=compensation_binding,
                    reason_code="PAID_CALL_TRANSPORT_FAILED",
                )
                if cancelled_during_compensation:
                    raise asyncio.CancelledError
                raise PaidCallAdmissionRejected(
                    "PAID_CALL_TRANSPORT_FAILED",
                ) from exc
            if getattr(result, "isError", False) is True:
                cancelled_during_compensation = await shielded_compensate_route_group(
                    scope=scope,
                    selected_capability=selected_capability,
                    compensation_binding=compensation_binding,
                    reason_code="PAID_CALL_MCP_ERROR_RESULT",
                )
                if cancelled_during_compensation:
                    raise asyncio.CancelledError
            return result

        headers[PAID_CALL_GRANT_HEADER] = _validate_opaque_grant(opaque_grant)
        return await handler(request.override(headers=headers))

    setattr(
        interceptor,
        "__deerflow_paid_mcp_route_keys__",
        frozenset(route_map),
    )
    return interceptor


def paid_mcp_interceptor_route_keys(
    interceptor: Any,
) -> frozenset[tuple[str, str]]:
    """Return operator-owned route keys attached by the paid interceptor builder."""

    raw = getattr(interceptor, "__deerflow_paid_mcp_route_keys__", frozenset())
    if not isinstance(raw, frozenset):
        return frozenset()
    keys: set[tuple[str, str]] = set()
    for item in raw:
        if not isinstance(item, tuple) or len(item) != 2 or not all(isinstance(value, str) and value for value in item):
            return frozenset()
        keys.add(item)
    return frozenset(keys)


def hidden_mcp_headers(context: Context) -> Mapping[str, Any]:
    """Read interceptor metadata without exposing it as a tool parameter."""

    try:
        meta = context.request_context.meta
    except (AttributeError, ValueError) as exc:
        raise PaidCallAdmissionRejected("MCP_REQUEST_CONTEXT_MISSING") from exc
    extras = getattr(meta, "model_extra", None) if meta is not None else None
    headers = extras.get("headers") if isinstance(extras, Mapping) else None
    if headers is None:
        return {}
    if not isinstance(headers, Mapping):
        raise PaidCallAdmissionRejected("INVALID_MCP_HEADERS")
    return headers


def hidden_paid_call_grant(context: Context) -> str | None:
    """Return the opaque hidden grant, if present, using case-insensitive lookup."""

    found: list[Any] = [value for key, value in hidden_mcp_headers(context).items() if str(key).casefold() == PAID_CALL_GRANT_HEADER.casefold()]
    if not found:
        return None
    if len(found) != 1:
        raise PaidCallAdmissionRejected("DUPLICATE_PAID_CALL_GRANT")
    return _validate_opaque_grant(found[0])


def hidden_paid_call_selected_capability(context: Context) -> str | None:
    """Read the one Gateway-selected route-group capability from metadata."""

    found: list[Any] = [value for key, value in hidden_mcp_headers(context).items() if str(key).casefold() == PAID_CALL_SELECTED_CAPABILITY_HEADER.casefold()]
    if not found:
        return None
    if len(found) != 1:
        raise PaidCallAdmissionRejected("DUPLICATE_PAID_CALL_SELECTED_CAPABILITY")
    return _validate_selected_capability(found[0])


def invocation_from_context(
    context: Context,
    *,
    server_name: str,
    tool_name: str,
    provider: str,
    capability: str,
) -> PaidCallInvocation:
    """Build the independently observed invocation from the raw MCP request."""

    try:
        request = context.request_context.request
        params = request.params
        raw_tool_name = params.name
        arguments = params.arguments or {}
    except (AttributeError, ValueError) as exc:
        raise PaidCallAdmissionRejected("MCP_INVOCATION_CONTEXT_MISSING") from exc
    if not isinstance(arguments, Mapping):
        raise PaidCallAdmissionRejected("TOOL_ARGUMENTS_MISSING")
    if str(raw_tool_name) != tool_name:
        raise PaidCallAdmissionRejected("PAID_CALL_TOOL_MISMATCH")
    return PaidCallInvocation(
        server_name=server_name,
        tool_name=str(raw_tool_name),
        tool_args_sha256=canonical_tool_args_sha256(arguments),
        provider=provider,
        capability=capability,
    )


def route_group_invocation_from_context(
    context: Context,
    *,
    server_name: str,
    tool_name: str,
    provider: str,
    allowed_capabilities: Iterable[str],
) -> PaidCallRouteGroupInvocation:
    """Build a multi-capability invocation from the raw MCP request."""

    try:
        request = context.request_context.request
        params = request.params
        raw_tool_name = params.name
        arguments = params.arguments or {}
    except (AttributeError, ValueError) as exc:
        raise PaidCallAdmissionRejected("MCP_INVOCATION_CONTEXT_MISSING") from exc
    if not isinstance(arguments, Mapping):
        raise PaidCallAdmissionRejected("TOOL_ARGUMENTS_MISSING")
    if str(raw_tool_name) != tool_name:
        raise PaidCallAdmissionRejected("PAID_CALL_TOOL_MISMATCH")
    allowed = tuple(allowed_capabilities)
    selected = hidden_paid_call_selected_capability(context)
    if selected is None:
        raise PaidCallAdmissionRejected("PAID_CALL_SELECTED_CAPABILITY_MISSING")
    if selected not in allowed:
        raise PaidCallAdmissionRejected("PAID_CALL_CAPABILITY_NOT_ALLOWED")
    return PaidCallRouteGroupInvocation(
        server_name=server_name,
        tool_name=str(raw_tool_name),
        tool_args_sha256=canonical_tool_args_sha256(arguments),
        provider=provider,
        allowed_capabilities=allowed,
        selected_capability=selected,
    )


def _require_claim_matches_invocation(
    claim: PaidCallAdmissionClaim,
    invocation: PaidCallInvocation | PaidCallRouteGroupInvocation,
) -> None:
    exact_fields = ("server_name", "tool_name", "provider")
    if any(getattr(claim, field) != getattr(invocation, field) for field in exact_fields):
        raise PaidCallAdmissionRejected("PAID_CALL_SCOPE_MISMATCH")
    if not hmac.compare_digest(claim.tool_args_sha256, invocation.tool_args_sha256):
        raise PaidCallAdmissionRejected("PAID_CALL_ARGUMENTS_MISMATCH")
    if isinstance(invocation, PaidCallRouteGroupInvocation):
        if claim.capability not in invocation.allowed_capabilities:
            raise PaidCallAdmissionRejected("PAID_CALL_CAPABILITY_NOT_ALLOWED")
        if claim.capability != invocation.selected_capability:
            raise PaidCallAdmissionRejected("PAID_CALL_CAPABILITY_MISMATCH")
    elif claim.capability != invocation.capability:
        raise PaidCallAdmissionRejected("PAID_CALL_SCOPE_MISMATCH")


def _observed_utc(now: datetime | None) -> datetime:
    observed_now = now or datetime.now(UTC)
    if observed_now.tzinfo is None or observed_now.utcoffset() is None:
        raise PaidCallAdmissionRejected("VERIFICATION_CLOCK_NOT_TIMEZONE_AWARE")
    return observed_now.astimezone(UTC)


def _require_grant_not_expired(
    claim: PaidCallAdmissionClaim,
    *,
    now: datetime | None,
) -> None:
    if claim.expires_at <= _observed_utc(now):
        raise PaidCallAdmissionRejected("PAID_CALL_GRANT_EXPIRED")


async def _verify_unconsumed_grant(
    opaque_grant: str,
    invocation: PaidCallInvocation | PaidCallRouteGroupInvocation,
    *,
    verifier: TwoPhasePaidCallGrantVerifier,
    now: datetime | None,
) -> VerifiedPaidCallGrant:
    verify = getattr(verifier, "verify", None)
    consume_once = getattr(verifier, "consume_once", None)
    if not callable(verify) or not callable(consume_once):
        raise PaidCallAdmissionRejected("PAID_CALL_TWO_PHASE_VERIFIER_REQUIRED")
    try:
        raw_claim = await verify(opaque_grant, invocation)
        claim = PaidCallAdmissionClaim.model_validate(raw_claim)
    except PaidCallAdmissionRejected:
        raise
    except Exception as exc:
        raise PaidCallAdmissionRejected("PAID_CALL_GRANT_REJECTED") from exc
    _require_claim_matches_invocation(claim, invocation)
    _require_grant_not_expired(claim, now=now)
    verified = VerifiedPaidCallGrant.model_validate(claim.model_dump(mode="python"))
    verified._consume_once_async = consume_once
    sync_consumer = getattr(verifier, "_consume_verified_once_sync", None)
    verified._consume_once_sync = sync_consumer if callable(sync_consumer) else None
    return verified


async def verify_hidden_paid_call_grant(
    context: Context,
    *,
    server_name: str,
    tool_name: str,
    provider: str,
    capability: str,
    verifier: TwoPhasePaidCallGrantVerifier,
    now: datetime | None = None,
) -> VerifiedPaidCallGrant:
    """Verify one hidden grant without consuming its one-shot JTI."""

    opaque_grant = hidden_paid_call_grant(context)
    if opaque_grant is None:
        raise PaidCallAdmissionRejected("PAID_CALL_GRANT_MISSING")
    invocation = invocation_from_context(
        context,
        server_name=server_name,
        tool_name=tool_name,
        provider=provider,
        capability=capability,
    )
    return await _verify_unconsumed_grant(
        opaque_grant,
        invocation,
        verifier=verifier,
        now=now,
    )


async def verify_hidden_paid_call_grant_for_route_group(
    context: Context,
    *,
    server_name: str,
    tool_name: str,
    provider: str,
    allowed_capabilities: Iterable[str],
    verifier: TwoPhasePaidCallGrantVerifier,
    now: datetime | None = None,
) -> VerifiedPaidCallGrant:
    """Verify a route-group grant against its exact Gateway-selected capability."""

    opaque_grant = hidden_paid_call_grant(context)
    if opaque_grant is None:
        raise PaidCallAdmissionRejected("PAID_CALL_GRANT_MISSING")
    invocation = route_group_invocation_from_context(
        context,
        server_name=server_name,
        tool_name=tool_name,
        provider=provider,
        allowed_capabilities=allowed_capabilities,
    )
    return await _verify_unconsumed_grant(
        opaque_grant,
        invocation,
        verifier=verifier,
        now=now,
    )


async def consume_hidden_paid_call_grant(
    context: Context,
    *,
    server_name: str,
    tool_name: str,
    provider: str,
    capability: str,
    verifier: PaidCallGrantVerifier | TwoPhasePaidCallGrantVerifier,
    now: datetime | None = None,
) -> PaidCallAdmissionClaim:
    """Compatibility API that verifies and immediately consumes one grant."""

    if callable(getattr(verifier, "verify", None)) and callable(
        getattr(verifier, "consume_once", None),
    ):
        verified = await verify_hidden_paid_call_grant(
            context,
            server_name=server_name,
            tool_name=tool_name,
            provider=provider,
            capability=capability,
            verifier=verifier,
            now=now,
        )
        await verified._consume_once_async(verified)
        return PaidCallAdmissionClaim.model_validate(verified.model_dump(mode="python"))

    opaque_grant = hidden_paid_call_grant(context)
    if opaque_grant is None:
        raise PaidCallAdmissionRejected("PAID_CALL_GRANT_MISSING")
    invocation = invocation_from_context(
        context,
        server_name=server_name,
        tool_name=tool_name,
        provider=provider,
        capability=capability,
    )
    try:
        raw_claim = await verifier.verify_and_admit_once(opaque_grant, invocation)
        claim = PaidCallAdmissionClaim.model_validate(raw_claim)
    except PaidCallAdmissionRejected:
        raise
    except Exception as exc:
        raise PaidCallAdmissionRejected("PAID_CALL_GRANT_REJECTED") from exc

    _require_claim_matches_invocation(claim, invocation)
    _require_grant_not_expired(claim, now=now)
    return claim


async def consume_hidden_paid_call_grant_for_route_group(
    context: Context,
    *,
    server_name: str,
    tool_name: str,
    provider: str,
    allowed_capabilities: Iterable[str],
    verifier: PaidCallGrantVerifier | TwoPhasePaidCallGrantVerifier,
    now: datetime | None = None,
) -> PaidCallAdmissionClaim:
    """Compatibility API that consumes one exact selected-capability grant."""

    if callable(getattr(verifier, "verify", None)) and callable(
        getattr(verifier, "consume_once", None),
    ):
        verified = await verify_hidden_paid_call_grant_for_route_group(
            context,
            server_name=server_name,
            tool_name=tool_name,
            provider=provider,
            allowed_capabilities=allowed_capabilities,
            verifier=verifier,
            now=now,
        )
        await verified._consume_once_async(verified)
        return PaidCallAdmissionClaim.model_validate(verified.model_dump(mode="python"))

    opaque_grant = hidden_paid_call_grant(context)
    if opaque_grant is None:
        raise PaidCallAdmissionRejected("PAID_CALL_GRANT_MISSING")
    invocation = route_group_invocation_from_context(
        context,
        server_name=server_name,
        tool_name=tool_name,
        provider=provider,
        allowed_capabilities=allowed_capabilities,
    )
    try:
        raw_claim = await verifier.verify_and_admit_once(opaque_grant, invocation)
        claim = PaidCallAdmissionClaim.model_validate(raw_claim)
    except PaidCallAdmissionRejected:
        raise
    except Exception as exc:
        raise PaidCallAdmissionRejected("PAID_CALL_GRANT_REJECTED") from exc

    _require_claim_matches_invocation(claim, invocation)
    _require_grant_not_expired(claim, now=now)
    return claim


def _require_provider_request_binding_values(
    claim: PaidCallAdmissionClaim,
    *,
    provider_request_sha256: str,
    source_sha256: str,
    stage_spec_sha256: str,
    estimated_amount_micros: int,
    currency: str,
) -> None:
    for expected, observed in (
        (claim.provider_request_sha256, provider_request_sha256),
        (claim.source_sha256, source_sha256),
        (claim.stage_spec_sha256, stage_spec_sha256),
    ):
        if not hmac.compare_digest(expected, observed):
            raise PaidCallAdmissionRejected("PAID_PROVIDER_REQUEST_MISMATCH")
    if currency != claim.currency:
        raise PaidCallAdmissionRejected("PAID_PROVIDER_CURRENCY_MISMATCH")
    if estimated_amount_micros < 0 or estimated_amount_micros > claim.maximum_amount_micros:
        raise PaidCallAdmissionRejected("PAID_PROVIDER_AMOUNT_EXCEEDS_RESERVATION")


async def finalize_verified_paid_call_grant(
    verified: VerifiedPaidCallGrant,
    *,
    provider_request_sha256: str,
    source_sha256: str,
    stage_spec_sha256: str,
    estimated_amount_micros: int,
    currency: str,
    now: datetime | None = None,
) -> PaidCallAdmissionClaim:
    """Bind the exact provider request, then atomically consume the grant JTI."""

    if not isinstance(verified, VerifiedPaidCallGrant):
        raise PaidCallAdmissionRejected("PAID_CALL_GRANT_NOT_VERIFIED")
    _require_grant_not_expired(verified, now=now)
    _require_provider_request_binding_values(
        verified,
        provider_request_sha256=provider_request_sha256,
        source_sha256=source_sha256,
        stage_spec_sha256=stage_spec_sha256,
        estimated_amount_micros=estimated_amount_micros,
        currency=currency,
    )
    try:
        consumer = verified._consume_once_async
    except AttributeError as exc:
        raise PaidCallAdmissionRejected("PAID_CALL_GRANT_NOT_VERIFIED") from exc
    if not callable(consumer):
        raise PaidCallAdmissionRejected("PAID_CALL_GRANT_NOT_VERIFIED")
    await consumer(verified)
    return PaidCallAdmissionClaim.model_validate(verified.model_dump(mode="python"))


def require_provider_request_binding(
    claim: PaidCallAdmissionClaim,
    *,
    provider_request_sha256: str,
    source_sha256: str,
    stage_spec_sha256: str,
    estimated_amount_micros: int,
    currency: str,
) -> None:
    """Recheck exact binding and finalize a deferred grant before submission.

    Plain admission claims retain the historical validation-only behavior.
    A :class:`VerifiedPaidCallGrant` is consumed only after every binding and
    freshness check passes.  Evidence ASR uses this synchronous finalization
    seam immediately before it enters the provider worker thread.
    """

    _require_provider_request_binding_values(
        claim,
        provider_request_sha256=provider_request_sha256,
        source_sha256=source_sha256,
        stage_spec_sha256=stage_spec_sha256,
        estimated_amount_micros=estimated_amount_micros,
        currency=currency,
    )
    if isinstance(claim, VerifiedPaidCallGrant):
        _require_grant_not_expired(claim, now=None)
        try:
            consumer = claim._consume_once_sync
        except AttributeError as exc:
            raise PaidCallAdmissionRejected("PAID_CALL_GRANT_NOT_VERIFIED") from exc
        if consumer is None:
            raise PaidCallAdmissionRejected("PAID_CALL_ASYNC_FINALIZE_REQUIRED")
        consumer(claim)
