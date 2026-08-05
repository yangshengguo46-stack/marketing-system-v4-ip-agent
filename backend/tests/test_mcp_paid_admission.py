from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_mcp_adapters.interceptors import MCPToolCallRequest
from mcp.server.fastmcp import Context
from mcp.shared.context import RequestContext
from mcp.types import (
    CallToolRequest,
    CallToolRequestParams,
    CallToolResult,
    RequestParams,
    TextContent,
)

from deerflow.ip_agent import evidence_mcp
from deerflow.mcp.paid_admission import (
    PAID_CALL_GRANT_HEADER,
    PAID_CALL_SELECTED_CAPABILITY_HEADER,
    PaidCallAdmissionClaim,
    PaidCallAdmissionRejected,
    PaidCallInvocation,
    PaidCallRouteGroupCompensationBinding,
    PaidCallRouteGroupResolution,
    PaidCallRouteGroupScope,
    PaidCallScope,
    PaidMCPToolRoute,
    PaidMCPToolRouteGroup,
    SignedPreAdmittedGrantVerifier,
    build_paid_call_grant_interceptor,
    canonical_tool_args_sha256,
    consume_hidden_paid_call_grant,
    consume_hidden_paid_call_grant_for_route_group,
    encode_pre_admitted_paid_call_grant,
    finalize_verified_paid_call_grant,
    hidden_paid_call_grant,
    require_provider_request_binding,
    verify_hidden_paid_call_grant,
)

_SERVER = "ip-agent-evidence"
_TOOL = "inspect_reference_videos"
_PROVIDER = "volcengine-mediakit"
_CAPABILITY = "asr"
_REMUX_CAPABILITY = "managed_https_ingress_remux"
_CHAT_CAPABILITY = "video_understanding_chat"
_GROUP_CAPABILITIES = (_REMUX_CAPABILITY, _CHAT_CAPABILITY)
_GRANT = "opaque-paid-grant-value"
_COMPENSATION_BINDING = PaidCallRouteGroupCompensationBinding(
    call_id="call-route-group-1",
    admission_jti_sha256="f" * 64,
)
_SIGNING_SECRET = b"paid-call-route-group-test-secret-32-bytes"
_ARGS = {
    "video_refs": ["/mnt/user-data/uploads/reference.mp4"],
    "analysis_depth": "speech_text",
}


def _context(
    *,
    arguments: dict[str, Any] | None = None,
    tool_name: str = _TOOL,
    grant: str | None = _GRANT,
    selected_capability: str | None = None,
) -> Context:
    headers = {} if grant is None else {PAID_CALL_GRANT_HEADER: grant}
    if selected_capability is not None:
        headers[PAID_CALL_SELECTED_CAPABILITY_HEADER] = selected_capability
    meta = RequestParams.Meta.model_validate({"headers": headers})
    request = CallToolRequest(
        params=CallToolRequestParams(
            name=tool_name,
            arguments=arguments if arguments is not None else dict(_ARGS),
        )
    )
    request_context = RequestContext(
        request_id="request-1",
        meta=meta,
        session=object(),
        lifespan_context=None,
        request=request,
    )
    return Context(request_context=request_context)


def _claim(
    invocation: PaidCallInvocation,
    *,
    expires_at: datetime | None = None,
    **updates: Any,
) -> PaidCallAdmissionClaim:
    values: dict[str, Any] = {
        "owner_user_id": "owner-1",
        "thread_id": "thread-1",
        "run_id": "run-1",
        "server_name": invocation.server_name,
        "tool_name": invocation.tool_name,
        "tool_args_sha256": invocation.tool_args_sha256,
        "provider": invocation.provider,
        "capability": invocation.capability,
        "call_id": "call-1",
        "jti": "jti-1234567890123456",
        "approval_ref": "approval-1",
        "reservation_ref": "reservation-1",
        "provider_request_sha256": "a" * 64,
        "source_sha256": "b" * 64,
        "stage_spec_sha256": "c" * 64,
        "maximum_amount_micros": 50,
        "currency": "CNY",
        "expires_at": expires_at or datetime.now(UTC) + timedelta(minutes=5),
    }
    values.update(updates)
    return PaidCallAdmissionClaim.model_validate(values)


class _Resolver:
    def __init__(self, result: str | None) -> None:
        self.result = result
        self.scopes: list[PaidCallScope] = []

    async def reserve_approved_call(self, scope: PaidCallScope) -> str | None:
        self.scopes.append(scope)
        return self.result


class _GroupResolver:
    def __init__(
        self,
        result: PaidCallRouteGroupResolution,
        *,
        compensation_fails: bool = False,
    ) -> None:
        self.result = result
        self.compensation_fails = compensation_fails
        self.scopes: list[PaidCallRouteGroupScope] = []
        self.compensations: list[
            tuple[
                PaidCallRouteGroupScope,
                str,
                PaidCallRouteGroupCompensationBinding,
                str,
            ]
        ] = []

    async def reserve_approved_call_for_group(
        self,
        scope: PaidCallRouteGroupScope,
    ) -> PaidCallRouteGroupResolution:
        self.scopes.append(scope)
        return self.result

    async def compensate_admitted_call_for_group(
        self,
        scope: PaidCallRouteGroupScope,
        *,
        selected_capability: str,
        compensation_binding: PaidCallRouteGroupCompensationBinding,
        reason_code: str,
    ) -> None:
        self.compensations.append(
            (scope, selected_capability, compensation_binding, reason_code),
        )
        if self.compensation_fails:
            raise RuntimeError("reconciliation unavailable")


