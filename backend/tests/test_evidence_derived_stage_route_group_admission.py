from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_mcp_adapters.interceptors import MCPToolCallRequest
from mcp.types import CallToolResult, TextContent

from app.gateway.evidence_paid_call_admission import (
    EVIDENCE_INSPECT_TOOL_NAME,
    EVIDENCE_MCP_CLIENT_NAME,
    MEDIAKIT_DERIVED_STAGE_CAPABILITIES,
    MEDIAKIT_PROVIDER,
    MEDIAKIT_REMUX_CAPABILITY,
    MEDIAKIT_VIDEO_UNDERSTANDING_CHAT_CAPABILITY,
    EvidenceDerivedStageRouteGroupGrantResolver,
    build_evidence_derived_stage_route_group_interceptor,
)
from deerflow.config.database_config import DatabaseConfig
from deerflow.ip_agent.mediakit_video_understanding_pricing import (
    VIDEO_UNDERSTANDING_MODEL_ID,
    VIDEO_UNDERSTANDING_PRICE_VERSION,
)
from deerflow.mcp.paid_admission import (
    PAID_CALL_GRANT_HEADER,
    PAID_CALL_SELECTED_CAPABILITY_HEADER,
    PaidCallAdmissionRejected,
    PaidCallRouteGroupInvocation,
    PaidCallRouteGroupScope,
    SignedPreAdmittedGrantVerifier,
    canonical_tool_args_sha256,
)
from deerflow.persistence.engine import (
    close_engine,
    get_session_factory,
    init_engine_from_config,
)
from deerflow.persistence.personal_ip_paid_calls import (
    EVIDENCE_MANAGED_REMUX_OPERATOR_CAP_POLICY_VERSION,
    EVIDENCE_VIDEO_UNDERSTANDING_CHAT_OPERATOR_CAP_POLICY_VERSION,
    OperatorCappedEvidenceStagePolicy,
    PersonalIPPaidCallRepository,
)

NOW = datetime(2026, 8, 3, 20, 0, tzinfo=UTC)
SECRET = "derived-stage-route-group-secret-000000000000000000"
ARGS = {
    "video_refs": ["https://www.douyin.com/video/7658501922794432731"],
    "reference_context": "standalone_reference",
    "purpose": "benchmark",
    "analysis_depth": "full",
    "max_frames": 8,
    "account_binding_receipt": None,
}
SOURCE_SHA = "a" * 64
REMUX_STAGE_SHA = "b" * 64
CHAT_STAGE_SHA = "c" * 64
REMUX_REQUEST_SHA = "d" * 64
CHAT_REQUEST_SHA = "e" * 64
APPROVAL_SHA = "f" * 64
REMUX_LIMIT = 100_000
CHAT_LIMIT = 900_000
MAX_DURATION = 120_000


def _policies() -> tuple[OperatorCappedEvidenceStagePolicy, ...]:
    return (
        OperatorCappedEvidenceStagePolicy(
            capability=MEDIAKIT_REMUX_CAPABILITY,
            policy_version=EVIDENCE_MANAGED_REMUX_OPERATOR_CAP_POLICY_VERSION,
            local_admission_limit_micros=REMUX_LIMIT,
            max_source_duration_millis=MAX_DURATION,
        ),
        OperatorCappedEvidenceStagePolicy(
            capability=MEDIAKIT_VIDEO_UNDERSTANDING_CHAT_CAPABILITY,
            policy_version=EVIDENCE_VIDEO_UNDERSTANDING_CHAT_OPERATOR_CAP_POLICY_VERSION,
            local_admission_limit_micros=CHAT_LIMIT,
            max_source_duration_millis=MAX_DURATION,
        ),
    )


async def _repository(tmp_path: Any) -> PersonalIPPaidCallRepository:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path / "db")))
    session_factory = get_session_factory()
    assert session_factory is not None
    return PersonalIPPaidCallRepository(session_factory)