class _StaticVerifier:
    def __init__(self, mutate: dict[str, Any] | None = None) -> None:
        self.mutate = mutate or {}
        self.calls: list[tuple[str, PaidCallInvocation]] = []

    async def verify_and_admit_once(
        self,
        opaque_grant: str,
        invocation: PaidCallInvocation,
    ) -> PaidCallAdmissionClaim:
        self.calls.append((opaque_grant, invocation))
        return _claim(invocation, **self.mutate)


class _RejectingVerifier:
    async def verify_and_admit_once(
        self,
        opaque_grant: str,
        invocation: PaidCallInvocation,
    ) -> PaidCallAdmissionClaim:
        del opaque_grant, invocation
        raise PaidCallAdmissionRejected("PAID_CALL_GRANT_INVALID")


class _ReplayTestDouble:
    """Test-only atomic-consumption stand-in; never used as product storage."""

    def __init__(self) -> None:
        self._consumed: set[str] = set()

    async def verify_and_admit_once(
        self,
        opaque_grant: str,
        invocation: PaidCallInvocation,
    ) -> PaidCallAdmissionClaim:
        if opaque_grant in self._consumed:
            raise PaidCallAdmissionRejected("PAID_CALL_GRANT_REPLAYED")
        self._consumed.add(opaque_grant)
        return _claim(invocation)


def _signed_grant(
    capability: str,
    *,
    jti: str = "jti-signed-1234567890123456",
    **claim_updates: Any,
) -> str:
    invocation = PaidCallInvocation(
        server_name=_SERVER,
        tool_name=_TOOL,
        tool_args_sha256=canonical_tool_args_sha256(_ARGS),
        provider=_PROVIDER,
        capability=capability,
    )
    claim = _claim(invocation, jti=jti, **claim_updates)
    return encode_pre_admitted_paid_call_grant(
        claim,
        signing_secret=_SIGNING_SECRET,
    )


def test_evidence_tool_schema_does_not_expose_paid_admission_transport() -> None:
    tool = evidence_mcp.server._tool_manager.get_tool(_TOOL)
    assert tool is not None
    assert tool.context_kwarg == "ctx"
    encoded = json.dumps(tool.parameters, sort_keys=True).casefold()
    for forbidden in (
        "ctx",
        "authorized",
        "paid_call",
        "paid-call",
        "admission",
        "grant",
        "token",
        PAID_CALL_GRANT_HEADER.casefold(),
    ):
        assert forbidden not in encoded


@pytest.mark.asyncio
async def test_interceptor_injects_reserved_grant_without_changing_tool_args() -> None:
    resolver = _Resolver(_GRANT)
    interceptor = build_paid_call_grant_interceptor(
        routes=[PaidMCPToolRoute(_SERVER, _TOOL, _PROVIDER, _CAPABILITY)],
        resolver=resolver,
    )
    runtime = SimpleNamespace(context={"user_id": "owner-1", "thread_id": "thread-1", "run_id": "run-1"})
    request = MCPToolCallRequest(
        name=_TOOL,
        args=dict(_ARGS),
        server_name=_SERVER,
        runtime=runtime,
    )

    async def handler(observed: MCPToolCallRequest) -> MCPToolCallRequest:
        return observed

    observed = await interceptor(request, handler)
    assert observed.args == _ARGS
    assert PAID_CALL_GRANT_HEADER not in json.dumps(observed.args)
    assert observed.headers == {PAID_CALL_GRANT_HEADER: _GRANT}
    assert resolver.scopes == [
        PaidCallScope(
            owner_user_id="owner-1",
            thread_id="thread-1",
            run_id="run-1",
            server_name=_SERVER,
            tool_name=_TOOL,
            tool_args_sha256=canonical_tool_args_sha256(_ARGS),
            provider=_PROVIDER,
            capability=_CAPABILITY,
        )
    ]


@pytest.mark.parametrize("second_capability", [_CAPABILITY, "ocr"])
def test_duplicate_single_routes_fail_closed_at_construction(
    second_capability: str,
) -> None:
    with pytest.raises(ValueError, match="explicit route group"):
        build_paid_call_grant_interceptor(
            routes=[
                PaidMCPToolRoute(_SERVER, _TOOL, _PROVIDER, _CAPABILITY),
                PaidMCPToolRoute(_SERVER, _TOOL, _PROVIDER, second_capability),
            ],
            resolver=_Resolver(_GRANT),
        )


def test_route_group_requires_compensation_callback_at_construction() -> None:
    class ResolverWithoutCompensation:
        async def reserve_approved_call_for_group(
            self,
            scope: PaidCallRouteGroupScope,
        ) -> PaidCallRouteGroupResolution:
            del scope
            return PaidCallRouteGroupResolution()

    with pytest.raises(ValueError, match="compensation callback"):
        build_paid_call_grant_interceptor(
            routes=[
                PaidMCPToolRouteGroup(
                    _SERVER,
                    _TOOL,
                    _PROVIDER,
                    _GROUP_CAPABILITIES,
                )
            ],
            resolver=ResolverWithoutCompensation(),
        )


@pytest.mark.asyncio
async def test_route_group_zero_matches_injects_no_grant() -> None:
    resolver = _GroupResolver(PaidCallRouteGroupResolution())
    interceptor = build_paid_call_grant_interceptor(
        routes=[
            PaidMCPToolRouteGroup(
                _SERVER,
                _TOOL,
                _PROVIDER,
                _GROUP_CAPABILITIES,
            )
        ],
        resolver=resolver,
    )
    runtime = SimpleNamespace(
        context={
            "user_id": "owner-1",
            "thread_id": "thread-1",
            "run_id": "run-1",
        }
    )
    request = MCPToolCallRequest(
        name=_TOOL,
        args=dict(_ARGS),
        server_name=_SERVER,
        headers={
            PAID_CALL_GRANT_HEADER.lower(): "attacker-supplied-grant",
            PAID_CALL_SELECTED_CAPABILITY_HEADER.lower(): _CHAT_CAPABILITY,
            "X-Trace": "safe",
        },
        runtime=runtime,
    )

    async def handler(observed: MCPToolCallRequest) -> MCPToolCallRequest:
        return observed

    observed = await interceptor(request, handler)
    assert observed.headers == {"X-Trace": "safe"}
    assert resolver.scopes == [
        PaidCallRouteGroupScope(
            owner_user_id="owner-1",
            thread_id="thread-1",
            run_id="run-1",
            server_name=_SERVER,
            tool_name=_TOOL,
            tool_args_sha256=canonical_tool_args_sha256(_ARGS),
            provider=_PROVIDER,
            allowed_capabilities=_GROUP_CAPABILITIES,
        )
    ]


@pytest.mark.asyncio
async def test_route_group_unique_match_injects_actual_capability_signed_grant() -> None:
    grant = _signed_grant(_REMUX_CAPABILITY)
    resolver = _GroupResolver(
        PaidCallRouteGroupResolution(
            matched_capabilities=(_REMUX_CAPABILITY,),
            opaque_grant=grant,
            compensation_binding=_COMPENSATION_BINDING,
        )
    )
    interceptor = build_paid_call_grant_interceptor(
        routes=[
            PaidMCPToolRouteGroup(
                _SERVER,
                _TOOL,
                _PROVIDER,
                _GROUP_CAPABILITIES,
            )
        ],
        resolver=resolver,
    )
    runtime = SimpleNamespace(
        context={
            "user_id": "owner-1",
            "thread_id": "thread-1",
            "run_id": "run-1",
        }
    )
    request = MCPToolCallRequest(
        name=_TOOL,
        args=dict(_ARGS),
        server_name=_SERVER,
        runtime=runtime,
    )

    async def handler(observed: MCPToolCallRequest) -> MCPToolCallRequest:
        return observed

    observed = await interceptor(request, handler)
    assert observed.args == _ARGS
    assert observed.headers == {
        PAID_CALL_GRANT_HEADER: grant,
        PAID_CALL_SELECTED_CAPABILITY_HEADER: _REMUX_CAPABILITY,
    }
    assert len(resolver.scopes) == 1


@pytest.mark.asyncio
async def test_route_group_signed_claim_must_equal_gateway_selected_capability() -> None:
    verifier = SignedPreAdmittedGrantVerifier(signing_secret=_SIGNING_SECRET)
    with pytest.raises(PaidCallAdmissionRejected) as caught:
        await consume_hidden_paid_call_grant_for_route_group(
            _context(
                grant=_signed_grant(_CHAT_CAPABILITY),
                selected_capability=_REMUX_CAPABILITY,
            ),
            server_name=_SERVER,
            tool_name=_TOOL,
            provider=_PROVIDER,
            allowed_capabilities=_GROUP_CAPABILITIES,
            verifier=verifier,
        )
    assert caught.value.reason_code == "PAID_CALL_CAPABILITY_MISMATCH"


@pytest.mark.asyncio
async def test_route_group_requires_server_selected_capability_header() -> None:
    with pytest.raises(PaidCallAdmissionRejected) as caught:
        await consume_hidden_paid_call_grant_for_route_group(
            _context(grant=_signed_grant(_REMUX_CAPABILITY)),
            server_name=_SERVER,
            tool_name=_TOOL,
            provider=_PROVIDER,
            allowed_capabilities=_GROUP_CAPABILITIES,
            verifier=SignedPreAdmittedGrantVerifier(signing_secret=_SIGNING_SECRET),
        )
    assert caught.value.reason_code == "PAID_CALL_SELECTED_CAPABILITY_MISSING"


@pytest.mark.asyncio
async def test_route_group_multiple_matches_fail_closed_before_mcp_call() -> None:
    resolver = _GroupResolver(PaidCallRouteGroupResolution(matched_capabilities=_GROUP_CAPABILITIES))
    interceptor = build_paid_call_grant_interceptor(
        routes=[
            PaidMCPToolRouteGroup(
                _SERVER,
                _TOOL,
                _PROVIDER,
                _GROUP_CAPABILITIES,
            )
        ],
        resolver=resolver,
    )
    request = MCPToolCallRequest(
        name=_TOOL,
        args=dict(_ARGS),
        server_name=_SERVER,
        runtime=SimpleNamespace(
            context={
                "user_id": "owner-1",
                "thread_id": "thread-1",
                "run_id": "run-1",
            }
        ),
    )
    handler_called = False

    async def handler(observed: MCPToolCallRequest) -> MCPToolCallRequest:
        nonlocal handler_called
        handler_called = True
        return observed

    with pytest.raises(PaidCallAdmissionRejected) as caught:
        await interceptor(request, handler)
    assert caught.value.reason_code == "PAID_CALL_CAPABILITY_AMBIGUOUS"
    assert handler_called is False