async def _approved_stage(
    repository: PersonalIPPaidCallRepository,
    *,
    capability: str,
    request_key: str,
) -> dict[str, Any]:
    if capability == MEDIAKIT_REMUX_CAPABILITY:
        policy_version = EVIDENCE_MANAGED_REMUX_OPERATOR_CAP_POLICY_VERSION
        local_limit = REMUX_LIMIT
        stage_sha = REMUX_STAGE_SHA
        provider_request_sha = REMUX_REQUEST_SHA
        model = "volcengine-mediakit-remux-https-ingress-v1"
        sku = "remux-video"
    else:
        policy_version = EVIDENCE_VIDEO_UNDERSTANDING_CHAT_OPERATOR_CAP_POLICY_VERSION
        local_limit = CHAT_LIMIT
        stage_sha = CHAT_STAGE_SHA
        provider_request_sha = CHAT_REQUEST_SHA
        model = VIDEO_UNDERSTANDING_MODEL_ID
        sku = "ark-input-output-token"
    requested = await repository.request_call(
        owner_user_id="owner-1",
        request_key=request_key,
        scope_kind="run",
        thread_id="thread-1",
        origin_run_id="origin-run-1",
        server_name=EVIDENCE_MCP_CLIENT_NAME,
        tool_name=EVIDENCE_INSPECT_TOOL_NAME,
        tool_args_sha256=canonical_tool_args_sha256(ARGS),
        provider=MEDIAKIT_PROVIDER,
        capability=capability,
        model=model,
        sku=sku,
        provider_label="火山引擎 AI MediaKit",
        capability_label=("托管 HTTPS 转封装" if capability == MEDIAKIT_REMUX_CAPABILITY else "视频理解 Chat"),
        object_ref_label="参考视频 aaaaaaaa…aaaaaaaa",
        source_duration_millis=70_867,
        source_sha256=SOURCE_SHA,
        stage_digest=stage_sha,
        provider_request_sha256=provider_request_sha,
        maximum_amount_micros=local_limit,
        currency="CNY",
        billing_basis="Owner 接受本地风险上限；该值不是供应商报价或账单封顶",
        policy_version=policy_version,
        price_version=("mediakit-remux-public-tariff-2026-08-03" if capability == MEDIAKIT_REMUX_CAPABILITY else VIDEO_UNDERSTANDING_PRICE_VERSION),
        provider_input_attested=False,
        evidence_coverage="partial",
        warning_code="provider_content_hash_unattested",
        expires_at=NOW + timedelta(minutes=15),
        price_status="operator_capped",
        now=NOW,
    )
    approved = await repository.approve(
        requested["id"],
        owner_user_id="owner-1",
        event_key=f"approve:{request_key}",
        expected_request_digest=requested["request_digest"],
        approval_digest=APPROVAL_SHA,
        expected_event_count=1,
        now=NOW + timedelta(seconds=1),
    )
    assert approved is not None
    return approved


def _request(
    *,
    server_name: str = EVIDENCE_MCP_CLIENT_NAME,
    tool_name: str = EVIDENCE_INSPECT_TOOL_NAME,
) -> MCPToolCallRequest:
    return MCPToolCallRequest(
        name=tool_name,
        args=dict(ARGS),
        server_name=server_name,
        runtime=SimpleNamespace(
            context={
                "user_id": "owner-1",
                "thread_id": "thread-1",
                "run_id": "execution-run-1",
            }
        ),
    )