@pytest.mark.asyncio
async def test_route_group_rejects_resolver_capability_outside_allowed_set() -> None:
    resolver = _GroupResolver(
        PaidCallRouteGroupResolution(
            matched_capabilities=(_CAPABILITY,),
            opaque_grant=_GRANT,
            compensation_binding=_COMPENSATION_BINDING,
        )
    )
    interceptor = build_paid_call_grant_interceptor(
        routes=[
            PaidMCPToolRouteGroup(
                _SERVER,
                _TOOL,
                _PROVIDER,
                _GROUP_CAPABILITIES,
            )
        ],
        resolver=resolver,
    )
    request = MCPToolCallRequest(
        name=_TOOL,
        args=dict(_ARGS),
        server_name=_SERVER,
        runtime=SimpleNamespace(
            context={
                "user_id": "owner-1",
                "thread_id": "thread-1",
                "run_id": "run-1",
            }
        ),
    )

    async def handler(observed: MCPToolCallRequest) -> MCPToolCallRequest:
        return observed

    with pytest.raises(PaidCallAdmissionRejected) as caught:
        await interceptor(request, handler)
    assert caught.value.reason_code == "PAID_CALL_CAPABILITY_NOT_ALLOWED"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_stage", ["grant", "override", "handler"])
async def test_route_group_compensates_every_post_admission_transport_failure(
    failure_stage: str,
) -> None:
    grant = "invalid\ngrant-value" if failure_stage == "grant" else _GRANT
    resolver = _GroupResolver(
        PaidCallRouteGroupResolution(
            matched_capabilities=(_REMUX_CAPABILITY,),
            opaque_grant=grant,
            compensation_binding=_COMPENSATION_BINDING,
        )
    )
    interceptor = build_paid_call_grant_interceptor(
        routes=[
            PaidMCPToolRouteGroup(
                _SERVER,
                _TOOL,
                _PROVIDER,
                _GROUP_CAPABILITIES,
            )
        ],
        resolver=resolver,
    )
    runtime = SimpleNamespace(context={"user_id": "owner-1", "thread_id": "thread-1", "run_id": "run-1"})

    class Request:
        server_name = _SERVER
        name = _TOOL
        args = dict(_ARGS)
        headers = None

        def __init__(self) -> None:
            self.runtime = runtime

        def override(self, **updates: Any) -> Request:
            if failure_stage == "override":
                raise RuntimeError("override failed")
            return MCPToolCallRequest(
                name=self.name,
                args=self.args,
                server_name=self.server_name,
                headers=updates.get("headers"),
                runtime=self.runtime,
            )

    async def handler(observed: MCPToolCallRequest) -> MCPToolCallRequest:
        if failure_stage == "handler":
            raise RuntimeError("handler failed")
        return observed

    with pytest.raises(PaidCallAdmissionRejected) as caught:
        await interceptor(Request(), handler)
    expected = "INVALID_PAID_CALL_GRANT" if failure_stage == "grant" else "PAID_CALL_TRANSPORT_FAILED"
    assert caught.value.reason_code == expected
    assert len(resolver.compensations) == 1
    _, selected, binding, reason = resolver.compensations[0]
    assert selected == _REMUX_CAPABILITY
    assert binding == _COMPENSATION_BINDING
    assert reason == expected


@pytest.mark.asyncio
async def test_route_group_compensation_failure_has_stable_reconciliation_error() -> None:
    resolver = _GroupResolver(
        PaidCallRouteGroupResolution(
            matched_capabilities=(_REMUX_CAPABILITY,),
            opaque_grant="invalid\ngrant-value",
            compensation_binding=_COMPENSATION_BINDING,
        ),
        compensation_fails=True,
    )
    interceptor = build_paid_call_grant_interceptor(
        routes=[
            PaidMCPToolRouteGroup(
                _SERVER,
                _TOOL,
                _PROVIDER,
                _GROUP_CAPABILITIES,
            )
        ],
        resolver=resolver,
    )
    request = MCPToolCallRequest(
        name=_TOOL,
        args=dict(_ARGS),
        server_name=_SERVER,
        runtime=SimpleNamespace(context={"user_id": "owner-1", "thread_id": "thread-1", "run_id": "run-1"}),
    )

    async def handler(observed: MCPToolCallRequest) -> MCPToolCallRequest:
        return observed

    with pytest.raises(PaidCallAdmissionRejected) as caught:
        await interceptor(request, handler)
    assert caught.value.reason_code == "PAID_CALL_TRANSPORT_RECONCILIATION_FAILED"