def test_route_group_rejects_cross_bound_capability_policy() -> None:
    policies = list(_policies())
    policies[0] = OperatorCappedEvidenceStagePolicy(
        capability=MEDIAKIT_REMUX_CAPABILITY,
        policy_version=EVIDENCE_VIDEO_UNDERSTANDING_CHAT_OPERATOR_CAP_POLICY_VERSION,
        local_admission_limit_micros=REMUX_LIMIT,
        max_source_duration_millis=MAX_DURATION,
    )
    with pytest.raises(ValueError, match="capability and policy binding"):
        EvidenceDerivedStageRouteGroupGrantResolver(
            repository=object(),  # type: ignore[arg-type]
            trusted_stage_policies=policies,
            signing_secret=SECRET,
            capability_configured=lambda _capability: True,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("capability", "expected_limit"),
    [
        (MEDIAKIT_REMUX_CAPABILITY, REMUX_LIMIT),
        (MEDIAKIT_VIDEO_UNDERSTANDING_CHAT_CAPABILITY, CHAT_LIMIT),
    ],
)
async def test_shared_route_selects_and_signs_only_the_approved_stage_without_provider_call(
    tmp_path: Any,
    capability: str,
    expected_limit: int,
) -> None:
    repository = await _repository(tmp_path)
    configuration_probes: list[str] = []
    try:
        approved = await _approved_stage(
            repository,
            capability=capability,
            request_key=f"approved-{capability}",
        )
        interceptor = build_evidence_derived_stage_route_group_interceptor(
            repository=repository,
            trusted_stage_policies=_policies(),
            signing_secret=SECRET,
            capability_configured=lambda candidate: configuration_probes.append(candidate) or True,
            clock=lambda: NOW + timedelta(seconds=2),
        )

        async def handler(observed: MCPToolCallRequest) -> MCPToolCallRequest:
            return observed

        observed = await interceptor(_request(), handler)
        assert observed.args == ARGS
        assert observed.headers is not None
        assert observed.headers[PAID_CALL_SELECTED_CAPABILITY_HEADER] == capability
        grant = observed.headers[PAID_CALL_GRANT_HEADER]
        verifier = SignedPreAdmittedGrantVerifier(signing_secret=SECRET)
        claim = await verifier.verify(
            grant,
            PaidCallRouteGroupInvocation(
                server_name=EVIDENCE_MCP_CLIENT_NAME,
                tool_name=EVIDENCE_INSPECT_TOOL_NAME,
                tool_args_sha256=canonical_tool_args_sha256(ARGS),
                provider=MEDIAKIT_PROVIDER,
                allowed_capabilities=MEDIAKIT_DERIVED_STAGE_CAPABILITIES,
                selected_capability=capability,
            ),
        )
        assert claim.capability == capability
        assert claim.maximum_amount_micros == expected_limit
        assert claim.call_id == approved["id"]
        current = await repository.get(approved["id"], owner_user_id="owner-1")
        assert current is not None
        assert current["status"] == "admitted"
        assert current["capability"] == capability
        assert current["price_status"] == "operator_capped"
        if capability == MEDIAKIT_VIDEO_UNDERSTANDING_CHAT_CAPABILITY:
            assert current["model"] == VIDEO_UNDERSTANDING_MODEL_ID
            assert current["price_version"] == VIDEO_UNDERSTANDING_PRICE_VERSION
        serialized = json.dumps(current, ensure_ascii=False)
        assert grant not in serialized
        assert "derived-stage-route-group-secret" not in serialized
        assert configuration_probes == list(MEDIAKIT_DERIVED_STAGE_CAPABILITIES)
    finally:
        await close_engine()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "capability",
    [
        MEDIAKIT_REMUX_CAPABILITY,
        MEDIAKIT_VIDEO_UNDERSTANDING_CHAT_CAPABILITY,
    ],
)
async def test_handler_failure_compensates_exact_selected_stage_without_provider_call(
    tmp_path: Any,
    capability: str,
) -> None:
    repository = await _repository(tmp_path)
    try:
        approved = await _approved_stage(
            repository,
            capability=capability,
            request_key=f"compensate-{capability}",
        )
        interceptor = build_evidence_derived_stage_route_group_interceptor(
            repository=repository,
            trusted_stage_policies=_policies(),
            signing_secret=SECRET,
            capability_configured=lambda _candidate: True,
            clock=lambda: NOW + timedelta(seconds=2),
        )

        async def handler(_observed: MCPToolCallRequest) -> MCPToolCallRequest:
            raise RuntimeError("synthetic transport failure before any executor")

        with pytest.raises(PaidCallAdmissionRejected) as caught:
            await interceptor(_request(), handler)
        assert caught.value.reason_code == "PAID_CALL_TRANSPORT_FAILED"
        current = await repository.get(approved["id"], owner_user_id="owner-1")
        assert current is not None
        assert current["status"] == "reconciliation_required"
        assert current["capability"] == capability
        assert current["events"][-1]["event_type"] == "reconciliation_required"
        assert current["events"][-1]["reason_code"] == ("provider_execution_outcome_unresolved")
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_mcp_error_result_compensates_without_provider_call(
    tmp_path: Any,
) -> None:
    repository = await _repository(tmp_path)
    try:
        approved = await _approved_stage(
            repository,
            capability=MEDIAKIT_REMUX_CAPABILITY,
            request_key="mcp-error-result-compensation",
        )
        interceptor = build_evidence_derived_stage_route_group_interceptor(
            repository=repository,
            trusted_stage_policies=_policies(),
            signing_secret=SECRET,
            capability_configured=lambda _candidate: True,
            clock=lambda: NOW + timedelta(seconds=2),
        )
        error_result = CallToolResult(
            content=[TextContent(type="text", text="derived executor is not wired")],
            isError=True,
        )

        async def handler(_observed: MCPToolCallRequest) -> CallToolResult:
            return error_result

        assert await interceptor(_request(), handler) is error_result
        current = await repository.get(approved["id"], owner_user_id="owner-1")
        assert current is not None
        assert current["status"] == "reconciliation_required"
        assert current["capability"] == MEDIAKIT_REMUX_CAPABILITY
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_cancel_after_repository_commit_compensates_exact_stage(
    tmp_path: Any,
) -> None:
    repository = await _repository(tmp_path)

    class CommitWindowRepository:
        def __init__(self) -> None:
            self.committed = asyncio.Event()
            self.release_result = asyncio.Event()

        async def admit_next_operator_capped_evidence_stage_exact(
            self,
            **kwargs: Any,
        ) -> dict[str, Any] | None:
            row = await repository.admit_next_operator_capped_evidence_stage_exact(
                **kwargs,
            )
            self.committed.set()
            await self.release_result.wait()
            return row

        async def mark_operator_capped_evidence_stage_invocation_unresolved(
            self,
            **kwargs: Any,
        ) -> dict[str, Any] | None:
            return await repository.mark_operator_capped_evidence_stage_invocation_unresolved(
                **kwargs,
            )

    commit_window_repository = CommitWindowRepository()
    try:
        approved = await _approved_stage(
            repository,
            capability=MEDIAKIT_REMUX_CAPABILITY,
            request_key="cancel-after-commit",
        )
        interceptor = build_evidence_derived_stage_route_group_interceptor(
            repository=commit_window_repository,
            trusted_stage_policies=_policies(),
            signing_secret=SECRET,
            capability_configured=lambda _candidate: True,
            clock=lambda: NOW + timedelta(seconds=2),
        )
        handler_called = False

        async def handler(_observed: MCPToolCallRequest) -> None:
            nonlocal handler_called
            handler_called = True

        task = asyncio.create_task(interceptor(_request(), handler))
        await commit_window_repository.committed.wait()
        task.cancel()
        commit_window_repository.release_result.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert handler_called is False
        current = await repository.get(approved["id"], owner_user_id="owner-1")
        assert current is not None
        assert current["status"] == "reconciliation_required"
        assert current["capability"] == MEDIAKIT_REMUX_CAPABILITY
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_zero_and_disabled_matches_do_not_consume_an_approval(
    tmp_path: Any,
) -> None:
    repository = await _repository(tmp_path)
    try:
        approved = await _approved_stage(
            repository,
            capability=MEDIAKIT_VIDEO_UNDERSTANDING_CHAT_CAPABILITY,
            request_key="disabled-chat",
        )
        interceptor = build_evidence_derived_stage_route_group_interceptor(
            repository=repository,
            trusted_stage_policies=_policies(),
            signing_secret=SECRET,
            capability_configured=lambda capability: capability == MEDIAKIT_REMUX_CAPABILITY,
            clock=lambda: NOW + timedelta(seconds=2),
        )

        async def handler(observed: MCPToolCallRequest) -> MCPToolCallRequest:
            return observed

        observed = await interceptor(_request(), handler)
        assert observed.headers is None
        current = await repository.get(approved["id"], owner_user_id="owner-1")
        assert current is not None
        assert current["status"] == "approved"
        assert current["execution_run_id"] is None
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_legacy_operator_route_is_an_explicit_non_match(
    tmp_path: Any,
) -> None:
    repository = await _repository(tmp_path)
    try:
        approved = await _approved_stage(
            repository,
            capability=MEDIAKIT_REMUX_CAPABILITY,
            request_key="legacy-route-must-not-match",
        )
        resolver = EvidenceDerivedStageRouteGroupGrantResolver(
            repository=repository,
            trusted_stage_policies=_policies(),
            signing_secret=SECRET,
            capability_configured=lambda _capability: True,
            clock=lambda: NOW + timedelta(seconds=2),
        )
        resolution = await resolver.reserve_approved_call_for_group(
            PaidCallRouteGroupScope(
                owner_user_id="owner-1",
                thread_id="thread-1",
                run_id="execution-run-1",
                server_name="ip-agent-operator",
                tool_name="managed_https_ingress_remux",
                tool_args_sha256=canonical_tool_args_sha256(ARGS),
                provider=MEDIAKIT_PROVIDER,
                allowed_capabilities=MEDIAKIT_DERIVED_STAGE_CAPABILITIES,
            )
        )
        assert resolution.matched_capabilities == ()
        assert resolution.opaque_grant is None
        current = await repository.get(approved["id"], owner_user_id="owner-1")
        assert current is not None
        assert current["status"] == "approved"
        assert current["execution_run_id"] is None
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_two_approved_stages_are_ambiguous_before_any_state_change(
    tmp_path: Any,
) -> None:
    repository = await _repository(tmp_path)
    try:
        approved = [
            await _approved_stage(
                repository,
                capability=capability,
                request_key=f"ambiguous-{capability}",
            )
            for capability in MEDIAKIT_DERIVED_STAGE_CAPABILITIES
        ]
        interceptor = build_evidence_derived_stage_route_group_interceptor(
            repository=repository,
            trusted_stage_policies=_policies(),
            signing_secret=SECRET,
            capability_configured=lambda _capability: True,
            clock=lambda: NOW + timedelta(seconds=2),
        )
        handler_called = False

        async def handler(observed: MCPToolCallRequest) -> MCPToolCallRequest:
            nonlocal handler_called
            handler_called = True
            return observed

        with pytest.raises(PaidCallAdmissionRejected) as caught:
            await interceptor(_request(), handler)
        assert caught.value.reason_code == "PAID_CALL_CAPABILITY_AMBIGUOUS"
        assert handler_called is False
        for row in approved:
            current = await repository.get(row["id"], owner_user_id="owner-1")
            assert current is not None
            assert current["status"] == "approved"
            assert current["execution_run_id"] is None
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_compensation_is_idempotent_across_a_later_gateway_clock(
    tmp_path: Any,
) -> None:
    repository = await _repository(tmp_path)
    observed_times = iter(
        (
            NOW + timedelta(seconds=2),
            NOW + timedelta(seconds=3),
            NOW + timedelta(seconds=9),
        )
    )
    try:
        approved = await _approved_stage(
            repository,
            capability=MEDIAKIT_REMUX_CAPABILITY,
            request_key="idempotent-compensation",
        )
        resolver = EvidenceDerivedStageRouteGroupGrantResolver(
            repository=repository,
            trusted_stage_policies=_policies(),
            signing_secret=SECRET,
            capability_configured=lambda _capability: True,
            clock=lambda: next(observed_times),
        )
        scope = PaidCallRouteGroupScope(
            owner_user_id="owner-1",
            thread_id="thread-1",
            run_id="execution-run-1",
            server_name=EVIDENCE_MCP_CLIENT_NAME,
            tool_name=EVIDENCE_INSPECT_TOOL_NAME,
            tool_args_sha256=canonical_tool_args_sha256(ARGS),
            provider=MEDIAKIT_PROVIDER,
            allowed_capabilities=MEDIAKIT_DERIVED_STAGE_CAPABILITIES,
        )
        resolution = await resolver.reserve_approved_call_for_group(scope)
        assert resolution.matched_capabilities == (MEDIAKIT_REMUX_CAPABILITY,)
        assert resolution.compensation_binding is not None
        await resolver.compensate_admitted_call_for_group(
            scope,
            selected_capability=MEDIAKIT_REMUX_CAPABILITY,
            compensation_binding=resolution.compensation_binding,
            reason_code="PAID_CALL_TRANSPORT_FAILED",
        )
        await resolver.compensate_admitted_call_for_group(
            scope,
            selected_capability=MEDIAKIT_REMUX_CAPABILITY,
            compensation_binding=resolution.compensation_binding,
            reason_code="PAID_CALL_TRANSPORT_FAILED",
        )
        current = await repository.get(approved["id"], owner_user_id="owner-1")
        assert current is not None
        assert current["status"] == "reconciliation_required"
        assert current["event_count"] == 5
        assert [event["event_type"] for event in current["events"]].count("reconciliation_required") == 1
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_compensation_is_bound_to_exact_call_id_and_admission_jti(
    tmp_path: Any,
) -> None:
    repository = await _repository(tmp_path)
    try:
        first = await _approved_stage(
            repository,
            capability=MEDIAKIT_REMUX_CAPABILITY,
            request_key="exact-compensation-first",
        )
        resolver = EvidenceDerivedStageRouteGroupGrantResolver(
            repository=repository,
            trusted_stage_policies=_policies(),
            signing_secret=SECRET,
            capability_configured=lambda _capability: True,
            clock=lambda: NOW + timedelta(seconds=2),
        )
        scope = PaidCallRouteGroupScope(
            owner_user_id="owner-1",
            thread_id="thread-1",
            run_id="execution-run-1",
            server_name=EVIDENCE_MCP_CLIENT_NAME,
            tool_name=EVIDENCE_INSPECT_TOOL_NAME,
            tool_args_sha256=canonical_tool_args_sha256(ARGS),
            provider=MEDIAKIT_PROVIDER,
            allowed_capabilities=MEDIAKIT_DERIVED_STAGE_CAPABILITIES,
        )
        first_resolution = await resolver.reserve_approved_call_for_group(scope)
        assert first_resolution.compensation_binding is not None

        second = await _approved_stage(
            repository,
            capability=MEDIAKIT_REMUX_CAPABILITY,
            request_key="exact-compensation-second",
        )
        second_resolution = await resolver.reserve_approved_call_for_group(scope)
        assert second_resolution.compensation_binding is not None
        assert first_resolution.compensation_binding.call_id != second_resolution.compensation_binding.call_id

        with pytest.raises(
            RuntimeError,
            match="did not find the admitted stage",
        ):
            await resolver.compensate_admitted_call_for_group(
                scope,
                selected_capability=MEDIAKIT_REMUX_CAPABILITY,
                compensation_binding=(
                    first_resolution.compensation_binding.model_copy(
                        update={"admission_jti_sha256": "0" * 64},
                    )
                ),
                reason_code="PAID_CALL_TRANSPORT_FAILED",
            )
        first_before = await repository.get(first["id"], owner_user_id="owner-1")
        second_before = await repository.get(second["id"], owner_user_id="owner-1")
        assert first_before is not None
        assert second_before is not None
        assert first_before["status"] == "admitted"
        assert second_before["status"] == "admitted"

        await resolver.compensate_admitted_call_for_group(
            scope,
            selected_capability=MEDIAKIT_REMUX_CAPABILITY,
            compensation_binding=first_resolution.compensation_binding,
            reason_code="PAID_CALL_TRANSPORT_FAILED",
        )
        first_current = await repository.get(first["id"], owner_user_id="owner-1")
        second_current = await repository.get(second["id"], owner_user_id="owner-1")
        assert first_current is not None
        assert second_current is not None
        assert first_current["status"] == "reconciliation_required"
        assert second_current["status"] == "admitted"
    finally:
        await close_engine()