@pytest.mark.asyncio
async def test_route_group_compensates_mcp_error_result_before_returning_it() -> None:
    resolver = _GroupResolver(
        PaidCallRouteGroupResolution(
            matched_capabilities=(_REMUX_CAPABILITY,),
            opaque_grant=_GRANT,
            compensation_binding=_COMPENSATION_BINDING,
        )
    )
    interceptor = build_paid_call_grant_interceptor(
        routes=[
            PaidMCPToolRouteGroup(
                _SERVER,
                _TOOL,
                _PROVIDER,
                _GROUP_CAPABILITIES,
            )
        ],
        resolver=resolver,
    )
    request = MCPToolCallRequest(
        name=_TOOL,
        args=dict(_ARGS),
        server_name=_SERVER,
        runtime=SimpleNamespace(
            context={
                "user_id": "owner-1",
                "thread_id": "thread-1",
                "run_id": "run-1",
            }
        ),
    )
    error_result = CallToolResult(
        content=[TextContent(type="text", text="synthetic MCP error")],
        isError=True,
    )

    async def handler(_observed: MCPToolCallRequest) -> CallToolResult:
        return error_result

    assert await interceptor(request, handler) is error_result
    assert len(resolver.compensations) == 1
    _, selected, binding, reason = resolver.compensations[0]
    assert selected == _REMUX_CAPABILITY
    assert binding == _COMPENSATION_BINDING
    assert reason == "PAID_CALL_MCP_ERROR_RESULT"


@pytest.mark.asyncio
async def test_route_group_shields_compensation_and_restores_cancellation() -> None:
    resolver = _GroupResolver(
        PaidCallRouteGroupResolution(
            matched_capabilities=(_REMUX_CAPABILITY,),
            opaque_grant=_GRANT,
            compensation_binding=_COMPENSATION_BINDING,
        )
    )
    interceptor = build_paid_call_grant_interceptor(
        routes=[
            PaidMCPToolRouteGroup(
                _SERVER,
                _TOOL,
                _PROVIDER,
                _GROUP_CAPABILITIES,
            )
        ],
        resolver=resolver,
    )
    request = MCPToolCallRequest(
        name=_TOOL,
        args=dict(_ARGS),
        server_name=_SERVER,
        runtime=SimpleNamespace(
            context={
                "user_id": "owner-1",
                "thread_id": "thread-1",
                "run_id": "run-1",
            }
        ),
    )

    handler_started = asyncio.Event()
    never_finishes = asyncio.Event()

    async def handler(_observed: MCPToolCallRequest) -> None:
        handler_started.set()
        await never_finishes.wait()

    task = asyncio.create_task(interceptor(request, handler))
    await handler_started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(resolver.compensations) == 1
    _, selected, binding, reason = resolver.compensations[0]
    assert selected == _REMUX_CAPABILITY
    assert binding == _COMPENSATION_BINDING
    assert reason == "PAID_CALL_TRANSPORT_CANCELLED"


@pytest.mark.asyncio
async def test_route_group_resolves_commit_window_before_restoring_cancellation() -> None:
    class CommitWindowResolver(_GroupResolver):
        def __init__(self) -> None:
            super().__init__(
                PaidCallRouteGroupResolution(
                    matched_capabilities=(_REMUX_CAPABILITY,),
                    opaque_grant=_GRANT,
                    compensation_binding=_COMPENSATION_BINDING,
                )
            )
            self.committed = asyncio.Event()
            self.release_result = asyncio.Event()

        async def reserve_approved_call_for_group(
            self,
            scope: PaidCallRouteGroupScope,
        ) -> PaidCallRouteGroupResolution:
            self.scopes.append(scope)
            self.committed.set()
            await self.release_result.wait()
            return self.result

    resolver = CommitWindowResolver()
    interceptor = build_paid_call_grant_interceptor(
        routes=[
            PaidMCPToolRouteGroup(
                _SERVER,
                _TOOL,
                _PROVIDER,
                _GROUP_CAPABILITIES,
            )
        ],
        resolver=resolver,
    )
    request = MCPToolCallRequest(
        name=_TOOL,
        args=dict(_ARGS),
        server_name=_SERVER,
        runtime=SimpleNamespace(
            context={
                "user_id": "owner-1",
                "thread_id": "thread-1",
                "run_id": "run-1",
            }
        ),
    )
    handler_called = False

    async def handler(_observed: MCPToolCallRequest) -> None:
        nonlocal handler_called
        handler_called = True

    task = asyncio.create_task(interceptor(request, handler))
    await resolver.committed.wait()
    task.cancel()
    resolver.release_result.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert handler_called is False
    assert len(resolver.compensations) == 1
    _, selected, binding, reason = resolver.compensations[0]
    assert selected == _REMUX_CAPABILITY
    assert binding == _COMPENSATION_BINDING
    assert reason == "PAID_CALL_RESERVATION_CANCELLED"


@pytest.mark.asyncio
@pytest.mark.parametrize("handler_outcome", ["exception", "mcp_error"])
async def test_route_group_shields_all_post_admit_compensation_from_cancellation(
    handler_outcome: str,
) -> None:
    class BlockingCompensationResolver(_GroupResolver):
        def __init__(self) -> None:
            super().__init__(
                PaidCallRouteGroupResolution(
                    matched_capabilities=(_REMUX_CAPABILITY,),
                    opaque_grant=_GRANT,
                    compensation_binding=_COMPENSATION_BINDING,
                )
            )
            self.compensation_started = asyncio.Event()
            self.release_compensation = asyncio.Event()

        async def compensate_admitted_call_for_group(
            self,
            scope: PaidCallRouteGroupScope,
            *,
            selected_capability: str,
            compensation_binding: PaidCallRouteGroupCompensationBinding,
            reason_code: str,
        ) -> None:
            self.compensation_started.set()
            await self.release_compensation.wait()
            await super().compensate_admitted_call_for_group(
                scope,
                selected_capability=selected_capability,
                compensation_binding=compensation_binding,
                reason_code=reason_code,
            )

    resolver = BlockingCompensationResolver()
    interceptor = build_paid_call_grant_interceptor(
        routes=[
            PaidMCPToolRouteGroup(
                _SERVER,
                _TOOL,
                _PROVIDER,
                _GROUP_CAPABILITIES,
            )
        ],
        resolver=resolver,
    )
    request = MCPToolCallRequest(
        name=_TOOL,
        args=dict(_ARGS),
        server_name=_SERVER,
        runtime=SimpleNamespace(
            context={
                "user_id": "owner-1",
                "thread_id": "thread-1",
                "run_id": "run-1",
            }
        ),
    )
    error_result = CallToolResult(
        content=[TextContent(type="text", text="synthetic MCP error")],
        isError=True,
    )

    async def handler(_observed: MCPToolCallRequest) -> CallToolResult:
        if handler_outcome == "exception":
            raise RuntimeError("synthetic transport failure")
        return error_result

    task = asyncio.create_task(interceptor(request, handler))
    await resolver.compensation_started.wait()
    task.cancel()
    resolver.release_compensation.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(resolver.compensations) == 1
    _, selected, binding, reason = resolver.compensations[0]
    assert selected == _REMUX_CAPABILITY
    assert binding == _COMPENSATION_BINDING
    assert reason == ("PAID_CALL_TRANSPORT_FAILED" if handler_outcome == "exception" else "PAID_CALL_MCP_ERROR_RESULT")


@pytest.mark.asyncio
async def test_interceptor_strips_untrusted_grant_when_no_approved_call_matches() -> None:
    resolver = _Resolver(None)
    interceptor = build_paid_call_grant_interceptor(
        routes=[PaidMCPToolRoute(_SERVER, _TOOL, _PROVIDER, _CAPABILITY)],
        resolver=resolver,
    )
    runtime = SimpleNamespace(context={"user_id": "owner-1", "thread_id": "thread-1", "run_id": "run-1"})
    request = MCPToolCallRequest(
        name=_TOOL,
        args=dict(_ARGS),
        server_name=_SERVER,
        headers={PAID_CALL_GRANT_HEADER.lower(): "attacker-supplied-grant", "X-Trace": "safe"},
        runtime=runtime,
    )

    async def handler(observed: MCPToolCallRequest) -> MCPToolCallRequest:
        return observed

    observed = await interceptor(request, handler)
    assert observed.headers == {"X-Trace": "safe"}
    assert resolver.scopes


@pytest.mark.asyncio
async def test_interceptor_does_not_resolve_grant_without_trusted_run_scope() -> None:
    resolver = _Resolver(_GRANT)
    interceptor = build_paid_call_grant_interceptor(
        routes=[PaidMCPToolRoute(_SERVER, _TOOL, _PROVIDER, _CAPABILITY)],
        resolver=resolver,
    )
    request = MCPToolCallRequest(
        name=_TOOL,
        args=dict(_ARGS),
        server_name=_SERVER,
        runtime=SimpleNamespace(context={"user_id": "owner-1", "thread_id": "thread-1"}),
    )

    async def handler(observed: MCPToolCallRequest) -> MCPToolCallRequest:
        return observed

    observed = await interceptor(request, handler)
    assert observed.headers is None
    assert resolver.scopes == []


@pytest.mark.asyncio
async def test_reserved_grant_header_is_stripped_from_unrelated_mcp_tools() -> None:
    resolver = _Resolver(_GRANT)
    interceptor = build_paid_call_grant_interceptor(
        routes=[PaidMCPToolRoute(_SERVER, _TOOL, _PROVIDER, _CAPABILITY)],
        resolver=resolver,
    )
    request = MCPToolCallRequest(
        name="unrelated_tool",
        args={},
        server_name="unrelated-server",
        headers={PAID_CALL_GRANT_HEADER: _GRANT},
    )

    async def handler(observed: MCPToolCallRequest) -> MCPToolCallRequest:
        return observed

    observed = await interceptor(request, handler)
    assert observed.headers is None
    assert resolver.scopes == []


def test_hidden_context_reads_grant_from_mcp_meta_headers() -> None:
    assert hidden_paid_call_grant(_context()) == _GRANT


def test_hidden_context_rejects_non_header_safe_grant() -> None:
    with pytest.raises(PaidCallAdmissionRejected, match="INVALID_PAID_CALL_GRANT"):
        hidden_paid_call_grant(_context(grant="opaque-grant-with\nnewline"))


@pytest.mark.asyncio
async def test_missing_grant_is_rejected_before_verifier() -> None:
    verifier = _StaticVerifier()
    with pytest.raises(PaidCallAdmissionRejected, match="PAID_CALL_GRANT_MISSING"):
        await consume_hidden_paid_call_grant(
            _context(grant=None),
            server_name=_SERVER,
            tool_name=_TOOL,
            provider=_PROVIDER,
            capability=_CAPABILITY,
            verifier=verifier,
        )
    assert verifier.calls == []


@pytest.mark.asyncio
async def test_forged_grant_is_rejected_without_exposing_opaque_value() -> None:
    with pytest.raises(PaidCallAdmissionRejected) as caught:
        await consume_hidden_paid_call_grant(
            _context(grant="forged-paid-grant-value"),
            server_name=_SERVER,
            tool_name=_TOOL,
            provider=_PROVIDER,
            capability=_CAPABILITY,
            verifier=_RejectingVerifier(),
        )
    assert caught.value.reason_code == "PAID_CALL_GRANT_INVALID"
    assert "forged-paid-grant-value" not in str(caught.value)


@pytest.mark.asyncio
async def test_expired_grant_is_rejected_after_typed_verification() -> None:
    now = datetime(2026, 8, 2, tzinfo=UTC)
    with pytest.raises(PaidCallAdmissionRejected, match="PAID_CALL_GRANT_EXPIRED"):
        await consume_hidden_paid_call_grant(
            _context(),
            server_name=_SERVER,
            tool_name=_TOOL,
            provider=_PROVIDER,
            capability=_CAPABILITY,
            verifier=_StaticVerifier({"expires_at": now - timedelta(seconds=1)}),
            now=now,
        )


@pytest.mark.asyncio
async def test_expired_signed_grant_does_not_burn_its_jti() -> None:
    now = datetime(2026, 8, 2, tzinfo=UTC)
    grant = _signed_grant(
        _CAPABILITY,
        expires_at=now - timedelta(seconds=1),
    )
    verifier = SignedPreAdmittedGrantVerifier(signing_secret=_SIGNING_SECRET)
    for _attempt in range(2):
        with pytest.raises(PaidCallAdmissionRejected) as caught:
            await consume_hidden_paid_call_grant(
                _context(grant=grant),
                server_name=_SERVER,
                tool_name=_TOOL,
                provider=_PROVIDER,
                capability=_CAPABILITY,
                verifier=verifier,
                now=now,
            )
        assert caught.value.reason_code == "PAID_CALL_GRANT_EXPIRED"


@pytest.mark.asyncio
async def test_provider_binding_failure_does_not_consume_then_success_replays() -> None:
    verifier = SignedPreAdmittedGrantVerifier(signing_secret=_SIGNING_SECRET)
    grant = _signed_grant(_CAPABILITY)
    verified = await verify_hidden_paid_call_grant(
        _context(grant=grant),
        server_name=_SERVER,
        tool_name=_TOOL,
        provider=_PROVIDER,
        capability=_CAPABILITY,
        verifier=verifier,
    )
    with pytest.raises(PaidCallAdmissionRejected) as caught:
        await finalize_verified_paid_call_grant(
            verified,
            provider_request_sha256="f" * 64,
            source_sha256="b" * 64,
            stage_spec_sha256="c" * 64,
            estimated_amount_micros=50,
            currency="CNY",
        )
    assert caught.value.reason_code == "PAID_PROVIDER_REQUEST_MISMATCH"

    consumed = await finalize_verified_paid_call_grant(
        verified,
        provider_request_sha256="a" * 64,
        source_sha256="b" * 64,
        stage_spec_sha256="c" * 64,
        estimated_amount_micros=50,
        currency="CNY",
    )
    assert consumed.jti == verified.jti
    with pytest.raises(PaidCallAdmissionRejected) as replayed:
        await verify_hidden_paid_call_grant(
            _context(grant=grant),
            server_name=_SERVER,
            tool_name=_TOOL,
            provider=_PROVIDER,
            capability=_CAPABILITY,
            verifier=verifier,
        )
    assert replayed.value.reason_code == "PAID_CALL_GRANT_REPLAYED"


@pytest.mark.asyncio
async def test_scope_failure_does_not_consume_signed_jti() -> None:
    verifier = SignedPreAdmittedGrantVerifier(signing_secret=_SIGNING_SECRET)
    grant = _signed_grant(_CAPABILITY)
    with pytest.raises(PaidCallAdmissionRejected) as caught:
        await consume_hidden_paid_call_grant(
            _context(grant=grant),
            server_name=_SERVER,
            tool_name=_TOOL,
            provider=_PROVIDER,
            capability="ocr",
            verifier=verifier,
        )
    assert caught.value.reason_code == "PAID_CALL_SCOPE_MISMATCH"

    verified = await verify_hidden_paid_call_grant(
        _context(grant=grant),
        server_name=_SERVER,
        tool_name=_TOOL,
        provider=_PROVIDER,
        capability=_CAPABILITY,
        verifier=verifier,
    )
    assert verified.capability == _CAPABILITY


@pytest.mark.asyncio
async def test_raw_mcp_tool_name_must_match_the_expected_paid_route() -> None:
    verifier = _StaticVerifier()
    with pytest.raises(PaidCallAdmissionRejected, match="PAID_CALL_TOOL_MISMATCH"):
        await consume_hidden_paid_call_grant(
            _context(tool_name="different_tool"),
            server_name=_SERVER,
            tool_name=_TOOL,
            provider=_PROVIDER,
            capability=_CAPABILITY,
            verifier=verifier,
        )
    assert verifier.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mutation", "reason_code"),
    [
        ({"tool_name": "different_tool"}, "PAID_CALL_SCOPE_MISMATCH"),
        ({"tool_args_sha256": "f" * 64}, "PAID_CALL_ARGUMENTS_MISMATCH"),
        ({"provider": "different-provider"}, "PAID_CALL_SCOPE_MISMATCH"),
        ({"capability": "ocr"}, "PAID_CALL_SCOPE_MISMATCH"),
    ],
)
async def test_claim_must_match_exact_tool_arguments_and_provider_scope(
    mutation: dict[str, Any],
    reason_code: str,
) -> None:
    with pytest.raises(PaidCallAdmissionRejected) as caught:
        await consume_hidden_paid_call_grant(
            _context(),
            server_name=_SERVER,
            tool_name=_TOOL,
            provider=_PROVIDER,
            capability=_CAPABILITY,
            verifier=_StaticVerifier(mutation),
        )
    assert caught.value.reason_code == reason_code


@pytest.mark.asyncio
async def test_route_group_verifier_returns_signed_actual_capability() -> None:
    claim = await consume_hidden_paid_call_grant_for_route_group(
        _context(
            grant=_signed_grant(_REMUX_CAPABILITY),
            selected_capability=_REMUX_CAPABILITY,
        ),
        server_name=_SERVER,
        tool_name=_TOOL,
        provider=_PROVIDER,
        allowed_capabilities=_GROUP_CAPABILITIES,
        verifier=SignedPreAdmittedGrantVerifier(signing_secret=_SIGNING_SECRET),
    )
    assert claim.capability == _REMUX_CAPABILITY


@pytest.mark.asyncio
async def test_route_group_verifier_rejects_signed_capability_outside_allowed_set() -> None:
    with pytest.raises(PaidCallAdmissionRejected) as caught:
        await consume_hidden_paid_call_grant_for_route_group(
            _context(
                grant=_signed_grant(_CAPABILITY),
                selected_capability=_CAPABILITY,
            ),
            server_name=_SERVER,
            tool_name=_TOOL,
            provider=_PROVIDER,
            allowed_capabilities=_GROUP_CAPABILITIES,
            verifier=SignedPreAdmittedGrantVerifier(signing_secret=_SIGNING_SECRET),
        )
    assert caught.value.reason_code == "PAID_CALL_CAPABILITY_NOT_ALLOWED"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("claim_mutation", "reason_code"),
    [
        ({"server_name": "different-server"}, "PAID_CALL_SCOPE_MISMATCH"),
        ({"tool_name": "different-tool"}, "PAID_CALL_SCOPE_MISMATCH"),
        ({"tool_args_sha256": "f" * 64}, "PAID_CALL_ARGUMENTS_MISMATCH"),
        ({"provider": "different-provider"}, "PAID_CALL_SCOPE_MISMATCH"),
    ],
)
async def test_route_group_verifier_requires_exact_transport_scope(
    claim_mutation: dict[str, Any],
    reason_code: str,
) -> None:
    with pytest.raises(PaidCallAdmissionRejected) as caught:
        await consume_hidden_paid_call_grant_for_route_group(
            _context(
                grant=_signed_grant(
                    _REMUX_CAPABILITY,
                    **claim_mutation,
                ),
                selected_capability=_REMUX_CAPABILITY,
            ),
            server_name=_SERVER,
            tool_name=_TOOL,
            provider=_PROVIDER,
            allowed_capabilities=_GROUP_CAPABILITIES,
            verifier=SignedPreAdmittedGrantVerifier(signing_secret=_SIGNING_SECRET),
        )
    assert caught.value.reason_code == reason_code


@pytest.mark.asyncio
async def test_signed_capability_grant_cannot_be_cross_used_as_another_capability() -> None:
    with pytest.raises(PaidCallAdmissionRejected) as caught:
        await consume_hidden_paid_call_grant(
            _context(grant=_signed_grant(_REMUX_CAPABILITY)),
            server_name=_SERVER,
            tool_name=_TOOL,
            provider=_PROVIDER,
            capability=_CHAT_CAPABILITY,
            verifier=SignedPreAdmittedGrantVerifier(signing_secret=_SIGNING_SECRET),
        )
    assert caught.value.reason_code == "PAID_CALL_SCOPE_MISMATCH"


@pytest.mark.asyncio
async def test_replay_is_rejected_by_atomic_verifier_contract() -> None:
    verifier = _ReplayTestDouble()
    first = await consume_hidden_paid_call_grant(
        _context(),
        server_name=_SERVER,
        tool_name=_TOOL,
        provider=_PROVIDER,
        capability=_CAPABILITY,
        verifier=verifier,
    )
    assert first.admission_state == "admitted"
    with pytest.raises(PaidCallAdmissionRejected, match="PAID_CALL_GRANT_REPLAYED"):
        await consume_hidden_paid_call_grant(
            _context(),
            server_name=_SERVER,
            tool_name=_TOOL,
            provider=_PROVIDER,
            capability=_CAPABILITY,
            verifier=verifier,
        )


def test_provider_request_must_match_hashes_currency_and_reserved_maximum() -> None:
    invocation = PaidCallInvocation(
        server_name=_SERVER,
        tool_name=_TOOL,
        tool_args_sha256=canonical_tool_args_sha256(_ARGS),
        provider=_PROVIDER,
        capability=_CAPABILITY,
    )
    claim = _claim(invocation)
    require_provider_request_binding(
        claim,
        provider_request_sha256="a" * 64,
        source_sha256="b" * 64,
        stage_spec_sha256="c" * 64,
        estimated_amount_micros=50,
        currency="CNY",
    )
    with pytest.raises(
        PaidCallAdmissionRejected,
        match="PAID_PROVIDER_AMOUNT_EXCEEDS_RESERVATION",
    ):
        require_provider_request_binding(
            claim,
            provider_request_sha256="a" * 64,
            source_sha256="b" * 64,
            stage_spec_sha256="c" * 64,
            estimated_amount_micros=51,
            currency="CNY",
        )
